#!/usr/bin/env python3
"""Pull finished runs from a RunPod pod to a Spark (runbook §3.4 item 3). Host python3 only.

  python3 pull_run.py https://<podId>-8000.proxy.runpod.net/<token> [--dest ~/esj/runs] [--wait]
                      [--reveal-seed SECRET_FILE]

With --wait, class-F runs the pod packs early (out/READY) are pulled while it keeps generating.
With class-O runs (runbook §3.5) the pod stops after generation (out/GENERATED) and waits for the
draw seed. --reveal-seed checks the file against the hash fixed before generation (in pod.json),
PUTs it to the pod, and then waits for the pod to extract, verify and pack. --wait polls until
the pod is DONE instead of exiting.

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
import threading
import time
import urllib.request
from pathlib import Path


def get(url: str) -> str:
    # the RunPod proxy (Cloudflare) answers 403 to urllib's default user agent
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8 esj-pull"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode()


def exists(url: str) -> bool:
    try:
        get(url)
        return True
    except Exception:  # noqa: BLE001
        return False


def reveal(base: str, secret: Path) -> None:
    seed_hex = secret.read_text().strip()
    pod = json.loads(get(f"{base}/out/pod.json"))
    want = pod.get("draw_seed_sha256")
    if not want or hashlib.sha256(bytes.fromhex(seed_hex)).hexdigest() != want:
        raise SystemExit("this seed does not match the hash the pod was given at creation; not revealing")
    subprocess.run(["curl", "-sSf", "-A", "curl/8 esj-pull", "-T", str(secret), f"{base}/secret/draw_seed.hex"],
                   check=True, stdout=subprocess.DEVNULL)
    print("draw seed revealed to the pod")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--dest", default=str(Path.home() / "esj" / "runs"))
    ap.add_argument("--pod-created-unix", type=float, default=None, help="for billed hours; default pod.json")
    ap.add_argument("--wait", action="store_true", help="poll until the pod job is DONE")
    ap.add_argument("--reveal-seed", default=None, help="draw seed file for class-O runs (after generation)")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    dest = Path(a.dest).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    pulled: set[str] = set()
    # The seed is revealed from its own thread: a class-F tar can take hours to download, and a
    # reveal that waits for it leaves the pod idle and billing (runbook §4, 2026-11-26).
    revealed = threading.Event()
    reveal_error: list[str] = []

    def revealer() -> None:
        secret = Path(a.reveal_seed).expanduser()
        while True:
            try:
                if exists(f"{base}/out/DONE") or exists(f"{base}/out/FAILED"):
                    return
                if exists(f"{base}/out/GENERATED"):
                    reveal(base, secret)
                    revealed.set()
                    return
            except SystemExit as e:  # wrong seed: never retry
                reveal_error.append(str(e))
                return
            except Exception as e:  # noqa: BLE001  (a network blip: try again next round)
                print("reveal attempt failed, retrying:", e, flush=True)
            time.sleep(30)

    if a.reveal_seed:
        threading.Thread(target=revealer, daemon=True).start()
    bad: list[str] = []

    def pull(tname: str) -> None:
        run = dest / tname[:-4]
        if tname in pulled or (run / "manifest.json").exists() and \
                "pulled_unix" in json.loads((run / "manifest.json").read_text()):
            pulled.add(tname)
            return
        local = dest / tname
        subprocess.run(["curl", "-sSf", "-A", "curl/8 esj-pull", "--retry", "8", "-C", "-", "-o", str(local),
                        f"{base}/out/{tname}"], check=True)
        want = get(f"{base}/out/{tname}.sha256").strip()
        h = hashlib.sha256()
        with open(local, "rb") as f:
            for b in iter(lambda: f.read(1 << 24), b""):
                h.update(b)
        if h.hexdigest() != want:
            print("CHECKSUM MISMATCH", tname, flush=True)
            bad.append(tname)
            local.unlink()
            return
        with tarfile.open(local) as t:
            t.extractall(dest, filter="data")
        pod = json.loads((run / "logs" / "pod.json").read_text())
        m = json.loads((run / "manifest.json").read_text())
        start = a.pod_created_unix or pod.get("job_start_unix")
        hours = (time.time() - start) / 3600 if start else None
        rate = pod.get("hourly_rate_usd")
        # billed_hours: pod time from the job start to this pull, an upper bound per run; the RunPod
        # balance is the source for totals (runbook §3 finding 18)
        m.update(provider="runpod", cloud_type=pod.get("cloud_type"), host_id=pod.get("pod_id"),
                 data_center=pod.get("data_center"), gpu_uuid=pod.get("gpu_uuid"), driver=pod.get("driver"),
                 hourly_rate_usd=rate, billed_hours=hours, cost_usd=(hours * rate if hours and rate else None),
                 raw_checksums={tname: want}, pulled_unix=time.time())
        (run / "manifest.json").write_text(json.dumps(m, indent=1))
        local.unlink()
        pulled.add(tname)
        print("pulled", run.name, flush=True)

    while True:
        if exists(f"{base}/out/FAILED"):
            print("pod job FAILED:", get(f"{base}/out/FAILED").strip(), flush=True)
            return 3
        if exists(f"{base}/out/DONE"):
            break
        generated = exists(f"{base}/out/GENERATED")
        if generated and not revealed.is_set():
            if not a.reveal_seed:
                print("pod is waiting for the draw seed: rerun with --reveal-seed")
                return 2
            if reveal_error:
                print(reveal_error[0], flush=True)
                return 4
        if not (a.wait or generated or revealed.is_set()):
            print("pod job not finished")
            return 2
        # runs the pod packed early (class F, runbook §3 finding 18) come home while it generates
        if exists(f"{base}/out/READY"):
            for tname in get(f"{base}/out/READY").split():
                pull(tname)
        time.sleep(30)
    for tname in get(f"{base}/out/INDEX").split():
        pull(tname)
    ok = not bad
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
