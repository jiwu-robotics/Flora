#!/usr/bin/env python3
"""Check and reconcile local SHA-256 references under an explicit package root.

Only references with an unambiguous local target are managed. Historical
``supersedes`` self-references and opaque provider/git revisions stay intact.
The default mode is read-only; use ``--write`` only after accepting the new
artifact revisions.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SHA256 = r"[0-9a-f]{64}"
PATH_HASH = re.compile(
    rf"(?P<path>(?:\.\./)?(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:md|yaml))"
    rf"#sha256:(?P<digest>{SHA256})"
)
NAMED_HASH = re.compile(rf"^(?P<prefix>\s*(?P<key>[a-z0-9_]+):\s*sha256:)(?P<digest>{SHA256})(?P<suffix>\s*)$", re.MULTILINE)
GUIDE_HASH = re.compile(
    rf"^(?P<prefix>(?:requirements|manifest|W7 analysis|W8 analysis):\s+sha256:)(?P<digest>{SHA256})(?P<suffix>\s*)$",
    re.MULTILINE,
)

# These fields are intentionally explicit: a bare sha256 value has no target
# unless its schema assigns one. Do not infer a target from its field name.
NAMED_REFERENCE_TARGETS = {
    "requirements_revision": "requirements/orchestration-requirements.md",
    "bindings_revision": "analysis/w6-skill-permission-bindings.md",
    "w7_analysis_revision": "analysis/w7-template-delivery.md",
    "w8_analysis_revision": "analysis/w8-enforcement-controls.md",
    "package_manifest_revision": "manifests/orchestration-package.yaml",
    "handoff_gate_contract_revision": "contracts/handoff-gate-contracts.md",
    "human_decision_schema_revision": "contracts/handoff-gate-contracts.md",
}
GUIDE_REFERENCE_TARGETS = {
    "requirements": "requirements/orchestration-requirements.md",
    "manifest": "manifests/orchestration-package.yaml",
    "W7 analysis": "analysis/w7-template-delivery.md",
    "W8 analysis": "analysis/w8-enforcement-controls.md",
}


@dataclass(frozen=True)
class Reference:
    source: Path
    target: Path
    start: int
    end: int
    expected: str


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files(root: Path) -> list[Path]:
    return sorted(path for suffix in ("*.md", "*.yaml") for path in root.rglob(suffix))


def resolve_target(root: Path, source: Path, raw_path: str) -> Path | None:
    candidate = source.parent / raw_path if raw_path.startswith("../") else root / raw_path
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def replaceable_references(root: Path, source: Path) -> tuple[list[Reference], list[str]]:
    content = source.read_text(encoding="utf-8")
    references: list[Reference] = []
    skipped: list[str] = []

    def add_reference(match: re.Match[str], raw_path: str, digest_group: str = "digest") -> None:
        target = resolve_target(root, source, raw_path)
        if target is None:
            skipped.append(f"{source.relative_to(root)}: absent or external artifact {raw_path!r}")
            return
        if target == source.resolve():
            return
        references.append(Reference(source, target, match.start(digest_group), match.end(digest_group), match[digest_group]))

    for match in PATH_HASH.finditer(content):
        add_reference(match, match["path"])

    for match in NAMED_HASH.finditer(content):
        target = NAMED_REFERENCE_TARGETS.get(match["key"])
        if target is not None:
            add_reference(match, target)

    if source.relative_to(root).as_posix() == "guide-to-setup-multica.md":
        for match in GUIDE_HASH.finditer(content):
            label = match["prefix"].split(":", 1)[0]
            add_reference(match, GUIDE_REFERENCE_TARGETS[label])

    unique: dict[tuple[int, int], Reference] = {(reference.start, reference.end): reference for reference in references}
    return list(unique.values()), skipped


def build_reference_map(root: Path) -> tuple[dict[Path, list[Reference]], list[str]]:
    references: dict[Path, list[Reference]] = {}
    skipped: list[str] = []
    for source in source_files(root):
        found, source_skips = replaceable_references(root, source)
        if found:
            references[source] = found
        skipped.extend(source_skips)
    return references, skipped


def dependency_order(references: dict[Path, list[Reference]]) -> list[Path]:
    order: list[Path] = []
    visiting: list[Path] = []
    visited: set[Path] = set()

    def visit(source: Path) -> None:
        if source in visited:
            return
        if source in visiting:
            cycle = visiting[visiting.index(source) :] + [source]
            raise ValueError("local digest cycle: " + " -> ".join(path.as_posix() for path in cycle))
        visiting.append(source)
        for reference in references.get(source, []):
            if reference.target in references:
                visit(reference.target)
        visiting.pop()
        visited.add(source)
        order.append(source)

    for source in sorted(references):
        visit(source)
    return order


def mismatches(references: Iterable[Reference]) -> list[tuple[Reference, str]]:
    return [(reference, actual) for reference in references if (actual := sha256(reference.target)) != reference.expected]


def update_source(source: Path, references: list[Reference]) -> int:
    content = source.read_text(encoding="utf-8")
    replacements = [(reference.start, reference.end, sha256(reference.target)) for reference in references]
    changed = sum(content[start:end] != replacement for start, end, replacement in replacements)
    if not changed:
        return 0
    for start, end, replacement in sorted(replacements, reverse=True):
        content = content[:start] + replacement + content[end:]
    descriptor, temporary = tempfile.mkstemp(prefix=f".{source.name}.", dir=source.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, source)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return changed


def plan_payload(root: Path, stale: list[tuple[Reference, str]]) -> dict[str, object]:
    return {
        "schema": "orchestrator-hash-plan/v1",
        "root": str(root),
        "references": [
            {"source": str(reference.source.relative_to(root)), "target": str(reference.target.relative_to(root)), "expected": reference.expected, "actual": actual}
            for reference, actual in stale
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[5] / "multica-orchestrator-kick-off", help="package root (default: multica-orchestrator-kick-off Skill root)")
    parser.add_argument("--path", action="append", default=[], help="source file relative to root; may be repeated")
    parser.add_argument("--plan", type=Path, help="write a reviewable stale-reference plan, or consume it with --write")
    parser.add_argument("--write", action="store_true", help="apply only references named by --plan")
    parser.add_argument("--json", action="store_true", help="emit machine-readable stale-reference output")
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")
    if args.write and args.plan is None:
        parser.error("--write requires --plan")

    references, skipped = build_reference_map(root)
    selected = {Path(path).as_posix() for path in args.path}
    if selected:
        references = {source: items for source, items in references.items() if source.relative_to(root).as_posix() in selected}
    stale = mismatches(reference for items in references.values() for reference in items)
    if args.plan is not None and not args.write:
        args.plan.parent.mkdir(parents=True, exist_ok=True)
        args.plan.write_text(json.dumps(plan_payload(root, stale), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.write:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        planned = {(item["source"], item["target"], item["expected"], item["actual"]) for item in plan.get("references", [])}
        current = {(str(ref.source.relative_to(root)), str(ref.target.relative_to(root)), ref.expected, actual) for ref, actual in stale}
        if planned != current:
            print("Refusing stale or out-of-scope reconciliation plan.", file=sys.stderr)
            return 2
        order = dependency_order(references)
        updates = sum(update_source(source, references[source]) for source in order)
        references, skipped = build_reference_map(root)
        if selected:
            references = {source: items for source, items in references.items() if source.relative_to(root).as_posix() in selected}
        stale = mismatches(reference for items in references.values() for reference in items)
        if not stale:
            print(f"Updated {updates} managed SHA-256 reference(s).")
            return 0
    if args.json:
        print(json.dumps({"ok": not stale, "stale": plan_payload(root, stale)["references"], "skipped": skipped}, indent=2, sort_keys=True))
    else:
        for item in skipped:
            print(f"Skipped unmanaged reference: {item}", file=sys.stderr)
        for reference, actual in stale:
            print(f"{reference.source.relative_to(root)} -> {reference.target.relative_to(root)}: expected sha256:{reference.expected}, actual sha256:{actual}")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
