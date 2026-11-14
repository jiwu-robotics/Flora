#!/usr/bin/env python3
"""Verify a Project binding and atomically activate its selected primary Runtime."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

from binding_common import (
    InputError,
    github_repository_slug,
    load_input,
    load_server_bundle,
    run_multica,
    server_handoff_errors,
    validate_binding_manifest,
    validate_portable_config,
)
from multica_state_bundle.bundle_store import BundleStore
from multica_state_bundle.claims import acquire_claim, release_claim
from multica_state_bundle.errors import StateBundleError
from multica_state_bundle.handoff import BundleError, write_bundle
from multica_state_bundle.identities import DeploymentIndex, StateError, StagePointers, canonical_json, digest_bytes, utc_now
from multica_state_bundle.namespaces import create_namespace
from multica_state_bundle.relocations import hold_relocation_mutation_guard, release_relocation_mutation_guard
from multica_orchestrator_cli.common.dispatch_runtime import DispatchRuntimeError
from multica_state_bundle.storage import atomic_bytes
from multica_orchestrator_cli.common.dispatch_runtime import read_active_release, read_runtime_binding
from multica_orchestrator_cli.common.runtime_activation import (
    ACTIVATION_RECEIPT_SCHEMA,
    ACTIVATION_RECEIPT_WIRE,
    AGGREGATE_SCHEMA_V1,
    RuntimeActivationError,
    build_active_release,
    build_release_publication,
    publish_local_release,
    verify_activation_target,
)


def encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _required_configs(root: Path, manifest: Path, configuration: Mapping[str, Any], handoff: Mapping[str, Any]) -> tuple[dict[str, str], str]:
    expected_binding = root / ".multica" / "agents" / "orchestrator-binding.yaml"
    paths = {
        "issue_tracker": root / ".multica" / "agents" / "issue-tracker.md",
        "triage_mapping": root / ".multica" / "agents" / "triage-mapping.md",
        "domain_mapping": root / ".multica" / "agents" / "domain.md",
    }
    digests: dict[str, str] = {}
    for name, path in paths.items():
        if not path.is_file():
            raise InputError(f"{name} portable configuration is missing")
        validate_portable_config(path, path.name)
        digests[name] = digest_bytes(path.read_bytes())
    if not manifest.is_file() or manifest.resolve() != expected_binding:
        raise InputError("repository binding manifest is missing")
    validate_binding_manifest(manifest, configuration, handoff)
    return digests, digest_bytes(manifest.read_bytes())


def _active_lineage(cas_root: Path, project_key: str) -> tuple[int, str | None]:
    try:
        active = read_active_release(cas_root, project_key)
    except Exception as error:
        if not (cas_root / "releases" / project_key.split(":", 1)[1] / "active.json").exists():
            return 1, None
        raise InputError(f"current active release is invalid: {error}") from error
    return int(active["release"]["generation"]) + 1, str(active["release_digest"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--binding-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-bundle", type=Path, required=True)
    parser.add_argument("--release-candidate", type=Path, required=True)
    parser.add_argument("--authorization-ref", required=True)
    parser.add_argument("--activation-receipt", type=Path, required=True)
    parser.add_argument("--activation-aggregate", type=Path, required=True)
    parser.add_argument("--active-release", type=Path, required=True)
    parser.add_argument("--pointer-state-root", type=Path, required=True)
    parser.add_argument("--multica-command", default="multica")
    parser.add_argument("--generation", type=int)
    parser.add_argument("--previous-release-digest")
    parser.add_argument("--relocation-intent-digest")
    parser.add_argument("--predecessor-project-key")
    parser.add_argument("--predecessor-release-digest")
    args = parser.parse_args()
    relocation_guard: int | None = None
    claim = None
    namespace = None
    outcome = "FAILED"
    try:
        configuration = load_input(args.input)
        operator_root = Path(configuration["bundle_store"]["state_root"]).resolve().parent
        if args.pointer_state_root.expanduser().resolve() != operator_root:
            raise InputError("Project publish roots differ from the input-bound operator state")
        handoff, handoff_digest, server_bundle = load_server_bundle(configuration)
        blockers = server_handoff_errors(configuration, handoff, server_bundle)
        repository = configuration["repository"]
        project = configuration["project"]
        if not repository["registered"] or not repository.get("repository_ref"):
            blockers.append("REPOSITORY_ASSOCIATION_UNVERIFIED")
        if not project["exists"] or not project.get("project_ref"):
            blockers.append("PROJECT_ASSOCIATION_UNVERIFIED")
        if not repository["project_has_resource"] or not repository.get("resource_ref"):
            blockers.append("PROJECT_REPOSITORY_RESOURCE_UNVERIFIED")
        if configuration["local_directory_observation"]["state"] != "EXACT_WORKTREE":
            blockers.append("PRIMARY_LOCAL_DIRECTORY_UNVERIFIED")
        root = Path(repository["root"]).resolve()
        try:
            config_digests, binding_digest = _required_configs(root, args.binding_manifest, configuration, handoff)
        except InputError as error:
            blockers.append(str(error))
            config_digests, binding_digest = {}, ""
        if blockers:
            print(json.dumps({"ok": False, "error": "PROJECT_BINDING_BLOCKED", "blockers": sorted(set(blockers)), "side_effects_not_executed": ["Project bundle", "candidate", "primary ACTIVE release", "Runtime binding", "pointers"]}, sort_keys=True))
            return 1

        runtime = configuration["primary_runtime"]
        store = BundleStore(Path(configuration["bundle_store"]["state_root"]))
        repository_identity = "github:" + github_repository_slug(repository["url"])
        project_key = digest_bytes(canonical_json({"workspace_key": configuration["server"]["workspace_key"], "repository_identity": repository_identity, "project_subpath": repository["project_subpath"]}))
        generation, previous_release_digest = _active_lineage(Path(configuration["bundle_store"]["state_root"]), project_key)
        if args.generation is not None and args.generation != generation:
            raise InputError("generation differs from current active release")
        if args.previous_release_digest is not None and args.previous_release_digest != previous_release_digest:
            raise InputError("previous release digest differs from current active release")
        if bool(args.predecessor_project_key) != bool(args.predecessor_release_digest):
            raise InputError("relocation predecessor requires both Project key and release digest")
        predecessor = ({"relation": "server-relocation", "project_key": args.predecessor_project_key, "release_digest": args.predecessor_release_digest} if args.predecessor_project_key else None)
        relocation_intent_digest = args.relocation_intent_digest or handoff.get("relocation_intent_digest")
        if relocation_intent_digest and predecessor is None:
            raise InputError("relocation intent requires an explicit predecessor Project and release")

        runtime_policy = {"schema": "multica-orchestrator.runtime-target-policy.v4", **configuration["runtime_target_policy"]}
        runtime_policy_digest = digest_bytes(canonical_json(runtime_policy))
        native_squad_dispatch_digest = digest_bytes(canonical_json(runtime_policy["native_squad_dispatch"]))
        command_profiles_digest = digest_bytes(canonical_json(configuration["command_profiles"]))
        runtime_capability_digest = digest_bytes(canonical_json([{"runtime_alias": item["runtime_alias"], "required_capability_revision": item["required_capability_revision"]} for item in sorted(runtime_policy["required_runtimes"], key=lambda item: item["runtime_alias"])]))
        dispatch_root = Path(__file__).resolve().parents[5] / "multica-orchestrator-dispatch"
        dispatch_contract_digest = digest_bytes(canonical_json({relative: digest_bytes((dispatch_root / relative).read_bytes()) for relative in ("SKILL.md", "contracts/run-admission-ref.schema.json", "contracts/integration-check-evidence.schema.json", "contracts/provider-verification.schema.json")}))
        repository_policy = {**{key: configuration["policy"][key] for key in ("main_ref", "develop_ref", "execution_mode", "work_item_id_source", "runtime_branch_authority", "integration_branch_authority", "branch_policy_digest", "repository_command_profile")}, "runtime_capability_digest": runtime_capability_digest, "project_subpath": repository["project_subpath"]}
        package = handoff["package"]
        binding = {
            "schema": "multica-orchestrator-nail-down.project-binding-ref.v12",
            "server_bundle_manifest_digest": server_bundle.manifest_digest,
            "server_orchestration_ref": handoff_digest,
            "deployment_key": configuration["server"]["deployment_key"],
            "relocation_intent_digest": relocation_intent_digest,
            "workspace_key": configuration["server"]["workspace_key"],
            "project_key": project_key,
            "workspace_ref": configuration["server"]["workspace_ref"],
            "project_ref": project["project_ref"],
            "repository_ref": repository["repository_ref"],
            "repository_provider": repository["provider"],
            "repository_identity": repository_identity,
            "repository_resource_ref": repository["resource_ref"],
            "orchestrator_profile": {"id": package["id"], "manifest_digest": package["manifest_digest"], "contract_version": package["contract_version"]},
            "command_profiles": configuration["command_profiles"],
            "repository_policy": repository_policy,
            "command_profiles_digest": command_profiles_digest,
            "runtime_target_policy_digest": runtime_policy_digest,
            "dispatch_contract_digest": dispatch_contract_digest,
            "native_squad_dispatch": runtime_policy["native_squad_dispatch"],
            "repository_configuration": {**config_digests, "binding_manifest_digest": binding_digest},
            "desired_state": {"reissue_spec_digest": None},
            "state": "PROJECT_BOUND",
            "activation_state": "ACTIVE",
            "blockers": [],
            "produced_at": utc_now(),
        }
        verification_spec = {"schema": "multica-orchestrator.project-verification-spec.v8", "deployment_key": binding["deployment_key"], "relocation_intent_digest": relocation_intent_digest, "project_key": project_key, "workspace_ref": binding["workspace_ref"], "project_ref": binding["project_ref"], "repository_identity": repository_identity, "repository_policy_digest": digest_bytes(canonical_json(repository_policy)), "command_profiles_digest": command_profiles_digest, "runtime_target_policy_digest": runtime_policy_digest, "native_squad_dispatch_digest": native_squad_dispatch_digest, "dispatch_contract_digest": dispatch_contract_digest}
        reissue_body = {"schema": "multica-orchestrator.project-reissue-spec.v3", "project_key": project_key, "repository_identity": repository_identity, "project_subpath": repository["project_subpath"], "repository_policy": repository_policy, "command_profiles": configuration["command_profiles"], "runtime_target_policy": runtime_policy, "repository_configuration": binding["repository_configuration"], "dispatch_contract_digest": dispatch_contract_digest}
        reissue_spec = {**reissue_body, "spec_digest": digest_bytes(canonical_json(reissue_body))}
        binding["desired_state"]["reissue_spec_digest"] = digest_bytes(encoded(reissue_spec))
        project_bundle = write_bundle(args.output_bundle, stage="project-binding", artifact_bytes={"project-binding": encoded(binding), "runtime-target-policy": encoded(runtime_policy), "project-verification-spec": encoded(verification_spec), "project-reissue-spec": encoded(reissue_spec)}, produced_at=binding["produced_at"], parents=[{"stage": "server-orchestration", "manifest_digest": server_bundle.manifest_digest}])
        published = store.publish(args.output_bundle, expected_stage="project-binding", expected_manifest_digest=project_bundle.manifest_digest)
        candidate = {"schema": "multica-orchestrator.project-release-candidate.v8", "deployment_key": binding["deployment_key"], "relocation_intent_digest": relocation_intent_digest, "project_key": project_key, "generation": generation, "project_bundle_manifest_digest": project_bundle.manifest_digest, "required_runtime_aliases": [runtime["runtime_alias"]], "native_squad_dispatch_digest": native_squad_dispatch_digest, "runtime_capability_digest": runtime_capability_digest, "dispatch_contract_digest": dispatch_contract_digest, "previous_release_digest": previous_release_digest, "predecessor": predecessor, "repository_identity": repository_identity, "project_subpath": repository["project_subpath"], "produced_at": utc_now()}
        atomic_bytes(args.release_candidate, encoded(candidate))
        candidate_digest = digest_bytes(args.release_candidate.read_bytes())

        evidence = verify_activation_target(project_bundle=published, candidate={**candidate, "release_candidate_digest": candidate_digest}, server=handoff, profile=configuration["server"]["profile"], account_ref=configuration["server"]["account_ref"], repository_url=repository["url"], repository_root=repository["root"], project_subpath=repository["project_subpath"], runtime_alias=runtime["runtime_alias"], runtime_ref=runtime["runtime_ref"], daemon_ref=runtime["daemon_ref"], command_profile=runtime_policy["required_runtimes"][0]["command_profile"], run_multica=lambda command: run_multica(configuration, args.multica_command, list(command)), run_process=lambda *_args, **_kwargs: None)
        receipt = {"schema": ACTIVATION_RECEIPT_SCHEMA, "wire": ACTIVATION_RECEIPT_WIRE, "runtime_alias": runtime["runtime_alias"], "project_key": project_key, "generation": generation, "release_candidate_digest": candidate_digest, "project_bundle_manifest_digest": project_bundle.manifest_digest, "native_squad_dispatch_digest": native_squad_dispatch_digest, "workspace_ref": binding["workspace_ref"], "runtime_ref": runtime["runtime_ref"], "daemon_ref": runtime["daemon_ref"], "repository_identity": repository_identity, "command_profile": evidence["command_profile"], "local_directory_resource_ref": evidence["local_directory_resource_ref"], "execution_mode": "worktree", "worktree_capability_revision": evidence["observed_capability_revision"], "verification": {"runtime_readback_digest": evidence["runtime_readback_digest"], "project_resources_digest": evidence["project_resources_digest"], "execution_mode": "worktree", "worktree_capability_revision": evidence["observed_capability_revision"]}, "state": "ACTIVATED", "verified_at": utc_now()}
        receipt["receipt_digest"] = digest_bytes(canonical_json(receipt))
        aggregate = {"schema": AGGREGATE_SCHEMA_V1, "project_key": project_key, "generation": generation, "release_candidate_digest": candidate_digest, "project_bundle_manifest_digest": project_bundle.manifest_digest, "native_squad_dispatch_digest": native_squad_dispatch_digest, "required_runtime_aliases": [runtime["runtime_alias"]], "receipts": [receipt], "optional_failures": [], "state": "VERIFIED", "aggregated_at": utc_now()}
        aggregate["aggregate_digest"] = digest_bytes(canonical_json(aggregate))
        publication_receipt = {**receipt, "activation_aggregate": aggregate}
        release = build_active_release(candidate=candidate, candidate_digest=candidate_digest, project_bundle=published, aggregate=aggregate, authorization_ref=args.authorization_ref)
        target = {"state_root": configuration["bundle_store"]["state_root"], "daemon_ref": runtime["daemon_ref"], "runtime_alias": runtime["runtime_alias"], "runtime_ref": runtime["runtime_ref"], "profile": configuration["server"]["profile"], "repository_root": repository["root"]}
        publication = build_release_publication(configuration=configuration, project_binding=binding, release=release, candidate=candidate, receipt=publication_receipt, target=target)
        activation_store = (
            Path(configuration["bundle_store"]["state_root"])
            / "releases" / project_key.split(":", 1)[1] / "activation"
        )
        activation_store.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_bytes(activation_store / f"primary-receipt-{receipt['receipt_digest'].split(':', 1)[1]}.json", encoded(receipt))
        atomic_bytes(activation_store / f"aggregate-{aggregate['aggregate_digest'].split(':', 1)[1]}.json", encoded(aggregate))

        relocation_guard = hold_relocation_mutation_guard(operator_root, binding["deployment_key"], relocation_intent_digest, kind="project-publish", subject=project_key)
        namespace = create_namespace(state_root=operator_root, workspace_key_value=binding["workspace_key"], repository=repository["url"], subpath=repository["project_subpath"])
        claim = acquire_claim(namespace, "project-publish", generation)
        publish_local_release(publication)
        active = read_active_release(Path(configuration["bundle_store"]["state_root"]), project_key)
        resolved_binding = read_runtime_binding(binding["server_kind"] if "server_kind" in binding else configuration["server"]["kind"], configuration["server"]["ref"], binding["workspace_ref"], binding["project_ref"])
        if active["release_digest"] != release["release_digest"] or resolved_binding["local_directory_resource_ref"] != receipt["local_directory_resource_ref"]:
            raise RuntimeActivationError("primary activation readback differs")
        atomic_bytes(args.output, encoded(binding))
        atomic_bytes(args.activation_receipt, encoded(receipt))
        atomic_bytes(args.activation_aggregate, encoded(aggregate))
        atomic_bytes(args.active_release, encoded(release))
        pointer_path = StagePointers(operator_root).write_candidate(project_key, project_bundle_manifest_digest=project_bundle.manifest_digest, release_candidate_path=args.release_candidate, release_candidate_digest=candidate_digest, repository_identity_value=repository_identity, project_subpath=repository["project_subpath"], generation=generation, previous_release_digest=previous_release_digest)
        deployment_path = DeploymentIndex(operator_root).publish_project(binding["deployment_key"], project_key, project_bundle.manifest_digest, candidate_digest)
        outcome = "PUBLISHED"
        print(json.dumps({"ok": True, "project_binding_state": "PROJECT_BOUND", "activation_state": "ACTIVE", "primary_runtime_alias": runtime["runtime_alias"], "output": str(args.output), "bundle_manifest_digest": project_bundle.manifest_digest, "release_candidate_digest": candidate_digest, "receipt_digest": receipt["receipt_digest"], "aggregate_digest": aggregate["aggregate_digest"], "active_release_digest": release["release_digest"], "candidate_pointer": str(pointer_path), "deployment_index": str(deployment_path)}, sort_keys=True))
        return 0
    except (StateError, StateBundleError, InputError, RuntimeActivationError, DispatchRuntimeError, BundleError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": "PROJECT_BINDING_INPUT_INVALID", "detail": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    finally:
        if relocation_guard is not None:
            release_relocation_mutation_guard(relocation_guard)
        if claim is not None and namespace is not None:
            release_claim(namespace, claim, outcome)


if __name__ == "__main__":
    raise SystemExit(main())
