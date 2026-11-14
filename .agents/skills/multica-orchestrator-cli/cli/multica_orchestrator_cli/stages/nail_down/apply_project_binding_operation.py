#!/usr/bin/env python3
"""Apply one authorized Project operation with stale-plan and postcondition checks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping
from binding_common import InputError, PLAN_SCHEMA, load_input, load_server_bundle, read_json, records, run_multica
from multica_orchestrator_cli.common.runtime_activation import (
    RuntimeActivationError,
    ensure_local_directory,
    select_local_directory_resource,
)
from multica_state_bundle.identities import StateError, canonical_json, digest_bytes, project_key, repository_identity
from multica_state_bundle.relocations import hold_relocation_mutation_guard, release_relocation_mutation_guard
from multica_state_bundle.storage import atomic_bytes


def unique(payload: Any, predicate: Callable[[Mapping[str, Any]], bool], label: str) -> Mapping[str, Any] | None:
    matches = [item for item in records(payload, label) if predicate(item)]
    if len(matches) > 1:
        raise InputError(f"STALE_PLAN: {label} contains multiple matching resources")
    return matches[0] if matches else None



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--input", type=Path, required=True)
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
        plan = read_json(args.plan, "project binding plan")
        if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA:
            raise InputError("invalid project binding plan schema")
        unsigned = dict(plan)
        observed = unsigned.pop("plan_digest", None)
        actual = digest_bytes(canonical_json(unsigned))
        if observed != actual or args.plan_digest != actual:
            raise InputError("plan digest does not match current plan")
        if plan.get("input_digest") != digest_bytes(args.input.read_bytes()):
            raise InputError("project binding input changed after the reviewed plan was generated")
        _, handoff_digest, bundle = load_server_bundle(configuration)
        if plan.get("orchestrator_bundle_manifest_digest") != bundle.manifest_digest or plan.get("server_orchestration_ref") != handoff_digest:
            raise InputError("orchestrator handoff bundle changed after the reviewed plan was generated")
        expected_files = plan.get("repository_file_digests")
        if not isinstance(expected_files, dict):
            raise InputError("project binding plan lacks repository file observations")
        root = Path(plan["repository_root"]).resolve()
        current_files = {}
        for relative in expected_files:
            path = (root / relative).resolve()
            try:
                path.relative_to(root)
            except ValueError as error:
                raise InputError("repository observation escapes repository root") from error
            current_files[relative] = digest_bytes(path.read_bytes()) if path.is_file() else None
        primary_observation = plan.get("primary_local_directory")
        current_primary = primary_observation
        if configuration["project"].get("project_ref"):
            resources = run_multica(
                configuration, args.multica_command,
                ["project", "resource", "list", configuration["project"]["project_ref"]],
            )
            current_primary = select_local_directory_resource(
                resources,
                root=configuration["repository"]["root"],
                daemon_ref=configuration["primary_runtime"]["daemon_ref"],
            )
        observed_state = {
            "input_digest": digest_bytes(args.input.read_bytes()),
            "orchestrator_bundle_manifest_digest": bundle.manifest_digest,
            "repository_files": current_files,
            "primary_local_directory": current_primary,
        }
        if (
            expected_files != current_files
            or plan.get("primary_local_directory") != current_primary
            or plan.get("observed_state_digest") != digest_bytes(canonical_json(observed_state))
        ):
            raise InputError("repository or primary Runtime observed state changed after the reviewed plan was generated")
        if plan.get("blockers"):
            raise InputError("plan has unresolved server-layer blockers")
        server = configuration["server"]
        server_handoff = bundle.artifacts["server-orchestration"]
        _relocation_guard = hold_relocation_mutation_guard(
            Path(configuration["bundle_store"]["state_root"]).parent,
            server["deployment_key"],
            server_handoff.get("relocation_intent_digest"),
            kind="project-apply",
            subject=project_key(
                configuration["server"]["workspace_key"],
                repository_identity(configuration["repository"]["url"]),
                configuration["repository"]["project_subpath"],
            ),
        )
        matches = [item for item in plan.get("operations", []) if isinstance(item, dict) and item.get("id") == args.operation]
        if len(matches) != 1:
            raise InputError("operation is not unique in plan")
        operation = matches[0]
        action = operation.get("action")
        mutation: Any
        postcondition: Any
        if action == "repo-add":
            before = run_multica(configuration, args.multica_command, ["repo", "list"])
            if unique(before, lambda item: item.get("url", item.get("repository_url")) == operation["url"], "repository list") is not None:
                raise InputError("STALE_PLAN: repository is already registered")
            mutation = run_multica(configuration, args.multica_command, ["repo", "add", operation["url"]])
            after = run_multica(configuration, args.multica_command, ["repo", "list"])
            postcondition = unique(after, lambda item: item.get("url", item.get("repository_url")) == operation["url"], "repository list")
            if postcondition is None:
                raise InputError("postcondition failed: repository registration is absent")
        elif action == "project-create":
            before = run_multica(configuration, args.multica_command, ["project", "list"])
            if unique(before, lambda item: item.get("name", item.get("title")) == operation["name"], "project list") is not None:
                raise InputError("STALE_PLAN: Project already exists")
            command = ["project", "create", "--title", operation["name"], "--repo", operation["url"]]
            if operation.get("description"):
                command.extend(["--description", operation["description"]])
            mutation = run_multica(configuration, args.multica_command, command)
            after = run_multica(configuration, args.multica_command, ["project", "list"])
            postcondition = unique(after, lambda item: item.get("name", item.get("title")) == operation["name"], "project list")
            if postcondition is None:
                raise InputError("postcondition failed: Project is absent")
        elif action == "project-resource-add":
            if not operation.get("project_ref"):
                raise InputError("project-resource-add requires a current project_ref; re-inspect and re-plan")
            before = run_multica(configuration, args.multica_command, ["project", "resource", "list", operation["project_ref"]])
            predicate = lambda item: item.get("url", item.get("repository_url")) == operation["url"] and item.get("type", item.get("resource_type")) == "github_repo"
            if unique(before, predicate, "Project resource list") is not None:
                raise InputError("STALE_PLAN: GitHub repository resource already exists")
            mutation = run_multica(configuration, args.multica_command, ["project", "resource", "add", operation["project_ref"], "--type", "github_repo", "--url", operation["url"]])
            after = run_multica(configuration, args.multica_command, ["project", "resource", "list", operation["project_ref"]])
            postcondition = unique(after, predicate, "Project resource list")
            if postcondition is None:
                raise InputError("postcondition failed: GitHub repository resource is absent")
        elif action == "write-portable-config":
            root = Path(plan["repository_root"]).resolve()
            destination = (root / operation["destination"]).resolve()
            try:
                destination.relative_to(root)
            except ValueError as error:
                raise InputError("binding destination escapes repository root") from error
            current = destination.read_bytes() if destination.is_file() else None
            current_digest = digest_bytes(current) if current is not None else None
            if current_digest != operation.get("before_digest"):
                raise InputError("STALE_PLAN: repository configuration changed")
            content = operation["content"].encode("utf-8")
            if digest_bytes(content) != operation["content_digest"]:
                raise InputError("binding content digest mismatch")
            atomic_bytes(destination, content)
            mutation = {"path": str(destination), "digest": digest_bytes(content)}
            postcondition = {"path": str(destination), "digest": digest_bytes(destination.read_bytes())}
            if postcondition["digest"] != operation["content_digest"]:
                raise InputError("postcondition failed: repository configuration digest differs")
        elif action == "bind-primary-local-directory":
            project_ref = operation.get("project_ref")
            if not isinstance(project_ref, str) or not project_ref:
                raise InputError("bind-primary-local-directory requires an existing Project; reprepare and replan")
            resources = run_multica(configuration, args.multica_command, ["project", "resource", "list", project_ref])
            fresh = select_local_directory_resource(
                resources,
                root=str(operation["root"]),
                daemon_ref=str(operation["daemon_ref"]),
            )
            if fresh != operation.get("before"):
                raise InputError("STALE_PLAN: primary local-directory observation changed")
            result = ensure_local_directory(
                resources_before=resources,
                project_ref=project_ref,
                root=str(operation["root"]),
                daemon_ref=str(operation["daemon_ref"]),
                run_multica=lambda command: run_multica(configuration, args.multica_command, list(command)),
            )
            mutation = {"state": result["state"]}
            postcondition = result["resource"]
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
    except (StateError, InputError, RuntimeActivationError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "error": "PROJECT_BINDING_OPERATION_REJECTED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        if _relocation_guard is not None:
            release_relocation_mutation_guard(_relocation_guard)


if __name__ == "__main__":
    raise SystemExit(main())
