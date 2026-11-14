#!/usr/bin/env python3
"""Capture a verified Workspace and explicitly selected Runtime fleet."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from foundation_common import (
    InputError,
    LABEL_COLORS,
    STATUS_CODES,
    multica_environment,
    read_json,
    records,
    require_mapping,
    require_string,
)
from multica_state_bundle.identities import canonical_json, digest_bytes, utc_now
from multica_state_bundle.storage import atomic_bytes
from multica_orchestrator_cli.common.runtime_capability import (
    RuntimeCapabilityEvidenceError,
    runtime_capability_revision,
    runtime_fleet_stability_projection,
)

EXPECTED_STATUSES = {
    "needs_triage": ("Pending Triage", "backlog"),
    "needs_information": ("Needs Information", "blocked"),
    "ready_for_agent": ("Ready for Agent", "backlog"),
    "ready_for_human": ("Ready for Human", "todo"),
    "wontfix": ("Won't Fix", "cancelled"),
}


def run(
    executable: str,
    profile: str,
    server_kind: str,
    arguments: list[str],
    *,
    workspace_ref: str | None = None,
    json_output: bool = True,
) -> Any:
    command = [executable, "--profile", profile]
    if workspace_ref:
        command.extend(["--workspace-id", workspace_ref])
    command.extend(arguments)
    if json_output:
        command.extend(["--output", "json"])
    completed = subprocess.run(
        command,
        env=multica_environment(server_kind),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise InputError((completed.stderr or completed.stdout).strip() or f"command failed: {command}")
    if not json_output:
        output = completed.stdout + completed.stderr
        output = re.sub(r"(?im)^Token:.*$", "Token: [redacted]", output)
        return {"stdout": output}
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise InputError(f"multica command did not return JSON: {' '.join(command)}") from error


def unique(payload: Any, field: str, value: str, label: str) -> dict[str, Any]:
    matches = [dict(item) for item in records(payload, label) if item.get(field) == value]
    if len(matches) != 1:
        raise InputError(f"{label} must contain exactly one {field}={value!r}")
    return matches[0]


def parse_runtime_selections(values: list[str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    aliases: set[str] = set()
    refs: set[str] = set()
    for value in values:
        alias, separator, runtime_ref = value.partition("=")
        if not separator or not alias or not runtime_ref:
            raise InputError("--runtime must use <alias>=<runtime-ref>")
        if alias in aliases or runtime_ref in refs:
            raise InputError("Runtime aliases and refs must be unique")
        aliases.add(alias)
        refs.add(runtime_ref)
        result.append((alias, runtime_ref))
    return sorted(result)


def write_json(path: Path, value: Any) -> None:
    atomic_bytes(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-kind", choices=("cloud", "self-hosted"), required=True)
    parser.add_argument("--server-ref", required=True)
    parser.add_argument("--deployment-key")
    parser.add_argument("--relocation-intent-digest")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--account-ref", required=True)
    parser.add_argument("--workspace-ref", required=True)
    parser.add_argument("--runtime", action="append", required=True, metavar="ALIAS=RUNTIME_REF")
    parser.add_argument("--status-attestation", type=Path)
    parser.add_argument("--capability-readback", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--operator-state-root", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--multica-command", default="multica")
    args = parser.parse_args()
    try:
        selections = parse_runtime_selections(args.runtime)
        state = args.state_dir.resolve()
        input_path = args.input.resolve()
        if not input_path.is_relative_to(state):
            raise InputError("--input must be inside --state-dir so the snapshot binds it")
        readback = state / "readback"
        readback.mkdir(parents=True, exist_ok=False, mode=0o700)
        captures = {
            "auth-status.json": run(args.multica_command, args.profile, args.server_kind, ["auth", "status"], json_output=False),
            "config-show.json": run(args.multica_command, args.profile, args.server_kind, ["config", "show"], json_output=False),
            "workspace-list.json": run(args.multica_command, args.profile, args.server_kind, ["workspace", "list"]),
            "workspace.json": run(args.multica_command, args.profile, args.server_kind, ["workspace", "get", args.workspace_ref], workspace_ref=args.workspace_ref),
            "members.json": run(args.multica_command, args.profile, args.server_kind, ["workspace", "member", "list"], workspace_ref=args.workspace_ref),
            "labels.json": run(args.multica_command, args.profile, args.server_kind, ["label", "list"], workspace_ref=args.workspace_ref),
            "runtimes.json": run(args.multica_command, args.profile, args.server_kind, ["runtime", "list"], workspace_ref=args.workspace_ref),
        }
        for name, payload in captures.items():
            write_json(readback / name, payload)
        workspace = captures["workspace.json"]
        if not isinstance(workspace, dict) or workspace.get("id", workspace.get("workspace_id")) != args.workspace_ref:
            raise InputError("workspace get does not match --workspace-ref")
        unique(captures["workspace-list.json"], "id", args.workspace_ref, "workspace list")
        labels = records(captures["labels.json"], "label list")
        label_input: dict[str, Any] = {}
        for name, color in LABEL_COLORS.items():
            matches = [item for item in labels if item.get("name") == name]
            if len(matches) > 1:
                raise InputError(f"label list contains duplicate canonical label: {name}")
            item = matches[0] if matches else None
            label_input[name] = {
                "exists": item is not None,
                "label_ref": item.get("id", item.get("label_id")) if item else None,
                "color": str(item.get("color", color) if item else color).lower(),
            }
        runtime_input: list[dict[str, Any]] = []
        for alias, runtime_ref in selections:
            runtime = unique(captures["runtimes.json"], "id", runtime_ref, "runtime list")
            daemon_ref = runtime.get("daemon_id", runtime.get("daemon_ref"))
            if not isinstance(daemon_ref, str) or not daemon_ref:
                raise InputError(f"selected Runtime {alias} lacks daemon_ref")
            runtime_input.append({
                "alias": alias,
                "name": runtime.get("name", runtime.get("display_name", runtime_ref)),
                "exists": True,
                "runtime_ref": runtime_ref,
                "daemon_ref": daemon_ref,
                "status": runtime.get("status"),
                "provider": runtime.get("provider"),
                "capability_revision": runtime_capability_revision(runtime),
                "daemon_start_required": False,
            })
        if args.status_attestation is None:
            status_input = {
                key: {
                    "state": "PENDING_CONFIRMATION",
                    "evidence_ref": "human-confirmation:required",
                }
                for key in STATUS_CODES
            }
        else:
            attestation = require_mapping(
                read_json(args.status_attestation, "status attestation"),
                "status attestation",
            )
            member_refs = {
                item.get("id", item.get("member_id", item.get("user_id")))
                for item in records(captures["members.json"], "workspace member list")
            }
            statuses = attestation.get("statuses")
            valid_attestation = (
                attestation.get("schema")
                == "multica-orchestrator-link-up.status-contract-attestation.v1"
                and attestation.get("workspace_ref") == args.workspace_ref
                and isinstance(attestation.get("actor_member_ref"), str)
                and attestation.get("actor_member_ref") in member_refs
                and isinstance(attestation.get("observed_at"), str)
                and isinstance(statuses, dict)
                and set(statuses) == set(STATUS_CODES)
                and all(
                    isinstance(statuses.get(key), dict)
                    and statuses[key].get("display_name") == display_name
                    and statuses[key].get("category") == category
                    for key, (display_name, category) in EXPECTED_STATUSES.items()
                )
            )
            if valid_attestation:
                attestation_copy = state / "status-attestation.json"
                atomic_bytes(attestation_copy, args.status_attestation.read_bytes())
                attestation_digest = digest_bytes(attestation_copy.read_bytes())
                status_input = {
                    key: {
                        "state": "VERIFIED",
                        "evidence_ref": f"status-attestation:{attestation_digest}",
                    }
                    for key in STATUS_CODES
                }
            else:
                status_input = {
                    key: {
                        "state": "CONFLICT",
                        "evidence_ref": "human-confirmation:conflicting-attestation",
                    }
                    for key in STATUS_CODES
                }
        capabilities = require_mapping(
            read_json(args.capability_readback, "CLI capability readback"),
            "CLI capability readback",
        )
        if capabilities.get("schema") != "multica-orchestrator-link-up.cli-capabilities.v2":
            raise InputError("CLI capability readback schema is invalid")
        native_routing = require_mapping(
            capabilities.get("native_squad_routing"),
            "CLI capability native_squad_routing",
        )
        if capabilities.get("compatible") is not True or not native_routing or not all(
            value is True for value in native_routing.values()
        ):
            raise InputError("NATIVE_SQUAD_CAPABILITY_UNAVAILABLE")
        capability_copy = state / "cli-capabilities.json"
        atomic_bytes(capability_copy, args.capability_readback.read_bytes())
        capability_digest = digest_bytes(capability_copy.read_bytes())
        server_input = {
            "kind": args.server_kind,
            "ref": args.server_ref,
            "profile": args.profile,
            "account_ref": args.account_ref,
        }
        if args.deployment_key:
            server_input["deployment_key"] = args.deployment_key
        if args.relocation_intent_digest:
            server_input["relocation_intent_digest"] = args.relocation_intent_digest
        configuration = {
            "schema": "multica-orchestrator-link-up.workspace-foundation-input.v3",
            "operator_state_root": str(args.operator_state_root.expanduser().resolve()),
            "server": server_input,
            "workspace": {"name": workspace.get("name", workspace.get("title")), "exists": True, "workspace_ref": args.workspace_ref},
            "labels": label_input,
            "statuses": status_input,
            "runtime_fleet": {"runtimes": runtime_input},
            "orchestration_capabilities": {
                "state": "VERIFIED",
                "evidence_ref": f"cli-capabilities:{capability_digest}",
                "native_squad_routing": dict(sorted(native_routing.items())),
            },
        }
        write_json(input_path, configuration)
        workspace_after = run(args.multica_command, args.profile, args.server_kind, ["workspace", "get", args.workspace_ref], workspace_ref=args.workspace_ref)
        runtimes_after = run(args.multica_command, args.profile, args.server_kind, ["runtime", "list"], workspace_ref=args.workspace_ref)
        if (
            canonical_json(workspace_after) != canonical_json(captures["workspace.json"])
            or runtime_fleet_stability_projection(records(runtimes_after, "runtime list"))
            != runtime_fleet_stability_projection(records(captures["runtimes.json"], "runtime list"))
        ):
            raise InputError("STALE_READBACK_SNAPSHOT: workspace or Runtime fleet changed during capture")
        write_json(readback / "workspace-after.json", workspace_after)
        write_json(readback / "runtimes-after.json", runtimes_after)
        artifacts = {
            str(path.relative_to(state)): digest_bytes(path.read_bytes())
            for path in sorted(state.rglob("*.json"))
            if path.name != "snapshot.json"
        }
        snapshot = {
            "schema": "multica-orchestrator-link-up.readback-snapshot.v2",
            "server_ref": args.server_ref,
            "profile_ref": args.profile,
            "account_ref": args.account_ref,
            "workspace_ref": args.workspace_ref,
            "runtime_refs": sorted(runtime_ref for _, runtime_ref in selections),
            "observed_at": utc_now(),
            "artifacts": artifacts,
        }
        snapshot["snapshot_digest"] = digest_bytes(canonical_json(snapshot))
        write_json(state / "snapshot.json", snapshot)
        print(json.dumps({"ok": True, "input": str(args.input), "snapshot": str(state / "snapshot.json"), "snapshot_digest": snapshot["snapshot_digest"]}, sort_keys=True))
        return 0
    except (InputError, RuntimeCapabilityEvidenceError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "error": "WORKSPACE_FOUNDATION_CAPTURE_FAILED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
