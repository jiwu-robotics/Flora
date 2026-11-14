"""Resolve authenticated Multica profile and Workspace identity from live CLI readback."""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Mapping

from multica_state_bundle.identities import StateError

PROXIES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
AUTH_SERVER = re.compile(r"^Server:\s+(\S+)\s*$", re.MULTILINE)
AUTH_ACCOUNT = re.compile(r"^User:\s+.*\(([^()]+)\)\s*$", re.MULTILINE)
CONFIG_FIELD = re.compile(r"^([a-z_]+):\s+(.*?)\s*$", re.MULTILINE)


def environment(server_kind: str = "self-hosted") -> dict[str, str]:
    value = dict(os.environ)
    if server_kind == "self-hosted":
        for name in PROXIES:
            value.pop(name, None)
    return value


def records(value: Any, label: str) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        values = value
    elif isinstance(value, Mapping):
        values = next((value[key] for key in ("items", "data", "results", "workspaces") if isinstance(value.get(key), list)), None)
        if values is None:
            raise StateError(f"{label} does not contain a record list")
    else:
        raise StateError(f"{label} must be a list or wrapped list")
    if not all(isinstance(item, Mapping) for item in values):
        raise StateError(f"{label} records must be objects")
    return list(values)


def infer_server_kind(server_ref: str) -> str:
    return "cloud" if re.fullmatch(r"https://(?:api\.)?multica\.ai/?", server_ref) else "self-hosted"


@dataclass(frozen=True)
class ProfileSession:
    profile: str
    server_kind: str
    server_ref: str
    account_ref: str
    workspace_ref: str
    workspace: Mapping[str, Any]

    @property
    def multica(self) -> dict[str, str]:
        return {"profile": self.profile, "server_kind": self.server_kind, "server_ref": self.server_ref, "account_ref": self.account_ref}

    def command(self, arguments: list[str], *, workspace: bool = False, json_output: bool = True) -> list[str]:
        command = ["multica", "--profile", self.profile]
        if workspace:
            command.extend(["--workspace-id", self.workspace_ref])
        command.extend(arguments)
        if json_output:
            command.extend(["--output", "json"])
        return command

    def read_json(self, arguments: list[str], *, workspace: bool = False) -> Any:
        completed = subprocess.run(self.command(arguments, workspace=workspace), text=True, capture_output=True, env=environment(self.server_kind), check=False)
        if completed.returncode:
            raise StateError((completed.stderr or completed.stdout).strip() or "Multica readback failed")
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise StateError("Multica readback did not return JSON") from error


def resolve_profile_session(profile: str, workspace_selector: str | None) -> ProfileSession:
    completed = subprocess.run(["multica", "--profile", profile, "auth", "status"], text=True, capture_output=True, env=environment(), check=False)
    if completed.returncode:
        raise StateError("AUTHENTICATION_REQUIRED: invoke multica-login for the requested profile")
    output = completed.stdout + completed.stderr
    server = AUTH_SERVER.search(output)
    account = AUTH_ACCOUNT.search(output)
    if server is None or account is None:
        raise StateError("authenticated profile readback lacks server or account identity")
    server_ref = server.group(1)
    server_kind = infer_server_kind(server_ref)
    config = subprocess.run(["multica", "--profile", profile, "config", "show"], text=True, capture_output=True, env=environment(server_kind), check=False)
    if config.returncode:
        raise StateError((config.stderr or config.stdout).strip() or "profile configuration readback failed")
    configured = {key: value for key, value in CONFIG_FIELD.findall(config.stdout)}
    if configured.get("server_url") and configured["server_url"] != server_ref:
        raise StateError("authenticated server differs from profile configuration")
    listing = subprocess.run(["multica", "--profile", profile, "workspace", "list", "--output", "json"], text=True, capture_output=True, env=environment(server_kind), check=False)
    if listing.returncode:
        raise StateError((listing.stderr or listing.stdout).strip() or "Workspace list failed")
    try:
        values = records(json.loads(listing.stdout), "Workspace list")
    except json.JSONDecodeError as error:
        raise StateError("Workspace list did not return JSON") from error
    effective = workspace_selector or configured.get("workspace_id")
    matches = [item for item in values if effective is None or effective in {item.get("id"), item.get("workspace_id"), item.get("name"), item.get("slug")}]
    if len(matches) != 1:
        raise StateError(f"Workspace selection must resolve exactly one record; observed {len(matches)}")
    workspace = matches[0]
    workspace_ref = workspace.get("id", workspace.get("workspace_id"))
    if not isinstance(workspace_ref, str) or not workspace_ref:
        raise StateError("selected Workspace lacks an id")
    return ProfileSession(profile, server_kind, server_ref, account.group(1), workspace_ref, workspace)
