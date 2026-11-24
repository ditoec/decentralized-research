"""Score a run (honest or attacked) with every trajectory evidence level (runbook §6 item 2).

  python -m trajver.verify RUN --ckpt CLAIMED.safetensors --prompts P [--thresholds thresholds_v1.json --th-sha256 H]

For each job in RUN (a ``pilot gen`` or ``attacks.run`` folder) it loads the committed trajectory and the
delivered image, rebuilds the claimed JobSpec from the run manifest, and computes on THIS node:
  E1    x_0, schedule, conditioning, decoded image
  E2-H  Tier A (all steps) + Tier B on ONE pass over all steps, from which the verdict for every
        k in {1,2,3,5,8} is derived with the step draw of ``draw_steps`` (commit-before-reveal logged)
  E2-W  the deployed SN30 rule (3 random steps)
and writes long-format rows ``job_id, attack, s, evidence, k, verdict, score`` to <new run>/verdicts.jsonl.
Ground-truth labels are NOT read here; the paper author joins them afterwards by job_id.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from . import comfy_env

KS = (1, 2, 3, 5, 8)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--flags", default="")
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--ckpt-sha256", default=None)
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--negative", default="")
    ap.add_argument("--thresholds", default=None)
    ap.add_argument("--th-sha256", default=None)
    ap.add_argument("--wp", default="wp3")
    ap.add_argument("--name", default=None)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args(argv)
    comfy_env.configure(a.flags.split())
    from PIL import Image

    from . import manifest
    from .job import JobSpec, Pipeline, sha256_file
    from .pilot import read_prompts
    from .rules.e1 import e1
    from .rules.e2h import draw_steps, tier_a, tier_b
    from .rules.e2w import e2w
    from .thresholds import load, tau_for
    from .trajectory import Trajectory

    src = Path(a.run)
    pm = json.loads((src / "manifest.json").read_text())
    th = load(a.thresholds, a.th_sha256)
    prompts = dict(read_prompts(a.prompts))
    claimed = pm.get("claimed") or {"steps": pm["steps"], "cfg": pm["cfg"], "sampler": pm["sampler"],
                                     "resolution": pm["resolution"]}
    if th.get("sampler") and th["sampler"] != claimed["sampler"]:
        raise SystemExit(f"thresholds are for {th['sampler']}, the run claims {claimed['sampler']}")
    res = int(claimed["resolution"].split("x")[0])
    sha = a.ckpt_sha256 or sha256_file(a.ckpt)
    d, m = manifest.start(a.wp, a.name or f"verify-{src.name.split('-', 2)[-1]}", "evidence levels E1, E2-H, E2-W",
                          rid=a.run_id, source_run=src.name, attack=pm.get("attack", "honest"),
                          threshold_file_sha256=th.get("_sha256"), thresholds_version=th.get("version"),
                          models=[{"filename": Path(a.ckpt).name, "sha256": sha}])
    pipe = Pipeline(a.ckpt, sha)
    jobs = [json.loads(l) for l in (src / "jobs.jsonl").read_text().splitlines() if l.strip()][: a.limit or None]
    out = open(d / "verdicts.jsonl", "a")
    log: list = []
    for r in jobs:
        traj = Trajectory.load(src / "raw" / "traj" / f"{r['job']}.safetensors")
        spec = JobSpec(prompt=prompts[r["prompt_id"]], negative=a.negative, seed=r["seed"], steps=claimed["steps"],
                       cfg=claimed["cfg"], sampler=claimed["sampler"], width=res, height=res)
        img = torch.from_numpy(np.asarray(Image.open(src / "raw" / "images" / f"{r['job']}.png")).copy())[None]
        base = {"job_id": r["job"], "attack": pm.get("attack", "honest"), "s": pm.get("actual", {}).get("s")}
        v1 = e1(traj, pipe, spec, img, th)
        out.write(json.dumps({**base, "evidence": "E1", "k": None, "verdict": v1.verdict,
                              "score": None, "reasons": v1.reasons}) + "\n")
        va = tier_a(traj, claimed["sampler"], th)
        out.write(json.dumps({**base, "evidence": "E2-H.tierA", "k": None, "verdict": va.verdict,
                              "score": va.scores.get("max_rel_l2"), "reasons": va.reasons}) + "\n")
        T = traj.T
        if T == claimed["steps"]:
            vb = tier_b(traj, lambda st, sg: pipe.replay_denoised(spec, st, sg), list(range(T)), th, log)
            per = vb.scores["per_step"]
            metric = th["tier_b_metric"]
            for k in KS:
                steps = draw_steps(T, k, f"{r['job']}|k{k}")
                bad = [i for i in steps if not per[str(i)][metric] <= tau_for(th, i)]
                tb = "fail" if bad else "pass"
                both = "fail" if ("fail" in (v1.verdict, va.verdict, tb)) else "pass"
                out.write(json.dumps({**base, "evidence": "E2-H", "k": k, "verdict": both,
                                      "score": max(per[str(i)][metric] for i in steps), "tier_b": tb,
                                      "steps": steps}) + "\n")
        else:
            for k in KS:
                out.write(json.dumps({**base, "evidence": "E2-H", "k": k, "verdict": "fail", "score": None,
                                      "reasons": ["step count differs from the claim"]}) + "\n")
        vw = e2w(traj, claimed["steps"], claimed["sampler"], lambda st, sg: pipe.replay_denoised(spec, st, sg), th,
                 seed=int(r["seed"]) + r["prompt_id"], frames_dtype=pipe.model_dtype())
        out.write(json.dumps({**base, "evidence": "E2-W", "k": 3, "verdict": vw.verdict,
                              "score": vw.scores.get("score")}) + "\n")
        out.flush()
        print(r["job"], "E1", v1.verdict, "A", va.verdict, "E2-W", vw.verdict, flush=True)
    out.close()
    (d / "logs" / "commit_reveal.jsonl").write_text("".join(json.dumps(x) + "\n" for x in log))
    rows = [json.loads(l) for l in (d / "verdicts.jsonl").read_text().splitlines() if l.strip()]
    summ = {}
    for rr in rows:
        key = rr["evidence"] + ("" if rr["k"] in (None,) else f"@k={rr['k']}")
        s = summ.setdefault(key, {"n": 0, "pass": 0})
        s["n"] += 1
        s["pass"] += rr["verdict"] == "pass"
    manifest.finish(d, m, {"acceptance": summ})
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
