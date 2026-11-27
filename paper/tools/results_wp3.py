"""Manuscript results read from the logged analysis outputs (CLAUDE.md: never type a number by hand).

Sources, all under experiments/analysis/ and each row carrying the run ids it came from:
  wp2/fig_r1_5_levels.csv                     RQ1 pixel equality by level (trajver.analysis_wp2 levels)
  wp2/fig_r1_4_steps.csv                      RQ1 per-step honest deviation (trajver.analysis_wp2 steps)
  wp3/v1/*.csv, wp3/v2/*.csv, wp3/base/*.csv  RQ2 (trajver.analysis_wp3 via code/tools/wp3_analyze.sh)
  wp5/devnet_combined_summary.json            RQ3 escrow cost (WP5 Devnet, commit ebdb93e)
A value that is not there yet stays a red {R|...} placeholder.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
A = ROOT / "experiments" / "analysis"
sys.path.insert(0, str(ROOT / "code"))
from trajver import theory  # noqa: E402

ATTACKS = [("A1b", "A1: 20 of 30 steps"), ("A2", "A2: fp8 network"), ("A3-Turbo", "A3: SDXL-Turbo, 4 steps"),
           ("A3-LCM", "A3: LCM-LoRA, 6 steps"), ("F1", "F1: frame copy, s = 0.5"),
           ("F2", "F2: prediction reuse, s = 0.5"), ("F3", "F3: solver inversion, s = 0.5"),
           ("A8", "A8: unrelated image"), ("M", "M: false metadata (control)")]


def rows(*parts) -> list[dict]:
    p = A.joinpath(*parts)
    return list(csv.DictReader(open(p, newline=""))) if p.exists() else []


def have(ver: str = "v1") -> bool:
    return bool(rows("wp3", ver, "r2_3_sensitivity.csv"))


def pc(x, d=1) -> str:
    return f"{100 * float(x):.{d}f}"


def ph(tag: str) -> str:
    return "{R|" + tag + "}"


def ci(r: dict, v: str, lo: str, hi: str, d=1) -> str:
    return f"{pc(r[v], d)} ({pc(r[lo], d)}–{pc(r[hi], d)})"


# ------------------------------------------------------------------ RQ1
def r1_identity() -> list[list[str]]:
    """Share of bit-identical images by model, sampler and level (pooled over precisions)."""
    g = defaultdict(lambda: [0.0, 0, 0])
    for r in rows("wp2", "fig_r1_5_levels.csv"):
        if r["metric"] != "pixel_equal" or r["level"] == "L1":
            continue
        k = (r["model"], r["sampler"], r["level"])
        g[k][0] += float(r["value"]) * int(r["n"]); g[k][1] += int(r["n"]); g[k][2] += 1
    out = []
    for model, sampler in [("sd15", "euler"), ("sd15", "dpmpp_2m"), ("sdxl", "euler"), ("sdxl", "dpmpp_2m")]:
        cells = []
        for lv in ["L0", "L2", "L3", "L4"]:
            e = g.get((model, sampler, lv))
            cells.append(f"{pc(e[0] / e[1], 0)} ({e[2]}; {e[1]:,})" if e else "not run")
        out.append([{"sd15": "SD1.5", "sdxl": "SDXL"}[model] + ", " + sampler.replace("dpmpp_2m", "DPM++ 2M")] + cells)
    return out


def r1_factors() -> dict:
    """L1 (same unit, one software factor changed): identical share per factor."""
    g = defaultdict(lambda: [0.0, 0, 0])
    for r in rows("wp2", "fig_r1_5_levels.csv"):
        if r["metric"] == "pixel_equal" and r["level"] == "L1":
            g[r["factor"]][0] += float(r["value"]) * int(r["n"]); g[r["factor"]][1] += int(r["n"]); g[r["factor"]][2] += 1
    return {f: (v[0] / v[1], v[2], v[1]) for f, v in g.items()}


def r1_steps() -> dict:
    """Per-step honest Tier B distance (rel. L2) by hardware pair: median and max per step."""
    by = defaultdict(lambda: defaultdict(list))
    n_jobs = defaultdict(set)
    for r in rows("wp2", "fig_r1_4_steps.csv"):
        by[r["hw_pair"]][int(r["step"])].append(float(r["d_value"]))
        n_jobs[r["hw_pair"]].add(r["job"])
    return {p: {"median": {i: statistics.median(v) for i, v in s.items()}, "max": {i: max(v) for i, v in s.items()},
                "n_jobs": len(n_jobs[p])} for p, s in by.items()}


# ------------------------------------------------------------------ RQ2
def _sens(ver):
    return {(r["attack"], r["evidence"], r["k"]): r for r in rows("wp3", ver, "r2_3_sensitivity.csv")}


def _fpr(ver, stratum="pooled"):
    return {(r["evidence"], r["k"]): r for r in rows("wp3", ver, "honest_fpr.csv") if r["stratum"] == stratum}


def table_deployed() -> list[list[str]]:
    acc = {(r["attack"], r["rule"]): r for r in rows("wp3", "v1", "r2_5_acceptance.csv")}
    out = []
    for key, label in [("honest", "Honest, 1,800 test jobs (RTX 3090, 4090, 5090 → Spark)")] + ATTACKS:
        cells = []
        for rule in ["E0-N", "E2-W"]:
            r = acc.get((key, rule))
            cells.append(ci(r, "acceptance", "ci_lo", "ci_hi") if r else ph("R2.5: not verified yet"))
        out.append([label] + cells)
    return out


def table_sensitivity() -> list[list[str]]:
    s1, s2 = _sens("v1"), _sens("v2")
    cols = [("v1", "E0", ""), ("v1", "E1", ""), ("v2", "E1", ""), ("v1", "E2-H", "1"), ("v2", "E2-H", "1"),
            ("v2", "E2-H", "8")]
    out = []
    for key, label in ATTACKS:
        cells = []
        for ver, ev, k in cols:
            r = (s1 if ver == "v1" else s2).get((key, ev, k))
            cells.append(ci(r, "q", "q_ci_lo", "q_ci_hi") if r else ph("R2.3"))
        out.append([label] + cells)
    f1, f2 = _fpr("v1"), _fpr("v2")
    hon = []
    for ver, ev, k in cols:
        r = (f1 if ver == "v1" else f2).get((ev, k))
        hon.append(ci(r, "fpr", "ci_lo", "ci_hi") if r else ph("R2.5"))
    out.append(["Honest false rejection (1,800 test jobs)"] + hon)
    return out


def rates() -> dict:
    """r_A per attack and the honest alpha_s, per k (per checked step)."""
    out = defaultdict(dict)
    for r in rows("wp3", "v1", "r2_6_rates.csv"):
        out[r["attack"]][int(r["k"])] = r
    return out


# Session 1's F1-F3 harness generated honestly before forging, so its timing could not give beta; session 2's
# realistic forgers are timed paired with an honest generation of the same job (doc 14 items 1-2). The bound is used
# only when no paired measurement exists.
F_BOUND = {"F1": 0.5, "F2": 0.5, "F3": 0.5}


def beta() -> dict:
    """Measured beta_A vs the honest base run. F1-F3: the harness runs the honest trajectory before forging, so
    its timing does not measure the saving; beta is replaced by its upper bound s (marked bound=True)."""
    out = {r["attack"]: dict(r) for r in rows("wp3", "v1", "r2_4_beta.csv")}
    for k, sv in F_BOUND.items():
        if k in out and "paired" not in (out[k].get("time_fields") or ""):
            out[k] = {**out[k], "beta_median": str(sv), "bound": True}
    return out


def table_deterrence() -> list[list[str]]:
    """r_A (k = 1, per checked step), beta_A, and Eq. 9's p* at c/P = 1 for B/P in {0, 1}, k in {1, 3}."""
    ra, be = rates(), beta()
    a_s = {k: float(v["rate"]) for k, v in ra.get("honest", {}).items()}
    out = []
    for key, label in ATTACKS:
        r1 = ra.get(key, {}).get(1)
        b = be.get(key)
        cells = [ci(r1, "rate", "ci_lo", "ci_hi") if r1 else ph("R2.6"),
                 (f"≤ {float(b['beta_median']):.2f} (bound s)" if b and b.get("bound") else
                  f"{float(b['beta_median']):.2f} ({float(b['beta_ci_lo']):.2f}–{float(b['beta_ci_hi']):.2f})"
                  if b and b.get("beta_median") not in (None, "") else ph("R2.4"))]
        for k, bp in [(1, 0.0), (1, 1.0), (3, 1.0)]:
            p = pstar_attack(key, k, bp)
            cells.append(ph("R3.2") if p is None else "none needed" if p == "none" else
                         "∞" if math.isinf(p) else ("> 1" if p > 1 else f"{p:.3f}"))
        out.append([label] + cells)
    return out


