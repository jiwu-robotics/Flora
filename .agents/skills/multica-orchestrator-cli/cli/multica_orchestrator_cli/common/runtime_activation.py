"""Shared Runtime activation primitives for primary and additional-host releases.

This module owns neither the Dispatch control database nor lifecycle policy.  It
constructs the unchanged RuntimeBinding.v1 / receipt / ACTIVE-release wire
objects and uses ``dispatch_runtime`` for all local authority publication.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from multica_state_bundle.handoff import canonical_json, digest_bytes
from multica_state_bundle.identities import utc_now
from multica_state_bundle.storage import atomic_bytes
from multica_orchestrator_cli.common.dispatch_runtime import (
    ACTIVE_RELEASE_SCHEMA,
    ACTIVATION_FENCE_SCHEMA,
    RUNTIME_BINDING_SCHEMA,
    DispatchRuntimeError,
    authority_lock,
    read_active_release,
    read_runtime_binding,
    runtime_state_root,
    write_runtime_binding,
)
from multica_orchestrator_cli.common.runtime_capability import (
    RuntimeCapabilityEvidenceError,
    runtime_capabilities,
    runtime_capability_revision,
)

ACTIVATION_RECEIPT_SCHEMA = "multica-orchestrator.runtime-activation-receipt.v2"
ACTIVATION_RECEIPT_WIRE = {
    "algorithm": "sha256",
    "canonicalization": "json-compact-sorted-utf8-v1",
    "embedded_field": "receipt_digest",
}
AGGREGATE_SCHEMA_V1 = "multica-orchestrator.activation-aggregate.v1"
AGGREGATE_SCHEMA_V2 = "multica-orchestrator.activation-aggregate.v2"


class RuntimeActivationError(ValueError):
    """Runtime activation evidence or publication is unsafe."""


def _records(value: Any, label: str) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        result = value
    elif isinstance(value, Mapping) and isinstance(value.get("items"), list):
        result = value["items"]
    elif isinstance(value, Mapping) and isinstance(value.get("data"), list):
        result = value["data"]
    else:
        raise RuntimeActivationError(f"{label} must be an array")
    if not all(isinstance(item, Mapping) for item in result):
        raise RuntimeActivationError(f"{label} contains an invalid record")
    return result


def _resource_values(item: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = item.get("resource_ref")
    return nested if isinstance(nested, Mapping) else item


def local_directory_resource_identity(item: Mapping[str, Any]) -> tuple[Any, Any] | None:
    """Return a local-directory's stable path/daemon identity, if present."""
    if item.get("type", item.get("resource_type")) != "local_directory":
        return None
    attributes = _resource_values(item)
    return (
        attributes.get("local_path", attributes.get("path")),
        attributes.get("daemon_id", attributes.get("daemon_ref")),
    )


def local_directory_execution_mode(item: Mapping[str, Any]) -> Any:
    attributes = _resource_values(item)
    return attributes.get("execution_mode")


def select_local_directory_resource(
    resources: Any, *, root: str, daemon_ref: str
) -> dict[str, Any]:
    """Classify one exact Runtime checkout resource without selecting by order."""
    records = _records(resources, "Project resource list")
    exact = [item for item in records if local_directory_resource_identity(item) == (root, daemon_ref)]
    conflicts = [
        item for item in records
        if (identity := local_directory_resource_identity(item)) is not None
        and identity != (root, daemon_ref)
        and (identity[0] == root or identity[1] == daemon_ref)
    ]
    if len(exact) > 1:
        return {"state": "AMBIGUOUS", "resources": exact}
    if conflicts:
        return {"state": "CONFLICTING", "resources": conflicts}
    if not exact:
        return {"state": "ABSENT", "resource": None}
    resource = exact[0]
    return {
        "state": "EXACT_WORKTREE" if local_directory_execution_mode(resource) == "worktree" else "EXACT_WRONG_MODE",
        "resource": resource,
    }


