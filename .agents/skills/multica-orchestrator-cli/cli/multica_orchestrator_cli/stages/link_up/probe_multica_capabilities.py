#!/usr/bin/env python3
"""Probe the read-only Multica CLI surface required by Foundation and native Squad orchestration."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from foundation_common import multica_environment

REQUIRED = {
    "auth-status": ("auth", "status"),
    "config-show": ("config", "show"),
    "workspace-list": ("workspace", "list"),
    "workspace-get": ("workspace", "get"),
    "workspace-member-list": ("workspace", "member", "list"),
    "label-list": ("label", "list"),
    "label-create": ("label", "create"),
    "runtime-list": ("runtime", "list"),
    "runtime-profile-create": ("runtime", "profile", "create"),
    "runtime-profile-list": ("runtime", "profile", "list"),
    "daemon-start": ("daemon", "start"),
    "agent-list": ("agent", "list"),
    "agent-get": ("agent", "get"),
    "agent-create": ("agent", "create"),
    "agent-update": ("agent", "update"),
    "agent-skills-list": ("agent", "skills", "list"),
    "agent-skills-set": ("agent", "skills", "set"),
    "squad-list": ("squad", "list"),
    "squad-get": ("squad", "get"),
    "squad-create": ("squad", "create"),
    "squad-update": ("squad", "update"),
    "squad-member-list": ("squad", "member", "list"),
    "squad-member-add": ("squad", "member", "add"),
    "squad-member-remove": ("squad", "member", "remove"),
    "squad-member-set-role": ("squad", "member", "set-role"),
    "squad-activity": ("squad", "activity"),
    "issue-get": ("issue", "get"),
    "issue-update": ("issue", "update"),
    "issue-assign": ("issue", "assign"),
    "issue-comment-add": ("issue", "comment", "add"),
    "issue-runs": ("issue", "runs"),
}

REQUIRED_FLAGS = {
    "agent-create": {"--description", "--instructions", "--permission-mode", "--runtime-id", "--model", "--max-concurrent-tasks"},
    "agent-update": {"--description", "--instructions", "--permission-mode", "--runtime-id", "--model", "--max-concurrent-tasks"},
    "squad-create": {"--description", "--leader"},
    "squad-update": {"--instructions", "--leader"},
    "squad-member-add": {"--member-id", "--type", "--role"},
    "squad-member-remove": {"--member-id", "--type"},
    "issue-assign": {"--to-id", "--no-start"},
    "issue-comment-add": {"--content", "--parent"},
}


def probe(
    executable: str,
    server_kind: str,
    command: tuple[str, ...],
    required_flags: set[str],
) -> dict[str, object]:
    completed = subprocess.run(
        [executable, *command, "--help"],
        env=multica_environment(server_kind),
        text=True,
        capture_output=True,
        check=False,
    )
    help_text = completed.stdout + completed.stderr
    observed_flags = sorted(flag for flag in required_flags if flag in help_text)
    missing_flags = sorted(required_flags - set(observed_flags))
    return {
        "available": completed.returncode == 0 and not missing_flags,
        "command": list(command),
        "exit_status": completed.returncode,
        "required_flags": sorted(required_flags),
        "observed_flags": observed_flags,
        "missing_flags": missing_flags,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-kind", choices=("cloud", "self-hosted"), required=True)
    parser.add_argument("--multica-command", default="multica")
    args = parser.parse_args()
    capabilities = {
        name: probe(args.multica_command, args.server_kind, command, REQUIRED_FLAGS.get(name, set()))
        for name, command in REQUIRED.items()
    }
    missing = sorted(name for name, result in capabilities.items() if not result["available"])
    native_squad_routing = {
        "leader_first_surface": capabilities["squad-create"]["available"] and capabilities["squad-activity"]["available"],
        "exact_member_routing_surface": capabilities["squad-member-list"]["available"] and capabilities["issue-comment-add"]["available"],
        "no_start_assignment_surface": capabilities["issue-assign"]["available"],
        "thread_reply_surface": capabilities["issue-comment-add"]["available"],
        "run_readback_surface": capabilities["issue-runs"]["available"],
        "membership_role_surface": capabilities["squad-member-add"]["available"] and capabilities["squad-member-set-role"]["available"],
        "private_agent_surface": capabilities["agent-create"]["available"] and capabilities["agent-get"]["available"],
    }
    compatible = not missing and all(native_squad_routing.values())
    print(json.dumps({
        "schema": "multica-orchestrator-link-up.cli-capabilities.v2",
        "compatible": compatible,
        "capabilities": capabilities,
        "native_squad_routing": native_squad_routing,
        "missing": missing,
    }, sort_keys=True))
    return 0 if compatible else 1


if __name__ == "__main__":
    raise SystemExit(main())
