# Progress Summary for the Paper (as of 2026-11-26, 13:00 UTC)

For: the paper author and co-authors. This is a map from what has been done so far to what the manuscript (`paper/manuscript_ESJ.docx`) can use. Every number here is copied from its source. The **Source** column names the runbook finding (`docs/07-runbook.md`), run ID or ops record behind it. Use the source, not this page, when you write the number into the paper.

How to read the labels:
- **Paper-ready**: measured in a logged run, final for its purpose.
- **Pilot**: logged and real, but measured on the WP0b pilot's small samples (20–60 jobs). Good for the Methods narrative and to motivate design choices. The paper's RQ1 numbers come from the WP2 data instead.
- **Not a result**: a pipeline test, in-sample, or a dry run. Do not cite as a finding.

Guardrails (CLAUDE.md, doc 05 §2):
- Never write "first" or "no prior work" without a fresh literature check.
- Per-step spot-checking itself is prior art (WOMBO SN30, 2024).
- No Spark timing *claims* except quiet-window numbers (doc 10 §2.2 rule 4).

---

## 1. Where the project stands

| Work package | Plan (doc 05 §6) | Status on 2026-11-26 |
|---|---|---|
| WP0 reads, delta locked | Nov 24 – Dec 6 | Done (docs 04, 06, 08) |
| WP0b hardware pilot, go/no-go #0 | Nov 26 – Dec 6 | **Done; verdict Go** (`docs/11-go-no-go-0.md`) |
| WP1 instrumentation | Dec 7 – Jan 3 | **Done early.** `trajver` package, ComfyUI node, verifiers, attack injectors, Spark runner, RunPod launcher (runbook §3) |
| WP2 RQ1 study | Jan 4 – 31 | **Running now, about five weeks early.** Spark grid on Sparks 4–6; all rentals generated; pulls finishing |
| Calibration freeze (§5) | end of WP2 | Next, once WP2 data is home |
| WP3 RQ2 attacks | Feb 1 – 28 | Not started (attack injectors and A3 models ready) |
| WP4 theory and Monte Carlo | Feb 1 – 28 | Not started (no compute needed) |
| WP5 escrow, cost table, demo | Jan 4 – Mar 14 | Not started |

The manuscript has its Introduction, Related Work and Methods drafted. Its results are placeholders `[R…]`, mapped to sources in runbook §10. R0.5 (split sizes 400 / 200 / 400 PartiPrompts prompts) is already filled.

---

## 2. Results the paper can already use

### 2.1 Headline: the deployed validators fail in both directions (RQ2, R2.1, R2.5)

| Finding | Numbers | Label | Source |
|---|---|---|---|
| The deployed step-check rule (SN30, E2-W) accepts frame-copy forgeries | Every honest job and every F1, F2, F3 forgery accepted (10/10 each, s = 0.25 / 0.5 / 1.0) on all four card types; minimum adjacent-state cosine 0.977, against its 0.70 threshold (hypothesis W1) | Pilot | Findings 8, 10, 11, 16; `docs/11-go-no-go-0.md` |
| The deployed output rule (SN23, E0-N) rejects honest work | SDXL: job `p00083_s1`, Spark vs RTX 3090, CLIP cosine 0.899 < 0.9. SD1.5: job `p00293_s0` fails against **all three** x86 cards (CLIP 0.888–0.899), while the x86 cards agree with each other (0.988–0.999) | Pilot | Findings 11, 17; figure `docs/pilot-findings/fig/sn23_honest_fail_p00293.png` |
| SN23's black-image filter never fires | It compares 6×6 hashes with an 8×8 hash of a black image, so the strings never match | Paper-ready (code fact) | Runbook §3 finding 4; `trajver/rules/e0n.py` |

### 2.2 Honest variation: the structure RQ1 will quantify (R1.1, R1.6, R1.9)

| Level | Result | Label | Source |
|---|---|---|---|
| L0, same Spark twice | 40/40 bit-identical trajectories (Merkle roots), SD1.5 and SDXL | Pilot | Findings 9, 10 |
| L2, Spark-4 vs Spark-5 | 40/40 bit-identical, SD1.5 and SDXL | Pilot | Findings 9, 10 |
| L3, consumer Blackwell (RTX 5090) vs Spark (GB10) | **0/40 identical**: Blackwell does not imply bit-exactness | Pilot | Finding 16 (go/no-go criterion 1) |
| L4, across architectures (Spark, RTX 4090, 3090, 5090) | 0/40 identical for every pair; Spark vs 4090: LPIPS median 0.005 (max 0.057), mean pixel difference median 1.19 levels | Pilot | Findings 10, 11, 16 |
| Co-tenancy on a Spark | 60/60 bit-identical in all four load conditions, with and without the batching pin, chat model serving during up to 30 of 60 jobs | Pilot (answers R1.9 for the loads tested) | Finding 12 |
| Initial noise x₀ | Two families: Sparks agree 100/100, the three x86 hosts agree 100/100, Spark vs x86 0/100 (largest difference 2.3e-6) | Pilot (R1.1) | Findings 7, 8, 11, 16 |

