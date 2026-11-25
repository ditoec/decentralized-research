#!/usr/bin/env bash
# WP2 rented workload (runbook §4 item 2), run inside a RunPod pod by tools/pod_job.sh.
#
#   NODE=rtx5090 MODELS=/work/models ITEMS="ref prec" bash tools/workloads/wp2_rent.sh
#
# ITEMS  ref    reference config, euler and dpmpp_2m, SD1.5 and SDXL, x 3 seeds:
#               prompts_rent_caldev300 (class F) and prompts_rent_test200 (class O; stored, not scored
#               until §6)
#        prec   precision factor on prompts_grid50 x 3 seeds, both samplers: bf16 for both models,
#               fp32 for SD1.5 only (SDXL fp32 is out of the grid, finding 10) (class I)
#        slice  RTX 4090 only: the x86 factor slice at fp16, det {nd, det} x attn {sdpa, split} x
#               {euler, dpmpp_2m} minus the two reference configs, on prompts_grid50 x 3 seeds (class I)
#        l2     the second RTX 5090 (L2): reference config, SDXL, prompts_l2_50 x 3 seeds (class F)
# The pod must be created with POD_RETENTION='*-test-*=O,*-prec-*=I,*-slice-*=I,*=F' and
# POD_DRAW_SEED_SHA256 (trajver.retention newseed) when ITEMS includes ref.
set -euo pipefail
source "$(dirname "$0")/wp2_lib.sh"
ITEMS="${ITEMS:-ref prec}"; MODELS_LIST="${MODELS_LIST:-sd15 sdxl}"
for m in $MODELS_LIST; do
  for s in euler dpmpp_2m; do
    if has ref; then
      gen "$m" "fp16-sdpa-$s-nd" prompts_rent_caldev300.txt 0,1,2 ref-caldev
      gen "$m" "fp16-sdpa-$s-nd" prompts_rent_test200.txt 0,1,2 ref-test
    fi
    if has prec; then
      gen "$m" "bf16-sdpa-$s-nd" prompts_grid50.txt 0,1,2 prec
      [ "$m" = sd15 ] && gen "$m" "fp32-sdpa-$s-nd" prompts_grid50.txt 0,1,2 prec
    fi
    if has slice; then
      for attn in sdpa split; do for det in nd det; do
        [ "$attn-$det" = sdpa-nd ] && continue  # the reference config, already in ref
        gen "$m" "fp16-$attn-$s-$det" prompts_grid50.txt 0,1,2 slice
      done; done
    fi
    if has l2 && [ "$m" = sdxl ] && [ "$s" = euler ]; then
      gen sdxl fp16-sdpa-euler-nd prompts_l2_50.txt 0,1,2 l2
    fi
  done
done
echo "wp2 rented workload done on $NODE"
