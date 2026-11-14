"""Canonical provider names and verified OMP model-catalog resolution."""
from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Mapping, Sequence


PROVIDER_ALIASES = {"ohmypi": "omp"}
MODEL_FAMILIES = ("Luna", "Terra", "Sol")


class ProviderModelError(ValueError):
    """A provider or its model catalog cannot satisfy orchestration policy."""


def canonical_provider(provider: str) -> str:
    """Return the supported canonical provider name without guessing unknown values."""
    if not isinstance(provider, str) or not provider.strip():
        raise ProviderModelError("Runtime provider must be a non-empty string")
    normalized = provider.strip().lower()
    return PROVIDER_ALIASES.get(normalized, normalized)


def query_omp_models(executable: str = "omp") -> list[Mapping[str, Any]]:
    """Read OMP's live machine-readable catalog; never synthesize model IDs."""
    completed = subprocess.run(
        [executable, "models", "--json"], text=True, capture_output=True, check=False
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise ProviderModelError(f"OMP_MODEL_CATALOG_UNAVAILABLE: {detail or 'omp models failed'}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ProviderModelError("OMP_MODEL_CATALOG_INVALID: omp models did not return JSON") from error
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list) or not all(isinstance(model, Mapping) for model in models):
        raise ProviderModelError("OMP_MODEL_CATALOG_INVALID: models must be an array")
    return models


def resolve_omp_families(
    models: Sequence[Mapping[str, Any]], required_thinking: Mapping[str, set[str]]
) -> dict[str, str]:
    """Resolve Luna, Terra, and Sol to one catalog selector each.

    A family is usable only when the live catalog has exactly one `-<family>`
    model with a non-empty exact selector and all requested thinking levels.
    """
    resolved: dict[str, str] = {}
    for family in MODEL_FAMILIES:
        suffix = "-" + family.lower()
        matches = [
            model
            for model in models
            if isinstance(model.get("id"), str)
            and model["id"].lower().endswith(suffix)
            and isinstance(model.get("selector"), str)
            and model["selector"].strip()
        ]
        selectors = {model["selector"] for model in matches}
        if len(matches) != 1 or len(selectors) != 1:
            raise ProviderModelError(
                f"ORCHESTRATION_POLICY_INPUT_REQUIRED: {family} must resolve to exactly one OMP catalog model"
            )
        thinking = matches[0].get("thinking")
        if not isinstance(thinking, list) or not all(isinstance(level, str) for level in thinking):
            raise ProviderModelError(
                f"ORCHESTRATION_POLICY_INPUT_REQUIRED: {family} catalog model lacks thinking capability readback"
            )
        missing = required_thinking.get(family, set()) - set(thinking)
        if missing:
            raise ProviderModelError(
                f"ORCHESTRATION_POLICY_INPUT_REQUIRED: {family} does not support thinking {', '.join(sorted(missing))}"
            )
        resolved[family] = matches[0]["selector"]
    return resolved
