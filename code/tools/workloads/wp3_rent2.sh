#!/usr/bin/env bash
# WP3 second rented session (doc 14 items 1 and 2a, 2026-11-27): realistic forgers and beta_A on one timer.
# Run inside a RunPod pod by tools/pod_job.sh, or on a Spark host with SPARK=1 for a dry run.
#
#   NODE=rtx5090 MODELS=/work/models bash tools/workloads/wp3_rent2.sh
#
# Same scope and job set as wp3_rent.sh (SDXL, 1024², 30 steps, Euler, reference config, test split, the first
# prompts of prompts_rent_test200.txt × seed 0).
#   atkr-f1..f3   F1-F3 with the realistic forger (forgeries.realistic_euler: the model runs only at computed
#                 steps, from the forger's own states), s = 0.5, LIMIT jobs (default 100), class O for verification;
#                 --pair-honest gives beta_A on one timer
#   time-<tag>    beta_A re-timing (doc 14 item 1), LIMIT_T jobs (default 50), class I (timing only):
#                 A1b, A3 Turbo, A3 LCM-LoRA, A8 and M with --pair-honest (honest generation of the same job in
#                 the same process, alternating order); A2 (fp8 flags apply to the whole process) against
#                 timebase, a pilot gen run on this card timed on the same field (t_sample_s)
# The pod must be created with POD_RETENTION='*-wp3-atkr-*=O,*=I' and POD_DRAW_SEED_SHA256.
set -euo pipefail
NODE="${NODE:?set NODE}"; MODELS="${MODELS:-/models}"; LIMIT="${LIMIT:-100}"; LIMIT_T="${LIMIT_T:-50}"
DATE="${DATE:-$(date -u +%Y%m%d)}"; REP="${REP:-01}"
CFG=../experiments/configs; P=$CFG/prompts_rent_test200.txt
SDXL="$MODELS/checkpoints/sd_xl_base_1.0.safetensors"; SDXL_SHA=31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b
TURBO="$MODELS/checkpoints/sd_xl_turbo_1.0_fp16.safetensors"; LCM="$MODELS/loras/lcm-lora-sdxl.safetensors"
REF="--force-fp16 --use-pytorch-cross-attention"
COMMON=(--ckpt "$SDXL" --ckpt-sha256 "$SDXL_SHA" --prompts "$P" --seeds 0 --res 1024 --steps 30 --sampler euler)
launch() { local id=$1; shift; if [ "${SPARK:-0}" = 1 ]; then python3 tools/spark_run.py --run-id "$id" --margin-gb "${MARGIN_GB:-20}" -- "$@"; else "$@"; fi; }
fail=0
run_atk() {  # run_atk PREFIX TAG LIMIT FLAGS ATTACK-ARGS...
  local pre=$1 tag=$2 lim=$3 flags=$4; shift 4
  local id="$DATE-wp3-$pre-$tag-sdxl-euler-$NODE-$REP"
  launch "$id" python -m trajver.attacks.run --flags="$flags" --wp wp3 --name "$pre-$tag-sdxl-euler-$NODE" --run-id "$id" \
    "${COMMON[@]}" --limit "$lim" "$@" || { echo "FAILED $id"; fail=1; }
}
for f in F1 F2 F3; do
  run_atk atkr "$(echo $f | tr A-Z a-z)" "$LIMIT" "$REF" --attack "$f" --s 0.5 --forger realistic --pair-honest
done
id="$DATE-wp3-timebase-sdxl-euler-$NODE-$REP"
launch "$id" python -m trajver.pilot --flags="$REF" gen --wp wp3 --name "timebase-sdxl-euler-$NODE" --run-id "$id" \
  "${COMMON[@]}" --limit "$LIMIT_T" --save-traj --purpose "WP3 beta_A re-timing: honest baseline for A2 (t_sample_s)" \
  || { echo "FAILED $id"; fail=1; }
run_atk time a2      "$LIMIT_T" "--fp8_e4m3fn-unet --use-pytorch-cross-attention" --attack A2
run_atk time a1b     "$LIMIT_T" "$REF" --attack A1b --run-steps 20 --pair-honest
run_atk time a3turbo "$LIMIT_T" "$REF" --attack A3 --cheap-ckpt "$TURBO" --run-steps 4 --run-cfg 1.0 --pair-honest
run_atk time a3lcm   "$LIMIT_T" "$REF" --attack A3 --lora "$LCM" --run-steps 6 --run-cfg 1.5 --pair-honest
run_atk time a8      "$LIMIT_T" "$REF" --attack A8 --pair-honest
run_atk time m       "$LIMIT_T" "$REF" --attack M --pair-honest
echo "wp3 second rented workload done on $NODE (fail=$fail)"
exit $fail
