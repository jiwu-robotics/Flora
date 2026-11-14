#!/usr/bin/env python3
"""Atomic daemon-local orchestration controls for one selected runtime daemon."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import re
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from multica_orchestrator_cli.common.dispatch_runtime import (
    DispatchRuntimeError,
    assert_writable_binding,
    authority_lock,
    read_runtime_binding,
    runtime_state_root,
)

SCHEMA_VERSION = "5"
TERMINAL_EXECUTION_STATES = {"COMPLETED", "CANCELLED", "FAILED", "STALE"}
QUEUE_STATES = {"EVALUATING", "READY", "MERGING", "MERGED", "STALE", "FAILED"}
ACTIVE_QUEUE_STATES = {"EVALUATING", "READY", "MERGING"}
NOTIFICATION_STATES = {"RESERVED", "SENT", "FAILED", "SUPERSEDED"}
ZERO_HASH = "sha256:" + "0" * 64


class ControlError(RuntimeError):
    """A requested transition violates the orchestration control contract."""


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def reference(kind: str) -> str:
    return f"{kind}:{uuid.uuid4()}"


def connect(path: Path) -> sqlite3.Connection:
    path = path.expanduser().resolve()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    connection = sqlite3.connect(path, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")
    initialize(connection)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return connection


def initialize_base(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS executions (
          execution_ref TEXT PRIMARY KEY,
          admission_ref TEXT NOT NULL,
          project_key TEXT NOT NULL,
          project_ref TEXT NOT NULL,
          repository_ref TEXT NOT NULL,
          active_release_digest TEXT NOT NULL,
          project_binding_digest TEXT NOT NULL,
          dispatch_contract_digest TEXT NOT NULL,
          runtime_alias TEXT NOT NULL,
          work_item_ref TEXT NOT NULL,
          work_item_id TEXT NOT NULL,
          work_item_url TEXT,
          work_type TEXT NOT NULL,
          squad_ref TEXT NOT NULL,
          leader_ref TEXT NOT NULL,
          epoch INTEGER NOT NULL,
          state TEXT NOT NULL,
          created_at TEXT NOT NULL,
          ended_at TEXT,
          admission_digest TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_execution
          ON executions(project_ref, repository_ref, work_item_ref)
          WHERE state = 'ACTIVE';
        CREATE TABLE IF NOT EXISTS work_item_branches (
          execution_ref TEXT PRIMARY KEY REFERENCES executions(execution_ref),
          repository_ref TEXT NOT NULL,
          work_item_ref TEXT NOT NULL,
          integration_branch TEXT NOT NULL,
          base_ref TEXT NOT NULL,
          target_ref TEXT NOT NULL,
          current_head_revision TEXT NOT NULL,
          revision INTEGER NOT NULL,
          provider_receipt_ref TEXT NOT NULL,
          bound_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(repository_ref, integration_branch)
        );
        CREATE TABLE IF NOT EXISTS run_checkouts (
          run_ref TEXT PRIMARY KEY,
          execution_ref TEXT NOT NULL REFERENCES executions(execution_ref),
          runtime_ref TEXT NOT NULL,
          daemon_ref TEXT NOT NULL,
          resource_ref TEXT NOT NULL,
          checkout_root TEXT NOT NULL UNIQUE,
          runtime_branch TEXT NOT NULL,
          ownership_ref TEXT NOT NULL,
          baseline_revision TEXT NOT NULL,
          head_revision TEXT NOT NULL,
          session_ref TEXT NOT NULL UNIQUE,
          state_namespace TEXT NOT NULL UNIQUE,
          git_index_file TEXT NOT NULL UNIQUE,
          state TEXT NOT NULL,
          bound_at TEXT NOT NULL,
          released_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_writer_run
          ON run_checkouts(execution_ref)
          WHERE state = 'ACTIVE';
        CREATE TABLE IF NOT EXISTS ledger_events (
          stream_ref TEXT NOT NULL,
          revision INTEGER NOT NULL,
          previous_hash TEXT NOT NULL,
          event_hash TEXT NOT NULL UNIQUE,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY(stream_ref, revision)
        );
        CREATE TABLE IF NOT EXISTS ledger_heads (
          stream_ref TEXT PRIMARY KEY,
          revision INTEGER NOT NULL,
          event_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scopes (
          scope_ref TEXT PRIMARY KEY,
          project_ref TEXT NOT NULL,
          execution_ref TEXT NOT NULL REFERENCES executions(execution_ref),
          kind TEXT NOT NULL,
          scope_key TEXT NOT NULL,
          state TEXT NOT NULL,
          created_at TEXT NOT NULL,
          released_at TEXT
        );
        CREATE INDEX IF NOT EXISTS active_scopes
          ON scopes(project_ref, kind, state, scope_key);
        CREATE TABLE IF NOT EXISTS lease_events (
          resource_key TEXT NOT NULL,
          revision INTEGER NOT NULL,
          execution_ref TEXT NOT NULL,
          state TEXT NOT NULL,
          expires_at TEXT,
          created_at TEXT NOT NULL,
          PRIMARY KEY(resource_key, revision)
        );
        CREATE TABLE IF NOT EXISTS lease_heads (
          resource_key TEXT PRIMARY KEY,
          revision INTEGER NOT NULL,
          execution_ref TEXT NOT NULL,
          state TEXT NOT NULL,
          expires_at TEXT
        );
        CREATE TABLE IF NOT EXISTS integration_events (
          repository_ref TEXT NOT NULL,
          target_ref TEXT NOT NULL,
          revision INTEGER NOT NULL,
          attempt_ref TEXT NOT NULL,
          source_head TEXT NOT NULL,
          target_head TEXT NOT NULL,
          state TEXT NOT NULL,
          result_head TEXT,
          created_at TEXT NOT NULL,
          PRIMARY KEY(repository_ref, target_ref, revision)
        );
        CREATE TABLE IF NOT EXISTS integration_heads (
          repository_ref TEXT NOT NULL,
          target_ref TEXT NOT NULL,
          revision INTEGER NOT NULL,
          attempt_ref TEXT NOT NULL,
          source_head TEXT NOT NULL,
          target_head TEXT NOT NULL,
          state TEXT NOT NULL,
          result_head TEXT,
          PRIMARY KEY(repository_ref, target_ref)
        );
        CREATE TABLE IF NOT EXISTS notification_reservations (
          reservation_ref TEXT PRIMARY KEY,
          dedupe_key TEXT NOT NULL UNIQUE,
          project_ref TEXT NOT NULL,
          work_item_ref TEXT NOT NULL,
          execution_ref TEXT NOT NULL,
          subject TEXT NOT NULL,
          designation_ref TEXT NOT NULL,
          plan_ref TEXT NOT NULL,
          sorted_input_revisions TEXT NOT NULL,
          revision INTEGER NOT NULL,
          state TEXT NOT NULL,
          reminder_count INTEGER NOT NULL,
          reserved_at TEXT NOT NULL,
          next_reminder_at TEXT,
          provider_receipt_ref TEXT
        );
        CREATE TABLE IF NOT EXISTS notification_events (
          reservation_ref TEXT NOT NULL,
          revision INTEGER NOT NULL,
          state TEXT NOT NULL,
          provider_receipt_ref TEXT,
          created_at TEXT NOT NULL,
          PRIMARY KEY(reservation_ref, revision)
        );
        CREATE TABLE IF NOT EXISTS human_designations (
          project_ref TEXT PRIMARY KEY,
          designation_ref TEXT NOT NULL UNIQUE,
          account_ref TEXT NOT NULL,
          consent_ref TEXT NOT NULL,
          revision INTEGER NOT NULL,
          state TEXT NOT NULL,
          recorded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS human_decisions (
          decision_ref TEXT PRIMARY KEY,
          project_ref TEXT NOT NULL,
          repository_ref TEXT NOT NULL,
          target_ref TEXT NOT NULL,
          attempt_ref TEXT NOT NULL UNIQUE,
          source_head TEXT NOT NULL,
          target_head TEXT NOT NULL,
          designation_ref TEXT NOT NULL,
          actor_account_ref TEXT NOT NULL,
          actor_type TEXT NOT NULL,
          decision TEXT NOT NULL,
          recorded_at TEXT NOT NULL
        );
        """
    )
    execution_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(executions)")
    }
    for name in (
        "admission_ref", "project_key", "active_release_digest",
        "project_binding_digest", "dispatch_contract_digest", "runtime_alias",
        "work_type", "squad_ref", "leader_ref", "admission_digest",
    ):
        if name not in execution_columns:
            db.execute(f"ALTER TABLE executions ADD COLUMN {name} TEXT")
    for table in ("integration_events", "integration_heads"):
        columns = {
            row["name"] for row in db.execute(f"PRAGMA table_info({table})")
        }
        if "result_head" not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN result_head TEXT")
    row = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
    if row is None:
        db.execute("INSERT INTO metadata(key, value) VALUES('schema_version', ?)", (SCHEMA_VERSION,))
    elif row["value"] in {"2", "3"}:
        db.execute("UPDATE executions SET state='STALE' WHERE state='ACTIVE'")
        db.execute("UPDATE metadata SET value=? WHERE key='schema_version'", (SCHEMA_VERSION,))
    elif row["value"] not in {"4", SCHEMA_VERSION}:
        raise ControlError(f"unsupported control-store schema {row['value']}")
    db.execute(
        """
        UPDATE executions
           SET state='STALE'
         WHERE state='ACTIVE'
           AND (
             admission_ref IS NULL OR project_key IS NULL OR active_release_digest IS NULL
             OR project_binding_digest IS NULL OR dispatch_contract_digest IS NULL
             OR runtime_alias IS NULL OR work_type IS NULL OR squad_ref IS NULL
             OR leader_ref IS NULL OR admission_digest IS NULL
           )
        """
    )

