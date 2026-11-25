"""The orchestrator: a FIFO job queue driven through the escrow lifecycle.

For each job: create_job (requester) -> assign a provider -> accept_job -> the provider executes
and commits (Merkle root, output digest) -> draw_sample (relayed by the orchestrator) ->
unsampled: release | sampled: first verifier (never the provider) commits, then reveals its verdict
-> pass: release | fail/inconclusive: escalate, second verifier (neither provider nor first verifier)
-> release / slash / refund. A job past its deadline is refunded with timeout_refund.

Every relayed transaction and every off-chain step is written to the event log with timestamps.
"""
from __future__ import annotations

import collections
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .assign import Assigner
from .events import EventLog
from .reputation import Reputation
from .verifier import VerifierOutcome


class Chain(Protocol):
    def call(self, op: str, signer: str | None = None, **args) -> dict: ...


@dataclass
class JobRequest:
    job_id: int
    requester: str  # relay signer name
    payment: int
    verifier_fee: int
    bond: int
    spec: dict = field(default_factory=dict)


@dataclass
class ProviderResult:
    merkle_root: str  # hex, 32 bytes
    output_digest: str  # hex, 32 bytes
    run_dir: str  # trajver run folder holding the committed trajectory and the image
    job_key: str  # the job's id inside that run folder (verdicts.jsonl "job_id")


Executor = Callable[[str, JobRequest], ProviderResult]  # (provider node, job) -> result
Verify = Callable[[str, JobRequest, ProviderResult], VerifierOutcome]  # (verifier node, job, result)


class Orchestrator:
    def __init__(self, chain: Chain, assigner: Assigner, execute: Executor, verify: Verify,
                 log: EventLog, reputation: Reputation, signer: str = "orchestrator"):
        self.chain, self.assigner, self.execute, self.verify = chain, assigner, execute, verify
        self.log, self.rep, self.me = log, reputation, signer
        self.queue: collections.deque[JobRequest] = collections.deque()
        self.results: dict[int, dict] = {}

    # ---- plumbing ----
    def submit(self, job: JobRequest):
        self.queue.append(job)
        self.log.emit("offchain", "queued", job_id=job.job_id, requester=job.requester)

    def tx(self, op: str, signer: str, job_id: int, **args) -> dict:
        r = self.chain.call(op, signer, job_id=job_id, **args)
        rec = r.get("rec", {})
        job = r.get("job", {})
        self.log.emit("chain", op, job_id=job_id, signer=signer, sig=rec.get("sig"), cu=rec.get("cu"),
                      fee=rec.get("fee"), slot=rec.get("slot"), ms_confirmed=rec.get("ms_confirmed"),
                      state=job.get("state"))
        return job

    def run(self):
        while self.queue:
            self.process(self.queue.popleft())

    # ---- lifecycle ----
    def _verifier_round(self, job: JobRequest, res: ProviderResult, exclude: set[str], op: str) -> tuple[str, dict]:
        v = self.assigner.verifier(exclude)
        self.log.emit("offchain", "verifier_assigned", job_id=job.job_id, verifier=v.name, round=op)
        out = self.verify(v.name, job, res)
        self.log.emit("offchain", "verifier_done", job_id=job.job_id, verifier=v.name, verdict=out.verdict,
                      commitment=out.commitment, verify_run=out.run_id, error=out.error)
        self.tx(op, v.name, job.job_id, commitment=out.commitment)
        return v.name, self.tx(op, v.name, job.job_id, verdict=out.verdict)

    def process(self, job: JobRequest) -> dict:
        jid = job.job_id
        self.tx("create_job", job.requester, jid, payment=job.payment, verifier_fee=job.verifier_fee, bond=job.bond)
        prov = self.assigner.provider()
        prov.busy = True
        try:
            self.log.emit("offchain", "provider_assigned", job_id=jid, provider=prov.name,
                          reputation=self.rep.get(prov.name))
            self.tx("accept_job", prov.name, jid)
            try:
                res = self.execute(prov.name, job)
            except Exception as e:  # provider failed: the job stalls and is refunded after its deadline
                self.log.emit("offchain", "execution_failed", job_id=jid, provider=prov.name, error=str(e))
                return self._finish(job, prov.name, self._timeout(jid), outcome="timeout")
            self.log.emit("offchain", "executed", job_id=jid, provider=prov.name, run_dir=res.run_dir)
            self.tx("commit_result", prov.name, jid, merkle_root=res.merkle_root, output_digest=res.output_digest)
        finally:
            prov.busy = False
        j = self.tx("draw_sample", self.me, jid)
        self.log.emit("offchain", "drawn", job_id=jid, sampled=j["sampled"], draw_slot=j["draw_slot"],
                      draw_seed=j["draw_seed"])
        if not j["sampled"]:
            return self._finish(job, prov.name, self.tx("release", self.me, jid), outcome="unsampled")
        v1, j = self._verifier_round(job, res, {prov.name}, "submit_verdict")
        if j["state"] == "closedPaid":
            return self._finish(job, prov.name, self.tx("release", self.me, jid), outcome="pass")
        self.tx("escalate", self.me, jid)
        _, j = self._verifier_round(job, res, {prov.name, v1}, "final_verdict")
        if j["state"] == "closedPaid":
            return self._finish(job, prov.name, self.tx("release", self.me, jid), outcome="pass")
        if j["state"] == "closedRefunded" and j["slashed"]:
            return self._finish(job, prov.name, self.tx("slash", self.me, jid), outcome="fail")
        return self._finish(job, prov.name, self.tx("refund", self.me, jid), outcome="unresolved")

    def _timeout(self, jid: int) -> dict:
        j = self.chain.call("get_job", job_id=jid)["job"]
        deadline = j["exec_deadline"] if j["state"] == "assigned" else j["final_deadline"]
        while self.chain.call("slot")["slot"] <= deadline:
            time.sleep(0.2)
        return self.tx("timeout_refund", self.me, jid)

    def _finish(self, job: JobRequest, provider: str, j: dict, outcome: str) -> dict:
        r = self.rep.record(provider, outcome, job.job_id)
        self.log.emit("offchain", "closed", job_id=job.job_id, provider=provider, outcome=outcome,
                      state=j.get("state"), reputation=r)
        self.results[job.job_id] = {"outcome": outcome, "state": j.get("state"), "provider": provider}
        return self.results[job.job_id]
