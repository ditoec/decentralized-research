#!/usr/bin/env bash
# WP3 S8 on the Mac (docs/ops/2026-11-27-wp3-overnight.md): fetch run metadata from the verifier Sparks,
# assemble the E0 compare folder, build the thresholds_v2 views (E1 rows patched by trajver.e1img), and
# run trajver.analysis_wp3 under v1 and v2 into experiments/analysis/wp3/{v1,v2,base}.
#
#   bash code/tools/wp3_analyze.sh [--no-fetch] [--partial]
#
# Placement (LOG 2026-11-27, rebalanced 05:12 UTC): Spark-4 a1b a3lcm; Spark-5 a2 a3turbo f3 m (+ cost replay); Spark-6 a8 f1 f2 base;
# Spark-3 honest test verify/E0/E1-image; Spark-1 the F3 sweep. Node N is 10.41.3.(N+1) (docs/local-nodes.md).
set -o pipefail  # no -u: bash 3.2 (macOS) treats empty arrays as unbound
cd "$(dirname "$0")/../.."
FETCH=1; PARTIAL=(); for x in "$@"; do case $x in --no-fetch) FETCH=0;; --partial) PARTIAL=(--partial);; esac; done
RUNS=experiments/runs; OUT=experiments/analysis/wp3; PY=code/.venv/bin/python
D=20261126; V=20261127; X=sdxl-euler-rtx5090-01; RERUN=$D-wp3-rerun-sdxl-euler-spark3-01
node_of() { case $1 in a1b|a3lcm) echo 4;; a2|a3turbo|f3|m) echo 5;; a8|f1|f2|base) echo 6;; esac; }
TH1=experiments/configs/thresholds_v1_sdxl_euler.json; TH2=experiments/configs/thresholds_v2_sdxl_euler.json

fetch() {  # node run...: run metadata only (top-level files, logs/, raw/labels/), never bundles or images
  local n=$1; shift
  for r in "$@"; do
    mkdir -p "$RUNS/$r"
    ssh -n -o ConnectTimeout=10 -o ServerAliveInterval=10 "aign-dgx@10.41.3.$((n + 1))" "cd ~/esj/runs/$r 2>/dev/null && { find . -maxdepth 1 -type f; \
      [ -d logs ] && find logs -maxdepth 1 -type f -size -5M; [ -d raw/labels ] && find raw/labels -type f; } | tar -cf - -T -" \
      | tar -C "$RUNS/$r" -xf - || echo "fetch failed: $r on Spark-$n"
    [ -n "$(ls -A "$RUNS/$r")" ] || { rmdir "$RUNS/$r"; echo "missing: $r on Spark-$n"; }
  done
}

ATK=(a1b a2 a3turbo a3lcm f1 f2 f3 a8 m)
if [ $FETCH = 1 ]; then
  for a in "${ATK[@]}"; do n=$(node_of $a); g=$D-wp3-atk-$a-$X
    fetch "$n" "$g" "$V-wp3-verify-wp3-atk-$a-$X-on-spark$n" "$V-wp3-e0-wp3-atk-$a-$X-on-spark$n" "$V-wp3-e1img-wp3-atk-$a-$X-on-spark$n"
  done
  fetch 6 "$D-wp3-base-$X" "$V-wp3-verify-wp3-base-$X-on-spark6" "$V-wp3-e0-wp3-base-$X-on-spark6" "$V-wp3-e1img-wp3-base-$X-on-spark6"
  fetch 5 "$D-wp3-cost-replay-$X"
  for s in s010 s025 s050 s075 s100; do fetch 1 "$D-wp3-sweep-f3-$s-sdxl-euler-spark1-01" "$V-wp3-verify-wp3-sweep-f3-$s-sdxl-euler-spark1-01-on-spark1"; done
  for s in s050 s075 s100; do fetch 3 "$V-wp3-verify-wp3-sweep-f3-$s-sdxl-euler-spark1-01-on-spark3"; done  # moved to Spark-3 at 05:20 UTC
  (cd code && .venv/bin/python tools/sanitize_runs.py ../$RUNS >/dev/null && .venv/bin/python tools/sanitize_runs.py --check ../$RUNS) || exit 1
fi

# E0 compare folder: <generation run>__<Spark re-run>.e0.jsonl (analysis_wp3 --compare)
CMP=$OUT/compare; rm -rf "$CMP"; mkdir -p "$CMP"
for c in 20261125-wp2-ref-test-sdxl-fp16-sdpa-euler-nd-rtx3090-01 20261125-wp2-ref-test-sdxl-fp16-sdpa-euler-nd-rtx4090-02 \
         20261126-wp2-ref-test-sdxl-fp16-sdpa-euler-nd-rtx5090-01; do
  cp "$RUNS/20261126-wp3-e0-${c#*-}-on-spark3/e0.jsonl" "$CMP/${c}__$RERUN.e0.jsonl"
