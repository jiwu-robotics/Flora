#!/usr/bin/env python3
"""Stable thin entrypoint for one Project and repository binding lifecycle."""
from __future__ import annotations

import os
import sys
from pathlib import Path

def activate_state_bundle() -> None:
    package_cli = Path(__file__).resolve().parents[3]
    if not (package_cli / "multica_state_bundle" / "__init__.py").is_file():
        print("STATE_BUNDLE_UNAVAILABLE: install multica-orchestrator-cli", file=sys.stderr)
        raise SystemExit(2)
    sys.path.insert(0, str(package_cli))
    from multica_state_bundle.bootstrap import activate_installed_package

    activate_installed_package(Path(__file__))

SCRIPTS = {
    "prepare": "prepare_project_binding.py",
    "plan": "plan_project_binding.py",
    "apply": "apply_project_binding_operation.py",
    "verify": "verify_project_binding.py",
}


def main() -> int:
    activate_state_bundle()
    if len(sys.argv) < 2 or sys.argv[1] not in SCRIPTS:
        print("usage: run.py <prepare|plan|apply|verify> [mode arguments...]", file=sys.stderr)
        return 2
    script = Path(__file__).with_name(SCRIPTS[sys.argv[1]])
    os.execv(sys.executable, [sys.executable, str(script), *sys.argv[2:]])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
