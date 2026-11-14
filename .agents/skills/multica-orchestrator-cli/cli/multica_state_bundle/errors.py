"""Typed, secret-safe failures for the Multica state bundle."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ErrorDetail:
    """Portable diagnostic data with no secret-bearing fields."""

    code: str
    message: str
    next_action: str
    exit_code: int = 2

    def as_dict(self) -> Mapping[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "next_action": self.next_action,
        }


class StateBundleError(ValueError):
    """A safe, typed error that callers can render without leaking secrets."""

    def __init__(self, code: str, message: str, next_action: str, *, exit_code: int = 2):
        super().__init__(message)
        self.detail = ErrorDetail(code, message, next_action, exit_code)

    @property
    def code(self) -> str:
        return self.detail.code

    @property
    def next_action(self) -> str:
        return self.detail.next_action

    @property
    def exit_code(self) -> int:
        return self.detail.exit_code

    def as_dict(self) -> Mapping[str, object]:
        return self.detail.as_dict()


class StateError(StateBundleError):
    """Compatibility name for state validation failures within the package."""

    def __init__(self, message: str, *, code: str = "GENERATION_INTEGRITY_INVALID", next_action: str = "Inspect the affected state and establish a valid lifecycle generation."):
        super().__init__(code, message, next_action)


class BundleError(StateBundleError):
    """Compatibility name for immutable handoff bundle failures."""

    def __init__(self, message: str, *, code: str = "GENERATION_INTEGRITY_INVALID", next_action: str = "Recreate the affected handoff from its applicable lifecycle stage."):
        super().__init__(code, message, next_action)
