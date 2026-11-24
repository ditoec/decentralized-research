"""Pilot measurements P1–P7 (runbook §2) and the generic generation workload they share.

One process = one ComfyUI configuration (flags are parsed once). Subcommands:

  noise    P1: sha256 and raw bytes of the initial noise for seeds 0..N-1, SD1.5 and SDXL shapes
  gen      generate jobs from a prompt file x seeds; save images (+ trajectories), per-job time,
           memory peaks and co-tenant load. Used by P2, P3, P4, P6, P7 and the RQ1 grid.
           Resumable: jobs whose outputs exist are skipped (Spark runner restarts).
  w1       P5: honest trajectories + E2-W on honest and F1–F3 (as tools/dev_w1.py, any model)
  fp4      P4: does the NVFP4 path of the pinned commit run on this GPU?
  compare  two gen runs -> pixel equality, per-pixel difference, per-step D_i distances
  noisecmp two noise runs -> identical count and max ULP difference per shape

    python -m trajver.pilot gen --ckpt sd_xl_base_1.0.safetensors --prompts prompts_pilot20.txt \
        --seeds 0,1 --res 1024 --name p2-spark4-a --save-traj

All outputs go to $TRAJVER_RUNS/<run_id>/ (default experiments/runs/).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import statistics
import sys
import threading
import time
from pathlib import Path

import torch

from . import comfy_env

SHAPES = {"sd15": (1, 4, 64, 64), "sdxl": (1, 4, 128, 128)}


# ------------------------------------------------------------------------------------ helpers
def read_prompts(path: str | Path) -> list[tuple[int, str]]:
    out = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            i, p = line.split("\t", 1)
            out.append((int(i), p))
    return out


def meminfo() -> dict:
    """Host memory from /proc/meminfo (in a container this is the host's, which is what matters
    on the Spark's shared pool). Values in GB."""
    out = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            if k in ("MemTotal", "MemAvailable", "MemFree"):
                out[k] = int(v.split()[0]) / 1e6
    except OSError:
        pass
    return out


class MemSampler:
    """Samples host MemAvailable every 0.5 s; reports the minimum seen."""

    def __init__(self):
        self.min_avail = None
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            a = meminfo().get("MemAvailable")
            if a is not None:
                self.min_avail = a if self.min_avail is None else min(self.min_avail, a)
            self._stop.wait(0.5)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join()
        return False


def sync():
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    elif torch.backends.mps.is_available():
        torch.mps.synchronize()


def cotenant_snapshot() -> dict | None:
    """Co-tenant load written by the Spark runner (it can see docker and Prometheus; we can't)."""
    p = os.environ.get("TRAJVER_COTENANT_FILE")
    if p and Path(p).exists():
        try:
            return json.loads(Path(p).read_text())
        except Exception:
            return None
    return None


def save_png(img_uint8: torch.Tensor, path: Path) -> str:
    from PIL import Image

    arr = img_uint8[0].numpy() if img_uint8.ndim == 4 else img_uint8.numpy()
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(path, compress_level=4)
    return hashlib.sha256(arr.tobytes()).hexdigest()


def pctl(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, round(q * (len(xs) - 1))))]


# ------------------------------------------------------------------------------------ P1 noise
def cmd_noise(a):
    from . import manifest
    from .noise import initial_noise

    d, m = manifest.start(a.wp, a.name, "P1: initial noise bytes across CPU ISAs", rid=a.run_id,
                          seeds=list(range(a.seeds)), shapes=SHAPES)
    out = {}
    for name, shape in SHAPES.items():
        blobs = []
        out[name] = []
        for s in range(a.seeds):
            b = initial_noise(shape, s).numpy().tobytes()
            blobs.append(b)
            out[name].append(hashlib.sha256(b).hexdigest())
        (d / "raw" / f"noise_{name}.bin").write_bytes(b"".join(blobs))
    manifest.finish(d, m, {"digests": out})
    print(d)


