"""The committed object: a sampler trajectory plus the conditioning it was computed from.

File format: one ``trajectory.safetensors`` per job. Tensor keys::

    sigmas            shape [T+1]
    x_000 .. x_{T-1}  state before step i (internal latent space, sampler dtype)
    D_000 .. D_{T-1}  CFG-combined denoised prediction at step i
    x_final           state after the last step (before process_latent_out)
    cond_pos, cond_neg[, cond_pos_pooled, cond_neg_pooled]

Metadata (str -> str) carries the job description as JSON under ``"job"``.
Commitment leaf order is fixed by :meth:`Trajectory.named_tensors`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import load_file, save_file

from .commit import Commitment, commit, inclusion_proof, leaf_hash

COND_KEYS = ("cond_pos", "cond_pos_pooled", "cond_neg", "cond_neg_pooled")


def xkey(i: int) -> str:
    return f"x_{i:03d}"


def dkey(i: int) -> str:
    return f"D_{i:03d}"


@dataclass
class Trajectory:
    sigmas: torch.Tensor
    xs: list[torch.Tensor]
    Ds: list[torch.Tensor]
    x_final: torch.Tensor
    conds: dict[str, torch.Tensor] = field(default_factory=dict)
    job: dict = field(default_factory=dict)

    def __post_init__(self):
        if len(self.xs) != len(self.Ds):
            raise ValueError("xs and Ds differ in length")
        if self.sigmas.numel() != len(self.xs) + 1:
            raise ValueError(f"sigmas has {self.sigmas.numel()} entries for {len(self.xs)} steps")

    @property
    def T(self) -> int:
        return len(self.xs)

    def state(self, i: int) -> torch.Tensor:
        """x_i for 0 <= i <= T (x_T is x_final)."""
        return self.x_final if i == self.T else self.xs[i]

    def named_tensors(self) -> list[tuple[str, torch.Tensor]]:
        out = [("sigmas", self.sigmas)]
        for i in range(self.T):
            out.append((xkey(i), self.xs[i]))
            out.append((dkey(i), self.Ds[i]))
        out.append(("x_final", self.x_final))
        for k in COND_KEYS:
            if k in self.conds:
                out.append((k, self.conds[k]))
        return out

    def commitment(self) -> Commitment:
        return commit(self.named_tensors())

    def opening(self, name: str):
        """(tensor, leaf hash, inclusion proof) for one committed tensor, e.g. ``D_007``."""
        named = self.named_tensors()
        names = [n for n, _ in named]
        idx = names.index(name)
        leaves = [leaf_hash(n, t) for n, t in named]
        return named[idx][1], leaves[idx], inclusion_proof(leaves, idx)

    def nbytes(self) -> int:
        return sum(t.numel() * t.element_size() for _, t in self.named_tensors())

    def save(self, path: str | Path) -> str:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tensors = {n: t.detach().cpu().contiguous() for n, t in self.named_tensors()}
        root = self.commitment().hex
        save_file(tensors, str(path), metadata={"job": json.dumps(self.job, sort_keys=True), "root": root})
        return root

    @classmethod
    def load(cls, path: str | Path) -> "Trajectory":
        path = str(path)
        with safe_open(path, framework="pt") as f:
            meta = f.metadata() or {}
        t = load_file(path)
        T = t["sigmas"].numel() - 1
        return cls(
            sigmas=t["sigmas"],
            xs=[t[xkey(i)] for i in range(T)],
            Ds=[t[dkey(i)] for i in range(T)],
            x_final=t["x_final"],
            conds={k: t[k] for k in COND_KEYS if k in t},
            job=json.loads(meta.get("job", "{}")),
        )

    def clone(self) -> "Trajectory":
        return Trajectory(
            sigmas=self.sigmas.clone(),
            xs=[x.clone() for x in self.xs],
            Ds=[d.clone() for d in self.Ds],
            x_final=self.x_final.clone(),
            conds={k: v.clone() for k, v in self.conds.items()},
            job=json.loads(json.dumps(self.job)),
        )
