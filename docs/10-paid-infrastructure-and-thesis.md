# Infrastructure Plan (six shared DGX Sparks, US$200 on RunPod) and Thesis Operating Model

Date: 2026-11-23 (third revision the same day). **Status: applied** to `05-revised-design.md`, `07-runbook.md` and the manuscript (§6). The corresponding author should still confirm it.

**Hard constraints:**
- Total paid infrastructure is at most **US$200**, for everything.
- All rented compute comes from **RunPod**, including the x86 Blackwell card and the host of the Solana local validator.
- The only owned hardware is **six DGX Sparks, which also run a live production platform**. There are no owned RTX 5080s.

Two objectives, in this order: **(1) the ESJ paper, (2) the thesis.** The paper's scope does not grow.

RunPod prices below were read from runpod.io/pricing on 2026-11-23 (page dated 2026-11-12). Run times are estimates until the pilot measures them. Record the actual rate in each run manifest.

## 1. What changed, and the principle

| Fact | Consequence |
|---|---|
| No owned RTX 5080 | Every x86 GPU is rented. The Sparks carry the volume |
| Rented cards are consumer GeForce RTX only (decided 2026-11-23) | The x86 Blackwell card is the **RTX 5080** (Community Cloud, US$0.39/h, the card the paper first described); the RTX 5090 is its fallback. Workstation and datacenter cards (A5000, L4, A100) are not used |
| Six Sparks, not two | Unit-to-unit variation (L2) rests on up to 15 same-model pairs |
| The Sparks are shared with production | Research runs beside live services: small memory footprint, no timing claims from shared nodes, strict rules (§2.2) |
| The Solana validator runs on RunPod | A rented x86 pod builds the program and runs the local validator |

**Principle: the Sparks do everything that is only about numerical results. RunPod does everything that needs x86, another GPU generation, or a machine to itself.**

| Need | Where | Paid? |
|---|---|---|
| Full 24-config factor grid; L0, L1, L2 | Sparks | No |
| Large reference-config workload (calibration volume) | Sparks | No |
| Attack generation and most verification | Sparks | No |
| Raw data storage | Spark disks | No |
| x86 Blackwell (L3) and Ampere, Ada (L4) honest runs | RunPod | Yes |
| Initial-noise and Tier A checks on an x86 CPU | RunPod (minutes) | Yes, cents |
| All timing: attacker's saving β_A and verifier GPU-seconds | RunPod (a pod to itself) | Yes, small |
| Rented provider and rented verifier for the attack runs | RunPod | Yes, small |
| Solana program build and local validator | RunPod x86 pod | Yes, small |
| Solana Devnet | free | No |

The submission target stays **mid-May 2027**.

## 2. Compute plan

### 2.1 Hardware matrix

| Group | Model | Generation, host | Role | Price (Community) |
|---|---|---|---|---|
| Owned | DGX Spark ×6 (Spark-1 … Spark-6) | Blackwell GB10, ARM64 | Volume, verifier, storage | — |
| RunPod, required | RTX 5080 | Blackwell, consumer, 16 GB | L3; provider; timing | US$0.39/h (Community only) |
| RunPod, required | RTX 4090 | Ada, consumer, 24 GB | L4; verifier; timing | US$0.34/h |
| RunPod, required | RTX 3090 | Ampere, consumer, 24 GB | L4; provider; also the cheap x86 host for Solana and smoke tests | US$0.22/h |
| RunPod, if the reserve allows | RTX 5090 | Blackwell, consumer, 32 GB | a second Blackwell chip; fallback for the 5080 | US$0.69/h |
| RunPod, substitutes when a required card has no stock | RTX 4080 SUPER (Ada), RTX 3090 Ti (Ampere) | consumer | same role as the card they replace | US$0.28/h, US$0.27/h |

Prices are Community Cloud on-demand rates from Runpod's catalog read on 2026-11-23.

- This gives **4 or 5 GPU models across 3 generations** (Ampere, Ada, Blackwell), all consumer RTX apart from the Spark: 6 to 10 cross-model pairs.
- **Stock is the binding constraint, not price.** On 2026-11-23 only the RTX 5080 and RTX 4090 had pod stock. Book each card when a stock read shows it; use the substitutes above, or Secure Cloud at about twice the price, before giving up a generation.
- Turing and older, and Hopper, are not tested. Make no claim about them.
- **L2:** the six Sparks. One paid extra: a second RTX 5080 on a different host for a short subset, to see host-to-host spread on rented x86.
- **L1 (software factors)** is measured in full only on the Spark, because every Spark is the same platform and a full x86 grid is not worth its cost. Two measures narrow that gap:
  - **Second software stack on a Spark (free).** Spark-4 repeats all 24 configs on 100 prompts under a second PyTorch and CUDA version, in a second research image. This shows whether the factor effects survive a library change.
  - **x86 factor slice on the RTX 4090 (about US$5).** At fp16, deterministic mode {off, on} × attention backend {SDPA, alternative} × both samplers, on the 200-prompt grid subset. That is six configs beyond the reference pair, about a quarter of the full grid. Add xformers as a third backend if it installs. This puts x86 evidence under the one claim that needs it: whether a deterministic configuration exists.
  - The paper then says: the full grid was measured on one GPU platform under two software stacks, and the deterministic-mode and attention factors also on an x86 Ada card.
