"""
ledger.py — Simulates the ledger layer (Section 4.1, item 4) as a local
append-only log. This is NOT a blockchain: there is no consensus, no
endorsement, no ordering service and no replication, so a holder of the
signing key could rewrite the whole log. It exposes the interface a
permissioned-ledger chaincode would (see HYPERLEDGER_FABRIC_MAPPING.md),
so the provenance mechanism can be validated locally before deployment.
Per the brief's fallback plan (Section 6), it stands in
for a Hyperledger Fabric smart contract: it only ever stores Merkle roots
+ metadata, never raw data, and every entry is signed by an "operator DID"
which here is simplified to an ECDSA (SECP256R1) keypair, as explicitly
sanctioned in Section 4.3 ("simplified DID scheme" is an acceptable
limitation to state in the paper).

Two entry types map directly onto Section 4.1 / 4.2:
  - EPISODE_ROOT:   one per monitoring episode (Merkle root of pipeline stages)
  - PARAMETER_CHANGE: a governance transaction changing alpha/beta/lambda/tau

Because it is append-only (a plain Python list persisted to a JSON file),
any retroactive edit to a past entry is itself an integrity violation
detectable by recomputing signatures -- this is what makes "silently
editing tau after the fact" (Attack Type 2) show up in the demo.
"""

from __future__ import annotations
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature


# Storage model for one anchored episode: a SHA-256 Merkle root plus one
# ECDSA P-256 signature in fixed-size raw r||s form. The PoC serializes the
# signature as DER (70-72 B) and each entry also carries a 32 B hash-chain
# link and metadata. Those are not counted, so ANCHORED_BYTES_PER_EPISODE is
# a lower bound on real per-episode ledger cost.
ROOT_BYTES = 32
SIGNATURE_BYTES = 64
ANCHORED_BYTES_PER_EPISODE = ROOT_BYTES + SIGNATURE_BYTES


def canonical_bytes(obj) -> bytes:
    """Deterministic JSON serialization used as the signing/hashing input."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass
class OperatorDID:
    """A simplified DID: an ECDSA keypair plus a human-readable identifier."""
    did: str
    _private_key: ec.EllipticCurvePrivateKey = field(repr=False)

    @classmethod
    def generate(cls, did: str) -> "OperatorDID":
        return cls(did=did, _private_key=ec.generate_private_key(ec.SECP256R1()))

    def public_key_pem(self) -> str:
        pub = self._private_key.public_key()
        return pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

    def sign(self, payload: bytes) -> str:
        sig = self._private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        return sig.hex()

    def public_key_obj(self):
        return self._private_key.public_key()


@dataclass
class LedgerEntry:
    entry_type: str          # "EPISODE_ROOT" | "PARAMETER_CHANGE"
    payload: dict            # e.g. {"root": "...", "episode_id": "..."} or {"param": "tau", "old": 0.4, "new": 0.6}
    operator_did: str
    timestamp: float
    signature: str
    prev_entry_hash: str      # chains entries together, append-only

    def signing_payload(self) -> dict:
        return {
            "entry_type": self.entry_type,
            "payload": self.payload,
            "operator_did": self.operator_did,
            "timestamp": self.timestamp,
            "prev_entry_hash": self.prev_entry_hash,
        }


class ProvenanceLedger:
    """Append-only, hash-chained, signed local log standing in for the ledger layer."""

    GENESIS_HASH = "0" * 64

    def __init__(self):
        self.entries: list[LedgerEntry] = []
        self._identities: dict[str, OperatorDID] = {}

    def register_operator(self, did_obj: OperatorDID):
        self._identities[did_obj.did] = did_obj

    def _last_hash(self) -> str:
        if not self.entries:
            return self.GENESIS_HASH
        import hashlib
        return hashlib.sha256(canonical_bytes(asdict(self.entries[-1]))).hexdigest()

    def append(self, entry_type: str, payload: dict, operator: OperatorDID) -> LedgerEntry:
        entry = LedgerEntry(
            entry_type=entry_type,
            payload=payload,
            operator_did=operator.did,
            timestamp=time.time(),
            signature="",
            prev_entry_hash=self._last_hash(),
        )
        entry.signature = operator.sign(canonical_bytes(entry.signing_payload()))
        self.entries.append(entry)
        return entry

    def verify_entry(self, entry: LedgerEntry) -> bool:
        operator = self._identities.get(entry.operator_did)
        if operator is None:
            return False
        try:
            operator.public_key_obj().verify(
                bytes.fromhex(entry.signature),
                canonical_bytes(entry.signing_payload()),
                ec.ECDSA(hashes.SHA256()),
            )
            return True
        except InvalidSignature:
            return False

    def verify_chain(self) -> Optional[int]:
        """Returns the index of the first entry whose prev_entry_hash no
        longer matches the actual hash of its predecessor (i.e. detects
        a retroactive edit anywhere in the append-only log), or None if
        the chain is intact."""
        import hashlib
        expected_prev = self.GENESIS_HASH
        for i, entry in enumerate(self.entries):
            if entry.prev_entry_hash != expected_prev:
                return i
            if not self.verify_entry(entry):
                return i
            expected_prev = hashlib.sha256(canonical_bytes(asdict(entry))).hexdigest()
        return None

    def latest_params(self) -> dict:
        """Reconstructs the current governance-approved parameter set by
        replaying all PARAMETER_CHANGE entries in order."""
        params = {"alpha": 0.5, "beta": 0.3, "lambda": 0.2, "tau": 0.4}  # defaults, mirrors GEE script
        for e in self.entries:
            if e.entry_type == "PARAMETER_CHANGE":
                params[e.payload["param"]] = e.payload["new"]
        return params

    def params_as_of(self, timestamp: float) -> dict:
        """Same as latest_params(), but only replays PARAMETER_CHANGE
        entries at or before `timestamp`. Cross-checking an episode's own
        recorded params against latest_params() (the *current* ledger
        state) rather than against params_as_of(episode_timestamp) is a
        real bug: it false-flags every legitimately-anchored older episode
        as soon as ANY later, valid governance change is appended, even
        though that episode was correctly computed under the params
        approved at the time. Found via fp_sweep.py's
        'legitimate_old_episode_naive_check' scenario; this method is the
        fix (see BSS2026_Final_Hardening_Brief.md Section 1.1)."""
        params = {"alpha": 0.5, "beta": 0.3, "lambda": 0.2, "tau": 0.4}
        for e in self.entries:
            if e.entry_type == "PARAMETER_CHANGE" and e.timestamp <= timestamp:
                params[e.payload["param"]] = e.payload["new"]
        return params
