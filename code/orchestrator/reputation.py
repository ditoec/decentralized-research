"""Per-provider reputation record for the testbed (runbook section 7 item 2).

Starts at 0.5. A verified pass moves it toward 1 (r <- r + up * (1 - r)); a confirmed fail
(two verifiers against the provider, bond slashed) lowers it (r <- r * (1 - down)). Unsampled and
unresolved jobs leave it unchanged. Providers below ``minimum`` are not assigned new jobs.
Reputation is recorded for the testbed only; it is not part of the RQ2 detection metrics.
"""
from __future__ import annotations

import json
from pathlib import Path

START = 0.5


class Reputation:
    def __init__(self, path: str | Path | None = None, up: float = 0.1, down: float = 0.5, minimum: float = 0.2):
        self.path = Path(path) if path else None
        self.up, self.down, self.minimum = up, down, minimum
        self.scores: dict[str, float] = {}
        self.history: list[dict] = []
        if self.path and self.path.exists():
            d = json.loads(self.path.read_text())
            self.scores, self.history = d["scores"], d.get("history", [])

    def get(self, provider: str) -> float:
        return self.scores.get(provider, START)

    def eligible(self, provider: str) -> bool:
        return self.get(provider) >= self.minimum

    def record(self, provider: str, outcome: str, job_id: int | None = None) -> float:
        """outcome: "pass" (verified pass, incl. a dispute won), "fail" (confirmed fail), anything else: no change."""
        r = self.get(provider)
        if outcome == "pass":
            r = r + self.up * (1 - r)
        elif outcome == "fail":
            r = r * (1 - self.down)
        self.scores[provider] = r
        self.history.append({"provider": provider, "job_id": job_id, "outcome": outcome, "reputation": r})
        if self.path:
            self.path.write_text(json.dumps({"scores": self.scores, "history": self.history}, indent=1))
        return r
