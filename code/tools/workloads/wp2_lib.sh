# Shared by the WP2 (RQ1) workloads (runbook §4). Sourced, not run. Expects, from code/:
#   NODE (run-name tag), MODELS (dir with checkpoints/), optional LIMIT (prompts per run, x 3 seeds: dry runs),
#   optional DATE (run-id prefix, default today UTC), optional REP (run-id suffix, default 01).
#
# A config is "<prec>-<attn>-<sampler>-<det>":
#   prec    fp16 (--force-fp16) | bf16 (--bf16-unet) | fp32 (--force-fp32)       (as pilot P7)
#   attn    sdpa (--use-pytorch-cross-attention) | split (--use-split-cross-attention)
#           (the runbook's "split or quad" factor level: split is the one used)
#   sampler euler | dpmpp_2m
#   det     nd (off) | det (--deterministic)
# The reference config is fp16-sdpa-<sampler>-nd.
#
# Run names carry the retention class for tools/pod_job.sh's POD_RETENTION map (runbook §3.5):
#   ...-test-...  class O     ...-prec-... / ...-slice-...  class I     anything else  class F
NODE="${NODE:?set NODE}"; MODELS="${MODELS:-/models}"; LIMIT="${LIMIT:-0}"
DATE="${DATE:-$(date -u +%Y%m%d)}"; REP="${REP:-01}"
CFG=../experiments/configs
SD15="$MODELS/checkpoints/v1-5-pruned-emaonly.safetensors"; SD15_SHA=6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa
SDXL="$MODELS/checkpoints/sd_xl_base_1.0.safetensors"; SDXL_SHA=31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b
RETENTION_MAP='*-test-*=O,*-prec-*=I,*-slice-*=I,*=F'
has() { [[ " $ITEMS " == *" $1 "* ]]; }

flags_of() {  # config tag -> ComfyUI flags
  local prec attn sampler det f=""
  IFS=- read -r prec attn sampler det <<<"${1/dpmpp_2m/dpmpp2m}"
  case $prec in fp16) f="--force-fp16";; bf16) f="--bf16-unet";; fp32) f="--force-fp32";; *) echo "bad prec $prec" >&2; return 1;; esac
  case $attn in sdpa) f="$f --use-pytorch-cross-attention";; split) f="$f --use-split-cross-attention";; *) echo "bad attn $attn" >&2; return 1;; esac
  case $det in nd) ;; det) f="$f --deterministic";; *) echo "bad det $det" >&2; return 1;; esac
  echo "$f"
}
sampler_of() { local s; s=$(cut -d- -f3 <<<"$1"); echo "$s"; }

# gen MODEL CONFIG PROMPTS SEEDS PART [PURPOSE]: one run, trajectories kept, resumable by run id
gen() {
  local m=$1 cfg=$2 prompts=$3 seeds=$4 part=$5 purpose=${6:-"WP2 RQ1 honest variation"}
  local ck=$SD15 sha=$SD15_SHA res=512
  [ "$m" = sdxl ] && ck=$SDXL && sha=$SDXL_SHA && res=1024
  local name="$part-$m-$cfg-$NODE" id="$DATE-wp2-$part-$m-$cfg-$NODE-$REP"
  # on a Spark (SPARK=1) the host script starts each run in a research container via spark_run.py
  local launch=(); [ "${SPARK:-0}" = 1 ] && launch=(python3 tools/spark_run.py --run-id "$id" --)
  "${launch[@]}" python -m trajver.pilot --flags="$(flags_of "$cfg")" gen --wp wp2 --name "$name" \
    --run-id "$id" --ckpt "$ck" --ckpt-sha256 "$sha" --prompts "$CFG/$prompts" \
    --seeds "$seeds" --res $res --steps 30 --sampler "$(sampler_of "$cfg")" --save-traj --limit "$LIMIT" \
    --purpose "$purpose ($part, $cfg)" || { echo "FAILED $id"; [ "${SPARK:-0}" = 1 ] || return 1; }
}