- RunPod pods are containers and the host sets the driver. Verify the card with `nvidia-smi` and the GPU UUID, and record the driver, host and data-center ID.
- Community Cloud first. Secure Cloud costs two to three times as much; use it only when a model is unavailable.

### 2.2 Using the Sparks beside production

Inventory, taken read-only on 2026-11-23: all six are identical (DGX OS 7.5.0, kernel 7.0.0-1019-nvidia, driver 580.178.04, CUDA 13.0, 20 ARM cores, 121 GB unified memory, 1 TB NVMe). All six run live services and have been up for five weeks.

| Node | Memory free | Disk free | Research role |
|---|---|---|---|
| Spark-1 | 25 GB | 617 GB | L2 subset only |
| Spark-2 | 25 GB | 715 GB | L2 subset only |
| Spark-3 | 41 GB | 439 GB | L2 subset only |
| Spark-4 | 46 GB | 491 GB | **Main research node** |
| Spark-5 | 47 GB | 540 GB | **Main research node** |
| Spark-6 | 44 GB | 541 GB | **Main research node** |

Host names, addresses, login details and the production services on each node are kept in `docs/local-nodes.md`, which is not in git because this repository is public.

Rules for every research run on a Spark:
1. **Never touch a production container**, including the ComfyUI that one node already runs for production (it is not our pinned commit). Research containers carry the label `research=esj` and a localhost-only port.
2. **Memory.** GPU and system memory are one pool, so a research job that runs out of memory can take a production model down. SDXL in fp16 is the normal load. Test fp32 on one node first. FLUX runs only in a window agreed with the platform admin, or not at all.
3. **Stop conditions.** The run script pauses when free memory falls below 15 GB or free disk below 200 GB.
4. **No timing claims from a Spark** unless the admin grants a quiet window with the chat model stopped. Timing comes from RunPod.
5. **Co-tenancy check (new, free).** Repeat 50 jobs while the chat model is busy and while it is idle. If the outputs are bit-identical, the paper can state that shared load does not affect verification. Record the load from the existing Prometheus on node 5.
6. **Versions.** Automatic updates are on and the research account has no sudo. Ask the admin to hold the driver and kernel packages from January to March. Every manifest records the versions, so drift is visible.
7. **PyTorch.** The PyTorch 2.9.1 in the production image warns that the GB10's compute capability (12.1) is above its supported maximum (12.0). Choose the research image's PyTorch build in the pilot and record it.
8. **Storage.** Raw data is spread over nodes 4 to 6 and moved between them over the 200 Gb links that join nodes 3 to 6. Rented data lands on these nodes too.
9. **Network.** The Sparks sit behind a VPN, so a RunPod pod cannot open a connection to them. The Sparks always connect outward: they pull data from pods and send their own transactions to Devnet.

### 2.3 Workloads

| Workload | Sparks | RunPod models |
|---|---|---|
| Reference config (fp16, SDPA, euler and dpmpp_2m, `--deterministic` off) | 1,000 prompts × 3 seeds on nodes 4, 5 and 6 | 500 prompts × 3 seeds |
| Rest of the 24-config grid | 200 prompts × 3 seeds on nodes 4 and 5 | not run |
| Precision factor (bf16, fp32) | part of the grid | 100 prompts × 3 seeds |
| Deterministic-mode and attention factors at fp16 (x86 slice) | part of the grid | RTX 4090 only, 200 prompts × 3 seeds |
| Second software stack, all 24 configs | 100 prompts × 3 seeds on node 4 | — |
| L0 repeats | 10% subset on node 4 | — |
| L2 subset | 50 prompts × 3 seeds on all six | second RTX 5080, same subset |
| Models | SD1.5, SDXL; FLUX.1-schnell optional (rule 2) | SD1.5, SDXL |

Sample sizes for the attack study (RQ2):

| Quantity | Value | Where |
|---|---|---|
| Honest test jobs per stratum | 1,000 where the pooled pairs allow it, never under 299 | Sparks, plus the rented honest runs |
| Attacked jobs per cell, Spark provider | 100 | Sparks |
| Attacked jobs per cell, rented provider | 100, on the RTX 5080 and RTX 3090 | RunPod |
| Timing of each attack (β_A) | 20 jobs per attack | RunPod RTX 5080 and RTX 3090 |
| Verifier GPU-seconds per evidence level | one pass | RunPod RTX 4090 and RTX 5080 |