def _migrate_v4_to_v5(db: sqlite3.Connection) -> None:
    db.execute("BEGIN IMMEDIATE")
    try:
        duplicate = db.execute(
            "SELECT repository_ref, work_item_ref FROM executions "
            "WHERE state='ACTIVE' GROUP BY repository_ref, work_item_ref HAVING COUNT(*) > 1"
        ).fetchone()
        if duplicate is not None:
            raise ControlError("LEGACY_ACTIVE_EXECUTION_CONFLICT")
        db.execute("DROP INDEX IF EXISTS one_active_execution")
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS one_active_execution "
            "ON executions(repository_ref, work_item_ref) WHERE state='ACTIVE'"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS control_authority("
            "singleton INTEGER PRIMARY KEY CHECK(singleton=1), deployment_key TEXT NOT NULL, daemon_ref TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS admission_resolutions("
            "admission_ref TEXT NOT NULL, provider_run_ref TEXT NOT NULL, resolution_digest TEXT NOT NULL, "
            "payload_json TEXT NOT NULL, recorded_at TEXT NOT NULL, "
            "PRIMARY KEY(admission_ref, provider_run_ref, resolution_digest))"
        )
        db.execute("UPDATE metadata SET value=? WHERE key='schema_version'", (SCHEMA_VERSION,))
    except Exception:
        db.execute("ROLLBACK")
        raise
    else:
        db.execute("COMMIT")


def initialize(db: sqlite3.Connection) -> None:
    """Create schema-v5 state or migrate a canonical v4 authority atomically."""
    try:
        current = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
    except sqlite3.OperationalError:
        current = None
    if current is not None and current["value"] == "4":
        _migrate_v4_to_v5(db)
        return
    initialize_base(db)
    version = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()["value"]
    if version != SCHEMA_VERSION:
        raise ControlError(f"unsupported control-store schema {version}")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_active_execution ON executions(repository_ref, work_item_ref) WHERE state='ACTIVE'")
    db.execute("CREATE TABLE IF NOT EXISTS control_authority(singleton INTEGER PRIMARY KEY CHECK(singleton=1), deployment_key TEXT NOT NULL, daemon_ref TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS admission_resolutions(admission_ref TEXT NOT NULL, provider_run_ref TEXT NOT NULL, resolution_digest TEXT NOT NULL, payload_json TEXT NOT NULL, recorded_at TEXT NOT NULL, PRIMARY KEY(admission_ref, provider_run_ref, resolution_digest))")


def _bound_authority(path: Path) -> Mapping[str, Any]:
    target = path.expanduser().resolve()
    indexes = runtime_state_root() / "indexes"
    if not indexes.is_dir() or indexes.is_symlink():
        raise ControlError("DISPATCH_STATE_ACCESS_UNVERIFIED")
    matches: list[Mapping[str, Any]] = []
    for candidate in indexes.glob("*/*.json"):
        try:
            value = json.loads(candidate.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or Path(str(value.get("control_db", ""))).expanduser().resolve() != target:
                continue
            binding = read_runtime_binding(
                str(value.get("server_kind")), str(value.get("server_ref")),
                str(value.get("workspace_ref")), str(value.get("project_ref")),
            )
            matches.append(binding)
        except (OSError, ValueError, json.JSONDecodeError, DispatchRuntimeError):
            raise ControlError("DISPATCH_STATE_ACCESS_UNVERIFIED")
    if len(matches) != 1:
        raise ControlError("DISPATCH_STATE_ACCESS_UNVERIFIED")
    return matches[0]


@contextmanager
def control_session(path: Path, *, initialize_if_missing: bool = False) -> Iterator[sqlite3.Connection]:
    """Open one registry-bound, unfenced authority under its shared file lock."""
    target = path.expanduser().resolve()
    binding = _bound_authority(target)
    if not target.exists() and not initialize_if_missing:
        raise ControlError("DISPATCH_STATE_ACCESS_UNVERIFIED")
    try:
        assert_writable_binding(binding)
        with authority_lock(target):
            with connect(target) as db:
                authority = db.execute(
                    "SELECT deployment_key, daemon_ref FROM control_authority WHERE singleton=1"
                ).fetchone()
                expected = (binding["deployment_key"], binding["daemon_ref"])
                if authority is None:
                    db.execute(
                        "INSERT INTO control_authority(singleton,deployment_key,daemon_ref) VALUES(1,?,?)",
                        expected,
                    )
                elif (authority["deployment_key"], authority["daemon_ref"]) != expected:
                    raise ControlError("DISPATCH_AUTHORITY_MISMATCH")
                yield db
    except DispatchRuntimeError as error:
        raise ControlError(str(error)) from error


@contextmanager
def transaction(db: sqlite3.Connection) -> Iterator[None]:
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
    except Exception:
        db.execute("ROLLBACK")
        raise
    else:
        db.execute("COMMIT")


def admission_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "schema": "multica-orchestrator-dispatch.run-admission-ref.v1",
        "admission_ref": row["admission_ref"],
        "execution_ref": row["execution_ref"],
        "project_key": row["project_key"],
        "project_ref": row["project_ref"],
        "repository_ref": row["repository_ref"],
        "active_release_digest": row["active_release_digest"],
        "project_binding_digest": row["project_binding_digest"],
        "dispatch_contract_digest": row["dispatch_contract_digest"],
        "runtime_alias": row["runtime_alias"],
        "work_item_ref": row["work_item_ref"],
        "work_item_id": row["work_item_id"],
        "work_item_url": row["work_item_url"],
        "work_type": row["work_type"],
        "squad_ref": row["squad_ref"],
        "leader_ref": row["leader_ref"],
        "epoch": row["epoch"],
        "state": row["state"],
        "created_at": row["created_at"],
        "admission_digest": row["admission_digest"],
    }


