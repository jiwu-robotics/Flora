#!/usr/bin/env python3
"""Publish one immutable ACTIVE source release on selected additional Runtime hosts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from multica_state_bundle.handoff import BundleError, canonical_json, digest_bytes
from multica_state_bundle.storage import atomic_bytes
from multica_orchestrator_cli.common.dispatch_runtime import read_active_release
from multica_orchestrator_cli.common.runtime_activation import build_release_publication
from migration_common import (
    AGGREGATE_SCHEMA,
    MigrationError,
    encoded,
    load_input,
    load_release_context,
    parse_json_stdout,
    read_json,
    scp_to,
    ssh_command,
    target_context,
)


def _remote_publication(target: Mapping[str, Any], publication: Mapping[str, Any], operation: str, work_dir: Path) -> Mapping[str, Any]:
    remote_base = Path(str(target["state_root"])) / "migrations" / publication["runtime_binding"]["project_key"].split(":", 1)[1] / str(publication["release"]["generation"])
    local = work_dir / f"dispatch-publication-{target['runtime_alias']}.json"
    atomic_bytes(local, encoded(publication))
    digest = digest_bytes(local.read_bytes())
    remote = str(remote_base / "dispatch-publication.json")
    ssh_command(str(target["ssh_config_host"]), ["install", "-d", "-m", "700", str(remote_base)])
    scp_to(str(target["ssh_config_host"]), local, remote)
    receiver = Path(str(target["state_root"])) / "receiver-v1" / "remote_receiver.py"
    completed = ssh_command(str(target["ssh_config_host"]), ["python3", str(receiver), operation, "--publication-input", remote, "--publication-digest", digest])
    payload = parse_json_stdout(completed, "dispatch publication receiver")
    if not isinstance(payload, Mapping) or payload.get("ok") is not True or not isinstance(payload.get("result"), Mapping):
        raise MigrationError("dispatch publication receiver did not return a result")
    return payload["result"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--aggregate", type=Path, required=True)
    parser.add_argument("--authorization-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if not args.apply:
            raise MigrationError("--apply is required")
        configuration = load_input(args.input)
        candidate, _, _, project_bundle, _ = load_release_context(configuration)
        aggregate = dict(read_json(args.aggregate, "activation aggregate"))
        unsigned = dict(aggregate)
        observed_digest = unsigned.pop("aggregate_digest", None)
        if aggregate.get("schema") != AGGREGATE_SCHEMA or observed_digest != digest_bytes(canonical_json(unsigned)):
            raise MigrationError("activation aggregate digest is invalid")
        expected = {
            "project_key": candidate["project_key"],
            "generation": candidate["generation"],
            "release_candidate_digest": configuration["source"]["release_candidate_digest"],
            "project_bundle_manifest_digest": project_bundle.manifest_digest,
            "native_squad_dispatch_digest": candidate["native_squad_dispatch_digest"],
            "primary_runtime_alias": configuration["source"]["primary_runtime_alias"],
            "base_active_release_digest": configuration["source"]["source_active_release_digest"],
            "target_runtime_aliases": sorted(item["runtime_alias"] for item in configuration["targets"]),
            "state": "VERIFIED",
        }
        mismatches = [key for key, value in expected.items() if aggregate.get(key) != value]
        if mismatches:
            raise MigrationError("activation aggregate differs from ACTIVE source: " + ", ".join(mismatches))
        active = read_active_release(Path(configuration["source"]["state_root"]), candidate["project_key"])
        if active["release_digest"] != configuration["source"]["source_active_release_digest"]:
            raise MigrationError("source ACTIVE release changed before target activation")
        release = active["release"]
        work_dir = args.output.parent / "activation-publications"
        work_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        target_results: list[dict[str, Any]] = []
        by_alias = {item["runtime_alias"]: item for item in configuration["targets"]}
        for receipt in aggregate["receipts"]:
            alias = receipt["runtime_alias"]
            target = {**by_alias[alias], **target_context(configuration, project_bundle, alias)["runtime"]}
            transient_receipt = {**receipt, "activation_aggregate": aggregate}
            publication = build_release_publication(
                configuration=configuration,
                project_binding=project_bundle.artifacts["project-binding"],
                release=release,
                candidate=candidate,
                receipt=transient_receipt,
                target=target,
            )
            staged = _remote_publication(target, publication, "stage-dispatch-release", work_dir)
            committed = _remote_publication(target, publication, "commit-dispatch-release", work_dir)
            readback = _remote_publication(target, publication, "read-dispatch-release", work_dir)
            if readback.get("release_digest") != active["release_digest"]:
                raise MigrationError(f"target {alias} does not expose the source ACTIVE release")
            target_results.append({"runtime_alias": alias, "receipt_digest": receipt["receipt_digest"], "stage": staged, "commit": committed, "readback": readback})
        source_after = read_active_release(Path(configuration["source"]["state_root"]), candidate["project_key"])
        if source_after["release_digest"] != active["release_digest"]:
            raise MigrationError("source ACTIVE release changed during target activation")
        record = {
            "schema": "multica-orchestrator-migrate.migration-activation-record.v1",
            "project_key": candidate["project_key"],
            "primary_runtime_alias": configuration["source"]["primary_runtime_alias"],
            "state": "ADDITIONAL_TARGETS_ACTIVE",
            "source_active_release_digest": active["release_digest"],
            "source_generation": release["generation"],
            "activation_aggregate_digest": aggregate["aggregate_digest"],
            "targets": target_results,
            "authorization_ref": args.authorization_ref,
        }
        record["record_digest"] = digest_bytes(canonical_json(record))
        atomic_bytes(args.output, encoded(record))
        print(json.dumps({"ok": True, "state": "ADDITIONAL_TARGETS_ACTIVE", "output": str(args.output), "record_digest": record["record_digest"], "source_active_release_digest": active["release_digest"]}, sort_keys=True))
        return 0
    except (MigrationError, BundleError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": "TARGET_ACTIVATION_REJECTED", "detail": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
