"""Run IDs and run manifests (runbook §0)."""
from __future__ import annotations

import datetime as _dt
import json
import os
import platform
import socket
import subprocess
from pathlib import Path

import torch

from . import __version__, comfy_env

REPO_ROOT = Path(__file__).resolve().parents[2]
# On the Sparks and pods the code lives outside a git checkout; TRAJVER_RUNS points at the run store.
RUNS = Path(os.environ.get("TRAJVER_RUNS", REPO_ROOT / "experiments" / "runs"))


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


def start(wp: str, name: str, purpose: str, rid: str | None = None, **fields) -> tuple[Path, dict]:
    given = rid
    rid = rid or run_id(wp, name)
    d = RUNS / rid
    resume = given is not None and (d / "manifest.json").exists()
    (d / "raw").mkdir(parents=True, exist_ok=given is not None)
    (d / "logs").mkdir(exist_ok=True)
    if resume:  # a restarted run (Spark runner stop condition) keeps its first manifest
        m = json.loads((d / "manifest.json").read_text())
        m.setdefault("restarts", []).append(_dt.datetime.now(_dt.timezone.utc).isoformat())
        (d / "manifest.json").write_text(json.dumps(m, indent=1, default=str))
        return d, m
    m = {
        "run_id": rid, "wp": wp, "purpose": purpose,
        # Outside a checkout (Sparks, pods) the runner passes the synced commit in TRAJVER_GIT_COMMIT.
        "git_commit": os.environ.get("TRAJVER_GIT_COMMIT") or _git("rev-parse", "HEAD"),
        "git_dirty": os.environ.get("TRAJVER_GIT_DIRTY", "") == "1" or _git("status", "--porcelain") not in ("", "unknown"),
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
