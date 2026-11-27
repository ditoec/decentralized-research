# Results Status: What Is Done and What Still Needs Work (2026-11-27)

For: the paper authors and the tech team. This is a review of the Results the tech team generated into the manuscript on 2026-11-27 (doc 12 §9), checked against the analysis files and the attack code. In the manuscript, every open item now carries a red **[NEEDS WORK: …]** marker; text without a marker is considered done.

## Done (paper-ready, from logged runs)

| Result | Manuscript | Source |
|---|---|---|
| Bit-identity by level: identical within one GPU model (L0, L2), never across chips or generations (L3, L4) | §4-1, Table 6 | `experiments/analysis/wp2/fig_r1_5_levels.csv` |
| Software factors on one unit: precision and attention change every image, deterministic mode changes none | §4-1, Factors | same file, `factor` column |
| Per-step honest deviation, falls about 100× over the steps, same profile for all three x86 → Spark pairs | §4-1, Figure 3 | `wp2/fig_r1_4_steps.csv` |
| Deployed rules fail: E2-W accepted ≥ 90% of every attack condition, including unrelated images; E0-N accepted 64–70% of A1, A2 and F1–F3 and rejected 0.4% of honest jobs | §4-2, Table 7 (except the F1–F3 rows, see below) | `wp3/v1/r2_5_acceptance.csv` |
| E2-H at k = 1 rejects ≥ 95% of A1, A2, A3 (Turbo, LCM-LoRA) and A8, at an honest false-rejection rate of 1.2% (CI 0.8–1.8%) on 1,800 cross-GPU test jobs | §4-2, Table 8 | `wp3/v2/r2_3_sensitivity.csv`, `honest_fpr.csv` |
| E1 image tolerance: the uncalibrated 2-level constant rejected every honest RTX 3090/4090 job; recalibrated post-freeze (v2), both versions reported | §4-2 | `wp3/v1`, `wp3/v2`, `docs/ops/LOG.md` |
| Per-step separability r_A ≥ 50% for every condition at k = 1 | §4-2, Table 9 (r_A column) | `wp3/v1/r2_6_rates.csv` |
| Verifier GPU time on the RTX 5090: Tier B k = 1 is 3.6% of E0, k = 3 10.9%, k = 8 29.1% | §4-3, Table 10 | cost-replay and base runs |
| Escrow cost per lifecycle path on Devnet (compute units, fees, latency), 100 jobs per path | §4-3, Table 11 | `wp5/devnet_combined_summary.json` |
| Monte Carlo agrees with the closed form (Equations 4 and 7) | §4-3 | `wp4/mc_sweep.csv` |

## Needs work

The Machine column follows three rules (doc 10 §2.2, runbook §1.1):
- timing comes only from a rented GPU that the job has to itself, never from a shared Spark;
- work that is only about numerical results runs on the Sparks, for free;
- new attack data comes from the RTX 5090, the provider card of the WP3 attack study, so it stays comparable.

Run times are estimates from job counts and measured seconds per image, not measurements.

