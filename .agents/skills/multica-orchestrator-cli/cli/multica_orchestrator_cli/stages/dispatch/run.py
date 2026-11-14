#!/usr/bin/env python3
"""Stable thin entrypoint for per-Work-Item dispatch and integration control."""
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
    "control": "control_store.py",
    "schedule-notifications": "notification_scheduler.py",
    "record-human-decision": "record_human_decision.py",
    "capture-control-evidence": "capture_control_evidence.py",
    "capture-provider": "capture_github_provider_evidence.py",
    "refresh-provider-evidence": "capture_github_provider_evidence.py",
    "verify-provider": "verify_provider_evidence.py",
    "check": "check_ci_evidence.py",
}
LEADER_COMMANDS = {"inspect", "admit-or-resume"}

def main() -> int:
    activate_state_bundle()
    if len(sys.argv) < 2:
        print(f"usage: run.py <{'|'.join((*LEADER_COMMANDS, *SCRIPTS))}> [mode arguments...]", file=sys.stderr)
        return 2
    mode = sys.argv[1]
    if mode in LEADER_COMMANDS:
        script = Path(__file__).with_name("leader_control.py")
        os.execv(sys.executable, [sys.executable, str(script), mode, *sys.argv[2:]])
        return 127
    if mode not in SCRIPTS:
        print(f"usage: run.py <{'|'.join((*LEADER_COMMANDS, *SCRIPTS))}> [mode arguments...]", file=sys.stderr)
        return 2
    script = Path(__file__).with_name(SCRIPTS[mode])
    os.execv(sys.executable, [sys.executable, str(script), *sys.argv[2:]])


if __name__ == "__main__":
    raise SystemExit(main())
