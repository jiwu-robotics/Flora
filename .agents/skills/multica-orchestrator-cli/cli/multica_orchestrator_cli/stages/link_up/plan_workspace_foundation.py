#!/usr/bin/env python3
"""Create a deterministic, read-only workspace foundation plan."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from foundation_common import LABEL_COLORS, PLAN_SCHEMA, InputError, foundation_blockers, load_input, readback_snapshot_digest
from multica_state_bundle.identities import canonical_json, digest_bytes
from multica_state_bundle.storage import atomic_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--readback-snapshot", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    try:
        configuration = load_input(args.input)
        runtime_refs = [
            runtime["runtime_ref"]
            for runtime in configuration["runtime_fleet"]["runtimes"]
            if runtime.get("runtime_ref")
        ]
        snapshot_digest = readback_snapshot_digest(
            args.readback_snapshot,
            server_ref=configuration["server"]["ref"],
            profile_ref=configuration["server"]["profile"],
            account_ref=configuration["server"]["account_ref"],
            workspace_ref=configuration["workspace"].get("workspace_ref"),
            runtime_refs=runtime_refs,
        )
        workspace = configuration["workspace"]
        operations: list[dict[str, object]] = []
        if not workspace["exists"]:
            operations.append({"id": "workspace/create", "action": "workspace-create", "name": workspace["name"], "slug": workspace["slug"], "issue_prefix": workspace["issue_prefix"]})
        else:
            for name, desired_color in LABEL_COLORS.items():
                label = configuration["labels"][name]
                if not label["exists"]:
                    operations.append({"id": f"label/{name}/create", "action": "label-create", "name": name, "color": desired_color})
            for runtime in configuration["runtime_fleet"]["runtimes"]:
                profile = runtime.get("profile")
                if profile and not profile["exists"]:
                    operations.append({
                        "id": f"runtime/{runtime['alias']}/profile/create",
                        "action": "runtime-profile-create",
                        "display_name": profile["display_name"],
                        "command_name": profile["command_name"],
                        "protocol_family": profile["protocol_family"],
                    })
                if runtime["status"] != "online" and runtime["daemon_start_required"]:
                    operations.append({
                        "id": f"runtime/{runtime['alias']}/daemon/start",
                        "action": "runtime-daemon-start",
                        "runtime_name": runtime["name"],
                    })
        payload = {
            "schema": PLAN_SCHEMA,
            "input_digest": digest_bytes(args.input.read_bytes()),
            "observed_state_digest": snapshot_digest,
            "workspace_ref": workspace.get("workspace_ref"),
            "operations": operations,
            "blockers": foundation_blockers(configuration),
        }
        payload["plan_digest"] = digest_bytes(canonical_json(payload))
        atomic_bytes(args.plan, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        print(payload["plan_digest"])
        return 0
    except (InputError, OSError, KeyError, TypeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
