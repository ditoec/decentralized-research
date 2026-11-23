"""Analytical model of manuscript §3-3 (Equations 4–9)."""
from __future__ import annotations

import math


def q_spot_check(T: int, m: int, k: int, r: float, alpha_s: float) -> float:
    """Eq. 4: P(a sampled job with m faked steps fails Tier B), k steps checked w/o replacement."""
    total = math.comb(T, k)
    q_pass = 0.0
    for x in range(0, min(k, m) + 1):
        if k - x > T - m:
            continue
        p_x = math.comb(m, x) * math.comb(T - m, k - x) / total
        q_pass += p_x * (1 - r) ** x * (1 - alpha_s) ** (k - x)
    return 1 - q_pass


def q_large_T(s: float, k: int, r: float, alpha_s: float) -> float:
    return 1 - (1 - s * r - (1 - s) * alpha_s) ** k


def alpha_job(alpha_s: float, k: int) -> float:
    """Eq. 5: job-level false rejection of an honest job."""
    return 1 - (1 - alpha_s) ** k


def alpha_step_budget(alpha_star: float, k: int) -> float:
    """Eq. 6: the per-step false-rejection rate that keeps the job-level rate at alpha_star."""
    return 1 - (1 - alpha_star) ** (1 / k)


def gain(s: float, beta: float, c: float, p: float, k: int, r: float, alpha_s: float, L: float) -> float:
    """Eq. 7 (large-T): expected gain of faking a fraction s of steps, relative to honesty."""
    return beta * s * c - p * (q_large_T(s, k, r, alpha_s) - alpha_job(alpha_s, k)) * L


def deterred(p: float, k: int, r: float, alpha_s: float, P: float, B: float, beta: float, c: float) -> bool:
    """Eq. 8."""
    return p * (1 - (1 - r) ** k - alpha_job(alpha_s, k)) * (P + B) >= beta * c


def p_star(k: int, attacks: list[tuple[float, float]], alpha_s: float, P: float, B: float, c: float) -> float:
    """Eq. 9: smallest sampling rate deterring every attack (beta_A, r_A). inf if infeasible."""
    worst = 0.0
    for beta, r in attacks:
        margin = 1 - (1 - r) ** k - alpha_job(alpha_s, k)
        if margin <= 0:
            return math.inf
        worst = max(worst, beta * c / (margin * (P + B)))
    return worst
