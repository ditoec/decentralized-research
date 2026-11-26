#!/usr/bin/env python3
"""Release a RunPod pod once its runs are safely home (runbook §4). Host python3 only; runs on the
Spark next to tools/pull_run.py, so the rental ends without a laptop staying on.

  python3 release_pod.py https://<podId>-8000.proxy.runpod.net/<token> [--dest ~/esj/runs]

Polls the pod until out/DONE, then waits until every run named in out/INDEX is in --dest with
pulled_unix in its manifest (pull_run.py writes that only after the tar's sha256 matched) and no
partial tar is left. Then runs `python -m trajver.retention check` on those runs in a research
container (label research=esj, no GPU), and only if it passes PUTs secret/release to the pod.
tools/pod_selfstop.sh on the pod then deletes the pod. A pod that wrote out/FAILED is never released.
Exit codes: 0 released, 3 pod FAILED, 4 retention check failed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pull_run import exists, get  # noqa: E402

CHECK = ("docker run --rm --name esj-retcheck-{pod}-{uid} --label research=esj "
         "-v {dest}:/runs -v {code}:/opt/esj/code -w /opt/esj/code esj-research:main "
         "python -m trajver.retention check {runs}")


def log(*a) -> None:
    print(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), *a, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--dest", default=str(Path.home() / "esj" / "runs"))
    ap.add_argument("--code", default=str(Path.home() / "esj" / "code"))
    ap.add_argument("--poll", type=float, default=120)
    ap.add_argument("--check-cmd", default=CHECK, help="template; {dest} {code} {runs} {pod} are filled in")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    dest = Path(a.dest).expanduser()
    host = base.split("//", 1)[-1].split("/", 1)[0]
    pod = "".join(ch for ch in host.split("-8000", 1)[0] if ch.isalnum())  # the pod id, never the token
    while True:
        try:
            if exists(f"{base}/out/FAILED"):
                log("pod job FAILED, not releasing:", get(f"{base}/out/FAILED").strip())
                return 3
            if exists(f"{base}/out/DONE"):
                names = [t[:-4] for t in get(f"{base}/out/INDEX").split()]
                missing = [n for n in names if not (dest / n / "manifest.json").exists()
                           or "pulled_unix" not in json.loads((dest / n / "manifest.json").read_text())
                           or (dest / f"{n}.tar").exists()]
                if not missing:
                    break
                log(f"{len(names) - len(missing)}/{len(names)} runs pulled and verified; waiting")
        except Exception as e:  # noqa: BLE001  (proxy blip: try again)
            log("poll failed, retrying:", e)
        time.sleep(a.poll)
    runs = " ".join(f"/runs/{n}" for n in names)
    cmd = a.check_cmd.format(dest=dest, code=Path(a.code).expanduser(), runs=runs, pod=pod, uid=os.getpid())
    log("all", len(names), "runs pulled and verified; retention check")
    r = subprocess.run(cmd, shell=True)
    if r.returncode != 0:
        log("retention check FAILED (exit", r.returncode, "); not releasing")
        return 4
    note = f"released {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}: {len(names)} runs verified"
    note_file = dest / f".release-{pod}"
    note_file.write_text(note + "\n")  # a file, not stdin: pod_server needs a Content-Length
    for _ in range(10):
        c = subprocess.run(["curl", "-sS", "-A", "curl/8 esj-pull", "-o", "/dev/null", "-w", "%{http_code}",
                            "-T", str(note_file), f"{base}/secret/release"], capture_output=True, text=True)
        if c.stdout.strip() == "201":
            break
        time.sleep(30)
    else:
        log("could not PUT secret/release; terminate the pod by hand")
        return 5
    log(note, "; pod will delete itself")
    for _ in range(40):  # confirm it is gone (the proxy stops answering for a deleted pod)
        time.sleep(30)
        if not exists(f"{base}/out/DONE"):
            log("pod no longer answers: terminated")
            return 0
    log("pod still answers 20 min after release; check it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