def cmd_noisecmp(a):
    import numpy as np

    ra, rb = Path(a.run_a), Path(a.run_b)
    sa, sb = json.loads((ra / "summary.json").read_text()), json.loads((rb / "summary.json").read_text())
    res = {}
    for name, shape in SHAPES.items():
        da, db = sa["digests"][name], sb["digests"][name]
        n = min(len(da), len(db))
        res[name] = {"n_seeds": n, "n_identical": sum(x == y for x, y in zip(da[:n], db[:n]))}
        fa, fb = ra / "raw" / f"noise_{name}.bin", rb / "raw" / f"noise_{name}.bin"
        if fa.exists() and fb.exists():
            va = np.frombuffer(fa.read_bytes(), dtype=np.float32)
            vb = np.frombuffer(fb.read_bytes(), dtype=np.float32)
            k = min(len(va), len(vb))
            ulp = np.abs(va[:k].view(np.int32).astype(np.int64) - vb[:k].view(np.int32).astype(np.int64))
            res[name].update(max_ulp=int(ulp.max()), frac_values_equal=float((ulp == 0).mean()),
                             max_abs=float(np.abs(va[:k] - vb[:k]).max()))
    out = {"a": sa.get("node", ra.name), "b": rb.name, "result": res}
    print(json.dumps(out, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1))


# ------------------------------------------------------------------------------------ gen
def _job_key(pid: int, seed: int) -> str:
    return f"p{pid:05d}_s{seed}"


