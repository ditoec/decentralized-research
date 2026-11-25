"""Data retention for rented jobs (runbook §3.5): retention classes F, O and I.

A rented pod cannot send every SDXL trajectory home (about 2 MB/s from RunPod to the Sparks), so
what each job keeps depends on its class:

  F  full trajectory, as on a Spark (calibration and dev prompts; nothing changes)
  O  "opened steps": the delivered image, the Merkle root, and a bundle that opens, with inclusion
     proofs, x_0, the schedule, the conditioning, x_final and the tensors of the pre-drawn steps;
     plus the pod-side Tier A residuals of every step (test prompts, attacked jobs)
  I  image level: the image, the root, x_final and the schedule (opened), and Tier A (factor runs)

Step draw (rule 1). Before a class-O workload a random 32-byte ``draw_seed`` is made on the
operator's machine (``newseed``); only its sha256 goes to the pod and into the manifests. After
generation the seed is revealed to the pod for extraction (rule 2: injectors never see it). For each
job the order of all T steps is a Fisher-Yates shuffle driven by a SHA-256 counter stream keyed by
``sha256(draw_seed || job_id)``, so it is the same in any language and Python version:

  Tier B / E2-H at k   = the first k entries of the order (nested: one pull serves k = 1, 2, 3, 5, 8)
  E2-W (SN30) steps    = the first 3 entries that are >= 1 (SN30 re-runs step j = i + 1, i in
                         range(T - 1); filtering a uniform order keeps it uniform). They always lie in
                         the first 4 entries, hence inside the 8 opened steps.

What a class-O bundle opens, by committed tensor name (trajectory.py):
  sigmas, x_000, x_final, every conditioning key;
  for each of the 8 drawn steps s: x_s, D_s, and D_{s-1} for dpmpp_2m (its step uses the previous D);
  for each E2-W step j: x_j and x_{j+1} (x_final when j + 1 = T).

  python -m trajver.retention newseed SECRET_FILE            # operator: prints the sha256 to give the pod
  python -m trajver.retention extract RUN --cls O --seed-file F [--keep-full]
  python -m trajver.retention check RUN                      # re-verify every bundle of a pulled run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import load_file, save_file

from .commit import inclusion_proof, leaf_hash, verify_inclusion
from .trajectory import COND_KEYS, Trajectory, dkey, xkey

CLASSES = ("F", "O", "I")
N_OPEN = 8  # largest k in the study
N_E2W = 3   # SN30: k = min(3, T)


# ------------------------------------------------------------------ the step draw
def seed_sha256(seed: bytes) -> str:
    return hashlib.sha256(seed).hexdigest()


def read_seed(path: str | Path) -> bytes:
    s = bytes.fromhex(Path(path).read_text().strip())
    if len(s) != 32:
        raise ValueError("draw_seed must be 32 bytes (64 hex characters)")
    return s


def _stream(key: bytes):
    c = 0
    while True:
        yield from hashlib.sha256(key + c.to_bytes(8, "big")).digest()
        c += 1


def _below(stream, n: int) -> int:
    """Uniform integer in [0, n) by rejection sampling on 32-bit words (no modulo bias)."""
    lim = (1 << 32) - ((1 << 32) % n)
    while True:
        v = int.from_bytes(bytes(next(stream) for _ in range(4)), "big")
        if v < lim:
            return v % n


def step_order(draw_seed: bytes, job_id: str, T: int) -> list[int]:
    """A uniform permutation of range(T), fixed by the seed and the job id."""
    key = hashlib.sha256(draw_seed + b"|" + job_id.encode()).digest()
    st = _stream(key)
    order = list(range(T))
    for i in range(T - 1, 0, -1):
        j = _below(st, i + 1)
        order[i], order[j] = order[j], order[i]
    return order


def drawn(order: list[int], k: int) -> list[int]:
    """Tier B steps at k: the first k entries of the order, sorted."""
    return sorted(order[:k])


def e2w_steps(order: list[int]) -> list[int]:
    """SN30's re-run step indices j (>= 1), as the first N_E2W qualifying entries of the order."""
    return [s for s in order if s >= 1][:N_E2W]


def opened_names(order: list[int], T: int, sampler: str, conds: list[str], cls: str) -> list[str]:
    def state(i):
        return "x_final" if i == T else xkey(i)

    names = ["sigmas", "x_final"]
    if cls == "O":
        names += [xkey(0)] + [k for k in COND_KEYS if k in conds]
        for s in order[:N_OPEN]:
            names += [xkey(s), dkey(s)]
            if sampler == "dpmpp_2m" and s > 0:
                names.append(dkey(s - 1))
        for j in e2w_steps(order):
            names += [state(j), state(j + 1)]
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


