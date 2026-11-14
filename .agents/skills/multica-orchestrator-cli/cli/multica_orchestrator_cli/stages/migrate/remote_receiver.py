#!/usr/bin/env python3
"""Run fixed, fail-closed bundle import and target adaptation operations on a Runtime host."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from multica_state_bundle.bundle_store import BundleStore
from multica_state_bundle.handoff import BundleError, canonical_json, digest_bytes
from multica_state_bundle.identities import canonical_json as compact_json, utc_now
from multica_state_bundle.storage import atomic_bytes
from multica_orchestrator_cli.common.dispatch_runtime import (
    ACTIVATION_FENCE_SCHEMA,
    DispatchRuntimeError,
    RUNTIME_BINDING_SCHEMA,
    authority_lock,
    read_active_release,
    write_runtime_binding,
)
from multica_orchestrator_cli.common.runtime_activation import (
    ensure_local_directory,
    local_directory_execution_mode,
    local_directory_resource_identity,
)
from migration_common import (
    ACTIVATION_RECEIPT_SCHEMA,
    ACTIVATION_RECEIPT_WIRE,
    NATIVE_SQUAD_CLI_REQUIREMENTS,
    MigrationError,
    encoded,
    github_slug,
    local_directory_resource_matches,
    native_squad_capability_errors,
    nested_contains,
    parse_json_stdout,
    proxy_environment,
    read_json,
    records,
    require_absolute,
    require_digest,
    require_string,
    run_process,
)
from multica_orchestrator_cli.common.runtime_capability import RuntimeCapabilityEvidenceError, runtime_capabilities, runtime_capability_revision


def multica(server_kind: str, profile: str, workspace_ref: str, arguments: list[str], *, output_json: bool = True) -> Any:
    command = ["multica", "--profile", profile, "--workspace-id", workspace_ref, *arguments]
    if output_json:
        command.extend(["--output", "json"])
    completed = run_process(command, environment=proxy_environment(server_kind))
    return parse_json_stdout(completed, "Multica readback") if output_json else completed.stdout + completed.stderr


def contract_digest(value: Any) -> str:
    return digest_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def unique_resource(payload: Any, *, root: str, daemon_ref: str) -> Mapping[str, Any] | None:
    matches = [
        item for item in records(payload, "Project resource list")
        if local_directory_resource_matches(item, root=root, daemon_ref=daemon_ref)
    ]
    if len(matches) > 1:
        raise MigrationError("multiple identical local-directory resources exist")
    return matches[0] if matches else None


def import_pack(args: argparse.Namespace) -> dict[str, Any]:
    bundle = BundleStore(Path(args.state_root)).import_pack(Path(args.pack), expected_pack_digest=args.pack_digest)
    if bundle.stage != "project-binding" or bundle.manifest_digest != args.bundle_digest:
        raise MigrationError("imported pack root differs from the authorized Project bundle")
    closure = BundleStore(Path(args.state_root)).closure("project-binding", args.bundle_digest)
    return {"bundle_manifest_digest": bundle.manifest_digest, "closure": [item.manifest_digest for item in closure]}


def checkout_repository(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(require_absolute(args.root, "repository root"))
    expected_slug = github_slug(args.url)
    if root.exists():
        if root.is_symlink() or not root.is_dir():
            raise MigrationError("repository root exists but is not a regular directory")
        inside = run_process(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"], allow_failure=True)
        if inside.returncode or inside.stdout.strip() != "true":
            raise MigrationError("repository root exists but is not a Git worktree")
        origin = run_process(["git", "-C", str(root), "remote", "get-url", "origin"]).stdout.strip()
        if github_slug(origin) != expected_slug:
            raise MigrationError("repository origin conflicts with the Project binding")
        return {"state": "ALREADY_PRESENT", "root": str(root), "repository_identity": "github:" + expected_slug}
    root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    run_process(["git", "clone", "--", args.url, str(root)])
    origin = run_process(["git", "-C", str(root), "remote", "get-url", "origin"]).stdout.strip()
    if github_slug(origin) != expected_slug:
        raise MigrationError("repository checkout postcondition failed")
    return {"state": "CLONED", "root": str(root), "repository_identity": "github:" + expected_slug}


def bind_local_directory(args: argparse.Namespace) -> dict[str, Any]:
    before = multica(args.server_kind, args.profile, args.workspace_ref, ["project", "resource", "list", args.project_ref])
    return ensure_local_directory(
        resources_before=before,
        project_ref=args.project_ref,
        root=args.root,
        daemon_ref=args.daemon_ref,
        run_multica=lambda command: multica(
            args.server_kind, args.profile, args.workspace_ref, list(command)
        ),
    )


def validate_target_server_identity(server_input: Any, server: Mapping[str, Any]) -> Mapping[str, Any]:
    expected_server_fields = {"kind", "ref", "workspace_ref"}
    if not isinstance(server_input, dict) or set(server_input) not in (
        expected_server_fields,
        expected_server_fields | {"deployment_key"},
    ):
        raise MigrationError("target server identity is invalid")
    target_deployment_key = server_input.get("deployment_key")
    if target_deployment_key is not None:
        require_digest(target_deployment_key, "target server deployment_key")
    bundle_deployment_key = server.get("deployment_key")
    if bundle_deployment_key is None and target_deployment_key is not None:
        bundle_deployment_key = digest_bytes(canonical_json({
            "schema": "multica-orchestrator.deployment-key.v1",
            "server_kind": server.get("server_kind"),
            "server_ref": server.get("server_ref"),
            "workspace_ref": server.get("workspace_ref"),
        }))
    if (
        server.get("server_ref") != server_input["ref"]
        or server.get("server_kind") != server_input["kind"]
        or server.get("workspace_ref") != server_input["workspace_ref"]
        or bundle_deployment_key != target_deployment_key
    ):
        raise MigrationError("target server identity differs from bundle")
    return server_input


def verify_target(args: argparse.Namespace) -> dict[str, Any]:
    target = read_json(Path(args.target_input), "target activation input")
    expected_fields = {
        "schema", "server", "state_root", "project_bundle_manifest_digest", "release_candidate_digest",
        "native_squad_dispatch_digest", "project_key", "generation", "runtime_alias", "runtime_ref", "daemon_ref",
        "profile", "account_ref", "repository_url", "repository_root",
        "repository_subpath", "command_profile",
    }
    if target.get("schema") != "multica-orchestrator-migrate.target-activation-input.v3" or set(target) != expected_fields:
        raise MigrationError("target activation input fields are invalid")
    state_root = Path(require_absolute(target["state_root"], "state_root"))
    project_bundle = BundleStore(state_root).resolve("project-binding", require_digest(target["project_bundle_manifest_digest"], "Project bundle digest"))
    closure = BundleStore(state_root).closure("project-binding", project_bundle.manifest_digest)
    if [item.stage for item in closure] != ["workspace-foundation", "server-orchestration", "project-binding"]:
        raise MigrationError("target bundle closure is incomplete")
    foundation_bundle, server_bundle, _ = closure
    foundation = foundation_bundle.artifacts["workspace-foundation"]
    server = server_bundle.artifacts["server-orchestration"]
    project = project_bundle.artifacts["project-binding"]
    policy = project_bundle.artifacts["runtime-target-policy"]
    project_specification = project_bundle.artifacts["project-verification-spec"]
    server_specification = server_bundle.artifacts["server-verification-spec"]
    if foundation.get("state") != "WORKSPACE_FOUNDATION_VERIFIED" or foundation.get("blockers") or server.get("state") != "ORCHESTRATOR_LAYER_VERIFIED" or project.get("state") != "PROJECT_BOUND" or project.get("blockers"):
        raise MigrationError("bundle verification state is not releasable")
    if (
        project.get("project_key") != target["project_key"]
        or project_specification.get("project_key") != target["project_key"]
        or project_specification.get("project_ref") != project.get("project_ref")
        or project_specification.get("repository_identity") != project.get("repository_identity")
        or project_specification.get("workspace_ref") != server.get("workspace_ref")
    ):
        raise MigrationError("Project verification specification identity differs")
    dispatch = policy.get("native_squad_dispatch")
    if (
        not isinstance(dispatch, dict)
        or digest_bytes(compact_json(dispatch)) != target["native_squad_dispatch_digest"]
        or project_specification.get("native_squad_dispatch_digest") != target["native_squad_dispatch_digest"]
        or project.get("native_squad_dispatch") != dispatch
    ):
        raise MigrationError("target native Squad dispatch policy differs from bundle")
    target_policy = [item for group in ("required_runtimes", "optional_runtimes") for item in policy[group] if item["runtime_alias"] == target["runtime_alias"]]
    runtime = [item for item in server["runtime_fleet"]["runtimes"] if item["alias"] == target["runtime_alias"]]
    if len(target_policy) != 1 or len(runtime) != 1:
        raise MigrationError("Runtime policy or fleet placement is ambiguous")
    if runtime[0]["runtime_ref"] != target["runtime_ref"] or runtime[0]["daemon_ref"] != target["daemon_ref"] or target_policy[0]["command_profile"] != target["command_profile"]:
        raise MigrationError("Runtime target input differs from bundle policy")
    server_input = validate_target_server_identity(target["server"], server)
    auth = multica(server_input["kind"], target["profile"], server_input["workspace_ref"], ["auth", "status"], output_json=False)
    config = multica(server_input["kind"], target["profile"], server_input["workspace_ref"], ["config", "show"], output_json=False)
    if target["account_ref"] not in auth or server_input["ref"] not in config:
        raise MigrationError("consumer-local profile/account/server identity is unverified")
    capability_results: dict[str, tuple[int, str]] = {}
    for name, (command, _) in NATIVE_SQUAD_CLI_REQUIREMENTS.items():
        completed = run_process(
            ["multica", *command, "--help"],
            environment=proxy_environment(server_input["kind"]),
            allow_failure=True,
        )
        capability_results[name] = (completed.returncode, completed.stdout + completed.stderr)
    capability_errors = native_squad_capability_errors(capability_results)
    if capability_errors:
        raise MigrationError("target Runtime lacks native Squad CLI capabilities: " + ", ".join(capability_errors))
    workspaces = multica(server_input["kind"], target["profile"], server_input["workspace_ref"], ["workspace", "list"])
    if len([item for item in records(workspaces, "workspace list") if item.get("id", item.get("workspace_id")) == server_input["workspace_ref"]]) != 1:
        raise MigrationError("workspace is not uniquely visible")
    runtimes = multica(server_input["kind"], target["profile"], server_input["workspace_ref"], ["runtime", "list"])
    runtime_records = [item for item in records(runtimes, "Runtime list") if item.get("id", item.get("runtime_id")) == target["runtime_ref"]]
    if len(runtime_records) != 1 or runtime_records[0].get("status") != "online" or runtime_records[0].get("daemon_id", runtime_records[0].get("daemon_ref")) != target["daemon_ref"]:
        raise MigrationError("target Runtime readback differs")
    try:
        observed_capability_revision = runtime_capability_revision(runtime_records[0])
        worktree_capable = "local-worktree-v1" in runtime_capabilities(runtime_records[0])
    except RuntimeCapabilityEvidenceError as error:
        raise MigrationError(str(error)) from error
    if (
        observed_capability_revision != runtime[0].get("capability_revision")
        or observed_capability_revision != target_policy[0].get("required_capability_revision")
    ):
        raise MigrationError("target Runtime capability revision differs")
    if not worktree_capable:
        raise MigrationError("target Runtime lacks local-worktree-v1")
    if (
        server_specification.get("server_ref") != server_input["ref"]
        or server_specification.get("server_kind") != server_input["kind"]
        or server_specification.get("workspace_ref") != server_input["workspace_ref"]
        or server_specification.get("package_manifest_digest") != server.get("package", {}).get("manifest_digest")
    ):
        raise MigrationError("Server verification specification identity differs")
    skill_list = multica(server_input["kind"], target["profile"], server_input["workspace_ref"], ["skill", "list"])
    skill_records = records(skill_list, "Skill list")
    skill_ids: dict[str, str] = {}
    skill_readback_digests: dict[str, str] = {}
    for name, expected_digest in server_specification["skills"].items():
        matches = [item for item in skill_records if item.get("name") == name]
        if len(matches) != 1 or not isinstance(matches[0].get("id"), str):
            raise MigrationError(f"workspace Skill identity differs: {name}")
        skill_id = matches[0]["id"]
        detail = multica(server_input["kind"], target["profile"], server_input["workspace_ref"], ["skill", "get", skill_id, "--with-content"])
        observed_digest = contract_digest(detail)
        if observed_digest != expected_digest:
            raise MigrationError(f"workspace Skill content differs: {name}")
        skill_ids[name] = skill_id
        skill_readback_digests[name] = observed_digest
    agent_list = multica(server_input["kind"], target["profile"], server_input["workspace_ref"], ["agent", "list", "--include-archived"])
    agent_records = records(agent_list, "Agent list")
    agent_readback_digests: dict[str, str] = {}
    for role, expected in server_specification["agents"].items():
        matches = [item for item in agent_records if item.get("name") == role]
        if len(matches) != 1 or matches[0].get("id") != expected["agent_ref"]:
            raise MigrationError(f"Agent identity differs: {role}")
        detail = multica(server_input["kind"], target["profile"], server_input["workspace_ref"], ["agent", "get", expected["agent_ref"]])
        observed_thinking = detail.get("thinking_level")
        if observed_thinking == "":
            observed_thinking = None
        fields = {
            "name": role,
            "runtime_id": expected["runtime_ref"],
            "model": expected["model"],
            "thinking_level": expected["thinking_level"],
            "max_concurrent_tasks": expected["max_concurrent_tasks"],
            "permission_mode": "private",
        }
        if any((observed_thinking if key == "thinking_level" else detail.get(key)) != value for key, value in fields.items()):
            raise MigrationError(f"Agent configuration differs: {role}")
        instructions = detail.get("instructions")
        if not isinstance(instructions, str) or digest_bytes(instructions.encode()) != expected["instructions_digest"]:
            raise MigrationError(f"Agent instructions differ: {role}")
        agent_skills = multica(server_input["kind"], target["profile"], server_input["workspace_ref"], ["agent", "skills", "list", expected["agent_ref"]])
        observed_skill_ids = {
            item.get("id", item.get("skill_id"))
            for item in records(agent_skills, f"Agent Skills {role}")
        }
        if observed_skill_ids != {skill_ids[name] for name in expected["skill_names"]}:
            raise MigrationError(f"Agent Skill bindings differ: {role}")
        agent_readback_digests[role] = digest_bytes(canonical_json({
            "detail": detail, "skill_ids": sorted(observed_skill_ids),
        }))
    squad_list = multica(server_input["kind"], target["profile"], server_input["workspace_ref"], ["squad", "list"])
    squad_records = records(squad_list, "Squad list")
    squad_readback_digests: dict[str, str] = {}
    for name, expected in server_specification["squads"].items():
        matches = [item for item in squad_records if item.get("name") == name]
        if len(matches) != 1 or matches[0].get("id") != expected["squad_ref"]:
            raise MigrationError(f"Squad identity differs: {name}")
        detail = multica(server_input["kind"], target["profile"], server_input["workspace_ref"], ["squad", "get", expected["squad_ref"]])
        members_payload = multica(server_input["kind"], target["profile"], server_input["workspace_ref"], ["squad", "member", "list", expected["squad_ref"]])
        members = records(members_payload, f"Squad members {name}")
        leader_refs = {
            item.get("agent_id", item.get("member_id", item.get("id")))
            for item in members if item.get("role") == "leader"
        }
        member_refs = {
            item.get("agent_id", item.get("member_id", item.get("id")))
            for item in members if item.get("role") != "leader"
        }
        instructions = detail.get("instructions")
        if (
            detail.get("leader_id", detail.get("leader_agent_id")) != expected["leader_ref"]
            or leader_refs != {expected["leader_ref"]}
            or member_refs != set(expected["member_refs"])
            or not isinstance(instructions, str)
            or digest_bytes(instructions.encode()) != expected["instructions_digest"]
        ):
            raise MigrationError(f"Squad configuration differs: {name}")
        squad_readback_digests[name] = digest_bytes(canonical_json({
            "detail": detail, "members": members_payload,
        }))
    daemon_completed = run_process(["multica", "--profile", target["profile"], "daemon", "status", "--output", "json"], environment=proxy_environment(server_input["kind"]))
    daemon = parse_json_stdout(daemon_completed, "daemon status")
    if daemon.get("status") not in {"running", "online"} or not nested_contains({"daemon": daemon, "config": config}, target["daemon_ref"]):
        raise MigrationError("local daemon ownership is unverified")
    resources = multica(server_input["kind"], target["profile"], server_input["workspace_ref"], ["project", "resource", "list", project["project_ref"]])
    local_resource = unique_resource(resources, root=target["repository_root"], daemon_ref=target["daemon_ref"])
    if local_resource is None or local_directory_execution_mode(local_resource) != "worktree":
        raise MigrationError("target local-directory worktree resource is absent")
    repository_resource_ref = project.get("repository_resource_ref")
    if repository_resource_ref and len([item for item in records(resources, "Project resource list") if item.get("id", item.get("resource_id")) == repository_resource_ref]) != 1:
        raise MigrationError("Project GitHub repository resource is absent")
    root = Path(require_absolute(target["repository_root"], "repository_root"))
    origin = run_process(["git", "-C", str(root), "remote", "get-url", "origin"]).stdout.strip()
    project_subpath = (root / PurePosixPath(target["repository_subpath"])).resolve()
    try:
        project_subpath.relative_to(root.resolve())
    except ValueError as error:
        raise MigrationError("repository project subpath escapes root") from error
    if github_slug(origin) != github_slug(target["repository_url"]) or not project_subpath.is_dir():
        raise MigrationError("repository identity or subpath differs")
    if contract_digest(project["command_profiles"]) != project["command_profiles_digest"] or target["command_profile"] not in project["command_profiles"]:
        raise MigrationError("command profile digest or selection differs")
    verification = {
        "bundle_closure": [item.manifest_digest for item in closure],
        "foundation_artifact_digest": foundation_bundle.manifest["artifacts"]["workspace-foundation"]["digest"],
        "server_spec_digest": server_bundle.manifest["artifacts"]["server-verification-spec"]["digest"],
        "project_spec_digest": project_bundle.manifest["artifacts"]["project-verification-spec"]["digest"],
        "runtime_readback_digest": digest_bytes(canonical_json(runtime_records[0])),
        "daemon_readback_digest": digest_bytes(canonical_json(daemon)),
        "project_resources_digest": digest_bytes(canonical_json(resources)),
        "execution_mode": "worktree",
        "worktree_capability_revision": observed_capability_revision,
        "skill_readback_digests": skill_readback_digests,
        "agent_readback_digests": agent_readback_digests,
        "squad_readback_digests": squad_readback_digests,
        "native_squad_cli_capabilities_digest": digest_bytes(canonical_json({
            name: {"returncode": result[0], "help_digest": digest_bytes(result[1].encode())}
            for name, result in sorted(capability_results.items())
        })),
    }
    receipt = {
        "schema": ACTIVATION_RECEIPT_SCHEMA,
        "wire": ACTIVATION_RECEIPT_WIRE,
        "runtime_alias": target["runtime_alias"],
        "project_key": target["project_key"],
        "generation": target["generation"],
        "release_candidate_digest": target["release_candidate_digest"],
        "project_bundle_manifest_digest": project_bundle.manifest_digest,
        "native_squad_dispatch_digest": target["native_squad_dispatch_digest"],
        "workspace_ref": server_input["workspace_ref"],
        "runtime_ref": target["runtime_ref"],
        "daemon_ref": target["daemon_ref"],
        "repository_identity": project["repository_identity"],
        "command_profile": target["command_profile"],
        "local_directory_resource_ref": require_string(local_resource.get("id", local_resource.get("resource_id")), "local-directory resource ref"),
        "execution_mode": "worktree",
        "worktree_capability_revision": observed_capability_revision,
        "verification": verification,
        "state": "ACTIVATED",
        "verified_at": utc_now(),
    }
    receipt["receipt_digest"] = digest_bytes(compact_json(receipt))
    atomic_bytes(Path(args.receipt), encoded(receipt))
    return receipt


def _publication(args: argparse.Namespace) -> Mapping[str, Any]:
    path = Path(args.publication_input)
    raw = path.read_bytes()
    if digest_bytes(raw) != args.publication_digest:
        raise MigrationError("dispatch publication digest differs")
    publication = read_json(path, "dispatch publication")
    expected = {
        "schema", "runtime_binding", "release", "release_candidate",
        "activation_aggregate", "previous_release_digest", "transaction_digest",
        "legacy_control_store",
    }
    if set(publication) != expected or publication.get("schema") != "multica-orchestrator-dispatch.release-publication.v1":
        raise MigrationError("dispatch publication fields are invalid")
    if not isinstance(publication.get("runtime_binding"), dict) or publication["runtime_binding"].get("schema") != RUNTIME_BINDING_SCHEMA:
        raise MigrationError("dispatch publication Runtime binding is invalid")
    if digest_bytes(canonical_json({key: value for key, value in publication["release"].items() if key != "release_digest"})) != publication["release"].get("release_digest"):
        raise MigrationError("dispatch publication release digest is invalid")
    return publication


def stage_dispatch_release(args: argparse.Namespace) -> dict[str, Any]:
    publication = _publication(args)
    binding = publication["runtime_binding"]
    release = publication["release"]
    release_root = Path(binding["release_root"]).expanduser().resolve()
    if release_root.name != binding["project_key"].split(":", 1)[1]:
        raise MigrationError("dispatch publication release root differs")
    release_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    fence = {
        "schema": ACTIVATION_FENCE_SCHEMA,
        "project_key": binding["project_key"],
        "previous_release_digest": publication["previous_release_digest"],
        "release_digest": release["release_digest"],
        "transaction_digest": publication["transaction_digest"],
    }
    with authority_lock(Path(binding["control_db"])):
        if (release_root / "active.json").exists():
            active = read_active_release(Path(binding["cas_root"]), binding["project_key"])
            if active["release_digest"] == release["release_digest"]:
                return {"state": "ALREADY_ACTIVE", "release_digest": release["release_digest"]}
            raise MigrationError("target active release conflicts with source release")
        fence_path = release_root / "activation-pending.json"
        if fence_path.exists():
            if read_json(fence_path, "dispatch activation fence") != fence:
                raise MigrationError("target activation fence conflicts with source release")
            return {"state": "ALREADY_STAGED", "release_digest": release["release_digest"], "transaction_digest": publication["transaction_digest"]}
        atomic_bytes(fence_path, encoded(fence))
    return {"state": "STAGED", "release_digest": release["release_digest"], "transaction_digest": publication["transaction_digest"]}


def commit_dispatch_release(args: argparse.Namespace) -> dict[str, Any]:
    publication = _publication(args)
    binding = publication["runtime_binding"]
    release = publication["release"]
    release_root = Path(binding["release_root"]).expanduser().resolve()
    with authority_lock(Path(binding["control_db"])):
        if (release_root / "active.json").exists():
            active = read_active_release(Path(binding["cas_root"]), binding["project_key"])
            if active["release_digest"] == release["release_digest"]:
                return {"state": "ALREADY_ACTIVE", "release_digest": release["release_digest"], "active_pointer": str(release_root / "active.json")}
            raise MigrationError("target active release conflicts with source release")
        fence_path = release_root / "activation-pending.json"
        fence = read_json(fence_path, "dispatch activation fence")
        if fence.get("release_digest") != release["release_digest"] or fence.get("transaction_digest") != publication["transaction_digest"]:
            raise MigrationError("dispatch activation fence differs")
        immutable = release_root / f"generation-{release['generation']}-{release['release_digest'].split(':', 1)[1]}.json"
        atomic_bytes(immutable, encoded(release))
        pointer = {
            "schema": "multica-orchestrator-migrate.active-pointer.v1",
            "project_key": binding["project_key"],
            "generation": release["generation"],
            "release_digest": release["release_digest"],
            "release_path": str(immutable),
        }
        atomic_bytes(release_root / "active.json", encoded(pointer))
        write_runtime_binding(binding)
        fence_path.unlink()
    return {"state": "COMMITTED", "release_digest": release["release_digest"], "active_pointer": str(release_root / "active.json")}


def read_dispatch_release(args: argparse.Namespace) -> dict[str, Any]:
    publication = _publication(args)
    binding = publication["runtime_binding"]
    active = read_active_release(Path(binding["cas_root"]), binding["project_key"])
    if active["release_digest"] != publication["release"]["release_digest"]:
        raise MigrationError("target dispatch release differs")
    return {"state": "ACTIVE", "release_digest": active["release_digest"], "active_pointer": str(Path(binding["release_root"]) / "active.json")}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    imported = commands.add_parser("import-pack")
    imported.add_argument("--state-root", required=True)
    imported.add_argument("--pack", required=True)
    imported.add_argument("--pack-digest", required=True)
    imported.add_argument("--bundle-digest", required=True)
    checkout = commands.add_parser("checkout-repository")
    checkout.add_argument("--root", required=True)
    checkout.add_argument("--url", required=True)
    bind = commands.add_parser("bind-local-directory")
    bind.add_argument("--server-kind", choices=("cloud", "self-hosted"), required=True)
    bind.add_argument("--profile", required=True)
    bind.add_argument("--workspace-ref", required=True)
    bind.add_argument("--project-ref", required=True)
    bind.add_argument("--root", required=True)
    bind.add_argument("--daemon-ref", required=True)
    bind.add_argument("--execution-mode", choices=("worktree",), required=True)
    verify = commands.add_parser("verify-activation")
    verify.add_argument("--target-input", required=True)
    verify.add_argument("--receipt", required=True)
    for name in ("stage-dispatch-release", "commit-dispatch-release", "read-dispatch-release"):
        publication = commands.add_parser(name)
        publication.add_argument("--publication-input", required=True)
        publication.add_argument("--publication-digest", required=True)
    return root
def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "import-pack":
            result = import_pack(args)
        elif args.command == "checkout-repository":
            result = checkout_repository(args)
        elif args.command == "bind-local-directory":
            result = bind_local_directory(args)
        elif args.command == "stage-dispatch-release":
            result = stage_dispatch_release(args)
        elif args.command == "commit-dispatch-release":
            result = commit_dispatch_release(args)
        elif args.command == "read-dispatch-release":
            result = read_dispatch_release(args)
        else:
            result = verify_target(args)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, sort_keys=True))
        return 0
    except (DispatchRuntimeError, MigrationError, BundleError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "error": "REMOTE_MIGRATION_OPERATION_FAILED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
