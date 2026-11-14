"""Credential-free project namespace creation and read-only resolution."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .errors import StateBundleError
from .identities import DIGEST, default_state_root, normalize_subpath, project_key, read_object, repository_identity, require_absolute, utc_now
from .storage import atomic_json, require_private_directory

NAMESPACE_SCHEMA = "multica-state-bundle.project-namespace.v1"


@dataclass(frozen=True)
class ProjectNamespace:
    root: Path
    project_key: str
    workspace_key: str
    repository_identity: str
    project_subpath: str

    @property
    def directory(self) -> Path:
        return self.root / "projects" / self.project_key.split(":", 1)[1]

    @property
    def descriptor_path(self) -> Path:
        return self.directory / "namespace.json"



@dataclass(frozen=True)
class WorkspaceNamespace:
    root: Path
    workspace_key: str

    @property
    def project_key(self) -> str:
        return self.workspace_key

    @property
    def directory(self) -> Path:
        return self.root / "workspaces" / self.workspace_key.split(":", 1)[1]

    @property
    def descriptor_path(self) -> Path:
        return self.directory / "namespace.json"


def create_workspace_namespace(*, state_root: Path | str | None, workspace_key_value: str) -> WorkspaceNamespace:
    if DIGEST.fullmatch(workspace_key_value) is None:
        raise StateBundleError(
            "PROJECT_IDENTITY_MISSING",
            "a validated workspace key is required",
            "Provide the validated workspace key from the selected lifecycle state.",
        )
    root = require_absolute(Path(state_root) if state_root is not None else default_state_root(), "state root")
    namespace = WorkspaceNamespace(root, workspace_key_value)
    require_private_directory(namespace.directory)
    if not namespace.descriptor_path.exists():
        atomic_json(
            namespace.descriptor_path,
            {
                "schema": "multica-state-bundle.workspace-namespace.v1",
                "workspace_key": workspace_key_value,
                "created_at": utc_now(),
                "state_version": 1,
            },
        )
    return namespace


def established_project_namespace(*, state_root: Path | str | None, project_key_value: str) -> ProjectNamespace:
    if DIGEST.fullmatch(project_key_value) is None:
        raise StateBundleError(
            "PROJECT_IDENTITY_MISSING",
            "a validated project key is required",
            "Use the project key from a verified Project binding.",
        )
    root = require_absolute(Path(state_root) if state_root is not None else default_state_root(), "state root")
    namespace = ProjectNamespace(root, project_key_value, "", "", "")
    require_private_directory(namespace.directory)
    return namespace

def _identity(workspace_key_value: str, repository: str, subpath: str) -> tuple[str, str, str]:
    if DIGEST.fullmatch(workspace_key_value) is None:
        raise StateBundleError(
            "PROJECT_IDENTITY_MISSING",
            "a validated workspace key is required",
            "Provide the validated workspace key from the selected lifecycle state.",
        )
    identity = repository_identity(repository)
    normalized = normalize_subpath(subpath)
    return project_key(workspace_key_value, identity, normalized), identity, normalized


def create_namespace(
    *, state_root: Path | str | None, workspace_key_value: str, repository: str, subpath: str
) -> ProjectNamespace:
    root = require_absolute(Path(state_root) if state_root is not None else default_state_root(), "state root")
    key, identity, normalized = _identity(workspace_key_value, repository, subpath)
    namespace = ProjectNamespace(root, key, workspace_key_value, identity, normalized)
    directory = require_private_directory(namespace.directory)
    if namespace.descriptor_path.exists():
        resolve_namespace(
            state_root=root,
            workspace_key_value=workspace_key_value,
            repository=repository,
            subpath=subpath,
        )
        return namespace
    atomic_json(
        namespace.descriptor_path,
        {
            "schema": NAMESPACE_SCHEMA,
            "project_key": key,
            "workspace_key": workspace_key_value,
            "repository_identity": identity,
            "project_subpath": normalized,
            "created_at": utc_now(),
            "state_version": 1,
        },
    )
    return namespace


def resolve_namespace(
    *, state_root: Path | str | None, workspace_key_value: str, repository: str, subpath: str
) -> ProjectNamespace:
    root = require_absolute(Path(state_root) if state_root is not None else default_state_root(), "state root")
    key, identity, normalized = _identity(workspace_key_value, repository, subpath)
    namespace = ProjectNamespace(root, key, workspace_key_value, identity, normalized)
    try:
        descriptor = read_object(namespace.descriptor_path, "project namespace")
    except StateBundleError as error:
        raise StateBundleError(
            "PROJECT_IDENTITY_MISSING",
            "the selected project namespace has not been established",
            "Run the applicable first lifecycle stage to establish project state.",
        ) from error
    expected: Mapping[str, Any] = {
        "schema": NAMESPACE_SCHEMA,
        "project_key": key,
        "workspace_key": workspace_key_value,
        "repository_identity": identity,
        "project_subpath": normalized,
        "state_version": 1,
    }
    if any(descriptor.get(name) != value for name, value in expected.items()):
        raise StateBundleError(
            "PROJECT_NAMESPACE_MISMATCH",
            "the selected project namespace does not match its credential-free identity",
            "Select the matching workspace, repository, and project subpath.",
        )
    return namespace
