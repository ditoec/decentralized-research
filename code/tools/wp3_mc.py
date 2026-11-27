#!/usr/bin/env python3
"""WP4 Monte Carlo with the WP3 measurements (runbook §8): builds the params from
experiments/analysis/wp3/v1 (r_A at k = 1, beta_A vs M, honest alpha_s at k = 1) and runs trajver.montecarlo.

  code/.venv/bin/python code/tools/wp3_mc.py

c/P = 1 is a design assumption (stated in the paper), not a measurement; T = 30 as in the SDXL Euler workflow.
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
A = ROOT / "experiments" / "analysis"
rates = list(csv.DictReader(open(A / "wp3" / "v1" / "r2_6_rates.csv")))
beta = {r["attack"]: r for r in csv.DictReader(open(A / "wp3" / "v1" / "r2_4_beta.csv"))}
base = json.loads((ROOT / "experiments" / "configs" / "mc_params_provisional.json").read_text())
alpha = next(float(r["rate"]) for r in rates if r["quantity"] == "honest_alpha_s" and r["k"] == "1")
attacks = []
for r in rates:
    if r["quantity"] != "r_A" or r["k"] != "1" or r["attack"] in ("M", "honest") or r["attack"] not in beta:
        continue
    b = dict(beta[r["attack"]])
    if r["attack"] in ("F1", "F2", "F3") and "paired" not in b.get("time_fields", ""):
        b["beta_median"] = r["s"] or "0.5"  # transform forger (generates honestly first): use the bound beta <= s
    if b["beta_median"] in ("", None):
        continue
    attacks.append({"name": r["attack"],
                    "r_A": {"value": float(r["rate"]), "provisional": False, "source": "WP3 r2_6_rates.csv, k = 1: " + r["run_ids"][:120]},
                    "beta_A": {"value": max(0.0, float(b["beta_median"])), "provisional": False,
                               "source": "WP3 r2_4_beta.csv, " + (b.get("time_fields") or "") + " (negative medians floored at 0: no saving)"}})
p = dict(base)
p.update(provisional=False, note="WP4 params from the WP3 measurements (experiments/analysis/wp3/v1); c/P = 1 is a design assumption.",
         alpha_s={"value": alpha, "provisional": False, "source": "WP3 honest alpha_s, k = 1, 1,800 test jobs"},
         c={"value": 1.0, "provisional": False, "source": "design assumption c/P = 1 (payment just covers the honest cost)"},
         attacks=attacks)
out = A / "wp4"
out.mkdir(parents=True, exist_ok=True)
(out / "mc_params_wp3.json").write_text(json.dumps(p, indent=1) + "\n")
sys.exit(subprocess.call([str(ROOT / "code" / ".venv" / "bin" / "python"), "-m", "trajver.montecarlo",
                          "--params", str(out / "mc_params_wp3.json"), "--out", str(out)], cwd=ROOT / "code"))
