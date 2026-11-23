"""Initial noise, reproduced exactly as ComfyUI draws it (comfy/sample.py: prepare_noise_inner).

ComfyUI calls ``torch.manual_seed(seed)`` and then draws ``torch.randn(shape, dtype=float32,
device="cpu")`` from the returned default generator. A fresh CPU generator seeded with the same
value produces the same stream, so the verifier needs only the seed, the latent shape and the
torch version. Whether the bytes also agree across CPU instruction sets (x86 vs ARM) is pilot
item P1 and result R1.1.
"""
from __future__ import annotations

import hashlib
import math

import torch


def initial_noise(shape, seed: int, dtype: torch.dtype = torch.float32) -> torch.Tensor:
    g = torch.Generator(device="cpu")
    g.manual_seed(seed)
    return torch.randn(tuple(shape), dtype=torch.float32, generator=g, device="cpu").to(dtype)


def noise_digest(shape, seed: int) -> str:
    """sha256 of the raw float32 bytes of the initial noise (pilot P1)."""
    return hashlib.sha256(initial_noise(shape, seed).numpy().tobytes()).hexdigest()


def max_denoise(model_sampling, sigmas: torch.Tensor) -> bool:
    """Mirror of comfy.samplers.KSAMPLER.max_denoise."""
    max_sigma = float(model_sampling.sigma_max)
    sigma = float(sigmas[0])
    return math.isclose(max_sigma, sigma, rel_tol=1e-05) or sigma > max_sigma


def expected_x0(model_sampling, noise: torch.Tensor, sigmas: torch.Tensor, latent_image: torch.Tensor,
                device: torch.device | str = "cpu") -> torch.Tensor:
    """x_0 as KSAMPLER.sample builds it: noise_scaling(sigma_0, noise, latent, max_denoise).

    The provider computes this on its own device in float32. ``device`` lets the verifier
    reproduce it on the same kind of device, or on the CPU.
    """
    noise = noise.to(device=device, dtype=torch.float32)
    latent_image = latent_image.to(device=device, dtype=torch.float32)
    sigmas = sigmas.to(device)
    return model_sampling.noise_scaling(sigmas[0], noise, latent_image, max_denoise(model_sampling, sigmas)).cpu()
