"""Portable, parent-linked Multica handoff bundles."""
from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from .errors import BundleError
from .identities import digest_bytes
from .storage import atomic_bytes

BUNDLE_SCHEMA = "multica-orchestrator.handoff-bundle.v2"
MANIFEST_NAME = "manifest.json"
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
ARTIFACT_SPECS = {
    "workspace-foundation": (
        "artifacts/workspace-foundation.json",
        ("multica-orchestrator-link-up.workspace-foundation-ref.v6",),
    ),
    "server-orchestration": (
        "artifacts/server-orchestration.json",
        ("multica-orchestrator.server-orchestration-ref.v10",),
    ),
    "server-verification-spec": (
        "artifacts/server-verification-spec.json",
        ("multica-orchestrator.server-verification-spec.v3",),
    ),
    "server-reissue-spec": (
        "artifacts/server-reissue-spec.json",
        ("multica-orchestrator.server-reissue-spec.v1",),
    ),
    "project-binding": (
        "artifacts/project-binding.json",
        (
            "multica-orchestrator-nail-down.project-binding-ref.v11",
            "multica-orchestrator-nail-down.project-binding-ref.v12",
        ),
    ),
    "runtime-target-policy": (
        "artifacts/runtime-target-policy.json",
        ("multica-orchestrator.runtime-target-policy.v4",),
    ),
    "project-verification-spec": (
        "artifacts/project-verification-spec.json",
        ("multica-orchestrator.project-verification-spec.v8",),
    ),
    "project-reissue-spec": (
        "artifacts/project-reissue-spec.json",
        ("multica-orchestrator.project-reissue-spec.v3",),
    ),
}
STAGE_ARTIFACTS = {
    "workspace-foundation": ("workspace-foundation",),
    "server-orchestration": ("server-orchestration", "server-verification-spec", "server-reissue-spec"),
    "project-binding": ("project-binding", "runtime-target-policy", "project-verification-spec", "project-reissue-spec"),
}
STAGE_PARENTS = {
    "workspace-foundation": (),
    "server-orchestration": ("workspace-foundation",),
    "project-binding": ("server-orchestration",),
}


@dataclass(frozen=True)
class Bundle:
    root: Path
    manifest: Mapping[str, Any]
    manifest_digest: str
    artifacts: Mapping[str, Mapping[str, Any]]
    artifact_bytes: Mapping[str, bytes]

    @property
    def stage(self) -> str:
        return str(self.manifest["stage"])

    @property
    def parents(self) -> tuple[Mapping[str, str], ...]:
        return tuple(self.manifest["parents"])


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"

def require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or DIGEST.fullmatch(value) is None:
        raise BundleError(f"{label} must be a SHA-256 digest")
    return value




def _root(path: Path) -> Path:
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise BundleError(f"bundle path must not be a symlink: {candidate}")
    root = candidate.resolve()
    if not root.is_dir():
        raise BundleError(f"bundle path must be a directory: {root}")
    return root


def _artifact_path(root: Path, relative: str) -> Path:
    parsed = PurePosixPath(relative)
    if parsed.is_absolute() or ".." in parsed.parts or str(parsed) != relative:
        raise BundleError(f"artifact path is not portable: {relative}")
    path = root.joinpath(*parsed.parts)
    if path.is_symlink():
        raise BundleError(f"bundle artifact must not be a symlink: {relative}")
    try:
        path.resolve().relative_to(root)
    except ValueError as error:
        raise BundleError(f"artifact path escapes bundle: {relative}") from error
    return path


