#!/usr/bin/env python3
"""Verify aggregate GitHub evidence for all baseline orchestration checks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dispatch_common import InputError, read_json
from multica_state_bundle.identities import canonical_json, digest_bytes
from multica_state_bundle.storage import atomic_bytes
from check_ci_evidence import ALL_CHECKS

PASS_CONCLUSIONS = {"SUCCESS", "PASS", "PASSED"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--merge-head", required=True)
    parser.add_argument("--required-check", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        evidence = read_json(args.evidence, "GitHub provider evidence")
        if not isinstance(evidence, dict) or evidence.get("schema") != "multica-orchestrator-dispatch.github-provider-evidence.v2":
            raise InputError("GitHub provider evidence schema is invalid")
        unsigned = dict(evidence)
        observed_digest = unsigned.pop("evidence_digest", None)
        actual_digest = digest_bytes(canonical_json(unsigned))
        if observed_digest != actual_digest:
            raise InputError("GitHub provider evidence digest is invalid")
        pr = evidence.get("pull_request")
        if not isinstance(pr, dict) or pr.get("state") != "MERGED":
            raise InputError("pull request is not merged")
        expected = {
            "source_head": args.source,
            "target_head_at_validation": args.target,
            "merge_head": args.merge_head,
        }
        mismatches = [key for key, value in expected.items() if pr.get(key) != value]
        if mismatches:
            raise InputError("provider evidence revision mismatch: " + ", ".join(mismatches))
        if evidence.get("checks_revision") != args.merge_head:
            raise InputError("provider checks were not captured from the accepted merge revision")
        if evidence.get("current_target_head") != args.merge_head:
            raise InputError("current provider target head does not equal the accepted merge head")
        required = tuple(args.required_check) if args.required_check else ALL_CHECKS
        checks = evidence.get("checks")
        if not isinstance(checks, list):
            raise InputError("provider evidence checks must be an array")
        by_name: dict[str, list[dict[str, Any]]] = {}
        for item in checks:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                by_name.setdefault(item["name"], []).append(item)
        missing = [name for name in required if len(by_name.get(name, [])) != 1]
        if missing:
            raise InputError("required provider checks are missing or ambiguous: " + ", ".join(sorted(missing)))
        failed = [name for name in required if str(by_name[name][0].get("conclusion", "")).upper() not in PASS_CONCLUSIONS]
        if failed:
            raise InputError("required provider checks did not pass: " + ", ".join(sorted(failed)))
        result = {
            "schema": "multica-orchestrator-dispatch.provider-verification.v2",
            "state": "VERIFIED",
            "repository": evidence.get("repository"),
            "pull_request": pr,
            "source_head": args.source,
            "target_head_before_merge": args.target,
            "merge_head": args.merge_head,
            "checks_revision": evidence["checks_revision"],
            "required_checks": list(required),
            "provider_evidence_digest": actual_digest,
        }
        result["verification_digest"] = digest_bytes(canonical_json(result))
        atomic_bytes(args.output, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        print(json.dumps({"ok": True, "output": str(args.output), "verification_digest": result["verification_digest"]}, sort_keys=True))
        return 0
    except (InputError, OSError, TypeError) as error:
        print(json.dumps({"ok": False, "error": "PROVIDER_EVIDENCE_INVALID", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
