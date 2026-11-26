#!/usr/bin/env bash
# P3 throughput on a Spark at a busy hour and in a quiet window (runbook §2, §3 finding 17 "Not done").
# Runs on the HOST from ~/esj/code; each run is a research container via tools/spark_run.py, which
# logs the co-tenants (production containers and the chat model's load) in every job row.
#
#   COND=busy  NODE=spark3 bash tools/workloads/p3_spark.sh   # production serving as usual
#   COND=quiet NODE=spark3 bash tools/workloads/p3_spark.sh   # chat model stopped by the operator
#
# Same command as the pilot's P3 (tools/workloads/pilot.sh): reference flags, prompts_pilot20, seed 0,
# 21 jobs (the first is the warm-up and is excluded), 30 steps, euler; SD1.5 at 512 and SDXL at 1024.
# No trajectories kept (timing only). Busy-hour numbers size the work; only quiet-window numbers may
# be quoted as Spark timing (doc 10 §2.2 rule 4, runbook §1 rule 7).
set -euo pipefail
COND="${COND:?busy or quiet}"; NODE="${NODE:?}"; DATE="${DATE:-$(date -u +%Y%m%d)}"
C=/models/checkpoints; P=../experiments/configs/prompts_pilot20.txt
SD15=$C/v1-5-pruned-emaonly.safetensors; SD15_SHA=6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa
SDXL=$C/sd_xl_base_1.0.safetensors; SDXL_SHA=31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b
run() { local id="$1"; shift; python3 tools/spark_run.py --run-id "$id" -- "$@" || echo "FAILED $id"; }
for m in sd15 sdxl; do
  if [ $m = sd15 ]; then ck=$SD15; sha=$SD15_SHA; res=512; else ck=$SDXL; sha=$SDXL_SHA; res=1024; fi
  id="$DATE-wp0b-p3-$m-$COND-$NODE-01"
  run "$id" python -m trajver.pilot gen --wp wp0b --name "p3-$m-$COND-$NODE" --run-id "$id" --ckpt $ck \
    --ckpt-sha256 $sha --prompts $P --seeds 0 --res $res --steps 30 --sampler euler --limit 21 \
    --purpose "P3: $m throughput on a Spark, $COND (warm; first job excluded)"
done
echo "p3 $COND done on $NODE"
