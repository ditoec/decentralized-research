"""E2-W: faithful reproduction of the deployed WOMBO SN30 step check, adapted to ComfyUI.

Source (MIT licence, Copyright (c) 2023 Opentensor / Yuma Rao, (c) 2024 WOMBO), repository
womboai/wombo-bittensor-subnet at commit 91b66fe2e58a2508a3e3495ea345e90a676cf842:

* forwarding-validator/forwarding_validator/similarity_score_pipeline.py: ``__similarity``,
  ``score_similarity``, ``__validate_internal_cn``;
* base-validator/base_validator/cryptographic_sample.py: ``cryptographic_sample``;
* forwarding-validator/forwarding_validator/validator.py: ``RANDOM_VALIDATION_CHANCE = 0.35``
  and ``if similarity_score < 0.85`` -> bad response.

Their logic, as audited (doc 06 §2):

    if frames.shape[0] != num_inference_steps: return 0.0
    k = min(3, num_inference_steps); if frames.shape[0] - 1 < k: return 0.0
    idx = sorted(cryptographic_sample(range(frames.shape[0] - 1), k))
    frames = frames.to(unet.device, unet.dtype)
    sims = [cos(step(index=i + 1, from=frames[i]), frames[i + 1]) for i in idx]
    score = max(min(sims) * 0.5 + 0.5, 0.0)          # reject if score < 0.85
    cos(a, b) = torch.cosine_similarity(a.flatten(), b.flatten(), eps=1e-3, dim=0)

``frames`` are the latents after each step (diffusers ``callback_on_step_end``), i.e. in our
notation frames[j] = x_{j+1}, with frames[T-1] = x_final.

Adaptations, recorded here and in the paper:

1. The single step is ComfyUI's (model call through the provider's CFG pipeline, then the
   sampler update), not diffusers' ``scheduler.step``.
2. Their validator re-creates the scheduler for each check, so a multistep solver has no
   history and takes a first-order step; we do the same (D_prev = None).
3. Index sampling uses a seeded RNG instead of ``os.urandom`` so runs are reproducible; the
   distribution (k distinct indices, uniform over range(T - 1)) is the same.
4. ControlNet is not used (our workflows are text-to-image).
"""
from __future__ import annotations

import random

import torch

from ..solvers import dpmpp_2m_replica, euler_replica
from ..trajectory import Trajectory
from . import FAIL, PASS, Verdict
from .e2h import Replay


def similarity(a: torch.Tensor, b: torch.Tensor) -> float:
    return torch.cosine_similarity(a.flatten(), b.flatten(), eps=1e-3, dim=0).item()


def frames_of(traj: Trajectory) -> list[torch.Tensor]:
    return [traj.state(j + 1) for j in range(traj.T)]


def score_similarity(traj: Trajectory, num_inference_steps: int, sampler: str, replay: Replay,
                     rng: random.Random, frames_dtype: torch.dtype | None = None) -> tuple[float, dict]:
    frames = frames_of(traj)
    if len(frames) != num_inference_steps:
        return 0.0, {"reason": "frame count != num_inference_steps"}
    k = min(3, num_inference_steps)
    if len(frames) - 1 < k:
        return 0.0, {"reason": "too few frames"}
    idx = sorted(rng.sample(range(len(frames) - 1), k))
    if frames_dtype is not None:  # frames_tensor.to(unet.device, unet.dtype)
        frames = [f.to(frames_dtype).to(torch.float32) for f in frames]
    # Re-running step index i+1 from frames[i] = x_{i+1} uses sigma_{i+1}.
    D_hat = replay({i + 1: frames[i] for i in idx}, traj.sigmas)
    sig = traj.sigmas.float().cpu()
    sims = []
    for i in idx:
        j = i + 1
        x = frames[i].float().cpu()
        if sampler == "euler":
            nxt = euler_replica(x, D_hat[j].float().cpu(), sig, j)
        elif sampler == "dpmpp_2m":
            nxt = dpmpp_2m_replica(x, D_hat[j].float().cpu(), sig, j, D_prev=None)
        else:
            raise ValueError(sampler)
        sims.append(similarity(nxt, frames[i + 1].float().cpu()))
    score = max(min(sims) * 0.5 + 0.5, 0.0)
    return score, {"indices": idx, "similarities": sims}


def e2w(traj: Trajectory, num_inference_steps: int, sampler: str, replay: Replay, th: dict,
        seed: int, frames_dtype: torch.dtype | None = None) -> Verdict:
    score, info = score_similarity(traj, num_inference_steps, sampler, replay, random.Random(seed), frames_dtype)
    ok = score >= th["e2w_score_min"]
    return Verdict("E2-W", PASS if ok else FAIL, {"score": score, **info},
                   [] if ok else [f"similarity score {score:.3f} < {th['e2w_score_min']}"])


def adjacent_cosines(traj: Trajectory) -> list[float]:
    """Hypothesis W1 (pilot P5): cosine of x_i vs x_{i+1} for every i on an honest trajectory.

    If these are >= 0.70 everywhere, the frame-copy forgery F1 passes the deployed rule.
    """
    return [similarity(traj.state(i), traj.state(i + 1)) for i in range(traj.T)]