def execution_admit(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    if args.work_type not in {"feature", "fix"}:
        raise ControlError("work-type must be feature or fix")
    for label, value in (
        ("active-release-digest", args.active_release_digest),
        ("project-binding-digest", args.project_binding_digest),
        ("dispatch-contract-digest", args.dispatch_contract_digest),
        ("project-key", args.project_key),
    ):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            raise ControlError(f"{label} must be a sha256 digest")
    with transaction(db):
        active = db.execute(
            "SELECT * FROM executions WHERE repository_ref=? AND work_item_ref=? AND state='ACTIVE'",
            (args.repository, args.work_item_ref),
        ).fetchone()
        if active is not None:
            expected = {
                "project_key": args.project_key,
                "project_ref": args.project,
                "repository_ref": args.repository,
                "active_release_digest": args.active_release_digest,
                "project_binding_digest": args.project_binding_digest,
                "dispatch_contract_digest": args.dispatch_contract_digest,
                "runtime_alias": args.runtime_alias,
                "work_type": args.work_type,
                "squad_ref": args.squad_ref,
                "leader_ref": args.leader_ref,
            }
            mismatches = [name for name, value in expected.items() if active[name] != value]
            if mismatches:
                raise ControlError("active execution admission differs: " + ", ".join(mismatches))
            admission = admission_from_row(active)
            _record_admission_resolution(db, admission, args)
            return admission
        epoch = db.execute(
            "SELECT COALESCE(MAX(epoch), 0) + 1 AS value FROM executions WHERE repository_ref=? AND work_item_ref=?",
            (args.repository, args.work_item_ref),
        ).fetchone()["value"]
        try:
            uuid.UUID(args.work_item_ref)
        except ValueError as error:
            raise ControlError("work-item-ref must be a Multica Issue UUID") from error
        if not args.work_item_id or args.work_item_id.isdecimal():
            raise ControlError("work-item-id must be a canonical routable Issue key")
        execution_ref = reference("WorkItemExecutionRef")
        admission_ref = reference("RunAdmissionRef")
        created_at = now()
        admission = {
            "schema": "multica-orchestrator-dispatch.run-admission-ref.v1",
            "admission_ref": admission_ref,
            "execution_ref": execution_ref,
            "project_key": args.project_key,
            "project_ref": args.project,
            "repository_ref": args.repository,
            "active_release_digest": args.active_release_digest,
            "project_binding_digest": args.project_binding_digest,
            "dispatch_contract_digest": args.dispatch_contract_digest,
            "runtime_alias": args.runtime_alias,
            "work_item_ref": args.work_item_ref,
            "work_item_id": args.work_item_id,
            "work_item_url": args.work_item_url,
            "work_type": args.work_type,
            "squad_ref": args.squad_ref,
            "leader_ref": args.leader_ref,
            "epoch": epoch,
            "state": "ACTIVE",
            "created_at": created_at,
        }
        admission["admission_digest"] = digest(canonical(admission))
        db.execute(
            "INSERT INTO executions("
            "execution_ref,admission_ref,project_key,project_ref,repository_ref,"
            "active_release_digest,project_binding_digest,dispatch_contract_digest,"
            "runtime_alias,work_item_ref,work_item_id,work_item_url,work_type,"
            "squad_ref,leader_ref,epoch,state,created_at,ended_at,admission_digest"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'ACTIVE',?,NULL,?)",
            (
                execution_ref, admission_ref, args.project_key, args.project,
                args.repository, args.active_release_digest,
                args.project_binding_digest, args.dispatch_contract_digest,
                args.runtime_alias, args.work_item_ref, args.work_item_id,
                args.work_item_url, args.work_type, args.squad_ref,
                args.leader_ref, epoch, created_at, admission["admission_digest"],
            ),
        )
        _record_admission_resolution(db, admission, args)
    return admission


def _record_admission_resolution(
    db: sqlite3.Connection, admission: Mapping[str, Any], args: argparse.Namespace
) -> None:
    provider_run_ref = getattr(args, "provider_run_ref", None)
    resolution = getattr(args, "resolution", None)
    if provider_run_ref is None and resolution is None:
        return
    if not isinstance(provider_run_ref, str) or not provider_run_ref or not isinstance(resolution, Mapping):
        raise ControlError("admission resolution fields are invalid")
    payload = dict(resolution)
    resolution_digest = digest(canonical(payload))
    db.execute(
        "INSERT OR IGNORE INTO admission_resolutions("
        "admission_ref,provider_run_ref,resolution_digest,payload_json,recorded_at"
        ") VALUES(?,?,?,?,?)",
        (admission["admission_ref"], provider_run_ref, resolution_digest, canonical(payload), now()),
    )


