# Literature Review: Novelty Check for the Main Paper (2026-11-22)

**Purpose.** This review maps every line of work that touches the main paper's claims, says what each line already covers, and states what is left. Entries marked "read in full" were read beyond the abstract (via HTML full text). The rest come from abstracts and search snippets and must be read before citing.

---

## 1. Map of the field

Verification work differs mainly in **what evidence the verifier can see**:

```
 black-box (final output only)  ──►  sampler-level (per-step state)  ──►  white-box (operators/activations)  ──►  cryptographic
 2307.01898, PoQ, Bittensor         [GAP: diffusion]                   TAO, Verde, TOPLOC, SVIP, VeriLLM      ZKML, zkLLM, NANOZK,
 validators, Cai et al., MET        WOMBO SN30 (grey literature)       Seal-then-Sample, EigenAI, DiFR       Anthropic provable inference
```

The draft sits at the **black-box** end. That is the end where the evidence (Cai et al., MET) says cost-saving substitution is hardest to detect.

---

## 2. Closest works

### 2.1 Tolerance-aware verification across GPUs

**TAO: Tolerance-Aware Optimistic Verification for Floating-Point Neural Networks.** Yao, Su, Liao, Cheng, Zhang, Wang, Viswanath. *EuroSys 2026*, pp. 1515–1532, doi:10.1145/3767295.3803612; arXiv:2510.16028. Read in full. The earlier docs called this "NAO"; that was a mistake.

- **Commitments.** Merkle roots of the weights, the graph and the per-operator thresholds, plus the hashes of input and output.
- **Disputes.** An N-way partition game narrows a dispute down to a single operator. The final verdict comes either from an IEEE-754 error bound or from a committee vote against empirical thresholds.
- **Calibration.** Per-operator error percentiles from 50 inputs on 4 GPUs (RTX 4090, RTX 6000, A100, H100), combined as a max envelope and multiplied by α = 3.
- **Settlement.** An Ethereum Holesky contract handles bonds, slashing and the challenge window. Randomized audits happen with probability φ, and the paper states incentive constraints.
- **Results.** 0.3% overhead on the happy path. 0 false positives on 1,000 honest inputs. 0% attack success with empirical thresholds.
- **Diffusion coverage.** SD v1.5 appears only in the cost table. Per-step verification over the denoising loop is mentioned as **future work** (a temporal Merkle tree).
- **Access needed.** It is **white-box**: the PyTorch FX graph is instrumented at operator level. It cannot run against ComfyUI or Ollama as they ship. Ollama is llama.cpp, not PyTorch.
- **Stated limitation.** "Semantic-changing optimizations (fast-math, **undeclared quantization, early exit**, pruning) are not caught unless committed."

**Impact on the draft.** This is the strongest prior work. It already combines escrow and bonds, sampled audits, cross-GPU tolerance calibration and on-chain settlement, and it was published at a top venue. A general claim that our *combination* is new will not survive review. What TAO leaves open is narrower: (a) backends without operator-level access, (b) diffusion workflows evaluated end to end, (c) cost-saving attacks it explicitly does not catch, and (d) consumer GPUs.

**Generative AI Reproducibility and Consensus.** Kim, Isozaki, Sirkin, Robson (Drexel). arXiv:2307.01898 v2, 2024. Preprint. Read in full.

- **Hardware and models.** 22 consumer and datacenter GPUs of 5 or more models (RTX 3060 Ti, 3070 Ti, 3080 Ti, 3090; A40), running SD v1.5, a fine-tuned model, LoRA and textual inversion.
- **Measurements.** Perceptual hashes (aHash, pHash, dHash, cHash) with Hamming tolerance 0, 1 or 2. Exact-pHash consensus is 92.9%, rising to about 99.5–99.8% at tolerance 2. A binomial majority-vote model gives 99.84% for 3 verifiers.
- **LLM result.** Greedy and beam decoding were deterministic across these GPUs.
- **What it lacks.** **No adversary** beyond guessing an image from a different seed. No step-count, quantization or model-substitution attacks. No blockchain, escrow, sampling or cost measurement. No tolerance calibration procedure.

**Impact on the draft.** It is the prior measurement of honest cross-GPU variation for Stable Diffusion, and it must be cited and extended. It shows honest variation is small. It does **not** show whether attacks fall outside that variation.

### 2.2 Checking outputs only: the evidence that it fails on cheap substitutes

**Are You Getting What You Pay For? Auditing Model Substitution in LLM APIs.** Cai, Shi, Zhao, Song (UC Berkeley). arXiv:2504.04715. Read in full.

