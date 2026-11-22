# Revised Paper Design: Deeper Focus, Achievable Scope

This design replaces the scope and RQs of the original proposal, based on the novelty check in `04-literature-review.md`. Date: 2026-11-22.

## 1. The change in one paragraph

The draft spread itself across two backends (ComfyUI and Ollama), black-box checks, Solana fees, reputation and a 100-provider simulation. After TAO (EuroSys 2026) and Cai et al., most of that breadth is either already done or shallow. The revised paper **narrows to diffusion workflows** and asks one deep question: **when an untrusted consumer GPU is paid through escrow to run a diffusion workflow, what is the cheapest evidence that reliably catches cost-saving cheating, given that honest re-execution on a different GPU is never bit-exact?** It answers with three things:
- A measurement of honest variation.
- An attack-separability study at three evidence levels.
- A sampler-level spot-check protocol with a deterrence model, run on the existing Solana escrow.

## 2. Working title and positioning

> **Trajectory Spot-Checking: Detecting Cost-Saving Cheating in Escrow-Settled Diffusion Inference on Heterogeneous Consumer GPUs**

Alternative: *What Must a Decentralized GPU Market Verify? Output- versus Trajectory-Level Evidence for Diffusion Workloads*.

**Delta statement (for abstract and cover letter):**
- *Output-only* reproduction checks (Kim et al.; Bittensor validators) can't tell honest cross-GPU variation from cheaper computation.
- *Operator-level* tolerance schemes (TAO, Verde) need instrumented runtimes and explicitly leave undeclared quantization and early exit out of scope.
- We show where the boundary lies for diffusion. We propose the cheapest evidence level that crosses it: per-step sampler commitments with random one-step re-execution. That level needs only a sampler hook, not operator access. We price it under escrow settlement.

## 3. Revised research questions

| RQ | Question | Replaces |
|---|---|---|
| **RQ1: Characterize** | How much do honest ComfyUI diffusion outputs vary across consumer GPUs and software configurations? Measured at three evidence levels (final image, per-step latent, single-step transition), and which factors drive it: GPU architecture, precision, attention backend, sampler, noise device? | Old G3 / RQ3 (calibration part) |
| **RQ2: Separate** | At a false-rejection rate of at most 1%, which cost-saving attacks can be detected at each evidence level, and which are indistinguishable from honest variation? | Old RQ1 / RQ3 (detection part) |
| **RQ3: Price** | What verification cost (verifier GPU-seconds, on-chain fees, latency) reaches a stated detection and deterrence target under sampled verification with escrow? And how does step-level spot-checking change the cost-optimal sampling policy (p, k)? | Old RQ1 (cost part) + RQ2 |

RQ1 is pure measurement and always produces a result. RQ2 produces a result whether attacks turn out separable or not. RQ3 combines theory with checks against measured data. **None of the RQs can come back empty.**

## 4. Method

### 4.1 Evidence levels compared (the core independent variable)

| Level | What the provider commits | What the verifier does when sampled | Cost relative to the job |
|---|---|---|---|
| **E0, output** | Image digest | Re-runs the full workflow and compares images: pixel hash, pHash, LPIPS, DINOv2 cosine | ≈ 1.0 |
| **E1, trajectory endpoints** | Image, plus the Merkle root of the per-step latents x_T … x_0 | Checks x_T = noise(seed) (CPU), the text-encoder conditioning, and VAE(x_0) = image | ≈ 0.05–0.1 |
| **E2, trajectory spot-check** (proposed) | As E1, with latents stored off-chain until the job closes | E1, plus k randomly chosen steps t: takes the committed x_t, runs **one** sampler step, and compares the result with the committed x_(t−1) against a tolerance τ_t calibrated per step | ≈ (k + c)/T |

**Why E2 is achievable.**
- ComfyUI's KSampler exposes a per-step callback, so a custom node can record latents without operator-level instrumentation.
- Each SDXL latent is 128×128×4 in fp16, about 128 KB. At 30 steps that is about 4 MB per job, which is fine to store off-chain.
- ComfyUI generates the initial noise on the CPU by default (confirm this), so x_T can be reproduced exactly.

**Restrictions.** Use deterministic samplers (Euler, DDIM, DPM++ 2M). Ancestral samplers are supported only if the per-step noise comes from the committed seed. State this as a scope limit.

### 4.2 Attack set (cost-saving first, because that is what TAO and output checks miss)

