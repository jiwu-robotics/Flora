#!/usr/bin/env python3
"""Inspect or record immutable local Skill content provenance.

The observed remote HEAD is a candidate for the next refresh, not a claim that an
un-pinned installer selected that commit. The recorded content digests identify the
actual installed Skill bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from multica_state_bundle.storage import atomic_json

PROJECT_SKILL_ROOTS = (Path(".agents/skills"), Path(".claude/skills"))
SKILLS = {"multica-cli": ("multica-ai/multica-cli", "skills/multica-cli/SKILL.md")}


@dataclass(frozen=True)
class LockEntry:
    source: str | None
    skill_path: str | None
    computed_hash: str | None


@dataclass(frozen=True)
class Snapshot:
    source: str
    skill_path: str
    lock: LockEntry
    local_tree_sha256: str | None
    local_skill_path: str
    remote_head: str | None
    remote_error: str | None
    remote_url: str


def project_skill_root(root: Path, skill: str) -> Path:
    for relative in PROJECT_SKILL_ROOTS:
        candidate = root / relative
        if (candidate / skill).is_dir():
            return candidate
    return root / PROJECT_SKILL_ROOTS[0]


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def canonical_github_repository(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    if candidate.startswith("git@github.com:"):
        path = candidate.removeprefix("git@github.com:")
    elif candidate.startswith(("ssh://git@github.com/", "https://github.com/", "http://github.com/")):
        path = urlsplit(candidate).path.lstrip("/")
    elif "://" not in candidate and candidate.count("/") >= 1:
        path = candidate
    else:
        return None
    parts = path.removesuffix(".git").split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    return "/".join(parts[:2])


def github_remote_url(value: str | None, canonical: str) -> str:
    if value and value.startswith(("git@github.com:", "ssh://git@github.com/")):
        return value
    return f"https://github.com/{canonical}.git"


def lock_entry(lock: dict[str, Any], skill: str) -> LockEntry:
    value = lock.get("skills", {}).get(skill, {})
    if not isinstance(value, dict):
        value = {}
    return LockEntry(value.get("source"), value.get("skillPath"), value.get("computedHash"))


def tree_hash(directory: Path) -> str | None:
    if not directory.is_dir():
        return None
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(directory).as_posix().encode()
        if path.is_symlink():
            digest.update(b"link\0" + relative + b"\0" + str(path.readlink()).encode() + b"\0")
        elif path.is_file():
            digest.update(b"file\0" + relative + b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def remote_head(git_bin: str, repository_url: str) -> tuple[str | None, str | None]:
    command = [git_bin, "ls-remote", "--exit-code", repository_url, "HEAD"]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as error:
        return None, str(error)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        return None, f"exit status {completed.returncode}: {detail}"
    fields = completed.stdout.strip().split()
    if not fields:
        return None, "remote did not return HEAD"
    return fields[0], None


def snapshot(root: Path, git_bin: str, skill: str, skills_root: Path) -> Snapshot:
    source, skill_path = SKILLS[skill]
    lock = lock_entry(read_json(root / "skills-lock.json"), skill)
    remote_url = github_remote_url(lock.source, source)
    head, error = remote_head(git_bin, remote_url)
    return Snapshot(
        source=source,
        skill_path=skill_path,
        lock=lock,
        local_tree_sha256=tree_hash(skills_root / skill),
        local_skill_path=str(skills_root / skill),
        remote_head=head,
        remote_error=error,
        remote_url=remote_url,
    )


def eligibility(value: Snapshot) -> list[str]:
    errors: list[str] = []
    if canonical_github_repository(value.lock.source) != value.source:
        errors.append(f"lock source is {value.lock.source!r}, expected repository {value.source!r}")
    if value.lock.skill_path != value.skill_path:
        errors.append(f"lock skillPath is {value.lock.skill_path!r}, expected {value.skill_path!r}")
    if not value.lock.computed_hash:
        errors.append("lock has no computedHash")
    if not value.local_tree_sha256:
        errors.append("local Skill directory is missing or unreadable")
    return errors


def changes(previous: dict[str, Any] | None, current: Snapshot) -> dict[str, str]:
    if not previous:
        return {"record": "unrecorded"}
    observed = {
        "lock_computed_hash": current.lock.computed_hash,
        "local_tree_sha256": current.local_tree_sha256,
        "remote_head": current.remote_head,
    }
    return {
        key: "changed" if previous.get(key) != value else "unchanged"
        for key, value in observed.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--git-bin", default="git", help="Git executable used for the remote HEAD query")
    parser.add_argument("--record", action="store_true", help="write current provenance after a verified refresh")
    parser.add_argument("--require-lock", action="store_true", help="fail when source/path/hash are not locked")
    parser.add_argument("--require-remote", action="store_true", help="fail when the remote HEAD cannot be read")
    arguments = parser.parse_args()

    root = arguments.project_root.resolve()
    skills_root = project_skill_root(root, "multica-cli")
    state_path = skills_root / "skill-provenance.json"
    try:
        state = read_json(state_path)
        current = snapshot(root, arguments.git_bin, "multica-cli", skills_root)
    except ValueError as error:
        parser.error(str(error))

    previous = state.get("skills", {}).get("multica-cli")
    errors = eligibility(current)
    if arguments.require_remote and current.remote_error:
        errors.append(f"cannot read remote HEAD: {current.remote_error}")

    report = {
        "skill": "multica-cli",
        "eligible": not errors,
        "errors": errors,
        "changes": changes(previous if isinstance(previous, dict) else None, current),
        "current": {
            "source": current.source,
            "skill_path": current.skill_path,
            "lock": asdict(current.lock),
            "local_tree_sha256": current.local_tree_sha256,
            "remote_head_candidate": current.remote_head,
            "remote_error": current.remote_error,
            "remote_url": current.remote_url,
            "local_skill_path": current.local_skill_path,
        },
        "previous": previous if isinstance(previous, dict) else None,
        "state_file": str(state_path),
    }

    if arguments.record and not errors:
        skills = state.setdefault("skills", {})
        if not isinstance(skills, dict):
            parser.error(f"{state_path}: skills must be a JSON object")
        skills["multica-cli"] = {
            "source": current.source,
            "skill_path": current.skill_path,
            "lock_computed_hash": current.lock.computed_hash,
            "local_tree_sha256": current.local_tree_sha256,
            "remote_head": current.remote_head,
        }
        state["version"] = 1
        atomic_json(state_path, state)
        report["recorded"] = True
    else:
        report["recorded"] = False

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
