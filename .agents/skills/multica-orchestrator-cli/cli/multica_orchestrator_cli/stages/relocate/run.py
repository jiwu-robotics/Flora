#!/usr/bin/env python3
"""Stable runner for digest-bound Multica orchestrator relocation."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

PACKAGE_CLI = Path(__file__).resolve().parents[3]
if not (PACKAGE_CLI / "multica_state_bundle" / "__init__.py").is_file():
    print("STATE_BUNDLE_UNAVAILABLE: install multica-orchestrator-cli", file=sys.stderr)
    raise SystemExit(2)
sys.path.insert(0, str(PACKAGE_CLI))
from multica_state_bundle.bootstrap import activate_installed_package

activate_installed_package(Path(__file__))

from relocation_common import (
    RelocationError,
    active_release,
    digest_object,
    ensure_private_directory,
    read_json,
    require_digest,
    verify_embedded_digest,
)
from multica_state_bundle.bundle_store import BundleStore
from multica_state_bundle.claims import acquire_claim, release_claim
from multica_state_bundle.errors import StateBundleError
from multica_state_bundle.namespaces import resolve_namespace
from multica_state_bundle.identities import (
    DeploymentIndex,
    StagePointers,
    StateError,
    canonical_json,
    digest_bytes,
    project_key,
    require_absolute,
    utc_now,
    workspace_key,
)
from multica_state_bundle.relocations import (
    complete_mutation,
    fence_path,
    mutation_barrier,
    mutation_entries,
    record_completed_mutation,
    record_mutation_start,
    relocation_lock,
)
from multica_state_bundle.storage import atomic_json, read_private_object
AUTHORIZATION_REF = re.compile(r"^approval:[A-Za-z0-9][A-Za-z0-9._/-]*$")


INPUT_SCHEMA = "multica-orchestrator-relocate.input.v2"
READBACK_SCHEMA = "multica-orchestrator-relocate.target-readback.v2"
SNAPSHOT_SCHEMA = "multica-orchestrator-relocate.preflight.v3"
PLAN_SCHEMA = "multica-orchestrator-relocate.plan.v1"
INTENT_SCHEMA = "multica-orchestrator-relocate.intent.v2"
FENCE_SCHEMA = "multica-orchestrator-relocate.fence.v2"
PROJECT_RECEIPT_SCHEMA = "multica-orchestrator-relocate.project-receipt.v2"
AGGREGATE_SCHEMA = "multica-orchestrator-relocate.aggregate.v1"
RUNTIME_RECEIPT_SCHEMA = "multica-orchestrator.runtime-activation-receipt.v1"
RECORD_SCHEMA = "multica-orchestrator-relocate.record.v3"
MIGRATION_RECEIPT_SCHEMA = "multica-migrate-server.server-migration-receipt.v1"
NATIVE_SQUAD_DISPATCH_KEYS = {
    "leader_first",
    "leader_routes_by_exact_member_mention",
    "member_reply_retriggers_leader",
    "issue_assignment_no_start_required",
    "runtime_open_fence_required",
}


def load_typed(path: Path, schema: str, digest_field: str, label: str) -> dict[str, Any]:
    value = read_json(path.resolve(), label)
    if value.get("schema") != schema:
        raise RelocationError(f"{label} schema is invalid")
    verify_embedded_digest(value, digest_field, label)
    return value


def load_runtime_receipt(path: Path, label: str) -> dict[str, Any]:
    value = read_json(path.resolve(), label)
    if value.get("schema") != RUNTIME_RECEIPT_SCHEMA:
        raise RelocationError(f"{label} schema is invalid")
    if value.get("wire") != {
        "algorithm": "sha256",
        "canonicalization": "json-compact-sorted-utf8-v1",
        "embedded_field": "receipt_digest",
    }:
        raise RelocationError(f"{label} digest wire contract is invalid")
    verify_embedded_digest(value, "receipt_digest", label)
    return value


def observed_at(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise RelocationError(f"{label} observed_at is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RelocationError(f"{label} observed_at is invalid") from error
    if parsed.tzinfo is None:
        raise RelocationError(f"{label} observed_at must include a timezone")
    return parsed





def ensure_readback_after_mutations(
    state_root: Path,
    deployment_key: str,
    readback: Mapping[str, Any],
    label: str,
) -> None:
    current = mutation_barrier(state_root, deployment_key)
    if readback.get("mutation_barrier") != current:
        raise RelocationError(
            f"RELOCATION_PRECONDITION_CHANGED: {label} mutation barrier is stale"
        )
def ensure_only_relocation_mutations(
    state_root: Path,
    deployment_key: str,
    *,
    after_sequence: int,
    relocation_intent_digest: str,
) -> None:
    for entry in mutation_entries(state_root, deployment_key):
        sequence = entry["sequence"]
        if (
            sequence > after_sequence
            and entry.get("relocation_intent_digest") != relocation_intent_digest
        ):
            raise RelocationError(
                "RELOCATION_PRECONDITION_CHANGED: unrelated mutation invalidated the snapshot"
            )



def load_readback(path: Path, label: str) -> dict[str, Any]:
    value = load_typed(path, READBACK_SCHEMA, "readback_digest", label)
    expected = {
        "schema", "server", "workspace_ref", "identity_sets", "runtime_aliases",
        "runtime_state", "dispatch_quiesced", "active_executions",
        "active_leases", "integration_operations", "evidence",
        "mutation_barrier", "observed_at", "readback_digest",
    }
    server = value.get("server")
    identities = value.get("identity_sets")
    aliases = value.get("runtime_aliases")
    evidence = value.get("evidence")
    barrier = value.get("mutation_barrier")
    if (
        set(value) != expected
        or not isinstance(server, dict)
        or set(server) != {"kind", "ref"}
        or server.get("kind") not in {"cloud", "self-hosted"}
        or not isinstance(server.get("ref"), str)
        or not server["ref"]
        or not isinstance(value.get("workspace_ref"), str)
        or not value["workspace_ref"]
        or not isinstance(identities, dict)
        or set(identities) != {"workspace_digest", "project_set_digest", "orchestrator_resource_digest", "runtime_fleet_membership_digest"}
        or any(not isinstance(item, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", item) is None for item in identities.values())
        or not isinstance(aliases, list)
        or any(not isinstance(alias, str) or not alias for alias in aliases)
        or len(set(aliases)) != len(aliases)
        or value.get("runtime_state") not in {"RUNTIMES_READY", "RUNTIMES_NOT_READY"}
        or not isinstance(value.get("dispatch_quiesced"), bool)
        or any(not isinstance(value.get(field), int) or value[field] < 0 for field in ("active_executions", "active_leases", "integration_operations"))
        or not isinstance(evidence, dict)
        or set(evidence) != {"service_snapshot", "control_snapshot"}
        or not isinstance(barrier, dict)
        or set(barrier) != {"sequence", "journal_count", "journal_digest"}
        or not isinstance(barrier.get("sequence"), int)
        or barrier["sequence"] < 0
        or not isinstance(barrier.get("journal_count"), int)
        or barrier["journal_count"] < 0
        or re.fullmatch(r"sha256:[0-9a-f]{64}", str(barrier.get("journal_digest"))) is None
    ):
        raise RelocationError(f"{label} structure or identity fields are invalid")
    observed_at(value.get("observed_at"), label)
    for evidence_label, descriptor in evidence.items():
        if not isinstance(descriptor, dict) or set(descriptor) != {"path", "digest"}:
            raise RelocationError(f"{label} {evidence_label} descriptor is invalid")
        evidence_path = require_absolute(descriptor.get("path"), f"{label} {evidence_label} path")
        if evidence_path.is_symlink() or not evidence_path.is_file():
            raise RelocationError(f"{label} {evidence_label} file is invalid")
        if digest_bytes(evidence_path.read_bytes()) != require_digest(descriptor.get("digest"), f"{label} {evidence_label} digest"):
            raise RelocationError(f"{label} {evidence_label} bytes differ")
    return value


def load_target_inventory(path: Path) -> tuple[dict[str, Any], str]:
    candidate = path.expanduser().resolve()
    value = read_private_object(
        candidate,
        "multica-orchestrator.runtime-target-inventory.v1",
        "Runtime target inventory",
    )
    if value.get("schema") != "multica-orchestrator.runtime-target-inventory.v1":
        raise RelocationError("Runtime target inventory schema differs")
    targets = value.get("targets")
    if not isinstance(targets, dict) or not targets:
        raise RelocationError("Runtime target inventory must declare at least one target")
    return value, digest_bytes(candidate.read_bytes())


def migration_receipt(path: Path) -> dict[str, Any]:
    receipt = load_typed(path, MIGRATION_RECEIPT_SCHEMA, "receipt_digest", "server migration receipt")
    if receipt.get("target_authoritative") is not True or receipt.get("source_service_state") != "stopped":
        raise RelocationError("migration receipt does not prove an authoritative target and stopped source")
    if receipt.get("runtime_state") != "RUNTIMES_READY" or receipt.get("final_state") not in {"RUNTIMES_READY", "OBSERVING"}:
        raise RelocationError("migration receipt does not prove a ready Runtime fleet")
    return receipt


def write_digest_object(path: Path, value: dict[str, Any], field: str, *, replace: bool = False) -> str:
    value[field] = digest_object(value, field)
    if path.exists():
        existing = read_json(path, "existing digest-bound output")
        if existing == value:
            return value[field]
        raise RelocationError(f"refusing to overwrite output: {path}")
    atomic_json(path, value, replace=replace)
    return value[field]


def command_prepare(args: argparse.Namespace) -> dict[str, Any]:
    state_root = args.state_root.expanduser().resolve()
    receipt_path = args.migration_receipt.expanduser().resolve()
    receipt = migration_receipt(receipt_path)
    workspace_ref = receipt["workspace_ref"]
    source_server = {
        "kind": receipt["source"]["server_kind"],
        "ref": receipt["source"]["server_ref"],
    }
    target_server = {
        "kind": receipt["target"]["server_kind"],
        "ref": receipt["target"]["server_ref"],
    }
    deployment_index = DeploymentIndex(state_root)
    source_index = deployment_index.resolve(
        source_server["kind"],
        source_server["ref"],
        workspace_ref,
    )
    deployment = require_digest(source_index.get("deployment_key"), "deployment_key")
    if source_index.get("server_kind") != source_server["kind"] or source_index.get("server_ref") != source_server["ref"]:
        raise RelocationError("migration receipt source differs from the deployment index")
    old_key = require_digest(source_index.get("workspace_key"), "Workspace key")
    new_key = workspace_key(target_server["kind"], target_server["ref"], workspace_ref, deployment)
    if new_key != old_key:
        raise RelocationError("stable deployment identity produced a different Workspace key")
    inventory_path = args.target_inventory.expanduser().resolve()
    inventory, inventory_digest = load_target_inventory(inventory_path)
    profiles = {
        target.get("consumer_profile")
        for target in inventory["targets"].values()
        if isinstance(target, dict)
    }
    if args.target_profile not in profiles:
        raise RelocationError("target profile is not referenced by Runtime target inventory")
    for repository_identity, project_subpath in args.project:
        parsed_subpath = PurePosixPath(project_subpath)
        if re.fullmatch(r"github:[^/\s]+/[^/\s]+", repository_identity) is None:
            raise RelocationError("Project repository identity must be canonical github:owner/repository")
        if parsed_subpath.is_absolute() or ".." in parsed_subpath.parts:
            raise RelocationError("Project subpath must be relative and cannot traverse parents")
    selectors = sorted({tuple(selector) for selector in args.project})
    if args.project_scope == "explicit" and not selectors:
        raise RelocationError("explicit Project scope requires at least one --project selector")
    if args.project_scope != "explicit" and selectors:
        raise RelocationError("--project selectors require --project-scope explicit")
    output = ensure_private_directory(args.output_dir)
    unexpected = {path.name for path in output.iterdir()} - {"relocation-input.json"}
    if unexpected:
        raise RelocationError(
            f"relocation output directory contains unexpected entries: {sorted(unexpected)}"
        )
    payload = {
        "schema": INPUT_SCHEMA,
        "state_root": str(state_root),
        "source_index": {
            "path": source_index["_path"],
            "digest": source_index["_digest"],
        },
        "target_inventory": {
            "path": str(inventory_path),
            "digest": inventory_digest,
        },
        "target_profile": args.target_profile,
        "deployment_key": deployment,
        "migration_receipt": {"path": str(receipt_path), "digest": receipt["receipt_digest"]},
        "workspace_ref": workspace_ref,
        "old_server": source_server,
        "target_server": target_server,
        "old_workspace_key": old_key,
        "new_workspace_key": new_key,
        "project_scope": args.project_scope,
        "project_selectors": [
            {"repository_identity": repository_identity, "project_subpath": project_subpath}
            for repository_identity, project_subpath in selectors
        ],
        "created_at": receipt["observed_at"],
    }
    input_path = output / "relocation-input.json"
    input_digest = write_digest_object(input_path, payload, "input_digest")
    return {
        "ok": True,
        "state": "MIGRATION_RECEIPT_VERIFIED",
        "input": str(input_path),
        "input_digest": input_digest,
        "deployment_index": source_index["_path"],
    }


def load_input(path: Path, *, allow_index_cutover: bool = False) -> dict[str, Any]:
    value = load_typed(path, INPUT_SCHEMA, "input_digest", "relocation input")
    state_root = require_absolute(value.get("state_root"), "relocation input state_root")
    descriptor = value.get("source_index")
    if not isinstance(descriptor, dict):
        raise RelocationError("relocation input deployment index descriptor is invalid")
    index_path = require_absolute(descriptor.get("path"), "deployment index path")
    source_digest = require_digest(descriptor.get("digest"), "deployment index digest")
    expected_path = DeploymentIndex(state_root).deployment_path(value["deployment_key"])
    if index_path != expected_path or not index_path.is_file():
        raise RelocationError("deployment index path differs from state root")
    observed_digest = digest_bytes(index_path.read_bytes())
    if not allow_index_cutover and observed_digest != source_digest:
        raise RelocationError("deployment index changed")
    index_value = read_json(index_path, "Workspace deployment index")
    if (
        index_value.get("schema") != "multica-orchestrator.workspace-deployment-index.v1"
        or index_value.get("deployment_key") != value["deployment_key"]
        or index_value.get("workspace_ref") != value["workspace_ref"]
        or index_value.get("workspace_key") != value["new_workspace_key"]
    ):
        raise RelocationError("deployment index identity differs")
    expected_servers = {tuple(sorted(value["old_server"].items()))}
    if allow_index_cutover:
        expected_servers.add(tuple(sorted(value["target_server"].items())))
    observed_server = tuple(sorted({
        "kind": index_value.get("server_kind"),
        "ref": index_value.get("server_ref"),
    }.items()))
    if observed_server not in expected_servers:
        raise RelocationError("deployment index server differs")
    inventory_descriptor = value.get("target_inventory")
    if not isinstance(inventory_descriptor, dict):
        raise RelocationError("relocation input Runtime target inventory descriptor is invalid")
    inventory_path = require_absolute(inventory_descriptor.get("path"), "Runtime target inventory path")
    inventory, inventory_digest = load_target_inventory(inventory_path)
    if inventory_digest != inventory_descriptor.get("digest"):
        raise RelocationError("Runtime target inventory changed")
    if value.get("target_profile") not in {
        target.get("consumer_profile")
        for target in inventory["targets"].values()
        if isinstance(target, dict)
    }:
        raise RelocationError("target profile differs from Runtime target inventory")
    receipt_path = require_absolute(value["migration_receipt"].get("path"), "migration receipt path")
    receipt = migration_receipt(receipt_path)
    if receipt["receipt_digest"] != value["migration_receipt"].get("digest"):
        raise RelocationError("migration receipt differs from relocation input")
    if receipt["workspace_ref"] != value["workspace_ref"] or receipt["target"]["server_ref"] != value["target_server"]["ref"]:
        raise RelocationError("migration receipt identity differs from relocation input")
    value["_state_root"] = state_root
    value["_receipt"] = receipt
    value["_deployment_index"] = index_value
    value["_deployment_index_digest"] = observed_digest
    value["_target_inventory"] = inventory
    return value


def candidate_projects(configuration: dict[str, Any], server_digest: str) -> list[dict[str, Any]]:
    state_root: Path = configuration["_state_root"]
    root = state_root / "pointers" / "projects"
    if not root.exists():
        return []
    projects: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/candidate/current.json")):
        if path.is_symlink() or not path.is_file():
            raise RelocationError(f"Project candidate pointer must be a regular file: {path}")
        pointer = read_json(path, "Project candidate pointer")
        project = pointer.get("project_key")
        bundle_digest = pointer.get("project_bundle_manifest_digest")
        if not isinstance(project, str) or not isinstance(bundle_digest, str):
            raise RelocationError("Project candidate pointer lacks identity")
        bundle = BundleStore(state_root / "bundle-store").resolve("project-binding", bundle_digest)
        binding = bundle.artifacts.get("project-binding")
        policy = bundle.artifacts.get("runtime-target-policy")
        if not isinstance(binding, dict) or not isinstance(policy, dict):
            raise RelocationError("Project bundle lacks binding or Runtime policy")
        if binding.get("workspace_key") != configuration["old_workspace_key"]:
            continue
        if binding.get("server_bundle_manifest_digest") != server_digest:
            raise RelocationError("Project bundle is linked to an unexpected Server bundle")
        release, active_digest = active_release(state_root, project)
        if (
            release.get("project_key") != project
            or release.get("generation") != pointer.get("generation")
            or release.get("release_candidate_digest") != pointer.get("release_candidate_digest")
            or release.get("project_bundle_manifest_digest") != bundle_digest
        ):
            raise RelocationError(
                "Project candidate differs from the active release; finish or abandon the pending release before relocation"
            )
        repository_identity = binding.get("repository_identity")
        subpath = binding.get("repository_policy", {}).get("project_subpath", binding.get("project_subpath", "."))
        if not isinstance(repository_identity, str) or not isinstance(subpath, str):
            raise RelocationError("Project binding lacks repository identity or subpath")
        if (
            pointer.get("repository_identity") != repository_identity
            or pointer.get("project_subpath") != subpath
        ):
            raise RelocationError("Project candidate repository identity differs from binding")
        required = policy.get("required_runtimes")
        if not isinstance(required, list):
            raise RelocationError("Runtime target policy lacks required_runtimes")
        aliases = sorted(item.get("runtime_alias") for item in required if isinstance(item, dict) and isinstance(item.get("runtime_alias"), str))
        if len(aliases) != len(required) or len(set(aliases)) != len(aliases):
            raise RelocationError("Runtime target policy aliases are invalid")
        projects.append({
            "repository_identity": repository_identity,
            "project_subpath": subpath,
            "old_project_key": project,
            "new_project_key": project_key(configuration["new_workspace_key"], repository_identity, subpath),
            "old_project_bundle_manifest_digest": bundle_digest,
            "old_active_release_digest": active_digest,
            "required_runtime_aliases": aliases,
        })
    active_projects: set[str] = set()
    releases_root = state_root / "bundle-store" / "releases"
    if releases_root.exists():
        for active_path in sorted(releases_root.glob("*/active.json")):
            if active_path.is_symlink() or not active_path.is_file():
                raise RelocationError(f"active release pointer must be a regular file: {active_path}")
            pointer = read_json(active_path, "active release pointer")
            active_project = require_digest(pointer.get("project_key"), "active release project_key")
            release, _ = active_release(state_root, active_project)
            release_bundle = require_digest(
                release.get("project_bundle_manifest_digest"),
                "active release Project bundle",
            )
            release_bundle = BundleStore(state_root / "bundle-store").resolve(
                "project-binding", release_bundle
            )
            release_binding = release_bundle.artifacts.get("project-binding")
            if isinstance(release_binding, dict) and release_binding.get("workspace_key") == configuration["old_workspace_key"]:
                active_projects.add(active_project)
    candidate_keys = {item["old_project_key"] for item in projects}
    if active_projects != candidate_keys:
        raise RelocationError("BLOCKED_PROJECT_INVENTORY: active Project and candidate pointer sets differ")
    projects.sort(key=lambda item: (item["repository_identity"], item["project_subpath"]))
    return projects


def command_capture(args: argparse.Namespace) -> dict[str, Any]:
    configuration = load_input(args.input)
    readback = load_readback(args.live_readback, "target readback")
    receipt = configuration["_receipt"]
    if readback.get("server") != configuration["target_server"] or readback.get("workspace_ref") != configuration["workspace_ref"]:
        raise RelocationError("target readback server or Workspace differs")
    if readback.get("identity_sets") != receipt.get("identity_sets"):
        raise RelocationError("BLOCKED_IDENTITY_DRIFT: target identity sets differ from migration receipt")
    if readback.get("runtime_state") != "RUNTIMES_READY":
        raise RelocationError("BLOCKED_RUNTIME_FLEET: Runtime fleet is not ready")
    if readback.get("dispatch_quiesced") is not True or any(readback.get(field) != 0 for field in ("active_executions", "active_leases", "integration_operations")):
        raise RelocationError("BLOCKED_ACTIVE_EXECUTIONS: dispatch is not quiesced")
    ensure_readback_after_mutations(
        configuration["_state_root"],
        configuration["deployment_key"],
        readback,
        "capture readback",
    )
    pointers = StagePointers(configuration["_state_root"])
    foundation = pointers.read(
        "workspaces", configuration["old_workspace_key"], "foundation", "workspace-foundation"
    )
    server = pointers.read(
        "workspaces", configuration["old_workspace_key"], "server", "server-orchestration"
    )
    BundleStore(configuration["_state_root"] / "bundle-store").resolve(
        "workspace-foundation", foundation["manifest_digest"]
    )
    server_bundle = BundleStore(configuration["_state_root"] / "bundle-store").resolve(
        "server-orchestration", server["manifest_digest"]
    )
    parents = server_bundle.manifest.get("parents")
    if (
        not isinstance(parents, list)
        or len(parents) != 1
        or parents[0].get("manifest_digest") != foundation["manifest_digest"]
    ):
        raise RelocationError("old Server bundle parent differs from Foundation pointer")
    projects = candidate_projects(configuration, server["manifest_digest"])
    discovered = {
        (item["repository_identity"], item["project_subpath"])
        for item in projects
    }
    requested = {
        (item["repository_identity"], item["project_subpath"])
        for item in configuration["project_selectors"]
    }
    if configuration["project_scope"] == "explicitly-empty" and projects:
        raise RelocationError("explicitly-empty Project scope conflicts with discovered Projects")
    if configuration["project_scope"] == "explicit" and requested != discovered:
        raise RelocationError("BLOCKED_PROJECT_INVENTORY: explicit Project list is incomplete or stale")
    if configuration["project_scope"] == "all" and receipt["identity_sets"]["project_set_digest"] != readback["identity_sets"]["project_set_digest"]:
        raise RelocationError("BLOCKED_PROJECT_INVENTORY: Project set digest differs")
    runtime_aliases = sorted({alias for item in projects for alias in item["required_runtime_aliases"]})
    if not set(runtime_aliases).issubset(set(readback.get("runtime_aliases", []))):
        raise RelocationError("BLOCKED_RUNTIME_FLEET: required Runtime aliases are absent")
    snapshot = {
        "schema": SNAPSHOT_SCHEMA,
        "input_digest": configuration["input_digest"],
        "migration_receipt_digest": configuration["migration_receipt"]["digest"],
        "old_graph": {"foundation_manifest_digest": foundation["manifest_digest"], "server_manifest_digest": server["manifest_digest"]},
        "target_identity_sets": readback["identity_sets"],
        "target_readback_digest": readback["readback_digest"],
        "target_readback_observed_at": readback["observed_at"],
        "projects": projects,
        "runtime_aliases": runtime_aliases,
        "dispatch_quiesced": True,
        "mutation_barrier": readback["mutation_barrier"],
        "observed_at": readback["observed_at"],
    }
    if mutation_barrier(configuration["_state_root"], configuration["deployment_key"]) != snapshot["mutation_barrier"]:
        raise RelocationError("RELOCATION_PRECONDITION_CHANGED: mutation invalidated the captured snapshot")
    snapshot_digest = write_digest_object(args.snapshot.resolve(), snapshot, "snapshot_digest")
    return {"ok": True, "state": "GRAPH_CAPTURED", "snapshot": str(args.snapshot.resolve()), "snapshot_digest": snapshot_digest, "projects": len(projects), "runtime_aliases": runtime_aliases}


def load_snapshot(path: Path, configuration: dict[str, Any]) -> dict[str, Any]:
    snapshot = load_typed(path, SNAPSHOT_SCHEMA, "snapshot_digest", "relocation snapshot")
    if snapshot.get("input_digest") != configuration["input_digest"] or snapshot.get("migration_receipt_digest") != configuration["migration_receipt"]["digest"]:
        raise RelocationError("relocation snapshot differs from input")
    return snapshot


def command_plan(args: argparse.Namespace) -> dict[str, Any]:
    configuration = load_input(args.input)
    snapshot = load_snapshot(args.snapshot, configuration)
    if mutation_barrier(configuration["_state_root"], configuration["deployment_key"]) != snapshot["mutation_barrier"]:
        raise RelocationError("RELOCATION_PRECONDITION_CHANGED: mutation invalidated the relocation snapshot")
    precondition = snapshot["snapshot_digest"]
    operations = [
        {"id": "relocation/acquire-fence", "kind": "acquire-fence", "precondition_digest": precondition, "authorization_required": True},
        {"id": "workspace/reissue-foundation", "kind": "reissue-foundation", "precondition_digest": precondition, "authorization_required": False},
        {"id": "workspace/reissue-server", "kind": "reissue-server", "precondition_digest": precondition, "authorization_required": False},
    ]
    for item in snapshot["projects"]:
        key = item["new_project_key"].split(":", 1)[1]
        operations.append({"id": f"project/{key}/reissue", "kind": "reissue-project", "subject": item["new_project_key"], "precondition_digest": precondition, "authorization_required": False})
        for alias in item["required_runtime_aliases"]:
            operations.append({"id": f"project/{key}/runtime/{alias}/sync", "kind": "sync-runtime-closure", "subject": alias, "precondition_digest": precondition, "authorization_required": True})
        operations.append({"id": f"project/{key}/activate", "kind": "activate-release", "subject": item["new_project_key"], "precondition_digest": precondition, "authorization_required": True})
    operations.extend([
        {"id": "relocation/commit-index", "kind": "commit-index", "precondition_digest": precondition, "authorization_required": True},
        {"id": "relocation/verify", "kind": "verify-relocation", "precondition_digest": precondition, "authorization_required": False},
    ])
    plan = {
        "schema": PLAN_SCHEMA,
        "input_digest": configuration["input_digest"],
        "snapshot_digest": snapshot["snapshot_digest"],
        "migration_receipt_digest": configuration["migration_receipt"]["digest"],
        "deployment_key": configuration["deployment_key"],
        "operations": operations,
        "blockers": [],
        "state": "RELOCATION_PLANNED",
    }
    plan_digest = write_digest_object(args.plan.resolve(), plan, "plan_digest")
    return {"ok": True, "state": "RELOCATION_PLANNED", "plan": str(args.plan.resolve()), "plan_digest": plan_digest, "operations": len(operations)}


def load_plan(path: Path, configuration: dict[str, Any], snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    plan = load_typed(path, PLAN_SCHEMA, "plan_digest", "relocation plan")
    if plan.get("input_digest") != configuration["input_digest"] or plan.get("migration_receipt_digest") != configuration["migration_receipt"]["digest"]:
        raise RelocationError("relocation plan differs from input")
    if snapshot is not None and plan.get("snapshot_digest") != snapshot["snapshot_digest"]:
        raise RelocationError("relocation plan differs from snapshot")
    if plan.get("blockers") or plan.get("state") != "RELOCATION_PLANNED":
        raise RelocationError("relocation plan is blocked")
    return plan


def relocation_object_path(state_root: Path, value_digest: str) -> Path:
    require_digest(value_digest, "relocation object digest")
    return state_root / "relocations" / "objects" / f"{value_digest.split(':', 1)[1]}.json"




def command_fence(args: argparse.Namespace) -> dict[str, Any]:
    if AUTHORIZATION_REF.fullmatch(args.authorization or "") is None:
        raise RelocationError("fence requires a canonical approval reference")
    configuration = load_input(args.input)
    state_root: Path = configuration["_state_root"]
    snapshot = load_snapshot(args.snapshot, configuration)
    plan = load_plan(args.plan, configuration, snapshot)
    if mutation_barrier(state_root, configuration["deployment_key"]) != snapshot["mutation_barrier"]:
        raise RelocationError("RELOCATION_PRECONDITION_CHANGED: mutation invalidated the relocation snapshot")
    readback = load_readback(args.live_readback, "target readback")
    if readback.get("server") != configuration["target_server"] or readback.get("workspace_ref") != configuration["workspace_ref"]:
        raise RelocationError("target readback server or Workspace differs before fence")
    if (
        readback.get("identity_sets") != snapshot["target_identity_sets"]
        or readback.get("runtime_state") != "RUNTIMES_READY"
        or readback.get("dispatch_quiesced") is not True
        or any(readback.get(field) != 0 for field in ("active_executions", "active_leases", "integration_operations"))
    ):
        raise RelocationError("RELOCATION_PRECONDITION_CHANGED: live target state changed before fence")
    if observed_at(readback.get("observed_at"), "fence readback") <= observed_at(snapshot.get("target_readback_observed_at"), "preflight target readback"):
        raise RelocationError("RELOCATION_PRECONDITION_CHANGED: fence readback is not newer than preflight")
    pointers = StagePointers(configuration["_state_root"])
    foundation = pointers.read(
        "workspaces", configuration["old_workspace_key"], "foundation", "workspace-foundation"
    )
    server = pointers.read(
        "workspaces", configuration["old_workspace_key"], "server", "server-orchestration"
    )
    if (
        foundation["manifest_digest"] != snapshot["old_graph"]["foundation_manifest_digest"]
        or server["manifest_digest"] != snapshot["old_graph"]["server_manifest_digest"]
        or candidate_projects(configuration, server["manifest_digest"]) != snapshot["projects"]
    ):
        raise RelocationError("RELOCATION_PRECONDITION_CHANGED: local state graph changed before fence")
    intent = {
        "schema": INTENT_SCHEMA,
        "deployment_key": configuration["deployment_key"],
        "migration_receipt_digest": configuration["migration_receipt"]["digest"],
        "plan_digest": plan["plan_digest"],
        "source_index_digest": configuration["source_index"]["digest"],
        "target_inventory_digest": configuration["target_inventory"]["digest"],
        "old_workspace_key": configuration["old_workspace_key"],
        "new_workspace_key": configuration["new_workspace_key"],
        "fence_readback_digest": readback["readback_digest"],
        "fence_readback_observed_at": readback["observed_at"],
        "project_keys": sorted(item.get("subject") for item in plan["operations"] if item["kind"] == "reissue-project"),
        "created_at": snapshot["observed_at"],
    }
    intent["intent_digest"] = digest_object(intent, "intent_digest")
    intent_path = relocation_object_path(state_root, intent["intent_digest"])
    with relocation_lock(state_root, configuration["deployment_key"]):
        ensure_readback_after_mutations(
            state_root,
            configuration["deployment_key"],
            readback,
            "fence readback",
        )
        if intent_path.exists():
            if read_json(intent_path, "relocation intent") != intent:
                raise RelocationError("relocation intent digest collision")
        else:
            atomic_json(intent_path, intent, replace=False)
        current_path = fence_path(state_root, configuration["deployment_key"])
        generation = 1
        if current_path.exists():
            current = read_json(current_path, "relocation fence")
            if current.get("state") == "IN_PROGRESS" and current.get("transaction_digest") == intent["intent_digest"]:
                return {"ok": True, "state": "RELOCATION_FENCED", "intent": str(intent_path), "intent_digest": intent["intent_digest"], "fence": str(current_path)}
            if current.get("state") not in {"OPEN", "COMMITTED"}:
                raise RelocationError("another relocation fence is active")
            generation = int(current.get("generation", 0)) + 1
        fence = {
            "schema": FENCE_SCHEMA,
            "deployment_key": configuration["deployment_key"],
            "generation": generation,
            "transaction_digest": intent["intent_digest"],
            "source_index_digest": configuration["source_index"]["digest"],
            "target_inventory_digest": configuration["target_inventory"]["digest"],
            "state": "IN_PROGRESS",
            "authorization_ref": args.authorization,
            "updated_at": utc_now(),
        }
        atomic_json(current_path, fence)
    return {"ok": True, "state": "RELOCATION_FENCED", "intent": str(intent_path), "intent_digest": intent["intent_digest"], "fence": str(current_path)}


def command_receipt(args: argparse.Namespace) -> dict[str, Any]:
    evidence = read_json(args.evidence.resolve(), "Project relocation evidence")
    if "receipt_digest" in evidence or "runtime_receipts" in evidence:
        raise RelocationError("Project relocation evidence must omit generated receipt fields")
    required = {
        "schema", "plan_digest", "relocation_intent_digest", "old_project_key", "new_project_key",
        "old_project_bundle_manifest_digest", "new_project_bundle_manifest_digest", "old_active_release_digest",
        "new_active_release_digest", "repository_identity", "project_subpath",
        "state", "verified_at",
    }
    if set(evidence) != required or evidence.get("schema") != PROJECT_RECEIPT_SCHEMA or evidence.get("state") != "ACTIVE":
        raise RelocationError("Project relocation evidence fields or state are invalid")
    for field in ("plan_digest", "relocation_intent_digest", "old_project_key", "new_project_key", "old_project_bundle_manifest_digest", "new_project_bundle_manifest_digest", "old_active_release_digest", "new_active_release_digest"):
        require_digest(evidence.get(field), field)
    state_root = require_absolute(str(args.state_root), "receipt state root")
    runtime_receipts: dict[str, str] = {}
    for path in args.runtime_receipt:
        runtime = load_runtime_receipt(path, "Runtime activation receipt")
        alias = runtime.get("runtime_alias")
        if not isinstance(alias, str) or not alias or alias in runtime_receipts:
            raise RelocationError("Runtime activation receipt alias is invalid or duplicated")
        expected = {
            "project_key": evidence["new_project_key"],
            "project_bundle_manifest_digest": evidence["new_project_bundle_manifest_digest"],
            "repository_identity": evidence["repository_identity"],
            "execution_mode": "worktree",
            "state": "ACTIVATED",
        }
        if any(runtime.get(field) != value for field, value in expected.items()):
            raise RelocationError("Runtime activation receipt differs from Project relocation evidence")
        object_path = relocation_object_path(state_root, runtime["receipt_digest"])
        if object_path.exists():
            if read_json(object_path, "stored Runtime activation receipt") != runtime:
                raise RelocationError("Runtime activation receipt digest collision")
        else:
            atomic_json(object_path, runtime, replace=False)
        runtime_receipts[alias] = runtime["receipt_digest"]
    if not runtime_receipts:
        raise RelocationError("at least one Runtime activation receipt is required")
    evidence["runtime_receipts"] = dict(sorted(runtime_receipts.items()))
    receipt_digest = write_digest_object(args.output.resolve(), evidence, "receipt_digest")
    return {"ok": True, "receipt": str(args.output.resolve()), "receipt_digest": receipt_digest}


def validate_runtime_receipt_closure(
    state_root: Path,
    receipt: Mapping[str, Any],
    active: Mapping[str, Any],
    candidate: Mapping[str, Any],
    workspace_ref: str,
    runtime_targets: Mapping[str, Mapping[str, Any]],
) -> None:
    for alias, runtime_digest in receipt["runtime_receipts"].items():
        runtime = load_runtime_receipt(
            relocation_object_path(state_root, runtime_digest),
            "stored Runtime activation receipt",
        )
        target = runtime_targets.get(alias)
        if not isinstance(target, Mapping):
            raise RelocationError("Runtime activation receipt alias is absent from relocated Server and Project policy")
        expected = {
            "runtime_alias": alias,
            "runtime_ref": target.get("runtime_ref"),
            "daemon_ref": target.get("daemon_ref"),
            "command_profile": target.get("command_profile"),
            "project_key": receipt["new_project_key"],
            "generation": active.get("generation"),
            "release_candidate_digest": active.get("release_candidate_digest"),
            "project_bundle_manifest_digest": receipt["new_project_bundle_manifest_digest"],
            "workspace_ref": workspace_ref,
            "repository_identity": receipt["repository_identity"],
            "state": "ACTIVATED",
            "native_squad_dispatch_digest": active.get("native_squad_dispatch_digest"),
            "execution_mode": "worktree",
            "worktree_capability_revision": target.get("capability_revision"),
        }
        if any(runtime.get(field) != value for field, value in expected.items()):
            raise RelocationError("stored Runtime activation receipt differs from relocated release")
        verification = runtime.get("verification", {})
        capabilities_digest = verification.get("native_squad_cli_capabilities_digest")
        if (
            not isinstance(capabilities_digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", capabilities_digest) is None
            or verification.get("execution_mode") != "worktree"
            or verification.get("worktree_capability_revision")
            != target.get("capability_revision")
        ):
            raise RelocationError("stored Runtime activation receipt lacks worktree/native Squad capability evidence")


def validate_reissued_workspace(
    state_root: Path,
    foundation_digest: str,
    server_digest: str,
    target_server: Mapping[str, Any],
    deployment_key: str,
    workspace_key_value: str,
    workspace_ref: str,
    relocation_intent_digest: str,
) -> dict[str, Mapping[str, Any]]:
    foundation_bundle = BundleStore(state_root / "bundle-store").resolve(
        "workspace-foundation", foundation_digest
    )
    foundation_manifest = foundation_bundle.manifest
    foundation_artifacts = foundation_bundle.artifacts
    foundation_artifact_digest = foundation_manifest["artifacts"]["workspace-foundation"]["digest"]
    foundation_ref = foundation_artifacts.get("workspace-foundation")
    expected_foundation = {
        "schema": "multica-orchestrator-link-up.workspace-foundation-ref.v6",
        "server_ref": target_server["ref"],
        "server_kind": target_server["kind"],
        "deployment_key": deployment_key,
        "workspace_key": workspace_key_value,
        "relocation_intent_digest": relocation_intent_digest,
        "workspace_ref": workspace_ref,
    }
    if (
        foundation_manifest.get("parents") != []
        or not isinstance(foundation_ref, dict)
        or any(foundation_ref.get(field) != value for field, value in expected_foundation.items())
    ):
        raise RelocationError("new Foundation bundle identity or relocation lineage differs")
    foundation_capabilities = foundation_ref.get("orchestration_capabilities")
    native_routing = (
        foundation_capabilities.get("native_squad_routing")
        if isinstance(foundation_capabilities, dict)
        else None
    )
    if (
        not isinstance(foundation_capabilities, dict)
        or foundation_capabilities.get("state") != "VERIFIED"
        or not isinstance(native_routing, dict)
        or not native_routing
        or not all(value is True for value in native_routing.values())
    ):
        raise RelocationError("new Foundation lacks verified native Squad capabilities")
    server_bundle = BundleStore(state_root / "bundle-store").resolve(
        "server-orchestration", server_digest
    )
    server_manifest = server_bundle.manifest
    server_artifacts = server_bundle.artifacts
    if server_manifest.get("parents") != [
        {"stage": "workspace-foundation", "manifest_digest": foundation_digest}
    ]:
        raise RelocationError("new Server bundle does not parent the new Foundation bundle")
    server_ref = server_artifacts.get("server-orchestration")
    expected_server = {
        "schema": "multica-orchestrator.server-orchestration-ref.v10",
        "server_ref": target_server["ref"],
        "server_kind": target_server["kind"],
        "deployment_key": deployment_key,
        "workspace_key": workspace_key_value,
        "relocation_intent_digest": relocation_intent_digest,
        "workspace_ref": workspace_ref,
    }
    if (
        not isinstance(server_ref, dict)
        or any(server_ref.get(field) != value for field, value in expected_server.items())
        or server_ref.get("workspace_foundation_ref", {}).get("bundle_manifest_digest") != foundation_digest
        or server_ref.get("workspace_foundation_ref", {}).get("artifact_digest") != foundation_artifact_digest
    ):
        raise RelocationError("new Server bundle identity or relocation lineage differs")
    if (
        server_ref.get("package", {}).get("contract_version") != "10"
        or server_ref.get("project_binding_contract", {}).get("minimum_contract_version") != "12"
        or server_ref.get("dispatch_contract", {}).get("required_skill") != "multica-orchestrator-dispatch"
    ):
        raise RelocationError("new Server bundle contract version differs")
    server_reissue = server_artifacts.get("server-reissue-spec")
    server_reissue_descriptor = server_manifest.get("artifacts", {}).get("server-reissue-spec")
    if (
        not isinstance(server_reissue, dict)
        or server_reissue.get("schema") != "multica-orchestrator.server-reissue-spec.v1"
        or not isinstance(server_reissue_descriptor, dict)
        or server_ref.get("desired_state", {}).get("reissue_spec_digest") != server_reissue_descriptor.get("digest")
    ):
        raise RelocationError("new Server bundle lacks its portable reissue specification")
    runtimes = server_ref.get("runtime_fleet", {}).get("runtimes")
    if not isinstance(runtimes, list):
        raise RelocationError("new Server bundle lacks Runtime fleet")
    result: dict[str, Mapping[str, Any]] = {}
    for runtime in runtimes:
        if not isinstance(runtime, dict) or not isinstance(runtime.get("alias"), str) or runtime["alias"] in result:
            raise RelocationError("new Server Runtime fleet aliases are invalid")
        result[runtime["alias"]] = runtime
    return result


def validate_reissued_project(
    state_root: Path,
    receipt: Mapping[str, Any],
    required_aliases: set[str],
    server_runtimes: Mapping[str, Mapping[str, Any]],
    server_manifest_digest: str,
    deployment_key: str,
    workspace_key_value: str,
    workspace_ref: str,
    relocation_intent_digest: str,
) -> tuple[dict[str, Any], str]:
    project_key_value = receipt["new_project_key"]
    project_bundle = BundleStore(state_root / "bundle-store").resolve(
        "project-binding", receipt["new_project_bundle_manifest_digest"]
    )
    project_manifest = project_bundle.manifest
    artifacts = project_bundle.artifacts
    if project_manifest.get("parents") != [
        {"stage": "server-orchestration", "manifest_digest": server_manifest_digest}
    ]:
        raise RelocationError("new Project bundle does not parent the new Server bundle")
    binding = artifacts.get("project-binding")
    policy = artifacts.get("runtime-target-policy")
    verification_spec = artifacts.get("project-verification-spec")
    reissue_spec = artifacts.get("project-reissue-spec")
    if not all(isinstance(value, dict) for value in (binding, policy, verification_spec, reissue_spec)):
        raise RelocationError("new Project bundle lacks binding, Runtime policy, verification, or reissue specification")
    expected_binding = {
        "schema": "multica-orchestrator-nail-down.project-binding-ref.v12",
        "server_bundle_manifest_digest": server_manifest_digest,
        "deployment_key": deployment_key,
        "relocation_intent_digest": relocation_intent_digest,
        "workspace_key": workspace_key_value,
        "project_key": project_key_value,
        "workspace_ref": workspace_ref,
        "repository_identity": receipt["repository_identity"],
    }
    if any(binding.get(field) != value for field, value in expected_binding.items()):
        raise RelocationError("new Project binding identity or relocation lineage differs")
    expected_verification = {
        "schema": "multica-orchestrator.project-verification-spec.v8",
        "deployment_key": deployment_key,
        "relocation_intent_digest": relocation_intent_digest,
        "project_key": project_key_value,
        "workspace_ref": workspace_ref,
        "repository_identity": receipt["repository_identity"],
    }
    if any(verification_spec.get(field) != value for field, value in expected_verification.items()):
        raise RelocationError("new Project verification specification identity differs")
    reissue_descriptor = project_manifest.get("artifacts", {}).get("project-reissue-spec")
    if (
        reissue_spec.get("schema") != "multica-orchestrator.project-reissue-spec.v3"
        or not isinstance(reissue_descriptor, dict)
        or binding.get("desired_state", {}).get("reissue_spec_digest") != reissue_descriptor.get("digest")
    ):
        raise RelocationError("new Project reissue specification differs")
    dispatch = policy.get("native_squad_dispatch")
    dispatch_digest = digest_bytes(canonical_json(dispatch)) if isinstance(dispatch, dict) else None
    if (
        policy.get("schema") != "multica-orchestrator.runtime-target-policy.v4"
        or not isinstance(dispatch, dict)
        or set(dispatch) != NATIVE_SQUAD_DISPATCH_KEYS
        or not all(dispatch[key] is True for key in NATIVE_SQUAD_DISPATCH_KEYS)
        or binding.get("native_squad_dispatch") != dispatch
        or binding.get("runtime_target_policy_digest") != digest_bytes(canonical_json(policy))
        or verification_spec.get("native_squad_dispatch_digest") != dispatch_digest
    ):
        raise RelocationError("new Project native Squad dispatch policy differs")
    if (
        binding.get("repository_policy", {}).get("project_subpath") != receipt["project_subpath"]
        or binding.get("repository_policy", {}).get("execution_mode") != "worktree"
    ):
        raise RelocationError("new Project binding subpath or execution mode differs")
    required = policy.get("required_runtimes")
    if not isinstance(required, list):
        raise RelocationError("new Runtime target policy lacks required_runtimes")
    policy_targets: dict[str, Mapping[str, Any]] = {}
    for item in required:
        if not isinstance(item, dict) or not isinstance(item.get("runtime_alias"), str):
            raise RelocationError("new Runtime target policy aliases are invalid")
        alias = item["runtime_alias"]
        server_runtime = server_runtimes.get(alias)
        if (
            alias in policy_targets
            or not isinstance(server_runtime, Mapping)
            or item.get("required_capability_revision") != server_runtime.get("capability_revision")
        ):
            raise RelocationError("new Runtime target policy differs from Server Runtime fleet")
        policy_targets[alias] = {
            "runtime_ref": server_runtime.get("runtime_ref"),
            "daemon_ref": server_runtime.get("daemon_ref"),
            "capability_revision": item.get("required_capability_revision"),
            "command_profile": item.get("command_profile"),
        }
    policy_aliases = set(policy_targets)
    if policy_aliases != required_aliases:
        raise RelocationError("new Runtime target policy aliases differ")
    candidate_pointer = StagePointers(state_root).read_candidate(project_key_value)
    expected_pointer = {
        "schema": "multica-orchestrator.candidate-pointer.v2",
        "project_key": project_key_value,
        "project_bundle_manifest_digest": receipt["new_project_bundle_manifest_digest"],
        "repository_identity": receipt["repository_identity"],
        "project_subpath": receipt["project_subpath"],
    }
    if any(candidate_pointer.get(field) != value for field, value in expected_pointer.items()):
        raise RelocationError("new Project candidate pointer identity differs")
    candidate_path = require_absolute(
        candidate_pointer.get("release_candidate_path"), "new Project release candidate path"
    )
    if digest_bytes(candidate_path.read_bytes()) != require_digest(
        candidate_pointer.get("release_candidate_digest"), "new Project release candidate digest"
    ):
        raise RelocationError("new Project release candidate bytes changed")
    candidate = read_json(candidate_path, "new Project release candidate")
    if (
        not isinstance(candidate.get("generation"), int)
        or candidate["generation"] < 1
        or candidate_pointer.get("generation") != candidate["generation"]
    ):
        raise RelocationError("new Project release candidate generation differs from pointer")
    predecessor = {
        "relation": "server-relocation",
        "project_key": receipt["old_project_key"],
        "release_digest": receipt["old_active_release_digest"],
    }
    runtime_capability_digest = digest_bytes(canonical_json([
        {
            "runtime_alias": item["runtime_alias"],
            "required_capability_revision": item["required_capability_revision"],
        }
        for item in sorted(required, key=lambda value: value["runtime_alias"])
    ]))
    dispatch_contract_digest = binding.get("dispatch_contract_digest")
    expected_candidate = {
        "schema": "multica-orchestrator.project-release-candidate.v8",
        "deployment_key": deployment_key,
        "relocation_intent_digest": relocation_intent_digest,
        "project_key": project_key_value,
        "project_bundle_manifest_digest": receipt["new_project_bundle_manifest_digest"],
        "repository_identity": receipt["repository_identity"],
        "project_subpath": receipt["project_subpath"],
        "predecessor": predecessor,
        "native_squad_dispatch_digest": dispatch_digest,
        "runtime_capability_digest": runtime_capability_digest,
        "dispatch_contract_digest": dispatch_contract_digest,
    }
    if any(candidate.get(field) != value for field, value in expected_candidate.items()):
        raise RelocationError("new Project release candidate identity or predecessor differs")
    if set(candidate.get("required_runtime_aliases", [])) != required_aliases:
        raise RelocationError("new Project release candidate Runtime aliases differ")
    active, active_digest = active_release(state_root, project_key_value)
    expected_active = {
        "schema": "multica-orchestrator.active-project-release.v2",
        "deployment_key": deployment_key,
        "relocation_intent_digest": relocation_intent_digest,
        "project_key": project_key_value,
        "generation": candidate.get("generation"),
        "release_candidate_digest": candidate_pointer["release_candidate_digest"],
        "project_bundle_manifest_digest": receipt["new_project_bundle_manifest_digest"],
        "project_binding_digest": project_manifest["artifacts"]["project-binding"]["digest"],
        "runtime_capability_digest": runtime_capability_digest,
        "dispatch_contract_digest": dispatch_contract_digest,
        "predecessor": predecessor,
        "native_squad_dispatch_digest": dispatch_digest,
        "state": "ACTIVE",
    }
    if any(active.get(field) != value for field, value in expected_active.items()):
        raise RelocationError("new active Project release identity or predecessor differs")
    validate_runtime_receipt_closure(
        state_root, receipt, active, candidate_pointer, workspace_ref, policy_targets
    )
    return active, active_digest

def bundle_manifest_digest(path: Path, stage: str) -> str:
    candidate = path.expanduser().resolve()
    manifest = read_json(candidate, f"{stage} bundle manifest")
    if (
        manifest.get("schema") != "multica-orchestrator.handoff-bundle.v2"
        or manifest.get("stage") != stage
    ):
        raise RelocationError(f"{stage} bundle manifest identity is invalid")
    return digest_bytes(candidate.read_bytes())


def command_aggregate(args: argparse.Namespace) -> dict[str, Any]:
    configuration = load_input(args.input, allow_index_cutover=True)
    snapshot = load_snapshot(args.snapshot, configuration)
    plan = load_plan(args.plan, configuration, snapshot)
    intent = load_typed(args.intent, INTENT_SCHEMA, "intent_digest", "relocation intent")
    if intent.get("plan_digest") != plan["plan_digest"]:
        raise RelocationError("relocation intent differs from plan")
    foundation = bundle_manifest_digest(args.foundation_manifest, "workspace-foundation")
    current_fence = read_json(
        fence_path(configuration["_state_root"], configuration["deployment_key"]),
        "relocation fence",
    )
    if (
        current_fence.get("schema") != FENCE_SCHEMA
        or current_fence.get("state") != "IN_PROGRESS"
        or current_fence.get("transaction_digest") != intent["intent_digest"]
    ):
        raise RelocationError("matching IN_PROGRESS relocation fence is required")
    server = bundle_manifest_digest(args.server_manifest, "server-orchestration")
    server_runtimes = validate_reissued_workspace(
        configuration["_state_root"],
        foundation,
        server,
        configuration["target_server"],
        configuration["deployment_key"],
        configuration["new_workspace_key"],
        configuration["workspace_ref"],
        intent["intent_digest"],
    )
    expected = {item["new_project_key"]: item for item in snapshot["projects"]}
    observed: dict[str, dict[str, Any]] = {}
    receipt_directory = args.project_receipt_dir.expanduser().resolve()
    if receipt_directory.is_symlink() or not receipt_directory.is_dir():
        raise RelocationError("Project receipt directory must be a non-symlink directory")
    receipt_paths = sorted(path for path in receipt_directory.iterdir() if path.is_file() and not path.is_symlink() and path.suffix == ".json")
    for path in receipt_paths:
        receipt = load_typed(path, PROJECT_RECEIPT_SCHEMA, "receipt_digest", "Project relocation receipt")
        key = receipt.get("new_project_key")
        if key not in expected or key in observed:
            raise RelocationError("Project relocation receipt set is unexpected or duplicated")
        source = expected[key]
        for field in ("old_project_key", "old_project_bundle_manifest_digest", "old_active_release_digest", "repository_identity", "project_subpath"):
            if receipt.get(field) != source.get(field):
                raise RelocationError(f"Project relocation receipt {field} differs")
        if receipt.get("plan_digest") != plan["plan_digest"] or receipt.get("relocation_intent_digest") != intent["intent_digest"]:
            raise RelocationError("Project relocation receipt lineage differs")
        if set(receipt["runtime_receipts"]) != set(source["required_runtime_aliases"]):
            raise RelocationError("Project relocation Runtime receipt set differs")
        _, active_digest = validate_reissued_project(
            configuration["_state_root"],
            receipt,
            set(source["required_runtime_aliases"]),
            server_runtimes,
            server,
            configuration["deployment_key"],
            configuration["new_workspace_key"],
            configuration["workspace_ref"],
            intent["intent_digest"],
        )
        if active_digest != receipt["new_active_release_digest"]:
            raise RelocationError("Project active release differs from relocation receipt")
        object_path = relocation_object_path(configuration["_state_root"], receipt["receipt_digest"])
        if not object_path.exists():
            atomic_json(object_path, receipt, replace=False)
        observed[key] = receipt
    if set(observed) != set(expected):
        raise RelocationError("Project relocation receipt set is incomplete")
    aggregate = {
        "schema": AGGREGATE_SCHEMA,
        "plan_digest": plan["plan_digest"],
        "input_digest": configuration["input_digest"],
        "snapshot_digest": snapshot["snapshot_digest"],
        "relocation_intent_digest": intent["intent_digest"],
        "foundation_manifest_digest": foundation,
        "server_manifest_digest": server,
        "project_receipts": [{"project_key": key, "receipt_digest": observed[key]["receipt_digest"]} for key in sorted(observed)],
        "state": "RELEASES_REACTIVATED",
        "aggregated_at": max(
            [snapshot["observed_at"]]
            + [receipt["verified_at"] for receipt in observed.values()]
        ),
    }
    aggregate_digest = write_digest_object(args.output.resolve(), aggregate, "aggregate_digest")
    return {"ok": True, "state": "RELEASES_REACTIVATED", "aggregate": str(args.output.resolve()), "aggregate_digest": aggregate_digest}


def load_aggregate(
    path: Path,
    configuration: dict[str, Any],
    plan: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    aggregate = load_typed(path, AGGREGATE_SCHEMA, "aggregate_digest", "relocation aggregate")
    expected_projects = {item["new_project_key"] for item in snapshot["projects"]}
    rows = aggregate.get("project_receipts")
    observed_projects = {
        item.get("project_key")
        for item in rows
        if isinstance(item, dict)
    } if isinstance(rows, list) else set()
    if (
        aggregate.get("plan_digest") != plan["plan_digest"]
        or aggregate.get("input_digest") != configuration["input_digest"]
        or aggregate.get("snapshot_digest") != snapshot["snapshot_digest"]
        or aggregate.get("state") != "RELEASES_REACTIVATED"
        or len(observed_projects) != len(rows or [])
        or observed_projects != expected_projects
    ):
        raise RelocationError("relocation aggregate differs from plan, snapshot, or complete Project set")
    return aggregate

def _relocation_project_claims(args: argparse.Namespace) -> list[tuple[Any, Any]]:
    configuration = load_input(args.input, allow_index_cutover=True)
    snapshot = load_snapshot(args.snapshot, configuration)
    plan = load_plan(args.plan, configuration, snapshot)
    aggregate = load_aggregate(args.aggregate, configuration, plan, snapshot)
    claims: list[tuple[Any, Any]] = []
    try:
        for item in sorted(aggregate["project_receipts"], key=lambda item: item["project_key"]):
            receipt = load_typed(
                relocation_object_path(configuration["_state_root"], item["receipt_digest"]),
                PROJECT_RECEIPT_SCHEMA,
                "receipt_digest",
                "stored Project relocation receipt",
            )
            repository_identity = receipt["repository_identity"]
            if not isinstance(repository_identity, str) or not re.fullmatch(r"github:[^/\s]+/[^/\s]+", repository_identity):
                raise RelocationError("Project relocation receipt repository identity is invalid")
            namespace = resolve_namespace(
                state_root=configuration["_state_root"],
                workspace_key_value=configuration["new_workspace_key"],
                repository=f"https://github.com/{repository_identity.removeprefix('github:')}.git",
                subpath=receipt["project_subpath"],
            )
            if namespace.project_key != receipt["new_project_key"]:
                raise RelocationError("Project relocation receipt namespace identity differs")
            claims.append((namespace, acquire_claim(namespace, "relocation-commit")))
    except BaseException:
        for namespace, claim in reversed(claims):
            release_claim(namespace, claim, "BLOCKED")
        raise
    return claims


def _with_relocation_project_claims(command: Any) -> Any:
    def guarded(args: argparse.Namespace) -> dict[str, Any]:
        if args.output.exists():
            return command(args)
        claims = _relocation_project_claims(args)
        outcome = "FAILED"
        try:
            result = command(args)
            outcome = "PUBLISHED"
            return result
        finally:
            for namespace, claim in reversed(claims):
                release_claim(namespace, claim, outcome)

    return guarded


@_with_relocation_project_claims
def command_commit(args: argparse.Namespace) -> dict[str, Any]:
    if AUTHORIZATION_REF.fullmatch(args.authorization or "") is None:
        raise RelocationError("commit requires a canonical approval reference")
    configuration = load_input(args.input, allow_index_cutover=True)
    snapshot = load_snapshot(args.snapshot, configuration)
    plan = load_plan(args.plan, configuration, snapshot)
    aggregate = load_aggregate(args.aggregate, configuration, plan, snapshot)
    intent = load_typed(
        relocation_object_path(configuration["_state_root"], aggregate["relocation_intent_digest"]),
        INTENT_SCHEMA,
        "intent_digest",
        "relocation intent",
    )
    live_readback = load_readback(args.live_readback, "post-relocation target readback")
    if (
        live_readback.get("server") != configuration["target_server"]
        or live_readback.get("workspace_ref") != configuration["workspace_ref"]
        or live_readback.get("identity_sets") != snapshot["target_identity_sets"]
        or live_readback.get("runtime_state") != "RUNTIMES_READY"
        or live_readback.get("dispatch_quiesced") is not True
        or any(live_readback.get(field) != 0 for field in ("active_executions", "active_leases", "integration_operations"))
    ):
        raise RelocationError("RELOCATION_PRECONDITION_CHANGED: post-relocation target readback is not safe to commit")
    if (
        live_readback["readback_digest"] == intent["fence_readback_digest"]
        or observed_at(live_readback.get("observed_at"), "commit readback")
        <= observed_at(intent.get("fence_readback_observed_at"), "fence readback")
    ):
        raise RelocationError("RELOCATION_PRECONDITION_CHANGED: commit requires a newer target readback")
    state_root = configuration["_state_root"]
    with relocation_lock(state_root, configuration["deployment_key"]):
        current_fence_path = fence_path(state_root, configuration["deployment_key"])
        fence = read_json(current_fence_path, "relocation fence")
        if (
            fence.get("schema") != FENCE_SCHEMA
            or fence.get("state") not in {"IN_PROGRESS", "BLOCKED", "COMMITTED"}
            or fence.get("transaction_digest") != aggregate["relocation_intent_digest"]
        ):
            raise RelocationError("matching relocation fence is required")
        if fence.get("authorization_ref") == args.authorization:
            raise RelocationError("commit approval must differ from fence approval")
        output_path = args.output.resolve()
        if output_path.exists():
            existing_record = load_typed(
                output_path,
                RECORD_SCHEMA,
                "record_digest",
                "existing relocation record",
            )
            if (
                existing_record.get("deployment_key") != configuration["deployment_key"]
                or existing_record.get("migration_receipt_digest") != configuration["migration_receipt"]["digest"]
                or existing_record.get("plan_digest") != plan["plan_digest"]
                or existing_record.get("aggregate_digest") != aggregate["aggregate_digest"]
                or existing_record.get("commit_authorization_ref") != args.authorization
            ):
                raise RelocationError("existing relocation record differs from transaction")
            return {
                "ok": True,
                "state": "INDEX_COMMITTED",
                "record": str(output_path),
                "record_digest": existing_record["record_digest"],
                "fence": str(current_fence_path),
            }
        ensure_readback_after_mutations(
            state_root,
            configuration["deployment_key"],
            live_readback,
            "commit readback",
        )
        ensure_only_relocation_mutations(
            state_root,
            configuration["deployment_key"],
            after_sequence=snapshot["mutation_barrier"]["sequence"],
            relocation_intent_digest=aggregate["relocation_intent_digest"],
        )
        server_runtimes = validate_reissued_workspace(
            state_root,
            aggregate["foundation_manifest_digest"],
            aggregate["server_manifest_digest"],
            configuration["target_server"],
            configuration["deployment_key"],
            configuration["new_workspace_key"],
            configuration["workspace_ref"],
            aggregate["relocation_intent_digest"],
        )
        receipt_rows = []
        expected_projects: dict[str, str] = {}
        for item in aggregate["project_receipts"]:
            receipt_path = relocation_object_path(state_root, item["receipt_digest"])
            receipt = load_typed(
                receipt_path,
                PROJECT_RECEIPT_SCHEMA,
                "receipt_digest",
                "stored Project relocation receipt",
            )
            _, active_digest = validate_reissued_project(
                state_root,
                receipt,
                set(receipt["runtime_receipts"]),
                server_runtimes,
                aggregate["server_manifest_digest"],
                configuration["deployment_key"],
                configuration["new_workspace_key"],
                configuration["workspace_ref"],
                aggregate["relocation_intent_digest"],
            )
            if active_digest != receipt["new_active_release_digest"]:
                raise RelocationError("Project active release changed before commit")
            expected_projects[receipt["new_project_key"]] = receipt["new_project_bundle_manifest_digest"]
            receipt_rows.append({
                "old_project_key": receipt["old_project_key"],
                "new_project_key": receipt["new_project_key"],
                "receipt_digest": receipt["receipt_digest"],
            })
        pointers = StagePointers(state_root)
        foundation = pointers.read(
            "workspaces",
            configuration["new_workspace_key"],
            "foundation",
            "workspace-foundation",
        )
        server = pointers.read(
            "workspaces",
            configuration["new_workspace_key"],
            "server",
            "server-orchestration",
        )
        if (
            foundation["manifest_digest"] != aggregate["foundation_manifest_digest"]
            or server["manifest_digest"] != aggregate["server_manifest_digest"]
            or server.get("parent_manifest_digest") != aggregate["foundation_manifest_digest"]
        ):
            raise RelocationError("reissued Workspace pointers differ from relocation aggregate")
        index = DeploymentIndex(state_root).read(configuration["deployment_key"])
        if (
            index.get("server_kind") != configuration["target_server"]["kind"]
            or index.get("server_ref") != configuration["target_server"]["ref"]
            or index.get("workspace_ref") != configuration["workspace_ref"]
            or index.get("workspace_key") != configuration["new_workspace_key"]
            or index.get("foundation_manifest_digest") != aggregate["foundation_manifest_digest"]
            or index.get("server_manifest_digest") != aggregate["server_manifest_digest"]
        ):
            raise RelocationError("reissued deployment index differs from relocation aggregate")
        indexed_projects = index.get("projects")
        if not isinstance(indexed_projects, dict) or {
            key: row.get("project_manifest_digest")
            for key, row in indexed_projects.items()
            if key in expected_projects and isinstance(row, dict)
        } != expected_projects:
            raise RelocationError("reissued deployment index Project graph differs")
        resolved_target = DeploymentIndex(state_root).resolve(
            configuration["target_server"]["kind"],
            configuration["target_server"]["ref"],
            configuration["workspace_ref"],
        )
        if resolved_target["_digest"] != index["_digest"]:
            raise RelocationError("target Workspace selection does not resolve to the committed index")
        commit_mutation = record_completed_mutation(
            state_root,
            configuration["deployment_key"],
            relocation_intent_digest=aggregate["relocation_intent_digest"],
            kind="relocation-commit",
            subject=index["_path"],
            outcome="SUCCEEDED",
            return_code=0,
        )
        committed_at = utc_now()
        record = {
            "schema": RECORD_SCHEMA,
            "state_root": str(state_root),
            "deployment_key": configuration["deployment_key"],
            "generation": fence["generation"],
            "migration_receipt_digest": configuration["migration_receipt"]["digest"],
            "plan_digest": plan["plan_digest"],
            "relocation_intent_digest": aggregate["relocation_intent_digest"],
            "aggregate_digest": aggregate["aggregate_digest"],
            "deployment_index_path": index["_path"],
            "source_index_digest": configuration["source_index"]["digest"],
            "target_index_digest": index["_digest"],
            "target_inventory_digest": configuration["target_inventory"]["digest"],
            "old_server": configuration["old_server"],
            "target_server": configuration["target_server"],
            "old_workspace_key": configuration["old_workspace_key"],
            "new_workspace_key": configuration["new_workspace_key"],
            "workspace_ref": configuration["workspace_ref"],
            "target_identity_sets": snapshot["target_identity_sets"],
            "foundation_manifest_digest": aggregate["foundation_manifest_digest"],
            "server_manifest_digest": aggregate["server_manifest_digest"],
            "projects": sorted(receipt_rows, key=lambda item: item["new_project_key"]),
            "commit_authorization_ref": args.authorization,
            "state": "INDEX_COMMITTED",
            "activation_state": "ACTIVE",
            "dispatch_state": "BLOCKED_VERIFICATION_REQUIRED",
            "commit_readback_observed_at": live_readback["observed_at"],
            "mutation_sequence": commit_mutation["sequence"],
            "committed_at": committed_at,
        }
        record["record_digest"] = digest_object(record, "record_digest")
        atomic_json(output_path, record, replace=False)
        stored_record = relocation_object_path(state_root, record["record_digest"])
        if stored_record.exists():
            if read_json(stored_record, "stored relocation record") != record:
                raise RelocationError("stored relocation record digest collision")
        else:
            atomic_json(stored_record, record, replace=False)
        if fence.get("state") != "COMMITTED":
            fence["state"] = "BLOCKED"
            fence["updated_at"] = committed_at
        atomic_json(current_fence_path, fence)
    return {
        "ok": True,
        "state": "INDEX_COMMITTED",
        "record": str(args.output.resolve()),
        "record_digest": record["record_digest"],
        "fence": str(current_fence_path),
    }


def command_verify(args: argparse.Namespace) -> dict[str, Any]:
    record = load_typed(args.record, RECORD_SCHEMA, "record_digest", "relocation record")
    if record.get("state") != "INDEX_COMMITTED" or record.get("dispatch_state") != "BLOCKED_VERIFICATION_REQUIRED":
        raise RelocationError("relocation record is not awaiting verification")
    live_readback = load_readback(args.live_readback, "verification target readback")
    if (
        live_readback.get("server") != record["target_server"]
        or live_readback.get("workspace_ref") != record["workspace_ref"]
        or live_readback.get("identity_sets") != record["target_identity_sets"]
        or live_readback.get("runtime_state") != "RUNTIMES_READY"
        or live_readback.get("dispatch_quiesced") is not True
        or any(live_readback.get(field) != 0 for field in ("active_executions", "active_leases", "integration_operations"))
    ):
        raise RelocationError("relocated target live readback is not ready for explicit dispatch")
    if observed_at(live_readback.get("observed_at"), "verification readback") <= observed_at(record.get("committed_at"), "commit record"):
        raise RelocationError("verification requires a target readback newer than commit")
    if live_readback["mutation_barrier"]["sequence"] < record["mutation_sequence"]:
        raise RelocationError("verification readback predates the relocation commit mutation")
    state_root = require_absolute(record.get("state_root"), "relocation record state_root")
    with relocation_lock(state_root, record["deployment_key"]):
        ensure_readback_after_mutations(
            state_root,
            record["deployment_key"],
            live_readback,
            "verification readback",
        )
        index = DeploymentIndex(state_root).read(record["deployment_key"])
        if (
            index["_path"] != record["deployment_index_path"]
            or index["_digest"] != record["target_index_digest"]
            or index.get("server_kind") != record["target_server"]["kind"]
            or index.get("server_ref") != record["target_server"]["ref"]
            or index.get("foundation_manifest_digest") != record["foundation_manifest_digest"]
            or index.get("server_manifest_digest") != record["server_manifest_digest"]
        ):
            raise RelocationError("committed deployment index differs")
        current_fence_path = fence_path(state_root, record["deployment_key"])
        fence = read_json(current_fence_path, "relocation fence")
        if (
            fence.get("state") not in {"BLOCKED", "COMMITTED"}
            or fence.get("transaction_digest") != record["relocation_intent_digest"]
        ):
            raise RelocationError("relocation fence is not awaiting matching verification")
        pointers = StagePointers(state_root)
        foundation = pointers.read(
            "workspaces", record["new_workspace_key"], "foundation", "workspace-foundation"
        )
        server = pointers.read(
            "workspaces", record["new_workspace_key"], "server", "server-orchestration"
        )
        if foundation["manifest_digest"] != record["foundation_manifest_digest"] or server["manifest_digest"] != record["server_manifest_digest"]:
            raise RelocationError("committed Workspace pointers differ from relocation record")
        server_runtimes = validate_reissued_workspace(
            state_root,
            foundation["manifest_digest"],
            server["manifest_digest"],
            record["target_server"],
            record["deployment_key"],
            record["new_workspace_key"],
            record["workspace_ref"],
            record["relocation_intent_digest"],
        )
        for item in record["projects"]:
            receipt = load_typed(
                relocation_object_path(state_root, item["receipt_digest"]),
                PROJECT_RECEIPT_SCHEMA,
                "receipt_digest",
                "stored Project relocation receipt",
            )
            if receipt["old_project_key"] != item["old_project_key"] or receipt["new_project_key"] != item["new_project_key"]:
                raise RelocationError("stored Project relocation receipt mapping differs")
            _, active_digest = validate_reissued_project(
                state_root,
                receipt,
                set(receipt["runtime_receipts"]),
                server_runtimes,
                record["server_manifest_digest"],
                record["deployment_key"],
                record["new_workspace_key"],
                record["workspace_ref"],
                record["relocation_intent_digest"],
            )
            if active_digest != receipt["new_active_release_digest"]:
                raise RelocationError("committed Project active release differs")
        fence["state"] = "COMMITTED"
        fence["updated_at"] = live_readback["observed_at"]
        atomic_json(current_fence_path, fence)
    return {
        "ok": True,
        "state": "ORCHESTRATOR_RELOCATION_VERIFIED",
        "activation_state": "ACTIVE",
        "dispatch_state": "EXPLICIT_DISPATCH_REQUIRED",
        "record_digest": record["record_digest"],
    }




def command_status(args: argparse.Namespace) -> dict[str, Any]:
    configuration = load_input(args.input, allow_index_cutover=True)
    run_directory = args.input.resolve().parent
    snapshot_path = (args.snapshot or run_directory / "relocation-preflight.json").resolve()
    plan_path = (args.plan or run_directory / "relocation-plan.json").resolve()
    aggregate_path = (args.aggregate or run_directory / "relocation-aggregate.json").resolve()
    record_path = (args.record or run_directory / "relocation-record.json").resolve()
    if not snapshot_path.is_file():
        return {
            "ok": True,
            "state": "TARGET_READBACK_REQUIRED",
            "next": [
                f"python3 <skill>/cli/capture_target_readback.py --input '{args.input.resolve()}' --control-db '<control-authority.sqlite3>' --output-dir '<new-readback-dir>'",
                f"python3 <skill>/cli/run.py capture --input '{args.input.resolve()}' --live-readback '<new-readback-dir>/target-readback.json' --snapshot '{snapshot_path}'",
            ],
        }
    snapshot = load_snapshot(snapshot_path, configuration)
    if not plan_path.is_file():
        return {
            "ok": True,
            "state": "PLAN_REQUIRED",
            "next": [
                f"python3 <skill>/cli/run.py plan --input '{args.input.resolve()}' --snapshot '{snapshot_path}' --plan '{plan_path}'"
            ],
        }
    plan = load_plan(plan_path, configuration, snapshot)
    current_fence_path = fence_path(configuration["_state_root"], configuration["deployment_key"])
    if not current_fence_path.is_file():
        return {
            "ok": True,
            "state": "FENCE_REQUIRED",
            "next": [
                f"python3 <skill>/cli/run.py fence --input '{args.input.resolve()}' --snapshot '{snapshot_path}' --plan '{plan_path}' --live-readback '<fresh-readback.json>' --authorization 'approval:<fence-approval>'"
            ],
        }
    fence = read_json(current_fence_path, "relocation fence")
    if fence.get("state") == "IN_PROGRESS":
        if not aggregate_path.is_file():
            return {
                "ok": True,
                "state": "REISSUE_OR_AGGREGATE_REQUIRED",
                "next": [
                    "Complete the planned Foundation, Server, Project, Runtime, and activation operations.",
                    f"python3 <skill>/cli/run.py aggregate --input '{args.input.resolve()}' --snapshot '{snapshot_path}' --plan '{plan_path}' --intent '<intent.json>' --foundation-manifest '<foundation-manifest.json>' --server-manifest '<server-manifest.json>' --project-receipt-dir '<receipt-dir>' --output '{aggregate_path}'",
                ],
            }
        load_aggregate(aggregate_path, configuration, plan, snapshot)
        return {
            "ok": True,
            "state": "COMMIT_REQUIRED",
            "next": [
                f"python3 <skill>/cli/run.py commit --input '{args.input.resolve()}' --snapshot '{snapshot_path}' --plan '{plan_path}' --aggregate '{aggregate_path}' --live-readback '<post-relocation-readback.json>' --authorization 'approval:<cutover-approval>' --output '{record_path}'"
            ],
        }
    if fence.get("state") == "BLOCKED":
        if not record_path.is_file():
            raise RelocationError("BLOCKED fence lacks the relocation record")
        record = load_typed(record_path, RECORD_SCHEMA, "record_digest", "relocation record")
        return {
            "ok": True,
            "state": "POST_COMMIT_VERIFY_REQUIRED",
            "record_digest": record["record_digest"],
            "next": [
                f"python3 <skill>/cli/capture_target_readback.py --input '{args.input.resolve()}' --control-db '<control-authority.sqlite3>' --output-dir '<new-post-commit-readback-dir>'",
                f"python3 <skill>/cli/run.py verify --record '{record_path}' --live-readback '<new-post-commit-readback-dir>/target-readback.json'",
            ],
        }
    if fence.get("state") == "COMMITTED":
        return {
            "ok": True,
            "state": "ORCHESTRATOR_RELOCATION_VERIFIED",
            "next": [],
        }
    raise RelocationError("relocation fence state is invalid")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--state-root", type=Path, required=True)
    prepare.add_argument("--migration-receipt", type=Path, required=True)
    prepare.add_argument("--target-profile", required=True)
    prepare.add_argument("--target-inventory", type=Path, required=True)
    prepare.add_argument("--project-scope", choices=("all", "explicit", "explicitly-empty"), default="all")
    prepare.add_argument("--project", nargs=2, action="append", default=[], metavar=("REPOSITORY_IDENTITY", "PROJECT_SUBPATH"))
    prepare.add_argument("--output-dir", type=Path, required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("--input", type=Path, required=True)
    capture.add_argument("--live-readback", type=Path, required=True)
    capture.add_argument("--snapshot", type=Path, required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--input", type=Path, required=True)
    plan.add_argument("--snapshot", type=Path, required=True)
    plan.add_argument("--plan", type=Path, required=True)
    fence = commands.add_parser("fence")
    fence.add_argument("--input", type=Path, required=True)
    fence.add_argument("--plan", type=Path, required=True)
    fence.add_argument("--snapshot", type=Path, required=True)
    fence.add_argument("--live-readback", type=Path, required=True)
    fence.add_argument("--authorization", required=True)
    receipt = commands.add_parser("receipt")
    receipt.add_argument("--evidence", type=Path, required=True)
    receipt.add_argument("--state-root", type=Path, required=True)
    receipt.add_argument("--runtime-receipt", type=Path, action="append", default=[])
    receipt.add_argument("--output", type=Path, required=True)
    aggregate = commands.add_parser("aggregate")
    aggregate.add_argument("--input", type=Path, required=True)
    aggregate.add_argument("--snapshot", type=Path, required=True)
    aggregate.add_argument("--plan", type=Path, required=True)
    aggregate.add_argument("--intent", type=Path, required=True)
    aggregate.add_argument("--foundation-manifest", type=Path, required=True)
    aggregate.add_argument("--server-manifest", type=Path, required=True)
    aggregate.add_argument("--project-receipt-dir", type=Path, required=True)
    aggregate.add_argument("--output", type=Path, required=True)
    commit = commands.add_parser("commit")
    commit.add_argument("--input", type=Path, required=True)
    commit.add_argument("--snapshot", type=Path, required=True)
    commit.add_argument("--plan", type=Path, required=True)
    commit.add_argument("--aggregate", type=Path, required=True)
    commit.add_argument("--live-readback", type=Path, required=True)
    commit.add_argument("--authorization", required=True)
    commit.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--record", type=Path, required=True)
    verify.add_argument("--live-readback", type=Path, required=True)
    status = commands.add_parser("status")
    status.add_argument("--input", type=Path, required=True)
    status.add_argument("--snapshot", type=Path)
    status.add_argument("--plan", type=Path)
    status.add_argument("--aggregate", type=Path)
    status.add_argument("--record", type=Path)
    next_command = commands.add_parser("next")
    next_command.add_argument("--input", type=Path, required=True)
    next_command.add_argument("--snapshot", type=Path)
    next_command.add_argument("--plan", type=Path)
    next_command.add_argument("--aggregate", type=Path)
    next_command.add_argument("--record", type=Path)
    return root


def main() -> int:
    args = parser().parse_args()
    handlers = {
        "prepare": command_prepare,
        "capture": command_capture,
        "plan": command_plan,
        "fence": command_fence,
        "receipt": command_receipt,
        "aggregate": command_aggregate,
        "commit": command_commit,
        "verify": command_verify,
        "status": command_status,
        "next": command_status,
    }
    try:
        print(json.dumps(handlers[args.command](args), ensure_ascii=False, sort_keys=True))
        return 0
    except StateBundleError as error:
        print(json.dumps({"ok": False, "error": "ORCHESTRATOR_RELOCATION_FAILED", "detail": f"{error.code}: {error}"}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    except (OSError, StateError, RelocationError, KeyError, TypeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": "ORCHESTRATOR_RELOCATION_FAILED", "detail": str(error)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
