"""E1: trajectory endpoints. Cheap checks that bind the trajectory to the job.

(a) x_0 equals noise(seed) after noise scaling, exactly;
(b) the committed schedule equals the schedule implied by (model, scheduler, steps, denoise),
    exactly, and T equals the requested step count;
(c) VAE-decoding x_final gives the delivered image (tolerance: cross-GPU decode differs);
(d) re-encoding the prompts gives the committed conditioning (tolerance).
"""
from __future__ import annotations

import torch

from ..noise import expected_x0, initial_noise
from ..solvers import residual
from ..trajectory import Trajectory
from . import FAIL, PASS, Verdict, combine


def max_ulp(a: torch.Tensor, b: torch.Tensor) -> int:
    """Largest distance in float32 units in the last place between two tensors of equal shape."""
    ia = a.float().contiguous().view(torch.int32).long()
    ib = b.float().contiguous().view(torch.int32).long()
    # map the sign-magnitude float order onto a monotone integer line
    ia = torch.where(ia < 0, -(ia & 0x7FFFFFFF), ia)
    ib = torch.where(ib < 0, -(ib & 0x7FFFFFFF), ib)
    return int((ia - ib).abs().max())


def check_x0(traj: Trajectory, model_sampling, seed: int, device="cpu", max_abs_noise: float = 0.0) -> Verdict:
    """x_0 = noise_scaling(noise(seed)). Exact when provider and verifier share a CPU and PyTorch build.
    Across builds PyTorch's vectorized normal sampler rounds differently (runbook §3 findings 6-7):
    ARM vs ARM differed by <= 3 ULP, but x86 vs ARM by up to 2.3e-6 in absolute terms, which near
    zero is hundreds of thousands of ULP. The tolerance is therefore absolute, in units of the
    unit-variance noise: max |x0_expected - x0_committed| / sigma_0 <= ``max_abs_noise``, set from
    pilot P1 and frozen (decision of 2026-11-24, revised after the x86 P1 run)."""
    shape = tuple(traj.xs[0].shape)
    noise = initial_noise(shape, seed)
    latent = torch.zeros(shape, dtype=torch.float32)
    sigma0 = float(traj.sigmas[0]) if float(traj.sigmas[0]) > 0 else 1.0
    scores = {}
    ok = False
    for dev in dict.fromkeys(["cpu", str(device)]):
        exp = expected_x0(model_sampling, noise, traj.sigmas, latent, dev)
        exact = bool(torch.equal(exp, traj.xs[0].float()))
        d = (exp.double() - traj.xs[0].double()).abs().max().item()
        scores[f"exact_{dev}"] = exact
        scores[f"max_abs_{dev}"] = d
        scores[f"max_abs_noise_units_{dev}"] = d / sigma0
        scores[f"max_ulp_{dev}"] = 0 if exact else max_ulp(exp, traj.xs[0])
        ok = ok or exact or d / sigma0 <= max_abs_noise
    return Verdict("E1.x0", PASS if ok else FAIL, scores, [] if ok else ["x_0 is not noise(seed)"])


def check_schedule(traj: Trajectory, expected_sigmas: torch.Tensor, steps: int) -> Verdict:
    reasons = []
    if traj.T != steps:
        reasons.append(f"trajectory has {traj.T} steps, job requires {steps}")
    same = traj.sigmas.shape == expected_sigmas.shape and torch.equal(traj.sigmas.float(), expected_sigmas.float())
    if not same:
        reasons.append("committed sigma schedule differs from the job's schedule")
    return Verdict("E1.schedule", FAIL if reasons else PASS, {"T": traj.T, "schedule_equal": same}, reasons)


def check_image(decoded_uint8: torch.Tensor, delivered_uint8: torch.Tensor, th: dict) -> Verdict:
    if decoded_uint8.shape != delivered_uint8.shape:
        return Verdict("E1.image", FAIL, {"shape": list(delivered_uint8.shape)}, ["image shape differs"])
    diff = (decoded_uint8.int() - delivered_uint8.int()).abs()
    scores = {"max_abs": int(diff.max()), "frac_equal": float((diff == 0).float().mean())}
    ok = scores["max_abs"] <= th["image_max_abs"]
    return Verdict("E1.image", PASS if ok else FAIL, scores, [] if ok else ["decoded x_final does not match image"])


def check_conditioning(traj: Trajectory, fresh: dict[str, torch.Tensor], th: dict) -> Verdict:
    scores, reasons = {}, []
    for k, v in fresh.items():
        if k not in traj.conds:
            reasons.append(f"{k} missing from commitment")
            continue
        if traj.conds[k].shape != v.shape:
            reasons.append(f"{k} shape differs")
            continue
        r = residual(v, traj.conds[k])
        scores[k] = r
        if r["rel_l2"] > th["cond_rel_l2"]:
            reasons.append(f"{k} differs (rel_l2={r['rel_l2']:.3g})")
    return Verdict("E1.cond", FAIL if reasons else PASS, scores, reasons)


def e1(traj: Trajectory, pipeline, spec, delivered_uint8: torch.Tensor | None, th: dict) -> Verdict:
    """All E1 checks with a loaded verifier Pipeline."""
    parts = [
        check_x0(traj, pipeline.model_sampling(), spec.seed, pipeline.model.load_device, th.get("x0_max_abs_noise", 0.0)),
        check_schedule(traj, pipeline.schedule(spec), spec.steps),
    ]
    pos, neg = pipeline.encode(spec.prompt), pipeline.encode(spec.negative)
    fresh = {"cond_pos": pos[0][0].detach().cpu(), "cond_neg": neg[0][0].detach().cpu()}
    for name, c in (("cond_pos_pooled", pos), ("cond_neg_pooled", neg)):
        if c[0][1].get("pooled_output") is not None:
            fresh[name] = c[0][1]["pooled_output"].detach().cpu()
    parts.append(check_conditioning(traj, fresh, th))
    if delivered_uint8 is not None:
        decoded = pipeline.to_uint8(pipeline.decode(pipeline.latent_out(traj.x_final)))
        parts.append(check_image(decoded, delivered_uint8, th))
    return combine("E1", parts)