The rented-provider cells matter: a consumer x86 card as provider and a Spark as verifier is the direction a real marketplace has.

### 2.4 How RunPod runs are operated

1. **Two container images, one per CPU architecture** (arm64 for the Sparks, x86-64 for RunPod), each pinned by digest, with the same ComfyUI commit, custom nodes and verifier code. Model files are checked by sha256 at start-up.
2. **One launcher script:** start the pod, verify the card and model hashes, run the workload, wait for a Spark to pull the raw data with checksums, write the manifest, then **terminate the pod**. An idle volume bills at US$0.20 per GB per month.
3. **Dry runs.** Workload logic is first run for 20 jobs on a Spark. The x86 image is then smoke-tested for 20 jobs on the cheapest consumer pod (RTX 3090, US$0.22/h) before any dearer pod starts.
4. **Manifest fields for rented nodes:** `provider`, `cloud_type`, `host_id` or data-center ID, `hourly_rate_usd`, `billed_hours`, `cost_usd`.
5. **Dollar costs in the paper.** RQ3 states verifier cost and the attacker's saving in dollars at the recorded rental rates.
6. RunPod's pricing page does not mention data-transfer fees. Confirm this in the pilot with the first large copy.

### 2.5 Budget

| Item | Basis | Estimate |
|---|---|---|
| Pilot (RTX 5080, 4090, 3090, a few hours each; x86 noise check) | about 10 GPU-hours | US$8 |
| Honest runs, three required models | about 8,400 jobs per model; about 100 GPU-hours in total, doubled for uncertainty | US$60 |
| Second RTX 5080 (L2 subset) | 3–4 hours | US$3 |
| x86 factor slice on the RTX 4090 | about 7,200 jobs, about 12 hours | US$5 |
| Attack study on RunPod: rented providers, rented verifier, timing | about 30 GPU-hours | US$15 |
| Testbed demo with rented providers | about 15 GPU-hours | US$8 |
| Solana build and local validator on an RTX 3090 pod (or a CPU pod if cheaper) | about 60 hours | US$13 |
| Pod disk during runs | — | US$10 |
| Solana fees | Devnet | US$0 |
| **Planned total** | | **about US$120** |
| Optional RTX 5090 | about 15 hours | US$10 |
| **Reserve for reruns and the review round** | | **about US$70** |

Spending rules:
- Load RunPod credit in US$50 steps. The prepaid balance is then the cap.
- Stop and review at **US$120 spent**. The RTX 5090 is booked only if the required three came in on estimate.
- Keep at least US$30 of the reserve untouched until reviews arrive.

## 3. Solana plan

| Stage | Where | Purpose | Jobs |
|---|---|---|---|
| S1 | Local validator on a RunPod x86 pod (RTX 3090, or a CPU pod) | Compute units and signature counts per instruction. Scripted replay of each lifecycle path; no GPU work needed | at least 100 per path |
| S2 | Devnet | End-to-end testbed with real nodes; latency | at least 100 per path |

- **Paths:** unsampled accept, sampled pass, sampled fail with dispute, timeout refund.
- **Build:** the Anchor program is built on the same x86 pod. Keep the program source and the built artifact in the repository so a terminated pod loses nothing.
- **Run S1 in few, long sessions**, not many short ones. The pod is only up while S1 runs.
- **S2 topology:** a rented card (RTX 3090, 4090 or 5080) is the provider, a Spark is the verifier, and the orchestrator runs on the provider's pod. The Spark connects outward to the pod and to Devnet (§2.2 rule 9). Record the RPC endpoint and its rate limits.
- **Mainnet is out of the paper.** Deploying a program there locks up several SOL of rent, which does not fit the cap. Mainnet fees are calculated from the measured signature counts and compute units at a dated SOL price, and labeled as calculated.
- **What is lost:** measured mainnet latency, priority-fee behaviour and landing rate. The paper states this as a limitation.

## 4. Timeline changes (the rest of doc 05 §8 is unchanged)

| WP | Change | Dates |
|---|---|---|
| WP0b pilot | Runs on Sparks 4 to 6 plus short RunPod rentals (RTX 5080, 4090, 3090). Adds the co-tenancy check and the choice of PyTorch build. Agree the research windows and the package hold with the platform admin | Nov 26 – Dec 6 |
| WP1 | Add the two container images, the launcher, and the Spark run script with its stop conditions | Dec 7 – Jan 3 |
| WP2 | Spark grid on nodes 4 to 6; RunPod honest runs in the first two weeks | Jan 4 – Jan 31 |
| WP3 | Attacks on Sparks; rented providers, verifier and timing on RunPod | Feb 1 – Feb 28 |
| WP5 | Solana S1 on a RunPod pod, S2 on Devnet | Jan 4 – Mar 14 |
| Submission | Unchanged | mid-May 2027 |

