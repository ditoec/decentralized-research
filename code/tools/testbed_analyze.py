#!/usr/bin/env python3
"""Testbed demo analysis (runbook §7 item 5): realized gain of each injected attacker against the honest
provider, from the on-chain outcomes, beside Equation 7's prediction from the measured rates.

    code/.venv/bin/python code/tools/testbed_analyze.py experiments/runs/<rid>

Per job, in units of the payment P (c/P = 1, the paper's conservative cost ratio; B/P from the run):
    payoff = P·paid − B·slashed − c·(1 − β_A)        (β_A = 0 for the honest provider)
"paid" means the job closed paid (unsampled, or sampled and passed); "slashed" a confirmed fail. The
realized gain Δ of an attacker at a sampling rate p is its mean payoff minus the honest provider's
mean payoff over the same jobs; the 95% interval is a bootstrap over jobs (10,000 resamples, seed 0).
The prediction is Equation 7, Δ = β c − p·(q − α(k))·(P + B), with the job-level rates the attack study measured
at the testbed's own configuration (the run's threshold version, E2-H, the run's k): q is the attack's measured
rejection rate on the same 100 jobs, α(k) the honest rejection rate on the RTX 5090 test jobs (the provider the
recorded outputs come from), and β the measured share of the job's GPU time the attack saves (for a forger this
is β_A·s in the paper's notation). p* is Equation 9 for that attack alone: β c / ((q − α(k))(P + B)).

Writes experiments/analysis/wp5/testbed/{summary.json, cells.csv} (every row with its run id).
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

KEY = {"A3-Turbo": "A3-Turbo", "F2": "F2"}  # label -> attack key in the WP3 tables
STRATUM = "rtx5090->spark"  # the recorded provider outputs are the rented RTX 5090's


def wp3(version: str, k: int):
    """Job-level rates at E2-H and the run's k, from the WP3 tables of the run's threshold version."""
    a = ROOT / "experiments" / "analysis" / "wp3" / version
    beta = {r["attack"]: float(r["beta_median"]) for r in csv.DictReader(open(a / "r2_4_beta.csv")) if r["beta_median"]}
    q = {r["attack"]: float(r["q"]) for r in csv.DictReader(open(a / "r2_3_sensitivity.csv"))
         if r["evidence"] == "E2-H" and r["k"] == str(k)}
    alpha = next(float(r["fpr"]) for r in csv.DictReader(open(a / "honest_fpr.csv"))
                 if r["stratum"] == STRATUM and r["evidence"] == "E2-H" and r["k"] == str(k))
    return beta, q, alpha


def boot(diff_a: list[float], diff_h: list[float], n=10_000, seed=0) -> tuple[float, float]:
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        a = [rnd.choice(diff_a) for _ in diff_a]
        h = [rnd.choice(diff_h) for _ in diff_h]
        out.append(sum(a) / len(a) - sum(h) / len(h))
    out.sort()
    return out[int(0.025 * n)], out[int(0.975 * n) - 1]


def main(run: Path):
    m = json.loads((run / "manifest.json").read_text())
    lab = json.loads((run / "labels.json").read_text())["providers"]
    rows = [json.loads(l) for l in (run / "jobs.jsonl").read_text().splitlines() if l.strip()]
    P, B, k = m["payment"], m["bond"], m["k"]
    c = P  # c/P = 1
    version = m["thresholds"].split("_")[1]  # thresholds_v1_sdxl_euler.json -> v1
    beta, qs, a_job = wp3(version, k)

    def payoff(r: dict, b: float) -> float:
        paid = r.get("state") == "closedPaid"
        slashed = r.get("outcome") == "fail"
        return (P * paid - B * slashed - c * (1 - b)) / P

    cells, summary = [], {"run_id": run.name, "k": k, "B_over_P": B / P, "c_over_P": 1.0, "thresholds": version,
                      "alpha_k": a_job, "alpha_source": f"honest_fpr.csv, {STRATUM}, E2-H, k = {k}", "cells": []}
    for p in m["p"]:
        hon_prov = next(n for n, v in lab.items() if v["label"] == "honest")
        hon = [r for r in rows if r["p"] == p and r["provider"] == hon_prov]
        ph = [payoff(r, 0.0) for r in hon]
        for prov, v in lab.items():
            if v["label"] == "honest":
                continue
            att = [r for r in rows if r["p"] == p and r["provider"] == prov]
            if not att or not hon:
                continue
            b = beta[KEY[v["label"]]]
            pa = [payoff(r, b) for r in att]
            d = sum(pa) / len(pa) - sum(ph) / len(ph)
            lo, hi = boot(pa, ph)
            q = qs[KEY[v["label"]]]
            pred = b * c / P - p * (q - a_job) * (P + B) / P
            pstar = b * c / ((q - a_job) * (P + B)) if q > a_job else float("inf")
            n_s = sum(r["outcome"] in ("pass", "fail", "unresolved") for r in att)
            oc_a, oc_h = Counter(r["outcome"] for r in att), Counter(r["outcome"] for r in hon)
            row = {"attack": v["label"], "provider": prov, "p": p, "k": k, "bond_ratio": B / P, "n_attacker": len(att),
                   "n_honest": len(hon), "delta_mean": round(d, 4), "delta_ci_lo": round(lo, 4), "delta_ci_hi": round(hi, 4),
                   "delta_eq7": round(pred, 4), "beta_A": round(b, 4), "q": round(q, 4),
                   "alpha_k": round(a_job, 4), "p_star": round(pstar, 4), "n_sampled_attacker": n_s,
                   "outcomes_attacker": dict(oc_a), "outcomes_honest": dict(oc_h), "source": "testbed", "run_id": run.name}
            cells.append(row)
            summary["cells"].append(row)
    out = ROOT / "experiments" / "analysis" / "wp5" / "testbed"
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    with open(out / "cells.csv", "w", newline="") as f:
        cols = ["attack", "provider", "p", "k", "bond_ratio", "n_attacker", "n_honest", "delta_mean", "delta_ci_lo",
                "delta_ci_hi", "delta_eq7", "beta_A", "q", "alpha_k", "p_star", "n_sampled_attacker", "source", "run_id"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(cells)
    for r in cells:
        print(f"{r['attack']:9s} p={r['p']:<5} Δ={r['delta_mean']:+.3f} ({r['delta_ci_lo']:+.3f}, {r['delta_ci_hi']:+.3f})"
              f"  Eq.7 {r['delta_eq7']:+.3f}  attacker {r['outcomes_attacker']}  honest {r['outcomes_honest']}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
