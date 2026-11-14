#!/usr/bin/env python3
"""Capture target Multica and local control-authority evidence for relocation."""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

PACKAGE_CLI = Path(__file__).resolve().parents[3]
if not (PACKAGE_CLI / "multica_state_bundle" / "__init__.py").is_file():
    print("STATE_BUNDLE_UNAVAILABLE: install multica-orchestrator-cli", file=sys.stderr)
    raise SystemExit(2)
sys.path.insert(0, str(PACKAGE_CLI))
from multica_state_bundle.bootstrap import activate_installed_package

activate_installed_package(Path(__file__))
from relocation_common import (
    RelocationError,
    digest_object,
    ensure_private_directory,
    read_json,
    require_digest,
    verify_embedded_digest,
)
from multica_state_bundle.identities import canonical_json, digest_bytes, require_absolute, utc_now
from multica_state_bundle.relocations import mutation_barrier, relocation_lock
from multica_state_bundle.storage import atomic_json

INPUT_SCHEMA = "multica-orchestrator-relocate.input.v2"
READBACK_SCHEMA = "multica-orchestrator-relocate.target-readback.v2"
MIGRATION_RECEIPT_SCHEMA = "multica-migrate-server.server-migration-receipt.v1"
ACTIVE_EXECUTION_STATES = {"ACTIVE", "RUNNING", "IN_PROGRESS"}
ACTIVE_LEASE_STATES = {"ACTIVE"}
ACTIVE_INTEGRATION_STATES = {"ACTIVE", "OPEN", "IN_PROGRESS"}
PROXY_VARIABLES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


