#!/usr/bin/env python3
"""Generate exact source/target/merge integration evidence from Dispatch authorities."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dispatch_common import InputError, REVISION, read_json
from multica_state_bundle.identities import canonical_json, digest_bytes
from multica_state_bundle.storage import atomic_bytes
from check_ci_evidence import CONTROL_CHECKS

ACTIVE_ATTEMPT_STATES = {"EVALUATING", "READY"}
CHECKOUT_STATES = {"ACTIVE", "RELEASED", "RETAINED_ON_FAILURE"}


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{label} must be a non-empty string")
    return value


def require_revision(value: Any, label: str) -> str:
    revision = require_string(value, label)
    if REVISION.fullmatch(revision) is None:
        raise InputError(f"{label} must be a 40-character lowercase Git revision")
    return revision


def load_admission(path: Path) -> tuple[dict[str, Any], str]:
    value = read_json(path, "Run admission")
    if not isinstance(value, dict) or value.get("schema") != "multica-orchestrator-dispatch.run-admission-ref.v1":
        raise InputError("Run admission schema is invalid")
    unsigned = dict(value)
    observed = unsigned.pop("admission_digest", None)
    actual = digest_bytes(canonical_json(unsigned))
    if observed != actual or value.get("state") != "ACTIVE":
        raise InputError("Run admission is not active or its digest is invalid")
    return value, actual


def fetch_one(connection: sqlite3.Connection, query: str, arguments: tuple[Any, ...], label: str) -> sqlite3.Row:
    rows = connection.execute(query, arguments).fetchall()
    if len(rows) != 1:
        raise InputError(f"{label} must resolve exactly one record; observed {len(rows)}")
    return rows[0]


def snapshot_digest(value: Any) -> str:
    return digest_bytes(canonical_json(value))


def generate_checks(
    connection: sqlite3.Connection,
    *,
    project: str,
    repository: str,
    target_ref: str,
    attempt_ref: str,
    source: str,
    target: str,
    merge: str,
    admission: dict[str, Any],
    admission_digest: str,
) -> dict[str, dict[str, Any]]:
    attempt = fetch_one(
        connection,
        "SELECT * FROM integration_heads WHERE repository_ref=? AND target_ref=?",
        (repository, target_ref),
        "current integration attempt",
    )
    if (
        attempt["attempt_ref"] != attempt_ref
        or attempt["source_head"] != source
        or attempt["target_head"] != target
        or attempt["state"] not in ACTIVE_ATTEMPT_STATES
    ):
        raise InputError("integration attempt is stale or not dispatchable")
    branch = fetch_one(
        connection,
        "SELECT b.*,e.admission_ref,e.project_key,e.project_ref,e.work_item_id,"
        "e.state AS execution_state,e.active_release_digest,"
        "e.project_binding_digest,e.dispatch_contract_digest,e.runtime_alias,"
        "e.work_type,e.squad_ref,e.leader_ref "
        "FROM work_item_branches b JOIN executions e USING(execution_ref) "
        "WHERE b.repository_ref=? AND b.target_ref=? AND b.current_head_revision=?",
        (repository, target_ref, source),
        "source Work Item branch",
    )
    if branch["project_ref"] != project:
        raise InputError("source Work Item belongs to a different Project")
    admission_fields = {
        "admission_ref": "admission_ref",
        "project_key": "project_key",
        "project_ref": "project_ref",
        "active_release_digest": "active_release_digest",
        "project_binding_digest": "project_binding_digest",
        "dispatch_contract_digest": "dispatch_contract_digest",
        "runtime_alias": "runtime_alias",
        "work_type": "work_type",
        "squad_ref": "squad_ref",
        "leader_ref": "leader_ref",
    }
    mismatches = [
        field
        for field, column in admission_fields.items()
        if branch[column] != admission.get(field)
    ]
    if mismatches or branch["execution_ref"] != admission.get("execution_ref"):
        raise InputError("Run admission does not match the active execution: " + ", ".join(mismatches))
    execution_ref = branch["execution_ref"]
    checkouts = [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM run_checkouts WHERE execution_ref=? ORDER BY bound_at",
            (execution_ref,),
        )
    ]
    matching_checkouts = [
        row
        for row in checkouts
        if row["head_revision"] == source and row["state"] in CHECKOUT_STATES
    ]
    if len(matching_checkouts) != 1:
        raise InputError("source execution lacks one exact-revision checkout")
    scopes = [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM scopes WHERE execution_ref=? ORDER BY scope_ref",
            (execution_ref,),
        )
    ]
    other_active_scopes = [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM scopes WHERE execution_ref<>? AND state='ACTIVE' ORDER BY scope_ref",
            (execution_ref,),
        )
    ]
    for current in scopes:
        if current["state"] != "ACTIVE" or current["kind"] != "path":
            continue
        for other in other_active_scopes:
            if other["kind"] != "path":
                continue
            left = current["scope_key"].strip("/")
            right = other["scope_key"].strip("/")
            if left == right or left.startswith(right + "/") or right.startswith(left + "/"):
                raise InputError("current Work Item has an unresolved active scope conflict")
    leases = [dict(row) for row in connection.execute("SELECT * FROM lease_heads ORDER BY resource_key")]
    ledger = connection.execute(
        "SELECT * FROM ledger_heads WHERE stream_ref=?",
        (f"work:{branch['work_item_id']}",),
    ).fetchone()
    if ledger is None:
        raise InputError("current Work Item has no workflow ledger head")
    designation = fetch_one(
        connection,
        "SELECT * FROM human_designations WHERE project_ref=? AND state='VERIFIED'",
        (project,),
        "current Human designation",
    )
    decision = fetch_one(
        connection,
        "SELECT * FROM human_decisions WHERE attempt_ref=?",
        (attempt_ref,),
        "current Human decision",
    )
    if (
        decision["project_ref"] != project
        or decision["repository_ref"] != repository
        or decision["target_ref"] != target_ref
        or decision["source_head"] != source
        or decision["target_head"] != target
        or decision["designation_ref"] != designation["designation_ref"]
        or decision["actor_account_ref"] != designation["account_ref"]
        or decision["actor_type"] != "human"
        or decision["decision"] != "APPROVED"
    ):
        raise InputError("Human approval does not match the current exact-revision attempt")
    permission_inputs = {
        "project_binding_digest": admission["project_binding_digest"],
        "dispatch_contract_digest": admission["dispatch_contract_digest"],
    }
    facts = {
        "orchestration-contract": {
            "run_admission_digest": admission_digest,
            "active_release_digest": admission["active_release_digest"],
            "ledger": dict(ledger),
        },
        "work-type-isolation": {"execution_ref": execution_ref, "work_item_id": branch["work_item_id"], "execution_state": branch["execution_state"], "work_type": branch["work_type"]},
        "work-item-execution-isolation": {"branch": dict(branch), "checkout": matching_checkouts[0]},
        "cross-work-item-scope-conflict": {"scopes": scopes, "other_active_scopes": other_active_scopes},
        "resource-lease-integrity": {"execution_ref": execution_ref, "lease_heads": leases},
        "integration-target-freshness": {"integration_attempt": dict(attempt), "merge_revision": merge},
        "artifact-revision-integrity": {"source_revision": source, "target_revision": target, "merge_revision": merge, "branch_revision": branch["current_head_revision"], "checkout_revision": matching_checkouts[0]["head_revision"], "ledger": dict(ledger)},
        "permission-boundary": permission_inputs,
        "human-approval-evidence": {"designation": dict(designation), "decision": dict(decision)},
    }
    return {
        check: {
            "state": "PASS",
            "evidence_ref": f"dispatch:{check}:{snapshot_digest(facts[check])}",
            "details": facts[check],
        }
        for check in CONTROL_CHECKS
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="mode-0600 Project control-store SQLite path")
    parser.add_argument("--project-ref", required=True)
    parser.add_argument("--repository-ref", required=True)
    parser.add_argument("--target-ref", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--target-revision", required=True)
    parser.add_argument("--merge-revision", required=True)
    parser.add_argument("--run-admission", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        source = require_revision(arguments.source_revision, "source revision")
        target = require_revision(arguments.target_revision, "target revision")
        merge = require_revision(arguments.merge_revision, "merge revision")
        admission, admission_digest = load_admission(arguments.run_admission)
        if admission.get("project_ref") != arguments.project_ref or admission.get("repository_ref") != arguments.repository_ref:
            raise InputError("Run admission belongs to a different Project or repository")
        if not arguments.db.is_file():
            raise InputError(f"Project control store does not exist: {arguments.db}")
        connection = sqlite3.connect(f"file:{arguments.db.resolve()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise InputError(f"Project control store integrity check failed: {integrity}")
            checks = generate_checks(
                connection,
                project=arguments.project_ref,
                repository=arguments.repository_ref,
                target_ref=arguments.target_ref,
                attempt_ref=arguments.attempt,
                source=source,
                target=target,
                merge=merge,
                admission=admission,
                admission_digest=admission_digest,
            )
            queue_revision = connection.execute(
                "SELECT revision FROM integration_heads WHERE repository_ref=? AND target_ref=?",
                (arguments.repository_ref, arguments.target_ref),
            ).fetchone()[0]
        finally:
            connection.close()
        payload = {
            "schema": "multica-orchestrator-dispatch.integration-check-evidence.v1",
            "generator": "multica-orchestrator-dispatch.default-integration-evaluator.v1",
            "run_admission_digest": admission_digest,
            "source_revision": source,
            "target_revision": target,
            "merge_revision": merge,
            "project_ref": arguments.project_ref,
            "integration_attempt": {
                "repository_ref": arguments.repository_ref,
                "target_ref": arguments.target_ref,
                "attempt_ref": arguments.attempt,
                "control_store_revision": queue_revision,
            },
            "checks": checks,
            "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        payload["evidence_digest"] = digest_bytes(canonical_json(payload))
        atomic_bytes(arguments.output, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        print(json.dumps({"ok": True, "output": str(arguments.output), "evidence_digest": payload["evidence_digest"]}, sort_keys=True))
        return 0
    except (InputError, OSError, sqlite3.Error, TypeError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": "CONTROL_EVIDENCE_CAPTURE_FAILED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
