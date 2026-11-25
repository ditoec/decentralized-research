#!/usr/bin/env python3
"""Spark runner (runbook §3.4 item 1). Runs ONE research command in a research container on a
DGX Spark under the production-safety rules of runbook §1.1, using only the host's python3
standard library (no installs on the host).

  python3 spark_run.py --run-id 20261124-wp0b-p2-spark4-a-01 [--image esj-research:main] \
      [--stack main] -- python -m trajver.pilot gen --run-id 20261124-wp0b-p2-spark4-a-01 ...

What it does:
* starts the container with label research=esj, a name esj-<run-id>, no published ports, the GPU,
  and bind mounts of the research folder (~/esj: code, models, runs); never touches other
  containers;
* every 5 s checks host MemAvailable and free disk. Below 15 GB memory or 200 GB disk it STOPS
  the container (pausing would keep the memory held), waits until memory is back above
  15 GB + the run's own footprint margin (default 20 GB) and disk above 200 GB, then starts the
  same command again. Workloads are resumable (trajver.pilot gen skips finished jobs), so the
  run continues where it stopped;
* writes a co-tenant snapshot every 15 s to <run>/logs/cotenants.json, which the workload copies
  into every job row: running non-research containers, their CPU/memory share, the vLLM
  request load scraped from each chat container's /metrics, and host memory;
* logs every stop and restart to <run>/logs/runner.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

MEM_MIN_GB = 15.0
DISK_MIN_GB = 200.0
ESJ = Path.home() / "esj"


def mem_available_gb() -> float:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1e6
    return 0.0


def disk_free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1e9


def sh(*args: str, check: bool = False, timeout: float = 60) -> str:
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"{args}: {r.stderr.strip()}")
    return r.stdout


def vllm_load() -> dict:
    """vLLM's own Prometheus metrics, read on the host loopback if the chat model publishes them
    there; otherwise via `docker exec` (read-only, no change to the container)."""
    out = {}
    for name in sh("docker", "ps", "--format", "{{.Names}}").split():
        if "vllm" not in name:
            continue
        txt = ""
        try:
            txt = sh("docker", "exec", name, "sh", "-c",
                     "curl -s -m 3 localhost:8000/metrics || python3 -c \"import urllib.request;"
                     "print(urllib.request.urlopen('http://localhost:8000/metrics',timeout=3).read().decode())\"",
                     timeout=10)
        except Exception:
            pass
        vals = {}
        for line in txt.splitlines():
            for key in ("vllm:num_requests_running", "vllm:num_requests_waiting", "vllm:gpu_cache_usage_perc",
                        "vllm:kv_cache_usage_perc"):
                if line.startswith(key + "{") or line.startswith(key + " "):
                    try:
                        vals[key.split(":")[1]] = vals.get(key.split(":")[1], 0.0) + float(line.rsplit(" ", 1)[1])
                    except ValueError:
                        pass
        out[name] = vals
    return out


def cotenants() -> dict:
    rows = []
    stats = sh("docker", "stats", "--no-stream", "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}", timeout=30)
    labels = {}
    for line in sh("docker", "ps", "--format", "{{.Names}}|{{.Label \"research\"}}|{{.Image}}").splitlines():
        n, lab, img = line.split("|", 2)
        labels[n] = (lab, img)
    for line in stats.splitlines():
        n, cpu, mem = line.split("|", 2)
        lab, img = labels.get(n, ("", ""))
        if lab != "esj":
            rows.append({"name": n, "image": img, "cpu": cpu, "mem": mem})
    return {"time": time.time(), "host_mem_available_gb": mem_available_gb(), "containers": rows,
            "vllm": vllm_load()}


class Cotenants(threading.Thread):
    def __init__(self, path: Path, period: float = 15.0):
        super().__init__(daemon=True)
        self.path, self.period, self.stop = path, period, threading.Event()

    def run(self):
        while not self.stop.is_set():
            try:
                snap = cotenants()
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(snap))
                tmp.replace(self.path)
            except Exception as e:  # a failed snapshot must never stop the run
                print("cotenant snapshot failed:", e, file=sys.stderr)
            self.stop.wait(self.period)


def log(run_dir: Path, **ev):
    ev["time"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with open(run_dir / "logs" / "runner.jsonl", "a") as f:
        f.write(json.dumps(ev) + "\n")
    print(json.dumps(ev), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--image", default="esj-research:main")
    ap.add_argument("--stack", default="main")
    ap.add_argument("--margin-gb", type=float, default=20.0, help="extra free memory required before (re)start")
    ap.add_argument("--max-guard-stops", type=int, default=3, help="give up after this many guard stops")
    ap.add_argument("--backoff-s", type=int, default=600, help="wait after a guard stop before restarting")
    ap.add_argument("--git-commit", default=os.environ.get("TRAJVER_GIT_COMMIT", ""))
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    runs = ESJ / "runs"
    run_dir = runs / a.run_id
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    name = "esj-" + a.run_id.lower()
    cot = run_dir / "logs" / "cotenants.json"
    watcher = Cotenants(cot)
    watcher.start()
    # the single software image is pinned by digest and recorded in every manifest (decision of 2026-11-24)
    digest = sh("docker", "image", "inspect", "-f", "{{.Id}}", a.image).strip()
    if not digest.startswith("sha256:"):
        raise SystemExit(f"image {a.image} not found")
    docker_run = [
        "docker", "run", "-d", "--name", name, "--hostname", f"{os.uname().nodename}-esj", "--label", "research=esj", "--gpus", "all",
        "--ipc", "host", "--ulimit", "memlock=-1",
        "-v", f"{ESJ}/code:/opt/esj/code", "-v", f"{ESJ}/experiments:/opt/esj/experiments:ro",
        "-v", f"{ESJ}/models:/models:ro", "-v", f"{runs}:/runs",
        "-v", f"{ESJ}/hf:/root/.cache/huggingface",
        "-e", "TRAJVER_RUNS=/runs", "-e", f"TRAJVER_COTENANT_FILE=/runs/{a.run_id}/logs/cotenants.json",
        "-e", f"TRAJVER_GIT_COMMIT={a.git_commit}", "-e", "PYTHONUNBUFFERED=1",
        "-e", f"TRAJVER_IMAGE_DIGEST={digest}",
        "-w", "/opt/esj/code", a.image, *cmd,
    ]
    (ESJ / "hf").mkdir(exist_ok=True)
    attempts = guard_stops = 0
    try:
        while True:
            need = MEM_MIN_GB + a.margin_gb
            while mem_available_gb() < need or disk_free_gb(ESJ) < DISK_MIN_GB:
                log(run_dir, event="waiting", mem_available_gb=round(mem_available_gb(), 1),
                    disk_free_gb=round(disk_free_gb(ESJ), 1), need_mem_gb=need)
                time.sleep(60)
            sh("docker", "rm", "-f", name)  # only our own, by exact name
            cid = sh(*docker_run, check=True).strip()
            attempts += 1
            log(run_dir, event="started", container=cid[:12], attempt=attempts,
                mem_available_gb=round(mem_available_gb(), 1))
            logf = open(run_dir / "logs" / f"container-{attempts}.log", "w")
            follower = subprocess.Popen(["docker", "logs", "-f", name], stdout=logf, stderr=subprocess.STDOUT)
            stopped_for, exit_code = None, -1
            while True:
                state = sh("docker", "inspect", "-f", "{{.State.Status}} {{.State.ExitCode}}", name).split()
                if not state or state[0] in ("exited", "dead"):
                    exit_code = int(state[1]) if len(state) > 1 else -1
                    break
                m, d = mem_available_gb(), disk_free_gb(ESJ)
                if m < MEM_MIN_GB or d < DISK_MIN_GB:
                    stopped_for = {"mem_available_gb": round(m, 1), "disk_free_gb": round(d, 1)}
                    sh("docker", "stop", "-t", "20", name, timeout=60)
                    break
                time.sleep(5)
            follower.wait(timeout=30)
            logf.close()
            if stopped_for:
                guard_stops += 1
                log(run_dir, event="stopped_by_guard", stops=guard_stops, **stopped_for)
                if guard_stops >= a.max_guard_stops:
                    # the workload itself needs more memory than the node can spare: do not keep retrying
                    log(run_dir, event="aborted", reason="memory guard tripped repeatedly; workload too large for this node")
                    return 3
                time.sleep(a.backoff_s)  # memory recovers as soon as we stop; give production room first
                continue
            sh("docker", "rm", "-f", name)
            # files written as root in the container: make the run readable for the pull (no sudo on the host)
            sh("docker", "run", "--rm", "--label", "research=esj", "-v", f"{runs}:/runs", a.image,
               "sh", "-c", "chmod -R a+rX /runs", timeout=600)
            ok = exit_code == 0
            log(run_dir, event="finished", ok=ok, exit_code=exit_code, attempts=attempts)
            return 0 if ok else 1
    finally:
        watcher.stop.set()
        sh("docker", "rm", "-f", name)


if __name__ == "__main__":
    sys.exit(main())
