import pytest
import torch

from trajver.rules import e0n


def test_e0n_reward_formula_matches_audited_source():
    # cos > 0.9 -> 1.0 ; 0.4 < cos <= 0.9 -> (cos + 0.1) ** 3 ; else 0.0  (strict inequalities)
    assert e0n.reward_from_cosine(0.95) == 1.0
    assert e0n.reward_from_cosine(0.9) == pytest.approx(1.0 ** 3)      # 0.9 is not > 0.9: (0.9 + 0.1)^3
    assert e0n.reward_from_cosine(0.6) == pytest.approx(0.7 ** 3)
    assert e0n.reward_from_cosine(0.4) == 0.0
    assert e0n.reward_from_cosine(-0.2) == 0.0


def _img(v):
    return torch.full((64, 64, 3), v, dtype=torch.uint8)


def test_e0n_nsfw_filter_never_fires_as_deployed():
    black, grey = _img(0), torch.randint(0, 255, (64, 64, 3), dtype=torch.uint8, generator=torch.Generator().manual_seed(0))
    assert e0n.nsfw_filter(grey, black, faithful_nsfw=True) == 0     # deployed: size-6 vs size-8 hashes
    assert e0n.nsfw_filter(grey, black, faithful_nsfw=False) == 1    # intended behaviour
    assert e0n.nsfw_filter(black, grey, faithful_nsfw=False) == 2


def test_phash_rule():
    a = torch.randint(0, 255, (64, 64, 3), dtype=torch.uint8, generator=torch.Generator().manual_seed(1))
    ok, d = e0n.phash_match(a, a)
    assert ok and d == 0
    ok, d = e0n.phash_match(a, 255 - a)
    assert not ok and d > 6
