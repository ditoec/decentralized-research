"""Trajectory commitment and verification for escrow-settled diffusion inference.

Notation follows the manuscript: T sampler steps, states x_0 .. x_T (x_0 is the noise-scaled
initial latent, x_T the final latent), CFG-combined predictions D_0 .. D_{T-1}, noise levels
sigma_0 > ... > sigma_T. In files and code the final state is ``x_final``.
"""

__version__ = "0.1.0"
