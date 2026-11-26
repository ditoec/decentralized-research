# Engineering Runbook: Step-by-Step Technical Work

**Audience:** the engineer who builds and runs the experiments.
**Paper:** `paper/manuscript_ESJ.docx` (Emerging Science Journal, Word). Every red `[R…]` placeholder in the paper is filled from a run listed in the **Placeholder map** (§10).
**Ground rules:**
1. Never type a number into the paper by hand. Every number comes from `experiments/runs/<run_id>/`.
2. Thresholds are frozen and hashed *before* attack data is looked at.
3. Pin every version, and record it in the run manifest.
4. Paid infrastructure is capped at **US$200 in total, on RunPod only**. Budget and spending rules: `docs/10-paid-infrastructure-and-thesis.md` §2.5. The co-author who holds the RunPod account approves every pod start.
5. The six DGX Sparks are the only owned hardware, and they **run a live production platform**. Follow the rules in §1.1 on every run. There are no owned RTX 5080s: every x86 GPU is a RunPod pod.

Background reading: `docs/05-revised-design.md` (the design), `docs/06-code-audit.md` (the ComfyUI internals this relies on), and Figure 2 and Section 3-2 of the manuscript (the protocol).

**Who's who.** "The paper author" means the corresponding author, Anjas Risky Maradita. Send results, go/no-go reports and any question that would change a config, threshold or scope there.

**Status.** Last updated 2026-11-25 (retention classes F/O/I implemented and tested, §3.5; pilot P1–P7 done on Sparks 4–5, RTX 4090 and RTX 3090; RTX 5090 in place of the out-of-stock RTX 5080; Spark-6 set up; results in §3 findings 7–16, summary in `docs/11-go-no-go-0.md`). It matches `paper/manuscript_ESJ.docx` (Emerging Science Journal format): equation numbers, placeholder IDs and notation are as in that file.

**Notation (same as the manuscript).** T = number of sampler steps. x₀ = the initial (noise-scaled) latent, x_T = the final latent. D_i = the CFG-combined denoised prediction at step i. σ_i = the noise level at step i. k = number of steps checked by Tier B. p = probability that a job is sampled. In code and file names, x₀ is `x_000`.

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
- Sparks only: `cotenants` (the production services running on the node during the run).
- Rented nodes only: `provider` (runpod), `cloud_type`, `host_id` or data-center ID, `hourly_rate_usd`, `billed_hours`, `cost_usd`.
- Freezing and outputs: `threshold_file_sha256` (where applicable), `start_time`, `end_time`, `raw_checksums`.

**Prompt set:** download PartiPrompts once, or COCO captions if PartiPrompts' licence doesn't suit. Select **1,000 prompts** and fix the split by prompt ID into calibration 40%, dev 20% and test 40%. Commit `experiments/configs/prompts_{cal,dev,test}.txt` and record their sha256. **The test split is not used until §6.**

Also commit three fixed subsets, each keeping the 40/20/40 proportions where it spans splits:
- `prompts_rent500.txt`: 500 prompts (200 calibration, 100 dev, 200 test), for the reference config on RunPod nodes.
- `prompts_grid200.txt`: 200 prompts from calibration and dev only, for the non-reference configs on the Sparks.
- `prompts_prec100.txt`: 100 prompts taken from `prompts_grid200.txt`, for the precision factor on RunPod nodes.
- `prompts_grid50.txt`: 50 prompts taken from `prompts_prec100.txt`, for every non-reference factor config, on the Sparks and on RunPod (decision of 2026-11-26).
- `prompts_l2_50.txt`: 50 calibration prompts, for the unit-to-unit subset on all six Sparks and on the second RTX 5090.

---

## 1. Node setup (WP0b, days 1–2)

**Nodes.**

| Node | Address | Use |
|---|---|---|
| Spark-4, Spark-5, Spark-6 (DGX Spark, ARM64) | see `docs/local-nodes.md` | Main research nodes: grid, attacks, verification, storage |
| Spark-1, Spark-2, Spark-3 (DGX Spark, ARM64) | see `docs/local-nodes.md` | The 50-prompt L2 subset only |
| RunPod pods (x86-64) | — | Consumer GeForce RTX only: RTX 5090 (the L3 card, decided 2026-11-24), RTX 4090, RTX 3090; RTX 4080 SUPER or 3090 Ti as stock substitutes |

Addresses and login details are in `docs/local-nodes.md`, which is kept out of git because this repository is public; ask the paper author for a copy. All six were inventoried on 2026-11-23 and are identical: DGX OS 7.5.0, kernel 7.0.0-1019-nvidia, driver 580.178.04, CUDA 13.0. Re-check these at the start of every work package, because automatic updates are on.

### 1.1 Rules on the Sparks (production is running)

1. **Never stop, restart or change a container you did not start.** That includes the ComfyUI already on Spark-1; it is a production service on a different version. Do not use it.
2. Start research containers with the label `research=esj`, a name starting with `esj-`, and a port bound to `127.0.0.1` only. Clean up only containers that carry that label.
3. **Memory is one pool for the CPU and the GPU.** A research job that runs out of memory can take a production model down. Run SDXL in fp16 as the normal load. Test fp32 on one node, off-peak, before using it in the grid. Do not run FLUX without a window agreed with the platform admin.
4. The run script must **pause when free memory is below 15 GB or free disk is below 200 GB**, and resume by itself.
5. There is no sudo. Do not install system packages. Everything runs in the research container.
6. Tell the platform admin before the first heavy run of each work package, and ask for the driver and kernel packages to be held until March.
7. **No timing numbers from a Spark** unless the admin has stopped the chat model for a quiet window. Record in the manifest which production services were running (`cotenants`).

### 1.2 Setup steps

**Implemented (2026-11-24).** One locked environment for both architectures: `code/env/setup_env.sh [main|alt]` builds Python 3.12.13 (uv-managed) with `env/lock-<stack>.txt`; the lock files were compiled for aarch64 and x86-64 and are identical. `main` = torch 2.14.1+cu130 (needs driver >= 580, i.e. a CUDA 13 host on RunPod); `alt` = torch 2.13.0+cu129 (built for the second software stack, which was dropped on 2026-11-24; keep it only as a fallback build). On the Sparks, `code/env/Dockerfile` wraps the same script into `esj-research:<stack>` (label `research=esj`). On RunPod we cannot push an image, so `tools/pod_job.sh` runs the same script inside the pod. Models: `experiments/configs/models.json` (sha256 = Hugging Face LFS object id). Prompts: `code/tools/make_prompts.py` wrote `experiments/configs/prompts_*.txt` and `prompts.json` (PartiPrompts, Apache-2.0, seed 20261123), plus `prompts_pilot20.txt` for P2.

**Network finding (2026-11-24).** The Sparks' internet egress is filtered and slow: Hugging Face's file CDN (`*.cdn.hf.co`, Xet transfer hosts) is unreachable, and other downloads run at about 250 KB/s per connection, so the image build alone takes hours. The RunPod HTTPS proxy (`*.proxy.runpod.net`) is reachable. Models therefore reach the Sparks from the operator's machine or through a RunPod relay pod (`python:3.12-slim`, CPU, US$0.12/h) that downloads from Hugging Face and serves the files under a random token path. Ask the network admin whether `huggingface.co` CDN egress can be opened for the research nodes; until then budget the transfer time.

1. **Images.** Build two research images from one Dockerfile, `arm64` for the Sparks and `x86-64` for RunPod, each pinned by digest. Use the **same Python minor version and the same torch version** in both if a build exists for both. If not, record the mismatch; it becomes part of level L3.
   - Spark: an aarch64 PyTorch build that supports the GB10 (compute capability 12.1). The PyTorch 2.9.1 found in the production image warns that 12.1 is above its supported maximum, so choose the build here and record it in `docs/pilot-notes.md`.
   - RunPod: the official PyTorch CUDA wheel that supports Blackwell consumer cards (compute capability 12.0). The official Runpod image `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404` (PyTorch 2.8.0, CUDA 12.8) runs on the RTX 5080.
   - Check: `python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.get_device_name(), torch.cuda.get_device_capability())"`
2. **ComfyUI.** In the image, `git checkout <PINNED_COMMIT>` (start from `8b25bbc`, see doc 06; freeze it at the end of WP0b). **Do not let it auto-update.** Record any failure on aarch64 (for example xformers) in `docs/pilot-notes.md`.
3. **Models.** Download SD1.5, SDXL base, SDXL-Turbo and an LCM-LoRA to a research model folder on each main Spark, outside the production model folders. Compute sha256 for each and store it in `experiments/configs/models.json`. Every node, rented pods included, must show identical hashes.
4. **RunPod.** Use Community Cloud. Record `nvidia-smi -q`, the driver, the host and the data-center ID of every pod in the manifest. Terminate pods when a run ends; an idle volume keeps billing.
5. **Smoke test.** Generate one SDXL image through the ComfyUI API (`POST /prompt`, API-format workflow JSON) on Sparks 4 to 6 and on one RTX 3090 pod (the cheapest consumer x86 pod).

**Acceptance:** every node produces an image, and every node's manifest is complete.

---

## 2. Pilot measurements (WP0b, days 2–3): go/no-go #0 by Dec 6

Run each item as its own run ID.

