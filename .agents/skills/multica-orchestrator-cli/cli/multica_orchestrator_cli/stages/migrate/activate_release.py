#!/usr/bin/env python3
"""Compatibility entrypoint; additional-host activation lives in activate_targets."""
from activate_targets import main


if __name__ == "__main__":
    raise SystemExit(main())