"""Retention classes F/O/I (runbook §3.5): step draw, bundles with Merkle proofs, extraction, and
the rules evaluated on an opened bundle giving the same verdicts as on the full trajectory."""
import json
from collections import Counter

import pytest
import torch

from trajver import retention as R
from trajver.rules import e2w as e2w_mod
from trajver.rules.e2h import tier_a, tier_a_from_rows, tier_b
from trajver.thresholds import DEV_DEFAULTS

from .toy import ToyDenoiser, karras_like_sigmas, run_sampler, toy_replay

SEED = bytes(range(32))


# ---------------------------------------------------------------- the step draw
def test_step_order_is_a_fixed_permutation():
    o = R.step_order(SEED, "job-1", 30)
    assert sorted(o) == list(range(30))
    assert o == R.step_order(SEED, "job-1", 30)
    assert o != R.step_order(SEED, "job-2", 30)
    assert o != R.step_order(bytes(32), "job-1", 30)


def test_draw_is_nested_and_e2w_inside_the_opened_steps():
    for j in range(200):
        o = R.step_order(SEED, f"job-{j}", 30)
        sets = [set(R.drawn(o, k)) for k in (1, 2, 3, 5, 8)]
        assert all(a <= b for a, b in zip(sets, sets[1:]))
        w = R.e2w_steps(o)
        assert len(w) == 3 and all(s >= 1 for s in w) and set(w) <= set(o[: R.N_OPEN])


def test_step_order_is_uniform():
    first = Counter(R.step_order(SEED, f"j{n}", 10)[0] for n in range(20000))
    assert all(1700 < first[i] < 2300 for i in range(10))  # expected 2000 each


# ---------------------------------------------------------------- bundles
@pytest.fixture
def traj(comfy):
    return run_sampler("dpmpp_2m", ToyDenoiser(), karras_like_sigmas(T=12))


def _bundle(traj, tmp_path, cls="O", tamper=None):
    order = R.step_order(SEED, "job-1", traj.T) if cls == "O" else []
    names = R.opened_names(order, traj.T, "dpmpp_2m", list(traj.conds), cls)
    tensors, md = R.make_bundle(traj, names, {"order": order[: R.N_OPEN], "tier_a": R.tier_a_rows(traj, "dpmpp_2m")})
    if tamper:
        tensors[tamper] = tensors[tamper] + 1e-3
    p = tmp_path / "b.safetensors"
    R.save_bundle(p, tensors, md)
    return p, order


def test_bundle_proofs_hold_and_tampering_is_caught(traj, tmp_path):
    p, order = _bundle(traj, tmp_path)
    b = R.load_bundle(p, traj.commitment().hex)
    s = order[0]
    assert torch.equal(b.xs[s], traj.xs[s]) and torch.equal(b.Ds[s], traj.Ds[s])
    unopened = next(i for i in range(traj.T) if i not in b.Ds)
    with pytest.raises(KeyError):
        b.Ds[unopened]
    with pytest.raises(ValueError, match="committed root"):
        R.load_bundle(p, "00" * 32)
    p2, _ = _bundle(traj, tmp_path, tamper=f"D_{s:03d}")
    with pytest.raises(ValueError, match="inclusion proof"):
        R.load_bundle(p2, traj.commitment().hex)


def test_dpmpp_bundle_opens_previous_D(traj, tmp_path):
    p, order = _bundle(traj, tmp_path)
    b = R.load_bundle(p)
    for s in order[: R.N_OPEN]:
        if s > 0:
            assert s - 1 in b.Ds


# ---------------------------------------------------------------- rules on an opened bundle
def test_rules_on_bundle_match_full_trajectory(traj, tmp_path):
    den = ToyDenoiser()
    p, order = _bundle(traj, tmp_path)
    b = R.load_bundle(p, traj.commitment().hex)
    th = DEV_DEFAULTS
    assert tier_a_from_rows(b.meta["tier_a"], th).verdict == tier_a(traj, "dpmpp_2m", th).verdict
    steps = R.drawn(order, 8)
    vb_full = tier_b(traj, toy_replay(den), steps, th)
    vb_open = tier_b(b, toy_replay(den), steps, th)
    assert vb_full.verdict == vb_open.verdict == "pass"
    assert vb_full.scores["per_step"] == vb_open.scores["per_step"]
    idx = [j - 1 for j in R.e2w_steps(order)]
    w_full = e2w_mod.e2w(traj, traj.T, "dpmpp_2m", toy_replay(den), th, seed=0, idx=idx)
    w_open = e2w_mod.e2w(b, b.T, "dpmpp_2m", toy_replay(den), th, seed=0, idx=idx)
    assert w_full.scores == w_open.scores