def cmd_gen(a):
    if a.no_pin:
        comfy_env.PIN_BATCHING = False
    from . import manifest
    from .job import JobSpec, Pipeline, sha256_file

    prompts = read_prompts(a.prompts)[: a.limit or None]
    seeds = [int(s) for s in a.seeds.split(",")]
    w, h = (int(x) for x in a.res.split("x")) if "x" in a.res else (int(a.res), int(a.res))
    ckpt_sha = a.ckpt_sha256 or sha256_file(a.ckpt)
    d, m = manifest.start(
        a.wp, a.name, a.purpose, rid=a.run_id,
        models=[{"filename": Path(a.ckpt).name, "sha256": ckpt_sha}],
        sampler=a.sampler, scheduler=a.scheduler, steps=a.steps, cfg=a.cfg, resolution=f"{w}x{h}",
        precision_flags=list(comfy_env.configured_flags() or ()), pin_batching=comfy_env.PIN_BATCHING,
        prompt_set={"file": Path(a.prompts).name, "sha256": hashlib.sha256(Path(a.prompts).read_bytes()).hexdigest(),
                    "n": len(prompts)},
        seeds=seeds, save_traj=a.save_traj)
    rows_path = d / "jobs.jsonl"
    done = set()
    if rows_path.exists():
        done = {json.loads(l)["job"] for l in rows_path.read_text().splitlines() if l.strip()}
    mem_before_load = meminfo().get("MemAvailable")
    t_load = time.perf_counter()
    pipe = Pipeline(a.ckpt, ckpt_sha)
    load_s = time.perf_counter() - t_load
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    jobs = [(pid, p, s) for pid, p in prompts for s in seeds]
    ran = 0
    with MemSampler() as ms, open(rows_path, "a") as rows:
        for n, (pid, prompt, seed) in enumerate(jobs):
            key = _job_key(pid, seed)
            if key in done:
                continue
            spec = JobSpec(prompt=prompt, negative=a.negative, seed=seed, steps=a.steps, cfg=a.cfg,
                           sampler=a.sampler, scheduler=a.scheduler, width=w, height=h)
            co = cotenant_snapshot()
            sync()
            t0 = time.perf_counter()
            if a.save_traj:
                samples, traj = pipe.run(spec)
            else:
                samples, traj = pipe.run_stock(spec), None
            sync()
            t1 = time.perf_counter()
            img = Pipeline.to_uint8(pipe.decode(samples))
            sync()
            t2 = time.perf_counter()
            row = {"job": key, "prompt_id": pid, "seed": seed, "t_sample_s": t1 - t0, "t_decode_s": t2 - t1,
                   "t_total_s": t2 - t0, "image_sha256": save_png(img, d / "raw" / "images" / f"{key}.png"),
                   "latent_sha256": hashlib.sha256(samples.float().cpu().numpy().tobytes()).hexdigest(),
                   "mem_available_gb": meminfo().get("MemAvailable"), "cotenants": co,
                   "time": time.time()}
            if traj is not None:
                row["merkle_root"] = traj.save(d / "raw" / "traj" / f"{key}.safetensors")
            rows.write(json.dumps(row) + "\n")
            rows.flush()
            ran += 1
            print(f"[{n + 1}/{len(jobs)}] {key} {row['t_total_s']:.2f}s", flush=True)
        min_avail = ms.min_avail
    all_rows = [json.loads(l) for l in rows_path.read_text().splitlines() if l.strip()]
    times = [r["t_total_s"] for r in all_rows[1:]] or [r["t_total_s"] for r in all_rows]  # first job = warm-up
    summary = {
        "n_jobs": len(all_rows), "model_load_s": load_s,
        "time_per_image_s": {"median": statistics.median(times), "p95": pctl(times, 0.95), "min": min(times),
                             "max": max(times), "n": len(times), "note": "warm; first job excluded"},
        "memory": {
            # host-level: the drop in MemAvailable from before the model load to the lowest point of the run.
            # On a DGX Spark (unified memory) this is what production feels; it includes co-tenant changes.
            "host_available_before_load_gb": mem_before_load,
            "host_drop_gb": (mem_before_load - min_avail) if (mem_before_load and min_avail) else None,
            "torch_peak_allocated_gb": torch.cuda.max_memory_allocated() / 1e9 if torch.cuda.is_available() else None,
            "torch_peak_reserved_gb": torch.cuda.max_memory_reserved() / 1e9 if torch.cuda.is_available() else None,
            "process_peak_rss_gb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1e6 if sys.platform != "darwin" else 1e9),
            "host_min_available_gb": min_avail, "host_total_gb": meminfo().get("MemTotal"),
        },
    }
    prev = d / "summary.json"
    if ran == 0 and prev.exists():  # a resumed process that did no work must not overwrite the measurements
        summary["memory"] = json.loads(prev.read_text()).get("memory", summary["memory"])
    summary["memory"]["measured_in_process_with_jobs"] = ran
    manifest.finish(d, m, summary)
    print(json.dumps(summary, indent=1))
    print(d)


# ------------------------------------------------------------------------------------ compare
def _load_rows(run: Path) -> dict[str, dict]:
    return {r["job"]: r for r in (json.loads(l) for l in (run / "jobs.jsonl").read_text().splitlines() if l.strip())}


