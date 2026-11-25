# orchestrator: minimal testbed service for RQ3 (WP5)

This is the service of runbook `docs/07-runbook.md` §7 item 2. It drives jobs through the
`trajescrow` program (`code/program`) and delegates verification to the existing verifier,
`python -m trajver.verify`. Verification logic is not reimplemented here.

| Module | What it does |
|---|---|
| `service.py` | `Orchestrator`: FIFO queue. It runs each job through create → assign → accept → execute → commit → draw → (verifier 1 → escalate → verifier 2) → release / slash / refund. A provider failure ends in `timeout_refund` after the deadline. |
| `assign.py` | Node registry and assignment. Rented cards are providers and Sparks are verifiers. A node never verifies a job it provided, and verifier 2 is never verifier 1. Providers below the reputation minimum get no jobs. |
| `relay.py` | Transaction relay. It runs `code/program/scripts/relay.ts` as a long-lived process and talks to it in JSON lines. Mainnet URLs are refused. |
| `verifier.py` | `TrajverVerifier` runs `python -m trajver.verify RUN --wp wp5 --run-id … <args>` (optionally behind a per-node command prefix that is given at run time and kept out of the repo). It reads `verdicts.jsonl`, **drops the `attack` / `s` label fields first**, and maps the job's E2-H verdict at the configured k to pass / fail. A failed run or a missing row maps to inconclusive. The on-chain commitment is the SHA-256 of the verifier's own label-free rows. |
| `events.py` | Append-only JSON-lines event log. Every relayed transaction (`source: chain`, with signature, CU, fee, slot and time to confirmed) and every off-chain step (`source: offchain`: queued, assigned, executed, verifier done, drawn, closed) gets a UTC wall-clock and a monotonic timestamp. |
| `reputation.py` | Per-provider reputation. It starts at 0.5. A verified pass applies r ← r + 0.1(1 − r), a confirmed fail (bond slashed) applies r ← 0.5 r, and the minimum is 0.2. It is used for the testbed only, not for the RQ2 metrics. |

## Usage

```python
from orchestrator.assign import Assigner, Node
from orchestrator.events import EventLog
from orchestrator.relay import Relay
from orchestrator.reputation import Reputation
from orchestrator.service import JobRequest, Orchestrator
from orchestrator.verifier import TrajverVerifier

relay = Relay("http://127.0.0.1:8899", "keys.json")   # keys.json: signer name -> keypair file (untracked)
tv = TrajverVerifier(args=["--ckpt", CKPT, "--prompts", PROMPTS, "--thresholds", TH, "--th-sha256", TH_SHA], k=3)
rep, log = Reputation("reputation.json"), EventLog("events.jsonl")
nodes = [Node("pod-4090", {"provider"}), Node("spark-a", {"verifier"}), Node("spark-b", {"verifier"})]
o = Orchestrator(relay, Assigner(nodes, rep), execute,
                 lambda v, job, res: tv.verify(v, job.job_id, res.run_dir, res.job_key), log, rep)
o.submit(JobRequest(job_id, "requester", payment, verifier_fee, bond, spec))
o.run()
```

`execute(provider, job) -> ProviderResult(merkle_root, output_digest, run_dir, job_key)` is the hook
for the provider side. In the testbed demo (§7 item 5) it starts the pinned ComfyUI workflow with
the trajectory-commit node on the rented pod. That hook is not part of this step.

## Tests

```bash
cd code
python -m pytest tests/unit/test_orchestrator.py                 # no chain, no GPU
TRAJESCROW_LOCALNET=1 python -m pytest -m localnet \
  tests/integration/test_orchestrator_localnet.py                # local validator (code/program/scripts/local-validator.sh)
```

The local-validator test runs the unsampled, pass, slash and timeout paths through the real relay
and program. In place of `trajver.verify` it uses a stand-in module (`tests/integration/stub_verify.py`)
with the same CLI and output, because this test has no GPU or ComfyUI. Its rows carry a deliberately
wrong `attack` label, so the test fails if the label ever influences a verdict. The test rewrites the
program's singleton `Config`, so do not run it while another client (for example the replay) uses the same validator.

## Limits

- **Commit before open.** The protocol has the verifier commit its recomputed values before the
  provider opens its commitment. `trajver.verify` recomputes and compares in one run, so the
  commitment here is computed after that run. Splitting `trajver.verify` into a recompute phase and
  a compare phase would make the order strict. That change belongs in `trajver`, not here.
- **One job at a time.** Jobs are processed sequentially. That is enough for the testbed's job rates.