| # | Task | How | Output in `summary.json` |
|---|---|---|---|
| P1 | **Initial noise x₀ across CPU ISAs** | On a RunPod pod (x86, any GPU; the test uses the CPU only) and a Spark (ARM), for seeds 0–99 and the latent shapes of SD1.5 (1×4×64×64) and SDXL (1×4×128×128), reproduce ComfyUI's noise **exactly as `comfy/sample.py: prepare_noise` does**: `torch.manual_seed(seed)`, then `torch.randn(shape, dtype=float32, device="cpu")`. Store the sha256 of the raw bytes | `n_seeds`, `n_identical` per shape. (No second torch version: the x₀ check is build-agnostic, see Decisions) |
| P2 | **First look at L0, L2, L3 and L4** | SDXL, 30 steps, euler, fp16 default flags. Use 20 *calibration* prompts × 2 seeds, on Spark-4 twice (L0), on Spark-5 (L2), and on a RunPod RTX 5080 (L3), RTX 4090 and RTX 3090 (L4). The pilot rentals cost about US$8 in total; set them up by hand, the launcher of §3.4 does not exist yet | Fraction of pixel-identical images per pair, and the median and maximum per-pixel difference |
| P3 | **Throughput** | Time per image for SD1.5 and SDXL on a Spark (beside production, at a busy hour and at a quiet hour) and on each pilot pod, warm cache, n = 20 | s/image, median and p95. The Spark numbers size the RQ1 grid (§4); the pod numbers size the RunPod budget |
| P4 | **Attack feasibility** | Launch with `--fp8_e4m3fn-unet` on a Spark and on the RTX 5080 and generate an image. Check whether any FP4/NVFP4 path works at the pinned commit | Works / fails per node, and the speed-up vs fp16 |
| P5 | **WOMBO hypothesis W1** | After §3 step 1 works, record honest trajectories for 10 prompts. Compute the cosine similarity between `x_i` and `x_{i+1}` (flattened) for every i | Minimum, median and maximum cosine. **If the minimum is ≥ 0.70, the frame-copy forgery F1 already passes the deployed SN30 rule.** Report this to the paper author immediately |

| P6 | **Co-tenancy** | On Spark-4, run 50 SDXL jobs while its chat model is serving requests and again while it is idle (read the load from the existing Prometheus on Spark-5) | Fraction of bit-identical trajectories between the two conditions. **If it is below 1, report it immediately**: shared load would then be a source of honest variation |
| P7 | **Memory footprint** | Peak memory of the research container for SD1.5 and SDXL in fp16, bf16 and fp32 on Spark-4 | GB per config, and the free memory left on the node. Decides whether fp32 may run in the grid |

**Commands (implemented 2026-11-24).** Every pilot item is one call of `code/tools/workloads/pilot.sh` (`NODE=<tag> ITEMS="p1 p2 p3 p4 p5 p7"`), which drives `python -m trajver.pilot`:

| Item | Command | Compare / plot |
|---|---|---|
| P1 | `pilot noise --seeds 100` on each ISA | `pilot noisecmp RUN_A RUN_B` → n_identical, max ULP |
| P2 | `pilot gen --save-traj` (SDXL, 30 steps, euler, 20 × 2) | `pilot compare A B --steps-detail --e0-out e0.jsonl`; `plots stepdist` |
| P3 | `pilot gen` timings (first job excluded) | `plots throughput` |
| P4 | `pilot --flags=--fp8_e4m3fn-unet gen`, `pilot fp4` | speed-up vs P2/P3 |
| P5 | `pilot w1` | `plots w1`, `plots e2w` |
| P6 | `tools/workloads/p6_spark.sh` on the host: `pilot gen --save-traj` idle / beside `tools/gpu_load.py`, each with and without `--no-pin`; co-tenant load logged | `pilot compare` vs idle-pin |
| P7 | `pilot --flags=<precision> gen`, memory peaks in `summary.json` | `plots memory` |

On a Spark every command runs through `tools/spark_run.py` (§3.4). Every run also saves its figures under `<run>/figures/` (PNG, PDF and the CSV behind them) for the paper and the thesis.

**Go/no-go #0:**
- If P2 shows the RTX 5080 and the Spark are **pixel-identical** on all pairs, all the variation will come from L4. The pilot rentals show whether it does.
- Use P3 and the rented timings to re-estimate the RunPod cost of §4 item 2. If it exceeds the planned US$120, tell the paper author before WP2.
- Send P1–P5 to the paper author.

---

## 3. Build the instrumentation (WP1, Dec 7 – Jan 3)

**Implementation status (2026-11-23).** §3.1–§3.3 are implemented in `code/` as the Python package `trajver`, and tested on a Mac (MPS) with SD1.5. See `code/README.md` for setup and commands.

| Spec | Module |
|---|---|
| §3.1 recording, trajectory file, Merkle commitment | `trajver/job.py` (`sample_and_record`, `Pipeline.run`), `trajver/trajectory.py`, `trajver/commit.py`; ComfyUI node in `code/comfyui_trajectory/` |
| §3.2 E1 | `trajver/rules/e1.py`, `trajver/noise.py` |
| §3.2 Tier A, Tier B, E2-H | `trajver/solvers.py`, `trajver/rules/e2h.py`, `Pipeline.replay_denoised` |
| §3.2 E2-W, E0-N (deployed rules) | `trajver/rules/e2w.py`, `trajver/rules/e0n.py` (audited source cited in the module docstrings) |
| §3.2 E0 | `trajver/rules/e0.py` |
| §3.3 forgeries F1–F3, attack configs | `trajver/attacks/forgeries.py`, `trajver/attacks/configs.py` |
| Manifests, thresholds, theory | `trajver/manifest.py`, `trajver/thresholds.py`, `trajver/theory.py` |

Acceptance tests T1, T2 and T3 pass on MPS (`pytest tests/integration`). Findings from development, for the paper author:
1. **ComfyUI's batching depends on free memory.** At every model call it runs the conditional and unconditional CFG passes as one batch only if enough memory is free (`comfy/samplers.py: _calc_cond_batch`), and VAE decoding tiles by free memory too. A different batch changes the arithmetic, so identical jobs can give different trajectories depending on other memory use. T1 failed intermittently until this was pinned. `trajver` now pins both decisions while sampling, replaying and decoding (`comfy_env.pinned_batching`, recorded as `pin_batching` in every trajectory). Treat this as a protocol requirement, and on the shared Sparks as a likely co-tenancy effect: P6 should run with the pin on and off.
2. **A full frame copy passes Tier A.** With every step faked and D_i := x_i, the solver maps x_i to itself, so the forged trajectory is solver-consistent. Tier B catches it. Partial copies fail Tier A at the boundary.
3. **Storage is larger than estimated.** ComfyUI keeps latents in float32, not fp16: about 3.9 MB per 30-step SD1.5 job and about 15 MB per SDXL job, plus conditioning. R3.3 is measured, so the paper is unaffected, but the "about 7.7 MB" in doc 05 §4.1 is too low.
5. **The noise schedule depends on where ComfyUI computes it.** `KSampler` computes the sigmas on whatever device the model's sampling object sits on: the CPU before the first job of a process, the GPU after the model loads. On an RTX 5080 the two schedules differed by one float32 ULP (2.4e-7), and that changed the final latent of an otherwise identical job by up to 0.36, so T1 and T2 failed on CUDA. `trajver` now computes a canonical schedule on the CPU (`job.canonical_sigmas`) and passes it to the sampler; with that, T1–T3 pass on the RTX 5080 (Runpod pod, 2026-11-23). Treat the canonical schedule as a protocol requirement.
6. **The initial noise is not bit-identical across CPU instruction sets (preliminary P1).** With the same seed and PyTorch 2.8.0, an AMD EPYC (x86-64) CPU and an Apple M1 (ARM64) CPU give the same random stream but values that differ in the last one or two ULPs, for every tensor of 16 or more elements. Smaller tensors are identical, which points to PyTorch's vectorized normal sampler (AVX2 vs NEON). On ARM, PyTorch 2.8.0 and 2.15.0 agree exactly. The exact x₀ check of E1 therefore fails between an x86 provider and an ARM verifier. Confirm on a DGX Spark in the pilot, then choose: a canonical noise path (for example drawing in chunks below the vectorized threshold, which also changes the provider's noise) or a tolerance of a few ULPs on x₀. Paper author's decision.
7. **Pilot P1 on a DGX Spark (2026-11-24, run `20261124-wp0b-p1-noise-spark4-01`): the noise differs even between two ARM machines.** Spark-4 (Cortex-X925, Linux aarch64, torch 2.14.1) and an Apple M1 Pro (macOS arm64, torch 2.14.1 and 2.15.0) give 0 of 100 identical seeds for both latent shapes; 98.5% of values are equal and the rest differ by at most 3 ULP (max abs 4.8e-7). PyTorch dispatches the Spark to its `SVE128` CPU path; forcing `ATEN_CPU_CAPABILITY=default` does not make the bytes match, so the build itself (compiler, libm) matters, not only the vector unit. The difference is therefore "per CPU and PyTorch build", not "x86 vs ARM". This supports the approved ULP tolerance for E1(a); the x86 pod run of P1 still has to be compared with the Spark (Spark vs x86 is the pair that matters).
8. **Pilot results on a rented RTX 4090 (Secure Cloud, 2026-11-24, runs `20261124-wp0b-*-rtx4090-01`; same environment as the Sparks: Python 3.12.13, torch 2.14.1+cu130, ComfyUI 8b25bbc).**
   - P1, x86 (RTX 4090 host CPU) vs Spark-4: 0 of 100 seeds identical for both shapes; 61.5% of values equal; largest difference 2.3e-6 (unit-variance noise). Near zero this is up to 8.6 million ULP, so the E1 tolerance is absolute, not in ULP (see Decisions).
   - P3: SD1.5 512², 30 steps: median 1.94 s/image (n = 19). P2 timing, SDXL 1024², 30 steps: median 3.87 s/image (n = 39).
   - P4: `--fp8_e4m3fn-unet` on SDXL runs but is slower than fp16 (median 4.18 s vs 3.87 s; peak GPU memory 16.6 vs 19.3 GB). The NVFP4 path of the pinned commit runs only through comfy_kitchen's dequantize fallback on Ada (8× slower than bf16 per linear layer): no fp4 speed-up on this card.
   - P5 (W1) on SDXL, 10 prompts: adjacent-state cosine min 0.977, median 0.9994. Hypothesis W1 holds: the deployed SN30 rule accepted every honest job and every F1, F2 and F3 forgery at s = 0.25, 0.5 and 1.0 (10/10 each). **Report to the paper author.**
   - Spend: balance 8.66 → 7.76 US$ for this pod (Secure Cloud at 0.89 US$/h, because no Community 4090 was available at create time). The per-run `cost_usd` in these manifests all measure from job start to the pull, so they overlap and must not be summed.