def cmd_compare(a):
    import numpy as np
    from PIL import Image

    from .solvers import residual
    from .trajectory import Trajectory

    ra, rb = Path(a.run_a), Path(a.run_b)
    A, B = _load_rows(ra), _load_rows(rb)
    common = sorted(set(A) & set(B))
    per, e0rows = [], []
    step_rel, step_max = {}, {}
    for k in common:
        r = {"job": k, "image_equal": A[k]["image_sha256"] == B[k]["image_sha256"],
             "latent_equal": A[k]["latent_sha256"] == B[k]["latent_sha256"]}
        if "merkle_root" in A[k] and "merkle_root" in B[k]:
            r["root_equal"] = A[k]["merkle_root"] == B[k]["merkle_root"]
        if not r["image_equal"]:
            ia = np.asarray(Image.open(ra / "raw" / "images" / f"{k}.png"), dtype=np.int16)
            ib = np.asarray(Image.open(rb / "raw" / "images" / f"{k}.png"), dtype=np.int16)
            diff = np.abs(ia - ib)
            r.update(px_max=int(diff.max()), px_mean=float(diff.mean()), px_frac_equal=float((diff == 0).mean()))
        else:
            r.update(px_max=0, px_mean=0.0, px_frac_equal=1.0)
        ta, tb = ra / "raw" / "traj" / f"{k}.safetensors", rb / "raw" / "traj" / f"{k}.safetensors"
        if a.steps_detail and ta.exists() and tb.exists() and not r.get("root_equal", False):
            Ta, Tb = Trajectory.load(ta), Trajectory.load(tb)
            for i in range(min(Ta.T, Tb.T)):
                res = residual(Ta.Ds[i], Tb.Ds[i])
                step_rel.setdefault(i, []).append(res["rel_l2"])
                step_max.setdefault(i, []).append(res["max_abs"])
            r["x0_equal"] = bool(torch.equal(Ta.xs[0], Tb.xs[0]))
            r["first_D_diff_step"] = next((i for i in range(min(Ta.T, Tb.T)) if not torch.equal(Ta.Ds[i], Tb.Ds[i])), None)
        if a.e0_out:
            from .rules import e0 as E0
            from .rules import e0n as E0N

            ia_t = torch.from_numpy(np.asarray(Image.open(ra / "raw" / "images" / f"{k}.png")).copy())
            ib_t = torch.from_numpy(np.asarray(Image.open(rb / "raw" / "images" / f"{k}.png")).copy())
            sc = E0.scores(ia_t, ib_t, with_models=True)
            v = E0N.e0n(ia_t, ib_t)
            e0rows.append({"job": k, "prompt_id": A[k]["prompt_id"], **sc, "e0n": v.scores, "e0n_pass": v.passed})
        per.append(r)
    if a.e0_out:
        Path(a.e0_out).write_text("".join(json.dumps(x, default=float) + "\n" for x in e0rows))
    n = len(per)
    summary = {
        "run_a": ra.name, "run_b": rb.name, "n_pairs": n,
        "frac_image_identical": sum(r["image_equal"] for r in per) / n if n else None,
        "frac_latent_identical": sum(r["latent_equal"] for r in per) / n if n else None,
        "frac_root_identical": (sum(r.get("root_equal", False) for r in per) / n) if n and "root_equal" in per[0] else None,
        "px_absdiff_median_of_means": statistics.median(r["px_mean"] for r in per) if n else None,
        "px_absdiff_max": max(r["px_max"] for r in per) if n else None,
        "per_step_D": {i: {"rel_l2_median": statistics.median(v), "rel_l2_max": max(v),
                           "max_abs_max": max(step_max[i])} for i, v in step_rel.items()},
        "pairs": per,
    }
    txt = json.dumps(summary, indent=1)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(txt)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("pairs", "per_step_D")}, indent=1))


