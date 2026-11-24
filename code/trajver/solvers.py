"""Tier A: solver consistency. The next state is a fixed function of committed values only.

Two recomputations per step:

* ``float64``: the manuscript's Equations 1 and 2 evaluated in double precision. Its residual
  against the committed float32 state measures how far the commitment is from the solver,
  independent of the provider's device.
* ``replica``: the exact float32 torch operation sequence of the pinned ComfyUI sampler
  (comfy/k_diffusion/sampling.py: sample_euler, sample_dpmpp_2m), run on the CPU. Where the
  provider's device rounds the same way, this reproduces the committed state bit for bit.

Only deterministic samplers are supported (doc 06 §1.1).
"""
from __future__ import annotations

import math

import torch

from .trajectory import Trajectory

SUPPORTED = ("euler", "dpmpp_2m")


# ------------------------------------------------------------------ float64, Equations 1 and 2
def euler_f64(x, D, s, s_next):
    return x + (x - D) / s * (s_next - s)


def dpmpp_2m_f64(x, D, s, s_next, D_prev=None, s_prev=None):
    if s_next == 0.0:
        return D.clone()
    h = math.log(s / s_next)
    if D_prev is None:
        return (s_next / s) * x - math.expm1(-h) * D
    h_last = math.log(s_prev / s)
    r = h_last / h
    Dd = (1 + 1 / (2 * r)) * D - (1 / (2 * r)) * D_prev
    return (s_next / s) * x - math.expm1(-h) * Dd


# ------------------------------------------------------------------ float32 replica of ComfyUI
def euler_replica(x, D, sigmas, i):
    sigma_hat = sigmas[i]
    d = (x - D) / sigma_hat
    dt = sigmas[i + 1] - sigma_hat
    return x + d * dt


def dpmpp_2m_replica(x, D, sigmas, i, D_prev=None):
    sigma_fn = lambda t: t.neg().exp()  # noqa: E731
    t_fn = lambda sigma: sigma.log().neg()  # noqa: E731
    t, t_next = t_fn(sigmas[i]), t_fn(sigmas[i + 1])
    h = t_next - t
    if D_prev is None or sigmas[i + 1] == 0:
        return (sigma_fn(t_next) / sigma_fn(t)) * x - (-h).expm1() * D
    h_last = t - t_fn(sigmas[i - 1])
    r = h_last / h
    Dd = (1 + 1 / (2 * r)) * D - (1 / (2 * r)) * D_prev
    return (sigma_fn(t_next) / sigma_fn(t)) * x - (-h).expm1() * Dd


# ------------------------------------------------------------------ per-step prediction
def predict_next(traj: Trajectory, i: int, sampler: str, mode: str = "float64") -> torch.Tensor:
    if sampler not in SUPPORTED:
        raise ValueError(f"Tier A supports {SUPPORTED}, not {sampler!r}")
    s = traj.sigmas
    x, D = traj.xs[i], traj.Ds[i]
    D_prev = traj.Ds[i - 1] if i > 0 else None
    if mode == "float64":
        x64, D64 = x.double(), D.double()
        if sampler == "euler":
            return euler_f64(x64, D64, float(s[i]), float(s[i + 1]))
        return dpmpp_2m_f64(x64, D64, float(s[i]), float(s[i + 1]),
                            None if D_prev is None else D_prev.double(),
                            None if i == 0 else float(s[i - 1]))
    if mode == "replica":
        sig = s.to(torch.float32).cpu()
        x32, D32 = x.float().cpu(), D.float().cpu()
        if sampler == "euler":
            return euler_replica(x32, D32, sig, i)
        return dpmpp_2m_replica(x32, D32, sig, i, None if D_prev is None else D_prev.float().cpu())
    raise ValueError(mode)


def residual(pred: torch.Tensor, actual: torch.Tensor) -> dict:
    a = actual.double()
    diff = pred.double() - a
    denom = a.norm().item()
    pn = pred.double().norm().item()
    return {
        "max_abs": diff.abs().max().item(),
        "rel_l2": diff.norm().item() / denom if denom > 0 else float("inf"),
        # 1 - cosine, a third candidate Tier B metric (runbook §5 item 2)
        "cos_dist": 1.0 - (float((pred.double().flatten() @ a.flatten()) / (pn * denom)) if pn > 0 and denom > 0 else 0.0),
    }


def tier_a_residuals(traj: Trajectory, sampler: str) -> list[dict]:
    """One row per step i: residual of the recomputed x_{i+1} against the committed one."""
    rows = []
    for i in range(traj.T):
        actual = traj.state(i + 1)
        r = residual(predict_next(traj, i, sampler, "float64"), actual)
        rep = predict_next(traj, i, sampler, "replica")
        r["replica_exact"] = bool(torch.equal(rep, actual.float().cpu()))
        r["replica_max_abs"] = (rep.double() - actual.double()).abs().max().item()
        r["step"] = i
        rows.append(r)
    return rows


# ------------------------------------------------------------------ inversion (forgery F3)
def solve_D(traj: Trajectory, i: int, sampler: str, x_next: torch.Tensor) -> torch.Tensor:
    """The D_i that makes the solver map x_i to ``x_next`` exactly (in float64).

    Used by forgery F3: a provider that computed only some steps fabricates D_i so that Tier A
    passes. The result is cast to the committed dtype, so Tier A sees only rounding error.
    """
    s = traj.sigmas
    x = traj.xs[i].double()
    xn = x_next.double()
    si, sn = float(s[i]), float(s[i + 1])
    dtype = traj.Ds[i].dtype
    if sampler == "euler":
        if sn == 0.0:
            return xn.to(dtype)
        return (x - (xn - x) * si / (sn - si)).to(dtype)
    if sampler == "dpmpp_2m":
        if sn == 0.0:
            return xn.to(dtype)
        h = math.log(si / sn)
        Dd = ((sn / si) * x - xn) / math.expm1(-h)
        if i == 0:
            return Dd.to(dtype)
        r = math.log(float(s[i - 1]) / si) / h
        D_prev = traj.Ds[i - 1].double()
        return ((Dd + D_prev / (2 * r)) / (1 + 1 / (2 * r))).to(dtype)
    raise ValueError(sampler)
