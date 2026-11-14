#!/usr/bin/env python3
"""Private Runtime-local publication and authority primitives for Dispatch."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, ContextManager, Iterator, Mapping

RUNTIME_BINDING_SCHEMA = "multica-orchestrator-dispatch.runtime-binding.v1"
ACTIVE_POINTER_SCHEMA = "multica-orchestrator-migrate.active-pointer.v1"
ACTIVE_RELEASE_SCHEMA = "multica-orchestrator.active-project-release.v2"
ACTIVATION_FENCE_SCHEMA = "multica-orchestrator-dispatch.activation-fence.v1"
_DIGEST_PREFIX = "sha256:"
_BINDING_FIELDS = {
    "schema", "server_kind", "server_ref", "workspace_ref", "deployment_key",
    "project_key", "project_ref", "repository_ref", "daemon_ref", "runtime_alias",
    "runtime_ref", "consumer_profile", "cas_root", "release_root", "control_db",
    "local_directory_resource_ref", "repository_root", "project_subpath",
}


class DispatchRuntimeError(ValueError):
    """Runtime-local Dispatch state cannot prove a safe authority."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _release_canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _digest(value: bytes) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(value).hexdigest()


def _digest_value(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith(_DIGEST_PREFIX):
        raise DispatchRuntimeError(f"{label} must be a SHA-256 digest")
    if any(character not in "0123456789abcdef" for character in value[len(_DIGEST_PREFIX):]):
        raise DispatchRuntimeError(f"{label} must be a SHA-256 digest")
    return value


def runtime_state_root() -> Path:
    """Return the selected Runtime user's private Dispatch state root."""
    configured = os.environ.get("XDG_STATE_HOME")
    base = Path(configured).expanduser() if configured else Path.home() / ".local" / "state"
    if not base.is_absolute() or ".." in base.parts:
        raise DispatchRuntimeError("XDG_STATE_HOME must be an absolute normalized path")
    if base.exists() and base.is_symlink():
        raise DispatchRuntimeError("Dispatch state base must not be a symlink")
    return (base / "multica-orchestrator-dispatch").resolve()


def _regular(path: Path, label: str, *, required: bool = True) -> Path:
    if not path.exists():
        if required:
            raise DispatchRuntimeError(f"{label} is missing")
        return path
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise DispatchRuntimeError(f"{label} is not a private regular file")
    return path


def _directory(path: Path, label: str, *, create: bool = False) -> Path:
    if path.exists():
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise DispatchRuntimeError(f"{label} is not a private directory")
    elif create:
        path.mkdir(parents=True, mode=0o700)
    else:
        raise DispatchRuntimeError(f"{label} is missing")
    if create:
        os.chmod(path, 0o700)
    return path.resolve()


def _private_json(path: Path, label: str) -> dict[str, Any]:
    _regular(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DispatchRuntimeError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise DispatchRuntimeError(f"{label} must be an object")
    return value


def _absolute(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise DispatchRuntimeError(f"{label} must be an absolute path")
    path = Path(value).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise DispatchRuntimeError(f"{label} must be an absolute normalized path")
    return path.resolve()


def _contained(path: Path, parent: Path, label: str) -> None:
    try:
        path.relative_to(parent)
    except ValueError as error:
        raise DispatchRuntimeError(f"{label} escapes its declared root") from error


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    _directory(path.parent, "Dispatch state parent", create=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _selector_key(server_kind: str, server_ref: str, workspace_ref: str) -> str:
    if server_kind not in {"cloud", "self-hosted"} or not all(isinstance(value, str) and value for value in (server_ref, workspace_ref)):
        raise DispatchRuntimeError("Runtime binding server selector is invalid")
    return _digest(_canonical({"server_kind": server_kind, "server_ref": server_ref, "workspace_ref": workspace_ref}))


def _project_hash(project_ref: str) -> str:
    if not isinstance(project_ref, str) or not project_ref:
        raise DispatchRuntimeError("Runtime binding project ref is invalid")
    return hashlib.sha256(project_ref.encode("utf-8")).hexdigest()


def binding_path(server_kind: str, server_ref: str, workspace_ref: str, project_ref: str) -> Path:
    selector = _selector_key(server_kind, server_ref, workspace_ref).split(":", 1)[1]
    return runtime_state_root() / "indexes" / selector / f"{_project_hash(project_ref)}.json"


def read_runtime_binding(server_kind: str, server_ref: str, workspace_ref: str, project_ref: str) -> dict[str, Any]:
    """Read one exact private Runtime binding; never selects by timestamp."""
    path = binding_path(server_kind, server_ref, workspace_ref, project_ref)
    binding = _private_json(path, "Runtime binding")
    if set(binding) != _BINDING_FIELDS or binding.get("schema") != RUNTIME_BINDING_SCHEMA:
        raise DispatchRuntimeError("Runtime binding fields are invalid")
    for field, expected in (("server_kind", server_kind), ("server_ref", server_ref), ("workspace_ref", workspace_ref), ("project_ref", project_ref)):
        if binding.get(field) != expected:
            raise DispatchRuntimeError("Runtime binding identity differs")
    for field in ("deployment_key", "project_key"):
        _digest_value(binding[field], f"Runtime binding {field}")
    for field in ("repository_ref", "daemon_ref", "runtime_alias", "runtime_ref", "consumer_profile", "local_directory_resource_ref"):
        if not isinstance(binding.get(field), str) or not binding[field]:
            raise DispatchRuntimeError(f"Runtime binding {field} is invalid")
    root = runtime_state_root()
    cas_root = _absolute(binding["cas_root"], "Runtime binding cas_root")
    release_root = _absolute(binding["release_root"], "Runtime binding release_root")
    control_db = _absolute(binding["control_db"], "Runtime binding control_db")
    repository_root = _absolute(binding["repository_root"], "Runtime binding repository_root")
    _contained(release_root, cas_root, "Runtime binding release_root")
    _contained(control_db, root, "Runtime binding control_db")
    if release_root.name != binding["project_key"].split(":", 1)[1]:
        raise DispatchRuntimeError("Runtime binding release root does not match Project key")
    if control_db.name != "control.sqlite3":
        raise DispatchRuntimeError("Runtime binding control DB name is invalid")
    if not isinstance(binding.get("project_subpath"), str) or Path(binding["project_subpath"]).is_absolute() or ".." in Path(binding["project_subpath"]).parts:
        raise DispatchRuntimeError("Runtime binding project subpath is invalid")
    result = dict(binding)
    result.update({"_path": str(path), "_cas_root": str(cas_root), "_release_root": str(release_root), "_control_db": str(control_db), "_repository_root": str(repository_root)})
    return result


def write_runtime_binding(binding: Mapping[str, Any]) -> Path:
    """Publish an exact binding only after target activation proved every field."""
    candidate = dict(binding)
    if set(candidate) != _BINDING_FIELDS or candidate.get("schema") != RUNTIME_BINDING_SCHEMA:
        raise DispatchRuntimeError("Runtime binding fields are invalid")
    path = binding_path(candidate["server_kind"], candidate["server_ref"], candidate["workspace_ref"], candidate["project_ref"])
    # Reuse the public validator against a temporary view only after writing is avoided.
    root = runtime_state_root()
    cas_root = _absolute(candidate["cas_root"], "Runtime binding cas_root")
    release_root = _absolute(candidate["release_root"], "Runtime binding release_root")
    control_db = _absolute(candidate["control_db"], "Runtime binding control_db")
    _contained(release_root, cas_root, "Runtime binding release_root")
    _contained(control_db, root, "Runtime binding control_db")
    existing = path if path.exists() else None
    if existing is not None:
        observed = _private_json(existing, "Runtime binding")
        if observed != candidate:
            raise DispatchRuntimeError("DISPATCH_AUTHORITY_CONFLICT")
        return existing
    _atomic_json(path, candidate)
    return path


def read_active_release(cas_root: Path, project_key: str) -> dict[str, Any]:
    """Read an ACTIVE pointer with strict containment and digest verification."""
    _digest_value(project_key, "Project key")
    root = _absolute(str(cas_root), "CAS root")
    releases = root / "releases" / project_key.split(":", 1)[1]
    pointer_path = releases / "active.json"
    pointer = _private_json(pointer_path, "ACTIVE release pointer")
    if set(pointer) != {"schema", "project_key", "generation", "release_digest", "release_path"} or pointer.get("schema") != ACTIVE_POINTER_SCHEMA or pointer.get("project_key") != project_key or not isinstance(pointer.get("generation"), int) or pointer["generation"] < 1:
        raise DispatchRuntimeError("ACTIVE release pointer is invalid")
    _digest_value(pointer.get("release_digest"), "ACTIVE release digest")
    release_path = _absolute(pointer.get("release_path"), "ACTIVE release path")
    _contained(release_path, releases.resolve(), "ACTIVE release path")
    release = _private_json(release_path, "ACTIVE release")
    unsigned = dict(release)
    observed = unsigned.pop("release_digest", None)
    if observed != pointer["release_digest"] or observed != _digest(_release_canonical(unsigned)) or release.get("schema") != ACTIVE_RELEASE_SCHEMA or release.get("project_key") != project_key or release.get("generation") != pointer["generation"] or release.get("state") != "ACTIVE":
        raise DispatchRuntimeError("ACTIVE release differs from pointer")
    return {"pointer": pointer, "release": release, "release_path": str(release_path), "release_digest": observed}


def read_activation_fence(release_root: Path) -> dict[str, Any] | None:
    root = _absolute(str(release_root), "release root")
    path = root / "activation-pending.json"
    if not path.exists():
        return None
    fence = _private_json(path, "activation fence")
    if set(fence) != {"schema", "project_key", "previous_release_digest", "release_digest", "transaction_digest"} or fence.get("schema") != ACTIVATION_FENCE_SCHEMA:
        raise DispatchRuntimeError("activation fence is invalid")
    for field in ("release_digest", "transaction_digest"):
        _digest_value(fence.get(field), f"activation fence {field}")
    if fence.get("previous_release_digest") is not None:
        _digest_value(fence["previous_release_digest"], "activation fence previous release digest")
    return fence


def assert_writable_binding(binding: Mapping[str, Any]) -> None:
    release_root = _absolute(str(binding["release_root"]), "Runtime binding release_root")
    if read_activation_fence(release_root) is not None:
        raise DispatchRuntimeError("DISPATCH_ACTIVATION_PENDING")
    control_db = _absolute(str(binding["control_db"]), "Runtime binding control_db")
    _directory(control_db.parent, "Dispatch authority directory", create=True)


@contextmanager
def authority_lock(control_db: Path) -> Iterator[None]:
    """Serialize one target authority without creating or opening SQLite."""
    control = _absolute(str(control_db), "control DB")
    parent = _directory(control.parent, "Dispatch authority directory", create=True)
    lock = parent / "authority.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.chmod(lock, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
