#!/usr/bin/env python3
"""One-job run folders ("slices") of recorded provider runs, for the testbed demo (runbook §7 item 5).

Runs on a Spark host (standard library only). Each slice is what a verifier receives for one sampled job:
the committed image, the opened steps of the class-O bundle, the revealed draw seed, and a neutral
manifest (the claimed job only). The attack name, the "actual" parameters, the purpose and the
rental fields are left out, and so are the ground-truth labels (raw/labels): the verifier sees what a
provider would send. Files are hard links, so a slice costs no disk.

    python3 tools/testbed_slices.py --runs ~/esj/runs --plan slices.json

slices.json: [{"slice": "<run id of the slice>", "src": "<source run id>", "job": "p00016_s0"}, ...]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

KEEP_MANIFEST = ("wp", "trajver_version", "comfyui_commit", "cli_flags", "models", "claimed", "sampler", "scheduler",
                 "steps", "cfg", "resolution", "precision_flags", "seeds", "prompt_set", "draw_seed_sha256",
                 "image_digest", "retention")
KEEP_JOB = ("job", "prompt_id", "seed", "image_sha256", "merkle_root", "retention", "draw_seed_sha256", "opened_bytes")


def link(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    os.link(src, dst)


def make(runs: Path, slice_id: str, src_id: str, job: str):
    src, out = runs / src_id, runs / slice_id
    m = json.loads((src / "manifest.json").read_text())
    row = next(json.loads(l) for l in (src / "jobs.jsonl").read_text().splitlines()
               if l.strip() and json.loads(l)["job"] == job)
    out.mkdir(parents=True, exist_ok=True)
    man = {"run_id": slice_id, "purpose": "testbed demo: one provider job as sent to a verifier",
           **{k: m[k] for k in KEEP_MANIFEST if k in m}}
    (out / "manifest.json").write_text(json.dumps(man, indent=1) + "\n")
    (out / "jobs.jsonl").write_text(json.dumps({k: row[k] for k in KEEP_JOB if k in row}) + "\n")
    link(src / "logs" / "draw_seed.hex", out / "logs" / "draw_seed.hex")
    link(src / "raw" / "images" / f"{job}.png", out / "raw" / "images" / f"{job}.png")
    link(src / "raw" / "opened" / f"{job}.safetensors", out / "raw" / "opened" / f"{job}.safetensors")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--plan", required=True)
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text())
    for e in plan:
        make(Path(a.runs).expanduser(), e["slice"], e["src"], e["job"])
    print(f"{len(plan)} slices under {a.runs}")
