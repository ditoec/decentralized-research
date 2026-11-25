#!/usr/bin/env bash
# WP2 Spark grid (runbook §4 item 1). Runs on the HOST from ~/esj/code; every run is a research
# container started by tools/spark_run.py (runbook §1.1 rules, co-tenant log), one at a time.
#
#   NODE=spark4 ITEMS="ref grid" nohup bash tools/workloads/wp2_spark.sh > ~/esj/logs/wp2.log 2>&1 &
#
# ITEMS  ref    reference config (fp16-sdpa-{euler,dpmpp_2m}-nd), SD1.5 and SDXL, cal + dev (600) x 3 seeds
#               (Sparks 4, 5 and 6)
#        grid   the other configs of precision x attention x sampler x deterministic on prompts_grid200
#               x 3 seeds; SDXL without fp32 (finding 10) (Sparks 4 and 5)
#        l0     a 10 % repeat of the reference config on the same node (REP=02; Spark-4)
#        l2     reference config, SDXL euler, prompts_l2_50 x 3 seeds (all six Sparks; nodes 1-3
#               off-peak and fp16 only)
# Everything keeps full trajectories (Spark jobs are class F). GRID_GLOB filters grid configs by glob
# (e.g. GRID_GLOB='bf16-*') to split the grid across days.
set -euo pipefail
export SPARK=1 MODELS=/models  # paths as the container sees them
source "$(dirname "$0")/wp2_lib.sh"
ITEMS="${ITEMS:-ref}"; MODELS_LIST="${MODELS_LIST:-sd15 sdxl}"; GRID_GLOB="${GRID_GLOB:-*}"
CALDEV=prompts_caldev600.txt
[ -f "$CFG/$CALDEV" ] || { echo "missing $CFG/$CALDEV"; exit 1; }
for m in $MODELS_LIST; do
  for s in euler dpmpp_2m; do
    has ref && gen "$m" "fp16-sdpa-$s-nd" $CALDEV 0,1,2 ref
    if has l0; then
      LIMIT=${L0_LIMIT:-60} REP=02 gen "$m" "fp16-sdpa-$s-nd" $CALDEV 0,1,2 ref "WP2 L0 repeat, 10 %"
    fi
    if has grid; then
      for prec in fp16 bf16 fp32; do
        [ "$m-$prec" = sdxl-fp32 ] && continue
        for attn in sdpa split; do for det in nd det; do
          cfg="$prec-$attn-$s-$det"
          [ "$cfg" = "fp16-sdpa-$s-nd" ] && continue
          [[ $cfg == $GRID_GLOB ]] || continue
          gen "$m" "$cfg" prompts_grid200.txt 0,1,2 grid
        done; done
      done
    fi
  done
done
has l2 && gen sdxl fp16-sdpa-euler-nd prompts_l2_50.txt 0,1,2 l2
echo "wp2 spark workload done on $NODE"