# ------------------------------------------------------------------------------------ replay
def cmd_replay(a):
    """Verifier side of RQ1 (runbook §4 item 3, §5 item 2): load a provider's honest trajectories
    from a gen run, replay D_i at EVERY step on this node, and record per-step Tier B distances and
    Tier A residuals. One pass gives the data for every k."""
    from . import manifest
    from .job import JobSpec, Pipeline, sha256_file
    from .solvers import residual, tier_a_residuals
    from .trajectory import Trajectory

    src = Path(a.provider_run)
    pm = json.loads((src / "manifest.json").read_text())
    rows_src = [json.loads(l) for l in (src / "jobs.jsonl").read_text().splitlines() if l.strip()]
    prompts = dict(read_prompts(a.prompts))
    ckpt_sha = a.ckpt_sha256 or sha256_file(a.ckpt)
    if ckpt_sha != pm["models"][0]["sha256"]:
        raise SystemExit("verifier model differs from the provider's")
    w, h = (int(x) for x in pm["resolution"].split("x"))
    d, m = manifest.start(a.wp, a.name, "verifier replay of every step (Tier B distances, Tier A residuals)",
                          rid=a.run_id, provider_run=src.name, provider_node=pm.get("node"),
                          models=pm["models"], sampler=pm["sampler"], steps=pm["steps"], cfg=pm["cfg"],
                          resolution=pm["resolution"], pin_batching=comfy_env.PIN_BATCHING)
    out_path = d / "jobs.jsonl"
    done = {json.loads(l)["job"] for l in out_path.read_text().splitlines() if l.strip()} if out_path.exists() else set()
    pipe = Pipeline(a.ckpt, ckpt_sha)
    with open(out_path, "a") as out:
        for r in rows_src[: a.limit or None]:
            if r["job"] in done or r["prompt_id"] not in prompts:
                continue
            traj = Trajectory.load(src / "raw" / "traj" / f"{r['job']}.safetensors")
            spec = JobSpec(prompt=prompts[r["prompt_id"]], negative=a.negative, seed=r["seed"], steps=pm["steps"],
                           cfg=pm["cfg"], sampler=pm["sampler"], scheduler=pm.get("scheduler", "normal"),
                           width=w, height=h)
            t0 = time.perf_counter()
            D_hat = pipe.replay_denoised(spec, {i: traj.xs[i] for i in range(traj.T)}, traj.sigmas)
            t_rep = time.perf_counter() - t0
            steps = []
            for i in range(traj.T):
                res = residual(D_hat[i], traj.Ds[i])
                res["exact"] = bool(torch.equal(D_hat[i].to(traj.Ds[i].dtype), traj.Ds[i]))
                steps.append(res)
            ta = tier_a_residuals(traj, pm["sampler"])
            row = {"job": r["job"], "prompt_id": r["prompt_id"], "seed": r["seed"], "t_replay_all_s": t_rep,
                   "tier_b": steps, "tier_a": [{"rel_l2": x["rel_l2"], "max_abs": x["max_abs"],
                                                "replica_exact": x["replica_exact"]} for x in ta]}
            out.write(json.dumps(row) + "\n")
            out.flush()
            print(r["job"], "max rel_l2 %.3g" % max(s["rel_l2"] for s in steps), flush=True)
    rows = [json.loads(l) for l in out_path.read_text().splitlines() if l.strip()]
    allb = [s for r in rows for s in r["tier_b"]]
    summary = {"n_jobs": len(rows), "frac_steps_exact": sum(s["exact"] for s in allb) / max(1, len(allb)),
               "tier_b_rel_l2_max": max((s["rel_l2"] for s in allb), default=None),
               "tier_a_rel_l2_max": max((x["rel_l2"] for r in rows for x in r["tier_a"]), default=None),
               "tier_a_replica_exact_frac": sum(x["replica_exact"] for r in rows for x in r["tier_a"])
               / max(1, sum(len(r["tier_a"]) for r in rows))}
    manifest.finish(d, m, summary)
    print(json.dumps(summary, indent=1))


