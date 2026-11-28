# Confirmatory run of the v2 honest false-rejection rate (pre-registered 2026-11-28)

For: the authors and the engineer. Written and committed before any confirmatory job is generated; the git
commit date of this file is the evidence. Answers co-author review point 1 (P.Y., 2026-11-28): the v2 result
came after the protocol was frozen and needs an untouched confirmatory set.

## Why only the honest rate is confirmed

Thresholds v2 change one parameter of v1: the E1 image tolerance, from 2 to 264 uint8 levels, so the image
comparison never rejects. Every other threshold (E0, Tier A's ε_A, Tier B's τ_i) is v1 as frozen before the
test split was examined. Two consequences:

- **Attack detection cannot gain from v2.** v2 removes a check and adds none, so for every attacked job a v2
  rejection implies a v1 rejection. v2 was also frozen and committed (05:02 UTC on 2026-11-27, commit
  `dee3e68`, sha256 `d62ea967…f0c0`) before any attack verification finished and before any attack verdict
  was analysed (`docs/ops/LOG.md`, 2026-11-27).
- **The honest rate is what v2 changed, after the honest test split was seen.** The v2 value of E2-H's
  honest false-rejection rate (1.22%, 22 of 1,800) is therefore exploratory. This run confirms or refutes it.

## Data (untouched)

- Prompts: `experiments/configs/prompts_confirm200.txt`, the 200 test-split prompts of `prompts_test.txt`
  that are not in `prompts_rent_test200.txt` (file order kept; sha256
  `e8c1c4e649ba114f67eb9ed5d98c9b07d43150ca740e6f89b9d15b1cea41ec83`). No run has generated them:
  they appear in no other prompt list.
- Jobs: 200 prompts × seeds 0, 1, 2 = 600 jobs per card, SDXL 1024², Euler, 30 steps, reference configuration
  (fp16, SDPA, deterministic mode off), the pinned ComfyUI and software image of the study.
- Providers: rented RTX 4090, RTX 5090 and RTX 3090 (as for the test split), each in its own pod, whichever is
  in stock first. The run is reported per card. If a card stays out of stock, the run is reported for the cards
  that ran and the missing card is named; no card is replaced by another model.
- Retention: class O (8 pre-drawn steps plus Tier A) with a fresh draw seed held on a DGX Spark and revealed
  after generation, as in WP3.
- Verifier: DGX Spark, `trajver.verify` and `trajver.e1img measure` as in WP3; E0 against a DGX Spark
  reference of the same 600 jobs (secondary).

## Analysis, fixed now

- Thresholds: `thresholds_v1_sdxl_euler.json` (sha256 `91cdc2f2…cc58`) and the v2 patch
  (`thresholds_v2_sdxl_euler.json`, sha256 `d62ea967…f0c0`). Nothing is recalibrated.
- Scripts: `code/tools/wp3_analyze.sh`'s steps (`trajver.analysis_wp3`, `trajver.e1img patch`) with the
  confirmatory runs as `--honest`, and `experiments/analysis/wp3/cluster/cluster_ci.py` for the clustered
  intervals (cluster bootstrap over prompts, 10,000 draws, seed 20261128).
- **Primary endpoint:** E2-H at k = 1 under v2, honest job-level false-rejection rate, pooled over the cards,
  with its 95% cluster-bootstrap interval over prompts.
- **Confirmation criterion:** the v2 result is confirmed if the pooled confirmatory rate is at most 2.0% and
  the upper bound of its 95% cluster-bootstrap interval is at most 3.0%. Otherwise it is reported as not
  confirmed, with the confirmatory value replacing the exploratory one in the paper's claims.
- **Secondary, reported whatever they show:** the same rate per card; E2-H at k = 2, 3, 8; Tier A; E1 under
  v1 and v2; E0 and E0-N; the deployed rule E2-W.
- No job is dropped. A job that fails to generate is reported as missing, not replaced.

## Cost (prices read 2026-11-28 about 11:55 UTC, get-gpu-type; balance US$19.50)

| Card | Price, Secure / Community | Stock at the read | Estimated hours | Estimated cost |
|---|---|---|---|---|
| RTX 4090 | US$0.89 / 0.34 per h | Secure HIGH (EU-RO-1); Community none | about 1.7 | about US$1.50 (Secure) |
| RTX 5090 | US$1.39 / 0.69 per h | none | about 1.3 | about US$1.80 (Secure) |
| RTX 3090 | US$0.50 / 0.22 per h | none | about 2.5 | about US$1.25 (Secure) |

Hours: setup, generation (the test-split runs took 43, 31 and 86 minutes of generation) and the pull of about
4 GB of class O bundles before the pod deletes itself. Total about US$4.5 at Secure prices, within the
US$200 cap. Community is tried first, as before.
