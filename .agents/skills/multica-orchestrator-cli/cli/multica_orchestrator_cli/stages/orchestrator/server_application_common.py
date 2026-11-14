"""Stdlib-only helpers for reusable Multica server-layer application."""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from multica_state_bundle.bundle_store import BundleStore
from multica_state_bundle.handoff import BundleError
from multica_state_bundle.identities import canonical_json, digest_bytes
INPUT_SCHEMA = "multica-orchestrator.server-application-input.v7"
FOUNDATION_SCHEMAS = {
    "multica-orchestrator-link-up.workspace-foundation-ref.v5",
    "multica-orchestrator-link-up.workspace-foundation-ref.v6",
}
NATIVE_SQUAD_CAPABILITIES = {
    "leader_first_surface",
    "exact_member_routing_surface",
    "no_start_assignment_surface",
    "thread_reply_surface",
    "run_readback_surface",
    "membership_role_surface",
    "private_agent_surface",
}
ROLE = re.compile(r"^  - role_key: (?P<value>[A-Za-z0-9_-]+)\s*$")
DESCRIPTION = re.compile(r'^    description: "(?P<value>[^"]+)"\s*$')
INSTRUCTIONS = re.compile(r"^    instructions: (?P<value>\S+)\s*$")
WORK_TYPE = re.compile(r"^    work_type: (?P<value>shared|feature|fix)\s*$")
REQUIRED = re.compile(r"^    required_skills:\s*$")
OPTIONAL = re.compile(r"^    optional_skills:\s*$")
SKILL = re.compile(r"^      - (?P<value>[A-Za-z0-9_.-]+)\s*$")
OPTIONAL_SKILL = re.compile(r"^      - name: (?P<value>[A-Za-z0-9_.-]+)\s*$")
FIELD = re.compile(r"^    [A-Za-z_][A-Za-z0-9_]*:")
SQUAD = re.compile(r"^  - squad_key: (?P<value>[a-z][a-z0-9-]+)\s*$")
SQUAD_LEADER = re.compile(r"^    leader: (?P<value>[a-z][a-z0-9-]+)\s*$")
SQUAD_MEMBER = re.compile(r"^      - role_key: (?P<value>[a-z][a-z0-9-]+)\s*$")
SQUAD_ROLE = re.compile(r'^        squad_role: "(?P<value>[^"]+)"\s*$')
ROOT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:")
ROLE_OPERATION = re.compile(
    r"^      (?P<role>[a-z][a-z0-9-]+): \[(?P<operations>[a-z0-9-, ]+)\]\s*$"
)
SINGLE_OPERATION_DECLARATION = re.compile(r"operation_key=(?P<operations>[a-z0-9-]+)")
MULTI_OPERATION_DECLARATION = re.compile(
    r"`operation_key` 只能是 `(?P<operations>[a-z0-9-|]+)`"
)
CONTRACT_OPERATION_ROW = re.compile(
    r"^\| `(?P<role>[a-z][a-z0-9-]+)` \| (?P<operations>.+) \|$"
)
CONTRACT_OPERATION_VALUE = re.compile(r"`(?P<operation>[a-z][a-z0-9-]+)`")
LEGACY_ROLE_ALIAS = re.compile(r"\bA(?:0[1-9]|1[0-6])\b")


class InputError(ValueError):
    pass


@dataclass(frozen=True)
class RoleSpec:
    key: str
    description: str
    instructions: str
    work_type: str
    skills: frozenset[str]

@dataclass(frozen=True)
class SquadSpec:
    key: str
    description: str
    instructions: str
    work_type: str
    leader: str
    members: tuple[tuple[str, str], ...]



def normalized_thinking_level(value: Any) -> Any:
    return None if value == "" else value


def squad_member_agent_id(value: Mapping[str, Any]) -> Any:
    return value.get("agent_id", value.get("member_id", value.get("id")))

def squad_member_role(value: Mapping[str, Any]) -> Any:
    return value.get("role")


