"""WP4 Monte Carlo of Propositions 2 and 3 (manuscript §3-3, Equations 4–9; runbook §8).

Simulates providers that fake a fraction s of the T steps, over a grid of sampling rate p, checked
steps k and bond-to-payment ratio B/P. For each cell it estimates

- the Tier B detection probability of a *sampled* faked job, against Equation 4 (Proposition 2);
- the realized gain from cheating relative to honesty, Δ(s) (Equation 7), with a 95% CI;
- whether the cell is deterred by Equation 8, and where p*(k) of Equation 9 lies (Proposition 3).

All formulas come from `trajver.theory`; this module only draws the random outcomes they describe.

Per job the simulation draws: sampled ~ Bernoulli(p); the number x of faked steps among the k checked
ones ~ Hypergeometric(T, m = round(sT), k); and one uniform U_j per checked step. A faked checked step
fails when U_j < r_A, an honest one when U_j < α_s. The honest counterfactual of the same job uses the
same draws with every step honest, so at s = 0 cheating and honesty coincide exactly (common random
numbers). With a detected fraud forfeiting L = P + B, the per-job gain is

    Δ_i = β_A s c − L · sampled_i · (fail_cheat_i − fail_honest_i),

whose expectation is Equation 7 with the finite-T q of Equation 4.

Inputs r_A, α_s and β_A come from a params file (see `experiments/configs/mc_params_provisional.json`).
Until WP3 produces measured values every output is provisional and is labelled as such.

    python -m trajver.montecarlo --params PARAMS.json --out DIR
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from trajver import theory

Z95 = 1.959963984540054
CSV_COLUMNS = [
    "attack", "p", "k", "BP", "s", "n_sim",
    "detect_sim", "detect_ci_lo", "detect_ci_hi", "detect_closed",
    "gain_mean", "gain_ci_lo", "gain_ci_hi", "gain_closed",
    "deterred", "p_star",
]


# ---------------------------------------------------------------- statistics
def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 1.0)
    ph = successes / n
    den = 1 + z * z / n
    centre = (ph + z * z / (2 * n)) / den
    half = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


# ---------------------------------------------------------------- one cell
@dataclass(frozen=True)
class Cell:
    attack: str
    p: float
    k: int
    BP: float
    s: float
    n_sim: int
    detect_sim: float
    detect_ci_lo: float
    detect_ci_hi: float
    detect_closed: float
    gain_mean: float
    gain_ci_lo: float
    gain_ci_hi: float
    gain_closed: float
    deterred: bool
    p_star: float

    def row(self) -> dict:
        return {c: getattr(self, c) for c in CSV_COLUMNS}


def faked_steps(s: float, T: int) -> int:
    return int(round(s * T))


def simulate_cell(rng: np.random.Generator, *, attack: str, p: float, k: int, BP: float, s: float,
                  T: int, r: float, alpha_s: float, beta: float, c: float, P: float, n_sim: int) -> Cell:
    """Simulate n_sim jobs of one provider strategy s in one (p, k, B/P) cell."""
    if not 1 <= k <= T:
        raise ValueError(f"need 1 <= k <= T, got k={k}, T={T}")
    m = faked_steps(s, T)
    B = BP * P
    L = P + B

    sampled = rng.random(n_sim) < p
    x = rng.hypergeometric(m, T - m, k, size=n_sim) if m > 0 else np.zeros(n_sim, dtype=np.int64)
    u = rng.random((n_sim, k))
    faked = np.arange(k)[None, :] < x[:, None]          # checked steps are exchangeable
    fail_honest = (u < alpha_s).any(axis=1)
    fail_cheat = np.where(faked, u < r, u < alpha_s).any(axis=1)

    n_fail = int(fail_cheat.sum())
    lo, hi = wilson(n_fail, n_sim)
    q_exact = theory.q_spot_check(T, m, k, r, alpha_s)

    delta = beta * s * c - L * sampled * (fail_cheat.astype(np.int8) - fail_honest.astype(np.int8))
    mean = float(delta.mean())
    se = float(delta.std(ddof=1)) / math.sqrt(n_sim) if n_sim > 1 else math.inf
    gain_closed = beta * s * c - p * (q_exact - theory.alpha_job(alpha_s, k)) * L

    return Cell(
        attack=attack, p=p, k=k, BP=BP, s=s, n_sim=n_sim,
        detect_sim=n_fail / n_sim, detect_ci_lo=lo, detect_ci_hi=hi, detect_closed=q_exact,
        gain_mean=mean, gain_ci_lo=mean - Z95 * se, gain_ci_hi=mean + Z95 * se, gain_closed=gain_closed,
        deterred=theory.deterred(p, k, r, alpha_s, P, B, beta, c),
        p_star=theory.p_star(k, [(beta, r)], alpha_s, P, B, c),
    )


# ---------------------------------------------------------------- params
def _val(entry: Any) -> Any:
    """A params entry is {"value": ..., "provisional": ..., "source": ...} or a bare value."""
    return entry["value"] if isinstance(entry, dict) and "value" in entry else entry


def alpha_s_for(params: dict, k: int) -> float:
    """Honest per-step false-rejection rate: the params value, or the Equation 6 budget for alpha_star."""
    a = _val(params.get("alpha_s"))
    if a is not None:
        return float(a)
    a_star = _val(params.get("alpha_star"))
    if a_star is None:
        raise ValueError("params need alpha_s or alpha_star")
    return theory.alpha_step_budget(float(a_star), k)


def ready_attacks(params: dict) -> tuple[list[dict], list[dict]]:
    """Split attacks into those with r_A and beta_A set, and those still awaiting WP3 (null)."""
    ready, waiting = [], []
    for a in params["attacks"]:
        r, b = _val(a.get("r_A")), _val(a.get("beta_A"))
        (ready if r is not None and b is not None else waiting).append(a)
    return ready, waiting


# ---------------------------------------------------------------- sweep
def run_sweep(params: dict, seed: int | None = None, n_sim: int | None = None) -> tuple[list[Cell], dict]:
    seed = int(_val(params["seed"]) if seed is None else seed)
    n_sim = int(_val(params["n_sim"]) if n_sim is None else n_sim)
    T, c, P = int(_val(params["T"])), float(_val(params["c"])), float(_val(params["P"]))
    grid = params["grid"]
    ps, ks, bps, ss = (list(map(float, _val(grid["p"]))), list(map(int, _val(grid["k"]))),
                       list(map(float, _val(grid["BP"]))), list(map(float, _val(grid["s"]))))
    rng = np.random.default_rng(seed)
    ready, waiting = ready_attacks(params)

    cells: list[Cell] = []
    for a in ready:
        r, beta = float(_val(a["r_A"])), float(_val(a["beta_A"]))
        for k in ks:
            a_s = alpha_s_for(params, k)
            for bp in bps:
                for p in ps:
                    for s in ss:
                        cells.append(simulate_cell(rng, attack=a["name"], p=p, k=k, BP=bp, s=s, T=T, r=r,
                                                   alpha_s=a_s, beta=beta, c=c, P=P, n_sim=n_sim))
    checks = _checks(cells)
    meta = {"seed": seed, "n_sim": n_sim, "T": T, "c": c, "P": P,
            "attacks_run": [a["name"] for a in ready],
            "attacks_waiting_for_wp3": [a["name"] for a in waiting]}
    return cells, {**meta, "checks": checks}


def _checks(cells: list[Cell]) -> dict:
    """Compare the simulation with Propositions 2 and 3."""
    if not cells:
        return {}
    # Proposition 2: Equation 4 inside the Wilson CI of the simulated detection rate.
    inside = [c.detect_ci_lo <= c.detect_closed <= c.detect_ci_hi for c in cells]
    # Proposition 3 / Equation 8: at s = 1, deterred iff the simulated Δ(1) is not above 0.
    groups: dict[tuple, list[Cell]] = {}
    for c in cells:
        groups.setdefault((c.attack, c.p, c.k, c.BP), []).append(c)
    agree = disagree = inconclusive = 0
    interior_max = 0
    disagreements = []
    for key, cs in groups.items():
        cs = sorted(cs, key=lambda c: c.s)
        full = cs[-1]
        if full.s == 1.0:
            if full.gain_ci_hi < 0 or full.gain_ci_lo > 0:
                sim_deterred = full.gain_ci_hi < 0
                if sim_deterred == full.deterred:
                    agree += 1
                else:
                    disagree += 1
                    disagreements.append(dict(zip(("attack", "p", "k", "BP"), key)))
            else:
                inconclusive += 1     # Δ(1) within simulation error of 0: on the Equation 8 boundary
        # All-or-nothing: no interior s whose gain is significantly above both endpoints.
        if len(cs) >= 3:
            ends = max(cs[0].gain_ci_hi, cs[-1].gain_ci_hi)
            interior_max += any(c.gain_ci_lo > ends for c in cs[1:-1])
    return {
        "prop2_eq4_inside_wilson95": {"n": len(cells), "inside": int(sum(inside)),
                                      "max_abs_diff": max(abs(c.detect_sim - c.detect_closed) for c in cells)},
        "prop3_eq8_at_s1": {"agree": agree, "disagree": disagree, "inconclusive_near_boundary": inconclusive,
                            "disagreements": disagreements[:20]},
        "prop3_interior_maximum_cells": interior_max,
        "n_cells_pk_bp": len(groups),
    }


# ---------------------------------------------------------------- output
def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              cwd=Path(__file__).parent, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def write_outputs(cells: list[Cell], summary: dict, out: Path) -> tuple[Path, Path]:
    out.mkdir(parents=True, exist_ok=True)
    csv_path, json_path = out / "mc_sweep.csv", out / "mc_summary.json"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for c in cells:
            w.writerow(c.row())
    json_path.write_text(json.dumps(summary, indent=1, default=str) + "\n")
    return csv_path, json_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m trajver.montecarlo", description="WP4 Monte Carlo of Propositions 2 and 3")
    ap.add_argument("--params", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seed", type=int, help="override the params seed")
    ap.add_argument("--n-sim", type=int, help="override the params n_sim")
    a = ap.parse_args(argv)

    raw = a.params.read_bytes()
    params = json.loads(raw)
    t0 = time.time()
    cells, summary = run_sweep(params, seed=a.seed, n_sim=a.n_sim)
    summary = {
        "provisional": bool(params.get("provisional", True)),
        "note": params.get("note"),
        "params_file": str(a.params),
        "params_sha256": hashlib.sha256(raw).hexdigest(),
        "git_commit": _git_commit(),
        "numpy": np.__version__,
        "rng": "numpy.random.default_rng (PCG64)",
        "n_rows": len(cells),
        "wall_s": round(time.time() - t0, 2),
        **summary,
        "params": params,
    }
    csv_path, json_path = write_outputs(cells, summary, a.out)
    print(f"{len(cells)} rows -> {csv_path}\nsummary -> {json_path}")
    if summary["attacks_waiting_for_wp3"]:
        print("skipped (r_A or beta_A null, awaiting WP3):", ", ".join(summary["attacks_waiting_for_wp3"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
