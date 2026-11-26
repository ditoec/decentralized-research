# WP4: Monte Carlo of the analytical model

Status 2026-11-26: simulator built and tested. **No results yet.** The inputs r_A, α_s and β_A come from WP3 (runbook §6), which has not run, so every output of the shipped params file is provisional and must not be quoted. This page reports no numbers.

Code: `code/trajver/montecarlo.py` (on top of `code/trajver/theory.py`). Params: `experiments/configs/mc_params_provisional.json`. Tests: `code/tests/unit/test_montecarlo.py`. Runbook: §8. Figures: R3.2, R3.5, R3.6.

## The three propositions (manuscript §3-3)

**Proposition 1 (output-only ceiling, Eq. 3).** Any rule that sees only the output, with false-rejection rate α, has sensitivity q_A ≤ α + TV(𝒟_A, 𝒟_H) for every sampling rate p. Sampling more often changes how many jobs are examined, not this bound. The simulator does not test it; WP3 measures it directly (R2.5).

**Proposition 2 (spot-check detection, Eqs. 4–6).** A provider fakes m = sT of T steps so that Tier A passes, and Tier B checks k steps drawn without replacement. A faked step fails with probability r_A, an honest step with α_s. The number of faked steps among the checked ones is hypergeometric, so a sampled faked job fails with q(s, k) of Eq. 4 (`theory.q_spot_check`), and an honest job with α(k) = 1 − (1 − α_s)^k (Eq. 5, `theory.alpha_job`). Holding α(k) ≤ α* needs the per-step budget of Eq. 6 (`theory.alpha_step_budget`).

**Proposition 3 (all-or-nothing best response, Eqs. 7–9).** Honest cost c, saving β_A·s·c from faking a fraction s, forfeit L = P + B on detection, no reputation term. The gain over honesty is Δ(s) = β_A s c − p[q(s, k) − α(k)]L (Eq. 7, `theory.gain`). In the large-T form Δ is convex in s, so the best response is s* ∈ {0, 1}, and cheating is deterred if and only if Δ(1) ≤ 0, which is Eq. 8 (`theory.deterred`). The smallest sampling rate that deters every attack in scope is p*(k) of Eq. 9 (`theory.p_star`); it is infinite when r_A ≈ α_s.

## Simulation design

For each attack A with r_A and β_A set, and each cell (p, k, B/P, s), the simulator draws `n_sim` jobs. Per job:

1. sampled ~ Bernoulli(p), as the on-chain `draw_sample` does;
2. x ~ Hypergeometric(T, m = round(sT), k), the faked steps among the checked ones;
3. one uniform U_j per checked step: a faked step fails if U_j < r_A, an honest one if U_j < α_s;
4. the honest counterfactual of the same job reuses the same draws with every step honest (common random numbers), so at s = 0 cheating and honesty are the same job and Δ = 0 exactly;
5. Δ_i = β_A s c − L · sampled_i · (fail_cheat_i − fail_honest_i). Its mean is Eq. 7 with the finite-T q of Eq. 4.

If α_s is null, the simulator uses the Eq. 6 budget for α* at each k, which is how the verifier will be calibrated. Attacks whose r_A or β_A is null are skipped and listed as waiting for WP3.

Per cell, the output records the simulated detection rate with a Wilson 95% CI against Eq. 4, the mean gain with a normal 95% CI against Eq. 7, the Eq. 8 verdict, and p*(k). The summary checks:

- **Prop. 2:** the share of cells where Eq. 4 lies inside the Wilson CI. About 95% is expected at nominal coverage; a much lower share means the model or the code is wrong.
- **Prop. 3, Eq. 8:** at s = 1, the sign of the simulated Δ(1) against the Eq. 8 verdict. Cells where the CI contains 0 are counted as on the boundary, not as disagreements.
- **Prop. 3, all-or-nothing:** cells where an interior s has a gain significantly above both endpoints. The expected count is zero.

Finite T is used for q (Eq. 4), and Eq. 8 is exact at s = 1 because every checked step is then faked. The large-T approximation enters only through the convexity argument. The simulation therefore also shows whether the endpoint result holds at the workflow's real T.

## Outputs

`python -m trajver.montecarlo --params PARAMS.json --out DIR` writes:

- `mc_sweep.csv`, long format: `attack, p, k, BP, s, n_sim, detect_sim, detect_ci_lo, detect_ci_hi, detect_closed, gain_mean, gain_ci_lo, gain_ci_hi, gain_closed, deterred, p_star`;
- `mc_summary.json`: the seed, the params sha256 and a full copy of the params, git commit, numpy version, the checks above, and the attacks run or skipped.

The RNG is `numpy.random.default_rng(seed)`, and the same seed and params give identical rows. The R3.6 CSV of runbook §8b (`source = monte_carlo`) is a projection of `mc_sweep.csv` at s = 1.

## Final run (after WP3)

1. Copy the params file to `mc_params_wp3.json`. Fill r_A and β_A per attack, α_s per evidence level, T, and c (cost per job at the dated hourly rate), each with the `run_id` it came from, and set `"provisional": false`.
2. Run into `experiments/runs/<date>-wp4-montecarlo-01/`, log it in `docs/ops/LOG.md` and the catalog, and only then fill R3.2, R3.5 and R3.6.
