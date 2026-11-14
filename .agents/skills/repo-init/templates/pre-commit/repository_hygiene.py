"""Validate fast repository-hygiene checks for pre-commit."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

import yaml

PRIVATE_KEY = re.compile(rb"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----")
TEXT_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".json", ".py", ".pyi", ".toml", ".yaml", ".yml"}


def validate(path: Path) -> list[str]:
    if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
        return []

    errors: list[str] = []
    content = path.read_bytes()
    if PRIVATE_KEY.search(content):
        errors.append("contains a private-key marker")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return errors
    if text and not text.endswith("\n"):
        errors.append("does not end with a newline")
    if any(line.rstrip(" \t") != line for line in text.splitlines()):
        errors.append("contains trailing whitespace")
    try:
        if path.suffix in {".yaml", ".yml"}:
            yaml.safe_load(text)
        elif path.suffix == ".json":
            json.loads(text)
        elif path.suffix == ".toml":
            tomllib.loads(text)
    except (json.JSONDecodeError, tomllib.TOMLDecodeError, yaml.YAMLError) as error:
        errors.append(f"has invalid syntax: {error}")
    return errors


def main(arguments: list[str]) -> int:
    failed = False
    for argument in arguments:
        path = Path(argument)
        for error in validate(path):
            print(f"{path}: {error}", file=sys.stderr)
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
