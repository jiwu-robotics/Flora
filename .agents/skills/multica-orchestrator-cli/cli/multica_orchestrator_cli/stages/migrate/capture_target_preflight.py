#!/usr/bin/env python3
"""Capture read-only Multica, daemon, Project resource, and Git state over pinned SSH."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from multica_state_bundle.handoff import digest_bytes
from multica_state_bundle.identities import canonical_json, utc_now
from multica_state_bundle.storage import atomic_bytes
from multica_orchestrator_cli.common.runtime_capability import RuntimeCapabilityEvidenceError, runtime_capabilities, runtime_capability_revision
from migration_common import (
    MigrationError,
    NATIVE_SQUAD_CLI_REQUIREMENTS,
    PREFLIGHT_SCHEMA,
    PROXY_NAMES,
    encoded,
    load_input,
    load_release_context,
    local_directory_execution_mode,
    local_directory_resource_matches,
    nested_contains,
    parse_json_stdout,
    records,
    native_squad_capability_errors,
    ssh_command,
    target_context,
)


def multica_arguments(configuration: dict, target: dict, command: list[str], *, workspace: bool = False, output_json: bool = False) -> list[str]:
    arguments: list[str] = []
    if configuration["server"]["kind"] == "self-hosted":
        arguments.extend(["env", *(part for name in PROXY_NAMES for part in ("-u", name))])
    arguments.extend(["multica", "--profile", target["profile"]])
    if workspace:
        arguments.extend(["--workspace-id", configuration["server"]["workspace_ref"]])
    arguments.extend(command)
    if output_json:
        arguments.extend(["--output", "json"])
    return arguments


def one_target(configuration: dict, project_bundle, candidate: dict, target: dict) -> dict:
    context = target_context(configuration, project_bundle, target["runtime_alias"])
    host = target["ssh_config_host"]
    version = ssh_command(host, ["multica", "version"])
    capability_help = {
        name: ssh_command(host, ["multica", *command, "--help"], allow_failure=True)
        for name, (command, _) in NATIVE_SQUAD_CLI_REQUIREMENTS.items()
    }
    auth = ssh_command(host, multica_arguments(configuration, target, ["auth", "status"]))
    config = ssh_command(host, multica_arguments(configuration, target, ["config", "show"]))
    workspaces_completed = ssh_command(host, multica_arguments(configuration, target, ["workspace", "list"], output_json=True))
    runtimes_completed = ssh_command(host, multica_arguments(configuration, target, ["runtime", "list"], workspace=True, output_json=True))
    daemon_completed = ssh_command(host, multica_arguments(configuration, target, ["daemon", "status"], output_json=True))
    resources_completed = ssh_command(host, multica_arguments(configuration, target, ["project", "resource", "list", context["project_ref"]], workspace=True, output_json=True))
    workspaces = parse_json_stdout(workspaces_completed, "workspace list")
    runtimes = parse_json_stdout(runtimes_completed, "Runtime list")
    daemon = parse_json_stdout(daemon_completed, "daemon status")
    resources = parse_json_stdout(resources_completed, "Project resource list")
    expected_runtime = context["runtime"]
    runtime_matches = [item for item in records(runtimes, "Runtime list") if item.get("id", item.get("runtime_id")) == expected_runtime["runtime_ref"]]
    workspace_matches = [item for item in records(workspaces, "workspace list") if item.get("id", item.get("workspace_id")) == configuration["server"]["workspace_ref"]]
    local_resources = [
        item for item in records(resources, "Project resource list")
        if local_directory_resource_matches(
            item,
            root=target["repository_root"],
            daemon_ref=expected_runtime["daemon_ref"],
        )
    ]
    blockers: list[str] = []
    version_match = re.search(r"(?:^|\s)v?(\d+)\.(\d+)\.(\d+)(?:\s|$)", version.stdout)
    if version_match is None or tuple(map(int, version_match.groups())) < (0, 4, 26):
        blockers.append("MULTICA_VERSION_UNSUPPORTED")
    capability_results = {
        name: (completed.returncode, completed.stdout + completed.stderr)
        for name, completed in capability_help.items()
    }
    blockers.extend(native_squad_capability_errors(capability_results))
    if len(workspace_matches) != 1:
        blockers.append("WORKSPACE_NOT_VISIBLE")
    if target["account_ref"] not in (auth.stdout + auth.stderr):
        blockers.append("ACCOUNT_IDENTITY_UNVERIFIED")
    if configuration["server"]["ref"] not in (config.stdout + config.stderr):
        blockers.append("SERVER_IDENTITY_UNVERIFIED")
    if len(runtime_matches) != 1:
        blockers.append("RUNTIME_NOT_VISIBLE")
    else:
        runtime = runtime_matches[0]
        if runtime.get("status") != "online":
            blockers.append("RUNTIME_NOT_ONLINE")
        if runtime.get("daemon_id", runtime.get("daemon_ref")) != expected_runtime["daemon_ref"]:
            blockers.append("RUNTIME_DAEMON_MISMATCH")
        try:
            capability_revision = runtime_capability_revision(runtime)
            worktree_capable = "local-worktree-v1" in runtime_capabilities(runtime)
        except RuntimeCapabilityEvidenceError as error:
            blockers.append(str(error))
        else:
            if (
                capability_revision != expected_runtime.get("capability_revision")
                or capability_revision != context["target_policy"].get("required_capability_revision")
            ):
                blockers.append("RUNTIME_CAPABILITY_REVISION_MISMATCH")
            if not worktree_capable:
                blockers.append("RUNTIME_WORKTREE_CAPABILITY_UNVERIFIED")
    daemon_status = daemon.get("status") if isinstance(daemon, dict) else None
    if daemon_status not in {"running", "online"}:
        blockers.append("LOCAL_DAEMON_NOT_RUNNING")
    daemon_identity_source = {"daemon": daemon, "config": config.stdout}
    if not nested_contains(daemon_identity_source, expected_runtime["daemon_ref"]):
        blockers.append("LOCAL_DAEMON_IDENTITY_UNVERIFIED")
    if len(local_resources) > 1:
        blockers.append("LOCAL_DIRECTORY_RESOURCE_AMBIGUOUS")
    local_execution_mode = (
        local_directory_execution_mode(local_resources[0])
        if len(local_resources) == 1
        else None
    )
    origin = ssh_command(host, ["git", "-C", target["repository_root"], "remote", "get-url", "origin"], allow_failure=True)
    if origin.returncode == 0:
        repository_state = {"present": True, "origin": origin.stdout.strip()}
    else:
        repository_state = {"present": False, "origin": None}
    evidence = {
        "multica_version": digest_bytes(version.stdout.encode()),
        "auth_status": digest_bytes(auth.stdout.encode()),
        "config_show": digest_bytes(config.stdout.encode()),
        "workspace_list": digest_bytes(workspaces_completed.stdout.encode()),
        "runtime_list": digest_bytes(runtimes_completed.stdout.encode()),
        "daemon_status": digest_bytes(daemon_completed.stdout.encode()),
        "project_resources": digest_bytes(resources_completed.stdout.encode()),
        "native_squad_cli_capabilities": digest_bytes(canonical_json({
            name: {"returncode": result[0], "help_digest": digest_bytes(result[1].encode())}
            for name, result in sorted(capability_results.items())
        })),
    }
    return {
        "runtime_alias": target["runtime_alias"],
        "ssh_config_host": host,
        "profile": target["profile"],
        "account_ref": target["account_ref"],
        "runtime_ref": expected_runtime["runtime_ref"],
        "daemon_ref": expected_runtime["daemon_ref"],
        "workspace_ref": configuration["server"]["workspace_ref"],
        "daemon_status": daemon_status,
        "local_directory_resource_ref": (local_resources[0].get("id", local_resources[0].get("resource_id")) if len(local_resources) == 1 else None),
        "local_directory_execution_mode": local_execution_mode,
        "repository": repository_state,
        "evidence": evidence,
        "blockers": sorted(set(blockers)),
    }


REVISION = re.compile(r"^[0-9a-f]{40}$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    try:
        configuration = dict(load_input(args.input))
        candidate, _, _, project_bundle, _ = load_release_context(configuration)
        targets = []
        for target in configuration["targets"]:
            try:
                targets.append(one_target(configuration, project_bundle, dict(candidate), target))
            except MigrationError as error:
                targets.append({
                    "runtime_alias": target["runtime_alias"],
                    "ssh_config_host": target["ssh_config_host"],
                    "profile": target["profile"],
                    "account_ref": target["account_ref"],
                    "runtime_ref": None,
                    "daemon_ref": None,
                    "workspace_ref": configuration["server"]["workspace_ref"],
                    "daemon_status": None,
                    "local_directory_resource_ref": None,
                    "repository": {"present": False, "origin": None},
                    "evidence": {},
                    "blockers": [f"TARGET_PREFLIGHT_FAILED:{error}"],
                })
        payload = {
            "schema": PREFLIGHT_SCHEMA,
            "input_digest": digest_bytes(args.input.read_bytes()),
            "release_candidate_digest": configuration["source"]["release_candidate_digest"],
            "project_bundle_manifest_digest": project_bundle.manifest_digest,
            "native_squad_dispatch_digest": candidate["native_squad_dispatch_digest"],
            "targets": sorted(targets, key=lambda item: item["runtime_alias"]),
            "observed_at": utc_now(),
        }
        payload["snapshot_digest"] = digest_bytes(canonical_json(payload))
        atomic_bytes(args.snapshot, encoded(payload))
        blockers = sorted({blocker for target in targets for blocker in target["blockers"]})
        print(json.dumps({"ok": not blockers, "snapshot": str(args.snapshot), "snapshot_digest": payload["snapshot_digest"], "blockers": blockers}, ensure_ascii=False, sort_keys=True))
        return 0 if not blockers else 1
    except (MigrationError, BundleError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "error": "MIGRATION_PREFLIGHT_FAILED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
