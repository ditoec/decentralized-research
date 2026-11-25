# Revised Paper Design: Deeper Focus, Achievable Scope

This design replaces the scope and RQs of the original proposal, based on the novelty check in `04-literature-review.md`. Date: 2026-11-22.

> **Update 2026-11-23:** §4.5, §6, §7 and §8 now include the paid-infrastructure plan: at most US$200 in total, RunPod only, Solana on the local validator and Devnet. The budget, the spending rules and the thesis operating model are in [10-paid-infrastructure-and-thesis.md](10-paid-infrastructure-and-thesis.md).

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
- Storage is about 16.5 MB per 30-step SDXL job and 3.9 MB per SD1.5 job, off-chain (measured in the WP0b pilot; ComfyUI keeps latents in float32). The earlier estimate of 7.7 MB was too low.
- **The initial noise is generated on the CPU in float32 from `torch.manual_seed(seed)`** (`comfy/sample.py`). It is not bit-exact across CPU families (ARM vs x86 differ by up to 2.3e-6 in the pilot), so E1 checks it within the fixed tolerance u₀ = 1e-5 (runbook §3, decisions of 2026-11-24).

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

### 4.5 Hardware and statistics (updated 2026-11-23 after the hardware inventory)

**Hardware: six owned DGX Sparks, and rented x86 GPUs from RunPod.** There are no owned RTX 5080s; the rented x86 Blackwell card is a Runpod **RTX 5090** (decided 2026-11-24, after the pilot ran on it because the RTX 5080 had no stock). All rented cards are consumer GeForce RTX (decided 2026-11-23). Budget, node roles and rules: doc 10 §2.

| Property | DGX Spark (GB10), owned ×6 | RTX 5090, rented |
|---|---|---|
| GPU | Blackwell GB10, compute capability 12.1 (confirmed), about 121 GB memory **unified** with the CPU | Blackwell, 32 GB (discrete), compute capability 12.0 (sm_120, confirmed in the pilot, 2026-11-24) |
| Host CPU / ISA | **ARM64** (Cortex-X925 / A725, 20 cores), DGX OS 7.5 | x86-64, host-controlled driver |
| Role in the study | Volume, full factor grid, verifier, storage | L3 partner of the Spark; consumer-class provider; timing |
| Constraint | **Shared with a live production platform** (doc 10 §2.2) | US$0.69/h Community Cloud; the pilot paid US$1.39/h on Secure Cloud |

All six Sparks were inventoried on 2026-11-23 and are identical: driver 580.178.04, CUDA 13.0, kernel 7.0.0-1019-nvidia. Nodes 4 to 6 are the main research nodes.

**Heterogeneity is measured as nested levels.** This replaces "at least 5 GPU models", and it is a stronger design because each level isolates one cause:

| Level | Comparison | Hardware | What it isolates |
|---|---|---|---|
| L0 | Same card, repeated runs | Spark | Run-to-run nondeterminism |
| L1 | Same card, different software config (precision, attention backend, `--deterministic`, torch/ComfyUI version) | Spark in full, under one pinned software stack; RTX 4090 for the deterministic-mode and attention factors; every rented model for precision | Software-stack effects (these are the RQ1 factors) |
| L2 | Different physical units of the same model | Six Sparks (up to 15 pairs); two rented RTX 5090s | Unit-to-unit variation (expected: none) |
| L3 | Same generation, different chip, memory system and CPU ISA (RTX 5090 ↔ Spark) | Spark and rented | Kernel selection per compute capability, and x86 vs ARM CPU |
| L4 | Different generation (Blackwell ↔ Ada ↔ Ampere) | **rented** | The marketplace reality: providers of mixed generations |

**Rentals (RunPod only, hard cap US$200 for all paid infrastructure).**
- Required, all consumer GeForce RTX: RTX 5090 (Blackwell), RTX 4090 (Ada), RTX 3090 (Ampere).
- Substitutes when a required card has no stock: RTX 4080 SUPER (Ada), RTX 3090 Ti (Ampere).
- A second RTX 5090 on a different host, for a short L2 subset.
- On rentals, run only the **reference config plus the precision factor** (workload below). The RTX 4090 also runs the x86 factor slice: at fp16, deterministic mode {off, on} × attention backend {SDPA, alternative, and xformers if it installs} × both samplers, on the 200-prompt grid subset.
- Cross-GPU results then cover **4 or 5 GPU models across 3 generations** (Ampere, Ada, Blackwell), which is 6 to 10 cross-model pairs. The Sparks carry the full factor grid.
- Turing and older, and Hopper, are not tested. Make no claim about them.
- RunPod pods are containers, so the host sets the driver. Record the driver, host and data-center ID; driver spread is honest variation.
- Record the hourly rate and billed hours of every pod. RQ3 uses them to state costs in dollars.

