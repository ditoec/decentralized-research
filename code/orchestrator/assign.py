"""Node registry and assignment. Rented cards are providers, Sparks are verifiers; a node may hold
both roles, but it never verifies a job it provided, and the second verifier differs from the first."""
from __future__ import annotations

from dataclasses import dataclass, field

from .reputation import Reputation


@dataclass
class Node:
    name: str  # also the relay's signer name
    roles: set[str] = field(default_factory=set)  # {"provider", "verifier"}
    busy: bool = False


class NoNodeAvailable(RuntimeError):
    pass


class Assigner:
    def __init__(self, nodes: list[Node], reputation: Reputation):
        self.nodes = {n.name: n for n in nodes}
        self.rep = reputation
        self._rr = 0

    def _pick(self, cands: list[Node]) -> Node:
        if not cands:
            raise NoNodeAvailable
        cands.sort(key=lambda n: n.name)
        n = cands[self._rr % len(cands)]
        self._rr += 1
        return n

    def provider(self) -> Node:
        return self._pick([n for n in self.nodes.values()
                           if "provider" in n.roles and not n.busy and self.rep.eligible(n.name)])

    def verifier(self, exclude: set[str]) -> Node:
        """A verifier that is none of ``exclude`` (the job's provider, and its first verifier)."""
        return self._pick([n for n in self.nodes.values() if "verifier" in n.roles and n.name not in exclude])
