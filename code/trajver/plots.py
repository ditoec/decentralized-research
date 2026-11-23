"""Figures from run folders, for the pilot report, the paper and the thesis.

  python -m trajver.plots throughput RUN [RUN ...] --out fig.png      # P3: s/image per node (box)
  python -m trajver.plots w1 RUN [RUN ...] --out fig.png              # P5: adjacent cosine per step
  python -m trajver.plots e2w RUN --out fig.png                       # P5: E2-W acceptance of F1-F3
  python -m trajver.plots stepdist COMPARE.json [...] --out fig.png   # P2: per-step D_i distance
  python -m trajver.plots memory RUN [RUN ...] --out fig.png          # P7: peak memory per config
  python -m trajver.plots tierb REPLAY_RUN [...] --out fig.png        # honest Tier B distance per step

Every figure is written as PNG (300 dpi) and PDF, and the numbers behind it as CSV next to it,
so the paper can redraw it. The plotted values come only from the run folders.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.dpi": 150, "savefig.bbox": "tight"})
PALETTE = ["#2f6db3", "#d9822b", "#3a9a5b", "#b8423c", "#7a5ba6", "#8c6d46", "#c55ca8", "#6b6b6b"]


def _rows(run: Path) -> list[dict]:
    return [json.loads(l) for l in (run / "jobs.jsonl").read_text().splitlines() if l.strip()]


def _label(run: Path) -> str:
    m = json.loads((run / "manifest.json").read_text())
    n = m.get("node", {})
    gpu = n.get("gpu_name", "?").replace("NVIDIA ", "").replace("GeForce ", "")
    flags = " ".join(m.get("cli_flags") or [])
    return f"{gpu}" + (f"\n{flags}" if flags else "")


def _save(fig, out: str, header: list[str], table: list[list]) -> None:
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p.with_suffix(".png"), dpi=300)
    fig.savefig(p.with_suffix(".pdf"))
    with open(p.with_suffix(".csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(table)
    print("wrote", p.with_suffix(".png"))


def throughput(runs: list[Path], out: str):
    fig, ax = plt.subplots(figsize=(max(3.2, 1.1 * len(runs)), 2.8))
    data, labels, table = [], [], []
    for r in runs:
        t = [x["t_total_s"] for x in _rows(r)][1:]  # drop the warm-up job
        data.append(t)
        labels.append(_label(r))
        table.append([r.name, len(t), statistics.median(t), sorted(t)[int(0.95 * (len(t) - 1))]])
    bp = ax.boxplot(data, patch_artist=True, widths=0.55)
    for i, b in enumerate(bp["boxes"]):
        b.set_facecolor(PALETTE[i % len(PALETTE)] + "55")
    ax.set_xticks(range(1, len(labels) + 1), labels, fontsize=7)
    ax.set_ylabel("seconds per image (warm)")
    _save(fig, out, ["run", "n", "median_s", "p95_s"], table)


def w1(runs: list[Path], out: str):
    fig, ax = plt.subplots(figsize=(4.2, 2.8))
    table = []
    for k, r in enumerate(runs):
        s = json.loads((r / "summary.json").read_text())["adjacent_cosine"]["per_step"]
        steps = sorted(int(i) for i in s)
        lo = [s[str(i)]["min"] for i in steps]
        med = [s[str(i)]["median"] for i in steps]
        c = PALETTE[k % len(PALETTE)]
        ax.plot(steps, med, color=c, label=_label(r).split("\n")[0])
        ax.fill_between(steps, lo, [s[str(i)]["max"] for i in steps], color=c, alpha=0.2, lw=0)
        table += [[r.name, i, s[str(i)]["min"], s[str(i)]["median"], s[str(i)]["max"]] for i in steps]
    ax.axhline(0.70, color="#b8423c", ls="--", lw=1)
    ax.text(0.3, 0.705, "SN30 frame-copy pass line (cos 0.70)", color="#b8423c", fontsize=7, va="bottom")
    ax.set_xlabel("step i")
    ax.set_ylabel(r"cos($x_i$, $x_{i+1}$)")
    ax.legend(frameon=False, fontsize=7)
    _save(fig, out, ["run", "step", "min", "median", "max"], table)


def e2w(run: Path, out: str):
    acc = json.loads((run / "summary.json").read_text())["e2w_acceptance"]
    names = list(acc)
    rates = [acc[n]["accepted"] / acc[n]["n"] for n in names]
    fig, ax = plt.subplots(figsize=(max(3.5, 0.45 * len(names)), 2.6))
    cols = [PALETTE[2] if n == "honest" else PALETTE[3] for n in names]
    ax.bar(range(len(names)), rates, color=cols)
    ax.set_xticks(range(len(names)), [n.replace("@s=", "\ns=") for n in names], fontsize=7)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("accepted by E2-W (SN30 rule)")
    _save(fig, out, ["case", "n", "accepted", "rate", "min_score"],
          [[n, acc[n]["n"], acc[n]["accepted"], r, acc[n]["min_score"]] for n, r in zip(names, rates)])


def stepdist(files: list[Path], out: str):
    fig, ax = plt.subplots(figsize=(4.2, 2.8))
    table = []
    for k, f in enumerate(files):
        s = json.loads(f.read_text())
        per = s.get("per_step_D") or {}
        if not per:
            continue
        steps = sorted(int(i) for i in per)
        ax.semilogy(steps, [max(per[str(i)]["rel_l2_median"], 1e-12) for i in steps], color=PALETTE[k % 8],
                    label=f"{s['run_a'].split('-wp0b-')[-1]} vs {s['run_b'].split('-wp0b-')[-1]}")
        table += [[f.name, i, per[str(i)]["rel_l2_median"], per[str(i)]["rel_l2_max"]] for i in steps]
    ax.set_xlabel("step i")
    ax.set_ylabel(r"rel. L2 of $D_i$ between runs (median)")
    ax.legend(frameon=False, fontsize=6)
    _save(fig, out, ["compare", "step", "rel_l2_median", "rel_l2_max"], table)


def memory(runs: list[Path], out: str):
    labels, peak, rss, table = [], [], [], []
    for r in runs:
        s = json.loads((r / "summary.json").read_text())["memory"]
        m = json.loads((r / "manifest.json").read_text())
        lab = r.name.split("-wp0b-")[-1].rsplit("-", 1)[0]
        labels.append(lab)
        peak.append(s.get("torch_peak_allocated_gb") or 0)
        rss.append(s.get("process_peak_rss_gb") or 0)
        table.append([r.name, " ".join(m.get("cli_flags") or []), peak[-1], rss[-1], s.get("host_min_available_gb")])
    fig, ax = plt.subplots(figsize=(max(3.5, 0.6 * len(runs)), 2.8))
    x = range(len(runs))
    ax.bar([i - 0.2 for i in x], peak, 0.4, label="GPU tensors (peak)", color=PALETTE[0])
    ax.bar([i + 0.2 for i in x], rss, 0.4, label="process RSS (peak)", color=PALETTE[1])
    ax.set_xticks(list(x), labels, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("GB")
    ax.legend(frameon=False, fontsize=7)
    _save(fig, out, ["run", "flags", "torch_peak_gb", "rss_peak_gb", "host_min_available_gb"], table)


def tierb(runs: list[Path], out: str):
    fig, ax = plt.subplots(figsize=(4.2, 2.8))
    table = []
    for k, r in enumerate(runs):
        rows = _rows(r)
        T = min(len(x["tier_b"]) for x in rows)
        med = [statistics.median(x["tier_b"][i]["rel_l2"] for x in rows) for i in range(T)]
        hi = [max(x["tier_b"][i]["rel_l2"] for x in rows) for i in range(T)]
        ax.semilogy(range(T), [max(v, 1e-12) for v in med], color=PALETTE[k % 8], label=r.name.split("-wp")[-1])
        ax.semilogy(range(T), [max(v, 1e-12) for v in hi], color=PALETTE[k % 8], ls=":", lw=0.8)
        table += [[r.name, i, med[i], hi[i]] for i in range(T)]
    ax.set_xlabel("step i")
    ax.set_ylabel(r"honest rel. L2($\hat D_i$, $D_i$)")
    ax.legend(frameon=False, fontsize=6)
    _save(fig, out, ["run", "step", "median", "max"], table)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["throughput", "w1", "e2w", "stepdist", "memory", "tierb"])
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    ins = [Path(x) for x in a.inputs]
    {"throughput": lambda: throughput(ins, a.out), "w1": lambda: w1(ins, a.out), "e2w": lambda: e2w(ins[0], a.out),
     "stepdist": lambda: stepdist(ins, a.out), "memory": lambda: memory(ins, a.out),
     "tierb": lambda: tierb(ins, a.out)}[a.kind]()


if __name__ == "__main__":
    main()
