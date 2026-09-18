"""
fp_sweep.py — False Positive Rate sweep (BSS2026_Final_Hardening_Brief.md,
Section 1.1, "the most valuable addition"). Every prior experiment
(demo_tamper_detection.py, attack_sweep.py) measures only true-positive
detection under attack. This measures the complementary, equally
important property: does verification ever raise a false alarm on
legitimate, unmodified, or properly governance-approved activity?

Four scenarios, N_TRIALS seeds each:

  genuine_unmodified
      A baseline episode, nothing touched, verified against its own
      anchored root. Expected: 0% (pure sanity check).

  legitimate_new_param_recomputed
      A fresh episode is properly recomputed end-to-end under a NEW
      governance-approved tau (0.5), after the matching PARAMETER_CHANGE
      tx. Verified by recomputing its root (should match, nothing was
      tampered) and cross-checking its claimed tau against
      ledger.latest_params(). Expected: 0%.

  legitimate_old_episode_naive_check
      An OLDER episode is anchored under tau=0.4. AFTERWARDS, a later,
      legitimate, signed governance tx changes tau to 0.5. The old
      episode's own recorded tau (0.4, correct at the time) is then
      cross-checked against ledger.latest_params()["tau"] -- the *current*
      approved value, i.e. the exact style demo_tamper_detection.py uses.
      This is a genuine timestamp-scoping bug, not a hypothetical: the old
      episode did nothing wrong, but this check flags it anyway because
      latest_params() has moved on. Expected (before the fix): 100%.

  legitimate_old_episode_scoped_check
      The same setup as above, but cross-checked against
      ledger.params_as_of(episode_timestamp) instead (the fix added to
      ledger.py). Expected (after the fix): 0%.

Run: python3 fp_sweep.py
Output: fp_sweep_results.json
"""
from __future__ import annotations
import json
import time

from ledger import ProvenanceLedger, OperatorDID
from pipeline import run_episode, DEFAULT_PARAMS
from demo_tamper_detection import build_episode_tree

N_TRIALS = 40


def scenario_genuine_unmodified(seed: int) -> bool:
    """True iff a false positive was raised (should never happen)."""
    operator = OperatorDID.generate(did=f"did:example:fp-genuine-{seed}")
    records = run_episode(seed=seed, operator_did=operator.did, params=DEFAULT_PARAMS)
    anchored_root = build_episode_tree(records).root
    recomputed_root = build_episode_tree(records).root  # verifier's independent recompute
    return recomputed_root != anchored_root


def scenario_new_param_recomputed(seed: int) -> bool:
    """A brand-new episode, properly recomputed under a governance-approved
    new tau. True iff falsely flagged."""
    operator = OperatorDID.generate(did=f"did:example:fp-new-{seed}")
    ledger = ProvenanceLedger()
    ledger.register_operator(operator)
    ledger.append("PARAMETER_CHANGE", {"param": "tau", "old": 0.4, "new": 0.5}, operator)

    new_params = dict(DEFAULT_PARAMS, tau=0.5)
    records = run_episode(seed=seed, operator_did=operator.did, params=new_params)
    anchored_root = build_episode_tree(records).root
    recomputed_root = build_episode_tree(records).root
    root_mismatch = recomputed_root != anchored_root

    claimed_tau = next(r.params["tau"] for r in records if r.label == "change_mask")
    approved_tau = ledger.latest_params()["tau"]
    param_mismatch = approved_tau != claimed_tau
    return root_mismatch or param_mismatch


def scenario_old_episode(seed: int, scoped: bool) -> bool:
    """An episode anchored under tau=0.4, followed by a LATER legitimate
    governance change to tau=0.5. Cross-checks the OLD episode's own
    recorded tau against either the ledger's current state (scoped=False,
    the buggy check) or the state as of the episode's own timestamp
    (scoped=True, the fix). True iff falsely flagged."""
    operator = OperatorDID.generate(did=f"did:example:fp-old-{seed}")
    ledger = ProvenanceLedger()
    ledger.register_operator(operator)

    old_ts = time.time()
    old_records = run_episode(seed=seed, operator_did=operator.did,
                               params=DEFAULT_PARAMS, timestamp=old_ts)
    ledger.append("EPISODE_ROOT", {"episode_id": f"trial-{seed}",
                                     "root": build_episode_tree(old_records).root}, operator)

    ledger.append("PARAMETER_CHANGE", {"param": "tau", "old": 0.4, "new": 0.5}, operator)  # strictly later

    claimed_tau = next(r.params["tau"] for r in old_records if r.label == "change_mask")
    approved_tau = ledger.params_as_of(old_ts)["tau"] if scoped else ledger.latest_params()["tau"]
    return approved_tau != claimed_tau


def run_scenario(name, fn, **kwargs):
    fp = sum(fn(seed, **kwargs) for seed in range(N_TRIALS))
    return {"scenario": name, "n_trials": N_TRIALS, "false_positive_count": fp,
            "false_positive_rate": round(fp / N_TRIALS, 4)}


def main():
    results = [
        run_scenario("genuine_unmodified", scenario_genuine_unmodified),
        run_scenario("legitimate_new_param_recomputed", scenario_new_param_recomputed),
        run_scenario("legitimate_old_episode_naive_check", scenario_old_episode, scoped=False),
        run_scenario("legitimate_old_episode_scoped_check", scenario_old_episode, scoped=True),
    ]

    with open("fp_sweep_results.json", "w") as f:
        json.dump(results, f, indent=2)

    for r in results:
        print(f"{r['scenario']:>38}: {r['false_positive_count']:>3}/{r['n_trials']} "
              f"({r['false_positive_rate']*100:.1f}%)")
    print("\nWritten: fp_sweep_results.json")


if __name__ == "__main__":
    main()
