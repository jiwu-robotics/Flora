"""Shared state primitives for the Multica orchestrator lifecycle."""
from .errors import BundleError, ErrorDetail, StateBundleError, StateError

__all__ = ["BundleError", "ErrorDetail", "StateBundleError", "StateError"]
__version__ = "1.0.0"
