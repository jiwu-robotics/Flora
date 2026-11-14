"""Canonical identity, pointers, indexes, and operator-local state."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlparse

from .errors import StateError
from .storage import atomic_json, read_private_object

RESOLUTION_SCHEMA = "multica-orchestrator.resolution-manifest.v2"
POINTER_SCHEMA = "multica-orchestrator.stage-pointer.v1"
CANDIDATE_POINTER_SCHEMA = "multica-orchestrator.candidate-pointer.v2"
DEPLOYMENT_INDEX_SCHEMA = "multica-orchestrator.workspace-deployment-index.v1"
SELECTION_INDEX_SCHEMA = "multica-orchestrator.workspace-selection-index.v1"
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
STAGES = {"workspace-foundation", "server-orchestration", "project-binding"}


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def default_state_root() -> Path:
    value = os.environ.get("XDG_STATE_HOME")
    base = Path(value).expanduser() if value else Path.home() / ".local" / "state"
    if not base.is_absolute() or ".." in base.parts:
        raise StateError("XDG_STATE_HOME must be a normalized absolute path")
    return base.resolve() / "multica-orchestrator"


def require_absolute(value: Any, label: str) -> Path:
    if not isinstance(value, (str, Path)) or not str(value):
        raise StateError(f"{label} must be a non-empty absolute path")
    path = Path(value).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise StateError(f"{label} must be a normalized absolute path")
    return path.resolve()


def read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise StateError(f"cannot read {label}: {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise StateError(f"invalid JSON in {label}: {path}: {error.msg}") from error
    if not isinstance(value, dict):
        raise StateError(f"{label} must be a JSON object")
    return value




def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def allocate_run(state_root: Path, stage: str, subject: str | None = None) -> tuple[str, Path]:
    if SAFE_NAME.fullmatch(stage) is None:
        raise StateError("run stage is invalid")
    suffix = ""
    if subject:
        suffix = f"-{subject}" if SAFE_NAME.fullmatch(subject) else f"-{hashlib.sha256(subject.encode()).hexdigest()[:12]}"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"{stamp}-{stage}{suffix}"
    root = state_root.expanduser().resolve() / "runs" / run_id
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    return run_id, root


def bootstrap_deployment_key(server_kind: str, server_ref: str, workspace_ref: str) -> str:
    return digest_bytes(canonical_json({"schema": "multica-orchestrator.deployment-key.v1", "server_kind": server_kind, "server_ref": server_ref, "workspace_ref": workspace_ref}))


def workspace_key(server_kind: str, server_ref: str, workspace_ref: str, deployment_key: str | None = None) -> str:
    if deployment_key is not None:
        if DIGEST.fullmatch(deployment_key) is None:
            raise StateError("deployment_key must be a SHA-256 digest")
        return digest_bytes(canonical_json({"deployment_key": deployment_key, "workspace_ref": workspace_ref}))
    return digest_bytes(canonical_json({"server_kind": server_kind, "server_ref": server_ref, "workspace_ref": workspace_ref}))


def repository_identity(url: str) -> str:
    ssh_match = re.fullmatch(r"git@github\.com:([^/\s]+/[^/\s]+?)(?:\.git)?", url)
    if ssh_match:
        return "github:" + ssh_match.group(1)
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.hostname == "github.com" and parsed.port is None and parsed.username is None and parsed.password is None and not parsed.query and not parsed.fragment:
        path = parsed.path.removeprefix("/").removesuffix(".git")
        if re.fullmatch(r"[^/\s]+/[^/\s]+", path):
            return "github:" + path
    raise StateError("repository URL is not a credential-free canonical GitHub SSH or HTTPS URL")


def normalize_subpath(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise StateError("project subpath must be a non-empty repository-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise StateError("project subpath must be normalized and repository-relative")
    return "." if str(path) == "." else path.as_posix()


def project_key(workspace: str, repository: str, subpath: str) -> str:
    if DIGEST.fullmatch(workspace) is None:
        raise StateError("workspace_key must be a SHA-256 digest")
    return digest_bytes(
        canonical_json(
            {
                "workspace_key": workspace,
                "repository_identity": repository_identity(repository)
                if repository.startswith(("git@", "https://"))
                else repository,
                "project_subpath": normalize_subpath(subpath),
            }
        )
    )




class StagePointers:
    def __init__(self, state_root: Path):
        self.root = require_absolute(state_root, "pointer state root")

    def _path(self, scope: str, subject_key: str, name: str) -> Path:
        if scope not in {"workspaces", "projects"} or SAFE_NAME.fullmatch(name) is None or DIGEST.fullmatch(subject_key) is None:
            raise StateError("stage pointer identity is invalid")
        return self.root / "pointers" / scope / subject_key.split(":", 1)[1] / name / "current.json"

    def read(self, scope: str, subject_key: str, name: str, stage: str) -> dict[str, Any]:
        path = self._path(scope, subject_key, name)
        value = read_object(path, "stage pointer")
        if value.get("schema") != POINTER_SCHEMA or value.get("scope") != scope or value.get("subject_key") != subject_key or value.get("name") != name or value.get("stage") != stage:
            raise StateError("stage pointer identity differs")
        if stage not in STAGES or DIGEST.fullmatch(str(value.get("manifest_digest"))) is None:
            raise StateError("stage pointer manifest digest is invalid")
        return {**value, "_path": str(path), "_digest": digest_bytes(path.read_bytes())}

    def write(self, scope: str, subject_key: str, name: str, stage: str, manifest_digest: str, *, parent_manifest_digest: str | None = None, generation: int | None = None) -> Path:
        if stage not in STAGES or DIGEST.fullmatch(manifest_digest) is None:
            raise StateError("stage pointer value is invalid")
        if parent_manifest_digest is not None and DIGEST.fullmatch(parent_manifest_digest) is None:
            raise StateError("stage pointer parent digest is invalid")
        path = self._path(scope, subject_key, name)
        atomic_json(path, {"schema": POINTER_SCHEMA, "scope": scope, "subject_key": subject_key, "name": name, "stage": stage, "manifest_digest": manifest_digest, "parent_manifest_digest": parent_manifest_digest, "generation": generation, "updated_at": utc_now()})
        return path

    def read_candidate(self, subject_key: str) -> dict[str, Any]:
        path = self._path("projects", subject_key, "candidate")
        value = read_object(path, "candidate pointer")
        if value.get("schema") != CANDIDATE_POINTER_SCHEMA or value.get("project_key") != subject_key:
            raise StateError("candidate pointer identity differs")
        for field in ("project_bundle_manifest_digest", "release_candidate_digest"):
            if DIGEST.fullmatch(str(value.get(field))) is None:
                raise StateError(f"candidate pointer {field} is invalid")
        candidate_path = require_absolute(value.get("release_candidate_path"), "candidate pointer release_candidate_path")
        if not candidate_path.is_file() or digest_bytes(candidate_path.read_bytes()) != value["release_candidate_digest"]:
            raise StateError("candidate pointer release candidate bytes differ")
        return {**value, "_path": str(path), "_digest": digest_bytes(path.read_bytes())}

    def write_candidate(self, subject_key: str, *, project_bundle_manifest_digest: str, release_candidate_path: Path, release_candidate_digest: str, repository_identity_value: str, project_subpath: str, generation: int, previous_release_digest: str | None) -> Path:
        if DIGEST.fullmatch(project_bundle_manifest_digest) is None or DIGEST.fullmatch(release_candidate_digest) is None:
            raise StateError("candidate pointer bundle or candidate digest is invalid")
        candidate_path = release_candidate_path.expanduser().resolve()
        if not candidate_path.is_file() or digest_bytes(candidate_path.read_bytes()) != release_candidate_digest:
            raise StateError("candidate pointer release candidate bytes differ")
        path = self._path("projects", subject_key, "candidate")
        atomic_json(path, {"schema": CANDIDATE_POINTER_SCHEMA, "project_key": subject_key, "project_bundle_manifest_digest": project_bundle_manifest_digest, "release_candidate_path": str(candidate_path), "release_candidate_digest": release_candidate_digest, "repository_identity": repository_identity_value, "project_subpath": project_subpath, "generation": generation, "previous_release_digest": previous_release_digest, "updated_at": utc_now()})
        return path


class DeploymentIndex:
    def __init__(self, state_root: Path):
        self.root = require_absolute(state_root, "deployment index state root")

    @staticmethod
    def selector_key(server_kind: str, server_ref: str, workspace_ref: str) -> str:
        return digest_bytes(canonical_json({"server_kind": server_kind, "server_ref": server_ref, "workspace_ref": workspace_ref}))

    def deployment_path(self, deployment_key: str) -> Path:
        if DIGEST.fullmatch(deployment_key) is None:
            raise StateError("deployment key is invalid")
        return self.root / "deployments" / deployment_key.split(":", 1)[1] / "index.json"

    def selection_path(self, server_kind: str, server_ref: str, workspace_ref: str) -> Path:
        key = self.selector_key(server_kind, server_ref, workspace_ref)
        return self.root / "indexes" / "workspaces" / key.split(":", 1)[1] / "current.json"

    def read(self, deployment_key: str) -> dict[str, Any]:
        path = self.deployment_path(deployment_key)
        value = read_object(path, "Workspace deployment index")
        if value.get("schema") != DEPLOYMENT_INDEX_SCHEMA or value.get("deployment_key") != deployment_key:
            raise StateError("Workspace deployment index identity differs")
        return {**value, "_path": str(path), "_digest": digest_bytes(path.read_bytes())}

    def resolve(self, server_kind: str, server_ref: str, workspace_ref: str) -> dict[str, Any]:
        path = self.selection_path(server_kind, server_ref, workspace_ref)
        selector = read_object(path, "Workspace selection index")
        expected_key = self.selector_key(server_kind, server_ref, workspace_ref)
        if selector.get("schema") != SELECTION_INDEX_SCHEMA or selector.get("selector_key") != expected_key:
            raise StateError("Workspace selection index identity differs")
        deployment = self.read(str(selector.get("deployment_key")))
        if deployment["workspace_ref"] != workspace_ref or deployment["workspace_key"] != selector.get("workspace_key"):
            raise StateError("Workspace selection index target differs")
        return deployment

    def publish_foundation(self, *, server_kind: str, server_ref: str, workspace_ref: str, deployment_key: str, workspace_key_value: str, foundation_manifest_digest: str, relocation_intent_digest: str | None = None) -> Path:
        for value, label in ((deployment_key, "deployment key"), (workspace_key_value, "workspace key"), (foundation_manifest_digest, "Foundation manifest digest")):
            if DIGEST.fullmatch(value) is None:
                raise StateError(f"{label} is invalid")
        path = self.deployment_path(deployment_key)
        previous = self.read(deployment_key) if path.is_file() else None
        projects = previous.get("projects", {}) if previous else {}
        server_manifest = previous.get("server_manifest_digest") if previous else None
        generation = int(previous.get("generation", 0)) + 1 if previous else 1
        value = {"schema": DEPLOYMENT_INDEX_SCHEMA, "deployment_key": deployment_key, "workspace_key": workspace_key_value, "server_kind": server_kind, "server_ref": server_ref, "workspace_ref": workspace_ref, "foundation_manifest_digest": foundation_manifest_digest, "server_manifest_digest": server_manifest, "projects": projects, "relocation_intent_digest": relocation_intent_digest, "generation": generation, "updated_at": utc_now()}
        atomic_json(path, value)
        selection_path = self.selection_path(server_kind, server_ref, workspace_ref)
        atomic_json(selection_path, {"schema": SELECTION_INDEX_SCHEMA, "selector_key": self.selector_key(server_kind, server_ref, workspace_ref), "deployment_key": deployment_key, "workspace_key": workspace_key_value, "updated_at": utc_now()})
        return path

    def publish_server(self, deployment_key: str, server_manifest_digest: str) -> Path:
        if DIGEST.fullmatch(server_manifest_digest) is None:
            raise StateError("Server manifest digest is invalid")
        value = self.read(deployment_key)
        path = Path(value.pop("_path"))
        value.pop("_digest", None)
        value.update({"server_manifest_digest": server_manifest_digest, "generation": value["generation"] + 1, "updated_at": utc_now()})
        atomic_json(path, value)
        return path

    def publish_project(self, deployment_key: str, project_key_value: str, project_manifest_digest: str, candidate_digest: str) -> Path:
        for value, label in ((project_key_value, "project key"), (project_manifest_digest, "Project manifest digest"), (candidate_digest, "candidate digest")):
            if DIGEST.fullmatch(value) is None:
                raise StateError(f"{label} is invalid")
        value = self.read(deployment_key)
        path = Path(value.pop("_path"))
        value.pop("_digest", None)
        projects = dict(value.get("projects", {}))
        projects[project_key_value] = {"project_manifest_digest": project_manifest_digest, "candidate_digest": candidate_digest}
        value.update({"projects": dict(sorted(projects.items())), "generation": value["generation"] + 1, "updated_at": utc_now()})
        atomic_json(path, value)
        return path


def write_resolution(path: Path, *, run_id: str, request: Mapping[str, Any], resolved_input: Path, fields: Mapping[str, Any]) -> None:
    atomic_json(path, {"schema": RESOLUTION_SCHEMA, "run_id": run_id, "request_digest": digest_bytes(canonical_json(request)), "resolved_input": str(resolved_input), "resolved_input_digest": digest_bytes(resolved_input.read_bytes()), "fields": dict(sorted(fields.items()))})
