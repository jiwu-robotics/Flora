"""Read-only project-state validation and redacted diagnostic rendering."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .errors import StateBundleError
from .generations import validate_generation
from .namespaces import ProjectNamespace, resolve_namespace

INSPECTION_SCHEMA = "multica-state-bundle.inspection-result.v1"


def _result(namespace: ProjectNamespace, *, stage: str | None, readiness: str, blocker: StateBundleError | None = None, generation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    material = namespace.directory / "private-material.json"
    result: dict[str, Any] = {
        "schema": INSPECTION_SCHEMA,
        "project_key": namespace.project_key,
        "stage": stage,
        "generation": generation.get("generation") if generation else None,
        "readiness": readiness,
        "protected_material": "present" if material.is_file() else "absent",
        "redactions": ["credentials", "tokens", "secret_paths"],
    }
    if blocker is not None:
        result.update({"blocker_code": blocker.code, "next_action": blocker.next_action})
    return result


def inspect_namespace(*, state_root: Path | str | None, workspace_key_value: str | None, repository: str, subpath: str, stage: str | None) -> dict[str, Any]:
    if workspace_key_value is None:
        raise StateBundleError(
            "PROJECT_IDENTITY_MISSING",
            "a workspace key is required to select one project namespace",
            "Provide the validated workspace key from the selected lifecycle state.",
        )
    namespace = resolve_namespace(
        state_root=state_root,
        workspace_key_value=workspace_key_value,
        repository=repository,
        subpath=subpath,
    )
    if stage is None:
        return _result(namespace, stage=None, readiness="READY")
    try:
        generation = validate_generation(namespace.root, namespace.project_key, stage)
    except StateBundleError as error:
        return _result(namespace, stage=stage, readiness="BLOCKED", blocker=error)
    return _result(namespace, stage=stage, readiness="READY", generation=generation)


def validate_namespace(**arguments: Any) -> dict[str, Any]:
    """Alias with the same read-only behavior, retained as a command-level verb."""
    return inspect_namespace(**arguments)
