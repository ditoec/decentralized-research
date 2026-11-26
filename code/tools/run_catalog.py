#!/usr/bin/env python3
"""Catalog of runs: every input and output, plus image sheets (docs/ops/README.md). Host python3 + PIL.

  python3 run_catalog.py ~/esj/runs/2026112*-wp2-* --out ~/esj/catalog [--sheet 8] [--thumb 160]
  python3 run_catalog.py --compare p00006_s0 RUN_A RUN_B ... --out ~/esj/catalog

Per run it writes one row to <out>/runs.csv (merged with rows already there, keyed by run_id):
  inputs   code commit, ComfyUI commit, image digest, models (file and sha256), prompt set, seeds,
           resolution, steps, sampler, scheduler, cfg, precision and CLI flags, retention class,
           draw-seed hash, node, provider, cloud, data center, rate
  outputs  jobs logged, jobs with an image hash, images on disk, MB of images, trajectories and
           opened bundles, mean seconds per job (observation; analyses read jobs.jsonl), start
           and end time, pulled time, billed cost
and a contact sheet <out>/sheets/<run_id>.jpg of the first --sheet jobs' images, labelled with
prompt id and seed. --compare tiles one job's image from several runs (same prompt and seed on
different hardware or configs) into <out>/compare/<job>__<n>runs.jpg.
Nothing that matches a host name or an internal address is written (the repository is public).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from pathlib import Path

from PIL import Image, ImageDraw

LEAK = re.compile(r"[a-z]+-dgx-\d|[a-z]+-soc-|10\.\d+\.\d+\.\d+")
COLS = ["run_id", "wp", "node", "provider", "cloud_type", "data_center", "hourly_rate_usd",
        "model", "model_sha256", "resolution", "steps", "sampler", "scheduler", "cfg", "precision_flags",
        "cli_flags", "prompt_set", "seeds", "retention", "draw_seed_sha256", "git_commit", "comfyui_commit",
        "image_digest", "start_time", "end_time", "jobs_logged", "jobs_with_image_sha", "images_on_disk",
        "images_mb", "traj_mb", "opened_mb", "mean_s_per_job", "pulled_unix", "cost_usd"]


def mb(p: Path) -> float:
    return round(sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1e6, 1) if p.exists() else 0.0


def flat(v) -> str:
    if isinstance(v, (list, tuple)):
        return " ".join(flat(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, sort_keys=True)
    return "" if v is None else str(v)


def row(run: Path) -> dict[str, object]:
    m = json.loads((run / "manifest.json").read_text())
    jobs = [json.loads(line) for line in (run / "jobs.jsonl").read_text().splitlines() if line.strip()] \
        if (run / "jobs.jsonl").exists() else []
    models = m.get("models") or []
    if isinstance(models, dict):
        models = [models]
    times = [j["t_total_s"] for j in jobs if isinstance(j.get("t_total_s"), (int, float))]
    imgs = run / "raw" / "images"
    r: dict[str, object] = {k: flat(m.get(k)) for k in COLS if k in m}
    r.update(
        run_id=run.name,
        model=" ".join(flat(x.get("file") or x.get("filename") or x.get("name")) for x in models if isinstance(x, dict)),
        model_sha256=" ".join(flat(x.get("sha256")) for x in models if isinstance(x, dict)),
        jobs_logged=len(jobs),
        jobs_with_image_sha=sum(1 for j in jobs if j.get("image_sha256")),
        images_on_disk=len(list(imgs.glob("*.png"))) if imgs.exists() else 0,
        images_mb=mb(imgs), traj_mb=mb(run / "raw" / "traj"), opened_mb=mb(run / "raw" / "opened"),
        mean_s_per_job=round(statistics.mean(times), 3) if times else "",
    )
    for k, v in r.items():
        if LEAK.search(str(v)):
            r[k] = "redacted"
    return r


def label(im: Image.Image, text: str) -> Image.Image:
    d = ImageDraw.Draw(im)
    d.rectangle((0, im.height - 14, im.width, im.height), fill=(0, 0, 0))
    d.text((3, im.height - 13), text[:40], fill=(255, 255, 255))
    return im


def sheet(paths: list[tuple[Path, str]], thumb: int, cols: int) -> Image.Image | None:
    tiles = []
    for p, text in paths:
        try:
            im = Image.open(p).convert("RGB")
        except Exception:  # noqa: BLE001  (an image still being written)
            continue
        im.thumbnail((thumb, thumb))
        tiles.append(label(im, text))
    if not tiles:
        return None
    rows = (len(tiles) + cols - 1) // cols
    out = Image.new("RGB", (cols * thumb, rows * thumb), (255, 255, 255))
    for i, t in enumerate(tiles):
        out.paste(t, ((i % cols) * thumb, (i // cols) * thumb))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sheet", type=int, default=8)
    ap.add_argument("--thumb", type=int, default=160)
    ap.add_argument("--compare", default=None, help="job id, e.g. p00006_s0: tile it across the runs")
    a = ap.parse_args()
    out = Path(a.out).expanduser()
    runs = [Path(r).expanduser() for r in a.runs if (Path(r).expanduser() / "manifest.json").exists()]
    if a.compare:
        paths = [(r / "raw" / "images" / f"{a.compare}.png", f"{r.name.rsplit('-', 2)[-2]}  {a.compare}") for r in runs]
        im = sheet([p for p in paths if p[0].exists()], a.thumb * 2, len(paths))
        if im:
            (out / "compare").mkdir(parents=True, exist_ok=True)
            dst = out / "compare" / f"{a.compare}__{len(paths)}runs.jpg"
            im.save(dst, quality=85)
            print("wrote", dst)
        return 0
    (out / "sheets").mkdir(parents=True, exist_ok=True)
    table = out / "runs.csv"
    rows = {}
    if table.exists():
        with open(table) as f:
            rows = {r["run_id"]: r for r in csv.DictReader(f)}
    for run in runs:
        rows[run.name] = row(run)
        imgs = sorted((run / "raw" / "images").glob("*.png"))[: a.sheet]
        im = sheet([(p, p.stem.replace("_", " ")) for p in imgs], a.thumb, min(len(imgs), 8) or 1)
        if im:
            im.save(out / "sheets" / f"{run.name}.jpg", quality=80)
    with open(table, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])
    print(f"{len(runs)} runs cataloged; {len(rows)} rows in {table}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
