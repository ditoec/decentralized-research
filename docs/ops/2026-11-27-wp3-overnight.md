# WP3 overnight procedure (2026-11-26/27, operator asleep)

The operator approved the reduced attack study (plan `plan-for-reduced-attack-keen-stroustrup`, doc 05 §4.2, runbook §6) and asked Claude to carry it through the night to a paper draft. This file is the procedure the overnight checks follow. Every step logs one line in `docs/ops/LOG.md`. The state is read from the nodes each time, never assumed.

Nodes: Spark-N is `aign-dgx@10.41.3.(N+1)`; host details live in `docs/local-nodes.md` (git-ignored). Write `${n}`, never `$n:e`, in zsh. Never print pod tokens, proxy URLs or unrevealed draw seeds.

## S0. Dry run (gate for S4)
- **Where:** chained on Spark-1 after its SDXL euler 4090 replay. The log is `~/esj/logs/wp3-dryrun-spark1.log`; the runs are `*-dryspark1-dry`.
- **Pass when:** the log ends with `fail=0`, and the class O path works:
  - on Spark-1, extract the dry base, F1 and M runs with a throwaway seed (`trajver.retention newseed` / `extract --cls O`);
  - run `trajver.verify` with the pilot thresholds (`experiments/runs/20261124-wp0b-calib-dryrun-01/thresholds_pilot.json`; copy it to the node);
  - the base passes E2-H, F1 fails E2-H, and the rows carry `per_step` and `tau_k`.
- **If it fails:** fix the code, commit it, redeploy `trajver/`, and re-run before S4. Not paper data.

## S1. E0 weights and E0 calibration scores
1. The tar is `~/esj/hfw/e0weights.tar` on Spark-5, with sha256 `b7c4f1c8…76c6`. It holds DINOv2-base and the timm CLIP-384 in the HF cache layout, downloaded on the staging pod because the site cannot reach HF's file servers.
2. Copy it to Sparks 1 and 3 and untar it into `~/esj/hf/`.
3. On Spark-1, re-run `20261126-wp2-e0cal-sdxl-euler-spark1-01` through `spark_run.py` with `TORCH_HOME=/root/.cache/huggingface/torch HF_HUB_OFFLINE=1`: `pilot compare <rented ref-caldev SDXL euler run> /runs/20261125-wp2-ref-sdxl-fp16-sdpa-euler-nd-spark5-01 --out ... --e0-out .../e0-<card>.jsonl` for rtx4090-02, rtx3090-01 and rtx5090-01. Copy the 5090 run there when it is home.

## S2. Staging cleanup
When every WP2 tag is released, the staging pod `twazk132j21s05` deletes itself. Then delete the network volume `xgzm7eis58` (created by this work; about 120 GB) and confirm with `list-network-volumes`. The WP3 pull goes straight to Spark-5.

## S3. Freeze (gate for S4)
- **When:** the three SDXL euler replays have `summary.json`: `20261126-wp2-replay-cal-sdxl-euler-rtx4090-02on-spark1-01`, `...-rtx3090-01on-spark3-01` and `20261126-wp2-replay-cal-sdxl-euler-rtx5090-01on-spark1-01` (moved to Spark-1 at 17:17 UTC, which is faster), together with the three E0 files.
- **Steps:**
  1. Fetch their metadata (`jobs.jsonl`, `manifest.json`, `summary.json`, E0 files) into `experiments/runs/`, then `sanitize_runs.py` and `--check`.
  2. Filter the E0 rows to calibration prompt ids (`trajver.calibrate.calibration_ids()`).
  3. Run on the Mac (`code/.venv`), from `code/`:
     `python -m trajver.calibrate --replay <3 replay dirs> --e0 <3 filtered files> --p1 ../experiments/runs/20261124-wp0b-p1-noise-*/noisecmp_*.json --metric rel_l2 --levels L3,L4 --out ../experiments/configs/thresholds_v1_sdxl_euler.json`
- **If calibrate refuses** (P1 tolerance, mixed samplers, non-cal rows): stop and log it. Never edit the rules to make it pass.
- **Commit and push** the thresholds file before any S4 step; the commit time is the evidence. Then copy it to `~/esj/experiments/configs/` on Sparks 1, 3, 5 and 6.

