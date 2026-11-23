"""A toy analytic denoiser driven through ComfyUI's real k-diffusion samplers.

The denoiser D(x, sigma) is a smooth nonlinear map, so trajectories are nontrivial, but it needs
no weights. Running it through ``comfy.k_diffusion.sampling.sample_euler`` / ``sample_dpmpp_2m``
at the pinned commit checks Tier A against the real update code, not against our own copy.
"""
from __future__ import annotations

import torch

from trajver.trajectory import Trajectory


class ToyDenoiser:
    def __init__(self, shape=(1, 4, 8, 8), seed=0, perturb: float = 0.0):
        g = torch.Generator().manual_seed(seed)
        self.target = torch.randn(shape, generator=g)
        self.mix = torch.randn(shape, generator=g) * 0.1
        self.perturb = perturb  # a "cheaper model": systematically different predictions

    def __call__(self, x, sigma, **kwargs):
        s = sigma.reshape(-1, *([1] * (x.ndim - 1))).to(x.dtype)
        w = 1.0 / (1.0 + s ** 2)
        D = w * x + (1 - w) * self.target + self.mix * torch.tanh(x)
        if self.perturb:
            D = D + self.perturb * torch.sin(3 * x)
        return D


def karras_like_sigmas(T=12, smax=14.6, smin=0.03):
    s = torch.exp(torch.linspace(torch.log(torch.tensor(smax)), torch.log(torch.tensor(smin)), T))
    return torch.cat([s, torch.zeros(1)]).to(torch.float32)


def run_sampler(sampler: str, denoiser: ToyDenoiser, sigmas: torch.Tensor, seed=1) -> Trajectory:
    import comfy.k_diffusion.sampling as ks

    fn = {"euler": ks.sample_euler, "dpmpp_2m": ks.sample_dpmpp_2m}[sampler]
    g = torch.Generator().manual_seed(seed)
    x0 = torch.randn(denoiser.target.shape, generator=g) * sigmas[0]
    xs, Ds = [], []

    def cb(d):
        xs.append(d["x"].detach().clone())
        Ds.append(d["denoised"].detach().clone())

    out = fn(denoiser, x0, sigmas, callback=cb, disable=True)
    return Trajectory(sigmas=sigmas.clone(), xs=xs, Ds=Ds, x_final=out.detach().clone(),
                      job={"toy": True, "sampler": sampler})


def toy_replay(denoiser: ToyDenoiser):
    def replay(states, sigmas):
        return {i: denoiser(x, sigmas[i].reshape(1)) for i, x in states.items()}
    return replay
