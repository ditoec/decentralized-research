"""Run a ComfyUI text-to-image job and record its trajectory.

``Pipeline.run`` mirrors ``nodes.common_ksampler`` + ``comfy.sample.sample`` at the pinned commit,
with two additions that do not change the computation (acceptance test T1):

* a sampler callback that copies (x_i, D_i) to the CPU at every step, as ComfyUI hands them
  over (internal latent space, sampler dtype);
* a wrapper around the sampler function that captures the final state x_T before
  ``inverse_noise_scaling`` and ``process_latent_out`` (the callback never sees it).

Call ``trajver.comfy_env.configure(flags)`` before constructing a Pipeline.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import torch

from . import comfy_env
from .trajectory import Trajectory

DETERMINISTIC_SAMPLERS = ("euler", "heun", "dpmpp_2m", "ddim", "lms", "uni_pc")


@dataclass
class JobSpec:
    prompt: str
    seed: int
    negative: str = ""
    steps: int = 30
    cfg: float = 7.0
    sampler: str = "euler"
    scheduler: str = "normal"
    width: int = 512
    height: int = 512
    denoise: float = 1.0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()


def sha256_file(path: str | Path, chunk: int = 1 << 24) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def _cpu(t: torch.Tensor) -> torch.Tensor:
    return t.detach().to("cpu", copy=True)


def canonical_sigmas(model, scheduler: str, steps: int, sampler_name: str, denoise: float | None = 1.0) -> torch.Tensor:
    """The noise schedule, computed on the CPU from a CPU copy of the model's sampling object.

    ``comfy.samplers.KSampler`` computes the schedule on whatever device ``model_sampling`` sits
    on: the CPU before the first job of a process, the GPU after the model was loaded. The two
    differ by about one float32 ulp, and that changes the whole trajectory (found on an RTX 5080,
    2026-11-23: first and second run of the same job differed by up to 0.36 in the final latent).
    The protocol therefore fixes the schedule as this CPU computation; it mirrors
    ``KSampler.calculate_sigmas`` / ``set_steps`` at the pinned commit.
    """
    import copy

    import comfy.samplers

    ms = copy.deepcopy(model.get_model_object("model_sampling")).to("cpu")
    KS = comfy.samplers.KSampler

    def calc(n: int) -> torch.Tensor:
        discard = sampler_name in KS.DISCARD_PENULTIMATE_SIGMA_SAMPLERS
        if discard:
            n += 1
        s = comfy.samplers.calculate_sigmas(ms, scheduler, n)
        if discard:
            s = torch.cat([s[:-2], s[-1:]])
        return s.detach().cpu()

    if denoise is None or denoise > 0.9999:
        return calc(steps)
    if denoise <= 0.0:
        return torch.FloatTensor([])
    return calc(int(steps / denoise))[-(steps + 1):]


def sample_and_record(model, noise, latent, positive, negative, cfg: float, sampler_name: str,
                      sigmas: torch.Tensor, seed: int, allow_nondeterministic: bool = False):
    """``comfy.sample.sample`` with trajectory recording. Shared by Pipeline.run and the node.

    Returns (output-space samples, Trajectory without job metadata).
    """
    import comfy.model_management as mm
    import comfy.samplers

    if sampler_name not in DETERMINISTIC_SAMPLERS and not allow_nondeterministic:
        raise ValueError(f"sampler {sampler_name!r} draws per-step noise on the GPU; not allowed (doc 06 §1.1)")
    rec: dict = {"xs": [], "Ds": []}
    sampler = comfy.samplers.sampler_object(sampler_name)
    inner = sampler.sampler_function

    def recording_sampler(model_k, x, sigmas_dev, *args, **kwargs):
        out = inner(model_k, x, sigmas_dev, *args, **kwargs)
        rec["x_final"] = _cpu(out)
        rec["sigmas"] = _cpu(sigmas_dev)
        return out

    sampler.sampler_function = recording_sampler

    def callback(step, denoised, x, total_steps):
        if step != len(rec["xs"]):
            raise RuntimeError(f"callback step {step} out of order")
        rec["xs"].append(_cpu(x))
        rec["Ds"].append(_cpu(denoised))

    with comfy_env.pinned_batching():
        samples = comfy.samplers.sample(model, noise, positive, negative, cfg, model.load_device, sampler,
                                        sigmas, model.model_options, latent_image=latent, denoise_mask=None,
                                        callback=callback, disable_pbar=True, seed=seed)
    samples = samples.to(device=mm.intermediate_device(), dtype=mm.intermediate_dtype())

    conds = {"cond_pos": _cpu(positive[0][0]), "cond_neg": _cpu(negative[0][0])}
    for name, c in (("cond_pos_pooled", positive), ("cond_neg_pooled", negative)):
        pooled = c[0][1].get("pooled_output")
        if pooled is not None:
            conds[name] = _cpu(pooled)
    traj = Trajectory(sigmas=rec["sigmas"], xs=rec["xs"], Ds=rec["Ds"], x_final=rec["x_final"], conds=conds)
    return samples, traj


class Pipeline:
    """One loaded checkpoint (model, text encoder, VAE)."""

    def __init__(self, ckpt_path: str | Path, ckpt_sha256: str | None = None):
        if comfy_env.configured_flags() is None:
            comfy_env.configure(())
        import comfy.sd

        self.ckpt_path = str(ckpt_path)
        self.ckpt_sha256 = ckpt_sha256
        out = comfy.sd.load_checkpoint_guess_config(self.ckpt_path, output_vae=True, output_clip=True)
        self.model, self.clip, self.vae = out[0], out[1], out[2]

    # ----------------------------------------------------------- building blocks (as the nodes do)
    def encode(self, text: str):
        tokens = self.clip.tokenize(text)
        return self.clip.encode_from_tokens_scheduled(tokens)

    def empty_latent(self, spec: JobSpec) -> torch.Tensor:
        import comfy.model_management as mm
        import comfy.sample

        latent = torch.zeros([1, 4, spec.height // 8, spec.width // 8],
                             device=mm.intermediate_device(), dtype=mm.intermediate_dtype())
        return comfy.sample.fix_empty_latent_channels(self.model, latent, 8, None)

    def ksampler(self, spec: JobSpec):
        import comfy.samplers

        return comfy.samplers.KSampler(self.model, steps=spec.steps, device=self.model.load_device,
                                       sampler=spec.sampler, scheduler=spec.scheduler,
                                       denoise=spec.denoise, model_options=self.model.model_options)

    def schedule(self, spec: JobSpec) -> torch.Tensor:
        """The canonical (CPU-computed) schedule of the job; see ``canonical_sigmas``."""
        return canonical_sigmas(self.model, spec.scheduler, spec.steps, spec.sampler, spec.denoise)

    def model_sampling(self):
        return self.model.get_model_object("model_sampling")

    def model_dtype(self) -> torch.dtype:
        return self.model.model_dtype()

    def decode(self, samples: torch.Tensor) -> torch.Tensor:
        """VAE decode of output-space latents -> float image [B, H, W, 3] in [0, 1]."""
        with comfy_env.pinned_batching():
            return self.vae.decode(samples).detach().cpu()

    @staticmethod
    def to_uint8(images: torch.Tensor) -> torch.Tensor:
        # nodes.SaveImage: clip(255 * i, 0, 255).astype(uint8)
        return torch.clamp(images * 255.0, 0, 255).to(torch.uint8)

    def latent_out(self, x_internal: torch.Tensor) -> torch.Tensor:
        """process_latent_out as CFGGuider.inner_sample applies it (on float32)."""
        dev = self.model.load_device
        return self.model.model.process_latent_out(x_internal.to(device=dev, dtype=torch.float32)).cpu()

    # ----------------------------------------------------------- stock path (reference for T1)
    def run_stock(self, spec: JobSpec) -> torch.Tensor:
        import comfy.sample

        latent = self.empty_latent(spec)
        noise = comfy.sample.prepare_noise(latent, spec.seed)
        pos, neg = self.encode(spec.prompt), self.encode(spec.negative)
        with comfy_env.pinned_batching():
            return comfy.sample.sample(self.model, noise, spec.steps, spec.cfg, spec.sampler, spec.scheduler,
                                       pos, neg, latent, denoise=spec.denoise, callback=None,
                                       disable_pbar=True, seed=spec.seed, sigmas=self.schedule(spec))

    # ----------------------------------------------------------- recording path
    def run(self, spec: JobSpec, sigmas: torch.Tensor | None = None,
            allow_nondeterministic: bool = False) -> tuple[torch.Tensor, Trajectory]:
        """Run the job; return (output-space samples, recorded trajectory).

        ``sigmas`` overrides the schedule (used by attack A1 to run fewer steps).
        """
        import comfy.sample

        latent = self.empty_latent(spec)
        noise = comfy.sample.prepare_noise(latent, spec.seed)
        pos, neg = self.encode(spec.prompt), self.encode(spec.negative)
        if sigmas is None:
            sigmas = self.schedule(spec)
        samples, traj = sample_and_record(self.model, noise, latent, pos, neg, spec.cfg, spec.sampler, sigmas,
                                          spec.seed, allow_nondeterministic)
        traj.job = self.job_record(spec)
        return samples, traj

    def job_record(self, spec: JobSpec) -> dict:
        return {
            "spec": spec.to_dict(),
            "ckpt": Path(self.ckpt_path).name,
            "ckpt_sha256": self.ckpt_sha256,
            "comfyui_commit": comfy_env.comfy_commit(),
            "cli_flags": list(comfy_env.configured_flags() or ()),
            "device": str(self.model.load_device),
            "model_dtype": str(self.model_dtype()),
            "pin_batching": comfy_env.PIN_BATCHING,
        }

    # ----------------------------------------------------------- one-step replay (Tier B, E2-W)
    def replay_denoised(self, spec: JobSpec, states: dict[int, torch.Tensor], sigmas: torch.Tensor) -> dict[int, torch.Tensor]:
        """Recompute D_i = CFG(model(x_i, sigma_i)) for the given {i: x_i}.

        The call goes through ``comfy.samplers.sample`` with a sampler function that makes one
        model call per requested step instead of iterating, so conditioning preparation, CFG
        batching, model patching and ``extra_args`` are exactly those of the provider's run.
        The committed D_i are never read here (commit-before-reveal is enforced by the caller).
        """
        import comfy.samplers

        latent = self.empty_latent(spec)
        dummy_noise = torch.zeros_like(latent, device="cpu")
        pos, neg = self.encode(spec.prompt), self.encode(spec.negative)
        out: dict[int, torch.Tensor] = {}

        def replay_sampler(model_k, x, sigmas_dev, extra_args=None, callback=None, disable=None, **kw):
            extra_args = {} if extra_args is None else extra_args
            s_in = x.new_ones([x.shape[0]])
            for i in sorted(states):
                xi = states[i].to(device=x.device, dtype=x.dtype)
                out[i] = _cpu(model_k(xi, sigmas_dev[i] * s_in, **extra_args))
            return x

        sampler = comfy.samplers.KSAMPLER(replay_sampler)
        with comfy_env.pinned_batching():
            comfy.samplers.sample(self.model, dummy_noise, pos, neg, spec.cfg, self.model.load_device, sampler,
                                  sigmas, self.model.model_options, latent_image=latent, denoise_mask=None,
                                  callback=None, disable_pbar=True, seed=spec.seed)
        return out
