#!/usr/bin/env python3
"""Plan and attest deterministic Multica login state transitions."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INPUT_SCHEMA = "multica-login.input.v1"
PLAN_SCHEMA = "multica-login.plan.v1"
SESSION_SCHEMA = "multica-login.session-receipt.v1"
DIGEST_PREFIX = "sha256:"
SESSION_STATES = (
    "endpoint_verified",
    "browser_authenticated",
    "cli_authenticated",
    "workspace_selected",
    "runtime_ready",
)


class LoginError(RuntimeError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return DIGEST_PREFIX + hashlib.sha256(value).hexdigest()


def digest_object(value: dict[str, Any], field: str) -> str:
    return digest_bytes(canonical_json({key: item for key, item in value.items() if key != field}))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def require_private_parent(path: Path) -> None:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if parent.is_symlink() or not parent.is_dir():
        raise LoginError(f"output parent must be a non-symlink directory: {parent}")
    mode = parent.stat().st_mode & 0o777
    if mode & 0o077:
        raise LoginError(f"output parent must not be group/world accessible: {parent}")


def atomic_json(path: Path, value: dict[str, Any], *, replace: bool = False) -> None:
    path = path.expanduser().resolve()
    require_private_parent(path)
    if path.exists() and not replace:
        raise LoginError(f"refusing to overwrite output: {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def read_object(path: Path, label: str) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if path.is_symlink() or not path.is_file():
        raise LoginError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LoginError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise LoginError(f"{label} must be a JSON object")
    return value


def require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith(DIGEST_PREFIX):
        raise LoginError(f"{label} must be a SHA-256 digest")
    try:
        int(value.removeprefix(DIGEST_PREFIX), 16)
    except ValueError as error:
        raise LoginError(f"{label} must be a SHA-256 digest") from error
    return value


def load_typed(path: Path, schema: str, digest_field: str, label: str) -> dict[str, Any]:
    value = read_object(path, label)
    if value.get("schema") != schema:
        raise LoginError(f"{label} schema is invalid")
    declared = require_digest(value.get(digest_field), f"{label}.{digest_field}")
    if digest_object(value, digest_field) != declared:
        raise LoginError(f"{label} embedded digest mismatch")
    return value


def selector(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or len(value) != 1:
        raise LoginError("workspace_selector must contain exactly one selector")
    key, selected = next(iter(value.items()))
    if key not in {"id", "name", "slug"} or not isinstance(selected, str) or not selected.strip():
        raise LoginError("workspace_selector must contain one non-empty id, name, or slug")
    return {key: selected.strip()}


def validate_input(value: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "schema", "target_type", "deployment_scope", "server_url", "web_url",
        "client_kind", "client_location", "profile", "account_ref",
        "workspace_selector", "execution_requested", "routes", "ssh_owner_path",
    }
    if set(value) != expected or value.get("schema") != INPUT_SCHEMA:
        raise LoginError("login input fields or schema are invalid")
    if value.get("target_type") not in {"cloud", "self-hosted"}:
        raise LoginError("target_type must be cloud or self-hosted")
    if value.get("deployment_scope") not in {"cloud", "public", "lan", "local"}:
        raise LoginError("deployment_scope is invalid")
    for field in ("server_url", "web_url", "account_ref"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise LoginError(f"{field} must be a non-empty string")
    if value.get("client_kind") not in {"cli", "desktop"}:
        raise LoginError("client_kind must be cli or desktop")
    if value.get("client_location") not in {"browser-host", "remote-server", "remote-machine"}:
        raise LoginError("client_location is invalid")
    if value["client_kind"] == "cli" and (not isinstance(value.get("profile"), str) or not value["profile"].strip()):
        raise LoginError("CLI login requires an explicit profile")
    if value["client_kind"] == "desktop" and value.get("profile") is not None:
        raise LoginError("Desktop login must not declare a CLI profile")
    value["workspace_selector"] = selector(value.get("workspace_selector"))
    if not isinstance(value.get("execution_requested"), bool) or not isinstance(value.get("ssh_owner_path"), bool):
        raise LoginError("execution_requested and ssh_owner_path must be booleans")
    routes = value.get("routes")
    if not isinstance(routes, dict) or set(routes) != {"http_reachable", "cli_reachable"} or not all(isinstance(routes[key], bool) for key in routes):
        raise LoginError("routes must contain boolean http_reachable and cli_reachable")
    return value


def choose_callback(value: dict[str, Any]) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if value["client_kind"] == "desktop":
        return "desktop_application_callback", blockers
    location = value["client_location"]
    if location == "browser-host":
        return "direct_loopback_callback", blockers
    if value["ssh_owner_path"]:
        return "ssh_tunnel_loopback_callback", blockers
    if value["deployment_scope"] in {"public", "lan"}:
        return "direct_callback_probe_required", blockers
    return "private_prompt_pat", blockers


def choose_transport(value: dict[str, Any]) -> tuple[str, list[str]]:
    routes = value["routes"]
    if routes["cli_reachable"]:
        return "direct_api", []
    if routes["http_reachable"] and value["ssh_owner_path"]:
        return "ssh_tunnel_api", []
    return "blocked", ["BLOCKED_API_ROUTE: CLI cannot reach the authoritative API directly or through the operator-owned SSH path"]


def command_plan(args: argparse.Namespace) -> dict[str, Any]:
    raw = read_object(args.input, "login input")
    value = validate_input(raw)
    callback_mode, callback_blockers = choose_callback(value)
    transport, transport_blockers = choose_transport(value)
    blockers = [*callback_blockers, *transport_blockers]
    if callback_mode == "direct_callback_probe_required":
        blockers.append("CALLBACK_PREFLIGHT_REQUIRED: prove browser-to-CLI callback reachability before login")
    phases = [
        {"state": "endpoint_verified", "proof": "service URL and /health or /ready readback"},
        {"state": "browser_authenticated", "proof": "browser account identity readback"},
        {"state": "cli_authenticated", "proof": "the initiating CLI prints authentication completion and auth status succeeds"},
        {"state": "workspace_selected", "proof": "workspace list and selected workspace readback"},
    ]
    if value["execution_requested"]:
        phases.append({"state": "runtime_ready", "proof": "runtime list and daemon/provider readback"})
    plan = {
        "schema": PLAN_SCHEMA,
        "input_digest": digest_bytes(canonical_json(value)),
        "target": {
            "target_type": value["target_type"],
            "deployment_scope": value["deployment_scope"],
            "server_url": value["server_url"],
            "web_url": value["web_url"],
        },
        "client": {
            "kind": value["client_kind"],
            "location": value["client_location"],
            "profile": value["profile"],
            "account_ref": value["account_ref"],
        },
        "workspace_selector": value["workspace_selector"],
        "execution_requested": value["execution_requested"],
        "callback_mode": callback_mode,
        "api_transport": transport,
        "phases": phases,
        "blockers": blockers,
        "state": "BLOCKED" if blockers else "PLANNED",
        "planned_at": utc_now(),
    }
    plan["plan_digest"] = digest_object(plan, "plan_digest")
    atomic_json(args.output, plan)
    return {"ok": not blockers, "state": plan["state"], "plan": str(args.output.resolve()), "plan_digest": plan["plan_digest"], "callback_mode": callback_mode, "api_transport": transport, "blockers": blockers}


def command_start(args: argparse.Namespace) -> dict[str, Any]:
    plan = load_typed(args.plan, PLAN_SCHEMA, "plan_digest", "login plan")
    if plan.get("state") != "PLANNED" or plan.get("blockers"):
        raise LoginError("cannot start a blocked login plan")
    receipt = {
        "schema": SESSION_SCHEMA,
        "plan_digest": plan["plan_digest"],
        "previous_receipt_digest": None,
        "sequence": 0,
        "state": "planned",
        "evidence_digest": None,
        "observed_at": utc_now(),
    }
    receipt["receipt_digest"] = digest_object(receipt, "receipt_digest")
    atomic_json(args.output, receipt)
    return {"ok": True, "state": "planned", "receipt": str(args.output.resolve()), "receipt_digest": receipt["receipt_digest"]}


def command_advance(args: argparse.Namespace) -> dict[str, Any]:
    plan = load_typed(args.plan, PLAN_SCHEMA, "plan_digest", "login plan")
    receipt = load_typed(args.receipt, SESSION_SCHEMA, "receipt_digest", "login session receipt")
    if receipt.get("plan_digest") != plan["plan_digest"]:
        raise LoginError("login receipt belongs to a different plan")
    if args.state not in SESSION_STATES:
        raise LoginError("requested state is invalid")
    allowed = [item["state"] for item in plan.get("phases", [])]
    if args.state not in allowed:
        raise LoginError("requested state is outside this plan")
    current = receipt.get("state")
    expected = allowed[0] if current == "planned" else allowed[allowed.index(current) + 1] if current in allowed and allowed.index(current) + 1 < len(allowed) else None
    if args.state != expected:
        raise LoginError(f"invalid login transition from {current!r} to {args.state!r}; expected {expected!r}")
    evidence = require_digest(args.evidence_digest, "evidence_digest")
    next_receipt = {
        "schema": SESSION_SCHEMA,
        "plan_digest": plan["plan_digest"],
        "previous_receipt_digest": receipt["receipt_digest"],
        "sequence": int(receipt.get("sequence", -1)) + 1,
        "state": args.state,
        "evidence_digest": evidence,
        "observed_at": utc_now(),
    }
    next_receipt["receipt_digest"] = digest_object(next_receipt, "receipt_digest")
    atomic_json(args.output, next_receipt)
    return {"ok": True, "state": args.state, "receipt": str(args.output.resolve()), "receipt_digest": next_receipt["receipt_digest"]}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--input", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    start = commands.add_parser("start-session")
    start.add_argument("--plan", type=Path, required=True)
    start.add_argument("--output", type=Path, required=True)
    advance = commands.add_parser("advance-session")
    advance.add_argument("--plan", type=Path, required=True)
    advance.add_argument("--receipt", type=Path, required=True)
    advance.add_argument("--state", required=True)
    advance.add_argument("--evidence-digest", required=True)
    advance.add_argument("--output", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "plan":
            result = command_plan(args)
        elif args.command == "start-session":
            result = command_start(args)
        else:
            result = command_advance(args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("ok", True) else 2
    except (LoginError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": "MULTICA_LOGIN_WORKFLOW_FAILED", "detail": str(error)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    import sys
    raise SystemExit(main())