**The Sparks are shared with production.** Consequences for the design:
- Research jobs run beside live inference services, with a small memory footprint and stop conditions.
- **No timing result comes from a shared Spark.** The attacker's saving β_A and verifier GPU-seconds are measured on rented pods, which the job has to itself.
- **Co-tenancy check (new):** repeat a small job set while the co-located model is busy and while it is idle. If the outputs are bit-identical, the paper can state that shared load does not affect verification.
- The full software-factor grid exists only on the Spark platform. The RTX 4090 runs the x86 factor slice to narrow the gap (doc 10 §2.1). The second software stack was dropped on 2026-11-24: the protocol pins one software image (by digest), so library versions are fixed by design, and the paper states that its tolerances are not claimed to cover other PyTorch or CUDA versions.

**Exact-reproducibility checks across CPU ISAs:**
- **x_T across CPU ISAs.** ComfyUI draws the initial noise from the CPU (`torch.randn` on the CPU, doc 06 §1). PyTorch uses vectorized normal-distribution paths for larger tensors, and these may differ between x86 (AVX2) and ARM (NEON). Test whether x_T is **bit-identical on x86 and ARM**. The x86 side runs on any RunPod pod and costs cents. If the bytes differ, the E1 seed binding must name a canonical CPU path, or compare within a tolerance. The result is publishable either way.
- **The Tier A solver check on ARM vs x86**, run on the CPU: is it bit-exact, or does it need a tolerance?

**Blackwell-native low precision makes the attacks realistic.** Blackwell tensor cores run fp8 natively (and NVFP4). An fp8 UNet (`--fp8_e4m3fn-unet`, optionally with `--supports-fp8-compute` / fp8 matmul) is therefore a **fast** attack on these cards, which is exactly a provider's incentive. Add **A2b: NVFP4 / 4-bit quantized model**, if ComfyUI's Blackwell FP4 support covers SDXL or FLUX at the pinned version. Check this in the pilot, and drop A2b if not.

**Software caveats:**
- The PyTorch 2.9.1 build found on the Sparks warns that compute capability 12.1 is above its supported maximum of 12.0. Choose the research image's aarch64 PyTorch build in the pilot and record it.
- **xformers may be unavailable on aarch64**, so the attention factor on the Spark is {SDPA, split, quad}. Record exactly which backend is used.
- Pin one ComfyUI commit across all nodes. Start with `8b25bbc` from the code audit and freeze it at the pilot.
- Automatic updates are enabled on the Sparks. Ask the platform admin to hold the driver and kernel packages during the study.
- The Anchor build and the local Solana validator (`solana-test-validator`) run on a rented x86 RunPod pod.

**Models:** SD1.5 and SDXL are required. FLUX.1-schnell is optional: it needs most of a Spark's free memory, so it runs only in a window agreed with the platform admin.

**RQ1 factor grid on the Sparks:**
- Factors: {fp16, bf16, fp32} × {SDPA, alternative attention backend} × {euler, dpmpp_2m} × {`--deterministic` off, on}, which is 24 configs.
- Prompt set: 1,000 prompts, split 40/20/40 into calibration, dev and test.
- Workload on the Sparks: the **reference config** (fp16, SDPA, both samplers, `--deterministic` off) runs all 1,000 prompts × 3 seeds on nodes 4, 5 and 6. Every other config runs a fixed 50-prompt subset (`prompts_grid50.txt`) × 3 seeds on nodes 4, 5 and 6 (**decision of 2026-11-26**; was 200 prompts on nodes 4 and 5). A 50-prompt L2 subset runs on all six. (As run, the Spark reference config uses the 600 calibration and dev prompts, runbook §4 item 1.)
- Workload on RunPod nodes: the reference config on a fixed 500-prompt subset × 3 seeds, and the precision factor (bf16, fp32) on the same 50-prompt subset as the Spark grid × 3 seeds (decision of 2026-11-26; was 100 prompts). That is 6,900 jobs per rented model for SD1.5 plus SDXL (was about 8,400).
- Why the reference config gets more prompts: per-step tolerances are extreme quantiles. For k = 8, α_s ≈ 0.13%, and estimating that quantile needs about 2,400 or more honest samples per step. Only configs with a frozen threshold need that many.
- The Sparks cost nothing per hour, so the volume goes there. Their throughput beside production is unknown until the pilot. If the Spark workload does not fit in January, cut the reference config to 500 prompts.
- The old "noise on CPU vs GPU" factor is dropped. ComfyUI always uses CPU noise, and the CPU-ISA test replaces it.

