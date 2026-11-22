# Novelty and Technical Feasibility Review

**Manuscript:** *Tokenized Settlement and Probabilistic Verification in a Decentralized GPU Marketplace for Generative AI Workloads* (A. R. Maradita), revised proposal draft, 10 pp. Source: `drafts/Tokenized Settlement ... (1).pdf`
**Review date:** 2026-11-22
**Target:** Q1 journal (see `03-publication-plan.md`)

---

## 1. What the paper is

It is a **research proposal**, not a results paper. It says so itself ("No experimental findings are claimed at this proposal stage").

- **System:** OpenCompute marketplace, ParkedGPU provider agent, Solana Anchor escrow, and an OCC SPL token used only as a unit of settlement.
- **Workloads:** pinned ComfyUI workflows (image) and Ollama LLM inference (text), both treated as **black boxes** that are judged on their outputs only.
- **Mechanism:**
  1. The provider commits the result before the sampling decision.
  2. The sampling draw comes from a Solana slot hash after a delay.
  3. Sampled jobs are re-executed by another node and judged with a 3-valued acceptance rule (pass / fail / inconclusive).
  4. A fail or inconclusive verdict triggers 2-of-3 adjudication.
  5. Reputation enters scheduling.
- **Questions:**
  - RQ1: detection versus overhead.
  - RQ2: Solana escrow fees and latency versus a centralized broker.
  - RQ3: sampling rate and acceptance rule versus FP/FN rates.
- **Method:**
  - Pre-registered thresholds (99% honest-pass calibration).
  - A factor grid: N ∈ {10..100}, malicious share ∈ {0, 10, 25%}, p ∈ {0.05..1.0}.
  - Five attack classes plus a negative control.
  - Baselines B1–B3.
  - Wilson and cluster-bootstrap confidence intervals.
  - Real GPU fidelity runs plus replayed traces on a local validator.

**Strengths.** The experimental design is unusually careful for a first draft. Specifically:
- Pre-registered, frozen thresholds and a disjoint test set.
- Pooled-q pitfall analysis.
- The observation that an output-only rule cannot detect an attack whose output distribution matches honest output, and that raising p cannot fix this.
- Explicit trust table (Table II).
- Ground truth is never used to resolve disputes.
- Censored detection times and paid-fraud volume.
- One-component-at-a-time baselines.

These are what Q1 reviewers look for. Keep them.

---

## 2. Novelty assessment

### 2.1 The stated novelty claim

> "In the sources reviewed, no study measures black-box output acceptance, sampled re-execution and escrow cost together for ComfyUI and Ollama jobs on heterogeneous consumer GPUs."

The paper also says, correctly, that novelty lies in *integration and measurement*, not in inventing escrow, sampling or reputation.

### 2.2 Prior work the draft does not cite (found 2026-11-22; full texts still to be read)

| Work | Why it matters |
|---|---|
| **Kim, Isozaki, Sirkin, Robson, "Generative AI Reproducibility and Consensus," arXiv:2307.01898 (Drexel, 2023/24)** | **The most damaging omission.** It runs Stable Diffusion and LLM tasks, sets tolerance and error bounds for verification, and uses majority vote among 3 independent verifiers for image perceptual collisions. It reports >99.89% detection, and 100% consensus for LLMs with greedy or beam decoding. It frames all of this as groundwork for a blockchain fraud proof. It covers much of G3, and the draft's 2-of-3 adjudication is very close to it. |
| **NAO: Nondeterminism-Aware Optimistic Verification for Floating-Point NNs, arXiv:2510.16028** | Tolerance-aware verification across heterogeneous accelerators. It calibrates empirical percentile error profiles across GPUs and evaluates CNNs, Transformers, LLMs **and diffusion models**. Its calibrated tolerance across hardware is the same idea as the draft's acceptance-rule calibration. |
| **DiFR, arXiv:2511.20621** | Inference verification despite nondeterminism, by replaying the provider's output tokens. This bears directly on the Ollama side. |
| **Proof of Quality, arXiv:2405.17934** | Validates the quality of generative output on-chain instead of the inference itself. It is an alternative design point that reviewers will ask about. |
| **Hawkeye: Reproducing GPU-level non-determinism, arXiv:2603.20421 (MLSys 2026)** | Weakens the assumption that consumer-GPU outputs cannot be reproduced bit for bit. |
| **Accelerating mitigation of LLM nondeterminism across GPU architectures, arXiv:2609.25624** | Bears on whether exact-match LLM verification across GPU generations is feasible. |
| Heterogeneous Decentralized Diffusion Models, arXiv:2603.06741 (CVPR 2026) | Shows diffusion work in decentralized settings. Useful context. |

**Consequence:** the sentence "no study measures ..." would probably not survive review as written. The joint combination is still unoccupied, but G3 (tolerant acceptance rules for diffusion and LLM output) is now partly covered by 2307.01898 and NAO.

### 2.3 What remains defensibly novel

Ranked by strength:

1. **End-to-end joint measurement.** The trade-off curve linking sampling rate, calibrated FP/FN and escrow cost on a real token-settled system, with honest cross-GPU variation measured on **consumer** GPUs. Prior work measures one or two of these, not all three. This is moderate novelty, but strong if executed well.
2. **The "cost-saving attack" result.** Specifically, the indistinguishability bound: an output-only sensitivity q cannot exceed the false-rejection rate when the attack's output distribution matches honest output. The empirical evidence would cover:
   - Fewer diffusion steps.
   - Lower quantization.
   - A smaller model that still answers correctly.

   This is the most interesting scientific claim in the paper. It is currently a one-paragraph remark. **It should be formalized as a proposition and made a headline contribution.**
