#!/usr/bin/env python3
"""Bootstrap one authenticated profile and capture its Workspace Foundation."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from foundation_common import InputError, multica_environment, records
from multica_state_bundle.identities import bootstrap_deployment_key, canonical_json, digest_bytes
from multica_state_bundle.storage import atomic_json
from multica_orchestrator_cli.common.provider_models import (
    ProviderModelError,
    canonical_provider,
)



class PrepareError(ValueError):
    pass


def default_state_root() -> Path:
    value = __import__("os").environ.get("XDG_STATE_HOME")
    return (Path(value).expanduser() if value else Path.home() / ".local" / "state") / "multica-orchestrator"



AUTH_SERVER = re.compile(r"^Server:\s+(\S+)\s*$", re.MULTILINE)
AUTH_ACCOUNT = re.compile(r"^User:\s+.*\(([^()]+)\)\s*$", re.MULTILINE)
CONFIG_FIELD = re.compile(r"^([a-z_]+):\s+(.*?)\s*$", re.MULTILINE)


def run_multica(profile: str, arguments: list[str], *, workspace_ref: str | None = None) -> subprocess.CompletedProcess[str]:
    command = ["multica", "--profile", profile]
    if workspace_ref:
        command.extend(["--workspace-id", workspace_ref])
    command.extend(arguments)
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        env=multica_environment("self-hosted"),
        check=False,
    )


def read_text(profile: str, arguments: list[str], label: str) -> str:
    completed = run_multica(profile, arguments)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise PrepareError(f"{label} failed: {detail or 'no diagnostic'}")
    return completed.stdout


def read_json(profile: str, arguments: list[str], label: str, *, workspace_ref: str | None = None) -> Any:
    completed = run_multica(profile, [*arguments, "--output", "json"], workspace_ref=workspace_ref)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise PrepareError(f"{label} failed: {detail or 'no diagnostic'}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise PrepareError(f"{label} did not return JSON") from error


def authenticated_identity(profile: str) -> tuple[str, str]:
    completed = run_multica(profile, ["auth", "status"])
    if completed.returncode:
        raise PrepareError("AUTHENTICATION_REQUIRED: invoke multica-login for the requested profile before Link Up")
    output = completed.stdout + completed.stderr
    server = AUTH_SERVER.search(output)
    account = AUTH_ACCOUNT.search(output)
    if server is None or account is None:
        raise PrepareError("authenticated profile readback lacks server or account identity")
    return server.group(1), account.group(1)


def profile_configuration(profile: str) -> Mapping[str, str]:
    output = read_text(profile, ["config", "show"], "profile configuration readback")
    return {key: value for key, value in CONFIG_FIELD.findall(output)}


def infer_server_kind(server_ref: str) -> str:
    return "cloud" if re.fullmatch(r"https://(?:api\.)?multica\.ai/?", server_ref) else "self-hosted"


def unique_workspace(values: list[Mapping[str, Any]], selector: str | None, configured_ref: str | None) -> Mapping[str, Any]:
    effective = selector or configured_ref
    if effective:
        selected = [
            item
            for item in values
            if effective in {item.get("id"), item.get("workspace_id"), item.get("name"), item.get("slug")}
        ]
    else:
        selected = values
    if len(selected) != 1:
        raise PrepareError(f"Workspace selection must resolve exactly one record; observed {len(selected)}")
    return selected[0]


def parse_runtime_requests(values: list[str]) -> list[tuple[str, str]]:
    requested = values or ["primary-runtime=omp"]
    result: list[tuple[str, str]] = []
    aliases: set[str] = set()
    providers: set[str] = set()
    for value in requested:
        alias, separator, requested_provider = value.partition("=")
        if not separator or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", alias) is None or not requested_provider:
            raise PrepareError("--runtime must use <lowercase-alias>=<provider>")
        try:
            provider = canonical_provider(requested_provider)
        except ProviderModelError as error:
            raise PrepareError(str(error)) from error
        if alias in aliases or provider in providers:
            raise PrepareError("Runtime aliases and providers must be unique")
        aliases.add(alias)
        providers.add(provider)
        result.append((alias, provider))
    return sorted(result)


def daemon_status(profile: str) -> Mapping[str, Any] | None:
    completed = run_multica(profile, ["daemon", "status", "--output", "json"])
    if completed.returncode:
        return None
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise PrepareError("daemon status did not return JSON") from error
    if not isinstance(value, dict):
        raise PrepareError("daemon status must be an object")
    return value


def runtime_for_provider(
    runtime_records: list[Mapping[str, Any]], provider: str, daemon_ref: str
) -> Mapping[str, Any] | None:
    matches = [
        runtime
        for runtime in runtime_records
        if runtime.get("provider") == provider
        and runtime.get("daemon_id", runtime.get("daemon_ref")) == daemon_ref
        and runtime.get("status") == "online"
    ]
    if len(matches) > 1:
        raise PrepareError(f"provider {provider} has multiple online Runtimes on daemon {daemon_ref}")
    return matches[0] if matches else None


def ensure_runtimes(
    profile: str,
    workspace_ref: str,
    requested: list[tuple[str, str]],
    runtime_name: str | None,
) -> tuple[list[str], dict[str, str], str]:
    status = daemon_status(profile)
    runtime_values = records(
        read_json(profile, ["runtime", "list"], "Runtime list", workspace_ref=workspace_ref),
        "Runtime list",
    )
    daemon_ref = status.get("daemon_id") if status else None
    agents = set(status.get("agents", [])) if status else set()
    ready = (
        isinstance(daemon_ref, str)
        and daemon_ref
        and all(provider in agents and runtime_for_provider(runtime_values, provider, daemon_ref) for _, provider in requested)
    )
    action = "skipped-already-ready"
    if not ready:
        active_tasks = status.get("active_task_count", 0) if status else 0
        if not isinstance(active_tasks, int) or active_tasks != 0:
            raise PrepareError("RUNTIME_REGISTRATION_UNSAFE: daemon has active tasks")
        missing_launchers = [provider for _, provider in requested if shutil.which(provider) is None]
        if missing_launchers:
            raise PrepareError("RUNTIME_LAUNCHER_UNAVAILABLE: " + ", ".join(sorted(missing_launchers)))
        verb = "restart" if status and status.get("status") == "running" else "start"
        arguments = ["daemon", verb]
        if runtime_name:
            arguments.extend(["--runtime-name", runtime_name])
        completed = run_multica(profile, arguments)
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip()
            raise PrepareError(f"RUNTIME_REGISTRATION_FAILED: {detail or 'daemon command failed'}")
        action = f"daemon-{verb}"
        deadline = time.monotonic() + 20
        while True:
            status = daemon_status(profile)
            runtime_values = records(
                read_json(profile, ["runtime", "list"], "Runtime list", workspace_ref=workspace_ref),
                "Runtime list",
            )
            daemon_ref = status.get("daemon_id") if status else None
            agents = set(status.get("agents", [])) if status else set()
            ready = (
                isinstance(daemon_ref, str)
                and daemon_ref
                and all(provider in agents and runtime_for_provider(runtime_values, provider, daemon_ref) for _, provider in requested)
            )
            if ready or time.monotonic() >= deadline:
                break
            time.sleep(1)
        if not ready:
            raise PrepareError("RUNTIME_REGISTRATION_UNVERIFIED: daemon/provider Runtime readback is not ready")

    assert isinstance(daemon_ref, str)
    runtime_arguments: list[str] = []
    resolved: dict[str, str] = {}
    for alias, provider in requested:
        runtime = runtime_for_provider(runtime_values, provider, daemon_ref)
        if runtime is None:
            raise PrepareError(f"RUNTIME_REGISTRATION_UNVERIFIED: provider {provider}")
        runtime_ref = runtime.get("id", runtime.get("runtime_id"))
        if not isinstance(runtime_ref, str) or not runtime_ref:
            raise PrepareError(f"Runtime {provider} lacks an id")
        runtime_arguments.extend(["--runtime", f"{alias}={runtime_ref}"])
        resolved[alias] = runtime_ref
    return runtime_arguments, resolved, action


def allocate_run(state_root: Path) -> tuple[str, Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"{stamp}-foundation"
    root = state_root.expanduser().resolve() / "runs" / run_id
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    return run_id, root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--workspace", help="Workspace id, name, or slug; defaults to the profile selection")
    parser.add_argument("--runtime", action="append", default=[], metavar="ALIAS=PROVIDER")
    parser.add_argument("--runtime-name")
    parser.add_argument("--status-attestation", type=Path)
    parser.add_argument("--state-root", type=Path, default=default_state_root())
    parser.add_argument("--server-kind", choices=("cloud", "self-hosted"))
    parser.add_argument("--deployment-key")
    parser.add_argument("--relocation-intent-digest")
    args = parser.parse_args()
    try:
        server_ref, account_ref = authenticated_identity(args.profile)
        config = profile_configuration(args.profile)
        configured_server = config.get("server_url")
        if configured_server and configured_server != server_ref:
            raise PrepareError("authenticated server differs from profile configuration")
        server_kind = args.server_kind or infer_server_kind(server_ref)
        workspace_values = records(
            read_json(args.profile, ["workspace", "list"], "Workspace list"),
            "Workspace list",
        )
        workspace = unique_workspace(workspace_values, args.workspace, config.get("workspace_id"))
        workspace_ref = workspace.get("id", workspace.get("workspace_id"))
        if not isinstance(workspace_ref, str) or not workspace_ref:
            raise PrepareError("selected Workspace lacks an id")
        requested_runtimes = parse_runtime_requests(args.runtime)
        runtime_arguments, resolved_runtimes, runtime_action = ensure_runtimes(
            args.profile, workspace_ref, requested_runtimes, args.runtime_name
        )
        run_id, run_root = allocate_run(args.state_root)
        input_path = run_root / "input.json"
        capability_path = run_root / "preflight-cli-capabilities.json"
        capability_probe = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("probe_multica_capabilities.py")),
                "--server-kind",
                server_kind,
            ],
            text=True,
            capture_output=True,
            env=multica_environment(server_kind),
            check=False,
        )
        if capability_probe.returncode:
            raise PrepareError(capability_probe.stderr.strip()
            or capability_probe.stdout.strip()
            or "NATIVE_SQUAD_CAPABILITY_UNAVAILABLE")
        atomic_json(capability_path, json.loads(capability_probe.stdout))
        command = [
            sys.executable,
            str(Path(__file__).with_name("capture_workspace_foundation.py")),
            "--server-kind",
            server_kind,
            "--server-ref",
            server_ref,
            "--profile",
            args.profile,
            "--account-ref",
            account_ref,
            "--workspace-ref",
            workspace_ref,
            *runtime_arguments,
            "--capability-readback",
            str(capability_path),
            "--state-dir",
            str(run_root),
            "--operator-state-root",
            str(args.state_root.expanduser().resolve()),
            "--input",
            str(input_path),
        ]
        if args.status_attestation:
            command.extend(["--status-attestation", str(args.status_attestation)])
        deployment_key = args.deployment_key or bootstrap_deployment_key(
            server_kind, server_ref, workspace_ref
        )
        command.extend(["--deployment-key", deployment_key])
        if args.relocation_intent_digest:
            command.extend(["--relocation-intent-digest", args.relocation_intent_digest])
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode:
            raise PrepareError((completed.stderr or completed.stdout).strip())
        request = {
            "profile": args.profile,
            "workspace_selector": args.workspace or "profile-default",
            "runtime_providers": {alias: provider for alias, provider in requested_runtimes},
            "runtime_action": runtime_action,
            "status_attestation": "provided" if args.status_attestation else "human-confirmation-required",
            "relocation_intent_digest": args.relocation_intent_digest,
        }
        resolution = {
            "schema": "multica-orchestrator.foundation-resolution-manifest.v2",
            "run_id": run_id,
            "profile_ref": args.profile,
            "request_digest": digest_bytes(canonical_json(request)),
            "resolved_input": str(input_path),
            "resolved_input_digest": digest_bytes(input_path.read_bytes()),
            "fields": {
                "server": {"source": "multica-cli", "evidence": "readback/auth-status.json", "value": server_ref},
                "workspace_ref": {"source": "multica-cli", "evidence": "readback/workspace-list.json", "value": workspace_ref},
                "runtime_refs": {"source": "multica-cli", "evidence": "readback/runtimes.json", "value": resolved_runtimes},
                "runtime_registration": {"source": "multica-daemon", "value": runtime_action},
                "paths": {"source": "state-layout", "value": str(run_root)},
            },
        }
        atomic_json(run_root / "resolution.json", resolution)
        result = json.loads(completed.stdout)
        print(
            json.dumps(
                {
                    **result,
                    "run_id": run_id,
                    "run_root": str(run_root),
                    "resolution": str(run_root / "resolution.json"),
                    "runtime_action": runtime_action,
                    "status_reminder": None if args.status_attestation else "HUMAN_STATUS_CONFIRMATION_REQUIRED",
                },
                sort_keys=True,
            )
        )
        return 0
    except (PrepareError, InputError, OSError, KeyError, TypeError) as error:
        print(
            json.dumps(
                {"ok": False, "error": "FOUNDATION_PREPARE_FAILED", "detail": str(error)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
