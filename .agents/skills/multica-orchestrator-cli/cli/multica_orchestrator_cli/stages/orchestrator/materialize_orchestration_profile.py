"""Materialize a verified tier policy from Foundation-bound OMP model readback."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from multica_state_bundle.bundle_store import BundleStore
from multica_state_bundle.identities import DeploymentIndex, StagePointers, StateError, digest_bytes, write_resolution
from multica_state_bundle.storage import atomic_json
from multica_orchestrator_cli.common.provider_models import (
    ProviderModelError,
    query_omp_models,
    resolve_omp_families,
)
from multica_orchestrator_cli.common.profile_session import resolve_profile_session
from multica_orchestrator_cli.common.provider_models import canonical_provider
from prepare_server_application import allocate_run, default_state_root
from server_application_common import load_manifest


ROLE_TIERS: dict[str, dict[str, tuple[str, str]]] = {
    "Lite": {
        "shared-intake": ("Luna", "medium"),
        "workflow-leader": ("Terra", "medium"),
        "commit-policy-reviewer": ("Luna", "low"),
        "feature-loop-guard": ("Luna", "low"),
        "feature-governance-producer": ("Luna", "medium"),
        "feature-requirement-producer": ("Luna", "medium"),
        "feature-requirement-reviewer": ("Luna", "medium"),
        "feature-planning-producer": ("Luna", "medium"),
        "feature-convergence-reviewer": ("Luna", "medium"),
        "feature-core-maker": ("Terra", "medium"),
        "feature-loop-maker": ("Terra", "medium"),
        "feature-reviewer": ("Terra", "high"),
        "feature-loop-checker": ("Terra", "high"),
        "fix-assessor": ("Terra", "medium"),
        "fix-maker": ("Terra", "medium"),
        "fix-verifier": ("Terra", "high"),
    },
    "Pro": {
        "shared-intake": ("Terra", "medium"),
        "workflow-leader": ("Sol", "medium"),
        "commit-policy-reviewer": ("Luna", "low"),
        "feature-loop-guard": ("Luna", "low"),
        "feature-governance-producer": ("Terra", "medium"),
        "feature-requirement-producer": ("Terra", "medium"),
        "feature-requirement-reviewer": ("Terra", "medium"),
        "feature-planning-producer": ("Terra", "medium"),
        "feature-convergence-reviewer": ("Terra", "medium"),
        "feature-core-maker": ("Sol", "medium"),
        "feature-loop-maker": ("Sol", "medium"),
        "feature-reviewer": ("Sol", "high"),
        "feature-loop-checker": ("Sol", "high"),
        "fix-assessor": ("Sol", "medium"),
        "fix-maker": ("Sol", "medium"),
        "fix-verifier": ("Sol", "high"),
    },
    "Max": {
        "shared-intake": ("Terra", "medium"),
        "workflow-leader": ("Sol", "medium"),
        "commit-policy-reviewer": ("Luna", "low"),
        "feature-loop-guard": ("Terra", "medium"),
        "feature-governance-producer": ("Terra", "high"),
        "feature-requirement-producer": ("Terra", "high"),
        "feature-requirement-reviewer": ("Terra", "high"),
        "feature-planning-producer": ("Terra", "high"),
        "feature-convergence-reviewer": ("Terra", "high"),
        "feature-core-maker": ("Sol", "high"),
        "feature-loop-maker": ("Sol", "high"),
        "feature-reviewer": ("Sol", "high"),
        "feature-loop-checker": ("Sol", "high"),
        "fix-assessor": ("Sol", "high"),
        "fix-maker": ("Sol", "high"),
        "fix-verifier": ("Sol", "high"),
    },
}


class MaterializationError(ValueError):
    pass


def tier_profile(tier: str, runtime_alias: str, roles: list[Any], models: Mapping[str, str]) -> dict[str, Any]:
    policy = ROLE_TIERS[tier]
    expected = {role.key for role in roles}
    if set(policy) != expected:
        missing = sorted(expected - set(policy))
        extra = sorted(set(policy) - expected)
        raise MaterializationError(
            f"ORCHESTRATION_POLICY_INPUT_REQUIRED: tier role matrix differs from manifest; missing={missing}, extra={extra}"
        )
    return {
        "schema": "multica-orchestrator.orchestration-profile.v1",
        "name": f"role-tier-{tier.lower()}",
        "collaboration_runtime_alias": runtime_alias,
        "defaults": {"max_concurrent_tasks": 1, "permission_mode": "private"},
        "model_groups": {},
        "roles": {
            role.key: {
                "model": models[policy[role.key][0]],
                "thinking_level": policy[role.key][1],
                "max_concurrent_tasks": 1,
                "permission_mode": "private",
            }
            for role in roles
        },
    }


def resolve_foundation(
    profile: str, workspace: str | None, state_root: Path
) -> tuple[Any, Mapping[str, Any], str, Mapping[str, Any], str]:
    session = resolve_profile_session(profile, workspace)
    deployment = DeploymentIndex(state_root).resolve(
        session.server_kind, session.server_ref, session.workspace_ref
    )
    pointer = StagePointers(state_root).read(
        "workspaces", deployment["workspace_key"], "foundation", "workspace-foundation"
    )
    foundation_digest = pointer["manifest_digest"]
    if foundation_digest != deployment["foundation_manifest_digest"]:
        raise MaterializationError("Foundation pointer differs from the deployment index")
    bundle = BundleStore(state_root / "bundle-store").resolve("workspace-foundation", foundation_digest)
    foundation = bundle.artifacts["workspace-foundation"]
    expected = {
        "server_kind": session.server_kind,
        "server_ref": session.server_ref,
        "workspace_ref": session.workspace_ref,
        "deployment_key": deployment["deployment_key"],
        "workspace_key": deployment["workspace_key"],
    }
    mismatches = [key for key, value in expected.items() if foundation.get(key) != value]
    if mismatches:
        raise MaterializationError(
            "Foundation identity differs from live profile/index: " + ", ".join(mismatches)
        )
    if foundation.get("state") != "WORKSPACE_FOUNDATION_VERIFIED" or foundation.get("blockers"):
        raise MaterializationError("WORKSPACE_FOUNDATION_REQUIRED: foundation is not verified")
    return session, deployment, foundation_digest, foundation, str(pointer["_path"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--workspace")
    parser.add_argument("--runtime-alias", required=True)
    parser.add_argument("--tier", choices=sorted(ROLE_TIERS), default="Pro")
    parser.add_argument("--state-root", type=Path, default=default_state_root())
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[5]
        / "multica-orchestrator-kick-off"
        / "manifests/orchestration-package.yaml",
    )
    args = parser.parse_args()
    try:
        state_root = args.state_root.expanduser().resolve()
        _, deployment, foundation_digest, foundation, pointer_path = resolve_foundation(
            args.profile, args.workspace, state_root
        )
        runtimes = foundation.get("runtime_fleet", {}).get("runtimes")
        if not isinstance(runtimes, list):
            raise MaterializationError("ORCHESTRATION_POLICY_INPUT_REQUIRED: Foundation Runtime fleet is invalid")
        selected = [runtime for runtime in runtimes if isinstance(runtime, Mapping) and runtime.get("alias") == args.runtime_alias]
        if len(selected) != 1:
            raise MaterializationError("ORCHESTRATION_POLICY_INPUT_REQUIRED: collaboration Runtime alias is absent from the Foundation fleet")
        runtime = selected[0]
        if runtime.get("status") != "online" or canonical_provider(str(runtime.get("provider", ""))) != "omp":
            raise MaterializationError("ORCHESTRATION_POLICY_INPUT_REQUIRED: selected Runtime must be an online OMP Runtime")
        roles = load_manifest(args.manifest)
        policy = ROLE_TIERS[args.tier]
        required_thinking = {
            family: {thinking for model_family, thinking in policy.values() if model_family == family}
            for family in ("Luna", "Terra", "Sol")
        }
        catalog = query_omp_models()
        models = resolve_omp_families(catalog, required_thinking)
        run_id, run_root = allocate_run(state_root, "orchestration-profile")
        catalog_path = run_root / "omp-model-catalog.json"
        atomic_json(
            catalog_path,
            {
                "runtime_alias": args.runtime_alias,
                "runtime_ref": runtime.get("runtime_ref"),
                "daemon_ref": runtime.get("daemon_ref"),
                "provider": "omp",
                "models": catalog,
            },
        )
        profile_path = run_root / "orchestration-profile.json"
        atomic_json(profile_path, tier_profile(args.tier, args.runtime_alias, roles, models))
        profile_path.chmod(0o600)
        request = {
            "profile": args.profile,
            "workspace": args.workspace or "profile-current",
            "runtime_alias": args.runtime_alias,
            "tier": args.tier,
        }
        profile_digest = digest_bytes(profile_path.read_bytes())
        catalog_digest = digest_bytes(catalog_path.read_bytes())
        resolution_path = run_root / "profile-resolution.json"
        write_resolution(
            resolution_path,
            run_id=run_id,
            request=request,
            resolved_input=profile_path,
            fields={
                "foundation_manifest_digest": {
                    "source": "cas-pointer",
                    "evidence": pointer_path,
                    "value": foundation_digest,
                },
                "model_catalog": {
                    "source": "omp models --json",
                    "evidence": str(catalog_path),
                    "value": {"digest": catalog_digest, "models": models},
                },
                "orchestration_profile": {
                    "source": "role-tier-matrix",
                    "evidence": str(profile_path),
                    "value": profile_digest,
                },
            },
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "run_id": run_id,
                    "run_root": str(run_root),
                    "profile": str(profile_path),
                    "profile_digest": profile_digest,
                    "resolution": str(resolution_path),
                    "foundation_manifest_digest": foundation_digest,
                    "tier": args.tier,
                    "models": models,
                },
                sort_keys=True,
            )
        )
        return 0
    except (MaterializationError, ProviderModelError, StateError, OSError, KeyError, TypeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": "ORCHESTRATION_POLICY_INPUT_REQUIRED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
