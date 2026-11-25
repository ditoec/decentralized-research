"""End-to-end orchestrator run on a local validator: relay -> trajescrow program, verifier through a
subprocess with trajver.verify's CLI (stand-in module, no GPU). Covers unsampled, pass, slash and
timeout paths. Opt-in: it rewrites the program's (singleton) Config, so do not run it while another
client uses the same validator.

    code/program/scripts/local-validator.sh &        # after code/program/scripts/build.sh
    TRAJESCROW_LOCALNET=1 python -m pytest -m localnet tests/integration/test_orchestrator_localnet.py
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

from orchestrator.assign import Assigner, Node
from orchestrator.events import EventLog
from orchestrator.relay import Relay
from orchestrator.reputation import Reputation
from orchestrator.service import JobRequest, Orchestrator, ProviderResult
from orchestrator.verifier import TrajverVerifier

pytestmark = [
    pytest.mark.localnet,
    pytest.mark.skipif(os.environ.get("TRAJESCROW_LOCALNET") != "1", reason="set TRAJESCROW_LOCALNET=1"),
]
URL = os.environ.get("TRAJESCROW_RPC", "http://127.0.0.1:8899")
SOLBIN = Path.home() / ".local/share/solana/install/active_release/bin"


def keygen(path: Path):
    subprocess.run([str(SOLBIN / "solana-keygen"), "new", "--no-bip39-passphrase", "-s", "-f", "-o", str(path)],
                   check=True, capture_output=True)


def test_orchestrator_paths(tmp_path):
    names = ["orchestrator", "req", "pod1", "spark1", "spark2"]
    keys = {"admin": str(Path.home() / ".config/solana/id.json")}
    for n in names:
        keygen(tmp_path / f"{n}.json")
        keys[n] = str(tmp_path / f"{n}.json")
    (tmp_path / "keys.json").write_text(json.dumps(keys))
    relay = Relay(URL, tmp_path / "keys.json")
    try:
        pk = relay.call("pubkeys")["pubkeys"]
        cfg = dict(orchestrator=pk["orchestrator"], drawDelay=2, execTimeout=40, disputeTimeout=150,
                   verifiers=[pk["spark1"], pk["spark2"]])
        relay.call("init", **{**cfg, "sampleProb": 1})
        relay.call("setup_node", node="orchestrator")
        relay.call("setup_node", node="req", tokens=10**10)
        relay.call("setup_node", node="pod1", tokens=10**9, bond=10**8)
        for v in ("spark1", "spark2"):
            relay.call("setup_node", node=v)

        verdict_of = {}  # job key -> what the stand-in verifier will find

        def execute(node, job):
            if job.spec.get("crash"):
                raise RuntimeError("provider crashed")
            run = tmp_path / "runs_src" / f"job{job.job_id}"
            run.mkdir(parents=True, exist_ok=True)
            key = f"j{job.job_id:04d}"
            verdict_of[key] = job.spec["outcome"]
            (run / "stub_verdict.json").write_text(json.dumps({key: job.spec["outcome"]}))
            return ProviderResult(f"{job.job_id:064x}", "ee" * 32, str(run), key)

        tv = TrajverVerifier(args=[], k=3, runs_root=tmp_path / "verify_runs", module="tests.integration.stub_verify")
        rep = Reputation(tmp_path / "reputation.json")
        log = EventLog(tmp_path / "events.jsonl")
        nodes = [Node("pod1", {"provider"}), Node("spark1", {"verifier"}), Node("spark2", {"verifier"})]
        o = Orchestrator(relay, Assigner(nodes, rep), execute,
                         lambda v, job, res: tv.verify(v, job.job_id, res.run_dir, res.job_key), log, rep)
        base = int.from_bytes(os.urandom(4), "little") * 1000
        o.submit(JobRequest(base + 1, "req", 1_000_000, 100_000, 500_000, {"outcome": "pass"}))
        o.submit(JobRequest(base + 2, "req", 1_000_000, 100_000, 500_000, {"outcome": "fail"}))
        o.run()
        relay.call("init", **{**cfg, "sampleProb": 0})
        o.submit(JobRequest(base + 3, "req", 1_000_000, 100_000, 500_000, {"outcome": "pass"}))
        o.run()
        relay.call("init", **{**cfg, "sampleProb": 0, "execTimeout": 3})
        o.submit(JobRequest(base + 4, "req", 1_000_000, 100_000, 500_000, {"crash": True}))
        o.run()

        assert o.results[base + 1] == {"outcome": "pass", "state": "closedPaid", "provider": "pod1"}
        assert o.results[base + 2]["outcome"] == "fail" and o.results[base + 2]["state"] == "closedRefunded"
        assert o.results[base + 3]["outcome"] == "unsampled"
        assert o.results[base + 4]["outcome"] == "timeout" and o.results[base + 4]["state"] == "closedRefunded"
        j2 = relay.call("get_job", job_id=base + 2)["job"]
        assert j2["slashed"] and j2["settled"] and j2["verifier1"] != j2["verifier2"]
        assert pk["pod1"] not in (j2["verifier1"], j2["verifier2"])
        chain = [json.loads(l) for l in (tmp_path / "events.jsonl").read_text().splitlines()]
        assert all(e["sig"] and e["cu"] for e in chain if e["source"] == "chain")
        # reputation: +pass, then a confirmed fail, unsampled and timeout leave it unchanged
        assert rep.get("pod1") == pytest.approx((0.5 + 0.1 * 0.5) * 0.5)
    finally:
        relay.close()
