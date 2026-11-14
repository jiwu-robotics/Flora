"""Leader-only read/commit facade for verified Dispatch admission."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from multica_state_bundle.claims import acquire_claim, release_claim
from multica_state_bundle.errors import StateBundleError
from multica_state_bundle.namespaces import established_project_namespace
from control_store import ControlError, control_session, execution_admit
from multica_state_bundle.identities import canonical_json, digest_bytes
from multica_state_bundle.storage import atomic_bytes
from dispatch_context import DispatchContextError, ResolvedDispatchContext, resolve_dispatch_context


class LeaderControlError(ValueError):
    """A Leader evaluation cannot safely create or reuse an admission."""


def _output(*, state: str, action: str, context: ResolvedDispatchContext | None, admission: dict[str, Any] | None, blockers: list[str]) -> dict[str, Any]:
    return {
        "ok": not blockers,
        "dispatch_state": state,
        "admission_action": action,
        "run_admission": admission,
        "resolved": context.public() if context is not None else None,
        "blockers": blockers,
    }


def _resolution(context: ResolvedDispatchContext) -> dict[str, Any]:
    return {
        "schema": "multica-orchestrator-dispatch.admission-resolution.v1",
        "issue_ref": context.issue_ref,
        "issue_snapshot": context.issue_snapshot,
        "active_release_digest": context.active_release_digest,
        "project_binding_digest": context.project_binding_digest,
        "dispatch_contract_digest": context.dispatch_contract_digest,
        "runtime_ref": context.runtime_ref,
        "daemon_ref": context.daemon_ref,
        "squad_ref": context.squad_ref,
        "leader_ref": context.leader_ref,
    }


def _arguments(context: ResolvedDispatchContext, run_ref: str) -> SimpleNamespace:
    return SimpleNamespace(
        project_key=context.project_key,
        project=context.project_ref,
        repository=context.repository_ref,
        active_release_digest=context.active_release_digest,
        project_binding_digest=context.project_binding_digest,
        dispatch_contract_digest=context.dispatch_contract_digest,
        runtime_alias=context.runtime_alias,
        work_item_ref=context.issue_ref,
        work_item_id=context.issue_key,
        work_item_url=context.issue_url,
        work_type=context.work_type,
        squad_ref=context.squad_ref,
        leader_ref=context.leader_ref,
        provider_run_ref=run_ref,
        resolution=_resolution(context),
    )


def _admission_file(control_db: Path, admission: dict[str, Any]) -> Path:
    return control_db.parent / "admissions" / f"{admission['admission_digest'].split(':', 1)[1]}.json"


def admit_or_resume(context: ResolvedDispatchContext, run_ref: str | None = None, *, restart: bool = False) -> tuple[dict[str, Any], str]:
    """Create/reuse only a context-verified local execution identity."""
    selected_run = run_ref or context.leader_run_ref
    state_root = context.cas_root.parent if context.cas_root.name == "bundle-store" else context.cas_root
    namespace = established_project_namespace(
        state_root=state_root,
        project_key_value=context.project_key,
    )
    claim = None
    outcome = "FAILED"
    try:
        claim = acquire_claim(namespace, "dispatch-admit")
        with control_session(context.control_db, initialize_if_missing=True) as db:
            prior = db.execute(
                "SELECT * FROM executions WHERE repository_ref=? AND work_item_ref=? ORDER BY epoch DESC LIMIT 1",
                (context.repository_ref, context.issue_ref),
            ).fetchone()
            if prior is not None and prior["state"] != "ACTIVE" and not restart:
                raise LeaderControlError("EXECUTION_RESTART_REQUIRED")
            if restart and prior is not None and prior["state"] == "ACTIVE":
                raise LeaderControlError("ADMISSION_CONTRACT_CHANGED")
            if restart and prior is not None:
                busy = db.execute(
                    "SELECT 1 FROM run_checkouts WHERE execution_ref=? AND state='ACTIVE'",
                    (prior["execution_ref"],),
                ).fetchone()
                if busy is not None:
                    raise LeaderControlError("EXECUTION_RESTART_REQUIRED")
            action = "REUSE" if prior is not None and prior["state"] == "ACTIVE" else "CREATE"
            admission = execution_admit(db, _arguments(context, selected_run))
        path = _admission_file(context.control_db, admission)
        if path.exists() and path.read_bytes() != canonical_json(admission):
            raise LeaderControlError("ADMISSION_CONTRACT_CHANGED")
        if not path.exists():
            atomic_bytes(path, canonical_json(admission))
        outcome = "PUBLISHED"
        return admission, action
    except (ControlError, sqlite3.Error, OSError, StateBundleError) as error:
        raise LeaderControlError(str(error)) from error
    finally:
        if claim is not None:
            release_claim(namespace, claim, outcome)


def inspect(profile: str, workspace: str | None, issue: str) -> dict[str, Any]:
    try:
        context = resolve_dispatch_context(profile, workspace, issue)
        if context.control_db.exists():
            return _output(state="READY", action="REUSE", context=context, admission=None, blockers=[])
        return _output(state="READY", action="CREATE", context=context, admission=None, blockers=[])
    except DispatchContextError as error:
        if str(error) == "ISSUE_TERMINAL_NO_ACTION":
            return _output(state="NO_ACTION", action="NONE", context=None, admission=None, blockers=[])
        return _output(state="BLOCKED", action="NONE", context=None, admission=None, blockers=[str(error)])

def admit(profile: str, workspace: str | None, issue: str, run_ref: str | None, restart: bool) -> dict[str, Any]:
    try:
        context = resolve_dispatch_context(profile, workspace, issue, run_ref=run_ref)
        admission, action = admit_or_resume(context, run_ref, restart=restart)
        return _output(state="ADMITTED", action=action, context=context, admission=admission, blockers=[])
    except (DispatchContextError, LeaderControlError) as error:
        if str(error) == "ISSUE_TERMINAL_NO_ACTION":
            return _output(state="NO_ACTION", action="NONE", context=None, admission=None, blockers=[])
        return _output(state="BLOCKED", action="NONE", context=None, admission=None, blockers=[str(error)])


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("inspect", "admit-or-resume"):
        command = commands.add_parser(name)
        command.add_argument("--profile", required=True)
        command.add_argument("--workspace")
        command.add_argument("--issue", required=True)
        if name == "admit-or-resume":
            command.add_argument("--run-ref")
            command.add_argument("--restart", action="store_true")
    return root


def main() -> int:
    args = parser().parse_args()
    result = inspect(args.profile, args.workspace, args.issue) if args.command == "inspect" else admit(args.profile, args.workspace, args.issue, args.run_ref, args.restart)
    if result["dispatch_state"] == "BLOCKED":
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
