#!/usr/bin/env python3
"""Resolve upstream bundles, a portable Project request, and live readbacks into ProjectBindingInput.v12."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from binding_common import InputError, read_json, records, require_digest, validate_portable_config
from multica_state_bundle.bundle_store import BundleStore
from multica_state_bundle.identities import (
    DeploymentIndex,
    StagePointers,
    StateError,
    allocate_run,
    canonical_json,
    default_state_root,
    digest_bytes,
    project_key,
    repository_identity,
    write_resolution,
)
from multica_state_bundle.storage import atomic_json
from multica_orchestrator_cli.common.profile_session import ProfileSession, resolve_profile_session
from multica_orchestrator_cli.common.runtime_capability import runtime_capability_revision
from multica_orchestrator_cli.common.runtime_activation import select_local_directory_resource

REQUEST_SCHEMA = "multica-orchestrator-nail-down.project-binding-request.v6"
SNAPSHOT_SCHEMA = "multica-orchestrator-nail-down.project-binding-snapshot.v6"

def existing_reference(repository_root: Path, candidates: tuple[str, ...]) -> str:
    for candidate in candidates:
        if (repository_root / candidate).exists():
            return candidate
    return "."


def render_portable_configs(
    run_root: Path,
    repository_root: Path,
    repository_url: str,
    project_subpath: str,
    request: Mapping[str, Any],
    server_handoff: Mapping[str, Any],
) -> dict[str, Path]:
    templates = Path(__file__).resolve().parents[4].parent / "multica-orchestrator-nail-down" / "templates"
    policy = request["policy"]
    commands = request["command_profiles"][policy["repository_command_profile"]]
    package = server_handoff["package"]
    replacements = {
        "<sha256>": package["manifest_digest"],
        "<runtime-alias>": server_handoff["agents"]["collaboration_runtime_alias"],
        "<project-name>": request["project"]["name"],
        "<canonical-repository-url>": repository_url,
        "<repository-relative-project-root>": project_subpath,
        "<GitHub>": "GitHub",
        "<default-branch>": policy["main_ref"],
        "<project-governance-path>": existing_reference(repository_root, (".specify/memory/constitution.md", "AGENTS.md", "README.md")),
        "<architecture-or-context-path>": existing_reference(repository_root, (".specify/memory/architecture.md", "README.md")),
        "<roadmap-or-product-scope-path>": existing_reference(repository_root, ("specs", "docs", "README.md")),
        "<feature-specification-path-or-pattern>": existing_reference(repository_root, ("specs", "README.md")),
        "<adr-directory-or-pattern>": existing_reference(repository_root, ("docs/adr", "adr", ".specify/memory", "README.md")),
        "<domain-reference-directory>": existing_reference(repository_root, ("docs", "README.md")),
        "<yes-or-no>": "no",
        "<repository-policy>": "follow repository policy",
        "<create-or-link-a-Multica-Issue-before-triage>": "create or link a Multica Issue before triage",
        "<inspect-only-or-separately-authorized>": "separately authorized",
        "<term>": "repository terminology",
        "<project-specific-meaning-and-boundary>": "use the repository's documented terminology",
    }
    rendered: dict[str, str] = {}
    for destination, template_name in {
        "orchestrator-binding": "orchestrator-binding.template.yaml",
        "issue-tracker": "issue-tracker.template.md",
        "triage-mapping": "triage-mapping.template.md",
        "domain": "domain.template.md",
    }.items():
        content = (templates / template_name).read_text(encoding="utf-8")
        for source, replacement in replacements.items():
            content = content.replace(source, str(replacement))
        rendered[destination] = re.sub(
            r"<(?!(?:target-project-command(?:-or-remove-and-use-na-policy)?)>)([^>\n]+)>",
            lambda match: match.group(1).replace("-or-", " or "),
            content,
        )
    binding = rendered["orchestrator-binding"]
    for name in ("test", "lint", "build"):
        command = commands[name]
        if "command" in command:
            binding = re.sub(
                r'    command: "<target-project-command(?:-or-remove-and-use-na-policy)?>"',
                f'    command: "{command["command"]}"',
                binding,
                count=1,
            )
        else:
            binding = re.sub(
                r'    command: "<target-project-command(?:-or-remove-and-use-na-policy)?>"',
                f'    na_policy_ref: "{command["na_policy_ref"]}"',
                binding,
                count=1,
            )
    rendered["orchestrator-binding"] = binding
    paths: dict[str, Path] = {}
    for name, content in rendered.items():
        path = run_root / f"{name}{'.yaml' if name == 'orchestrator-binding' else '.md'}"
        path.write_text(content, encoding="utf-8")
        path.chmod(0o600)
        paths[name] = path
    return paths


def run(command: list[str]) -> str:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise StateError((completed.stderr or completed.stdout).strip() or f"command failed: {command[0]}")
    return completed.stdout.strip()


def run_multica(session: ProfileSession, arguments: list[str]) -> Any:
    return session.read_json(arguments, workspace=True)


def unique(values: list[Mapping[str, Any]], predicate, label: str, *, optional: bool = True) -> Mapping[str, Any] | None:
    matches = [item for item in values if predicate(item)]
    if len(matches) > 1 or (not optional and len(matches) != 1):
        raise StateError(f"{label} must resolve {'exactly' if not optional else 'at most'} one record; observed {len(matches)}")
    return matches[0] if matches else None


def resource_values(value: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = value.get("resource_ref")
    return nested if isinstance(nested, Mapping) else value

REQUEST_POLICY_KEYS = (
    "execution_mode",
    "work_item_id_source",
    "runtime_branch_authority",
    "integration_branch_authority",
    "main_ref",
    "develop_ref",
    "repository_command_profile",
)
REQUEST_KEYS = {
    "schema",
    "project",
    "repository",
    "policy",
    "command_profiles",
    "runtime_target_policy",
}


def policy_input_required(detail: str) -> None:
    raise StateError(f"PROJECT_POLICY_INPUT_REQUIRED: {detail}")


def check_profile(checks: Mapping[str, Any], name: str, *, command_required: bool = False) -> dict[str, str]:
    value = checks.get(name)
    if not isinstance(value, Mapping):
        policy_input_required(f"repository command policy lacks {name}")
    command = value.get("command")
    if isinstance(command, str) and command.strip() and command != "project-test-command":
        return {"command": command}
    reference = value.get("na_policy_ref")
    if (
        not command_required
        and value.get("state") == "HUMAN_APPROVED_NA"
        and isinstance(reference, str)
        and reference.startswith("human-approved:")
    ):
        return {"na_policy_ref": reference}
    policy_input_required(f"repository command policy has no accepted {name} command or Human N/A reference")
    raise AssertionError("unreachable")


def current_reissue(
    store: BundleStore,
    deployment: Mapping[str, Any],
    project_subject: str,
) -> Mapping[str, Any] | None:
    projects = deployment.get("projects")
    if not isinstance(projects, Mapping):
        policy_input_required("deployment index projects field is invalid")
    entry = projects.get(project_subject)
    if entry is None:
        return None
    if not isinstance(entry, Mapping) or not isinstance(entry.get("project_manifest_digest"), str):
        policy_input_required("current Project reissue policy is invalid")
    bundle = store.resolve("project-binding", entry["project_manifest_digest"])
    reissue = bundle.artifacts.get("project-reissue-spec")
    if not isinstance(reissue, Mapping):
        policy_input_required("current Project bundle lacks a reissue specification")
    body = dict(reissue)
    observed_digest = body.pop("spec_digest", None)
    if (
        body.get("schema") != "multica-orchestrator.project-reissue-spec.v3"
        or observed_digest != digest_bytes(canonical_json(body))
        or body.get("project_key") != project_subject
    ):
        policy_input_required("current Project reissue specification is stale or invalid")
    return body


def validate_request(request: Mapping[str, Any], project_subpath: str, runtime_alias: str) -> None:
    if (
        set(request) - REQUEST_KEYS
        or {
            "schema",
            "project",
            "repository",
            "policy",
            "command_profiles",
            "runtime_target_policy",
        } - set(request)
        or request.get("schema") != REQUEST_SCHEMA
    ):
        policy_input_required("materialized Project request schema is invalid")
    project = request.get("project")
    repository = request.get("repository")
    policy = request.get("policy")
    profiles = request.get("command_profiles")
    target_policy = request.get("runtime_target_policy")
    if (
        not isinstance(project, Mapping)
        or set(project) - {"name", "description"}
        or not isinstance(project.get("name"), str)
        or not project["name"].strip()
        or not isinstance(repository, Mapping)
        or set(repository) != {"project_subpath"}
        or repository.get("project_subpath") != project_subpath
        or not isinstance(policy, Mapping)
        or set(policy) != set(REQUEST_POLICY_KEYS)
        or any(not isinstance(policy.get(key), str) or not policy[key].strip() for key in REQUEST_POLICY_KEYS)
        or policy.get("execution_mode") != "worktree"
        or policy.get("work_item_id_source") != "multica-issue-key"
        or policy.get("runtime_branch_authority") != "multica"
        or policy.get("integration_branch_authority") != "repository-provider"
        or not isinstance(profiles, Mapping)
        or policy.get("repository_command_profile") not in profiles
        or not isinstance(target_policy, Mapping)
        or set(target_policy) != {"required_runtimes", "optional_runtimes", "native_squad_dispatch"}
    ):
        policy_input_required("materialized Project request has incomplete policy")
    profile = profiles[policy["repository_command_profile"]]
    if not isinstance(profile, Mapping) or set(profile) != {"test", "lint", "build"}:
        policy_input_required("materialized Project request command profile is invalid")
    for name, entry in profile.items():
        if not isinstance(entry, Mapping):
            policy_input_required(f"materialized Project request {name} profile is invalid")
        selected = [
            key
            for key in ("command", "na_policy_ref")
            if isinstance(entry.get(key), str) and entry[key].strip()
        ]
        if len(selected) != 1 or set(entry) != set(selected):
            policy_input_required(f"materialized Project request {name} profile is invalid")
    if "command" not in profile["test"]:
        policy_input_required("materialized Project request lacks a test command")
    required = target_policy.get("required_runtimes")
    optional = target_policy.get("optional_runtimes")
    dispatch = target_policy.get("native_squad_dispatch")
    if (
        not isinstance(required, list)
        or len(required) != 1
        or not isinstance(required[0], Mapping)
        or required[0].get("runtime_alias") != runtime_alias
        or required[0].get("local_directory_required") is not True
        or require_digest(required[0].get("required_capability_revision"), "runtime_target_policy.required_runtimes[0].required_capability_revision") is None
        or set(required[0].get("workload_classes", [])) != {"feature", "fix"}
        or optional != []
        or not isinstance(dispatch, Mapping)
        or set(dispatch) != {
            "leader_first",
            "leader_routes_by_exact_member_mention",
            "member_reply_retriggers_leader",
            "issue_assignment_no_start_required",
            "runtime_open_fence_required",
        }
        or not all(value is True for value in dispatch.values())
    ):
        policy_input_required("materialized Project Runtime target policy is invalid")


def materialize_request(
    repository_root: Path,
    project_subpath: str,
    runtime_alias: str,
    identity: str,
    store: BundleStore,
    deployment: Mapping[str, Any],
    server_handoff: Mapping[str, Any],
) -> dict[str, Any]:
    runtimes = server_handoff.get("runtime_fleet", {}).get("runtimes")
    if not isinstance(runtimes, list):
        policy_input_required("Server Runtime fleet is invalid")
    runtime = next((item for item in runtimes if isinstance(item, Mapping) and item.get("alias") == runtime_alias), None)
    if runtime is None or sum(item.get("alias") == runtime_alias for item in runtimes if isinstance(item, Mapping)) != 1:
        policy_input_required("required Runtime alias is absent or ambiguous in the current Server fleet")
    template_path = Path(__file__).resolve().parents[5] / "multica-orchestrator-nail-down" / "templates" / "orchestrator-request.template.json"
    template = read_json(template_path, "Project request template")
    if not isinstance(template, dict) or template.get("schema") != REQUEST_SCHEMA:
        raise StateError("Project request template is invalid")
    request = json.loads(json.dumps(template))
    project_subject = project_key(str(deployment["workspace_key"]), identity, project_subpath)
    request["project"] = {"name": identity.rsplit("/", 1)[1], "description": ""}
    request["repository"] = {"project_subpath": project_subpath}
    reissue = current_reissue(store, deployment, project_subject)
    if reissue is not None:
        repository_policy = reissue.get("repository_policy")
        command_profiles = reissue.get("command_profiles")
        target_policy = reissue.get("runtime_target_policy")
        if (
            not isinstance(repository_policy, Mapping)
            or not isinstance(command_profiles, Mapping)
            or not isinstance(target_policy, Mapping)
        ):
            policy_input_required("current Project reissue policy is incomplete")
        request["policy"] = {key: repository_policy.get(key) for key in REQUEST_POLICY_KEYS}
        request["command_profiles"] = command_profiles
        request["runtime_target_policy"] = {
            key: target_policy.get(key)
            for key in ("required_runtimes", "optional_runtimes", "native_squad_dispatch")
        }
    else:
        policy_path = repository_root / ".multica" / "orchestration-ci-policy.json"
        try:
            policy_document = read_json(policy_path, "repository command policy")
        except InputError as error:
            policy_input_required(str(error))
        if not isinstance(policy_document, Mapping) or policy_document.get("schema") != "multica-orchestration.ci-policy.v1":
            policy_input_required("repository command policy schema is invalid")
        checks = policy_document.get("checks")
        if not isinstance(checks, Mapping):
            policy_input_required("repository command policy checks are invalid")
        request["command_profiles"] = {
            "default": {
                "test": check_profile(checks, "project-test", command_required=True),
                "lint": check_profile(checks, "project-lint"),
                "build": check_profile(checks, "project-build"),
            }
        }
        request["runtime_target_policy"]["required_runtimes"][0]["runtime_alias"] = runtime_alias
        request["runtime_target_policy"]["required_runtimes"][0]["command_profile"] = "default"
    request["runtime_target_policy"]["required_runtimes"][0]["required_capability_revision"] = runtime["capability_revision"]
    validate_request(request, project_subpath, runtime_alias)
    return request


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="authenticated Multica CLI profile")
    parser.add_argument("--workspace", help="Workspace id, name, or slug; defaults to the profile selection")
    parser.add_argument("--state-root", type=Path, default=default_state_root())
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--project-subpath")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--runtime-alias", help="required Server Runtime alias when materializing a request")
    parser.add_argument("--server-digest")
    parser.add_argument("--relocation-intent-digest")
    args = parser.parse_args()
    try:
        state_root = args.state_root.expanduser().resolve()
        session = resolve_profile_session(args.profile, args.workspace)
        deployment = DeploymentIndex(state_root).resolve(session.server_kind, session.server_ref, session.workspace_ref)
        if args.relocation_intent_digest != deployment.get("relocation_intent_digest"):
            raise StateError("relocation intent differs from the current deployment index")
        request: Mapping[str, Any] | None = None
        request_path = args.request
        if args.request is not None:
            request = read_json(args.request, "Project binding request")
            if not isinstance(request, dict) or request.get("schema") != REQUEST_SCHEMA:
                raise StateError(f"Project request must use {REQUEST_SCHEMA}")
            requested_subpath = request.get("repository", {}).get("project_subpath")
            if not isinstance(requested_subpath, str) or not requested_subpath:
                raise StateError("Project request lacks repository.project_subpath")
            if args.project_subpath is not None and args.project_subpath != requested_subpath:
                raise StateError("--project-subpath differs from Project binding request")
        else:
            if not isinstance(args.project_subpath, str) or not args.project_subpath:
                policy_input_required("project_subpath is required when no Project request is supplied")
            if not isinstance(args.runtime_alias, str) or not args.runtime_alias:
                policy_input_required("required Runtime alias is required when no Project request is supplied")
            requested_subpath = args.project_subpath
        if args.server_digest:
            server_digest = args.server_digest
            pointer_evidence = "explicit-request"
        else:
            pointer = StagePointers(state_root).read("workspaces", deployment["workspace_key"], "server", "server-orchestration")
            server_digest = pointer["manifest_digest"]
            pointer_evidence = pointer["_path"]
        if server_digest != deployment.get("server_manifest_digest"):
            raise StateError("Server pointer differs from the deployment index")
        store = BundleStore(state_root / "bundle-store")
        server_bundle = store.resolve("server-orchestration", server_digest)
        closure = store.closure("server-orchestration", server_digest)
        if [item.stage for item in closure] != ["workspace-foundation", "server-orchestration"]:
            raise StateError("Server bundle closure must contain Foundation then Server")
        foundation = closure[0].artifacts["workspace-foundation"]
        server_handoff = server_bundle.artifacts["server-orchestration"]
        expected_identity = {
            "server_kind": session.server_kind,
            "server_ref": session.server_ref,
            "workspace_ref": session.workspace_ref,
            "deployment_key": deployment["deployment_key"],
            "workspace_key": deployment["workspace_key"],
        }
        if any(foundation.get(key) != value or server_handoff.get(key) != value for key, value in expected_identity.items()):
            raise StateError("Foundation/Server identity differs from live profile and deployment index")
        repository_root = Path(run(["git", "-C", str(args.repository_root), "rev-parse", "--show-toplevel"])).resolve()
        origin = run(["git", "-C", str(repository_root), "config", "--get", "remote.origin.url"])
        identity = repository_identity(origin)
        project_subject = project_key(deployment["workspace_key"], identity, requested_subpath)
        run_id, run_root = allocate_run(state_root, "nail-down", identity.rsplit("/", 1)[1])
        if request is None:
            assert args.runtime_alias is not None
            request = materialize_request(
                repository_root,
                requested_subpath,
                args.runtime_alias,
                identity,
                store,
                deployment,
                server_handoff,
            )
            request_path = run_root / "project-binding-request.v6.json"
            atomic_json(request_path, request)
        required_targets = request.get("runtime_target_policy", {}).get("required_runtimes")
        if not isinstance(required_targets, list) or len(required_targets) != 1 or not isinstance(required_targets[0], Mapping):
            policy_input_required("Project request must select exactly one required Runtime")
        requested_runtime_alias = required_targets[0].get("runtime_alias")
        if not isinstance(requested_runtime_alias, str):
            policy_input_required("Project request required Runtime alias is invalid")
        if args.runtime_alias is not None and args.runtime_alias != requested_runtime_alias:
            policy_input_required("required Runtime alias differs from the Project request")
        validate_request(request, requested_subpath, requested_runtime_alias)
        policy = request["policy"]
        selected_profile = policy["repository_command_profile"]
        selected_commands = request["command_profiles"][selected_profile]
        branch_policy_digest = digest_bytes(canonical_json({
            key: policy[key]
            for key in (
                "execution_mode",
                "work_item_id_source",
                "runtime_branch_authority",
                "integration_branch_authority",
                "main_ref",
                "develop_ref",
            )
        }))
        skill_profile_digest = digest_bytes(canonical_json({
            "repository_command_profile": selected_profile,
            "commands": {
                name: selected_commands[name]
                for name in ("test", "lint", "build")
            },
            "runtime_target_policy": request["runtime_target_policy"],
        }))
        project_request = request.get("project")
        if not isinstance(project_request, Mapping) or not isinstance(project_request.get("name"), str):
            raise StateError("Project request lacks project.name")
        repositories = records(run_multica(session, ["repo", "list"]), "repository list")
        repository_record = unique(
            repositories,
            lambda item: item.get("url", item.get("repository_url")) == origin,
            "repository",
        )
        projects = records(run_multica(session, ["project", "list"]), "Project list")
        project_record = unique(projects, lambda item: item.get("name", item.get("title")) == project_request["name"], "Project")
        project_ref = project_record.get("id", project_record.get("project_id")) if project_record else None
        resources = records(run_multica(session, ["project", "resource", "list", project_ref]), "Project resource list") if project_ref else []
        github_resource = unique(resources, lambda item: item.get("type", item.get("resource_type")) == "github_repo" and resource_values(item).get("url", resource_values(item).get("repository_url")) == origin, "Project GitHub resource")
        runtime = next(
            (
                item
                for item in server_handoff["runtime_fleet"]["runtimes"]
                if item.get("alias") == requested_runtime_alias
            ),
            None,
        )
        if not isinstance(runtime, dict):
            raise StateError(f"Project request Runtime alias is absent from Server fleet: {requested_runtime_alias}")
        live_runtimes = records(run_multica(session, ["runtime", "list"]), "Runtime list")
        daemon_ref = runtime["daemon_ref"]
        live_runtime = unique(
            live_runtimes,
            lambda item: item.get("id", item.get("runtime_id")) == runtime["runtime_ref"]
            and item.get("daemon_id", item.get("daemon_ref")) == daemon_ref,
            f"Runtime {requested_runtime_alias}",
            optional=False,
        )
        assert live_runtime is not None
        capability_revision = runtime_capability_revision(live_runtime)
        required_capability_revision = required_targets[0].get("required_capability_revision")
        if capability_revision != runtime.get("capability_revision") or capability_revision != required_capability_revision:
            raise StateError(f"RUNTIME_CAPABILITY_REVISION_MISMATCH: {requested_runtime_alias}")
        runtime_targets = [{
            "runtime_alias": requested_runtime_alias,
            "runtime_ref": runtime["runtime_ref"],
            "daemon_ref": daemon_ref,
            "capability_revision": capability_revision,
        }]
        local_directory = (
            select_local_directory_resource(resources, root=str(repository_root), daemon_ref=daemon_ref)
            if project_ref else {"state": "ABSENT", "resource": None}
        )
        snapshot = {
            "schema": SNAPSHOT_SCHEMA,
            "workspace_ref": session.workspace_ref,
            "server_manifest_digest": server_digest,
            "repository": {"url": origin, "root": str(repository_root), "registered": repository_record is not None, "repository_ref": repository_record.get("id", repository_record.get("repository_id", origin)) if repository_record else None, "project_has_resource": github_resource is not None, "resource_ref": github_resource.get("id", github_resource.get("resource_id")) if github_resource else None},
            "project": {"exists": project_record is not None, "project_ref": project_ref},
            "runtime_targets": runtime_targets,
            "primary_local_directory": local_directory,
            "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        snapshot["snapshot_digest"] = digest_bytes(canonical_json(snapshot))
        snapshot_path = run_root / "snapshot.json"
        atomic_json(snapshot_path, snapshot)
        input_value = {
            "schema": "multica-orchestrator-nail-down.project-binding-input.v12",
            "bundle_store": {"state_root": str(state_root / "bundle-store")},
            "server": {"kind": session.server_kind, "ref": session.server_ref, "deployment_key": deployment["deployment_key"], "workspace_key": deployment["workspace_key"], "profile": session.profile, "workspace_ref": session.workspace_ref, "account_ref": session.account_ref},
            "server_handoff_bundle": {"manifest_digest": server_digest},
            "repository": {"provider": "github", "url": origin, "root": str(repository_root), "project_subpath": requested_subpath, "registered": snapshot["repository"]["registered"], "repository_ref": snapshot["repository"]["repository_ref"], "project_has_resource": snapshot["repository"]["project_has_resource"], "resource_ref": snapshot["repository"]["resource_ref"]},
            "project": {"name": project_request["name"], "description": project_request.get("description", ""), "exists": snapshot["project"]["exists"], "project_ref": project_ref},
            "policy": {**policy, "branch_policy_digest": branch_policy_digest, "skill_profile_digest": skill_profile_digest},
            "command_profiles": request["command_profiles"],
            "runtime_target_policy": request["runtime_target_policy"],
            "primary_runtime": runtime_targets[0],
            "local_directory_observation": local_directory,
        }
        if args.relocation_intent_digest is not None:
            input_value["server"]["relocation_intent_digest"] = args.relocation_intent_digest
        input_path = run_root / "input.json"
        atomic_json(input_path, input_value)
        portable_configs = render_portable_configs(
            run_root,
            repository_root,
            origin,
            requested_subpath,
            request,
            server_handoff,
        )
        for name, path in portable_configs.items():
            validate_portable_config(path, f"rendered {name}")
        if request_path != run_root / "project-binding-request.v6.json":
            atomic_json(run_root / "request.json", request)
        assert request_path is not None
        write_resolution(run_root / "resolution.json", run_id=run_id, request=request, resolved_input=input_path, fields={
            "deployment_index": {"source": "operator-state", "evidence": deployment["_path"], "value": deployment["_digest"]},
            "server_manifest_digest": {"source": "explicit" if args.server_digest else "cas-pointer", "evidence": pointer_evidence, "value": server_digest},
            "workspace_ref": {"source": "multica-cli", "value": session.workspace_ref},
            "repository": {"source": "git", "value": {"url": origin}},
            "project_and_resources": {"source": "multica-cli", "value": {"project_ref": project_ref, "repository_ref": snapshot["repository"]["repository_ref"], "resource_ref": snapshot["repository"]["resource_ref"]}},
            "runtime_capability": {"source": "multica-cli", "value": {"runtime_alias": requested_runtime_alias, "capability_revision": capability_revision}},
            "portable_configs": {"source": "nail-down-templates", "value": {name: str(path) for name, path in sorted(portable_configs.items())}},
            "paths": {"source": "state-layout", "value": str(run_root)},
        })
        print(json.dumps({"ok": True, "run_id": run_id, "run_root": str(run_root), "request": str(request_path), "snapshot": str(snapshot_path), "input": str(input_path), "resolution": str(run_root / "resolution.json"), "portable_configs": {name: str(path) for name, path in sorted(portable_configs.items())}}, sort_keys=True))
        return 0
    except (StateError, InputError, OSError, KeyError, TypeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": "PROJECT_PREPARE_FAILED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
