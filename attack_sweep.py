"""
attack_sweep.py — Attack Sensitivity Sweep (BSS2026_Improvement_Brief.md,
Section 1). Replaces the single-episode / single-magnitude / single-stage
tamper demo (demo_tamper_detection.py) with a statistically meaningful
sweep: every attack type x every applicable target stage x a grid of
magnitudes x N_TRIALS random seeds, recording detection/localization
rates for both the proposed (Merkle multi-level) scheme and the naive
(sign-only-the-final-output) baseline.

Attack types (per brief Section 1.2):
  type1_data      -- data_acquisition_s2 / data_acquisition_s1: simulate
                      scene replay/reuse (swap the scene-id-commitment hash),
                      binary (attacked or not). This is the empirical test
                      for what Limitations previously called only
                      "structurally addressed."
  type2_parameter -- a governance parameter (tau on change_mask, or
                      alpha/beta/lambda jointly on risk_index) is edited on
                      the record retroactively, with NO matching
                      PARAMETER_CHANGE governance-log entry, and the
                      stage's numeric output left stale (attacker doesn't
                      bother recomputing) -- exactly mirrors the tau attack
                      in demo_tamper_detection.py, generalized to a
                      magnitude grid and to risk_index's own parameters.
  type3_output    -- the recorded output of ANY of the 9 stages is edited
                      directly (its numeric summary field, or for the two
                      data-acquisition stages, the scene-hash commitment),
                      without recomputing anything downstream.

For type2/type3, the perturbation is relative to the stage's own value
with a floor (max(|value|, 1e-6)) so a near-zero baseline value still
gets a meaningful nonzero perturbation; the perturbation's sign is drawn
per-trial from that trial's own RNG (documented choice: unbiased random
direction rather than always-inflate or always-deflate).

Detection: recompute leaf hashes for the (possibly tampered) records and
compare the resulting Merkle root against the anchored (genuine) root.
Localization: MerkleTree.find_mismatched_stage against the genuine tree's
leaves -- correct iff it names exactly the attacked stage.
Naive baseline: signs only change_mask's output; by construction it can
only ever detect a tamper that changes change_mask's own output, and can
never localize (no per-stage structure).

Run: python3 attack_sweep.py
Output: attack_sweep_results.json (one object per attack_type x
target_stage x magnitude combination, per the brief's Section 1.3 schema).
"""

from __future__ import annotations
import copy
import json
import time

import numpy as np

from ledger import OperatorDID
from merkle import sha256_hex
from pipeline import run_episode, DEFAULT_PARAMS
from demo_tamper_detection import (
    build_episode_tree,
    recompute_leaves,
    naive_baseline_sign,
    naive_baseline_verify,
)

N_TRIALS = 40  # within the brief's 30-50 range

STAGES = [
    "data_acquisition_s2", "data_acquisition_s1",
    "pearson_corr_period1", "pearson_corr_period2",
    "delta_corr", "r_t", "moran_index", "risk_index", "change_mask",
]

# which output field type3 perturbs, per stage (the two data-acquisition
# stages have no continuous numeric output -- see apply_type3).
NUMERIC_FIELD = {
    "pearson_corr_period1": "mean", "pearson_corr_period2": "mean",
    "delta_corr": "mean", "r_t": "mean", "moran_index": "mean",
    "risk_index": "mean", "change_mask": "changed_pixels",
}

TAU_DELTAS = [0.02, 0.05, 0.1, 0.15, 0.2, 0.3]          # absolute, both signs
RISK_PARAM_MAGNITUDES = [0.05, 0.10, 0.20, 0.30, 0.50]  # relative to alpha/beta/lambda
OUTPUT_MAGNITUDES = [0.01, 0.05, 0.10, 0.25, 0.50]      # relative, type3


def _perturb(old_value: float, rel_magnitude: float, sign: float) -> float:
    """Relative perturbation with a floor so a near-zero baseline value
    still gets a meaningful nonzero change (documented Section 1.2 choice)."""
    floor = max(abs(old_value), 1e-6)
    return old_value + sign * rel_magnitude * floor


def apply_type1(records: list, stage_label: str, rng) -> list:
    tampered = copy.deepcopy(records)
    for r in tampered:
        if r.label == stage_label:
            new_output = dict(r.output)
            new_output["n_images_ref_hash"] = sha256_hex(
                f"replayed-scene-{int(rng.integers(0, 1_000_000))}".encode())
            r.output = new_output
    return tampered


