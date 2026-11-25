"""Stand-in for ``python -m trajver.verify`` in orchestrator tests (no GPU, no ComfyUI).

Same CLI shape (RUN positional, --run-id, other flags ignored) and the same output file
(<TRAJVER_RUNS>/<run-id>/verdicts.jsonl). Its verdicts come from RUN/stub_verdict.json, a map from
job key to "pass"/"fail" written by the test's stand-in provider. Each row also carries an ``attack``
field set to the opposite label, so a test fails if the orchestrator ever reads it.
"""
import argparse
import json
import os
import sys
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--run-id", required=True)
    a, _ = ap.parse_known_args(argv)
    src = Path(a.run) / "stub_verdict.json"
    if not src.exists():
        sys.exit(f"no run at {a.run}")
    out = Path(os.environ["TRAJVER_RUNS"]) / a.run_id
    out.mkdir(parents=True, exist_ok=True)
    with (out / "verdicts.jsonl").open("w") as f:
        for job, v in json.loads(src.read_text()).items():
            decoy = "honest" if v == "fail" else "fewer_steps"
            for k in (1, 2, 3, 5, 8):
                f.write(json.dumps({"job_id": job, "attack": decoy, "s": 1.0, "evidence": "E2-H", "k": k,
                                    "verdict": v, "score": 0.0}) + "\n")


if __name__ == "__main__":
    main()