9. **Pilot results on the Sparks, SD1.5 (2026-11-24).** L0 (Spark-4 twice) and L2 (Spark-4 vs Spark-5): 40 of 40 jobs with identical images, final latents and Merkle roots, i.e. whole trajectories bit-identical. P1 Spark-4 vs Spark-5: 100 of 100 seeds identical. P3: median 1.94 s/image on each Spark beside production (sizing only, rule 7).
10. **Pilot results on the Sparks, SDXL (2026-11-24).**
   - P2, L0 (Spark-4 twice) and L2 (Spark-4 vs Spark-5): 40 of 40 identical images, latents and Merkle roots. Spark vs RTX 4090 (L4): 0 of 40 identical; mean per-image pixel difference median 1.19 levels (max single pixel 247); LPIPS median 0.005 (max 0.057), DINOv2 cosine >= 0.981, CLIP cosine >= 0.982, so the deployed SN23 rule (E0-N) accepts 40 of 40; pHash Hamming <= 1. Free-running D_i differ from step 0 (relative L2 1.4-3% median, up to 10.6%).
   - Honest Tier B across hardware (run `20261124-wp0b-replay-4090on-spark5-01`: Spark-5 replays every step of the 4090 provider's 40 trajectories): no step bit-exact; relative L2 of D̂_i vs D_i falls with the step, median 2.7% (max 4.8%) at step 0, 0.97% at step 10, 0.22% at step 25, 0.04% at step 29. Per-step tolerances τ_i are needed. Full replay of 30 steps: 19.9 s per job on a Spark.
   - Tier A across hardware: the Spark's CPU recomputation reproduced the 4090's x_{i+1} bit-exactly at all 1,200 steps (float32 replica); largest float64 residual 2.8e-8. ε_A can be set at the float64 rounding level.
   - P4 on Spark-4: fp8 SDXL 13.55 s vs fp16 12.45 s (median); NVFP4 only via the dequantize fallback (0.19× bf16 speed). Same picture as the 4090: no cheaper path at the pinned commit on either card.
   - P5 on Spark-4: W1 holds (min adjacent cosine 0.977); SN30 accepted all honest jobs and every F1-F3 forgery (10/10 each).
   - P7 on Spark-4 (runs `*-p7-*-spark4-02`): host memory drop SD1.5 fp16/bf16 7.9/7.6 GB, fp32 13.1 GB; SDXL fp16/bf16 22.0/22.2 GB (free memory stayed >= 26 GB). **SDXL fp32 is not allowed on a Spark beside production:** the first P7 attempt took host free memory from about 49 GB to 5.9 GB; the runner's guard stopped it three times and production was unaffected (no restarts, no OOM kill), but the runner now backs off 10 minutes after a guard stop and aborts after three. Run SDXL fp32 only on RunPod or in an admin-agreed window.
   - Spark timing beside production (sizing only): SD1.5 1.94 s, SDXL 12.4 s per image (fp16, 30 steps).
11. **Pilot results on a rented RTX 3090 (Secure Cloud, EU-CZ-1, 0.50 US$/h, host CPU AMD EPYC 7C13; 2026-11-24, runs `20261124-wp0b-*-rtx3090-01`; same environment).**
   - P1: the 3090 host and the 4090 host give 100 of 100 identical seeds for both shapes, so the two x86 hosts agree bit for bit; against Spark-4, 0 of 100 (max abs 2.3e-6, as for the 4090). The 4090 host's CPU model was not recorded; `pod_job.sh` now saves `lscpu` with every pod run.
   - P2 (L4): 0 of 40 identical images against Spark-4 and against the 4090. Spark vs 3090: mean pixel difference median 1.46 levels (max 232), LPIPS median 0.0064 (max 0.054), DINOv2 cosine >= 0.927; 4090 vs 3090: LPIPS median 0.0077 (max 0.048), DINOv2 >= 0.940. **The deployed SN23 rule (E0-N, full reward = CLIP cosine > 0.9) rejected one honest pair:** job `p00083_s1`, Spark-4 vs 3090, CLIP cosine 0.899 (reward 0.998); the same job scored 0.903 for 4090 vs 3090 and 0.98+ for Spark vs 4090. Honest cross-hardware E0-N full-reward rate: Spark–3090 39/40, 4090–3090 40/40, Spark–4090 40/40.
   - P3: SD1.5 median 1.51 s/image (p95 1.74, n = 19); SDXL (P2 timing) 8.21 s (p95 8.35, n = 39).
   - P4: fp8 SDXL 8.65 s vs fp16 8.21 s (Ampere has no fp8 units; slower, as on the 4090 and the Spark). NVFP4 only via the dequantize fallback (0.11× bf16 speed).
   - P5: W1 holds (min adjacent cosine 0.977); SN30 accepted every honest job and every F1-F3 forgery (10/10 each), the same as on the 4090 and the Spark.
   - P7 (the "alternative way" for SDXL fp32, which may not run beside production on a Spark): torch peak reserved GPU memory SD1.5 fp16/bf16 5.5 GB, fp32 10.3 GB; SDXL fp16/bf16 20.0 GB, **fp32 24.6 GB, i.e. the whole 24 GB card**: ComfyUI offloads part of the model and the job takes 34.0 s/image, 4.1× fp16. SDXL fp32 therefore needs more than 24 GB to run without offload; it is feasible but slow on a 24 GB card and is excluded from the RQ1 grid. (Host-memory numbers on a pod are not meaningful: the host has about 1 TB shared with other tenants.)
   - Honest Tier B, 3090 provider → Spark-5 verifier (run `20261124-wp0b-replay-3090on-spark5-01`): no step bit-exact; relative L2 median 2.9% (max 5.3%) at step 0, 0.97% at step 10, 0.23% at step 25, 0.04% at step 29, i.e. the same profile as the 4090 provider (figure `tierb_honest_x86_to_spark`). Tier A: 1,200 of 1,200 steps bit-exact, largest float64 residual 2.8e-8.
   - Spend: balance 7.75 → 6.38 US$ over this rental (pod terminated after a checksum-verified pull).
12. **P6 co-tenancy on Spark-4 (2026-11-24, runs `20261124-wp0b-p6-*-spark4-01`).** 60 SDXL jobs (pilot20 prompts × seeds 0–2, 30 steps, trajectories kept) in four conditions, each compared with the first:
   - idle-pin (reference), load-pin, load-nopin, idle-nopin. "Load" is a second research container (`tools/gpu_load.py`) holding 6 GB and running fp16 matmuls at about 46 TFLOP/s; it slowed sampling from a median 11.7 s to 27.4 s (pin on) and 30.2 s (pin off) and lowered host free memory to a minimum of 19.0 GB.
   - **Result: 60 of 60 jobs bit-identical (images, final latents and Merkle roots) in every condition, with and without the batching pin.** The production chat model was serving requests during 1 (idle-pin), 6 (load-pin), 30 (load-nopin) and 6 (idle-nopin) of the 60 jobs; it was never driven by research code.
   - Interpretation: on a Spark at these memory levels, neither GPU contention nor ComfyUI's memory-adaptive batching changed a single byte; the batching decision did not flip because free memory never fell low enough (on the 16 GB Mac it did, finding 1). The pin stays a protocol requirement for small-memory providers. R1.9 is answered "bit-identical" for the loads tested; a Spark under memory pressure near the 15 GB guard was not tested, by rule.
   - Deviation from the §2 wording: the busy condition is load we own and can repeat, not the chat model's own traffic, because production services are never driven by research code. The chat model's actual load is logged per job.
14. **Spark-6 is a research node (2026-11-24).** It now holds the research image `esj-research:main` (same image ID as Sparks 4–5, copied with `docker save | docker load` over the internal link) and all four checkpoints (SD1.5, SDXL, SDXL-Turbo, LCM-LoRA; sha256 checked). Smoke test `20261124-wp0b-p1-noise-spark6-01`: initial noise identical to Spark-4 for 100 of 100 seeds, both shapes.
15. **Calibration dry run (`20261124-wp0b-calib-dryrun-01`).** `trajver.calibrate` ran end to end on the pilot's honest data (three x86 → Spark replays, 240 E0 pairs, P1). Underpowered on purpose: with 120 samples per step every requested quantile at k ≥ 2 is the sample maximum, so it is not `thresholds_v1` and `calibrate` now refuses to write a `thresholds_v*` file when `n·α_s < 1`. Early values: ε_A = 0 (Tier A bit-exact), τ_i (rel. L2, k = 3) 0.053 → 0.00056 from step 0 to 29, LPIPS t_pass 0.079, DINOv2 t_pass 0.940. Required for the real freeze at k = 3: at least 300 honest samples per step (1/α_s), pooled over the supported levels.
16. **Pilot results on a rented RTX 5090 in place of the RTX 5080 (Secure Cloud, EU-CZ-1, 1.39 US$/h, host CPU AMD EPYC 9554; 2026-11-24, runs `20261124-wp0b-*-rtx5090-01`).** The RTX 5080 had no stock all day; the 5090 is the consumer Blackwell card (sm_120) the L3 level needs (team decision).
   - **Go/no-go #0, criterion 1: consumer Blackwell ↔ Spark (Blackwell GB10) is not bit-exact: 0 of 40 identical images, latents and roots.** Mean pixel difference median 1.25 levels (max 226), LPIPS median 0.0050 (max 0.079), DINOv2 >= 0.981; vs 4090 and vs 3090 likewise 0/40 identical. SN23 E0-N full reward 40/40 against the Spark, the 4090 and the 3090.
   - P1: the EPYC 9554 (Zen 4, AVX-512) host gives noise identical to both other x86 hosts (100/100) and differs from the Spark by at most 2.3e-6: two families (ARM Spark, x86), no difference inside a family.
   - Honest Tier B, 5090 → Spark-5 (`20261124-wp0b-replay-5090on-spark5-01`): relative L2 median 2.7% (max 4.8%) at step 0, 0.97% at step 10, 0.22% at step 25, 0.04% at step 29; Tier A 1,200/1,200 bit-exact. All three x86 providers give the same profile (figure `tierb_honest_rtx_to_spark`).
   - P3: SD1.5 1.46 s/image, SDXL 2.71 s (fastest node). P4: fp8 SDXL 2.91 s vs fp16 2.71 s (slower again, also on consumer Blackwell); NVFP4 only via the dequantize fallback (0.10× bf16): no fp4 kernel at the pinned commit on sm_120 either. P5: W1 holds (min 0.977); SN30 accepts all honest jobs and F1–F3 (10/10 each).
   - P7: reserved GPU memory SD1.5 fp16/bf16 5.6 GB, fp32 10.4 GB; SDXL fp16/bf16 20.0 GB, fp32 32.9 GB, i.e. the whole 32 GB card again (14.6 s/image, 5.4× fp16). SDXL fp32 stays out of the grid.
   - Spend: about 22 minutes at 1.39 US$/h (≈ 0.5 US$); credit was added during the rental (balance 25.97 US$ afterwards), so the balance change does not isolate it.
17. **Pilot leftovers (2026-11-24).**
   - **Second sampler, dpmpp_2m (SDXL, 40 jobs):** Spark-4 vs Spark-5 bit-identical (40/40 Merkle roots); Spark-5 replaying Spark-4: Tier B exact at 1,200/1,200 steps. **Tier A's float32 replica is exact at only 560/1,200 steps** (float64 residual <= 1.0e-7 relative), even on the same node: ComfyUI computes dpmpp_2m's step coefficients (exp, log, expm1 of sigma) on the GPU, which a CPU cannot reproduce bit for bit; euler has no such coefficients. Hence **ε_A is per sampler** (euler 0, dpmpp_2m about 2e-7) and `calibrate` refuses to mix samplers in one thresholds file; `verify` refuses thresholds made for another sampler.
   - **The canonical CPU schedule differs between ARM and x86** in 4 of 31 entries by one float32 ULP (relative 9.7e-8); the three x86 hosts agree exactly. E1's exact schedule check therefore rejected every honest x86 job verified on a Spark. Fixed in the same build-agnostic way as x₀: protocol constant `SCHED_TOL_REL` = 1e-6 per entry (about 8 ULP) plus the exact step count (`rules/e1.py`, tests in `tests/unit/test_x0.py`). Tier A now passes a step when the float32 replica is bit-exact or the float64 residual is within ε_A (it compared the float64 residual with ε_A = 0 before).
   - **SD1.5 across GPUs (P3 images, 20 jobs):** Spark-4 vs Spark-5 20/20 identical; Spark vs every x86 card 0/20. The deployed SN23 rule fails the same honest job (`p00293_s0`) against all three x86 cards (CLIP 0.888–0.899 < 0.9), while the x86 cards agree with each other (CLIP 0.988–0.999 for that job, SN23 20/20). Figure `p3-sd15-spark4-01/figures/sn23_honest_fail_p00293`.
   - **SDXL-Turbo and LCM-LoRA run on the Sparks (attack A3).** Attacked jobs on Spark-4, 10 calibration prompts each: A1b (20 of 30 steps, 7.9 s), A3 Turbo (4 steps, 1.0 s), A3 LCM-LoRA (6 steps, 2.7 s), F1–F3 (s = 0.5); an honest SDXL job takes 12.4 s, so A3 Turbo saves about 92% of the work.
   - **Cross-node detection smoke test** (Spark-4 provider → Spark-5 verifier for the attacks; RTX 5090 → Spark-5 for 20 honest jobs), with the dry-run thresholds, which were fitted on these same honest pairs (in-sample: a pipeline test, not a result), runs `verify-*-on-spark5-02`: honest 0/20 rejected at every level; A1b, A3 Turbo, A3 LCM-LoRA rejected 10/10 by Tier B alone at k = 1, 3 and 8; F1–F3 (s = 0.5) 9/10 at k = 1 and 3, 10/10 at k = 8; E2-H at k = 3 rejected every attack; the deployed SN30 rule rejected none; E1 rejected none (the attacks claim the right seed, schedule and step count). Tier A rejected every attack, but only because these forgers' re-solved D_i do not round to a bit-exact float32 replica; a careful forger can fix that, so detection is credited to Tier B. The first verifier run (`-01`, deleted) rejected every honest x86 job: it exposed the schedule and Tier A exactness bugs above.
   - **Not done:** P3 Spark timing at a busy and a quiet hour (rule 7 needs an admin-agreed quiet window).
18. **WP2 dry run (2026-11-25, runbook §3.4 step 5; not paper data).** `wp2_rent.sh` (items `ref prec slice`, `LIMIT=7`: 7 prompts × 3 seeds = 21 jobs per run) on a rented RTX 4090, and `wp2_spark.sh` (items `ref grid l0 l2`, same limit) on Spark-4.
   - **A faulty RunPod host.** The first RTX 4090 pod (Community, US$0.34/h, Intel Xeon 8352V, driver 580.173) showed the card in `nvidia-smi` but no PyTorch build could use CUDA ("CUDA unknown error"), not even the image's own. It was terminated after about 10 minutes, before any job. `pod_job.sh` now stops at once when CUDA is unusable, so a workload cannot silently run on the CPU. Community 4090 capacity was then gone; the dry run used a Secure Cloud RTX 4090 (EU-RO-1, US$0.89/h, AMD EPYC 7352, driver 595.112).
   - **Rented side, runs `20261125-wp2-*-rtx4090-01` (26 runs, 546 jobs, all complete).** The seed handshake worked as designed: the pod stopped after generation (`out/GENERATED`), `pull_run.py --reveal-seed --wait` on Spark-5 checked the seed against `pod.json` and sent it, the pod extracted, re-verified and packed. Spark-5 pulled 1.97 GB at about 2.3 MB/s; `trajver.retention check` passed 26/26 runs (21/21 jobs each), and every manifest carries the class, the seed hash and the software pin (`lock-main:sha256:8865f8b0…`). Kept bytes per job: class O 41 % (SD1.5 euler), 50 % (SD1.5 dpmpp_2m), 38 % (SDXL euler, 6.6 MB) and 47 % (SDXL dpmpp_2m, 8.2 MB) of the full trajectory; class I 1.5 % (0.29 MB for SDXL). Spend: US$1.41 in total (both pods; balance 25.90 → 24.49). The manifests' `cost_usd` (US$0.50) counts only the job from `pod.json`'s start, not pod setup or the pull: use the RunPod balance for totals.
   - **RTX 4090 timings (median s/image, 30 steps):** SD1.5 fp16 1.05, bf16 1.04, fp32 2.1; SDXL fp16 3.6, bf16 3.5; `--deterministic` adds about 3–15 %; split attention costs 1.6–1.8 s (SD1.5) and 5.9–6.0 s (SDXL), about 1.6× SDPA. Re-estimate at these speeds: one rented card's §4 item 2 workload is about 5.0 GPU-hours, the 4090 factor slice about 6.8 more.
   - **Transfer volume, re-estimated from the measured sizes:** per rented card about 41 GB class F (SDXL 18.4 MB/job, SD1.5 4.5 MB/job over 1,800 jobs each) and 11 GB class O, so about 125 GB F and 34 GB O over three cards plus the L2 5090: higher than §3.5 rule 7's 90 GB F estimate, because SDXL class F dominates. At 2.3 MB/s that is about 19 hours of pulls. Today the pod packs everything after the last run, so it bills while the pull runs: about 6 hours per card, US$2–5 at the planned rates. **Fixed the same day:** `pod_job.sh` now packs each class-F run as soon as its manifest has an `end_time` (it needs no seed) and lists it in `out/READY`; `pull_run.py --wait` pulls READY runs while the pod keeps generating. Class O/I runs still wait for the seed and are packed at the end. Start the pull with `--wait` right after the workload starts (tested against a local `pod_server.py`).
   - **Spark side, runs `20261125-wp2-*-spark4-01/02` (45 runs, 945 jobs, all complete, no memory or disk stops).** Every factor level runs on a Spark beside production, including `--deterministic`, split attention and SD1.5 fp32. Median s/image (30 steps): SD1.5 fp16/bf16 SDPA 1.8 (`--deterministic` 1.95), split 4.3–4.5, fp32 SDPA 5.2–5.35, fp32 split 10.3–10.5; SDXL fp16/bf16 SDPA 11.7 (`--deterministic` 12.1–12.2), split 22.7–23.4. Split attention costs about 2.4× SDPA for SD1.5 and 1.9× for SDXL. The L0 repeat (`-02`) took the same time as the first pass.
   - **Spark grid duration at these speeds:** non-reference grid on `prompts_grid200.txt` × 3 seeds about 18 h (SD1.5) + 43 h (SDXL) = 61 h per node (Spark-4 and Spark-5 each); reference config on cal + dev × 3 seeds about 13.5 h per node (Sparks 4–6); L0 1.4 h, L2 0.5 h per node. Spark-4 about 76 h, Spark-5 about 75 h, Spark-6 about 14 h of GPU time: about 3.2 days per node run back to back, well inside WP2.
   - **Storage is short (needs a decision before WP2).** A stored trajectory is 19.1 MB for SDXL and 5.0 MB for SD1.5 (measured); gzip, zstd and xz save only about 9 % (float32 latents). Full WP2 at full retention needs about 324 GB on Spark-4, 312 GB on Spark-5, 90 GB on Spark-6, plus about 160 GB of pulled rentals: about 886 GB. The Sparks have 432, 505 and 514 GB free, and §1.1's stop condition keeps 200 GB free on each, so about 851 GB are usable, before any WP3 attack data. **Decided 2026-11-25: option (a)**, implemented in `wp2_spark.sh` and tested on Spark-4 (2 runs, SD1.5 bf16, seed hash in the manifest before generation, bundles 3/3, pair comparison on the 8 shared steps). With it WP2 needs about 200 GB on Spark-4, 190 GB on Spark-5 and 90 GB on Spark-6 plus about 160 GB of rentals, about 640 of the 851 GB usable. Options were: (a) keep full trajectories only for the reference config (calibration needs them) and store the other grid configs as class O bundles with a draw seed, as on the rentals; (b) cut `prompts_grid200.txt` to 100 prompts for SDXL non-reference configs (the runbook forbids cutting configs, not prompts); (c) ask the Spark admins for a lower disk floor; (d) move finished runs to a Spark with room over the 200 Gb links (helps balance, not the total).
   - **E1 on the Mac (not a WP2 issue).** On the Mac (MPS) the decoded `x_final` matched the delivered image only within one process; in a fresh verifier process 5 of 6 jobs differed (max 10–15 levels), because MPS falls back to memory-sized attention slicing in the VAE. On Spark-5, verifying Spark-4's SD1.5 runs passed E1 on 9/9 jobs for both split attention and SDPA (`20261125-wp2-e1check-*-spark5`), as did Tier A, E2-H at every k and E2-W.
   - **dpmpp_2m across hardware (pilot leftover, closed).** Spark-5 replayed every step of the dry run's class-F reference runs from the RTX 4090 (`20261125-wp2-replay-{sd15,sdxl}-{dpmpp_2m,euler}-rtx4090on-spark5-01`, 21 jobs each, `--force-fp16 --use-pytorch-cross-attention`). Tier B: dpmpp_2m's per-step profile matches euler's (relative L2 median at steps 0 / 10 / 20 / 29: SD1.5 0.065 / 0.0088 / 0.0037 / 0.00017, SDXL 0.048 / 0.0102 / 0.0037 / 0.00033; euler SD1.5 0.065 / 0.0091 / 0.0038 / 0.00021, SDXL 0.048 / 0.0105 / 0.0036 / 0.00039); no step was bit-exact across the two. Tier A: euler's float32 replica is exact at 630/630 steps per model (x86 trajectories checked on an ARM CPU), as in finding 16; dpmpp_2m's at 252/630 with a largest float64 residual of 1.3e-7, so 2× gives ε_A = 2.6e-7, above the Spark-only 2.0e-7 of finding 17. §3.5 rule 3 (take the larger of x86 and Spark) therefore matters: calibrate dpmpp_2m's ε_A on the rented class-F runs as well. These step-0 distances (4.8 % for SDXL) are larger than the pilot's 2.7–2.9 % (finding 16), which used ComfyUI's default flags rather than `--force-fp16`; the WP2 calibration uses the WP2 reference config, so only its own values count.
13. **Models on the Sparks.** SDXL-Turbo (`sd_xl_turbo_1.0_fp16.safetensors`, sha256 e869ac7d…) and the SDXL LCM-LoRA (a764e685…) are on Sparks 4, 5 and 6, hash-checked on each (fetched on a pod, pulled by Spark-4 through the pod's proxy, then copied over the internal link). Attack A3 can run.
4. **The deployed SN23 black-image filter never fires.**
4. **The deployed SN23 black-image filter never fires.** It compares 6×6 hashes of the two images with an 8×8 hash of a black image, so the strings never match. `e0n.py` reproduces this as deployed.

**Decisions (approved by the team, 2026-11-24).**
- Findings 1 and 5 are protocol requirements: the canonical CPU schedule and pinned batching (Methods §3-2, "Reproducibility requirements").
- Finding 6: providers keep ComfyUI's stock noise path; E1 accepts x₀ within an absolute tolerance in units of the unit-variance noise (|Δx₀|/σ₀). **Revised 2026-11-24 (team decision): the tolerance is a build-agnostic protocol constant, `X0_TOL` = 1e-5 (`rules/e1.py`), not a value measured per CPU or PyTorch version**, so no build pairing needs its own test and no torch-version comparison is run. It is 4.3× the largest difference seen across six machines (three Sparks, three x86 hosts incl. an AVX-512 EPYC 9554: 2.3e-6), and far below anything an attacker could use (a wrong seed differs by O(1) per element; tests in `tests/unit/test_x0.py`). `calibrate` records the P1 maximum as evidence and stops if 2× it ever exceeds the constant. The first version used a ULP limit; finding 8 showed ULP distance is the wrong measure.
- Rentals are consumer GeForce RTX only.

**Decisions at go/no-go #0 (2026-11-24, accepted for the paper author by the team).**
- **L3 card: RTX 5090** (consumer Blackwell, sm_120) replaces the RTX 5080 wherever this runbook and doc 05 name a 5080 (L3 rentals, rented providers in §6, the second same-model card for L2). The 5080 had no RunPod stock during the pilot.
- **SDXL fp32 is dropped from the RQ1 grid** (§4 item 1): not allowed beside production on a Spark, and it fills a 24 or 32 GB card and offloads. fp32 stays in the grid for SD1.5.
- **Transfer of rented trajectories:** retention classes by split (decided later the same day; §3.5). An earlier record here (pull while generating for all jobs) is superseded.
- **Second software stack: dropped** (decided later the same day; §4 item 1). The protocol pins one software image; an earlier record here (keep it) is superseded.
- The research containers may run on Sparks 4–6 under §1.1.

**Added 2026-11-24.** `trajver/attacks/run.py` (all of A1a/A1b, A2–A8, F1–F3 and M as runnable injectors with ground-truth sidecars), `trajver/verify.py` (E1, E2-H for k ∈ {1,2,3,5,8} from one all-steps pass, and E2-W; long-format `verdicts.jsonl`), `trajver/calibrate.py` (§5), `trajver/plots.py`, and `pilot replay` (honest all-steps Tier B distances for calibration). The ComfyUI node was run inside a ComfyUI server at the pinned commit (run `20261124-wp1-comfyui-node-ui-01`, with UI screenshots).

### 3.1 Trajectory-commit node (a ComfyUI custom node)

Functional spec. These facts were checked in doc 06:
- Mirror `nodes.py: common_ksampler`. Pass your own `callback` into `comfy.sample.sample(...)`. ComfyUI calls it as `callback(i, denoised, x, total_steps)`. Here `x` is the latent **before** step i's update, and `denoised` is the CFG-combined prediction D_i.
- These tensors are in the model's **internal latent space**: `process_latent_in` has already been applied (`comfy/samplers.py`, around L1224). Record them **as they are**, in their native dtype, moved to the CPU. Don't rescale them.
- Also record `sigmas` (from the sampler or `KSampler.sigmas`), and the **final latent**. The callback never sees the final latent, so capture it from the sampler's return value. It is returned *after* `process_latent_out`, so also save `process_latent_in(final)`, or record x_T inside a wrapper around the sampler function.
- Also record the **conditioning** the sampler received: the positive and negative text-encoder outputs, including the pooled outputs for SDXL, under keys `cond_pos`, `cond_neg` (plus `cond_pos_pooled`, `cond_neg_pooled`). E1 checks them.
- Write one file per job: `trajectory.safetensors` with keys `x_000..x_{T-1}`, `D_000..D_{T-1}`, `x_final`, `sigmas` and the conditioning keys, plus metadata (workflow digest, seed, sampler, scheduler, steps, cfg, model sha256).
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
| **E1** | (a) Recompute the initial noise exactly, as in P1, and compare it with the committed `x_000` (x₀). Note that `x_000` is the *noise-scaled* state, so apply `model_sampling.noise_scaling(sigmas[0], noise, latent, max_denoise)` the way `KSAMPLER.sample` does. (b) Check that the committed `sigmas` equal the schedule computed from (scheduler, steps, model). (c) Check that VAE-decoding `x_final` gives the committed image. Pixel-exact is expected on the same GPU; on a different GPU use a calibrated tolerance. (d) Re-encode the job's prompt and negative prompt with the pinned text encoder(s) and compare with the committed conditioning (`cond_*` keys), with a calibrated tolerance across GPUs. This catches a provider that conditions on a different or truncated prompt |
| **E2-H, Tier A** | On the CPU, in float64, recompute `x_{i+1}` from the committed `(x_i, D_i, D_{i-1}, σ)` using the solver formula: paper Eq. (1) for euler, Eq. (2) for dpmpp_2m. **Check these against the source of `comfy/k_diffusion/sampling.py: sample_euler` / `sample_dpmpp_2m` at the pinned commit.** Compare with the committed `x_{i+1}` (and `x_final` for the last step) using the max-abs and relative-L2 error. Record both |
| **E2-H, Tier B** | For k sampled steps, recompute `D̂_i = CFG(model(x_i, σ_i, cond))` on the verifier GPU and compute the distance to the committed `D_i`, using the metric chosen in §5. **Order matters (commit-before-reveal):** the verifier downloads only the inputs it needs (`x_i`, `σ_i`, the conditioning), computes every `D̂_i`, and records `sha256` of its results in the run log (on-chain in the §7 testbed) *before* it reads the provider's `D_i`. That way a verifier cannot simply copy the provider's values. In offline experiment runs, enforce the same order in code and log both timestamps |

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

**Measure β_A** (GPU time saved) for each attack on a RunPod RTX 5090 and RTX 3090, which the job has to itself: `1 − t_attack / t_honest`, median over 20 jobs. Do not measure it on a Spark; the shared GPU makes the timing unreliable.

### 3.4 Run scripts: Spark runner and RunPod launcher

1. **Spark runner.** Takes a workload file, starts the research container under the §1.1 rules, runs the jobs, and enforces the stop conditions (free memory under 15 GB, free disk under 200 GB). It resumes where it stopped, and writes the manifest including `cotenants`.
2. **RunPod launcher.** It starts the pod with the x86-64 image, verifies the card (`nvidia-smi`, GPU UUID) and the model hashes, records the driver, host and data-center ID, runs the assigned workload, and writes the manifest with the cost fields of §0.
3. **Data comes home by pull.** The Sparks are behind a VPN, so a pod cannot connect to them. A Spark pulls the raw data from the pod over SSH and verifies the checksums. Only then does the launcher **terminate** the pod.
4. **No paid storage.** Raw data lives on Sparks 4 to 6. Rented jobs bring home only what §3.5 allows for their class. Move data between Sparks over the 200 Gb links, not the 1 Gb management network.
5. **Dry run first.** Run every workload for 20 jobs on a Spark. Then smoke-test the x86-64 image for 20 jobs on an RTX 3090 pod (US$0.22/h) before any dearer pod is started. Nobody debugs on an expensive pod.
6. Use Community Cloud first. Use Secure Cloud only when a model is unavailable.

**Implemented (2026-11-24).**
- `code/tools/spark_run.py --run-id ID -- <command>`: research container `esj-<id>` (label `research=esj`, no published ports), stops it when free memory < 15 GB or disk < 200 GB and restarts it when memory is back above 15 GB + a margin, logs to `<run>/logs/runner.jsonl`, and writes co-tenant snapshots (other containers' CPU/memory, vLLM running/waiting requests) every 15 s that each job row copies. Host python3 only.
- RunPod: create the pod through the Runpod tools with `POD_TOKEN` (random), `POD_HOURLY_USD` and `POD_CLOUD` in its environment and port `8000/http`; start `tools/pod_server.py` (token-protected GET with resume and PUT); PUT `code.tar.gz` (code + experiments/configs); run `tools/pod_job.sh tools/workloads/<w>.sh`; then on a Spark (or the operator's machine) `tools/pull_run.py https://<pod>-8000.proxy.runpod.net/<token>` downloads, verifies checksums, extracts and adds the cost fields. Terminate the pod only after a clean pull.
- Before committing run folders (the repository is public): `python3 tools/sanitize_runs.py ../experiments/runs/<run> ...` replaces Spark hostnames and production co-tenant container names and images with role labels (`cotenant-llm`, `cotenant-svc`), leaving every measured number unchanged; `--check` must exit 0. The unredacted originals stay on the node under `~/esj/runs`.

### 3.5 Data retention for rented jobs (decision of 2026-11-24)

The Sparks' site link gives about 2 MB/s from RunPod and an SDXL trajectory is 16.5 MB, so rented trajectories are **not** all brought home. What each rented job keeps depends on what the analysis needs from it. Spark-generated jobs are unaffected: they keep full trajectories as before.

| Class | Rented jobs | What comes home | Why |
|---|---|---|---|
| **F (full)** | Reference config on **calibration and dev** prompts (the 300 such prompts in `prompts_rent500.txt`), every rented model; the second RTX 5090's L2 subset (`prompts_l2_50.txt`) | The whole trajectory, as on a Spark | τ_i is an extreme per-step quantile and needs every step (≥ 300 honest samples per step at k = 3); the dev split chooses the Tier B metric; the RQ1 per-step analysis (R1.4) and the x86 ε_A calibration need all steps |
| **O (opened steps)** | Reference config on **test** prompts (the 200 such prompts in `prompts_rent500.txt`), every attacked job from a rented provider (§6), and **the non-reference Spark grid configs** (§4 item 1; decision of 2026-11-25) | The image; x₀, the schedule, the conditioning hash and the final latent; the Merkle root; the eight pre-drawn steps (x_i, D_i, σ_i, and D_{i−1} for dpmpp_2m) with their inclusion proofs; the pod-side Tier A result | After the freeze, a verifier only opens the k ≤ 8 drawn steps. This is also what a deployed verifier receives |
| **I (image level)** | The precision factor and the RTX 4090 factor slice | The image, the final latent, the Merkle root, and the pod-side Tier A result | R1.7 is answered at image level and by bit identity of the Merkle roots |

Rules:
1. **Step draw, fixed before generation.** Before a class-O workload starts, generate a random `draw_seed`, record its sha256 in the manifest and keep the seed itself out of the workload. For each job, the drawn steps are the first 8 entries of a permutation of the T steps seeded by `sha256(draw_seed ‖ job_id)`. The set for k is the first k entries, so the sets are nested and one pull serves k ∈ {1, 2, 3, 5, 8}. E2-W (SN30) uses the first 3 entries as its random steps.
2. **Attack injectors never see `draw_seed`.** It is passed to the pod only after generation, for the extraction step. Otherwise a forger could fake only the steps that will not be opened.
3. **Tier A runs on the pod's CPU** over all steps before the full trajectory is discarded. Store the per-step residuals (30 numbers per job) and the verdict. Tier A is bit-exact across CPUs for Euler (pilot, finding 16); for dpmpp_2m, calibrate ε_A from the class-F jobs on both an x86 CPU and a Spark, and use the larger value.
4. **Extraction then discard.** The pod writes the class-O bundle, verifies the Merkle proofs against the root, and deletes the full trajectory before the pull. Record `retention: F|O|I` and the `draw_seed` hash in every job row.
5. **Code.** `verify.py` must accept class-O bundles (Tier B and E2-W from the opened steps; E1 from the metadata; Tier A read from the pod's result). `calibrate.py` must refuse anything but class F.
6. **What this gives up.** On rented test and attack jobs, no analysis with k > 8 or at undrawn steps is possible. The partial-faking sweep (R2.7) therefore uses Spark-generated jobs, which keep full trajectories.
7. **Estimated volume** (not measured): about 90 GB for class F and 40 GB for class O over all rented models, about 18 hours of pulls at 2 MB/s, roughly US$10–20 of pod time at the planned rates. Measure the real numbers on the first rented workload and record them in its manifest.

**Implemented (2026-11-25).** `code/trajver/retention.py`, tests in `code/tests/unit/test_retention.py`.
- *Step draw.* `python -m trajver.retention newseed SECRET` (operator's machine) writes a 32-byte seed with mode 600 and prints its sha256. The order of a job's T steps is a Fisher–Yates shuffle driven by a SHA-256 counter stream keyed by `sha256(draw_seed ‖ "|" ‖ job_id)`, so it does not depend on the Python version. Tier B at k = the first k entries. **E2-W uses the first three entries that are ≥ 1**, not the first three: SN30 re-runs step j = i + 1 with i in range(T − 1), so it never re-runs step 0; skipping 0 keeps its draw uniform over its own range, and the three steps always lie within the eight opened ones.
- *Bundle* (`raw/opened/<job>.safetensors`). Opened tensors under their committed names: `sigmas`, `x_000`, `x_final`, the conditioning, and for each of the eight drawn steps x_s, D_s (and D_{s−1} for dpmpp_2m); for each E2-W step j also x_j and x_{j+1}. Metadata: the root, an inclusion proof per opened tensor, the first eight entries of the order, the seed hash, and the pod-side Tier A residuals of all T steps. Class I opens only `sigmas` and `x_final` and carries Tier A.
- *Pod.* `tools/pod_job.sh` reads `POD_RETENTION` (per-run globs, e.g. `wp2-*-test-*=O,*=F`) and `POD_DRAW_SEED_SHA256` from the pod environment; the hash goes into `pod.json` and, through `TRAJVER_DRAW_SEED_SHA256`, into every run manifest before generation. After the workload, if any run is class O, the pod writes `out/GENERATED` and waits (up to 24 h) for `secret/draw_seed.hex`; then `trajver.retention extract` checks the seed against the hash, computes Tier A over every step, writes and re-verifies each bundle, deletes the full trajectory, writes `logs/draw_seed.hex` (the seed is public from then on) and marks `retention` and the seed hash in every job row; `trajver.retention check` re-verifies all bundles before packing.
- *Operator.* `python3 tools/pull_run.py <pod url> --reveal-seed SECRET --wait`: refuses a seed whose hash differs from the one in `pod.json`, PUTs it once the pod reports GENERATED, waits for DONE, then pulls as before. Run `python -m trajver.retention check <run>` on the Spark after the pull.
- *Verifier.* `trajver.verify` takes class F, O and I jobs in one run. Class O: every opened tensor is checked against the committed root in `jobs.jsonl` and the opened steps against the revealed seed, otherwise all of the job's verdicts are `fail` with the reason; E2-H at k uses the first k entries of the order (nested); E2-W its three steps; Tier A the pod's residuals. Class I: E1's image check (decoded `x_final` vs the delivered image) and Tier A. `pilot replay` and `calibrate` refuse anything but class F.
- *End-to-end check (2026-11-25, SD1.5 512², 30 steps, euler, on a Mac with the dev thresholds, 3 jobs each; not paper data).* Honest, A1b (10 steps run) and F2 (s = 0.5) runs were verified twice: as generated (class F) and after `extract --cls O` on a copy. Every verdict was the same in both forms (E1, Tier A, E2-H at k = 1–8, E2-W) for all 9 jobs: honest passed everything; A1b failed E2-H at every k; F2 failed Tier A and E2-H at every k; E2-W passed both attacks, as in the pilot. A class-O bundle kept 40 % of the trajectory's bytes for SD1.5 (5.4 of 13.4 MB for 3 jobs; the conditioning tensors are a large share at this resolution). The seed handshake was tested against a local `pod_server.py`: a wrong seed is refused before it is sent, and a pod waiting for the seed makes `pull_run.py` stop with a message unless `--reveal-seed` is given.
- *Software pin:* every run manifest records `image_digest`: on a Spark the research image's digest (`tools/spark_run.py` reads it with `docker image inspect`), on a pod `lock-<stack>:sha256:<hash of env/lock-<stack>.txt>`, since pods build the environment from the lock file instead of pulling the image.


---

## 4. RQ1: honest variation (WP2, Jan 4–31)

1. **Spark grid (L0–L2).**
   - Configs: precision {fp16, bf16, fp32 (`--force-fp32`)} × attention {SDPA (`--use-pytorch-cross-attention`), split or quad} × sampler {euler, dpmpp_2m} × `--deterministic` {off, on}. That is 24 configs.
   - Models: SD1.5 and SDXL.
   - Prompts, × 3 seeds:
     - the **reference config** (fp16, SDPA, euler and dpmpp_2m, `--deterministic` off) runs all calibration plus dev prompts (600);
     - every other config runs `prompts_grid50.txt` (**decision of 2026-11-26**: 50 prompts instead of 200, and the same 50 for every factor config on every node and on RunPod; was `prompts_grid200.txt`).
   - If P3 says this is too slow, cut the reference config to 300 prompts. Never cut the configs; ask the paper author first.
   - Run the reference config, the other configs and L2 on all three of Spark-4, Spark-5 and Spark-6 (decision of 2026-11-26: with 50 grid prompts the grid fits on Spark-6 too, so every config has three Spark-to-Spark pairs and every node runs the same items). Repeat a 10% subset on Spark-4 for L0.
   - **Second software stack: dropped (decision of 2026-11-24).** The protocol pins one software image instead; do not build or run a second stack.
   - Run `prompts_l2_50.txt` × 3 seeds, reference config, SDXL, on all six Sparks (L2, up to 15 pairs). On nodes 1 to 3 run it off-peak and keep to fp16.
   - Record the trajectory for every job (§3.1). The reference config, L0 and L2 keep full trajectories (class F). **The non-reference grid configs are class O** (decision of 2026-11-25, finding 18: the disks cannot hold full trajectories for all of WP2): one grid draw seed for the whole study arm, the same file on Sparks 4–6, so a job opens the same 8 steps in every config and on every node and `pilot compare --steps-detail` compares those steps. Each step is then opened in about 40 of a pair's 150 jobs. Each grid run is extracted right after it finishes, in a separate container that alone gets the seed (`wp2_spark.sh`, `GRID_SEED_FILE`).
2. **Rentals (L3 and L4), on RunPod through the §3.4 launcher.**
   - Required models, consumer GeForce RTX only: RTX 5090 (L3), RTX 4090, RTX 3090. Substitutes when out of stock: RTX 4080 SUPER, RTX 3090 Ti.
   - **x86 factor slice, RTX 4090 only:** at fp16, `--deterministic` {off, on} × attention {SDPA, split or quad} × {euler, dpmpp_2m}, on `prompts_grid50.txt` × 3 seeds (was `prompts_grid200.txt`; decision of 2026-11-26), for SD1.5 and SDXL. The two reference configs are already run, so this adds six configs per model, 1,800 jobs. If xformers installs in the x86-64 image, add it as a third attention backend.
   - Workload per model, for SD1.5 and SDXL, × 3 seeds: the reference config on `prompts_rent500.txt`, and the precision factor (bf16, and fp32 for SD1.5 only, both samplers; SDXL fp32 is out of the grid, finding 10) on `prompts_grid50.txt` (was `prompts_prec100.txt`; decision of 2026-11-26). That is 6,900 jobs per rented model.
   - `prompts_rent500.txt` includes test-split prompts, so that each model is rented only once. **Store those outputs but do not score them until §6.** Keep data per the retention classes of §3.5: calibration and dev prompts class F, test prompts class O, the precision factor and the factor slice class I.
   - L2: a second RTX 5090 on a different host, reference config, `prompts_l2_50.txt` × 3 seeds.
   - If a card is slower than estimated, cut its prompts, never the reference config, and record the cut.
   - Spending: load credit in US$50 steps and stop for a review at US$120 spent.
3. **Per pair, compute:**
   - the image-level pixel-equality rate, LPIPS and DINOv2;
   - for each step i, the distance between the two runs' `D_i` (max-abs and relative L2), and the Tier A residual.

   Use pairs within each level L0–L4.
4. **Outputs:** fill R1.1–R1.8. Save the figure data for R1.4 and R1.5 as CSV in `summary.json` or alongside it.

**Workload scripts (2026-11-25).** `code/tools/workloads/wp2_spark.sh` (items `ref`, `grid`, `l0`, `l2`) and `wp2_rent.sh` (items `ref`, `prec`, `slice`, `l2`), sharing `wp2_lib.sh`.
- A config is `<prec>-<attn>-<sampler>-<det>`: fp16 = `--force-fp16`, bf16 = `--bf16-unet`, fp32 = `--force-fp32` (as in P7); sdpa = `--use-pytorch-cross-attention`, split = `--use-split-cross-attention` (the "split or quad" level is **split**); det = `--deterministic`. The reference config is `fp16-sdpa-{euler,dpmpp_2m}-nd`. All runs are 30 steps, 512² for SD1.5 and 1024² for SDXL, seeds 0, 1, 2, trajectories kept.
- `prompts_grid50.txt` (2026-11-26): 50 prompts (32 cal, 18 dev) drawn from `prompts_prec100.txt` by `make_prompts.py` after all its other draws, so the earlier files are unchanged and grid50 ⊂ prec100 ⊂ grid200. It is the prompt set of every non-reference factor config: the Spark grid, the rented precision factor and the x86 slice, so every factor level is compared on the same 150 jobs.
- New prompt files (subsets, no new draws; hashes in `prompts.json`): `prompts_caldev600.txt` (cal + dev, the Spark reference config), and `prompts_rent500.txt` split by retention class into `prompts_rent_caldev300.txt` (class F) and `prompts_rent_test200.txt` (class O).
- Run names carry the retention class: `-test-` runs are class O, `-prec-` and `-slice-` runs class I, the rest class F. Create every rented pod with `POD_RETENTION='*-test-*=O,*-prec-*=I,*-slice-*=I,*=F'` and, for `ref`, `POD_DRAW_SEED_SHA256`.
- `LIMIT=n` caps each run at n prompts (× 3 seeds) for dry runs; `GRID_GLOB` splits the Spark grid across days (e.g. `GRID_GLOB='bf16-*'`). Runs resume by run id.

**Spark grid launched (2026-11-26, code at commit `58f57c6`, the same files on all three nodes).** Items `ref grid l2` on Spark-5 and Spark-6, `ref l0 grid l2` on Spark-4; grid on `prompts_grid50.txt`, the one grid draw seed on all three nodes (sha256 `c4295abf…`). Expected about 29 h per node (reference 13.5 h, grid about 15 h, L2 0.5 h; Spark-4 also L0 1.4 h). Run ids take the node's own UTC date (`DATE` is not overridden):
- Spark-5 and Spark-6 started at 17:30 UTC on 2026-11-25, so their run ids begin `20261125-`.
- **Spark-4 incident.** It started at the same time, but its WP2 dry-run runs of 2026-11-25 (finding 18) have the same ids, and runs resume by id. It was stopped after about 2 minutes. By then it had appended 69 reference-config jobs to the dry-run folder `20261125-wp2-ref-sd15-fp16-sdpa-euler-nd-spark4-01` (21 → 90 jobs). That folder stays dry-run data, not paper data; its committed metadata (21 jobs) is unchanged.
- Spark-4 then started a waiter that reads the node's clock and launches the workload once the UTC date is 2026-11-26, so its run ids begin `20261126-`.
- Pairs are matched by config, not by date.

**Rentals started (2026-11-25 17:55 UTC).** Stock at launch, from the RunPod catalog: RTX 5090 and RTX 3090 none in Community or Secure Cloud; RTX 4090 Community none, Secure low.
- RTX 4090 on Secure Cloud, EU-RO-1, US$0.89/h, 200 GB disk, code identical to main `70b6308`, items `ref prec slice`. It has its own draw seed (on Spark-5; sha256 `c51a7b35…` in `pod.json`).
- The pull runs on Spark-5 with `--wait --reveal-seed`.
- **`REP=02`.** The 4090 dry run (finding 18) used `20261125-…-rtx4090-01` on the same UTC date, and `pull_run.py` skips folders already pulled. The date is not overridden; this pod's runs are `20261125-wp2-…-rtx4090-02`. REP has no other meaning on the rentals.
- RTX 5090 (L3), second RTX 5090 (L2) and RTX 3090: start when stock appears, each with its own draw seed.
- **RTX 3090 started 2026-11-25 22:34 UTC.** Community Cloud had none; Secure Cloud, EU-CZ-1, US$0.50/h, 200 GB disk, driver 595.112, code identical to main `70b6308`, items `ref prec`. Its own draw seed (on Spark-5; sha256 `40c56a37…`). `REP=01`: the only earlier 3090 run is the WP0b pilot of 2026-11-24, so no id collides. Pull on Spark-5 with `--wait --reveal-seed`. (An hour earlier a Community 3090 at US$0.22/h sold out between the stock read and the create; nothing was billed.)
- **RTX 5090, first try 2026-11-25 23:34 UTC: faulty host, terminated.** Community Cloud, US$0.69/h (AMD Threadripper 3960X, driver 580.178). `nvidia-smi` showed the card but PyTorch reported "CUDA unknown error", as on the first 4090 dry-run host. Terminated after about 2 minutes, before any job; the pod's own draw seed (sha256 `f3240700…`) stays on Spark-5 for the next try. Community stock still listed only that host's CUDA version (13.0), so the next try waits for other stock rather than landing on it again.
- **RTX 4090 seed revealed by hand (2026-11-26 01:19 UTC).** The pod finished generating at 01:05 and waited for the draw seed, but `pull_run.py` reveals only between downloads, and it was inside a 17 GB SDXL class-F tar at 0.4–2 MB/s (the Spark-5 link is shared with the 3090 pull). The seed was revealed in a separate call to `pull_run.reveal()`, which checks it against the hash in `pod.json` first; the running pull continued. Fixed the same day: `pull_run.py` now reveals from its own thread, checked against a local fake pod whose tar download was slowed (seed revealed at 0.2 s while the download ran; a wrong seed is refused with exit 4 and never reaches the pod). The 3090 pull was restarted on the new code; downloads resume (`curl -C -`) and pulled runs are skipped.

---

## 5. Calibration and freezing (end of WP2): no attack data before this step

Use the **calibration split only**.

1. **E0 thresholds.** Use this rule: `t_pass` is the lowest score at which at least 99% of honest pairs pass, and `t_fail` is the highest score at or below which at most 0.5% of honest pairs fall. Use honest pairs pooled over the levels you intend to support (state which: L3 and L4).
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

Use the **test split** prompts. Providers: Sparks, plus a rented RTX 5090 and RTX 3090. Verifiers: Sparks, plus a rented RTX 4090. The rented honest data is the other side of each cross-model pair.

1. For each attack A1–A8, F1–F4 and M, produce **100 attacked jobs per cell** (never under 30). A cell is (attack × model × hardware pair). Produce **1,000 honest jobs per stratum** where the pooled pairs allow it, and never under 299. Zero false rejections in 299 bound the false-rejection rate below 1% at 95% confidence; 1,000 still bound it below 1% with up to 4 false rejections. The Spark-provider cells run on the Sparks.
   - **Rented providers:** generate the same 100 attacked jobs per attack on a RunPod RTX 5090 and RTX 3090, and verify them on a Spark. These jobs are class O (§3.5): only the pre-drawn steps come home. A consumer x86 card as provider and a Spark as verifier is the direction a real marketplace has.
   - **Rented verifier:** run E0 and the all-steps Tier B pass over the Spark-generated attacked jobs once on a RunPod RTX 4090.
   - Budget for both, with the β_A timing of §3.3: about US$15.
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

**Toolchain on the operator's Mac (installed 2026-11-25).** Solana CLI 4.4.1 (Anza installer; `solana-test-validator`, `cargo-build-sbf`) and Anchor 1.2.2 via `avm` 1.2.2, with platform-tools v1.57. A local build and test on the local validator therefore cost nothing; the RunPod pod §7 item 3 budgets for the Anchor build is not needed for local-validator work. Known issue: rustup 1.28.2 reads the platform-tools toolchain name `1.95.0-sbpf-solana-v1.57` as an official channel and fails ("target 'sbpf-solana-v1.57' not found in channel"). Workaround, which builds, tests and deploys an Anchor 1.2 template:

```
export PATH="$HOME/.cargo/bin:$HOME/.local/share/solana/install/active_release/bin:$PATH"
PATH="$HOME/.cache/solana/v1.57/platform-tools/rust/bin:$PATH" anchor build --no-idl -- --no-rustup-override
anchor idl build -o target/idl/<program>.json
anchor test --skip-build
```

**Status 2026-11-25 (items 1–3, local validator only).**
- **Item 1 is done.** The Anchor program is in `code/program/` (`trajescrow`). It implements the table below one to one, with one test per row on `solana-test-validator`. Choices the table leaves open, such as the fee split and the rule that inconclusive plus inconclusive is unresolved, are listed in `code/program/README.md`. Its 16 mocha tests and 2 Rust unit tests pass.
- **Item 2 is done in minimal form.** The orchestrator is in `code/orchestrator/` (queue, assignment, JSON-lines relay, event log, reputation). It calls `python -m trajver.verify` and drops the label fields before it reads a verdict. Its unit tests pass, and its local-validator test passes with a stand-in verifier.
- **Item 3, local part.** `code/program/scripts/replay.ts` replays the four paths, interleaved, and records signatures, compute units and fees per transaction. Run `experiments/runs/20261125-wp5-escrow-replay-local-01` (100 jobs per path, 400 of 400 closed in the expected state, on the operator's Mac). Its signature counts and compute units are properties of the program and do not depend on the machine. Its latencies are local and are not for the paper. `program_tree_dirty` is true only because of the then-untracked `scripts/relay.ts`; the binary is identified by `program_so_sha256`. Still open: the ≥100-per-path run on the x86 pod, Devnet, latency to finalized, the RPC details and the calculated mainnet fee.
- **Build with this repo:** `code/program/scripts/build.sh` runs the workaround above and copies the IDL to `code/program/idl/`. Run the tests with `anchor test --skip-build --validator legacy`, because Anchor 1.x starts surfpool unless told `legacy`.

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

   **State machine** (manuscript Figure 2 shows the same flow):

   | From | Event | To | Funds |
   |---|---|---|---|
   | — | `create_job` | Funded | P + verifier fee locked |
   | Funded | `accept_job` | Assigned | bond B locked |
   | Funded | requester cancels (before assignment) | Closed-refunded | P returned |
   | Assigned | `commit_result` | Committed | — |
   | Assigned | deadline passes | Closed-refunded | P returned, B returned |
   | Committed | `draw_sample` → not sampled | Closed-paid | P to provider, B returned |
   | Committed | `draw_sample` → sampled | UnderVerification | — |
   | UnderVerification | `submit_verdict` = pass | Closed-paid | P to provider, B returned, fee to verifier |
   | UnderVerification | `submit_verdict` = fail or inconclusive | Disputed | — |
   | Disputed | `final_verdict`: second verifier agrees with the provider | Closed-paid | as for pass |
   | Disputed | `final_verdict`: both verifiers against the provider | Closed-refunded | P to requester, B slashed |
   | Disputed | all three disagree | Closed-unresolved | P to requester, B returned (no penalty) |
   | any open state | `timeout_refund` after the dispute deadline | Closed-refunded | P to requester, B returned |

   The ground-truth attack label is **never** used to resolve a dispute.
2. **Orchestrator.** A minimal service: queue, assignment (rented card = provider, Spark = verifier, a node never verifies itself), transaction relay, and an event log of all on-chain and off-chain events with timestamps. It also keeps a **reputation record** per provider (start 0.5; a verified pass moves it toward 1; a confirmed fail lowers it), updated from the verdicts and used to exclude providers below a minimum. Reputation is recorded for the testbed only; it is not part of the RQ2 detection metrics.
3. **Measurement.** For each path (accept unsampled, sampled-pass, sampled-fail with dispute, timeout refund), run at least 100 jobs on the **local validator** and at least 100 on **Devnet**. The Anchor build and the local validator run on a RunPod x86 pod (RTX 3090, US$0.22/h, or a CPU pod if cheaper; budget about US$13). The local-validator runs are a scripted replay of each path and need no GPU work, so do them in a few long sessions and terminate the pod in between; keep the program source and build artifact in the repository. Devnet SOL is free from the faucet. Record the signature count, compute units, fee in lamports, and latency to processed, confirmed and finalized. Record the RPC endpoint, its plan and rate limits, the priority-fee policy and the time of day. Interleave the paths. Fill R3.4.
   - **Mainnet is not used.** Deploying there locks up several SOL of rent, which does not fit the budget. Report a **calculated** mainnet fee per path from the measured signature count and compute units, at a dated SOL price, and label it as calculated.
4. **Verifier cost per job**, timed on the rented RTX 4090 and RTX 5090 (not on a shared Spark): verifier GPU-seconds for E0, E0-N, E2-W, E1 and E2-H at each k. Also record storage in MB per job. Fills R3.1 and R3.3. Convert GPU-seconds to US dollars with the `hourly_rate_usd` recorded for each rented model, per model and with the date of the rate. Fills R3.7.
5. **Testbed demo.** Run the end-to-end flow on Devnet with rented providers (RTX 3090, 4090 or 5090), including injected attackers, and real Spark verifiers, at p ∈ {0.05, 0.1, 0.25}. The orchestrator runs on the provider's pod; the Spark connects outward to it and to Devnet. Budget: about US$8. These are the points overlaid on Fig. R3.6.

---

## 8. Monte Carlo (WP4; the paper author can do this from the §6 outputs)

Simulate providers using strategy s ∈ [0, 1], with the measured r_A, α_s and β_A, over (p, k, B/P). Estimate the realized gain Δ(s). This checks Proposition 2 (detection probability, manuscript Equation 4) and Proposition 3 (the all-or-nothing response and the deterrence condition, Equation 8; cost-optimal sampling rate, Equation 9). Inputs: the §6 summaries. Output: R3.2, R3.5 and R3.6.

## 8b. Data for the result figures

The paper author draws the five result figures from the data, in the same style as Figures 1–2 (`paper/tools/make_figures.py`). Deliver one CSV per figure in the relevant run folder. Every row carries the `run_id` it came from.

| Figure placeholder | CSV | Columns |
|---|---|---|
| R1.5: honest deviation by level | `fig_r1_5_levels.csv` | `level, hw_pair, model, sampler, precision, metric, value` (metric ∈ pixel_equal, lpips, dinov2, step_d_rel_l2) |
| R1.4: per-step honest deviation | `fig_r1_4_steps.csv` | `hw_pair, model, sampler, step, d_value, tau_step` |
| R2.7: partial faking | `fig_r2_7_partial.csv` | `attack, s, k, n_jobs, n_detected, alpha_s, r_measured` |
| R3.5: cost–detection frontier | `fig_r3_5_pareto.csv` | `evidence, p, k, verifier_gpu_s_per_job, detection_rate, fpr` |
| R3.6: deterrence region | `fig_r3_6_deterrence.csv` | `attack, p, k, bond_ratio, delta_mean, delta_ci_lo, delta_ci_hi, source` (source ∈ monte_carlo, testbed) |

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
| R0.5 | Split sizes | **Filled in the manuscript 2026-11-24:** 400 / 200 / 400 PartiPrompts prompts (`experiments/configs/prompts.json`) |
| R1.1 | Initial noise x₀ bit-exact across x86 and ARM | P1 |
| R1.2 | Tier A ε_A, and whether it is exact across CPUs | §4.3, §5.3 |
| R1.3 | Tier B metric | §5.2 |
| R1.4 | Per-step honest deviation vs step, and τ_i | §4.3, §5.2 |
| R1.5 | Deviation by level (figure) | §4.3 |
| R1.6 | Bit-identical fractions per level | §4.3 |
| R1.7 | Factor effects; deterministic profile and its cost | §4.1 |
| R1.9 | Bit-identical outputs on a Spark with and without co-located load | P6 |
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
| R3.8 | Data sent to the verifier per sampled job (MB): full trajectory, since Tier A needs every step, versus the opened steps alone | §7.4, §3.5 |
| R3.4 | Escrow CU, fees (Devnet measured, mainnet calculated), latency | §7.3 |
| R3.7 | Verifier cost in US$ at observed rental rates | §7.4, rented-node manifests |
| R3.5 | Pareto data | §6 + §7.4 |
| R3.6 | Deterrence region data | §8 + §7.5 |
| R4.1, R5.1 | Implications, conclusion | Paper author |
