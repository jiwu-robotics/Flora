#!/usr/bin/env python3
"""Materialize a provenance lock from deterministic archives and live Skill readbacks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from server_application_common import InputError, load_manifest, records
from multica_state_bundle.identities import digest_bytes
from multica_state_bundle.storage import atomic_json
from verify_skill_integrity import canonical_content_digest, read_json, workspace_entries


def unique_named(payload: Any, name: str, label: str) -> dict[str, Any]:
    matches = [item for item in records(payload, label) if item.get("name") == name]
    if len(matches) != 1 or not isinstance(matches[0].get("id"), str) or not matches[0]["id"]:
        raise InputError(f"{label} must contain exactly one named resource: {name}")
    return dict(matches[0])


def source_record(item: dict[str, Any]) -> dict[str, str]:
    content_digest = item.get("content_digest")
    revision = item.get("source_revision")
    source_path = item.get("source_path")
    if not isinstance(content_digest, str) or not content_digest.startswith("sha256:"):
        raise InputError("archive plan Skill has invalid content digest")
    if not isinstance(revision, str) or not isinstance(source_path, str):
        raise InputError("archive plan Skill has invalid provenance")
    if revision.startswith("git:"):
        return {
            "relative_path": source_path,
            "revision": revision,
            "content_sha256": content_digest,
        }
    if revision == f"content:{content_digest}":
        return {
            "revision": revision,
            "content_sha256": content_digest,
        }
    raise InputError("archive plan Skill has unsupported provenance")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-plan", type=Path, required=True)
    parser.add_argument("--skill-list-readback", type=Path, required=True)
    parser.add_argument("--skill-readback-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--agent-list-readback", type=Path, required=True)
    parser.add_argument("--agent-readback-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        roles = load_manifest(arguments.manifest)
        if len(roles) != 16 or len({role.key for role in roles}) != 16:
            raise InputError("manifest must declare exactly sixteen unique Agent roles")
        plan = read_json(arguments.archive_plan, "Skill archive plan")
        if not isinstance(plan, dict) or plan.get("schema") != "skill-archive-plan/v1":
            raise InputError("invalid Skill archive plan")
        manifest_digest = plan.get("manifest_sha256")
        if manifest_digest != digest_bytes(arguments.manifest.read_bytes()):
            raise InputError("Skill archive plan manifest digest differs from the manifest")
        skills = plan.get("skills")
        if not isinstance(skills, list):
            raise InputError("Skill archive plan is incomplete")
        listed = read_json(arguments.skill_list_readback, "Skill list readback")
        lock_skills: list[dict[str, Any]] = []
        for item in skills:
            if not isinstance(item, dict):
                raise InputError("Skill archive plan contains an invalid Skill")
            name = item.get("name")
            archive_path = item.get("archive_path")
            archive_digest = item.get("archive_raw_digest")
            content_digest = item.get("content_digest")
            binding = item.get("binding")
            if not all(isinstance(value, str) for value in (name, archive_path, archive_digest, content_digest, binding)):
                raise InputError("Skill archive plan Skill is incomplete")
            archive = arguments.archive_plan.parent / archive_path
            if not archive.is_file() or digest_bytes(archive.read_bytes()) != archive_digest:
                raise InputError(f"Skill archive digest mismatch: {name}")
            workspace = unique_named(listed, name, "Skill list")
            payload = read_json(arguments.skill_readback_dir / f"{name}.json", f"Skill readback for {name}")
            workspace_id, workspace_name, entries = workspace_entries(payload, f"Skill readback for {name}")
            if workspace_id != workspace["id"] or workspace_name != name:
                raise InputError(f"Skill workspace readback identity mismatch: {name}")
            workspace_digest = canonical_content_digest(entries)
            if workspace_digest != content_digest:
                raise InputError(f"Skill workspace content differs from archive: {name}")
            lock_skills.append({
                "name": name,
                "binding": binding,
                "source": source_record(item),
                "archive": {
                    "relative_path": archive_path,
                    "sha256": archive_digest,
                    "content_sha256": content_digest,
                },
                "workspace": {
                    "id": workspace_id,
                    "content_sha256": workspace_digest,
                },
            })
        agent_list = read_json(arguments.agent_list_readback, "Agent list readback")
        lock_agents: list[dict[str, str]] = []
        for role in sorted(roles, key=lambda value: value.key):
            listed_agent = unique_named(agent_list, role.key, "Agent list")
            detail = read_json(
                arguments.agent_readback_dir / f"{role.key}.json",
                f"Agent readback for {role.key}",
            )
            if not isinstance(detail, dict):
                raise InputError(f"Agent readback must be an object: {role.key}")
            if detail.get("id") != listed_agent["id"] or detail.get("name") != role.key:
                raise InputError(f"Agent readback identity mismatch: {role.key}")
            lock_agents.append({"role_key": role.key, "id": listed_agent["id"]})
        atomic_json(arguments.output, {
            "schema": "skill-integrity-lock/v1",
            "manifest_sha256": manifest_digest,
            "skills": lock_skills,
            "agents": lock_agents,
        })
        print(f"materialized integrity lock for {len(lock_skills)} Skills and {len(lock_agents)} Agents")
        return 0
    except (InputError, OSError, TypeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
