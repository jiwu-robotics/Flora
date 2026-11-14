#!/usr/bin/env python3
"""Create a deterministic, stale-state-bound Runtime migration plan."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from multica_state_bundle.handoff import BundleError, canonical_json, digest_bytes
from multica_state_bundle.storage import atomic_bytes
from migration_common import (
    MigrationError,
    PLAN_SCHEMA,
    PREFLIGHT_SCHEMA,
    encoded,
    load_input,
    load_release_context,
    read_json,
    target_context,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    try:
        configuration = load_input(args.input)
        candidate, _, _, project_bundle, closure = load_release_context(configuration)
        snapshot = read_json(args.snapshot, "target preflight")
        if snapshot.get("schema") != PREFLIGHT_SCHEMA:
            raise MigrationError("preflight snapshot schema is invalid")
        unsigned_snapshot = dict(snapshot)
        observed_snapshot_digest = unsigned_snapshot.pop("snapshot_digest", None)
        if observed_snapshot_digest != digest_bytes(canonical_json(unsigned_snapshot)):
            raise MigrationError("preflight snapshot digest is invalid")
        if snapshot.get("input_digest") != digest_bytes(args.input.read_bytes()):
            raise MigrationError("migration input changed after preflight capture")
        if snapshot.get("release_candidate_digest") != configuration["source"]["release_candidate_digest"] or snapshot.get("project_bundle_manifest_digest") != project_bundle.manifest_digest:
            raise MigrationError("preflight snapshot names a different release")
        if snapshot.get("native_squad_dispatch_digest") != candidate["native_squad_dispatch_digest"]:
            raise MigrationError("preflight snapshot native Squad dispatch lineage differs")
        snapshot_targets = snapshot.get("targets")
        if not isinstance(snapshot_targets, list):
            raise MigrationError("preflight targets are invalid")
        by_alias = {item.get("runtime_alias"): item for item in snapshot_targets if isinstance(item, dict)}
        if len(by_alias) != len(snapshot_targets):
            raise MigrationError("preflight Runtime aliases are not unique")
        pack_manifest = {
            "schema": "multica-orchestrator.bundle-transfer-pack.v1",
            "root": {"stage": "project-binding", "manifest_digest": project_bundle.manifest_digest},
            "objects": [
                {
                    "stage": bundle.stage,
                    "manifest_digest": bundle.manifest_digest,
                    "path": f"objects/{bundle.stage}/{bundle.manifest_digest.split(':', 1)[1]}",
                }
                for bundle in closure
            ],
        }
        pack_manifest_digest = digest_bytes(canonical_json(pack_manifest))
        cli = Path(__file__).resolve().parent
        receiver_files = {
            name: digest_bytes((cli / name).read_bytes())
            for name in (
                "remote_receiver.py",
                "migration_common.py",
                "control_store.py",
            )
        }
        package_cli = cli.parents[2]
        package_files = (
            package_cli / "multica_orchestrator_cli" / "__init__.py",
            *(path for directory in (
                package_cli / "multica_state_bundle",
                package_cli / "multica_orchestrator_cli" / "common",
            ) for path in directory.rglob("*.py")),
        )
        receiver_files.update(
            {
                path.relative_to(package_cli).as_posix(): digest_bytes(path.read_bytes())
                for path in sorted(package_files)
            }
        )
        operations: list[dict[str, object]] = []
        blockers: list[str] = []
        project_ref = project_bundle.artifacts["project-binding"]
        for target in configuration["targets"]:
            alias = target["runtime_alias"]
            observed = by_alias.get(alias)
            if observed is None:
                blockers.append(f"{alias}:TARGET_PREFLIGHT_MISSING")
                continue
            for blocker in observed.get("blockers", []):
                blockers.append(f"{alias}:{blocker}")
            context = target_context(configuration, project_bundle, alias)
            remote_base = f"{target['state_root']}/migrations/{project_ref['project_key'].split(':', 1)[1]}/{candidate['generation']}"
            receiver_dir = f"{target['state_root']}/receiver-v1"
            remote_pack = f"{remote_base}/bundle-pack"
            remote_target_input = f"{remote_base}/target-input.json"
            remote_receipt = target["remote_receipt_path"]
            common = {
                "runtime_alias": alias,
                "ssh_config_host": target["ssh_config_host"],
                "target_state_root": target["state_root"],
                "remote_base": remote_base,
            }
            operations.extend([
                {
                    "id": f"{alias}/install-receiver", "action": "install-receiver", **common,
                    "receiver_dir": receiver_dir, "receiver_files": receiver_files,
                },
                {
                    "id": f"{alias}/transfer-bundle-pack", "action": "transfer-bundle-pack", **common,
                    "remote_pack": remote_pack, "pack_manifest_digest": pack_manifest_digest,
                },
                {
                    "id": f"{alias}/import-bundle-pack", "action": "import-bundle-pack", **common,
                    "receiver_dir": receiver_dir, "remote_pack": remote_pack,
                    "pack_manifest_digest": pack_manifest_digest,
                },
                {
                    "id": f"{alias}/checkout-repository", "action": "checkout-repository", **common,
                    "receiver_dir": receiver_dir, "repository_root": target["repository_root"],
                    "repository_url": configuration["repository"]["url"],
                },
                {
                    "id": f"{alias}/bind-local-directory", "action": "bind-local-directory", **common,
                    "receiver_dir": receiver_dir, "profile": target["profile"],
                    "workspace_ref": configuration["server"]["workspace_ref"],
                    "project_ref": context["project_ref"], "repository_root": target["repository_root"],
                    "daemon_ref": context["runtime"]["daemon_ref"],
                    "execution_mode": project_ref["repository_policy"]["execution_mode"],
                },
                {
                    "id": f"{alias}/verify-activation", "action": "verify-activation", **common,
                    "receiver_dir": receiver_dir, "remote_target_input": remote_target_input,
                    "remote_receipt": remote_receipt,
                    "coordinator_receipt": target["coordinator_receipt_path"],
                },
            ])
        payload = {
            "schema": PLAN_SCHEMA,
            "input_digest": digest_bytes(args.input.read_bytes()),
            "preflight_snapshot_digest": snapshot["snapshot_digest"],
            "release_candidate_digest": configuration["source"]["release_candidate_digest"],
            "project_bundle_manifest_digest": project_bundle.manifest_digest,
            "native_squad_dispatch_digest": candidate["native_squad_dispatch_digest"],
            "bundle_closure": [bundle.manifest_digest for bundle in closure],
            "operations": operations,
            "blockers": sorted(set(blockers)),
        }
        payload["plan_digest"] = digest_bytes(canonical_json(payload))
        atomic_bytes(args.plan, encoded(payload))
        print(json.dumps({"ok": not blockers, "plan": str(args.plan), "plan_digest": payload["plan_digest"], "blockers": payload["blockers"]}, ensure_ascii=False, sort_keys=True))
        return 0 if not blockers else 1
    except (MigrationError, BundleError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "error": "MIGRATION_PLAN_REJECTED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
