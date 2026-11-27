import json
from pathlib import Path

import numpy as np
import pytest

from trajver import montecarlo as mc
from trajver import theory

CONFIG = Path(__file__).resolve().parents[3] / "experiments" / "configs" / "mc_params_provisional.json"
BASE = dict(T=30, c=0.5, P=1.0)


def cell(seed=0, **kw):
    args = {**BASE, "attack": "t", "n_sim": 50_000, **kw}
    return mc.simulate_cell(np.random.default_rng(seed), **args)


# ---------------------------------------------------------------- Proposition 2
@pytest.mark.parametrize("s,k,r,a_s", [
    (1.0, 3, 0.9, 0.0033),
    (0.4, 3, 0.8, 0.003),
    (0.1, 5, 0.5, 0.002),
    (0.5, 1, 0.3, 0.01),
    (0.2, 8, 0.9, 0.00126),
])
def test_detection_matches_eq4(s, k, r, a_s):
    c = cell(p=0.1, k=k, BP=1.0, s=s, r=r, alpha_s=a_s, beta=0.5)
    assert c.detect_closed == pytest.approx(theory.q_spot_check(30, mc.faked_steps(s, 30), k, r, a_s))
    assert c.detect_ci_lo <= c.detect_closed <= c.detect_ci_hi


def test_gain_matches_eq7():
    c = cell(p=0.25, k=3, BP=1.0, s=0.5, r=0.8, alpha_s=0.0033, beta=0.9)
    assert c.gain_ci_lo <= c.gain_closed <= c.gain_ci_hi
    # finite T = 30 with s*T integral is close to the large-T Eq. 7 in theory.gain
    assert c.gain_closed == pytest.approx(theory.gain(0.5, 0.9, 0.5, 0.25, 3, 0.8, 0.0033, 2.0), abs=0.01)


# ---------------------------------------------------------------- s = 0
@pytest.mark.parametrize("p,k,BP", [(0.05, 1, 0.0), (0.5, 3, 2.0), (1.0, 8, 5.0)])
def test_no_cheating_no_gain(p, k, BP):
    c = cell(p=p, k=k, BP=BP, s=0.0, r=0.9, alpha_s=0.01, beta=0.9)
    assert c.gain_mean == 0.0 and c.gain_ci_lo == 0.0 and c.gain_ci_hi == 0.0
    assert c.gain_closed == pytest.approx(0.0, abs=1e-12)


# ---------------------------------------------------------------- Proposition 3
@pytest.mark.parametrize("k,r,beta,BP", [(3, 0.9, 0.9, 1.0), (1, 0.5, 0.5, 0.5), (5, 0.3, 0.9, 2.0)])
def test_deterrence_boundary_is_p_star(k, r, beta, BP):
    a_s = theory.alpha_step_budget(0.01, k)
    p_star = theory.p_star(k, [(beta, r)], a_s, P=1.0, B=BP, c=0.5)
    assert 0 < p_star < 1
    below = cell(p=p_star * 0.7, k=k, BP=BP, s=1.0, r=r, alpha_s=a_s, beta=beta, n_sim=200_000)
    above = cell(p=min(1.0, p_star * 1.3), k=k, BP=BP, s=1.0, r=r, alpha_s=a_s, beta=beta, n_sim=200_000)
    assert not below.deterred and below.gain_ci_lo > 0          # cheating pays below p*
    assert above.deterred and above.gain_ci_hi < 0              # and is deterred above it
    at = cell(p=p_star, k=k, BP=BP, s=1.0, r=r, alpha_s=a_s, beta=beta, n_sim=1000)
    assert at.gain_closed == pytest.approx(0.0, abs=1e-12) and at.p_star == pytest.approx(p_star)


def test_sweep_end_to_end(tmp_path):
    params = json.loads(CONFIG.read_text())
    params["grid"]["p"]["value"] = [0.05, 0.25]
    params["grid"]["k"]["value"] = [3]
    params["grid"]["BP"]["value"] = [1]
    cells, summary = mc.run_sweep(params, n_sim=5000)
    assert summary["seed"] == 20261126
    assert summary["attacks_waiting_for_wp3"] == ["F3-partial"]
    assert len(cells) == 2 * 2 * 11
    assert summary["checks"]["prop3_interior_maximum_cells"] == 0
    assert summary["checks"]["prop3_eq8_at_s1"]["disagree"] == 0
    # deterministic given the seed
    again, _ = mc.run_sweep(params, n_sim=5000)
    assert [c.gain_mean for c in again] == [c.gain_mean for c in cells]
    assert mc.main(["--params", str(CONFIG), "--out", str(tmp_path), "--n-sim", "200"]) == 0
    head = (tmp_path / "mc_sweep.csv").read_text().splitlines()[0].split(",")
    assert {"p", "k", "BP", "s", "n_sim", "detect_sim", "detect_closed", "gain_mean",
            "gain_ci_lo", "gain_ci_hi", "deterred"} <= set(head)
    out = json.loads((tmp_path / "mc_summary.json").read_text())
    assert out["provisional"] is True and out["seed"] == 20261126
