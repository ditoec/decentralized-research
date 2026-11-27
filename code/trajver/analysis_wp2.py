"""WP2 analysis: hardware pairs by level and the figure data of runbook §8b (R1.4, R1.5).

  python -m trajver.analysis_wp2 pairs   RUNS_DIR --out pairs.csv
  python -m trajver.analysis_wp2 levels  RUNS_DIR --out fig_r1_5_levels.csv [--compare DIR] [--partial]
  python -m trajver.analysis_wp2 steps   RUNS_DIR --out fig_r1_4_steps.csv [--thresholds thresholds_v1.json] [--partial]

Works on run METADATA (manifest.json, jobs.jsonl), so it runs anywhere the sanitized run folders are.

* ``pairs``: every pair of WP2 runs with the same model and config (or, for L1, the same node and a
  config one factor away from the reference), labelled with its level (design doc 05 §3):
  L0 same unit repeated; L1 same unit, different software config; L2 different units of the same GPU
  model; L3 Spark vs RTX 5090 (same generation, different chip and CPU ISA); L4 different generations.
* ``levels``: fig_r1_5_levels.csv. ``pixel_equal`` (the share of common jobs whose PNG sha256 match)
  comes from jobs.jsonl; ``lpips``, ``dinov2`` and ``step_d_rel_l2`` come from ``pilot compare
  --steps-detail --e0-out`` outputs in ``--compare DIR`` (``<run_a>__<run_b>.json`` and
  ``<run_a>__<run_b>.e0.jsonl``), which need the raw data and run on the nodes.
* ``steps``: fig_r1_4_steps.csv from verifier replay runs (``pilot replay``): the per-step Tier B
  distance between the provider's committed D_i and the Spark verifier's replayed D̂_i, one row per
  job and step. ``tau_step`` is filled only from a frozen thresholds file.

Excluded on purpose (each with its reason in EXCLUDE): test-split runs, which are not scored before
the attack study (runbook §4 item 2, §6); the WP2 dry-run runs (finding 18).
Every row carries the run ids it came from. With ``--partial`` every row is marked partial=1: the data
are incomplete while the grid and the pulls run, and nothing marked partial goes into the paper.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path

NAME = re.compile(r"^(?P<date>\d{8})-wp2-(?P<kind>ref|grid|l2|prec|slice)(?:-(?P<split>caldev|test))?-"
                  r"(?P<model>sd15|sdxl)-(?P<prec>fp16|bf16|fp32)-(?P<attn>sdpa|split|quad|xformers)-"
                  r"(?P<sampler>euler|dpmpp_2m)-(?P<det>det|nd)-(?P<node>spark\d|rtx\d{4}b?)-(?P<rep>\d{2})$")
REF = ("fp16", "sdpa", "nd")


def EXCLUDE(name: str, r: dict) -> str | None:
    if r["split"] == "test":
        return "test split: not scored before §6"
    if r["node"] == "spark4" and r["date"] == "20261125":
        return "Spark-4 WP2 dry run (finding 18)"
    if r["node"] == "rtx4090" and r["rep"] == "01":
        return "RTX 4090 WP2 dry run (finding 18)"
    return None


def gpu_model(node: str) -> str:
    return "spark" if node.startswith("spark") else node.rstrip("b")


GEN = {"spark": "blackwell", "rtx5090": "blackwell", "rtx4090": "ada", "rtx3090": "ampere"}


@dataclass(frozen=True)
class Run:
    run_id: str
    path: Path
    model: str
    prec: str
    attn: str
    sampler: str
    det: str
    node: str
    rep: str
    kind: str

    @property
    def config(self):
        return (self.prec, self.attn, self.sampler, self.det)


def load_runs(runs_dir: Path, verbose=False) -> list[Run]:
    out = []
    for d in sorted(Path(runs_dir).iterdir()):
        m = NAME.match(d.name)
        if not m or not (d / "jobs.jsonl").exists() or not (d / "summary.json").exists():
            continue
        r = m.groupdict()
        why = EXCLUDE(d.name, r)
        if why:
            if verbose:
                print(f"skip {d.name}: {why}")
            continue
        out.append(Run(d.name, d, r["model"], r["prec"], r["attn"], r["sampler"], r["det"], r["node"], r["rep"],
                       r["kind"]))
    return out


def level(a: Run, b: Run) -> str | None:
    """Level of a pair, or None if the pair is not one the design compares."""
    if a.model != b.model:
        return None
    ga, gb = gpu_model(a.node), gpu_model(b.node)
    if a.node == b.node:
        if a.config == b.config:
            return "L0" if a.rep != b.rep else None
        if a.sampler != b.sampler or a.rep != b.rep:
            return None
        # L1: one of the pair is the reference config, the other differs in exactly one factor
        fa, fb = (a.prec, a.attn, a.det), (b.prec, b.attn, b.det)
        if REF not in (fa, fb) or sum(x != y for x, y in zip(fa, fb)) != 1:
            return None
        return "L1"
    if a.config != b.config:
        return None
    if ga == gb:
        return "L2"
    if GEN[ga] == GEN[gb]:
        return "L3"
    return "L4"


def factor(a: Run, b: Run) -> str:
    return next(n for n, x, y in zip(("precision", "attention", "deterministic"), (a.prec, a.attn, a.det),
                                     (b.prec, b.attn, b.det)) if x != y) if a.config != b.config else ""


def pairs(runs: list[Run]):
    for a, b in itertools.combinations(runs, 2):
        lv = level(a, b)
        if lv:
            a, b = sorted((a, b), key=lambda r: r.run_id)
            yield lv, a, b


def rows(path: Path) -> dict:
    return {r["job"]: r for r in (json.loads(l) for l in (path / "jobs.jsonl").read_text().splitlines() if l.strip())}


def hw_pair(a: Run, b: Run) -> str:
    return "|".join(sorted((a.node, b.node))) if a.node != b.node else a.node


def write(path, header, data, partial):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header + (["partial"] if partial else []))
        for r in data:
            w.writerow(list(r) + ([1] if partial else []))


def cmd_pairs(a):
    runs = load_runs(Path(a.runs), verbose=a.verbose)
    out = []
    for lv, x, y in pairs(runs):
        n = len(set(rows(x.path)) & set(rows(y.path)))
        if n:
            out.append((lv, hw_pair(x, y), x.model, x.sampler, x.prec if x.prec == y.prec else f"{x.prec}/{y.prec}",
                        factor(x, y), n, x.run_id, y.run_id))
    write(a.out, ["level", "hw_pair", "model", "sampler", "precision", "factor", "n_common_jobs", "run_a", "run_b"],
          out, a.partial)
    print(f"{len(out)} pairs from {len(runs)} runs -> {a.out}")


def cmd_levels(a):
    runs = load_runs(Path(a.runs))
    out = []
    for lv, x, y in pairs(runs):
        A, B = rows(x.path), rows(y.path)
        common = sorted(set(A) & set(B))
        if not common:
            continue
        prec = x.prec if x.prec == y.prec else f"{x.prec}/{y.prec}"
        base = (lv, hw_pair(x, y), x.model, x.sampler, prec, factor(x, y))
        eq = sum(A[k]["image_sha256"] == B[k]["image_sha256"] for k in common) / len(common)
        out.append(base + ("pixel_equal", eq, len(common), x.run_id, y.run_id))
        if a.compare:
            stem = Path(a.compare) / f"{x.run_id}__{y.run_id}"
            if stem.with_suffix(".e0.jsonl").exists():
                e0 = [json.loads(l) for l in stem.with_suffix(".e0.jsonl").read_text().splitlines() if l.strip()]
                for key, metric in (("lpips", "lpips"), ("dino_cosine", "dinov2")):
                    v = [r[key] for r in e0 if r.get(key) is not None]
                    if v:
                        out.append(base + (metric, statistics.median(v), len(v), x.run_id, y.run_id))
            if stem.with_suffix(".json").exists():
                s = json.loads(stem.with_suffix(".json").read_text())
                for i, v in sorted(s.get("per_step_D", {}).items(), key=lambda t: int(t[0])):
                    out.append(base + (f"step_d_rel_l2@{i}", v["rel_l2_median"], s["n_pairs"], x.run_id, y.run_id))
    write(a.out, ["level", "hw_pair", "model", "sampler", "precision", "factor", "metric", "value", "n", "run_a",
                  "run_b"],
          out, a.partial)
    print(f"{len(out)} rows -> {a.out}")


REPLAY = re.compile(r"^\d{8}-wp2-replay-(?:cal-)?(?P<model>sd15|sdxl)-(?P<sampler>euler|dpmpp_2m)-"
                    r"(?P<prov>rtx\d{4}b?)(?:-\d{2})?on-(?P<ver>spark\d)-\d{2}$")


def cmd_steps(a):
    tau = {}
    if a.thresholds:
        th = json.loads(Path(a.thresholds).read_text())
        tau = {int(i): v for i, v in th.get("tier_b", {}).get("tau_by_step", {}).items()}
    out = []
    for d in sorted(Path(a.runs).iterdir()):
        m = REPLAY.match(d.name)
        if not m or not (d / "jobs.jsonl").exists():
            continue
        pm = json.loads((d / "manifest.json").read_text())
        if pm.get("provider_run", "").endswith("rtx4090-01"):
            continue  # the provider is a WP2 dry-run run (finding 18)
        hp = f"{m['prov']}|{m['ver']}"
        for r in rows(d).values():
            for i, s in enumerate(r["tier_b"]):
                out.append((hp, m["model"], m["sampler"], i, s[a.metric], tau.get(i, ""), r["job"], d.name,
                            pm.get("provider_run", "")))
    write(a.out, ["hw_pair", "model", "sampler", "step", "d_value", "tau_step", "job", "run_id", "provider_run_id"],
          out, a.partial)
    print(f"{len(out)} rows -> {a.out}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("pairs", "levels", "steps"):
        p = sub.add_parser(n)
        p.add_argument("runs")
        p.add_argument("--out", required=True)
        p.add_argument("--partial", action="store_true")
    sub.choices["pairs"].add_argument("--verbose", action="store_true")
    sub.choices["levels"].add_argument("--compare", default=None)
    sub.choices["steps"].add_argument("--thresholds", default=None)
    sub.choices["steps"].add_argument("--metric", default="rel_l2", choices=["rel_l2", "max_abs", "cos_dist"])
    a = ap.parse_args(argv)
    {"pairs": cmd_pairs, "levels": cmd_levels, "steps": cmd_steps}[a.cmd](a)


if __name__ == "__main__":
    main()
