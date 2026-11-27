"""WP3 aggregation: verify outputs -> the RQ2 tables and the WP4 inputs (runbook §6 items 3-4, §8b).

  python -m trajver.analysis_wp3 --honest RUN... --attacked RUN... --thresholds TH.json --out DIR \
      [--sweep RUN...] [--baseline GENRUN...] [--compare DIR] [--th-sha256 H] [--partial]

Every RUN is a ``python -m trajver.verify`` run folder (manifest.json, verdicts.jsonl). Its manifest names
the generation run it scored (``source_run``), looked up next to it or under $TRAJVER_RUNS; that run gives
the model, sampler and provider card (manifest), the pod timings (jobs.jsonl) and the ground-truth labels
(raw/labels/<job>.json). Labels are joined here, after verification, never by the verifier.
``--compare DIR`` holds ``pilot compare --e0-out`` files named ``<run_a>__<run_b>.e0.jsonl`` (as for WP2);
a file is joined to the verify run whose generation run is run_a or run_b.

Outputs in DIR, one CSV each, every row with the run ids it came from:
* r2_3_sensitivity.csv  q = share of attacked jobs rejected, per attack x evidence x k, Wilson 95% CI, beside the
                        honest job-level FPR of the same evidence and k on the same model and sampler.
* r2_5_acceptance.csv   acceptance of the deployed rules E0-N and E2-W, per attack and for honest jobs.
* r2_6_rates.csv        per-step rates: r_A (share of FAKED checked steps over tau_i) and honest alpha_s.
* r2_4_beta.csv         beta_A = 1 - t_attack / t_honest per matched job; median, cluster bootstrap CI over prompts.
* fig_r2_7_partial.csv  the F3 sweep (§8b): attack, s, k, n_jobs, n_detected, alpha_s, r_measured.
* honest_fpr.csv        honest rejections per stratum (model, sampler, provider->verifier) and evidence level,
                        Wilson CI and the one-sided exact 95% upper bound (the runbook's 0-in-299 rule).
* inputs.json           run ids, thresholds hash and the warnings printed.

Conventions
* Rejected = any verdict other than "pass" (E0 also has "inconclusive", counted separately).
* q is read from the frozen verdicts; thresholds are never re-fitted on test data. The thresholds file must
  be the one every verify run recorded (``threshold_file_sha256``), or the script stops.
* E2-H at k: when a row carries per-step distances (``per_step``, written by verify.py since 2026-11-26),
  its Tier B part is recomputed with the frozen tau of that k (``tau_by_k``), which is what verify.py now
  does itself. Older rows have no ``per_step`` and were judged with the single ``tau`` of the frozen k at
  every k; their verdict is used as written. The ``tau_k`` column says which.
* r_A and alpha_s: from per-step distances when the rows have them (every replayed step of a job, once);
  for older rows from the k = 1 rows only, whose one checked step is drawn independently of the faking pattern. Steps of one job are correlated,
  so their Wilson CI is optimistic.
* Faked steps: the label's ``faked`` list for F1-F3 and A6; every step for attacks that replace the whole
  computation; for M (honest compute, false metadata) also every step, so its r_A is a control that
  should match honest alpha_s.
* s is reported only for attacks that use it (F1-F3, A6).
* beta_A = 1 - t_compute_s(attack) / t_sample_s(honest), matched by job key: attacks.run times sampling plus
  forging without the decode, pilot gen times sampling (t_sample_s) and decode (t_decode_s) apart. The honest
  times come from ``--baseline`` (the ``*-wp3-base-*`` pilot gen run on the attack card), else from the
  --honest runs' generation runs; a job's honest time is the median over those runs of the same model on the
  same card. The first job of every run is a warm-up and is dropped. Fallbacks, only when a field is absent:
  t_compute_s on both sides (an attacks.run M-style baseline), then t_total_s on both. The ``time_fields``
  column says which pair was used.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import theory
from .stats import cluster_bootstrap_median, cp_upper, wilson
from .thresholds import load as load_thresholds
from .thresholds import tau_for

KS = (1, 2, 3, 5, 8)
S_ATTACKS = {"F1", "F2", "F3", "A6"}
# (attack field, honest field). attacks.run records t_compute_s (sampling + forging, no decode); pilot gen records
# t_sample_s, t_decode_s and t_total_s (= both). The first pair is the WP3 rule (beta_A = 1 - t_compute/t_sample).
# preferred first: the same field on both sides (sampling incl. trajectory capture; attacks.run records it since
# 2026-11-27); the older pairs remain for runs made before that
TIME_FIELDS = (("t_sample_s", "t_sample_s"), ("t_compute_s", "t_sample_s"), ("t_compute_s", "t_compute_s"),
               ("t_total_s", "t_total_s"))
WARN: list[str] = []


def warn(msg: str) -> None:
    WARN.append(msg)
    print("warning:", msg)


def jl(path) -> list[dict]:
    p = Path(path)
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def gpu_label(manifest: dict | None) -> str:
    """Card model only (no host names): spark, rtx5090, rtx4090, ..."""
    name = ((manifest or {}).get("node") or {}).get("gpu_name") or ""
    if "GB10" in name:
        return "spark"
    m = re.search(r"RTX\s*(?:PRO\s*)?(\d{4})", name)
    if m:
        return f"rtx{m.group(1)}"
    return re.sub(r"[^a-z0-9]+", "", name.lower()) or "unknown"


def model_label(manifest: dict | None) -> str:
    models = (manifest or {}).get("models") or []
    name = models[0]["filename"] if models else ""
    if re.search(r"xl", name, re.I):
        return "sdxl"
    if re.search(r"v1-5|sd15|sd_1\.5|1\.5", name, re.I):
        return "sd15"
    return Path(name).stem or "unknown"


@dataclass
class Run:
    run_id: str
    path: Path
    attack: str
    s: float | None
    model: str
    sampler: str
    provider: str
    verifier: str
    th_sha: str | None
    source_id: str | None
    source: Path | None
    rows: dict = field(default_factory=dict)   # (job, evidence, k) -> row (last one wins: verify appends on resume)
    e0: dict = field(default_factory=dict)     # job -> pilot compare e0 row
    e0_refs: list = field(default_factory=list)

    @property
    def jobs(self) -> list[str]:
        return sorted({j for j, _, _ in self.rows})

    @property
    def pair(self) -> str:
        return f"{self.provider}->{self.verifier}"

    @property
    def ids(self) -> list[str]:
        return [self.run_id] + ([self.source_id] if self.source_id else []) + self.e0_refs


def find_source(path: Path, source_id: str | None) -> Path | None:
    if not source_id:
        return None
    for base in (path.parent, Path(os.environ["TRAJVER_RUNS"]) if os.environ.get("TRAJVER_RUNS") else None):
        if base is not None and (base / source_id / "manifest.json").exists():
            return base / source_id
    return None


def load_run(path) -> Run:
    path = Path(path)
    if not (path / "verdicts.jsonl").exists():
        raise SystemExit(f"{path}: no verdicts.jsonl (pass verify runs, not generation runs)")
    vm = json.loads((path / "manifest.json").read_text())
    sid = vm.get("source_run")
    src = find_source(path, sid)
    if sid and src is None:
        warn(f"{path.name}: generation run {sid} not found; no model, timing or labels for it")
    sm = json.loads((src / "manifest.json").read_text()) if src else {}
    if "cal" in str((sm.get("prompt_set") or {}).get("file", "")):
        warn(f"{path.name}: generation run used {sm['prompt_set']['file']}; §6 uses the test split")
    rows = {}
    for r in jl(path / "verdicts.jsonl"):
        rows[(r["job_id"], r["evidence"], r.get("k"))] = r
    attack = vm.get("attack") or next((r.get("attack") for r in rows.values()), "honest") or "honest"
    # one attack name can cover several variants (A3: SDXL-Turbo or LCM-LoRA); the generation run id says which
    v = re.search(r"-atk-(a3[a-z]+)-", sid or path.name)
    if attack == "A3" and v:
        attack = {"a3turbo": "A3-Turbo", "a3lcm": "A3-LCM"}.get(v.group(1), attack)
    s = next((r.get("s") for r in rows.values() if r.get("s") is not None), None) if attack in S_ATTACKS else None
    sampler = (sm.get("claimed") or {}).get("sampler") or sm.get("sampler") or "unknown"
    model = model_label(sm) if sm else model_label(vm)
    return Run(path.name, path, attack, s, model, sampler, gpu_label(sm), gpu_label(vm), vm.get("threshold_file_sha256"),
               sid, src, rows)


def attach_e0(runs: list[Run], compare: str | None) -> None:
    if not compare:
        return
    files = sorted(Path(compare).glob("*__*.e0.jsonl"))
    for r in runs:
        for f in files:
            a, b = f.name[: -len(".e0.jsonl")].split("__", 1)
            if r.source_id not in (a, b):
                continue
            new = {x["job"]: x for x in jl(f) if x["job"] not in r.e0}
            if new:
                r.e0.update(new)
                r.e0_refs.append(b if a == r.source_id else a)


# ------------------------------------------------------------------------------------------- verdicts
def tau_k(th: dict, k: int | None, i: int) -> float:
    return tau_for(th, i, k)


def alpha_nominal(th: dict, k: int) -> float:
    tb = (th.get("tau_by_k") or {}).get(str(k))
    return float(tb["alpha_s"]) if tb and "alpha_s" in tb else theory.alpha_step_budget(0.01, k)


def step_value(x, metric: str) -> float:
    return float(x[metric] if isinstance(x, dict) else x)


def e0_verdict(r: dict, e: dict | None) -> str | None:
    if r.get("pixel_equal"):
        return "pass"
    if not e or "lpips_t_pass" not in e or r.get("lpips") is None or r.get("dino_cosine") is None:
        return None
    if r["lpips"] > e["lpips_t_fail"] or r["dino_cosine"] < e["dino_t_fail"]:
        return "fail"
    if r["lpips"] <= e["lpips_t_pass"] and r["dino_cosine"] >= e["dino_t_pass"]:
        return "pass"
    return "inconclusive"


def job_verdicts(run: Run, th: dict) -> dict:
    """(evidence, k) -> {job: verdict} and (evidence, k) -> tau note."""
    out: dict = defaultdict(dict)
    note: dict = {}
    metric = th["tier_b_metric"]
    for (job, ev, k), r in sorted(run.rows.items(), key=lambda t: (t[0][0], t[0][1], t[0][2] or 0)):
        v = r["verdict"]
        if ev == "E2-H" and r.get("per_step") and r.get("steps") and r.get("tier_b") is not None:
            e1 = run.rows.get((job, "E1", None), {}).get("verdict", "pass")
            ta = run.rows.get((job, "E2-H.tierA", None), {}).get("verdict", "pass")
            bad = any(step_value(r["per_step"][str(i)], metric) > tau_k(th, k, i) for i in r["steps"])
            v = "fail" if bad or "fail" in (e1, ta) else "pass"
            note[(ev, k)] = f"tau_by_k[{k}]"
        elif ev == "E2-H":
            note.setdefault((ev, k), f"as written (tau of k={th.get('k')})")
        out[(ev, k)][job] = v
    for job, r in run.e0.items():
        if "e0n_pass" in r:
            out[("E0-N", None)][job] = "pass" if r["e0n_pass"] else "fail"
        v = e0_verdict(r, th.get("e0"))
        if v is not None:
            out[("E0", None)][job] = v
    return out, note


def count(verdicts: list[str]) -> tuple[int, int, int]:
    """n, rejected (anything but pass), inconclusive."""
    return len(verdicts), sum(v != "pass" for v in verdicts), sum(v == "inconclusive" for v in verdicts)


def pooled(runs: list[Run], th: dict) -> tuple[dict, dict]:
    """(evidence, k) -> list of verdicts over (run, job); and the tau notes."""
    out, notes = defaultdict(list), {}
    for r in runs:
        jv, nt = job_verdicts(r, th)
        for key, d in jv.items():
            out[key].extend(d.values())
        notes.update(nt)
    return out, notes


def ev_order(key) -> tuple:
    ev, k = key
    return ({"E0": 0, "E0-N": 1, "E1": 2, "E1.image": 3, "E2-H.tierA": 4, "E2-H": 5, "E2-W": 6}.get(ev, 9), k or 0)


def ids(runs: list[Run]) -> str:
    return ";".join(sorted({i for r in runs for i in r.ids}))


def group(runs: list[Run], key) -> dict:
    g = defaultdict(list)
    for r in runs:
        g[key(r)].append(r)
    return dict(sorted(g.items(), key=lambda t: tuple("" if x is None else str(x) for x in t[0])))


def fmt_s(s) -> str:
    return "" if s is None else f"{s:g}"


# ------------------------------------------------------------------------------------------- tables
def table_honest_fpr(honest: list[Run], th: dict) -> list[list]:
    out = []
    strata = list(group(honest, lambda r: (r.model, r.sampler, r.pair)).items())
    strata += [((m, sp, "pooled"), rs) for (m, sp), rs in group(honest, lambda r: (r.model, r.sampler)).items()]
    for (model, sampler, pair), rs in strata:
        vs, _ = pooled(rs, th)
        for key in sorted(vs, key=ev_order):
            n, rej, inc = count(vs[key])
            lo, hi = wilson(rej, n)
            out.append([model, sampler, pair, key[0], key[1] if key[1] is not None else "", n, rej, inc,
                        rej / n if n else "", lo, hi, cp_upper(rej, n), ids(rs)])
    return out


def table_sensitivity(attacked: list[Run], honest: list[Run], th: dict) -> list[list]:
    out = []
    hp = {k: pooled(rs, th)[0] for k, rs in group(honest, lambda r: (r.model, r.sampler)).items()}
    hids = {k: ids(rs) for k, rs in group(honest, lambda r: (r.model, r.sampler)).items()}
    for (attack, s, model, sampler), rs in group(attacked, lambda r: (r.attack, r.s, r.model, r.sampler)).items():
        vs, notes = pooled(rs, th)
        hv = hp.get((model, sampler), {})
        for key in sorted(vs, key=ev_order):
            n, rej, inc = count(vs[key])
            lo, hi = wilson(rej, n)
            hn, hrej, _ = count(hv.get(key, []))
            flo, fhi = wilson(hrej, hn) if hn else ("", "")
            fpr = hrej / hn if hn else ""
            out.append([attack, fmt_s(s), model, sampler, key[0], key[1] if key[1] is not None else "", n, rej, inc,
                        rej / n if n else "", lo, hi, hn, hrej, fpr, fhi,
                        int(fpr <= 0.01) if hn else "", notes.get(key, ""), ";".join(sorted({r.pair for r in rs})),
                        th.get("version"), th.get("_sha256"), ids(rs), hids.get((model, sampler), "")])
    return out


def table_acceptance(attacked: list[Run], honest: list[Run], th: dict) -> list[list]:
    out = []
    cells = [(("honest", None, m, sp), rs) for (m, sp), rs in group(honest, lambda r: (r.model, r.sampler)).items()]
    cells += list(group(attacked, lambda r: (r.attack, r.s, r.model, r.sampler)).items())
    for (attack, s, model, sampler), rs in cells:
        vs, _ = pooled(rs, th)
        for key in (("E0-N", None), ("E2-W", 3)):
            if key not in vs:
                warn(f"{attack} {model}: no {key[0]} verdicts" + (" (pass --compare)" if key[0] == "E0-N" else ""))
                continue
            n, rej, _ = count(vs[key])
            lo, hi = wilson(n - rej, n)
            out.append([attack, fmt_s(s), model, sampler, key[0], n, n - rej, (n - rej) / n if n else "", lo, hi,
                        ids(rs)])
    return out


def faked_set(run: Run, job: str) -> set[int] | None | bool:
    """Faked step indices; None = every step; False = label missing."""
    if run.attack == "honest":
        return set()
    if run.attack not in S_ATTACKS:
        return None
    lab = run.source / "raw" / "labels" / f"{job}.json" if run.source else None
    if lab is None or not lab.exists():
        return False
    return set(json.loads(lab.read_text()).get("faked", []))


def checked_steps(run: Run, th: dict):
    """Yield (k, over_tau, source) for each checked step of interest (faked steps; every step if honest)."""
    metric = th["tier_b_metric"]
    seen: dict = {}
    k1 = []
    for (job, ev, k), r in run.rows.items():
        if ev != "E2-H" or r.get("tier_b") is None:
            continue
        if r.get("per_step"):
            for i, x in r["per_step"].items():
                seen[(job, int(i))] = step_value(x, metric)
        elif k == 1 and len(r.get("steps") or []) == 1:
            k1.append((job, r["steps"][0], r["tier_b"] == "fail"))
    missing = set()
    if seen:
        for (job, i), v in seen.items():
            f = faked_set(run, job)
            if f is False:
                missing.add(job)
                continue
            if run.attack == "honest" or f is None or i in f:
                for k in KS:
                    yield k, v > tau_k(th, k, i), "per_step"
    else:
        for job, i, over in k1:
            f = faked_set(run, job)
            if f is False:
                missing.add(job)
                continue
            if run.attack == "honest" or f is None or i in f:
                yield th.get("k"), over, f"k1_rows (tau of k={th.get('k')})"
    if missing:
        warn(f"{run.run_id}: {len(missing)} jobs without labels left out of r_A")


def rates(runs: list[Run], th: dict) -> dict:
    """k -> [n_steps, n_over, sources]."""
    acc: dict = {}
    for r in runs:
        for k, over, src in checked_steps(r, th):
            a = acc.setdefault(k, [0, 0, set()])
            a[0] += 1
            a[1] += over
            a[2].add(src)
    return acc


def table_rates(attacked: list[Run], honest: list[Run], th: dict) -> list[list]:
    out = []
    cells = [(("honest", None, m, sp), rs) for (m, sp), rs in group(honest, lambda r: (r.model, r.sampler)).items()]
    cells += list(group(attacked, lambda r: (r.attack, r.s, r.model, r.sampler)).items())
    for (attack, s, model, sampler), rs in cells:
        for k, (n, over, src) in sorted(rates(rs, th).items(), key=lambda t: t[0] or 0):
            lo, hi = wilson(over, n)
            out.append(["honest_alpha_s" if attack == "honest" else "r_A", attack, fmt_s(s), model, sampler, k, n, over,
                        over / n if n else "", lo, hi, alpha_nominal(th, k), ";".join(sorted(src)), ids(rs)])
    return out


def timing(run: Run) -> dict:
    rows = jl(run.source / "jobs.jsonl") if run.source else []
    return {r["job"]: r for r in rows[1:]}  # the first job of a run is the warm-up


def load_gen(path) -> Run:
    """A generation run used only for its timings (the honest baseline ``*-wp3-base-*``, a ``pilot gen`` run)."""
    path = Path(path)
    if not (path / "jobs.jsonl").exists():
        raise SystemExit(f"{path}: no jobs.jsonl (--baseline takes generation runs)")
    m = json.loads((path / "manifest.json").read_text())
    if m.get("attack") not in (None, "honest"):
        raise SystemExit(f"{path}: an attack run ({m['attack']}) cannot be the honest baseline")
    sampler = (m.get("claimed") or {}).get("sampler") or m.get("sampler") or "unknown"
    return Run(path.name, path, "honest", None, model_label(m), sampler, gpu_label(m), "", None, path.name, path)


def table_beta(attacked: list[Run], honest: list[Run], n_boot: int) -> list[list]:
    out = []
    ht: dict = defaultdict(lambda: defaultdict(list))  # (model, provider) -> job -> [(row, run_id)]
    for h in honest:
        for job, r in timing(h).items():
            ht[(h.model, h.provider)][job].append((r, h.source_id))
    for (attack, s, model, prov), rs in group(attacked, lambda r: (r.attack, r.s, r.model, r.provider)).items():
        at = [(job, r, a.source_id) for a in rs for job, r in timing(a).items()]
        if at and all("t_honest_sample_s" in r and "t_sample_s" in r for _, r, _ in at):
            # paired in one process (attacks.run --pair-honest): the honest generation of the same job, timed on
            # the same field right before or after the attack, alternating per job
            ta = [float(r["t_sample_s"]) for _, r, _ in at]
            th_ = [float(r["t_honest_sample_s"]) for _, r, _ in at]
            beta = [1 - x / y for x, y in zip(ta, th_)]
            clusters = [r.get("prompt_id", job.split("_")[0]) for job, r, _ in at]
            lo, hi = cluster_bootstrap_median(beta, clusters, n_boot=n_boot)
            ids_ = ";".join(sorted({sid for _, _, sid in at if sid}))
            out.append([attack, fmt_s(s), model, prov, len(at), statistics.median(beta), lo, hi,
                        statistics.median(ta), statistics.median(th_), "t_sample_s/t_honest_sample_s (paired)", n_boot,
                        ids_, ids_])
            continue
        hj = ht.get((model, prov), {})
        matched = [(job, r, sid, hj[job]) for job, r, sid in at if job in hj]
        if not matched:
            warn(f"beta {attack} {fmt_s(s)} {model} {prov}: no honest run on the same card with the same jobs")
            continue
        pair = next(((fa, fh) for fa, fh in TIME_FIELDS
                     if all(fa in r for _, r, _, _ in matched) and all(fh in x for *_, hs in matched for x, _ in hs)),
                    None)
        if pair is None:
            warn(f"beta {attack} {fmt_s(s)} {model} {prov}: no time field common to every matched job")
            continue
        fa, fh = pair
        ta = [float(r[fa]) for _, r, _, _ in matched]
        th_ = [statistics.median(float(x[fh]) for x, _ in hs) for *_, hs in matched]
        beta = [1 - a / h for a, h in zip(ta, th_)]
        clusters = [r.get("prompt_id", job.split("_")[0]) for job, r, _, _ in matched]
        lo, hi = cluster_bootstrap_median(beta, clusters, n_boot=n_boot)
        hids = sorted({sid for *_, hs in matched for _, sid in hs if sid})
        out.append([attack, fmt_s(s), model, prov, len(matched), statistics.median(beta), lo, hi,
                    statistics.median(ta), statistics.median(th_), f"{fa}/{fh}", n_boot,
                    ";".join(sorted({sid for _, _, sid, _ in matched if sid})), ";".join(hids)])
    return out


def table_partial(sweep: list[Run], honest: list[Run], th: dict) -> list[list]:
    out = []
    for (attack, s, model, sampler), rs in group(sweep, lambda r: (r.attack, r.s, r.model, r.sampler)).items():
        vs, _ = pooled(rs, th)
        rr = rates(rs, th)
        per_step = any("per_step" in v[2] for v in rr.values())
        for k in KS:
            if ("E2-H", k) not in vs:
                continue
            n, rej, _ = count(vs[("E2-H", k)])
            # the tau a k-step verdict really used: tau_by_k[k] if recomputed, else the frozen k's for every k
            kt = k if per_step else th.get("k")
            ns, over, _ = rr.get(kt, (0, 0, set()))
            out.append([attack, fmt_s(s), k, n, rej, alpha_nominal(th, kt), over / ns if ns else "",
                        f"tau of k={kt}" + ("" if ns else "; no labelled steps"), model, sampler, ids(rs)])
    return out


def write(path: Path, header: list[str], rows: list[list], partial: bool) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header + (["partial"] if partial else []))
        for r in rows:
            w.writerow([("" if x is None else x) for x in r] + ([1] if partial else []))
    print(f"{len(rows)} rows -> {path}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--honest", nargs="+", required=True)
    ap.add_argument("--attacked", nargs="*", default=[])
    ap.add_argument("--sweep", nargs="*", default=[])
    ap.add_argument("--baseline", nargs="*", default=[],
                    help="honest generation runs timed on the attacked job set (beta_A); default: the --honest runs' sources")
    ap.add_argument("--thresholds", required=True)
    ap.add_argument("--th-sha256", default=None)
    ap.add_argument("--compare", default=None, help="folder of pilot compare --e0-out files <run_a>__<run_b>.e0.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--partial", action="store_true", help="mark every row partial=1 (data still coming in)")
    a = ap.parse_args(argv)
    WARN.clear()
    th = load_thresholds(a.thresholds, a.th_sha256)
    honest, attacked, sweep = ([load_run(p) for p in ps] for ps in (a.honest, a.attacked, a.sweep))
    allruns = honest + attacked + sweep
    bad = [r.run_id for r in allruns if r.th_sha != th["_sha256"]]
    if bad:
        raise SystemExit(f"these verify runs did not use {a.thresholds} (sha256 {th['_sha256'][:12]}): {bad}")
    wrong = [r.run_id for r in honest if r.attack != "honest"] + [r.run_id for r in attacked + sweep
                                                                   if r.attack == "honest"]
    if wrong:
        raise SystemExit(f"runs in the wrong list (honest vs attacked): {wrong}")
    attach_e0(allruns, a.compare)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    write(out / "honest_fpr.csv", ["model", "sampler", "stratum", "evidence", "k", "n_jobs", "n_rejected",
                                    "n_inconclusive", "fpr", "ci_lo", "ci_hi", "upper_1s_exact95", "run_ids"],
          table_honest_fpr(honest, th), a.partial)
    write(out / "r2_3_sensitivity.csv", ["attack", "s", "model", "sampler", "evidence", "k", "n_jobs", "n_rejected",
                                         "n_inconclusive", "q", "q_ci_lo", "q_ci_hi", "honest_n", "honest_rejected",
                                         "fpr", "fpr_ci_hi", "fpr_le_1pct", "tau_k", "pairs", "thresholds_version",
                                         "thresholds_sha256", "run_ids", "honest_run_ids"],
          table_sensitivity(attacked, honest, th), a.partial)
    write(out / "r2_5_acceptance.csv", ["attack", "s", "model", "sampler", "rule", "n_jobs", "n_accepted",
                                        "acceptance", "ci_lo", "ci_hi", "run_ids"],
          table_acceptance(attacked, honest, th), a.partial)
    write(out / "r2_6_rates.csv", ["quantity", "attack", "s", "model", "sampler", "k", "n_steps", "n_over_tau", "rate",
                                   "ci_lo", "ci_hi", "alpha_s_nominal", "source", "run_ids"],
          table_rates(attacked, honest, th), a.partial)
    write(out / "r2_4_beta.csv", ["attack", "s", "model", "provider", "n_matched", "beta_median", "beta_ci_lo",
                                  "beta_ci_hi", "t_attack_median_s", "t_honest_median_s", "time_fields", "n_boot",
                                  "run_ids", "honest_run_ids"],
          table_beta(attacked, [load_gen(p) for p in a.baseline] or honest, a.n_boot), a.partial)
    write(out / "fig_r2_7_partial.csv", ["attack", "s", "k", "n_jobs", "n_detected", "alpha_s", "r_measured",
                                         "alpha_s_source", "model", "sampler", "run_ids"],
          table_partial(sweep, honest, th), a.partial)
    (out / "inputs.json").write_text(json.dumps({
        "thresholds": Path(a.thresholds).name, "thresholds_sha256": th["_sha256"], "thresholds_version": th.get("version"),
        "honest": [r.run_id for r in honest], "attacked": [r.run_id for r in attacked], "sweep": [r.run_id for r in sweep],
        "compare_files": sorted({x for r in allruns for x in r.e0_refs}), "partial": a.partial, "warnings": WARN,
    }, indent=1) + "\n")


if __name__ == "__main__":
    main()
