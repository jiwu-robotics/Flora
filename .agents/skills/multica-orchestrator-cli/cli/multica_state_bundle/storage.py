"""Owner-only atomic persistence for state-bundle private material."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .errors import StateBundleError


def require_private_directory(path: Path) -> Path:
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise StateBundleError(
            "GENERATION_INTEGRITY_INVALID",
            "private state directory must not be a symlink",
            "Use a private non-symlink directory under the state root.",
        )
    candidate.mkdir(parents=True, exist_ok=True, mode=0o700)
    if candidate.is_symlink() or not candidate.is_dir():
        raise StateBundleError(
            "GENERATION_INTEGRITY_INVALID",
            "private state directory must be a non-symlink directory",
            "Use a private non-symlink directory under the state root.",
        )
    os.chmod(candidate, 0o700)
    return candidate.resolve()


def atomic_bytes(path: Path, content: bytes, *, replace: bool = True) -> Path:
    """Publish owner-only bytes atomically, optionally as an immutable create."""
    candidate = path.expanduser()
    parent = require_private_directory(candidate.parent)
    destination = parent / candidate.name
    if destination.is_symlink():
        raise StateBundleError(
            "GENERATION_INTEGRITY_INVALID",
            f"protected destination must not be a symlink: {destination}",
            "Remove the symlink and recreate the protected state record.",
        )
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, destination)
        else:
            try:
                os.link(temporary, destination)
            except FileExistsError as error:
                raise StateBundleError(
                    "GENERATION_INTEGRITY_INVALID",
                    f"refusing to overwrite immutable protected state: {destination}",
                    "Choose a new generation path or inspect the existing state record.",
                ) from error
        os.chmod(destination, 0o600)
        directory_descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        return destination
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def atomic_json(path: Path, value: Any, *, replace: bool = True) -> Path:
    return atomic_bytes(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n",
        replace=replace,
    )


def read_private_object(path: Path, schema: str, label: str) -> dict[str, Any]:
    if path.is_symlink():
        raise StateBundleError(
            "GENERATION_INTEGRITY_INVALID",
            f"{label} must not be a symlink",
            "Recreate the protected state record.",
        )
    try:
        mode = path.stat().st_mode
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StateBundleError(
            "GENERATION_INTEGRITY_INVALID",
            f"cannot read protected {label}",
            "Recreate the protected state record.",
        ) from error
    if mode & 0o077 or not isinstance(value, dict) or value.get("schema") != schema:
        raise StateBundleError(
            "GENERATION_INTEGRITY_INVALID",
            f"protected {label} is invalid",
            "Recreate the protected state record.",
        )
    return value


def write_protected_material(path: Path, payload: Mapping[str, Any]) -> Path:
    """Persist local-only material; callers must never add it to portable records."""
    return atomic_json(path, dict(payload))
