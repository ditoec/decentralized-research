#!/usr/bin/env bash
# Retry calibration replays until every one is complete (operator's request, 2026-11-26).
# Runs on the HOST from ~/esj/code after replay_cal_spark.sh. For each provider run in RUNS, it finds the
# node's replay folder (or starts one) and reruns `pilot replay` until the folder has summary.json; a rerun
# resumes by run id. An existing folder keeps its id, so a pass after midnight UTC does not start a new run.
# Before each attempt it drops our own provider files from the page cache (tools/evict_cache.py): on the
# GB10's unified memory CUDA context creation can fail with out of memory while page cache is high.
#
#   AFTER_PID=<queue pid> NODE=spark3 RUNS="<provider run> ..." bash tools/workloads/replay_sweep.sh
#
# MAX_ATTEMPTS (default 50) per run is a safety cap against a permanent error; WAIT (default 300 s).
#
# FREE_CONTAINER=<name> (optional; operator's standing permission of 2026-11-26, runbook §1 rule 1): after
# FREE_AFTER (default 2) failed attempts in a row, that production container is stopped (docker stop, not
# pause) only while the replay starts, and started again as soon as the replay has written its first job
# (or ended); a trap restarts it on any exit, its health is confirmed, and both times go to
# ~/esj/logs/free-mem-$NODE.log. Never security monitoring.
set -uo pipefail
NODE="${NODE:?}"; RUNS="${RUNS:?}"; MAX="${MAX_ATTEMPTS:-50}"; WAIT="${WAIT:-300}"
C=/models/checkpoints; P=../experiments/configs/prompts_cal.txt
SD15=$C/v1-5-pruned-emaonly.safetensors; SD15_SHA=6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa
SDXL=$C/sd_xl_base_1.0.safetensors; SDXL_SHA=31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b
say() { echo "$(date -u +%FT%TZ) $*"; }
FREE="${FREE_CONTAINER:-}"; FREE_AFTER="${FREE_AFTER:-2}"
case "$FREE" in *wazuh*|*soc*) echo "refusing to stop $FREE"; exit 2;; esac
flog() { echo "$(date -u +%FT%TZ) $*" >> ~/esj/logs/free-mem-$NODE.log; }
restore() {
  if [ -n "$FREE" ] && [ "$(docker inspect -f '{{.State.Running}}' "$FREE" 2>/dev/null)" = false ]; then
    docker start "$FREE" > /dev/null && flog "$FREE start issued"
    for _ in $(seq 1 60); do
      h=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}' "$FREE" 2>/dev/null)
      [ "$h" = healthy ] || [ "$h" = running ] && { flog "$FREE $h"; return; }; sleep 10
    done
    flog "$FREE NOT healthy after 10 min"
  fi
}
trap restore EXIT
trap 'restore; exit 1' INT TERM HUP
if [ -n "${AFTER_PID:-}" ]; then while kill -0 "$AFTER_PID" 2>/dev/null; do sleep 60; done; fi
for src in $RUNS; do
  until [ -f ~/esj/runs/"$src"/summary.json ]; do sleep 60; done
  case "$src" in *-sd15-*) m=sd15; ck=$SD15; sha=$SD15_SHA; res=512;; *) m=sdxl; ck=$SDXL; sha=$SDXL_SHA; res=1024;; esac
  case "$src" in *-dpmpp_2m-*) s=dpmpp_2m;; *) s=euler;; esac
  hw=$(echo "$src" | sed -E 's/.*-(rtx[0-9]+[a-z]?)-([0-9]+)$/\1-\2/')
  dir=$(ls -d ~/esj/runs/*-wp2-replay-cal-$m-$s-${hw}on-$NODE-01 2>/dev/null | head -1)
  id=$(basename "${dir:-$(date -u +%Y%m%d)-wp2-replay-cal-$m-$s-${hw}on-$NODE-01}")
  n=0; fails=0
  while [ ! -f ~/esj/runs/"$id"/summary.json ]; do
    n=$((n + 1))
    if [ "$n" -gt "$MAX" ]; then say "GAVE UP $id after $MAX attempts"; break; fi
    python3 tools/evict_cache.py "~/esj/runs/*-wp2-ref-caldev-*-rtx*" > /dev/null
    say "attempt $n $id"
    jobs0=$(cat ~/esj/runs/"$id"/jobs.jsonl 2>/dev/null | wc -l)
    esc=0
    if [ -n "$FREE" ] && [ "$fails" -ge "$FREE_AFTER" ]; then
      docker stop "$FREE" > /dev/null && { esc=1; flog "$FREE stopped for $id (after $fails failed starts)"; }
    fi
    python3 tools/spark_run.py --run-id "$id" -- python -m trajver.pilot \
      --flags="--force-fp16 --use-pytorch-cross-attention" replay --wp wp2 --name "replay-cal-$m-$s-${hw}on-$NODE" \
      --run-id "$id" --provider-run "/runs/$src" --ckpt $ck --ckpt-sha256 $sha --prompts $P --res $res --steps 30 \
      --sampler $s &
    rp=$!
    if [ "$esc" = 1 ]; then
      while kill -0 $rp 2>/dev/null && [ "$(cat ~/esj/runs/"$id"/jobs.jsonl 2>/dev/null | wc -l)" -le "$jobs0" ]; do sleep 10; done
      restore
    fi
    if wait $rp; then fails=0; else fails=$(( ${fails:-0} + 1 )); say "FAILED $id (attempt $n)"; sleep "$WAIT"; fi
  done
  [ -f ~/esj/runs/"$id"/summary.json ] && say "DONE $id"
done
say "sweep done on $NODE"
