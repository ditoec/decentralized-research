"""ComfyUI custom node: KSampler that records and commits its trajectory.

Install by symlinking this folder into ``ComfyUI/custom_nodes/`` and making ``trajver``
importable (``pip install -e code``). The node has the stock KSampler inputs plus ``job_id``.
It writes ``<output>/trajectories/<job_id>/trajectory.safetensors`` and returns the Merkle root
as a string next to the latent. All logic lives in ``trajver.job.sample_and_record``.
"""
from __future__ import annotations

import os

import comfy.sample
import comfy.samplers
import folder_paths

from trajver import comfy_env
from trajver.job import DETERMINISTIC_SAMPLERS, sample_and_record


class KSamplerTrajectory:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "control_after_generate": True}),
                "steps": ("INT", {"default": 30, "min": 1, "max": 10000}),
                "cfg": ("FLOAT", {"default": 7.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01}),
                "sampler_name": (list(DETERMINISTIC_SAMPLERS),),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "latent_image": ("LATENT",),
                "job_id": ("STRING", {"default": "job"}),
            }
        }

    RETURN_TYPES = ("LATENT", "STRING")
    RETURN_NAMES = ("LATENT", "merkle_root")
    FUNCTION = "sample"
    CATEGORY = "sampling/trajver"

    def sample(self, model, seed, steps, cfg, sampler_name, scheduler, positive, negative, latent_image, job_id):
        latent = latent_image["samples"]
        latent = comfy.sample.fix_empty_latent_channels(model, latent, latent_image.get("downscale_ratio_spacial"),
                                                        latent_image.get("downscale_ratio_temporal"))
        noise = comfy.sample.prepare_noise(latent, seed, latent_image.get("batch_index"))
        ks = comfy.samplers.KSampler(model, steps=steps, device=model.load_device, sampler=sampler_name,
                                     scheduler=scheduler, denoise=1.0, model_options=model.model_options)
        samples, traj = sample_and_record(model, noise, latent, positive, negative, cfg, sampler_name,
                                          ks.sigmas, seed)
        traj.job = {"job_id": job_id, "seed": seed, "steps": steps, "cfg": cfg, "sampler": sampler_name,
                    "scheduler": scheduler, "pin_batching": comfy_env.PIN_BATCHING}
        out_dir = os.path.join(folder_paths.get_output_directory(), "trajectories", job_id)
        root = traj.save(os.path.join(out_dir, "trajectory.safetensors"))
        out = latent_image.copy()
        out.pop("downscale_ratio_spacial", None)
        out.pop("downscale_ratio_temporal", None)
        out["samples"] = samples
        return (out, root)


NODE_CLASS_MAPPINGS = {"KSamplerTrajectory": KSamplerTrajectory}
NODE_DISPLAY_NAME_MAPPINGS = {"KSamplerTrajectory": "KSampler (record trajectory)"}