S_OF = {"F1": 0.5, "F2": 0.5, "F3": 0.5}  # faked share of the evaluated forgery runs (attacks.run --s)


def pstar_attack(key: str, k: int, bp: float, c_over_p: float = 1.0):
    """Equation 9 for one attack at k checked steps: p* = beta c / ((q - alpha_job)(P + B)), with q = Equation 4's
    q(s, k) for a forger that fakes a share s (F1-F3), and 1 - (1 - r_A)^k for an attack that alters every step.
    Returns None when an input is missing, 'none' when the attack saves nothing, inf when the margin is <= 0."""
    ra, be = rates(), beta()
    a = ra.get("honest", {}).get(k)
    r = ra.get(key, {}).get(k)
    b = be.get(key)
    if a is None or r is None or not b or b.get("beta_median") in (None, ""):
        return None
    beta_ = float(b["beta_median"])
    if beta_ <= 0:
        return "none"
    al, rr = float(a["rate"]), float(r["rate"])
    if key in S_OF:
        q = theory.q_spot_check(30, round(S_OF[key] * 30), k, rr, al)
    else:
        q = 1 - (1 - rr) ** k
    margin = q - theory.alpha_job(al, k)
    return math.inf if margin <= 0 else beta_ * c_over_p / (margin * (1 + bp))