def ensure_local_directory(
    *,
    resources_before: Any,
    project_ref: str,
    root: str,
    daemon_ref: str,
    run_multica: Callable[[Sequence[str]], Any],
) -> dict[str, Any]:
    """Create or repair only the exact Project local-directory resource."""
    observed = select_local_directory_resource(resources_before, root=root, daemon_ref=daemon_ref)
    state = observed["state"]
    if state in {"AMBIGUOUS", "CONFLICTING"}:
        raise RuntimeActivationError(f"local-directory resource is {state.lower()}")
    if state == "EXACT_WORKTREE":
        return {"state": "ALREADY_PRESENT", "resource": observed["resource"]}
    if state == "ABSENT":
        run_multica((
            "project", "resource", "add", project_ref, "--type", "local_directory",
            "--local-path", root, "--daemon-id", daemon_ref, "--execution-mode", "worktree",
        ))
        operation = "ADDED"
    else:
        resource = observed["resource"]
        resource_ref = resource.get("id", resource.get("resource_id"))
        if not isinstance(resource_ref, str) or not resource_ref:
            raise RuntimeActivationError("exact local-directory resource ref is invalid")
        run_multica((
            "project", "resource", "update", project_ref, resource_ref,
            "--execution-mode", "worktree",
        ))
        operation = "UPDATED"
    after = select_local_directory_resource(
        run_multica(("project", "resource", "list", project_ref)), root=root, daemon_ref=daemon_ref
    )
    if after["state"] != "EXACT_WORKTREE":
        raise RuntimeActivationError("local-directory worktree postcondition failed")
    return {"state": operation, "resource": after["resource"]}


def verify_activation_target(
    *,
    project_bundle: Any,
    candidate: Mapping[str, Any],
    server: Mapping[str, Any],
    profile: str,
    account_ref: str,
    repository_url: str,
    repository_root: str,
    project_subpath: str,
    runtime_alias: str,
    runtime_ref: str,
    daemon_ref: str,
    command_profile: str,
    run_multica: Callable[[Sequence[str]], Any],
    run_process: Callable[..., Any],
) -> dict[str, Any]:
    """Perform the common non-mutating local Runtime evidence checks.

    Stage code supplies its authenticated Multica/process adapters.  This keeps
    policy and transport at the stage boundary while preventing first-activation
    from diverging from additional-host checks.
    """
    runtimes = _records(run_multica(("runtime", "list")), "Runtime list")
    matches = [
        item for item in runtimes
        if item.get("id", item.get("runtime_id")) == runtime_ref
        and item.get("daemon_id", item.get("daemon_ref")) == daemon_ref
        and item.get("status") == "online"
    ]
    if len(matches) != 1:
        raise RuntimeActivationError("Runtime readback differs")
    try:
        observed_capability_revision = runtime_capability_revision(matches[0])
        if "local-worktree-v1" not in runtime_capabilities(matches[0]):
            raise RuntimeActivationError("Runtime lacks local-worktree-v1")
    except RuntimeCapabilityEvidenceError as error:
        raise RuntimeActivationError(str(error)) from error
    policy = project_bundle.artifacts["runtime-target-policy"]
    targets = [
        item for group in ("required_runtimes", "optional_runtimes")
        for item in policy[group] if item["runtime_alias"] == runtime_alias
    ]
    if len(targets) != 1 or targets[0].get("required_capability_revision") != observed_capability_revision:
        raise RuntimeActivationError("Runtime capability revision differs from Project policy")
    if targets[0].get("command_profile") != command_profile:
        raise RuntimeActivationError("Runtime command profile differs from Project policy")
    resources = run_multica(("project", "resource", "list", project_bundle.artifacts["project-binding"]["project_ref"]))
    selection = select_local_directory_resource(resources, root=repository_root, daemon_ref=daemon_ref)
    if selection["state"] != "EXACT_WORKTREE":
        raise RuntimeActivationError("local-directory worktree resource is absent")
    resource = selection["resource"]
    resource_ref = resource.get("id", resource.get("resource_id"))
    if not isinstance(resource_ref, str) or not resource_ref:
        raise RuntimeActivationError("local-directory resource ref is invalid")
    return {
        "runtime_alias": runtime_alias,
        "runtime_ref": runtime_ref,
        "daemon_ref": daemon_ref,
        "profile": profile,
        "account_ref": account_ref,
        "repository_url": repository_url,
        "repository_root": repository_root,
        "project_subpath": project_subpath,
        "command_profile": command_profile,
        "local_directory_resource_ref": resource_ref,
        "observed_capability_revision": observed_capability_revision,
        "runtime_readback_digest": digest_bytes(canonical_json(matches[0])),
        "project_resources_digest": digest_bytes(canonical_json(resources)),
        "candidate_digest": candidate.get("release_candidate_digest"),
        "server_ref": server.get("server_ref"),
    }


