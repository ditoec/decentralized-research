"""E0 follow-up (doc 14 item 5): are the test-split Spark reference images the cause of E0's 3.3%?

The calibration references (20261125-wp2-ref-sdxl-fp16-sdpa-euler-nd-spark5-01, WP2 procedure, Spark-5) and
the test references (20261126-wp3-rerun-sdxl-euler-spark3-01, WP3 re-run procedure, Spark-3) came from two
procedures on two nodes. Run 20261127-wp3-e0check-cal30-sdxl-euler-spark3-01 regenerated 30 calibration
prompts x 3 seeds with the WP3 re-run procedure on Spark-3. If its images equal the calibration references
bit for bit, the reference procedure is ruled out and the higher test rate belongs to the test jobs.

    python -P experiments/analysis/wp3/e0_gap/refcheck.py   (from the repository root; writes refcheck.json)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RUNS = ROOT / "experiments" / "runs"
CHECK, CAL = "20261127-wp3-e0check-cal30-sdxl-euler-spark3-01", "20261125-wp2-ref-sdxl-fp16-sdpa-euler-nd-spark5-01"


def rows(run):
    return {r["job"]: r for r in (json.loads(l) for l in (RUNS / run / "jobs.jsonl").read_text().splitlines() if l.strip())}


a, b = rows(CHECK), rows(CAL)
common = sorted(set(a) & set(b))
img = sum(a[j]["image_sha256"] == b[j]["image_sha256"] for j in common)
lat = sum(a[j].get("latent_sha256") == b[j].get("latent_sha256") for j in common if a[j].get("latent_sha256"))
out = {"check_run": CHECK, "calibration_reference_run": CAL, "n_jobs": len(common), "image_identical": img,
       "latent_identical": lat, "differing_jobs": [j for j in common if a[j]["image_sha256"] != b[j]["image_sha256"]]}
(Path(__file__).parent / "refcheck.json").write_text(json.dumps(out, indent=1) + "\n")
print(out)