| Attack | Savings | Why it is hard |
|---|---|---|
| A1: fewer steps (30 → 25, 20, 15) | 17–50% | The image looks plausible |
| A2: fp8 or quantized UNet | about 30–50% of memory and time | Small numeric shift, possibly inside the honest band |
| A3: distilled or turbo model (SDXL-Turbo, LCM-LoRA, lightning) | 75–95% | A different model, but a similar image |
| A4: cheaper sampler or scheduler swap | varies | |
| A5: lower resolution then upscale | about 50–75% | |
| A6: early exit, where the trajectory is truncated and the remaining latents are interpolated | proportional to the steps skipped | E2 targets this directly |
| A7: replay or cache of a near-duplicate prompt | about 100% | |
| A8: unrelated or corrupted output (sanity class) | 100% | Trivially detected, used as a control |

Also test **partial cheating**: a provider who skips a fraction s of the steps, which is the attacker parameter in the theory below. The negative control from the draft (falsified metadata) carries over.

### 4.3 Theory: three short results (WP4)

1. **Proposition 1 (output-only ceiling).** For any rule that sees only the output and has false-rejection rate α, sensitivity to an attack is at most α + TV(D_attack, D_honest), where TV is the total-variation distance between attack and honest output distributions and D_honest includes variation across GPUs. Raising p does not raise this ceiling. *Measured by:* estimating the honest band and the attack distributions at each evidence level in RQ2.
2. **Proposition 2 (spot-check detection).** If a provider fakes a fraction s of the T steps, and k steps are checked uniformly without replacement, a sampled job is caught with probability q(s, k) = 1 − C(T−sT, k)/C(T, k) ≈ 1 − (1−s)^k. This assumes each faked step exceeds τ_t with probability r, measured in RQ2. In general q = 1 − (1 − s·r)^k.
3. **Proposition 3 (deterrence and best skip fraction).** The provider saves s·c_job and loses L if caught, where L is the forfeited payment plus a bond or lost future work. Its expected gain from cheating is s·c_job − p·q(s, k)·L. Derive the attacker's best s*, and the smallest p·k at which s* = 0, meaning honesty is the best response. Then derive the cost-optimal (p, k) that minimizes the verifier cost p·(k + c)/T·c_job subject to deterrence. This builds on the contract models of Pham, Khouzani and Cid. What is new is the structure q(s, k) specific to step skipping.

These are short and provable, and RQ2 data checks them directly. That gives the paper analytical depth without an expensive large-scale simulation.

### 4.4 Settlement (kept, but slimmed)

The Solana Anchor escrow, commit-then-sample with slot-hash randomness, and 2-of-3 adjudication are all kept as the **real substrate** that makes forfeiture credible. Add three things:
- An **optional provider bond**, so that L in Proposition 3 is enforceable. The draft had stake turned off. Run the deterrence analysis with and without a bond.
- **Verifier commits its result before it sees the provider's.**
- **Merkle root of the trajectory on-chain, latents stored off-chain.**

RQ3 reports compute units, fees and latency for each lifecycle path, including disputes, in **one table**. The B3-vs-OC comparison (broker vs chain) is answered by argument plus the cost of the refund-on-timeout path. It is no longer a full experimental arm.

### 4.5 Hardware and statistics

- **GPUs:** at least 5 models across at least 3 architectures, for example RTX 3060 and 3090 (Ampere), 4060 Ti and 4090 (Ada), one Turing card (2080 or T4), and one Blackwell card (5090) if possible. Use owned cards plus short rentals. RQ1 needs only about 2–4 GPU-hours per card.
- **Models:** SD1.5 and SDXL (required). FLUX.1-schnell (optional; it uses a different architecture, a flow transformer).
- **RQ1 factor grid per GPU:** {fp16, bf16, fp32} × {SDPA, xformers} × {Euler, DPM++ 2M} × {noise on CPU, noise on GPU}, with 200 prompts × 3 seeds on the calibration split.
- **Splits:** calibration / dev / test, separated by prompt. Thresholds are frozen by hash, as in the draft. Keep the draft's Wilson intervals and cluster bootstrap, and the "299 audits for FPR < 1%" sizing rule.
- **Replay simulation:** **drop** the 10–100 provider grid. Replace it with a small Monte Carlo that checks Propositions 2 and 3 using the measured r and τ_t. It takes hours, not weeks.

## 5. What is dropped or demoted, and why

