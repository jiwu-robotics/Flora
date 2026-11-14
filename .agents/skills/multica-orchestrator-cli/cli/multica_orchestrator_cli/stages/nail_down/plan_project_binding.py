#!/usr/bin/env python3
"""Create a deterministic, read-only project binding plan."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from binding_common import InputError, PLAN_SCHEMA, load_input, load_server_bundle, server_handoff_errors, validate_binding_manifest, validate_portable_config
from multica_state_bundle.identities import canonical_json, digest_bytes
from multica_state_bundle.storage import atomic_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--binding-content", type=Path, required=True)
    parser.add_argument("--issue-tracker-content", type=Path, required=True)
    parser.add_argument("--triage-mapping-content", type=Path, required=True)
    parser.add_argument("--domain-content", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    try:
        configuration = load_input(args.input)
        handoff, handoff_digest, bundle = load_server_bundle(configuration)
        blockers = server_handoff_errors(configuration, handoff, bundle)
        validate_binding_manifest(args.binding_content, configuration, handoff)
        portable_contents = {
            ".multica/agents/issue-tracker.md": args.issue_tracker_content,
            ".multica/agents/triage-mapping.md": args.triage_mapping_content,
            ".multica/agents/domain.md": args.domain_content,
        }
        for destination_name, source in portable_contents.items():
            validate_portable_config(source, destination_name)
        repository = configuration["repository"]
        project = configuration["project"]
        operations: list[dict[str, object]] = []
        if not repository["registered"]:
            operations.append({"id": "repository/register", "action": "repo-add", "url": repository["url"]})
        if not project["exists"]:
            operations.append({"id": "project/create", "action": "project-create", "name": project["name"], "description": project.get("description", ""), "url": repository["url"]})
        if project["exists"] and not repository["project_has_resource"]:
            operations.append({"id": "project/repository-resource", "action": "project-resource-add", "project_ref": project.get("project_ref"), "url": repository["url"]})
        portable_contents[".multica/agents/orchestrator-binding.yaml"] = args.binding_content
        observed_files: dict[str, str | None] = {}
        for relative, source in portable_contents.items():
            content = source.read_bytes()
            destination = Path(repository["root"]).resolve() / relative
            current = destination.read_bytes() if destination.is_file() else None
            before_digest = digest_bytes(current) if current is not None else None
            observed_files[relative] = before_digest
            if current != content:
                operation_name = Path(relative).stem
                operations.append({"id": f"repository/write-{operation_name}", "action": "write-portable-config", "destination": relative, "content": content.decode("utf-8"), "content_digest": digest_bytes(content), "before_digest": before_digest})
        local_directory = configuration["local_directory_observation"]
        local_directory_state = local_directory["state"]
        if local_directory_state in {"AMBIGUOUS", "CONFLICTING"}:
            blockers.append(f"PRIMARY_LOCAL_DIRECTORY_{local_directory_state}")
        elif local_directory_state in {"ABSENT", "EXACT_WRONG_MODE"}:
            operations.append({
                "id": "project/bind-primary-local-directory",
                "action": "bind-primary-local-directory",
                "project_ref": configuration["project"].get("project_ref"),
                "root": repository["root"],
                "daemon_ref": configuration["primary_runtime"]["daemon_ref"],
                "before": local_directory,
            })
        observed_state = {
            "input_digest": digest_bytes(args.input.read_bytes()),
            "orchestrator_bundle_manifest_digest": bundle.manifest_digest,
            "repository_files": observed_files,
            "primary_local_directory": local_directory,
        }
        payload = {
            "schema": PLAN_SCHEMA,
            "input_digest": digest_bytes(args.input.read_bytes()),
            "observed_state_digest": digest_bytes(canonical_json(observed_state)),
            "orchestrator_bundle_manifest_digest": bundle.manifest_digest,
            "server_orchestration_ref": handoff_digest,
            "workspace_ref": configuration["server"]["workspace_ref"],
            "repository_root": repository["root"],
            "repository_file_digests": observed_files,
            "primary_local_directory": local_directory,
            "operations": operations,
            "manual_actions": [],
            "blockers": sorted(set(blockers)),
        }
        payload["plan_digest"] = digest_bytes(canonical_json(payload))
        atomic_bytes(args.plan, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        print(payload["plan_digest"])
        return 0
    except (InputError, OSError, UnicodeDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
