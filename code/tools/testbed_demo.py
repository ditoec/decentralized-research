#!/usr/bin/env python3
"""Testbed demo (runbook §7 item 5): the escrow lifecycle on Devnet with an honest provider and two
injected attackers, Spark verifiers, at sampling rates p in {0.05, 0.1, 0.25}.

    code/.venv/bin/python code/tools/testbed_demo.py --admin <Devnet payer keypair> [--n 50] [--k 2]

What is live and what is recorded:
- Live: every escrow transaction on Devnet (create, accept, commit, the on-chain draw, verdicts,
  escalation, release / slash / refund) through code/orchestrator and the trajescrow program; the
  verification of every sampled job by trajver.verify on a DGX Spark (Spark-5 or Spark-6), started per
  job; the second verifier on a dispute; reputation.
- Recorded: the providers' outputs. Each on-chain job is backed by one job that a rented RTX 5090
  computed earlier (class-O retention: image, Merkle root, the opened steps of its committed draw seed).
  Provider "pod-a" is honest (WP2 ref-test run), "pod-b" runs A3 with SDXL-Turbo, "pod-c" the realistic
  F2 forger at s = 0.5 (WP3 runs). The provider names on chain and the slices a verifier receives carry
  no attack label; the mapping is kept in labels.json for the analysis only.
- The on-chain draw decides WHETHER a job is checked; the checked steps are the first k of the job's
  committed retention order (the provider's draw seed was hashed into the manifest before generation).

Writes experiments/runs/<rid>/: manifest.json, events.jsonl (every transaction with signature, CU, fee,
slot, time to confirmed; every off-chain step), jobs.jsonl (one row per on-chain job), labels.json,
verify/<verify run>.jsonl (the verifier's label-free rows). Keypairs stay in code/program/.anchor/devnet/
(git-ignored); leftover SOL is swept back to the admin at the end.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))
from orchestrator.assign import Assigner, Node  # noqa: E402
from orchestrator.events import EventLog  # noqa: E402
from orchestrator.relay import Relay  # noqa: E402
from orchestrator.reputation import Reputation  # noqa: E402
from orchestrator.service import JobRequest, Orchestrator, ProviderResult  # noqa: E402
from orchestrator.verifier import VerifierOutcome, decide, strip_labels  # noqa: E402

PROVIDERS = {  # on-chain name -> (source run on the verifier Sparks, label, beta_A from r2_4_beta.csv)
    "pod-a": ("20261126-wp2-ref-test-sdxl-fp16-sdpa-euler-nd-rtx5090-01", "honest"),
    "pod-b": ("20261126-wp3-atk-a3turbo-sdxl-euler-rtx5090-01", "A3-Turbo"),
    "pod-c": ("20261127-wp3-atkr-f2-sdxl-euler-rtx5090-01", "F2"),
}
VERIFIERS = {"spark5": "aign-dgx@10.41.3.6", "spark6": "aign-dgx@10.41.3.7"}
SDXL = "/models/checkpoints/sd_xl_base_1.0.safetensors"
SDXL_SHA = "31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b"
TH = "../experiments/configs/thresholds_v1_sdxl_euler.json"
PROMPTS = "../experiments/configs/prompts_rent_test200.txt"
P, FEE, B = 1_000_000, 100_000, 1_000_000  # payment, verifier fee, bond (token units): B/P = 1
SOLBIN = Path.home() / ".local/share/solana/install/active_release/bin"


def jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def slice_id(rid: str, prov: str, job: str) -> str:
    return f"{rid[:8]}-wp5-tb-{hashlib.sha256(f'{rid}|{prov}|{job}'.encode()).hexdigest()[:10]}"


def ssh(host: str, cmd: str, timeout: float = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=30", host, cmd],
                          capture_output=True, text=True, timeout=timeout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin", required=True, help="Devnet payer keypair (program upgrade authority)")
    ap.add_argument("--rid", default=f"{dt.datetime.now(dt.timezone.utc):%Y%m%d}-wp5-testbed-01")
    ap.add_argument("--n", type=int, default=50, help="jobs per provider and sampling rate")
    ap.add_argument("--p", default="0.05,0.1,0.25")
    ap.add_argument("--k", type=int, default=2, help="checked steps (E2-H at k)")
    ap.add_argument("--prepare-only", action="store_true", help="build and copy the slices, then stop")
    a = ap.parse_args()
    ps = [float(x) for x in a.p.split(",")]
    out = ROOT / "experiments" / "runs" / a.rid
    out.mkdir(parents=True, exist_ok=True)
    (out / "verify").mkdir(exist_ok=True)

    # ---- job set: the first n jobs of the attack runs (test split, seed 0), the same keys for every provider
    jobs = [r["job"] for r in jl(ROOT / "experiments" / "runs" / PROVIDERS["pod-c"][0] / "jobs.jsonl")][: a.n]
    rec = {prov: {r["job"]: r for r in jl(ROOT / "experiments" / "runs" / src / "jobs.jsonl")}
           for prov, (src, _) in PROVIDERS.items()}
    for prov in PROVIDERS:
        missing = [j for j in jobs if j not in rec[prov]]
        assert not missing, f"{prov}: {missing[:3]} not in its source run"
    plan = [{"slice": slice_id(a.rid, prov, j), "src": src, "job": j} for prov, (src, _) in PROVIDERS.items() for j in jobs]
    (out / "slices.json").write_text(json.dumps(plan, indent=1) + "\n")
    (out / "labels.json").write_text(json.dumps(
        {"providers": {p_: {"source_run": s, "label": l} for p_, (s, l) in PROVIDERS.items()},
         "note": "ground truth for the analysis only; never sent to the orchestrator's verifier or the chain"}, indent=1) + "\n")

    # ---- slices on both verifier Sparks (sources on Spark-5; copied to Spark-6 through this machine)
    s5, s6 = VERIFIERS["spark5"], VERIFIERS["spark6"]
    subprocess.run(["scp", "-q", str(out / "slices.json"), str(ROOT / "code/tools/testbed_slices.py"), f"{s5}:esj/logs/"], check=True)
    r = ssh(s5, f"python3 ~/esj/logs/testbed_slices.py --runs ~/esj/runs --plan ~/esj/logs/slices.json")
    print(r.stdout.strip(), r.stderr.strip()[-300:])
    names = " ".join(e["slice"] for e in plan)
    have6 = ssh(s6, f"cd ~/esj/runs && ls -d {names} 2>/dev/null | wc -l").stdout.strip()
    if have6 != str(len(plan)):
        cp = subprocess.run(f"ssh {s5} 'cd ~/esj/runs && tar cf - {names}' | ssh {s6} 'cd ~/esj/runs && tar xf -'",
                            shell=True)
        assert cp.returncode == 0, "slice copy to Spark-6 failed"
    print(f"{len(plan)} slices on Spark-5 and Spark-6")
    if a.prepare_only:
        return

    # ---- keys (throwaway, git-ignored) and relay
    kd = ROOT / "code" / "program" / ".anchor" / "devnet" / f"testbed-{a.rid}"
    kd.mkdir(parents=True, exist_ok=True)
    names_ = ["orchestrator", "req", *PROVIDERS, *VERIFIERS]
    keys = {"admin": str(Path(a.admin).resolve())}
    for n in names_:
        f = kd / f"keypair-{n}.json"
        if not f.exists():
            subprocess.run([str(SOLBIN / "solana-keygen"), "new", "--no-bip39-passphrase", "-s", "-o", str(f)],
                           check=True, capture_output=True)
        keys[n] = str(f)
    (kd / "keys.json").write_text(json.dumps(keys))
    relay = Relay("devnet", kd / "keys.json")
    log = EventLog(out / "events.jsonl")
    rep = Reputation(out / "reputation.json", minimum=0.0)  # recorded, but no provider is excluded mid-measurement
    manifest = {"run_id": a.rid, "wp": "wp5", "purpose": "testbed demo, runbook §7 item 5", "cluster": "devnet",
                "program_id": "HmMX8b7GLwUeJv4dw42xHAryRVfQm319ArWNbfj9ePpf", "p": ps, "k": a.k, "n_per_cell": a.n,
                "payment": P, "verifier_fee": FEE, "bond": B, "jobs": jobs, "verifiers": list(VERIFIERS),
                "providers": list(PROVIDERS), "thresholds": "thresholds_v1_sdxl_euler.json",
                "start_time": dt.datetime.now(dt.timezone.utc).isoformat()}
    try:
        pk = relay.call("pubkeys")["pubkeys"]
        manifest["pubkeys"] = {n: pk[n] for n in names_ + ["admin"]}
        cfg = dict(orchestrator=pk["orchestrator"], drawDelay=2, execTimeout=300, disputeTimeout=3000,
                   verifiers=[pk[v] for v in VERIFIERS])
        relay.call("init", **{**cfg, "sampleProb": ps[0]})
        n_jobs = len(ps) * len(PROVIDERS) * a.n
        jobrent = 0.0045  # SOL per Job account (8 + 500 bytes, rent-exempt; never closed)
        relay.call("setup_node", node="orchestrator", sol=0.2)
        relay.call("setup_node", node="req", sol=round(n_jobs * (jobrent + 0.00005) * 1.15 + 0.05, 3), tokens=4 * 10**9)
        for prov in PROVIDERS:
            relay.call("setup_node", node=prov, sol=0.15, tokens=10**9, bond=10**9)
        for v in VERIFIERS:
            relay.call("setup_node", node=v, sol=0.08)

        def execute(prov: str, job: JobRequest) -> ProviderResult:
            r = rec[prov][job.spec["job"]]
            return ProviderResult(r["merkle_root"], r["image_sha256"], job.spec["slice"], job.spec["job"])

        def verify(vnode: str, job: JobRequest, res: ProviderResult) -> VerifierOutcome:
            vid = f"{a.rid[:8]}-wp5-tbv-{job.job_id}-{vnode}"
            cmd = (f"cd ~/esj/code && python3 tools/spark_run.py --run-id {vid} -- python -m trajver.verify "
                   f"/runs/{res.run_dir} --flags={shlex.quote('--force-fp16 --use-pytorch-cross-attention')} "
                   f"--ckpt {SDXL} --ckpt-sha256 {SDXL_SHA} --prompts {PROMPTS} --thresholds {TH} --wp wp5 "
                   f"--run-id {vid} > ~/esj/logs/{vid}.log 2>&1; cat ~/esj/runs/{vid}/verdicts.jsonl")
            err, rows = None, []
            try:
                p_ = ssh(VERIFIERS[vnode], cmd)
                rows = [strip_labels(json.loads(l)) for l in p_.stdout.splitlines() if l.strip().startswith("{")]
                if not rows:
                    err = f"no verdict rows (exit {p_.returncode}): {p_.stderr[-300:]}"
            except subprocess.TimeoutExpired:
                err = "verify timed out"
            mine = [r for r in rows if r.get("job_id") == res.job_key]
            (out / "verify" / f"{vid}.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in mine))
            verdict = "inconclusive" if err else decide(mine, res.job_key, a.k)
            blob = json.dumps(mine, sort_keys=True, separators=(",", ":")).encode()
            return VerifierOutcome(verdict, hashlib.sha256(blob).hexdigest(), vid, mine, err)

        vnodes = [Node(v, {"verifier"}) for v in VERIFIERS]
        orch = {prov: Orchestrator(relay, Assigner([Node(prov, {"provider"}), *vnodes], rep), execute, verify, log, rep)
                for prov in PROVIDERS}
        base = int(time.time()) * 1000  # Job PDAs persist on Devnet: a fresh id range per run
        rows_out = (out / "jobs.jsonl").open("a")
        jid = base
        for p_ in ps:
            relay.call("init", **{**cfg, "sampleProb": p_})
            log.emit("offchain", "phase", p=p_)
            for i, j in enumerate(jobs):
                for prov in PROVIDERS:  # interleaved, so the three providers see the same chain conditions
                    jid += 1
                    req = JobRequest(jid, "req", P, FEE, B, {"job": j, "slice": slice_id(a.rid, prov, j)})
                    t0 = time.monotonic()
                    try:
                        res = orch[prov].process(req)
                    except Exception as e:  # recorded and counted, the run continues
                        res = {"outcome": "error", "error": str(e)[:300]}
                        log.emit("offchain", "job_error", job_id=jid, error=str(e)[:300])
                        if relay.proc.poll() is not None:  # the relay process died: start a new one
                            relay = Relay("devnet", kd / "keys.json")
                            for o in orch.values():
                                o.chain = relay
                            log.emit("offchain", "relay_restarted", job_id=jid)
                    rows_out.write(json.dumps({"job_id": jid, "p": p_, "provider": prov, "job": j, **res,
                                               "s_wall": round(time.monotonic() - t0, 1)}) + "\n")
                    rows_out.flush()
                print(f"p={p_} round {i + 1}/{len(jobs)}", flush=True)
        rows_out.close()
    finally:
        swept = 0
        for n in names_:
            try:
                swept += relay.call("sweep", node=n)["swept"]
            except Exception as e:
                print("sweep", n, e)
        manifest.update(end_time=dt.datetime.now(dt.timezone.utc).isoformat(), swept_lamports=swept)
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
        relay.close()


if __name__ == "__main__":
    main()
