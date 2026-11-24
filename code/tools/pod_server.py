"""File server for a RunPod pod (runbook §3.4 items 2-3). Standard library only.

The pod is reached through RunPod's HTTPS proxy (https://<podId>-8000.proxy.runpod.net), which
is public. Every path must start with /<POD_TOKEN>/ (a random 32-hex token set at pod creation
and never logged); anything else is 404. Under that prefix:

  GET  /<token>/<path>    download a file from /work (supports Range, so curl -C - resumes)
  PUT  /<token>/<path>    upload a file into /work (code tarball from the operator)

The Sparks sit behind a VPN and cannot be reached from a pod, but they can reach the proxy, so
run data comes home by pull (tools/pull_run.py) and the pod is terminated only afterwards.
"""
from __future__ import annotations

import os
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(os.environ.get("POD_WORK", "/work")).resolve()
TOKEN = os.environ["POD_TOKEN"]


class H(BaseHTTPRequestHandler):
    def _target(self) -> Path | None:
        parts = self.path.split("?", 1)[0].lstrip("/").split("/", 1)
        if len(parts) != 2 or parts[0] != TOKEN or not parts[1]:
            return None
        p = (ROOT / parts[1]).resolve()
        return p if ROOT in p.parents else None

    def do_GET(self):
        p = self._target()
        if p is None or not p.is_file():
            self.send_error(404)
            return
        size = p.stat().st_size
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else 0
            end = int(b) if b else size - 1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        with open(p, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def do_PUT(self):
        p = self._target()
        if p is None:
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length", "0"))
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".part")
        with open(tmp, "wb") as f:
            left = n
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        shutil.move(tmp, p)
        self.send_response(201)
        self.end_headers()

    def log_message(self, fmt, *args):  # keep the token out of the pod log
        pass


if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("POD_PORT", "8000"))), H).serve_forever()
