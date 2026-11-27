"""Why E0's honest non-pass rate is 3.3% on the test split against a 1% target (doc 14, item 5).

Reads only existing score files; no new compute. Run from the repository root:
    python -P experiments/analysis/wp3/e0_gap/e0_gap.py > experiments/analysis/wp3/e0_gap/result.txt

Three analyses:
1. Non-pass rate per split and card, and per metric, with the frozen v1 thresholds.
2. Random 200/200 re-splits of the 400 calibration + test prompts: thresholds fitted on one half with
   the frozen rule (trajver.calibrate.e0_thresholds), non-pass rate on the other half.
3. Concentration: how many failing jobs fail against one, two or all three rented cards.
"""
import json
import random
import statistics as st
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "code"))
from trajver.calibrate import e0_thresholds  # noqa: E402  (the frozen rule)

RUNS = ROOT / "experiments" / "runs"
TH = json.loads((ROOT / "experiments/configs/thresholds_v1_sdxl_euler.json").read_text())["e0"]
CARDS = ("rtx3090-01", "rtx4090-02", "rtx5090-01")
CAL = {c: RUNS / "20261126-wp2-e0cal-sdxl-euler-spark1-01" / f"cal-e0-{c}.jsonl" for c in CARDS}
TEST = {c: RUNS / f"20261126-wp3-e0-wp2-ref-test-sdxl-fp16-sdpa-euler-nd-{c}-on-spark3" / "e0.jsonl" for c in CARDS}
OBSERVED = None


def load(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def nonpass(r, th):
    if r["pixel_equal"]:
        return False
    return not (r["lpips"] <= th["lpips_t_pass"] and r["dino_cosine"] >= th["dino_t_pass"])


def rate(rows, th):
    return sum(nonpass(r, th) for r in rows) / len(rows)


def report(name, rows):
    n = len(rows)
    lp = sum(r["lpips"] > TH["lpips_t_pass"] for r in rows) / n
    dn = sum(r["dino_cosine"] < TH["dino_t_pass"] for r in rows) / n
    p99 = sorted(r["lpips"] for r in rows)[int(0.99 * n)]
    print(f"{name:22s} n={n:5d}  non-pass {100 * rate(rows, TH):5.2f}%  LPIPS>t_pass {100 * lp:4.2f}%  "
          f"DINOv2<t_pass {100 * dn:4.2f}%  LPIPS median {st.median(r['lpips'] for r in rows):.4f}  p99 {p99:.4f}")


print("1. Non-pass rate with the frozen v1 E0 thresholds:",
      {k: round(v, 4) for k, v in TH.items() if isinstance(v, float)})
cal, test = [], []
for c in CARDS:
    rows = load(CAL[c]); cal += rows; report("calibration " + c, rows)
for c in CARDS:
    rows = load(TEST[c]); test += rows; report("test " + c, rows)
report("calibration pooled", cal)
report("test pooled", test)
OBSERVED = rate(test, TH)

print("\n2. Random 200/200 prompt re-splits (2,000 splits, seed 20261127)")
by_prompt = {}
for r in cal + test:
    by_prompt.setdefault(r["prompt_id"], []).append(r)
prompts = sorted(by_prompt)
assert len(prompts) == 400
rng = random.Random(20261127)
held = []
for _ in range(2000):
    rng.shuffle(prompts)
    a = [r for p in prompts[:200] for r in by_prompt[p]]
    b = [r for p in prompts[200:] for r in by_prompt[p]]
    held.append(rate(b, e0_thresholds(a)))
held.sort()
print(f"held-out non-pass: median {100 * held[1000]:.2f}%, 95% range {100 * held[50]:.2f}-{100 * held[1950]:.2f}%; "
      f"splits at or above the observed {100 * OBSERVED:.2f}%: {100 * sum(x >= OBSERVED for x in held) / len(held):.1f}%")

print("\n3. Concentration of non-pass jobs across the three rented cards")
for name, paths in (("calibration", CAL), ("test", TEST)):
    per_job = Counter()
    for p in paths.values():
        for r in load(p):
            if nonpass(r, TH):
                per_job[r["job"]] += 1
    h = Counter(per_job.values())
    print(f"{name:12s} non-pass rows {sum(per_job.values()):3d}, distinct jobs {len(per_job):3d}, "
          f"failing against 1 / 2 / 3 cards: {h.get(1, 0)} / {h.get(2, 0)} / {h.get(3, 0)}")
