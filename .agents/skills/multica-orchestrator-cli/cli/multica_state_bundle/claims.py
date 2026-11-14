"""Immediate project mutation claims with fail-closed stale-claim recovery."""
from __future__ import annotations

import fcntl
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from .errors import StateBundleError
from .generations import validate_generation
from .namespaces import resolve_namespace
from .storage import atomic_json, read_private_object, require_private_directory

CLAIM_SCHEMA = "multica-state-bundle.mutation-claim.v1"

_THREAD_LOCKS: dict[Path, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()
_HELD_LOCKS: dict[str, tuple[Path, threading.Lock, BinaryIO]] = {}


def _claim_path(directory: Path) -> Path:
    return directory / "claim.json"


def _lock_path(directory: Path) -> Path:
    return directory / "claim.lock"


def _thread_lock(path: Path) -> threading.Lock:
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(path, threading.Lock())


def _acquire_lock(directory: Path) -> tuple[Path, threading.Lock, BinaryIO]:
    """Acquire an immediate cross-process mutation fence without waiting."""
    private_directory = require_private_directory(directory)
    path = _lock_path(private_directory)
    guard = _thread_lock(path)
    if not guard.acquire(blocking=False):
        raise StateBundleError(
            "MUTATION_IN_PROGRESS",
            "another mutation owns the selected project namespace",
            "Wait for the active lifecycle operation to complete or use recover after its writer is proven inactive.",
        )
    stream: BinaryIO | None = None
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        os.chmod(path, 0o600)
        stream = os.fdopen(descriptor, "r+b")
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return path, guard, stream
    except (OSError, BlockingIOError) as error:
        if stream is not None:
            stream.close()
        guard.release()
        raise StateBundleError(
            "MUTATION_IN_PROGRESS",
            "another mutation owns the selected project namespace",
            "Wait for the active lifecycle operation to complete or use recover after its writer is proven inactive.",
        ) from error


def _release_lock(lock: tuple[Path, threading.Lock, BinaryIO]) -> None:
    _, guard, stream = lock
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        stream.close()
        guard.release()


def _inactive(owner: object) -> bool:
    if not isinstance(owner, dict) or not isinstance(owner.get("pid"), int):
        return False
    try:
        os.kill(owner["pid"], 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _claim(directory: Path) -> dict[str, Any] | None:
    path = _claim_path(directory)
    return read_private_object(path, CLAIM_SCHEMA, "mutation claim") if path.exists() else None


def acquire_claim(namespace, operation: str, expected_generation: int | None = None) -> dict[str, Any]:
    if not operation or not isinstance(operation, str):
        raise StateBundleError(
            "GENERATION_INTEGRITY_INVALID",
            "mutation operation kind is invalid",
            "Use a named lifecycle operation.",
        )
    lock = _acquire_lock(namespace.directory)
    try:
        existing = _claim(namespace.directory)
        if existing is not None and existing.get("outcome") == "IN_PROGRESS":
            raise StateBundleError(
                "MUTATION_IN_PROGRESS",
                "an incomplete mutation claim remains for the selected project namespace",
                "Run recover only after its writer is proven inactive.",
            )
        claim = {
            "schema": CLAIM_SCHEMA,
            "project_key": namespace.project_key,
            "claim_id": str(uuid.uuid4()),
            "operation_kind": operation,
            "owner": {"pid": os.getpid()},
            "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "expected_generation": expected_generation,
            "outcome": "IN_PROGRESS",
        }
        atomic_json(_claim_path(namespace.directory), claim)
        _HELD_LOCKS[claim["claim_id"]] = lock
        return claim
    except BaseException:
        _release_lock(lock)
        raise


def release_claim(namespace, claim: dict[str, Any], outcome: str) -> None:
    if outcome not in {"PUBLISHED", "FAILED", "BLOCKED", "RECOVERED"}:
        raise StateBundleError("GENERATION_INTEGRITY_INVALID", "claim outcome is invalid", "Use a terminal lifecycle claim outcome.")
    claim_id = claim.get("claim_id")
    if not isinstance(claim_id, str):
        raise StateBundleError("GENERATION_INTEGRITY_INVALID", "claim identity is invalid", "Use the acquired mutation claim.")
    lock = _HELD_LOCKS.pop(claim_id, None)
    if lock is None:
        raise StateBundleError(
            "MUTATION_IN_PROGRESS",
            "the current process does not own the mutation claim",
            "Inspect the active project claim before mutating lifecycle state.",
        )
    try:
        current = _claim(namespace.directory)
        if current is None or current.get("claim_id") != claim_id:
            raise StateBundleError("MUTATION_IN_PROGRESS", "claim ownership changed", "Inspect the active project claim.")
        current["outcome"] = outcome
        atomic_json(_claim_path(namespace.directory), current)
    finally:
        _release_lock(lock)


def recover_namespace(*, state_root, workspace_key_value, repository, subpath, stage=None) -> dict[str, Any]:
    namespace = resolve_namespace(state_root=state_root, workspace_key_value=workspace_key_value, repository=repository, subpath=subpath)
    lock = _acquire_lock(namespace.directory)
    try:
        claim = _claim(namespace.directory)
        if claim is None or claim.get("outcome") != "IN_PROGRESS" or not _inactive(claim.get("owner")):
            raise StateBundleError("RECOVERY_WRITER_ACTIVE", "the mutation writer is still active or cannot be proven inactive", "Leave the claim blocked and resolve the active writer.")
        if stage is not None:
            validate_generation(namespace.root, namespace.project_key, stage)
        claim["outcome"] = "RECOVERED"
        atomic_json(_claim_path(namespace.directory), claim)
        return {
            "schema": "multica-state-bundle.recovery-evidence.v1",
            "project_key": namespace.project_key,
            "claim_id": claim["claim_id"],
            "writer_inactive": True,
            "state_complete": True,
            "result": "RECOVERED",
        }
    finally:
        _release_lock(lock)
