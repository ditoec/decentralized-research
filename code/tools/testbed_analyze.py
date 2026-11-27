#!/usr/bin/env python3
"""Testbed demo analysis (runbook §7 item 5): realized gain of each injected attacker against the honest
provider, from the on-chain outcomes, beside Equation 7's prediction from the measured rates.

    code/.venv/bin/python code/tools/testbed_analyze.py experiments/runs/<rid>

Per job, in units of the payment P (c/P = 1, the paper's conservative cost ratio; B/P from the run):
    payoff = P·paid − B·slashed − c·(1 − β_A)        (β_A = 0 for the honest provider)
"paid" means the job closed paid (unsampled, or sampled and passed); "slashed" a confirmed fail. The
realized gain Δ of an attacker at a sampling rate p is its mean payoff minus the honest provider's
mean payoff over the same jobs; the 95% interval is a bootstrap over jobs (10,000 resamples, seed 0).
The prediction is Equation 7 with the WP3 measurements: Δ = β_A c − p·(q − α(k))·(P + B), where q is
1 − (1 − r_A)^k for a whole-job attack and Equation 4's q(s, k) for the partial forger.

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
sys.path.insert(0, str(ROOT / "code"))
from trajver import theory  # noqa: E402

A = ROOT / "experiments" / "analysis" / "wp3" / "v1"
KEY = {"A3-Turbo": "A3-Turbo", "F2": "F2"}  # label -> attack key in the WP3 tables
S = {"A3-Turbo": None, "F2": 0.5}


def wp3(k: int):
    rates = list(csv.DictReader(open(A / "r2_6_rates.csv")))
    beta = {r["attack"]: float(r["beta_median"]) for r in csv.DictReader(open(A / "r2_4_beta.csv")) if r["beta_median"]}
    # per-step rates at the run's k (each k has its own frozen tau_i)
    r_a = {r["attack"]: float(r["rate"]) for r in rates if r["quantity"] == "r_A" and r["k"] == str(k)}
    alpha_s = next(float(r["rate"]) for r in rates if r["quantity"] == "honest_alpha_s" and r["k"] == str(k))
    return beta, r_a, alpha_s


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
    beta, r_a, alpha_s = wp3(k)
    a_job = theory.alpha_job(alpha_s, k)

    def payoff(r: dict, b: float) -> float:
        paid = r.get("state") == "closedPaid"
        slashed = r.get("outcome") == "fail"
        return (P * paid - B * slashed - c * (1 - b)) / P

    cells, summary = [], {"run_id": run.name, "k": k, "B_over_P": B / P, "c_over_P": 1.0, "alpha_s": alpha_s, "cells": []}
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
            r = r_a[KEY[v["label"]]]
            q = 1 - (1 - r) ** k if S[v["label"]] is None else theory.q_spot_check(30, round(S[v["label"]] * 30), k, r, alpha_s)
            pred = b * c / P - p * (q - a_job) * (P + B) / P
            oc_a, oc_h = Counter(r["outcome"] for r in att), Counter(r["outcome"] for r in hon)
            row = {"attack": v["label"], "provider": prov, "p": p, "k": k, "bond_ratio": B / P, "n_attacker": len(att),
                   "n_honest": len(hon), "delta_mean": round(d, 4), "delta_ci_lo": round(lo, 4), "delta_ci_hi": round(hi, 4),
                   "delta_eq7": round(pred, 4), "beta_A": round(b, 4), "q": round(q, 4),
                   "outcomes_attacker": dict(oc_a), "outcomes_honest": dict(oc_h), "source": "testbed", "run_id": run.name}
            cells.append(row)
            summary["cells"].append(row)
    out = ROOT / "experiments" / "analysis" / "wp5" / "testbed"
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    with open(out / "cells.csv", "w", newline="") as f:
        cols = ["attack", "provider", "p", "k", "bond_ratio", "n_attacker", "n_honest", "delta_mean", "delta_ci_lo",
                "delta_ci_hi", "delta_eq7", "beta_A", "q", "source", "run_id"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(cells)
    for r in cells:
        print(f"{r['attack']:9s} p={r['p']:<5} Δ={r['delta_mean']:+.3f} ({r['delta_ci_lo']:+.3f}, {r['delta_ci_hi']:+.3f})"
              f"  Eq.7 {r['delta_eq7']:+.3f}  attacker {r['outcomes_attacker']}  honest {r['outcomes_honest']}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
