"""Versioned, stable Runtime capability evidence for orchestration handoffs."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

RUNTIME_CAPABILITY_EVIDENCE_SCHEMA = "multica-orchestrator.runtime-capability-evidence.v1"


class RuntimeCapabilityEvidenceError(ValueError):
    """A Runtime readback cannot produce unambiguous capability evidence."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeCapabilityEvidenceError(
            f"RUNTIME_CAPABILITY_READBACK_INVALID: {label} must be an object"
        )
    return value


def _string(
    record: Mapping[str, Any],
    metadata: Mapping[str, Any],
    fields: Sequence[str],
    label: str,
    *,
    required: bool,
) -> str | None:
    values: list[tuple[str, str]] = []
    for source_name, source in (("runtime", record), ("metadata", metadata)):
        for field in fields:
            if field not in source:
                continue
            value = source[field]
            if value in (None, "") and not required:
                continue
            if not isinstance(value, str) or not value.strip():
                raise RuntimeCapabilityEvidenceError(
                    f"RUNTIME_CAPABILITY_READBACK_INVALID: {source_name}.{field} must be a non-empty string"
                )
            values.append((f"{source_name}.{field}", value))
    if not values:
        if required:
            raise RuntimeCapabilityEvidenceError(
                f"RUNTIME_CAPABILITY_READBACK_INVALID: Runtime lacks {label}"
            )
        return None
    distinct = {value for _, value in values}
    if len(distinct) != 1:
        locations = ", ".join(location for location, _ in values)
        raise RuntimeCapabilityEvidenceError(
            f"RUNTIME_CAPABILITY_READBACK_AMBIGUOUS: conflicting {label} at {locations}"
        )
    return values[0][1]


def _capability_names(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value} if value else set()
    if isinstance(value, list):
        return {name for item in value for name in _capability_names(item)}
    if isinstance(value, Mapping):
        names = {
            key
            for key, enabled in value.items()
            if isinstance(key, str) and enabled is True
        }
        for nested in value.values():
            names.update(_capability_names(nested))
        return names
    return set()


def runtime_capabilities(value: Mapping[str, Any]) -> frozenset[str]:
    """Read capabilities from the supported top-level or metadata locations."""
    record = _mapping(value, "Runtime")
    metadata_value = record.get("metadata", {})
    metadata = _mapping(metadata_value, "Runtime metadata") if metadata_value is not None else {}
    observed: list[tuple[str, set[str]]] = []
    if "capabilities" in record:
        observed.append(("runtime.capabilities", _capability_names(record["capabilities"])))
    if "capabilities" in metadata:
        observed.append(("metadata.capabilities", _capability_names(metadata["capabilities"])))
    if len(observed) == 2 and observed[0][1] != observed[1][1]:
        raise RuntimeCapabilityEvidenceError(
            "RUNTIME_CAPABILITY_READBACK_AMBIGUOUS: conflicting runtime.capabilities and metadata.capabilities"
        )
    return frozenset(observed[0][1] if observed else set())


def runtime_capability_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable, versioned evidence whose digest anchors Runtime capability."""
    record = _mapping(value, "Runtime")
    metadata_value = record.get("metadata", {})
    metadata = _mapping(metadata_value, "Runtime metadata") if metadata_value is not None else {}
    return {
        "schema": RUNTIME_CAPABILITY_EVIDENCE_SCHEMA,
        "runtime_ref": _string(record, metadata, ("id", "runtime_id"), "runtime_ref", required=True),
        "daemon_ref": _string(record, metadata, ("daemon_id", "daemon_ref"), "daemon_ref", required=True),
        "provider": _string(record, metadata, ("provider",), "provider", required=True),
        "runtime_mode": _string(record, metadata, ("runtime_mode", "mode"), "runtime_mode", required=False),
        "runtime_version": _string(record, metadata, ("runtime_version", "version"), "runtime_version", required=False),
        "capabilities": sorted(runtime_capabilities(record)),
    }


def runtime_capability_revision(value: Mapping[str, Any]) -> str:
    """Digest stable Runtime capability evidence with the handoff wire format."""
    encoded = json.dumps(
        runtime_capability_evidence(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def runtime_fleet_stability_projection(values: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Canonical fleet projection for capture fences; ignores heartbeat-only fields."""
    evidence = [runtime_capability_evidence(value) for value in values]
    references = [item["runtime_ref"] for item in evidence]
    if len(set(references)) != len(references):
        raise RuntimeCapabilityEvidenceError(
            "RUNTIME_CAPABILITY_READBACK_AMBIGUOUS: Runtime fleet contains duplicate runtime_ref values"
        )
    return sorted(evidence, key=lambda item: item["runtime_ref"])
