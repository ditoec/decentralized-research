"""End-to-end settlement latency of the Devnet testbed (co-author review, 2026-11-28, point 3).

From run 20261127-wp5-testbed-01 (450 jobs: 3 providers x 3 sampling rates x 50 jobs), per job, from the
timestamps of its own events in events.jsonl (wall clock of the orchestrator host):
* escrow   create_job -> commit_result: fund, accept and commit on Devnet. The providers' outputs are the
           recorded RTX 5090 outputs of the attack study, so provider generation time is NOT included.
* draw     commit_result -> draw_sample: the fixed delay before the slot-hash draw plus its transaction.
* verify   verifier_assigned -> verifier_done, summed over the verifiers of the job (a second DGX Spark after a
           failed verdict): Tier A on the full trajectory, Tier B at k = 2, E1, on DGX Spark systems shared
           with production workloads, so these times are upper bounds for a dedicated verifier.
* chain after verify   the rest: verdict, escalation, final verdict, release or slash transactions.
* total    create_job -> closed.
Grouped by outcome (unsampled, sampled and passed, sampled and failed). Writes latency.csv and latency.json.

    python3 -P experiments/analysis/wp5/testbed/latency.py
"""
import csv
import json
import statistics as st
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RUN = "20261127-wp5-testbed-01"


def ts(e: dict) -> float:
    return datetime.fromisoformat(e["t"]).timestamp()


def q(v: list[float], p: float) -> float:
    v = sorted(v)
    return v[min(len(v) - 1, max(0, round(p * (len(v) - 1))))]


def main():
    d = ROOT / "experiments" / "runs" / RUN
    jobs = {j["job_id"]: j for j in (json.loads(l) for l in (d / "jobs.jsonl").read_text().splitlines() if l.strip())}
    ev = defaultdict(list)
    for e in (json.loads(l) for l in (d / "events.jsonl").read_text().splitlines() if l.strip()):
        if e.get("job_id") in jobs and "t" in e:
            ev[e["job_id"]].append(e)
    rows = []
    for jid, es in ev.items():
        es.sort(key=ts)
        first = {}
        for e in es:
            first.setdefault(e["event"], ts(e))
        t0, t_end = first["create_job"], first["closed"]
        verify, start = 0.0, None
        for e in es:
            if e["event"] == "verifier_assigned":
                start = ts(e)
            elif e["event"] == "verifier_done" and start is not None:
                verify += ts(e) - start
                start = None
        escrow = first["commit_result"] - t0
        draw = first["draw_sample"] - first["commit_result"]
        total = t_end - t0
        rows.append({"job_id": jid, "outcome": jobs[jid]["outcome"], "p": jobs[jid]["p"], "provider": jobs[jid]["provider"],
                     "escrow_s": escrow, "draw_s": draw, "verify_s": verify,
                     "chain_after_s": total - escrow - draw - verify, "total_s": total, "run_id": RUN})
    with open(Path(__file__).with_name("latency.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows({k: round(v, 3) if isinstance(v, float) else v for k, v in r.items()} for r in rows)
    summ = {"run_id": RUN, "n_jobs": len(rows), "by_outcome": {}}
    for oc in ("unsampled", "pass", "fail"):
        rs = [r for r in rows if r["outcome"] == oc]
        summ["by_outcome"][oc] = {"n": len(rs), **{f"{c}_median": round(st.median(r[c] for r in rs), 2)
                                                  for c in ("escrow_s", "draw_s", "verify_s", "chain_after_s", "total_s")},
                                  "total_s_p95": round(q([r["total_s"] for r in rs], 0.95), 2)}
    (Path(__file__).with_name("latency.json")).write_text(json.dumps(summ, indent=1) + "\n")
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
