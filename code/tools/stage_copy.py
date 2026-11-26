#!/usr/bin/env python3
"""Stage finished GPU pods' results on a cheap CPU pod so the GPU pods can end (runbook §4,
decision of 2026-11-26). Runs on the staging pod next to pod_server.py. Standard library + curl.

  STAGE_SPEC='[{"tag": "rtx4090", "src": "https://<pod>-8000.proxy.runpod.net/<token>",
                "skip": ["<run already on the Spark>.tar", ...]}, ...]' python3 stage_copy.py

For each tag, in parallel: wait until the GPU pod wrote out/DONE (it may still be generating), then
download every tar in its out/INDEX that is not in "skip" into /work/stage/<tag>/out/, resuming
until complete, and check it against the pod's .sha256 (a mismatch is downloaded again). Then copy
pod.json, nvidia-smi-q.txt and lscpu.txt, write INDEX (all runs, skipped ones included, so the Spark's
pull_run.py sees the full list and skips what it already has), then DONE, then STAGED. Only then PUT
secret/release to the GPU pod, whose pod_selfstop.sh deletes it. The Spark pulls from
https://<staging>-8000.proxy.runpod.net/<token>/stage/<tag> afterwards. A GPU pod that wrote FAILED
is never released. Logs: /work/stage/<tag>/copy.log.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("POD_WORK", "/work")) / "stage"
UA = "curl/8 esj-stage"


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode()


def exists(url: str) -> bool:
    try:
        get(url)
        return True
    except Exception:  # noqa: BLE001
        return False


def retry(fn, log, what):
    while True:
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            log(f"{what} failed, retrying in 60 s: {e}")
            time.sleep(60)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def stage(spec: dict, poll: float) -> None:
    tag, src, skip = spec["tag"], spec["src"].rstrip("/"), set(spec.get("skip", []))
    d = ROOT / tag
    out = d / "out"
    out.mkdir(parents=True, exist_ok=True)
    logf = open(d / "copy.log", "a")

    def log(*a):
        logf.write(time.strftime("%Y-%m-%dT%H:%M:%SZ ", time.gmtime()) + " ".join(map(str, a)) + "\n")
        logf.flush()

    log("staging", tag, "skip", len(skip))
    while not exists(f"{src}/out/DONE"):
        if exists(f"{src}/out/FAILED"):
            log("GPU pod wrote FAILED; not staging, not releasing")
            return
        time.sleep(poll)
    index = retry(lambda: get(f"{src}/out/INDEX").split(), log, "INDEX")
    for t in index:
        if t in skip:
            continue
        local = out / t
        want = retry(lambda: get(f"{src}/out/{t}.sha256").strip(), log, f"{t}.sha256")
        while True:
            r = subprocess.run(["curl", "-sSf", "-A", UA, "--retry", "8", "-C", "-", "-o", str(local),
                                f"{src}/out/{t}"])
            if r.returncode != 0:
                log(f"curl exit {r.returncode} on {t}; resuming in 60 s")
                time.sleep(60)
                continue
            if sha256(local) == want:
                break
            log("CHECKSUM MISMATCH, downloading again:", t)
            local.unlink()
        (out / f"{t}.sha256").write_text(want + "\n")
        log("staged", t, local.stat().st_size)
    for f in ("pod.json", "nvidia-smi-q.txt", "lscpu.txt"):
        try:
            (out / f).write_text(get(f"{src}/out/{f}"))
        except Exception as e:  # noqa: BLE001
            log("could not copy", f, e)
    (out / "INDEX").write_text("\n".join(index) + "\n")
    (out / "DONE").write_text("ok\n")
    note = f"staged {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}: {len(index) - len(skip & set(index))} tars verified on the staging pod"
    (d / "STAGED").write_text(note + "\n")
    tmp = d / ".release"
    tmp.write_text(note + "\n")
    for _ in range(20):
        c = subprocess.run(["curl", "-sS", "-A", UA, "-o", "/dev/null", "-w", "%{http_code}", "-T", str(tmp),
                            f"{src}/secret/release"], capture_output=True, text=True)
        if c.stdout.strip() == "201":
            log("released the GPU pod:", note)
            return
        time.sleep(30)
    log("could not release the GPU pod; terminate it by hand")


def main() -> None:
    specs = json.loads(os.environ["STAGE_SPEC"])
    poll = float(os.environ.get("STAGE_POLL", "60"))
    ths = [threading.Thread(target=stage, args=(s, poll)) for s in specs]
    for t in ths:
        t.start()
    for t in ths:
        t.join()


if __name__ == "__main__":
    main()
