#!/usr/bin/env python3
"""Capture read-only GitHub PR, check-run, and target-head evidence."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dispatch_common import InputError
from multica_state_bundle.identities import canonical_json, digest_bytes
from multica_state_bundle.storage import atomic_bytes


def run(executable: str, arguments: list[str]) -> Any:
    completed = subprocess.run([executable, *arguments], text=True, capture_output=True, check=False)
    if completed.returncode:
        raise InputError((completed.stderr or completed.stdout).strip() or "GitHub CLI command failed")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise InputError("GitHub CLI command did not return JSON") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="GitHub owner/repository")
    parser.add_argument("--pull-request", required=True)
    parser.add_argument("--merge-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gh-command", default="gh")
    args = parser.parse_args()
    try:
        pr = run(args.gh_command, ["pr", "view", args.pull_request, "--repo", args.repository, "--json", "number,url,state,headRefName,headRefOid,baseRefName,baseRefOid,mergeCommit"])
        if not isinstance(pr, dict):
            raise InputError("GitHub PR readback must be an object")
        base = pr.get("baseRefName")
        if not isinstance(base, str) or not base:
            raise InputError("GitHub PR lacks baseRefName")
        source = pr.get("headRefOid")
        if not isinstance(source, str) or not source:
            raise InputError("GitHub PR lacks headRefOid")
        target = run(args.gh_command, ["api", f"repos/{args.repository}/git/ref/heads/{base}"])
        try:
            current_target_head = target["object"]["sha"]
        except (KeyError, TypeError) as error:
            raise InputError("GitHub target ref readback lacks object.sha") from error
        check_response = run(
            args.gh_command,
            [
                "api",
                "-H",
                "Accept: application/vnd.github+json",
                f"repos/{args.repository}/commits/{args.merge_revision}/check-runs?per_page=100",
            ],
        )
        if not isinstance(check_response, dict):
            raise InputError("GitHub proposed-merge check-run readback must be an object")
        checks = check_response.get("check_runs")
        total_count = check_response.get("total_count")
        if not isinstance(checks, list) or not isinstance(total_count, int):
            raise InputError("GitHub proposed-merge check-run readback is invalid")
        if total_count != len(checks):
            raise InputError("GitHub proposed-merge check-run readback is truncated")
        normalized_checks = []
        for item in checks:
            if not isinstance(item, dict):
                raise InputError("GitHub proposed-merge check-run readback contains a non-object")
            name = item.get("name")
            if not isinstance(name, str) or not name:
                raise InputError("GitHub check-run lacks a name")
            app = item.get("app")
            normalized_checks.append({
                "name": name,
                "conclusion": item.get("conclusion"),
                "details_url": item.get("details_url"),
                "workflow_name": app.get("name") if isinstance(app, dict) else None,
            })
        merge_commit = pr.get("mergeCommit")
        merge_head = merge_commit.get("oid") if isinstance(merge_commit, dict) else None
        if merge_head is not None and merge_head != args.merge_revision:
            raise InputError("GitHub merge commit differs from the requested merge revision")
        payload = {
            "schema": "multica-orchestrator-dispatch.github-provider-evidence.v2",
            "repository": args.repository,
            "pull_request": {
                "number": pr.get("number"),
                "url": pr.get("url"),
                "state": pr.get("state"),
                "source_ref": pr.get("headRefName"),
                "source_head": source,
                "target_ref": base,
                "target_head_at_validation": pr.get("baseRefOid"),
                "merge_head": merge_head,
            },
            "current_target_head": current_target_head,
            "checks_revision": args.merge_revision,
            "checks": sorted(normalized_checks, key=lambda item: item["name"]),
            "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        payload["evidence_digest"] = digest_bytes(canonical_json(payload))
        atomic_bytes(args.output, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        print(json.dumps({"ok": True, "output": str(args.output), "evidence_digest": payload["evidence_digest"]}, sort_keys=True))
        return 0
    except (InputError, OSError, TypeError) as error:
        print(json.dumps({"ok": False, "error": "GITHUB_PROVIDER_CAPTURE_FAILED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