def test_cheap_model_is_caught_on_the_opened_steps(comfy, tmp_path):
    cheap = run_sampler("euler", ToyDenoiser(perturb=0.3), karras_like_sigmas(T=12))
    order = R.step_order(SEED, "job-1", cheap.T)
    tensors, md = R.make_bundle(cheap, R.opened_names(order, cheap.T, "euler", [], "O"), {"order": order[:8]})
    R.save_bundle(tmp_path / "c.safetensors", tensors, md)
    b = R.load_bundle(tmp_path / "c.safetensors")
    assert not tier_b(b, toy_replay(ToyDenoiser()), R.drawn(order, 3), DEV_DEFAULTS).passed


# ---------------------------------------------------------------- extraction on a run folder
def _run(tmp_path, traj, n=3, seed_hash=None):
    run = tmp_path / "wp2-x-test-01"
    (run / "raw" / "traj").mkdir(parents=True)
    (run / "logs").mkdir()
    m = {"run_id": run.name, "sampler": "dpmpp_2m"}
    if seed_hash:
        m["draw_seed_sha256"] = seed_hash
    (run / "manifest.json").write_text(json.dumps(m))
    rows = []
    for i in range(n):
        job = f"p{i:05d}_s0"
        root = traj.save(run / "raw" / "traj" / f"{job}.safetensors")
        rows.append({"job": job, "prompt_id": i, "seed": 0, "merkle_root": root})
    (run / "jobs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return run


def test_extract_class_o(traj, tmp_path):
    run = _run(tmp_path, traj, seed_hash=R.seed_sha256(SEED))
    st = R.extract(run, "O", SEED)
    assert st["n"] == 3
    assert not list((run / "raw" / "traj").iterdir())
    rows = [json.loads(l) for l in (run / "jobs.jsonl").read_text().splitlines()]
    assert all(r["retention"] == "O" and r["draw_seed_sha256"] == R.seed_sha256(SEED) for r in rows)
    assert (run / "logs" / "draw_seed.hex").read_text().strip() == SEED.hex()
    assert R.check_run(run) == 0
    assert R.extract(run, "O", SEED)["n"] == 0  # resumable: nothing left to do


def test_class_o_keeps_about_half_at_t30(comfy, tmp_path):
    # 30 steps, SDXL-like latent size per tensor: x_0, x_final, schedule, 8 x (x_s, D_s, D_{s-1}),
    # E2-W states; dpmpp_2m is the worst case
    big = run_sampler("dpmpp_2m", ToyDenoiser(shape=(1, 4, 64, 64)), karras_like_sigmas(T=30))
    run = _run(tmp_path, big, n=1, seed_hash=R.seed_sha256(SEED))
    st = R.extract(run, "O", SEED)
    assert st["kept_bytes"] < 0.6 * st["full_bytes"]


def test_extract_refuses_unfixed_or_wrong_seed(traj, tmp_path):
    with pytest.raises(SystemExit, match="not fixed"):
        R.extract(_run(tmp_path / "a", traj), "O", SEED)
    with pytest.raises(SystemExit, match="does not match"):
        R.extract(_run(tmp_path / "b", traj, seed_hash=R.seed_sha256(bytes(32))), "O", SEED)


def test_extract_class_i_and_f(traj, tmp_path):
    run = _run(tmp_path / "i", traj)
    R.extract(run, "I", None)
    b = R.load_bundle(run / "raw" / "opened" / "p00000_s0.safetensors")
    assert not b.xs and not b.Ds and len(b.meta["tier_a"]) == traj.T
    run = _run(tmp_path / "f", traj)
    R.extract(run, "F", None)
    assert len(list((run / "raw" / "traj").iterdir())) == 3


def test_check_run_catches_a_swapped_order(traj, tmp_path):
    run = _run(tmp_path, traj, seed_hash=R.seed_sha256(SEED))
    R.extract(run, "O", SEED)
    (run / "logs" / "draw_seed.hex").write_text(bytes(32).hex())
    assert R.check_run(run) == 1


def test_class_map():
    spec = "wp2-*-test-*=O,wp2-*-prec-*=I,*=F"
    assert R.class_for("wp2-x-test-01", spec) == "O"
    assert R.class_for("wp2-x-prec-01", spec) == "I"
    assert R.class_for("wp2-x-cal-01", spec) == "F"