**For the narrative:** honest variation is zero inside a hardware family and appears across families. This is why calibrated tolerances are needed, and why exact-hash rules break.

### 2.3 The two-tier check works on honest data (R1.2, R1.4)

| Finding | Numbers | Label | Source |
|---|---|---|---|
| Tier A (solver consistency on the CPU) is bit-exact across hardware for euler | 1,200/1,200 steps bit-exact for 4090, 3090 and 5090 providers verified on a Spark; largest float64 residual 2.8e-8 | Pilot | Findings 10, 11, 16 |
| Tier A for dpmpp_2m is not bit-exact, even on one node | float32 replica exact at 560/1,200 steps; float64 residual ≤ 1.0e-7 relative, so **ε_A is per sampler** (euler 0, dpmpp_2m about 2e-7) | Pilot | Finding 17 |
| Tier B honest deviation falls with the step | Relative L2 of D̂_i vs D_i, median: 2.7% at step 0 → 0.97% at step 10 → 0.22% at step 25 → 0.04% at step 29; the same profile for all three x86 providers | Pilot | Findings 10, 11, 16; figure `docs/pilot-findings/fig/tierb_honest_rtx_to_spark.png` |
| dpmpp_2m's Tier B profile matches euler's | SDXL steps 0 / 10 / 20 / 29: 0.048 / 0.0102 / 0.0037 / 0.00033 (euler 0.048 / 0.0105 / 0.0036 / 0.00039) | Dry run | Finding 18 |

**For the narrative:** a single cosine threshold (SN30) cannot work, but per-step tolerances τ_i can.

### 2.4 Attacks are cheap to run and Tier B sees them

| Finding | Numbers | Label | Source |
|---|---|---|---|
| Cost saving available to a cheater (β_A, R2.4) | Honest SDXL job 12.4 s on a Spark; A3 SDXL-Turbo (4 steps) 1.0 s, saving about 92%; A3 LCM-LoRA (6 steps) 2.7 s; A1b (20 of 30 steps) 7.9 s | Pilot | Finding 17 |
| No cheaper fp8 or fp4 path at the pinned ComfyUI | fp8 SDXL is slower than fp16 on every card (for example 4.18 vs 3.87 s on the 4090); NVFP4 only through a dequantize fallback | Pilot | Findings 8, 10, 11, 16 |
| Detection, smoke test | Thresholds fitted on the same honest pairs, so a pipeline test only. Tier B rejected A1b and A3 10/10 at k = 1; F1–F3 9/10 at k = 1 and 3, 10/10 at k = 8; SN30 rejected none | **Not a result** | Finding 17 |

### 2.5 Throughput (R3.1 and R3.7 inputs; sizing)

| Node | SD1.5 512², 30 steps | SDXL 1024², 30 steps | Label | Source |
|---|---|---|---|---|
| RTX 5090 (consumer Blackwell) | 1.46 s/image | 2.71 s | Pilot | Finding 16 |
| RTX 4090 (Ada) | 1.94 (P3); fp16 1.05 in the WP2 dry run | 3.87 (P2); fp16 3.6 in the dry run | Pilot / dry run | Findings 8, 18 |
| RTX 3090 (Ampere) | 1.51 (p95 1.74) | 8.21 (p95 8.35) | Pilot | Finding 11 |
| Spark-3 (GB10), **quiet window** (chat model stopped) | 1.84 (p95 1.88) | 12.04 (p95 12.32) | **Paper-ready** (n = 19, the only quotable Spark timing) | Finding 17, runs `20261126-wp0b-p3-*-quiet-spark3-01` |
| Spark-3, busy hour | 1.84 (p95 1.86) | 12.32 (p95 15.15) | Sizing only | Same, `*-busy-*` |

**Observation:** co-tenancy on a Spark moves the SDXL tail (p95 15.15 → 12.32 s), not the median. Full Tier B replay of 30 SDXL steps on a Spark takes 19.9 s per job (finding 10).

### 2.6 Storage and transfer (R3.3, R3.8)

- **Trajectory size:** ComfyUI keeps latents in float32, so a stored trajectory is 19.1 MB for SDXL and 5.0 MB for SD1.5. gzip, zstd and xz save only about 9% (finding 18).
- **What the retention classes keep (§3.5):**
  - class O (8 opened steps) keeps about 41–50% of the bytes;
  - class I (image-level) keeps about 1.5%. For example, an RTX 3090 SDXL precision run went from 2.59 GB to 40 MB per run (`docs/ops/LOG.md`, 2026-11-26 09:25).
