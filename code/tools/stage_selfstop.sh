#!/usr/bin/env bash
# Runs on the staging pod (tools/stage_copy.py). Deletes the staging pod once the Spark has released
# every staged tag, i.e. /work/stage/<tag>/secret/release exists for each tag in STAGE_TAGS (the Spark's
# release_pod.py PUTs it only after every run is pulled, checksum-verified and passes the retention check).
#   STAGE_TAGS="rtx4090 rtx3090 rtx5090" nohup bash /work/stage_selfstop.sh > /work/stage/selfstop.log 2>&1 &
set -u
API="${RUNPOD_API_BASE:-https://api.runpod.io/v2}"
WORK="${POD_WORK:-/work}"
while :; do
  left=0
  for t in $STAGE_TAGS; do [ -s "$WORK/stage/$t/secret/release" ] || left=$((left + 1)); done
  if [ "$left" -eq 0 ]; then
    echo "$(date -u +%FT%TZ) all tags released by the Spark: $STAGE_TAGS"
    for i in 1 2 3 4 5 6 7 8 9 10; do
      code=$(curl -s -o /dev/null -w '%{http_code}' -X DELETE -H "Authorization: Bearer $RUNPOD_API_KEY" \
             "$API/pods/$RUNPOD_POD_ID")
      echo "$(date -u +%FT%TZ) delete attempt $i: HTTP $code"
      case $code in 2??) exit 0;; esac
      sleep 30
    done
    echo "$(date -u +%FT%TZ) could not delete the staging pod; the operator must terminate it"
    exit 1
  fi
  sleep "${SELFSTOP_POLL:-60}"
done
