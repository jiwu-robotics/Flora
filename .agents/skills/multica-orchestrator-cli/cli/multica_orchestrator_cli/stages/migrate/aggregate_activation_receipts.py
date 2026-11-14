#!/usr/bin/env python3
"""Validate and aggregate activation receipts for selected additional Runtime targets."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from multica_state_bundle.handoff import BundleError, canonical_json, digest_bytes
from multica_state_bundle.identities import canonical_json as compact_json, utc_now
from multica_state_bundle.storage import atomic_bytes
from migration_common import (
    ACTIVATION_RECEIPT_SCHEMA,
    AGGREGATE_SCHEMA,
    MigrationError,
    encoded,
    load_input,
    load_release_context,
    read_json,
    target_context,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        configuration = load_input(args.input)
        candidate, _, _, project_bundle, _ = load_release_context(configuration)
        project = project_bundle.artifacts["project-binding"]
        policy = project_bundle.artifacts["runtime-target-policy"]
        selected_aliases = {item["runtime_alias"] for item in configuration["targets"]}
        optional_aliases = {item["runtime_alias"] for item in policy["optional_runtimes"]}
        if not selected_aliases or not selected_aliases <= optional_aliases:
            raise MigrationError("migration aggregate targets must be selected optional Runtimes")
        receipts: dict[str, dict] = {}
        for path in args.receipt:
            receipt = dict(read_json(path, f"Runtime activation receipt {path}"))
            unsigned = dict(receipt)
            observed_digest = unsigned.pop("receipt_digest", None)
            if receipt.get("schema") != ACTIVATION_RECEIPT_SCHEMA or observed_digest != digest_bytes(compact_json(unsigned)):
                raise MigrationError(f"Runtime activation receipt digest is invalid: {path}")
            alias = receipt.get("runtime_alias")
            if alias in receipts:
                raise MigrationError(f"duplicate Runtime activation receipt: {alias}")
            if alias not in selected_aliases:
                raise MigrationError(f"unexpected Runtime activation receipt: {alias}")
            context = target_context(configuration, project_bundle, alias)
            expected = {
                "project_key": project["project_key"],
                "generation": candidate["generation"],
                "release_candidate_digest": configuration["source"]["release_candidate_digest"],
                "native_squad_dispatch_digest": candidate["native_squad_dispatch_digest"],
                "project_bundle_manifest_digest": project_bundle.manifest_digest,
                "workspace_ref": configuration["server"]["workspace_ref"],
                "runtime_ref": context["runtime"]["runtime_ref"],
                "daemon_ref": context["runtime"]["daemon_ref"],
                "repository_identity": project["repository_identity"],
                "command_profile": context["target_policy"]["command_profile"],
                "execution_mode": "worktree",
                "worktree_capability_revision": context["runtime"]["capability_revision"],
                "state": "ACTIVATED",
            }
            mismatches = [key for key, value in expected.items() if receipt.get(key) != value]
            if mismatches:
                raise MigrationError(f"Runtime activation receipt {alias} differs: {', '.join(mismatches)}")
            receipts[alias] = receipt
        if receipts.keys() != selected_aliases:
            missing = sorted(selected_aliases - receipts.keys())
            raise MigrationError("selected Runtime activation receipts are missing: " + ", ".join(missing))
        payload = {
            "schema": AGGREGATE_SCHEMA,
            "project_key": project["project_key"],
            "generation": candidate["generation"],
            "release_candidate_digest": configuration["source"]["release_candidate_digest"],
            "project_bundle_manifest_digest": project_bundle.manifest_digest,
            "native_squad_dispatch_digest": candidate["native_squad_dispatch_digest"],
            "primary_runtime_alias": configuration["source"]["primary_runtime_alias"],
            "base_active_release_digest": configuration["source"]["source_active_release_digest"],
            "target_runtime_aliases": sorted(selected_aliases),
            "receipts": [receipts[alias] for alias in sorted(receipts)],
            "state": "VERIFIED",
            "aggregated_at": utc_now(),
        }
        payload["aggregate_digest"] = digest_bytes(canonical_json(payload))
        atomic_bytes(args.output, encoded(payload))
        print(json.dumps({"ok": True, "output": str(args.output), "aggregate_digest": payload["aggregate_digest"], "targets": payload["target_runtime_aliases"]}, ensure_ascii=False, sort_keys=True))
        return 0
    except (MigrationError, BundleError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "error": "ACTIVATION_AGGREGATION_REJECTED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
