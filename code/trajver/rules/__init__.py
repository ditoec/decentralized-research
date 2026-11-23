"""Verdict functions. Every rule returns a :class:`Verdict` with its raw scores, so thresholds
can be re-applied offline after calibration (runbook §5) without re-running the GPU work."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

PASS, FAIL, INCONCLUSIVE = "pass", "fail", "inconclusive"


@dataclass
class Verdict:
    rule: str
    verdict: str
    scores: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verdict == PASS

    def to_dict(self) -> dict:
        return asdict(self)


def combine(rule: str, parts: list[Verdict]) -> Verdict:
    """Fail if any part fails; inconclusive if any part is inconclusive; else pass."""
    verdicts = [p.verdict for p in parts]
    v = FAIL if FAIL in verdicts else INCONCLUSIVE if INCONCLUSIVE in verdicts else PASS
    return Verdict(rule, v, {p.rule: p.to_dict() for p in parts},
                   [f"{p.rule}: {r}" for p in parts for r in p.reasons])