## S4. RTX 5090 attacks (only after S0 and S3)
1. **Balance:** read `get-balance`. Need at least US$5. If it is lower, stop and log; the operator tops up.
2. **New draw seed on Spark-5:** `python3 -m trajver.retention newseed ~/esj/secret/wp3-rtx5090.hex` (mode 600). Record only its sha256.
3. **Create the pod** as in WP2:
   - image `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`, GPU `NVIDIA GeForce RTX 5090`, `minCudaVersion` 12.8, disk 100, ports `8000/http`;
   - env: `POD_TOKEN` (random, kept on Spark-5 only), `POD_HOURLY_USD`, `POD_CLOUD`, `POD_RETENTION='*-wp3-base-*=O,*-wp3-atk-*=O,*=F'`, `POD_DRAW_SEED_SHA256`;
   - Community first (about US$0.69/h), then Secure (about US$1.39/h); log the price before creating;
   - read the stock first, and retry on a 400.

   The WP2 creates are recorded in the session transcript and the runbook §4 records.
4. **Start the pod:**
   - `pod_server.py` via `exec-pod`;
   - PUT `code.tar.gz` (code + experiments/configs, with the frozen thresholds);
   - `nohup bash /work/code/tools/pod_job.sh tools/workloads/wp3_rent.sh` with `NODE=rtx5090 MODELS=/work/models`;
   - install `pod_selfstop.sh`.
4b. **No RTX 5090 stock (fallback rule, decided 20:40 UTC 2026-11-26 while the operator sleeps):**
   - retry the RTX 5090 at every check until **22:30 UTC**, Community first, then Secure;
   - then rent an **RTX 3090** instead, with the same workload and `NODE=rtx3090`. The RTX 3090 is the runbook §6 design's other rented provider, its honest test runs are home, and the frozen thresholds cover its calibration pair (L4);
   - doc 05 §4.2, runbook §6 and Methods then name the provider actually used.
5. **On Spark-5:** `pull_run.py <base> --wait --reveal-seed ~/esj/secret/wp3-rtx5090.hex` and `release_pod.py`, as in WP2. The pod deletes itself after a verified pull. Watch out for a faulty host (CUDA unknown error): terminate it at once and retry elsewhere.

## S5. Spark honest re-run (E0 reference)
- Chained on Spark-3 after its SDXL euler 3090 replay (17:18 UTC): `ITEMS=rerun NODE=spark3 bash tools/workloads/wp3_spark.sh` (log `~/esj/logs/wp3-rerun-spark3.log`), then the SD1.5/dpmpp_2m replays resume.
- 600 jobs, about 2.2 h. The run is `<date>-wp3-rerun-sdxl-euler-spark3-01`.

## S6. F3 sweep
After the grid finishes on Spark-5/6 (no `research=esj` container left):
- deploy `trajver/` and `wp3_spark.sh`;
- `ITEMS=sweep NODE=spark5 SWEEP_S="0.1 0.25 0.5"` and `NODE=spark6 SWEEP_S="0.75 1.0"`.

## S7. Verify
On Spark-3 (where the re-run is), copy over from Spark-5:
- the pulled WP3 runs;
- the rented honest test runs `*-wp2-ref-test-sdxl-fp16-sdpa-euler-nd-{rtx5090-01,rtx4090-02,rtx3090-01}`.

Run `ITEMS=verify NODE=spark3 TH=../experiments/configs/thresholds_v1_sdxl_euler.json RERUN=<rerun id> RUNS="<runs>"`. Verify the sweep runs where they are; E2-H only is enough for R2.7, so `compare` there may fail harmlessly.

## S8. Analysis and paper
1. Fetch the verify outputs, the pod timing metadata and the sweep metadata; sanitize them.
2. `python -m trajver.analysis_wp3 ... --baseline <base run>` writes the R2 tables and `fig_r2_7_partial.csv`.
3. `trajver.montecarlo` with the measured rates writes `fig_r3_6_deterrence.csv`.
4. Write Results RQ2/RQ3, Discussion and Limitations in `paper/tools/build_esj_docx.py`, using only logged numbers. Rebuild the docx and PDF (LibreOffice). Update doc 12.
5. Commit, push and open a PR.

## Standing rules
- **Costs:** US$200 cap, RunPod only, and log every pod's price. The WP5 Devnet run is a separate session.
- **Spark memory:** 15 GB floor. Production containers may be stopped only through `replay_sweep.sh`'s rule (stop, never pause; never Wazuh; trap restore; logged).
- **Thresholds:** never change them after attack data exists (any change is v2).
- **Numbers:** never invent one. A missing result stays a placeholder.
