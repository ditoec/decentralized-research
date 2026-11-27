#!/usr/bin/env bash
# WP3 reduced attack study, Spark side (operator's decision of 2026-11-26; runbook §6). Runs on the HOST
# from ~/esj/code; every GPU process is a research container via tools/spark_run.py.
#
#   ITEMS=rerun  NODE=spark1 bash tools/workloads/wp3_spark.sh
#   ITEMS=sweep  NODE=spark5 SWEEP_S="0.1 0.25" bash tools/workloads/wp3_spark.sh
#   ITEMS=verify NODE=spark3 TH=../experiments/configs/thresholds_v1_sdxl_euler.json RUNS="<run> ..." bash ...
#
# rerun   the verifier's honest re-run of the test job set: SDXL euler reference config on
#         prompts_rent_test200 × seeds 0,1,2 (600 jobs, class F). It is the E0 / E0-N reference for every
#         rented honest test job and every attacked job (the attacked set is its first 100 prompts × seed 0).
# sweep   R2.7 partial faking: F3 at s ∈ SWEEP_S (default 0.1 0.25 0.5 0.75 1.0) on the attacked job set,
#         generated on this Spark with full trajectories (runbook §3.5 rule 6).
# verify  for each run in RUNS: trajver.verify (E1, E2-H at k ∈ {1,2,3,5,8}, E2-W) with the frozen thresholds,
#         and pilot compare --e0-out against the Spark re-run RERUN (E0 and E0-N scores).
set -euo pipefail
ITEMS="${ITEMS:?rerun|sweep|verify}"; NODE="${NODE:?}"; DATE="${DATE:-$(date -u +%Y%m%d)}"; LIMIT="${LIMIT:-100}"
CFG=../experiments/configs; P=$CFG/prompts_rent_test200.txt
SDXL=/models/checkpoints/sd_xl_base_1.0.safetensors; SDXL_SHA=31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b
REF="--force-fp16 --use-pytorch-cross-attention"
has() { [[ " $ITEMS " == *" $1 "* ]]; }
run() { local id=$1; shift; python3 tools/spark_run.py --run-id "$id" ${MARGIN_GB:+--margin-gb "$MARGIN_GB"} -- "$@" || echo "FAILED $id"; }
if has rerun; then
  id="$DATE-wp3-rerun-sdxl-euler-$NODE-01"
  run "$id" python -m trajver.pilot --flags="$REF" gen --wp wp3 --name "rerun-sdxl-euler-$NODE" --run-id "$id" \
    --ckpt $SDXL --ckpt-sha256 $SDXL_SHA --prompts $P --seeds 0,1,2 --res 1024 --steps 30 --sampler euler \
    --save-traj --purpose "WP3 verifier honest re-run of the test job set (E0 reference)"
fi
if has sweep; then
  for s in ${SWEEP_S:-0.1 0.25 0.5 0.75 1.0}; do
    tag=$(printf "s%03d" "$(awk -v s="$s" 'BEGIN{printf "%d", s*100+0.5}')")
    id="$DATE-wp3-sweep-f3-$tag-sdxl-euler-$NODE-01"
    run "$id" python -m trajver.attacks.run --flags="$REF" --wp wp3 --name "sweep-f3-$tag-sdxl-euler-$NODE" \
      --run-id "$id" --attack F3 --s "$s" --ckpt $SDXL --ckpt-sha256 $SDXL_SHA --prompts $P --seeds 0 \
      --limit "$LIMIT" --res 1024 --steps 30 --sampler euler
  done
fi
if has verify; then
  # STEPS orders the work over all RUNS (most important first); two chains with different STEPS can
  # share a node, e.g. STEPS=verify and STEPS="e0 e1img" MARGIN_GB=8 (the light steps beside verify)
  TH="${TH:?frozen thresholds file}"; RERUN="${RERUN:?Spark re-run run id}"
  for step in ${STEPS:-verify e0 e1img}; do
    for src in ${RUNS:?}; do
      short=$(echo "$src" | sed -E 's/^[0-9]{8}-//')
      case $step in
        verify)
          id="$DATE-wp3-verify-$short-on-$NODE"
          run "$id" python -m trajver.verify "/runs/$src" --flags="$REF" --ckpt $SDXL --ckpt-sha256 $SDXL_SHA \
            --prompts $P --thresholds "$TH" --wp wp3 --name "verify-$short-on-$NODE" --run-id "$id" ;;
        e0)
          id="$DATE-wp3-e0-$short-on-$NODE"
          mkdir -p ~/esj/runs/"$id"
          run "$id" sh -c "export TORCH_HOME=/root/.cache/huggingface/torch HF_HUB_OFFLINE=1; python -m trajver.pilot compare /runs/$src \
            /runs/$RERUN --out /runs/$id/compare.json --e0-out /runs/$id/e0.jsonl" ;;
        e1img)  # thresholds_v2 input (docs/ops/2026-11-27-wp3-overnight.md S7b)
          id="$DATE-wp3-e1img-$short-on-$NODE"
          mkdir -p ~/esj/runs/"$id"
          run "$id" python -m trajver.e1img measure "/runs/$src" --ckpt $SDXL --ckpt-sha256 $SDXL_SHA \
            --out "/runs/$id/e1img.jsonl" ;;
      esac
    done
  done
fi
echo "wp3 spark ($ITEMS) done on $NODE"