# ------------------------------------------------------------------------------------ P5 W1
def cmd_w1(a):
    import random

    from . import manifest
    from .attacks.forgeries import f1_copy, f2_interpolate, f3_invert, faked_steps
    from .job import JobSpec, Pipeline, sha256_file
    from .rules.e2w import adjacent_cosines, e2w
    from .thresholds import DEV_DEFAULTS

    prompts = read_prompts(a.prompts)[: a.n]
    w, h = (int(a.res), int(a.res))
    ckpt_sha = a.ckpt_sha256 or sha256_file(a.ckpt)
    fractions = [float(x) for x in a.fractions.split(",")]
    d, m = manifest.start(a.wp, a.name, "P5: hypothesis W1 (adjacent-state cosine) and E2-W on F1-F3", rid=a.run_id,
                          models=[{"filename": Path(a.ckpt).name, "sha256": ckpt_sha}], sampler=a.sampler,
                          scheduler="normal", steps=a.steps, cfg=a.cfg, resolution=f"{w}x{h}",
                          prompt_set={"file": Path(a.prompts).name, "n": len(prompts)}, seeds=[0])
    pipe = Pipeline(a.ckpt, ckpt_sha)
    rows, per_step = [], {}
    for j, (pid, prompt) in enumerate(prompts):
        spec = JobSpec(prompt=prompt, negative=a.negative, seed=j, steps=a.steps, cfg=a.cfg, sampler=a.sampler,
                       width=w, height=h)
        _, traj = pipe.run(spec)
        cos = adjacent_cosines(traj)
        for i, c in enumerate(cos):
            per_step.setdefault(i, []).append(c)
        replay = lambda states, sigmas, spec=spec: pipe.replay_denoised(spec, states, sigmas)  # noqa: E731
        cases = [("honest", None, traj)]
        for s in fractions:
            faked = faked_steps(traj.T, s, random.Random(1000 + j))
            cases += [("F1", s, f1_copy(traj, faked)), ("F2", s, f2_interpolate(traj, faked)),
                      ("F3", s, f3_invert(traj, faked, a.sampler))]
        for name, s, t in cases:
            v = e2w(t, a.steps, a.sampler, replay, DEV_DEFAULTS, seed=j, frames_dtype=pipe.model_dtype())
            rows.append({"prompt_id": pid, "case": name, "s": s, "score": v.scores["score"], "accepted": v.passed})
        print(f"job {j}: min adjacent cosine {min(cos):.5f}", flush=True)
    acc = {}
    for name in ("honest", "F1", "F2", "F3"):
        for s in ([None] if name == "honest" else fractions):
            sel = [r for r in rows if r["case"] == name and r["s"] == s]
            acc[name + ("" if s is None else f"@s={s}")] = {"n": len(sel), "accepted": sum(r["accepted"] for r in sel),
                                                           "min_score": min(r["score"] for r in sel)}
    allc = [c for v in per_step.values() for c in v]
    summary = {"adjacent_cosine": {"min": min(allc), "median": statistics.median(allc), "max": max(allc),
                                   "per_step": {i: {"min": min(v), "median": statistics.median(v), "max": max(v)}
                                                for i, v in per_step.items()}},
               "w1_holds_min_ge_0.70": min(allc) >= 0.70, "e2w_acceptance": acc, "rows": rows}
    manifest.finish(d, m, summary)
    print(json.dumps(acc, indent=1))
    print("adjacent cosine min/median/max:", summary["adjacent_cosine"]["min"], summary["adjacent_cosine"]["median"],
          summary["adjacent_cosine"]["max"])
    print(d)


