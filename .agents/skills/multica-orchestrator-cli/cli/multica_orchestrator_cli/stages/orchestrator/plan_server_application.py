#!/usr/bin/env python3
"""Create a deterministic plan for the reusable workspace orchestrator layer."""
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
from verify_skill_integrity import canonical_content_digest, workspace_entries
from multica_state_bundle.identities import canonical_json, digest_bytes
from multica_state_bundle.storage import atomic_json

SCHEMA = "multica-orchestrator.server-application-plan.v6"


def by_name(payload: Any, label: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for item in records(payload, label):
        name = item.get("name")
        if isinstance(name, str) and name:
            result.setdefault(name, []).append(dict(item))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--application-input", type=Path, required=True)
    parser.add_argument("--readback-dir", type=Path, required=True)
    parser.add_argument("--skill-archive-plan", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
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
        archive_plan = read_json(args.skill_archive_plan, "Skill archive plan")
        if not isinstance(archive_plan, dict) or archive_plan.get("schema") != "skill-archive-plan/v1":
            raise InputError("invalid Skill archive plan")
        archive_items = archive_plan.get("skills")
        if not isinstance(archive_items, list):
            raise InputError("Skill archive plan lacks skills")
        archives = {
            item.get("name"): item
            for item in archive_items
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        agents = by_name(read_json(args.readback_dir / "agent-list.json", "agent list"), "agent list")
        squads = by_name(read_json(args.readback_dir / "squad-list.json", "squad list"), "squad list")
        skills = by_name(read_json(args.readback_dir / "skill-list.json", "skill list"), "skill list")
        operations: list[dict[str, Any]] = []
        blockers: list[str] = []
        skill_ids: dict[str, str] = {}
        required_names = sorted({name for role in roles for name in role.skills})
        for name in required_names:
            matches = skills.get(name, [])
            archive = archives.get(name)
            if not isinstance(archive, dict):
                blockers.append(f"SKILL_ARCHIVE_MISSING:{name}")
                continue
            archive_path = (args.skill_archive_plan.parent / str(archive.get("archive_path", ""))).resolve()
            archive_digest = archive.get("archive_raw_digest")
            expected_content_digest = archive.get("content_digest")
            if (
                not archive_path.is_file()
                or not isinstance(archive_digest, str)
                or digest_bytes(archive_path.read_bytes()) != archive_digest
                or not isinstance(expected_content_digest, str)
            ):
                blockers.append(f"SKILL_ARCHIVE_INVALID:{name}")
                continue
            if not matches:
                operations.append({
                    "id": f"skill/{name}/import",
                    "action": "skill-import",
                    "name": name,
                    "archive_path": str(archive_path),
                    "archive_raw_digest": archive_digest,
                    "content_digest": expected_content_digest,
                })
                continue
            if len(matches) != 1 or not isinstance(matches[0].get("id"), str) or not matches[0]["id"]:
                blockers.append(f"WORKSPACE_SKILL_NAME_AMBIGUOUS:{name}")
                continue
            detail_path = args.readback_dir / "skills" / f"{name}.json"
            if not detail_path.is_file():
                blockers.append(f"WORKSPACE_SKILL_READBACK_MISSING:{name}")
                continue
            try:
                observed_id, observed_name, observed_entries = workspace_entries(
                    read_json(detail_path, f"Skill {name}"),
                    f"Skill {name}",
                )
            except ValueError:
                blockers.append(f"WORKSPACE_SKILL_READBACK_INVALID:{name}")
                continue
            resource_id = matches[0]["id"]
            if observed_id != resource_id or observed_name != name:
                blockers.append(f"WORKSPACE_SKILL_READBACK_IDENTITY_MISMATCH:{name}")
                continue
            observed_content_digest = canonical_content_digest(observed_entries)
            if observed_content_digest != expected_content_digest:
                operations.append({
                    "id": f"skill/{name}/update",
                    "action": "skill-update",
                    "name": name,
                    "resource_id": resource_id,
                    "archive_path": str(archive_path),
                    "archive_raw_digest": archive_digest,
                    "content_digest": expected_content_digest,
                })
                continue
            skill_ids[name] = resource_id
        if operations or blockers:
            payload = {
                "schema": SCHEMA,
                "manifest_sha256": digest_bytes(args.manifest.read_bytes()),
                "application_input_sha256": digest_bytes(args.application_input.read_bytes()),
                "skill_archive_plan_sha256": digest_bytes(args.skill_archive_plan.read_bytes()),
                "foundation_bundle_manifest_digest": desired["foundation_bundle_manifest_digest"],
                "observed_state_digest": snapshot_digest,
                "workspace_id": desired["workspace_id"],
                "operations": operations,
                "blockers": sorted(set(blockers)),
            }
            payload["plan_digest"] = digest_bytes(canonical_json(payload))
            atomic_json(args.plan, payload)
            print(payload["plan_digest"])
            return 0
        owner_refs = account_owner_refs(args.readback_dir, desired["account_ref"])
        agent_ids: dict[str, str] = {}
        for role in roles:
            matches = agents.get(role.key, [])
            if len(matches) > 1:
                blockers.append(f"AGENT_NAME_AMBIGUOUS:{role.key}")
                continue
            config = desired["agents"][role.key]
            runtime = desired["runtimes_by_alias"][config["runtime_alias"]]
            expected_fields = {
                "description": role.description,
                "runtime_id": runtime["runtime_ref"],
                "runtime_alias": config["runtime_alias"],
                "model": config["model"],
                "thinking_level": config.get("thinking_level"),
                "max_concurrent_tasks": config["max_concurrent_tasks"],
                "permission_mode": "private",
            }
            instruction_digest = digest_bytes(instruction_path(args.manifest, role).read_bytes())
            expected = {
                **expected_fields,
                "owner_ref": desired["account_ref"],
                "instructions_digest": instruction_digest,
                "skill_names": sorted(role.skills),
            }
            missing_skill = [name for name in role.skills if name not in skill_ids]
            if not matches:
                if not missing_skill:
                    operations.append({"id": f"agent/{role.key}/create", "action": "agent-create", "role_key": role.key, "expected": expected})
                continue
            identifier = matches[0].get("id")
            if not isinstance(identifier, str) or not identifier:
                blockers.append(f"AGENT_ID_MISSING:{role.key}")
                continue
            agent_ids[role.key] = identifier
            detail_path = args.readback_dir / "agents" / f"{role.key}.json"
            if not detail_path.is_file():
                blockers.append(f"AGENT_READBACK_MISSING:{role.key}")
                continue
            detail = read_json(detail_path, f"Agent {role.key}")
            if not isinstance(detail, dict) or agent_owner_ref(detail) not in owner_refs:
                blockers.append(f"AGENT_PRIVATE_OWNER_READBACK_MISMATCH:{role.key}")
            comparable = {
                key: expected[key]
                for key in ("description", "runtime_id", "model", "thinking_level", "max_concurrent_tasks", "permission_mode")
            }
            differs = (
                not isinstance(detail, dict)
                or any(
                    (normalized_thinking_level(detail.get(key)) if key == "thinking_level" else detail.get(key)) != value
                    for key, value in comparable.items()
                )
                or not isinstance(detail.get("instructions"), str)
                or digest_bytes(detail["instructions"].encode()) != instruction_digest
            )
            if differs:
                operations.append({"id": f"agent/{role.key}/update", "action": "agent-update", "role_key": role.key, "resource_id": identifier, "expected": expected})
            if not missing_skill:
                binding_path = args.readback_dir / "agents" / f"{role.key}.skills.json"
                if not binding_path.is_file():
                    blockers.append(f"AGENT_SKILL_READBACK_MISSING:{role.key}")
                else:
                    observed_ids = {item.get("id", item.get("skill_id")) for item in records(read_json(binding_path, f"Agent Skills {role.key}"), f"Agent Skills {role.key}")}
                    expected_ids = {skill_ids[name] for name in role.skills}
                    if observed_ids != expected_ids:
                        operations.append({"id": f"agent/{role.key}/skills", "action": "agent-skills-set", "role_key": role.key, "resource_id": identifier, "skill_ids": sorted(expected_ids)})
        leader = agent_ids.get("workflow-leader")
        squad_specs = load_squad_specs(args.manifest, roles)
        for squad_name, squad_spec in squad_specs.items():
            matches = squads.get(squad_name, [])
            expected_roles = dict(squad_spec.members)
            if len(matches) > 1:
                blockers.append(f"SQUAD_NAME_AMBIGUOUS:{squad_name}")
            elif not matches:
                if leader:
                    operations.append({
                        "id": f"squad/{squad_name}/create",
                        "action": "squad-create",
                        "name": squad_name,
                        "leader_id": leader,
                    })
            else:
                squad_id = matches[0].get("id")
                if not isinstance(squad_id, str) or not squad_id:
                    blockers.append(f"SQUAD_ID_MISSING:{squad_name}")
                    continue
                detail_path = args.readback_dir / "squads" / f"{squad_name}.json"
                members_path = args.readback_dir / "squads" / f"{squad_name}.members.json"
                if not detail_path.is_file() or not members_path.is_file():
                    blockers.append(f"SQUAD_READBACK_MISSING:{squad_name}")
                    continue
                detail = read_json(detail_path, f"Squad {squad_name}")
                instructions = (args.manifest.parent / squad_spec.instructions).resolve().read_text(encoding="utf-8")
                if (
                    detail.get("leader_id", detail.get("leader_agent_id")) != leader
                    or detail.get("description") != squad_spec.description
                    or detail.get("instructions") != instructions
                ):
                    operations.append({"id": f"squad/{squad_name}/update", "action": "squad-update", "name": squad_name, "resource_id": squad_id, "leader_id": leader})
                member_records = records(read_json(members_path, f"Squad members {squad_name}"), f"Squad members {squad_name}")
                leader_members = {squad_member_agent_id(item) for item in member_records if squad_member_role(item) == "leader"}
                ordinary_records = [item for item in member_records if squad_member_role(item) != "leader"]
                if leader_members != ({leader} if leader else set()):
                    blockers.append(f"SQUAD_LEADER_MEMBERSHIP_MISMATCH:{squad_name}")
                expected_by_id = {
                    agent_ids[role_key]: (role_key, squad_role)
                    for role_key, squad_role in expected_roles.items()
                    if role_key in agent_ids
                }
                observed_by_id: dict[str, list[dict[str, Any]]] = {}
                for item in ordinary_records:
                    member_id = squad_member_agent_id(item)
                    if isinstance(member_id, str):
                        observed_by_id.setdefault(member_id, []).append(dict(item))
                for member_id, records_for_id in observed_by_id.items():
                    if len(records_for_id) > 1:
                        blockers.append(f"SQUAD_MEMBER_AMBIGUOUS:{squad_name}:{member_id}")
                    elif member_id not in expected_by_id:
                        operations.append({
                            "id": f"squad/{squad_name}/member/{member_id}/remove",
                            "action": "squad-member-remove",
                            "resource_id": squad_id,
                            "agent_id": member_id,
                        })
                for member_id, (role_key, expected_role) in expected_by_id.items():
                    observed = observed_by_id.get(member_id, [])
                    if not observed:
                        operations.append({
                            "id": f"squad/{squad_name}/member/{role_key}/add",
                            "action": "squad-member-add",
                            "resource_id": squad_id,
                            "agent_id": member_id,
                            "squad_role": expected_role,
                        })
                    elif len(observed) == 1 and squad_member_role(observed[0]) != expected_role:
                        operations.append({
                            "id": f"squad/{squad_name}/member/{role_key}/role",
                            "action": "squad-member-role-update",
                            "resource_id": squad_id,
                            "agent_id": member_id,
                            "squad_role": expected_role,
                        })
        payload = {
            "schema": SCHEMA,
            "manifest_sha256": digest_bytes(args.manifest.read_bytes()),
            "application_input_sha256": digest_bytes(args.application_input.read_bytes()),
            "skill_archive_plan_sha256": digest_bytes(args.skill_archive_plan.read_bytes()),
            "foundation_bundle_manifest_digest": desired["foundation_bundle_manifest_digest"],
            "observed_state_digest": snapshot_digest,
            "workspace_id": desired["workspace_id"],
            "operations": operations,
            "blockers": sorted(set(blockers)),
        }
        payload["plan_digest"] = digest_bytes(canonical_json(payload))
        atomic_json(args.plan, payload)
        print(payload["plan_digest"])
        return 0
    except (InputError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
