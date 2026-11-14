"""Shared relocation mutation journals, fences, and mutation guards."""
from __future__ import annotations

import fcntl
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from .errors import StateError
from .identities import DIGEST, SAFE_NAME, canonical_json, digest_bytes, read_object, utc_now
from .storage import atomic_json, require_private_directory

MUTATION_SEQUENCE_SCHEMA = "multica-orchestrator.mutation-sequence.v1"
MUTATION_JOURNAL_SCHEMA = "multica-orchestrator.mutation-journal.v2"
_MUTATION_RECORDS: dict[int, Path] = {}


def _deployment_hex(deployment_key: str) -> str:
    if DIGEST.fullmatch(deployment_key) is None:
        raise StateError("deployment_key must be a SHA-256 digest")
    return deployment_key.split(":", 1)[1]


def fence_path(state_root: Path, deployment_key: str) -> Path:
    return state_root / "relocations" / "fences" / _deployment_hex(deployment_key) / "current.json"


def mutation_journal_directory(state_root: Path, deployment_key: str) -> Path:
    return state_root / "relocations" / "mutations" / _deployment_hex(deployment_key)


def mutation_sequence_path(state_root: Path, deployment_key: str) -> Path:
    return state_root / "relocations" / "mutation-sequences" / f"{_deployment_hex(deployment_key)}.json"


def _sequence_lock_path(state_root: Path, deployment_key: str) -> Path:
    return state_root / "relocations" / "mutation-sequences" / f"{_deployment_hex(deployment_key)}.lock"


def current_mutation_sequence(state_root: Path, deployment_key: str) -> int:
    path = mutation_sequence_path(state_root, deployment_key)
    if not path.exists():
        return 0
    value = read_object(path, "mutation sequence")
    if (
        value.get("schema") != MUTATION_SEQUENCE_SCHEMA
        or value.get("deployment_key") != deployment_key
        or not isinstance(value.get("sequence"), int)
        or value["sequence"] < 0
    ):
        raise StateError("mutation sequence is invalid")
    return value["sequence"]


