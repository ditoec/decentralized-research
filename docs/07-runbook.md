# Engineering Runbook: Step-by-Step Technical Work

**Audience:** the engineer who builds and runs the experiments.
**Paper:** `paper/manuscript_ESJ.docx` (Emerging Science Journal, Word). Every red `[R…]` placeholder in the paper is filled from a run listed in the **Placeholder map** (§10).
**Ground rules:**
1. Never type a number into the paper by hand. Every number comes from `experiments/runs/<run_id>/`.
2. Thresholds are frozen and hashed *before* attack data is looked at.
3. Pin every version, and record it in the run manifest.

Background reading: `docs/05-revised-design.md` (the design), `docs/06-code-audit.md` (the ComfyUI internals this relies on).

---

## 0. Conventions

**Run ID:** `YYYYMMDD-<wp>-<short-name>-<nn>`, for example `20261127-wp0b-xT-isa-01`.

**Run folder layout:**
```
experiments/runs/<run_id>/
  manifest.json     # required (schema below)
  summary.json      # the numbers that feed the paper
  raw/              # large files; git-ignored; archived to storage, with checksums in manifest
  logs/
```

**`manifest.json` fields:**
- Identity and code: `run_id`, `wp`, `purpose`, `git_commit` (of this repo), `comfyui_commit`, `custom_nodes`, each with its commit.
- Per node: `hostname`, `gpu_name`, `compute_capability`, `gpu_uuid`, `driver`, `cuda`, `torch`, `python`, `cpu_model`, `cpu_isa`, `os`.
- Models: `filename` and `sha256` for each model.
- Configuration: `cli_flags` (exact ComfyUI launch flags), `attention_backend` (as actually used, read from the log), `precision`, `sampler`, `scheduler`, `steps`, `cfg`, `resolution`.
- Inputs: `prompt_set` (name, split, sha256 of the prompt file), `seeds`.
- Freezing and outputs: `threshold_file_sha256` (where applicable), `start_time`, `end_time`, `raw_checksums`.

**Prompt set:** download PartiPrompts once, or COCO captions if PartiPrompts' licence doesn't suit. Fix the split by prompt ID into calibration 40%, dev 20% and test 40%. Commit `experiments/configs/prompts_{cal,dev,test}.txt` and record their sha256. **The test split is not used until §6.**

---

## 1. Node setup (WP0b, days 1–2)

Set up **every** node: at least 2× RTX 5080 (x86) and at least 2× DGX Spark (ARM64).

1. **OS and drivers.**
   - 5080 hosts: Ubuntu LTS with the NVIDIA driver and the CUDA version supported by Blackwell sm_120.
   - Sparks: stock DGX OS.
   - Record `nvidia-smi -q` in the manifest.
2. **Python environment.** Create one env per node with the **same** Python minor version everywhere.
   - x86: the official PyTorch CUDA wheel that supports sm_120.
   - Spark: NVIDIA's aarch64 PyTorch build for GB10.
   - Use the **same torch version on all nodes** if one exists for both. If not, record the mismatch; it becomes part of level L3.
   - Check: `python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.get_device_name(), torch.cuda.get_device_capability())"`
3. **ComfyUI.** Clone it, `git checkout <PINNED_COMMIT>` (start from `8b25bbc`, see doc 06; freeze it at the end of WP0b), and install its requirements. **Do not let it auto-update.** Record any failure on aarch64 (for example xformers) in `docs/pilot-notes.md`.
4. **Models.** Download SD1.5, SDXL base, SDXL-Turbo and an LCM-LoRA (optionally FLUX.1-schnell) to `models/checkpoints`. Compute sha256 for each and store it in `experiments/configs/models.json`. Every node must show identical hashes.
5. **Smoke test.** Generate one SDXL image through the ComfyUI API (`POST /prompt`, API-format workflow JSON) on each node.

**Acceptance:** every node produces an image, and every node's manifest is complete.

---

## 2. Pilot measurements (WP0b, days 2–3): go/no-go #0 by Dec 6

Run each item as its own run ID.

