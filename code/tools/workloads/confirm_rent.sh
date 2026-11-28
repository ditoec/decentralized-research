#!/usr/bin/env bash
# Confirmatory run (docs/16-confirmatory-run.md, pre-registered 2026-11-28, commit 6aa4746), inside a RunPod pod
# by tools/pod_job.sh, or on a Spark host with SPARK=1 for a dry run.
#
#   NODE=rtx4090-03 MODELS=/work/models bash tools/workloads/confirm_rent.sh
#
# Honest jobs only: SDXL, 1024², 30 steps, Euler, the reference configuration (fp16, SDPA, deterministic off),
# exactly as the test-split ref-test runs (tools/workloads/wp2_lib.sh gen), on the 200 never-generated test
# prompts (prompts_confirm200.txt) x seeds 0, 1, 2 = 600 jobs. Trajectories are saved; retention class O.
# The pod must be created with POD_RETENTION='*-confirm-test-*=O' and POD_DRAW_SEED_SHA256.
set -euo pipefail
NODE="${NODE:?set NODE}"; MODELS="${MODELS:-/models}"; LIMIT="${LIMIT:-0}"
DATE="${DATE:-$(date -u +%Y%m%d)}"; REP="${REP:-01}"
CFG=../experiments/configs
SDXL="$MODELS/checkpoints/sd_xl_base_1.0.safetensors"; SDXL_SHA=31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b
id="$DATE-wp3-confirm-test-sdxl-fp16-sdpa-euler-nd-$NODE-$REP"
launch=(); [ "${SPARK:-0}" = 1 ] && launch=(python3 tools/spark_run.py --run-id "$id" --)
"${launch[@]}" python -m trajver.pilot --flags="--force-fp16 --use-pytorch-cross-attention" gen --wp wp3 \
  --name "confirm-test-sdxl-fp16-sdpa-euler-nd-$NODE" --run-id "$id" --ckpt "$SDXL" --ckpt-sha256 "$SDXL_SHA" \
  --prompts "$CFG/prompts_confirm200.txt" --seeds 0,1,2 --res 1024 --steps 30 --sampler euler --save-traj \
  --limit "$LIMIT" --purpose "Confirmatory run (docs/16): honest, untouched test prompts, reference config"
echo "confirmatory workload done on $NODE"
