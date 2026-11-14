#!/usr/bin/env python3
"""Emit and publish a parent-linked ServerOrchestrationRef.v10 bundle."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from multica_state_bundle.bundle_store import BundleStore
from multica_state_bundle.claims import acquire_claim, release_claim
from multica_state_bundle.errors import StateBundleError
from multica_state_bundle.handoff import BundleError, canonical_json as artifact_json, write_bundle
from multica_state_bundle.identities import (
    DeploymentIndex,
    StateError,
    StagePointers,
    canonical_json,
    digest_bytes,
)
from multica_state_bundle.namespaces import create_workspace_namespace
from multica_state_bundle.relocations import hold_relocation_mutation_guard, release_relocation_mutation_guard
from server_application_common import InputError, load_input, load_manifest, read_json, readback_snapshot_digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--application-input", type=Path, required=True)
    parser.add_argument("--verification-report", type=Path, required=True)
    parser.add_argument("--skill-integrity-report", type=Path, required=True)
    parser.add_argument("--skill-integrity-lock", type=Path, required=True)
    parser.add_argument("--readback-dir", type=Path, required=True)
    parser.add_argument("--package-version", required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--output-bundle", type=Path)
    parser.add_argument("--pointer-state-root", type=Path, required=True)
    args = parser.parse_args()
    temporary: Path | None = None
    _relocation_guard: int | None = None
    mutation_claim = None
    mutation_namespace = None
    claim_outcome = "FAILED"
    try:
        manifest_lines = args.manifest.read_text(encoding="utf-8").splitlines()
        package_versions = [
            line.removeprefix('  version: "').removesuffix('"')
            for line in manifest_lines
            if line.startswith('  version: "') and line.endswith('"')
        ]
        if len(package_versions) != 1 or args.package_version != package_versions[0]:
            raise InputError("PACKAGE_VERSION_MISMATCH: package version must equal the manifest")
        roles = load_manifest(args.manifest)
        configuration = load_input(args.application_input, roles)
        verification = read_json(args.verification_report, "Server verification report")
        integrity = read_json(args.skill_integrity_report, "Skill integrity report")
        manifest_digest = digest_bytes(args.manifest.read_bytes())
        application_digest = digest_bytes(args.application_input.read_bytes())
        snapshot_digest = readback_snapshot_digest(
            args.readback_dir,
            workspace_id=configuration["workspace_id"],
            runtime_refs=configuration["runtime_refs"],
            daemon_refs=configuration["daemon_refs"],
        )
        expected_verification = {
            "schema": "multica-orchestrator.server-verification.v3",
            "manifest_digest": manifest_digest,
            "application_input_digest": application_digest,
            "foundation_manifest_digest": configuration["foundation_bundle_manifest_digest"],
            "readback_snapshot_digest": snapshot_digest,
            "workspace_ref": configuration["workspace_id"],
            "runtime_refs": configuration["runtime_refs"],
            "daemon_refs": configuration["daemon_refs"],
        }
        if (
            not isinstance(verification, dict)
            or not verification.get("ok")
            or any(verification.get(key) != value for key, value in expected_verification.items())
        ):
            raise InputError("STALE_SERVER_VERIFICATION: verification report does not match current inputs")
        expected_integrity = {
            "schema": "multica-orchestrator.skill-integrity-report.v1",
            "manifest_digest": manifest_digest,
            "lock_digest": digest_bytes(args.skill_integrity_lock.read_bytes()),
            "readback_snapshot_digest": snapshot_digest,
        }
        if (
            not isinstance(integrity, dict)
            or not integrity.get("ok")
            or any(integrity.get(key) != value for key, value in expected_integrity.items())
        ):
            raise InputError("STALE_SKILL_INTEGRITY_REPORT: integrity report does not match current inputs")
        role_map = verification.get("agent_ids")
        if not isinstance(role_map, dict) or set(role_map) != {role.key for role in roles}:
            raise InputError("verification report lacks exact role map")
        verification_spec = verification.get("verification_spec")
        if not isinstance(verification_spec, dict) or verification_spec.get("schema") not in {
            "multica-orchestrator.server-verification-spec.v3",
        }:
            raise InputError("verification report lacks a supported Server verification specification")
        produced_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        spec_bytes = artifact_json(verification_spec)
        agent_configuration = verification_spec["agents"]
        placements = {
            role: value["runtime_alias"]
            for role, value in sorted(agent_configuration.items())
        }
        squad_configuration = verification_spec["squads"]
        runtime_fleet = configuration["foundation"]["runtime_fleet"]
        skill_digest = digest_bytes(canonical_json(integrity))
        reissue_body = {
            "schema": "multica-orchestrator.server-reissue-spec.v1",
            "package": {
                "id": "multica-super-individual-orchestration",
                "version": args.package_version,
                "manifest_digest": manifest_digest,
            },
            "collaboration_runtime_alias": configuration["collaboration_runtime_alias"],
            "agent_configuration": agent_configuration,
            "skill_bindings": verification_spec["skills"],
            "squads": squad_configuration,
        }
        reissue_spec = {
            **reissue_body,
            "spec_digest": digest_bytes(canonical_json(reissue_body)),
        }
        reissue_bytes = artifact_json(reissue_spec)
        payload = {
            "schema": "multica-orchestrator.server-orchestration-ref.v10",
            "workspace_foundation_ref": {
                "bundle_manifest_digest": configuration["foundation_bundle_manifest_digest"],
                "artifact_digest": configuration["foundation_digest"],
            },
            "server_ref": configuration["server_ref"],
            "server_kind": configuration["server_kind"],
            "deployment_key": configuration["deployment_key"],
            "workspace_key": configuration["workspace_key"],
            "relocation_intent_digest": configuration["relocation_intent_digest"],
            "producer_session": {
                "profile_ref": configuration["profile"],
                "authenticated_account_ref": configuration["account_ref"],
            },
            "workspace_ref": configuration["workspace_id"],
            "package": {
                "id": "multica-super-individual-orchestration",
                "version": args.package_version,
                "manifest_digest": manifest_digest,
                "contract_version": "10",
            },
            "runtime_fleet": {
                "membership_digest": runtime_fleet["membership_digest"],
                "placements_digest": digest_bytes(canonical_json(placements)),
                "runtimes": runtime_fleet["runtimes"],
            },
            "skills": {
                "package_digest": skill_digest,
                "bindings_digest": digest_bytes(canonical_json(verification_spec["skills"])),
                "integrity_report_digest": digest_bytes(args.skill_integrity_report.read_bytes()),
            },
            "agents": {
                "role_map_digest": digest_bytes(canonical_json(role_map)),
                "configuration_digest": digest_bytes(canonical_json(agent_configuration)),
                "placement_digest": digest_bytes(canonical_json(placements)),
                "count": 16,
                "collaboration_runtime_alias": configuration["collaboration_runtime_alias"],
            },
            "squads": {
                "configuration_digest": digest_bytes(canonical_json(squad_configuration)),
                "membership_digest": digest_bytes(canonical_json({
                    name: value["member_refs"] for name, value in sorted(squad_configuration.items())
                })),
                "names": ["feature", "fix"],
            },
            "orchestrator_controls": {
                "skill_integrity": "VERIFIED",
                "permission_readback": "VERIFIED",
                "concurrency_readback": "VERIFIED",
                "runtime_placement_readback": "VERIFIED",
            },
            "verification": {
                "readback_snapshot_digest": snapshot_digest,
                "server_verification_report_digest": digest_bytes(args.verification_report.read_bytes()),
                "server_verification_spec_digest": digest_bytes(spec_bytes),
                "skill_integrity_report_digest": digest_bytes(args.skill_integrity_report.read_bytes()),
                "application_input_digest": application_digest,
            },
            "desired_state": {
                "reissue_spec_digest": digest_bytes(reissue_bytes),
                "agent_configuration_digest": digest_bytes(canonical_json(agent_configuration)),
                "skill_bindings_digest": digest_bytes(canonical_json(verification_spec["skills"])),
                "squad_configuration_digest": digest_bytes(canonical_json(squad_configuration)),
            },
            "project_binding_contract": {
                "required_skill": "multica-orchestrator-nail-down",
                "minimum_contract_version": "12",
            },
            "dispatch_contract": {
                "required_skill": "multica-orchestrator-dispatch",
                "minimum_contract_version": "1",
            },
            "state": "ORCHESTRATOR_LAYER_VERIFIED",
            "dispatch_state": "BLOCKED_PROJECT_BINDING",
            "produced_at": produced_at,
        }
        operator_state_root = Path(configuration["bundle_store"]["state_root"]).resolve().parent
        if (
            args.pointer_state_root.expanduser().resolve() != operator_state_root
            or args.state_root.expanduser().resolve() != operator_state_root / "bundle-store"
        ):
            raise InputError("Server publish roots differ from the input-bound operator state")
        _relocation_guard = hold_relocation_mutation_guard(
            operator_state_root,
            configuration["deployment_key"],
            configuration.get("relocation_intent_digest"),
            kind="server-publish",
            subject=configuration["workspace_id"],
        )
        mutation_namespace = create_workspace_namespace(
            state_root=operator_state_root,
            workspace_key_value=configuration["workspace_key"],
        )
        mutation_claim = acquire_claim(mutation_namespace, "server-publish")
        if args.output_bundle is None:
            temporary = Path(tempfile.mkdtemp(prefix="server-bundle-"))
            output = temporary / "bundle"
        else:
            output = args.output_bundle
        bundle = write_bundle(
            output,
            stage="server-orchestration",
            parents=[{
                "stage": "workspace-foundation",
                "manifest_digest": configuration["foundation_bundle_manifest_digest"],
            }],
            artifact_bytes={
                "server-orchestration": artifact_json(payload),
                "server-verification-spec": spec_bytes,
                "server-reissue-spec": reissue_bytes,
            },
            produced_at=produced_at,
        )
        stored = BundleStore(args.state_root).publish(
            bundle.root,
            expected_stage="server-orchestration",
            expected_manifest_digest=bundle.manifest_digest,
        )
        pointer_path = None
        deployment_index_path = None
        subject_key = configuration["workspace_key"]
        pointer_path = StagePointers(args.pointer_state_root).write(
            "workspaces",
            subject_key,
            "server",
            "server-orchestration",
            stored.manifest_digest,
            parent_manifest_digest=configuration["foundation_bundle_manifest_digest"],
        )
        deployment_index_path = DeploymentIndex(args.pointer_state_root).publish_server(
            configuration["deployment_key"],
            stored.manifest_digest,
        )
        claim_outcome = "PUBLISHED"
        print(json.dumps({
            "ok": True,
            "bundle": str(stored.root),
            "export_bundle": str(args.output_bundle) if args.output_bundle else None,
            "manifest_digest": stored.manifest_digest,
            "server_artifact_digest": stored.manifest["artifacts"]["server-orchestration"]["digest"],
            "verification_spec_digest": stored.manifest["artifacts"]["server-verification-spec"]["digest"],
            "reissue_spec_digest": stored.manifest["artifacts"]["server-reissue-spec"]["digest"],
            "pointer": str(pointer_path) if pointer_path else None,
            "deployment_index": str(deployment_index_path) if deployment_index_path else None,
        }, sort_keys=True))
        return 0
    except (StateError, StateBundleError, BundleError, InputError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "error": "SERVER_HANDOFF_REJECTED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        if _relocation_guard is not None:
            release_relocation_mutation_guard(_relocation_guard)
        if mutation_claim is not None and mutation_namespace is not None:
            release_claim(mutation_namespace, mutation_claim, claim_outcome)
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
