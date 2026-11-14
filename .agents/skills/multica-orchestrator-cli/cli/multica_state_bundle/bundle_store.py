#!/usr/bin/env python3
"""Secure local CAS and transfer packs for Multica handoff bundle closures."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import stat
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping, Sequence

from .handoff import Bundle, BundleError, STAGE_PARENTS, canonical_json, digest_bytes, load_bundle, require_digest
from .identities import default_state_root
from .storage import atomic_bytes

STORE_SCHEMA = "multica-orchestrator.bundle-store.v1"
PACK_SCHEMA = "multica-orchestrator.bundle-transfer-pack.v1"


def state_root(override: Path | None = None) -> Path:
    if override is not None:
        candidate = override.expanduser()
        if not candidate.is_absolute():
            raise BundleError("--state-root must be absolute")
    else:
        candidate = default_state_root() / "bundle-store"
    if candidate.is_symlink():
        raise BundleError(f"state root must not be a symlink: {candidate}")
    return candidate.resolve()


def digest_hex(value: str) -> str:
    return require_digest(value, "manifest digest").split(":", 1)[1]


def _copy_regular_tree(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise BundleError("bundle source must be a non-symlink directory")
    destination.mkdir(parents=True, mode=0o700)
    os.chmod(destination, 0o700)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        target = destination / relative
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise BundleError(f"bundle source contains unsupported entry: {relative.as_posix()}")
        if stat.S_ISDIR(mode):
            target.mkdir(mode=0o700)
            os.chmod(target, 0o700)
        else:
            if path.stat().st_nlink != 1:
                raise BundleError(f"bundle source file must not be hard-linked: {relative.as_posix()}")
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with path.open("rb") as source_stream, target.open("xb") as target_stream:
                shutil.copyfileobj(source_stream, target_stream)
                target_stream.flush()
                os.fsync(target_stream.fileno())
            os.chmod(target, 0o600)


class BundleStore:
    def __init__(self, root: Path | None = None):
        self.root = state_root(root)
        self.objects = self.root / "objects" / "bundles"
        self.incoming = self.root / "incoming"
        self.quarantine = self.root / "quarantine"
        self.locks = self.root / "locks"

    def initialize(self) -> None:
        for directory in (self.root, self.objects, self.incoming, self.quarantine, self.locks):
            if directory.is_symlink():
                raise BundleError(f"bundle store directory must not be a symlink: {directory}")
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(directory, 0o700)
        marker = self.root / "store.json"
        expected = canonical_json({"schema": STORE_SCHEMA})
        if marker.exists():
            if marker.is_symlink() or marker.read_bytes() != expected:
                raise BundleError("bundle store marker is invalid")
        else:
            atomic_bytes(marker, expected)

    def object_path(self, stage: str, manifest_digest: str) -> Path:
        if stage not in STAGE_PARENTS:
            raise BundleError(f"unsupported bundle stage: {stage}")
        return self.objects / stage / digest_hex(manifest_digest)

    @contextmanager
    def lock(self) -> Iterator[None]:
        self.initialize()
        path = self.locks / "bundle-store.lock"
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def resolve(self, stage: str, manifest_digest: str) -> Bundle:
        self.initialize()
        return load_bundle(
            self.object_path(stage, manifest_digest),
            expected_stage=stage,
            expected_manifest_digest=manifest_digest,
        )

    def publish(
        self,
        source: Path,
        *,
        expected_stage: str | None = None,
        expected_manifest_digest: str | None = None,
    ) -> Bundle:
        source_bundle = load_bundle(
            source,
            expected_stage=expected_stage,
            expected_manifest_digest=expected_manifest_digest,
        )
        destination = self.object_path(source_bundle.stage, source_bundle.manifest_digest)
        with self.lock():
            if destination.exists():
                return load_bundle(
                    destination,
                    expected_stage=source_bundle.stage,
                    expected_manifest_digest=source_bundle.manifest_digest,
                )
            staging = Path(tempfile.mkdtemp(prefix="bundle-", dir=self.incoming))
            try:
                copy = staging / "object"
                _copy_regular_tree(source_bundle.root, copy)
                load_bundle(
                    copy,
                    expected_stage=source_bundle.stage,
                    expected_manifest_digest=source_bundle.manifest_digest,
                )
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                os.chmod(destination.parent, 0o700)
                os.replace(copy, destination)
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        return self.resolve(source_bundle.stage, source_bundle.manifest_digest)

    def closure(self, stage: str, manifest_digest: str) -> tuple[Bundle, ...]:
        result: list[Bundle] = []
        visiting: set[tuple[str, str]] = set()

        def visit(current_stage: str, current_digest: str) -> None:
            key = (current_stage, current_digest)
            if key in visiting:
                raise BundleError("bundle parent graph contains a cycle")
            if any(item.stage == current_stage and item.manifest_digest == current_digest for item in result):
                return
            visiting.add(key)
            bundle = self.resolve(current_stage, current_digest)
            for parent in bundle.parents:
                visit(parent["stage"], parent["manifest_digest"])
            visiting.remove(key)
            result.append(bundle)

        visit(stage, manifest_digest)
        return tuple(result)

    def export_pack(self, stage: str, manifest_digest: str, output: Path) -> Path:
        closure = self.closure(stage, manifest_digest)
        candidate = output.expanduser()
        if candidate.is_symlink():
            raise BundleError("pack output must not be a symlink")
        destination = candidate.resolve()
        if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
            raise BundleError("pack output must be a new or empty directory")
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(destination, 0o700)
        objects: list[dict[str, str]] = []
        for bundle in closure:
            relative = f"objects/{bundle.stage}/{digest_hex(bundle.manifest_digest)}"
            _copy_regular_tree(bundle.root, destination / PurePosixPath(relative))
            objects.append({"stage": bundle.stage, "manifest_digest": bundle.manifest_digest, "path": relative})
        manifest = {
            "schema": PACK_SCHEMA,
            "root": {"stage": stage, "manifest_digest": manifest_digest},
            "objects": objects,
        }
        atomic_bytes(destination / "pack-manifest.json", canonical_json(manifest))
        return destination

    def import_pack(self, pack: Path, *, expected_pack_digest: str | None = None) -> Bundle:
        candidate = pack.expanduser()
        if candidate.is_symlink() or not candidate.resolve().is_dir():
            raise BundleError("transfer pack must be a non-symlink directory")
        root = candidate.resolve()
        manifest_path = root / "pack-manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise BundleError("transfer pack manifest is missing")
        manifest_bytes = manifest_path.read_bytes()
        if expected_pack_digest is not None and digest_bytes(manifest_bytes) != expected_pack_digest:
            raise BundleError("transfer pack manifest digest mismatch")
        try:
            manifest = json.loads(manifest_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BundleError("transfer pack manifest is invalid JSON") from error
        if not isinstance(manifest, dict) or set(manifest) != {"schema", "root", "objects"} or manifest.get("schema") != PACK_SCHEMA:
            raise BundleError("transfer pack manifest fields are invalid")
        root_ref = manifest.get("root")
        if not isinstance(root_ref, dict) or set(root_ref) != {"stage", "manifest_digest"}:
            raise BundleError("transfer pack root descriptor is invalid")
        objects = manifest.get("objects")
        if not isinstance(objects, list) or not objects:
            raise BundleError("transfer pack has no objects")
        loaded: dict[tuple[str, str], Bundle] = {}
        declared_paths: set[str] = {"pack-manifest.json"}
        for descriptor in objects:
            if not isinstance(descriptor, dict) or set(descriptor) != {"stage", "manifest_digest", "path"}:
                raise BundleError("transfer pack object descriptor is invalid")
            stage = descriptor["stage"]
            manifest_digest = require_digest(descriptor["manifest_digest"], "transfer object digest")
            expected_path = f"objects/{stage}/{digest_hex(manifest_digest)}"
            if descriptor["path"] != expected_path:
                raise BundleError("transfer pack object path is not canonical")
            object_path = root / PurePosixPath(expected_path)
            try:
                object_path.resolve().relative_to(root)
            except ValueError as error:
                raise BundleError("transfer pack object escapes pack root") from error
            bundle = load_bundle(object_path, expected_stage=stage, expected_manifest_digest=manifest_digest)
            key = (stage, manifest_digest)
            if key in loaded:
                raise BundleError("transfer pack contains a duplicate object")
            loaded[key] = bundle
            declared_paths.add(expected_path)
            declared_paths.update(
                f"{expected_path}/{path.relative_to(object_path).as_posix()}" for path in object_path.rglob("*")
            )
        actual_paths = {path.relative_to(root).as_posix() for path in root.rglob("*")}
        expected_parents = {
            parent.as_posix()
            for relative in declared_paths
            for parent in PurePosixPath(relative).parents
            if parent != PurePosixPath(".")
        }
        if actual_paths != declared_paths | expected_parents:
            raise BundleError("transfer pack contains unexpected or missing entries")
        for bundle in loaded.values():
            for parent in bundle.parents:
                key = (parent["stage"], parent["manifest_digest"])
                if key not in loaded:
                    try:
                        self.resolve(*key)
                    except BundleError as error:
                        raise BundleError(f"transfer pack parent is missing: {key[0]} {key[1]}") from error
        order = {"workspace-foundation": 0, "server-orchestration": 1, "project-binding": 2}
        for bundle in sorted(loaded.values(), key=lambda item: order[item.stage]):
            self.publish(bundle.root, expected_stage=bundle.stage, expected_manifest_digest=bundle.manifest_digest)
        root_key = (root_ref.get("stage"), root_ref.get("manifest_digest"))
        if root_key not in loaded:
            raise BundleError("transfer pack root object is absent")
        return self.resolve(root_key[0], root_key[1])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    publish = subparsers.add_parser("publish")
    publish.add_argument("--source", type=Path, required=True)
    publish.add_argument("--stage", required=True)
    publish.add_argument("--manifest-digest")
    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--stage", required=True)
    resolve.add_argument("--manifest-digest", required=True)
    export = subparsers.add_parser("export-pack")
    export.add_argument("--stage", required=True)
    export.add_argument("--manifest-digest", required=True)
    export.add_argument("--output", type=Path, required=True)
    imported = subparsers.add_parser("import-pack")
    imported.add_argument("--pack", type=Path, required=True)
    imported.add_argument("--pack-manifest-digest")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        store = BundleStore(args.state_root)
        if args.command == "publish":
            bundle = store.publish(args.source, expected_stage=args.stage, expected_manifest_digest=args.manifest_digest)
            result: Mapping[str, Any] = {"stage": bundle.stage, "manifest_digest": bundle.manifest_digest, "path": str(bundle.root)}
        elif args.command == "resolve":
            bundle = store.resolve(args.stage, args.manifest_digest)
            result = {"stage": bundle.stage, "manifest_digest": bundle.manifest_digest, "path": str(bundle.root)}
        elif args.command == "export-pack":
            output = store.export_pack(args.stage, args.manifest_digest, args.output)
            result = {"output": str(output), "pack_manifest_digest": digest_bytes((output / "pack-manifest.json").read_bytes())}
        else:
            bundle = store.import_pack(args.pack, expected_pack_digest=args.pack_manifest_digest)
            result = {"stage": bundle.stage, "manifest_digest": bundle.manifest_digest, "path": str(bundle.root)}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (BundleError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "error": "BUNDLE_STORE_OPERATION_FAILED", "detail": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
