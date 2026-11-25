#!/usr/bin/env bash
# WP2 Spark grid (runbook §4 item 1). Runs on the HOST from ~/esj/code; every run is a research
# container started by tools/spark_run.py (runbook §1.1 rules, co-tenant log), one at a time.
#
#   NODE=spark4 ITEMS="ref grid" nohup bash tools/workloads/wp2_spark.sh > ~/esj/logs/wp2.log 2>&1 &
#
# ITEMS  ref    reference config (fp16-sdpa-{euler,dpmpp_2m}-nd), SD1.5 and SDXL, cal + dev (600) x 3 seeds
#               (Sparks 4, 5 and 6)
#        grid   the other configs of precision x attention x sampler x deterministic on prompts_grid200
#               x 3 seeds; SDXL without fp32 (finding 10) (Sparks 4 and 5). Class O (decision of
#               2026-11-25, finding 18: storage): needs GRID_SEED_FILE, the study's grid draw seed
#               (trajver.retention newseed, mode 600, the SAME file on Spark-4 and Spark-5, so a job opens
#               the same steps in every config and on both nodes). Its hash goes into each run's manifest
#               before generation; the seed is mounted only into the extraction container, after the run.
#        l0     a 10 % repeat of the reference config on the same node (REP=02; Spark-4)
#        l2     reference config, SDXL euler, prompts_l2_50 x 3 seeds (all six Sparks; nodes 1-3
#               off-peak and fp16 only)
# ref, l0 and l2 keep full trajectories (class F). GRID_GLOB filters grid configs by glob
# (e.g. GRID_GLOB='bf16-*') to split the grid across days.
set -euo pipefail
export SPARK=1 MODELS=/models  # paths as the container sees them
source "$(dirname "$0")/wp2_lib.sh"
ITEMS="${ITEMS:-ref}"; MODELS_LIST="${MODELS_LIST:-sd15 sdxl}"; GRID_GLOB="${GRID_GLOB:-*}"
CALDEV=prompts_caldev600.txt
if has grid; then
  [ -r "${GRID_SEED_FILE:-}" ] || { echo "grid needs GRID_SEED_FILE (the grid draw seed)"; exit 1; }
  GRID_SEED_SHA256=$(python3 -c "import hashlib,sys;print(hashlib.sha256(bytes.fromhex(open(sys.argv[1]).read().strip())).hexdigest())" "$GRID_SEED_FILE")
  echo "grid draw seed sha256 $GRID_SEED_SHA256"
fi
extract_o() {  # class O for a finished grid run: Tier A on all steps, bundles, delete full trajectories
  python3 tools/spark_run.py --run-id "$1" --secret "$GRID_SEED_FILE" -- \
    sh -c "python -m trajver.retention extract /runs/$1 --cls O --seed-file /secret/draw_seed.hex && python -m trajver.retention check /runs/$1" \
    || echo "FAILED extract $1"
}
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
          TRAJVER_DRAW_SEED_SHA256="$GRID_SEED_SHA256" gen "$m" "$cfg" prompts_grid200.txt 0,1,2 grid
          extract_o "$DATE-wp2-grid-$m-$cfg-$NODE-$REP"
        done; done
      done
    fi
  done
done
has l2 && gen sdxl fp16-sdpa-euler-nd prompts_l2_50.txt 0,1,2 l2
echo "wp2 spark workload done on $NODE"
