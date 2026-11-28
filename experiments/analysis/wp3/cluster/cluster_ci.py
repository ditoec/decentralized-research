"""Clustered uncertainty for the WP3 rejection rates (co-author review, 2026-11-28, point 2).

The experimental unit is the prompt. Each prompt is run with three seeds (jobs p<id>_s0..s2); every honest
test job is generated on each of three rented cards (RTX 3090, RTX 4090, RTX 5090) and checked against one
DGX Spark reference, so the 1,800 honest test jobs are 200 prompts x 3 seeds x 3 cards. The attack runs use
one job set on one card. Jobs of one prompt share the prompt and the reference image, and, pooled over the
cards, the same seed, so they are not independent.

For every cell (thresholds version, set, stratum, evidence level, k) this script reports beside the Wilson
interval of the analysis tables (which treats jobs as independent):
* a cluster bootstrap over prompts (resample whole prompts with replacement, 10,000 draws, seed 20261128),
  95% percentile interval of the rejection rate;
* the design effect deff = Var_cluster / Var_binomial (ratio estimator over prompts), the effective
  sample size n_eff = n / max(deff, 1), and the Wilson interval at n_eff. When no job was rejected the
  variance is zero and deff is undefined; n_eff is then the number of prompts (as if all jobs of a prompt
  were one observation), which is the conservative bound.
Verdicts are exactly those of analysis_wp3 (same frozen thresholds, same E1 patch for v2); nothing is refit.

    TRAJVER_RUNS=experiments/runs code/.venv/bin/python -P experiments/analysis/wp3/cluster/cluster_ci.py
writes cluster_ci.csv and honest_overlap.json (honest rejections: distinct jobs and prompts, and on how many
cards each rejected job was rejected) next to this file.
"""
import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "code"))
os.environ.setdefault("TRAJVER_RUNS", str(ROOT / "experiments" / "runs"))
from trajver.analysis_wp3 import attach_e0, job_verdicts, load_run  # noqa: E402
from trajver.stats import wilson  # noqa: E402
from trajver.thresholds import load as load_thresholds  # noqa: E402

A = ROOT / "experiments" / "analysis" / "wp3"
RUNS = ROOT / "experiments" / "runs"
TH1 = ROOT / "experiments" / "configs" / "thresholds_v1_sdxl_euler.json"
KEEP = {("E0", None), ("E0-N", None), ("E1", None), ("E2-H.tierA", None), ("E2-W", 3)} | {("E2-H", k) for k in (1, 2, 3, 8)}
N_BOOT, SEED = 10_000, 20261128
CARD = {"rtx3090": "RTX 3090", "rtx4090": "RTX 4090", "rtx5090": "RTX 5090"}


def prompt(job: str) -> str:
    return job.split("_")[0]


def card(run_id: str) -> str:
    return next(v for k, v in CARD.items() if k in run_id)


def clustered(verdicts: list[tuple[str, int]], rng) -> dict:
    """verdicts: (prompt, rejected 0/1) per job."""
    g = defaultdict(lambda: [0, 0])
    for p, x in verdicts:
        g[p][0] += x
        g[p][1] += 1
    y = np.array([v[0] for v in g.values()], float)
    m = np.array([v[1] for v in g.values()], float)
    n, C, rej = int(m.sum()), len(m), int(y.sum())
    rate = rej / n
    idx = rng.integers(0, C, size=(N_BOOT, C))
    boot = y[idx].sum(1) / m[idx].sum(1)
    lo_b, hi_b = np.quantile(boot, [0.025, 0.975])
    if 0 < rej < n:
        v_cl = C / (C - 1) * np.sum((y - rate * m) ** 2) / n ** 2  # ratio-estimator variance over clusters
        deff = v_cl / (rate * (1 - rate) / n)
        n_eff = n / max(deff, 1.0)
    else:
        deff, n_eff = float("nan"), float(C)
    lo_w, hi_w = wilson(rej, n)
    lo_e, hi_e = wilson(round(rate * n_eff), round(n_eff)) if rej else wilson(0, C)
    return {"n_jobs": n, "n_prompts": C, "n_rejected": rej, "rate": rate, "wilson_lo": lo_w, "wilson_hi": hi_w,
            "boot_lo": float(lo_b), "boot_hi": float(hi_b), "deff": deff, "n_eff": n_eff,
            "wilson_eff_lo": lo_e, "wilson_eff_hi": hi_e}


def main():
    th = load_thresholds(str(TH1))
    rng = np.random.default_rng(SEED)
    out, overlap = [], []
    for ver in ("v1", "v2"):
        inp = json.loads((A / ver / "inputs.json").read_text())
        base = A / "v2runs" if ver == "v2" else RUNS
        honest = [load_run(base / r) for r in inp["honest"]]
        attacked = [load_run(base / r) for r in inp["attacked"]]
        attach_e0(honest + attacked, str(A / "compare"))
        cells = defaultdict(list)  # (set, stratum, ev, k) -> [(prompt, rejected)]
        failed = defaultdict(lambda: defaultdict(set))  # (ev, k) -> job -> cards that rejected it
        for r in honest:
            jv, _ = job_verdicts(r, th)
            for key, d in jv.items():
                if key not in KEEP:
                    continue
                for job, v in d.items():
                    x = (prompt(job), int(v != "pass"))
                    cells[("honest", card(r.run_id), *key)].append(x)
                    cells[("honest", "pooled", *key)].append(x)
                    if x[1]:
                        failed[key][job].add(card(r.run_id))
        for (ev, k), jobs in failed.items():
            n_cards = [len(c) for c in jobs.values()]
            overlap.append({"thresholds": ver, "evidence": ev, "k": "" if k is None else k,
                            "n_rejections": sum(n_cards), "n_distinct_jobs": len(jobs),
                            "n_distinct_prompts": len({prompt(j) for j in jobs}),
                            "jobs_by_cards_rejecting": {str(i): n_cards.count(i) for i in (1, 2, 3)}})
        for r in attacked:
            jv, _ = job_verdicts(r, th)
            for key, d in jv.items():
                if key in KEEP:
                    cells[(r.attack, "RTX 5090", *key)] += [(prompt(j), int(v != "pass")) for j, v in d.items()]
        for (s, stratum, ev, k), vs in sorted(cells.items(), key=lambda t: tuple(str(x) for x in t[0])):
            ids = inp["honest"] if s == "honest" else [r.run_id for r in attacked if r.attack == s]
            out.append({"thresholds": ver, "set": s, "stratum": stratum, "evidence": ev, "k": "" if k is None else k,
                        **clustered(vs, rng), "run_ids": ";".join(ids)})
    cols = list(out[0].keys())
    with open(Path(__file__).with_name("cluster_ci.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in out:
            w.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()})
    Path(__file__).with_name("honest_overlap.json").write_text(json.dumps(overlap, indent=1) + "\n")
    print(f"{len(out)} rows -> {Path(__file__).with_name('cluster_ci.csv').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
