#!/usr/bin/env bash
# P6 co-tenancy on a Spark (runbook §2). Runs on the HOST from ~/esj/code with host python3;
# every GPU process is a research container started by tools/spark_run.py.
#
#   NODE=spark4 DATE=20261124 nohup bash tools/workloads/p6_spark.sh > ~/esj/p6.log 2>&1 &
#
# Four conditions, 50 SDXL jobs each (pilot20 prompts x seeds 0-2, first 50), trajectories kept:
#   idle-pin    reference: no research load, batching pinned
#   load-pin    beside tools/gpu_load.py (holds LOAD_GB, fp16 matmuls), batching pinned
#   load-nopin  same load, ComfyUI's memory-adaptive batching left on (--no-pin)
#   idle-nopin  no research load, --no-pin
# Production load (the chat model's running requests) is logged in every job row, never driven.
# Compare each condition with idle-pin by `pilot compare` (bit-identity of every trajectory).
set -euo pipefail
NODE="${NODE:?}"; DATE="${DATE:-$(date -u +%Y%m%d)}"; LOAD_GB="${LOAD_GB:-6}"
SDXL=/models/checkpoints/sd_xl_base_1.0.safetensors
SHA=31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b
rid() { echo "$DATE-wp0b-p6-$1-$NODE-01"; }

gen() {  # $1 condition, $2 extra flag
  python3 tools/spark_run.py --run-id "$(rid "$1")" -- python -m trajver.pilot gen --name "p6-$1-$NODE" \
    --run-id "$(rid "$1")" --ckpt "$SDXL" --ckpt-sha256 $SHA --prompts ../experiments/configs/prompts_pilot20.txt \
    --seeds 0,1,2 --limit 50 --res 1024 --steps 30 --sampler euler --save-traj $2 \
    --purpose "P6 co-tenancy: $1"
}
with_load() {  # $1 condition, $2 extra flag
  local lid; lid="$(rid "$1")-load"
  python3 tools/spark_run.py --run-id "$lid" --margin-gb 0 -- python tools/gpu_load.py --seconds 3600 --hold-gb "$LOAD_GB" &
  local lp=$!
  sleep 90  # let the load reach steady state
  gen "$1" "$2" || echo "P6 $1 FAILED"
  docker stop "esj-$lid" >/dev/null 2>&1 || true
  wait $lp || true
}

gen idle-pin ""
with_load load-pin ""
with_load load-nopin "--no-pin"
gen idle-nopin "--no-pin"

for c in load-pin load-nopin idle-nopin; do
  python3 tools/spark_run.py --run-id "$(rid "$c")-cmp" -- python -m trajver.pilot compare \
    "/runs/$(rid idle-pin)" "/runs/$(rid "$c")" --steps-detail --out "/runs/$(rid "$c")/compare_vs_idle-pin.json" \
    || echo "compare $c FAILED"
done
echo "P6 done on $NODE"
