#!/usr/bin/env python3
"""Pseudonymise internal host details in run folders before they are committed (the repo is public).

  python3 tools/sanitize_runs.py ../experiments/runs/<run> [...]      # rewrite in place
  python3 tools/sanitize_runs.py --check ../experiments/runs/*         # exit 1 if anything is left

What changes, in text files only (json, jsonl, log, txt, csv):
* Spark container hostnames ``<site>-dgx-N-esj`` become ``sparkN-esj``.
* Co-tenant container names become role labels: the LLM server keeps the role ``cotenant-llm``
  (P6 reads its load metrics); every other production container becomes ``cotenant-svc``.
  Their images become ``redacted``, except the LLM server's, which keeps only ``vllm``.
Numbers (memory, CPU, vLLM queue metrics) are untouched, so every measured value is preserved.
The unredacted originals stay on the node under ~/esj/runs.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

TEXT = {".json", ".jsonl", ".log", ".txt", ".csv", ".xml"}
HOST = re.compile(r"\b[a-z]+-dgx-(\d+)-esj\b")
LEAK = re.compile(r"[a-z]+-dgx-\d|[a-z]+-soc-|10\.\d+\.\d+\.\d+")


def role(name: str) -> str:
    if name.startswith("cotenant-"):
        return name
    return "cotenant-llm" if name.startswith("vllm") else "cotenant-svc"


def scrub_obj(o):
    if isinstance(o, dict):
        if "containers" in o and isinstance(o["containers"], list):
            for c in o["containers"]:
                if isinstance(c, dict) and "name" in c:
                    llm = c["name"].startswith("vllm") or c["name"] == "cotenant-llm"
                    c["name"] = role(c["name"])
                    if "image" in c:
                        c["image"] = "vllm" if llm else "redacted"
        if "vllm" in o and isinstance(o["vllm"], dict):
            o["vllm"] = {role(k): v for k, v in o["vllm"].items()}
        return {k: scrub_obj(v) for k, v in o.items()}
    if isinstance(o, list):
        return [scrub_obj(v) for v in o]
    if isinstance(o, str):
        return HOST.sub(r"spark\1-esj", o)
    return o


def scrub_text(s: str, suffix: str) -> str:
    if suffix == ".json":
        try:
            return json.dumps(scrub_obj(json.loads(s)), indent=1) + "\n"
        except json.JSONDecodeError:
            pass
    if suffix in (".jsonl", ".json"):
        out = []
        for line in s.splitlines():
            try:
                out.append(json.dumps(scrub_obj(json.loads(line))))
            except json.JSONDecodeError:
                out.append(HOST.sub(r"spark\1-esj", line))
        return "\n".join(out) + ("\n" if s.endswith("\n") else "")
    return HOST.sub(r"spark\1-esj", s)


def changed(s: str, suffix: str) -> bool:
    """True if scrubbing would change the content (not just the JSON whitespace)."""
    if suffix in (".json", ".jsonl"):
        try:
            objs = [json.loads(s)] if suffix == ".json" else [json.loads(l) for l in s.splitlines() if l.strip()]
            return any(scrub_obj(copy.deepcopy(o)) != o for o in objs)
        except json.JSONDecodeError:
            pass
    return HOST.sub(r"spark\1-esj", s) != s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    bad = 0
    for run in a.runs:
        for p in sorted(Path(run).rglob("*")):
            if not p.is_file() or p.suffix not in TEXT or "raw" in p.parts:
                continue
            s = p.read_text(errors="replace")
            if a.check:
                hits = set(LEAK.findall(s))
                if changed(s, p.suffix):
                    hits.add("unscrubbed co-tenant or host names")
                if hits:
                    print(p, sorted(hits))
                    bad += 1
                continue
            t = scrub_text(s, p.suffix)
            if t != s:
                p.write_text(t)
                print("scrubbed", p)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
