# Provenance PoC: what was built and why it holds up

This is a working summary of the Merkle-based provenance architecture, designed for later permissioned-ledger deployment, built on top of the multi-level optical-radar change detection pipeline. It covers what the system does, how each piece works, what was tested, what that testing found, and what is still open.

## The core idea

The pipeline computes 9 stages per monitoring episode: two data acquisition steps (Sentinel-2, Sentinel-1), then Pearson correlation for two periods, delta_corr, r_t, Moran's I, risk_index, and change_mask. Each stage produces a leaf hash:

H_i = SHA256(input_ref, params_i, output_i, operator_DID, timestamp)

Every stage gets its own leaf, not just the final output. The leaves for one episode are combined into a binary Merkle tree, and only the root plus a signature (96 bytes in total) go into the ledger. Changing a governance parameter such as tau, alpha, beta, or lambda requires a separate signed PARAMETER_CHANGE transaction. Any later mismatch between what a report claims and what is anchored gets caught at the exact stage where it happened, because the leaf hash bakes in both the parameters and the output for that stage.

This is the whole point of the design: most prior work signs only the final delivered result. That catches someone editing the output, but it is structurally blind to someone editing the parameters that produced it while leaving the final number untouched. Anchoring every stage closes that gap.

## What each file does

`merkle.py` builds the Merkle tree and generates and verifies proofs. It can also point to exactly which leaf caused a mismatch.

`ledger.py` is the local stand-in for the ledger layer: an append-only, hash-chained, signed log. It is not a blockchain, since it has no consensus, endorsement, ordering or replication, and a holder of the signing key could rewrite it. It stores EPISODE_ROOT entries (one Merkle root per episode) and PARAMETER_CHANGE entries (governance transactions). No raw data or raw parameters ever get anchored beyond what a single hash needs.

`pipeline.py` is a synthetic stand-in for the real Earth Engine script, using the same math and the same constants, so the provenance layer can be demonstrated and tested without needing live satellite data every time.

`demo_tamper_detection.py` is the original single-episode demonstration: anchor a baseline, do one legitimate parameter change, then simulate one parameter-level attack and one output-level attack, and compare against a naive baseline that signs only the final output.

## What was added this round, and why it matters

The single-episode demo above proves the concept works once. It does not prove it works reliably. Three things were built specifically to close that gap.

### Provenance coverage and tamper-injection validation (`attack_sweep.py`)

Injects controlled tampering into 64 combinations of attack type, target stage, and injected magnitude, each repeated over 40 seeds, for 2560 total episodes, and checks that verification rejects each injection and names the right stage. The seeds are derived deterministically, so a rerun reproduces the same results. It covers all three attack types from the threat model: data-level (scene replay), parameter-level, and output-level, and it runs them against every one of the 9 stages where that attack type applies, not just change_mask.

Result: the proposed scheme detects and correctly localizes 100% of attacks at every magnitude tested, from a 1% output distortion up to a 75% parameter shift. The naive baseline stays at 0% detection except for output-level attacks on change_mask specifically, where it catches the tamper but still cannot say which stage was affected.

The flat 100%/0% lines follow from the design and should not be read as a robustness measurement. Verification compares SHA-256 digests, so any nonzero change to an anchored field changes the digest, and detection cannot depend on the size of the change the way a statistical anomaly threshold would. This experiment is a coverage check of the implementation: it shows that every stage and every attack class actually enters the leaf hashes and that localization names the right stage. Its value is that it can catch coverage bugs, and it caught one (see the combined attack check below).

### False positive sweep (`fp_sweep.py`)

Every result above measures true positives. None of it says anything about whether the system cries wolf on legitimate activity. This sweep tests four scenarios, 40 trials each: an untouched genuine episode, a new episode properly recomputed under a governance-approved parameter change, an older episode checked the way the original demo checks it, and the same older episode checked with a fix described below.

This sweep found a real bug. The original cross-check compares an episode's recorded parameter against the ledger's current governance state. That works fine right after a change, but it means any episode anchored before a later, legitimate parameter change gets wrongly flagged as tampered once that later change is recorded, even though the episode was completely correct when it was made. In this test it produced a 100% false positive rate on that scenario.