def partial() -> list[dict]:
    return rows("wp3", "v1", "fig_r2_7_partial.csv")


# ------------------------------------------------------------------ RQ3
def escrow() -> list[list[str]]:
    p = A / "wp5" / "devnet_combined_summary.json"
    if not p.exists():
        return [["(one row per path)"] + [ph("R3.4")] * 4]
    d = json.loads(p.read_text())["paths"]
    out = []
    for key, label in [("unsampled", "Accepted, not sampled"), ("pass", "Sampled, verdict pass"),
                       ("dispute", "Sampled, dispute (fail)"), ("timeout", "Timeout refund")]:
        v = d[key]
        cu, fee, ms = v["compute_units_per_job"], v["fee_lamports_per_job"], v["ms_to_confirmed_per_tx"]
        out.append([label, f"{cu['median']:,} ({v['n_ok']} jobs)", f"{fee['median'] / 1e9:.6f}",
                    f"{fee['median'] / 1e9:.6f} + priority fees", f"{ms['median'] / 1000:.2f} s, {ms['p95'] / 1000:.2f} s"])
    return out


def escrow_failures() -> tuple[int, int, int, int]:
    p = A / "wp5" / "devnet_combined_summary.json"
    d = json.loads(p.read_text())["paths"]
    n = sum(v["n_jobs"] for v in d.values())
    f = sum(v["n_failed"] for v in d.values())
    fc = sum(v["n_failed_client_side"] for v in d.values())
    tx = sum(v["n_tx"] for v in d.values())
    return n, f, fc, tx


def _jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def verifier_cost() -> dict:
    """R3.1 on the rented RTX 5090 (a job has the card to itself): all-steps replay vs honest generation.
    The first job of each run is a warm-up and is dropped (as in analysis_wp3)."""
    R_ = ROOT / "experiments" / "runs"
    rep = _jl(R_ / "20261126-wp3-cost-replay-sdxl-euler-rtx5090-01" / "jobs.jsonl")[1:]
    gen = _jl(R_ / "20261126-wp3-base-sdxl-euler-rtx5090-01" / "jobs.jsonl")[1:]
    out = {}
    if rep:
        t = sorted(r["t_replay_all_s"] for r in rep)
        out.update(n_replay=len(t), replay_all_median=statistics.median(t), replay_all_p95=t[int(0.95 * (len(t) - 1))],
                   exact_share=sum(all(x.get("exact") for x in r["tier_b"]) for r in rep) / len(rep),
                   T=len(rep[0]["tier_b"]))
    if gen:
        ts = sorted(r.get("t_sample_s", 0) + r.get("t_decode_s", 0) for r in gen)
        out.update(n_gen=len(ts), gen_median=statistics.median(ts), gen_p95=ts[int(0.95 * (len(ts) - 1))])
    return out


def table_verifier_cost() -> list[list[str]]:
    v = verifier_cost()
    if "replay_all_median" not in v:
        return [["(one row per level)"] + [ph("R3.1")] * 3]
    T, step = v["T"], v["replay_all_median"] / v["T"]
    g = v.get("gen_median")
    rel = (lambda s: f"{100 * s / g:.1f}%") if g else (lambda s: ph("R3.1: needs the base run"))
    rows_ = [["E0 / E0-N: full regeneration (honest generation time; image metrics not included)", f"{g:.2f}" if g else ph("R3.1"), "100% (by definition)" if g else ph("R3.1")]]
    for k in (1, 3, 8):
        rows_.append([f"E2-H Tier B, k = {k} replayed steps", f"{k * step:.2f}", rel(k * step)])
    rows_.append([f"Tier B on all {T} steps (cost replay, {v['n_replay']} jobs)",
                  f"{v['replay_all_median']:.2f} (p95 {v['replay_all_p95']:.2f})", rel(v["replay_all_median"])])
    return rows_


# ------------------------------------------------------------------ narrative helpers (numbers from the CSVs)
def _lab(key):
    return dict(ATTACKS).get(key, key).split(":")[0] + ({"A3-Turbo": " (Turbo)", "A3-LCM": " (LCM-LoRA)"}.get(key, ""))


