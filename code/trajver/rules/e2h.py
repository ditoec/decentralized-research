"""E2-H: the proposed hardened trajectory check = E1 + Tier A on every step + Tier B at k steps.

``replay`` is any callable ``(states: {i: x_i}, sigmas) -> {i: D_hat_i}``; with a real model it
is ``Pipeline.replay_denoised`` bound to the job spec. Tier B never reads a committed D_i
before it has hashed its own recomputations (commit-before-reveal, manuscript §3-2).
"""
from __future__ import annotations

import hashlib
import random
import time
from typing import Callable

import torch

from ..commit import leaf_hash
from ..solvers import residual, tier_a_residuals
from ..thresholds import tau_for
from ..trajectory import Trajectory, dkey
from . import FAIL, PASS, Verdict, combine

Replay = Callable[[dict[int, torch.Tensor], torch.Tensor], dict[int, torch.Tensor]]


def draw_steps(T: int, k: int, seed: int | bytes | str) -> list[int]:
    """k distinct step indices, uniform without replacement, from a public seed.

    In the protocol the seed is the delayed Solana slot hash combined with the job id; in
    offline experiments it is any recorded value.
    """
    if isinstance(seed, (bytes, str)):
        seed = int.from_bytes(hashlib.sha256(seed if isinstance(seed, bytes) else seed.encode()).digest()[:8], "big")
    return sorted(random.Random(seed).sample(range(T), min(k, T)))


def tier_a(traj: Trajectory, sampler: str, th: dict) -> Verdict:
    rows = tier_a_residuals(traj, sampler)
    # pass if the float32 replica of the solver step is bit-exact, or the float64 residual is within
    # eps_A (calibrated as 0 when every honest step was replica-exact across nodes, runbook §5)
    bad = [r["step"] for r in rows if not (r["replica_exact"] or r["rel_l2"] <= th["eps_a_rel_l2"])]
    scores = {
        "max_rel_l2": max(r["rel_l2"] for r in rows),
        "max_abs": max(r["max_abs"] for r in rows),
        "replica_exact_steps": sum(r["replica_exact"] for r in rows),
        "steps": rows,
    }
    return Verdict("E2H.tierA", FAIL if bad else PASS, scores,
                   [f"solver inconsistency at steps {bad}"] if bad else [])


def tier_b(traj: Trajectory, replay: Replay, steps: list[int], th: dict, log: list | None = None) -> Verdict:
    states = {i: traj.xs[i] for i in steps}
    D_hat = replay(states, traj.sigmas)
    # Commit before reveal: hash our own recomputations before touching the provider's D_i.
    own = hashlib.sha256(b"".join(leaf_hash(dkey(i), D_hat[i]) for i in steps)).hexdigest()
    t_commit = time.time()
    if log is not None:
        log.append({"event": "verifier_commit", "hash": own, "steps": steps, "t": t_commit})
    per_step, bad = {}, []
    for i in steps:
        committed = traj.Ds[i]
        r = residual(D_hat[i], committed)
        r["exact"] = bool(torch.equal(D_hat[i].to(committed.dtype), committed))
        r["tau"] = tau_for(th, i)
        per_step[str(i)] = r
        if not r[th["tier_b_metric"]] <= r["tau"]:
            bad.append(i)
    if log is not None:
        log.append({"event": "reveal_compared", "t": time.time()})
    scores = {"steps": steps, "verifier_commitment": own, "per_step": per_step,
              "max_metric": max(per_step[str(i)][th["tier_b_metric"]] for i in steps)}
    return Verdict("E2H.tierB", FAIL if bad else PASS, scores,
                   [f"model inconsistency at steps {bad}"] if bad else [])


def e2h(traj: Trajectory, sampler: str, replay: Replay, steps: list[int], th: dict,
        e1_verdict: Verdict | None = None, log: list | None = None) -> Verdict:
    parts = [] if e1_verdict is None else [e1_verdict]
    parts += [tier_a(traj, sampler, th), tier_b(traj, replay, steps, th, log)]
    return combine("E2-H", parts)