| Item in the draft | Decision | Reason |
|---|---|---|
| Ollama / LLM workload | **Moved to Discussion**, with an optional 1-page appendix | The LLM space is crowded (TOPLOC, TAO, EigenAI, DiFR), and Cai et al. already showed output-only checks fail there |
| Old RQ2 as a full RQ (Solana fees) | Folded into RQ3 as one table | Fees are deterministic and not a finding |
| Provider population 10–100, replay grid | Dropped | Expensive and low-insight. Theory plus a small Monte Carlo cover it |
| Reputation score, Eq. (1) | Kept in the system, with one ablation at most | It is not part of the research question |
| B1–B3 baseline arms | B0: no verification; E0: full re-execution, as in Kim et al. and Bittensor; E1; E2 (ours); TAO **qualitatively**, since it needs white-box access | The baselines now match the new independent variable, the evidence level |
| Gray-box tier as "optional" | **It becomes the main proposed method (E2)** | It is the only defensible novelty |

## 6. Claims the paper will make (and avoid)

**Will claim** (falsifiable, scoped):
1. A quantified honest-variation profile for SD1.5 and SDXL in ComfyUI across at least 5 consumer GPUs, with the factors that dominate it.
2. For each cost-saving attack and evidence level, the detection rate at FPR ≤ 1%, including the attacks that are *not* separable at E0.
3. E2 reaches detection within X% of E0 for Y of Z attacks, at about (k + c)/T of E0's verifier cost. *(These numbers come from experiments; nothing is assumed in advance.)*
4. A deterrence condition and a cost-optimal (p, k) that hold within measured error in the Monte Carlo and real runs.
5. An open artifact: the ComfyUI trajectory-commit node, the escrow program, the datasets and the frozen thresholds.

**Will not claim:**
- That we are "first" to verify decentralized inference.
- That we prove execution on a particular GPU.
- Privacy of prompts.
- Robustness to colluding verifiers. That stays out of scope, with a citation to peer prediction and random assignment.
- Production economics.
- Anything about LLMs beyond discussion.

## 7. Risks and pivots

| Risk | What it would mean | Pivot |
|---|---|---|
| Honest per-step deviation across architectures is as large as fp8 per-step deviation | A2 is undetectable even at E2 | Report it as a finding: quantization is the irreducible gap without operator-level or TEE evidence. This matches TAO's limitation from the other side |
| Cross-GPU results are bit-exact under some configuration (e.g., fp32 + CPU noise + no xformers) | Tolerance is unnecessary in that configuration | Report a "deterministic profile" that marketplaces could require, with its throughput cost (compare EigenAI). This is a strong practical result |
| Fewer than 5 GPU models available | The heterogeneity claim is weaker | Rent short-term. The RQ1 budget is about US$50–150 |
| A provider fakes trajectories that are consistent step by step | Faking one step needs a true step computation, so cheating gives no savings | State this as a lemma: any trajectory that passes all one-step checks is a valid trajectory for the committed model, up to τ |
| WOMBO SN30 already does E2 | Novelty shrinks to the evaluation | Our contribution becomes the first calibrated evaluation of it, plus the theory. Still publishable, with a framing of "evaluating step-level validation" |

## 8. Revised timeline (it replaces the table in `03-publication-plan.md` §2)

| WP | Content | Dates |
|---|---|---|
| WP0 | Finish the priority reads (doc 04, §4). Read WOMBO and NicheImage code. Lock the delta | Nov 24 – Dec 6 |
| WP1 | ComfyUI trajectory-commit node, verifier (E0 / E1 / E2), attack injectors, run manifests | Dec 7 – Jan 3 |
| WP2 | **RQ1 study** on at least 5 GPUs. Freeze τ (E0) and τ_t (E2) | Jan 4 – Jan 31 |
| WP3 | RQ2 attack-separability runs and the partial-cheating sweep | Feb 1 – Feb 28 |
| WP4 | Propositions 1–3 with proofs, and the Monte Carlo (parallel with WP3) | Feb 1 – Feb 28 |
| WP5 | Anchor escrow with bond and trajectory root, the RQ3 cost table, end-to-end demo runs | Jan 4 – Mar 14 (parallel, second person) |
| WP6 | Analysis, figures and writing (elsarticle) | Mar 15 – Apr 25 |
| WP7 | Internal review, artifact DOI, arXiv, submission | Apr 26 – May 16 |

**Submission target: mid-May 2027.** That is about one month earlier than before, because the scope is smaller.

**Go / no-go (Jan 31, after RQ1):** if honest variation is bit-exact everywhere, switch the framing to the "deterministic profile" pivot in §7.
