"""Orchestrator logic without a chain: assignment, reputation, verdict mapping, label stripping."""
import json
import sys
from pathlib import Path

import pytest

from orchestrator.assign import Assigner, Node, NoNodeAvailable
from orchestrator.events import EventLog
from orchestrator.reputation import Reputation
from orchestrator.service import JobRequest, Orchestrator, ProviderResult
from orchestrator.verifier import TrajverVerifier, VerifierOutcome, decide, strip_labels


class FakeChain:
    """Test double of the relay: the escrow state machine reduced to what the orchestrator reads."""

    def __init__(self, sampled: bool):
        self.sampled, self.jobs, self.calls = sampled, {}, []

    def call(self, op, signer=None, **a):
        self.calls.append((op, signer, a))
        jid = a.get("job_id")
        j = self.jobs.setdefault(jid, {"state": None, "slashed": False, "v1": None})
        if op == "create_job":
            j["state"] = "funded"
        elif op == "accept_job":
            j["state"], j["provider"] = "assigned", signer
        elif op == "commit_result":
            j["state"] = "committed"
        elif op == "draw_sample":
            j.update(state="underVerification" if self.sampled else "closedPaid", sampled=self.sampled,
                     draw_slot=1, draw_seed="00" * 32)
        elif op in ("submit_verdict", "final_verdict") and "verdict" in a:
            assert signer != j["provider"], "a node verified its own job"
            v = a["verdict"]
            if op == "submit_verdict":
                j["v1"] = v
                j["state"] = "closedPaid" if v == "pass" else "disputed"
            elif v == "pass":
                j["state"] = "closedPaid"
            elif v == "fail" and j["v1"] == "fail":
                j["state"], j["slashed"] = "closedRefunded", True
            else:
                j["state"] = "closedUnresolved"
        return {"ok": True, "rec": {"sig": f"sig{len(self.calls)}", "cu": 1}, "job": dict(j)}


def make(sampled, verdicts, nodes=None):
    rep = Reputation()
    nodes = nodes or [Node("pod1", {"provider"}), Node("spark1", {"verifier"}), Node("spark2", {"verifier"}),
                      Node("both", {"provider", "verifier"})]
    seen: dict = {}

    def verify(node, job, res):  # the i-th verifier round of each job gets verdicts[i]
        i = seen[job.job_id] = seen.get(job.job_id, -1) + 1
        return VerifierOutcome(verdicts[i], "ab" * 32, f"r-{node}", [])

    def execute(node, job):
        return ProviderResult("11" * 32, "22" * 32, "run", "j0000")

    chain = FakeChain(sampled)
    o = Orchestrator(chain, Assigner(nodes, rep), execute, verify, EventLog(), rep)
    return o, chain, rep


@pytest.mark.parametrize("sampled,verdicts,outcome,settle", [
    (False, [], "unsampled", "release"),
    (True, ["pass"], "pass", "release"),
    (True, ["fail", "pass"], "pass", "release"),
    (True, ["fail", "fail"], "fail", "slash"),
    (True, ["fail", "inconclusive"], "unresolved", "refund"),
    (True, ["inconclusive", "fail"], "unresolved", "refund"),
])
def test_paths(sampled, verdicts, outcome, settle):
    o, chain, rep = make(sampled, verdicts)
    for i in range(4):
        o.submit(JobRequest(i, "req", 10, 1, 5))
    o.run()
    for i in range(4):
        assert o.results[i]["outcome"] == outcome
    ops = [c[0] for c in chain.calls if c[2].get("job_id") == 0]
    assert ops[-1] == settle
    if len(verdicts) == 2:
        assert "escalate" in ops
        # commit before reveal, for both verifiers
        vs = [c for c in chain.calls if c[0] in ("submit_verdict", "final_verdict") and c[2]["job_id"] == 0]
        assert ["commitment" in c[2] for c in vs] == [True, False, True, False]
        assert vs[0][1] != vs[2][1], "second verifier must differ from the first"
    events = [e["event"] for e in o.log.events]
    assert events.count("closed") == 4 and all("t" in e for e in o.log.events)


def test_never_verifies_itself():
    # the dual-role node provides every job here, so only spark1/spark2 may verify
    nodes = [Node("both", {"provider", "verifier"}), Node("spark1", {"verifier"}), Node("spark2", {"verifier"})]
    a = Assigner(nodes, Reputation())
    for _ in range(10):
        assert a.verifier({"both"}).name != "both"
        assert a.verifier({"both", "spark1"}).name == "spark2"
    with pytest.raises(NoNodeAvailable):
        a.verifier({"both", "spark1", "spark2"})


def test_reputation_and_exclusion():
    rep = Reputation(minimum=0.2)
    assert rep.get("p") == 0.5
    assert rep.record("p", "pass") == pytest.approx(0.55)
    rep.record("p", "unsampled")
    assert rep.get("p") == pytest.approx(0.55)
    rep.record("p", "fail")
    rep.record("p", "fail")
    assert rep.get("p") == pytest.approx(0.1375)
    a = Assigner([Node("p", {"provider"})], rep)
    with pytest.raises(NoNodeAvailable):
        a.provider()


def test_labels_are_dropped_and_verdict_mapping():
    row = {"job_id": "j1", "attack": "honest", "s": 0.0, "evidence": "E2-H", "k": 3, "verdict": "fail", "score": 2.0}
    clean = strip_labels(row)
    assert "attack" not in clean and "s" not in clean
    rows = [clean, {"job_id": "j1", "evidence": "E2-H", "k": 5, "verdict": "pass"},
            {"job_id": "j1", "evidence": "E2-W", "k": 3, "verdict": "pass"}]
    assert decide(rows, "j1", 3) == "fail"
    assert decide(rows, "j1", 5) == "pass"
    assert decide(rows, "j1", 8) == "inconclusive"
    assert decide(rows, "j2", 3) == "inconclusive"


def test_trajver_verifier_invocation(tmp_path):
    v = TrajverVerifier(args=["--ckpt", "m.safetensors", "--prompts", "p.txt"], k=3, runs_root=tmp_path,
                        prefix={"spark1": ["remote-shell", "spark1"]})
    cmd = v.command("spark1", "/runs/x", "rid")
    assert cmd[:2] == ["remote-shell", "spark1"]
    assert cmd[3:5] == ["-m", "trajver.verify"] and "--run-id" in cmd and cmd[-4:] == ["--ckpt", "m.safetensors", "--prompts", "p.txt"]


def test_trajver_verifier_end_to_end_with_stand_in(tmp_path):
    """Runs the verifier through a subprocess with a stand-in module that has trajver.verify's CLI and
    output format; its rows carry an "attack" label that must not influence the verdict."""
    v = TrajverVerifier(args=[], k=3, runs_root=tmp_path, module="tests.integration.stub_verify")
    run = tmp_path / "src"
    run.mkdir()
    (run / "stub_verdict.json").write_text(json.dumps({"j7": "pass"}))
    out = v.verify("spark1", 7, str(run), "j7")
    assert out.error is None and out.verdict == "pass"
    assert all("attack" not in r for r in out.rows)
    (run / "stub_verdict.json").write_text(json.dumps({"j7": "fail"}))
    assert v.verify("spark2", 7, str(run), "j7").verdict == "fail"
    assert v.verify("spark3", 7, str(tmp_path / "missing"), "j7").verdict == "inconclusive"