def apply_type2_tau(records: list, signed_delta: float) -> list:
    tampered = copy.deepcopy(records)
    for r in tampered:
        if r.label == "change_mask":
            new_params = dict(r.params)
            new_params["tau"] = new_params["tau"] + signed_delta
            r.params = new_params
            # output.changed_pixels intentionally left stale (computed under
            # the original tau) -- attacker edits the param, not the result.
    return tampered


def apply_type2_risk(records: list, rel_magnitude: float, sign: float) -> list:
    tampered = copy.deepcopy(records)
    for r in tampered:
        if r.label == "risk_index":
            new_params = dict(r.params)
            for k in ("alpha", "beta", "lambda"):
                new_params[k] = new_params[k] * (1 + sign * rel_magnitude)
            r.params = new_params  # output left stale, as above
    return tampered


def apply_type3(records: list, stage_label: str, rel_magnitude: float, sign: float, rng) -> list:
    tampered = copy.deepcopy(records)
    for r in tampered:
        if r.label != stage_label:
            continue
        new_output = dict(r.output)
        if stage_label in ("data_acquisition_s2", "data_acquisition_s1"):
            new_output["n_images_ref_hash"] = sha256_hex(
                f"edited-{stage_label}-{int(rng.integers(0, 1_000_000))}".encode())
        else:
            field = NUMERIC_FIELD[stage_label]
            new_val = _perturb(float(new_output[field]), rel_magnitude, sign)
            if stage_label == "change_mask":
                new_val = max(0, round(new_val))
            new_output[field] = new_val
        r.output = new_output
    return tampered


def run_trial(attack_type: str, target_stage: str, magnitude: float, seed: int, operator: OperatorDID):
    rng = np.random.default_rng(seed)
    genuine = run_episode(seed=seed, operator_did=operator.did, params=DEFAULT_PARAMS)
    genuine_tree = build_episode_tree(genuine)
    anchored_root = genuine_tree.root

    if attack_type == "type1_data":
        tampered = apply_type1(genuine, target_stage, rng)
    elif attack_type == "type2_parameter":
        if target_stage == "change_mask":
            tampered = apply_type2_tau(genuine, magnitude)
        else:
            sign = float(rng.choice([-1.0, 1.0]))
            tampered = apply_type2_risk(genuine, magnitude, sign)
    elif attack_type == "type3_output":
        sign = float(rng.choice([-1.0, 1.0]))
        tampered = apply_type3(genuine, target_stage, magnitude, sign, rng)
    else:
        raise ValueError(f"unknown attack_type {attack_type!r}")

    tampered_leaves = recompute_leaves(tampered)
    tampered_tree = build_episode_tree(tampered)
    proposed_detected = tampered_tree.root != anchored_root
    localized_stage = genuine_tree.find_mismatched_stage(tampered_leaves) if proposed_detected else None
    proposed_localized_correct = localized_stage == target_stage

    naive_anchor = naive_baseline_sign(genuine, operator)
    naive_ok = naive_baseline_verify(tampered, naive_anchor, operator)
    naive_detected = not naive_ok

    return proposed_detected, proposed_localized_correct, naive_detected


def apply_combined(records: list, rng) -> list:
    """Priority-2 combined-attack test (BSS2026_Final_Hardening_Brief.md):
    Type-2 on risk_index (alpha/beta/lambda, magnitude 0.2) AND Type-3 on
    change_mask (magnitude 0.1) simultaneously, in one episode."""
    tampered = apply_type2_risk(records, 0.2, float(rng.choice([-1.0, 1.0])))
    tampered = apply_type3(tampered, "change_mask", 0.1, float(rng.choice([-1.0, 1.0])), rng)
    return tampered


