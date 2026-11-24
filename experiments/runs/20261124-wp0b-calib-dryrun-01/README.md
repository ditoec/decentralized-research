# Calibration dry run on pilot data (not frozen)

`thresholds_pilot.json` is `python -m trajver.calibrate` run end to end on the pilot's honest data:

- Tier B: replays `20261124-wp0b-replay-{4090,3090,5090}on-spark5-01` (x86 provider → Spark verifier, 40 jobs each, 20 calibration prompts × 2 seeds).
- E0: honest image pairs among Spark-4, 4090, 3090 and 5090 (six pairings, 240 pairs).
- P1: noise comparisons of the three x86 hosts with each other and with Spark-4.

Command:

```
python -m trajver.calibrate --replay <three replay runs> --e0 <six e0 files> --p1 <noisecmp files> \
    --out experiments/runs/20261124-wp0b-calib-dryrun-01/thresholds_pilot.json
```

**This is not `thresholds_v1.json` and must not be used for attack runs.** With 120 honest samples per step, every quantile the runbook asks for at k ≥ 2 (99.5–99.87 %) is the sample maximum, so τ_i is the same for every k. The file says so in `notes`, and `calibrate` now refuses to write any `thresholds_v*` file in that case. The freeze happens at the end of WP2 on the calibration split at full size (runbook §5).

What the dry run shows already:
- Tier A is bit-exact across all pilot pairs, so ε_A = 0.
- τ_i (relative L2, k = 3) falls from 0.053 at step 0 to 0.0130 at step 10, 0.0046 at step 20 and 0.00056 at step 29: per-step thresholds are needed.
- E0 (honest cross-GPU pairs): LPIPS t_pass 0.079, DINOv2 t_pass 0.940; no pair was pixel-equal.
- x₀: the build-agnostic constant `X0_TOL` = 1e-5 holds with a margin of 4.3× over the largest P1 difference (2.3e-6).
