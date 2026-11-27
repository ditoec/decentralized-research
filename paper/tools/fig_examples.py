"""Qualitative figure: delivered images of honest and attacked jobs (illustration, not evidence).

  code/.venv/bin/python paper/tools/fig_examples.py IMAGE_DIR

IMAGE_DIR/<column>/<job>.png holds the delivered images, copied from the runs named in COLUMNS (raw/images/).
Selection rule, fixed before looking at the images: the first three jobs of the attacked test-split job set
(prompts_rent_test200.txt order, seed 0). Prompts: PartiPrompts (google-research/parti, Apache-2.0).

Writes paper/figures/fig_r2_examples.png and experiments/analysis/wp3/fig_examples_sources.json (run id, job and
sha256 of every full-size image, and the honest RTX 5090 vs Spark pixel differences shown in the difference column).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
JOBS = ["p00016_s0", "p00020_s0", "p00023_s0"]
AMP = 10  # difference map amplification
# (folder, column header, run id); the realistic forgery column is used when its images are present
COLUMNS = [
    ("spark", "Honest\nDGX Spark", "20261126-wp3-rerun-sdxl-euler-spark3-01"),
    ("rtx5090", "Honest\nRTX 5090", "20261126-wp2-ref-test-sdxl-fp16-sdpa-euler-nd-rtx5090-01"),
    ("diff", f"|5090 − Spark|\n×{AMP}", None),
    ("a1b", "A1\n20 of 30 steps", "20261126-wp3-atk-a1b-sdxl-euler-rtx5090-01"),
    ("a2", "A2\nfp8 network", "20261126-wp3-atk-a2-sdxl-euler-rtx5090-01"),
    ("a3turbo", "A3\nSDXL-Turbo", "20261126-wp3-atk-a3turbo-sdxl-euler-rtx5090-01"),
    ("a3lcm", "A3\nLCM-LoRA", "20261126-wp3-atk-a3lcm-sdxl-euler-rtx5090-01"),
    ("atkr-f3", "F3\ns = 0.5", "20261127-wp3-atkr-f3-sdxl-euler-rtx5090-01"),
    ("a8", "A8\nunrelated", "20261126-wp3-atk-a8-sdxl-euler-rtx5090-01"),
]


def prompt_text() -> dict[int, str]:
    out = {}
    for line in (ROOT / "experiments" / "configs" / "prompts_rent_test200.txt").read_text().splitlines():
        pid, _, text = line.partition("\t")
        if pid.strip().isdigit():
            out[int(pid)] = text.strip()
    return out


def main(img_dir: str) -> None:
    src = Path(img_dir)
    cols = [c for c in COLUMNS if c[0] == "diff" or all((src / c[0] / f"{j}.png").exists() for j in JOBS)]
    prompts = prompt_text()
    sources: dict = {"rule": "first three jobs of the attacked test-split job set (seed 0)",
                     "prompt_source": "PartiPrompts (google-research/parti, Apache-2.0)", "tiles": [], "diff": []}
    fig, axes = plt.subplots(len(JOBS), len(cols), figsize=(6.5, 0.83 * len(JOBS) + 0.45), dpi=300)
    for r, job in enumerate(JOBS):
        imgs = {}
        for c, (key, head, run) in enumerate(cols):
            ax = axes[r, c]
            ax.set_xticks([]); ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_visible(False)
            if key == "diff":
                a = imgs["rtx5090"].astype(np.int16); b = imgs["spark"].astype(np.int16)
                d = np.abs(a - b)
                sources["diff"].append({"job": job, "max_abs": int(d.max()), "mean_abs": float(d.mean()),
                                        "share_equal": float((d == 0).all(axis=-1).mean())})
                tile = np.clip(d.max(axis=-1) * AMP, 0, 255).astype(np.uint8)
                ax.imshow(Image.fromarray(tile).resize((256, 256), Image.LANCZOS), cmap="gray", vmin=0, vmax=255)
            else:
                p = src / key / f"{job}.png"
                raw = p.read_bytes()
                arr = np.asarray(Image.open(p).convert("RGB"))
                imgs[key] = arr
                sources["tiles"].append({"column": key, "run_id": run, "job": job,
                                         "png_sha256": hashlib.sha256(raw).hexdigest()})
                ax.imshow(Image.fromarray(arr).resize((256, 256), Image.LANCZOS))
            if r == 0:
                ax.set_title(head, fontsize=5.5, pad=3)
            if c == 0:
                pid = int(job[1:6])
                ax.set_ylabel(f"“{prompts.get(pid, job)}”", fontsize=6, rotation=90, labelpad=3)
    fig.subplots_adjust(left=0.04, right=0.995, top=0.86, bottom=0.01, wspace=0.04, hspace=0.04)
    out = ROOT / "paper" / "figures" / "fig_r2_examples.png"
    fig.savefig(out)
    (ROOT / "experiments" / "analysis" / "wp3" / "fig_examples_sources.json").write_text(json.dumps(sources, indent=1) + "\n")
    print("wrote", out, "columns:", ", ".join(c[0] for c in cols))
    for d in sources["diff"]:
        print(d)


if __name__ == "__main__":
    main(sys.argv[1])
