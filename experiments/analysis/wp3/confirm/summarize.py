"""Confirmatory run (docs/16-confirmatory-run.md, pre-registered 2026-11-28, commit 6aa4746): primary endpoint,
pre-registered criterion and secondary rates, from the verify runs of the confirmatory jobs.

    TRAJVER_RUNS=experiments/runs code/.venv/bin/python -P experiments/analysis/wp3/confirm/summarize.py \
        --v1 <verify run dir>... --v2 <E1-patched verify run dir>... --compare <dir of *.e0.jsonl>

Verdicts as in analysis_wp3 (frozen thresholds v1; v2 = the same rows with E1 patched by trajver.e1img), clustered
intervals as in ../cluster/cluster_ci.py (cluster bootstrap over prompts, 10,000 draws, seed 20261128; Wilson at
the number of prompts when no job or every job is rejected). Writes cluster_ci.csv and summary.json here.
Primary endpoint: E2-H at k = 1 under v2, pooled over the cards that ran. Confirmed if the rate is at most 2.0% and
the upper bound of its 95% clustered interval at most 3.0%.
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "code"))
sys.path.insert(0, str(HERE.parent / "cluster"))
os.environ.setdefault("TRAJVER_RUNS", str(ROOT / "experiments" / "runs"))
from cluster_ci import KEEP, SEED, card, clustered, prompt  # noqa: E402
from trajver.analysis_wp3 import attach_e0, job_verdicts, load_run  # noqa: E402
from trajver.thresholds import load as load_thresholds  # noqa: E402

TH1 = ROOT / "experiments" / "configs" / "thresholds_v1_sdxl_euler.json"
MAX_RATE, MAX_UPPER = 0.020, 0.030  # docs/16, fixed before any job
EXPLORATORY = {"rate": 22 / 1800, "n": 1800}  # test split, v2 (experiments/analysis/wp3/v2/honest_fpr.csv)


def upper(r: dict) -> float:
    return r["boot_hi"] if 0 < r["n_rejected"] < r["n_jobs"] else r["wilson_eff_hi"]


def lower(r: dict) -> float:
    return r["boot_lo"] if 0 < r["n_rejected"] < r["n_jobs"] else r["wilson_eff_lo"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v1", nargs="+", required=True)
    ap.add_argument("--v2", nargs="+", required=True)
    ap.add_argument("--compare", required=True)
    a = ap.parse_args()
    th = load_thresholds(str(TH1))
    rng = np.random.default_rng(SEED)
    out, ids = [], []
    for ver, dirs in (("v1", a.v1), ("v2", a.v2)):
        runs = [load_run(Path(d)) for d in dirs]
        bad = [r.run_id for r in runs if r.th_sha != th["_sha256"]]
        if bad:
            raise SystemExit(f"not verified with thresholds v1: {bad}")
        attach_e0(runs, a.compare)
        ids += [r.run_id for r in runs]
        cells = defaultdict(list)
        for r in runs:
            jv, _ = job_verdicts(r, th)
            for key, d in jv.items():
                if key in KEEP:
                    for job, v in d.items():
                        x = (prompt(job), int(v != "pass"))
                        cells[(card(r.run_id), *key)].append(x)
                        cells[("pooled", *key)].append(x)
        for (stratum, ev, k), vs in sorted(cells.items(), key=lambda t: tuple(str(x) for x in t[0])):
            out.append({"thresholds": ver, "stratum": stratum, "evidence": ev, "k": "" if k is None else k,
                        **clustered(vs, rng), "run_ids": ";".join(r.run_id for r in runs)})
    with open(HERE / "cluster_ci.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows({k: round(v, 6) if isinstance(v, float) else v for k, v in r.items()} for r in out)
    cell = {(r["thresholds"], r["stratum"], r["evidence"], str(r["k"])): r for r in out}
    p = cell[("v2", "pooled", "E2-H", "1")]
    ok = p["rate"] <= MAX_RATE and upper(p) <= MAX_UPPER
    cards = sorted({r["stratum"] for r in out if r["stratum"] != "pooled"})
    e0 = cell.get(("v1", "pooled", "E0", ""))
    pc = lambda x: f"{100 * x:.1f}"  # noqa: E731
    sent = (f"The confirmatory run used {p['n_jobs']:,} honest jobs ({p['n_prompts']} untouched test prompts × 3 seeds) "
            f"generated on a newly rented {', '.join(cards[:-1]) + ' and ' + cards[-1] if len(cards) > 1 else cards[0]}: E2-H with one checked step rejected {pc(p['rate'])}% of "
            f"them under v2 ({p['n_rejected']} jobs; 95% interval {pc(lower(p))}–{pc(upper(p))}%, clustered by prompt), "
            f"against {pc(EXPLORATORY['rate'])}% on the test split, so the pre-registered criterion (at most 2.0%, upper "
            f"bound at most 3.0%) was {'met' if ok else 'not met'}")
    if e0:
        sent += f"; E0 rejected {pc(e0['rate'])}%"
    sent += "."
    summary = {"docs": "docs/16-confirmatory-run.md", "criterion": {"max_rate": MAX_RATE, "max_upper": MAX_UPPER},
               "primary": {k: p[k] for k in ("n_jobs", "n_prompts", "n_rejected", "rate")} | {"lo": lower(p), "hi": upper(p)},
               "confirmed": ok, "cards": cards, "exploratory_test_split": EXPLORATORY, "sentence": sent,
               "run_ids": sorted(set(ids))}
    (HERE / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
