#!/usr/bin/env bash
# Pilot WP0b workload (runbook §2), the same on every node. Runs from code/ with the venv's python
# on PATH, TRAJVER_RUNS set, and models under $MODELS.
#
#   NODE=rtx5080 MODELS=/work/models ITEMS="p1 p2 p3 p4 p5" bash tools/workloads/pilot.sh
#
# NODE    short node tag used in run names (spark4, spark5, rtx5080, rtx4090, rtx3090, ...)
# ITEMS   which pilot items to run (default: all that apply to the node)
# DATE    run-id date prefix (default: today, UTC)
set -euo pipefail
NODE="${NODE:?set NODE}"; MODELS="${MODELS:-/models}"; ITEMS="${ITEMS:-p1 p2 p3 p4 p5}"
DATE="${DATE:-$(date -u +%Y%m%d)}"
CFG=../experiments/configs
SD15="$MODELS/checkpoints/v1-5-pruned-emaonly.safetensors"; SD15_SHA=6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa
SDXL="$MODELS/checkpoints/sd_xl_base_1.0.safetensors"; SDXL_SHA=31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b
P="python -m trajver.pilot"
has() { [[ " $ITEMS " == *" $1 "* ]]; }
rid() { echo "$DATE-wp0b-$1-$NODE-${2:-01}"; }

has p1 && $P noise --name "p1-noise-$NODE" --run-id "$(rid p1-noise)" --seeds 100
if has p2; then  # SDXL, 30 steps, euler, fp16 default flags, 20 cal prompts x 2 seeds, trajectories kept
  $P gen --name "p2-sdxl-$NODE" --run-id "$(rid p2-sdxl "${P2_REP:-01}")" --ckpt "$SDXL" --ckpt-sha256 $SDXL_SHA \
     --prompts $CFG/prompts_pilot20.txt --seeds 0,1 --res 1024 --steps 30 --sampler euler --save-traj \
     --purpose "P2: first look at L0-L4 (SDXL, fp16 default flags)"
fi
if has p3; then  # SD1.5 throughput, n=20 (+1 warm-up); SDXL throughput comes from P2's timings
  $P gen --name "p3-sd15-$NODE" --run-id "$(rid p3-sd15)" --ckpt "$SD15" --ckpt-sha256 $SD15_SHA \
     --prompts $CFG/prompts_pilot20.txt --seeds 0 --res 512 --steps 30 --sampler euler --limit 21 \
     --purpose "P3: SD1.5 throughput (warm)"
fi
if has p4; then  # fp8 attack feasibility and speed vs fp16 (P2/P3 are the fp16 reference); NVFP4 probe
  $P --flags=--fp8_e4m3fn-unet gen --name "p4-fp8-sdxl-$NODE" --run-id "$(rid p4-fp8-sdxl)" --ckpt "$SDXL" \
     --ckpt-sha256 $SDXL_SHA --prompts $CFG/prompts_pilot20.txt --seeds 0 --res 1024 --limit 11 \
     --purpose "P4: fp8_e4m3fn UNet (attack A2) on SDXL" || echo "P4 fp8 FAILED"
  $P fp4 --name "p4-fp4-$NODE" --run-id "$(rid p4-fp4)" || echo "P4 fp4 probe FAILED"
fi
if has p5; then  # hypothesis W1 on SDXL, 10 cal prompts
  $P w1 --name "p5-w1-$NODE" --run-id "$(rid p5-w1)" --ckpt "$SDXL" --ckpt-sha256 $SDXL_SHA \
     --prompts $CFG/prompts_pilot20.txt --n 10 --res 1024 --steps 30
fi
if has p7; then  # memory footprint per precision (P7): SD1.5 and SDXL, fp16 / bf16 / fp32
  # P7_SKIP lists model-precision pairs not to run, e.g. "sdxl-fp32" on a Spark beside production:
  # the 2026-11-24 test took host free memory from ~49 GB to 5.9 GB (runbook §3 finding 10).
  for prec in fp16:--force-fp16 bf16:--bf16-unet fp32:--force-fp32; do
    tag=${prec%%:*}; flag=${prec#*:}
    for m in sd15 sdxl; do
      [[ " ${P7_SKIP:-} " == *" $m-$tag "* ]] && { echo "skip P7 $m-$tag"; continue; }
      ck=$SD15; sha=$SD15_SHA; res=512; [ $m = sdxl ] && ck=$SDXL && sha=$SDXL_SHA && res=1024
      $P --flags=$flag gen --name "p7-$m-$tag-$NODE" --run-id "$(rid p7-$m-$tag "${P7_REP:-01}")" --ckpt "$ck" --ckpt-sha256 $sha \
         --prompts $CFG/prompts_pilot20.txt --seeds 0 --res $res --limit 3 --purpose "P7: memory footprint" \
         || echo "P7 $m $tag FAILED"
    done
  done
fi
echo "pilot workload done on $NODE"
