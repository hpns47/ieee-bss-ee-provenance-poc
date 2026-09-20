"""
demo_tamper_detection.py — The central experiment for the Evaluation
section (brief Section 5, items 1/3/4): runs one monitoring episode,
anchors it, then demonstrates that (a) a legitimate governance-approved
parameter change is accepted, (b) an unauthorized parameter-level
tamper (Type 2) is detected and localized to the exact stage, (c) an
unauthorized output-level tamper (Type 3) is detected and localized,
and (d) a naive sign-the-final-output baseline catches tampering but
cannot localize it to a stage -- motivating the multi-level design.

Run: python3 demo_tamper_detection.py
"""

from __future__ import annotations
import copy
import hashlib
import json
import time

from merkle import MerkleTree, sha256_hex
from ledger import ProvenanceLedger, OperatorDID, canonical_bytes, ROOT_BYTES, SIGNATURE_BYTES, ANCHORED_BYTES_PER_EPISODE
from pipeline import run_episode, DEFAULT_PARAMS

SEPARATOR = "=" * 78


def build_episode_tree(records) -> MerkleTree:
    leaves = [r.leaf_hash() for r in records]
    labels = [r.label for r in records]
    return MerkleTree(leaves=leaves, leaf_labels=labels)


def recompute_leaves(records) -> list:
    """Recompute leaf hashes straight from record fields (used by the
    auditor on whatever record set they are handed -- genuine or tampered)."""
    return [r.leaf_hash() for r in records]


def naive_baseline_sign(records, operator: OperatorDID) -> dict:
    """
    Section 5 item 4: naive baseline = ordinary digital signature /
    timestamping authority over the final output only, no multi-level
    structure, no per-stage anchoring. This is what most prior work in
    the RS-provenance cluster effectively does (hash the final product).
    """
    final_stage = records[-1]  # change_mask, the delivered artifact
    payload = canonical_bytes(final_stage.output)
    sig = operator.sign(payload)
    return {"final_output_hash": sha256_hex(payload), "signature": sig}


def naive_baseline_verify(reported_records, anchored: dict, operator: OperatorDID) -> bool:
    final_stage = reported_records[-1]
    payload = canonical_bytes(final_stage.output)
    if sha256_hex(payload) != anchored["final_output_hash"]:
        return False
    try:
        operator.public_key_obj().verify.__self__  # no-op, keep symmetry with ledger verify style
    except Exception:
        pass
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes as chashes
    from cryptography.exceptions import InvalidSignature
    try:
        operator.public_key_obj().verify(bytes.fromhex(anchored["signature"]), payload, ec.ECDSA(chashes.SHA256()))
        return True
    except InvalidSignature:
        return False


def section(title):
    print("\n" + SEPARATOR)
    print(title)
    print(SEPARATOR)


