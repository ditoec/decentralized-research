#!/usr/bin/env bash
# Runs inside a RunPod pod next to pod_job.sh (runbook §4). Lets the pod terminate itself once the
# operator's Spark has pulled and checked every run, so no laptop has to stay on to end the rental.
#
#   nohup bash /work/selfstop.sh > /work/out/selfstop.log 2>&1 &
#
# Waits until out/DONE exists and the Spark has PUT secret/release (tools/release_pod.py does this
# only after every run in out/INDEX is pulled, checksum-verified and passes trajver.retention check;
# the PUT needs the pod token). Then deletes this pod through the RunPod API with the pod-scoped key
# RunPod injects (RUNPOD_API_KEY, RUNPOD_POD_ID); the operator's own account key is never on the pod.
set -u
API="${RUNPOD_API_BASE:-https://api.runpod.io/v2}"
WORK="${POD_WORK:-/work}"
POLL="${SELFSTOP_POLL:-30}"
while :; do
  if [ -f "$WORK/out/DONE" ] && [ -s "$WORK/secret/release" ]; then
    echo "$(date -u +%FT%TZ) release received: $(head -c 200 "$WORK/secret/release")"
    for i in 1 2 3 4 5 6 7 8 9 10; do
      code=$(curl -s -o /dev/null -w '%{http_code}' -X DELETE -H "Authorization: Bearer $RUNPOD_API_KEY" \
             "$API/pods/$RUNPOD_POD_ID")
      echo "$(date -u +%FT%TZ) delete attempt $i: HTTP $code"
      case $code in 2??) exit 0;; esac
      sleep 30
    done
    echo "$(date -u +%FT%TZ) API delete failed; trying runpodctl"
    runpodctl config --apiKey "$RUNPOD_API_KEY" >/dev/null 2>&1
    runpodctl remove pod "$RUNPOD_POD_ID" && exit 0
    echo "$(date -u +%FT%TZ) could not delete this pod; the operator must terminate it"
    exit 1
  fi
  sleep "$POLL"
done