done
for a in "${ATK[@]}" base; do
  if [ $a = base ]; then g=$D-wp3-base-$X; e=$RUNS/$V-wp3-e0-wp3-base-$X-on-spark6
  else g=$D-wp3-atk-$a-$X; e=$RUNS/$V-wp3-e0-wp3-atk-$a-$X-on-spark$(node_of $a); fi
  [ -s "$e/e0.jsonl" ] && cp "$e/e0.jsonl" "$CMP/${g}__$RERUN.e0.jsonl" || echo "no E0 yet: $g"
done

HON=(); for c in rtx3090-01 rtx4090-02 rtx5090-01; do HON+=("$RUNS/20261126-wp3-verify-wp2-ref-test-sdxl-fp16-sdpa-euler-nd-$c-on-spark3"); done
ATT=(); for a in "${ATK[@]}"; do v=$RUNS/$V-wp3-verify-wp3-atk-$a-$X-on-spark$(node_of $a)
  [ -s "$v/verdicts.jsonl" ] && [ -f "$v/summary.json" ] && ATT+=("$v") || echo "not verified yet: $a"; done
SWP=(); for s in s010 s025 s050 s075 s100; do v=$RUNS/$V-wp3-verify-wp3-sweep-f3-$s-sdxl-euler-spark1-01-on-spark3
  [ -f "$v/summary.json" ] || v=$RUNS/$V-wp3-verify-wp3-sweep-f3-$s-sdxl-euler-spark1-01-on-spark1
  [ -f "$v/summary.json" ] && SWP+=("$v") || echo "sweep not verified yet: $s"; done
BASEV=$RUNS/$V-wp3-verify-wp3-base-$X-on-spark6
# beta_A baseline: M (honest compute, false metadata) runs through the same attacks.run instrument as every attack,
# so t_compute_s is compared with t_compute_s; the pilot-gen base run times t_sample_s without that instrument's
# trajectory overhead (A8, a full honest generation through attacks.run, took about 4x the base t_sample_s)
BASEGEN=$RUNS/$D-wp3-atk-m-$X

an() {  # out thresholds honest... -- attacked... -- sweep...
  local o=$1 th=$2; shift 2; local h=() t=() w=() z=h
  for x in "$@"; do case $x in --) [ $z = h ] && z=t || z=w;; *) eval "$z+=(\"\$x\")";; esac; done
  TRAJVER_RUNS=$RUNS $PY -m trajver.analysis_wp3 --honest "${h[@]}" ${t[@]:+--attacked "${t[@]}"} ${w[@]:+--sweep "${w[@]}"} \
    $([ -f "$BASEGEN/jobs.jsonl" ] && echo --baseline "$BASEGEN") --thresholds "$th" --compare "$CMP" --out "$o" "${PARTIAL[@]}" | sed "s#$PWD/##"
}
an "$OUT/v1" "$TH1" "${HON[@]}" -- "${ATT[@]}" -- "${SWP[@]}"
[ -f "$BASEV/summary.json" ] && an "$OUT/base" "$TH1" "$BASEV" -- --

# thresholds_v2: the same verify runs with their E1 rows patched (e1img patch); E2-H follows from E1 in
# analysis_wp3, every other row and the frozen v1 tau are unchanged, so the analysis still checks v1's hash
V2=$OUT/v2runs; rm -rf "$V2"; mkdir -p "$V2"
patch() {  # verify-run rows...
  local v=$1; shift; mkdir -p "$V2/$(basename "$v")"; cp "$v/manifest.json" "$v/summary.json" "$V2/$(basename "$v")/" 2>/dev/null
  $PY -m trajver.e1img patch "$v/verdicts.jsonl" --rows "$@" --thresholds "$TH2" --out "$V2/$(basename "$v")/verdicts.jsonl" | sed "s#$PWD/##"
}
H2=(); for c in 20261125-wp2-ref-test-sdxl-fp16-sdpa-euler-nd-rtx3090-01 20261125-wp2-ref-test-sdxl-fp16-sdpa-euler-nd-rtx4090-02 \
                20261126-wp2-ref-test-sdxl-fp16-sdpa-euler-nd-rtx5090-01; do
  v=$RUNS/20261126-wp3-verify-${c#*-}-on-spark3; patch "$v" "$RUNS/20261127-wp3-e1img-test-spark3-01/e1img-$c.jsonl"; H2+=("$V2/$(basename "$v")"); done
A2=(); for v in "${ATT[@]}"; do r=$(basename "$v" | sed -e "s/-verify-/-e1img-/")
  if [ -s "$RUNS/$r/e1img.jsonl" ]; then patch "$v" "$RUNS/$r/e1img.jsonl"; A2+=("$V2/$(basename "$v")"); else echo "no E1 image rows yet: $r"; fi; done
an "$OUT/v2" "$TH1" "${H2[@]}" -- "${A2[@]}" --
printf '%s\n' "E1 rows patched with $(basename "$TH2") (sha256 $(shasum -a 256 "$TH2" | cut -d' ' -f1)) by trajver.e1img patch;" \
  "all other rows and the Tier B tau as frozen in $(basename "$TH1"). Post-freeze, calibration split only (S7b)." > "$OUT/v2/NOTE.txt"
echo "wp3 analysis written to $OUT"
