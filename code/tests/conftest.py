import os
from pathlib import Path

import pytest

CODE = Path(__file__).resolve().parents[1]
SD15 = Path(os.environ.get("TRAJVER_SD15", CODE / ".cache" / "models" / "checkpoints" / "v1-5-pruned-emaonly.safetensors"))


@pytest.fixture(scope="session")
def comfy():
    """Configure the pinned ComfyUI once per test process (default flags)."""
    from trajver import comfy_env

    try:
        comfy_env.configure(())
    except FileNotFoundError as e:
        pytest.skip(str(e))
    return comfy_env


@pytest.fixture(scope="session")
def sd15_path():
    if not SD15.exists():
        pytest.skip(f"SD1.5 checkpoint not found at {SD15}")
    return SD15