- Doc 05 §4.1's earlier estimate of 7.7 MB per job is too low; the measured values replace it (finding 3).

---

## 3. Protocol requirements found along the way (Methods, "Reproducibility requirements")

These came out of the pilot and are decided (runbook §3, Decisions of 2026-11-24). Each is a paper-ready statement about the protocol.

1. **Pin ComfyUI's memory-adaptive batching** (CFG batch and VAE tiling). Otherwise identical jobs can differ with free memory (finding 1).
2. **Compute the noise schedule on the CPU (canonical schedule).** The device ComfyUI uses changes the sigmas by one ULP, and that changes the final latent by up to 0.36 (finding 5).
3. **E1 accepts x₀ within a build-agnostic constant, `X0_TOL` = 1e-5.** That is 4.3× the largest difference seen across six machines, so no CPU or PyTorch version needs its own test.
4. **E1 accepts the schedule within `SCHED_TOL_REL` = 1e-6 per entry.** ARM and x86 differ by one float32 ULP in 4 of 31 entries (finding 17).
5. **Deterministic samplers only** in the core study, because ancestral and SDE samplers draw noise on the GPU (doc 05 §4.1).
6. **ε_A is set per sampler**, and calibration refuses to mix samplers (finding 17).
7. **A full frame copy passes Tier A; Tier B catches it.** This is why two tiers are needed (finding 2).

---

## 4. WP2 (RQ1) data collected so far

All honest-variation data for RQ1 is being generated now. Nothing below has been analysed yet; these are the inputs to the calibration freeze.

| Arm | What | Status (13:00 UTC) | Source |
|---|---|---|---|
| Spark grid, L0–L2 (Sparks 4–6) | 24 configs (precision × attention × sampler × deterministic), SD1.5 and SDXL. Reference config on 600 cal + dev prompts × 3 seeds; other configs on `prompts_grid50.txt` × 3 seeds (decision of 2026-11-26) | Running, no failed jobs. Spark-4 72 run folders (including its dry run), Spark-5 37, Spark-6 30, now in the SDXL part | `docs/ops/LOG.md`; runbook §4 item 1 |
| L2 subset on Sparks 1–3 | `prompts_l2_50.txt` × 3 seeds, reference config, SDXL | Spark-1 and Spark-3 done (150/150 each); Spark-2 running after `vllm-asr` was stopped to free memory | `docs/ops/LOG.md` |
| L3/L4 rentals | Reference config on `prompts_rent500.txt`, precision factor on grid50, × 3 seeds, SD1.5 and SDXL: RTX 5090 (L3), RTX 4090, RTX 3090; x86 factor slice on the 4090 | **All generated.** RTX 4090: 26/26 runs on Spark-5, verified. RTX 5090: 8/14, RTX 3090: 9/14, pulling from the staging pod | runbook §4; `docs/ops/catalog/wp2/runs.csv` |
| L2 on rented x86 | Second RTX 5090 on a different host, `prompts_l2_50.txt` × 3, SDXL | Done, 150 jobs, on Spark-5 | runbook §4 |
| P3 Spark timing, busy vs quiet | See §2.5 | Done | Finding 17 |

- **Test-split outputs are stored but not scored** until after the freeze (runbook §4 item 2, §5).
- **Run catalog:** `docs/ops/catalog/wp2/runs.csv` holds 171 runs so far. Each row has every input (code and ComfyUI commit, image digest, model sha256, prompt set, seeds, sampler, precision, flags, retention class, hardware, data center, price) and every output (jobs, image hashes, sizes, mean s/job, cost).
- **Images:** contact sheets in `catalog/wp2/sheets/`. Same prompt and seed across Spark-5, RTX 4090, 3090 and 5090 in `catalog/wp2/compare/`: visually identical, though not bit-identical (§2.2). The numeric comparison is WP2's analysis.

---

## 5. Infrastructure material (Methods, threats to validity, thesis chapter)

From `docs/ops/2026-11-26-wp2-rentals/` (report, four charts, screenshot), `docs/ops/LOG.md` and runbook §4:

- **Hardware actually used:**
  - six DGX Sparks (GB10, ARM64, unified memory) shared with a live production platform;
  - rented consumer GeForce cards on RunPod: RTX 5090 (×2, different hosts), RTX 4090, RTX 3090.
