#!/usr/bin/env python3
"""Pull finished runs from a RunPod pod to a Spark (runbook §3.4 item 3). Host python3 only.

  python3 pull_run.py https://<podId>-8000.proxy.runpod.net/<token> [--dest ~/esj/runs] [--hourly 0.39]

Reads out/INDEX, downloads each <run>.tar with resume (curl -C -), checks it against
<run>.tar.sha256, extracts it under --dest, and adds the cost fields to the run manifest
(billed hours from pod.json's start to now, times the hourly rate). Exits non-zero unless every
run verified, so the operator terminates the pod only after a clean pull.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path


def get(url: str) -> str:
    # the RunPod proxy (Cloudflare) answers 403 to urllib's default user agent
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8 esj-pull"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--dest", default=str(Path.home() / "esj" / "runs"))
    ap.add_argument("--pod-created-unix", type=float, default=None, help="for billed hours; default pod.json")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    dest = Path(a.dest).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    if get(f"{base}/out/DONE").strip() != "ok":
        print("pod job not finished")
        return 2
    names = get(f"{base}/out/INDEX").split()
    ok = True
    for tname in names:
        local = dest / tname
        subprocess.run(["curl", "-sSf", "--retry", "8", "-C", "-", "-o", str(local), f"{base}/out/{tname}"], check=True)
        want = get(f"{base}/out/{tname}.sha256").strip()
        h = hashlib.sha256()
        with open(local, "rb") as f:
            for b in iter(lambda: f.read(1 << 24), b""):
                h.update(b)
        if h.hexdigest() != want:
            print("CHECKSUM MISMATCH", tname)
            ok = False
            continue
        with tarfile.open(local) as t:
            t.extractall(dest, filter="data")
        run = dest / tname[:-4]
        pod = json.loads((run / "logs" / "pod.json").read_text())
        m = json.loads((run / "manifest.json").read_text())
        start = a.pod_created_unix or pod.get("job_start_unix")
        hours = (time.time() - start) / 3600 if start else None
        rate = pod.get("hourly_rate_usd")
        m.update(provider="runpod", cloud_type=pod.get("cloud_type"), host_id=pod.get("pod_id"),
                 data_center=pod.get("data_center"), gpu_uuid=pod.get("gpu_uuid"), driver=pod.get("driver"),
                 hourly_rate_usd=rate, billed_hours=hours, cost_usd=(hours * rate if hours and rate else None),
                 raw_checksums={tname: want}, pulled_unix=time.time())
        (run / "manifest.json").write_text(json.dumps(m, indent=1))
        local.unlink()
        print("pulled", run.name)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
