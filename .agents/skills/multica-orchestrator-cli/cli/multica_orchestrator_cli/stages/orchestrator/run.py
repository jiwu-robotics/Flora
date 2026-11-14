#!/usr/bin/env python3
"""Stable entrypoint for orchestrator policy materialization and lifecycle stages."""
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
    "materialize-profile": "materialize_orchestration_profile.py",
    "build-archives": "build_skill_archives.py",
    "materialize-integrity-lock": "materialize_skill_integrity_lock.py",
    "verify-integrity": "verify_skill_integrity.py",
    "prepare": "prepare_server_application.py",
    "inspect": "capture_server_readbacks.py",
    "plan": "plan_server_application.py",
    "apply": "apply_server_operation.py",
    "verify": "verify_server_application.py",
    "emit": "emit_server_handoff.py",
}


def main() -> int:
    activate_state_bundle()
    if len(sys.argv) < 2 or sys.argv[1] not in SCRIPTS:
        print("usage: run.py <materialize-profile|build-archives|materialize-integrity-lock|prepare|inspect|plan|apply|verify-integrity|verify|emit> [mode arguments...]", file=sys.stderr)
        return 2
    script = Path(__file__).with_name(SCRIPTS[sys.argv[1]])
    os.execv(sys.executable, [sys.executable, str(script), *sys.argv[2:]])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
