# Go/no-go #0: pilot results (WP0b)

For: Anjas Risky Maradita (paper author). From the pilot runs of 2026-11-23/24. Every number below comes from a logged run in `experiments/runs/20261124-wp0b-*`; details and run IDs are in `docs/07-runbook.md` §3, findings 7–13.

Nodes: Spark-4, Spark-5 and Spark-6 (DGX Spark, GB10, ARM), rented RTX 5090 (consumer Blackwell, in place of the RTX 5080, which had no stock), RTX 4090 (Ada) and RTX 3090 (Ampere) on RunPod. Same software everywhere: Python 3.12.13, torch 2.14.1+cu130, ComfyUI 8b25bbc. SDXL, 30 steps, euler, fp16, unless stated.

## Verdict

**Go.** Both go/no-go criteria of doc 05 are answered:

| Criterion (doc 05 §WP0b) | Result | Status |
|---|---|---|
| Consumer Blackwell ↔ Spark bit-exact for SDXL? | **No.** Measured on an RTX 5090 (the RTX 5080 had no stock all day): 0/40 identical against the Spark, the 4090 and the 3090. Honest variation exists within Blackwell (L3) and across architectures (L4), so the study has variation to calibrate at every level | Answered (5090 as the L3 card) |
| W1 holds (frame-copy forgery passes SN30)? | Yes, on all four cards: min adjacent cosine 0.977 (≥ 0.70); the deployed SN30 rule accepted every honest job and every F1, F2, F3 forgery (10/10 each, s = 0.25/0.5/1.0) | **Break result secured** |
| RunPod cost of the honest runs within the planned US$60? | Yes on GPU time (see below); data transfer is the bottleneck, not money | Go, with one risk |

## Results

**Initial noise (P1).** Two families, no difference inside either: the three Sparks agree (100/100 seeds), and the three x86 hosts agree, including an AVX-512 EPYC 9554 (100/100). Spark vs x86: 0/100 identical, largest difference 2.3e-6 in unit-variance noise. E1 therefore checks x₀ against a fixed, build-agnostic tolerance of 1e-5 (4.3× the largest difference), so no CPU or PyTorch version needs its own test (decision of 2026-11-24, Methods updated).

**Bit-identity (P2, P6).**
- Same Spark twice (L0) and Spark-4 vs Spark-5 (L2): 40/40 bit-identical trajectories (Merkle roots), SD1.5 and SDXL.
- Co-tenancy (P6, 60 jobs × 4 conditions on Spark-4): 60/60 bit-identical with a heavy GPU load beside it (sampling 2.3–2.6× slower), with and without the batching pin, and with the production chat model serving requests during up to 30 of the 60 jobs. Shared load is **not** a source of honest variation on a Spark at the memory levels tested.
- Across GPUs (L4): 0/40 identical for every pair. Image distances are small:

| Pair | LPIPS median (max) | DINOv2 cosine min | SN23 E0-N full reward |
|---|---|---|---|
| Spark ↔ RTX 4090 | 0.005 (0.057) | 0.981 | 40/40 |
| Spark ↔ RTX 3090 | 0.006 (0.054) | 0.927 | **39/40** |
| RTX 4090 ↔ RTX 3090 | 0.008 (0.048) | 0.940 | 40/40 |
| Spark ↔ RTX 5090 | 0.005 (0.079) | 0.981 | 40/40 |
| RTX 4090 ↔ RTX 5090 | 0.005 (0.081) | 0.988 | 40/40 |
| RTX 3090 ↔ RTX 5090 | 0.005 (0.080) | 0.935 | 40/40 |

  New: **the deployed SN23 rule penalised one honest job** (`p00083_s1`, Spark vs 3090: CLIP cosine 0.899 < 0.9, reward 0.998). One case in 40 is not a rate, but it shows the image-level rule can fail an honest provider on hardware alone; worth a sentence in the paper once RQ1 gives the rate.

**Honest Tier B / Tier A across hardware.** A Spark replaying an x86 provider's trajectory (5090, 4090 and 3090, 40 jobs each):
- Tier B (one model call per step): no step bit-exact. Relative L2 of D̂_i vs D_i, median (max): step 0 2.7–2.9% (5.3%), step 10 1.0%, step 25 0.2%, step 29 0.04%. All three providers give the same profile, so **per-step thresholds τ_i are required** and pooling across the two x86 cards looks safe.
- Tier A (CPU recompute of the solver step): 1,200/1,200 steps bit-exact for every provider; largest float64 residual 2.8e-8. ε_A can sit at rounding level.
- Full replay of 30 steps costs 19.9 s per job on a Spark.

