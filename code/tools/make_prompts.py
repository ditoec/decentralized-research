"""Build the study's prompt set from PartiPrompts (runbook §0).

    python tools/make_prompts.py PartiPrompts.tsv

PartiPrompts (google-research/parti, Apache-2.0) has 1,632 prompts in 12 categories. We drop
prompts longer than 60 words (they are truncated by CLIP's 77-token limit, which would make
conditioning checks trivially pass on the truncated tail) and duplicates, then draw 1,000 with a
fixed seed, stratified by category so every split has the same category mix. Prompt IDs are the
1-based line numbers in the source file. Writes, under experiments/configs/:

  prompts_{cal,dev,test}.txt   40/20/40 split (400/200/400)
  prompts_caldev600.txt        cal + dev (reference config on the Sparks)
  prompts_rent500.txt          200 cal + 100 dev + 200 test (reference config on RunPod)
  prompts_rent_caldev300.txt   the cal + dev part of rent500 (retention class F)
  prompts_rent_test200.txt     the test part of rent500 (retention class O; not scored until §6)
  prompts_grid200.txt          120 cal + 80 dev (non-reference configs on the Sparks)
  prompts_prec100.txt          100 taken from grid200 (precision factor; second software stack)
  prompts_l2_50.txt            50 cal (unit-to-unit subset)
  prompts_pilot20.txt          20 cal (pilot P2)
  prompts.json                 sha256 of every file and of the source

Each line is "<id>\t<prompt>". The test split is not used until runbook §6.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

SEED = 20261123
OUT = Path(__file__).resolve().parents[2] / "experiments" / "configs"


def take(rng: random.Random, items: list, n: int) -> list:
    return sorted(rng.sample(items, n), key=lambda r: r[0])


def main(src: str) -> None:
    raw = Path(src).read_bytes()
    rows = list(csv.reader(raw.decode().splitlines(), delimiter="\t"))[1:]
    seen, pool = set(), []
    for i, r in enumerate(rows, start=2):  # line 1 is the header
        p = " ".join(r[0].split())
        if not p or p.lower() in seen or len(p.split()) > 60:
            continue
        seen.add(p.lower())
        pool.append((i, p, r[1]))
    rng = random.Random(SEED)
    by_cat = defaultdict(list)
    for row in pool:
        by_cat[row[2]].append(row)
    # stratified draw of 1,000: proportional per category, remainder by largest fraction
    quota = {c: 1000 * len(v) / len(pool) for c, v in by_cat.items()}
    n = {c: int(q) for c, q in quota.items()}
    for c in sorted(quota, key=lambda c: quota[c] - n[c], reverse=True)[: 1000 - sum(n.values())]:
        n[c] += 1
    split = {"cal": [], "dev": [], "test": []}
    for c in sorted(by_cat):
        chosen = rng.sample(by_cat[c], n[c])
        k_cal, k_dev = round(0.4 * len(chosen)), round(0.2 * len(chosen))
        split["cal"] += chosen[:k_cal]
        split["dev"] += chosen[k_cal:k_cal + k_dev]
        split["test"] += chosen[k_cal + k_dev:]
    # fix exact 400/200/400 by moving the overflow between splits deterministically
    allc = split["cal"] + split["dev"] + split["test"]
    rng.shuffle(allc)
    allc.sort(key=lambda r: ("cal", "dev", "test").index(next(s for s in split if r in split[s])))
    split = {"cal": allc[:400], "dev": allc[400:600], "test": allc[600:]}
    split = {k: sorted(v) for k, v in split.items()}

    rng2 = random.Random(SEED + 1)
    files = {f"prompts_{k}.txt": v for k, v in split.items()}
    files["prompts_rent500.txt"] = sorted(take(rng2, split["cal"], 200) + take(rng2, split["dev"], 100)
                                          + take(rng2, split["test"], 200))
    # the same 500 split by retention class (runbook §3.5): cal+dev class F, test class O; no rng draws
    test_ids = {r[0] for r in split["test"]}
    files["prompts_rent_caldev300.txt"] = [r for r in files["prompts_rent500.txt"] if r[0] not in test_ids]
    files["prompts_rent_test200.txt"] = [r for r in files["prompts_rent500.txt"] if r[0] in test_ids]
    files["prompts_caldev600.txt"] = sorted(split["cal"] + split["dev"])  # Spark reference config
    grid = sorted(take(rng2, split["cal"], 120) + take(rng2, split["dev"], 80))
    files["prompts_grid200.txt"] = grid
    files["prompts_prec100.txt"] = take(rng2, grid, 100)
    files["prompts_l2_50.txt"] = take(rng2, split["cal"], 50)
    files["prompts_pilot20.txt"] = take(rng2, split["cal"], 20)

    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"source": "PartiPrompts.tsv (google-research/parti, Apache-2.0)",
            "source_sha256": hashlib.sha256(raw).hexdigest(), "seed": SEED, "files": {}}
    for name, items in files.items():
        text = "".join(f"{i}\t{p}\n" for i, p, _ in items)
        (OUT / name).write_text(text)
        meta["files"][name] = {"n": len(items), "sha256": hashlib.sha256(text.encode()).hexdigest()}
    (OUT / "prompts.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(json.dumps(meta, indent=1))


def read_prompts(path: str | Path) -> list[tuple[int, str]]:
    out = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            i, p = line.split("\t", 1)
            out.append((int(i), p))
    return out


if __name__ == "__main__":
    main(sys.argv[1])
