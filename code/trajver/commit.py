"""Merkle commitment over an ordered list of named tensors.

Leaf: sha256(0x00 || len-prefixed name || len-prefixed dtype || len-prefixed shape || raw bytes).
Node: sha256(0x01 || left || right). The tree shape is RFC 6962 (split at the largest power of
two below n), so inclusion proofs can open single steps without revealing the rest.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence

import torch

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"


def _lp(b: bytes) -> bytes:
    return len(b).to_bytes(8, "big") + b


def tensor_bytes(t: torch.Tensor) -> bytes:
    """Raw little-endian bytes of a tensor in its own dtype (works for bf16/fp8 too)."""
    t = t.detach().to("cpu").contiguous().reshape(-1)
    return t.view(torch.uint8).numpy().tobytes()


def dtype_name(t: torch.Tensor) -> str:
    return str(t.dtype).removeprefix("torch.")


def leaf_hash(name: str, t: torch.Tensor) -> bytes:
    h = hashlib.sha256()
    h.update(LEAF_PREFIX)
    h.update(_lp(name.encode()))
    h.update(_lp(dtype_name(t).encode()))
    h.update(_lp("x".join(str(s) for s in t.shape).encode()))
    h.update(tensor_bytes(t))
    return h.digest()


def _node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(NODE_PREFIX + left + right).digest()


def _split(n: int) -> int:
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def merkle_root_from_leaves(leaves: Sequence[bytes]) -> bytes:
    n = len(leaves)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return leaves[0]
    k = _split(n)
    return _node(merkle_root_from_leaves(leaves[:k]), merkle_root_from_leaves(leaves[k:]))


def inclusion_proof(leaves: Sequence[bytes], index: int) -> list[tuple[str, bytes]]:
    """Audit path for leaf ``index``: list of (side, sibling hash), from the leaf upwards."""
    n = len(leaves)
    if not 0 <= index < n:
        raise IndexError(index)
    if n == 1:
        return []
    k = _split(n)
    if index < k:
        return inclusion_proof(leaves[:k], index) + [("R", merkle_root_from_leaves(leaves[k:]))]
    return inclusion_proof(leaves[k:], index - k) + [("L", merkle_root_from_leaves(leaves[:k]))]


def verify_inclusion(leaf: bytes, proof: Sequence[tuple[str, bytes]], root: bytes) -> bool:
    h = leaf
    for side, sib in proof:
        h = _node(h, sib) if side == "R" else _node(sib, h)
    return h == root


@dataclass(frozen=True)
class Commitment:
    root: bytes
    names: tuple[str, ...]

    @property
    def hex(self) -> str:
        return self.root.hex()


def commit(named: Sequence[tuple[str, torch.Tensor]]) -> Commitment:
    names = tuple(n for n, _ in named)
    if len(set(names)) != len(names):
        raise ValueError("duplicate tensor names in commitment")
    leaves = [leaf_hash(n, t) for n, t in named]
    return Commitment(merkle_root_from_leaves(leaves), names)
