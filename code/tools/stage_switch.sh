#!/usr/bin/env bash
# Runs on the Spark (tools/stage_copy.py). Waits until the staging pod has STAGED a tag, then stops
# that GPU pod's pull and release processes and starts both again against the staging copy; partial
# tars resume (curl -C -) because the staged bytes are the same.
#   setsid nohup bash tools/stage_switch.sh <tag> <stage_base> <old_pull_pid> <old_release_pid> &
# <stage_base> is https://<staging>-8000.proxy.runpod.net/<token>/stage/<tag>
set -u
TAG=$1; BASE=$2; PULL=$3; REL=$4
cd "$HOME/esj/code" || exit 1
until curl -sSf -A "curl/8 esj-pull" -o /dev/null "$BASE/STAGED" 2>/dev/null; do sleep 120; done
echo "$(date -u +%FT%TZ) $TAG staged; switching pull and release to the staging pod"
pkill -P "$PULL" 2>/dev/null; kill "$PULL" "$REL" 2>/dev/null; sleep 2
setsid nohup python3 tools/pull_run.py "$BASE" --dest "$HOME/esj/runs" --wait \
  >> "$HOME/esj/logs/pull-wp2-$TAG.log" 2>&1 < /dev/null &
setsid nohup python3 tools/release_pod.py "$BASE" --dest "$HOME/esj/runs" \
  >> "$HOME/esj/logs/release-wp2-$TAG.log" 2>&1 < /dev/null &
echo "$(date -u +%FT%TZ) $TAG switched"