| # | Task | How | Output in `summary.json` |
|---|---|---|---|
| P1 | **x_T across CPU ISAs** | On a 5080 host (x86) and a Spark (ARM), for seeds 0–99 and the latent shapes of SD1.5 (1×4×64×64) and SDXL (1×4×128×128), reproduce ComfyUI's noise **exactly as `comfy/sample.py: prepare_noise` does**: `torch.manual_seed(seed)`, then `torch.randn(shape, dtype=float32, device="cpu")`. Store the sha256 of the raw bytes | `n_seeds`, `n_identical` per shape. Also repeat with a second torch version if one is available |
| P2 | **First look at L0 and L3** | SDXL, 30 steps, euler, fp16 default flags. Use 20 *calibration* prompts × 2 seeds, on 5080-A twice (L0), on 5080-B (L2) and on Spark-A (L3) | Fraction of pixel-identical images per pair, and the median and maximum per-pixel difference |
| P3 | **Throughput** | Time per image for SD1.5 and SDXL on the 5080 and the Spark, warm cache, n = 20 | s/image, median and p95. This sizes the RQ1 grid (§4) |
| P4 | **Attack feasibility** | Launch with `--fp8_e4m3fn-unet` on each node type and generate an image. Check whether any FP4/NVFP4 path works at the pinned commit | Works / fails per node, and the speed-up vs fp16 |
| P5 | **WOMBO hypothesis W1** | After §3 step 1 works, record honest trajectories for 10 prompts. Compute the cosine similarity between `x_i` and `x_{i+1}` (flattened) for every i | Minimum, median and maximum cosine. **If the minimum is ≥ 0.70, the frame-copy forgery F1 already passes the deployed SN30 rule.** Report this to the paper author immediately |

**Go/no-go #0:**
- If P2 shows the 5080 and the Spark are **pixel-identical** on all pairs, book the L4 rentals **now** rather than in January, because all the variation will come from L4.
- Send P1–P5 to the paper author.

---

## 3. Build the instrumentation (WP1, Dec 7 – Jan 3)

### 3.1 Trajectory-commit node (a ComfyUI custom node)

Functional spec. These facts were checked in doc 06:
- Mirror `nodes.py: common_ksampler`. Pass your own `callback` into `comfy.sample.sample(...)`. ComfyUI calls it as `callback(i, denoised, x, total_steps)`. Here `x` is the latent **before** step i's update, and `denoised` is the CFG-combined prediction D_i.
- These tensors are in the model's **internal latent space**: `process_latent_in` has already been applied (`comfy/samplers.py`, around L1224). Record them **as they are**, in their native dtype, moved to the CPU. Don't rescale them.
- Also record `sigmas` (from the sampler or `KSampler.sigmas`), and the **final latent**. The callback never sees the final latent, so capture it from the sampler's return value. It is returned *after* `process_latent_out`, so also save `process_latent_in(final)`, or record x_T inside a wrapper around the sampler function.
- Write one file per job: `trajectory.safetensors` with keys `x_000..x_{T-1}`, `D_000..D_{T-1}`, `x_final`, `sigmas`, plus metadata (workflow digest, seed, sampler, scheduler, steps, cfg, model sha256).
- Commitment: a Merkle tree whose leaves are `sha256(name || dtype || shape || raw_bytes)` per tensor, in a fixed order. Output the root as a hex string.
- Only deterministic samplers are allowed: `euler`, `heun`, `dpmpp_2m`, `ddim`, `uni_pc`. **Reject** ancestral and SDE samplers. Their per-step noise is drawn on the GPU (doc 06 §1.1).

**Acceptance tests:**
- T1: the image produced with the node is **pixel-identical** to the image from the stock KSampler (same node, same seed). That is, recording must not change the computation.
- T2: re-running the same job on the same GPU gives an **identical Merkle root**. If it doesn't, L0 isn't deterministic; report this, because it's a finding.

### 3.2 Verifiers (outside ComfyUI is fine, but load models through ComfyUI's loader)

Implement five verdict functions. Each returns `pass`, `fail` or `inconclusive` plus its raw scores.

