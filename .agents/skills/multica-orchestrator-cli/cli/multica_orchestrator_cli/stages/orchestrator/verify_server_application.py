#!/usr/bin/env python3
"""Verify Runtime placements, Skills, Agents, and Squads without Project scope."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from server_application_common import (
    InputError,
    account_owner_refs,
    agent_owner_ref,
    instruction_path,
    load_input,
    load_manifest,
    load_squad_specs,
    normalized_thinking_level,
    read_json,
    readback_snapshot_digest,
    records,
    squad_member_agent_id,
    squad_member_role,
)
from multica_state_bundle.identities import canonical_json, digest_bytes, utc_now
from multica_state_bundle.storage import atomic_json


def fail(errors: list[dict[str, str]], code: str, subject: str, detail: str) -> None:
    errors.append({"code": code, "subject": subject, "detail": detail})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--application-input", type=Path, required=True)
    parser.add_argument("--readback-dir", type=Path, required=True)
    parser.add_argument("--setup-record", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        roles = load_manifest(args.manifest)
        desired = load_input(args.application_input, roles)
        snapshot_digest = readback_snapshot_digest(
            args.readback_dir,
            workspace_id=desired["workspace_id"],
            runtime_refs=desired["runtime_refs"],
            daemon_refs=desired["daemon_refs"],
        )
        errors: list[dict[str, str]] = []
        ids: dict[str, str] = {}
        runtime_records = records(read_json(args.readback_dir / "runtime-list.json", "Runtime list"), "Runtime list")
        for alias, runtime in desired["runtimes_by_alias"].items():
            matches = [item for item in runtime_records if item.get("id") == runtime["runtime_ref"]]
            if len(matches) != 1 or matches[0].get("status") != "online":
                fail(errors, "RUNTIME_NOT_ONLINE", alias, "selected Runtime is not uniquely online")
        skill_specs: dict[str, str] = {}
        required_skills = sorted({skill for role in roles for skill in role.skills})
        skill_list = records(read_json(args.readback_dir / "skill-list.json", "Skill list"), "Skill list")
        for skill_name in required_skills:
            matches = [item for item in skill_list if item.get("name") == skill_name]
            detail = args.readback_dir / "skills" / f"{skill_name}.json"
            if len(matches) != 1 or not detail.is_file():
                fail(errors, "SKILL_CONFIGURATION_MISMATCH", skill_name, "Skill identity or content readback is missing")
            else:
                skill_specs[skill_name] = digest_bytes(canonical_json(read_json(detail, f"Skill {skill_name}")))
        owner_refs = account_owner_refs(args.readback_dir, desired["account_ref"])
        agent_specs: dict[str, dict[str, Any]] = {}
        for role in roles:
            payload = read_json(args.readback_dir / "agents" / f"{role.key}.json", f"Agent readback for {role.key}")
            if not isinstance(payload, dict):
                raise InputError(f"Agent readback for {role.key} must be an object")
            identifier = payload.get("id")
            if not isinstance(identifier, str) or not identifier:
                fail(errors, "AGENT_CONFIGURATION_MISMATCH", role.key, "missing id")
                identifier = ""
            else:
                ids[role.key] = identifier
            expected = desired["agents"][role.key]
            runtime = desired["runtimes_by_alias"][expected["runtime_alias"]]
            fields = {
                "name": role.key,
                "description": role.description,
                "runtime_id": runtime["runtime_ref"],
                "model": expected["model"],
                "thinking_level": expected.get("thinking_level"),
                "max_concurrent_tasks": expected["max_concurrent_tasks"],
                "permission_mode": "private",
            }
            for key, value in fields.items():
                observed = normalized_thinking_level(payload.get(key)) if key == "thinking_level" else payload.get(key)
                if observed != value:
                    fail(errors, "AGENT_CONFIGURATION_MISMATCH", role.key, f"{key} expected {value!r}, observed {payload.get(key)!r}")
            instructions = payload.get("instructions")
            instructions_digest = digest_bytes(instruction_path(args.manifest, role).read_bytes())
            if not isinstance(instructions, str) or digest_bytes(instructions.encode()) != instructions_digest:
                fail(errors, "AGENT_CONFIGURATION_MISMATCH", role.key, "instructions differ from manifest source")
            owner_ref = agent_owner_ref(payload)
            if owner_ref not in owner_refs:
                fail(errors, "AGENT_PRIVATE_OWNER_READBACK_MISMATCH", role.key, "Agent owner does not match the authenticated operator account")
            skill_path = args.readback_dir / "agents" / f"{role.key}.skills.json"
            if not skill_path.is_file():
                fail(errors, "AGENT_SKILL_BINDING_MISMATCH", role.key, "Skill binding readback is missing")
            agent_specs[role.key] = {
                "agent_ref": identifier,
                "runtime_alias": expected["runtime_alias"],
                "runtime_ref": runtime["runtime_ref"],
                "model": expected["model"],
                "thinking_level": expected.get("thinking_level"),
                "max_concurrent_tasks": expected["max_concurrent_tasks"],
                "permission_mode": "private",
                "owner_ref": owner_ref,
                "access_attestation": {
                    "permission_mode": "private",
                    "owner_ref": owner_ref,
                    "same_owner": owner_ref == desired["account_ref"],
                },
                "instructions_digest": instructions_digest,
                "skill_names": sorted(role.skills),
            }
        squad_specs: dict[str, dict[str, Any]] = {}
        manifest_squads = load_squad_specs(args.manifest, roles)
        for squad_name, squad_spec in manifest_squads.items():
            payload = read_json(args.readback_dir / "squads" / f"{squad_name}.json", f"Squad readback for {squad_name}")
            member_records = records(read_json(args.readback_dir / "squads" / f"{squad_name}.members.json", f"Squad members for {squad_name}"), f"Squad members for {squad_name}")
            expected_by_id = {
                ids[role_key]: (role_key, squad_role)
                for role_key, squad_role in squad_spec.members
                if role_key in ids
            }
            ordinary_records = [item for item in member_records if squad_member_role(item) != "leader"]
            observed_by_id: dict[str, list[dict[str, Any]]] = {}
            for item in ordinary_records:
                member_id = squad_member_agent_id(item)
                if isinstance(member_id, str):
                    observed_by_id.setdefault(member_id, []).append(dict(item))
            leader_ref = ids.get("workflow-leader", "")
            leader_members = {squad_member_agent_id(item) for item in member_records if squad_member_role(item) == "leader"}
            if not isinstance(payload, dict) or payload.get("name") != squad_name:
                fail(errors, "SQUAD_CONFIGURATION_MISMATCH", squad_name, "name differs")
            if payload.get("description") != squad_spec.description:
                fail(errors, "SQUAD_CONFIGURATION_MISMATCH", squad_name, "description differs")
            if payload.get("leader_id", payload.get("leader_agent_id")) != leader_ref:
                fail(errors, "SQUAD_CONFIGURATION_MISMATCH", squad_name, "leader differs")
            if leader_members != {leader_ref}:
                fail(errors, "SQUAD_CONFIGURATION_MISMATCH", squad_name, "leader membership differs")
            if set(observed_by_id) != set(expected_by_id) or any(len(items) != 1 for items in observed_by_id.values()):
                fail(errors, "SQUAD_CONFIGURATION_MISMATCH", squad_name, "membership differs")
            role_mismatches = [
                role_key
                for member_id, (role_key, expected_role) in expected_by_id.items()
                if len(observed_by_id.get(member_id, [])) != 1
                or squad_member_role(observed_by_id[member_id][0]) != expected_role
            ]
            if role_mismatches:
                fail(errors, "SQUAD_ROLE_TEXT_MISMATCH", squad_name, ", ".join(sorted(role_mismatches)))
            instructions_path = (args.manifest.parent / squad_spec.instructions).resolve()
            instructions_digest = digest_bytes(instructions_path.read_bytes())
            if payload.get("instructions") != instructions_path.read_text(encoding="utf-8"):
                fail(errors, "SQUAD_CONFIGURATION_MISMATCH", squad_name, "instructions differ")
            squad_specs[squad_name] = {
                "squad_ref": payload.get("id", ""),
                "leader_ref": leader_ref,
                "instructions_digest": instructions_digest,
                "member_refs": sorted(expected_by_id),
                "member_roles": {
                    role_key: {
                        "agent_ref": member_id,
                        "squad_role": expected_role,
                    }
                    for member_id, (role_key, expected_role) in sorted(expected_by_id.items())
                },
            }
        if args.setup_record is not None:
            record = read_json(args.setup_record, "setup record")
            if not isinstance(record, dict) or record.get("dispatch_state") != "BLOCKED_PROJECT_BINDING":
                fail(errors, "DISPATCH_STATE_INVALID", "setup-record", "Server layer must remain BLOCKED_PROJECT_BINDING")
        produced_at = utc_now()
        verification_spec = {
            "schema": "multica-orchestrator.server-verification-spec.v3",
            "server_ref": desired["server_ref"],
            "server_kind": desired["server_kind"],
            "deployment_key": desired["deployment_key"],
            "relocation_intent_digest": desired["relocation_intent_digest"],
            "workspace_ref": desired["workspace_id"],
            "package_manifest_digest": digest_bytes(args.manifest.read_bytes()),
            "runtime_fleet": [
                {
                    "alias": alias,
                    "runtime_ref": runtime["runtime_ref"],
                    "daemon_ref": runtime["daemon_ref"],
                    "provider": runtime["provider"],
                    "capability_revision": runtime["capability_revision"],
                }
                for alias, runtime in sorted(desired["runtimes_by_alias"].items())
            ],
            "skills": skill_specs,
            "agents": agent_specs,
            "squads": squad_specs,
            "produced_at": produced_at,
        }
        result: dict[str, Any] = {
            "schema": "multica-orchestrator.server-verification.v3",
            "ok": not errors,
            "errors": errors,
            "manifest_digest": digest_bytes(args.manifest.read_bytes()),
            "application_input_digest": digest_bytes(args.application_input.read_bytes()),
            "foundation_manifest_digest": desired["foundation_bundle_manifest_digest"],
            "readback_snapshot_digest": snapshot_digest,
            "workspace_ref": desired["workspace_id"],
            "runtime_refs": desired["runtime_refs"],
            "daemon_refs": desired["daemon_refs"],
            "observed_at": produced_at,
            "agents": sorted(ids),
            "agent_ids": ids,
            "squads": ["feature", "fix"],
            "verification_spec": verification_spec,
            "dispatch_state": "BLOCKED_PROJECT_BINDING",
        }
        if args.output:
            atomic_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not errors else 1
    except (InputError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "errors": [{"code": "SERVER_APPLICATION_INPUT_INVALID", "detail": str(error)}]}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
