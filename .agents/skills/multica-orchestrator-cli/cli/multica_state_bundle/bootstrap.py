"""Resolve the installed central operational package for lifecycle launchers."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from .errors import StateBundleError

MINIMUM_VERSION = "1.0.0"
PACKAGE_NAME = "multica-orchestrator-cli"


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    if match is None:
        raise StateBundleError(
            "STATE_BUNDLE_UNAVAILABLE",
            f"the installed {PACKAGE_NAME} package has no compatible version marker",
            f"Install the reviewed {PACKAGE_NAME} Skill before running this lifecycle stage.",
        )
    return tuple(int(part) for part in match.groups())


def _validate_version(marker: Path) -> None:
    match = re.search(r'^__version__\s*=\s*"([^"]+)"\s*$', marker.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None or _version_tuple(match.group(1)) < _version_tuple(MINIMUM_VERSION):
        raise StateBundleError(
            "STATE_BUNDLE_UNAVAILABLE",
            f"the installed {PACKAGE_NAME} package is incompatible",
            f"Install the reviewed {PACKAGE_NAME} Skill before running this lifecycle stage.",
        )


def installed_package_cli(consumer_file: Path) -> Path:
    """Return this central package's CLI directory or fail before mutation."""
    resolved = consumer_file.resolve()
    for candidate in (resolved.parent, *resolved.parents):
        if candidate.name != PACKAGE_NAME:
            continue
        package_cli = candidate / "cli"
        marker = package_cli / "multica_state_bundle" / "__init__.py"
        if marker.is_file() and not marker.is_symlink():
            _validate_version(marker)
            return package_cli
    raise StateBundleError(
        "STATE_BUNDLE_UNAVAILABLE",
        f"the installed {PACKAGE_NAME} package is unavailable",
        f"Install the reviewed {PACKAGE_NAME} Skill before running this lifecycle stage.",
    )


def activate_installed_package(consumer_file: Path) -> Path:
    """Make the reviewed sibling package available to this process and child launchers."""
    package_cli = installed_package_cli(consumer_file)
    package_value = str(package_cli)
    if package_value not in sys.path:
        sys.path.insert(0, package_value)
    current = os.environ.get("PYTHONPATH", "")
    entries = [entry for entry in current.split(os.pathsep) if entry]
    if package_value not in entries:
        os.environ["PYTHONPATH"] = os.pathsep.join((package_value, *entries))
    return package_cli