**Marketplace testbed (end-to-end, RQ3):**
- Providers are rented consumer cards (RTX 3090, 4090, 5090). Verifiers are the Sparks. This is the direction a real marketplace has.
- The local validator runs on a rented x86 pod and measures compute units by scripted replay. The end-to-end runs use Devnet.
- The Sparks sit behind a VPN, so they connect outward to the provider's pod and to Devnet.
- Mainnet is not used: deploying a program there locks up several SOL of rent, which does not fit the budget. Mainnet fees are calculated from measured signature counts and compute units at a dated SOL price, and labeled as calculated.
- This replaces "simulated providers replaying traces" for the cost and latency results. The small Monte Carlo (below) covers the scale-out.

**Splits and statistics:**
- Calibration / dev / test splits are separated by prompt. Thresholds are frozen by hash, as in the draft.
- Keep the draft's Wilson intervals and cluster bootstrap. The "299 audits for FPR < 1%" rule is the minimum. The target is 1,000 honest test jobs per stratum, which bounds FPR below 1% with up to 4 false rejections, and 100 attacked jobs per cell.
- **The independent unit for cross-hardware claims is the hardware pair.** Report results per pair and per level (L0–L4). Do not claim results for GPU generations that were not tested.

**Replay simulation:** **drop** the 10–100 provider grid. Replace it with a small Monte Carlo that checks Propositions 2 and 3 using the measured r and τ_t. It takes hours, not weeks.

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
1. A quantified honest-variation profile for SD1.5 and SDXL in ComfyUI across 4 or 5 GPU models (DGX Spark and consumer GeForce RTX) of 3 generations (Ampere, Ada, Blackwell), with the factors that dominate it.
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
| Owned hardware is one model (DGX Spark) | Every other GPU model, including the x86 Blackwell card, is rented | L0–L2 run on the Sparks. Rent the consumer RTX 5090 for L3 and the RTX 4090 and RTX 3090 for L4 on RunPod (doc 10 §2). If a model is unavailable, report L4 for the models tested and narrow the claim |
| The US$200 cap runs out (reruns, higher prices) | Fewer rented models | Load credit in US$50 steps, dry-run every workload on a Spark and smoke-test the x86 image on the cheapest pod first, review at US$120 spent. Drop the optional RTX 5090 first, then cut prompts on rentals. Never cut the reference config |
| The Sparks are shared with a live production platform | A research job could disturb production, or be slowed by it | Use nodes 4 to 6, a small memory footprint and automatic stop conditions (doc 10 §2.2). Take all timing on rented pods. If the Sparks become unavailable, cut the Spark grid to the reference config and move it to an RTX 3090 pod (US$0.22/h) |
| No mainnet measurement | Latency, priority fees and landing rate on mainnet are unknown | State it as a limitation. Report calculated mainnet fees. Mainnet measurement is a thesis extension |
| The Spark's aarch64 stack lags (no xformers, ComfyUI or custom-node problems on sm_121) | Gaps in the factor grid on the Spark | Use SDPA or split attention on the Spark and record the backend. If ComfyUI fails on the Spark, use it as a verifier-only node with a matched PyTorch/diffusers reference implementation for Tier B, and say so in the paper |
| x_T differs between x86 and ARM | The exact seed binding breaks across CPUs | Report it as a finding. Fix a canonical noise path in the protocol (a pinned torch version, or scalar `randn` in chunks below the vectorization threshold), or use a tolerance for x_T |
| A provider fakes trajectories that are consistent step by step | Faking one step needs a true step computation, so cheating gives no savings | State this as a lemma: any trajectory that passes all one-step checks is a valid trajectory for the committed model, up to τ |
| WOMBO SN30 already does E2. **Confirmed by the code audit (2024, archived)** | Per-step spot-checking itself is not new | **Applied:** the framing is now break-and-fix. We evaluate the deployed rules (E0-N, E2-W), then harden the check (E2-H). See doc 06 |
| The deployed rules turn out robust (W1 is false) | The "attack" headline weakens | It is still a result: the first calibrated FPR and FNR for these rules. E2-H then competes on cost and on theory |