def deployed_summary() -> dict:
    acc = {(r["attack"], r["rule"]): r for r in rows("wp3", "v1", "r2_5_acceptance.csv")}
    out = {}
    for rule in ["E0-N", "E2-W"]:
        got = [(k, float(acc[(k, rule)]["acceptance"])) for k, _ in ATTACKS if k != "M" and (k, rule) in acc]
        out[rule] = {"n": len(got), "ge90": [k for k, a in got if a >= 0.9], "le10": [k for k, a in got if a <= 0.1],
                     "acc": dict(got)}
        h = acc.get(("honest", rule))
        out[rule]["honest"] = float(h["acceptance"]) if h else None
    return out


def sens_summary(ver="v2", ev="E2-H", k="1") -> dict:
    s = _sens(ver)
    got = {key: s[(key, ev, k)] for key, _ in ATTACKS if (key, ev, k) in s}
    return {"q": {key: float(r["q"]) for key, r in got.items()},
            "n": {key: int(r["n_jobs"]) for key, r in got.items()}}


def labels(keys) -> str:
    keys = [_lab(k) for k in keys]
    return ", ".join(keys[:-1]) + (" and " if len(keys) > 1 else "") + keys[-1] if keys else "none"


def narr_r21() -> str:
    d = deployed_summary()
    w, n = d["E2-W"], d["E0-N"]
    if not w["n"]:
        return ph("R2.1: narrative of the deployed-rule results")
    others = {k: a for k, a in n["acc"].items() if k not in n["le10"]}
    s = (f"The latent-cosine rule E2-W accepted {pc(w['honest'])}% of the honest jobs and at least 90% of the jobs of "
         f"{len(w['ge90'])} of the {w['n']} attack conditions ({labels(w['ge90'])})")
    s += (". It cannot see these attacks, because the verifier replays each checked step from the provider's own "
          "state, so any internally smooth trajectory stays above the cosine threshold whatever image it ends in. "
          f"The CLIP rule E0-N accepted {pc(n['honest'])}% of the honest jobs; it rejected at least 90% of the jobs of "
          f"{labels(n['le10'])}")
    if others:
        lo, hi = min(others.values()), max(others.values())
        rng = f"{pc(lo, 0)}%" if pc(lo, 0) == pc(hi, 0) else f"between {pc(lo, 0)}% and {pc(hi, 0)}%"
        s += (f", but accepted {rng} of the jobs of the other attack" + ("s" if len(others) > 1 else "")
              + f" ({labels(list(others))}), whose images stay semantically close to the honest output")
    return s + "."


def narr_r23() -> str:
    q = sens_summary("v2", "E2-H", "1")["q"]
    q8 = sens_summary("v2", "E2-H", "8")["q"]
    e0 = sens_summary("v1", "E0", "")["q"]
    if not q:
        return ph("R2.3: narrative of the sensitivity results")
    att = [k for k in q if k != "M"]
    hi = [k for k in att if q[k] >= 0.95]
    lo = [k for k in att if q[k] < 0.95]
    f = _fpr("v2").get(("E2-H", "1"))
    s = (f"With one checked step (k = 1) and the v2 image tolerance, E2-H rejected at least 95% of the jobs of {len(hi)} "
         f"of the {len(att)} attack conditions ({labels(hi)}) at an honest false-rejection rate of {pc(f['fpr'])}% "
         f"(95% CI upper bound {pc(f['ci_hi'])}%)" if f else "")
    if lo:
        s += "; below that were " + "; ".join(f"{_lab(k)} with {pc(q[k], 0)}% at k = 1 and {pc(q8.get(k, float('nan')), 0)}% at k = 8" for k in lo)
    if "M" in q:
        s += (f". The control M, honest computation under false device metadata, was rejected in {pc(q['M'], 0)}% of jobs, "
              "the honest rate, as it should be: no evidence level here observes the device")
    if e0:
        e0a = [k for k in att if k in e0]
        s += (f". The re-execution check E0 rejected between {pc(min(e0[k] for k in e0a), 0)}% and "
              f"{pc(max(e0[k] for k in e0a), 0)}% of the attacked jobs, but at a full regeneration per job and with an honest "
              f"false-rejection rate of {pc(_fpr('v1').get(('E0', ''), {}).get('fpr', 'nan'))}%") if e0a else ""
    return s + "."


def narr_r28() -> str:
    ra = rates()
    a1 = ra.get("honest", {}).get(1)
    if not a1:
        return ph("R2.8")
    near = [k for k, _ in ATTACKS if k != "M" and 1 in ra.get(k, {}) and float(ra[k][1]["rate"]) < 0.5]
    s = (f"The honest per-step rate α_s at k = 1 was {pc(a1['rate'], 2)}% on the test split (nominal 1%). ")
    if near:
        s += ("Per-step separability was below 50% for " + labels(near) + " (" +
              "; ".join(f"r_A = {pc(ra[k][1]['rate'])}%" for k in near) + "): by Proposition 1 these attacks can be "
              "deterred only through a larger k or sampling rate, or through other evidence.")
    else:
        s += ("Every attack condition had a per-step separability r_A of at least 50% at k = 1, so no attack here is "
              "inseparable in the sense of Proposition 1; the F attacks are separable only on their faked steps, which "
              "is why their job-level detection depends on s and k (Figure 5).")
    return s