def records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("data", "items", "workspaces", "projects", "runtimes", "skills", "agents", "squads"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return [dict(item) for item in candidate if isinstance(item, Mapping)]
            if isinstance(candidate, Mapping):
                for nested in ("items", "data", "results"):
                    nested_value = candidate.get(nested)
                    if isinstance(nested_value, list):
                        return [dict(item) for item in nested_value if isinstance(item, Mapping)]
    raise RelocationError("Multica list output does not contain a record array")


def projected(rows: Iterable[Mapping[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    result = [{field: row.get(field) for field in fields if field in row} for row in rows]
    return sorted(result, key=lambda item: canonical_json(item))


def load_input(path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    value = read_json(path.resolve(), "relocation input")
    if value.get("schema") != INPUT_SCHEMA:
        raise RelocationError("relocation input schema is invalid")
    verify_embedded_digest(value, "input_digest", "relocation input")
    inventory = value.get("target_inventory")
    migration = value.get("migration_receipt")
    if not isinstance(inventory, dict) or not isinstance(migration, dict):
        raise RelocationError("relocation input descriptors are invalid")
    inventory_path = require_absolute(inventory.get("path"), "Runtime target inventory path")
    migration_path = require_absolute(migration.get("path"), "migration receipt path")
    if inventory_path.stat().st_mode & 0o077:
        raise RelocationError("Runtime target inventory permissions must be private")
    if digest_bytes(inventory_path.read_bytes()) != require_digest(inventory.get("digest"), "Runtime target inventory digest"):
        raise RelocationError("Runtime target inventory bytes changed")
    targets = read_json(inventory_path, "Runtime target inventory")
    if targets.get("schema") != "multica-orchestrator.runtime-target-inventory.v1":
        raise RelocationError("Runtime target inventory schema is invalid")
    receipt = read_json(migration_path, "server migration receipt")
    if receipt.get("schema") != MIGRATION_RECEIPT_SCHEMA:
        raise RelocationError("server migration receipt schema is invalid")
    verify_embedded_digest(receipt, "receipt_digest", "server migration receipt")
    if receipt["receipt_digest"] != require_digest(migration.get("digest"), "migration receipt digest"):
        raise RelocationError("migration receipt differs from relocation input")
    return value, targets, receipt


def multica_json(command: str, profile: str, workspace_ref: str | None, arguments: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    environment = os.environ.copy()
    for name in PROXY_VARIABLES:
        environment.pop(name, None)
    invocation = [command, "--profile", profile]
    if workspace_ref is not None:
        invocation.extend(["--workspace-id", workspace_ref])
    invocation.extend([*arguments, "--output", "json"])
    try:
        completed = subprocess.run(invocation, env=environment, text=True, capture_output=True, check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RelocationError(f"Multica readback command could not execute: {arguments[0]}: {error}") from error
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise RelocationError(f"Multica readback failed for {arguments[0]} with exit {completed.returncode}: {detail[:300]}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RelocationError(f"Multica readback for {arguments[0]} returned invalid JSON") from error
    return records(payload), {"resource": arguments[0], "return_code": completed.returncode}


def selected_workspace(rows: list[dict[str, Any]], workspace_ref: str) -> dict[str, Any]:
    matches = [row for row in rows if workspace_ref in {row.get("id"), row.get("workspace_id")}]
    if len(matches) != 1:
        raise RelocationError("authoritative Workspace readback is missing or ambiguous")
    return matches[0]


def target_runtime_aliases(inventory: dict[str, Any], runtimes: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    targets = inventory.get("targets")
    if not isinstance(targets, dict):
        raise RelocationError("Runtime target inventory targets are invalid")
    ready: list[str] = []
    missing: list[str] = []
    for alias, target in sorted(targets.items()):
        if not isinstance(alias, str) or not alias or not isinstance(target, dict):
            raise RelocationError("Runtime target inventory entry is invalid")
        matches = [
            row
            for row in runtimes
            if alias in {
                row.get("id"),
                row.get("runtime_id"),
                row.get("name"),
                row.get("alias"),
            }
        ]
        healthy = []
        for row in matches:
            status_value = row.get("status", row.get("state"))
            online = row.get("online") is True or row.get("connected") is True
            healthy.append(online or (isinstance(status_value, str) and status_value.upper() in {"ONLINE", "READY", "RUNNING", "CONNECTED"}))
        if len(matches) == 1 and healthy == [True]:
            ready.append(alias)
        else:
            missing.append(alias)
    return ready, missing


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}


def control_snapshot(path: Path, observed: datetime) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if path.is_symlink() or not path.is_file():
        raise RelocationError("control authority database must be a regular file")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"executions", "lease_heads", "integration_heads"}
        if not required.issubset(tables):
            raise RelocationError(f"control authority database lacks required tables: {sorted(required - tables)}")
        selected: dict[str, list[dict[str, Any]]] = {}
        counts: dict[str, int] = {}
        for table, active_states, count_name in (
            ("executions", ACTIVE_EXECUTION_STATES, "active_executions"),
            ("lease_heads", ACTIVE_LEASE_STATES, "active_leases"),
            ("integration_heads", ACTIVE_INTEGRATION_STATES, "integration_operations"),
        ):
            columns = table_columns(connection, table)
            if "state" not in columns:
                raise RelocationError(f"control authority table {table} lacks state")
            identity_fields = [field for field in ("execution_ref", "lease_ref", "integration_ref", "project_ref", "work_item_ref", "target_ref", "repository_ref") if field in columns]
            query_fields = [*identity_fields, "state"]
            if table == "lease_heads" and "expires_at" in columns:
                query_fields.append("expires_at")
            rows = [dict(row) for row in connection.execute(f'SELECT {", ".join(query_fields)} FROM "{table}"')]
            active_rows: list[dict[str, Any]] = []
            for row in rows:
                if str(row.get("state", "")).upper() not in active_states:
                    continue
                if table == "lease_heads" and row.get("expires_at"):
                    try:
                        expires = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
                    except ValueError as error:
                        raise RelocationError("control authority lease expiry is invalid") from error
                    if expires.tzinfo is None:
                        raise RelocationError("control authority lease expiry lacks timezone")
                    if expires <= observed:
                        continue
                active_rows.append(row)
            selected[table] = sorted(active_rows, key=lambda item: canonical_json(item))
            counts[count_name] = len(active_rows)
        return {"database_path": str(path), "tables": selected, "counts": counts}
    finally:
        connection.close()


def command_capture(args: argparse.Namespace) -> dict[str, Any]:
    output = ensure_private_directory(args.output_dir, new=True)
    configuration, inventory, receipt = load_input(args.input)
    profile = configuration.get("target_profile")
    if not isinstance(profile, str) or not profile:
        raise RelocationError("relocation input lacks target profile")
    workspace_ref = str(configuration["workspace_ref"])
    service_rows: dict[str, list[dict[str, Any]]] = {}
    command_receipts: list[dict[str, Any]] = []
    for resource in ("workspace", "project", "runtime", "skill", "agent", "squad"):
        rows, command_receipt = multica_json(args.multica_command, profile, None if resource == "workspace" else workspace_ref, [resource, "list"])
        service_rows[resource] = rows
        command_receipts.append(command_receipt)
    workspace = selected_workspace(service_rows["workspace"], workspace_ref)
    projections = {
        "workspace": projected([workspace], ("id", "name", "slug")),
        "projects": projected(service_rows["project"], ("id", "title", "workspace_id")),
        "runtimes": projected(service_rows["runtime"], ("daemon_id", "id", "name", "provider", "workspace_id")),
        "skills": projected(service_rows["skill"], ("id", "name", "workspace_id")),
        "agents": projected(service_rows["agent"], ("id", "name", "runtime_id", "workspace_id")),
        "squads": projected(service_rows["squad"], ("id", "leader_id", "name", "workspace_id")),
    }
    identities = {
        "workspace_digest": digest_bytes(canonical_json(projections["workspace"])),
        "project_set_digest": digest_bytes(canonical_json(projections["projects"])),
        "runtime_fleet_membership_digest": digest_bytes(canonical_json(projections["runtimes"])),
        "orchestrator_resource_digest": digest_bytes(canonical_json({key: projections[key] for key in ("skills", "agents", "squads")})),
    }
    if identities != receipt.get("identity_sets"):
        raise RelocationError("target service identity sets differ from the server migration receipt")
    ready_aliases, missing_aliases = target_runtime_aliases(inventory, service_rows["runtime"])
    observed = datetime.now(timezone.utc)
    control = control_snapshot(args.control_db, observed)
    counts = control["counts"]
    dispatch_quiesced = not any(counts.values())
    service_path = output / "service-readback.json"
    control_path = output / "control-readback.json"
    atomic_json(service_path, {"schema": "multica-orchestrator-relocate.service-readback.v1", "commands": command_receipts, "records": service_rows, "projections": projections, "observed_at": observed.isoformat().replace("+00:00", "Z")}, replace=False)
    atomic_json(control_path, {"schema": "multica-orchestrator-relocate.control-readback.v1", **control, "observed_at": observed.isoformat().replace("+00:00", "Z")}, replace=False)
    state_root = require_absolute(configuration["state_root"], "relocation input state_root")
    with relocation_lock(state_root, configuration["deployment_key"]):
        barrier = mutation_barrier(state_root, configuration["deployment_key"])
    readback = {
        "schema": READBACK_SCHEMA,
        "server": configuration["target_server"],
        "workspace_ref": workspace_ref,
        "identity_sets": identities,
        "runtime_aliases": ready_aliases,
        "runtime_state": "RUNTIMES_READY" if not missing_aliases else "RUNTIMES_NOT_READY",
        "dispatch_quiesced": dispatch_quiesced,
        "active_executions": counts["active_executions"],
        "active_leases": counts["active_leases"],
        "integration_operations": counts["integration_operations"],
        "evidence": {
            "service_snapshot": {"path": str(service_path), "digest": digest_bytes(service_path.read_bytes())},
            "control_snapshot": {"path": str(control_path), "digest": digest_bytes(control_path.read_bytes())},
        },
        "mutation_barrier": barrier,
        "observed_at": utc_now(),
    }
    readback["readback_digest"] = digest_object(readback, "readback_digest")
    readback_path = output / "target-readback.json"
    atomic_json(readback_path, readback, replace=False)
    return {"ok": not missing_aliases and dispatch_quiesced, "state": "TARGET_READBACK_CAPTURED", "readback": str(readback_path), "readback_digest": readback["readback_digest"], "missing_runtime_aliases": missing_aliases, **counts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--control-db", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--multica-command", default="multica")
    args = parser.parse_args()
    try:
        result = command_capture(args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["ok"] else 2
    except (OSError, RelocationError, sqlite3.Error, ValueError) as error:
        print(json.dumps({"ok": False, "error": "TARGET_READBACK_FAILED", "detail": str(error)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