def run_combined_attack_check(n_trials: int, operator: OperatorDID) -> dict:
    detected = both_localized_new = only_one_localized_old = 0
    for i in range(n_trials):
        seed = hash(("combined", i)) % (2**31)
        rng = np.random.default_rng(seed)
        genuine = run_episode(seed=seed, operator_did=operator.did, params=DEFAULT_PARAMS)
        genuine_tree = build_episode_tree(genuine)
        tampered = apply_combined(genuine, rng)
        tampered_leaves = recompute_leaves(tampered)
        tampered_tree = build_episode_tree(tampered)

        if tampered_tree.root != genuine_tree.root:
            detected += 1
            all_mismatched = genuine_tree.find_all_mismatched_stages(tampered_leaves)
            if set(all_mismatched) == {"risk_index", "change_mask"}:
                both_localized_new += 1
            first_mismatched = genuine_tree.find_mismatched_stage(tampered_leaves)
            if first_mismatched in ("risk_index", "change_mask") and set(all_mismatched) != {first_mismatched}:
                only_one_localized_old += 1  # old method would have missed the other stage

    return {
        "n_trials": n_trials,
        "detected_count": detected,
        "both_stages_localized_correct_count_new_method": both_localized_new,
        "old_single_stage_method_would_have_missed_one_count": only_one_localized_old,
        "detection_rate": round(detected / n_trials, 4),
        "both_stage_localization_accuracy_new_method": round(both_localized_new / n_trials, 4),
    }


def build_combos():
    combos = []
    for stage in ("data_acquisition_s2", "data_acquisition_s1"):
        combos.append(("type1_data", stage, 1.0))  # binary: attack applied
    for d in TAU_DELTAS:
        for sign in (1.0, -1.0):
            combos.append(("type2_parameter", "change_mask", round(sign * d, 4)))
    for m in RISK_PARAM_MAGNITUDES:
        combos.append(("type2_parameter", "risk_index", m))
    for stage in STAGES:
        for m in OUTPUT_MAGNITUDES:
            combos.append(("type3_output", stage, m))
    return combos


def main():
    operator = OperatorDID.generate(did="did:example:sweep-operator")
    combos = build_combos()
    print(f"Running {len(combos)} combinations x {N_TRIALS} trials = "
          f"{len(combos) * N_TRIALS} episodes...")

    t0 = time.perf_counter()
    results = []
    for attack_type, target_stage, magnitude in combos:
        proposed_det = proposed_loc = naive_det = 0
        for i in range(N_TRIALS):
            seed = hash((attack_type, target_stage, magnitude, i)) % (2**31)
            pd, pl, nd = run_trial(attack_type, target_stage, magnitude, seed, operator)
            proposed_det += int(pd)
            proposed_loc += int(pl)
            naive_det += int(nd)
        results.append({
            "attack_type": attack_type,
            "target_stage": target_stage,
            "magnitude": magnitude,
            "n_trials": N_TRIALS,
            "proposed_detected_count": proposed_det,
            "proposed_localized_correct_count": proposed_loc,
            "naive_detected_count": naive_det,
            "naive_localized_correct_count": 0,  # naive baseline structurally cannot localize
            "proposed_detection_rate": round(proposed_det / N_TRIALS, 4),
            "proposed_localization_accuracy": round(proposed_loc / N_TRIALS, 4),
            "naive_detection_rate": round(naive_det / N_TRIALS, 4),
        })
    elapsed = time.perf_counter() - t0

    with open("attack_sweep_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"Done in {elapsed:.2f}s. Wrote {len(results)} combination results "
          f"to attack_sweep_results.json")

    print("\nCombined-attack check (Priority 2): Type-2 on risk_index + "
          "Type-3 on change_mask, simultaneously, in one episode...")
    combined = run_combined_attack_check(N_TRIALS, operator)
    with open("combined_attack_results.json", "w") as f:
        json.dump(combined, f, indent=2)
    print(json.dumps(combined, indent=2))
    print("Written: combined_attack_results.json")

    # quick honest summary printed to console
    for at in ("type1_data", "type2_parameter", "type3_output"):
        rows = [r for r in results if r["attack_type"] == at]
        pd_rates = [r["proposed_detection_rate"] for r in rows]
        nd_rates = [r["naive_detection_rate"] for r in rows]
        print(f"{at:>16}: n_combos={len(rows):>3}  "
              f"proposed_detection_rate min/mean/max = "
              f"{min(pd_rates):.2f}/{sum(pd_rates)/len(pd_rates):.2f}/{max(pd_rates):.2f}  "
              f"naive_detection_rate min/mean/max = "
              f"{min(nd_rates):.2f}/{sum(nd_rates)/len(nd_rates):.2f}/{max(nd_rates):.2f}")


if __name__ == "__main__":
    main()