NWF = '{R|NEEDS WORK: F1–F3 must be regenerated by a forger that runs the model at its computed steps from its own forged states}'



def sweep_undetected() -> dict:
    """Per sweep level: jobs with at least one faked step (ground-truth labels of the generation run, never read by
    the verifier) whose k = 1 Tier B deviation stayed at or below tau_i, out of the jobs verified."""
    R_ = ROOT / "experiments" / "runs"
    th = json.loads((ROOT / "experiments" / "configs" / "thresholds_v1_sdxl_euler.json").read_text())
    tau = th["tau_by_k"]["1"]["tau"]
    out = {}
    for r in sweep_tiers():
        if r["k"] != 1:
            continue
        v = R_ / r["run_id"]
        gen = R_ / ("20261127-wp3-" + r["run_id"].split("20261127-wp3-verify-wp3-", 1)[1].rsplit("-on-", 1)[0])
        lab = {q.stem: json.loads(q.read_text()).get("faked", []) for q in gen.glob("raw/**/labels/*.json")}
        last = {}
        for row in _jl(v / "verdicts.jsonl"):
            if row["evidence"] == "E2-H" and row.get("k") == 1:
                last[row["job_id"]] = row
        n = und = 0
        for j, row in last.items():
            if j not in lab:
                continue
            n += 1
            und += any(float(row["per_step"].get(str(i), 0.0)) <= tau[str(i)] for i in lab[j])
        out[r["s"]] = (und, n)
    return out

def _undetected_sentence(worst: tuple) -> str:
    """Why the worst cell misses Equation 4: faked steps within tau_i (labels), and the prediction with only the
    faked steps above tau_i counted as detectable (k = 1 only, where that count is exact)."""
    u = sweep_undetected()
    if not u:
        return ""
    big = max(u, key=lambda x: u[x][0] / max(1, u[x][1]))
    rest = [x for x in sorted(u) if x != big]
    out = (f"Part of the gap comes from faked steps that stay within the honest tolerance: at s = {big:g}, {u[big][0]} "
           f"of {u[big][1]} jobs had at least one faked step whose deviation did not exceed τ{{sub|i}}, against "
           + ", ".join(f"{u[x][0]} at s = {x:g}" for x in rest)
           + "; Equation 4 with m = sT counts every faked step as detectable.")
    r = worst[3]
    if r["k"] == 1 and r["s"] == big:
        m_det = statistics.mean(r["n_over_tau"])
        q_det = m_det / 30 + (1 - m_det / 30) * worst[4]  # Equation 4 at k = 1, r = 1, with a non-integer m
        se = (q_det * (1 - q_det) / r["n"]) ** 0.5
        out += (f" Setting m to each job's number of steps above τ{{sub|i}} ({m_det:.1f} on average, against "
                f"{round(r['s'] * 30)} faked) predicts {100 * q_det:.0f}% at k = 1, against the {100 * worst[1]:.0f}% measured "
                f"({abs(q_det - worst[1]) / se:.1f} binomial standard errors at n = {r['n']}).")
    return out


def narr_r27() -> str:
    """Session 2: the realistic forger's F3 sweep against Equation 4 with m = sT (doc 14 item 2b)."""
    rs = sweep_tiers()
    if not rs:
        return ph("R2.7: agreement of the F3 sweep with Equation 4")
    ra = rates()
    a_s = {k: float(v["rate"]) for k, v in ra.get("honest", {}).items()}
    svals = sorted({r["s"] for r in rs})
    dev = []
    for r in rs:
        qm = r["tierb_fail"] / r["n"]
        qe = theory.q_spot_check(30, round(r["s"] * 30), r["k"], 1.0, a_s.get(r["k"], 0.0))
        dev.append((abs(qm - qe), qm, qe, r, a_s.get(r["k"], 0.0)))
    worst = max(dev, key=lambda t: t[0])
    ta = [r for r in rs if r["k"] == 1]
    part = sorted({(r["s"], r["n_jobs"]) for r in rs if r.get("partial")})
    pn = ("; at s = " + ", ".join(f"{x:g} only {n} of 100 jobs were verified" for x, n in part)) if part else ""
    tsum = sum(r["tiera_fail"] for r in ta)
    return (f"Figure 5 shows the share of F3 jobs failing Tier B at s ∈ {{{', '.join(f'{x:g}' for x in svals)}}} "
            f"(100 jobs per s, generated and verified on DGX Spark systems with full trajectories{pn}), produced by the "
            "forger that runs its computed steps from its own states. Over the "
            f"{len(dev)} (s, k) cells the measured share differed from Equation 4 with m = sT, r = 1 and the measured "
            f"α{{sub|s}} by at most {100 * worst[0]:.0f} percentage points (s = {worst[3]['s']:g}, k = {worst[3]['k']}: "
            f"{100 * worst[1]:.0f}% measured, {100 * worst[2]:.0f}% predicted). "
            + _undetected_sentence(worst) + " "
            + (f"Tier A rejected none of the {sum(r['n_jobs'] for r in ta)} jobs: the forgery is consistent by "
               "construction, so detection rests on the spot check alone, as the model assumes."
               if tsum == 0 else
               "Tier A rejected " + "; ".join(f"{r['tiera_fail']} of {r['n_jobs']} jobs at s = {r['s']:g}" for r in ta) + "."))