- **Classifiers.** Text classifiers detect FP8 and INT8 quantization at **49–52% accuracy**, which is chance.
- **Statistical tests.** An MMD test never detects INT8 substitution on smaller models. It is at chance when 20% or less of traffic is randomly substituted.
- **Benchmarks.** Accuracy differences fall within one standard deviation and are confounded by temperature.
- **Greedy matching.** Agreement across real APIs was below 5%.
- **Logprobs.** They diverge across serving frameworks and GPUs.
- **What works.** TOPLOC works with activation access. TEEs work, at 3–16% overhead.
- **Conclusion.** Software that checks outputs alone cannot close the gap.

**Model Equality Testing: Which Model Is This API Serving?** Gao et al., ICLR 2025 (openreview QCDdI7X3f9). An MMD two-sample test; 11 of 31 Llama endpoints deviated. Follow-ups:
- RUT, a rank-based test (arXiv:2506.06975).
- **API-TAIL** (arXiv:2610.36801). It argues that the null hypothesis is *composite*, because honest providers legitimately serve the same model in many ways. That is the same issue as honest cross-GPU variation.
- One-token fingerprinting (arXiv:2607.10252).
- AgentProv (arXiv:2609.00052).

**Proof of Quality** (arXiv:2405.17934). Scores output quality instead of verifying the computation. It is a design alternative to acknowledge.

**Impact on the draft.** For **LLMs**, the paper's expected finding that output-only checks miss cheaper models **is already established**. Repeating it for Ollama adds little. For **diffusion**, no equivalent study was found. That is open ground.

### 2.3 White-box and activation-based verification (mostly LLMs)

| Work | Evidence used | Diffusion? | Notes |
|---|---|---|---|
| TOPLOC (ICML 2025, arXiv:2501.16007) | Locality-sensitive hashes of top-k activations | No | 258 B per 32 tokens; validation up to 100× faster than inference. Integrated with vLLM and SGLang |
| SVIP (arXiv:2410.22307) | Processed hidden states with a secret | No | |
| VeriLLM (arXiv:2509.24257) | Sampled hidden-state checks with on-chain settlement | No | About 1% overhead |
| Verde with RepOps (arXiv:2502.19405, Gensyn) | Bitwise-reproducible operators and a two-level bisection game | Not shown | In production in Gensyn Judge. Requires its own operator library |
| EigenAI (arXiv:2602.00182) | Bit-exact deterministic inference, so one honest replica is enough | No | Optimistic design, checked by byte equality |
| DiFR (arXiv:2511.20621) | Replays the provider's tokens | No | |
| TensorCommitments (arXiv:2602.12630) | Commitments with a light verifier | No | |
| Seal, Then Sample (arXiv:2609.27367) | Sampled layerwise proofs | No | GPT-2 up to 70B |
| opML (arXiv:2401.17555) | Optimistic fraud proofs | No | Providers are exposed to denial-of-service by challengers |
| PoSP / SpML (arXiv:2405.00295) | Sampling with a Nash-equilibrium argument | No | The paper's motivating example is swapping a 70B model for 13B |

### 2.4 Cryptographic verification

ZKML (EuroSys 2024) proved a small latent Stable Diffusion model in about 3,600 s. Other work: zkLLM, NANOZK (ICLR 2026), Anthropic's provable-inference work (Nov 2026), and arXiv:2511.19902. These are too expensive per image to serve as a marketplace baseline, but they belong in the related-work table as the high-assurance end.

### 2.5 Deployed decentralized image-generation validation (grey literature, primary sources still to be checked)

- **Bittensor SN23, NicheImage.** **Code audited; see doc 06.** The validator re-runs the whole image, compares CLIP ViT-B/16 embeddings and gives full reward above a cosine of 0.9. An alternative path accepts a pHash Hamming distance of 6 or less.
- **Bittensor SN30, WOMBO.** **Code audited; see doc 06.** It implements per-step spot checks:
  - the miner commits the sha256 of all per-step latents;
  - the validator checks with p = 0.35, at k = 3 random steps, re-running one UNet step each;
  - it compares by cosine similarity on the flattened latent and rejects if the minimum is below 0.70.

  This is prior art for the mechanism, and it is uncalibrated and has never been evaluated against attacks.
- **Common Risk Factors in Decentralized AI Subnets** (arXiv:2603.29751). A survey of these subnets.
- **Nosana, io.net, Render, Akash.** No primary documentation of their verification method was found.

### 2.6 Economics of auditing outsourced computation

- **Pham, Khouzani, Cid** (ePrint 2014/374), and **Khouzani, Pham, Cid** (on contracts robust to collusion). These derive optimal contracts that combine audit rate, fines, rewards and redundancy for lazy-but-honest contractors.
- **Tang and Pejó.** A Stackelberg game with a checking rate.
- **Nix and Kantarcioglu** (arXiv:1202.1567). Incentive contracts.
- **Blocki et al.** (IJCAI 2013). Audit games.
- **Verifier's dilemma.** TrueBit, and peer prediction for verifiers (arXiv:2406.01794). Collusion when provers are paid for agreeing (arXiv:1910.14269). Verifiers committed at random in an edge marketplace (arXiv:2203.12347).