3. **Black-box backends driven through public APIs (ComfyUI and Ollama).** This is practical relevance, not novelty in itself. Reviewers will ask why the system is limited to black-box access when ComfyUI custom nodes can easily expose intermediate latents.
4. **Settlement cost (RQ2) on Solana.** This is the **weakest** part. Solana base fees are deterministic (5,000 lamports per signature plus priority fee), so measuring them adds little. Limit RQ2 to compute units, account rent, dispute paths and latency under contention, or fold it into RQ1.

### 2.4 Novelty verdict

| Aspect | Rating |
|---|---|
| Problem relevance (DePIN plus generative AI integrity) | High, and topical in 2026 |
| Conceptual novelty of the mechanism | **Low to moderate.** Commit-then-sample, re-execution, escrow, reputation and majority vote are all known |
| Novelty of the empirical study | **Moderate**, if it fills the consumer-GPU, two-backend, escrow joint-measurement gap |
| Novelty of the theory | **Low** as written: Eqs. (2)–(4) are textbook. **Potentially moderate** with the indistinguishability bound and an optimal-p / deterrence model |
| Q1 readiness | **Not yet.** It needs results, a sharper contribution and the omitted prior work |

---

## 3. Technical feasibility

### 3.1 Components

| Component | Feasibility | Effort (one engineer) | Notes |
|---|---|---|---|
| Anchor escrow program (fund, commit, sample, verdict, release, refund, timeout) | High | 2–3 weeks | Standard PDA escrow and SPL transfer. Slot-hash randomness via the `SlotHashes` sysvar is easy, but note the sysvar keeps only about 512 recent slots, so the delayed draw must be taken within that window. |
| Orchestrator (scheduling, Eq. 1 ranking, state machine, adjudication) | High | 2–3 weeks | Python/FastAPI or TypeScript, with an event log in Postgres or SQLite. |
| ParkedGPU agent | High | 2 weeks | ComfyUI `/prompt` and websocket API. Ollama `/api/generate` with `seed`, `temperature=0` and `num_ctx`. Container image pinned by digest. |
| Verifier and acceptance rules | Medium | 2–3 weeks | LPIPS with a pinned backbone. Answer extraction for constrained LLM tasks. **Verifiers must re-execute without seeing Rp first** (commit their own output), or they can simply copy and approve. The draft does not say this, so it should be added. |
| Attack injection (classes i–v plus control) | High | 1 week | Fewer steps, quantization swap, smaller model, truncation, replay. |
| Harness, replay simulator, statistics | Medium | 3 weeks | Trace replay with up to 100 simulated providers on `solana-test-validator`. Wilson and cluster-bootstrap intervals in Python. |
| **Cross-GPU reproducibility study** | **Medium; this is the main risk** | 3–4 weeks of GPU time | Needs **at least 4–6 distinct GPU models** across at least 3 architectures (e.g., Turing, Ampere, Ada, Blackwell). Use owned GPUs plus short rentals. |

Total: about **4–5 months** for two people to working results, and about 6–7 months to a submitted manuscript.

### 3.2 Expected technical outcomes (hypotheses to test, not results)

- **ComfyUI, same GPU model, same driver and container, CPU-generated noise:** bitwise or near-bitwise match is likely. **Across architectures:** bitwise match will usually fail, while LPIPS between honest outputs is likely small but nonzero. Hugging Face Diffusers documentation confirms that cross-hardware reproducibility holds only within a tolerance.
- **Attack separability:**
  - Fewer steps (e.g., 30 → 20) or fp8 quantization may fall **inside** the honest LPIPS band. q is then low, which supports the indistinguishability result.
  - Unrelated output, replay and truncation will be easy to detect (q ≈ 1).
- **Ollama:** llama.cpp at temperature 0 is often identical on the same GPU and build, but output diverges across CUDA architectures and batch sizes. Answer-equality on constrained tasks will be robust. Model substitution with a smaller model that still answers correctly will be undetectable in many cases. That is an expected negative finding, and a publishable one.

### 3.3 Feasibility risks and mitigations

| Risk | Mitigation |
|---|---|
| Too few physical GPU models, so the heterogeneity claim is weak | Rent 3–4 additional architectures for a short reproducibility campaign. Report hardware pairs explicitly. |
| A trusted orchestrator plus an honest verifier pool invites the critique "this is a centralized broker with a ledger" | Make the **B3 vs OC** comparison the honest answer to "what does the chain add?" Add at least one relaxation experiment (e.g., x% lazy or colluding verifiers) and a deterrence inequality. |
| Black-box rules have low q on cost-saving attacks | Add a **gray-box tier** as an extension: hashes of intermediate latents at k sampled denoising steps (ComfyUI custom node), and token log-probabilities for Ollama if the runtime exposes them. This turns the negative result into a comparison: black-box vs gray-box sensitivity at equal cost. |
| RQ2 adds little because Solana fees are trivial and deterministic | Narrow RQ2 to latency, compute units and dispute cost, or merge it into RQ1. |
| Slot-hash grinding or validator influence | This is acceptable as a stated limitation. Optionally compare against Switchboard or ORAO VRF. |

**Feasibility verdict:** **feasible** with modest resources. No component is research-risky. The risk is **empirical**: results could show that black-box verification is weak. The draft already treats that as a valid outcome, which is good, but the paper then needs the gray-box comparison or the theoretical bound to carry it.
