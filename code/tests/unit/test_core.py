import random

import pytest
import torch

from trajver import theory
from trajver.attacks.forgeries import f1_copy, f2_interpolate, f3_invert, faked_steps
from trajver.commit import commit, inclusion_proof, leaf_hash, merkle_root_from_leaves, verify_inclusion
from trajver.rules import e2w as e2w_mod
from trajver.rules.e2h import draw_steps, e2h, tier_a, tier_b
from trajver.thresholds import DEV_DEFAULTS
from trajver.trajectory import Trajectory

from .toy import ToyDenoiser, karras_like_sigmas, run_sampler, toy_replay

SAMPLERS = ["euler", "dpmpp_2m"]


# ---------------------------------------------------------------- commitment
def test_merkle_deterministic_and_sensitive():
    a = torch.arange(12, dtype=torch.float32).reshape(3, 4)
    b = torch.ones(5, dtype=torch.float16)
    base = commit([("a", a), ("b", b)]).root
    assert base == commit([("a", a.clone()), ("b", b.clone())]).root
    a2 = a.clone(); a2[1, 2] = torch.nextafter(a2[1, 2], torch.tensor(1e9))
    assert commit([("a", a2), ("b", b)]).root != base                     # one ulp in one value
    assert commit([("a", a.double()), ("b", b)]).root != base             # dtype
    assert commit([("a", a.reshape(4, 3)), ("b", b)]).root != base        # shape
    assert commit([("b", b), ("a", a)]).root != base                      # order
    assert commit([("x", a), ("b", b)]).root != base                      # name


@pytest.mark.parametrize("n", [1, 2, 3, 5, 8, 13])
def test_inclusion_proofs(n):
    leaves = [leaf_hash(f"t{i}", torch.full((2,), float(i))) for i in range(n)]
    root = merkle_root_from_leaves(leaves)
    for i in range(n):
        assert verify_inclusion(leaves[i], inclusion_proof(leaves, i), root)
    if n > 1:
        assert not verify_inclusion(leaves[0], inclusion_proof(leaves, 1), root)


def test_trajectory_roundtrip(tmp_path, comfy):
    traj = run_sampler("euler", ToyDenoiser(), karras_like_sigmas())
    root = traj.save(tmp_path / "trajectory.safetensors")
    back = Trajectory.load(tmp_path / "trajectory.safetensors")
    assert back.commitment().hex == root == traj.commitment().hex
    t, leaf, proof = traj.opening("D_005")
    assert torch.equal(t, traj.Ds[5]) and verify_inclusion(leaf, proof, traj.commitment().root)


# ---------------------------------------------------------------- noise (E1a)
@pytest.mark.parametrize("shape", [(1, 4, 64, 64), (1, 4, 128, 128)])
def test_noise_matches_comfy(comfy, shape):
    import comfy.sample
    from trajver.noise import initial_noise

    latent = torch.zeros(shape)
    for seed in range(100):
        assert torch.equal(initial_noise(shape, seed), comfy.sample.prepare_noise(latent, seed)), seed


# ---------------------------------------------------------------- Tier A against ComfyUI's real samplers
@pytest.mark.parametrize("sampler", SAMPLERS)
def test_tier_a_honest_passes(comfy, sampler):
    traj = run_sampler(sampler, ToyDenoiser(), karras_like_sigmas())
    v = tier_a(traj, sampler, DEV_DEFAULTS)
    assert v.passed, v.reasons
    assert v.scores["max_rel_l2"] < 1e-6
    # On the CPU the float32 replica reproduces ComfyUI's update bit for bit.
    assert v.scores["replica_exact_steps"] == traj.T


@pytest.mark.parametrize("sampler", SAMPLERS)
def test_tier_a_catches_wrong_schedule_and_fewer_steps(comfy, sampler):
    den = ToyDenoiser()
    traj = run_sampler(sampler, den, karras_like_sigmas(T=12))
    relabelled = traj.clone()
    relabelled.sigmas = karras_like_sigmas(T=12, smin=0.05)   # claims a different schedule
    assert not tier_a(relabelled, sampler, DEV_DEFAULTS).passed
    short = run_sampler(sampler, den, karras_like_sigmas(T=8))
    # A1(b): 8 computed states relabelled as a 12-step trajectory by interpolation -> F2 shape
    fake = short.clone()
    assert fake.T == 8 and not tier_a(f2_interpolate(traj, faked_steps(12, 0.34, random.Random(0))), sampler, DEV_DEFAULTS).passed


