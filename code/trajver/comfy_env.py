"""Import the pinned ComfyUI as a library, with chosen command-line flags.

ComfyUI reads its flags once, when ``comfy.cli_args`` is first imported. Call :func:`configure`
with the flags of the run (for example ``["--fp8_e4m3fn-unet"]`` for attack A2, or
``["--force-fp32"]``) **before** anything imports ``comfy``. A second call with different
flags in the same process is an error: start a new process per configuration.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PINNED_COMMIT = "8b25bbc371b73e876996cf14c917d075d78de2ee"
_DEFAULT_ROOT = Path(__file__).resolve().parent.parent / ".cache" / "ComfyUI"
_configured: tuple[str, ...] | None = None


def comfy_root() -> Path:
    return Path(os.environ.get("TRAJVER_COMFYUI", _DEFAULT_ROOT)).resolve()


def comfy_commit(root: Path | None = None) -> str:
    root = root or comfy_root()
    try:
        return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def configure(flags: list[str] | tuple[str, ...] = (), require_pinned: bool = True) -> tuple[str, ...]:
    """Put ComfyUI on sys.path and parse ``flags`` as its command line. Returns the flags."""
    global _configured
    flags = tuple(flags)
    if _configured is not None:
        if flags != _configured:
            raise RuntimeError(f"ComfyUI already configured with {_configured}; got {flags}. Use a new process.")
        return flags
    root = comfy_root()
    if not (root / "comfy" / "samplers.py").exists():
        raise FileNotFoundError(f"ComfyUI not found at {root}; run tools/fetch_comfyui.sh or set TRAJVER_COMFYUI")
    if require_pinned and comfy_commit(root) != PINNED_COMMIT:
        raise RuntimeError(f"ComfyUI at {root} is at {comfy_commit(root)}, expected pinned {PINNED_COMMIT}")
    if "comfy.cli_args" in sys.modules:
        raise RuntimeError("comfy was imported before trajver.comfy_env.configure()")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import comfy.options

    saved = sys.argv
    comfy.options.enable_args_parsing(True)
    try:
        sys.argv = ["main.py", *flags]
        import comfy.cli_args  # noqa: F401  (parses sys.argv once)
    finally:
        sys.argv = saved
        comfy.options.enable_args_parsing(False)
    _configured = flags
    return flags


def configured_flags() -> tuple[str, ...] | None:
    return _configured


# ----------------------------------------------------------------------------- batching pin
# ComfyUI sizes batches from the free memory at the moment of each call:
#   comfy/samplers.py _calc_cond_batch: cond and uncond run as one batch only if
#       memory_required * 1.5 < model.current_patcher.get_free_memory(device);
#   comfy/sd.py VAE.decode: batch size and tiling also follow get_free_memory.
# A different batch composition changes the arithmetic, so identical jobs can give different
# trajectories depending on what else uses memory (found in dev testing on MPS). On nodes that
# share memory with other workloads this is a real source of honest variation. With
# PIN_BATCHING on, trajver reports unlimited free memory during sampling, replay and decoding:
# CFG always runs as one batch and the VAE decodes untiled. Provider and verifier must agree on
# this setting; it is recorded in every trajectory's job metadata.
PIN_BATCHING = True
_PINNED_FREE_MEMORY = 1 << 60


class pinned_batching:
    """Context manager: make ComfyUI's memory-adaptive batch decisions constant."""

    def __init__(self, enabled: bool | None = None):
        self.enabled = PIN_BATCHING if enabled is None else enabled
        self._orig = None

    def __enter__(self):
        if self.enabled:
            import comfy.model_patcher

            self._orig = comfy.model_patcher.ModelPatcher.get_free_memory
            comfy.model_patcher.ModelPatcher.get_free_memory = lambda self_, device: _PINNED_FREE_MEMORY
        return self

    def __exit__(self, *exc):
        if self._orig is not None:
            import comfy.model_patcher

            comfy.model_patcher.ModelPatcher.get_free_memory = self._orig
        return False