- **Same software everywhere:** Python 3.12.13, torch 2.14.1+cu130, ComfyUI 8b25bbc. One pinned image on the Sparks, one lock file on the pods.
- **Stock, not price, decided the rentals.** Community stock was scarce and sold out between read and create several times, so all three working cards ran on Secure Cloud.
- **Rented hosts can be faulty.** One RTX 4090 host (dry run) and one RTX 5090 host showed the card in `nvidia-smi` but no usable CUDA. `pod_job.sh` stops at once in that case. Threat: a provider's host health is not guaranteed.
- **The Spark site link is the bottleneck.** 0.35–2 MB/s to the Sparks, while the same pod served 5.9 MB/s elsewhere. The answer was a staging pod: finished GPU pods copy at about 75 MB/s inside RunPod and end at once.
- **WP2 rental cost:**

  | Pod | Time | Cost |
  |---|---|---|
  | RTX 4090 | 14.1 h | ≈ US$12.60 |
  | RTX 5090 (L3) | 6.5 h | ≈ US$9.10 |
  | RTX 3090 | 11.7 h | ≈ US$5.85 |
  | RTX 5090 (L2) | 1.8 h | ≈ US$2.50 |
  | Staging pod | ongoing | ≈ US$0.13/h |

  Much of each GPU pod's time was waiting on pulls, not generating. Source: runbook §4.
- **Pods end themselves after a checksum-verified pull and a retention check**, so the experiment runs without an operator's laptop. Tools: `release_pod.py`, `pod_selfstop.sh`, `stage_*.py/sh`.
- **Production safety on the Sparks:**
  - a memory floor of 15 GB plus a 20 GB margin before each run, and 200 GB of disk;
  - production services are never driven by research code;
  - stopping a production container to free memory is done only with operator approval, restored through a trap, and logged. Two uses: `vllm-chat` on Spark-3 was out of service about 9 min for the P3 quiet window, and `vllm-asr` on Spark-2 was stopped for its L2 run.

---

## 6. Figures available now

| Figure | File | Use |
|---|---|---|
| Methodology and protocol diagrams | `paper/figures/fig1_methodology.*`, `fig2_protocol.*` | Already in the manuscript |
| Honest Tier B deviation by step, three x86 providers | `docs/pilot-findings/fig/tierb_honest_rtx_to_spark.png` | Methods / RQ1 preview (pilot) |
| SN23 rejecting an honest SD1.5 job | `docs/pilot-findings/fig/sn23_honest_fail_p00293.png` | RQ2 headline (pilot) |
| Throughput on all nodes | `docs/pilot-findings/fig/throughput_all_nodes.png` | RQ3 sizing |
| Run-level figures (W1 cosine, step distance, P7 memory, ComfyUI node) | `experiments/runs/20261124-wp0b-*/figures/` (PDF and CSV in git) | Supplementary |
| Spark utilization, rental timeline, balance, throughput | `docs/ops/2026-11-26-wp2-rentals/figures/` | Infrastructure / thesis |
| Same prompt and seed across hardware | `docs/ops/catalog/wp2/compare/` | Illustration for L4 |

---

## 7. What is still open

| Placeholder | Needs | When |
|---|---|---|
| R1.3–R1.8 (Tier B metric, τ_i, deviation by level, factor effects, RQ1 answer) | WP2 data home, then the calibration freeze (runbook §5): `thresholds_v1.json`, committed before any attack data | Next: pulls finish around 18:00–19:00 UTC; the Spark grid later |
| R2.2–R2.9 (detection rates, chosen k, partial-faking curve) | WP3 attack runs against the frozen thresholds | After the freeze |
| R3.1–R3.8 (verifier cost, storage, escrow CU and fees, Pareto, deterrence) | WP3 timings plus WP5 (Solana escrow on Devnet) plus WP4 Monte Carlo | Feb–Mar plan, can start earlier |
| R0.1, R0.4 (rented models, version table) | Collect from all WP2 manifests | After WP2 |
| R0.2 (repository and DOI) | Release at hand-off | End |

Next steps, in order:
1. Finish the WP2 pulls. Clean and commit the run metadata (`tools/sanitize_runs.py`), and refresh the catalog.
2. Build the WP2 analysis and run the calibration freeze.
3. Start WP4 proofs (no compute).
4. WP3 attacks.
5. WP5 escrow.

---

## 8. Caveats for whoever writes the Results section

- Pilot numbers come from 20–60 jobs. Use them to explain choices, and replace them with WP2 numbers in Results.
- The cross-node detection smoke test (§2.4) used thresholds fitted on the same data. It shows the pipeline works, nothing more.
- Spark timing: only the quiet-window P3 numbers may be quoted (§2.5); everything else is sizing.
- Manifest `cost_usd` values for runs pulled from staging overstate GPU time; use the pod lifetimes in runbook §4.
- Novelty: per-step spot-checking is prior art (SN30). The claim is the calibrated evaluation, the attack on the deployed rules, and the hardened two-tier check (doc 05 §2).
