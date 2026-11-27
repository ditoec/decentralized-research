"""Produce attacked jobs A1–A8, F1–F4 and M (runbook §3.3, §6) as commitments under the CLAIMED job.

One process = one attack configuration (ComfyUI flags and the checkpoint are fixed per process).

  python -m trajver.attacks.run --attack A1b --run-steps 20 --ckpt SDXL --prompts P --seeds 0 --name a1b-20
  python -m trajver.attacks.run --attack A3 --cheap-ckpt sd_xl_turbo_1.0_fp16.safetensors --run-steps 4 ...
  python -m trajver.attacks.run --flags=--fp8_e4m3fn-unet --attack A2 ...

Writes a run folder like ``pilot gen``: raw/images/<job>.png (the delivered image), raw/traj/<job>.safetensors
(the committed, claimed trajectory), jobs.jsonl (timing of what was really computed, for beta_A), and the
ground-truth labels in raw/labels/<job>.json, which verifiers never read.

Attacks
  A1a  run T' < T steps, commit the T'-step trajectory under the T-step claim (E1 schedule check).
  A1b  run T' steps, then FORGE the claimed T-step schedule: states re-labelled onto the claimed sigmas by
       log-sigma interpolation and every D_i re-solved so that Tier A passes (strongest variant).
  A2   fp8 UNet (--fp8_e4m3fn-unet in --flags), committed as if fp16 (F4 when the trajectory is complete).
  A3   distilled model (SDXL-Turbo or LCM-LoRA) for a few steps, forged onto the claimed schedule as A1b.
  A4   cheaper sampler (--cheap-sampler) committed as the required sampler, D_i re-solved for Tier A.
  A5   half resolution, image upscaled 2x (bicubic) for delivery; mainly an E0 attack.
  A6   early exit at step j = (1-s)T: the remaining states extrapolated and D re-solved (F3 with a tail pattern).
  A7   honest output of a near-duplicate prompt (<= 2 words changed).
  A8   honest output of an unrelated prompt and seed (control).
  F1-3 forgeries of an honest trajectory with skip fraction --s (random pattern).
  M    honest job, falsified metadata (GPU name and timing): a negative control.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import time
from dataclasses import replace
from pathlib import Path

import torch

from .. import comfy_env


def relabel_schedule(run_traj, claimed_sigmas: torch.Tensor, sampler: str):
    """Map a trajectory computed on a short schedule onto the claimed (longer) schedule.

    States at the claimed sigmas are interpolated between the computed states in log-sigma (linear in
    sigma on the last interval, which ends at sigma = 0). x_0 is kept (both schedules start at
    sigma_max), the final state is kept, and every D_i is re-solved so the solver maps x_i to x_{i+1}.
    """
    from ..solvers import solve_D
    from ..trajectory import Trajectory

    s_run = [float(v) for v in run_traj.sigmas]
    states = [run_traj.state(j) for j in range(run_traj.T + 1)]
    out_states = []
    for S in [float(v) for v in claimed_sigmas]:
        if S >= s_run[0]:
            out_states.append(states[0].clone())
            continue
        if S <= 0.0:
            out_states.append(states[-1].clone())
            continue
        k = max(j for j in range(len(s_run) - 1) if s_run[j] >= S)
        a, b = s_run[k], s_run[k + 1]
        if b > 0:
            w = (math.log(a) - math.log(S)) / (math.log(a) - math.log(b))
        else:
            w = (a - S) / a
        out_states.append(((1 - w) * states[k].double() + w * states[k + 1].double()).to(states[k].dtype))
    T = len(claimed_sigmas) - 1
    t = Trajectory(sigmas=claimed_sigmas.clone(), xs=out_states[:T], Ds=[run_traj.Ds[0].clone()] * T,
                   x_final=out_states[T], conds=dict(run_traj.conds))
    for i in range(T):
        t.Ds[i] = solve_D(t, i, sampler, t.state(i + 1))
    return t


def resolve_all_D(traj, sampler: str):
    """Re-solve every D_i for ``sampler`` (attack A4: committed as the required sampler)."""
    from ..solvers import solve_D

    t = traj.clone()
    for i in range(t.T):
        t.Ds[i] = solve_D(t, i, sampler, t.state(i + 1))
    return t


def near_duplicate(prompt: str, rng: random.Random) -> str:
    """Change at most two words: drop one and swap two neighbours (A7)."""
    w = prompt.split()
    if len(w) >= 3:
        del w[rng.randrange(len(w))]
        j = rng.randrange(len(w) - 1)
        w[j], w[j + 1] = w[j + 1], w[j]
    elif w:
        w.append("photo")
    return " ".join(w)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--flags", default="")
    ap.add_argument("--attack", required=True,
                    choices=["A1a", "A1b", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "F1", "F2", "F3", "M"])
    ap.add_argument("--ckpt", required=True, help="the CLAIMED model")
    ap.add_argument("--ckpt-sha256", default=None)
    ap.add_argument("--cheap-ckpt", default=None, help="A3: distilled checkpoint actually run")
    ap.add_argument("--lora", default=None, help="A3: LCM-LoRA applied to --ckpt instead of --cheap-ckpt")
    ap.add_argument("--run-steps", type=int, default=None, help="A1/A3: steps actually run")
    ap.add_argument("--run-cfg", type=float, default=None, help="A3: cfg actually used (Turbo: 0 -> 1.0)")
    ap.add_argument("--cheap-sampler", default="euler", help="A4: sampler actually run")
    ap.add_argument("--s", type=float, default=0.5, help="F1-F3, A6: fraction of faked steps")
    ap.add_argument("--forger", choices=["transform", "realistic"], default="transform",
                    help="F1-F3: 'transform' edits an honest trajectory (WP3 of 2026-11-26); 'realistic' runs the model "
                         "only at computed steps from its own states (forgeries.realistic_euler; Euler only)")
    ap.add_argument("--pair-honest", action="store_true",
                    help="also time an honest generation of the same claimed job in this process (beta_A on one "
                         "timer; order alternates per job). Not for A2, whose flags change the whole process")
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--seeds", default="0")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--cfg", type=float, default=7.0)
    ap.add_argument("--sampler", default="euler")
    ap.add_argument("--res", default="1024")
    ap.add_argument("--negative", default="")
    ap.add_argument("--wp", default="wp3")
    ap.add_argument("--name", required=True)
    ap.add_argument("--run-id", default=None)
    a = ap.parse_args(argv)
    comfy_env.configure(a.flags.split())

    from .. import manifest
    from ..job import JobSpec, Pipeline, sha256_file
    from ..pilot import read_prompts, save_png, sync
    from .forgeries import f1_copy, f2_interpolate, f3_invert, faked_steps, realistic_euler, write_labels
    if a.pair_honest and a.attack == "A2":
        raise SystemExit("--pair-honest: A2's flags apply to the whole process, so its honest pair would not be "
                         "honest; time A2 against a pilot gen run on the same card (t_sample_s)")
    if a.forger == "realistic" and a.sampler != "euler":
        raise SystemExit("--forger realistic implements the Euler sampler only")

    prompts = read_prompts(a.prompts)[: a.limit or None]
    all_prompts = read_prompts(a.prompts)
    seeds = [int(x) for x in a.seeds.split(",")]
    res = int(a.res)
    sha = a.ckpt_sha256 or sha256_file(a.ckpt)
    d, m = manifest.start(a.wp, a.name, f"attack {a.attack}", rid=a.run_id,
                          models=[{"filename": Path(a.ckpt).name, "sha256": sha}], attack=a.attack,
                          claimed={"steps": a.steps, "cfg": a.cfg, "sampler": a.sampler, "resolution": f"{res}x{res}"},
                          actual={"flags": a.flags, "cheap_ckpt": a.cheap_ckpt and Path(a.cheap_ckpt).name,
                                  "lora": a.lora and Path(a.lora).name, "run_steps": a.run_steps,
                                  "cheap_sampler": a.cheap_sampler, "s": a.s,
                                  "forger": a.forger, "pair_honest": a.pair_honest},
                          seeds=seeds, prompt_set={"file": Path(a.prompts).name, "n": len(prompts)})
    pipe = Pipeline(a.ckpt, sha)  # the claimed model: its CLIP gives the claimed conditioning, its VAE decodes
    cheap = None
    if a.attack == "A3":
        if a.cheap_ckpt:
            cheap = Pipeline(a.cheap_ckpt)
        elif a.lora:
            import comfy.sd
            import comfy.utils

            cheap = Pipeline(a.ckpt, sha)
            lora = comfy.utils.load_torch_file(a.lora, safe_load=True)
            cheap.model, cheap.clip = comfy.sd.load_lora_for_models(cheap.model, cheap.clip, lora, 1.0, 1.0)
        else:
            raise SystemExit("A3 needs --cheap-ckpt or --lora")
    rows_path = d / "jobs.jsonl"
    done = {json.loads(l)["job"] for l in rows_path.read_text().splitlines() if l.strip()} if rows_path.exists() else set()
    rng = random.Random(20261124)
    njob = len(done)
    with open(rows_path, "a") as rows:
        for pid, prompt in prompts:
            for seed in seeds:
                key = f"p{pid:05d}_s{seed}"
                if key in done:
                    continue
                claimed = JobSpec(prompt=prompt, negative=a.negative, seed=seed, steps=a.steps, cfg=a.cfg,
                                  sampler=a.sampler, width=res, height=res)
                label: dict = {"claimed": claimed.to_dict()}
                njob += 1
                tt = {"sample": 0.0}

                def G(fn, *args, **kw):  # time a generation call (sampling incl. trajectory capture), as pilot gen
                    sync()
                    t = time.perf_counter()
                    out = fn(*args, **kw)
                    sync()
                    tt["sample"] += time.perf_counter() - t
                    return out

                def honest_pair() -> float:
                    sync()
                    t = time.perf_counter()
                    pipe.run(claimed)
                    sync()
                    return time.perf_counter() - t

                honest_first = a.pair_honest and njob % 2 == 0
                t_honest = honest_pair() if honest_first else None
                sync()
                t0 = time.perf_counter()
                img = None
                if a.attack in ("A1a", "A1b"):
                    run = replace(claimed, steps=a.run_steps)
                    samples, traj = G(pipe.run, run)
                    if a.attack == "A1b":
                        traj = relabel_schedule(traj, pipe.schedule(claimed), a.sampler)
                elif a.attack == "A3":
                    assert cheap is not None
                    run = replace(claimed, steps=a.run_steps, cfg=a.run_cfg if a.run_cfg is not None else claimed.cfg)
                    samples, traj = G(cheap.run, run)
                    traj = relabel_schedule(traj, pipe.schedule(claimed), a.sampler)
                elif a.attack == "A4":
                    samples, traj = G(pipe.run, replace(claimed, sampler=a.cheap_sampler))
                    traj.sigmas = pipe.schedule(claimed)
                    traj = resolve_all_D(traj, a.sampler)
                elif a.attack == "A5":
                    half = replace(claimed, width=res // 2, height=res // 2)
                    samples, traj = G(pipe.run, half)
                    small = pipe.decode(samples)
                    img = torch.nn.functional.interpolate(small.permute(0, 3, 1, 2), scale_factor=2, mode="bicubic",
                                                          align_corners=False).clamp(0, 1).permute(0, 2, 3, 1)
                elif a.attack == "A6":
                    samples, traj = G(pipe.run, claimed)
                    faked = faked_steps(traj.T, a.s, rng, pattern="tail")
                    traj = f3_invert(traj, faked, a.sampler)
                    label["faked"] = faked
                elif a.attack == "A7":
                    other = near_duplicate(prompt, rng)
                    samples, traj = G(pipe.run, replace(claimed, prompt=other))
                    label["actual_prompt"] = other
                elif a.attack == "A8":
                    opid, oprompt = rng.choice([x for x in all_prompts if x[0] != pid])
                    samples, traj = G(pipe.run, replace(claimed, prompt=oprompt, seed=seed + 1000))
                    label["actual_prompt_id"] = opid
                elif a.attack in ("F1", "F2", "F3") and a.forger == "realistic":
                    faked = faked_steps(a.steps, a.s, rng)
                    samples, traj = G(pipe.run, claimed, sampler_function=realistic_euler(a.attack, faked))
                    label["faked"] = faked
                    label["forger"] = "realistic"
                elif a.attack in ("F1", "F2", "F3"):
                    samples, traj = G(pipe.run, claimed)
                    faked = faked_steps(traj.T, a.s, rng)
                    traj = {"F1": f1_copy(traj, faked), "F2": f2_interpolate(traj, faked),
                            "F3": f3_invert(traj, faked, a.sampler)}[a.attack]
                    label["faked"] = faked
                else:  # A2 (flags), M
                    samples, traj = G(pipe.run, claimed)
                sync()
                sync()
                t_compute = time.perf_counter() - t0
                td0 = time.perf_counter()
                if img is None:
                    if a.attack in ("A1b", "A3", "A4", "A6", "F1", "F2", "F3"):
                        # deliver the image of the committed final state, so E1(c) is consistent
                        samples = pipe.model.model.process_latent_out(traj.x_final.float().to(pipe.model.load_device)).cpu()
                    img = pipe.decode(samples)
                sync()
                t_decode = time.perf_counter() - td0
                if a.pair_honest and not honest_first:
                    t_honest = honest_pair()
                traj.job = pipe.job_record(claimed)
                if a.attack == "M":
                    traj.job["device"] = "NVIDIA GeForce RTX 5090 (claimed)"
                    label["falsified"] = {"device": traj.job["device"]}
                # t_sample_s: generation calls only (same field as pilot gen's t_sample_s); t_forge_s: the rest of
                # the attack before decoding (schedule relabelling, D re-solving, trajectory edits)
                row = {"job": key, "prompt_id": pid, "seed": seed, "attack": a.attack, "t_compute_s": t_compute,
                       "t_sample_s": tt["sample"], "t_forge_s": t_compute - tt["sample"], "t_decode_s": t_decode,
                       **({"t_honest_sample_s": t_honest, "honest_first": honest_first} if a.pair_honest else {}),
                       "image_sha256": save_png(Pipeline.to_uint8(img), d / "raw" / "images" / f"{key}.png"),
                       "merkle_root": traj.save(d / "raw" / "traj" / f"{key}.safetensors")}
                (d / "raw" / "labels").mkdir(exist_ok=True)
                write_labels(d / "raw" / "labels" / f"{key}.json", key, a.attack, a.s, label.get("faked", []), label)
                rows.write(json.dumps(row) + "\n")
                rows.flush()
                print(key, a.attack, f"{t_compute:.2f}s", flush=True)
    allr = [json.loads(l) for l in rows_path.read_text().splitlines() if l.strip()]
    ts = sorted(r["t_compute_s"] for r in allr[1:] or allr)
    manifest.finish(d, m, {"n_jobs": len(allr), "t_compute_median_s": ts[len(ts) // 2],
                           "labels_sha256": hashlib.sha256(b"".join(
                               p.read_bytes() for p in sorted((d / "raw" / "labels").glob("*.json")))).hexdigest()})
    print(d)


if __name__ == "__main__":
    main()
