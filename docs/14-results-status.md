# Results Status: What Is Done and What Still Needs Work (2026-11-27)

For: the paper authors and the tech team. This is a review of the Results the tech team generated into the manuscript on 2026-11-27 (doc 12 §9), checked against the analysis files and the attack code. In the manuscript, every open item now carries a red **[NEEDS WORK: …]** marker; text without a marker is considered done.

## Done (paper-ready, from logged runs)

| Result | Manuscript | Source |
|---|---|---|
| Bit-identity by level: identical within one GPU model (L0, L2), never across chips or generations (L3, L4) | §4-1, Table 6 | `experiments/analysis/wp2/fig_r1_5_levels.csv` |
| Software factors on one unit: precision and attention change every image, deterministic mode changes none | §4-1, Factors | same file, `factor` column |
| Per-step honest deviation, falls about 100× over the steps, same profile for all three x86 → Spark pairs | §4-1, Figure 3 | `wp2/fig_r1_4_steps.csv` |
| Deployed rules fail: E2-W accepted ≥ 90% of every attack condition, including unrelated images; E0-N accepted 64–70% of A1, A2 and F1–F3 and rejected 0.4% of honest jobs | §4-2, Table 7 | `wp3/v1/r2_5_acceptance.csv` |
| E2-H at k = 1 rejects ≥ 95% of A1, A2, A3 (Turbo, LCM-LoRA) and A8, at an honest false-rejection rate of 1.2% (CI 0.8–1.8%) on 1,800 cross-GPU test jobs | §4-2, Table 8 | `wp3/v2/r2_3_sensitivity.csv`, `honest_fpr.csv` |
| E1 image tolerance: the uncalibrated 2-level constant rejected every honest RTX 3090/4090 job; recalibrated post-freeze (v2), both versions reported | §4-2 | `wp3/v1`, `wp3/v2`, `docs/ops/LOG.md` |
| Per-step separability r_A ≥ 50% for every condition at k = 1 | §4-2, Table 9 (r_A column) | `wp3/v1/r2_6_rates.csv` |
| Verifier GPU time on the RTX 5090: Tier B k = 1 is 3.6% of E0, k = 3 10.9%, k = 8 29.1% | §4-3, Table 10 | cost-replay and base runs |
| Escrow cost per lifecycle path on Devnet (compute units, fees, latency), 100 jobs per path | §4-3, Table 11 | `wp5/devnet_combined_summary.json` |
| Monte Carlo agrees with the closed form (Equations 4 and 7) | §4-3 | `wp4/mc_sweep.csv` |
| **Item 1 done (2026-11-27, second RTX 5090 session):** β_A on one timer. Each attacked job is timed against an honest generation of the same job in the same process, in alternating order (`t_sample_s`); A2 against an honest run of the same jobs on the same card. A1b 0.31, A3 Turbo 0.88, A3 LCM-LoRA 0.76, F1–F3 0.47; the controls M and A8 come out at −0.01 to 0; A2 −0.09 (no saving). Honest sampling took 2.6 s on this host and 11.0 s on the first session's host, so pairing within one process matters | §4-3, Table 9, Methods | `wp3/v1/r2_4_beta.csv`; runs `20261127-wp3-time-*`, `-timebase-`, `-atkr-*` |
| **Item 2 done (2026-11-27):** realistic forger (`forgeries.realistic_euler`: the model runs only at computed steps, from the forger's own states). (a) F1–F3 at s = 0.5 on the RTX 5090: E2-H rejects 48% at k = 1, 87% at k = 3, 100% at k = 8, against Equation 4's 50–51%, 89%, 100%; Tier A 0%. (b) F3 sweep, s ∈ {0.1, 0.25, 0.5, 0.75, 1}, 100 jobs each on the Sparks: within 16 points of Equation 4 with m = sT in all 25 (s, k) cells; the largest gap is at s = 0.75, k = 1 (58% vs 74%), where 31 of 100 jobs had a faked step within τ_i (setting m to the steps above τ_i predicts 66%). Tier A rejected none of the 500 sweep jobs. p* now uses Equation 4's q(s, k) for the forgers: 0.481 at k = 1 (set by F2), 0.449 at k = 2 (cost-optimal), 0.450 at k = 3 | §4-2 Partial faking, Figure 5, Tables 8–9, RQ2/RQ3 answers, abstract | `wp3/v1/fig_r2_7_partial.csv`, `r2_3_sensitivity.csv`; runs `20261127-wp3-atkr-*`, `-sweepr-f3-*`, their `-verify-` runs; `wp4/mc_summary.json` |
| Qualitative Figure 4: delivered images of three test jobs, honest (Spark, RTX 5090, ×10 difference) and each attack; illustration only | §4-2, Figure 4 | `paper/tools/fig_examples.py`, `wp3/fig_examples_sources.json` (run id and sha256 per tile) |
| **Item 4 done (2026-11-27):** Table 6 complete. 45 finished WP2 runs had never been fetched (SDXL DPM++ references on Sparks 5–6, Spark-4's SDXL Euler L0 and grid, replays, rented test runs); Spark-4 then finished the SDXL DPM++ reference and its L0 repeat. Every image bit-identical within one GPU model (L0, L2) for both models and both samplers, none across chips or generations | §3-4, §4-1, Table 6 | `wp2/fig_r1_5_levels.csv` |
| **Item 5 done (2026-11-27):** 90 calibration jobs regenerated on Spark-3 with the test-split reference procedure are bit-identical to the calibration references (images and latents). The reference procedure is ruled out; E0's 3.3% belongs to the test jobs (failures concentrate on jobs that fail against all three cards) | §4-2, E0 paragraph | `wp3/e0_gap/refcheck.json`, run `20261127-wp3-e0check-cal30-sdxl-euler-spark3-01` |
| References checked in a browser (Akash, Solana whitepaper, Solana fees; fees URL moved); Hawkeye in Proceedings of MLSys 8; ComfyUI commit confirmed from all 365 run manifests | References | `docs/ops/LOG.md` 2026-11-27 |

## Needs work

**Authoring notes are hidden in the built manuscript (2026-11-27).** The red NEEDS WORK and reference notes, the blue TODOs and the contact placeholder stay in `paper/tools/build_esj_docx.py` but are left out of the .docx and PDF. The build lists each hidden note; `--notes` shows them all again. The Acknowledgements section is omitted until it has text, and the corresponding author's e-mail (`CONTACT_EMAIL`) is blank until the authors set it. Hidden is not resolved: items 3–6 below are still open, and the Conflicts of Interest statement still needs the Vektor Labs declaration confirmed before submission.

The Machine column follows three rules (doc 10 §2.2, runbook §1.1):
- timing comes only from a rented GPU that the job has to itself, never from a shared Spark;
- work that is only about numerical results runs on the Sparks, for free;
- new attack data comes from the RTX 5090, the provider card of the WP3 attack study, so it stays comparable.

Run times are estimates from job counts and measured seconds per image, not measurements.

| # | Problem | Why it matters | Who | Machine (estimate) | Manuscript |
|---|---|---|---|---|---|
| 3 | **Testbed demo: running (2026-11-27).** `20261127-wp5-testbed-01` on Devnet: honest provider and two injected attackers (A3 Turbo, realistic F2 at s = 0.5) replaying recorded RTX 5090 outputs, 50 jobs each at p ∈ {0.05, 0.1, 0.25}, k = 2, B/P = 1; sampled jobs verified live on Spark-5/6. Code: `code/tools/testbed_demo.py`, `testbed_analyze.py` | Methods and Results text appear from `experiments/analysis/wp5/testbed/summary.json` | Claude | Devnet (test SOL only) and Sparks 5–6 | Methods sentence hidden until the summary exists |
| 6 | Administrative: Funding; Acknowledgements (AI-assisted writing statement); Conflicts of interest (Vektor Labs); responsible disclosure to the subnet operators; ComfyUI commit in the reference; three web references to verify by hand | Submission requirements | Authors | None | Blue TODO and red verify markers |

**Paid work left.** Items 1 and 2a ran in one RTX 5090 Secure Cloud session on 2026-11-27 (US$1.91; balance US$19.53 after it). Still paid: the testbed pod for item 3 (about US$8) and the L3 part of item 4. Check against the US$200 cap (doc 10 §2.5) before booking. Everything else is free.

## Text corrected in this review (no new numbers)

- **Tier A mechanism.** The draft said solver inversion "leaves solver inconsistencies at the joins" and that Tier A "caught the solver-inversion forgery at every faked fraction below one". Both describe this forgery implementation, not a careful forger. Partial faking and the Discussion now say so, and credit detection to Tier B, as the Methods already did.
- **Partial-faking claim.** The abstract and RQ2 answer said the sweep "matches the spot-check model once the steps a forgery spoils are counted". Fitting Equation 4 with m set to the measured number of failing steps is close to circular, so the claim is removed. Equation 4 with m = sT is the expected detection for a realistic forger.
- **RQ2 headline.** It now counts the five model- and step-substitution conditions separately from the forgeries, whose detection is pending item 2.
- **Missed targets.** Table 8's text now states that E2-H's 1.2% and E0's 3.3% exceed their 1% targets.
- **β_A explanation.** The claim that A1b's forging "costs more than the ten skipped steps save" is replaced by the timing explanation in item 1.
- **Limitations.** Under thresholds v2 the delivered image is no longer bound to the committed trajectory; this is now stated.
