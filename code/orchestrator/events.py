"""Append-only JSON-lines event log with wall-clock (UTC, ms) and monotonic timestamps."""
from __future__ import annotations

import datetime as _dt
import json
import threading
import time
from pathlib import Path


class EventLog:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.events: list[dict] = []
        self._lock = threading.Lock()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, source: str, event: str, **fields) -> dict:
        """source is "chain" (a confirmed transaction) or "offchain" (queue, assignment, execution, verification)."""
        e = {"t": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds"),
             "mono": round(time.monotonic(), 6), "source": source, "event": event, **fields}
        with self._lock:
            self.events.append(e)
            if self.path:
                with self.path.open("a") as f:
                    f.write(json.dumps(e, sort_keys=True) + "\n")
        return e
