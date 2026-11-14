#!/usr/bin/env python3
"""Verify locked Skill provenance, imported content, and Agent bindings.

The verifier is deliberately read-only.  It consumes JSON readbacks previously
captured from supported Multica CLI commands; it neither authenticates nor
changes a workspace.  The lock is operator-local because it contains live IDs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from server_application_common import InputError as SnapshotError, readback_snapshot_digest

SCHEMA = "skill-integrity-lock/v1"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
GIT_REVISION = re.compile(r"git:[0-9a-f]{40,64}\Z")
ROLE = re.compile(r"^  - role_key: (?P<value>[A-Za-z0-9_-]+)\s*$")
REQUIRED_SECTION = re.compile(r"^    required_skills:\s*$")
OPTIONAL_SECTION = re.compile(r"^    optional_skills:\s*$")
REQUIRED_SKILL = re.compile(r"^      - (?P<value>[A-Za-z0-9_.-]+)\s*$")
OPTIONAL_SKILL = re.compile(r"^      - name: (?P<value>[A-Za-z0-9_.-]+)\s*$")
FOUR_SPACE_FIELD = re.compile(r"^    [A-Za-z_][A-Za-z0-9_]*:")
ROOT_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:")
FRONTMATTER_NAME = re.compile(r"^name:\s*(?P<value>[^#\n]+?)\s*$", re.MULTILINE)


class VerificationInputError(ValueError):
    """The lock, manifest, or readback has no safe interpretation."""


@dataclass(frozen=True)
class Error:
    code: str
    subject: str
    detail: str

    def as_json(self) -> dict[str, str]:
        return {"code": self.code, "subject": self.subject, "detail": self.detail}


@dataclass(frozen=True)
class AgentBinding:
    role_key: str
    skill_names: frozenset[str]


def sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def canonical_content_digest(entries: Mapping[str, bytes]) -> str:
    """Hash a path-sorted textual package without archive metadata.

    Length-prefixing makes path/content boundaries unambiguous.  The domain
    separator permits future incompatible canonicalization rules.
    """
    digest = hashlib.sha256()
    digest.update(b"multica-skill-content-v1\0")
    for path in sorted(entries):
        encoded_path = path.encode("utf-8")
        content_digest = hashlib.sha256(entries[path]).digest()
        for field in (encoded_path, content_digest):
            digest.update(len(field).to_bytes(8, "big"))
            digest.update(field)
    return "sha256:" + digest.hexdigest()


def require_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise VerificationInputError(f"{context} must be an object")
    return value


def require_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise VerificationInputError(f"{context} must be an array")
    return value


def require_string(value: Any, context: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        qualifier = "string" if allow_empty else "non-empty string"
        raise VerificationInputError(f"{context} must be a {qualifier}")
    return value


def contained_path(root: Path, relative: str, context: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise VerificationInputError(f"{context} must be a relative path without '..'")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise VerificationInputError(f"{context} escapes its configured root") from error
    return resolved


def package_frontmatter_name(entries: Mapping[str, bytes], context: str) -> str:
    skill_md = entries.get("SKILL.md")
    if skill_md is None:
        raise VerificationInputError(f"{context} is missing SKILL.md")
    try:
        text = skill_md.decode("utf-8")
    except UnicodeDecodeError as error:
        raise VerificationInputError(f"{context} SKILL.md is not UTF-8") from error
    if not text.startswith("---\n"):
        raise VerificationInputError(f"{context} SKILL.md has no YAML frontmatter")
    closing = text.find("\n---", 4)
    if closing < 0:
        raise VerificationInputError(f"{context} SKILL.md has no closing YAML frontmatter")
    match = FRONTMATTER_NAME.search(text[4:closing])
    if match is None:
        raise VerificationInputError(f"{context} SKILL.md frontmatter has no name")
    return match["value"].strip(" '\"")


def validate_text_entries(entries: Mapping[str, bytes], context: str) -> None:
    if not entries:
        raise VerificationInputError(f"{context} contains no files")
    for path, content in entries.items():
        if not path or path.startswith("/") or "\\" in path:
            raise VerificationInputError(f"{context} contains unsafe path {path!r}")
        try:
            PurePosixPath(path)
        except ValueError as error:
            raise VerificationInputError(f"{context} contains invalid path {path!r}") from error
        if any(part in {"", ".", ".."} for part in PurePosixPath(path).parts):
            raise VerificationInputError(f"{context} contains unsafe path {path!r}")
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise VerificationInputError(f"{context} contains non-UTF-8 file {path!r}") from error
    package_frontmatter_name(entries, context)


def source_entries(directory: Path) -> dict[str, bytes]:
    if not directory.is_dir() or directory.is_symlink():
        raise VerificationInputError(f"source package is not a real directory: {directory}")

    entries: dict[str, bytes] = {}
    for current_root, directories, files in os.walk(directory, followlinks=False):
        root_path = Path(current_root)
        for child in directories:
            if (root_path / child).is_symlink():
                raise VerificationInputError(f"source package contains symlink: {(root_path / child).relative_to(directory)}")
        for filename in sorted(files):
            path = root_path / filename
            if path.is_symlink() or not path.is_file():
                raise VerificationInputError(f"source package contains non-regular file: {path.relative_to(directory)}")
            relative = path.relative_to(directory).as_posix()
            entries[relative] = path.read_bytes()
    validate_text_entries(entries, f"source package {directory}")
    return entries


def normalized_archive_path(raw_path: str) -> tuple[str, ...]:
    if not raw_path or raw_path.startswith("/") or "\\" in raw_path:
        raise VerificationInputError(f"archive contains unsafe path {raw_path!r}")
    parts = tuple(PurePosixPath(raw_path).parts)
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise VerificationInputError(f"archive contains unsafe path {raw_path!r}")
    return parts


def archive_entries(archive: Path) -> dict[str, bytes]:
    if not archive.is_file() or not zipfile.is_zipfile(archive):
        raise VerificationInputError(f"archive is not a readable .skill/.zip ZIP: {archive}")

    raw_entries: list[tuple[tuple[str, ...], zipfile.ZipInfo]] = []
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if info.is_dir():
                continue
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise VerificationInputError(f"archive contains symlink: {info.filename!r}")
            raw_entries.append((normalized_archive_path(info.filename), info))

        if not raw_entries:
            raise VerificationInputError(f"archive contains no files: {archive}")
        has_root_skill = any(parts == ("SKILL.md",) for parts, _ in raw_entries)
        prefixes = {parts[0] for parts, _ in raw_entries}
        strip_prefix = None
        if not has_root_skill and len(prefixes) == 1 and all(len(parts) > 1 for parts, _ in raw_entries):
            strip_prefix = next(iter(prefixes))

        entries: dict[str, bytes] = {}
        for parts, info in raw_entries:
            normalized = parts[1:] if strip_prefix is not None else parts
            path = "/".join(normalized)
            if path in entries:
                raise VerificationInputError(f"archive contains duplicate path: {path!r}")
            entries[path] = bundle.read(info)

    validate_text_entries(entries, f"archive {archive}")
    return entries


def workspace_entries(payload: Any, context: str) -> tuple[str, str, dict[str, bytes]]:
    record = require_mapping(payload, context)
    skill_id = require_string(record.get("id"), f"{context}.id")
    name = require_string(record.get("name"), f"{context}.name")
    content = require_string(record.get("content"), f"{context}.content", allow_empty=True)
    entries = {"SKILL.md": content.encode("utf-8")}
    for item in require_list(record.get("files"), f"{context}.files"):
        file_record = require_mapping(item, f"{context}.files[]")
        path = require_string(file_record.get("path"), f"{context}.files[].path")
        file_content = require_string(file_record.get("content"), f"{context}.files[{path!r}].content", allow_empty=True)
        if path in entries:
            raise VerificationInputError(f"{context} duplicates workspace path {path!r}")
        entries[path] = file_content.encode("utf-8")
    validate_text_entries(entries, context)
    return skill_id, name, entries


def extract_records(payload: Any, context: str) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        for key in ("skills", "items", "data"):
            if isinstance(payload.get(key), list):
                values = payload[key]
                break
        else:
            raise VerificationInputError(f"{context} contains no supported record list")
    else:
        raise VerificationInputError(f"{context} must be an array or object containing an array")
    return [require_mapping(item, f"{context}[]") for item in values]


def agent_skill_ids(payload: Any, context: str) -> set[str]:
    identifiers: set[str] = set()
    for record in extract_records(payload, context):
        identifiers.add(require_string(record.get("id"), f"{context}[].id"))
    return identifiers


def manifest_bindings(manifest: Path) -> list[AgentBinding]:
    if not manifest.is_file():
        raise VerificationInputError(f"manifest does not exist: {manifest}")
    bindings: list[AgentBinding] = []
    current_role: str | None = None
    current_skills: set[str] = set()
    section: str | None = None
    in_agents = False

    def finish_role() -> None:
        nonlocal current_role, current_skills, section
        if current_role is None:
            return
        if not current_skills:
            raise VerificationInputError(f"manifest role {current_role!r} has no Skill bindings")
        bindings.append(AgentBinding(current_role, frozenset(current_skills)))
        current_role = None
        current_skills = set()
        section = None

    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line == "agents:":
            if in_agents:
                raise VerificationInputError("manifest declares agents more than once")
            in_agents = True
            continue
        if not in_agents:
            continue
        if ROOT_FIELD.match(line):
            finish_role()
            break
        role = ROLE.match(line)
        if role:
            finish_role()
            current_role = role["value"]
            continue
        if current_role is None:
            continue
        if REQUIRED_SECTION.match(line):
            section = "required"
            continue
        if OPTIONAL_SECTION.match(line):
            section = "optional"
            continue
        if FOUR_SPACE_FIELD.match(line):
            section = None
            continue
        item = REQUIRED_SKILL.match(line) if section == "required" else OPTIONAL_SKILL.match(line) if section == "optional" else None
        if item:
            current_skills.add(item["value"])

    finish_role()
    if not bindings:
        raise VerificationInputError("manifest contains no agent Skill bindings")
    names = [binding.role_key for binding in bindings]
    if len(names) != len(set(names)):
        raise VerificationInputError("manifest contains duplicate role_key values")
    return bindings


def run_git(source_root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(source_root), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as error:
        raise VerificationInputError("git is required to verify source revisions") from error
    if completed.returncode:
        message = completed.stderr.strip() or completed.stdout.strip() or "unknown git error"
        raise VerificationInputError(f"git {' '.join(arguments)!r} failed: {message}")
    return completed.stdout.strip()


def error(errors: list[Error], code: str, subject: str, detail: str) -> None:
    errors.append(Error(code, subject, detail))


def compare_digest(errors: list[Error], code: str, subject: str, expected: Any, actual: str) -> None:
    if not isinstance(expected, str) or DIGEST.fullmatch(expected) is None:
        error(errors, "SKILL_LOCK_INVALID", subject, "missing or malformed expected SHA-256 digest")
    elif expected != actual:
        error(errors, code, subject, f"expected {expected}, observed {actual}")


def read_json(path: Path, context: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exception:
        raise VerificationInputError(f"missing {context}: {path}") from exception
    except json.JSONDecodeError as exception:
        raise VerificationInputError(f"invalid JSON in {context}: {path}: {exception.msg}") from exception


def verify(args: argparse.Namespace) -> tuple[list[Error], dict[str, Any]]:
    manifest = args.manifest.resolve()
    lock_path = args.lock.resolve()
    source_root = args.source_root.resolve()
    skill_readbacks = args.skill_readback_dir.resolve()
    skill_list_readback = args.skill_list_readback.resolve()
    agent_readbacks = args.agent_readback_dir.resolve() if args.agent_readback_dir is not None else None
    lock = require_mapping(read_json(lock_path, "integrity lock"), "integrity lock")
    errors: list[Error] = []

    if lock.get("schema") != SCHEMA:
        error(errors, "SKILL_LOCK_INVALID", "lock", f"schema must equal {SCHEMA!r}")
    compare_digest(errors, "SKILL_CONTENT_MISMATCH", "manifest", lock.get("manifest_sha256"), sha256_bytes(manifest.read_bytes()))

    bindings = manifest_bindings(manifest)
    expected_by_role = {binding.role_key: binding.skill_names for binding in bindings}
    workspace_name_ids: dict[str, list[str]] = {}
    for record in extract_records(read_json(skill_list_readback, "workspace Skill list"), "workspace Skill list"):
        list_name = require_string(record.get("name"), "workspace Skill list[].name")
        list_id = require_string(record.get("id"), "workspace Skill list[].id")
        workspace_name_ids.setdefault(list_name, []).append(list_id)

    expected_skills = set().union(*(binding.skill_names for binding in bindings))
    observed_source_revision = "git:" + run_git(source_root, "rev-parse", "HEAD")
    dirty_source_tree = run_git(source_root, "status", "--porcelain", "--", "skills")
    tracked_source_paths = set(run_git(source_root, "ls-tree", "-r", "--name-only", "HEAD", "--", "skills").splitlines())


    records = require_list(lock.get("skills"), "lock.skills")
    lock_skills: dict[str, Mapping[str, Any]] = {}
    verified_workspace_ids: dict[str, str] = {}
    skill_report: list[dict[str, str]] = []
    for raw_record in records:
        record = require_mapping(raw_record, "lock.skills[]")
        name = require_string(record.get("name"), "lock.skills[].name")
        if name in lock_skills:
            error(errors, "SKILL_LOCK_INVALID", name, "duplicate Skill record")
            continue
        lock_skills[name] = record

        source = require_mapping(record.get("source"), f"lock.skills[{name}].source")
        revision = source.get("revision")
        source_files: dict[str, bytes] | None = None
        if isinstance(revision, str) and GIT_REVISION.fullmatch(revision):
            source_relative = require_string(source.get("relative_path"), f"lock.skills[{name}].source.relative_path")
            source_path = contained_path(source_root, source_relative, f"lock.skills[{name}].source.relative_path")
            if revision != observed_source_revision:
                error(errors, "SKILL_SOURCE_REVISION_UNCONFIRMED", name, f"expected {revision}, observed {observed_source_revision}")
            if source_relative in dirty_source_tree:
                error(errors, "SKILL_SOURCE_REVISION_UNCONFIRMED", name, "source package has uncommitted or untracked changes")
            if not any(path == source_relative or path.startswith(source_relative + "/") for path in tracked_source_paths):
                error(errors, "SKILL_SOURCE_REVISION_UNCONFIRMED", name, "source package is not committed at HEAD")
            source_files = source_entries(source_path)
            source_digest = canonical_content_digest(source_files)
        elif isinstance(revision, str) and revision.startswith("content:"):
            source_digest = revision.removeprefix("content:")
        else:
            error(errors, "SKILL_LOCK_INVALID", name, "source revision must be git:<full commit SHA> or content:<SHA-256>")
            source_digest = ""
        compare_digest(errors, "SKILL_CONTENT_MISMATCH", f"{name}:source", source.get("content_sha256"), source_digest)

        archive = require_mapping(record.get("archive"), f"lock.skills[{name}].archive")
        archive_relative = require_string(archive.get("relative_path"), f"lock.skills[{name}].archive.relative_path")
        archive_path = contained_path(lock_path.parent, archive_relative, f"lock.skills[{name}].archive.relative_path")
        archive_digest = sha256_bytes(archive_path.read_bytes())
        compare_digest(errors, "SKILL_ARCHIVE_DIGEST_MISMATCH", f"{name}:archive", archive.get("sha256"), archive_digest)
        archive_files = archive_entries(archive_path)
        archive_content_digest = canonical_content_digest(archive_files)
        compare_digest(errors, "SKILL_CONTENT_MISMATCH", f"{name}:archive-content", archive.get("content_sha256"), archive_content_digest)

        workspace = require_mapping(record.get("workspace"), f"lock.skills[{name}].workspace")
        workspace_id = require_string(workspace.get("id"), f"lock.skills[{name}].workspace.id")
        listed_ids = workspace_name_ids.get(name, [])
        if len(listed_ids) != 1:
            error(errors, "WORKSPACE_SKILL_AMBIGUOUS", name, f"workspace skill list has {len(listed_ids)} entries with this name")
        elif listed_ids[0] != workspace_id:
            error(errors, "WORKSPACE_SKILL_AMBIGUOUS", name, f"lock workspace id {workspace_id!r} differs from listed id {listed_ids[0]!r}")
        workspace_payload = read_json(skill_readbacks / f"{name}.json", f"Skill readback for {name}")
        observed_id, observed_name, workspace_files = workspace_entries(workspace_payload, f"Skill readback for {name}")
        if observed_id != workspace_id:
            error(errors, "SKILL_CONTENT_MISMATCH", name, f"lock workspace id {workspace_id!r} does not match readback {observed_id!r}")
        if observed_name != name:
            error(errors, "SKILL_CONTENT_MISMATCH", name, f"workspace name {observed_name!r} does not match lock")
        workspace_content_digest = canonical_content_digest(workspace_files)
        compare_digest(errors, "SKILL_CONTENT_MISMATCH", f"{name}:workspace", workspace.get("content_sha256"), workspace_content_digest)

        package_entries = [("archive", archive_files), ("workspace", workspace_files)]
        if source_files is not None:
            package_entries.insert(0, ("source", source_files))
        for label, entries in package_entries:
            observed_name = package_frontmatter_name(entries, f"{name}:{label}")
            if observed_name != name:
                error(errors, "UNVERIFIABLE_SKILL_PACKAGE", f"{name}:{label}", f"SKILL.md frontmatter name is {observed_name!r}")
        if len({source_digest, archive_content_digest, workspace_content_digest}) != 1:
            error(errors, "SKILL_CONTENT_MISMATCH", name, "source, archive, and workspace content digests are not identical")

        verified_workspace_ids[workspace_id] = name
        skill_report.append(
            {
                "name": name,
                "source_content_sha256": source_digest,
                "archive_sha256": archive_digest,
                "archive_content_sha256": archive_content_digest,
                "workspace_content_sha256": workspace_content_digest,
            }
        )

    manifest_lock_skills = {
        name for name, record in lock_skills.items() if record.get("binding", "manifest") == "manifest"
    }
    missing_skills = expected_skills - manifest_lock_skills
    extra_skills = manifest_lock_skills - expected_skills
    for name in sorted(missing_skills):
        error(errors, "SKILL_LOCK_INVALID", name, "required manifest Skill has no manifest-bound lock record")
    for name in sorted(extra_skills):
        error(errors, "SKILL_LOCK_INVALID", name, "manifest-bound lock Skill is not bound by the manifest")

    if args.phase == "skills":
        return errors, {"skills": skill_report, "agents": []}

    if agent_readbacks is None:
        raise VerificationInputError("--agent-readback-dir is required for --phase full")

    agents = require_list(lock.get("agents"), "lock.agents")
    lock_agents: dict[str, Mapping[str, Any]] = {}
    for raw_record in agents:
        record = require_mapping(raw_record, "lock.agents[]")
        role_key = require_string(record.get("role_key"), "lock.agents[].role_key")
        if role_key in lock_agents:
            error(errors, "SKILL_LOCK_INVALID", role_key, "duplicate Agent record")
            continue
        lock_agents[role_key] = record

    missing_roles = set(expected_by_role) - set(lock_agents)
    extra_roles = set(lock_agents) - set(expected_by_role)
    for role_key in sorted(missing_roles):
        error(errors, "SKILL_LOCK_INVALID", role_key, "manifest Agent has no lock record")
    for role_key in sorted(extra_roles):
        error(errors, "SKILL_LOCK_INVALID", role_key, "lock Agent is not declared by the manifest")

    agent_report: list[dict[str, Any]] = []
    for role_key, expected_names in sorted(expected_by_role.items()):
        record = lock_agents.get(role_key)
        if record is None:
            continue
        agent_id = require_string(record.get("id"), f"lock.agents[{role_key}].id")
        agent_payload = require_mapping(read_json(agent_readbacks / f"{role_key}.json", f"Agent readback for {role_key}"), f"Agent readback for {role_key}")
        if require_string(agent_payload.get("id"), f"Agent readback for {role_key}.id") != agent_id:
            error(errors, "AGENT_SKILL_BINDING_MISMATCH", role_key, "Agent get id does not match the lock")
        if require_string(agent_payload.get("name"), f"Agent readback for {role_key}.name") != role_key:
            error(errors, "AGENT_SKILL_BINDING_MISMATCH", role_key, "Agent get name does not match the role key")
        get_ids = agent_skill_ids(agent_payload, f"Agent readback for {role_key}.skills")
        list_payload = read_json(agent_readbacks / f"{role_key}.skills.json", f"Agent Skill list for {role_key}")
        list_ids = agent_skill_ids(list_payload, f"Agent Skill list for {role_key}")
        if get_ids != list_ids:
            error(errors, "AGENT_SKILL_BINDING_MISMATCH", role_key, "agent get and agent skills list disagree")
        actual_names: set[str] = set()
        for skill_id in list_ids:
            name = verified_workspace_ids.get(skill_id)
            if name is None:
                error(errors, "AGENT_SKILL_BINDING_MISMATCH", role_key, f"assigned Skill id {skill_id!r} lacks a verified lock/readback")
            else:
                actual_names.add(name)
        if actual_names != expected_names:
            error(
                errors,
                "AGENT_SKILL_BINDING_MISMATCH",
                role_key,
                f"expected {sorted(expected_names)}, observed {sorted(actual_names)}",
            )
        agent_report.append({"role_key": role_key, "expected_skills": sorted(expected_names), "actual_skill_ids": sorted(list_ids)})

    report = {"skills": skill_report, "agents": agent_report}
    return errors, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="accepted orchestration package manifest")
    parser.add_argument("--lock", type=Path, required=True, help="operator-local JSON integrity lock")
    parser.add_argument("--source-root", type=Path, required=True, help="clean Git root containing source Skill packages")
    parser.add_argument("--skill-readback-dir", type=Path, required=True, help="restricted directory of '<skill>.json' skill get --with-content readbacks")
    parser.add_argument("--skill-list-readback", type=Path, required=True, help="restricted skill list --output json readback")
    parser.add_argument("--phase", choices=("skills", "full"), default="full", help="skills validates source/archive/workspace; full also validates every Agent binding")
    parser.add_argument("--agent-readback-dir", type=Path, help="restricted directory of '<role>.json' agent get and '<role>.skills.json' skills list readbacks; required for --phase full")
    parser.add_argument("--readback-snapshot", type=Path, required=True, help="snapshot.json binding all consumed workspace readbacks")
    args = parser.parse_args()

    try:
        errors, report = verify(args)
    except VerificationInputError as exception:
        payload = {"ok": False, "errors": [Error("INTEGRITY_INPUT_INVALID", "input", str(exception)).as_json()]}
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    except (OSError, SnapshotError, zipfile.BadZipFile) as exception:
        payload = {"ok": False, "errors": [Error("INTEGRITY_INPUT_INVALID", "input", str(exception)).as_json()]}
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    payload = {
        "schema": "multica-orchestrator.skill-integrity-report.v1",
        "ok": not errors,
        "errors": [item.as_json() for item in errors],
        "manifest_digest": sha256_bytes(args.manifest.read_bytes()),
        "lock_digest": sha256_bytes(args.lock.read_bytes()),
        "readback_snapshot_digest": readback_snapshot_digest(args.readback_snapshot.parent),
        **report,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
