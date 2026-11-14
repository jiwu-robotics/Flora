#!/usr/bin/env python3
"""Read-only compatibility check for the Spec Kit setup toolchain."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from typing import Sequence

VERSION = re.compile(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?(?:[-+][0-9A-Za-z.-]+)?")


@dataclass(frozen=True)
class Requirement:
    name: str
    command: list[str]
    minimum_version: str | None


@dataclass(frozen=True)
class Result:
    name: str
    command: list[str]
    compatible: bool
    installed_version: str | None
    minimum_version: str | None
    reason: str | None


def parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION.search(value)
    if not match:
        raise ValueError(f"no semantic version found in {value!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def check(requirement: Requirement) -> Result:
    try:
        completed = subprocess.run(requirement.command, check=False, capture_output=True, text=True)
    except OSError as error:
        return Result(
            requirement.name,
            requirement.command,
            False,
            None,
            requirement.minimum_version,
            str(error),
        )

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    if completed.returncode:
        return Result(
            requirement.name,
            requirement.command,
            False,
            None,
            requirement.minimum_version,
            f"exit status {completed.returncode}: {output}",
        )

    try:
        installed = parse_version(output)
    except ValueError as error:
        return Result(requirement.name, requirement.command, False, None, requirement.minimum_version, str(error))

    installed_text = ".".join(str(part) for part in installed)
    if requirement.minimum_version:
        required = parse_version(requirement.minimum_version)
        if installed < required:
            return Result(
                requirement.name,
                requirement.command,
                False,
                installed_text,
                requirement.minimum_version,
                f"requires {requirement.minimum_version} or newer",
            )
    return Result(requirement.name, requirement.command, True, installed_text, requirement.minimum_version, None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specify-bin", default="specify", help="Spec Kit executable to inspect")
    parser.add_argument("--node-bin", default="node", help="Node.js executable to inspect")
    parser.add_argument("--git-bin", default="git", help="Git executable to inspect")
    parser.add_argument("--bun-bin", default="bun", help="Bun executable to inspect")
    parser.add_argument("--bash-bin", default="bash", help="Bash executable to inspect")
    parser.add_argument("--adrkit-cli", help="optional ADRKit CLI entry point to inspect")
    arguments = parser.parse_args()

    requirements = [
        Requirement("specify", [arguments.specify_bin, "--version"], "1.0.0"),
        Requirement("node", [arguments.node_bin, "--version"], "22.0.0"),
        Requirement("git", [arguments.git_bin, "--version"], "2.15.0"),
        Requirement("bun", [arguments.bun_bin, "--version"], None),
        Requirement("bash", [arguments.bash_bin, "--version"], None),
    ]
    if arguments.adrkit_cli:
        requirements.append(Requirement("adrkit", [arguments.adrkit_cli, "--version"], "0.12.0"))

    results = [check(requirement) for requirement in requirements]
    print(json.dumps([asdict(result) for result in results], sort_keys=True))
    return 0 if all(result.compatible for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
