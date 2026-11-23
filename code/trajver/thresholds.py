"""Acceptance thresholds.

``DEV_DEFAULTS`` are placeholders that let the code run before calibration. They are NOT the
paper's thresholds. The paper's values come from the calibration split (runbook §5), are
written to ``experiments/configs/thresholds_v1.json`` and frozen by hash before any attack data
is examined. :func:`load` refuses a file whose hash does not match the one given.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

DEV_DEFAULTS = {
    "version": "dev",
    # E1
    "x0_max_ulp": 4,              # x_0 across CPU ISAs (finding 6); set from pilot P1, then frozen
    "cond_rel_l2": 1e-3,          # conditioning re-encode, relative L2
    "image_max_abs": 2,           # decoded image vs delivered image, uint8 levels
    # Tier A
    "eps_a_rel_l2": 1e-5,         # relative L2 of recomputed vs committed x_{i+1}
    # Tier B
    "tier_b_metric": "rel_l2",
    "tau_default": 1e-3,          # used for steps without a calibrated tau_i
    "tau": {},                    # {"7": 0.0012, ...} per-step tolerances after calibration
    "k": 3,
    # E2-W (deployed SN30 rule, not calibrated by design)
    "e2w_score_min": 0.85,
    # E0-N (deployed SN23 rule)
    "e0n_full_reward": 0.9,
}


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path: str | Path | None = None, expected_sha256: str | None = None) -> dict:
    if path is None:
        return dict(DEV_DEFAULTS)
    digest = file_sha256(path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(f"threshold file {path} has sha256 {digest}, expected {expected_sha256}")
    th = dict(DEV_DEFAULTS)
    th.update(json.loads(Path(path).read_text()))
    th["_sha256"] = digest
    return th


def tau_for(th: dict, step: int) -> float:
    return float(th.get("tau", {}).get(str(step), th["tau_default"]))
