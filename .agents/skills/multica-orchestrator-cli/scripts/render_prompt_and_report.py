#!/usr/bin/env python3
"""Render one immutable raw capture pair as a private two-section review document."""
from __future__ import annotations

import argparse
import re
import os
import tempfile
from pathlib import Path


class RenderError(ValueError):
    pass


def atomic_private_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            raise RenderError(f"refusing to overwrite: {path}")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-id", required=True)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        archive = args.cwd.resolve() / ".prompt-and-report"
        prompt_path = archive / f"{args.capture_id}.prompt.md"
        report_path = archive / f"{args.capture_id}.report.md"
        prompt = prompt_path.read_text(encoding="utf-8")
        report = report_path.read_text(encoding="utf-8")
        longest_fence = max((len(run) for run in re.findall(r"`+", prompt)), default=0)
        fence = "`" * max(3, longest_fence + 1)
        escaped_report = "\n".join(("\\" + line) if re.match(r"^#(?:[ \t]|$)", line) else line for line in report.splitlines())
        if report.endswith("\n"):
            escaped_report += "\n"
        rendered = f"# 提示词\n\n{fence}markdown\n{prompt.rstrip()}\n{fence}\n\n# 运行报告\n\n{escaped_report}"
        output = args.output.resolve() if args.output else archive / f"{args.capture_id}.md"
        atomic_private_write(output, rendered.encode("utf-8"))
        print(output)
        return 0
    except (OSError, UnicodeDecodeError, RenderError) as error:
        print(f"error: {error}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