def main():
    operator = OperatorDID.generate(did="did:example:almaty-monitoring-operator-01")
    ledger = ProvenanceLedger()
    ledger.register_operator(operator)

    # ---------------------------------------------------------------
    section("1. BASELINE EPISODE — run pipeline, anchor Merkle root in the ledger")
    # ---------------------------------------------------------------
    t0 = time.perf_counter()
    genuine_records = run_episode(seed=42, operator_did=operator.did, params=DEFAULT_PARAMS)
    t1 = time.perf_counter()
    pipeline_time = t1 - t0

    t2 = time.perf_counter()
    tree = build_episode_tree(genuine_records)
    entry = ledger.append(
        "EPISODE_ROOT",
        {"episode_id": "almaty-2023_2024-episode-001", "root": tree.root,
         "stage_labels": [r.label for r in genuine_records]},
        operator,
    )
    t3 = time.perf_counter()
    anchoring_time = t3 - t2

    print(f"Stages hashed and anchored (in pipeline order):")
    for r in genuine_records:
        print(f"  [{r.label:>22}] leaf = {r.leaf_hash()[:16]}...")
    print(f"\nEpisode Merkle root: {tree.root}")
    print(f"Ledger entry signed by {operator.did}, chained to prev_hash={entry.prev_entry_hash[:16]}...")
    print(f"\nOverhead: pipeline compute = {pipeline_time*1000:.2f} ms | "
          f"hash+Merkle+sign = {anchoring_time*1000:.2f} ms "
          f"({100*anchoring_time/max(pipeline_time,1e-9):.2f}% of pipeline time)")
    print(f"Storage cost: {len(genuine_records)} leaf hashes/episode off-chain "
          f"(32 bytes each = {len(genuine_records)*32} bytes) vs. "
          f"{ROOT_BYTES} B root + {SIGNATURE_BYTES} B signature = {ANCHORED_BYTES_PER_EPISODE} B "
          f"anchored in the ledger per episode.")

    # ---------------------------------------------------------------
    section("2. LEGITIMATE GOVERNANCE TRANSACTION — authorized tau change (0.4 -> 0.5)")
    # ---------------------------------------------------------------
    gov_entry = ledger.append("PARAMETER_CHANGE", {"param": "tau", "old": 0.4, "new": 0.5}, operator)
    print(f"Governance tx appended and signed by {operator.did}.")
    print(f"Ledger's current approved params: {ledger.latest_params()}")
    print("This is accepted: any later episode computed with tau=0.5 will match "
          "the governance log, and the change itself is permanently auditable.")

    # ---------------------------------------------------------------
    section("3. ATTACK TYPE 2 (parameter-level) — tau silently changed to 0.6, NO governance tx")
    # ---------------------------------------------------------------
    tampered_params_records = copy.deepcopy(genuine_records)
    for r in tampered_params_records:
        if r.label == "change_mask":
            r.params = dict(r.params)
            r.params["tau"] = 0.6  # attacker edits the record after the fact
            # NOTE: output.changed_pixels is left as originally computed under tau=0.4,
            # i.e. the attacker did not even bother recomputing -- exactly the scenario
            # the brief calls "задним числом меняется τ ... чтобы скрыть реальную аномалию"

    reported_leaves = recompute_leaves(tampered_params_records)
    reported_tree = build_episode_tree(tampered_params_records)
    anchored_root = ledger.entries[0].payload["root"]  # the genuine EPISODE_ROOT entry

    match = reported_tree.root == anchored_root
    print(f"Anchored root (ledger):     {anchored_root}")
    print(f"Recomputed root (reported): {reported_tree.root}")
    print(f"Root match? {match}  -->  {'PASS' if match else 'FAIL -- TAMPER DETECTED'}")

    if not match:
        original_leaves = [r.leaf_hash() for r in genuine_records]
        bad_stage = MerkleTree(leaves=original_leaves,
                                leaf_labels=[r.label for r in genuine_records]) \
            .find_mismatched_stage(reported_leaves)
        print(f"Localization: divergence first detected at stage -> '{bad_stage}'")
        approved_tau = ledger.latest_params()["tau"]
        claimed_tau = next(r.params["tau"] for r in tampered_params_records if r.label == "change_mask")
        print(f"Cross-check vs governance log: approved tau={approved_tau}, "
              f"claimed tau in report={claimed_tau} -> {'MATCH' if approved_tau==claimed_tau else 'MISMATCH (no governance tx for this change)'}")

    # ---------------------------------------------------------------
    section("4. ATTACK TYPE 3 (output-level) — change_mask output edited directly in report")
    # ---------------------------------------------------------------
    tampered_output_records = copy.deepcopy(genuine_records)
    for r in tampered_output_records:
        if r.label == "change_mask":
            real_count = r.output["changed_pixels"]
            r.output = dict(r.output)
            r.output["changed_pixels"] = 0  # attacker reports "no change detected"

    reported_leaves_2 = recompute_leaves(tampered_output_records)
    reported_tree_2 = build_episode_tree(tampered_output_records)
    match2 = reported_tree_2.root == anchored_root
    print(f"Anchored root (ledger):     {anchored_root}")
    print(f"Recomputed root (reported): {reported_tree_2.root}")
    print(f"Root match? {match2}  -->  {'PASS' if match2 else 'FAIL -- TAMPER DETECTED'}")
    if not match2:
        original_leaves = [r.leaf_hash() for r in genuine_records]
        bad_stage2 = MerkleTree(leaves=original_leaves,
                                 leaf_labels=[r.label for r in genuine_records]) \
            .find_mismatched_stage(reported_leaves_2)
        print(f"Localization: divergence first detected at stage -> '{bad_stage2}'")
        print(f"(reported changed_pixels=0, true anchored value implies {real_count} changed pixels)")

    # ---------------------------------------------------------------
    section("5. NAIVE BASELINE COMPARISON — sign only the final output, no per-stage anchoring")
    # ---------------------------------------------------------------
    naive_anchor = naive_baseline_sign(genuine_records, operator)
    print(f"Naive baseline anchors only: {naive_anchor['final_output_hash'][:16]}... (final change_mask hash)")

    ok_genuine = naive_baseline_verify(genuine_records, naive_anchor, operator)
    ok_output_tamper = naive_baseline_verify(tampered_output_records, naive_anchor, operator)
    ok_param_tamper = naive_baseline_verify(tampered_params_records, naive_anchor, operator)
    print(f"Naive verify genuine report:            {'PASS' if ok_genuine else 'FAIL'}")
    print(f"Naive verify output-tampered report:    {'PASS' if ok_output_tamper else 'FAIL (caught)'}")
    print(f"Naive verify param-tampered report:     {'PASS' if ok_param_tamper else 'FAIL (caught)'}")
    print("\nNote: the naive baseline signs only the final delivered artifact (change_mask's "
          "output), so it is structurally BLIND to attack #2 -- it never inspects tau at all. "
          "Here the attacker changed only the params field and left the final output "
          "untouched, so the naive signature still verifies (PASS = manipulation goes "
          "undetected). The multi-level scheme catches it regardless, because tau is anchored "
          "as its own leaf and cross-checked against the independent governance log (Section 3 "
          "above) -- detection does not depend on whether the output happens to change too. "
          "This is the concrete 'why multi-level, why not just sign the output' argument "
          "requested in the evaluation plan.")
    print("\nMore fundamentally: even where the naive baseline does catch a tamper (attack #3, "
          "the output itself was edited), it can only say PASS/FAIL on the whole report -- it "
          "cannot say *which* stage was manipulated, unlike the multi-level scheme's "
          "localization above.")

    # ---------------------------------------------------------------
    section("6. LEDGER INTEGRITY CHECK")
    # ---------------------------------------------------------------
    bad_index = ledger.verify_chain()
    print(f"Ledger chain integrity: {'INTACT' if bad_index is None else f'BROKEN at entry {bad_index}'}")
    print(f"Total ledger entries: {len(ledger.entries)} "
          f"({sum(1 for e in ledger.entries if e.entry_type=='EPISODE_ROOT')} episode roots, "
          f"{sum(1 for e in ledger.entries if e.entry_type=='PARAMETER_CHANGE')} governance txs)")

    # ---------------------------------------------------------------
    section("SUMMARY (for paper Table: Evaluation)")
    # ---------------------------------------------------------------
    summary = {
        "pipeline_compute_ms": round(pipeline_time * 1000, 3),
        "anchoring_overhead_ms": round(anchoring_time * 1000, 3),
        "anchoring_overhead_pct": round(100 * anchoring_time / max(pipeline_time, 1e-9), 4),
        "leaves_per_episode": len(genuine_records),
        "off_chain_leaf_storage_bytes": len(genuine_records) * 32,
        "anchored_root_bytes_per_episode": ROOT_BYTES,
        "anchored_signature_bytes_per_episode": SIGNATURE_BYTES,
        "anchored_bytes_per_episode": ANCHORED_BYTES_PER_EPISODE,
        "attack_type2_param_level_detected": not match,
        "attack_type2_localized_stage": bad_stage if not match else None,
        "attack_type3_output_level_detected": not match2,
        "attack_type3_localized_stage": bad_stage2 if not match2 else None,
        "naive_baseline_catches_type3": not ok_output_tamper,
        "naive_baseline_catches_type2_in_this_run": not ok_param_tamper,
        "naive_baseline_can_localize": False,
        "ledger_chain_intact": bad_index is None,
    }
    print(json.dumps(summary, indent=2))

    with open("evaluation_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print("\nWritten: evaluation_summary.json")


if __name__ == "__main__":
    main()
