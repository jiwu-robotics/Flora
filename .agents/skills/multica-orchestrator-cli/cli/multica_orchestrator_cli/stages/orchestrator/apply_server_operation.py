#!/usr/bin/env python3
"""Apply one authorized Server operation with stale-plan and postcondition checks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from server_application_common import (
    InputError,
    instruction_path,
    load_input,
    load_manifest,
    load_squad_specs,
    normalized_thinking_level,
    read_json,
    readback_snapshot_digest,
    records,
    run_multica,
)
from verify_skill_integrity import canonical_content_digest, workspace_entries
from multica_state_bundle.identities import StateError, canonical_json, digest_bytes
from multica_state_bundle.relocations import hold_relocation_mutation_guard, release_relocation_mutation_guard

PLAN_SCHEMA = "multica-orchestrator.server-application-plan.v6"


def unique_named(payload: Any, name: str, label: str) -> Mapping[str, Any] | None:
    matches = [item for item in records(payload, label) if item.get("name") == name]
    if len(matches) > 1:
        raise InputError(f"STALE_PLAN: {label} contains multiple resources named {name}")
    return matches[0] if matches else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-digest", required=True)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--authorization-ref", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--application-input", type=Path, required=True)
    parser.add_argument("--skill-archive-plan", type=Path, required=True)
    parser.add_argument("--readback-dir", type=Path, required=True)
    parser.add_argument("--multica-command", default="multica")
    args = parser.parse_args()
    _relocation_guard: int | None = None
    try:
        if not args.apply:
            raise InputError("--apply is required")
        roles = load_manifest(args.manifest)
        configuration = load_input(args.application_input, roles)
        role_map = {role.key: role for role in roles}
        squad_specs = load_squad_specs(args.manifest, roles)
        plan = read_json(args.plan, "server application plan")
        if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA:
            raise InputError("invalid server application plan schema")
        unsigned = dict(plan)
        observed = unsigned.pop("plan_digest", None)
        actual = digest_bytes(canonical_json(unsigned))
        if observed != actual or args.plan_digest != actual:
            raise InputError("plan digest does not match current plan")
        if plan.get("manifest_sha256") != digest_bytes(args.manifest.read_bytes()):
            raise InputError("manifest changed after the reviewed plan was generated")
        if plan.get("application_input_sha256") != digest_bytes(args.application_input.read_bytes()):
            raise InputError("application input changed after the reviewed plan was generated")
        if plan.get("skill_archive_plan_sha256") != digest_bytes(args.skill_archive_plan.read_bytes()):
            raise InputError("Skill archive plan changed after the reviewed plan was generated")
        if plan.get("foundation_bundle_manifest_digest") != configuration["foundation_bundle_manifest_digest"]:
            raise InputError("workspace foundation bundle changed after the reviewed plan was generated")
        if plan.get("observed_state_digest") != readback_snapshot_digest(
            args.readback_dir,
            workspace_id=configuration["workspace_id"],
            runtime_refs=configuration["runtime_refs"],
            daemon_refs=configuration["daemon_refs"],
        ):
            raise InputError("readback snapshot changed after the reviewed plan was generated")
        if plan.get("blockers"):
            raise InputError("plan has unresolved blockers")
        _relocation_guard = hold_relocation_mutation_guard(
            Path(configuration["bundle_store"]["state_root"]).parent,
            configuration["deployment_key"],
            configuration.get("relocation_intent_digest"),
            kind="server-apply",
            subject=configuration["workspace_id"],
        )
        matches = [item for item in plan.get("operations", []) if isinstance(item, dict) and item.get("id") == args.operation]
        if len(matches) != 1:
            raise InputError("operation is not unique in plan")
        operation = matches[0]
        action = operation["action"]
        mutation: Any
        postcondition: Any

        if action in {"skill-import", "skill-update"}:
            existing = unique_named(
                run_multica(configuration, args.multica_command, ["skill", "list"]),
                operation["name"],
                "Skill list",
            )
            if action == "skill-import" and existing is not None:
                raise InputError(f"STALE_PLAN: Skill already exists: {operation['name']}")
            if action == "skill-update" and (
                existing is None or existing.get("id") != operation["resource_id"]
            ):
                raise InputError(f"STALE_PLAN: Skill identity changed: {operation['name']}")
            archive = Path(operation["archive_path"]).resolve()
            if not archive.is_file() or digest_bytes(archive.read_bytes()) != operation["archive_raw_digest"]:
                raise InputError("Skill archive digest mismatch")
            mutation = run_multica(
                configuration,
                args.multica_command,
                [
                    "skill",
                    "import",
                    "--file",
                    str(archive),
                    "--on-conflict",
                    "overwrite" if action == "skill-update" else "fail",
                ],
            )
            listed = run_multica(configuration, args.multica_command, ["skill", "list"])
            current = unique_named(listed, operation["name"], "Skill list")
            if current is None or not isinstance(current.get("id"), str) or not current["id"]:
                raise InputError("postcondition failed: imported Skill is absent or ambiguous")
            postcondition = run_multica(
                configuration,
                args.multica_command,
                ["skill", "get", current["id"], "--with-content"],
            )
            observed_id, observed_name, observed_entries = workspace_entries(
                postcondition,
                f"Skill postcondition {operation['name']}",
            )
            if observed_id != current["id"] or observed_name != operation["name"]:
                raise InputError("postcondition failed: Skill identity differs")
            if canonical_content_digest(observed_entries) != operation["content_digest"]:
                raise InputError("postcondition failed: Skill content differs")
        elif action in {"agent-create", "agent-update"}:
            role = role_map[operation["role_key"]]
            desired = configuration["agents"][role.key]
            existing = unique_named(run_multica(configuration, args.multica_command, ["agent", "list", "--include-archived"]), role.key, "Agent list")
            if action == "agent-create" and existing is not None:
                raise InputError(f"STALE_PLAN: Agent already exists: {role.key}")
            if action == "agent-update":
                if existing is None or existing.get("id") != operation["resource_id"]:
                    raise InputError(f"STALE_PLAN: Agent identity changed: {role.key}")
                current = run_multica(configuration, args.multica_command, ["agent", "get", operation["resource_id"]])
                if desired.get("thinking_level") is None and normalized_thinking_level(current.get("thinking_level")) is not None:
                    raise InputError("AGENT_THINKING_RESET_UNSUPPORTED: runtime-default cannot be restored by omission")
            command = ["agent", "create" if action == "agent-create" else "update"]
            if action == "agent-update":
                command.append(operation["resource_id"])
            runtime = configuration["runtimes_by_alias"][desired["runtime_alias"]]
            command.extend([
                "--name", role.key,
                "--description", role.description,
                "--instructions", instruction_path(args.manifest, role).read_text(encoding="utf-8"),
                "--runtime-id", runtime["runtime_ref"],
                "--model", desired["model"],
                "--max-concurrent-tasks", str(desired["max_concurrent_tasks"]),
                "--permission-mode", "private",
            ])
            if desired.get("thinking_level") is not None:
                command.extend(["--thinking-level", desired["thinking_level"]])
            mutation = run_multica(configuration, args.multica_command, command)
            listed = run_multica(configuration, args.multica_command, ["agent", "list", "--include-archived"])
            current = unique_named(listed, role.key, "Agent list")
            if current is None or not isinstance(current.get("id"), str):
                raise InputError("postcondition failed: Agent is absent")
            postcondition = run_multica(configuration, args.multica_command, ["agent", "get", current["id"]])
        elif action == "agent-skills-set":
            mutation = run_multica(configuration, args.multica_command, ["agent", "skills", "set", operation["resource_id"], "--skill-ids", ",".join(operation["skill_ids"])])
            postcondition = run_multica(configuration, args.multica_command, ["agent", "skills", "list", operation["resource_id"]])
            observed_ids = {item.get("id", item.get("skill_id")) for item in records(postcondition, "Agent Skill list")}
            if observed_ids != set(operation["skill_ids"]):
                raise InputError("postcondition failed: Agent Skill binding differs")
        elif action in {"squad-create", "squad-update"}:
            existing = unique_named(run_multica(configuration, args.multica_command, ["squad", "list"]), operation["name"], "Squad list")
            if action == "squad-create" and existing is not None:
                raise InputError(f"STALE_PLAN: Squad already exists: {operation['name']}")
            if action == "squad-update" and (existing is None or existing.get("id") != operation["resource_id"]):
                raise InputError(f"STALE_PLAN: Squad identity changed: {operation['name']}")
            instructions = (args.manifest.parent / ".." / "squads" / f"{operation['name']}-squad.md").resolve().read_text(encoding="utf-8")
            if action == "squad-create":
                created = run_multica(
                    configuration,
                    args.multica_command,
                    [
                        "squad", "create",
                        "--name", operation["name"],
                        "--description", squad_specs[operation["name"]].description,
                        "--leader", operation["leader_id"],
                    ],
                )
                listed = run_multica(configuration, args.multica_command, ["squad", "list"])
                current = unique_named(listed, operation["name"], "Squad list")
                if current is None or not isinstance(current.get("id"), str):
                    raise InputError("postcondition failed: created Squad is absent")
                updated = run_multica(
                    configuration,
                    args.multica_command,
                    [
                        "squad", "update",
                        current["id"],
                        "--description", squad_specs[operation["name"]].description,
                        "--instructions", instructions,
                        "--leader", operation["leader_id"],
                    ],
                )
                mutation = {"create": created, "update": updated}
            else:
                mutation = run_multica(
                    configuration,
                    args.multica_command,
                    [
                        "squad", "update",
                        operation["resource_id"],
                        "--description", squad_specs[operation["name"]].description,
                        "--instructions", instructions,
                        "--leader", operation["leader_id"],
                    ],
                )
            listed = run_multica(configuration, args.multica_command, ["squad", "list"])
            current = unique_named(listed, operation["name"], "Squad list")
            if current is None or not isinstance(current.get("id"), str):
                raise InputError("postcondition failed: Squad is absent")
            postcondition = run_multica(configuration, args.multica_command, ["squad", "get", current["id"]])
        elif action in {"squad-member-add", "squad-member-role-update", "squad-member-remove"}:
            current = run_multica(configuration, args.multica_command, ["squad", "member", "list", operation["resource_id"]])
            current_records = records(current, "Squad member list")
            current_ids = {item.get("agent_id", item.get("member_id", item.get("id"))) for item in current_records}
            if action == "squad-member-add":
                if operation["agent_id"] in current_ids:
                    raise InputError("STALE_PLAN: Squad member already exists")
                command = [
                    "squad", "member", "add", operation["resource_id"],
                    "--member-id", operation["agent_id"],
                    "--type", "agent",
                    "--role", operation["squad_role"],
                ]
            elif action == "squad-member-role-update":
                if operation["agent_id"] not in current_ids:
                    raise InputError("STALE_PLAN: Squad member is absent")
                command = [
                    "squad", "member", "set-role", operation["resource_id"],
                    "--member-id", operation["agent_id"],
                    "--member-type", "agent",
                    "--role", operation["squad_role"],
                ]
            else:
                if operation["agent_id"] not in current_ids:
                    raise InputError("STALE_PLAN: Squad member is absent")
                command = [
                    "squad", "member", "remove", operation["resource_id"],
                    "--member-id", operation["agent_id"],
                    "--type", "agent",
                ]
            mutation = run_multica(configuration, args.multica_command, command)
            postcondition = run_multica(configuration, args.multica_command, ["squad", "member", "list", operation["resource_id"]])
            postcondition_records = records(postcondition, "Squad member list")
            matches = [
                item for item in postcondition_records
                if item.get("agent_id", item.get("member_id", item.get("id"))) == operation["agent_id"]
            ]
            if action == "squad-member-remove" and matches:
                raise InputError("postcondition failed: Squad member is still present")
            if action == "squad-member-add" and (
                len(matches) != 1 or matches[0].get("role") != operation["squad_role"]
            ):
                raise InputError("postcondition failed: Squad member or role is absent")
            if action == "squad-member-role-update" and (
                len(matches) != 1 or matches[0].get("role") != operation["squad_role"]
            ):
                raise InputError("postcondition failed: Squad member role differs")
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
    except (StateError, InputError, ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "error": "SERVER_APPLICATION_OPERATION_REJECTED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        if _relocation_guard is not None:
            release_relocation_mutation_guard(_relocation_guard)


if __name__ == "__main__":
    raise SystemExit(main())
