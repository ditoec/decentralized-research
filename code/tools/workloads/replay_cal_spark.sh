#!/usr/bin/env bash
# WP2 calibration inputs (runbook §5 item 2): Tier B / Tier A replay on a Spark verifier of the rented
# providers' class-F reference runs, calibration split only (prompts_cal.txt; pilot replay skips every
# other prompt). Runs on the HOST from ~/esj/code; each replay is a research container via
# tools/spark_run.py (memory and disk guard). Resumable: a rerun with the same run id skips done jobs.
#
#   NODE=spark1 RUNS="<provider run> ..." bash tools/workloads/replay_cal_spark.sh
#   AFTER_PID=<pid> waits for that process (an earlier queue or replay) to exit first.
#
# A provider run is used only once its folder has summary.json (copy complete); the script waits for it,
# so runs can be copied in while earlier replays are going. Same reference flags as the provider
# (--force-fp16 --use-pytorch-cross-attention). This is an input to the freeze, not the freeze itself.
set -euo pipefail
NODE="${NODE:?}"; RUNS="${RUNS:?}"; DATE="${DATE:-$(date -u +%Y%m%d)}"
C=/models/checkpoints; P=../experiments/configs/prompts_cal.txt
SD15=$C/v1-5-pruned-emaonly.safetensors; SD15_SHA=6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa
SDXL=$C/sd_xl_base_1.0.safetensors; SDXL_SHA=31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b
if [ -n "${AFTER_PID:-}" ]; then while kill -0 "$AFTER_PID" 2>/dev/null; do sleep 60; done; fi
for src in $RUNS; do
  until [ -f ~/esj/runs/"$src"/summary.json ]; do sleep 60; done
  case "$src" in *-sd15-*) m=sd15; ck=$SD15; sha=$SD15_SHA; res=512;; *) m=sdxl; ck=$SDXL; sha=$SDXL_SHA; res=1024;; esac
  case "$src" in *-dpmpp_2m-*) s=dpmpp_2m;; *) s=euler;; esac
  hw=$(echo "$src" | sed -E 's/.*-(rtx[0-9]+[a-z]?)-([0-9]+)$/\1-\2/')
  id="$DATE-wp2-replay-cal-$m-$s-${hw}on-$NODE-01"
  # On the GB10's unified memory, CUDA context creation can fail with out-of-memory while page cache
  # (e.g. from a just-copied provider run) is high, although MemAvailable is fine (2026-11-26, Spark-1).
  # The replay resumes by run id, so a failed attempt is retried after a pause.
  for try in $(seq 1 "${RETRIES:-3}"); do
    if python3 tools/spark_run.py --run-id "$id" -- python -m trajver.pilot \
      --flags="--force-fp16 --use-pytorch-cross-attention" replay --wp wp2 --name "replay-cal-$m-$s-${hw}on-$NODE" \
      --run-id "$id" --provider-run "/runs/$src" --ckpt $ck --ckpt-sha256 $sha --prompts $P --res $res --steps 30 \
      --sampler $s; then break; fi
    echo "FAILED $id (attempt $try)"; sleep "${RETRY_WAIT:-300}"
  done
done
echo "replay-cal done on $NODE"
