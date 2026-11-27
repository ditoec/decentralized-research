#!/usr/bin/env bash
# Stop ONE production container while our research processes run, and always start it again
# (operator's standing permission, memory note 2026-11-26: docker stop/start, never pause, fewest
# containers, never Wazuh, restore by trap, logged).   free_while.sh CONTAINER PATTERN
# Waits until no process matching PATTERN (our own launchers) is left, then restores the container.
set -u
C="$1"; PAT="$2"; LOG=~/esj/logs/free_while-$C.log
case "$C" in *wazuh*) echo "refusing: never Wazuh"; exit 1;; esac
restore() { docker start "$C" >/dev/null && echo "$(date -u +%FT%TZ) started $C again" >> "$LOG"; }
trap restore EXIT
trap 'exit 0' INT TERM HUP  # exit runs the EXIT trap once (a bare restore trap kept looping)
docker stop -t 30 "$C" >/dev/null && echo "$(date -u +%FT%TZ) stopped $C while '$PAT' runs" >> "$LOG"
mine() { pgrep -f "$PAT" | grep -vx "$$" >/dev/null; }  # never count this script, whose own args hold PAT
while mine; do sleep 30; done
