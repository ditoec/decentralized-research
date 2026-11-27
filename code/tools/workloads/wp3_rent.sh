#!/usr/bin/env bash
# WP3 reduced attack study (operator's decision of 2026-11-26; runbook §6), run inside a RunPod pod by
# tools/pod_job.sh, or on a Spark host with SPARK=1 for a dry run.
#
#   NODE=rtx5090 MODELS=/work/models bash tools/workloads/wp3_rent.sh
#
# Scope: SDXL, 1024², 30 steps, euler, reference config (fp16, SDPA, not deterministic), test split.
# Job set: the first LIMIT (default 100) prompts of prompts_rent_test200.txt × seed 0, the same jobs in
# every run, so attacked and honest jobs pair one to one (β_A timing; E0 against the verifier's re-run).
#   base           honest baseline on the job set (timing for β_A; honest class-O jobs)
#   atk-<attack>   A1b (20 of 30 steps), A2 (fp8 UNet), A3 Turbo (4 steps), A3 LCM-LoRA (6 steps),
#                  F1, F2, F3 (s = 0.5), A8 (unrelated output, control), M (falsified metadata, control)
#   cost-replay    verifier cost (R3.1): all-steps Tier B replay of the first COST_N (default 50) baseline
#                  jobs on this card, run before extraction while the baseline is still class F
# The pod must be created with POD_RETENTION='*-wp3-base-*=O,*-wp3-atk-*=O,*=F' and POD_DRAW_SEED_SHA256
# (trajver.retention newseed). The attack code never sees the draw seed: it arrives after generation.
set -euo pipefail
NODE="${NODE:?set NODE}"; MODELS="${MODELS:-/models}"; LIMIT="${LIMIT:-100}"; COST_N="${COST_N:-50}"
DATE="${DATE:-$(date -u +%Y%m%d)}"; REP="${REP:-01}"
CFG=../experiments/configs; P=$CFG/prompts_rent_test200.txt
SDXL="$MODELS/checkpoints/sd_xl_base_1.0.safetensors"; SDXL_SHA=31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b
TURBO="$MODELS/checkpoints/sd_xl_turbo_1.0_fp16.safetensors"; LCM="$MODELS/loras/lcm-lora-sdxl.safetensors"
REF="--force-fp16 --use-pytorch-cross-attention"
COMMON=(--ckpt "$SDXL" --ckpt-sha256 "$SDXL_SHA" --prompts "$P" --seeds 0 --limit "$LIMIT" --res 1024 --steps 30
        --sampler euler)
launch() { local id=$1; shift; if [ "${SPARK:-0}" = 1 ]; then python3 tools/spark_run.py --run-id "$id" --margin-gb "${MARGIN_GB:-20}" -- "$@"; else "$@"; fi; }
fail=0
id="$DATE-wp3-base-sdxl-euler-$NODE-$REP"
launch "$id" python -m trajver.pilot --flags="$REF" gen --wp wp3 --name "base-sdxl-euler-$NODE" --run-id "$id" \
  "${COMMON[@]}" --save-traj --purpose "WP3 honest baseline on the attacked job set (β_A timing)" || { echo "FAILED $id"; fail=1; }
atk() {  # atk TAG FLAGS ATTACK-ARGS...
  local tag=$1 flags=$2; shift 2
  local id="$DATE-wp3-atk-$tag-sdxl-euler-$NODE-$REP"
  launch "$id" python -m trajver.attacks.run --flags="$flags" --wp wp3 --name "atk-$tag-sdxl-euler-$NODE" --run-id "$id" \
    "${COMMON[@]}" "$@" || { echo "FAILED $id"; fail=1; }
}
atk a1b      "$REF" --attack A1b --run-steps 20
atk a2       "--fp8_e4m3fn-unet --use-pytorch-cross-attention" --attack A2
atk a3turbo  "$REF" --attack A3 --cheap-ckpt "$TURBO" --run-steps 4 --run-cfg 1.0
atk a3lcm    "$REF" --attack A3 --lora "$LCM" --run-steps 6 --run-cfg 1.5
atk f1       "$REF" --attack F1 --s 0.5
atk f2       "$REF" --attack F2 --s 0.5
atk f3       "$REF" --attack F3 --s 0.5
atk a8       "$REF" --attack A8
atk m        "$REF" --attack M
base="$DATE-wp3-base-sdxl-euler-$NODE-$REP"; root="${TRAJVER_RUNS:-/runs}"
id="$DATE-wp3-cost-replay-sdxl-euler-$NODE-$REP"
launch "$id" python -m trajver.pilot --flags="$REF" replay --wp wp3 --name "cost-replay-sdxl-euler-$NODE" --run-id "$id" \
  --provider-run "$root/$base" --ckpt "$SDXL" --ckpt-sha256 "$SDXL_SHA" --prompts "$P" --res 1024 --steps 30 \
  --limit "$COST_N" || { echo "FAILED $id"; fail=1; }
echo "wp3 rented workload done on $NODE (fail=$fail)"
exit $fail
