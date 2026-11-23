"""Run IDs and run manifests (runbook §0)."""
from __future__ import annotations

import datetime as _dt
import json
import platform
import socket
import subprocess
from pathlib import Path

import torch

from . import __version__, comfy_env

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS = REPO_ROOT / "experiments" / "runs"


def run_id(wp: str, name: str, date: _dt.date | None = None) -> str:
    """``YYYYMMDD-<wp>-<name>-<nn>`` with the next free nn."""
    d = (date or _dt.date.today()).strftime("%Y%m%d")
    stem = f"{d}-{wp}-{name}"
    n = 1
    while (RUNS / f"{stem}-{n:02d}").exists():
        n += 1
    return f"{stem}-{n:02d}"


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(REPO_ROOT), *args], text=True).strip()
    except Exception:
        return "unknown"


def node_info() -> dict:
    info = {
        "hostname": socket.gethostname(),
        "os": platform.platform(),
        "cpu_isa": platform.machine(),
        "cpu_model": platform.processor() or platform.machine(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
    }
    if torch.cuda.is_available():
        info.update(gpu_name=torch.cuda.get_device_name(), compute_capability=list(torch.cuda.get_device_capability()),
                    gpu_uuid=str(getattr(torch.cuda.get_device_properties(0), "uuid", "")))
        try:
            info["driver"] = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], text=True).strip()
        except Exception:
            info["driver"] = "unknown"
    elif torch.backends.mps.is_available():
        info["gpu_name"] = "Apple MPS"
    return info


def start(wp: str, name: str, purpose: str, **fields) -> tuple[Path, dict]:
    rid = run_id(wp, name)
    d = RUNS / rid
    (d / "raw").mkdir(parents=True)
    (d / "logs").mkdir()
    m = {
        "run_id": rid, "wp": wp, "purpose": purpose,
        "git_commit": _git("rev-parse", "HEAD"), "git_dirty": bool(_git("status", "--porcelain")),
        "trajver_version": __version__,
        "comfyui_commit": comfy_env.comfy_commit(), "cli_flags": list(comfy_env.configured_flags() or ()),
        "node": node_info(),
        "start_time": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        **fields,
    }
    (d / "manifest.json").write_text(json.dumps(m, indent=1, default=str))
    return d, m


def finish(d: Path, manifest: dict, summary: dict) -> None:
    manifest["end_time"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    (d / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
    (d / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
