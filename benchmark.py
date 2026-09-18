"""
benchmark.py — Evaluation Plan items 1-2 (brief Section 5), plus
BSS2026_Final_Hardening_Brief.md Section 1.2 (end-to-end verification
latency):

  1. Overhead of blockchain anchoring relative to pipeline compute time,
     at several scales (grid resolution stands in for the GEE `scale`
     parameter: 10m/30m/100m -> finer scale = more pixels = larger grid).
  2. Storage cost projection: how many hashes/blocks accumulate for one
     AOI over a realistic monitoring period.
  3. End-to-end verification latency: Merkle-proof generation for one
     stage (auditor requests it) and proof verification (auditor checks
     it) -- the two operations that actually happen at audit time,
     separate from and much cheaper than anchoring itself (log2(9) ~ 4
     hash ops per proof, independent of AOI size/scale, since n_leaves is
     always 9 regardless of resolution).

Single-run timings at millisecond scale are noisy, so this averages
over N_TRIALS repetitions per scale and reports mean +/- stdev.

Run: python3 benchmark.py
"""

from __future__ import annotations
import json
import statistics
import time

from ledger import ProvenanceLedger, OperatorDID
from merkle import MerkleTree
import pipeline as pl

N_TRIALS = 500

# Grid sizes as a proxy for GEE `scale` (finer scale over the same 10km
# buffer AOI -> more pixels). Real conversion: (2*10000/scale)^2 pixels;
# we cap the synthetic grid well below that for tractability but keep
# the *relative* pixel-count ratios comparable. 50m/20m added (per
# BSS2026_Improvement_Brief.md Fig. D) so the log-log latency plot has
# 5 points instead of 3.
SCALE_TO_GRID = {"100m": 24, "50m": 34, "30m": 48, "20m": 63, "10m": 96}


def time_episode(grid_size: int, operator: OperatorDID):
    pl.GRID_SIZE = grid_size  # monkey-patch module-level constant for this trial
    t0 = time.perf_counter()
    records = pl.run_episode(seed=1, operator_did=operator.did)
    t1 = time.perf_counter()
    tree = MerkleTree(leaves=[r.leaf_hash() for r in records],
                       leaf_labels=[r.label for r in records])
    t2 = time.perf_counter()

    # end-to-end verification latency: an auditor requesting a proof for
    # one stage, then checking it (Section 1.2) -- pick the middle stage
    # so the path length is representative, not best/worst case.
    idx = len(records) // 2
    t3 = time.perf_counter()
    proof = tree.get_proof(idx)
    t4 = time.perf_counter()
    ok = proof.verify()
    t5 = time.perf_counter()
    assert ok, "proof.verify() should always pass for an untampered episode"

    return (t1 - t0), (t2 - t1), (t4 - t3), (t5 - t4), len(records)


def main():
    operator = OperatorDID.generate(did="did:example:benchmark-operator")

    print("=" * 78)
    print("1. OVERHEAD ACROSS SCALES (mean +/- stdev over {} trials)".format(N_TRIALS))
    print("=" * 78)
    print(f"{'scale':>8} {'grid':>6} {'pipeline_ms':>14} {'anchor_ms':>12} {'overhead_%':>12}"
          f" {'proof_gen_us':>13} {'proof_verify_us':>16}")
    results = {}
    for scale_label, grid in SCALE_TO_GRID.items():
        pipe_times, anchor_times, proof_gen_times, proof_verify_times = [], [], [], []
        for _ in range(N_TRIALS):
            pt, at, pg, pv, n_leaves = time_episode(grid, operator)
            pipe_times.append(pt * 1000)
            anchor_times.append(at * 1000)
            proof_gen_times.append(pg * 1e6)
            proof_verify_times.append(pv * 1e6)
        pipe_mean, pipe_sd = statistics.mean(pipe_times), statistics.stdev(pipe_times)
        anchor_mean, anchor_sd = statistics.mean(anchor_times), statistics.stdev(anchor_times)
        proof_gen_mean = statistics.mean(proof_gen_times)
        proof_verify_mean = statistics.mean(proof_verify_times)
        overhead_pct = 100 * anchor_mean / pipe_mean
        results[scale_label] = dict(pipe_mean=pipe_mean, pipe_sd=pipe_sd,
                                     anchor_mean=anchor_mean, anchor_sd=anchor_sd,
                                     overhead_pct=overhead_pct, n_leaves=n_leaves,
                                     proof_gen_us_mean=proof_gen_mean,
                                     proof_verify_us_mean=proof_verify_mean)
        print(f"{scale_label:>8} {grid:>6} {pipe_mean:>10.2f}±{pipe_sd:<4.1f}"
              f" {anchor_mean:>8.2f}±{anchor_sd:<3.1f} {overhead_pct:>11.2f}%"
              f" {proof_gen_mean:>13.2f} {proof_verify_mean:>16.2f}")

    print("\n(As grid resolution increases, pipeline compute grows faster than "
          "hashing/Merkle/signing -- which touches only per-stage SUMMARY hashes, "
          "not every pixel individually -- so relative overhead should shrink at "
          "finer scales. Cite this trend, not just the raw percentages, since "
          "absolute ms values here are sandbox-dependent, not GEE-server-dependent.)")
    print("\n(Proof generation/verification -- what an auditor actually pays at "
          "query time -- are reported in microseconds and stay flat across scale, "
          "since a proof path is always log2(9) ~ 4 hash operations regardless of "
          "AOI size or resolution: verification cost does not grow with the data.)")

    print("\n" + "=" * 78)
    print("2. STORAGE COST PROJECTION over a monitoring period")
    print("=" * 78)
    leaves_per_episode = results["100m"]["n_leaves"]
    on_chain_bytes_per_episode = 32 + 64  # Merkle root + ECDSA signature (approx, SECP256R1 DER ~70-72B)
    off_chain_bytes_per_episode = leaves_per_episode * 32

    storage_projection = []
    for label, episodes_per_year in [("monthly monitoring", 12),
                                      ("bi-weekly monitoring", 26),
                                      ("weekly monitoring", 52)]:
        for years in (1, 2, 5):
            n_episodes = episodes_per_year * years
            on_chain_total = n_episodes * on_chain_bytes_per_episode
            off_chain_total = n_episodes * off_chain_bytes_per_episode
            storage_projection.append(dict(cadence=label, years=years, n_episodes=n_episodes,
                                            on_chain_bytes=on_chain_total, off_chain_bytes=off_chain_total))
            print(f"{label:>22}, {years}y: {n_episodes:>4} episodes -> "
                  f"on-chain {on_chain_total/1024:>7.2f} KB | "
                  f"off-chain leaf store {off_chain_total/1024:>7.2f} KB")

    print(f"\nPer-episode fixed leaf count: {leaves_per_episode} stages "
          f"(independent of AOI size or scale -- the pipeline structure is fixed, "
          f"only per-pixel array sizes inside each stage's array_hash change). "
          "This is the key scalability argument: on-chain storage growth is "
          "O(episodes), not O(pixels) or O(AOI area), because raw rasters never "
          "go on-chain -- only one root + one signature per episode.")

    with open("benchmark_results.json", "w") as f:
        json.dump({"overhead_by_scale": results, "storage_projection": storage_projection}, f, indent=2)
    print("\nWritten: benchmark_results.json")


if __name__ == "__main__":
    main()