# ------------------------------------------------------------------ the bundle
@dataclass
class Opened:
    """A trajectory of which only some committed tensors are opened. Reading an unopened one
    raises KeyError naming it, so no rule can silently use data the bundle does not carry."""
    T: int
    sigmas: torch.Tensor
    x_final: torch.Tensor
    xs: dict[int, torch.Tensor]
    Ds: dict[int, torch.Tensor]
    conds: dict[str, torch.Tensor]
    job: dict
    meta: dict = field(default_factory=dict)

    def state(self, i: int) -> torch.Tensor:
        return self.x_final if i == self.T else self.xs[i]


def make_bundle(traj: Trajectory, names: list[str], meta: dict) -> tuple[dict, dict]:
    named = traj.named_tensors()
    all_names = [n for n, _ in named]
    leaves = [leaf_hash(n, t) for n, t in named]
    tensors, proofs = {}, {}
    for n in names:
        i = all_names.index(n)
        tensors[n] = named[i][1].detach().cpu().contiguous()
        proofs[n] = [[side, h.hex()] for side, h in inclusion_proof(leaves, i)]
    md = {**meta, "root": traj.commitment().hex, "T": traj.T, "n_leaves": len(leaves),
          "job": traj.job, "proofs": proofs}
    return tensors, md


def save_bundle(path: Path, tensors: dict, md: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    save_file(tensors, str(path), metadata={"bundle": json.dumps(md, sort_keys=True)})
    path.chmod(0o644)


def load_bundle(path: str | Path, root_hex: str | None = None) -> Opened:
    """Load a bundle and check every opened tensor against the committed root.

    ``root_hex`` is the root the provider committed (jobs.jsonl / on chain); the bundle's own copy
    must equal it. Raises ValueError on any mismatch."""
    path = str(path)
    with safe_open(path, framework="pt") as f:
        md = json.loads((f.metadata() or {})["bundle"])
    t = load_file(path)
    root = bytes.fromhex(md["root"])
    if root_hex is not None and root_hex != md["root"]:
        raise ValueError(f"bundle root {md['root'][:12]} != committed root {root_hex[:12]}")
    if set(t) != set(md["proofs"]):
        raise ValueError("bundle tensors and proofs differ")
    for n, v in t.items():
        proof = [(side, bytes.fromhex(h)) for side, h in md["proofs"][n]]
        if not verify_inclusion(leaf_hash(n, v), proof, root):
            raise ValueError(f"inclusion proof fails for {n}")
    xs = {int(n[2:]): v for n, v in t.items() if n.startswith("x_") and n != "x_final"}
    Ds = {int(n[2:]): v for n, v in t.items() if n.startswith("D_")}
    return Opened(T=int(md["T"]), sigmas=t["sigmas"], x_final=t["x_final"], xs=xs, Ds=Ds,
                  conds={k: t[k] for k in COND_KEYS if k in t}, job=md.get("job", {}), meta=md)


# ------------------------------------------------------------------ pod side: extract, then discard
def class_for(run_name: str, spec: str) -> str:
    """Class of a run from a 'glob=CLASS,...' map (pod env POD_RETENTION); first match wins."""
    import fnmatch
    for part in filter(None, (x.strip() for x in spec.split(","))):
        pat, _, cls = part.rpartition("=")
        if cls not in CLASSES:
            raise SystemExit(f"bad retention map entry {part!r}")
        if fnmatch.fnmatch(run_name, pat or "*"):
            return cls
    raise SystemExit(f"no retention class for run {run_name!r} in {spec!r}")

def tier_a_rows(traj: Trajectory, sampler: str) -> list[dict]:
    from .solvers import tier_a_residuals
    return [{"rel_l2": r["rel_l2"], "max_abs": r["max_abs"], "replica_exact": r["replica_exact"]}
            for r in tier_a_residuals(traj, sampler)]


def run_sampler(pm: dict) -> str:
    return (pm.get("claimed") or {}).get("sampler") or pm["sampler"]


def extract(run: Path, cls: str, seed: bytes | None, keep_full: bool = False) -> dict:
    """Turn a finished run folder into its retention class (runbook §3.5 rules 3-4). Resumable."""
    if cls not in CLASSES:
        raise SystemExit(f"class must be one of {CLASSES}")
    if not (run / "jobs.jsonl").exists():  # not a job run (e.g. a noise or timing run): nothing to do
        return {"n": 0, "skipped": "no jobs.jsonl"}
    pm = json.loads((run / "manifest.json").read_text())
    want_hash = pm.get("draw_seed_sha256")
    if cls == "O":
        if seed is None:
            raise SystemExit("class O needs --seed-file (revealed after generation)")
        if not want_hash:
            raise SystemExit("class O run has no draw_seed_sha256 in its manifest: the draw was not fixed "
                             "before generation; refusing")
        if seed_sha256(seed) != want_hash:
            raise SystemExit("revealed draw_seed does not match the sha256 fixed before generation")
    sampler = run_sampler(pm)
    rows_path = run / "jobs.jsonl"
    rows = [json.loads(l) for l in rows_path.read_text().splitlines() if l.strip()]
    tdir, odir = run / "raw" / "traj", run / "raw" / "opened"
    stats = {"n": 0, "full_bytes": 0, "kept_bytes": 0}
    for r in rows:
        job = r["job"]
        tp, bp = tdir / f"{job}.safetensors", odir / f"{job}.safetensors"
        r["retention"] = cls
        if want_hash:
            r["draw_seed_sha256"] = want_hash
        if cls == "F":
            continue
        if bp.exists() and not tp.exists():  # done in an earlier pass
            continue
        traj = Trajectory.load(tp)
        root = traj.commitment().hex
        if r.get("merkle_root") and r["merkle_root"] != root:
            raise SystemExit(f"{job}: stored trajectory does not match its committed root")
        r["merkle_root"] = root
        order = step_order(seed, job, traj.T) if cls == "O" and seed is not None else []
        meta = {"retention": cls, "sampler": sampler, "draw_seed_sha256": want_hash,
                "order": order[:N_OPEN], "e2w_steps": e2w_steps(order) if order else [],
                "tier_a": tier_a_rows(traj, sampler)}
        tensors, md = make_bundle(traj, opened_names(order, traj.T, sampler, list(traj.conds), cls), meta)
        save_bundle(bp, tensors, md)
        load_bundle(bp, root)  # the pod checks its own proofs before it deletes anything
        stats["n"] += 1
        stats["full_bytes"] += tp.stat().st_size
        stats["kept_bytes"] += bp.stat().st_size
        r["opened_bytes"] = bp.stat().st_size
        if not keep_full:
            tp.unlink()
    rows_path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    pm["retention"] = cls
    if cls == "O" and seed is not None:
        # the seed is public once extraction is done; the verifier recomputes the order from it
        (run / "logs" / "draw_seed.hex").write_text(seed.hex() + "\n")
    pm.setdefault("retention_stats", {}).update(stats)
    (run / "manifest.json").write_text(json.dumps(pm, indent=1, default=str))
    return stats


def check_run(run: Path) -> int:
    """Re-verify a pulled run: every class-O/I job has a bundle whose proofs hold against the
    root in jobs.jsonl, and, for class O, whose opened steps follow from the revealed seed."""
    if not (run / "jobs.jsonl").exists():
        return 0
    pm = json.loads((run / "manifest.json").read_text())
    rows = [json.loads(l) for l in (run / "jobs.jsonl").read_text().splitlines() if l.strip()]
    seed = None
    if pm.get("retention") == "O":
        seed = read_seed(run / "logs" / "draw_seed.hex")
        if seed_sha256(seed) != pm.get("draw_seed_sha256"):
            print("revealed seed does not match the manifest hash")
            return 1
    bad = 0
    for r in rows:
        if r.get("retention", "F") == "F":
            continue
        try:
            b = load_bundle(run / "raw" / "opened" / f"{r['job']}.safetensors", r.get("merkle_root"))
            if seed is not None and step_order(seed, r["job"], b.T)[:N_OPEN] != b.meta["order"]:
                raise ValueError("opened steps do not follow from the revealed seed")
        except Exception as e:  # noqa: BLE001
            print(r["job"], "FAIL", e)
            bad += 1
    print(f"{len(rows) - bad}/{len(rows)} jobs ok")
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("newseed")
    s.add_argument("out")
    s = sub.add_parser("extract")
    s.add_argument("run", nargs="+")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--cls", choices=CLASSES)
    g.add_argument("--map", help="per-run classes by run-name glob, e.g. 'wp2-*-test-*=O,*=F' (first match wins)")
    s.add_argument("--seed-file", default=None)
    s.add_argument("--keep-full", action="store_true", help="testing only: do not delete the full trajectory")
    s = sub.add_parser("check")
    s.add_argument("run", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "newseed":
        out = Path(a.out)
        if out.exists():
            raise SystemExit(f"{out} exists; a draw seed is never reused")
        seed = secrets.token_bytes(32)
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, (seed.hex() + "\n").encode())
        os.close(fd)
        print(seed_sha256(seed))
        return 0
    if a.cmd == "extract":
        seed = read_seed(a.seed_file) if a.seed_file else None
        for r in a.run:
            cls = a.cls or class_for(Path(r).name, a.map)
            print(Path(r).name, cls, json.dumps(extract(Path(r), cls, seed, a.keep_full)))
        return 0
    return max(check_run(Path(r)) for r in a.run)


if __name__ == "__main__":
    sys.exit(main())