**Attack feasibility (P4).** fp8 (`--fp8_e4m3fn-unet`) is *slower* than fp16 on every card, consumer Blackwell included (Spark 13.55 vs 12.45 s, 5090 2.91 vs 2.71 s, 4090 4.18 vs 3.87 s, 3090 8.65 vs 8.21 s). NVFP4 only runs through a dequantize fallback on every card (0.1–0.2× bf16 speed). At the pinned ComfyUI commit, A2/A2b save the attacker nothing; they stay in the attack set as detection cases, and the economic argument rests on A1 (fewer steps), A3 (cheaper model) and the forgeries.

**Throughput (P3, warm, median s/image).**

| Node | SD1.5 512² | SDXL 1024² |
|---|---|---|
| Spark (beside production; sizing only) | 1.94 | 12.4 |
| RTX 4090 | 1.94 | 3.87 |
| RTX 3090 | 1.51 | 8.21 |
| RTX 5090 | 1.46 | 2.71 |

**Memory (P7).** Spark-4 host-memory drop: SD1.5 fp16/bf16 7.9/7.6 GB, fp32 13.1 GB; SDXL fp16/bf16 22.0/22.2 GB. SDXL fp32 is not allowed beside production (it took free memory to 5.9 GB). SDXL fp32 fills the card on both rented cards that tried it: 24.6 GB on the 24 GB RTX 3090 (34.0 s/image, 4.1× fp16) and 32.9 GB on the 32 GB RTX 5090 (14.6 s, 5.4× fp16). **SDXL fp32 is excluded from the RQ1 grid.**

## Cost re-estimate (runbook §2, "If it exceeds US$120, tell the paper author")

Upper bound: all 25,200 honest jobs of doc 10 §2.5 (8,400 × 3 models) on rented cards at the measured SDXL speed (Turbo and SD1.5 are faster):
- RTX 3090: 57.5 GPU-hours → US$12.6 (Community 0.22/h) to US$28.7 (Secure 0.50/h).
- RTX 4090: 27.1 GPU-hours → US$9.2 (0.34/h) to US$24.1 (0.89/h).

Within the US$60 line. Spent so far on RunPod in this pilot: balance 8.66 → 6.38 US$ for the 4090 and 3090 pods, plus about 0.5 US$ for the 5090 (22 minutes at 1.39 US$/h; credit was added during that rental, balance now 25.97 US$). The RTX 5080 smoke test of 2026-11-23 and a relay pod came before that.

**Risk: data transfer, not GPU time.** An SDXL trajectory is 16.5 MB (SD1.5 3.9 MB). The Sparks' site link gave about 2 MB/s from RunPod, so every 1,000 rented SDXL jobs take about 2.3 hours to pull, and the pod bills while it waits. Options for WP2, for you to choose: (a) keep only the steps a verifier opens plus the commitment (the Merkle tree allows this), (b) run the Spark-side replay on a rented verifier for the rented pairs, or (c) accept the extra pod hours (about US$1 per 1,000 SDXL jobs at 0.50/h).

## Open items

1. **Transfer plan** for WP2 (above).
2. The E0-N honest failure is worth one line in the paper once RQ1 gives its rate.
3. The RTX 5090 replaces the RTX 5080 as the L3 card; doc 05 and the Methods name the 5080 and should say so when the grid is fixed.
4. Calibration dry run (`experiments/runs/20261124-wp0b-calib-dryrun-01`): the pipeline works end to end; the real freeze needs at least 300 honest samples per step at k = 3, which WP2 provides.

## Figures (PNG, PDF and CSV under each run's `figures/`)

- Throughput, all nodes: `20261124-wp0b-p3-sd15-rtx5090-01/figures/throughput_all_nodes`
- Honest Tier B per step, three x86 providers → Spark: `20261124-wp0b-replay-5090on-spark5-01/figures/tierb_honest_rtx_to_spark`
- Step distances Spark vs 4090 / vs 3090: `…p2-sdxl-spark4-01/figures/p2_sdxl_stepdist_spark_vs_4090`, `…p2-sdxl-rtx3090-01/figures/p2_sdxl_stepdist_spark_vs_3090`
- W1 and SN30 acceptance: `…p5-w1-*/figures/`
- Memory per precision: `…p7-sdxl-fp16-spark4-02/figures/p7_memory_spark4`, `…p7-sdxl-fp32-rtx3090-01/figures/p7_memory_rtx3090`
