#!/usr/bin/env python3
"""Resolve an ACTIVE Project closure and selected optional targets into MigrationInput.v5."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from multica_state_bundle.bundle_store import BundleStore
from multica_state_bundle.identities import DeploymentIndex, StagePointers, StateError, allocate_run, atomic_json, default_state_root, digest_bytes, project_key, read_private_object, repository_identity, write_resolution
from multica_orchestrator_cli.common.profile_session import resolve_profile_session
from multica_orchestrator_cli.common.dispatch_runtime import read_active_release, read_runtime_binding

INVENTORY_SCHEMA = "multica-orchestrator.runtime-target-inventory.v1"


def run(command: list[str]) -> str:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise StateError((completed.stderr or completed.stdout).strip() or f"command failed: {command[0]}")
    return completed.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="authenticated coordinator Multica profile")
    parser.add_argument("--workspace", help="Workspace id, name, or slug; defaults to the profile selection")
    parser.add_argument("--state-root", type=Path, default=default_state_root())
    parser.add_argument("--target-inventory", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--project-subpath", default=".")
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--relocation-intent-digest")
    args = parser.parse_args()
    try:
        state_root = args.state_root.expanduser().resolve()
        session = resolve_profile_session(args.profile, args.workspace)
        deployment = DeploymentIndex(state_root).resolve(session.server_kind, session.server_ref, session.workspace_ref)
        if args.relocation_intent_digest != deployment.get("relocation_intent_digest"):
            raise StateError("relocation intent differs from the current deployment index")
        root = Path(run(["git", "-C", str(args.repository_root), "rev-parse", "--show-toplevel"])).resolve()
        origin = run(["git", "-C", str(root), "config", "--get", "remote.origin.url"])
        identity = repository_identity(origin)
        project_subject = project_key(deployment["workspace_key"], identity, args.project_subpath)
        pointer = StagePointers(state_root).read_candidate(project_subject)
        indexed_project = deployment.get("projects", {}).get(project_subject)
        if not isinstance(indexed_project, dict) or indexed_project.get("project_manifest_digest") != pointer["project_bundle_manifest_digest"] or indexed_project.get("candidate_digest") != pointer["release_candidate_digest"]:
            raise StateError("Project candidate pointer differs from the deployment index")
        candidate = json.loads(Path(pointer["release_candidate_path"]).read_text(encoding="utf-8"))
        if candidate.get("schema") != "multica-orchestrator.project-release-candidate.v8":
            raise StateError("current candidate schema is unsupported; reissue the Project binding")
        if candidate.get("repository_identity") != identity or candidate.get("project_subpath") != args.project_subpath:
            raise StateError("current candidate repository identity or subpath differs")
        store = BundleStore(state_root / "bundle-store")
        project_bundle = store.resolve("project-binding", pointer["project_bundle_manifest_digest"])
        closure = store.closure("project-binding", project_bundle.manifest_digest)
        if [item.stage for item in closure] != ["workspace-foundation", "server-orchestration", "project-binding"]:
            raise StateError("current candidate bundle closure is incomplete")
        foundation = closure[0].artifacts["workspace-foundation"]
        server = closure[1].artifacts["server-orchestration"]
        project = closure[2].artifacts["project-binding"]
        for artifact in (foundation, server, project):
            if artifact.get("deployment_key") != deployment["deployment_key"] or artifact.get("workspace_ref") != session.workspace_ref:
                raise StateError("Project closure identity differs from the deployment index")
        runtime_policy = project_bundle.artifacts["runtime-target-policy"]
        required_aliases = list(candidate["required_runtime_aliases"])
        if len(required_aliases) != 1:
            raise StateError("Project candidate must name exactly one primary Runtime")
        primary_alias = required_aliases[0]
        active = read_active_release(state_root / "bundle-store", project["project_key"])
        if active["release"]["release_candidate_digest"] != pointer["release_candidate_digest"]:
            raise StateError("current candidate does not match the ACTIVE Project release")
        binding = read_runtime_binding(session.server_kind, session.server_ref, session.workspace_ref, project["project_ref"])
        if binding["runtime_alias"] != primary_alias:
            raise StateError("primary Runtime binding differs from the Project policy")
        optional_aliases = {item["runtime_alias"] for item in runtime_policy["optional_runtimes"]}
        aliases = args.target or sorted(optional_aliases)
        if not aliases:
            raise StateError("migration requires one or more optional Runtime aliases")
        if primary_alias in aliases:
            raise StateError("migration must not target the primary Runtime alias")
        if len(set(aliases)) != len(aliases) or not set(aliases) <= optional_aliases:
            raise StateError("migration targets must be unique optional Runtime aliases")
        inventory_path = args.target_inventory.expanduser().resolve()
        inventory = read_private_object(inventory_path, INVENTORY_SCHEMA, "Runtime target inventory")
        repository_name = identity.split("/", 1)[1]
        owner = identity.split(":", 1)[1].split("/", 1)[0]
        run_id, run_root = allocate_run(state_root, "migrate", repository_name)
        targets = []
        for alias in aliases:
            target = inventory["targets"].get(alias)
            if not isinstance(target, dict):
                raise StateError(f"Runtime target is absent from inventory: {alias}")
            for field in ("ssh_config_host", "consumer_profile", "target_state_root", "repository_root_template"):
                if not isinstance(target.get(field), str) or not target[field]:
                    raise StateError(f"Runtime target {alias} lacks {field}")
            target_state = Path(target["target_state_root"])
            repository_root = target["repository_root_template"].format(repository=repository_name, owner=owner, alias=alias)
            remote_receipt = target_state / "receipts" / repository_name / f"generation-{candidate['generation']}.json"
            targets.append({"runtime_alias": alias, "ssh_config_host": target["ssh_config_host"], "profile": target["consumer_profile"], "account_ref": target.get("account_ref", session.account_ref), "state_root": str(target_state), "repository_root": repository_root, "remote_receipt_path": str(remote_receipt), "coordinator_receipt_path": str(run_root / "receipts" / f"{alias}.json")})
        value = {
            "schema": "multica-orchestrator-migrate.input.v5",
            "source": {"state_root": str(state_root / "bundle-store"), "operator_state_root": str(state_root), "project_bundle_manifest_digest": pointer["project_bundle_manifest_digest"], "release_candidate_path": pointer["release_candidate_path"], "release_candidate_digest": pointer["release_candidate_digest"], "primary_runtime_alias": primary_alias, "source_active_release_digest": active["release_digest"]},
            "server": {"kind": server["server_kind"], "ref": server["server_ref"], "workspace_ref": server["workspace_ref"], "deployment_key": server["deployment_key"]},
            "repository": {"url": origin, "project_subpath": candidate["project_subpath"]},
            "targets": targets,
        }
        input_path = run_root / "input.json"
        atomic_json(input_path, value)
        request = {"profile": args.profile, "workspace": args.workspace or "profile-current", "repository": repository_name, "candidate": "current", "targets": aliases, "target_inventory_digest": digest_bytes(inventory_path.read_bytes())}
        atomic_json(run_root / "request.json", request)
        write_resolution(run_root / "resolution.json", run_id=run_id, request=request, resolved_input=input_path, fields={
            "deployment_index": {"source": "operator-state", "evidence": deployment["_path"], "value": deployment["_digest"]},
            "candidate": {"source": "candidate-pointer", "evidence": pointer["_path"], "value": pointer["release_candidate_digest"]},
            "bundle_closure": {"source": "cas", "value": [item.manifest_digest for item in closure]},
            "repository": {"source": "candidate-and-git", "value": {"identity": identity}},
            "targets": {"source": "candidate-and-runtime-target-inventory", "evidence": str(inventory_path), "value": aliases},
            "paths": {"source": "state-layout", "value": str(run_root)},
        })
        print(json.dumps({"ok": True, "run_id": run_id, "run_root": str(run_root), "input": str(input_path), "resolution": str(run_root / "resolution.json"), "candidate_digest": pointer["release_candidate_digest"], "targets": aliases}, sort_keys=True))
        return 0
    except (StateError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": "MIGRATION_PREPARE_FAILED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
