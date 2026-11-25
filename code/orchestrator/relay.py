"""Transaction relay: a long-lived ``code/program/scripts/relay.ts`` process spoken to in JSON lines."""
from __future__ import annotations

import itertools
import json
import subprocess
from pathlib import Path

PROGRAM_DIR = Path(__file__).resolve().parents[1] / "program"


class RelayError(RuntimeError):
    def __init__(self, op: str, error: str, logs=None):
        super().__init__(f"{op}: {error}")
        self.op, self.error, self.logs = op, error, logs or []


class Relay:
    def __init__(self, url: str, keys_json: str | Path, program_dir: Path = PROGRAM_DIR):
        if "mainnet" in url:
            raise ValueError("mainnet is never used")
        self.proc = subprocess.Popen(
            ["npx", "ts-node", "-P", "tsconfig.json", "scripts/relay.ts", "--url", url, "--keys", str(keys_json)],
            cwd=program_dir, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self._ids = itertools.count(1)

    def call(self, op: str, signer: str | None = None, **args) -> dict:
        rid = next(self._ids)
        self.proc.stdin.write(json.dumps({"id": rid, "op": op, "signer": signer, "args": args}) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RelayError(op, "relay exited")
        r = json.loads(line)
        if r.get("id") != rid:
            raise RelayError(op, f"out-of-order reply {r.get('id')} != {rid}")
        if not r["ok"]:
            raise RelayError(op, r.get("error", "?"), r.get("logs"))
        return r

    def close(self):
        if self.proc.poll() is None:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