# ------------------------------------------------------------------------------------ P4 fp4
def cmd_fp4(a):
    """Probe the NVFP4 path of the pinned commit: quantize a weight with comfy_kitchen and run a
    linear layer through comfy.quant_ops on this GPU. Reports works/fails and the error."""
    from . import manifest

    d, m = manifest.start(a.wp, a.name, "P4: NVFP4 feasibility at the pinned commit", rid=a.run_id)
    res = {}
    try:
        import comfy.quant_ops as qo
        import comfy_kitchen as ck

        dev = "cuda"
        w = torch.randn(1280, 1280, device=dev, dtype=torch.bfloat16)
        x = torch.randn(64, 1280, device=dev, dtype=torch.bfloat16)
        res["comfy_kitchen"] = getattr(ck, "__version__", "?")
        res["backends"] = {k: str(v) for k, v in ck.list_backends().items()}
        qdata, params = qo.TensorCoreNVFP4Layout.quantize(w)
        qt = qo.QuantizedTensor(qdata, "TensorCoreNVFP4Layout", params)
        res["quantize"] = "ok"
        lin = torch.nn.functional.linear
        y = lin(x, qt)  # type: ignore[arg-type]
        ref = lin(x, w)
        res["linear"] = "ok"
        res["rel_err_vs_bf16"] = float((y.float() - ref.float()).norm() / ref.float().norm())
        for _ in range(5):
            lin(x, qt), lin(x, w)  # type: ignore[arg-type]
        sync()
        t0 = time.perf_counter()
        for _ in range(200):
            lin(x, qt)  # type: ignore[arg-type]
        sync()
        t1 = time.perf_counter()
        for _ in range(200):
            lin(x, w)
        sync()
        res["fp4_linear_ms"] = (t1 - t0) / 200 * 1e3
        res["bf16_linear_ms"] = (time.perf_counter() - t1) / 200 * 1e3
        res["speedup_vs_bf16"] = res["bf16_linear_ms"] / res["fp4_linear_ms"]
        res["note"] = ("comfy_kitchen dequantizes and falls back when no fp4 kernel exists; a speed-up "
                       "below 1 with a small error means the fallback ran, not an fp4 kernel")
        res["works"] = res.get("linear") == "ok"
    except Exception as e:  # report, don't hide
        res["works"] = False
        res["error"] = f"{type(e).__name__}: {e}"
    manifest.finish(d, m, res)
    print(json.dumps(res, indent=1))


# ------------------------------------------------------------------------------------ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m trajver.pilot")
    ap.add_argument("--flags", default="", help="ComfyUI CLI flags for this process, space separated")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, needs_model=True):
        p.add_argument("--wp", default="wp0b")
        p.add_argument("--name", required=True)
        p.add_argument("--run-id", default=None, help="fixed run id (resume)")
        if needs_model:
            p.add_argument("--ckpt", required=True)
            p.add_argument("--ckpt-sha256", default=None)
            p.add_argument("--prompts", required=True)
            p.add_argument("--negative", default="")
            p.add_argument("--steps", type=int, default=30)
            p.add_argument("--cfg", type=float, default=7.0)
            p.add_argument("--sampler", default="euler")
            p.add_argument("--res", default="1024")

    p = sub.add_parser("noise"); common(p, False); p.add_argument("--seeds", type=int, default=100)
    p = sub.add_parser("noisecmp"); p.add_argument("run_a"); p.add_argument("run_b"); p.add_argument("--out")
    p = sub.add_parser("gen"); common(p)
    p.add_argument("--seeds", default="0"); p.add_argument("--scheduler", default="normal")
    p.add_argument("--limit", type=int, default=0); p.add_argument("--save-traj", action="store_true")
    p.add_argument("--no-pin", action="store_true", help="P6: leave ComfyUI's memory-adaptive batching on")
    p.add_argument("--purpose", default="generation workload")
    p = sub.add_parser("compare"); p.add_argument("run_a"); p.add_argument("run_b"); p.add_argument("--out")
    p.add_argument("--steps-detail", action="store_true")
    p.add_argument("--e0-out", default=None, help="also score each pair with E0 (LPIPS, DINOv2) and E0-N; JSONL")
    p = sub.add_parser("w1"); common(p); p.add_argument("--n", type=int, default=10)
    p.add_argument("--fractions", default="0.25,0.5,1.0")
    p = sub.add_parser("fp4"); common(p, False)
    p = sub.add_parser("replay"); common(p); p.add_argument("--provider-run", required=True)
    p.add_argument("--limit", type=int, default=0)
    a = ap.parse_args(argv)
    if a.cmd not in ("noise", "noisecmp", "compare"):
        comfy_env.configure(a.flags.split())
    {"noise": cmd_noise, "noisecmp": cmd_noisecmp, "gen": cmd_gen, "compare": cmd_compare, "w1": cmd_w1,
     "fp4": cmd_fp4, "replay": cmd_replay}[a.cmd](a)


if __name__ == "__main__":
    main()