New risk for the schedule: the Sparks are shared, so their real throughput is unknown until pilot item P3. If the Spark workload does not fit in January, cut the reference config to 500 prompts before anything else.

## 5. The thesis

Assumption to confirm: this is one student's thesis (Maradita, UPH) in which the ESJ paper is the main publication. The repository holds no thesis requirements yet, so the points marked *check* depend on the programme.

### 5.1 Relationship between paper and thesis

The paper is the narrow, defensible core. The thesis is the superset: it contains the paper, plus the breadth that was deliberately cut from it. Nothing moves in the other direction; thesis topics must not leak back into the paper before submission.

| Thesis chapter | Source |
|---|---|
| 1. Introduction, problem, research questions | Paper §1, widened |
| 2. Background and literature review | Paper §2 plus the systematic review in `drafts/` (SLR), brought up to date |
| 3. System and threat model, protocol | Paper §3-1, §3-2, with the full escrow design and state machine |
| 4. Honest variation across GPUs | Paper RQ1, with the full per-pair tables the paper has no room for |
| 5. Attack separability and the hardened check | Paper RQ2 |
| 6. Deterrence model and settlement cost | Paper RQ3 and the propositions, with full proofs |
| 7. Extensions (thesis-only) | See §5.2 |
| 8. Discussion, limitations, conclusion | — |

### 5.2 Thesis-only extensions (start after paper submission)

Pick two or three. The first five need no paid infrastructure.

1. **Language-model workloads** (Ollama): do the output-only ceiling and activation-style checks carry over?
2. **Ancestral and SDE samplers** with CPU-side per-step noise as a protocol requirement.
3. **Dishonest or colluding verifiers:** how 2-of-3 adjudication degrades with 10–20% lazy verifiers.
4. **Broker versus chain:** the B3-versus-OC comparison as a measured arm, not an argument.
5. **Reputation:** the ablation the paper skips.
6. **Mainnet measurement** and **more GPU generations**, only if new funds appear. Both need a separate budget.

### 5.3 How the work should operate

- **One evidence base.** Paper and thesis both take every number from `experiments/runs/`. Thesis-only runs get their own work-package prefix (`wpT1`, …) so the two never mix.
- **Freeze points.** Tag the repository at paper submission. The thesis cites that tag for the shared chapters and adds on top of it.
- **Roles.**
  - Corresponding author: scope, theory, writing, final say on any threshold or config change.
  - Engineer: builds and runs from the runbook.
  - Co-authors: review at each gate; one of them holds the RunPod account and approves every pod start.
  - Platform admin of the DGX Sparks: agrees the research windows and is told before any heavy run (§2.2).
- **Cadence.** A short weekly sync with three fixed items: runs finished (by run ID), RunPod spend against the US$200, and decisions needed. Decisions go into a dated log in `docs/`.
- **Gates.** Keep the two go/no-go points of doc 05 and add two: **paper submitted** (thesis-only experiments may begin) and **reviews received** (reviewer requests take priority over thesis extensions).
- **Keep part of the reserve for the review round.** Reviewers may ask for one more run on a rented card. Whatever is left of the US$100 reserve after WP3 is held for that, not spent on extras.
- **Use the review period.** Thesis-only experiments and chapters 1–3 are written while the paper is under review. Reviewer comments then improve the thesis for free.
- **Check with the programme:**
  - thesis format and language;
  - whether a published or accepted paper is a graduation requirement, and by when;
  - how the journal's licence allows the article to be reused in the thesis;
  - how co-authored work must be attributed in the thesis.
- **Disclosure.** The break-and-fix result concerns deployed networks. Keep testing offline, and settle the disclosure to the affected teams before the preprint (doc 06 §2), not at thesis time.

## 6. Where this plan was applied

1. `05-revised-design.md`: §4.5 (hardware, levels, RunPod list, workloads, testbed), §6 claim 1, §7 risks, §8 timeline and pilot checklist.
2. `07-runbook.md`: ground rules, §0, §1 (Spark rules and RunPod setup), §2 (pilot), §3.3 (timing), §3.4 (images and launcher), §4, §6, §7, §10.
3. `paper/tools/build_esj_docx.py`, `paper/tools/make_figures.py`, and the rebuilt `paper/manuscript_ESJ.docx` and Figures 1 and 2: the abstract, Section 3-4, the Figure 2 caption, the two RQ3 tables and the Limitations paragraph.
4. `CLAUDE.md`: the Hardware line.
