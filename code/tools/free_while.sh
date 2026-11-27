#!/usr/bin/env bash
# Stop ONE production container while our research processes run, and always start it again
# (operator's standing permission, memory note 2026-11-26: docker stop/start, never pause, fewest
# containers, never Wazuh, restore by trap, logged).   free_while.sh CONTAINER PATTERN
# Waits until no process matching PATTERN (our own launchers) is left, then restores the container.
set -u
C="$1"; PAT="$2"; LOG=~/esj/logs/free_while-$C.log
case "$C" in *wazuh*) echo "refusing: never Wazuh"; exit 1;; esac
restore() { docker start "$C" >/dev/null && echo "$(date -u +%FT%TZ) started $C again" >> "$LOG"; }
trap restore EXIT INT TERM HUP
docker stop -t 30 "$C" >/dev/null && echo "$(date -u +%FT%TZ) stopped $C while '$PAT' runs" >> "$LOG"
while pgrep -f "$PAT" >/dev/null; do sleep 30; done