def build_active_release(
    *,
    candidate: Mapping[str, Any],
    candidate_digest: str,
    project_bundle: Any,
    aggregate: Mapping[str, Any],
    authorization_ref: str,
) -> dict[str, Any]:
    """Build the immutable ActiveProjectRelease.v2 wire object."""
    project = project_bundle.artifacts["project-binding"]
    release = {
        "schema": ACTIVE_RELEASE_SCHEMA,
        "deployment_key": candidate.get("deployment_key", project["deployment_key"]),
        "relocation_intent_digest": candidate.get("relocation_intent_digest"),
        "project_key": candidate["project_key"],
        "generation": candidate["generation"],
        "release_candidate_digest": candidate_digest,
        "project_bundle_manifest_digest": project_bundle.manifest_digest,
        "project_binding_digest": project_bundle.manifest["artifacts"]["project-binding"]["digest"],
        "runtime_capability_digest": candidate["runtime_capability_digest"],
        "dispatch_contract_digest": candidate["dispatch_contract_digest"],
        "native_squad_dispatch_digest": candidate["native_squad_dispatch_digest"],
        "activation_aggregate_digest": aggregate["aggregate_digest"],
        "previous_release_digest": candidate.get("previous_release_digest"),
        "predecessor": candidate.get("predecessor"),
        "authorization_ref": authorization_ref,
        "state": "ACTIVE",
        "activated_at": utc_now(),
    }
    release["release_digest"] = digest_bytes(canonical_json(release))
    return release


def _dispatch_root(cas_root: Path) -> Path:
    """Dispatch controls are owned by its Runtime-local state root, not CAS layout."""
    del cas_root
    return runtime_state_root()


