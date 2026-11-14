"""Shared validation and immutable-output helpers for Dispatch commands."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REVISION = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class InputError(ValueError):
    """Dispatch input cannot prove the requested operation."""




def read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InputError(f"{label} is not valid UTF-8 JSON: {error}") from error