## 8. Revised timeline (it replaces the table in `03-publication-plan.md` §2)

| WP | Content | Dates |
|---|---|---|
| WP0 | Finish the priority reads (doc 04, §4). The WOMBO and NicheImage code is already read (doc 06). Lock the delta | Nov 24 – Dec 6 |
| **WP0b** | **Hardware pilot (2–3 days, on Sparks 4 to 6 plus short RunPod rentals).** Run it in parallel with WP0. See the checklist below | Nov 26 – Dec 6 |
| WP1 | ComfyUI trajectory-commit node, verifier (E0-N, E2-W, E2-H), attack injectors (A1–A8, F1–F4), run manifests, the pinned container image and the RunPod launcher script | Dec 7 – Jan 3 |
| WP2 | **RQ1 study:** the full factor grid on the Sparks (L0–L2), plus the RunPod rentals for L3 and L4 in the first two weeks of January. Freeze τ (E0) and τ_i (E2-H) | Jan 4 – Jan 31 |
| WP3 | RQ2 attack-separability runs and the partial-cheating sweep | Feb 1 – Feb 28 |
| WP4 | Propositions 1–3 with proofs, and the Monte Carlo (parallel with WP3) | Feb 1 – Feb 28 |
| WP5 | Anchor escrow with bond and trajectory root, the RQ3 cost table, end-to-end demo runs | Jan 4 – Mar 14 (parallel, second person) |
| WP6 | Analysis, figures and writing (ESJ Word template) | Mar 15 – Apr 25 |
| WP7 | Internal review, artifact DOI, arXiv, submission | Apr 26 – May 16 |

**Submission target: mid-May 2027.** That is about one month earlier than before, because the scope is smaller.

**WP0b pilot checklist.** It needs the Sparks and about US$8 of RunPod time, and every item is logged as a run in `experiments/runs/`.
1. Inventory every node: GPU, compute capability, driver, CUDA, torch, ComfyUI commit, CPU ISA. The six Sparks were inventoried on 2026-11-23 (doc 10 §2.2); record each rented pod the same way. Agree the research windows and a hold on driver and kernel updates with the platform admin.
2. Build the arm64 and x86-64 research images with the pinned ComfyUI, and run them on a Spark and on a rented RTX 5080. Note anything that fails on aarch64, and choose the PyTorch build.
3. Generate x_T for 100 seeds on a rented x86 pod and on the Spark's ARM CPU, and check whether the bytes match.
4. Run SDXL, 30 steps, euler, on 20 prompts × 2 seeds, on two Sparks, and on a rented RTX 5080, RTX 4090 and RTX 3090. Compare by pixel hash and record the maximum absolute difference of the latent per step. This first look at L0, L2, L3 and L4 sets expectations for the go/no-go.
5. Measure the per-image time on each node, to size the RQ1 grid.
6. Check whether `--fp8_e4m3fn-unet` and any FP4 path work on each node (attacks A2 and A2b).
7. Quick check of hypothesis W1 (doc 06 §2): the cosine similarity of `frame[i]` vs `frame[i+1]` on a few honest trajectories. If it is above 0.70, the frame-copy forgery F1 already passes WOMBO's rule.
8. Co-tenancy check: repeat 50 jobs on one Spark while its chat model is busy and while it is idle, and compare the bytes.

**Go / no-go #0 (Dec 6, after the pilot):**
- If RTX 5080 ↔ Spark outputs are bit-exact for SDXL, honest cross-hardware variation within Blackwell is zero. The study then depends on L4, and the pilot's rentals already show whether L4 varies.
- If W1 already holds in the pilot, the break-and-fix headline is secured early.

**Go / no-go #1 (Jan 31, after RQ1):** if honest variation is bit-exact everywhere, including L4, switch the framing to the "deterministic profile" pivot in §7.
