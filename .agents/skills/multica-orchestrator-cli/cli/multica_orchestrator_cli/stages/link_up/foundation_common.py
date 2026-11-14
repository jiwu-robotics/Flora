"""Stdlib-only helpers for workspace foundation plans and verification."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping
from multica_state_bundle.identities import canonical_json, digest_bytes

INPUT_SCHEMA = "multica-orchestrator-link-up.workspace-foundation-input.v3"
OUTPUT_SCHEMA = "multica-orchestrator-link-up.workspace-foundation-ref.v6"
PLAN_SCHEMA = "multica-orchestrator-link-up.workspace-foundation-plan.v4"
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
LABEL_COLORS = {"bug": "#ef4444", "enhancement": "#3b82f6"}
STATUS_CODES = (
    "needs_triage",
    "needs_information",
    "ready_for_agent",
    "ready_for_human",
    "wontfix",
)
NATIVE_SQUAD_CAPABILITIES = {
    "leader_first_surface",
    "exact_member_routing_surface",
    "no_start_assignment_surface",
    "thread_reply_surface",
    "run_readback_surface",
    "membership_role_surface",
    "private_agent_surface",
}


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
        items = next((value[key] for key in ("items", "data", "results", "labels", "runtimes", "workspaces", "members") if isinstance(value.get(key), list)), None)
        if items is None:
            raise InputError(f"{label} does not contain a list")
    else:
        raise InputError(f"{label} must be a list or list wrapper")
    if not all(isinstance(item, dict) for item in items):
        raise InputError(f"{label} contains a non-object")
    return items


def readback_snapshot_digest(
    snapshot_path: Path,
    *,
    server_ref: str | None = None,
    profile_ref: str | None = None,
    account_ref: str | None = None,
    workspace_ref: str | None = None,
    runtime_refs: list[str] | None = None,
) -> str:
    snapshot = require_mapping(read_json(snapshot_path, "workspace readback snapshot"), "workspace readback snapshot")
    if snapshot.get("schema") != "multica-orchestrator-link-up.readback-snapshot.v2":
        raise InputError("workspace readback snapshot schema is invalid")
    expected_identity = {
        "server_ref": server_ref,
        "profile_ref": profile_ref,
        "account_ref": account_ref,
        "workspace_ref": workspace_ref,
        "runtime_refs": sorted(runtime_refs) if runtime_refs is not None else None,
    }
    mismatches = [
        name
        for name, expected in expected_identity.items()
        if expected is not None and snapshot.get(name) != expected
    ]
    if mismatches:
        raise InputError("workspace readback snapshot identity mismatch: " + ", ".join(mismatches))
    artifacts = require_mapping(snapshot.get("artifacts"), "workspace readback snapshot artifacts")
    if not artifacts:
        raise InputError("workspace readback snapshot has no artifacts")
    root = snapshot_path.parent.resolve()
    for relative, expected in artifacts.items():
        path = (root / require_string(relative, "snapshot artifact path")).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise InputError("workspace readback snapshot artifact escapes its directory") from error
        if not path.is_file() or digest_bytes(path.read_bytes()) != expected:
            raise InputError(f"workspace readback snapshot artifact digest mismatch: {relative}")
    unsigned = dict(snapshot)
    observed = unsigned.pop("snapshot_digest", None)
    actual = digest_bytes(canonical_json(unsigned))
    if observed != actual:
        raise InputError("workspace readback snapshot digest is invalid")
    return actual


def load_input(path: Path) -> Mapping[str, Any]:
    value = require_mapping(read_json(path, "workspace foundation input"), "workspace foundation input")
    if value.get("schema") != INPUT_SCHEMA:
        raise InputError(f"input schema must equal {INPUT_SCHEMA}")
    forbidden = {"repository", "project", "local_path", "checkout", "work_item"} & set(value)
    if forbidden:
        raise InputError(f"PROJECT_SCOPE_NOT_ALLOWED: {sorted(forbidden)}")
    expected = {
        "schema",
        "operator_state_root",
        "server",
        "workspace",
        "labels",
        "statuses",
        "runtime_fleet",
        "orchestration_capabilities",
    }
    if set(value) != expected:
        raise InputError(f"input fields must exactly equal {sorted(expected)}")
    state_root = value["operator_state_root"]
    if not isinstance(state_root, str) or not Path(state_root).is_absolute() or ".." in Path(state_root).parts:
        raise InputError("operator_state_root must be an absolute normalized path")

    server = require_mapping(value["server"], "server")
    if server.get("kind") not in {"cloud", "self-hosted"}:
        raise InputError("server.kind must be cloud or self-hosted")
    for field in ("ref", "profile", "account_ref"):
        require_string(server.get(field), f"server.{field}")
    if server.get("deployment_key") is not None and (
        not isinstance(server["deployment_key"], str)
        or DIGEST.fullmatch(server["deployment_key"]) is None
    ):
        raise InputError("server.deployment_key must be a SHA-256 digest")
    if server.get("relocation_intent_digest") is not None and (
        not isinstance(server["relocation_intent_digest"], str)
        or DIGEST.fullmatch(server["relocation_intent_digest"]) is None
    ):
        raise InputError("server.relocation_intent_digest must be a SHA-256 digest")

    workspace = require_mapping(value["workspace"], "workspace")
    require_string(workspace.get("name"), "workspace.name")
    if not isinstance(workspace.get("exists"), bool):
        raise InputError("workspace.exists must be boolean")
    if workspace["exists"] and not workspace.get("workspace_ref"):
        raise InputError("existing workspace requires workspace_ref")
    if not workspace["exists"]:
        require_string(workspace.get("slug"), "workspace.slug")
        require_string(workspace.get("issue_prefix"), "workspace.issue_prefix")

    labels = require_mapping(value["labels"], "labels")
    if set(labels) != set(LABEL_COLORS):
        raise InputError("labels must contain exactly bug and enhancement")
    for name, item_value in labels.items():
        item = require_mapping(item_value, f"labels.{name}")
        if not isinstance(item.get("exists"), bool):
            raise InputError(f"labels.{name}.exists must be boolean")
        require_string(item.get("color"), f"labels.{name}.color")
        if item["exists"] and not item.get("label_ref"):
            raise InputError(f"existing label {name} requires label_ref")

    statuses = require_mapping(value["statuses"], "statuses")
    if set(statuses) != set(STATUS_CODES):
        raise InputError("statuses do not exactly match the canonical status keys")
    for key, item_value in statuses.items():
        item = require_mapping(item_value, f"statuses.{key}")
        if item.get("state") not in {"VERIFIED", "PENDING_CONFIRMATION", "CONFLICT"}:
            raise InputError(f"statuses.{key}.state is invalid")
        require_string(item.get("evidence_ref"), f"statuses.{key}.evidence_ref")

    fleet = require_mapping(value["runtime_fleet"], "runtime_fleet")
    runtimes = fleet.get("runtimes")
    if not isinstance(runtimes, list) or not runtimes:
        raise InputError("runtime_fleet.runtimes must be a non-empty array")
    aliases: set[str] = set()
    runtime_refs: set[str] = set()
    for index, runtime_value in enumerate(runtimes):
        runtime = require_mapping(runtime_value, f"runtime_fleet.runtimes[{index}]")
        alias = require_string(runtime.get("alias"), f"runtime_fleet.runtimes[{index}].alias")
        if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", alias) is None or alias in aliases:
            raise InputError("runtime aliases must be unique lowercase kebab-case values")
        aliases.add(alias)
        require_string(runtime.get("name"), f"runtime_fleet.runtimes[{index}].name")
        if not isinstance(runtime.get("exists"), bool) or not isinstance(runtime.get("daemon_start_required"), bool):
            raise InputError("runtime exists and daemon_start_required must be boolean")
        if runtime.get("status") not in {"online", "offline", "missing"}:
            raise InputError("runtime.status is invalid")
        if runtime["exists"]:
            runtime_ref = require_string(runtime.get("runtime_ref"), "existing runtime runtime_ref")
            require_string(runtime.get("daemon_ref"), "existing runtime daemon_ref")
            if runtime_ref in runtime_refs:
                raise InputError("runtime_ref must be unique in runtime fleet")
            runtime_refs.add(runtime_ref)
        if profile := runtime.get("profile"):
            profile = require_mapping(profile, "runtime.profile")
            for field in ("display_name", "command_name", "protocol_family"):
                require_string(profile.get(field), f"runtime.profile.{field}")
            if not isinstance(profile.get("exists"), bool):
                raise InputError("runtime.profile.exists must be boolean")
    orchestration = require_mapping(
        value["orchestration_capabilities"],
        "orchestration_capabilities",
    )
    if orchestration.get("state") not in {"VERIFIED", "BLOCKED"}:
        raise InputError("orchestration_capabilities.state is invalid")
    require_string(
        orchestration.get("evidence_ref"),
        "orchestration_capabilities.evidence_ref",
    )
    native_routing = require_mapping(
        orchestration.get("native_squad_routing"),
        "orchestration_capabilities.native_squad_routing",
    )
    if set(native_routing) != NATIVE_SQUAD_CAPABILITIES or not all(
        isinstance(value, bool) for value in native_routing.values()
    ):
        raise InputError("native Squad routing capabilities are incomplete")
    return value


def foundation_blockers(configuration: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    workspace = configuration["workspace"]
    if not workspace["exists"] or not workspace.get("workspace_ref"):
        blockers.append("WORKSPACE_UNVERIFIED")
    for name, desired in LABEL_COLORS.items():
        item = configuration["labels"][name]
        if not item["exists"] or not item.get("label_ref"):
            blockers.append(f"LABEL_{name.upper()}_UNVERIFIED")
        elif item["color"].lower() != desired:
            blockers.append(f"LABEL_{name.upper()}_CONFLICT")
    for runtime in configuration["runtime_fleet"]["runtimes"]:
        subject = runtime["alias"].upper().replace("-", "_")
        if not runtime["exists"] or runtime["status"] != "online" or not runtime.get("runtime_ref"):
            blockers.append(f"RUNTIME_NOT_ONLINE:{subject}")
        if not runtime.get("daemon_ref"):
            blockers.append(f"RUNTIME_DAEMON_UNVERIFIED:{subject}")
        if not runtime.get("provider") or not runtime.get("capability_revision"):
            blockers.append(f"RUNTIME_CAPABILITY_UNVERIFIED:{subject}")
    orchestration = configuration["orchestration_capabilities"]
    if orchestration["state"] != "VERIFIED" or not all(
        orchestration["native_squad_routing"].values()
    ):
        blockers.append("NATIVE_SQUAD_CAPABILITY_UNAVAILABLE")
    return sorted(set(blockers))




def multica_environment(server_kind: str) -> dict[str, str]:
    environment = dict(os.environ)
    if server_kind == "self-hosted":
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            environment[name] = ""
    return environment


def run_multica(configuration: Mapping[str, Any], executable: str, arguments: list[str], *, workspace_scoped: bool, json_output: bool = True) -> Any:
    server = configuration["server"]
    command = [executable, "--profile", server["profile"]]
    if workspace_scoped:
        workspace_ref = configuration["workspace"].get("workspace_ref")
        if not workspace_ref:
            raise InputError("workspace-scoped operation requires workspace_ref")
        command.extend(["--workspace-id", workspace_ref])
    command.extend(arguments)
    if json_output:
        command.extend(["--output", "json"])
    completed = subprocess.run(command, env=multica_environment(server["kind"]), text=True, capture_output=True, check=False)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise InputError(f"multica command failed ({completed.returncode}): {detail}")
    if not json_output:
        return {"stdout": completed.stdout.strip()}
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise InputError("multica command did not return JSON") from error
