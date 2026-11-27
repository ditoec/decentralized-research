"""Result figures from the logged analysis outputs (paper/figures/fig_r1_4_steps.png, fig_r2_7_partial.png).

  code/.venv/bin/python paper/tools/figures_results.py

Palette: categorical slots 1-3 of the dataviz reference palette (validated: CVD dE 9.2, normal 27.6; slot 3 is
below 3:1 contrast, so every series also carries a marker shape, a legend and a direct label).
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import results_wp3 as R  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / "paper" / "figures"
C = ["#2a78d6", "#eb6834", "#1baf7a"]
MK = ["o", "s", "^"]
INK, MUTED, GRID = "#0b0b0b", "#6b6a64", "#e4e3de"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "lines.linewidth": 2,
                     "legend.frameon": False, "figure.dpi": 200})


def fig_steps():
    s = R.r1_steps()
    if not s:
        return
    th = json.loads((ROOT / "experiments" / "configs" / "thresholds_v1_sdxl_euler.json").read_text())
    fig, ax = plt.subplots(figsize=(6.5, 3.0))
    names = {"rtx3090|spark3": "RTX 3090 → Spark (L4)", "rtx4090|spark1": "RTX 4090 → Spark (L4)",
             "rtx5090|spark1": "RTX 5090 → Spark (L3)"}
    for i, (pair, v) in enumerate(sorted(s.items())):
        xs = sorted(v["median"])
        ax.plot(xs, [v["median"][x] for x in xs], color=C[i], marker=MK[i], markersize=4,
                label=f"{names.get(pair, pair)}, median of {v['n_jobs']} jobs")
        ax.plot(xs, [v["max"][x] for x in xs], color=C[i], linewidth=1, linestyle=":", alpha=0.9)
    tau = th.get("tau_by_k", {}).get("1") or th.get("tau")
    if isinstance(tau, dict) and "tau" in tau:
        tau = tau["tau"]
    if isinstance(tau, dict):
        tau = [tau[str(i)] for i in sorted(map(int, tau))]
    if isinstance(tau, list):
        ax.plot(range(len(tau)), tau, color=INK, linewidth=1.2, linestyle="--", label="frozen τ_i (k = 1)")
    ax.set_yscale("log")
    ax.set_xlabel("Denoising step i (SDXL, Euler, 30 steps)")
    ax.set_ylabel("Tier B distance, rel. L2 of D_i")
    ax.legend(fontsize=7, loc="upper right")
    ax.text(0.01, 0.03, "solid: median per step; dotted: maximum", transform=ax.transAxes, fontsize=7, color=MUTED)
    fig.tight_layout()
    fig.savefig(OUT / "fig_r1_4_steps.png")
    print("wrote", OUT / "fig_r1_4_steps.png")


def wilson(x, n, z=1.96):
    if n == 0:
        return 0, 0
    p = x / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0, c - h), min(1, c + h)


def fig_partial():
    rows = R.sweep_tiers()
    if not rows:
        return
    from trajver import theory
    ra = R.rates()
    a_s = {k: float(v["rate"]) for k, v in ra.get("honest", {}).items()}
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    grid = [x / 30 for x in range(0, 31)]
    for i, k in enumerate((1, 3, 8)):
        rk = sorted((r for r in rows if r["k"] == k), key=lambda r: r["s"])
        s = [r["s"] for r in rk]
        q = [r["tierb_fail"] / r["n"] for r in rk]
        ci = [wilson(r["tierb_fail"], r["n"]) for r in rk]
        ax.errorbar(s, q, yerr=[[max(0, a - l) for a, (l, _) in zip(q, ci)], [max(0, h - a) for a, (_, h) in zip(q, ci)]],
                    fmt=MK[i], color=C[i], markersize=5, capsize=2, linewidth=1, label=f"measured, k = {k}")
        al = a_s.get(k, 0.0)
        ax.plot(grid, [theory.q_spot_check(30, round(g * 30), k, 1.0, al) for g in grid], color=C[i], linewidth=1.5,
                alpha=0.8, label=f"Eq. 4, m = sT, k = {k}")
        # Eq. 4 with the measured detectable steps of each job (steps over tau), averaged over the jobs of each s
        ax.plot(s, [statistics.mean(theory.q_spot_check(30, m, k, 1.0, 0.0) for m in r["n_over_tau"]) for r in rk],
                color=C[i], linewidth=1, linestyle="--", alpha=0.9)
    ax.set_xlabel("Faked fraction s (F3, solver inversion; DGX Spark, class F)")
    ax.set_ylabel("Jobs failing Tier B (share)")
    ax.set_ylim(-0.02, 1.05)
    ax.legend(fontsize=6.5, loc="lower right", ncol=2)
    fig.tight_layout()
    fig.savefig(OUT / "fig_r2_7_partial.png")
    print("wrote", OUT / "fig_r2_7_partial.png")


if __name__ == "__main__":
    fig_steps()
    fig_partial()