def narr_r32() -> str:
    """p* over the attack conditions with a positive saving, per k (Equation 9 with Equation 4's q for forgers)."""
    out = []
    for k in (1, 2, 3, 5, 8):
        ps = {key: pstar_attack(key, k, 1.0) for key, _ in ATTACKS if key != "M"}
        ps = {key: v for key, v in ps.items() if isinstance(v, float)}
        if ps:
            worst = max(ps, key=ps.get)
            out.append((k, ps[worst], worst, len(ps)))
    if not out:
        return ph("R3.2: best k, p*, required bond ratio, and agreement between theory and measurement")
    best = min(out, key=lambda t: t[1])
    s = ("With a bond equal to the payment (B/P = 1) and the conservative cost ratio c/P = 1, the sampling rate that "
         f"deters all {out[0][3]} attack conditions with a positive saving at once (Equation 9, with Equation 4's "
         "detection q(s, k) for the forgers, which fake a share s = 0.5 of the steps) is "
         + "; ".join(f"p* = {p:.3f} at k = {k} (set by {_lab(w)})" for k, p, w, _ in out)
         + f". The cost-optimal choice here is k = {best[0]}: ")
    first = out[0]
    if best[0] != first[0]:
        s += (f"one checked step leaves a partial forger undetected about half the time, so it needs p* = {first[1]:.3f}, "
              f"while k = {best[0]} brings the forgers below the model substitutions and the requirement down to "
              f"{best[1]:.3f}; more steps add honest false rejections without lowering it. ")
    else:
        s += "further checked steps add honest false rejections rather than detection. "
    s += "p* scales linearly with c/P and with 1/(1 + B/P)."
    return s


def sweep_tiers() -> list[dict]:
    """F3 sweep, straight from the verify runs (one row per job and k; the last row wins after a guard restart):
    per s and k, jobs whose Tier B part failed, and jobs failed by Tier A (all steps, CPU)."""
    R_ = ROOT / "experiments" / "runs"
    out = []
    for tag in ["s010", "s025", "s050", "s075", "s100"]:
        v, partial_run = None, False
        cands = sorted(R_.glob(f"20261127-wp3-verify-wp3-sweepr-f3-{tag}-sdxl-euler-*-on-*"))
        done_ = [c for c in cands if (c / "summary.json").exists()]
        if done_:
            v = done_[0]
        elif cands and (cands[0] / "verdicts.jsonl").exists():  # aborted by a memory guard: partial, said so
            v, partial_run = cands[0], True
        if v is None:
            continue
        last = {}
        for r in _jl(v / "verdicts.jsonl"):
            last[(r["job_id"], r["evidence"], r.get("k"))] = r
        jobs = sorted({j for j, _, _ in last})
        ta = sum(last.get((j, "E2-H.tierA", None), {}).get("verdict") == "fail" for j in jobs)
        th = json.loads((ROOT / "experiments" / "configs" / "thresholds_v1_sdxl_euler.json").read_text())
        tau = {k: th["tau_by_k"][str(k)]["tau"] for k in (1, 2, 3, 5, 8)}
        # steps over tau (k = 1) per job, over all 30 replayed steps (class F): the detectable steps
        n_over = [sum(float(x) > tau[1][i] for i, x in last[(j, "E2-H", 1)]["per_step"].items())
                  for j in jobs if (j, "E2-H", 1) in last]
        for k in (1, 2, 3, 5, 8):
            rr = [last[(j, "E2-H", k)] for j in jobs if (j, "E2-H", k) in last]
            fail = sum(any(float(r["per_step"][str(i)]) > tau[k][str(i)] for i in r["steps"]) for r in rr)
            out.append({"s": int(tag[1:]) / 100, "k": k, "n": len(rr), "tierb_fail": fail, "tiera_fail": ta,
                        "n_jobs": len(jobs), "n_over_tau": n_over, "run_id": v.name, "partial": partial_run})
    return out


