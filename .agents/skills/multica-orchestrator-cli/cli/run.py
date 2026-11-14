#!/usr/bin/env python3
"""Stage-qualified lifecycle runner and safe shared-state diagnostics."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from multica_state_bundle.errors import StateBundleError

STAGE_RUNNERS = {
    "link-up": "link_up",
    "orchestrator": "orchestrator",
    "nail-down": "nail_down",
    "migrate": "migrate",
    "dispatch": "dispatch",
    "relocate": "relocate",
}
STATE_COMMANDS = frozenset(("inspect", "validate", "recover"))


def state_parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(description=__doc__)
    subcommands = command_parser.add_subparsers(dest="command", required=True)
    for command in STATE_COMMANDS:
        child = subcommands.add_parser(command)
        child.add_argument("--state-root")
        child.add_argument("--workspace-key")
        child.add_argument("--repository", required=True)
        child.add_argument("--subpath", required=True)
        child.add_argument("--stage")
        child.add_argument("--format", choices=("json", "text"), default="text")
    return command_parser


def render(value: object, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    elif isinstance(value, dict):
        for key, item in value.items():
            print(f"{key}: {item}")
    else:
        print(value)


def execute_state(arguments: argparse.Namespace) -> dict[str, object]:
    from multica_state_bundle.inspection import inspect_namespace, validate_namespace

    if arguments.command == "inspect":
        return inspect_namespace(
            state_root=arguments.state_root,
            workspace_key_value=arguments.workspace_key,
            repository=arguments.repository,
            subpath=arguments.subpath,
            stage=arguments.stage,
        )
    if arguments.command == "validate":
        return validate_namespace(
            state_root=arguments.state_root,
            workspace_key_value=arguments.workspace_key,
            repository=arguments.repository,
            subpath=arguments.subpath,
            stage=arguments.stage,
        )
    from multica_state_bundle.claims import recover_namespace

    return recover_namespace(
        state_root=arguments.state_root,
        workspace_key_value=arguments.workspace_key,
        repository=arguments.repository,
        subpath=arguments.subpath,
        stage=arguments.stage,
    )


def run_state(argv: Sequence[str]) -> int:
    arguments = state_parser().parse_args(argv)
    try:
        result = execute_state(arguments)
    except StateBundleError as error:
        render(dict(error.as_dict()), arguments.format)
        return error.exit_code
    render(result, arguments.format)
    return 2 if result.get("readiness") == "BLOCKED" else 0


def run_stage(stage: str, argv: Sequence[str]) -> int:
    if not argv:
        print(f"usage: run.py {stage} <mode> [arguments...]", file=sys.stderr)
        return 2
    stage_directory = Path(__file__).resolve().parent / "multica_orchestrator_cli" / "stages" / STAGE_RUNNERS[stage]
    runner = stage_directory / "run.py"
    runner_arguments = list(argv)
    if stage == "relocate" and argv[0] == "readback":
        runner = stage_directory / "capture_target_readback.py"
        runner_arguments = list(argv[1:])
    if not runner.is_file():
        print(f"ORCHESTRATOR_CLI_UNAVAILABLE: missing {stage} stage runner", file=sys.stderr)
        return 2
    package_cli = str(Path(__file__).resolve().parent)
    existing = [entry for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep) if entry]
    if package_cli not in existing:
        os.environ["PYTHONPATH"] = os.pathsep.join((package_cli, *existing))
    os.execv(sys.executable, [sys.executable, str(runner), *runner_arguments])
    return 127


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print(f"usage: run.py <state|{'|'.join(STAGE_RUNNERS)}> <mode> [arguments...]", file=sys.stderr)
        return 2
    surface, *remaining = arguments
    if surface == "state":
        return run_state(remaining)
    if surface not in STAGE_RUNNERS:
        print(f"unknown stage: {surface}", file=sys.stderr)
        return 2
    return run_stage(surface, remaining)


if __name__ == "__main__":
    raise SystemExit(main())
