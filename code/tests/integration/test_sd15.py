"""Acceptance tests T1–T3 (runbook §3.1, §3.2) and the rules on a real SD1.5 job.

Runs on whatever device ComfyUI picks (CUDA, MPS or CPU). Each test is a same-device check:
cross-device behaviour is what the experiments measure, not what the tests assert.
"""
import random

import pytest
import torch

from trajver.attacks.forgeries import f1_copy, f2_interpolate, f3_invert, faked_steps
from trajver.job import JobSpec, Pipeline
from trajver.rules.e1 import e1
from trajver.rules.e2h import e2h, tier_a
from trajver.rules.e2w import adjacent_cosines, e2w
from trajver.thresholds import DEV_DEFAULTS

pytestmark = pytest.mark.integration

SPEC = JobSpec(prompt="a lighthouse on a cliff at sunset, oil painting", negative="blurry, low quality",
               seed=42, steps=20, cfg=7.0, sampler="euler", scheduler="normal", width=512, height=512)


@pytest.fixture(scope="module")
def pipe(comfy, sd15_path):
    return Pipeline(sd15_path)


@pytest.fixture(scope="module")
def honest(pipe):
    return pipe.run(SPEC)


def replay_for(pipe, spec):
    return lambda states, sigmas: pipe.replay_denoised(spec, states, sigmas)


def test_T1_recording_does_not_change_the_output(pipe, honest):
    samples, _ = honest
    assert torch.equal(pipe.run_stock(SPEC), samples)


def test_T2_rerun_gives_the_same_root(pipe, honest):
    _, traj = honest
    _, again = pipe.run(SPEC)
    assert again.commitment().hex == traj.commitment().hex


def test_final_state_is_the_output(pipe, honest):
    samples, traj = honest
    assert traj.T == SPEC.steps and len(traj.Ds) == SPEC.steps
    assert torch.equal(pipe.latent_out(traj.x_final).to(samples.dtype).cpu(), samples.cpu())


def test_T3_replay_is_bit_exact(pipe, honest):
    _, traj = honest
    D_hat = pipe.replay_denoised(SPEC, {i: traj.xs[i] for i in range(traj.T)}, traj.sigmas)
    mismatched = [i for i in range(traj.T) if not torch.equal(D_hat[i], traj.Ds[i])]
    assert mismatched == []


def test_e1_honest_passes(pipe, honest):
    samples, traj = honest
    delivered = pipe.to_uint8(pipe.decode(samples))
    v = e1(traj, pipe, SPEC, delivered, DEV_DEFAULTS)
    assert v.passed, v.reasons
    assert v.scores["E1.x0"]["scores"]["exact_cpu"] or any(
        val for key, val in v.scores["E1.x0"]["scores"].items() if key.startswith("exact"))


def test_e1_catches_wrong_seed_and_prompt(pipe, honest):
    samples, traj = honest
    other = JobSpec(**{**SPEC.to_dict(), "seed": SPEC.seed + 1})
    assert not e1(traj, pipe, other, None, DEV_DEFAULTS).passed
    other = JobSpec(**{**SPEC.to_dict(), "prompt": "a lighthouse on a cliff at night"})
    assert not e1(traj, pipe, other, None, DEV_DEFAULTS).passed


def test_e2h_honest_passes_and_forgeries_fail(pipe, honest):
    _, traj = honest
    steps = list(range(traj.T))  # check every step so the test is deterministic
    replay = replay_for(pipe, SPEC)
    assert e2h(traj, "euler", replay, steps, DEV_DEFAULTS).passed
    faked = faked_steps(traj.T, 0.5, random.Random(0))
    for name, forged in (("F1", f1_copy(traj, faked)), ("F2", f2_interpolate(traj, faked)),
                         ("F3", f3_invert(traj, faked, "euler"))):
        assert not e2h(forged, "euler", replay, steps, DEV_DEFAULTS).passed, name
    assert tier_a(f3_invert(traj, faked, "euler"), "euler", DEV_DEFAULTS).passed


def test_dpmpp_2m_tier_a_on_real_model(pipe):
    spec = JobSpec(**{**SPEC.to_dict(), "sampler": "dpmpp_2m", "steps": 12})
    _, traj = pipe.run(spec)
    v = tier_a(traj, "dpmpp_2m", DEV_DEFAULTS)
    assert v.passed, (v.reasons, v.scores["max_rel_l2"])


def test_e2w_honest_and_frame_copy(pipe, honest):
    """Hypothesis W1 in miniature: does the deployed rule accept a full frame copy?"""
    _, traj = honest
    replay = replay_for(pipe, SPEC)
    honest_v = e2w(traj, SPEC.steps, "euler", replay, DEV_DEFAULTS, seed=0, frames_dtype=pipe.model_dtype())
    assert honest_v.passed, honest_v.scores
    cos = adjacent_cosines(traj)
    assert len(cos) == traj.T