def execution_end(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    if args.state not in TERMINAL_EXECUTION_STATES:
        raise ControlError("execution terminal state is invalid")
    with transaction(db):
        row = db.execute(
            "SELECT state FROM executions WHERE execution_ref=?", (args.execution,)
        ).fetchone()
        if row is None or row["state"] != "ACTIVE":
            raise ControlError("execution is not active")
        active_run = db.execute(
            "SELECT run_ref FROM run_checkouts WHERE execution_ref=? AND state='ACTIVE'",
            (args.execution,),
        ).fetchone()
        if active_run is not None:
            raise ControlError("active run checkout must be released before execution end")
        ended_at = now()
        db.execute(
            "UPDATE executions SET state=?, ended_at=? WHERE execution_ref=?",
            (args.state, ended_at, args.execution),
        )
        db.execute(
            "UPDATE scopes SET state='RELEASED', released_at=? WHERE execution_ref=? AND state='ACTIVE'",
            (ended_at, args.execution),
        )
    return {"execution_ref": args.execution, "state": args.state, "ended_at": ended_at}


def ledger_append(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError as error:
        raise ControlError(f"payload is not valid JSON: {error.msg}") from error
    payload_json = canonical(payload)
    with transaction(db):
        head = db.execute("SELECT revision, event_hash FROM ledger_heads WHERE stream_ref=?", (args.stream,)).fetchone()
        current_revision = 0 if head is None else head["revision"]
        previous_hash = ZERO_HASH if head is None else head["event_hash"]
        if args.expected_revision != current_revision:
            raise ControlError(f"ledger CAS failed: expected {args.expected_revision}, current {current_revision}")
        revision = current_revision + 1
        event_hash = digest(canonical({
            "stream_ref": args.stream, "revision": revision,
            "previous_hash": previous_hash, "payload": payload,
        }))
        created_at = now()
        db.execute(
            "INSERT INTO ledger_events VALUES(?,?,?,?,?,?)",
            (args.stream, revision, previous_hash, event_hash, payload_json, created_at),
        )
        db.execute(
            "INSERT INTO ledger_heads VALUES(?,?,?) ON CONFLICT(stream_ref) DO UPDATE SET revision=excluded.revision,event_hash=excluded.event_hash",
            (args.stream, revision, event_hash),
        )
    return {
        "stream_ref": args.stream, "revision": revision, "previous_hash": previous_hash,
        "event_hash": event_hash, "created_at": created_at,
    }


def scope_overlaps(kind: str, left: str, right: str) -> bool:
    if kind != "path":
        return left == right
    left = left.strip("/")
    right = right.strip("/")
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def scope_claim(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    requested: list[tuple[str, str]] = []
    for value in args.scope:
        kind, separator, key = value.partition(":")
        if not separator or kind not in {"path", "resource", "dependency"} or not key.strip():
            raise ControlError("scope must be path:<value>, resource:<value>, or dependency:<value>")
        requested.append((kind, key.strip()))
    with transaction(db):
        execution = db.execute("SELECT project_ref, repository_ref, state FROM executions WHERE execution_ref=?", (args.execution,)).fetchone()
        if execution is None or execution["state"] != "ACTIVE":
            raise ControlError("execution is not active")
        rows = db.execute(
            "SELECT scopes.execution_ref, scopes.kind, scopes.scope_key FROM scopes "
            "JOIN executions ON executions.execution_ref=scopes.execution_ref "
            "WHERE executions.repository_ref=? AND scopes.state='ACTIVE' AND scopes.execution_ref<>?",
            (execution["repository_ref"], args.execution),
        ).fetchall()
        conflicts = [
            {"execution_ref": row["execution_ref"], "kind": kind, "scope_key": key, "held_scope_key": row["scope_key"]}
            for kind, key in requested for row in rows
            if row["kind"] == kind and scope_overlaps(kind, key, row["scope_key"])
        ]
        if conflicts:
            raise ControlError("scope conflict: " + canonical(conflicts))
        created_at = now()
        refs = []
        for kind, key in requested:
            existing = db.execute(
                "SELECT scope_ref FROM scopes WHERE execution_ref=? AND kind=? AND scope_key=? AND state='ACTIVE'",
                (args.execution, kind, key),
            ).fetchone()
            if existing is not None:
                refs.append(existing["scope_ref"])
                continue
            scope_ref = reference("WorkScopeRef")
            db.execute(
                "INSERT INTO scopes VALUES(?,?,?,?,?,'ACTIVE',?,NULL)",
                (scope_ref, execution["project_ref"], args.execution, kind, key, created_at),
            )
            refs.append(scope_ref)
    return {"execution_ref": args.execution, "gate": "CLEAR", "scope_refs": refs}


def lease_acquire(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=args.ttl)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with transaction(db):
        execution = db.execute("SELECT state FROM executions WHERE execution_ref=?", (args.execution,)).fetchone()
        if execution is None or execution["state"] != "ACTIVE":
            raise ControlError("execution is not active")
        head = db.execute("SELECT * FROM lease_heads WHERE resource_key=?", (args.resource,)).fetchone()
        current_revision = 0 if head is None else head["revision"]
        if args.expected_revision != current_revision:
            raise ControlError(f"lease CAS failed: expected {args.expected_revision}, current {current_revision}")
        if head is not None and head["state"] == "ACTIVE" and head["expires_at"] > now() and head["execution_ref"] != args.execution:
            raise ControlError("resource already has an active lease")
        revision = current_revision + 1
        created_at = now()
        db.execute("INSERT INTO lease_events VALUES(?,?,?,?,?,?)", (args.resource, revision, args.execution, "ACTIVE", expires_at, created_at))
        db.execute(
            "INSERT INTO lease_heads VALUES(?,?,?,?,?) ON CONFLICT(resource_key) DO UPDATE SET revision=excluded.revision,execution_ref=excluded.execution_ref,state=excluded.state,expires_at=excluded.expires_at",
            (args.resource, revision, args.execution, "ACTIVE", expires_at),
        )
    return {"resource_key": args.resource, "execution_ref": args.execution, "revision": revision, "state": "ACTIVE", "expires_at": expires_at}


def lease_release(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    with transaction(db):
        head = db.execute("SELECT * FROM lease_heads WHERE resource_key=?", (args.resource,)).fetchone()
        if head is None or head["state"] != "ACTIVE" or head["execution_ref"] != args.execution:
            raise ControlError("execution does not hold the active lease")
        if head["revision"] != args.expected_revision:
            raise ControlError(f"lease CAS failed: expected {args.expected_revision}, current {head['revision']}")
        revision = head["revision"] + 1
        created_at = now()
        db.execute("INSERT INTO lease_events VALUES(?,?,?,?,NULL,?)", (args.resource, revision, args.execution, "RELEASED", created_at))
        db.execute("UPDATE lease_heads SET revision=?,state='RELEASED',expires_at=NULL WHERE resource_key=?", (revision, args.resource))
    return {"resource_key": args.resource, "execution_ref": args.execution, "revision": revision, "state": "RELEASED"}


def queue_enter(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    with transaction(db):
        head = db.execute(
            "SELECT * FROM integration_heads WHERE repository_ref=? AND target_ref=?",
            (args.repository, args.target),
        ).fetchone()
        current_revision = 0 if head is None else head["revision"]
        if args.expected_revision != current_revision:
            raise ControlError(f"integration queue CAS failed: expected {args.expected_revision}, current {current_revision}")
        if head is not None and head["state"] in ACTIVE_QUEUE_STATES:
            raise ControlError("integration target already has an active attempt")
        revision = current_revision + 1
        attempt_ref = reference("IntegrationAttemptRef")
        created_at = now()
        values = (
            args.repository, args.target, revision, attempt_ref,
            args.source_head, args.target_head, "EVALUATING", None,
        )
        db.execute(
            "INSERT INTO integration_events("
            "repository_ref,target_ref,revision,attempt_ref,source_head,"
            "target_head,state,result_head,created_at"
            ") VALUES(?,?,?,?,?,?,?,?,?)",
            (*values, created_at),
        )
        db.execute(
            "INSERT INTO integration_heads("
            "repository_ref,target_ref,revision,attempt_ref,source_head,"
            "target_head,state,result_head"
            ") VALUES(?,?,?,?,?,?,?,?) "
            "ON CONFLICT(repository_ref,target_ref) DO UPDATE SET "
            "revision=excluded.revision,attempt_ref=excluded.attempt_ref,"
            "source_head=excluded.source_head,target_head=excluded.target_head,"
            "state=excluded.state,result_head=excluded.result_head",
            values,
        )
    return {"repository_ref": args.repository, "target_ref": args.target, "revision": revision, "attempt_ref": attempt_ref, "source_head": args.source_head, "target_head": args.target_head, "state": "EVALUATING"}

def queue_transition(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    allowed = {
        "EVALUATING": {"READY", "FAILED", "STALE"},
        "READY": {"MERGING", "FAILED", "STALE"},
        "MERGING": {"MERGED", "FAILED", "STALE"},
    }
    if args.state not in QUEUE_STATES:
        raise ControlError("integration queue state is invalid")
    with transaction(db):
        head = db.execute(
            "SELECT * FROM integration_heads WHERE repository_ref=? AND target_ref=?",
            (args.repository, args.target),
        ).fetchone()
        if head is None or head["attempt_ref"] != args.attempt:
            raise ControlError("integration attempt is not current")
        if head["revision"] != args.expected_revision:
            raise ControlError(
                f"integration queue CAS failed: expected {args.expected_revision}, current {head['revision']}"
            )
        if args.state not in allowed.get(head["state"], set()):
            raise ControlError(f"invalid integration transition {head['state']} -> {args.state}")
        state = args.state
        result_head = None
        if state in {"READY", "MERGING"} and (
            args.current_source_head != head["source_head"]
            or args.current_target_head != head["target_head"]
        ):
            state = "STALE"
        elif state == "MERGED":
            if not args.merge_head:
                raise ControlError("MERGED transition requires merge-head")
            if (
                args.current_source_head != head["source_head"]
                or args.current_target_head != args.merge_head
            ):
                state = "STALE"
            else:
                result_head = args.merge_head
        revision = head["revision"] + 1
        created_at = now()
        values = (
            args.repository, args.target, revision, args.attempt,
            head["source_head"], head["target_head"], state, result_head,
        )
        db.execute(
            "INSERT INTO integration_events("
            "repository_ref,target_ref,revision,attempt_ref,source_head,"
            "target_head,state,result_head,created_at"
            ") VALUES(?,?,?,?,?,?,?,?,?)",
            (*values, created_at),
        )
        db.execute(
            "UPDATE integration_heads SET revision=?,state=?,result_head=? "
            "WHERE repository_ref=? AND target_ref=?",
            (revision, state, result_head, args.repository, args.target),
        )
    return {
        "repository_ref": args.repository,
        "target_ref": args.target,
        "revision": revision,
        "attempt_ref": args.attempt,
        "source_head": head["source_head"],
        "target_head": head["target_head"],
        "state": state,
        "fresh": state != "STALE",
        "result_head": result_head,
    }



def notification_reserve(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    inputs = sorted(set(args.input_revision))
    dedupe_key = digest(canonical({
        "project_ref": args.project, "work_item_ref": args.work_item,
        "execution_ref": args.execution, "subject": args.subject,
        "designation_ref": args.designation, "plan_ref": args.plan,
        "sorted_input_revisions": inputs,
    }))
    with transaction(db):
        existing = db.execute("SELECT * FROM notification_reservations WHERE dedupe_key=?", (dedupe_key,)).fetchone()
        if existing is not None:
            return {"created": False, **dict(existing)}
        reservation_ref = reference("HumanNotificationReservationRef")
        reserved_at = now()
        next_reminder_at = (datetime.now(timezone.utc) + timedelta(hours=24)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        db.execute(
            "INSERT INTO notification_reservations VALUES(?,?,?,?,?,?,?,?,?,1,'RESERVED',0,?,?,NULL)",
            (reservation_ref, dedupe_key, args.project, args.work_item, args.execution, args.subject, args.designation, args.plan, canonical(inputs), reserved_at, next_reminder_at),
        )
        db.execute("INSERT INTO notification_events VALUES(?,1,'RESERVED',NULL,?)", (reservation_ref, reserved_at))
    return {"created": True, "reservation_ref": reservation_ref, "dedupe_key": dedupe_key, "revision": 1, "state": "RESERVED", "reminder_count": 0, "reserved_at": reserved_at, "next_reminder_at": next_reminder_at}


def notification_record(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    if args.state not in {"SENT", "FAILED", "SUPERSEDED"}:
        raise ControlError("notification terminal state is invalid")
    if args.state == "SENT" and not args.provider_receipt:
        raise ControlError("sent notification requires a provider receipt")
    with transaction(db):
        row = db.execute("SELECT * FROM notification_reservations WHERE reservation_ref=?", (args.reservation,)).fetchone()
        if row is None or row["state"] not in {"RESERVED", "SENT"}:
            raise ControlError("notification reservation is not current")
        if row["revision"] != args.expected_revision:
            raise ControlError(f"notification CAS failed: expected {args.expected_revision}, current {row['revision']}")
        revision = row["revision"] + 1
        created_at = now()
        db.execute("INSERT INTO notification_events VALUES(?,?,?,?,?)", (args.reservation, revision, args.state, args.provider_receipt, created_at))
        db.execute(
            "UPDATE notification_reservations SET revision=?,state=?,provider_receipt_ref=? WHERE reservation_ref=?",
            (revision, args.state, args.provider_receipt, args.reservation),
        )
    return {"reservation_ref": args.reservation, "revision": revision, "state": args.state, "provider_receipt_ref": args.provider_receipt}

def notification_reminder_reserve(
    db: sqlite3.Connection, args: argparse.Namespace
) -> dict[str, Any]:
    observed_at = (
        datetime.fromisoformat(args.at.replace("Z", "+00:00"))
        if args.at
        else datetime.now(timezone.utc)
    )
    with transaction(db):
        row = db.execute(
            "SELECT * FROM notification_reservations WHERE reservation_ref=?",
            (args.reservation,),
        ).fetchone()
        if row is None or row["state"] != "SENT":
            raise ControlError("initial notification has not been sent")
        if row["revision"] != args.expected_revision:
            raise ControlError(
                f"notification CAS failed: expected {args.expected_revision}, current {row['revision']}"
            )
        if row["reminder_count"] >= 2:
            raise ControlError("notification reminder limit reached")
        due_at = datetime.fromisoformat(row["next_reminder_at"].replace("Z", "+00:00"))
        if observed_at < due_at:
            raise ControlError("notification reminder is not due")
        reminder_count = row["reminder_count"] + 1
        revision = row["revision"] + 1
        next_reminder_at = None
        if reminder_count == 1:
            reserved_at = datetime.fromisoformat(row["reserved_at"].replace("Z", "+00:00"))
            next_reminder_at = (
                reserved_at + timedelta(hours=72)
            ).isoformat().replace("+00:00", "Z")
        created_at = now()
        event_state = f"REMINDER_{reminder_count}_RESERVED"
        db.execute(
            "INSERT INTO notification_events VALUES(?,?,?,?,?)",
            (args.reservation, revision, event_state, None, created_at),
        )
        db.execute(
            "UPDATE notification_reservations "
            "SET revision=?,reminder_count=?,next_reminder_at=? "
            "WHERE reservation_ref=?",
            (revision, reminder_count, next_reminder_at, args.reservation),
        )
    return {
        "reservation_ref": args.reservation,
        "revision": revision,
        "state": event_state,
        "reminder_count": reminder_count,
        "next_reminder_at": next_reminder_at,
    }


def notification_reminder_record(
    db: sqlite3.Connection, args: argparse.Namespace
) -> dict[str, Any]:
    if args.state not in {"SENT", "FAILED"}:
        raise ControlError("reminder result state is invalid")
    if args.state == "SENT" and not args.provider_receipt:
        raise ControlError("sent reminder requires a provider receipt")
    with transaction(db):
        row = db.execute(
            "SELECT * FROM notification_reservations WHERE reservation_ref=?",
            (args.reservation,),
        ).fetchone()
        if row is None or row["state"] != "SENT" or row["reminder_count"] == 0:
            raise ControlError("notification reminder is not reserved")
        if row["revision"] != args.expected_revision:
            raise ControlError(
                f"notification CAS failed: expected {args.expected_revision}, current {row['revision']}"
            )
        latest = db.execute(
            "SELECT state FROM notification_events "
            "WHERE reservation_ref=? ORDER BY revision DESC LIMIT 1",
            (args.reservation,),
        ).fetchone()
        expected_state = f"REMINDER_{row['reminder_count']}_RESERVED"
        if latest is None or latest["state"] != expected_state:
            raise ControlError("current reminder reservation is already resolved")
        revision = row["revision"] + 1
        event_state = f"REMINDER_{row['reminder_count']}_{args.state}"
        created_at = now()
        db.execute(
            "INSERT INTO notification_events VALUES(?,?,?,?,?)",
            (args.reservation, revision, event_state, args.provider_receipt, created_at),
        )
        db.execute(
            "UPDATE notification_reservations SET revision=? WHERE reservation_ref=?",
            (revision, args.reservation),
        )
    return {
        "reservation_ref": args.reservation,
        "revision": revision,
        "state": event_state,
        "provider_receipt_ref": args.provider_receipt,
    }



def human_designate(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    with transaction(db):
        current = db.execute(
            "SELECT * FROM human_designations WHERE project_ref=?",
            (args.project,),
        ).fetchone()
        if (
            current is not None
            and current["account_ref"] == args.account
            and current["consent_ref"] == args.consent_ref
            and current["state"] == "VERIFIED"
        ):
            return {**dict(current), "created": False}
        designation_ref = reference("HumanDesignationRef")
        revision = 1 if current is None else int(current["revision"]) + 1
        recorded_at = now()
        db.execute(
            "INSERT INTO human_designations("
            "project_ref,designation_ref,account_ref,consent_ref,revision,state,recorded_at"
            ") VALUES(?,?,?,?,?,'VERIFIED',?) "
            "ON CONFLICT(project_ref) DO UPDATE SET "
            "designation_ref=excluded.designation_ref,account_ref=excluded.account_ref,"
            "consent_ref=excluded.consent_ref,revision=excluded.revision,"
            "state=excluded.state,recorded_at=excluded.recorded_at",
            (args.project, designation_ref, args.account, args.consent_ref, revision, recorded_at),
        )
    return {
        "project_ref": args.project,
        "designation_ref": designation_ref,
        "account_ref": args.account,
        "consent_ref": args.consent_ref,
        "revision": revision,
        "state": "VERIFIED",
        "recorded_at": recorded_at,
        "created": True,
    }


def human_decision_record(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    if args.decision not in {"APPROVED", "REJECTED"}:
        raise ControlError("Human decision must be APPROVED or REJECTED")
    with transaction(db):
        designation = db.execute(
            "SELECT * FROM human_designations WHERE project_ref=?",
            (args.project,),
        ).fetchone()
        if (
            designation is None
            or designation["state"] != "VERIFIED"
            or designation["account_ref"] != args.account
        ):
            raise ControlError("authenticated account does not match the current Human designation")
        attempt = db.execute(
            "SELECT * FROM integration_heads WHERE repository_ref=? AND target_ref=?",
            (args.repository, args.target),
        ).fetchone()
        if (
            attempt is None
            or attempt["attempt_ref"] != args.attempt
            or attempt["source_head"] != args.source_head
            or attempt["target_head"] != args.target_head
            or attempt["state"] not in {"EVALUATING", "READY"}
        ):
            raise ControlError("Human decision does not match the current frozen integration attempt")
        existing = db.execute(
            "SELECT * FROM human_decisions WHERE attempt_ref=?",
            (args.attempt,),
        ).fetchone()
        if existing is not None:
            if (
                existing["actor_account_ref"] == args.account
                and existing["decision"] == args.decision
                and existing["source_head"] == args.source_head
                and existing["target_head"] == args.target_head
            ):
                return {**dict(existing), "created": False}
            raise ControlError("integration attempt already has a different Human decision")
        decision_ref = reference("HumanDecisionRef")
        recorded_at = now()
        db.execute(
            "INSERT INTO human_decisions("
            "decision_ref,project_ref,repository_ref,target_ref,attempt_ref,"
            "source_head,target_head,designation_ref,actor_account_ref,actor_type,"
            "decision,recorded_at"
            ") VALUES(?,?,?,?,?,?,?,?,?,'human',?,?)",
            (
                decision_ref,
                args.project,
                args.repository,
                args.target,
                args.attempt,
                args.source_head,
                args.target_head,
                designation["designation_ref"],
                args.account,
                args.decision,
                recorded_at,
            ),
        )
    return {
        "decision_ref": decision_ref,
        "project_ref": args.project,
        "repository_ref": args.repository,
        "target_ref": args.target,
        "attempt_ref": args.attempt,
        "source_head": args.source_head,
        "target_head": args.target_head,
        "designation_ref": designation["designation_ref"],
        "actor_account_ref": args.account,
        "actor_type": "human",
        "decision": args.decision,
        "recorded_at": recorded_at,
        "created": True,
    }


def git_readback(root: Path, *values: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *values],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if completed.returncode:
        raise ControlError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout.strip()


def branch_bind(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    with transaction(db):
        execution = db.execute(
            "SELECT * FROM executions WHERE execution_ref=?", (args.execution,)
        ).fetchone()
        if execution is None or execution["state"] != "ACTIVE":
            raise ControlError("execution is not active")
        existing = db.execute(
            "SELECT * FROM work_item_branches WHERE execution_ref=?", (args.execution,)
        ).fetchone()
        if existing is not None:
            expected = {
                "integration_branch": args.integration_branch,
                "base_ref": args.base,
                "target_ref": args.target,
                "current_head_revision": args.head,
            }
            if any(existing[key] != value for key, value in expected.items()):
                raise ControlError("work item branch binding conflicts with current state")
            return {"created": False, **dict(existing)}
        timestamp = now()
        values = (
            args.execution,
            execution["repository_ref"],
            execution["work_item_ref"],
            args.integration_branch,
            args.base,
            args.target,
            args.head,
            1,
            args.provider_receipt,
            timestamp,
            timestamp,
        )
        db.execute(
            "INSERT INTO work_item_branches VALUES(?,?,?,?,?,?,?,?,?,?,?)", values
        )
    return {
        "created": True,
        "execution_ref": args.execution,
        "integration_branch": args.integration_branch,
        "base_ref": args.base,
        "target_ref": args.target,
        "current_head_revision": args.head,
        "revision": 1,
        "provider_receipt_ref": args.provider_receipt,
        "bound_at": timestamp,
        "updated_at": timestamp,
    }


def branch_advance(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise ControlError("repository root is not a directory")
    git_readback(root, "merge-base", "--is-ancestor", args.expected_head, args.head)
    with transaction(db):
        branch = db.execute(
            "SELECT * FROM work_item_branches WHERE execution_ref=?", (args.execution,)
        ).fetchone()
        execution = db.execute(
            "SELECT state FROM executions WHERE execution_ref=?", (args.execution,)
        ).fetchone()
        if execution is None or execution["state"] != "ACTIVE":
            raise ControlError("execution is not active")
        if branch is None:
            raise ControlError("work item branch is not bound")
        if branch["current_head_revision"] != args.expected_head:
            raise ControlError(
                "integration branch head CAS failed: "
                f"expected {args.expected_head}, current {branch['current_head_revision']}"
            )
        revision = branch["revision"] + 1
        timestamp = now()
        db.execute(
            "UPDATE work_item_branches SET current_head_revision=?, revision=?, "
            "provider_receipt_ref=?, updated_at=? WHERE execution_ref=?",
            (args.head, revision, args.provider_receipt, timestamp, args.execution),
        )
    return {
        **dict(branch),
        "current_head_revision": args.head,
        "previous_head_revision": args.expected_head,
        "revision": revision,
        "provider_receipt_ref": args.provider_receipt,
        "updated_at": timestamp,
    }


def run_checkout_bind(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise ControlError("run checkout root is not a directory")
    actual_root = Path(git_readback(root, "rev-parse", "--show-toplevel")).resolve()
    actual_branch = git_readback(root, "branch", "--show-current")
    actual_head = git_readback(root, "rev-parse", "HEAD")
    if (
        actual_root != root
        or actual_branch != args.runtime_branch
        or actual_head != args.head
        or git_readback(root, "status", "--porcelain")
    ):
        raise ControlError("run checkout root, branch, HEAD, or clean state is invalid")
    with transaction(db):
        execution = db.execute(
            "SELECT state FROM executions WHERE execution_ref=?", (args.execution,)
        ).fetchone()
        if execution is None or execution["state"] != "ACTIVE":
            raise ControlError("execution is not active")
        branch = db.execute(
            "SELECT * FROM work_item_branches WHERE execution_ref=?", (args.execution,)
        ).fetchone()
        if branch is None or branch["current_head_revision"] != args.baseline:
            raise ControlError("run baseline differs from current integration branch head")
        if args.head != args.baseline:
            raise ControlError("new run checkout must start at its declared baseline")
        existing = db.execute(
            "SELECT * FROM run_checkouts WHERE run_ref=?", (args.run,)
        ).fetchone()
        if existing is not None:
            return {"created": False, **dict(existing)}
        active = db.execute(
            "SELECT run_ref FROM run_checkouts WHERE execution_ref=? AND state='ACTIVE'",
            (args.execution,),
        ).fetchone()
        if active is not None:
            raise ControlError("another writer run is active for this work item")
        state_root = (
            Path(args.state_root).expanduser().resolve()
            / digest(args.run).split(":", 1)[1]
        )
        state_root.mkdir(mode=0o700, parents=True, exist_ok=False)
        state_root.chmod(0o700)
        index_file = state_root / "git.index"
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = str(index_file)
        git_readback(root, "read-tree", "HEAD", env=environment)
        index_file.chmod(0o600)
        session_ref = reference("ExecutionSessionRef")
        bound_at = now()
        values = (
            args.run,
            args.execution,
            args.runtime,
            args.daemon,
            args.resource,
            str(root),
            args.runtime_branch,
            args.ownership_ref,
            args.baseline,
            args.head,
            session_ref,
            str(state_root),
            str(index_file),
            "ACTIVE",
            bound_at,
            None,
        )
        db.execute(
            "INSERT INTO run_checkouts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values
        )
    return {
        "created": True,
        "run_ref": args.run,
        "execution_ref": args.execution,
        "runtime_ref": args.runtime,
        "daemon_ref": args.daemon,
        "resource_ref": args.resource,
        "checkout_root": str(root),
        "runtime_branch": args.runtime_branch,
        "ownership_ref": args.ownership_ref,
        "baseline_revision": args.baseline,
        "head_revision": args.head,
        "session_ref": session_ref,
        "state_namespace": str(state_root),
        "git_index_file": str(index_file),
        "state": "ACTIVE",
        "bound_at": bound_at,
        "released_at": None,
    }


def run_checkout_refresh(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise ControlError("run checkout root is not a directory")
    actual_root = Path(git_readback(root, "rev-parse", "--show-toplevel")).resolve()
    actual_branch = git_readback(root, "branch", "--show-current")
    actual_head = git_readback(root, "rev-parse", "HEAD")
    if (
        actual_root != root
        or actual_branch != args.runtime_branch
        or actual_head != args.head
        or git_readback(root, "status", "--porcelain")
    ):
        raise ControlError("run checkout root, branch, HEAD, or clean state is invalid")
    with transaction(db):
        checkout = db.execute(
            "SELECT * FROM run_checkouts WHERE run_ref=? AND execution_ref=?",
            (args.run, args.execution),
        ).fetchone()
        if checkout is None or checkout["state"] != "ACTIVE":
            raise ControlError("active run checkout is not bound")
        if (
            Path(checkout["checkout_root"]) != root
            or checkout["runtime_branch"] != args.runtime_branch
        ):
            raise ControlError("run checkout root or Runtime branch changed")
        if checkout["head_revision"] != args.expected_head:
            raise ControlError(
                "run checkout head CAS failed: "
                f"expected {args.expected_head}, current {checkout['head_revision']}"
            )
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = checkout["git_index_file"]
        git_readback(root, "read-tree", "HEAD", env=environment)
        db.execute(
            "UPDATE run_checkouts SET head_revision=? WHERE run_ref=?",
            (args.head, args.run),
        )
    return {
        **dict(checkout),
        "head_revision": args.head,
        "previous_head_revision": args.expected_head,
        "refreshed_at": now(),
    }


def run_checkout_release(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    with transaction(db):
        checkout = db.execute(
            "SELECT * FROM run_checkouts WHERE run_ref=? AND execution_ref=?",
            (args.run, args.execution),
        ).fetchone()
        if checkout is None or checkout["state"] != "ACTIVE":
            raise ControlError("active run checkout is not bound")
        released_at = now()
        db.execute(
            "UPDATE run_checkouts SET state=?, released_at=? WHERE run_ref=?",
            (args.state, released_at, args.run),
        )
    return {**dict(checkout), "state": args.state, "released_at": released_at}


def readback(db: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    active_executions = [dict(row) for row in db.execute("SELECT * FROM executions WHERE project_ref=? AND state='ACTIVE' ORDER BY created_at", (args.project,))]
    execution_refs = [item["execution_ref"] for item in active_executions]
    scopes: list[dict[str, Any]] = []
    if execution_refs:
        placeholders = ",".join("?" for _ in execution_refs)
        scopes = [
            dict(row)
            for row in db.execute(
                f"SELECT * FROM scopes WHERE execution_ref IN ({placeholders}) "
                "AND state='ACTIVE' ORDER BY scope_ref",
                execution_refs,
            )
        ]
    branches = [dict(row) for row in db.execute(
        "SELECT * FROM work_item_branches WHERE execution_ref IN "
        f"({','.join('?' for _ in execution_refs)}) ORDER BY execution_ref",
        execution_refs,
    )] if execution_refs else []
    checkouts = [dict(row) for row in db.execute(
        "SELECT * FROM run_checkouts WHERE execution_ref IN "
        f"({','.join('?' for _ in execution_refs)}) ORDER BY bound_at",
        execution_refs,
    )] if execution_refs else []
    return {
        "schema_version": SCHEMA_VERSION,
        "integrity": integrity,
        "project_ref": args.project,
        "active_executions": active_executions,
        "active_scopes": scopes,
        "work_item_branches": branches,
        "run_checkouts": checkouts,
        "ledger_heads": [dict(row) for row in db.execute("SELECT * FROM ledger_heads ORDER BY stream_ref")],
        "lease_heads": [dict(row) for row in db.execute("SELECT * FROM lease_heads ORDER BY resource_key")],
        "integration_heads": [dict(row) for row in db.execute("SELECT * FROM integration_heads ORDER BY repository_ref,target_ref")],
        "notification_reservations": [dict(row) for row in db.execute("SELECT * FROM notification_reservations ORDER BY reserved_at")],
        "human_designations": [dict(row) for row in db.execute("SELECT * FROM human_designations WHERE project_ref=?", (args.project,))],
        "human_decisions": [dict(row) for row in db.execute("SELECT * FROM human_decisions WHERE project_ref=? ORDER BY recorded_at", (args.project,))],
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--db", type=Path, required=True)
    commands = result.add_subparsers(dest="command", required=True)


    command = commands.add_parser("execution-end")
    command.add_argument("--execution", required=True)
    command.add_argument("--state", required=True)
    command.set_defaults(handler=execution_end)

    command = commands.add_parser("ledger-append")
    command.add_argument("--stream", required=True)
    command.add_argument("--expected-revision", type=int, required=True)
    command.add_argument("--payload", required=True)
    command.set_defaults(handler=ledger_append)

    command = commands.add_parser("scope-claim")
    command.add_argument("--execution", required=True)
    command.add_argument("--scope", action="append", required=True)
    command.set_defaults(handler=scope_claim)

    command = commands.add_parser("lease-acquire")
    command.add_argument("--execution", required=True)
    command.add_argument("--resource", required=True)
    command.add_argument("--expected-revision", type=int, required=True)
    command.add_argument("--ttl", type=int, default=3600)
    command.set_defaults(handler=lease_acquire)

    command = commands.add_parser("lease-release")
    command.add_argument("--execution", required=True)
    command.add_argument("--resource", required=True)
    command.add_argument("--expected-revision", type=int, required=True)
    command.set_defaults(handler=lease_release)

    command = commands.add_parser("queue-enter")
    for name in ("repository", "target", "source-head", "target-head"):
        command.add_argument(f"--{name}", required=True)
    command.add_argument("--expected-revision", type=int, required=True)
    command.set_defaults(handler=queue_enter)

    command = commands.add_parser("queue-transition")
    for name in (
        "repository", "target", "attempt", "state",
        "current-source-head", "current-target-head",
    ):
        command.add_argument(f"--{name}", required=True)
    command.add_argument("--expected-revision", type=int, required=True)
    command.add_argument("--merge-head")
    command.set_defaults(handler=queue_transition)

    command = commands.add_parser("notification-reserve")
    for name in ("project", "work-item", "execution", "subject", "designation", "plan"):
        command.add_argument(f"--{name}", required=True)
    command.add_argument("--input-revision", action="append", required=True)
    command.set_defaults(handler=notification_reserve)

    command = commands.add_parser("notification-record")
    command.add_argument("--reservation", required=True)
    command.add_argument("--expected-revision", type=int, required=True)
    command.add_argument("--state", required=True)
    command.add_argument("--provider-receipt")
    command.set_defaults(handler=notification_record)

    command = commands.add_parser("notification-reminder-reserve")
    command.add_argument("--reservation", required=True)
    command.add_argument("--expected-revision", type=int, required=True)
    command.add_argument("--at")
    command.set_defaults(handler=notification_reminder_reserve)

    command = commands.add_parser("notification-reminder-record")
    command.add_argument("--reservation", required=True)
    command.add_argument("--expected-revision", type=int, required=True)
    command.add_argument("--state", required=True)
    command.add_argument("--provider-receipt")
    command.set_defaults(handler=notification_reminder_record)

    command = commands.add_parser("human-designate")
    command.add_argument("--project", required=True)
    command.add_argument("--account", required=True)
    command.add_argument("--consent-ref", required=True)
    command.set_defaults(handler=human_designate)

    command = commands.add_parser("human-decision-record")
    for name in (
        "project", "repository", "target", "attempt", "source-head",
        "target-head", "account", "decision",
    ):
        command.add_argument(f"--{name}", required=True)
    command.set_defaults(handler=human_decision_record)

    command = commands.add_parser("branch-bind")
    for name in ("execution", "integration-branch", "base", "target", "head", "provider-receipt"):
        command.add_argument(f"--{name}", required=True)
    command.set_defaults(handler=branch_bind)

    command = commands.add_parser("branch-advance")
    for name in ("execution", "root", "expected-head", "head", "provider-receipt"):
        command.add_argument(f"--{name}", required=True)
    command.set_defaults(handler=branch_advance)

    command = commands.add_parser("run-checkout-bind")
    for name in (
        "execution", "run", "runtime", "daemon", "resource", "root",
        "runtime-branch", "ownership-ref", "baseline", "head", "state-root",
    ):
        command.add_argument(f"--{name}", required=True)
    command.set_defaults(handler=run_checkout_bind)

    command = commands.add_parser("run-checkout-refresh")
    for name in ("execution", "run", "root", "runtime-branch", "expected-head", "head"):
        command.add_argument(f"--{name}", required=True)
    command.set_defaults(handler=run_checkout_refresh)

    command = commands.add_parser("run-checkout-release")
    command.add_argument("--execution", required=True)
    command.add_argument("--run", required=True)
    command.add_argument(
        "--state", choices=("RELEASED", "RETAINED_ON_FAILURE"), required=True
    )
    command.set_defaults(handler=run_checkout_release)

    command = commands.add_parser("readback")
    command.add_argument("--project", required=True)
    command.set_defaults(handler=readback)
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        with control_session(arguments.db) as db:
            output = arguments.handler(db, arguments)
    except (ControlError, sqlite3.Error, OSError) as error:
        print(canonical({"error": str(error), "state": "BLOCKED"}), file=sys.stderr)
        return 1
    print(canonical(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
