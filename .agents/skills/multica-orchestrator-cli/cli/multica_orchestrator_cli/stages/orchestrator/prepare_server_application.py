#!/usr/bin/env python3
"""Resolve a verified Foundation and typed orchestration profile into Server input."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from multica_state_bundle.bundle_store import BundleStore
from multica_state_bundle.identities import (
    DeploymentIndex,
    StagePointers,
    StateError,
    allocate_run,
    default_state_root,
    digest_bytes,
    write_resolution,
)
from multica_state_bundle.storage import atomic_json, read_private_object
from multica_orchestrator_cli.common.profile_session import resolve_profile_session
from server_application_common import load_manifest

PROFILE_SCHEMA = "multica-orchestrator.orchestration-profile.v1"


def expand_profile(profile: Mapping[str, Any], roles: list[Any]) -> dict[str, Any]:
    defaults = profile.get("defaults")
    overrides = profile.get("roles", {})
    groups = profile.get("model_groups", {})
    if not isinstance(defaults, dict) or not isinstance(overrides, dict) or not isinstance(groups, dict):
        raise StateError("orchestration profile defaults, roles, and model_groups must be objects")
    if "runtime_alias" in defaults or any(isinstance(override, dict) and "runtime_alias" in override for override in overrides.values()):
        raise StateError("runtime_alias belongs only in collaboration_runtime_alias")
    model_by_role: dict[str, str] = {}
    for model, members in groups.items():
        if not isinstance(model, str) or not isinstance(members, list):
            raise StateError("orchestration profile model_groups is invalid")
        for role in members:
            if role in model_by_role:
                raise StateError(f"Agent role is assigned to multiple model groups: {role}")
            model_by_role[role] = model
    result = {}
    for role in roles:
        override = overrides.get(role.key, {})
        if not isinstance(override, dict):
            raise StateError(f"Agent role override is invalid: {role.key}")
        merged = {**defaults, **override}
        model = merged.get("model", model_by_role.get(role.key))
        value = {
            "model": model,
            "thinking_level": merged.get("thinking_level"),
            "max_concurrent_tasks": merged.get("max_concurrent_tasks"),
            "permission_mode": merged.get("permission_mode"),
        }
        if not isinstance(model, str) or not model:
            raise StateError(f"Agent role lacks an explicit model: {role.key}")
        if value["thinking_level"] is not None and not isinstance(value["thinking_level"], str):
            raise StateError(f"Agent role thinking_level must be string or null: {role.key}")
        if value["max_concurrent_tasks"] != 1:
            raise StateError(f"Agent role max_concurrent_tasks must equal 1: {role.key}")
        if value["permission_mode"] != "private":
            raise StateError(f"Agent role permission_mode must be private: {role.key}")
        result[role.key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="authenticated Multica CLI profile")
    parser.add_argument("--workspace", help="Workspace id, name, or slug; defaults to the profile selection")
    parser.add_argument("--state-root", type=Path, default=default_state_root())
    parser.add_argument("--orchestration-profile", type=Path, required=True)
    parser.add_argument("--foundation-digest")
    parser.add_argument("--relocation-intent-digest")
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[5] / "multica-orchestrator-kick-off" / "manifests/orchestration-package.yaml")
    args = parser.parse_args()
    try:
        state_root = args.state_root.expanduser().resolve()
        session = resolve_profile_session(args.profile, args.workspace)
        deployment = DeploymentIndex(state_root).resolve(session.server_kind, session.server_ref, session.workspace_ref)
        if args.relocation_intent_digest != deployment.get("relocation_intent_digest"):
            raise StateError("relocation intent differs from the current deployment index")
        if args.foundation_digest:
            foundation_digest = args.foundation_digest
            pointer_evidence = "explicit-request"
        else:
            pointer = StagePointers(state_root).read("workspaces", deployment["workspace_key"], "foundation", "workspace-foundation")
            foundation_digest = pointer["manifest_digest"]
            pointer_evidence = pointer["_path"]
        if foundation_digest != deployment["foundation_manifest_digest"]:
            raise StateError("Foundation pointer differs from the deployment index")
        foundation_bundle = BundleStore(state_root / "bundle-store").resolve("workspace-foundation", foundation_digest)
        foundation = foundation_bundle.artifacts["workspace-foundation"]
        expected = {
            "server_kind": session.server_kind,
            "server_ref": session.server_ref,
            "workspace_ref": session.workspace_ref,
            "deployment_key": deployment["deployment_key"],
            "workspace_key": deployment["workspace_key"],
        }
        mismatches = [key for key, value in expected.items() if foundation.get(key) != value]
        if mismatches:
            raise StateError("Foundation identity differs from live profile/index: " + ", ".join(mismatches))
        profile_path = args.orchestration_profile.expanduser().resolve()
        profile = read_private_object(profile_path, PROFILE_SCHEMA, "orchestration profile")
        roles = load_manifest(args.manifest)
        collaboration_runtime_alias = profile.get("collaboration_runtime_alias")
        if not isinstance(collaboration_runtime_alias, str) or not collaboration_runtime_alias:
            raise StateError("orchestration profile lacks collaboration_runtime_alias")
        aliases = {item["alias"] for item in foundation["runtime_fleet"]["runtimes"]}
        if collaboration_runtime_alias not in aliases:
            raise StateError("collaboration Runtime alias is absent from the Foundation fleet")
        run_id, run_root = allocate_run(state_root, "orchestrator")
        input_path = run_root / "input.json"
        value = {
            "schema": "multica-orchestrator.server-application-input.v7",
            "bundle_store": {"state_root": str(state_root / "bundle-store")},
            "workspace_handoff_bundle": {"manifest_digest": foundation_digest},
            "consumer_session": {"profile": session.profile, "account_ref": session.account_ref},
            "collaboration_runtime_alias": collaboration_runtime_alias,
            "agents": expand_profile(profile, roles),
        }
        atomic_json(input_path, value)
        request = {"profile": args.profile, "workspace": args.workspace or "profile-current", "orchestration_profile_digest": digest_bytes(profile_path.read_bytes()), "foundation": args.foundation_digest or "current"}
        atomic_json(run_root / "request.json", request)
        write_resolution(run_root / "resolution.json", run_id=run_id, request=request, resolved_input=input_path, fields={
            "workspace_ref": {"source": "multica-cli", "value": session.workspace_ref},
            "deployment_index": {"source": "operator-state", "evidence": deployment["_path"], "value": deployment["_digest"]},
            "foundation_manifest_digest": {"source": "explicit" if args.foundation_digest else "cas-pointer", "evidence": pointer_evidence, "value": foundation_digest},
            "agents": {"source": "orchestration-profile", "evidence": str(profile_path), "value": request["orchestration_profile_digest"]},
            "paths": {"source": "state-layout", "value": str(run_root)},
        })
        print(json.dumps({"ok": True, "run_id": run_id, "run_root": str(run_root), "input": str(input_path), "resolution": str(run_root / "resolution.json"), "foundation_manifest_digest": foundation_digest}, sort_keys=True))
        return 0
    except (StateError, OSError, KeyError, TypeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": "SERVER_PREPARE_FAILED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