| ID | Spec |
|---|---|
| **E0** | Re-run the full job on the verifier node. Compute the pixel-equality flag, LPIPS (pin the backbone, e.g. AlexNet, and the library version) and DINOv2 cosine, the last with a pinned checkpoint. Thresholds come from calibration (§5) |
| **E0-N** | **A faithful copy of SN23** (doc 06 §3): CLIP `vit_base_patch16_clip_384.laion2b_ft_in12k_in1k` via timm, cosine of the validator's image against the provider's image. Full reward if > 0.9, `(sim + 0.1)^3` between 0.4 and 0.9, and 0 otherwise. Also implement the pHash rule (Hamming distance ≤ 6). **Copy the logic line by line from the audited commit, and cite the file and lines in a code comment** |
| **E2-W** | **A faithful copy of SN30** (doc 06 §2): require the frame count to equal the step count, sample 3 indices, re-run one step from `frame[i]`, take the cosine of the flattened result against `frame[i+1]`, compute `score = max(min_cos·0.5 + 0.5, 0)`, and fail if score < 0.85. Because it is our pipeline rather than theirs, use **ComfyUI's** one-step replay (below), and document that adaptation |
| **E1** | (a) Recompute x_0 noise exactly, as in P1, and compare it with the committed `x_000`. Note that `x_000` is the *noise-scaled* state, so apply `model_sampling.noise_scaling(sigmas[0], noise, latent, max_denoise)` the way `KSAMPLER.sample` does. (b) Check that the committed `sigmas` equal the schedule computed from (scheduler, steps, model). (c) Check that VAE-decoding `x_final` gives the committed image. Pixel-exact is expected on the same GPU; on a different GPU use a calibrated tolerance |
| **E2-H, Tier A** | On the CPU, in float64, recompute `x_{i+1}` from the committed `(x_i, D_i, D_{i-1}, σ)` using the solver formula: paper Eq. (1) for euler, Eq. (2) for dpmpp_2m. **Check these against the source of `comfy/k_diffusion/sampling.py: sample_euler` / `sample_dpmpp_2m` at the pinned commit.** Compare with the committed `x_{i+1}` (and `x_final` for the last step) using the max-abs and relative-L2 error. Record both |
| **E2-H, Tier B** | For k sampled steps, recompute `D̂_i = CFG(model(x_i, σ_i, cond))` on the verifier GPU and compute the distance to the committed `D_i`, using the metric chosen in §5 |

**One-step replay (Tier B and E2-W), the hard part:**
- Feed the committed `x_i` **in internal latent space** directly to the model wrapper. Do **not** push it through `process_latent_out` / `process_latent_in`; that round trip adds rounding error.
- Recommended route: build the `CFGGuider` (`comfy/samplers.py: class CFGGuider`, with `set_conds`, `set_cfg`), run its preparation as `outer_sample` does, and call the inner CFG model on `(x_i, σ_i)` once. The alternative is a custom KSAMPLER whose sampler function makes exactly one model call at a given σ and returns `denoised`.
- **Acceptance test T3 (critical):** on the **same GPU and config** as the provider, replayed `D̂_i` must equal committed `D_i` **bit for bit** for every i. If it doesn't, the replay is wrong. Do not proceed until T3 passes.

### 3.3 Attack injectors

All attacks are controlled by an experiment flag. Ground-truth labels are written to a sidecar file that verifiers never read.

| ID | How |
|---|---|
| A1 | Run with T' ∈ {25, 20, 15} steps. Then make the commitment *claim* T = 30. Version (a) keeps the real σ schedule, so Tier A should catch it. Version (b) **forges** the claimed 30-step σ schedule and re-labels the states (the strongest variant) |
| A2 | Launch ComfyUI with `--fp8_e4m3fn-unet` and commit as if fp16 |
| A2b | FP4/NVFP4, only if P4 showed it works |
| A3 | Use SDXL-Turbo (1–4 steps) or LCM-LoRA (4–8 steps), then forge a 30-step trajectory by interpolation or solver inversion (see F3) |
| A4 | Use a cheaper sampler and commit it as the required sampler |
| A5 | Generate at 0.5× resolution and upscale. Mainly an E0 attack |
| A6 | Truncate at step j < T and extrapolate the remaining states |
| A7 | Return the stored output of a near-duplicate prompt (edit distance ≤ 2 words) |
| A8 | Return a random unrelated image or trajectory (control) |
| F1 | Set `x_{i+1} := x_i` (and `D_i := x_i`) for the faked steps |
| F2 | Compute anchor steps honestly and linearly interpolate the states between them |
| F3 | Compute m = sT steps honestly. For the remaining steps, set the states by interpolation, then **solve the solver equation for D_i** so that Tier A passes exactly. Sweep s ∈ {0.1, 0.25, 0.5, 0.75, 1.0} |
| F4 | Commit the complete, consistent trajectory of A2 or A3 |
| M | Falsify only the metadata (GPU name, timing). Negative control: verdicts must not change |

**Measure β_A** (GPU time saved) for each attack on the 5080: `1 − t_attack / t_honest`, median over 20 jobs.

---

## 4. RQ1: honest variation (WP2, Jan 4–31)

