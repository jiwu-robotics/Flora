#!/usr/bin/env python3
"""Inspect or record immutable project-local Skill provenance by required agent.

The observed remote HEAD is a candidate for the next refresh, not a claim that an
un-pinned installer selected that commit. Recorded content digests identify the
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

AGENT_SKILL_ROOTS = {
    "claude-code": Path(".claude/skills"),
    "codex": Path(".agents/skills"),
    "github-copilot": Path(".agents/skills"),
    "cursor": Path(".agents/skills"),
}
SKILLS = {
    "git-workflow": ("affaan-m/ECC", "skills/git-workflow/SKILL.md"),
}


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
    return {key: "changed" if previous.get(key) != value else "unchanged" for key, value in observed.items()}


def report_skill(previous: dict[str, Any] | None, current: Snapshot, errors: list[str]) -> dict[str, Any]:
    return {
        "eligible": not errors,
        "errors": errors,
        "changes": changes(previous, current),
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
        "previous": previous,
    }


def selected_roots(agents: list[str]) -> dict[Path, list[str]]:
    roots: dict[Path, list[str]] = {}
    for agent in agents:
        root = AGENT_SKILL_ROOTS[agent]
        roots.setdefault(root, []).append(agent)
    return roots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--agent", action="append", choices=sorted(AGENT_SKILL_ROOTS), required=True)
    parser.add_argument("--git-bin", default="git", help="Git executable used for the remote HEAD query")
    parser.add_argument("--record", action="store_true", help="write current provenance after every selected root verifies")
    parser.add_argument("--require-lock", action="store_true", help="fail when source/path/hash are not locked")
    parser.add_argument("--require-remote", action="store_true", help="fail when the remote HEAD cannot be read")
    arguments = parser.parse_args()

    root = arguments.project_root.resolve()
    roots = selected_roots(list(dict.fromkeys(arguments.agent)))
    root_states: dict[Path, dict[str, Any]] = {}
    root_snapshots: dict[Path, dict[str, Snapshot]] = {}
    root_errors: dict[Path, dict[str, list[str]]] = {}
    try:
        for relative_root in roots:
            state_path = root / relative_root / "skill-provenance.json"
            state = read_json(state_path)
            recorded = state.get("skills", {})
            if not isinstance(recorded, dict):
                raise ValueError(f"{state_path}: skills must be a JSON object")
            root_states[relative_root] = state
            snapshots = {
                skill: snapshot(root, arguments.git_bin, skill, root / relative_root)
                for skill in SKILLS
            }
            root_snapshots[relative_root] = snapshots
            errors_by_skill: dict[str, list[str]] = {}
            for skill, current in snapshots.items():
                errors = eligibility(current)
                if (arguments.require_remote or arguments.record) and current.remote_error:
                    errors.append(f"cannot read remote HEAD: {current.remote_error}")
                errors_by_skill[skill] = errors
            root_errors[relative_root] = errors_by_skill
    except ValueError as error:
        parser.error(str(error))

    for skill in SKILLS:
        digests = {
            root_snapshots[relative_root][skill].local_tree_sha256
            for relative_root in roots
        }
        if len(digests) > 1:
            for relative_root in roots:
                root_errors[relative_root][skill].append(
                    "local Skill tree differs across selected policy roots"
                )

    report: dict[str, Any] = {
        "roots": {
            relative_root.as_posix(): {
                "agents": agents,
                "state_file": str((root / relative_root / "skill-provenance.json").resolve()),
                "skills": {
                    skill: report_skill(
                        root_states[relative_root].get("skills", {}).get(skill)
                        if isinstance(root_states[relative_root].get("skills", {}).get(skill), dict)
                        else None,
                        current,
                        root_errors[relative_root][skill],
                    )
                    for skill, current in root_snapshots[relative_root].items()
                },
            }
            for relative_root, agents in roots.items()
        },
        "recorded": False,
    }
    has_errors = any(errors for per_root in root_errors.values() for errors in per_root.values())
    if arguments.record and not has_errors:
        written: list[str] = []
        try:
            for relative_root in roots:
                state = root_states[relative_root]
                recorded = state.setdefault("skills", {})
                for skill, current in root_snapshots[relative_root].items():
                    recorded[skill] = {
                        "source": current.source,
                        "skill_path": current.skill_path,
                        "lock_computed_hash": current.lock.computed_hash,
                        "local_tree_sha256": current.local_tree_sha256,
                        "remote_head": current.remote_head,
                    }
                state["version"] = 1
                state_path = root / relative_root / "skill-provenance.json"
                state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                written.append(relative_root.as_posix())
        except OSError as error:
            report["write_error"] = str(error)
            report["written_roots"] = written
            print(json.dumps(report, indent=2, sort_keys=True))
            return 1
        report["recorded"] = True
        report["written_roots"] = written

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not has_errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
