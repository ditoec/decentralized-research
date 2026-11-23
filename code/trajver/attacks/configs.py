"""Cost-saving attacks A1–A8 and the metadata control M, as declarative configurations.

Each attack says what the provider actually runs (``run``) and what it claims (``claim``). The
harness runs ``run`` on the provider node, then commits under the claimed job spec. Attacks that
need a separate ComfyUI process (different CLI flags) say so in ``flags``.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from ..job import JobSpec


@dataclass(frozen=True)
class Attack:
    id: str
    name: str
    flags: tuple[str, ...] = ()
    run_overrides: dict = field(default_factory=dict)
    forge: str | None = None        # how a full-length claimed trajectory is produced, if needed
    note: str = ""

    def run_spec(self, claimed: JobSpec) -> JobSpec:
        return replace(claimed, **self.run_overrides)


def attacks(claimed_steps: int = 30) -> dict[str, Attack]:
    a = [
        Attack("A1-25", "fewer steps", run_overrides={"steps": 25}, forge="schedule_relabel"),
        Attack("A1-20", "fewer steps", run_overrides={"steps": 20}, forge="schedule_relabel"),
        Attack("A1-15", "fewer steps", run_overrides={"steps": 15}, forge="schedule_relabel"),
        Attack("A2", "fp8 denoising network", flags=("--fp8_e4m3fn-unet",)),
        Attack("A2b", "4-bit model", note="only if supported at the pinned commit (pilot P4)"),
        Attack("A3-turbo", "distilled model", forge="interpolate_invert",
               note="SDXL-Turbo 1-4 steps or LCM-LoRA 4-8 steps; checkpoint chosen per model family"),
        Attack("A4", "sampler swap", note="cheaper sampler committed as the required one"),
        Attack("A5", "low resolution + upscale", note="half resolution, then upscale; mainly an E0 attack"),
        Attack("A6", "early exit", forge="tail_extrapolate", note="truncate at step j < T"),
        Attack("A7", "replay", note="output of a near-duplicate prompt (edit distance <= 2 words)"),
        Attack("A8", "unrelated output", note="sanity control"),
        Attack("M", "falsified metadata", note="negative control: verdicts must not change"),
    ]
    return {x.id: x for x in a}