def _require_regular_file(path: Path, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise BundleError(f"cannot inspect {label}: {error}") from error
    if not stat.S_ISREG(mode):
        raise BundleError(f"{label} must be a regular file")
    if path.stat().st_nlink != 1:
        raise BundleError(f"{label} must not be hard-linked")


def _validate_entries(root: Path, expected: set[str]) -> None:
    actual: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        try:
            mode = path.lstat().st_mode
        except OSError as error:
            raise BundleError(f"cannot inspect bundle entry {relative}: {error}") from error
        if stat.S_ISLNK(mode):
            raise BundleError(f"bundle entry must not be a symlink: {relative}")
        if not stat.S_ISDIR(mode) and not stat.S_ISREG(mode):
            raise BundleError(f"bundle entry must be a regular file or directory: {relative}")
        actual.add(relative)
    if actual != expected:
        raise BundleError(f"bundle contains unexpected or missing entries: {sorted(actual ^ expected)}")


def _parse_artifact(content: bytes, expected_schemas: Sequence[str], label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BundleError(f"bundle artifact is not valid JSON: {label}") from error
    if not isinstance(value, dict) or value.get("schema") not in expected_schemas:
        raise BundleError(f"bundle artifact {label} must use one of {list(expected_schemas)}")
    return value


def _validate_parents(stage: str, parents: Any) -> tuple[Mapping[str, str], ...]:
    expected_stages = STAGE_PARENTS[stage]
    if not isinstance(parents, list) or len(parents) != len(expected_stages):
        raise BundleError(f"bundle stage {stage} requires parent stages {list(expected_stages)}")
    result: list[Mapping[str, str]] = []
    for expected_stage, parent in zip(expected_stages, parents):
        if not isinstance(parent, dict) or set(parent) != {"stage", "manifest_digest"}:
            raise BundleError("bundle parent descriptor is invalid")
        if parent.get("stage") != expected_stage:
            raise BundleError(f"bundle parent stage must equal {expected_stage}")
        require_digest(parent.get("manifest_digest"), "bundle parent manifest_digest")
        result.append(parent)
    return tuple(result)


def load_bundle(
    path: Path,
    *,
    expected_stage: str | None = None,
    expected_manifest_digest: str | None = None,
) -> Bundle:
    root = _root(path)
    manifest_path = root / MANIFEST_NAME
    if manifest_path.is_symlink():
        raise BundleError("bundle manifest must not be a symlink")
    _require_regular_file(manifest_path, "bundle manifest")
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
    except OSError as error:
        raise BundleError(f"cannot read bundle manifest: {manifest_path}: {error}") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BundleError("bundle manifest is not valid JSON") from error
    manifest_digest = digest_bytes(manifest_bytes)
    if expected_manifest_digest is not None and manifest_digest != expected_manifest_digest:
        raise BundleError(
            f"bundle manifest digest mismatch: expected {expected_manifest_digest}, observed {manifest_digest}"
        )
    expected_fields = {"schema", "stage", "parents", "artifacts", "produced_at"}
    if not isinstance(manifest, dict) or set(manifest) != expected_fields:
        raise BundleError("bundle manifest fields are invalid")
    if manifest.get("schema") != BUNDLE_SCHEMA:
        raise BundleError(f"bundle manifest schema must equal {BUNDLE_SCHEMA}")
    stage = manifest.get("stage")
    if stage not in STAGE_ARTIFACTS or expected_stage is not None and stage != expected_stage:
        raise BundleError(f"bundle stage mismatch: expected {expected_stage}, observed {stage}")
    _validate_parents(stage, manifest.get("parents"))
    if not isinstance(manifest.get("produced_at"), str) or not manifest["produced_at"]:
        raise BundleError("bundle produced_at is required")
    descriptors = manifest.get("artifacts")
    expected_names = set(STAGE_ARTIFACTS[stage])
    if not isinstance(descriptors, dict) or set(descriptors) != expected_names:
        raise BundleError(f"bundle stage {stage} requires artifacts {sorted(expected_names)}")
    expected_files = {MANIFEST_NAME, *(ARTIFACT_SPECS[name][0] for name in expected_names)}
    expected_entries = expected_files | {
        parent.as_posix()
        for relative in expected_files
        for parent in PurePosixPath(relative).parents
        if parent != PurePosixPath(".")
    }
    _validate_entries(root, expected_entries)
    artifacts: dict[str, Mapping[str, Any]] = {}
    artifact_bytes: dict[str, bytes] = {}
    for name in sorted(expected_names):
        descriptor = descriptors[name]
        expected_path, expected_schemas = ARTIFACT_SPECS[name]
        if not isinstance(descriptor, dict) or set(descriptor) != {"path", "schema", "media_type", "digest"}:
            raise BundleError(f"bundle artifact descriptor is invalid: {name}")
        if (
            descriptor.get("path") != expected_path
            or descriptor.get("schema") not in expected_schemas
            or descriptor.get("media_type") != "application/json"
        ):
            raise BundleError(f"bundle artifact descriptor is not canonical: {name}")
        require_digest(descriptor.get("digest"), f"bundle artifact digest for {name}")
        artifact_path = _artifact_path(root, expected_path)
        _require_regular_file(artifact_path, f"bundle artifact {name}")
        content = artifact_path.read_bytes()
        observed = digest_bytes(content)
        if observed != descriptor["digest"]:
            raise BundleError(
                f"bundle artifact digest mismatch for {name}: expected {descriptor['digest']}, observed {observed}"
            )
        artifact_bytes[name] = content
        artifacts[name] = _parse_artifact(content, expected_schemas, name)
    return Bundle(root, manifest, manifest_digest, artifacts, artifact_bytes)


def write_bundle(
    path: Path,
    *,
    stage: str,
    artifact_bytes: Mapping[str, bytes],
    produced_at: str,
    parents: Sequence[Mapping[str, str]] = (),
) -> Bundle:
    if stage not in STAGE_ARTIFACTS:
        raise BundleError(f"unsupported bundle stage: {stage}")
    expected_names = set(STAGE_ARTIFACTS[stage])
    if set(artifact_bytes) != expected_names:
        raise BundleError(f"bundle stage {stage} requires artifacts {sorted(expected_names)}")
    canonical_parents = [dict(parent) for parent in parents]
    _validate_parents(stage, canonical_parents)
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise BundleError(f"bundle output must not be a symlink: {candidate}")
    root = candidate.resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise BundleError(f"bundle output must be a new or empty directory: {root}")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    descriptors: dict[str, dict[str, str]] = {}
    for name in sorted(expected_names):
        relative, schemas = ARTIFACT_SPECS[name]
        content = artifact_bytes[name]
        schema = str(_parse_artifact(content, schemas, name)["schema"])
        descriptors[name] = {
            "path": relative,
            "schema": schema,
            "media_type": "application/json",
            "digest": digest_bytes(content),
        }
        atomic_bytes(_artifact_path(root, relative), content)
    manifest = {
        "schema": BUNDLE_SCHEMA,
        "stage": stage,
        "parents": canonical_parents,
        "artifacts": descriptors,
        "produced_at": produced_at,
    }
    atomic_bytes(root / MANIFEST_NAME, canonical_json(manifest))
    return load_bundle(root, expected_stage=stage)
