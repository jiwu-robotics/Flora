#!/usr/bin/env python3
"""Reserve due Human reminders and emit a restricted workflow-leader outbox."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from control_store import ControlError, control_session, notification_reminder_reserve


def timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_outbox(directory: Path, event: dict[str, object]) -> Path:
    directory = directory.expanduser().resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    name = f"{event['reservation_ref'].replace(':', '_')}-{event['revision']}.json"
    destination = directory / name
    temporary = directory / f".{name}.{os.getpid()}.tmp"
    temporary.write_text(
        json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    os.replace(temporary, destination)
    destination.chmod(0o600)
    return destination


def reserve_due(db_path: Path, outbox: Path, observed_at: str) -> list[Path]:
    outputs: list[Path] = []
    with control_session(db_path) as db:
        rows = db.execute(
            "SELECT reservation_ref, revision FROM notification_reservations "
            "WHERE state='SENT' AND reminder_count < 2 "
            "AND next_reminder_at IS NOT NULL AND next_reminder_at <= ? "
            "ORDER BY next_reminder_at, reservation_ref",
            (observed_at,),
        ).fetchall()
    for row in rows:
        try:
            with control_session(db_path) as db:
                event = notification_reminder_reserve(
                    db,
                    SimpleNamespace(
                        reservation=row["reservation_ref"],
                        expected_revision=row["revision"],
                        at=observed_at,
                    ),
                )
        except ControlError:
            continue
        event["scheduler_observed_at"] = observed_at
        outputs.append(write_outbox(outbox, event))
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--outbox", type=Path, required=True)
    parser.add_argument("--poll-interval", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--now", dest="observed_at")
    arguments = parser.parse_args()
    if arguments.poll_interval < 1:
        parser.error("--poll-interval must be positive")

    arguments.outbox = arguments.outbox.expanduser().resolve()
    arguments.outbox.mkdir(mode=0o700, parents=True, exist_ok=True)
    arguments.outbox.chmod(0o700)
    print("notification-scheduler READY", flush=True)
    while True:
        observed_at = arguments.observed_at or timestamp()
        for path in reserve_due(arguments.db, arguments.outbox, observed_at):
            print(f"reserved {path.name}", flush=True)
        if arguments.once:
            return 0
        time.sleep(arguments.poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
