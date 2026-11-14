"""Resolve one canonical assigned Issue to an ACTIVE local Dispatch authority."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from multica_state_bundle.bundle_store import BundleStore, BundleError
from multica_orchestrator_cli.common.dispatch_runtime import DispatchRuntimeError, read_activation_fence, read_active_release, read_runtime_binding
from multica_orchestrator_cli.common.profile_session import ProfileSession, resolve_profile_session
from multica_orchestrator_cli.common.provider_readback import ProviderReadbackError, TERMINAL_ISSUE_STATES, current_leader_run, issue_object, issue_snapshot, run_objects, runtime_object
from multica_orchestrator_cli.common.runtime_capability import RuntimeCapabilityEvidenceError, runtime_capabilities, runtime_capability_revision


class DispatchContextError(ValueError):
    """Live readback cannot prove a stable Leader admission context."""


@dataclass(frozen=True)
class ResolvedDispatchContext:
    profile: str
    workspace_ref: str
    server_kind: str
    server_ref: str
    account_ref: str
    issue_ref: str
    issue_key: str
    issue_url: str | None
    issue_snapshot: str
    project_ref: str
    project_key: str
    repository_ref: str
    project_binding_digest: str
    dispatch_contract_digest: str
    active_release_digest: str
    project_bundle_manifest_digest: str
    release_candidate_digest: str
    runtime_alias: str
    runtime_ref: str
    daemon_ref: str
    squad_ref: str
    leader_ref: str
    work_type: str
    leader_run_ref: str
    control_db: Path
    release_root: Path
    cas_root: Path
    binding: Mapping[str, Any]

    def public(self) -> dict[str, Any]:
        return {
            "issue_ref": self.issue_ref,
            "issue_key": self.issue_key,
            "project_ref": self.project_ref,
            "project_key": self.project_key,
            "repository_ref": self.repository_ref,
            "project_binding_digest": self.project_binding_digest,
            "dispatch_contract_digest": self.dispatch_contract_digest,
            "active_release_digest": self.active_release_digest,
            "project_bundle_manifest_digest": self.project_bundle_manifest_digest,
            "release_candidate_digest": self.release_candidate_digest,
            "runtime_alias": self.runtime_alias,
            "runtime_ref": self.runtime_ref,
            "daemon_ref": self.daemon_ref,
            "squad_ref": self.squad_ref,
            "leader_ref": self.leader_ref,
            "work_type": self.work_type,
            "leader_run_ref": self.leader_run_ref,
        }


def _record(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DispatchContextError(f"PROVIDER_READBACK_UNSUPPORTED: {label} must be an object")
    return value


def _id(value: Mapping[str, Any], label: str) -> str:
    result = value.get("id", value.get(f"{label}_id"))
    if not isinstance(result, str) or not result:
        raise DispatchContextError(f"PROVIDER_READBACK_UNSUPPORTED: {label} lacks an id")
    return result




def _server_identity(session: ProfileSession, *, squad_ref: str, leader_ref: str) -> None:
    squad = _record(session.read_json(["squad", "get", squad_ref], workspace=True), "Squad readback")
    leader = _record(session.read_json(["agent", "get", leader_ref], workspace=True), "Agent readback")
    if _id(squad, "squad") != squad_ref or _id(leader, "agent") != leader_ref:
        raise DispatchContextError("DISPATCH_CONTEXT_CHANGED")


def _project(session: ProfileSession, project_ref: str) -> Mapping[str, Any]:
    project = _record(session.read_json(["project", "get", project_ref], workspace=True), "Project readback")
    if _id(project, "project") != project_ref:
        raise DispatchContextError("ISSUE_PROJECT_REQUIRED")
    return project


def _bundle_context(binding: Mapping[str, Any], active: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    release = _record(active["release"], "ACTIVE release")
    try:
        store = BundleStore(Path(str(binding["cas_root"])))
        closure = store.closure("project-binding", str(release["project_bundle_manifest_digest"]))
    except (BundleError, OSError, KeyError, TypeError) as error:
        raise DispatchContextError("DISPATCH_RUNTIME_NOT_ACTIVATED") from error
    if [bundle.stage for bundle in closure] != ["workspace-foundation", "server-orchestration", "project-binding"]:
        raise DispatchContextError("DISPATCH_RUNTIME_NOT_ACTIVATED")
    _, server, project = closure
    project_binding = _record(project.artifacts.get("project-binding"), "Project binding")
    verification = _record(project.artifacts.get("project-verification-spec"), "Project verification")
    server_spec = _record(server.artifacts.get("server-verification-spec"), "Server verification")
    if project_binding.get("project_key") != binding["project_key"] or project_binding.get("project_ref") != binding["project_ref"]:
        raise DispatchContextError("DISPATCH_CONTEXT_CHANGED")
    if verification.get("dispatch_contract_digest") != release.get("dispatch_contract_digest") or verification.get("project_key") != binding["project_key"]:
        raise DispatchContextError("DISPATCH_CONTEXT_CHANGED")
    if release.get("project_binding_digest") != project.manifest["artifacts"]["project-binding"]["digest"]:
        raise DispatchContextError("DISPATCH_CONTEXT_CHANGED")
    return project_binding, verification, server_spec


def _squad(server_spec: Mapping[str, Any], assignee_ref: str) -> tuple[str, Mapping[str, Any]]:
    squads = _record(server_spec.get("squads"), "Server squads")
    matches = [(name, value) for name, value in squads.items() if isinstance(value, Mapping) and value.get("squad_ref") == assignee_ref]
    if len(matches) != 1 or matches[0][0] not in {"feature", "fix"}:
        raise DispatchContextError("ISSUE_CLASSIFICATION_REQUIRED")
    work_type, squad = matches[0]
    leader = squad.get("leader_ref")
    agents = _record(server_spec.get("agents"), "Server agents")
    workflow = _record(agents.get("workflow-leader"), "workflow leader")
    if leader != workflow.get("agent_ref"):
        raise DispatchContextError("DISPATCH_CONTEXT_CHANGED")
    return work_type, squad


def _runtime(session: ProfileSession, binding: Mapping[str, Any]) -> None:
    runtime = runtime_object(session.read_json(["runtime", "list"], workspace=True), str(binding["runtime_ref"]))
    if runtime.get("status") != "online" or runtime.get("daemon_id", runtime.get("daemon_ref")) != binding["daemon_ref"]:
        raise DispatchContextError("RUNTIME_CAPABILITY_MISMATCH")
    try:
        if "local-worktree-v1" not in runtime_capabilities(runtime) or runtime_capability_revision(runtime) is None:
            raise DispatchContextError("RUNTIME_CAPABILITY_MISMATCH")
    except RuntimeCapabilityEvidenceError as error:
        raise DispatchContextError("RUNTIME_CAPABILITY_MISMATCH") from error


def resolve_dispatch_context(profile: str, workspace: str | None, issue: str, *, run_ref: str | None = None) -> ResolvedDispatchContext:
    """Resolve exactly one live Leader evaluation context without creating state."""
    try:
        session = resolve_profile_session(profile, workspace)
        first_issue = issue_object(session.read_json(["issue", "get", issue], workspace=True))
        if issue != first_issue["id"] and issue != first_issue["identifier"]:
            raise DispatchContextError("ISSUE_IDENTITY_MISMATCH")
        if first_issue["status"] in TERMINAL_ISSUE_STATES:
            raise DispatchContextError("ISSUE_TERMINAL_NO_ACTION")
        if first_issue["workspace_id"] != session.workspace_ref:
            raise DispatchContextError("ISSUE_IDENTITY_MISMATCH")
        project_ref = first_issue.get("project_id")
        if not isinstance(project_ref, str) or not project_ref:
            raise DispatchContextError("ISSUE_PROJECT_REQUIRED")
        binding = read_runtime_binding(session.server_kind, session.server_ref, session.workspace_ref, project_ref)
        if read_activation_fence(Path(str(binding["release_root"]))) is not None:
            raise DispatchContextError("DISPATCH_ACTIVATION_PENDING")
        active = read_active_release(Path(str(binding["cas_root"])), str(binding["project_key"]))
        release = _record(active["release"], "ACTIVE release")
        project = _project(session, project_ref)
        project_binding, verification, server_spec = _bundle_context(binding, active)
        if _id(project, "project") != binding["project_ref"] or release.get("project_key") != binding["project_key"]:
            raise DispatchContextError("DISPATCH_CONTEXT_CHANGED")
        work_type, squad = _squad(server_spec, first_issue["assignee_id"])
        if squad.get("leader_ref") != server_spec["agents"]["workflow-leader"]["agent_ref"]:
            raise DispatchContextError("DISPATCH_CONTEXT_CHANGED")
        _server_identity(session, squad_ref=str(squad["squad_ref"]), leader_ref=str(squad["leader_ref"]))
        _runtime(session, binding)
        runs = run_objects(session.read_json(["issue", "runs", first_issue["id"]], workspace=True))
        leader = current_leader_run(runs, issue_id=first_issue["id"], leader_ref=str(squad["leader_ref"]), runtime_ref=str(binding["runtime_ref"]), run_ref=run_ref)
        closing = issue_object(session.read_json(["issue", "get", first_issue["id"]], workspace=True))
        if issue_snapshot(closing) != issue_snapshot(first_issue):
            raise DispatchContextError("DISPATCH_CONTEXT_CHANGED")
        current = read_active_release(Path(str(binding["cas_root"])), str(binding["project_key"]))
        if current["release_digest"] != active["release_digest"]:
            raise DispatchContextError("DISPATCH_CONTEXT_CHANGED")
        return ResolvedDispatchContext(
            profile=profile, workspace_ref=session.workspace_ref, server_kind=session.server_kind, server_ref=session.server_ref,
            account_ref=session.account_ref, issue_ref=first_issue["id"], issue_key=first_issue["identifier"],
            issue_url=first_issue.get("url") if isinstance(first_issue.get("url"), str) else None,
            issue_snapshot=issue_snapshot(first_issue), project_ref=project_ref, project_key=str(binding["project_key"]),
            repository_ref=str(binding["repository_ref"]), project_binding_digest=str(release["project_binding_digest"]),
            dispatch_contract_digest=str(release["dispatch_contract_digest"]), active_release_digest=str(active["release_digest"]),
            project_bundle_manifest_digest=str(release["project_bundle_manifest_digest"]), release_candidate_digest=str(release["release_candidate_digest"]),
            runtime_alias=str(binding["runtime_alias"]), runtime_ref=str(binding["runtime_ref"]), daemon_ref=str(binding["daemon_ref"]),
            squad_ref=str(squad["squad_ref"]), leader_ref=str(squad["leader_ref"]), work_type=work_type,
            leader_run_ref=str(leader["id"]), control_db=Path(str(binding["control_db"])), release_root=Path(str(binding["release_root"])),
            cas_root=Path(str(binding["cas_root"])), binding=binding,
        )
    except (DispatchContextError, DispatchRuntimeError, ProviderReadbackError) as error:
        raise DispatchContextError(str(error)) from error