def cost_ratio(k=1):
    v = verifier_cost()
    if "replay_all_median" in v and "gen_median" in v:
        return k * v["replay_all_median"] / v["T"] / v["gen_median"]
    return None


def forgery_summary() -> dict | None:
    """F1-F3 (realistic forger, s = 0.5): measured E2-H rejection at k in {1, 3, 8} (v2) beside Equation 4."""
    sens, ra = _sens("v2"), rates()
    keys = [k for k in ("F1", "F2", "F3") if (k, "E2-H", "1") in sens]
    if not keys or not ra.get("honest"):
        return None
    out = {"keys": keys, "q": {}, "pred": {}, "tier_a": [float(sens[(k, "E2-H.tierA", "")]["q"]) for k in keys
                                                         if (k, "E2-H.tierA", "") in sens]}
    for kk in (1, 3, 8):
        out["q"][kk] = [float(sens[(k, "E2-H", str(kk))]["q"]) for k in keys]
        al = float(ra["honest"][kk]["rate"])
        out["pred"][kk] = [theory.q_spot_check(30, round(S_OF[k] * 30), kk, float(ra[k][kk]["rate"]), al) for k in keys]
    return out


def _rng(v: list[float]) -> str:
    lo, hi = pc(min(v), 0), pc(max(v), 0)
    return f"{lo}%" if lo == hi else f"{lo}–{hi}%"


def narr_r29() -> str:
    d, q = deployed_summary(), sens_summary("v2", "E2-H", "1")["q"]
    if not q or not d["E2-W"]["n"]:
        return ph("R2.9")
    att = [k for k in q if k != "M" and not k.startswith("F")]
    hi = [k for k in att if q[k] >= 0.95]
    f = _fpr("v2").get(("E2-H", "1"))
    return (f"The reproduced deployed rules do not separate cost-saving attacks from honest variation: the latent-cosine "
            f"rule accepted at least 90% of the jobs of {len(d['E2-W']['ge90'])} of {d['E2-W']['n']} attack conditions"
            + (", including unrelated images" if "A8" in d["E2-W"]["ge90"] else "") + f", and the CLIP rule rejected at least 90% only for {labels(d['E0-N']['le10'])}. "
            f"Calibrated trajectory evidence does: E2-H with a single checked step rejected at least 95% of the jobs of "
            f"{len(hi)} of {len(att)} model- and step-substitution conditions ({labels(hi)}) at an honest false-rejection "
            f"rate of {pc(f['fpr'])}% on 1,800 jobs from three GPU generations, once the one uncalibrated tolerance (the "
            "E1 image check) was set from the calibration split. " + _forgery_sentence())


def _forgery_sentence() -> str:
    fs = forgery_summary()
    if not fs:
        return NWF + "."
    q, pr = fs["q"], fs["pred"]
    s = (f"Forgeries that fake half of the steps ({labels(fs['keys'])}) were rejected in {_rng(q[1])} of jobs with one "
         f"checked step, {_rng(q[3])} with three and {_rng(q[8])} with eight, as Equation 4 predicts "
         f"({_rng(pr[1])}, {_rng(pr[3])} and {_rng(pr[8])})")
    if fs["tier_a"] and max(fs["tier_a"]) == 0:
        s += "; Tier A rejected none of them, because each committed state follows from its committed prediction"
    return s + "."


def abstract_findings() -> str:
    d, q = deployed_summary(), sens_summary("v2", "E2-H", "1")["q"]
    if not q or not d["E2-W"]["n"]:
        return ph("R2.1: deployed-rule headline") + ". " + ph("R2.2/R2.3: detection headline") + "."
    att = [k for k in q if k != "M" and not k.startswith("F")]
    hi = [k for k in att if q[k] >= 0.95]
    f = _fpr("v2").get(("E2-H", "1"))
    cr = cost_ratio(1)
    return (f"the reproduced latent-cosine rule of a deployed subnet accepted at least 90% of the jobs of "
            f"{len(d['E2-W']['ge90'])} of {d['E2-W']['n']} attack conditions" + (", including unrelated images" if "A8" in d["E2-W"]["ge90"] else "") + ". With one "
            f"checked step, the proposed check rejected at least 95% of the jobs of {len(hi)} of {len(att)} model- and "
            f"step-substitution conditions at an honest false-rejection rate of {pc(f['fpr'])}% on 1,800 cross-GPU test jobs"
            + (f", at {100 * cr:.0f}% of the GPU time of re-execution" if cr else "")
            + (". Forgeries that fake half of the steps were caught in {} of jobs with one checked step and {} with "
               "three, as the spot-check model predicts".format(_rng(forgery_summary()["q"][1]), _rng(forgery_summary()["q"][3]))
               if forgery_summary() else "")
            + ". Bit-exact reproduction held only within one GPU model, and one uncalibrated image tolerance "
              "rejected every honest cross-architecture job until it was calibrated")