| # | Problem | Why it matters | Who | Machine (estimate) | Manuscript |
|---|---|---|---|---|---|
| 1 | **β_A is measured on mismatched timers.** Attacked jobs record only `t_compute_s` (the whole attack harness: generation, forging, hashing), the honest baseline `t_sample_s` (sampling only). The control M, which computes honestly, comes out at −0.13; A1b (20 of 30 steps) at −0.37; SDXL-Turbo at 0.49, against about 0.92 on a Spark in the pilot (1.0 s vs 12.4 s) | Table 5, Table 9's β_A and p* columns, the RQ3 answer (p* = 0.253, "one checked step is cost-optimal") and the Conclusion all depend on β_A. A1 ("fewer steps costs more") would not survive review | Tech: re-time the honest baseline, A1b, A2, A3 Turbo, A3 LCM-LoRA, A8 and M (100 SDXL Euler jobs each) on the same field (sampling plus decode, outside the harness) | **Rented RTX 5090** (about 700 jobs, 1.5–2.5 h) | Flags in Table 9 text, RQ3 answer, Conclusion, abstract |
| 2 | **F1–F3 are forged from an honest trajectory.** `attacks/forgeries.py` keeps the honest D_i at every computed step, so the step after a forged segment disagrees with the forged state. A real forger that skips steps runs its next steps from its own forged states and leaves no such join | Tier A's rejection of F3 at s < 1, Tier B's "spoiled" extra steps, and F1–F3 at 100% for k = 1 are all inflated. For a realistic forger, detection at k = 1 should be about s (Equation 4 with m = sT). This also changes p* and the best k | Tech: add a forger that runs the model only at its computed steps, starting each from its own forged state. Then (a) regenerate and time F1–F3 (100 jobs each, s = 0.5; their β_A becomes measurable), and (b) regenerate the F3 sweep (s ∈ {0.1, 0.25, 0.5, 0.75, 1}, 100 jobs each) | (a) **Rented RTX 5090** as provider (300 jobs, under 1 h), **Sparks 4–6** as verifiers. (b) **Sparks** only, free (500 jobs plus replays, several hours) | Flags in Partial faking, Table 8 text, RQ2 answer, abstract |
| 3 | **Testbed demo with injected attackers not run** (runbook §7 item 5) | Methods promises an independent check of the deterrence region at three sampling rates | Tech: run it at p ∈ {0.05, 0.1, 0.25}, or the authors drop the sentence | **One rented consumer pod** (an RTX 3090 is enough; no timing is claimed) as provider and orchestrator host, **one Spark** as verifier, **Solana Devnet** (free). Runbook §7 planned about 15 GPU-hours, about US$8 | Flag in Methods, Testbed |
| 4 | **RQ1 gaps:** no SDXL run at L0; no SDXL DPM++ 2M at L2 or L3 | Methods plans L0 on 10% of the reference jobs and both samplers | Tech: run them, or narrow the Methods text | L0: **one Spark**, the one that ran the jobs (about 180 jobs, under 1 h, free). L2: **two Sparks** (150 jobs, free). L3: **rented RTX 5090**, in the same session as items 1 and 2a | Flag under Table 6 |
| 5 | **E0's honest false-rejection rate is 3.3% on test, against its 1% target.** Partly explained (2026-11-27, `experiments/analysis/wp3/e0_gap/`): (a) the two-metric rule already rejects 1.44% of honest jobs on the calibration split itself; (b) on test each metric is exceeded about twice as often, on all three cards; random 200/200 prompt re-splits give 0.78–2.94% (95%), and 3.33% or more in only 0.8% of splits; the failures concentrate on jobs failing against all three cards (6 vs 1). The calibration references are WP2 Spark-5 images, the test references a separate WP3 rerun on Spark-3 (code commit not recorded) | Decides whether the test references are equivalent to the calibration references, or whether some test prompts are harder; the text is already in the manuscript | Tech: rerun about 50 calibration jobs with the WP3 rerun procedure on Spark-3 and compare bit for bit with the WP2 Spark-5 images. Identical images point to the prompts; different images mean the test E0 must be rescored against a matching reference | **One Spark** (Spark-3), free, under 1 h | Explanation in Table 8 text; one flag left |
| 6 | Administrative: Funding; Acknowledgements (AI-assisted writing statement); Conflicts of interest (Vektor Labs); responsible disclosure to the subnet operators; ComfyUI commit in the reference; three web references to verify by hand | Submission requirements | Authors | None | Blue TODO and red verify markers |

**One rental covers the paid work.** Items 1, 2a and the L3 part of item 4 can run in one RTX 5090 session of about 4–6 hours: roughly US$6–9 at the Secure Cloud rate paid in WP2 (about US$1.40/h). The testbed pod for item 3 adds about US$8. Check this against the remaining US$200 budget (doc 10 §2.5) before booking. Everything else is free.

## Text corrected in this review (no new numbers)

- **Tier A mechanism.** The draft said solver inversion "leaves solver inconsistencies at the joins" and that Tier A "caught the solver-inversion forgery at every faked fraction below one". Both describe this forgery implementation, not a careful forger. Partial faking and the Discussion now say so, and credit detection to Tier B, as the Methods already did.
- **Partial-faking claim.** The abstract and RQ2 answer said the sweep "matches the spot-check model once the steps a forgery spoils are counted". Fitting Equation 4 with m set to the measured number of failing steps is close to circular, so the claim is removed. Equation 4 with m = sT is the expected detection for a realistic forger.
- **RQ2 headline.** It now counts the five model- and step-substitution conditions separately from the forgeries, whose detection is pending item 2.
- **Missed targets.** Table 8's text now states that E2-H's 1.2% and E0's 3.3% exceed their 1% targets.
- **β_A explanation.** The claim that A1b's forging "costs more than the ten skipped steps save" is replaced by the timing explanation in item 1.
- **Limitations.** Under thresholds v2 the delivered image is no longer bound to the committed trajectory; this is now stated.
