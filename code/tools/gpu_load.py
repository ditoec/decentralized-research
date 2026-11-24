"""Controlled co-located load for P6 (runbook §2), run in its own research container.

  python tools/gpu_load.py --seconds 1800 --hold-gb 6 --matmul 8192

Holds --hold-gb of GPU memory (on a Spark this is unified memory, so it also lowers host free
memory, which is what ComfyUI's memory-adaptive batching reads) and keeps the GPU busy with
fp16 matmuls of size --matmul. This replaces "the chat model is serving requests": production
services are never driven by research code, so the busy condition is load we own and can repeat.
Writes a heartbeat line every 30 s with the achieved TFLOP/s.
"""
from __future__ import annotations

import argparse
import json
import time

import torch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=1800)
    ap.add_argument("--hold-gb", type=float, default=6.0)
    ap.add_argument("--matmul", type=int, default=8192)
    a = ap.parse_args()
    dev = "cuda"
    hold = torch.empty(int(a.hold_gb * 1e9), dtype=torch.uint8, device=dev).fill_(1)
    n = a.matmul
    x = torch.randn(n, n, device=dev, dtype=torch.float16)
    y = torch.randn(n, n, device=dev, dtype=torch.float16)
    t0 = last = time.time()
    k = 0
    while time.time() - t0 < a.seconds:
        torch.mm(x, y)
        k += 1
        if k % 50 == 0:
            torch.cuda.synchronize()
            now = time.time()
            if now - last >= 30:
                print(json.dumps({"t": round(now - t0, 1), "iters": k,
                                  "tflops": round(2 * n ** 3 * k / (now - t0) / 1e12, 2),
                                  "hold_gb": hold.numel() / 1e9}), flush=True)
                last = now
    torch.cuda.synchronize()
    print(json.dumps({"done": True, "iters": k, "seconds": round(time.time() - t0, 1)}), flush=True)


if __name__ == "__main__":
    main()
