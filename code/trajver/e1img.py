"""E1 image tolerance (thresholds_v2; operator's decision of 2026-11-26/27).

E1(c) checks that VAE-decoding the committed x_final on the verifier reproduces the delivered image.
v1 used the development constant ``image_max_abs`` = 2 uint8 levels, which was never calibrated and
rejects honest cross-GPU jobs. v2 calibrates it on the calibration split only, with a rule fixed before
measuring (mirrors Tier A's eps_A): image_max_abs = 2 x the largest honest |decoded - delivered|,
pooled over the calibration pairs. Nothing else changes.

  python -m trajver.e1img measure RUN --ckpt CKPT [--ckpt-sha256 S] [--cal-only] --out ROWS.jsonl
  python -m trajver.e1img freeze --base thresholds_v1_sdxl_euler.json --rows A.jsonl [...] --out thresholds_v2_sdxl_euler.json
  python -m trajver.e1img patch VERDICTS.jsonl --rows ROWS.jsonl --thresholds TH.json --out VERDICTS_v2.jsonl

``measure`` works on class F (raw/traj) and class O (raw/opened, which opens x_final) runs.
``patch`` recomputes only the E1 rows of a verify run: E1 fails if any non-image check failed, or if the
measured image difference exceeds the tolerance of TH. Every other row is copied unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

IMAGE_REASON = "E1.image: decoded x_final does not match image"


def _rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def cmd_measure(a):
    import numpy as np
    import torch
    from PIL import Image

    from . import comfy_env
    comfy_env.configure(a.flags.split())
    from .calibrate import calibration_ids
    from .job import Pipeline
    from .trajectory import Trajectory

    run = Path(a.run)
    jobs = _rows(run / "jobs.jsonl")
    cal = calibration_ids() if a.cal_only else None
    pipe = Pipeline(a.ckpt, a.ckpt_sha256)
    out = open(a.out, "a")
    done = {r["job"] for r in _rows(Path(a.out))} if Path(a.out).exists() and Path(a.out).stat().st_size else set()
    for r in jobs[: a.limit or None]:
        if r["job"] in done or (cal is not None and r["prompt_id"] not in cal):
            continue
        tp, op = run / "raw" / "traj" / f"{r['job']}.safetensors", run / "raw" / "opened" / f"{r['job']}.safetensors"
        if tp.exists():
            x_final = Trajectory.load(tp).x_final
        elif op.exists():
            from safetensors.torch import load_file
            x_final = load_file(str(op))["x_final"]
        else:
            continue
        decoded = pipe.to_uint8(pipe.decode(pipe.latent_out(x_final)))
        # exactly as trajver.verify builds the delivered image for E1.image (batch dimension added)
        img = torch.from_numpy(np.asarray(Image.open(run / "raw" / "images" / f"{r['job']}.png")).copy())[None]
        if decoded.shape != img.shape:
            raise SystemExit(f"{r['job']}: decoded shape {tuple(decoded.shape)} != image {tuple(img.shape)}")
        diff = (decoded.int() - img.int()).abs()
        row = {"job": r["job"], "prompt_id": r["prompt_id"], "run_id": run.name, "max_abs": int(diff.max()),
               "frac_equal": float((diff == 0).float().mean())}
        out.write(json.dumps(row) + "\n")
        out.flush()
    out.close()


def cmd_freeze(a):
    out = Path(a.out)
    if out.exists():
        raise SystemExit(f"{out} exists: frozen thresholds are never overwritten")
    base_bytes = Path(a.base).read_bytes()
    th = json.loads(base_bytes)
    rows = [r for p in a.rows for r in _rows(Path(p))]
    if not rows:
        raise SystemExit("no rows")
    worst = max(r["max_abs"] for r in rows)
    th["version"] = out.stem
    th["image_max_abs"] = 2 * worst
    th["supersedes"] = {"file": Path(a.base).name, "sha256": hashlib.sha256(base_bytes).hexdigest()}
    th.setdefault("notes", []).append(
        f"v2: image_max_abs = 2 x the largest honest calibration-split |decoded - delivered| ({worst} uint8 levels, "
        f"{len(rows)} jobs over {len({r['run_id'] for r in rows})} runs); rule fixed before measuring; all else as v1")
    th.setdefault("sources", {})["e1_image_rows"] = sorted({Path(p).name for p in a.rows})
    text = json.dumps(th, indent=1) + "\n"
    out.write_text(text)
    print("froze", out, "sha256", hashlib.sha256(text.encode()).hexdigest())


def cmd_patch(a):
    th = json.loads(Path(a.thresholds).read_text())
    tol = th["image_max_abs"]
    meas = {r["job"]: r["max_abs"] for p in a.rows for r in _rows(Path(p))}
    n_missing = 0
    with open(a.out, "w") as f:
        for v in _rows(Path(a.verdicts)):
            if v.get("evidence") == "E1":
                other = [x for x in v.get("reasons", []) if x != IMAGE_REASON]
                m = meas.get(v["job_id"])
                if m is None:
                    n_missing += 1
                    v = {**v, "e1_image_max_abs": None, "thresholds": th["version"]}
                else:
                    img_ok = m <= tol
                    reasons = other + ([] if img_ok else [IMAGE_REASON])
                    v = {**v, "verdict": "fail" if reasons else "pass", "reasons": reasons, "e1_image_max_abs": m,
                         "thresholds": th["version"]}
            f.write(json.dumps(v) + "\n")
    print(f"patched -> {a.out} (missing image measurements: {n_missing})")


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("run"); m.add_argument("--ckpt", required=True); m.add_argument("--ckpt-sha256", default=None)
    m.add_argument("--flags", default="--force-fp16 --use-pytorch-cross-attention")
    m.add_argument("--cal-only", action="store_true"); m.add_argument("--limit", type=int, default=0)
    m.add_argument("--out", required=True)
    fz = sub.add_parser("freeze")
    fz.add_argument("--base", required=True); fz.add_argument("--rows", nargs="+", required=True)
    fz.add_argument("--out", required=True)
    pa = sub.add_parser("patch")
    pa.add_argument("verdicts"); pa.add_argument("--rows", nargs="+", required=True)
    pa.add_argument("--thresholds", required=True); pa.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    {"measure": cmd_measure, "freeze": cmd_freeze, "patch": cmd_patch}[a.cmd](a)


if __name__ == "__main__":
    main()