1. **Owned grid (L0–L3).**
   - Configs: precision {fp16, bf16, fp32 (`--force-fp32`)} × attention {SDPA (`--use-pytorch-cross-attention`), split or quad} × sampler {euler, dpmpp_2m} × `--deterministic` {off, on}. That is 24 configs.
   - Models: SD1.5 and SDXL.
   - Prompts: calibration plus dev prompts × 3 seeds. If P3 says the grid is too slow, cut the prompts. Never cut the configs; ask the paper author first.
   - Run on 5080-A, 5080-B, Spark-A and Spark-B. Repeat a 10% subset on 5080-A for L0.
   - Record the trajectory for every job (§3.1).
2. **Rentals (L4).** Book an RTX 4090, an RTX 3090 and one of T4, L4 or A100. Run **only** the reference config (fp16, SDPA, euler and dpmpp_2m, deterministic off) and the precision factor, on calibration plus dev prompts × 3 seeds, for SDXL (and SD1.5 if time allows). Use the same container image, the same ComfyUI commit and the same model hashes, and record full manifests.
3. **Per pair, compute:**
   - the image-level pixel-equality rate, LPIPS and DINOv2;
   - for each step i, the distance between the two runs' `D_i` (max-abs and relative L2), and the Tier A residual.

   Use pairs within each level L0–L4.
4. **Outputs:** fill R1.1–R1.8. Save the figure data for R1.4 and R1.5 as CSV in `summary.json` or alongside it.

---

## 5. Calibration and freezing (end of WP2): no attack data before this step

Use the **calibration split only**.

1. **E0 thresholds.** Use the draft's rule: `t_pass` is the lowest score at which at least 99% of honest pairs pass, and `t_fail` is the highest score at or below which at most 0.5% of honest pairs fall. Use honest pairs pooled over the levels you intend to support (state which: L3 and L4).
2. **Tier B metric and τ_i.**
   - Choose the distance metric on the **dev** split. Candidates: relative L2, max-abs, cosine on `D_i`. Pick the one with the best honest/attack separation on the dev split, where only F3 and A2 attack samples may be generated, on dev prompts.
   - Then set `α_s = 1 − (1 − 0.01)^(1/k)` for each candidate k ∈ {1, 2, 3, 5, 8}, and set `τ_i` as the (1 − α_s) quantile of honest per-step distances at step i. Pool over hardware pairs, and take the max over pairs if they differ a lot.
3. **Tier A ε_A.** Use the maximum honest residual × 2, or 0 if Tier A is bit-exact across nodes.
4. **Freeze.**
   - Write `experiments/configs/thresholds_v1.json` and record its sha256 in every later manifest.
   - Commit it to git **before** running §6.
   - Any later change means `thresholds_v2.json` and a new, labeled experiment group.

---

## 6. RQ2: attacks (WP3, Feb 1–28)

Use the **test split** prompts. Providers: 5080s. Verifiers: Sparks, plus the L4 data, used as the other side of each pair.

1. For each attack A1–A8, F1–F4 and M, produce at least **30 attacked jobs per cell**. A cell is (attack × model × hardware pair). Produce **at least 299 honest jobs per stratum**, which bounds the false-rejection rate below 1% at 95% confidence.
2. Run every job through E0, E0-N, E2-W, E1 and E2-H with k ∈ {1, 2, 3, 5, 8} (Tier B outputs for all k can be computed from one pass that checks all steps).
3. **Outputs:**
   - The acceptance-rate table for E0-N and E2-W (R2.5).
   - Sensitivity q at job-level FPR ≤ 1% per evidence level, with Wilson CIs (R2.3).
   - The per-step separability r_A and the honest α_s (R2.6, R2.8).
   - β_A (R2.4).
   - The F3 partial-faking sweep: empirical q(s, k) (R2.7).
4. **Store per-job verdicts** in `summary.json` as long-format rows: `job_id, attack, s, level_pair, evidence, k, verdict, score`. The paper author does the statistics and figures from these rows.

---

## 7. RQ3: escrow and testbed (WP5, Jan 4 – Mar 14, parallel second person)

1. **Anchor program** (`code/program/`). Accounts: `Job` (a PDA per job id), escrow token vault (OCC SPL), `ProviderBond`, `Config`.

   | Instruction | Purpose |
   |---|---|
   | `create_job` | Requester funds P plus the verifier fee |
   | `accept_job` | Provider locks bond B |
   | `commit_result` | Merkle root plus output digest. Records the slot |
   | `draw_sample` | Callable after `commit_slot + DELAY`. Reads the `SlotHashes` sysvar entry for `commit_slot + DELAY`, which must still be inside the sysvar window of about 512 slots. Computes `sampled = H(slot_hash ‖ job_id) < p` and the seed for the step indices |
   | `submit_verdict` | Verifier. Records the verifier's own commitment, then its verdict |
   | `escalate` / `final_verdict` | Two-of-three adjudication |
   | `release` / `refund` / `slash` | Settle funds |
   | `timeout_refund` | Refund if the job stalls |

   State machine: as in Fig. 3 of the original draft.
