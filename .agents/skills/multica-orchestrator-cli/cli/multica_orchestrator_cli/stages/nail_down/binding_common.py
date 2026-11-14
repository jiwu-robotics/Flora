"""Stdlib-only helpers for project binding plans and verification."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from multica_state_bundle.bundle_store import BundleStore
from multica_state_bundle.handoff import Bundle, BundleError, load_bundle
from multica_state_bundle.identities import canonical_json, digest_bytes

INPUT_SCHEMA = "multica-orchestrator-nail-down.project-binding-input.v12"
SERVER_SCHEMAS = {
    "multica-orchestrator.server-orchestration-ref.v10",
}
OUTPUT_SCHEMA = "multica-orchestrator-nail-down.project-binding-ref.v12"
PLAN_SCHEMA = "multica-orchestrator-nail-down.project-binding-plan.v11"
NATIVE_SQUAD_DISPATCH_KEYS = {
    "leader_first",
    "leader_routes_by_exact_member_mention",
    "member_reply_retriggers_leader",
    "issue_assignment_no_start_required",
    "runtime_open_fence_required",
}
NON_COLLABORATION_ROLES = frozenset({"shared-intake", "workflow-leader"})
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40}$")


class InputError(ValueError):
    """Input or readback has no safe interpretation."""




def read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise InputError(f"cannot read {label}: {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise InputError(f"invalid JSON in {label}: {path}: {error.msg}") from error


def require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise InputError(f"{label} must be an object")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{label} must be a non-empty string")
    return value

def records(value: Any, label: str) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        items = next((value[key] for key in ("items", "data", "results", "repositories", "projects", "resources") if isinstance(value.get(key), list)), None)
        if items is None:
            raise InputError(f"{label} does not contain a list")
    else:
        raise InputError(f"{label} must be a list or list wrapper")
    if not all(isinstance(item, dict) for item in items):
        raise InputError(f"{label} contains a non-object")
    return items


def require_digest(value: Any, label: str) -> str:
    result = require_string(value, label)
    if DIGEST.fullmatch(result) is None:
        raise InputError(f"{label} must be a sha256 digest")
    return result


def validate_repository_url(value: str) -> None:
    if re.fullmatch(r"git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", value):
        return
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username is not None or parsed.password is not None:
        raise InputError("repository.url must be a credential-free GitHub HTTPS or SSH URL")
    if len([part for part in parsed.path.split("/") if part]) != 2:
        raise InputError("repository.url must identify one GitHub owner/repository")

def github_repository_slug(value: str) -> str:
    if value.startswith("git@github.com:"):
        return value.split(":", 1)[1].removesuffix(".git")
    parsed = urlsplit(value)
    return parsed.path.strip("/").removesuffix(".git")


def contained_project_root(repository_root: str, subpath: str) -> Path:
    root = Path(require_string(repository_root, "repository.root")).expanduser().resolve()
    if not root.is_dir():
        raise InputError(f"repository.root is not a directory: {root}")
    relative = Path(require_string(subpath, "repository.project_subpath"))
    if relative.is_absolute():
        raise InputError("repository.project_subpath must be relative")
    project = (root / relative).resolve()
    try:
        project.relative_to(root)
    except ValueError as error:
        raise InputError("repository.project_subpath escapes repository.root") from error
    if not project.is_dir():
        raise InputError(f"project subpath is not a directory: {project}")
    return project


def load_input(path: Path) -> Mapping[str, Any]:
    value = require_mapping(read_json(path, "project binding input"), "project binding input")
    if value.get("schema") != INPUT_SCHEMA:
        raise InputError(f"input schema must equal {INPUT_SCHEMA}")
    if "projects" in value or isinstance(value.get("project"), list):
        raise InputError("MULTIPLE_PROJECTS_NOT_ALLOWED")
    expected_keys = {
        "schema", "bundle_store", "server", "server_handoff_bundle", "repository",
        "project", "policy", "command_profiles", "runtime_target_policy",
        "primary_runtime", "local_directory_observation",
    }
    if set(value) != expected_keys:
        raise InputError(f"project binding input fields must equal {sorted(expected_keys)}")
    for key in expected_keys - {"schema"}:
        require_mapping(value.get(key), key)
    state_root = Path(require_string(value["bundle_store"].get("state_root"), "bundle_store.state_root")).expanduser()
    if not state_root.is_absolute():
        raise InputError("bundle_store.state_root must be absolute")
    server = value["server"]
    for key in ("kind", "ref", "profile", "workspace_ref", "account_ref"):
        require_string(server.get(key), f"server.{key}")
    workspace_subject = server.get("workspace_key")
    if workspace_subject is None:
        server["workspace_key"] = digest_bytes(canonical_json({
            "server_kind": server["kind"],
            "server_ref": server["ref"],
            "workspace_ref": server["workspace_ref"],
        }))
    else:
        require_digest(workspace_subject, "server.workspace_key")
    deployment_key = server.get("deployment_key")
    if deployment_key is None:
        server["deployment_key"] = digest_bytes(canonical_json({
            "schema": "multica-orchestrator.deployment-key.v1",
            "server_kind": server["kind"],
            "server_ref": server["ref"],
            "workspace_ref": server["workspace_ref"],
        }))
    else:
        require_digest(deployment_key, "server.deployment_key")
    if server["kind"] not in {"cloud", "self-hosted"}:
        raise InputError("server.kind must be cloud or self-hosted")
    require_digest(value["server_handoff_bundle"].get("manifest_digest"), "server_handoff_bundle.manifest_digest")
    repository = value["repository"]
    if repository.get("provider") != "github":
        raise InputError("repository.provider must be github in contract v8")
    validate_repository_url(require_string(repository.get("url"), "repository.url"))
    contained_project_root(repository.get("root"), repository.get("project_subpath"))
    for key in ("registered", "project_has_resource"):
        if not isinstance(repository.get(key), bool):
            raise InputError(f"repository.{key} must be boolean")
    if "runtime_bindings" in repository:
        raise InputError("repository.runtime_bindings are owned by Migrate, not Nail Down")
    project = value["project"]
    require_string(project.get("name"), "project.name")
    if not isinstance(project.get("exists"), bool):
        raise InputError("project.exists must be boolean")
    policy = value["policy"]
    if policy.get("execution_mode") != "worktree":
        raise InputError("WORKTREE_EXECUTION_MODE_REQUIRED: policy.execution_mode must be worktree")
    for key in (
        "main_ref",
        "develop_ref",
        "repository_command_profile",
        "work_item_id_source",
        "runtime_branch_authority",
        "integration_branch_authority",
    ):
        require_string(policy.get(key), f"policy.{key}")
    if (
        policy["work_item_id_source"] != "multica-issue-key"
        or policy["runtime_branch_authority"] != "multica"
        or policy["integration_branch_authority"] != "repository-provider"
    ):
        raise InputError("DUAL_BRANCH_POLICY_REQUIRED")
    for key in ("branch_policy_digest", "skill_profile_digest"):
        require_digest(policy.get(key), f"policy.{key}")
    command_profiles = value["command_profiles"]
    if not command_profiles or policy["repository_command_profile"] not in command_profiles:
        raise InputError("policy.repository_command_profile must name a command profile")
    for profile_name, profile_value in command_profiles.items():
        require_string(profile_name, "command profile name")
        profile = require_mapping(profile_value, f"command_profiles.{profile_name}")
        if set(profile) != {"test", "lint", "build"}:
            raise InputError(f"command_profiles.{profile_name} must contain test, lint, and build")
        for command_name, command_value in profile.items():
            command = require_mapping(command_value, f"command_profiles.{profile_name}.{command_name}")
            selected = [key for key in ("command", "na_policy_ref") if isinstance(command.get(key), str) and command[key].strip()]
            if len(selected) != 1 or set(command) != set(selected):
                raise InputError(f"command_profiles.{profile_name}.{command_name} must contain exactly one command or na_policy_ref")
    target_policy = value["runtime_target_policy"]
    dispatch_policy = require_mapping(
        target_policy.get("native_squad_dispatch"),
        "runtime_target_policy.native_squad_dispatch",
    )
    if set(dispatch_policy) != NATIVE_SQUAD_DISPATCH_KEYS or not all(
        dispatch_policy.get(key) is True for key in NATIVE_SQUAD_DISPATCH_KEYS
    ):
        raise InputError("NATIVE_SQUAD_DISPATCH_POLICY_REQUIRED")
    target_aliases: set[str] = set()
    for group in ("required_runtimes", "optional_runtimes"):
        targets = target_policy.get(group)
        if not isinstance(targets, list) or (group == "required_runtimes" and not targets):
            raise InputError(f"runtime_target_policy.{group} must be a {'non-empty ' if group == 'required_runtimes' else ''}array")
        for index, target_value in enumerate(targets):
            target = require_mapping(target_value, f"runtime_target_policy.{group}[{index}]")
            required_fields = {
                "runtime_alias", "command_profile", "local_directory_required",
                "workload_classes", "required_capability_revision",
            }
            if set(target) != required_fields:
                raise InputError(f"Runtime target {index} fields are invalid")
            alias = require_string(target.get("runtime_alias"), f"runtime_target_policy.{group}[{index}].runtime_alias")
            if alias in target_aliases:
                raise InputError(f"duplicate Runtime target alias: {alias}")
            target_aliases.add(alias)
            if target.get("command_profile") not in command_profiles:
                raise InputError(f"Runtime target {alias} names an unknown command profile")
            if not isinstance(target.get("local_directory_required"), bool):
                raise InputError(f"Runtime target {alias} local_directory_required must be boolean")
            require_digest(target.get("required_capability_revision"), f"Runtime target {alias} required_capability_revision")
            classes = target.get("workload_classes")
            if not isinstance(classes, list) or not classes or not all(isinstance(item, str) and item.strip() for item in classes):
                raise InputError(f"Runtime target {alias} workload_classes must be a non-empty string array")
    required_targets = target_policy["required_runtimes"]
    optional_targets = target_policy["optional_runtimes"]
    if len(required_targets) != 1:
        raise InputError("COLLABORATION_RUNTIME_POLICY_REQUIRED: declare exactly one required Runtime")
    collaboration_target = required_targets[0]
    if (
        collaboration_target.get("local_directory_required") is not True
        or set(collaboration_target.get("workload_classes", [])) != {"feature", "fix"}
    ):
        raise InputError(
            "COLLABORATION_RUNTIME_POLICY_REQUIRED: the single feature/fix Runtime "
            "must require primary activation"
        )
    primary = require_mapping(value["primary_runtime"], "primary_runtime")
    if set(primary) != {"runtime_alias", "runtime_ref", "daemon_ref", "capability_revision"}:
        raise InputError("primary_runtime fields are invalid")
    if (
        primary.get("runtime_alias") != collaboration_target.get("runtime_alias")
        or primary.get("capability_revision") != collaboration_target.get("required_capability_revision")
    ):
        raise InputError("primary Runtime differs from required Runtime policy")
    for key in ("runtime_alias", "runtime_ref", "daemon_ref"):
        require_string(primary.get(key), f"primary_runtime.{key}")
    require_digest(primary.get("capability_revision"), "primary_runtime.capability_revision")
    observation = require_mapping(value["local_directory_observation"], "local_directory_observation")
    if observation.get("state") not in {"ABSENT", "EXACT_WORKTREE", "EXACT_WRONG_MODE", "AMBIGUOUS", "CONFLICTING"}:
        raise InputError("local_directory_observation state is invalid")
    return value


def load_server_bundle(configuration: Mapping[str, Any]) -> tuple[Mapping[str, Any], str, Bundle]:
    declared = configuration["server_handoff_bundle"]
    try:
        store = BundleStore(Path(configuration["bundle_store"]["state_root"]))
        bundle = store.resolve("server-orchestration", declared["manifest_digest"])
        closure = store.closure("server-orchestration", bundle.manifest_digest)
    except (BundleError, OSError) as error:
        raise InputError(f"server handoff bundle is invalid: {error}") from error
    if [item.stage for item in closure] != ["workspace-foundation", "server-orchestration"]:
        raise InputError("server handoff must have exactly one Foundation parent")
    foundation_bundle, resolved_server_bundle = closure
    if (
        resolved_server_bundle.manifest_digest != bundle.manifest_digest
        or len(bundle.parents) != 1
        or bundle.parents[0].get("stage") != "workspace-foundation"
        or bundle.parents[0].get("manifest_digest") != foundation_bundle.manifest_digest
    ):
        raise InputError("server handoff Foundation parent differs from its CAS closure")
    handoff = bundle.artifacts["server-orchestration"]
    foundation = foundation_bundle.artifacts["workspace-foundation"]
    server = configuration["server"]
    foundation_ref = handoff.get("workspace_foundation_ref")
    if (
        not isinstance(foundation_ref, Mapping)
        or foundation_ref.get("bundle_manifest_digest") != foundation_bundle.manifest_digest
        or handoff.get("server_kind") != server["kind"]
        or foundation.get("server_kind") != server["kind"]
        or handoff.get("server_ref") != server["ref"]
        or foundation.get("server_ref") != server["ref"]
        or any(
            handoff.get(key) != server[key] or foundation.get(key) != server[key]
            for key in ("workspace_ref", "deployment_key", "workspace_key")
        )
    ):
        raise InputError("server handoff Foundation closure identity differs from project input")
    handoff_digest = bundle.manifest["artifacts"]["server-orchestration"]["digest"]
    return handoff, handoff_digest, bundle


def server_handoff_errors(configuration: Mapping[str, Any], handoff: Mapping[str, Any], bundle: Bundle) -> list[str]:
    errors: list[str] = []
    server = configuration["server"]
    if any(handoff.get(key) != value for key, value in {
        "server_ref": server["ref"],
        "server_kind": server["kind"],
        "workspace_ref": server["workspace_ref"],
    }.items()) or (
        handoff.get("deployment_key") is not None
        and handoff.get("deployment_key") != server["deployment_key"]
    ) or (
        handoff.get("schema") == "multica-orchestrator.server-orchestration-ref.v10"
        and (
            handoff.get("workspace_key") != server["workspace_key"]
            or handoff.get("relocation_intent_digest") != server.get("relocation_intent_digest")
        )
    ):
        errors.append("STALE_SERVER_PROFILE")
    if handoff.get("state") != "ORCHESTRATOR_LAYER_VERIFIED" or handoff.get("dispatch_state") != "BLOCKED_PROJECT_BINDING":
        errors.append("SERVER_ORCHESTRATOR_UNVERIFIED")
    package = handoff.get("package")
    if not isinstance(package, dict) or package.get("id") != "multica-super-individual-orchestration" or package.get("contract_version") != "10":
        errors.append("SERVER_ORCHESTRATOR_CONTRACT_MISMATCH")
    project_binding_contract = handoff.get("project_binding_contract")
    if (
        not isinstance(project_binding_contract, dict)
        or project_binding_contract.get("required_skill") != "multica-orchestrator-nail-down"
        or project_binding_contract.get("minimum_contract_version") not in {"11", "12"}
    ):
        errors.append("SERVER_PROJECT_BINDING_CONTRACT_MISMATCH")
    dispatch_contract = handoff.get("dispatch_contract")
    if (
        not isinstance(dispatch_contract, dict)
        or dispatch_contract.get("required_skill") != "multica-orchestrator-dispatch"
        or dispatch_contract.get("minimum_contract_version") != "1"
    ):
        errors.append("SERVER_DISPATCH_CONTRACT_MISMATCH")
    verification = handoff.get("verification")
    verification_fields = (
        "readback_snapshot_digest", "server_verification_report_digest",
        "server_verification_spec_digest", "skill_integrity_report_digest",
        "application_input_digest",
    )
    if not isinstance(verification, dict) or any(
        not isinstance(verification.get(key), str) or DIGEST.fullmatch(verification[key]) is None
        for key in verification_fields
    ):
        errors.append("SERVER_VERIFICATION_LINEAGE_INVALID")
    server_spec = bundle.artifacts.get("server-verification-spec")
    spec_agents = server_spec.get("agents") if isinstance(server_spec, dict) else None
    collaboration_contract = handoff.get("agents")
    collaboration_alias = (
        collaboration_contract.get("collaboration_runtime_alias")
        if isinstance(collaboration_contract, dict)
        else None
    )
    if not isinstance(spec_agents, dict):
        errors.append("COLLABORATION_RUNTIME_PLACEMENT_UNVERIFIED")
    else:
        placed_aliases = {
            spec.get("runtime_alias")
            for role, spec in spec_agents.items()
            if role not in NON_COLLABORATION_ROLES and isinstance(spec, dict)
        }
        expected_roles = set(spec_agents) - NON_COLLABORATION_ROLES
        if (
            len(spec_agents) != 16
            or len(expected_roles) != 14
            or placed_aliases != {collaboration_alias}
        ):
            errors.append("COLLABORATION_RUNTIME_PLACEMENT_UNVERIFIED")
    required_targets = configuration["runtime_target_policy"]["required_runtimes"]
    if (
        not isinstance(collaboration_alias, str)
        or len(required_targets) != 1
        or required_targets[0].get("runtime_alias") != collaboration_alias
    ):
        errors.append("COLLABORATION_RUNTIME_TARGET_MISMATCH")
    fleet = handoff.get("runtime_fleet")
    runtimes = fleet.get("runtimes") if isinstance(fleet, dict) else None
    if not isinstance(runtimes, list) or not runtimes or any(
        not isinstance(runtime, dict) or runtime.get("status") != "online" for runtime in runtimes
    ):
        errors.append("RUNTIME_FLEET_NOT_ONLINE")
        runtime_aliases: set[str] = set()
    else:
        runtime_aliases = {runtime.get("alias") for runtime in runtimes if isinstance(runtime.get("alias"), str)}
    declared_aliases = {
        target["runtime_alias"]
        for group in ("required_runtimes", "optional_runtimes")
        for target in configuration["runtime_target_policy"][group]
    }
    if not declared_aliases <= runtime_aliases:
        errors.append("RUNTIME_TARGET_NOT_IN_SERVER_FLEET")
    fleet_by_alias = {
        runtime["alias"]: runtime
        for runtime in runtimes or []
        if isinstance(runtime, dict) and isinstance(runtime.get("alias"), str)
    }
    if any(
        target.get("required_capability_revision")
        != fleet_by_alias.get(target.get("runtime_alias"), {}).get("capability_revision")
        for target in configuration["runtime_target_policy"]["required_runtimes"]
    ):
        errors.append("RUNTIME_CAPABILITY_REVISION_MISMATCH")
    if len(bundle.parents) != 1:
        errors.append("STALE_WORKSPACE_FOUNDATION")
        return sorted(set(errors))
    foundation_manifest_digest = bundle.parents[0]["manifest_digest"]
    foundation_ref = handoff.get("workspace_foundation_ref")
    if not isinstance(foundation_ref, dict) or foundation_ref.get("bundle_manifest_digest") != foundation_manifest_digest:
        errors.append("STALE_WORKSPACE_FOUNDATION")
        return sorted(set(errors))
    try:
        store = BundleStore(Path(configuration["bundle_store"]["state_root"]))
        foundation_bundle = store.resolve("workspace-foundation", foundation_manifest_digest)
    except (BundleError, OSError):
        errors.append("STALE_WORKSPACE_FOUNDATION")
        return sorted(set(errors))
    foundation = foundation_bundle.artifacts["workspace-foundation"]
    foundation_digest = foundation_bundle.manifest["artifacts"]["workspace-foundation"]["digest"]
    if (
        foundation_ref.get("artifact_digest") != foundation_digest
        or foundation.get("state") != "WORKSPACE_FOUNDATION_VERIFIED"
        or foundation.get("blockers")
        or foundation.get("server_ref") != handoff.get("server_ref")
        or foundation.get("server_kind") != handoff.get("server_kind")
        or foundation.get("workspace_ref") != handoff.get("workspace_ref")
        or foundation.get("deployment_key", handoff.get("deployment_key")) != handoff.get("deployment_key")
        or foundation.get("workspace_key") != handoff.get("workspace_key")
        or foundation.get("relocation_intent_digest") != handoff.get("relocation_intent_digest")
        or foundation.get("runtime_fleet", {}).get("membership_digest") != fleet.get("membership_digest")
    ):
        errors.append("STALE_WORKSPACE_FOUNDATION")
    foundation_capabilities = foundation.get("orchestration_capabilities")
    native_routing = (
        foundation_capabilities.get("native_squad_routing")
        if isinstance(foundation_capabilities, dict)
        else None
    )
    if (
        not isinstance(foundation_capabilities, dict)
        or foundation_capabilities.get("state") != "VERIFIED"
        or not isinstance(native_routing, dict)
        or not native_routing
        or not all(value is True for value in native_routing.values())
    ):
        errors.append("FOUNDATION_NATIVE_SQUAD_CAPABILITY_UNVERIFIED")
    return sorted(set(errors))

def parse_binding_scalars(path: Path) -> dict[str, Any]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise InputError(f"cannot read repository binding manifest: {path}: {error}") from error
    result: dict[str, Any] = {}
    stack: list[tuple[int, str]] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"(?P<indent> *)(?P<key>[A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]*(?P<value>.*))?", line)
        if match is None:
            raise InputError(f"repository binding manifest line {number} is not a supported scalar mapping")
        indent = len(match.group("indent"))
        if indent % 2:
            raise InputError(f"repository binding manifest line {number} has invalid indentation")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if stack and indent != stack[-1][0] + 2:
            raise InputError(f"repository binding manifest line {number} skips a mapping level")
        key = match.group("key")
        raw = (match.group("value") or "").strip()
        dotted = ".".join([item[1] for item in stack] + [key])
        if not raw:
            stack.append((indent, key))
            continue
        if raw.startswith('"'):
            try:
                value: Any = json.loads(raw)
            except json.JSONDecodeError as error:
                raise InputError(f"repository binding manifest line {number} has an invalid quoted scalar") from error
        elif raw in {"true", "false"}:
            value = raw == "true"
        elif raw == "null":
            value = None
        else:
            value = raw
        result[dotted] = value
    return result


def validate_binding_manifest(path: Path, configuration: Mapping[str, Any], handoff: Mapping[str, Any]) -> None:
    values = parse_binding_scalars(path)
    package = require_mapping(handoff.get("package"), "server handoff package")
    require_mapping(handoff.get("project_binding_contract"), "server handoff project binding contract")
    repository = configuration["repository"]
    policy = configuration["policy"]
    commands = configuration["command_profiles"][policy["repository_command_profile"]]
    expected: dict[str, Any] = {
        "schema_version": "10",
        "orchestrator_profile.id": package.get("id"),
        "orchestrator_profile.contract_version": package.get("contract_version"),
        "orchestrator_profile.manifest_digest": package.get("manifest_digest"),
        "repository.provider": repository["provider"],
        "repository.execution_mode": policy["execution_mode"],
        "repository.work_item_id_source": policy["work_item_id_source"],
        "repository.runtime_branch_authority": policy["runtime_branch_authority"],
        "repository.integration_branch_authority": policy["integration_branch_authority"],
        "repository.main_ref": policy["main_ref"],
        "repository.develop_ref": policy["develop_ref"],
        "paths.project_root": repository["project_subpath"],
        "workflow.feature_squad": "feature",
        "workflow.fix_squad": "fix",
        "workflow.default_worktree": True,
        "workflow.loop_isolation": "runtime-worktree",
        "workflow.native_squad_routing": True,
        "workflow.leader_first": True,
        "workflow.exact_member_mentions": True,
        "workflow.member_reply_retriggers_leader": True,
        "workflow.runtime_open_fence": True,
        "workflow.collaboration_runtime": handoff.get("agents", {}).get("collaboration_runtime_alias"),
        "workflow.one_active_writer_per_work_item": True,
    }
    for name, command in commands.items():
        if "command" in command:
            expected[f"commands.{name}.command"] = command["command"]
        else:
            expected[f"commands.{name}.na_policy_ref"] = command["na_policy_ref"]
    mismatches = [key for key, value in expected.items() if values.get(key) != value]
    if mismatches:
        raise InputError("repository binding manifest does not match current project input: " + ", ".join(sorted(mismatches)))




def validate_portable_config(path: Path, label: str) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise InputError(f"cannot read {label}: {path}: {error}") from error
    if not content.strip():
        raise InputError(f"{label} is empty")
    if re.search(r"<[^>\n]+>", content):
        raise InputError(f"{label} contains unresolved placeholders")
    forbidden = (
        r"\b(?:workspace|runtime|agent|squad|label|resource)[_-](?:id|ref)\b",
        r"\bserver_ref\b",
        r"\baccount_ref\b",
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
        r"(?:^|[\s`'\"])/(?:Users|home|var|private|opt|tmp)/",
    )
    if any(re.search(pattern, content, re.IGNORECASE | re.MULTILINE) for pattern in forbidden):
        raise InputError(f"{label} contains a live identifier or absolute machine path")






def multica_environment(server_kind: str) -> dict[str, str]:
    environment = dict(os.environ)
    if server_kind == "self-hosted":
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            environment.pop(name, None)
    return environment


def run_multica(configuration: Mapping[str, Any], executable: str, arguments: list[str]) -> Any:
    server = configuration["server"]
    command = [executable, "--profile", server["profile"], "--workspace-id", server["workspace_ref"], *arguments, "--output", "json"]
    completed = subprocess.run(command, text=True, capture_output=True, env=multica_environment(server["kind"]), check=False)
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise InputError(f"multica command failed: {detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise InputError("multica command did not return JSON") from error
