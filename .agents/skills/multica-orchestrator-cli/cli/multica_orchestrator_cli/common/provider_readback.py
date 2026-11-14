"""Strict adapter for the supported Multica Issue and AgentTask readback shapes."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping


class ProviderReadbackError(ValueError):
    """The installed provider wrapper cannot prove an execution identity."""


ISSUE_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*-[1-9][0-9]*$")
ACTIVE_RUN_STATES = frozenset({"queued", "dispatched", "running"})
TERMINAL_ISSUE_STATES = frozenset({"done", "cancelled"})


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProviderReadbackError(f"PROVIDER_READBACK_UNSUPPORTED: {label} must be an object")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProviderReadbackError(f"PROVIDER_READBACK_UNSUPPORTED: {label} must be a non-empty string")
    return value


def issue_object(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping) and set(value) == {"issue"}:
        value = value["issue"]
    issue = _object(value, "Issue readback")
    allowed = {"id", "workspace_id", "identifier", "project_id", "assignee_type", "assignee_id", "status", "revision", "url"}
    if not set(issue) <= allowed:
        raise ProviderReadbackError("PROVIDER_READBACK_UNSUPPORTED: Issue wrapper or fields are unknown")
    for field in ("id", "workspace_id", "identifier", "assignee_type", "assignee_id", "status"):
        _string(issue.get(field), f"Issue.{field}")
    if issue["assignee_type"] != "squad":
        raise ProviderReadbackError("ISSUE_CLASSIFICATION_REQUIRED")
    if issue.get("project_id") is not None:
        _string(issue["project_id"], "Issue.project_id")
    if not ISSUE_KEY.fullmatch(issue["identifier"]):
        raise ProviderReadbackError("ISSUE_IDENTITY_MISMATCH")
    return issue


def run_objects(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping) and set(value) == {"tasks"}:
        value = value["tasks"]
    if not isinstance(value, list):
        raise ProviderReadbackError("PROVIDER_READBACK_UNSUPPORTED: runs must be an array or {tasks: array}")
    result: list[Mapping[str, Any]] = []
    for index, candidate in enumerate(value):
        run = _object(candidate, f"runs[{index}]")
        allowed = {"id", "agent_id", "runtime_id", "issue_id", "status", "trigger_comment_id", "parent_task_id", "attribution"}
        if not set(run) <= allowed:
            raise ProviderReadbackError("PROVIDER_READBACK_UNSUPPORTED: AgentTask wrapper or fields are unknown")
        for field in ("id", "agent_id", "runtime_id", "issue_id", "status"):
            _string(run.get(field), f"runs[{index}].{field}")
        result.append(run)
    return result


def runtime_object(value: Any, runtime_ref: str) -> Mapping[str, Any]:
    """Select one Runtime from the documented bare-array or wrapper response."""
    if isinstance(value, Mapping) and set(value) == {"runtimes"}:
        value = value["runtimes"]
    if not isinstance(value, list):
        raise ProviderReadbackError("PROVIDER_READBACK_UNSUPPORTED: runtimes must be an array or {runtimes: array}")
    allowed = {"id", "runtime_id", "daemon_id", "daemon_ref", "status", "provider", "runtime_mode", "mode", "runtime_version", "version", "capabilities", "metadata"}
    matches = [record for record in value if isinstance(record, Mapping) and record.get("id", record.get("runtime_id")) == runtime_ref]
    if len(matches) != 1 or not set(matches[0]) <= allowed:
        raise ProviderReadbackError("RUNTIME_CAPABILITY_MISMATCH")
    return matches[0]


def issue_snapshot(issue: Mapping[str, Any]) -> str:
    revision = issue.get("revision")
    if revision is not None:
        return _string(revision, "Issue.revision")
    identity = {field: issue.get(field) for field in ("id", "workspace_id", "identifier", "project_id", "assignee_type", "assignee_id", "status")}
    return "sha256:" + hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def current_leader_run(runs: list[Mapping[str, Any]], *, issue_id: str, leader_ref: str, runtime_ref: str, run_ref: str | None) -> Mapping[str, Any]:
    matches = [run for run in runs if run["issue_id"] == issue_id and run["agent_id"] == leader_ref and run["runtime_id"] == runtime_ref and run["status"] == "running"]
    if run_ref is not None:
        matches = [run for run in matches if run["id"] == run_ref]
    if len(matches) != 1:
        raise ProviderReadbackError("LEADER_RUN_CONTEXT_REQUIRED")
    return matches[0]
