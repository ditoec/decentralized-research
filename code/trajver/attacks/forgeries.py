"""Trajectory forgeries F1–F3 as transforms of a trajectory (runbook §3.3).

A forger fakes the steps in ``faked`` (a set of step indices i, meaning it did not run the model
at step i). The forged trajectory keeps the honest values at computed steps. These transforms
give the verifier exactly the commitment such a forger would publish; the computation the
forger saves is modelled separately (beta_A, measured on hardware).

F4 (a complete, consistent trajectory from a cheap model) needs no transform: it is the honest
trajectory of attack A2 or A3, committed under the claimed job.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import torch

from ..solvers import solve_D
from ..trajectory import Trajectory


def faked_steps(T: int, s: float, rng: random.Random, pattern: str = "random") -> list[int]:
    """Indices of the m = round(s*T) faked steps. ``tail`` fakes the last m steps (early exit)."""
    m = round(s * T)
    if pattern == "tail":
        return list(range(T - m, T))
    if pattern == "random":
        return sorted(rng.sample(range(T), m))
    raise ValueError(pattern)


def f1_copy(traj: Trajectory, faked: list[int]) -> Trajectory:
    """F1: each faked step copies its input state: x_{i+1} := x_i, D_i := x_i."""
    t = traj.clone()
    for i in sorted(faked):
        t.Ds[i] = t.xs[i].clone()
        nxt = t.xs[i].clone()
        if i + 1 < t.T:
            t.xs[i + 1] = nxt
        else:
            t.x_final = nxt
    return t


def _anchor_interp(vals: list[torch.Tensor], known: list[bool]) -> list[torch.Tensor]:
    """Linear interpolation over index between known entries; hold the last known value."""
    out = list(vals)
    idx = [j for j, k in enumerate(known) if k]
    for j in range(len(vals)):
        if known[j]:
            continue
        lo = max((a for a in idx if a < j), default=None)
        hi = min((a for a in idx if a > j), default=None)
        if lo is None:
            out[j] = vals[hi].clone()
        elif hi is None:
            out[j] = vals[lo].clone()
        else:
            w = (j - lo) / (hi - lo)
            out[j] = ((1 - w) * vals[lo].double() + w * vals[hi].double()).to(vals[j].dtype)
    return out


def f2_interpolate(traj: Trajectory, faked: list[int]) -> Trajectory:
    """F2: states produced by faked steps, and their D, are interpolated between computed anchors."""
    t = traj.clone()
    faked = set(faked)
    states = [t.state(j) for j in range(t.T + 1)]
    state_known = [True] + [(j - 1) not in faked for j in range(1, t.T + 1)]
    states = _anchor_interp(states, state_known)
    D_known = [i not in faked for i in range(t.T)]
    if any(D_known):
        Ds = _anchor_interp(t.Ds, D_known)
    else:  # nothing computed: the forger has no prediction to interpolate, so it uses the next state
        Ds = [states[i + 1].clone() for i in range(t.T)]
    t.xs, t.x_final, t.Ds = states[: t.T], states[t.T], Ds
    return t


def f3_invert(traj: Trajectory, faked: list[int], sampler: str) -> Trajectory:
    """F3: interpolate the states (as F2), then solve the solver equation for every D_i whose
    step touches a forged state, so that Tier A passes up to rounding."""
    t = f2_interpolate(traj, faked)
    faked = set(faked)
    d_changed = False
    for i in range(t.T):
        state_changed = not torch.equal(t.state(i), traj.state(i)) or not torch.equal(t.state(i + 1), traj.state(i + 1))
        # DPM-Solver++(2M) uses D_{i-1}: a fabricated D_{i-1} forces D_i to be fabricated too.
        need = i in faked or state_changed or (sampler == "dpmpp_2m" and d_changed)
        if need:
            t.Ds[i] = solve_D(t, i, sampler, t.state(i + 1))
        d_changed = not torch.equal(t.Ds[i], traj.Ds[i])
    return t


def realistic_euler(kind: str, faked: list[int]):
    """A realistic forger for F1-F3 under the Euler sampler (doc 14 item 2, 2026-11-27).

    The transforms above edit an HONEST trajectory, so every computed step keeps the honest D_i and the step
    after a forged segment disagrees with the forged state; a real forger has no honest trajectory. This
    sampler function (for ``Pipeline.run(sampler_function=...)``) walks the claimed schedule itself, runs the
    model ONLY at computed steps (each from the forger's own, possibly forged, state) and produces each faked
    D_i without a model call:
      F1  copy:          D_i := x_i, so the Euler update gives x_{i+1} = x_i;
      F2  reuse:         D_i := the last computed D (copy if none yet);
      F3  extrapolate:   x_{i+1} extrapolated linearly in sigma from (x_{i-1}, x_i), D_i solved so that the Euler
                         update reaches it (copy if no previous state).
    Every state then follows from its committed D by ComfyUI's own Euler update (to_d, dt, x + d*dt, as
    comfy.k_diffusion.sampling.sample_euler), so Tier A sees no inconsistency at all; only the faked D_i
    themselves can be detected (Equation 4 with m = sT).
    """
    from comfy.k_diffusion.sampling import to_d

    if kind not in ("F1", "F2", "F3"):
        raise ValueError(kind)
    faked = set(faked)

    def sampler(model, x, sigmas, extra_args=None, callback=None, disable=None, **kw):
        extra_args = {} if extra_args is None else extra_args
        s_in = x.new_ones([x.shape[0]])
        last_d, prev_x = None, None
        for i in range(len(sigmas) - 1):
            sigma_hat = sigmas[i]
            dt = sigmas[i + 1] - sigma_hat
            if i not in faked:
                denoised = model(x, sigma_hat * s_in, **extra_args)
                last_d = denoised
            elif kind == "F2" and last_d is not None:
                denoised = last_d
            elif kind == "F3" and prev_x is not None:
                target = x + (x - prev_x) * ((sigmas[i + 1] - sigmas[i]) / (sigmas[i] - sigmas[i - 1]))
                denoised = x - (target - x) * sigma_hat / dt
            else:  # F1, or nothing to reuse or extrapolate from yet
                denoised = x.clone()
            d = to_d(x, sigma_hat, denoised)
            if callback is not None:
                callback({"x": x, "i": i, "sigma": sigmas[i], "sigma_hat": sigma_hat, "denoised": denoised})
            prev_x = x
            x = x + d * dt
        return x

    return sampler


def write_labels(path: str | Path, job_id: str, attack: str, s: float, faked: list[int], extra: dict | None = None):
    """Ground-truth sidecar. Verifiers never read this file."""
    Path(path).write_text(json.dumps({"job_id": job_id, "attack": attack, "s": s, "faked": faked,
                                      **(extra or {})}, indent=1))
