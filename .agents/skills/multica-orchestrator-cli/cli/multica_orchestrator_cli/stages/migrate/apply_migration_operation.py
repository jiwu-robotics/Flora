#!/usr/bin/env python3
"""Apply one explicitly authorized migration operation with fixed remote command shapes."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path, PurePosixPath

from multica_state_bundle.bundle_store import BundleStore
from multica_state_bundle.handoff import BundleError, canonical_json, digest_bytes
from migration_common import (
    ACTIVATION_RECEIPT_SCHEMA,
    MigrationError,
    OPERATION_RECEIPT_SCHEMA,
    PLAN_SCHEMA,
    PREFLIGHT_SCHEMA,
    encoded,
    load_input,
    load_release_context,
    parse_json_stdout,
    read_json,
    run_process,
    scp_from,
    scp_to,
    ssh_command,
    target_context,
)
from multica_state_bundle.identities import StateError, utc_now
from multica_state_bundle.relocations import hold_relocation_mutation_guard, release_relocation_mutation_guard
from multica_state_bundle.storage import atomic_bytes


def remote_receiver(operation: dict, arguments: list[str]) -> dict:
    command = ["python3", f"{operation['receiver_dir']}/remote_receiver.py", *arguments]
    completed = ssh_command(operation["ssh_config_host"], command)
    payload = parse_json_stdout(completed, "remote receiver")
    if not isinstance(payload, dict) or payload.get("ok") is not True or not isinstance(payload.get("result"), dict):
        raise MigrationError("remote receiver did not return a successful result")
    return payload["result"]


def verify_plan(args: argparse.Namespace, configuration: dict) -> tuple[dict, dict, object, tuple]:
    plan = dict(read_json(args.plan, "migration plan"))
    if plan.get("schema") != PLAN_SCHEMA:
        raise MigrationError("migration plan schema is invalid")
    unsigned = dict(plan)
    observed = unsigned.pop("plan_digest", None)
    actual = digest_bytes(canonical_json(unsigned))
    if observed != actual or args.plan_digest != actual:
        raise MigrationError("migration plan digest differs from authorization")
    if plan.get("input_digest") != digest_bytes(args.input.read_bytes()):
        raise MigrationError("migration input changed after planning")
    snapshot = dict(read_json(args.snapshot, "target preflight"))
    if snapshot.get("schema") != PREFLIGHT_SCHEMA:
        raise MigrationError("preflight schema is invalid")
    unsigned_snapshot = dict(snapshot)
    snapshot_digest = unsigned_snapshot.pop("snapshot_digest", None)
    if snapshot_digest != digest_bytes(canonical_json(unsigned_snapshot)) or plan.get("preflight_snapshot_digest") != snapshot_digest:
        raise MigrationError("preflight snapshot differs from plan")
    if plan.get("blockers"):
        raise MigrationError("migration plan has unresolved blockers")
    candidate, _, _, project_bundle, closure = load_release_context(configuration)
    if plan.get("project_bundle_manifest_digest") != project_bundle.manifest_digest or plan.get("release_candidate_digest") != configuration["source"]["release_candidate_digest"]:
        raise MigrationError("release changed after planning")
    if plan.get("native_squad_dispatch_digest") != candidate["native_squad_dispatch_digest"]:
        raise MigrationError("native Squad dispatch policy changed after planning")
    if plan.get("bundle_closure") != [bundle.manifest_digest for bundle in closure]:
        raise MigrationError("bundle closure changed after planning")
    matches = [item for item in plan.get("operations", []) if isinstance(item, dict) and item.get("id") == args.operation]
    if len(matches) != 1:
        raise MigrationError("operation is not unique in migration plan")
    return plan, matches[0], project_bundle, (candidate, closure)


def apply_operation(args: argparse.Namespace, configuration: dict, operation: dict, project_bundle, candidate: dict) -> tuple[str, dict]:
    action = operation.get("action")
    host = operation["ssh_config_host"]
    alias = operation["runtime_alias"]
    target = next(item for item in configuration["targets"] if item["runtime_alias"] == alias)
    context = target_context(configuration, project_bundle, alias)
    if not operation["remote_base"].startswith(target["state_root"] + "/migrations/"):
        raise MigrationError("remote migration directory escapes target state root")
    if action == "install-receiver":
        ssh_command(host, ["install", "-d", "-m", "700", operation["receiver_dir"], operation["remote_base"]])
        cli = Path(__file__).resolve().parent
        package_cli = cli.parents[2]
        for name, expected in sorted(operation["receiver_files"].items()):
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise MigrationError(f"reviewed receiver path is unsafe: {name}")
            source = cli / relative
            if not source.is_file():
                source = package_cli / relative
            if not source.is_file() or source.is_symlink():
                raise MigrationError(f"reviewed receiver file is unavailable: {name}")
            if digest_bytes(source.read_bytes()) != expected:
                raise MigrationError(f"reviewed receiver file changed: {name}")
            parent = f"{operation['receiver_dir']}/{relative.parent}"
            ssh_command(host, ["install", "-d", "-m", "700", parent])
            remote_file = f"{operation['receiver_dir']}/{relative}"
            scp_to(host, source, remote_file)
            ssh_command(host, ["chmod", "600", remote_file])
            observed = ssh_command(host, ["sha256sum", remote_file]).stdout.split()[0]
            if "sha256:" + observed != expected:
                raise MigrationError(f"remote receiver checksum differs: {name}")
        return "APPLIED", {"receiver_dir": operation["receiver_dir"], "receiver_files": operation["receiver_files"]}
    if action == "transfer-bundle-pack":
        work_dir = args.work_dir.expanduser().resolve()
        if work_dir.is_symlink() or not work_dir.is_dir():
            raise MigrationError("--work-dir must be an existing non-symlink directory")
        os.chmod(work_dir, 0o700)
        pack = work_dir / f"{alias}-bundle-pack"
        if pack.exists():
            shutil.rmtree(pack)
        BundleStore(Path(configuration["source"]["state_root"])).export_pack("project-binding", project_bundle.manifest_digest, pack)
        if digest_bytes((pack / "pack-manifest.json").read_bytes()) != operation["pack_manifest_digest"]:
            raise MigrationError("exported transfer pack digest differs from plan")
        remote_parent = str(Path(operation["remote_pack"]).parent)
        ssh_command(host, ["install", "-d", "-m", "700", remote_parent])
        presence = ssh_command(host, ["test", "-e", operation["remote_pack"]], allow_failure=True)
        if presence.returncode == 0:
            observed = ssh_command(host, ["sha256sum", f"{operation['remote_pack']}/pack-manifest.json"]).stdout.split()[0]
            if "sha256:" + observed != operation["pack_manifest_digest"]:
                raise MigrationError("remote transfer pack path already contains different content")
            return "ALREADY_APPLIED", {"remote_pack": operation["remote_pack"], "pack_manifest_digest": operation["pack_manifest_digest"]}
        if presence.returncode != 1:
            raise MigrationError("cannot determine whether remote transfer pack exists")
        scp_to(host, pack, operation["remote_pack"], recursive=True)
        observed = ssh_command(host, ["sha256sum", f"{operation['remote_pack']}/pack-manifest.json"]).stdout.split()[0]
        if "sha256:" + observed != operation["pack_manifest_digest"]:
            raise MigrationError("remote transfer pack digest differs")
        return "APPLIED", {"remote_pack": operation["remote_pack"], "pack_manifest_digest": operation["pack_manifest_digest"]}
    if action == "import-bundle-pack":
        result = remote_receiver(operation, [
            "import-pack", "--state-root", target["state_root"], "--pack", operation["remote_pack"],
            "--pack-digest", operation["pack_manifest_digest"], "--bundle-digest", project_bundle.manifest_digest,
        ])
        return "APPLIED", result
    if action == "checkout-repository":
        result = remote_receiver(operation, [
            "checkout-repository", "--root", operation["repository_root"], "--url", operation["repository_url"],
        ])
        state = "ALREADY_APPLIED" if result.get("state") == "ALREADY_PRESENT" else "APPLIED"
        return state, result
    if action == "bind-local-directory":
        result = remote_receiver(operation, [
            "bind-local-directory", "--server-kind", configuration["server"]["kind"],
            "--profile", operation["profile"], "--workspace-ref", operation["workspace_ref"],
            "--project-ref", operation["project_ref"], "--root", operation["repository_root"],
            "--daemon-ref", operation["daemon_ref"], "--execution-mode", operation["execution_mode"],
        ])
        state = "ALREADY_APPLIED" if result.get("state") == "ALREADY_PRESENT" else "APPLIED"
        return state, result
    if action == "verify-activation":
        local_input = args.work_dir.expanduser().resolve() / f"{alias}-target-input.json"
        if local_input.parent.is_symlink() or not local_input.parent.is_dir():
            raise MigrationError("--work-dir must be an existing non-symlink directory")
        target_input = {
            "schema": "multica-orchestrator-migrate.target-activation-input.v3",
            "server": configuration["server"],
            "state_root": target["state_root"],
            "project_bundle_manifest_digest": project_bundle.manifest_digest,
            "release_candidate_digest": configuration["source"]["release_candidate_digest"],
            "native_squad_dispatch_digest": candidate["native_squad_dispatch_digest"],
            "project_key": context["project_key"],
            "generation": candidate["generation"],
            "runtime_alias": alias,
            "runtime_ref": context["runtime"]["runtime_ref"],
            "daemon_ref": context["runtime"]["daemon_ref"],
            "profile": target["profile"],
            "account_ref": target["account_ref"],
            "repository_url": configuration["repository"]["url"],
            "repository_root": target["repository_root"],
            "repository_subpath": configuration["repository"]["project_subpath"],
            "command_profile": context["target_policy"]["command_profile"],
        }
        atomic_bytes(local_input, encoded(target_input))
        scp_to(host, local_input, operation["remote_target_input"])
        remote_receiver(operation, ["verify-activation", "--target-input", operation["remote_target_input"], "--receipt", operation["remote_receipt"]])
        coordinator_receipt = Path(operation["coordinator_receipt"])
        if coordinator_receipt.resolve() == args.receipt.expanduser().resolve():
            raise MigrationError("activation receipt and operation receipt paths must differ")
        scp_from(host, operation["remote_receipt"], coordinator_receipt)
        receipt = dict(read_json(coordinator_receipt, "Runtime activation receipt"))
        unsigned = dict(receipt)
        observed = unsigned.pop("receipt_digest", None)
        if receipt.get("schema") != ACTIVATION_RECEIPT_SCHEMA or observed != digest_bytes(canonical_json(unsigned)):
            raise MigrationError("copied Runtime activation receipt digest is invalid")
        if receipt.get("runtime_alias") != alias or receipt.get("project_bundle_manifest_digest") != project_bundle.manifest_digest:
            raise MigrationError("Runtime activation receipt differs from operation")
        return "APPLIED", {"activation_receipt": str(coordinator_receipt), "receipt_digest": receipt["receipt_digest"]}
    raise MigrationError(f"unsupported migration operation action: {action}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-digest", required=True)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--authorization-ref", required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    _relocation_guard: int | None = None
    try:
        if not args.apply:
            raise MigrationError("--apply is required")
        configuration = dict(load_input(args.input))
        plan, operation, project_bundle, release = verify_plan(args, configuration)
        candidate, _ = release
        _relocation_guard = hold_relocation_mutation_guard(
            Path(configuration["source"]["operator_state_root"]),
            configuration["server"]["deployment_key"],
            candidate.get("relocation_intent_digest"),
            kind="runtime-migrate",
            subject=operation["runtime_alias"],
        )
        state, postcondition = apply_operation(args, configuration, operation, project_bundle, dict(candidate))
        receipt = {
            "schema": OPERATION_RECEIPT_SCHEMA,
            "plan_digest": plan["plan_digest"],
            "operation": operation["id"],
            "runtime_alias": operation["runtime_alias"],
            "authorization_ref": args.authorization_ref,
            "state": state,
            "postcondition_digest": digest_bytes(canonical_json(postcondition)),
            "completed_at": utc_now(),
        }
        atomic_bytes(args.receipt, encoded(receipt))
        print(json.dumps({"ok": True, "receipt": str(args.receipt), "state": state, "postcondition": postcondition}, ensure_ascii=False, sort_keys=True))
        return 0
    except (StateError, MigrationError, BundleError, OSError, KeyError, TypeError, StopIteration) as error:
        print(json.dumps({"ok": False, "error": "MIGRATION_OPERATION_REJECTED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        if _relocation_guard is not None:
            release_relocation_mutation_guard(_relocation_guard)


if __name__ == "__main__":
    raise SystemExit(main())
