#!/usr/bin/env python3
"""Capture reusable workspace runtime, Skill, Agent, and Squad readbacks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from server_application_common import InputError, load_input, load_manifest, records, run_multica
from multica_state_bundle.identities import canonical_json, digest_bytes, utc_now
from multica_state_bundle.storage import atomic_json
from multica_orchestrator_cli.common.runtime_capability import RuntimeCapabilityEvidenceError, runtime_fleet_stability_projection


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--application-input", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--multica-command", default="multica")
    args = parser.parse_args()
    try:
        roles = load_manifest(args.manifest)
        configuration = load_input(args.application_input, roles)
        state = args.state_dir / "readback"
        captures = {
            "workspace.json": ["workspace", "get", configuration["workspace_id"]],
            "workspace-member-list.json": ["workspace", "member", "list"],
            "runtime-list.json": ["runtime", "list"],
            "skill-list.json": ["skill", "list"],
            "agent-list.json": ["agent", "list", "--include-archived"],
            "squad-list.json": ["squad", "list"],
        }
        payloads = {}
        for name, command in captures.items():
            payloads[name] = run_multica(configuration, args.multica_command, command)
            atomic_json(state / name, payloads[name])
        agents = {item.get("name"): item.get("id") for item in records(payloads["agent-list.json"], "agent list") if isinstance(item.get("name"), str) and isinstance(item.get("id"), str)}
        squads = {item.get("name"): item.get("id") for item in records(payloads["squad-list.json"], "squad list") if isinstance(item.get("name"), str) and isinstance(item.get("id"), str)}
        skills_by_name: dict[str, list[str]] = {}
        for item in records(payloads["skill-list.json"], "skill list"):
            if isinstance(item.get("name"), str) and isinstance(item.get("id"), str):
                skills_by_name.setdefault(item["name"], []).append(item["id"])
        for skill_name in sorted({skill for role in roles for skill in role.skills}):
            identifiers = skills_by_name.get(skill_name, [])
            if len(identifiers) == 1:
                atomic_json(
                    state / "skills" / f"{skill_name}.json",
                    run_multica(configuration, args.multica_command, ["skill", "get", identifiers[0], "--with-content"]),
                )
        for role in roles:
            identifier = agents.get(role.key)
            if identifier:
                atomic_json(state / "agents" / f"{role.key}.json", run_multica(configuration, args.multica_command, ["agent", "get", identifier]))
                atomic_json(state / "agents" / f"{role.key}.skills.json", run_multica(configuration, args.multica_command, ["agent", "skills", "list", identifier]))
        for name in ("feature", "fix"):
            identifier = squads.get(name)
            if identifier:
                atomic_json(state / "squads" / f"{name}.json", run_multica(configuration, args.multica_command, ["squad", "get", identifier]))
                atomic_json(state / "squads" / f"{name}.members.json", run_multica(configuration, args.multica_command, ["squad", "member", "list", identifier]))
        workspace_after = run_multica(configuration, args.multica_command, ["workspace", "get", configuration["workspace_id"]])
        runtime_after = run_multica(configuration, args.multica_command, ["runtime", "list"])
        if (
            canonical_json(workspace_after) != canonical_json(payloads["workspace.json"])
            or runtime_fleet_stability_projection(records(runtime_after, "runtime list"))
            != runtime_fleet_stability_projection(records(payloads["runtime-list.json"], "runtime list"))
        ):
            raise InputError("STALE_READBACK_SNAPSHOT: workspace or Runtime fleet changed during capture")
        atomic_json(state / "workspace-after.json", workspace_after)
        atomic_json(state / "runtime-list-after.json", runtime_after)
        artifacts = {
            str(path.relative_to(state)): digest_bytes(path.read_bytes())
            for path in sorted(state.rglob("*.json"))
            if path.name != "snapshot.json"
        }
        snapshot = {
            "schema": "multica-orchestrator.readback-snapshot.v2",
            "workspace_id": configuration["workspace_id"],
            "runtime_refs": configuration["runtime_refs"],
            "daemon_refs": configuration["daemon_refs"],
            "observed_at": utc_now(),
            "artifacts": artifacts,
        }
        snapshot["snapshot_digest"] = digest_bytes(canonical_json(snapshot))
        atomic_json(state / "snapshot.json", snapshot)
        summary = {
            "ok": True,
            "workspace_id": configuration["workspace_id"],
            "runtimes": sorted(configuration["runtime_refs"]),
            "roles": len(roles),
            "squads": ["feature", "fix"],
            "snapshot_digest": snapshot["snapshot_digest"],
        }
        atomic_json(args.state_dir / "snapshot.json", summary)
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (InputError, RuntimeCapabilityEvidenceError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