**Impact on the draft.** The deterrence and optimal-sampling analysis must build on this work, not be presented as new. What is new is the **attacker's best skip fraction under step-level spot checks**, a structure specific to diffusion. See doc 05, Section 4.

### 2.7 Nondeterminism

- **Hugging Face Diffusers documentation.** Reproducibility across hardware holds only within a tolerance. Generating the noise on the CPU narrows the gap.
- **Community reports.** Pascal and Turing GPUs differ, and xformers adds nondeterminism.
- **Other studies.** Numerical nondeterminism in LLMs (arXiv:2506.09501). Atil et al. (2408.04667). Thinking Machines on batch invariance. Hawkeye (MLSys 2026, arXiv:2603.20421). Mitigation across GPU architectures (arXiv:2609.25624).
- **Gap.** No controlled quantitative study was found that compares Stable Diffusion or SDXL outputs across consumer GPUs while varying factors such as attention backend, precision, sampler and where the noise is generated. Kim et al. used perceptual hashes only and varied no factors.

### 2.8 Attribution and fingerprinting of generative models

WOUAF (CVPR 2024), latent fingerprinting (arXiv:2403.19653), LATTE (latent-trajectory detection, arXiv:2507.03054) and SPRINT (arXiv:2508.05691). AuthPrint claims to detect compressed or substituted Stable Diffusion models, but its arXiv ID is unconfirmed. These methods attribute an image to the *model* that made it. They do not check the *computation*. They are a possible second detector to compare against.

### 2.9 Blockchain compute markets

Du et al. (IEEE TMC 2023), Yang et al. (IEEE COMST 2019), Fan et al. (IEEE IoT-J 2021) and Wang et al. (IEEE TVT 2024) are already cited. Add: Fair Marketplace for Secure Outsourced Computations (arXiv:1808.09682), Commodification of Compute (arXiv:2406.19261) and Verifying Outsourced Computation in an Edge Computing Marketplace (arXiv:2203.12347). **None** of these verifies generative output.

---

## 3. What is left open

| Candidate claim in the draft | Status after this review |
|---|---|
| Joint measurement of escrow, sampled re-execution and tolerant acceptance | **Largely taken by TAO.** It does all three with on-chain bonds, though white-box |
| Tolerant acceptance rule for LLM outputs | **Taken or crowded**: TOPLOC, TAO, DiFR, EigenAI |
| Output-only checks cannot detect cheaper LLMs | **Already shown** by Cai et al. and MET |
| Honest cross-GPU variation of Stable Diffusion | **Partly done**: Kim et al., with perceptual hashes only, no factors, no adversary |
| **Cost-saving attacks on diffusion** (fewer steps, quantized or distilled UNet, sampler swap, early exit) **compared with honest cross-GPU variation** | **Open.** No study found. TAO explicitly excludes these attacks |
| Sampler-level (per-step) verification of diffusion without operator-level access | **Mechanism already deployed** by WOMBO SN30 in 2024, with an uncalibrated cosine-0.70 rule. It is absent from the academic literature, where TAO lists it as future work. Open: calibrated evaluation, attacks on the deployed rule, and a hardened two-tier design |
| **Attacker's best skip fraction and cost-optimal (p, k) under step spot-checks with escrow** | **Open.** Builds on the inspection-game literature |
| Token escrow on Solana for generative jobs | Engineering only, not novel. Keep it as the substrate |

**Conclusion.** The paper's original novelty, the combination plus black-box checks for both ComfyUI and Ollama, is **not defensible** at Q1 level after TAO and Cai et al. The defensible core is **diffusion-specific**: whether cost-saving cheating can be told apart from honest hardware variation, and what the cheapest sufficient evidence is. Doc 05 redesigns the paper around that core.

## 4. To read before writing (priority order)

1. TAO, full paper including the appendix on incentives. *Done for the main text.*
2. WOMBO SN30 and NicheImage SN23 validator code: what exactly is compared, and at which steps.
3. Kim et al. 2307.01898: the full Table 1 and the figures.
4. Cai et al. 2504.04715 and API-TAIL 2610.36801: the composite-null framing.
5. Pham, Khouzani, Cid: the contract model, to adapt in doc 05, Section 4.
6. EigenAI 2602.00182: if bit-exactness can be enforced, does that remove the need for tolerance? It is a competing design to discuss.
7. LATTE 2507.03054: latent-trajectory features, possibly reusable as a detector.
8. ZKML: the Stable Diffusion proving-time numbers, for the cost-comparison table.
