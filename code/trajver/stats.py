"""Interval estimates shared by the analysis scripts (no torch, so they run anywhere).

``wilson`` is the same function as ``montecarlo.wilson`` on the WP4 branch (claude/wp4-montecarlo);
when that branch merges, it should import this one instead of keeping its own copy.
"""
from __future__ import annotations

import math

import numpy as np

Z95 = 1.959963984540054


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Two-sided Wilson score interval for a binomial proportion [Wilson 1927]."""
    if n == 0:
        return (0.0, 1.0)
    ph = successes / n
    den = 1 + z * z / n
    centre = (ph + z * z / (2 * n)) / den
    half = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    lo = 0.0 if successes == 0 else max(0.0, centre - half)  # exact ends, not rounding residue
    hi = 1.0 if successes == n else min(1.0, centre + half)
    return (lo, hi)


def _binom_cdf(x: int, n: int, p: float) -> float:
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 1.0 if x >= n else 0.0
    lp, lq = math.log(p), math.log1p(-p)
    return min(1.0, sum(math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq)
                        for i in range(0, x + 1)))


def cp_upper(successes: int, n: int, alpha: float = 0.05) -> float:
    """One-sided exact (Clopper-Pearson) upper bound: the p with P(X <= successes; n, p) = alpha.

    This is the bound behind the runbook's "zero false rejections in 299 bound the rate below 1% at
    95% confidence": cp_upper(0, 299) = 1 - 0.05**(1/299) = 0.00997. The two-sided Wilson upper limit
    for 0/299 is higher (0.0127)."""
    if n == 0:
        return 1.0
    if successes >= n:
        return 1.0
    lo, hi = successes / n, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if _binom_cdf(successes, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def cluster_bootstrap_median(values, clusters, n_boot: int = 10000, seed: int = 20261126,
                             level: float = 0.95) -> tuple[float, float]:
    """Percentile CI of the median, resampling whole clusters (prompts) with replacement."""
    groups: dict = {}
    for v, c in zip(values, clusters):
        groups.setdefault(c, []).append(float(v))
    arrs = [np.asarray(g) for g in groups.values()]
    if not arrs:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    C = len(arrs)
    meds = np.empty(n_boot)
    if all(len(a) == 1 for a in arrs):
        flat = np.concatenate(arrs)
        meds = np.median(flat[rng.integers(0, C, size=(n_boot, C))], axis=1)
    else:
        for b in range(n_boot):
            meds[b] = np.median(np.concatenate([arrs[i] for i in rng.integers(0, C, size=C)]))
    a = (1 - level) / 2
    return (float(np.quantile(meds, a)), float(np.quantile(meds, 1 - a)))
