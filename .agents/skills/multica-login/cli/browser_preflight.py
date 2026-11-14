#!/usr/bin/env python3
"""Verify the pinned Agent Browser runtime and emit a private capability receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

LOCK_SCHEMA = "multica-login.browser-runtime-lock.v1"
RECEIPT_SCHEMA = "multica-login.browser-capability-receipt.v1"
CACHE_SECONDS = 86400


class PreflightError(RuntimeError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest_object(value: dict[str, Any], field: str) -> str:
    return digest_bytes(canonical_json({key: item for key, item in value.items() if key != field}))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def formatted(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def private_directory(path: Path) -> Path:
    path = path.expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not path.is_dir():
        raise PreflightError(f"private directory must be a non-symlink directory: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise PreflightError(f"private directory must not be group/world accessible: {path}")
    return path


def atomic_json(path: Path, value: dict[str, Any], *, replace: bool) -> None:
    path = path.expanduser().resolve()
    private_directory(path.parent)
    if path.exists() and not replace:
        raise PreflightError(f"refusing to overwrite output: {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def read_object(path: Path, label: str) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if path.is_symlink() or not path.is_file():
        raise PreflightError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PreflightError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise PreflightError(f"{label} must be a JSON object")
    return value


def executable(path: str | Path | None) -> Path | None:
    if path is None:
        return None
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        return None
    try:
        status = candidate.stat()
    except OSError:
        return None
    if candidate.is_symlink() or not stat.S_ISREG(status.st_mode) or not os.access(candidate, os.X_OK):
        return None
    return candidate.resolve()


def executable_identity(path: Path) -> dict[str, Any]:
    status = path.stat()
    return {
        "path": str(path),
        "device": status.st_dev,
        "inode": status.st_ino,
        "size": status.st_size,
        "mtime_ns": status.st_mtime_ns,
    }


def discover_system_chrome(explicit: str | None) -> tuple[Path | None, bool]:
    if explicit:
        selected = executable(explicit)
        if selected is None:
            raise PreflightError("AGENT_BROWSER_EXECUTABLE_PATH is not an absolute executable regular file")
        return selected, True
    candidates: list[Path] = []
    for name in ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found).resolve())
    candidates.extend([
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        Path("/usr/bin/google-chrome-stable"),
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/chromium"),
    ])
    for candidate in candidates:
        selected = executable(candidate)
        if selected is not None:
            return selected, False
    return None, False


def run(command: list[str], *, environment: dict[str, str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, env=environment, text=True, capture_output=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PreflightError(f"command failed to execute: {command[0]}: {error}") from error


def require_success(completed: subprocess.CompletedProcess[str], label: str) -> str:
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise PreflightError(f"{label} failed with exit {completed.returncode}: {detail[:400]}")
    return completed.stdout


def load_lock(path: Path) -> dict[str, Any]:
    value = read_object(path, "browser runtime lock")
    if value.get("schema") != LOCK_SCHEMA or set(value) != {"schema", "package", "version", "core_workflow"}:
        raise PreflightError("browser runtime lock fields or schema are invalid")
    if value.get("package") != "agent-browser" or not isinstance(value.get("version"), str) or not value["version"]:
        raise PreflightError("browser runtime lock package or version is invalid")
    if value.get("core_workflow") != "core --full":
        raise PreflightError("browser runtime lock core workflow is invalid")
    return value


def cached_browser(cache_path: Path, version: str, now: datetime) -> Path | None:
    if not cache_path.is_file() or cache_path.is_symlink():
        return None
    try:
        value = read_object(cache_path, "browser capability cache")
        if value.get("schema") != RECEIPT_SCHEMA or value.get("agent_browser_version") != version:
            return None
        expires = datetime.fromisoformat(str(value.get("expires_at", "")).replace("Z", "+00:00"))
        if expires <= now:
            return None
        identity = value.get("browser_executable")
        if not isinstance(identity, dict) or identity.get("source") != "system":
            return None
        path = executable(identity.get("path"))
        if path is None:
            return None
        if {key: executable_identity(path)[key] for key in ("device", "inode", "size", "mtime_ns")} != {key: identity.get(key) for key in ("device", "inode", "size", "mtime_ns")}:
            return None
        return path
    except (PreflightError, OSError, ValueError, TypeError):
        return None


def smoke(agent_browser: str, environment: dict[str, str]) -> None:
    session = "multica-login-probe-" + secrets.token_hex(8)
    opened = False
    try:
        require_success(run([agent_browser, "--session", session, "open", "about:blank"], environment=environment), "Agent Browser open smoke probe")
        opened = True
        require_success(run([agent_browser, "--session", session, "snapshot", "-i", "--json"], environment=environment), "Agent Browser snapshot smoke probe")
    finally:
        if opened:
            run([agent_browser, "--session", session, "close"], environment=environment)


def command_preflight(args: argparse.Namespace) -> dict[str, Any]:
    lock = load_lock(args.lock)
    version = lock["version"]
    cache_directory = private_directory(args.cache_dir)
    cache_path = cache_directory / "browser-capability-v1.json"
    now = utc_now()
    agent_browser = args.agent_browser or shutil.which("agent-browser")
    if agent_browser is None:
        if not args.install:
            raise PreflightError("agent-browser is missing; rerun with --install after explicit installation authorization")
        npm = shutil.which("npm")
        if npm is None:
            raise PreflightError("npm is required to install the pinned Agent Browser")
        require_success(run([npm, "install", "-g", f"agent-browser@{version}"], environment=os.environ.copy(), timeout=180), "pinned Agent Browser installation")
        agent_browser = shutil.which("agent-browser")
    if agent_browser is None:
        raise PreflightError("agent-browser executable is unavailable after installation")
    detected = require_success(run([agent_browser, "--version"], environment=os.environ.copy()), "Agent Browser version check").strip().split()[-1]
    if detected != version:
        raise PreflightError(f"Agent Browser version {detected!r} differs from pinned version {version!r}")
    core = require_success(run([agent_browser, "skills", "get", "core", "--full"], environment=os.environ.copy()), "Agent Browser core workflow load")
    if not core.strip():
        raise PreflightError("Agent Browser core workflow load returned empty output")

    explicit = os.environ.get("AGENT_BROWSER_EXECUTABLE_PATH")
    cached = cached_browser(cache_path, version, now) if explicit is None else None
    selected, explicit_choice = (cached, False) if cached is not None else discover_system_chrome(explicit)
    environment = os.environ.copy()
    source = "system"
    installed_managed = False
    if selected is not None:
        environment["AGENT_BROWSER_EXECUTABLE_PATH"] = str(selected)
        try:
            smoke(agent_browser, environment)
        except PreflightError:
            if explicit_choice or not args.install:
                raise
            selected = None
    if selected is None:
        if not args.install:
            raise PreflightError("no usable system Chrome/Chromium was found; rerun with --install after explicit managed-browser authorization")
        environment.pop("AGENT_BROWSER_EXECUTABLE_PATH", None)
        require_success(run([agent_browser, "install"], environment=environment, timeout=180), "Agent Browser managed browser installation")
        smoke(agent_browser, environment)
        source = "managed"
        installed_managed = True

    browser_identity: dict[str, Any]
    if selected is None:
        browser_identity = {"source": source, "path": None, "device": None, "inode": None, "size": None, "mtime_ns": None}
    else:
        browser_identity = {"source": source, **executable_identity(selected)}
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "lock_digest": digest_bytes(args.lock.resolve().read_bytes()),
        "agent_browser_version": version,
        "core_workflow_digest": digest_bytes(core.encode("utf-8")),
        "browser_executable": browser_identity,
        "smoke_probe": "PASSED",
        "cache_reused": cached is not None and selected == cached,
        "managed_browser_installed": installed_managed,
        "observed_at": formatted(now),
        "expires_at": formatted(now + timedelta(seconds=CACHE_SECONDS)),
    }
    receipt["receipt_digest"] = digest_object(receipt, "receipt_digest")
    atomic_json(cache_path, receipt, replace=True)
    if args.output.resolve() != cache_path:
        atomic_json(args.output, receipt, replace=False)
    return {"ok": True, "state": "BROWSER_CAPABILITY_VERIFIED", "receipt": str(args.output.resolve()), "receipt_digest": receipt["receipt_digest"], "cache_reused": receipt["cache_reused"], "browser_source": source}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=Path(__file__).resolve().parents[1] / "browser-runtime.lock.json")
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--agent-browser")
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    try:
        result = command_preflight(args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (PreflightError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": "AGENT_BROWSER_UNAVAILABLE", "detail": str(error)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
