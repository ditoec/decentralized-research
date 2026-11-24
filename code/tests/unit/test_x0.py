"""E1(a): the build-agnostic x_0 tolerance (rules.e1.X0_TOL)."""
import torch

from trajver.noise import initial_noise
from trajver.rules.e1 import X0_TOL, check_x0
from trajver.trajectory import Trajectory

SHAPE = (1, 4, 16, 16)


class _MS:  # minimal stand-in for ComfyUI's EPS model_sampling
    sigma_max = 14.6

    @staticmethod
    def noise_scaling(sigma, noise, latent, max_denoise=False):
        return latent + noise * (torch.sqrt(1.0 + sigma ** 2) if max_denoise else sigma)


def _traj(x0: torch.Tensor) -> Trajectory:
    sig = torch.tensor([14.6, 1.0, 0.0])
    z = torch.zeros(SHAPE)
    return Trajectory(sigmas=sig, xs=[x0, z], Ds=[z, z], x_final=z)


def _honest_x0(seed: int) -> torch.Tensor:
    return _MS.noise_scaling(torch.tensor(14.6), initial_noise(SHAPE, seed), torch.zeros(SHAPE), True)


def test_exact_x0_passes():
    assert check_x0(_traj(_honest_x0(7)), _MS, 7).verdict == "pass"


def test_cross_build_rounding_passes():
    # the largest pilot difference (2.3e-6 of the noise, ARM vs x86) scaled to x_0 units
    x0 = _honest_x0(7)
    sigma0 = float(torch.sqrt(torch.tensor(1.0 + 14.6 ** 2)))
    bump = torch.zeros_like(x0)
    bump.view(-1)[::3] = 2.3e-6 * sigma0
    assert check_x0(_traj(x0 + bump), _MS, 7).verdict == "pass"


def test_wrong_seed_fails():
    assert check_x0(_traj(_honest_x0(8)), _MS, 7).verdict == "fail"


def test_perturbation_above_tolerance_fails():
    x0 = _honest_x0(7)
    x0.view(-1)[0] += 20 * X0_TOL * 14.6
    assert check_x0(_traj(x0), _MS, 7).verdict == "fail"
