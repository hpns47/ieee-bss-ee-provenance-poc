"""
merkle.py — Binary Merkle tree over SHA-256, used to aggregate per-stage
leaf hashes of one monitoring episode into a single root (Section 4.1,
"Merkle Aggregation Layer").

Convention: if a level has an odd number of nodes, the last node is
duplicated (standard Bitcoin-style convention). This is noted explicitly
because it is a common source of second-preimage subtleties that a
reviewer may ask about; for an academic PoC it is sufficient but should
be called out in Limitations if the real system uses variable-arity
episodes.
"""

from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from typing import Optional


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _combine(left: str, right: str) -> str:
    """Hash two child hex-digests together to form the parent hash."""
    return sha256_hex(bytes.fromhex(left) + bytes.fromhex(right))


@dataclass
class MerkleProof:
    """Authentication path for one leaf: siblings + which side each is on."""
    leaf_hash: str
    leaf_index: int
    siblings: list  # list[(sibling_hash, 'L' | 'R')]
    root: str

    def verify(self) -> bool:
        current = self.leaf_hash
        for sib_hash, side in self.siblings:
            if side == "L":
                current = _combine(sib_hash, current)
            else:
                current = _combine(current, sib_hash)
        return current == self.root


@dataclass
class MerkleTree:
    leaves: list  # list[str] hex digests, in stage order
    leaf_labels: list = field(default_factory=list)  # human-readable stage names, same order
    levels: list = field(default_factory=list, init=False)  # levels[0] = leaves, levels[-1] = [root]

    def __post_init__(self):
        if not self.leaves:
            raise ValueError("MerkleTree requires at least one leaf")
        if self.leaf_labels and len(self.leaf_labels) != len(self.leaves):
            raise ValueError("leaf_labels length must match leaves length")
        self._build()

    def _build(self):
        level = list(self.leaves)
        self.levels = [level]
        while len(level) > 1:
            nxt = []
            for i in range(0, len(level), 2):
                left = level[i]
                right = level[i + 1] if i + 1 < len(level) else level[i]  # duplicate last if odd
                nxt.append(_combine(left, right))
            level = nxt
            self.levels.append(level)

    @property
    def root(self) -> str:
        return self.levels[-1][0]

    def get_proof(self, index: int) -> MerkleProof:
        if not (0 <= index < len(self.leaves)):
            raise IndexError("leaf index out of range")
        siblings = []
        idx = index
        for level in self.levels[:-1]:
            is_right = idx % 2 == 1
            pair_idx = idx - 1 if is_right else idx + 1
            if pair_idx >= len(level):
                pair_idx = idx  # duplicated node case
            sib_hash = level[pair_idx]
            side = "L" if is_right else "R"
            siblings.append((sib_hash, side))
            idx //= 2
        return MerkleProof(
            leaf_hash=self.leaves[index],
            leaf_index=index,
            siblings=siblings,
            root=self.root,
        )

    def find_mismatched_stage(self, recomputed_leaves: list) -> Optional[str]:
        """
        Diagnostic helper for the Verification/Audit Layer: given a freshly
        recomputed set of leaf hashes (same order as self.leaf_labels),
        return the label of the first stage whose hash no longer matches
        what is anchored in this tree. Returns None if everything matches
        (i.e. no tamper detected at the leaf level -- a mismatch could
        still exist purely at aggregation, which recompute-and-compare
        against `root` catches separately).

        NOTE: for a combined/multi-stage attack (more than one stage
        tampered at once) this under-reports -- it stops at the first
        divergence in stage order and silently omits any later one. Use
        find_all_mismatched_stages for that case (see attack_sweep.py's
        combined-attack test, BSS2026_Final_Hardening_Brief.md Priority 2).
        """
        for label, original, recomputed in zip(self.leaf_labels, self.leaves, recomputed_leaves):
            if original != recomputed:
                return label
        return None

    def find_all_mismatched_stages(self, recomputed_leaves: list) -> list:
        """Like find_mismatched_stage, but returns every stage whose hash
        no longer matches, not just the first -- the correct check when
        more than one stage may have been tampered simultaneously."""
        return [label for label, original, recomputed
                in zip(self.leaf_labels, self.leaves, recomputed_leaves)
                if original != recomputed]
