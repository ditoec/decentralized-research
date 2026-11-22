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

**Delta statement (for abstract and cover letter). Revised after the code audit in `06-code-audit.md`:**
- Deployed decentralized image networks already validate diffusion work by full re-execution with CLIP-embedding similarity (Bittensor SN23) or by per-step latent spot checks with cosine similarity (SN30, 2024).
- Their acceptance thresholds are uncalibrated, and they have never been evaluated against cost-saving attacks.
- *Operator-level* tolerance schemes (TAO, Verde) need instrumented runtimes and explicitly leave undeclared quantization and early exit out of scope.
- We provide the first calibrated evaluation of output-level and step-level rules against cost-saving attacks across consumer GPUs, and we test whether the deployed rules accept cheap forgeries.
- We propose a hardened two-tier trajectory check: solver consistency on every step plus model consistency at k random steps, with per-step tolerances, an exact seed binding and a deterrence analysis under escrow.
- **Do not claim** per-step spot-checking itself as new. WOMBO SN30 is prior art.

Working title after the audit: *Calibrated Trajectory Verification for Escrow-Settled Diffusion Inference: Attacking Deployed Validators and Hardening the Protocol*.

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
| **E2-W, deployed step check** (reproduction of WOMBO SN30, baseline) | sha256 of all per-step latents | 3 random steps, one UNet step each, cosine on the flattened latent, reject if min cosine < 0.70 | ≈ 3/T |
| **E0-N, deployed output check** (reproduction of NicheImage SN23, baseline) | Image | Full re-run, CLIP ViT-B/16 cosine, full reward above 0.9 | ≈ 1.0 |
| **E2-H, hardened trajectory check** (proposed) | Merkle root of (x_i, denoised_i, σ_i) for all i, plus the final x. Kept off-chain until the job closes | E1, plus **Tier A**: solver-consistency check on *every* step (CPU, no UNet). Plus **Tier B**: re-run the UNet at k random steps and compare `denoised_i` with a per-step calibrated τ_i | ≈ (k + c)/T |

**Why E2-H is achievable** (confirmed in `06-code-audit.md`):
- ComfyUI's sampler callback provides `x_i` (before the update) and `denoised_i` (the CFG-applied x0-prediction) at every step. A custom node records them, and also captures the sampler's return value for the final x.
- Storage is about 7.7 MB per 30-step SDXL job, off-chain.
- **The initial noise is generated on the CPU in float32 from `torch.manual_seed(seed)`** (`comfy/sample.py`). x_T can therefore be checked *exactly*.

**Restrictions** (from the code audit):
- Per-step noise in ancestral and SDE samplers is drawn on the GPU (`default_noise_sampler`), and a CPU run uses seed+1. So the core study uses **deterministic samplers only** (euler, heun, dpmpp_2m, ddim, uni_pc).
- Ancestral samplers are allowed only with a CPU noise sampler, and that is a protocol requirement.

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

**Trajectory forgeries.** These target step-level checks and are new relative to the draft:

| Attack | What the forger does |
|---|---|
| F1: frame copy | Sets `x_{i+1} := x_i` |
| F2: interpolation | Linearly interpolates between computed anchor steps |
| F3: solver inversion | Computes only some steps, then solves for the `denoised_i` values that make Tier A pass |
| F4: cheap-model trajectory | Commits a full, consistent trajectory from an fp8 or turbo UNet |

**RQ2a (headline):** run all attacks against the faithful reproductions E0-N and E2-W. *Hypothesis W1:* the cosine-0.70 rule of E2-W accepts F1, F2 and F4.

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
| WOMBO SN30 already does E2. **Confirmed by the code audit (2024, archived)** | Per-step spot-checking itself is not new | **Applied:** the framing is now break-and-fix. We evaluate the deployed rules (E0-N, E2-W), then harden the check (E2-H). See doc 06 |
| The deployed rules turn out robust (W1 is false) | The "attack" headline weakens | It is still a result: the first calibrated FPR and FNR for these rules. E2-H then competes on cost and on theory |

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
