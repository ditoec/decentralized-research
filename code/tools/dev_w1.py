"""Dev run: an early look at hypothesis W1 (pilot P5) on whatever machine this runs on.

For N honest SD1.5 trajectories it records the cosine of x_i vs x_{i+1} for every step, and runs
the reproduced deployed rule E2-W on the honest trajectory and on forgeries F1–F3 at several
skip fractions s. Logged under experiments/runs/ with wp="dev": it is NOT paper data (the paper's
P5 runs on the pilot hardware), but it tells us early whether the break-and-fix headline holds.

    python tools/dev_w1.py --ckpt .cache/models/checkpoints/v1-5-pruned-emaonly.safetensors --n 10
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trajver import comfy_env  # noqa: E402

PROMPTS = [
    "a lighthouse on a cliff at sunset, oil painting",
    "a red fox sitting in fresh snow, photograph",
    "an isometric illustration of a small coffee shop",
    "a bowl of ramen on a wooden table, studio lighting",
    "a medieval castle reflected in a lake at dawn",
    "portrait of an elderly fisherman, charcoal drawing",
    "a futuristic city street in the rain at night, neon signs",
    "a vase of sunflowers on a windowsill, watercolor",
    "a mountain road winding through autumn forest, aerial view",
    "a cat wearing a tiny astronaut helmet, digital art",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--sampler", default="euler")
    ap.add_argument("--fractions", default="0.25,0.5,1.0")
    args = ap.parse_args()

    comfy_env.configure(())
    from trajver import manifest
    from trajver.attacks.forgeries import f1_copy, f2_interpolate, f3_invert, faked_steps
    from trajver.job import JobSpec, Pipeline, sha256_file
    from trajver.rules.e2w import adjacent_cosines, e2w
    from trajver.thresholds import DEV_DEFAULTS

    ckpt_sha = sha256_file(args.ckpt)
    d, m = manifest.start("dev", "w1-cosine", "Early look at hypothesis W1 on dev hardware (not paper data)",
                          models=[{"filename": Path(args.ckpt).name, "sha256": ckpt_sha}],
                          sampler=args.sampler, scheduler="normal", steps=args.steps, cfg=7.0, resolution="512x512",
                          prompt_set={"name": "dev_w1_inline", "n": args.n}, seeds=list(range(args.n)))
    pipe = Pipeline(args.ckpt, ckpt_sha)
    fractions = [float(x) for x in args.fractions.split(",")]
    rows, per_step = [], {}
    for j in range(args.n):
        spec = JobSpec(prompt=PROMPTS[j % len(PROMPTS)], negative="blurry, low quality", seed=j,
                       steps=args.steps, sampler=args.sampler)
        _, traj = pipe.run(spec)
        traj.save(d / "raw" / f"job{j:03d}" / "trajectory.safetensors")
        cos = adjacent_cosines(traj)
        for i, c in enumerate(cos):
            per_step.setdefault(i, []).append(c)
        replay = lambda states, sigmas, spec=spec: pipe.replay_denoised(spec, states, sigmas)  # noqa: E731
        cases = [("honest", None, traj)]
        for s in fractions:
            faked = faked_steps(traj.T, s, random.Random(1000 + j))
            cases += [("F1", s, f1_copy(traj, faked)), ("F2", s, f2_interpolate(traj, faked)),
                      ("F3", s, f3_invert(traj, faked, args.sampler))]
        for name, s, t in cases:
            v = e2w(t, args.steps, args.sampler, replay, DEV_DEFAULTS, seed=j, frames_dtype=pipe.model_dtype())
            rows.append({"job": j, "case": name, "s": s, "score": v.scores["score"], "accepted": v.passed,
                         "indices": v.scores.get("indices"), "similarities": v.scores.get("similarities")})
        print(f"job {j}: min adjacent cosine {min(cos):.4f}", flush=True)

    summary = {
        "note": "dev hardware, not paper data",
        "adjacent_cosine": {
            "min": min(min(v) for v in per_step.values()),
            "per_step": {i: {"min": min(v), "median": statistics.median(v), "max": max(v)} for i, v in per_step.items()},
        },
        "e2w_acceptance": {},
        "rows": rows,
    }
    for name in ("honest", "F1", "F2", "F3"):
        for s in ([None] if name == "honest" else fractions):
            sel = [r for r in rows if r["case"] == name and r["s"] == s]
            summary["e2w_acceptance"][f"{name}" + ("" if s is None else f"@s={s}")] = {
                "n": len(sel), "accepted": sum(r["accepted"] for r in sel),
                "min_score": min(r["score"] for r in sel)}
    manifest.finish(d, m, summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}["e2w_acceptance"], indent=1))
    print("adjacent cosine min:", summary["adjacent_cosine"]["min"])
    print("run:", d)


if __name__ == "__main__":
    main()