2. **Orchestrator.** A minimal service: queue, assignment (5080 = provider, Spark = verifier, a node never verifies itself), transaction relay, and an event log of all on-chain and off-chain events with timestamps.
3. **Measurement.** For each path (accept unsampled, sampled-pass, sampled-fail with dispute, timeout refund), run at least 100 jobs on the **local validator** and at least 30 on **Devnet**. Record compute units, fee in lamports, and latency to processed, confirmed and finalized. Record the RPC endpoint, the priority-fee policy and the time of day. Interleave the paths. Fill R3.4.
4. **Verifier cost per job** from the RQ2 runs: verifier GPU-seconds for E0, E0-N, E2-W, E1 and E2-H at each k. Also record storage in MB per job. Fills R3.1 and R3.3.
5. **Testbed demo.** Run the end-to-end flow with real 5080 providers, including injected attackers, and real Spark verifiers, at p ∈ {0.05, 0.1, 0.25}. These are the points overlaid on Fig. R3.6.

---

## 8. Monte Carlo (WP4; the paper author can do this from the §6 outputs)

Simulate providers using strategy s ∈ [0, 1], with the measured r_A, α_s and β_A, over (p, k, B/P). Estimate the realized gain Δ(s). This checks Proposition 3 (the all-or-nothing response) and the deterrence boundary of Eq. (6). Inputs: the §6 summaries. Output: R3.2, R3.5 and R3.6.

---

## 9. Hand-off checklist (end of WP3/WP5)

- [ ] All runs have complete manifests, and raw data is archived with checksums
- [ ] `thresholds_v1.json` was committed before the first RQ2 run (check the git log dates)
- [ ] Acceptance tests T1, T2 and T3 passed and are logged
- [ ] The doc 06 facts were re-confirmed at the pinned ComfyUI commit (noise on CPU, callback semantics, solver formulas)
- [ ] The offline-only attack policy was followed, and any deployed-network contact went through the paper author
- [ ] The artifact is ready for Zenodo (R0.2)

---

## 10. Placeholder map (paper `\res{ID}` → source)

| ID | Content | Source run / section |
|---|---|---|
| R0.1 | Rented GPU models | §4.2 manifests |
| R0.2 | Repository URL and DOI | §9 |
| R0.3 | Summary of findings | Paper author, after all results |
| R0.4 | Version table | All manifests |
| R0.5 | Split sizes | §0 prompt files |
| R1.1 | x_T bit-exact across x86 and ARM | P1 |
| R1.2 | Tier A ε_A, and whether it is exact across CPUs | §4.3, §5.3 |
| R1.3 | Tier B metric | §5.2 |
| R1.4 | Per-step honest deviation vs step, and τ_i | §4.3, §5.2 |
| R1.5 | Deviation by level (figure) | §4.3 |
| R1.6 | Bit-identical fractions per level | §4.3 |
| R1.7 | Factor effects; deterministic profile and its cost | §4.1 |
| R1.8 | RQ1 answer | Paper author |
| R2.1 | Deployed-rule headline | §6 (E0-N, E2-W) |
| R2.2, R2.3 | Number of attacks detected; q at FPR ≤ 1% | §6 |
| R2.4 | β_A per attack | §3.3 |
| R2.5 | Acceptance table of the deployed rules | §6 |
| R2.6 | Chosen k | §5.2 / §6 |
| R2.7 | Partial-faking q(s, k) | §6 (F3 sweep) |
| R2.8 | Inseparable attacks | §6 |
| R2.9 | RQ2 answer | Paper author |
| R3.1 | Verifier GPU-s, relative to E0 | §7.4 |
| R3.2 | k*, p*, bond ratio, agreement with theory | §8 |
| R3.3 | Trajectory storage (MB) | §7.4 |
| R3.4 | Escrow CU, fees, latency | §7.3 |
| R3.5 | Pareto data | §6 + §7.4 |
| R3.6 | Deterrence region data | §8 + §7.5 |
| R4.1, R5.1 | Implications, conclusion | Paper author |
