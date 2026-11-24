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


# Build-agnostic tolerance for x_0, in units of the unit-variance noise (protocol constant).
# PyTorch's vectorized normal sampler rounds differently per CPU and build (runbook §3 findings
# 6-8, 11): the largest difference seen in the pilot is 2.3e-6 (ARM vs x86). The constant is set
# well above any rounding difference so that no CPU/PyTorch pairing needs its own measurement, and
# far below anything an attacker could use: a different seed or a doctored x_0 differs by O(1) per
# element, and 1e-5 of the noise changes no output a provider could profit from.
X0_TOL = 1e-5


def check_x0(traj: Trajectory, model_sampling, seed: int, device="cpu", max_abs_noise: float = X0_TOL) -> Verdict:
    """x_0 = noise_scaling(noise(seed)). Exact when provider and verifier share a CPU and PyTorch
    build; otherwise accepted if max |x0_expected - x0_committed| / sigma_0 <= ``max_abs_noise``
    (default the protocol constant X0_TOL; ULP distance is not used: near zero a 2e-6 rounding
    difference is millions of ULP)."""
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


# Build-agnostic tolerance for the committed schedule (protocol constant), relative per entry. The
# canonical CPU schedule differs between ARM and x86 CPUs by one float32 ULP in a few entries
# (relative 9.7e-8; runbook §3 finding 17), exactly like the noise. 1e-6 is about 8 ULP: above any
# rounding difference, and far below what a cheaper schedule changes (fewer steps change T, and a
# relabelled schedule moves sigmas by orders of magnitude more).
SCHED_TOL_REL = 1e-6


def check_schedule(traj: Trajectory, expected_sigmas: torch.Tensor, steps: int,
                   tol_rel: float = SCHED_TOL_REL) -> Verdict:
    reasons = []
    if traj.T != steps:
        reasons.append(f"trajectory has {traj.T} steps, job requires {steps}")
    same_shape = traj.sigmas.shape == expected_sigmas.shape
    exact = same_shape and torch.equal(traj.sigmas.float(), expected_sigmas.float())
    rel = float("inf")
    if same_shape:
        a, b = traj.sigmas.double(), expected_sigmas.double()
        rel = float(((a - b).abs() / b.abs().clamp_min(1e-12)).max())
    if not (exact or rel <= tol_rel):
        reasons.append("committed sigma schedule differs from the job's schedule")
    return Verdict("E1.schedule", FAIL if reasons else PASS,
                   {"T": traj.T, "schedule_equal": exact, "max_rel_diff": rel}, reasons)


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
        check_x0(traj, pipeline.model_sampling(), spec.seed, pipeline.model.load_device, th.get("x0_max_abs_noise", X0_TOL)),
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
