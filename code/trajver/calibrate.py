"""Calibration and freezing (runbook §5). Calibration split only; no attack data.

  python -m trajver.calibrate --replay RUN [RUN ...] --e0 E0SCORES.jsonl [...] --p1 NOISECMP.json [...] \
      --metric rel_l2 --levels L3,L4 --out experiments/configs/thresholds_v1.json

Inputs
* ``--replay``: verifier replay runs (``python -m trajver.pilot replay``) of honest provider
  trajectories, one per hardware pair. Rows whose prompt is not in prompts_cal.txt are refused.
* ``--e0``: JSONL rows ``{"prompt_id", "pixel_equal", "lpips", "dino_cosine"}`` for honest
  cross-node image pairs (``python -m trajver.pilot e0scores``).
* ``--p1``: outputs of ``pilot noisecmp`` between CPU/PyTorch builds. They do not set the x_0
  tolerance, which is the build-agnostic protocol constant ``rules.e1.X0_TOL``; they check it: if
  2x the largest observed difference exceeds the constant, calibration stops for a decision.

Rules (as in the runbook)
* Tier B: for each k in {1,2,3,5,8}, alpha_s = 1 - (1 - 0.01)^(1/k); tau_i = the (1 - alpha_s)
  quantile of honest step-i distances, pooled over pairs; if one pair's quantile is more than 2x
  the pooled one, the max over pairs is used instead and this is reported.
* Tier A: eps_A = 2 x the maximum honest residual, or 0 if every honest step was bit-exact.
* E0: t_pass = the lowest score at which >= 99% of honest pairs pass; t_fail = the highest score
  at or below which <= 0.5% of honest pairs fall (for LPIPS, a distance, the inequalities flip).
* Freeze: the file is written once (refuses to overwrite), and its sha256 is printed. Commit it
  before any attack run; a change means thresholds_v2.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from .rules.e1 import X0_TOL

KS = (1, 2, 3, 5, 8)
CONFIGS = Path(__file__).resolve().parents[2] / "experiments" / "configs"


def quantile(xs: list[float], q: float) -> float:
    """Higher empirical quantile (no interpolation): the smallest x with F(x) >= q."""
    xs = sorted(xs)
    if not xs:
        return float("nan")
    return xs[min(len(xs) - 1, max(0, math.ceil(q * len(xs)) - 1))]


def alpha_step(k: int, job_fpr: float = 0.01) -> float:
    return 1.0 - (1.0 - job_fpr) ** (1.0 / k)


def calibration_ids() -> set[int]:
    return {int(l.split("\t", 1)[0]) for l in (CONFIGS / "prompts_cal.txt").read_text().splitlines() if l.strip()}


def load_replays(paths: list[str]) -> dict[str, list[dict]]:
    cal = calibration_ids()
    out = {}
    for p in paths:
        rows = [json.loads(l) for l in (Path(p) / "jobs.jsonl").read_text().splitlines() if l.strip()]
        bad = [r["prompt_id"] for r in rows if r["prompt_id"] not in cal]
        if bad:
            raise SystemExit(f"{p}: {len(bad)} rows are not calibration prompts (e.g. {bad[:3]}); refusing")
        out[Path(p).name] = rows
    return out


def tier_b_taus(pairs: dict[str, list[dict]], metric: str) -> tuple[dict, list[str]]:
    notes = []
    T = min(len(r["tier_b"]) for rows in pairs.values() for r in rows)
    by_k = {}
    n = sum(len(rows) for rows in pairs.values())
    for k in KS:
        q = 1.0 - alpha_step(k)
        if n * alpha_step(k) < 1:  # the quantile is then just the sample maximum
            notes.append(f"k={k}: {n} honest samples per step < 1/alpha_s = {1 / alpha_step(k):.0f}; "
                         "tau is the sample maximum (underpowered, do not freeze)")
        tau = {}
        for i in range(T):
            pooled = [r["tier_b"][i][metric] for rows in pairs.values() for r in rows]
            t = quantile(pooled, q)
            per_pair = {n: quantile([r["tier_b"][i][metric] for r in rows], q) for n, rows in pairs.items()}
            if t > 0 and max(per_pair.values()) > 2 * t:
                notes.append(f"k={k} step {i}: pairs differ a lot ({per_pair}); using max over pairs")
                t = max(per_pair.values())
            tau[str(i)] = t
        by_k[str(k)] = {"alpha_s": alpha_step(k), "quantile": q, "tau": tau}
    return by_k, notes


def e0_thresholds(rows: list[dict]) -> dict:
    out = {"n_pairs": len(rows), "pixel_equal_rate": sum(r["pixel_equal"] for r in rows) / max(1, len(rows))}
    lp = sorted(r["lpips"] for r in rows)  # distance: pass if <= t_pass
    if lp:
        out["lpips_t_pass"] = quantile(lp, 0.99)
        out["lpips_t_fail"] = quantile(lp, 0.995)
    dn = sorted(r["dino_cosine"] for r in rows)  # similarity: pass if >= t_pass
    if dn:
        out["dino_t_pass"] = quantile([-x for x in dn], 0.99) * -1
        out["dino_t_fail"] = quantile([-x for x in dn], 0.995) * -1
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", nargs="+", required=True)
    ap.add_argument("--e0", nargs="*", default=[])
    ap.add_argument("--p1", nargs="*", default=[])
    ap.add_argument("--metric", default="rel_l2", choices=["rel_l2", "max_abs", "cos_dist"])
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--levels", default="L3,L4")
    ap.add_argument("--out", default=str(CONFIGS / "thresholds_v1.json"))
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists():
        raise SystemExit(f"{out} exists: frozen thresholds are never overwritten; write thresholds_v2.json")
    absd0 = [v["max_abs"] for p in a.p1 for v in json.loads(Path(p).read_text())["result"].values() if "max_abs" in v]
    if absd0 and 2 * max(absd0) > X0_TOL:
        raise SystemExit(f"P1 shows a cross-build x_0 difference of {max(absd0):.2e}; 2x that exceeds the "
                         f"protocol constant X0_TOL = {X0_TOL:g}. Decide a new constant before freezing.")
    pairs = load_replays(a.replay)
    samplers = {json.loads((Path(p) / "manifest.json").read_text()).get("sampler") for p in a.replay}
    if len(samplers) != 1:
        # Tier A's eps_A and Tier B's tau_i depend on the sampler: dpmpp_2m's step coefficients are
        # computed on the GPU and cannot be replicated bit-exactly on a CPU, euler's can (finding 17)
        raise SystemExit(f"replays mix samplers {samplers}: calibrate one sampler per thresholds file")
    sampler = samplers.pop()
    by_k, notes = tier_b_taus(pairs, a.metric)
    tier_a = [x["rel_l2"] for rows in pairs.values() for r in rows for x in r["tier_a"]]
    exact = all(x.get("replica_exact") for rows in pairs.values() for r in rows for x in r["tier_a"])
    e0rows = [json.loads(l) for p in a.e0 for l in Path(p).read_text().splitlines() if l.strip()]
    absd = [v["max_abs"] for p in a.p1 for v in json.loads(Path(p).read_text())["result"].values() if "max_abs" in v]
    th = {
        "version": out.stem,
        "sampler": sampler,
        "levels_supported": a.levels.split(","),
        "sources": {"replay_runs": sorted(pairs), "e0_files": [Path(p).name for p in a.e0],
                    "p1_files": [Path(p).name for p in a.p1],
                    "prompts_cal_sha256": hashlib.sha256((CONFIGS / "prompts_cal.txt").read_bytes()).hexdigest()},
        "tier_b_metric": a.metric, "k": a.k, "tau": by_k[str(a.k)]["tau"], "tau_by_k": by_k,
        "eps_a_rel_l2": 0.0 if exact else 2 * max(tier_a), "tier_a_bit_exact": exact,
        # build-agnostic protocol constant; the P1 maximum is recorded as evidence of the margin
        "x0_max_abs_noise": X0_TOL,
        "x0_p1_max_abs_observed": max(absd) if absd else None,
        "e0": e0_thresholds(e0rows) if e0rows else None,
        "notes": notes,
    }
    if out.stem.startswith("thresholds_v") and any("underpowered" in x for x in notes):
        raise SystemExit("too few honest samples for the chosen k: not freezing a thresholds_v* file\n" + "\n".join(notes))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(th, indent=1) + "\n")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"froze {out}\nsha256 {digest}\nRecord this hash in every later manifest and commit the file now.")


if __name__ == "__main__":
    main()
