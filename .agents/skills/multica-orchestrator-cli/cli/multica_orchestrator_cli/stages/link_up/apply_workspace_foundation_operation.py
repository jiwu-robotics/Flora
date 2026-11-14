#!/usr/bin/env python3
"""Apply one authorized foundation operation with stale-plan and postcondition checks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from foundation_common import (
    InputError,
    load_input,
    read_json,
    readback_snapshot_digest,
    records,
    run_multica,
)
from multica_state_bundle.identities import (
    StateError,
    bootstrap_deployment_key,
    canonical_json,
    digest_bytes,
)
from multica_state_bundle.relocations import hold_relocation_mutation_guard, release_relocation_mutation_guard


def unique_named(payload: Any, name: str, label: str) -> Mapping[str, Any] | None:
    matches = [item for item in records(payload, label) if item.get("name", item.get("display_name")) == name]
    if len(matches) > 1:
        raise InputError(f"STALE_PLAN: {label} contains multiple resources named {name}")
    return matches[0] if matches else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--readback-snapshot", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-digest", required=True)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--authorization-ref", required=True)
    parser.add_argument("--multica-command", default="multica")
    args = parser.parse_args()
    _relocation_guard: int | None = None
    try:
        if not args.apply:
            raise InputError("--apply is required")
        configuration = load_input(args.input)
        plan = read_json(args.plan, "workspace foundation plan")
        if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA:
            raise InputError("invalid workspace foundation plan schema")
        unsigned = dict(plan)
        observed = unsigned.pop("plan_digest", None)
        actual = digest_bytes(canonical_json(unsigned))
        if observed != actual or args.plan_digest != actual:
            raise InputError("plan digest does not match current plan")
        if plan.get("input_digest") != digest_bytes(args.input.read_bytes()):
            raise InputError("workspace foundation input changed after the reviewed plan was generated")
        runtime_refs = [
            runtime["runtime_ref"]
            for runtime in configuration["runtime_fleet"]["runtimes"]
            if runtime.get("runtime_ref")
        ]
        if plan.get("observed_state_digest") != readback_snapshot_digest(
            args.readback_snapshot,
            server_ref=configuration["server"]["ref"],
            profile_ref=configuration["server"]["profile"],
            account_ref=configuration["server"]["account_ref"],
            workspace_ref=configuration["workspace"].get("workspace_ref"),
            runtime_refs=runtime_refs,
        ):
            raise InputError("STALE_PLAN: workspace readback snapshot changed")
        server = configuration["server"]
        workspace_ref = configuration["workspace"].get("workspace_ref")
        deployment_key = server.get("deployment_key") or bootstrap_deployment_key(
            server["kind"], server["ref"], workspace_ref
        )
        _relocation_guard = hold_relocation_mutation_guard(
            Path(configuration["operator_state_root"]),
            deployment_key,
            server.get("relocation_intent_digest"),
            kind="workspace-apply",
            subject=str(workspace_ref or "workspace-pending"),
        )
        matches = [item for item in plan.get("operations", []) if isinstance(item, dict) and item.get("id") == args.operation]
        if len(matches) != 1:
            raise InputError("operation is not unique in plan")
        operation = matches[0]
        action = operation.get("action")
        mutation: Any
        postcondition: Any
        if action == "workspace-create":
            before = run_multica(configuration, args.multica_command, ["workspace", "list"], workspace_scoped=False)
            if unique_named(before, operation["name"], "workspace list") is not None:
                raise InputError("STALE_PLAN: workspace already exists")
            mutation = run_multica(configuration, args.multica_command, ["workspace", "create", "--name", operation["name"], "--slug", operation["slug"], "--issue-prefix", operation["issue_prefix"]], workspace_scoped=False)
            after = run_multica(configuration, args.multica_command, ["workspace", "list"], workspace_scoped=False)
            postcondition = unique_named(after, operation["name"], "workspace list")
            if postcondition is None:
                raise InputError("postcondition failed: workspace is absent")
        elif action == "label-create":
            before = run_multica(configuration, args.multica_command, ["label", "list"], workspace_scoped=True)
            if unique_named(before, operation["name"], "label list") is not None:
                raise InputError("STALE_PLAN: label already exists")
            mutation = run_multica(configuration, args.multica_command, ["label", "create", "--name", operation["name"], "--color", operation["color"]], workspace_scoped=True)
            after = run_multica(configuration, args.multica_command, ["label", "list"], workspace_scoped=True)
            postcondition = unique_named(after, operation["name"], "label list")
            if postcondition is None or str(postcondition.get("color", "")).lower() != operation["color"]:
                raise InputError("postcondition failed: label is absent or has the wrong color")
        elif action == "runtime-profile-create":
            before = run_multica(configuration, args.multica_command, ["runtime", "profile", "list"], workspace_scoped=True)
            if unique_named(before, operation["display_name"], "runtime profile list") is not None:
                raise InputError("STALE_PLAN: runtime profile already exists")
            mutation = run_multica(configuration, args.multica_command, ["runtime", "profile", "create", "--display-name", operation["display_name"], "--command-name", operation["command_name"], "--protocol-family", operation["protocol_family"]], workspace_scoped=True)
            after = run_multica(configuration, args.multica_command, ["runtime", "profile", "list"], workspace_scoped=True)
            postcondition = unique_named(after, operation["display_name"], "runtime profile list")
            if postcondition is None:
                raise InputError("postcondition failed: runtime profile is absent")
        elif action == "runtime-daemon-start":
            before = run_multica(configuration, args.multica_command, ["runtime", "list"], workspace_scoped=True)
            current = unique_named(before, operation["runtime_name"], "runtime list")
            if current is not None and current.get("status") == "online":
                raise InputError("STALE_PLAN: runtime is already online")
            mutation = run_multica(configuration, args.multica_command, ["daemon", "start", "--runtime-name", operation["runtime_name"]], workspace_scoped=False, json_output=False)
            after = run_multica(configuration, args.multica_command, ["runtime", "list"], workspace_scoped=True)
            postcondition = unique_named(after, operation["runtime_name"], "runtime list")
            if postcondition is None or postcondition.get("status") != "online":
                raise InputError("postcondition failed: runtime is not online")
        else:
            raise InputError(f"unsupported operation action: {action}")
        print(json.dumps({
            "ok": True,
            "operation": args.operation,
            "authorization_ref": args.authorization_ref,
            "mutation_response": mutation,
            "postcondition_readback": postcondition,
            "postcondition_digest": digest_bytes(canonical_json(postcondition)),
        }, ensure_ascii=False, sort_keys=True))
        return 0
    except (StateError, InputError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "error": "WORKSPACE_FOUNDATION_OPERATION_REJECTED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        if _relocation_guard is not None:
            release_relocation_mutation_guard(_relocation_guard)


if __name__ == "__main__":
    raise SystemExit(main())