def sizes() -> dict:
    """Trajectory and opened-bundle size per SDXL job from the class-O attack runs' retention stats."""
    full = kept = n = 0
    for d in (ROOT / "experiments" / "runs").glob("20261126-wp3-*-sdxl-euler-rtx5090-01"):
        m = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
        st = m.get("retention_stats") or {}
        if st.get("n"):
            full += st["full_bytes"]; kept += st["kept_bytes"]; n += st["n"]
    return {"full_mb": full / n / 1e6, "kept_mb": kept / n / 1e6, "n": n} if n else {}


def th_v1() -> dict:
    return json.loads((ROOT / "experiments" / "configs" / "thresholds_v1_sdxl_euler.json").read_text())


def inseparable() -> str:
    ra = rates()
    near = [k for k, _ in ATTACKS if k != "M" and 1 in ra.get(k, {}) and float(ra[k][1]["rate"]) < 0.5]
    return (labels(near) if near else "none of the conditions evaluated here; Table 9")


def table5_beta(key: str) -> str:
    """Table 5 column: measured beta_A for evaluated attacks; 'not evaluated' otherwise."""
    b = beta().get(key)
    if b and b.get("bound"):
        return f"≤ {float(b['beta_median']):.2f} (s; not measured)"
    if b and b.get("beta_median") not in (None, ""):
        return f"{float(b['beta_median']):.2f}"
    return "not evaluated" if key not in dict(ATTACKS) else ph("R2.4")


def narr_mc() -> str:
    rs = rows("wp4", "mc_sweep.csv")
    if not rs:
        return ""
    d = [abs(float(r["detect_sim"]) - float(r["detect_closed"])) for r in rs]
    firm = [r for r in rs if (float(r["gain_ci_lo"]) > 0) or (float(r["gain_ci_hi"]) < 0)]
    agree = sum((float(r["gain_mean"]) > 0) == (float(r["gain_closed"]) > 0) for r in firm)
    natk = len({r["attack"] for r in rs})
    n_sim = rs[0]["n_sim"]
    return (f"A Monte Carlo simulation of Equations 4 and 7 with the measured r{{sub|A}}, β{{sub|A}} and α{{sub|s}} "
            f"({natk} attack conditions with a positive or zero saving, {len(rs):,} cells of (p, k, B/P, s), "
            f"{int(n_sim):,} simulated jobs each) agreed with the closed form within {100 * max(d):.1f} percentage points "
            f"of detection, and in the {len(firm):,} cells whose 95% interval of the gain excludes zero the sign of the "
            f"simulated gain matched Equation 7 in {agree:,}.")


def _f3_caption(d: dict) -> str:
    f3 = [t for t in d["tiles"] if t["column"] == "atkr-f3" and "faked" in t]
    if not f3:
        return ""
    early = [t for t in f3 if {0, 1} <= set(t["faked"])]
    s = "; F3 skips half of the network calls"
    if early:
        s += (f", and in the {len(early)} job{'s' if len(early) > 1 else ''} where it skipped the first two steps, it had no "
              "earlier state to extrapolate from, copied the noise, and never denoised the image")
    return s


def examples_caption() -> str | None:
    """Caption of the qualitative figure, from experiments/analysis/wp3/fig_examples_sources.json."""
    p = A / "wp3" / "fig_examples_sources.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    mx = [x["max_abs"] for x in d["diff"]]
    cols = {t["column"] for t in d["tiles"]}
    return ("Delivered images of the first three jobs of the attacked test-split job set (selection rule fixed in "
            "advance; prompts from PartiPrompts {c|yu2022parti}). The honest DGX Spark and RTX 5090 images are not "
            f"bit-identical (largest per-pixel difference {min(mx)}–{max(mx)} uint8 levels, shown ×10) yet look the "
            "same; A1 and A2 are visually indistinguishable from the honest output"
            + _f3_caption(d)
            + "; A3's images are degraded by the forged schedule; A8 is unrelated. Illustration only: detection rates "
            "are in Tables 7 and 8")


def host_sampling() -> tuple[float, float] | None:
    """Median honest sampling time of the same job set on the two rented RTX 5090 hosts (session 1 base run,
    session 2 timebase run; first job dropped)."""
    R_ = ROOT / "experiments" / "runs"
    a = _jl(R_ / "20261126-wp3-base-sdxl-euler-rtx5090-01" / "jobs.jsonl")[1:]
    b = _jl(R_ / "20261127-wp3-timebase-sdxl-euler-rtx5090-01" / "jobs.jsonl")[1:]
    if not a or not b:
        return None
    return statistics.median(r["t_sample_s"] for r in b), statistics.median(r["t_sample_s"] for r in a)