# ---------------------------------------------------------------- forgeries vs Tier A / Tier B
@pytest.mark.parametrize("sampler", SAMPLERS)
@pytest.mark.parametrize("s", [0.25, 0.5, 1.0])
def test_forgeries(comfy, sampler, s):
    den = ToyDenoiser()
    traj = run_sampler(sampler, den, karras_like_sigmas(T=12))
    faked = faked_steps(traj.T, s, random.Random(1))
    th = DEV_DEFAULTS
    all_steps = list(range(traj.T))

    f1 = f1_copy(traj, faked)
    if s < 1.0:
        # A partial copy breaks the solver at the boundary between computed and copied steps.
        assert not tier_a(f1, sampler, th).passed
    else:
        # A full copy with D_i := x_i is a fixed point of the solver: Tier A cannot see it ...
        assert tier_a(f1, sampler, th).passed
    # ... but the full check always fails F1, through Tier B.
    assert not e2h(f1, sampler, toy_replay(den), all_steps, th).passed

    f2 = f2_interpolate(traj, faked)
    if s < 1.0:
        assert not tier_a(f2, sampler, th).passed
    # With no computed anchor at all, F2 degenerates into F1; Tier B still catches it.
    assert not e2h(f2, sampler, toy_replay(den), all_steps, th).passed

    f3 = f3_invert(traj, faked, sampler)
    assert tier_a(f3, sampler, th).passed            # F3 is built to pass Tier A
    vb = tier_b(f3, toy_replay(den), all_steps, th)  # ... and Tier B catches it
    assert not vb.passed

    honest = e2h(traj, sampler, toy_replay(den), all_steps, th)
    assert honest.passed, honest.reasons


def test_cheap_model_trajectory_f4(comfy):
    """F4: a complete, consistent trajectory from a different model passes Tier A, fails Tier B."""
    claimed, cheap = ToyDenoiser(), ToyDenoiser(perturb=0.05)
    traj = run_sampler("euler", cheap, karras_like_sigmas())
    assert tier_a(traj, "euler", DEV_DEFAULTS).passed
    assert not tier_b(traj, toy_replay(claimed), list(range(traj.T)), DEV_DEFAULTS).passed


def test_tier_b_commit_before_reveal(comfy):
    den = ToyDenoiser()
    traj = run_sampler("euler", den, karras_like_sigmas())
    log = []
    tier_b(traj, toy_replay(den), [1, 4, 7], DEV_DEFAULTS, log)
    assert [e["event"] for e in log] == ["verifier_commit", "reveal_compared"]


def test_draw_steps():
    a = draw_steps(30, 3, b"slot-hash|job-1")
    assert a == draw_steps(30, 3, b"slot-hash|job-1") and len(set(a)) == 3 and all(0 <= i < 30 for i in a)
    assert a != draw_steps(30, 3, b"slot-hash|job-2")


# ---------------------------------------------------------------- E2-W reproduction
def test_e2w_score_formula():
    # score = max(min_cos * 0.5 + 0.5, 0); cos uses eps=1e-3 on flattened tensors
    a = torch.tensor([1.0, 0.0]); b = torch.tensor([0.0, 1.0])
    assert e2w_mod.similarity(a, a) == pytest.approx(1.0)
    assert e2w_mod.similarity(a, b) == pytest.approx(0.0)
    assert e2w_mod.similarity(a, -a) == pytest.approx(-1.0)


def test_e2w_on_toy(comfy):
    den = ToyDenoiser()
    traj = run_sampler("euler", den, karras_like_sigmas(T=12))
    v = e2w_mod.e2w(traj, 12, "euler", toy_replay(den), DEV_DEFAULTS, seed=0)
    assert v.passed and v.scores["score"] > 0.99
    assert e2w_mod.e2w(traj, 30, "euler", toy_replay(den), DEV_DEFAULTS, seed=0).scores["score"] == 0.0


# ---------------------------------------------------------------- theory
def test_eq4_matches_monte_carlo():
    T, m, k, r, a = 30, 12, 3, 0.8, 0.003
    rng = random.Random(0)
    n, fails = 200_000, 0
    for _ in range(n):
        checked = rng.sample(range(T), k)
        failed = any((rng.random() < r) if i < m else (rng.random() < a) for i in checked)
        fails += failed
    assert theory.q_spot_check(T, m, k, r, a) == pytest.approx(fails / n, abs=4e-3)


def test_eq6_and_deterrence():
    assert theory.alpha_step_budget(0.01, 3) == pytest.approx(0.00334, abs=1e-5)
    assert theory.alpha_job(theory.alpha_step_budget(0.01, 3), 3) == pytest.approx(0.01)
    p = theory.p_star(3, [(0.5, 0.9)], theory.alpha_step_budget(0.01, 3), P=1.0, B=1.0, c=1.0)
    a_s = theory.alpha_step_budget(0.01, 3)
    assert theory.deterred(p * (1 + 1e-9), 3, 0.9, a_s, 1.0, 1.0, 0.5, 1.0)
    assert not theory.deterred(p * 0.99, 3, 0.9, a_s, 1.0, 1.0, 0.5, 1.0)
    assert theory.p_star(3, [(0.5, 0.001)], 0.0033, 1, 1, 1) == float("inf")   # inseparable attack
    # Proposition 3: gain is convex, so max over s is at an endpoint
    g = [theory.gain(s / 20, 0.5, 1, 0.2, 3, 0.9, 0.0033, 2) for s in range(21)]
    assert max(g) == pytest.approx(max(g[0], g[-1]))