def next_mutation_sequence(state_root: Path, deployment_key: str) -> int:
    """Allocate the next sequence under an exclusive deployment-local lock."""
    directory = require_private_directory(_sequence_lock_path(state_root, deployment_key).parent)
    lock_path = directory / _sequence_lock_path(state_root, deployment_key).name
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.chmod(lock_path, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        sequence = current_mutation_sequence(state_root, deployment_key) + 1
        atomic_json(
            mutation_sequence_path(state_root, deployment_key),
            {
                "schema": MUTATION_SEQUENCE_SCHEMA,
                "deployment_key": deployment_key,
                "sequence": sequence,
            },
        )
        return sequence
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _validate_mutation_fields(
    *,
    relocation_intent_digest: str | None,
    kind: str,
    subject: str | None,
) -> None:
    if relocation_intent_digest is not None and DIGEST.fullmatch(relocation_intent_digest) is None:
        raise StateError("relocation_intent_digest must be a SHA-256 digest")
    if SAFE_NAME.fullmatch(kind) is None:
        raise StateError("mutation kind must be shell-independent")
    if subject is not None and (not isinstance(subject, str) or not subject):
        raise StateError("mutation subject must be non-empty")


def record_mutation_start(
    state_root: Path,
    deployment_key: str,
    relocation_intent_digest: str | None,
    *,
    kind: str,
    subject: str | None,
) -> Path:
    _deployment_hex(deployment_key)
    _validate_mutation_fields(
        relocation_intent_digest=relocation_intent_digest, kind=kind, subject=subject
    )
    directory = require_private_directory(mutation_journal_directory(state_root, deployment_key))
    sequence = next_mutation_sequence(state_root, deployment_key)
    path = directory / f"mutation-{sequence:020d}.json"
    atomic_json(
        path,
        {
            "schema": MUTATION_JOURNAL_SCHEMA,
            "deployment_key": deployment_key,
            "relocation_intent_digest": relocation_intent_digest,
            "sequence": sequence,
            "kind": kind,
            "subject": subject,
            "outcome": "IN_PROGRESS",
            "return_code": None,
            "started_at": utc_now(),
            "completed_at": None,
        },
        replace=False,
    )
    return path


def complete_mutation(path: Path, *, outcome: str, return_code: int) -> None:
    entry = read_object(path, "mutation journal entry")
    if entry.get("schema") != MUTATION_JOURNAL_SCHEMA or entry.get("completed_at") is not None:
        raise StateError("mutation journal entry is already complete or invalid")
    if outcome not in {"SUCCEEDED", "FAILED"} or not isinstance(return_code, int):
        raise StateError("mutation outcome or return code is invalid")
    entry.update({"completed_at": utc_now(), "outcome": outcome, "return_code": return_code})
    atomic_json(path, entry)


def record_completed_mutation(
    state_root: Path,
    deployment_key: str,
    *,
    relocation_intent_digest: str | None,
    kind: str,
    subject: str | None,
    outcome: str,
    return_code: int,
) -> dict[str, Any]:
    if outcome not in {"SUCCEEDED", "FAILED"} or not isinstance(return_code, int):
        raise StateError("mutation outcome or return code is invalid")
    path = record_mutation_start(
        state_root,
        deployment_key,
        relocation_intent_digest,
        kind=kind,
        subject=subject,
    )
    complete_mutation(path, outcome=outcome, return_code=return_code)
    return {**read_object(path, "mutation journal entry"), "_path": str(path)}


def mutation_entries(state_root: Path, deployment_key: str, *, require_complete: bool = True) -> list[dict[str, Any]]:
    directory = mutation_journal_directory(state_root, deployment_key)
    entries: list[dict[str, Any]] = []
    if not directory.exists():
        return entries
    if directory.is_symlink() or not directory.is_dir():
        raise StateError("mutation journal must be a non-symlink directory")
    for path in sorted(directory.iterdir()):
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            raise StateError("mutation journal contains an invalid entry")
        entry = read_object(path, "mutation journal entry")
        if entry.get("schema") != MUTATION_JOURNAL_SCHEMA:
            raise StateError("mutation journal schema is invalid")
        expected = {
            "schema", "deployment_key", "relocation_intent_digest", "sequence", "kind", "subject",
            "outcome", "return_code", "started_at", "completed_at",
        }
        sequence = entry.get("sequence")
        if (
            set(entry) != expected
            or entry.get("deployment_key") != deployment_key
            or not isinstance(sequence, int)
            or sequence < 1
            or SAFE_NAME.fullmatch(str(entry.get("kind"))) is None
        ):
            raise StateError("mutation journal entry is invalid")
        if require_complete and entry.get("completed_at") is None:
            raise StateError("RELOCATION_PRECONDITION_CHANGED: mutation completion is unproven")
        entries.append({**entry, "_path": str(path)})
    return entries


def mutation_barrier(
    state_root: Path,
    deployment_key: str,
    *,
    require_complete: bool = True,
) -> dict[str, Any]:
    entries = mutation_entries(state_root, deployment_key, require_complete=require_complete)
    sequence = current_mutation_sequence(state_root, deployment_key)
    observed = [entry["sequence"] for entry in entries]
    if observed and (len(set(observed)) != len(observed) or sorted(observed) != list(range(1, sequence + 1))):
        raise StateError("mutation journal sequence is incomplete, duplicated, or gapped")
    if not observed and sequence:
        raise StateError("mutation journal sequence is incomplete, duplicated, or gapped")
    normalized = [
        {key: value for key, value in entry.items() if key != "_path"}
        for entry in sorted(entries, key=lambda item: item["sequence"])
    ]
    return {
        "sequence": sequence,
        "journal_count": len(normalized),
        "journal_digest": digest_bytes(canonical_json(normalized)),
    }


@contextmanager
def relocation_lock(state_root: Path, deployment_key: str) -> Iterator[None]:
    directory = require_private_directory(state_root / "relocations" / "locks")
    path = directory / f"{_deployment_hex(deployment_key)}.lock"
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.chmod(path, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def hold_relocation_mutation_guard(
    state_root: Path,
    deployment_key: str,
    relocation_intent_digest: str | None = None,
    *,
    kind: str = "unspecified",
    subject: str | None = None,
) -> int:
    _deployment_hex(deployment_key)
    _validate_mutation_fields(
        relocation_intent_digest=relocation_intent_digest, kind=kind, subject=subject
    )
    directory = require_private_directory(state_root / "relocations" / "locks")
    lock_path = directory / f"{_deployment_hex(deployment_key)}.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.chmod(lock_path, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_SH)
        fence = fence_path(state_root, deployment_key)
        value = read_object(fence, "relocation deployment fence") if fence.is_file() else None
        if value is not None and value.get("state") in {"IN_PROGRESS", "BLOCKED"}:
            if value.get("transaction_digest") != relocation_intent_digest:
                raise StateError("RELOCATION_IN_PROGRESS: mutation is fenced")
        elif relocation_intent_digest is not None:
            raise StateError("RELOCATION_TRANSACTION_NOT_ACTIVE: mutation intent is stale")
        _MUTATION_RECORDS[descriptor] = record_mutation_start(
            state_root, deployment_key, relocation_intent_digest, kind=kind, subject=subject
        )
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def release_relocation_mutation_guard(descriptor: int) -> None:
    path = _MUTATION_RECORDS.pop(descriptor, None)
    try:
        if path is None:
            raise StateError("relocation mutation guard has no journal entry")
        complete_mutation(path, outcome="SUCCEEDED", return_code=0)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