def build_release_publication(
    *,
    configuration: Mapping[str, Any],
    project_binding: Mapping[str, Any],
    release: Mapping[str, Any],
    candidate: Mapping[str, Any],
    receipt: Mapping[str, Any],
    target: Mapping[str, Any],
) -> dict[str, Any]:
    """Construct a digest-bound Dispatch publication for one Runtime."""
    cas_root = Path(str(target["state_root"])).expanduser().resolve()
    daemon_hash = hashlib.sha256(str(target["daemon_ref"]).encode("utf-8")).hexdigest()
    binding = {
        "schema": RUNTIME_BINDING_SCHEMA,
        "server_kind": configuration["server"]["kind"],
        "server_ref": configuration["server"]["ref"],
        "workspace_ref": configuration["server"]["workspace_ref"],
        "deployment_key": project_binding["deployment_key"],
        "project_key": project_binding["project_key"],
        "project_ref": project_binding["project_ref"],
        "repository_ref": project_binding.get("repository_ref", project_binding["repository_identity"]),
        "daemon_ref": target["daemon_ref"],
        "runtime_alias": target["runtime_alias"],
        "runtime_ref": target["runtime_ref"],
        "consumer_profile": target["profile"],
        "cas_root": str(cas_root),
        "release_root": str(cas_root / "releases" / project_binding["project_key"].split(":", 1)[1]),
        "control_db": str(_dispatch_root(cas_root) / "authorities" / project_binding["deployment_key"].split(":", 1)[1] / daemon_hash / "control.sqlite3"),
        "local_directory_resource_ref": receipt["local_directory_resource_ref"],
        "repository_root": target["repository_root"],
        "project_subpath": configuration["repository"]["project_subpath"],
    }
    aggregate = receipt.get("activation_aggregate")
    if not isinstance(aggregate, Mapping):
        raise RuntimeActivationError("receipt does not carry an activation aggregate")
    return {
        "schema": "multica-orchestrator-dispatch.release-publication.v1",
        "runtime_binding": binding,
        "release": dict(release),
        "release_candidate": dict(candidate),
        "activation_aggregate": dict(aggregate),
        "previous_release_digest": release["previous_release_digest"],
        "transaction_digest": digest_bytes(canonical_json({
            "project_key": project_binding["project_key"],
            "release_digest": release["release_digest"],
            "aggregate_digest": aggregate["aggregate_digest"],
            "runtime_alias": target["runtime_alias"],
        })),
        "legacy_control_store": None,
    }


def publish_local_release(publication: Mapping[str, Any]) -> dict[str, Any]:
    """Atomically publish a verified local ACTIVE pointer and Runtime binding."""
    binding = publication["runtime_binding"]
    release = publication["release"]
    release_root = Path(str(binding["release_root"])).expanduser().resolve()
    release_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    fence_path = release_root / "activation-pending.json"
    fence = {
        "schema": ACTIVATION_FENCE_SCHEMA,
        "project_key": binding["project_key"],
        "previous_release_digest": publication["previous_release_digest"],
        "release_digest": release["release_digest"],
        "transaction_digest": publication["transaction_digest"],
    }
    with authority_lock(Path(str(binding["control_db"]))):
        active_pointer = release_root / "active.json"
        current_release_digest = None
        if active_pointer.exists():
            active = read_active_release(Path(str(binding["cas_root"])), str(binding["project_key"]))
            current_release_digest = active["release_digest"]
            if current_release_digest == release["release_digest"]:
                existing = read_runtime_binding(
                    str(binding["server_kind"]), str(binding["server_ref"]),
                    str(binding["workspace_ref"]), str(binding["project_ref"]),
                )
                if {key: existing[key] for key in binding} != dict(binding):
                    raise RuntimeActivationError("DISPATCH_AUTHORITY_CONFLICT")
                return {"state": "ALREADY_ACTIVE", "active_pointer": str(active_pointer)}
            if (
                publication["previous_release_digest"] != current_release_digest
                or release.get("previous_release_digest") != current_release_digest
                or release["generation"] <= active["release"]["generation"]
            ):
                raise RuntimeActivationError("active release compare-and-swap precondition failed")
        atomic_bytes(fence_path, json.dumps(fence, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        immutable = release_root / f"generation-{release['generation']}-{release['release_digest'].split(':', 1)[1]}.json"
        atomic_bytes(immutable, json.dumps(release, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        pointer = {
            "schema": "multica-orchestrator-migrate.active-pointer.v1",
            "project_key": binding["project_key"],
            "generation": release["generation"],
            "release_digest": release["release_digest"],
            "release_path": str(immutable),
        }
        atomic_bytes(active_pointer, json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        write_runtime_binding(binding)
        observed = read_active_release(Path(str(binding["cas_root"])), str(binding["project_key"]))
        if observed["release_digest"] != release["release_digest"]:
            raise RuntimeActivationError("ACTIVE release readback differs")
        fence_path.unlink()
    return {"state": "ACTIVE", "active_pointer": str(active_pointer), "release_digest": release["release_digest"]}
