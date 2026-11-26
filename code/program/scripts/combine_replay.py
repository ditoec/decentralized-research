#!/usr/bin/env python3
"""Combine a Devnet replay run with its top-up run(s) into one per-path summary.

    python3 scripts/combine_replay.py MAIN_RUN_DIR [TOPUP_RUN_DIR ...] [--client-outage START/END "NOTE"]

--client-outage takes a UTC window (ISO times) in which the client's own network was known to be down
or changing; failed jobs inside it are counted as client-side, not as Devnet unreliability.

Writes MAIN_RUN_DIR/combined_summary.json and MAIN_RUN_DIR/SUMMARY.md. Statistics are computed from
the raw per-transaction records (txs.jsonl) of the successful jobs only. Failed jobs are kept and
counted per path and per error type, as a Devnet reliability figure. A run without jobs.jsonl (written
by replay.ts before 2026-11-26 17:30 UTC) has its failed jobs read from logs/errors.log, and its
successful jobs are the jobs with records in txs.jsonl. That run did not write a failed job's partial
transactions. Quantiles use the same rule as replay.ts: the sorted value at index floor(q * n).
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PATHS = ["unsampled", "pass", "dispute", "timeout"]


def q(xs, p):
    s = sorted(xs)
    return s[min(len(s) - 1, int(p * len(s)))] if s else None


def stats(xs):
    xs = list(xs)
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "mean": round(sum(xs) / len(xs), 2), "min": min(xs), "median": q(xs, 0.5),
            "p95": q(xs, 0.95), "max": max(xs)}


def error_type(msg):
    first = msg.strip().split("\n")[0]
    m = re.search(r"custom program error: (0x[0-9a-f]+)", first)
    if m:
        return f"program error {m.group(1)}"
    return first[:80]


def load(run):
    run = Path(run)
    txs = [json.loads(l) for l in open(run / "txs.jsonl")]
    jobs = []  # (path, job_id, ok, error, time)
    if (run / "jobs.jsonl").exists():
        for l in open(run / "jobs.jsonl"):
            j = json.loads(l)
            jobs.append((j["path"], j["job_id"], j["ok"], j.get("error"), j.get("time")))
    else:
        seen = {}
        for t in txs:
            if not t.get("failed_job"):
                seen[(t["path"], t["job_id"])] = True
        jobs += [(p, i, True, None, None) for (p, i) in seen]
        err = run / "logs" / "errors.log"
        ok_ids = {i for (_, i) in seen}
        logged = set()
        if err.exists():
            for l in open(err):
                m = re.match(r"(\S+) job (-?\d+) (\w+): (.*)", l)
                if m:
                    t, i, msg = m.group(1), int(m.group(2)), m.group(4)
                    # the old replay logged a failure before create_job under the previous job's id: an id that
                    # already belongs to a successful job, or one logged twice, marks such a failure
                    if i in ok_ids or i in logged:
                        msg = "before create_job: " + msg
                    logged.add(i)
                    jobs.append((m.group(3), i, False, msg, t))
    summ = json.load(open(run / "summary.json")) if (run / "summary.json").exists() else None
    return run, txs, jobs, summ


def main():
    argv = sys.argv[1:]
    outage = None
    if "--client-outage" in argv:
        k = argv.index("--client-outage")
        start, end = argv[k + 1].split("/")
        outage = {"start": start, "end": end, "note": argv[k + 2]}
        del argv[k:k + 3]
    runs = [load(r) for r in argv]
    main_dir = runs[0][0]
    in_outage = lambda t: bool(outage and t and outage["start"] <= t.replace("+00:00", "Z") <= outage["end"])
    out = {"runs": [r[0].name for r in runs], "cluster": "devnet",
           "note": "statistics over the successful jobs' transactions; failed jobs counted separately, split into "
                   "client-side (inside a known client network outage) and the rest",
           "client_outage": outage, "paths": {}}
    for p in PATHS:
        ok_ids, failed, failed_client = set(), defaultdict(int), defaultdict(int)
        recs = []
        for run, txs, jobs, summ in runs:
            ok = {(run.name, i) for (pp, i, k, _, _) in jobs if pp == p and k}
            ok_ids |= ok
            for (pp, i, k, e, t) in jobs:
                if pp == p and not k:
                    (failed_client if in_outage(t) else failed)[error_type(e or "unknown")] += 1
            recs += [t for t in txs if t["path"] == p and (run.name, t["job_id"]) in ok and not t.get("failed_job")]
        per_job = defaultdict(list)
        for t in recs:
            per_job[t["job_id"]].append(t)
        n_dev, n_cli = sum(failed.values()), sum(failed_client.values())
        out["paths"][p] = {
            "n_jobs": len(ok_ids) + n_dev + n_cli,
            "n_ok": len(ok_ids),
            "n_failed": n_dev + n_cli,
            "n_failed_client_side": n_cli,
            "n_failed_other": n_dev,
            "failure_rate_excluding_client_side": round(n_dev / (len(ok_ids) + n_dev), 4) if ok_ids or n_dev else None,
            "failures_by_error_client_side": dict(failed_client),
            "failures_by_error_other": dict(failed),
            "n_tx": len(recs),
            "tx_per_job": stats(len(v) for v in per_job.values()),
            "signatures_per_job": stats(sum(t["nsig"] for t in v) for v in per_job.values()),
            "compute_units_per_job": stats(sum(t["cu"] or 0 for t in v) for v in per_job.values()),
            "compute_units_per_tx_mean": round(sum(t["cu"] or 0 for t in recs) / len(recs), 1) if recs else None,
            "fee_lamports_per_job": stats(sum(t["fee"] or 0 for t in v) for v in per_job.values()),
            "fee_lamports_per_tx": stats(t["fee"] for t in recs if t["fee"] is not None),
            "ms_to_confirmed_per_tx": stats(t["ms_confirmed"] for t in recs),
            "ms_to_confirmed_per_tx_no_429": stats(t["ms_confirmed"] for t in recs if not t.get("rpc_429")),
            "n_tx_with_rpc_429": sum(1 for t in recs if t.get("rpc_429")),
            "n_tx_missing_meta": sum(1 for t in recs if t["cu"] is None or t["fee"] is None),
        }
    (main_dir / "combined_summary.json").write_text(json.dumps(out, indent=1) + "\n")

    lines = [f"# Devnet replay: combined summary ({', '.join(out['runs'])})", "",
             "Generated by `code/program/scripts/combine_replay.py` from the raw records. Statistics cover the",
             "successful jobs; failed jobs are counted per error type. Confirm time is wall-clock from send to",
             "`confirmed` over the public RPC, polled about every 0.45 s; \"no 429\" leaves out the transactions",
             "that met a rate-limit answer on the way.", "",
             "| Path | Jobs | OK | Failed (client-side / other) | Confirm median / p95 (ms) | No 429: median / p95 (ms) | Mean CU per tx | CU per job (median) | Signatures per job | Fee per job (lamports) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for p, v in out["paths"].items():
        c, c0 = v["ms_to_confirmed_per_tx"], v["ms_to_confirmed_per_tx_no_429"]
        lines.append(f"| {p} | {v['n_jobs']} | {v['n_ok']} | {v['n_failed_client_side']} / {v['n_failed_other']} | {c.get('median')} / {c.get('p95')} | "
                     f"{c0.get('median')} / {c0.get('p95')} | {v['compute_units_per_tx_mean']} | "
                     f"{v['compute_units_per_job'].get('median')} | {v['signatures_per_job'].get('median')} | "
                     f"{v['fee_lamports_per_job'].get('median')} |")
    lines += ["", "Failures by error type:", ""]
    if outage:
        lines += [f"Client-side window {outage['start']} to {outage['end']}: {outage['note']}", ""]
    for p, v in out["paths"].items():
        cli = ", ".join(f"{k} × {n}" for k, n in v["failures_by_error_client_side"].items()) or "none"
        oth = ", ".join(f"{k} × {n}" for k, n in v["failures_by_error_other"].items()) or "none"
        lines.append(f"- {p}: client-side {cli}; other {oth}")
    (main_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
