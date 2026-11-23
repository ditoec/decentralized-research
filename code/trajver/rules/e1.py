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


def check_x0(traj: Trajectory, model_sampling, seed: int, device="cpu") -> Verdict:
    shape = tuple(traj.xs[0].shape)
    noise = initial_noise(shape, seed)
    latent = torch.zeros(shape, dtype=torch.float32)
    scores = {}
    ok = False
    for dev in dict.fromkeys(["cpu", str(device)]):
        exp = expected_x0(model_sampling, noise, traj.sigmas, latent, dev)
        exact = bool(torch.equal(exp, traj.xs[0].float()))
        scores[f"exact_{dev}"] = exact
        scores[f"max_abs_{dev}"] = (exp.double() - traj.xs[0].double()).abs().max().item()
        ok = ok or exact
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
        check_x0(traj, pipeline.model_sampling(), spec.seed, pipeline.model.load_device),
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
