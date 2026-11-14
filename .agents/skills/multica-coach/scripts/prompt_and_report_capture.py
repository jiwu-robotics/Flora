#!/usr/bin/env python3
"""Atomically archive one Skill invocation's raw prompt and final report."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ARCHIVE_NAME = ".prompt-and-report"
EXCLUDE_RULE = f"/{ARCHIVE_NAME}/"
SKILL_NAME = re.compile(r"multica-[a-z0-9-]+\Z")
CAPTURE_ID = re.compile(r"\d{8}T\d{6}Z-multica-[a-z0-9-]+-[0-9a-f]{16}\Z")


class CaptureError(RuntimeError):
    """Raised when an archive cannot be written safely."""


def parse_cwd(raw_cwd: str) -> Path:
    cwd = Path(raw_cwd).resolve(strict=True)
    if not cwd.is_dir():
        raise CaptureError(f"invocation cwd is not a directory: {cwd}")
    return cwd


def archive_directory(cwd: Path) -> Path:
    directory = cwd / ARCHIVE_NAME
    if directory.exists() and directory.is_symlink():
        raise CaptureError(f"archive directory must not be a symlink: {directory}")
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise CaptureError(f"archive path must be a directory: {directory}")
    directory.chmod(0o700)
    return directory


def git_exclude(directory: Path) -> None:
    completed = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"],
        cwd=directory.parent,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        return

    exclude = Path(completed.stdout.strip())
    if not exclude.is_absolute():
        raise CaptureError("Git returned a non-absolute info/exclude path")
    exclude.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    if EXCLUDE_RULE in {line.strip() for line in existing.splitlines()}:
        return
    with exclude.open("a", encoding="utf-8") as stream:
        if existing and not existing.endswith("\n"):
            stream.write("\n")
        stream.write(f"{EXCLUDE_RULE}\n")


def write_new(path: Path, content: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError as error:
        raise CaptureError(f"refusing to overwrite existing archive: {path}") from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def start(arguments: argparse.Namespace) -> int:
    if not SKILL_NAME.fullmatch(arguments.skill):
        raise CaptureError(f"invalid Skill name: {arguments.skill!r}")
    prompt = sys.stdin.buffer.read()
    if not prompt:
        raise CaptureError("raw prompt is empty")

    cwd = parse_cwd(arguments.cwd)
    directory = archive_directory(cwd)
    git_exclude(directory)
    capture_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{arguments.skill}-{secrets.token_hex(8)}"
    write_new(directory / f"{capture_id}.prompt.md", prompt)
    print(json.dumps({"archive_dir": str(directory), "capture_id": capture_id}, sort_keys=True))
    return 0


def finish(arguments: argparse.Namespace) -> int:
    if not CAPTURE_ID.fullmatch(arguments.capture_id):
        raise CaptureError(f"invalid capture ID: {arguments.capture_id!r}")
    report = sys.stdin.buffer.read()
    if not report:
        raise CaptureError("final report is empty")

    cwd = parse_cwd(arguments.cwd)
    directory = archive_directory(cwd)
    prompt = directory / f"{arguments.capture_id}.prompt.md"
    if not prompt.is_file() or prompt.is_symlink():
        raise CaptureError(f"missing raw prompt for capture ID: {arguments.capture_id}")
    write_new(directory / f"{arguments.capture_id}.report.md", report)
    print(json.dumps({"archive_dir": str(directory), "capture_id": arguments.capture_id}, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    start_parser = commands.add_parser("start", help="write the exact invocation prompt")
    start_parser.add_argument("--skill", required=True)
    start_parser.add_argument("--cwd", required=True)

    finish_parser = commands.add_parser("finish", help="write the exact final report")
    finish_parser.add_argument("--capture-id", required=True)
    finish_parser.add_argument("--cwd", required=True)

    arguments = parser.parse_args()
    try:
        if arguments.command == "start":
            return start(arguments)
        return finish(arguments)
    except (CaptureError, OSError) as error:
        print(f"prompt/report capture failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
