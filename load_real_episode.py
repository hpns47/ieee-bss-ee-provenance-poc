"""
load_real_episode.py — Loads real_episode_data.json (produced by
gee_extract.py against actual Sentinel-1/2 data) and runs the same
provenance experiment as demo_tamper_detection.py, but on real data
instead of the synthetic pipeline. Reuses the exact same
merkle/ledger/naive-baseline machinery so the numbers are directly
comparable to (and can replace) the synthetic ones in the paper.

Run:
    python3 load_real_episode.py --in real_episode_data.json
"""

from __future__ import annotations
import argparse
import copy
import json

from merkle import MerkleTree
from ledger import ProvenanceLedger, OperatorDID
from pipeline import StageRecord
from demo_tamper_detection import (
    build_episode_tree, recompute_leaves, naive_baseline_sign,
    naive_baseline_verify, section,
)


def load_records(path: str, operator_did: str) -> list:
    with open(path) as f:
        data = json.load(f)
    records = []
    for r in data["records"]:
        records.append(StageRecord(
            label=r["label"], input_ref=r["input_ref"], params=r["params"],
            output=r["output"], operator_did=operator_did, timestamp=r["timestamp"],
        ))
    return records, data.get("episode_id", "unknown-episode"), data.get("params", {})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", default="real_episode_data.json")
    args = ap.parse_args()

    operator = OperatorDID.generate(did="did:example:almaty-monitoring-operator-01")
    ledger = ProvenanceLedger()
    ledger.register_operator(operator)

    section("1. BASELINE EPISODE (REAL GEE DATA) — anchor Merkle root on-chain")
    genuine_records, episode_id, source_params = load_records(args.infile, operator.did)
    print(f"Episode: {episode_id}  |  {len(genuine_records)} stages loaded from {args.infile}")

    tree = build_episode_tree(genuine_records)
    entry = ledger.append(
        "EPISODE_ROOT",
        {"episode_id": episode_id, "root": tree.root,
         "stage_labels": [r.label for r in genuine_records]},
        operator,
    )
    for r in genuine_records:
        out_preview = {k: v for k, v in r.output.items() if k in ("mean", "n_scenes", "changed_pixels_est")}
        print(f"  [{r.label:>22}] leaf={r.leaf_hash()[:16]}...  output={out_preview}")
    print(f"\nEpisode Merkle root: {tree.root}")
    anchored_root = tree.root

    section("2. ATTACK TYPE 2 (parameter-level) — tau silently changed, no governance tx")
    tampered_params_records = copy.deepcopy(genuine_records)
    for r in tampered_params_records:
        if r.label == "change_mask":
            old_tau = r.params.get("tau")
            r.params = dict(r.params)
            r.params["tau"] = round((old_tau or 0.4) + 0.2, 3)
    reported_tree = build_episode_tree(tampered_params_records)
    match = reported_tree.root == anchored_root
    print(f"Root match? {match} --> {'PASS' if match else 'FAIL -- TAMPER DETECTED'}")
    if not match:
        bad_stage = tree.find_mismatched_stage(recompute_leaves(tampered_params_records))
        print(f"Localization: '{bad_stage}'")

    section("3. ATTACK TYPE 3 (output-level) — change_mask output edited directly")
    tampered_output_records = copy.deepcopy(genuine_records)
    for r in tampered_output_records:
        if r.label == "change_mask":
            r.output = dict(r.output)
            if "changed_pixels_est" in r.output:
                r.output["changed_pixels_est"] = 0
            r.output["mean"] = 0.0
    reported_tree2 = build_episode_tree(tampered_output_records)
    match2 = reported_tree2.root == anchored_root
    print(f"Root match? {match2} --> {'PASS' if match2 else 'FAIL -- TAMPER DETECTED'}")
    if not match2:
        bad_stage2 = tree.find_mismatched_stage(recompute_leaves(tampered_output_records))
        print(f"Localization: '{bad_stage2}'")

    section("4. NAIVE BASELINE COMPARISON")
    naive_anchor = naive_baseline_sign(genuine_records, operator)
    ok_param = naive_baseline_verify(tampered_params_records, naive_anchor, operator)
    ok_output = naive_baseline_verify(tampered_output_records, naive_anchor, operator)
    print(f"Naive verify param-tampered:  {'PASS (missed)' if ok_param else 'FAIL (caught)'}")
    print(f"Naive verify output-tampered: {'PASS (missed)' if ok_output else 'FAIL (caught)'}")

    section("SUMMARY")
    summary = {
        "episode_id": episode_id,
        "n_stages": len(genuine_records),
        "merkle_root": anchored_root,
        "attack_type2_detected": not match,
        "attack_type3_detected": not match2,
        "naive_catches_type2": not ok_param,
        "naive_catches_type3": not ok_output,
    }
    print(json.dumps(summary, indent=2))
    with open("real_episode_evaluation.json", "w") as f:
        json.dump(summary, f, indent=2)
    print("\nWritten: real_episode_evaluation.json")


if __name__ == "__main__":
    main()