The fix is a new method, `ledger.params_as_of(timestamp)`, which replays governance history only up to the episode's own timestamp instead of to the current moment. After the fix, false positives are 0% across all four scenarios.

This is the kind of finding that a testing approach is supposed to produce. It was not assumed away, and it was not left as a known issue. It was found, reproduced, fixed, and the fix was verified by rerunning the same sweep.

### Combined attack check

Part of `attack_sweep.py`. Tests a single episode attacked in two stages at once, a parameter-level attack on risk_index together with an output-level attack on change_mask.

This also found a real bug. The original localization function, `find_mismatched_stage`, returns only the first mismatched stage it encounters, in stage order. Against a two-stage attack it would only ever name one of the two, missing the other in all 40 test trials. The fix is a new method, `find_all_mismatched_stages`, which returns every mismatched stage instead of stopping at the first one. With the fix, both tampered stages are correctly named in all 40 trials.

### Verification latency (`benchmark.py`)

The original benchmark measured pipeline compute time and anchoring overhead. It did not measure what an auditor actually pays at query time: generating a Merkle proof for one stage and verifying it. That was added, measured across the same 5 simulated resolutions used for the rest of the benchmark, and it stays flat at a few microseconds regardless of resolution, since a proof path through a 9-leaf tree is always about 4 hash operations. That is orders of magnitude cheaper than anchoring, and anchoring itself is already a small fraction of pipeline compute time.

### Figures

Six figures were generated at 300 DPI directly from the JSON results above, not from hand-typed numbers: detection rate against attack magnitude, a localization accuracy heatmap across all 9 stages, Type-1 detection, latency on a log-log scale, storage growth over a monitoring period, and the false positive rates including the bug and the fix.

### Real satellite data

`earthengine-api`'s own OAuth flow (both the notebook flow and the gcloud flow) failed repeatedly against this Google account, first with an incompatible OAuth2 client error on two different Cloud projects, then with a blocked-scope error from Google's shared gcloud client. Rather than keep fighting authentication, the fallback already anticipated in the project's own README was used: a JS version of the same pipeline (`gee_extract.js`) run directly in the Earth Engine Code Editor, exporting CSVs, with a Python loader (`load_real_episode_from_csv.py`) rebuilding the same JSON shape the direct API path would have produced. This ran successfully against real Sentinel-1/2 data over Almaty, and the full tamper detection experiment was run against it with results that look reasonable for the AOI size and scale used.

## Why this is a solid basis for the evaluation section

The methodology tests for failure, not just success. A false positive sweep is not a standard thing to include, and it is the kind of check a reviewer is likely to ask for if it is missing. Finding and fixing two real bugs through that testing, rather than needing them pointed out later, is a stronger result than a clean run with no findings at all would have been.

The numbers come from code, not from hand-written estimates. Every figure and every rate quoted anywhere is generated from a JSON file that a script produced, and every script can be rerun to reproduce the same numbers from the same seeds.

The reporting does not fill in gaps with invented numbers. Where a combination genuinely does not apply, such as a parameter-level attack on a stage that has no governance parameter, the heatmap says N/A rather than 0%, and the flat 100%/0% detection curves are explained as an expected property of hash-based verification rather than left to look suspiciously perfect with no comment.

## What is still open

The pipeline in this PoC runs against one real episode, obtained through the Code Editor CSV fallback rather than a direct `earthengine-api` call, because of the OAuth issues above. Running more episodes across different areas of interest, and getting the direct API path working, are both still open.

There is no real Hyperledger Fabric or Caliper deployment, so consensus, endorsement, ordering and replication are neither implemented nor measured. The multi-party guarantee that stops a single operator from rewriting history comes from that deployment, not from this local log. `HYPERLEDGER_FABRIC_MAPPING.md` documents the intended mapping in detail, but running it was a decision made against, given the timeline, not something left unfinished by accident.

DID is a plain ECDSA keypair plus a string identifier, not a full W3C DID document. This is stated as a deliberate simplification in the mapping document, with the equivalent real-world mapping (MSP client certificate identity on Fabric) noted alongside it.

Whatever remains to be written up should draw on the figures and JSON result files in this folder, and on the related work bibliography kept outside the repository.
