#!/usr/bin/env bash
# Pilot leftovers on the Sparks (runbook §3 finding 17). Runs on the HOST from ~/esj/code; every GPU
# process is a research container via tools/spark_run.py (one at a time per node).
#
#   ROLE=provider NODE=spark4 bash tools/workloads/leftovers_spark.sh   # Spark-4
#   ROLE=verifier NODE=spark5 bash tools/workloads/leftovers_spark.sh   # Spark-5
#
# provider: SDXL dpmpp_2m honest run (40 jobs, trajectories kept); attacked jobs on 10 calibration
#           prompts: A1b (20 of 30 steps), A3 SDXL-Turbo (4 steps), A3 LCM-LoRA (6 steps), F1-F3 (s = 0.5).
# verifier: SDXL dpmpp_2m honest run; then, once the provider's runs are copied over, Tier A/B replay
#           of the provider's dpmpp_2m run and `trajver.verify` of every attacked run and of the honest
#           RTX 5090 run, with the dry-run thresholds (NOT frozen; a smoke test of the pipeline, not paper data).
set -euo pipefail
ROLE="${ROLE:?}"; NODE="${NODE:?}"; DATE="${DATE:-20261124}"
C=/models/checkpoints; SDXL=$C/sd_xl_base_1.0.safetensors
SHA=31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b
P=../experiments/configs/prompts_pilot20.txt
run() { local id="$1"; shift; python3 tools/spark_run.py --run-id "$id" -- "$@" || echo "FAILED $id"; }
gen_dpm() {
  local id="$DATE-wp0b-p2-sdxl-dpmpp-$NODE-01"
  run "$id" python -m trajver.pilot gen --name "p2-sdxl-dpmpp-$NODE" --run-id "$id" --ckpt $SDXL --ckpt-sha256 $SHA \
    --prompts $P --seeds 0,1 --res 1024 --steps 30 --sampler dpmpp_2m --save-traj --purpose "P2: second sampler (dpmpp_2m), SDXL"
}
atk() {  # $1 tag, rest: attack args
  local tag="$1"; shift; local id="$DATE-wp0b-atk-$tag-$NODE-01"
  run "$id" python -m trajver.attacks.run --wp wp0b --name "atk-$tag-$NODE" --run-id "$id" --ckpt $SDXL --ckpt-sha256 $SHA \
    --prompts $P --seeds 0 --limit 10 --res 1024 --steps 30 "$@"
}
if [ "$ROLE" = provider ]; then
  gen_dpm
  atk a1b --attack A1b --run-steps 20
  atk a3-turbo --attack A3 --cheap-ckpt $C/sd_xl_turbo_1.0_fp16.safetensors --run-steps 4 --run-cfg 1.0
  atk a3-lcm --attack A3 --lora /models/loras/lcm-lora-sdxl.safetensors --run-steps 6 --run-cfg 1.5
  for f in F1 F2 F3; do atk "$(echo $f | tr F f)" --attack $f --s 0.5; done
  echo PROVIDER-DONE
else
  gen_dpm
  until [ -f ~/esj/runs/PROVIDER-COPIED ]; do sleep 30; done
  id="$DATE-wp0b-replay-dpmpp-spark4on-$NODE-01"
  run "$id" python -m trajver.pilot replay --name replay-dpmpp-spark4on-$NODE --run-id "$id" \
    --provider-run "/runs/$DATE-wp0b-p2-sdxl-dpmpp-spark4-01" --ckpt $SDXL --ckpt-sha256 $SHA --prompts $P --res 1024 --steps 30
  TH=/runs/$DATE-wp0b-calib-dryrun-01/thresholds_pilot.json
  for src in atk-a1b atk-a3-turbo atk-a3-lcm atk-f1 atk-f2 atk-f3; do
    s="$DATE-wp0b-$src-spark4-01"; id="$DATE-wp0b-verify-$src-on-$NODE-01"
    run "$id" python -m trajver.verify "/runs/$s" --ckpt $SDXL --ckpt-sha256 $SHA --prompts $P --thresholds $TH \
      --wp wp0b --name "verify-$src-on-$NODE" --run-id "$id"
  done
  id="$DATE-wp0b-verify-honest-rtx5090-on-$NODE-01"
  run "$id" python -m trajver.verify "/runs/$DATE-wp0b-p2-sdxl-rtx5090-01" --ckpt $SDXL --ckpt-sha256 $SHA --prompts $P \
    --thresholds $TH --limit 20 --wp wp0b --name "verify-honest-rtx5090-on-$NODE" --run-id "$id"
  echo VERIFIER-DONE
fi
