"""Immutable generation records and atomic lifecycle pointer publication."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .errors import StateBundleError
from .identities import DIGEST, STAGES, StagePointers, digest_bytes, read_object, require_absolute, utc_now
from .storage import atomic_json, require_private_directory

GENERATION_SCHEMA = "multica-state-bundle.generation.v1"


def _generation_directory(state_root: Path, project_key_value: str, stage: str) -> Path:
    if DIGEST.fullmatch(project_key_value) is None or stage not in STAGES:
        raise StateBundleError(
            "PROJECT_NAMESPACE_MISMATCH",
            "project generation identity is invalid",
            "Select a validated project identity and lifecycle stage.",
        )
    return require_private_directory(
        require_absolute(state_root, "state root")
        / "projects"
        / project_key_value.split(":", 1)[1]
        / "generations"
        / stage
    )


def _record_path(state_root: Path, project_key_value: str, stage: str, generation: int) -> Path:
    return _generation_directory(state_root, project_key_value, stage) / f"{generation}.json"


def publish_generation(
    *,
    state_root: Path,
    project_key_value: str,
    stage: str,
    manifest_digest: str,
    parent_manifest_digest: str | None = None,
    claim_id: str | None = None,
) -> Mapping[str, Any]:
    """Publish an immutable record before atomically switching the current pointer."""
    if DIGEST.fullmatch(manifest_digest) is None or (
        parent_manifest_digest is not None and DIGEST.fullmatch(parent_manifest_digest) is None
    ):
        raise StateBundleError(
            "GENERATION_INTEGRITY_INVALID",
            "generation digest is invalid",
            "Recreate the lifecycle handoff with a valid immutable manifest.",
        )
    root = require_absolute(state_root, "state root")
    pointers = StagePointers(root)
    try:
        prior = pointers.read("projects", project_key_value, stage, stage)
        generation = int(prior.get("generation", 0)) + 1
    except (OSError, StateBundleError):
        generation = 1
    path = _record_path(root, project_key_value, stage, generation)
    if path.exists():
        raise StateBundleError(
            "GENERATION_INTEGRITY_INVALID",
            "generation record already exists",
            "Create a new lifecycle generation rather than modifying history.",
        )
    record = {
        "schema": GENERATION_SCHEMA,
        "project_key": project_key_value,
        "stage": stage,
        "generation": generation,
        "manifest_digest": manifest_digest,
        "parent_manifest_digest": parent_manifest_digest,
        "claim_id": claim_id,
        "created_at": utc_now(),
    }
    atomic_json(path, record)
    pointer = pointers.write(
        "projects",
        project_key_value,
        stage,
        stage,
        manifest_digest,
        parent_manifest_digest=parent_manifest_digest,
        generation=generation,
    )
    return {**record, "pointer_digest": digest_bytes(pointer.read_bytes())}


def validate_generation(state_root: Path, project_key_value: str, stage: str) -> Mapping[str, Any]:
    """Return the only complete generation currently selected by a pointer."""
    root = require_absolute(state_root, "state root")
    try:
        pointer = StagePointers(root).read("projects", project_key_value, stage, stage)
    except StateBundleError as error:
        raise StateBundleError(
            "GENERATION_INCOMPLETE",
            "current lifecycle pointer has no complete generation",
            "Republish the lifecycle stage from a valid upstream state.",
        ) from error
    generation = pointer.get("generation")
    if not isinstance(generation, int) or generation < 1:
        raise StateBundleError(
            "GENERATION_INCOMPLETE",
            "current lifecycle pointer has no complete generation",
            "Republish the lifecycle stage from a valid upstream state.",
        )
    record = read_object(_record_path(root, project_key_value, stage, generation), "generation record")
    required = {
        "schema": GENERATION_SCHEMA,
        "project_key": project_key_value,
        "stage": stage,
        "generation": generation,
        "manifest_digest": pointer["manifest_digest"],
        "parent_manifest_digest": pointer.get("parent_manifest_digest"),
    }
    if any(record.get(key) != value for key, value in required.items()):
        raise StateBundleError(
            "GENERATION_INTEGRITY_INVALID",
            "generation record differs from its current pointer",
            "Republish the lifecycle stage from a valid upstream state.",
        )
    return {**record, "pointer_digest": pointer["_digest"]}
