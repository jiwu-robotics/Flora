#!/usr/bin/env python3
"""Record one authenticated Human decision for a frozen integration attempt."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from dispatch_common import InputError, REVISION
from multica_orchestrator_cli.common.profile_session import resolve_profile_session


def run_control(db: Path, arguments: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("control_store.py")), "--db", str(db), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise InputError((completed.stderr or completed.stdout).strip() or "control-store write failed")
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise InputError("control-store write returned a non-object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--workspace")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--project-ref", required=True)
    parser.add_argument("--repository-ref", required=True)
    parser.add_argument("--target-ref", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--target-revision", required=True)
    parser.add_argument("--decision", choices=("APPROVED", "REJECTED"), required=True)
    parser.add_argument("--authorization-ref", required=True)
    arguments = parser.parse_args()
    try:
        if REVISION.fullmatch(arguments.source_revision) is None or REVISION.fullmatch(arguments.target_revision) is None:
            raise InputError("source and target revisions must be 40-character lowercase Git revisions")
        session = resolve_profile_session(arguments.profile, arguments.workspace)
        # Designation is a separate operator action. Recording a decision must
        # never create, replace, or refresh the designated Human implicitly.
        decision = run_control(
            arguments.db,
            [
                "human-decision-record",
                "--project", arguments.project_ref,
                "--repository", arguments.repository_ref,
                "--target", arguments.target_ref,
                "--attempt", arguments.attempt,
                "--source-head", arguments.source_revision,
                "--target-head", arguments.target_revision,
                "--account", session.account_ref,
                "--decision", arguments.decision,
            ],
        )
        print(json.dumps({
            "ok": True,
            "authorization_ref": arguments.authorization_ref,
            "designation_ref": decision["designation_ref"],
            "decision_ref": decision["decision_ref"],
            "decision": decision["decision"],
            "attempt_ref": decision["attempt_ref"],
        }, sort_keys=True))
        return 0
    except (InputError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": "HUMAN_DECISION_REJECTED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
