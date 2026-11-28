#!/usr/bin/env bash
# Confirmatory run (docs/16): fetch the run metadata from the Sparks, build the E0 compare folder and the v2 view
# (E1 rows patched by trajver.e1img), run trajver.analysis_wp3 under v1 and v2, then summarize.py (primary
# endpoint and the pre-registered criterion). Same steps as code/tools/wp3_analyze.sh, for the confirmatory runs.
#
#   bash experiments/analysis/wp3/confirm/analyze.sh [--no-fetch]
set -euo pipefail
cd "$(dirname "$0")/../../../.."
RUNS=experiments/runs; OUT=experiments/analysis/wp3/confirm; PY=code/.venv/bin/python
GEN=20261128-wp3-confirm-test-sdxl-fp16-sdpa-euler-nd-rtx4090-03-01; S=${GEN#*-}
VER=20261128-wp3-verify-$S-on-spark4; E1I=20261128-wp3-e1img-$S-on-spark4; E0=20261128-wp3-e0-$S-on-spark3
RERUN=20261128-wp3-confirm-rerun-sdxl-euler-spark3-01
TH1=experiments/configs/thresholds_v1_sdxl_euler.json; TH2=experiments/configs/thresholds_v2_sdxl_euler.json

fetch() {  # node run...: run metadata only (top-level files, logs/, raw/labels/), never bundles or images
  local n=$1; shift
  for r in "$@"; do
    mkdir -p "$RUNS/$r"
    ssh -n -o ConnectTimeout=10 -o ServerAliveInterval=10 "aign-dgx@10.41.3.$((n + 1))" "cd ~/esj/runs/$r && { find . -maxdepth 1 -type f; \
      [ -d logs ] && find logs -maxdepth 1 -type f -size -5M; [ -d raw/labels ] && find raw/labels -type f; } | tar -cf - -T -" \
      | tar -C "$RUNS/$r" -xf - || { echo "fetch failed: $r on Spark-$n"; exit 1; }
  done
}
if [ "${1:-}" != --no-fetch ]; then
  fetch 4 "$GEN" "$VER" "$E1I"
  fetch 3 "$E0" "$RERUN"
  (cd code && .venv/bin/python tools/sanitize_runs.py ../$RUNS >/dev/null && .venv/bin/python tools/sanitize_runs.py --check ../$RUNS)
fi
CMP=$OUT/compare; rm -rf "$CMP"; mkdir -p "$CMP"
cp "$RUNS/$E0/e0.jsonl" "$CMP/${GEN}__$RERUN.e0.jsonl"
TRAJVER_RUNS=$RUNS $PY -m trajver.analysis_wp3 --honest "$RUNS/$VER" --thresholds "$TH1" --compare "$CMP" --out "$OUT/v1" | sed "s#$PWD/##"
V2=$OUT/v2runs/$VER; rm -rf "$OUT/v2runs"; mkdir -p "$V2"
cp "$RUNS/$VER/manifest.json" "$RUNS/$VER/summary.json" "$V2/"
$PY -m trajver.e1img patch "$RUNS/$VER/verdicts.jsonl" --rows "$RUNS/$E1I/e1img.jsonl" --thresholds "$TH2" --out "$V2/verdicts.jsonl"
TRAJVER_RUNS=$RUNS $PY -m trajver.analysis_wp3 --honest "$V2" --thresholds "$TH1" --compare "$CMP" --out "$OUT/v2" | sed "s#$PWD/##"
printf '%s\n' "E1 rows patched with $(basename "$TH2") (sha256 $(shasum -a 256 "$TH2" | cut -d' ' -f1)) by trajver.e1img patch;" \
  "all other rows and the Tier B tau as frozen in $(basename "$TH1")." > "$OUT/v2/NOTE.txt"
TRAJVER_RUNS=$RUNS $PY -P "$OUT/summarize.py" --v1 "$RUNS/$VER" --v2 "$V2" --compare "$CMP"
