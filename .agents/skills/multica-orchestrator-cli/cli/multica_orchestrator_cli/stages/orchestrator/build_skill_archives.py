#!/usr/bin/env python3
"""Build deterministic, operator-local Skill archives and a provenance lock."""
from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

from server_application_common import InputError, load_manifest
from multica_state_bundle.identities import digest_bytes
from multica_state_bundle.storage import atomic_json
from verify_skill_integrity import canonical_content_digest, source_entries


def git(source: Path, *arguments: str) -> str:
    completed = subprocess.run(["git", "-C", str(source), *arguments], text=True, capture_output=True, check=False)
    if completed.returncode:
        raise InputError(completed.stderr.strip() or "git command failed")
    return completed.stdout.strip()


def archive(path: Path, entries: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, strict_timestamps=True) as bundle:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, entries[name])
    path.chmod(0o600)
def parse_skill_sources(values: list[str], allowed: set[str]) -> dict[str, Path]:
    overrides: dict[str, Path] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        if not separator or not name or not raw_path or name not in allowed or name in overrides:
            raise InputError("--skill-source must use a unique required <skill-name>=<directory>")
        overrides[name] = Path(raw_path).expanduser().resolve()
    return overrides
def selected_skill_source(
    name: str, overrides: dict[str, Path], source_root: Path, fallback_root: Path | None
) -> tuple[Path, bool]:
    if name in overrides:
        return overrides[name], True
    source = source_root / "skills" / name
    if source.is_dir() and not source.is_symlink():
        return source, False
    if fallback_root is not None:
        return fallback_root / name, True
    return source, False






def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--supplemental-skill", action="append", default=[])
    parser.add_argument("--skill-source", action="append", default=[], metavar="NAME=DIRECTORY")
    parser.add_argument("--fallback-skill-root", type=Path)
    arguments = parser.parse_args()
    try:
        roles = load_manifest(arguments.manifest)
        names = {name for role in roles for name in role.skills} | set(arguments.supplemental_skill)
        if not names:
            raise InputError("no Skills selected")
        overrides = parse_skill_sources(arguments.skill_source, names)
        if git(arguments.source_root, "status", "--porcelain", "--", "skills"):
            raise InputError("source Skill tree is dirty")
        revision = "git:" + git(arguments.source_root, "rev-parse", "HEAD")
        skills = []
        for name in sorted(names):
            source, external = selected_skill_source(
                name,
                overrides,
                arguments.source_root,
                arguments.fallback_skill_root.expanduser().resolve()
                if arguments.fallback_skill_root
                else None,
            )
            if not external and not git(
                arguments.source_root,
                "ls-tree",
                "-r",
                "--name-only",
                "HEAD",
                "--",
                f"skills/{name}",
            ):
                external = True
            entries = source_entries(source)
            content_digest = canonical_content_digest(entries)
            destination = arguments.state_dir / "archives" / f"{name}.skill"
            archive(destination, entries)
            skills.append({
                "name": name,
                "source_path": f"override/{name}" if external else f"skills/{name}",
                "source_revision": f"content:{content_digest}" if external else revision,
                "archive_path": f"archives/{name}.skill",
                "archive_raw_digest": digest_bytes(destination.read_bytes()),
                "content_digest": content_digest,
                "binding": "manifest" if any(name in role.skills for role in roles) else "supplemental",
            })
        atomic_json(arguments.state_dir / "skill-archive-plan.json", {"schema": "skill-archive-plan/v1", "manifest_sha256": digest_bytes(arguments.manifest.read_bytes()), "skills": skills})
        print(f"built {len(skills)} deterministic archives")
        return 0
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
