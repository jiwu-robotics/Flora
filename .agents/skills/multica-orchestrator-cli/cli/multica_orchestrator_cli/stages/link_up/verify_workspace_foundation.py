#!/usr/bin/env python3
"""Verify Workspace Foundation state and publish a Runtime-fleet bundle."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from multica_state_bundle.bundle_store import BundleStore
from multica_state_bundle.claims import acquire_claim, release_claim
from foundation_common import (
    OUTPUT_SCHEMA,
    InputError,
    foundation_blockers,
    load_input,
    readback_snapshot_digest,
)
from multica_state_bundle.identities import (
    DeploymentIndex,
    StateError,
    StagePointers,
    bootstrap_deployment_key,
    canonical_json,
    digest_bytes,
    utc_now,
    workspace_key,
)
from multica_state_bundle.handoff import BundleError, canonical_json as artifact_json, write_bundle
from multica_state_bundle.errors import StateBundleError
from multica_state_bundle.identities import DeploymentIndex, StateError, StagePointers, bootstrap_deployment_key, workspace_key
from multica_state_bundle.relocations import hold_relocation_mutation_guard, release_relocation_mutation_guard
from multica_state_bundle.namespaces import create_workspace_namespace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--readback-snapshot", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--output-bundle", type=Path)
    parser.add_argument("--pointer-state-root", type=Path, required=True)
    parser.add_argument("--relocation-intent-digest")
    args = parser.parse_args()
    temporary: Path | None = None
    _relocation_guard: int | None = None
    mutation_claim = None
    mutation_namespace = None
    claim_outcome = "FAILED"
    try:
        configuration = load_input(args.input)
        runtime_refs = [
            runtime["runtime_ref"]
            for runtime in configuration["runtime_fleet"]["runtimes"]
            if runtime.get("runtime_ref")
        ]
        snapshot_digest = readback_snapshot_digest(
            args.readback_snapshot,
            server_ref=configuration["server"]["ref"],
            profile_ref=configuration["server"]["profile"],
            account_ref=configuration["server"]["account_ref"],
            workspace_ref=configuration["workspace"].get("workspace_ref"),
            runtime_refs=runtime_refs,
        )
        blockers = foundation_blockers(configuration)
        server = configuration["server"]
        workspace = configuration["workspace"]
        runtimes = [
            {
                "alias": runtime["alias"],
                "runtime_ref": runtime.get("runtime_ref"),
                "daemon_ref": runtime.get("daemon_ref"),
                "status": runtime["status"],
                "provider": runtime.get("provider"),
                "capability_revision": runtime.get("capability_revision"),
            }
            for runtime in sorted(configuration["runtime_fleet"]["runtimes"], key=lambda item: item["alias"])
        ]
        produced_at = utc_now()
        deployment_key = server.get("deployment_key") or bootstrap_deployment_key(
            server["kind"], server["ref"], workspace["workspace_ref"]
        )
        relocation_intent_digest = server.get("relocation_intent_digest")
        if args.relocation_intent_digest != relocation_intent_digest:
            raise InputError("relocation intent differs from Foundation input")
        payload = {
            "schema": OUTPUT_SCHEMA,
            "server_ref": server["ref"],
            "server_kind": server["kind"],
            "deployment_key": deployment_key,
            "workspace_key": workspace_key(
                server["kind"], server["ref"], workspace["workspace_ref"], deployment_key
            ),
            "relocation_intent_digest": relocation_intent_digest,
            "producer_session": {
                "profile_ref": server["profile"],
                "authenticated_account_ref": server["account_ref"],
            },
            "workspace_ref": workspace.get("workspace_ref"),
            "labels": {
                name: {"ref": value.get("label_ref"), "color": value["color"].lower()}
                for name, value in configuration["labels"].items()
            },
            "status_contract": {
                "state": (
                    "VERIFIED"
                    if all(value["state"] == "VERIFIED" for value in configuration["statuses"].values())
                    else "HUMAN_CONFIRMATION_REQUIRED"
                ),
                "evidence_refs": {
                    key: value["evidence_ref"] for key, value in configuration["statuses"].items()
                },
            },
            "runtime_fleet": {
                "membership_digest": digest_bytes(canonical_json(runtimes)),
                "runtimes": runtimes,
            },
            "orchestration_capabilities": {
                "state": configuration["orchestration_capabilities"]["state"],
                "evidence_ref": configuration["orchestration_capabilities"]["evidence_ref"],
                "native_squad_routing": dict(
                    sorted(configuration["orchestration_capabilities"]["native_squad_routing"].items())
                ),
            },
            "state": "WORKSPACE_FOUNDATION_VERIFIED" if not blockers else "PARTIAL",
            "dispatch_state": "BLOCKED_ORCHESTRATOR_LAYER",
            "blockers": blockers,
            "readback_snapshot_digest": snapshot_digest,
            "produced_at": produced_at,
        }
        if not blockers and args.pointer_state_root is not None:
            operator_state_root = Path(configuration["operator_state_root"]).resolve()
            if (
                args.pointer_state_root.expanduser().resolve() != operator_state_root
                or args.state_root.expanduser().resolve() != operator_state_root / "bundle-store"
            ):
                raise InputError("Foundation publish roots differ from the input-bound operator state")
            _relocation_guard = hold_relocation_mutation_guard(
                operator_state_root,
                deployment_key,
                relocation_intent_digest,
                kind="workspace-publish",
                subject=str(configuration["workspace"].get("workspace_ref") or "workspace-pending"),
            )
            mutation_namespace = create_workspace_namespace(
                state_root=operator_state_root,
                workspace_key_value=payload["workspace_key"],
            )
            mutation_claim = acquire_claim(mutation_namespace, "workspace-publish")
        if args.output_bundle is None:
            temporary = Path(tempfile.mkdtemp(prefix="foundation-bundle-"))
            output = temporary / "bundle"
        else:
            output = args.output_bundle
        bundle = write_bundle(
            output,
            stage="workspace-foundation",
            artifact_bytes={"workspace-foundation": artifact_json(payload)},
            produced_at=produced_at,
        )
        stored = BundleStore(args.state_root).publish(
            bundle.root,
            expected_stage="workspace-foundation",
            expected_manifest_digest=bundle.manifest_digest,
        )
        pointer_path = None
        deployment_index_path = None
        if not blockers and args.pointer_state_root is not None:
            subject_key = payload["workspace_key"]
            pointer_path = StagePointers(args.pointer_state_root).write(
                "workspaces",
                subject_key,
                "foundation",
                "workspace-foundation",
                stored.manifest_digest,
            )
            deployment_index_path = DeploymentIndex(args.pointer_state_root).publish_foundation(
                server_kind=payload["server_kind"],
                server_ref=payload["server_ref"],
                workspace_ref=payload["workspace_ref"],
                deployment_key=payload["deployment_key"],
                workspace_key_value=payload["workspace_key"],
                foundation_manifest_digest=stored.manifest_digest,
                relocation_intent_digest=relocation_intent_digest,
            )
        claim_outcome = "PUBLISHED"
        print(json.dumps({
            "ok": not blockers,
            "bundle": str(stored.root),
            "export_bundle": str(args.output_bundle) if args.output_bundle else None,
            "manifest_digest": stored.manifest_digest,
            "artifact_digest": stored.manifest["artifacts"]["workspace-foundation"]["digest"],
            "readback_snapshot_digest": snapshot_digest,
            "pointer": str(pointer_path) if pointer_path else None,
            "deployment_index": str(deployment_index_path) if deployment_index_path else None,
            "blockers": blockers,
        }, ensure_ascii=False, sort_keys=True))
        return 0 if not blockers else 1
    except (StateError, StateBundleError, BundleError, InputError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "error": "WORKSPACE_FOUNDATION_INPUT_INVALID", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
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
