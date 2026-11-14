"""Shared validation and process helpers for Runtime-host migration."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from multica_state_bundle.bundle_store import BundleStore
from multica_state_bundle.handoff import Bundle, BundleError, canonical_json, digest_bytes
from multica_state_bundle.identities import canonical_json as compact_json, utc_now
from multica_orchestrator_cli.common.runtime_activation import (
    ACTIVATION_RECEIPT_SCHEMA,
    ACTIVATION_RECEIPT_WIRE,
    local_directory_execution_mode,
    local_directory_resource_identity,
)
INPUT_SCHEMA = "multica-orchestrator-migrate.input.v5"
PREFLIGHT_SCHEMA = "multica-orchestrator-migrate.target-preflight.v3"
PLAN_SCHEMA = "multica-orchestrator-migrate.plan.v3"
OPERATION_RECEIPT_SCHEMA = "multica-orchestrator-migrate.operation-receipt.v1"
AGGREGATE_SCHEMA = "multica-orchestrator.activation-aggregate.v2"
ACTIVE_RELEASE_SCHEMA = "multica-orchestrator.active-project-release.v2"
CANDIDATE_SCHEMAS = {
    "multica-orchestrator.project-release-candidate.v8",
}
NATIVE_SQUAD_CLI_REQUIREMENTS = {
    "agent-create": (("agent", "create"), frozenset({"--description", "--instructions", "--permission-mode", "--runtime-id", "--model", "--max-concurrent-tasks"})),
    "agent-update": (("agent", "update"), frozenset({"--description", "--instructions", "--permission-mode", "--runtime-id", "--model", "--max-concurrent-tasks"})),
    "agent-get": (("agent", "get"), frozenset()),
    "agent-skills-list": (("agent", "skills", "list"), frozenset()),
    "squad-create": (("squad", "create"), frozenset({"--description", "--instructions", "--leader"})),
    "squad-update": (("squad", "update"), frozenset({"--description", "--instructions", "--leader-id"})),
    "squad-get": (("squad", "get"), frozenset()),
    "squad-member-add": (("squad", "member", "add"), frozenset({"--type"})),
    "squad-member-list": (("squad", "member", "list"), frozenset()),
    "issue-assign": (("issue", "assign"), frozenset({"--to-id", "--no-start"})),
    "issue-comment-add": (("issue", "comment", "add"), frozenset({"--content", "--parent"})),
    "run-list": (("run", "list"), frozenset()),
}
NATIVE_SQUAD_DISPATCH_KEYS = {
    "leader_first",
    "leader_routes_by_exact_member_mention",
    "member_reply_retriggers_leader",
    "issue_assignment_no_start_required",
    "runtime_open_fence_required",
}
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PROXY_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")



class MigrationError(ValueError):
    """Migration input or observed state cannot be trusted."""




def encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"




def read_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise MigrationError(f"cannot read {label}: {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise MigrationError(f"invalid JSON in {label}: {path}: {error.msg}") from error
    if not isinstance(value, dict):
        raise MigrationError(f"{label} must be an object")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MigrationError(f"{label} must be a non-empty string")
    return value


def require_digest(value: Any, label: str) -> str:
    result = require_string(value, label)
    if DIGEST.fullmatch(result) is None:
        raise MigrationError(f"{label} must be a sha256 digest")
    return result


def require_absolute(value: Any, label: str) -> str:
    result = require_string(value, label)
    if not PurePosixPath(result).is_absolute() or ".." in PurePosixPath(result).parts:
        raise MigrationError(f"{label} must be an absolute normalized POSIX path")
    return result


def github_slug(value: str) -> str:
    if re.fullmatch(r"git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", value):
        return value.split(":", 1)[1].removesuffix(".git")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password:
        raise MigrationError("repository.url must be a credential-free GitHub SSH or HTTPS URL")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise MigrationError("repository.url must identify one GitHub repository")
    return "/".join(parts).removesuffix(".git")

def native_squad_capability_errors(help_texts: Mapping[str, tuple[int, str]]) -> list[str]:
    errors: list[str] = []
    for name, (_, required_flags) in NATIVE_SQUAD_CLI_REQUIREMENTS.items():
        result = help_texts.get(name)
        if result is None or result[0] != 0:
            errors.append(f"NATIVE_SQUAD_COMMAND_UNAVAILABLE:{name}")
            continue
        missing = sorted(required_flags - set(re.findall(r"--[a-z0-9-]+", result[1])))
        errors.extend(f"NATIVE_SQUAD_FLAG_UNAVAILABLE:{name}:{flag}" for flag in missing)
    return errors


def load_input(path: Path) -> Mapping[str, Any]:
    value = read_json(path, "migration input")
    if value.get("schema") != INPUT_SCHEMA or set(value) != {"schema", "source", "server", "repository", "targets"}:
        raise MigrationError(f"migration input must use {INPUT_SCHEMA} and exact top-level fields")
    source = value.get("source")
    server = value.get("server")
    repository = value.get("repository")
    targets = value.get("targets")
    if not isinstance(source, dict) or set(source) != {
        "state_root", "operator_state_root", "project_bundle_manifest_digest",
        "release_candidate_path", "release_candidate_digest",
        "primary_runtime_alias", "source_active_release_digest",
    }:
        raise MigrationError("source fields are invalid")
    require_absolute(source.get("state_root"), "source.state_root")
    require_absolute(source.get("operator_state_root"), "source.operator_state_root")
    if PurePosixPath(source["state_root"]) != PurePosixPath(source["operator_state_root"]) / "bundle-store":
        raise MigrationError("source.state_root must equal source.operator_state_root/bundle-store")
    require_digest(source.get("project_bundle_manifest_digest"), "source.project_bundle_manifest_digest")
    require_absolute(source.get("release_candidate_path"), "source.release_candidate_path")
    require_digest(source.get("release_candidate_digest"), "source.release_candidate_digest")
    require_string(source.get("primary_runtime_alias"), "source.primary_runtime_alias")
    require_digest(source.get("source_active_release_digest"), "source.source_active_release_digest")
    if not isinstance(server, dict) or set(server) not in (
        {"kind", "ref", "workspace_ref"},
        {"kind", "ref", "workspace_ref", "deployment_key"},
    ):
        raise MigrationError("server fields are invalid")
    if server.get("kind") not in {"cloud", "self-hosted"}:
        raise MigrationError("server.kind must be cloud or self-hosted")
    require_string(server.get("ref"), "server.ref")
    require_string(server.get("workspace_ref"), "server.workspace_ref")
    if server.get("deployment_key") is not None:
        require_digest(server["deployment_key"], "server.deployment_key")
    if not isinstance(repository, dict) or set(repository) != {"url", "project_subpath"}:
        raise MigrationError("repository fields are invalid")
    github_slug(require_string(repository.get("url"), "repository.url"))
    subpath = PurePosixPath(require_string(repository.get("project_subpath"), "repository.project_subpath"))
    if subpath.is_absolute() or ".." in subpath.parts:
        raise MigrationError("repository.project_subpath must be relative and contained")
    if not isinstance(targets, list) or not targets:
        raise MigrationError("targets must be a non-empty array")
    aliases: set[str] = set()
    hosts: set[str] = set()
    for index, target in enumerate(targets):
        expected = {"runtime_alias", "ssh_config_host", "profile", "account_ref", "state_root", "repository_root", "remote_receipt_path", "coordinator_receipt_path"}
        if not isinstance(target, dict) or set(target) != expected:
            raise MigrationError(f"targets[{index}] fields are invalid")
        alias = require_string(target.get("runtime_alias"), f"targets[{index}].runtime_alias")
        host = require_string(target.get("ssh_config_host"), f"targets[{index}].ssh_config_host")
        profile = require_string(target.get("profile"), f"targets[{index}].profile")
        if any(SAFE_NAME.fullmatch(item) is None for item in (alias, host, profile)):
            raise MigrationError(f"targets[{index}] alias, SSH host, and profile must be shell-independent names")
        if alias in aliases or host in hosts:
            raise MigrationError("target Runtime aliases and SSH hosts must be unique")
        aliases.add(alias)
        hosts.add(host)
        require_string(target.get("account_ref"), f"targets[{index}].account_ref")
        for key in ("state_root", "repository_root", "remote_receipt_path", "coordinator_receipt_path"):
            require_absolute(target.get(key), f"targets[{index}].{key}")
    return value


def load_release_context(configuration: Mapping[str, Any]) -> tuple[Mapping[str, Any], Bundle, Bundle, Bundle, tuple[Bundle, ...]]:
    source = configuration["source"]
    candidate_path = Path(source["release_candidate_path"])
    if digest_bytes(candidate_path.read_bytes()) != source["release_candidate_digest"]:
        raise MigrationError("release candidate digest mismatch")
    candidate = read_json(candidate_path, "release candidate")
    if candidate.get("schema") not in CANDIDATE_SCHEMAS:
        raise MigrationError("release candidate schema is invalid")
    if candidate.get("project_bundle_manifest_digest") != source["project_bundle_manifest_digest"]:
        raise MigrationError("release candidate names a different Project bundle")
    try:
        store = BundleStore(Path(source["state_root"]))
        closure = store.closure("project-binding", source["project_bundle_manifest_digest"])
    except (BundleError, OSError) as error:
        raise MigrationError(f"Project bundle closure is invalid: {error}") from error
    if [bundle.stage for bundle in closure] != ["workspace-foundation", "server-orchestration", "project-binding"]:
        raise MigrationError("Project bundle closure must be Foundation, Server, Project")
    foundation, server, project = closure
    foundation_ref = foundation.artifacts["workspace-foundation"]
    server_ref = server.artifacts["server-orchestration"]
    project_ref = project.artifacts["project-binding"]
    runtime_policy = project.artifacts["runtime-target-policy"]
    verification_spec = project.artifacts["project-verification-spec"]
    project_reissue = project.artifacts["project-reissue-spec"]
    server_reissue = server.artifacts["server-reissue-spec"]
    if foundation_ref.get("state") != "WORKSPACE_FOUNDATION_VERIFIED" or foundation_ref.get("blockers"):
        raise MigrationError("Foundation bundle is not verified")
    if server_ref.get("state") != "ORCHESTRATOR_LAYER_VERIFIED":
        raise MigrationError("Server bundle is not verified")
    if project_ref.get("state") != "PROJECT_BOUND" or project_ref.get("activation_state") != "ACTIVE" or project_ref.get("blockers"):
        raise MigrationError("Project bundle is not ACTIVE or has blockers")
    if (
        project_reissue.get("schema") != "multica-orchestrator.project-reissue-spec.v3"
        or server_reissue.get("schema") != "multica-orchestrator.server-reissue-spec.v1"
    ):
        raise MigrationError("portable reissue specifications are invalid")
    server_input = configuration["server"]
    if any(server_ref.get(key) != server_input[value] for key, value in (("server_ref", "ref"), ("server_kind", "kind"), ("workspace_ref", "workspace_ref"))):
        raise MigrationError("migration server identity differs from bundle")
    deployment_key = server_ref.get("deployment_key", project_ref.get("deployment_key"))
    if server_input.get("deployment_key") is not None and deployment_key != server_input["deployment_key"]:
        raise MigrationError("migration deployment identity differs from bundle")
    if candidate.get("deployment_key") != deployment_key:
        raise MigrationError("release candidate deployment identity differs")
    if candidate.get("relocation_intent_digest") != project_ref.get("relocation_intent_digest"):
        raise MigrationError("release candidate relocation lineage differs")
    expected_repository_identity = "github:" + github_slug(configuration["repository"]["url"])
    if project_ref.get("repository_identity") != expected_repository_identity:
        raise MigrationError("migration repository differs from Project bundle")
    if candidate.get("repository_identity") != expected_repository_identity:
        raise MigrationError("release candidate repository identity differs")
    if candidate.get("project_subpath") != configuration["repository"]["project_subpath"]:
        raise MigrationError("release candidate project subpath differs")
    if project_ref.get("repository_policy", {}).get("project_subpath") != configuration["repository"]["project_subpath"]:
        raise MigrationError("migration project subpath differs from Project bundle")
    if project_ref.get("repository_policy", {}).get("execution_mode") != "worktree":
        raise MigrationError("Project bundle does not require worktree execution")
    if (
        verification_spec.get("project_key") != project_ref.get("project_key")
        or verification_spec.get("repository_identity") != project_ref.get("repository_identity")
    ):
        raise MigrationError("Project verification specification lineage is invalid")
    dispatch = runtime_policy.get("native_squad_dispatch")
    dispatch_digest = digest_bytes(compact_json(dispatch)) if isinstance(dispatch, dict) else None
    foundation_capabilities = foundation_ref.get("orchestration_capabilities")
    native_routing = (
        foundation_capabilities.get("native_squad_routing")
        if isinstance(foundation_capabilities, dict)
        else None
    )
    if (
        runtime_policy.get("schema") != "multica-orchestrator.runtime-target-policy.v4"
        or not isinstance(dispatch, dict)
        or set(dispatch) != NATIVE_SQUAD_DISPATCH_KEYS
        or not all(dispatch[key] is True for key in NATIVE_SQUAD_DISPATCH_KEYS)
        or project_ref.get("native_squad_dispatch") != dispatch
        or project_ref.get("runtime_target_policy_digest") != digest_bytes(compact_json(runtime_policy))
        or verification_spec.get("native_squad_dispatch_digest") != dispatch_digest
        or candidate.get("native_squad_dispatch_digest") != dispatch_digest
        or not isinstance(foundation_capabilities, dict)
        or foundation_capabilities.get("state") != "VERIFIED"
        or not isinstance(native_routing, dict)
        or not native_routing
        or not all(value is True for value in native_routing.values())
    ):
        raise MigrationError("native Squad dispatch policy or capability lineage is invalid")
    dispatch_contract_digest = project_ref.get("dispatch_contract_digest")
    if (
        not isinstance(dispatch_contract_digest, str)
        or DIGEST.fullmatch(dispatch_contract_digest) is None
        or verification_spec.get("dispatch_contract_digest") != dispatch_contract_digest
        or project_reissue.get("dispatch_contract_digest") != dispatch_contract_digest
        or candidate.get("dispatch_contract_digest") != dispatch_contract_digest
    ):
        raise MigrationError("Dispatch contract lineage is invalid")
    fleet_by_alias = {
        item["alias"]: item
        for item in server_ref.get("runtime_fleet", {}).get("runtimes", [])
        if isinstance(item, Mapping) and isinstance(item.get("alias"), str)
    }
    required_capabilities = [
        {
            "runtime_alias": item["runtime_alias"],
            "required_capability_revision": item["required_capability_revision"],
        }
        for item in sorted(runtime_policy["required_runtimes"], key=lambda item: item["runtime_alias"])
    ]
    runtime_capability_digest = digest_bytes(compact_json(required_capabilities))
    if (
        candidate.get("runtime_capability_digest") != runtime_capability_digest
        or project_ref.get("repository_policy", {}).get("runtime_capability_digest")
        != runtime_capability_digest
        or any(
            item["required_capability_revision"]
            != fleet_by_alias.get(item["runtime_alias"], {}).get("capability_revision")
            for item in runtime_policy["required_runtimes"]
        )
    ):
        raise MigrationError("Runtime capability lineage is invalid")
    required_aliases = {item["runtime_alias"] for item in runtime_policy["required_runtimes"]}
    optional_aliases = {item["runtime_alias"] for item in runtime_policy["optional_runtimes"]}
    target_aliases = {item["runtime_alias"] for item in configuration["targets"]}
    primary_alias = configuration["source"]["primary_runtime_alias"]
    if len(required_aliases) != 1 or primary_alias not in required_aliases:
        raise MigrationError("primary Runtime identity differs from Project policy")
    if primary_alias in target_aliases or not target_aliases or not target_aliases <= optional_aliases:
        raise MigrationError("migration targets must be a non-empty optional Runtime subset")
    if set(candidate.get("required_runtime_aliases", [])) != required_aliases:
        raise MigrationError("release candidate required Runtime aliases differ from policy")
    fleet_aliases = {item.get("alias") for item in server_ref.get("runtime_fleet", {}).get("runtimes", [])}
    if not target_aliases <= fleet_aliases:
        raise MigrationError("a migration target is absent from the Server Runtime fleet")
    return candidate, foundation, server, project, closure


def target_context(configuration: Mapping[str, Any], project_bundle: Bundle, alias: str) -> dict[str, Any]:
    project = project_bundle.artifacts["project-binding"]
    policy = project_bundle.artifacts["runtime-target-policy"]
    server_digest = project_bundle.parents[0]["manifest_digest"]
    store = BundleStore(Path(configuration["source"]["state_root"]))
    server_bundle = store.resolve("server-orchestration", server_digest)
    server = server_bundle.artifacts["server-orchestration"]
    runtime_matches = [item for item in server["runtime_fleet"]["runtimes"] if item["alias"] == alias]
    target_matches = [item for group in ("required_runtimes", "optional_runtimes") for item in policy[group] if item["runtime_alias"] == alias]
    configured_matches = [item for item in configuration["targets"] if item["runtime_alias"] == alias]
    if len(runtime_matches) != 1 or len(target_matches) != 1 or len(configured_matches) != 1:
        raise MigrationError(f"Runtime target {alias} is not unique")
    return {
        **configured_matches[0],
        "required": any(item["runtime_alias"] == alias for item in policy["required_runtimes"]),
        "runtime": runtime_matches[0],
        "target_policy": target_matches[0],
        "project_ref": project["project_ref"],
        "project_key": project["project_key"],
        "repository_identity": project["repository_identity"],
        "generation": None,
    }


def records(value: Any, label: str) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        items = next((value[key] for key in ("items", "data", "results", "runtimes", "workspaces", "resources") if isinstance(value.get(key), list)), None)
        if items is None:
            raise MigrationError(f"{label} does not contain a record list")
    else:
        raise MigrationError(f"{label} is not a record list")
    if not all(isinstance(item, dict) for item in items):
        raise MigrationError(f"{label} contains a non-object")
    return items


def local_directory_resource_matches(item: Mapping[str, Any], *, root: str, daemon_ref: str) -> bool:
    return local_directory_resource_identity(item) == (root, daemon_ref)




def proxy_environment(server_kind: str) -> dict[str, str]:
    result = dict(os.environ)
    if server_kind == "self-hosted":
        for name in PROXY_NAMES:
            result.pop(name, None)
    return result


def run_process(command: Sequence[str], *, environment: Mapping[str, str] | None = None, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(list(command), text=True, capture_output=True, env=environment, check=False)
    if completed.returncode and not allow_failure:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise MigrationError(f"command failed: {command[0]}: {detail}")
    return completed


def ssh_command(host: str, arguments: Sequence[str], *, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    if SAFE_NAME.fullmatch(host) is None:
        raise MigrationError("SSH configuration host is invalid")
    remote = shlex.join(list(arguments))
    return run_process(["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "--", host, remote], allow_failure=allow_failure)


def scp_to(host: str, source: Path, destination: str, *, recursive: bool = False) -> None:
    require_absolute(destination, "remote copy destination")
    command = ["scp", "-q", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes"]
    if recursive:
        command.append("-r")
    command.extend(["--", str(source), f"{host}:{destination}"])
    run_process(command)


def scp_from(host: str, source: str, destination: Path) -> None:
    require_absolute(source, "remote copy source")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    run_process(["scp", "-q", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "--", f"{host}:{source}", str(destination)])


def parse_json_stdout(completed: subprocess.CompletedProcess[str], label: str) -> Any:
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise MigrationError(f"{label} did not return JSON") from error


def nested_contains(value: Any, expected: str) -> bool:
    if value == expected:
        return True
    if isinstance(value, dict):
        return any(nested_contains(item, expected) for item in value.values())
    if isinstance(value, list):
        return any(nested_contains(item, expected) for item in value)
    return False