def agent_owner_ref(value: Mapping[str, Any]) -> Any:
    """Return the first populated owner identity exposed by the CLI."""
    for key in ("owner_ref", "owner_id", "created_by", "created_by_id"):
        candidate = value.get(key)
        if candidate not in (None, ""):
            return candidate
    return None


def read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise InputError(f"cannot read {label}: {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise InputError(f"invalid JSON in {label}: {path}: {error.msg}") from error

def account_owner_refs(readback_dir: Path, account_ref: str) -> set[str]:
    """Return account email and matching provider user identities."""
    refs = {account_ref}
    members_path = readback_dir / "workspace-member-list.json"
    if not members_path.is_file():
        return refs
    for member in records(read_json(members_path, "Workspace member list"), "Workspace member list"):
        email = member.get("email", member.get("email_address"))
        if email != account_ref:
            continue
        for key in ("user_id", "account_id", "user_ref", "owner_id"):
            candidate = member.get(key)
            if isinstance(candidate, str) and candidate:
                refs.add(candidate)
    return refs



def readback_snapshot_digest(
    readback_dir: Path,
    *,
    workspace_id: str | None = None,
    runtime_refs: Mapping[str, str] | None = None,
    daemon_refs: Mapping[str, str] | None = None,
) -> str:
    snapshot = read_json(readback_dir / "snapshot.json", "readback snapshot")
    if not isinstance(snapshot, dict) or snapshot.get("schema") != "multica-orchestrator.readback-snapshot.v2":
        raise InputError("readback snapshot schema is invalid")
    expected_identity = {
        "workspace_id": workspace_id,
        "runtime_refs": dict(sorted(runtime_refs.items())) if runtime_refs is not None else None,
        "daemon_refs": dict(sorted(daemon_refs.items())) if daemon_refs is not None else None,
    }
    mismatches = [
        name
        for name, expected in expected_identity.items()
        if expected is not None and snapshot.get(name) != expected
    ]
    if mismatches:
        raise InputError("readback snapshot identity mismatch: " + ", ".join(mismatches))
    artifacts = snapshot.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise InputError("readback snapshot has no artifacts")
    for relative, expected in artifacts.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise InputError("readback snapshot artifact entry is invalid")
        path = (readback_dir / relative).resolve()
        try:
            path.relative_to(readback_dir.resolve())
        except ValueError as error:
            raise InputError("readback snapshot artifact escapes its directory") from error
        if not path.is_file() or digest_bytes(path.read_bytes()) != expected:
            raise InputError(f"readback snapshot artifact digest mismatch: {relative}")
    unsigned = dict(snapshot)
    observed = unsigned.pop("snapshot_digest", None)
    actual = digest_bytes(canonical_json(unsigned))
    if observed != actual:
        raise InputError("readback snapshot digest is invalid")
    return actual




def records(value: Any, label: str) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        items = next((value[key] for key in ("items", "data", "results", "agents", "squads", "skills", "members") if isinstance(value.get(key), list)), None)
        if items is None:
            raise InputError(f"{label} does not contain a list")
    else:
        raise InputError(f"{label} must be a list or list wrapper")
    if not all(isinstance(item, dict) for item in items):
        raise InputError(f"{label} contains a non-object")
    return items


def manifest_role_operations(lines: list[str]) -> dict[str, frozenset[str]]:
    try:
        start = lines.index("    role_operations:")
    except ValueError as error:
        raise InputError("manifest invocation policy has no role_operations") from error
    operations: dict[str, frozenset[str]] = {}
    for line in lines[start + 1:]:
        if not line.startswith("      "):
            break
        match = ROLE_OPERATION.fullmatch(line)
        if not match:
            raise InputError(f"invalid manifest role operation entry: {line!r}")
        role = match["role"]
        values = frozenset(value.strip() for value in match["operations"].split(","))
        if role in operations or not values or "" in values:
            raise InputError(f"invalid manifest role operations for {role}")
        operations[role] = values
    return operations


def contract_role_operations(path: Path) -> dict[str, frozenset[str]]:
    operations: dict[str, frozenset[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = CONTRACT_OPERATION_ROW.fullmatch(line)
        if not match:
            continue
        values = frozenset(
            token["operation"]
            for token in CONTRACT_OPERATION_VALUE.finditer(match["operations"])
        )
        if values:
            operations[match["role"]] = values
    return operations


def declared_role_operations(text: str, role: str) -> frozenset[str]:
    declarations = {
        operation
        for pattern in (SINGLE_OPERATION_DECLARATION, MULTI_OPERATION_DECLARATION)
        for match in pattern.finditer(text)
        for operation in match["operations"].split("|")
    }
    if not declarations:
        raise InputError(f"{role} instructions must declare an operation_key contract")
    return frozenset(declarations)


def validate_prompt_contract(
    manifest_path: Path,
    manifest_lines: list[str],
    roles: list[RoleSpec],
) -> None:
    expected = manifest_role_operations(manifest_lines)
    role_keys = {role.key for role in roles}
    if set(expected) != role_keys:
        raise InputError("manifest role_operations must match exact Agent roles")
    contract_path = manifest_path.parent.parent / "contracts" / "handoff-gate-contracts.md"
    observed_contract = contract_role_operations(contract_path)
    if observed_contract != expected:
        raise InputError("handoff contract role operations differ from manifest")

    active_texts: list[tuple[str, str]] = []
    for role in roles:
        instruction_path = (manifest_path.parent / role.instructions).resolve()
        try:
            text = instruction_path.read_text(encoding="utf-8")
        except OSError as error:
            raise InputError(f"cannot read {role.key} instructions: {error}") from error
        active_texts.append((role.key, text))
        if "ExecutionContextRef.v1" not in text or "LeaderDispatchRef.v1" not in text:
            raise InputError(f"{role.key} instructions do not require native Squad run context")
        if f"`role_key={role.key}`" not in text:
            raise InputError(f"{role.key} instructions do not bind exact role_key")
        if declared_role_operations(text, role.key) != expected[role.key]:
            raise InputError(f"{role.key} instruction operations differ from manifest")

    skill_root = manifest_path.parent.parent
    for relative in (
        "agents/agent-instructions.md",
        "squads/squad-instructions.md",
        "squads/feature-squad.md",
        "squads/fix-squad.md",
    ):
        text = (skill_root / relative).read_text(encoding="utf-8")
        active_texts.append((relative, text))
    for label, text in active_texts:
        if LEGACY_ROLE_ALIAS.search(text):
            raise InputError(f"{label} contains a legacy Axx role alias")


def load_squad_specs(path: Path, roles: Iterable[RoleSpec]) -> dict[str, SquadSpec]:
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index("squads:")
    except ValueError as error:
        raise InputError("manifest has no squads") from error
    parsed: dict[str, SquadSpec] = {}
    current: dict[str, Any] | None = None
    current_member: str | None = None
    in_members = False

    def finish() -> None:
        nonlocal current
        if current is None:
            return
        key = current["key"]
        if key in parsed:
            raise InputError(f"manifest contains duplicate Squad {key}")
        parsed[key] = SquadSpec(
            key=key,
            description=current["description"],
            instructions=current["instructions"],
            work_type=current["work_type"],
            leader=current["leader"],
            members=tuple(current["members"]),
        )

    for line in lines[start + 1:]:
        if ROOT.match(line):
            break
        if match := SQUAD.match(line):
            finish()
            current = {
                "description": "",
                "key": match["value"],
                "instructions": "",
                "work_type": "",
                "leader": "",
                "members": [],
            }
            current_member = None
            in_members = False
            continue
        if current is None:
            continue
        if match := DESCRIPTION.match(line):
            current["description"] = match["value"]
        elif match := INSTRUCTIONS.match(line):
            current["instructions"] = match["value"]
        elif match := WORK_TYPE.match(line):
            current["work_type"] = match["value"]
        elif match := SQUAD_LEADER.match(line):
            current["leader"] = match["value"]
        elif line == "    members:":
            in_members = True
        elif in_members and (match := SQUAD_MEMBER.match(line)):
            current_member = match["value"]
        elif in_members and (match := SQUAD_ROLE.match(line)):
            if current_member is None:
                raise InputError(f"Squad role has no role_key in {current['key']}")
            current["members"].append((current_member, match["value"]))
            current_member = None
        elif line.startswith("    ") and not line.startswith("      "):
            if current_member is not None:
                raise InputError(f"Squad member has no squad_role in {current['key']}")
            in_members = False
    finish()

    role_map = {role.key: role for role in roles}
    expected = {
        work_type: {
            *(role.key for role in role_map.values() if role.work_type == work_type),
            "shared-intake",
            "commit-policy-reviewer",
        }
        for work_type in ("feature", "fix")
    }
    if set(parsed) != set(expected):
        raise InputError("manifest must declare exact feature and fix Squads")
    for key, squad in parsed.items():
        member_keys = [role_key for role_key, _ in squad.members]
        if (
            squad.work_type != key
            or squad.leader != "workflow-leader"
            or not squad.description
            or not squad.instructions
            or len(member_keys) != len(set(member_keys))
            or set(member_keys) != expected[key]
            or any(not description.strip() for _, description in squad.members)
        ):
            raise InputError(f"manifest Squad contract is incomplete or inconsistent: {key}")
    return parsed


def load_manifest(path: Path) -> list[RoleSpec]:
    lines = path.read_text(encoding="utf-8").splitlines()
    roles: list[RoleSpec] = []
    current: dict[str, Any] | None = None
    section: str | None = None
    in_agents = False
    for line in lines:
        if line == "agents:":
            in_agents = True
            continue
        if in_agents and ROOT.match(line):
            break
        match = ROLE.match(line) if in_agents else None
        if match:
            if current is not None:
                roles.append(RoleSpec(current["key"], current["description"], current["instructions"], current["work_type"], frozenset(current["skills"])))
            current = {"key": match["value"], "description": "", "instructions": "", "work_type": "", "skills": set()}
            section = None
            continue
        if current is None:
            continue
        if match := DESCRIPTION.match(line):
            current["description"] = match["value"]
        elif match := INSTRUCTIONS.match(line):
            current["instructions"] = match["value"]
        elif match := WORK_TYPE.match(line):
            current["work_type"] = match["value"]
        elif REQUIRED.match(line):
            section = "skills"
        elif OPTIONAL.match(line):
            section = "optional"
        elif section == "skills" and (match := SKILL.match(line)):
            current["skills"].add(match["value"])
        elif section == "optional" and (match := OPTIONAL_SKILL.match(line)):
            current["skills"].add(match["value"])
        elif FIELD.match(line):
            section = None
    if current is not None:
        roles.append(RoleSpec(current["key"], current["description"], current["instructions"], current["work_type"], frozenset(current["skills"])))
    if len(roles) != 16 or len({role.key for role in roles}) != 16:
        raise InputError("manifest must declare exactly sixteen unique Agent roles")
    if any(not role.description or not role.instructions or role.work_type not in {"shared", "feature", "fix"} for role in roles):
        raise InputError("manifest contains an incomplete Agent role")
    validate_prompt_contract(path, lines, roles)
    load_squad_specs(path, roles)
    return roles


def load_input(path: Path, roles: Iterable[RoleSpec]) -> Mapping[str, Any]:
    value = read_json(path, "server application input")
    if not isinstance(value, dict) or value.get("schema") != INPUT_SCHEMA:
        raise InputError(f"application input schema must equal {INPUT_SCHEMA}")
    forbidden = {"repository", "project", "local_path", "checkout", "work_item"} & set(value)
    if forbidden:
        raise InputError(f"PROJECT_SCOPE_NOT_ALLOWED: {sorted(forbidden)}")
    expected_fields = {
        "schema", "bundle_store", "workspace_handoff_bundle", "consumer_session",
        "collaboration_runtime_alias", "agents",
    }
    if set(value) != expected_fields:
        raise InputError(f"application input fields must equal {sorted(expected_fields)}")
    store_value = value.get("bundle_store")
    bundle_ref = value.get("workspace_handoff_bundle")
    session = value.get("consumer_session")
    if not isinstance(store_value, dict) or set(store_value) != {"state_root"}:
        raise InputError("BUNDLE_STORE_REQUIRED")
    if not isinstance(bundle_ref, dict) or set(bundle_ref) != {"manifest_digest"}:
        raise InputError("WORKSPACE_FOUNDATION_BUNDLE_REQUIRED")
    if not isinstance(session, dict) or set(session) != {"profile", "account_ref"}:
        raise InputError("CONSUMER_SESSION_REQUIRED")
    for field in ("profile", "account_ref"):
        if not isinstance(session.get(field), str) or not session[field]:
            raise InputError(f"consumer_session.{field} is required")
    state_root = store_value.get("state_root")
    expected_digest = bundle_ref.get("manifest_digest")
    if not isinstance(state_root, str) or not Path(state_root).is_absolute() or not isinstance(expected_digest, str):
        raise InputError("WORKSPACE_FOUNDATION_BUNDLE_REQUIRED")
    try:
        bundle = BundleStore(Path(state_root)).resolve("workspace-foundation", expected_digest)
    except BundleError as error:
        raise InputError(f"WORKSPACE_FOUNDATION_BUNDLE_INVALID: {error}") from error
    foundation = bundle.artifacts["workspace-foundation"]
    actual_digest = bundle.manifest["artifacts"]["workspace-foundation"]["digest"]
    if foundation.get("schema") not in FOUNDATION_SCHEMAS:
        raise InputError("WORKSPACE_FOUNDATION_REQUIRED: unsupported handoff schema")
    if foundation.get("state") != "WORKSPACE_FOUNDATION_VERIFIED" or foundation.get("blockers"):
        raise InputError("WORKSPACE_FOUNDATION_REQUIRED: foundation is not verified")
    orchestration_capabilities = foundation.get("orchestration_capabilities")
    native_routing = (
        orchestration_capabilities.get("native_squad_routing")
        if isinstance(orchestration_capabilities, dict)
        else None
    )
    if (
        not isinstance(orchestration_capabilities, dict)
        or orchestration_capabilities.get("state") != "VERIFIED"
        or not isinstance(native_routing, dict)
        or set(native_routing) != NATIVE_SQUAD_CAPABILITIES
        or not all(native_routing.get(key) is True for key in NATIVE_SQUAD_CAPABILITIES)
    ):
        raise InputError("FOUNDATION_NATIVE_SQUAD_CAPABILITY_UNVERIFIED")
    if not isinstance(foundation.get("readback_snapshot_digest"), str) or re.fullmatch(r"sha256:[0-9a-f]{64}", foundation["readback_snapshot_digest"]) is None:
        raise InputError("FOUNDATION_READBACK_SNAPSHOT_UNVERIFIED")
    fleet = foundation.get("runtime_fleet")
    runtimes = fleet.get("runtimes") if isinstance(fleet, dict) else None
    if not isinstance(runtimes, list) or not runtimes:
        raise InputError("FOUNDATION_RUNTIME_FLEET_REQUIRED")
    runtimes_by_alias: dict[str, Mapping[str, Any]] = {}
    for runtime in runtimes:
        if not isinstance(runtime, dict) or runtime.get("status") != "online":
            raise InputError("FOUNDATION_RUNTIME_NOT_ONLINE")
        alias = runtime.get("alias")
        if not isinstance(alias, str) or alias in runtimes_by_alias or not runtime.get("runtime_ref") or not runtime.get("daemon_ref"):
            raise InputError("FOUNDATION_RUNTIME_FLEET_INVALID")
        runtimes_by_alias[alias] = runtime
    for key in ("server_ref", "server_kind", "workspace_ref"):
        if foundation.get(key) in (None, ""):
            raise InputError(f"workspace foundation lacks {key}")
    if foundation["server_kind"] not in {"cloud", "self-hosted"}:
        raise InputError("workspace foundation server_kind must be cloud or self-hosted")
    collaboration_runtime_alias = value.get("collaboration_runtime_alias")
    if not isinstance(collaboration_runtime_alias, str) or collaboration_runtime_alias not in runtimes_by_alias:
        raise InputError("COLLABORATION_RUNTIME_PLACEMENT_REQUIRED: selected Runtime alias is unavailable")
    agents = value["agents"]
    if not isinstance(agents, dict):
        raise InputError("application input agents must be an object")
    expected_roles = {role.key for role in roles}
    if set(agents) != expected_roles:
        raise InputError("application input agents must exactly match manifest role keys")
    resolved_agents: dict[str, dict[str, Any]] = {}
    for role, config in agents.items():
        if not isinstance(config, dict) or set(config) != {"model", "thinking_level", "max_concurrent_tasks", "permission_mode"}:
            raise InputError(f"agent {role} configuration fields are invalid")
        if not isinstance(config.get("model"), str) or not config["model"]:
            raise InputError(f"agent {role} lacks model")
        if config.get("thinking_level") is not None and not isinstance(config["thinking_level"], str):
            raise InputError(f"agent {role} thinking_level must be string or null")
        if config.get("max_concurrent_tasks") != 1:
            raise InputError(f"agent {role} max_concurrent_tasks must equal 1")
        if config.get("permission_mode") != "private":
            raise InputError(f"agent {role} must use private permission_mode")
        resolved_agents[role] = {**config, "runtime_alias": collaboration_runtime_alias}
    return {
        **value,
        "agents": resolved_agents,
        "foundation": foundation,
        "foundation_digest": actual_digest,
        "foundation_bundle_manifest_digest": bundle.manifest_digest,
        "deployment_key": foundation.get("deployment_key") or digest_bytes(canonical_json({
            "schema": "multica-orchestrator.deployment-key.v1",
            "server_kind": foundation["server_kind"],
            "server_ref": foundation["server_ref"],
            "workspace_ref": foundation["workspace_ref"],
        })),
        "workspace_key": foundation.get("workspace_key") or digest_bytes(canonical_json({
            "server_kind": foundation["server_kind"],
            "server_ref": foundation["server_ref"],
            "workspace_ref": foundation["workspace_ref"],
        })),
        "relocation_intent_digest": foundation.get("relocation_intent_digest"),
        "server_ref": foundation["server_ref"],
        "server_kind": foundation["server_kind"],
        "profile": session["profile"],
        "account_ref": session["account_ref"],
        "workspace_id": foundation["workspace_ref"],
        "collaboration_runtime_alias": collaboration_runtime_alias,
        "runtimes_by_alias": runtimes_by_alias,
        "runtime_refs": {alias: runtime["runtime_ref"] for alias, runtime in sorted(runtimes_by_alias.items())},
        "daemon_refs": {alias: runtime["daemon_ref"] for alias, runtime in sorted(runtimes_by_alias.items())},
    }


def instruction_path(manifest: Path, role: RoleSpec) -> Path:
    resolved = (manifest.parent / role.instructions).resolve()
    if not resolved.is_file():
        raise InputError(f"missing instructions for {role.key}: {resolved}")
    return resolved


def multica_environment(server_kind: str) -> dict[str, str]:
    environment = dict(os.environ)
    if server_kind == "self-hosted":
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            environment.pop(key, None)
    return environment


def run_multica(configuration: Mapping[str, Any], executable: str, arguments: list[str]) -> Any:
    command = [executable, "--profile", configuration["profile"], "--workspace-id", configuration["workspace_id"], *arguments, "--output", "json"]
    completed = subprocess.run(command, text=True, capture_output=True, env=multica_environment(configuration["server_kind"]), check=False)
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise InputError(f"multica command failed: {detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise InputError("multica command did not return JSON") from error
