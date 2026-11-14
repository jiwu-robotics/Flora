#!/usr/bin/env python3
"""Validate private server-migration evidence and emit a digest-bound receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "multica-migrate-server.server-migration-receipt.v1"
PLAN_SCHEMA = "multica-migrate-server.server-migration-plan.v1"
READBACK_SCHEMA = "multica-migrate-server.server-migration-target-readback.v1"
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
IDENTITY_FIELDS = {
    "workspace_digest",
    "project_set_digest",
    "orchestrator_resource_digest",
    "runtime_fleet_membership_digest",
}


class ReceiptError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ReceiptError("evidence must be a regular non-symlink file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ReceiptError(f"evidence is invalid JSON: {error.msg}") from error
    if not isinstance(value, dict):
        raise ReceiptError("evidence must be a JSON object")
    return value


def read_evidence_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ReceiptError(f"{label} must be a regular non-symlink file")
    return path.read_bytes()


def require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or DIGEST.fullmatch(value) is None:
        raise ReceiptError(f"{label} must be a SHA-256 digest")
    return value


def require_server(value: Any, label: str) -> Mapping[str, str]:
    if not isinstance(value, dict) or set(value) != {"server_kind", "server_ref"}:
        raise ReceiptError(f"{label} must contain only server_kind and server_ref")
    if value.get("server_kind") != "self-hosted" or not isinstance(value.get("server_ref"), str) or not value["server_ref"]:
        raise ReceiptError(f"{label} must identify one self-hosted server")
    return value


def require_release(value: Any, label: str) -> Mapping[str, str]:
    if not isinstance(value, dict) or set(value) != {"commit", "image_set_digest"}:
        raise ReceiptError(f"{label} fields are invalid")
    if not isinstance(value["commit"], str) or COMMIT.fullmatch(value["commit"]) is None:
        raise ReceiptError(f"{label}.commit must be a full Git commit")
    require_digest(value["image_set_digest"], f"{label}.image_set_digest")
    return value


def require_identity_sets(value: Any, label: str) -> Mapping[str, str]:
    if not isinstance(value, dict) or set(value) != IDENTITY_FIELDS:
        raise ReceiptError(f"{label} fields are invalid")
    for name in sorted(IDENTITY_FIELDS):
        require_digest(value[name], f"{label}.{name}")
    return value


def validate_plan(value: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "schema", "source", "target", "origin_strategy", "workspace_ref",
        "application_release", "identity_sets",
    }
    if set(value) != expected or value.get("schema") != PLAN_SCHEMA:
        raise ReceiptError("migration plan fields or schema are invalid")
    source = require_server(value["source"], "migration plan source")
    target = require_server(value["target"], "migration plan target")
    if value["origin_strategy"] not in {"preserve", "change"}:
        raise ReceiptError("migration plan origin_strategy is invalid")
    if value["origin_strategy"] == "preserve" and source["server_ref"] != target["server_ref"]:
        raise ReceiptError("migration plan preserve origin requires identical server_ref")
    if value["origin_strategy"] == "change" and source["server_ref"] == target["server_ref"]:
        raise ReceiptError("migration plan change origin requires distinct server_ref")
    if not isinstance(value["workspace_ref"], str) or not value["workspace_ref"]:
        raise ReceiptError("migration plan workspace_ref is required")
    require_release(value["application_release"], "migration plan application_release")
    require_identity_sets(value["identity_sets"], "migration plan identity_sets")
    return value


def validate_readback(value: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "schema", "migration_plan_digest", "target", "workspace_ref",
        "application_release", "identity_sets", "target_authoritative",
        "source_service_state", "runtime_state", "final_state", "observed_at",
    }
    if set(value) != expected or value.get("schema") != READBACK_SCHEMA:
        raise ReceiptError("target readback fields or schema are invalid")
    require_digest(value["migration_plan_digest"], "target readback migration_plan_digest")
    require_server(value["target"], "target readback target")
    if not isinstance(value["workspace_ref"], str) or not value["workspace_ref"]:
        raise ReceiptError("target readback workspace_ref is required")
    require_release(value["application_release"], "target readback application_release")
    require_identity_sets(value["identity_sets"], "target readback identity_sets")
    if value["target_authoritative"] is not True or value["source_service_state"] != "stopped":
        raise ReceiptError("target readback does not prove authority and source quiescence")
    if value["runtime_state"] != "RUNTIMES_READY" or value["final_state"] not in {"RUNTIMES_READY", "OBSERVING"}:
        raise ReceiptError("target readback does not prove Runtime readiness")
    if not isinstance(value["observed_at"], str) or not value["observed_at"]:
        raise ReceiptError("target readback observed_at is required")
    return value


def validate(value: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "schema", "migration_plan_digest", "source", "target", "origin_strategy",
        "workspace_ref", "application_release", "identity_sets",
        "target_readback_digest", "target_authoritative", "source_service_state",
        "runtime_state", "final_state", "observed_at",
    }
    if set(value) != expected or value.get("schema") != SCHEMA:
        raise ReceiptError("evidence fields or schema are invalid")
    require_digest(value["migration_plan_digest"], "migration_plan_digest")
    source = require_server(value["source"], "source")
    target = require_server(value["target"], "target")
    if value["origin_strategy"] not in {"preserve", "change"}:
        raise ReceiptError("origin_strategy must be preserve or change")
    if value["origin_strategy"] == "preserve" and source["server_ref"] != target["server_ref"]:
        raise ReceiptError("preserve origin requires identical source and target server_ref")
    if value["origin_strategy"] == "change" and source["server_ref"] == target["server_ref"]:
        raise ReceiptError("change origin requires distinct source and target server_ref")
    if not isinstance(value["workspace_ref"], str) or not value["workspace_ref"]:
        raise ReceiptError("workspace_ref is required")
    require_release(value["application_release"], "application_release")
    require_identity_sets(value["identity_sets"], "identity_sets")
    require_digest(value["target_readback_digest"], "target_readback_digest")
    if value["target_authoritative"] is not True:
        raise ReceiptError("target must be authoritative")
    if value["source_service_state"] != "stopped":
        raise ReceiptError("source service must be stopped")
    if value["runtime_state"] != "RUNTIMES_READY":
        raise ReceiptError("Runtime fleet must be ready")
    if value["final_state"] not in {"RUNTIMES_READY", "OBSERVING"}:
        raise ReceiptError("final_state must be RUNTIMES_READY or OBSERVING")
    if not isinstance(value["observed_at"], str) or not value["observed_at"]:
        raise ReceiptError("observed_at is required")
    return value


def write_new(path: Path, payload: bytes) -> None:
    if not path.is_absolute():
        raise ReceiptError("output path must be absolute")
    parent = path.parent
    if (
        not parent.is_dir()
        or parent.is_symlink()
        or parent.stat().st_uid != os.geteuid()
        or parent.stat().st_mode & 0o077
    ):
        raise ReceiptError("output parent must be an existing current-user mode-0700 non-symlink directory")
    if path.exists() or path.is_symlink():
        raise ReceiptError("output must be a new path")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise ReceiptError("output must be a new path") from error
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--target-readback", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = validate(read_object(args.evidence.resolve()))
        plan_path = args.plan.resolve()
        readback_path = args.target_readback.resolve()
        plan_bytes = read_evidence_bytes(plan_path, "migration plan")
        readback_bytes = read_evidence_bytes(readback_path, "target readback")
        plan = validate_plan(read_object(plan_path))
        readback = validate_readback(read_object(readback_path))
        if digest(plan_bytes) != payload["migration_plan_digest"]:
            raise ReceiptError("migration plan bytes differ from evidence")
        if digest(readback_bytes) != payload["target_readback_digest"]:
            raise ReceiptError("target readback bytes differ from evidence")
        for field in ("source", "target", "origin_strategy", "workspace_ref", "application_release", "identity_sets"):
            if payload[field] != plan[field]:
                raise ReceiptError(f"migration plan {field} differs from evidence")
        if readback["migration_plan_digest"] != payload["migration_plan_digest"]:
            raise ReceiptError("target readback is not bound to the migration plan")
        for field in (
            "target", "workspace_ref", "application_release", "identity_sets",
            "target_authoritative", "source_service_state", "runtime_state",
            "final_state", "observed_at",
        ):
            if payload[field] != readback[field]:
                raise ReceiptError(f"target readback {field} differs from evidence")
        payload["receipt_digest"] = digest(canonical(payload))
        write_new(args.output.expanduser(), json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        print(json.dumps({"ok": True, "output": str(args.output.resolve()), "receipt_digest": payload["receipt_digest"]}, sort_keys=True))
        return 0
    except (OSError, ReceiptError) as error:
        print(json.dumps({"ok": False, "error": "SERVER_MIGRATION_RECEIPT_FAILED", "detail": str(error)}, sort_keys=True), file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
