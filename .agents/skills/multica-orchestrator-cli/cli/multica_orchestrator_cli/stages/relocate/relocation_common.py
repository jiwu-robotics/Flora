"""Relocate-owned parsing, validation, and active-release checks."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from multica_state_bundle.identities import (
    DIGEST,
    canonical_json,
    digest_bytes,
    require_absolute,
)


class RelocationError(ValueError):
    """Relocation input or state violates a fail-closed invariant."""


def digest_object(value: Mapping[str, Any], field: str) -> str:
    return digest_bytes(canonical_json({key: item for key, item in value.items() if key != field}))


def require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or DIGEST.fullmatch(value) is None:
        raise RelocationError(f"{label} must be a SHA-256 digest")
    return value


def read_json(path: Path, label: str) -> dict[str, Any]:
    candidate = path.expanduser()
    if candidate.is_symlink() or not candidate.is_file():
        raise RelocationError(f"{label} must be a regular non-symlink file")
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RelocationError(f"cannot read {label}") from error
    if not isinstance(value, dict):
        raise RelocationError(f"{label} must be a JSON object")
    return value


def verify_embedded_digest(value: Mapping[str, Any], field: str, label: str) -> str:
    declared = require_digest(value.get(field), f"{label}.{field}")
    if digest_object(value, field) != declared:
        raise RelocationError(f"{label} embedded digest differs")
    return declared


def ensure_private_directory(path: Path, *, new: bool = False) -> Path:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        raise RelocationError("private directory must be absolute")
    if candidate.exists():
        if candidate.is_symlink() or not candidate.is_dir():
            raise RelocationError("private directory must be a non-symlink directory")
    else:
        candidate.mkdir(parents=True, exist_ok=False, mode=0o700)
    resolved = candidate.resolve()
    if resolved.stat().st_uid != os.geteuid() or resolved.stat().st_mode & 0o077:
        raise RelocationError("private directory must be owned by the current user with mode 0700")
    if new and any(resolved.iterdir()):
        raise RelocationError("private output directory must be new or empty")
    return resolved


def active_release(state_root: Path, project: str) -> tuple[dict[str, Any], str]:
    require_digest(project, "project_key")
    pointer = read_json(
        state_root / "bundle-store" / "releases" / project.split(":", 1)[1] / "active.json",
        "active release pointer",
    )
    if pointer.get("project_key") != project or pointer.get("state") == "BLOCKED":
        raise RelocationError("active release pointer identity differs")
    release_path = require_absolute(pointer.get("release_path"), "active release path")
    release = read_json(release_path, "active release")
    declared = require_digest(pointer.get("release_digest"), "active release pointer digest")
    unsigned = {key: value for key, value in release.items() if key != "release_digest"}
    wire_digest = digest_bytes(
        json.dumps(unsigned, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    if release.get("schema") != "multica-orchestrator.active-project-release.v2":
        raise RelocationError("active release schema is unsupported")
    if wire_digest != declared:
        raise RelocationError("active release embedded digest mismatch")
    return release, declared
