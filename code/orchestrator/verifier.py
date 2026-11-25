"""Runs the existing verifier, ``python -m trajver.verify``, and turns its output into an on-chain verdict.

trajver.verify scores a run folder and writes long-format rows to <new run>/verdicts.jsonl
(``job_id, attack, s, evidence, k, verdict, score, ...``). The ``attack`` and ``s`` fields carry the
ground-truth label of experiment runs. They are dropped here, before anything else reads the rows:
the ground-truth attack label is never used to resolve a dispute (runbook section 7 item 1).

The on-chain verdict for a job is the E2-H verdict at the configured k. A failed verifier run, a
missing row or any other verdict maps to "inconclusive". The commitment recorded on chain is the
SHA-256 of the verifier's own (label-free) output rows for that job.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
KEEP = ("job_id", "evidence", "k", "verdict", "score", "tier_b", "steps", "retention", "reasons")


@dataclass
class VerifierOutcome:
    verdict: str  # "pass" | "fail" | "inconclusive"
    commitment: str  # hex sha256
    run_id: str
    rows: list[dict]
    error: str | None = None


def strip_labels(row: dict) -> dict:
    """Keep only verifier-computed fields (drops ``attack``, ``s`` and anything else)."""
    return {k: row[k] for k in KEEP if k in row}


def decide(rows: list[dict], job_key: str, k: int, evidence: str = "E2-H") -> str:
    hit = [r for r in rows if r.get("job_id") == job_key and r.get("evidence") == evidence and r.get("k") == k]
    if len(hit) != 1:
        return "inconclusive"
    v = hit[0].get("verdict")
    return v if v in ("pass", "fail") else "inconclusive"


@dataclass
class TrajverVerifier:
    """``args``: the remaining trajver.verify arguments (--ckpt, --prompts, --thresholds, --th-sha256, ...).
    ``prefix``: per-node command prefix (for example a remote shell to the Spark); kept out of the
    repository and given at run time. Empty = run locally."""

    args: list[str]
    k: int = 3
    python: str = sys.executable
    module: str = "trajver.verify"  # tests substitute a stand-in module with the same CLI and output
    runs_root: Path = CODE_DIR.parent / "experiments" / "runs"
    prefix: dict[str, list[str]] = field(default_factory=dict)
    timeout_s: float = 3600

    def command(self, node: str, run_dir: str, run_id: str) -> list[str]:
        return [*self.prefix.get(node, []), self.python, "-m", self.module, str(run_dir),
                "--wp", "wp5", "--run-id", run_id, *self.args]

    def verify(self, node: str, job_id: int, run_dir: str, job_key: str) -> VerifierOutcome:
        rid = f"{_dt.date.today():%Y%m%d}-wp5-verify-{job_id}-{node}"
        env = {**os.environ, "TRAJVER_RUNS": str(self.runs_root)}
        err = None
        try:
            p = subprocess.run(self.command(node, run_dir, rid), cwd=CODE_DIR, env=env, capture_output=True,
                               text=True, timeout=self.timeout_s)
            if p.returncode != 0:
                err = f"{self.module} exited {p.returncode}: {p.stderr[-500:]}"
        except subprocess.TimeoutExpired:
            err = f"{self.module} timed out"
        path = self.runs_root / rid / "verdicts.jsonl"
        rows = []
        if path.exists():
            rows = [strip_labels(json.loads(l)) for l in path.read_text().splitlines() if l.strip()]
        mine = [r for r in rows if r.get("job_id") == job_key]
        verdict = "inconclusive" if err else decide(mine, job_key, self.k)
        blob = json.dumps(mine, sort_keys=True, separators=(",", ":")).encode()
        return VerifierOutcome(verdict, hashlib.sha256(blob).hexdigest(), rid, mine, err)
