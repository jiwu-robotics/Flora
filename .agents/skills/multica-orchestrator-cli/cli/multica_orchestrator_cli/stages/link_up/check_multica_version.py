#!/usr/bin/env python3
"""Read-only compatibility check for the local Multica CLI."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Sequence

DEFAULT_MINIMUM = "0.4.26"
VERSION = re.compile(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?")


@dataclass(frozen=True)
class Result:
    command: list[str]
    compatible: bool
    installed_version: str | None
    minimum_version: str
    reason: str | None


def parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION.search(value)
    if not match:
        raise ValueError(f"no semantic version found in {value!r}")
    return tuple(int(part) for part in match.groups())


def check(command: Sequence[str], minimum: str) -> Result:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as error:
        return Result(list(command), False, None, minimum, str(error))

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    if completed.returncode:
        return Result(list(command), False, None, minimum, f"exit status {completed.returncode}: {output}")

    try:
        installed = parse_version(output)
        required = parse_version(minimum)
    except ValueError as error:
        return Result(list(command), False, None, minimum, str(error))

    installed_text = ".".join(str(part) for part in installed)
    if installed < required:
        return Result(
            list(command),
            False,
            installed_text,
            minimum,
            f"requires Multica CLI {minimum} or newer",
        )
    return Result(list(command), True, installed_text, minimum, None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--multica-bin", default="multica", help="Multica executable to inspect")
    parser.add_argument("--minimum", default=DEFAULT_MINIMUM, help="minimum compatible semantic version")
    arguments = parser.parse_args()

    try:
        parse_version(arguments.minimum)
    except ValueError as error:
        parser.error(str(error))

    result = check((arguments.multica_bin, "version"), arguments.minimum)
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.compatible else 1


if __name__ == "__main__":
    raise SystemExit(main())
