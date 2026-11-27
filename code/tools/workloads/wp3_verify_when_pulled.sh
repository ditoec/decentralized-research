#!/usr/bin/env bash
# WP3 S7 on a verifier Spark that pulls its own share of the pod's runs (pull_run.py --only): for each
# run in RUNS, wait until its pull is complete (manifest has pulled_unix), then run wp3_spark.sh
# ITEMS=verify on it with the caller's STEPS / TH / RERUN / NODE / MARGIN_GB.
set -uo pipefail
for src in ${RUNS:?}; do
  until python3 -c "import json,sys; sys.exit(0 if 'pulled_unix' in json.load(open(sys.argv[1])) else 1)" \
      ~/esj/runs/"$src"/manifest.json 2>/dev/null; do sleep 30; done
  echo "$(date -u +%FT%TZ) $src pulled: ${STEPS:-verify e0 e1img}"
  ITEMS=verify RUNS="$src" bash tools/workloads/wp3_spark.sh
done
echo "$(date -u +%FT%TZ) all done"
