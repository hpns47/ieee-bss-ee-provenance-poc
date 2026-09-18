# BSS2026 Provenance Paper — Project Context

Read this before doing anything. This is a research-paper-plus-PoC
project with a **hard deadline: paper submission Sept 20, 2026**
(EDAS, https://edas.info/newPaper.php?c=35179&track=139226). Camera-ready
is Oct 22 if accepted — anything not essential for submission belongs
there, not now.

## What this project is

A second, standalone paper for BSS 2026 (5th International Workshop on
Blockchain Security and Scalability) that builds a blockchain-anchored
provenance/audit layer on top of an already-published geospatial change
detection method (SIST 2026, cited as prior work in **third person only**
— double-blind review, do not deanonymize with "our earlier work").

Novelty: anchoring *every stage* of a multi-level statistical pipeline
(not just input/output) via Merkle trees, with an explicit threat model
covering **parameter-level manipulation** (τ/α/β/λ changed retroactively)
as a first-class attack, which the literature review found nothing else
does.

## Current status (as of last session)

All of this is implemented and tested, in this same directory:

- `merkle.py`, `ledger.py`, `pipeline.py` — Merkle tree + signed
  append-only ledger + synthetic pipeline mirroring the real GEE math
  (Pearson r, Δr, Moran's I, risk_index — same ALPHA=0.5/BETA=0.3/
  LAMBDA=0.2/TAU=0.4 as the original script).
- `demo_tamper_detection.py` — **the central evaluation experiment**:
  anchors a baseline episode, does a legitimate governance parameter
  change, then Attack Type 2 (parameter tamper) and Attack Type 3
  (output tamper), both detected and localized to the exact pipeline
  stage; compares against a naive sign-the-output-only baseline which
  is structurally blind to Attack Type 2. Runs clean, no deps beyond
  numpy + cryptography.
- `benchmark.py` — overhead across simulated scales + storage cost
  projection over monitoring periods. Runs clean.
- `gee_extract.py` — Python (`earthengine-api`) translation of the
  **original JS pipeline** (was never run against real Earth Engine —
  the previous sandbox this was written in has no network access to
  `earthengine.googleapis.com`). **This is the first thing to actually
  run and debug now that real network access exists.**
- `load_real_episode.py` — takes `gee_extract.py`'s JSON output and
  runs the same tamper-detection experiment on real Sentinel-1/2 data.
  Tested end-to-end against a synthetic stand-in JSON
  (`real_episode_data.example.json`); never against real GEE output.
- `HYPERLEDGER_FABRIC_MAPPING.md` — design-level mapping of `ledger.py`
  onto a Hyperledger Fabric chaincode (state model, function table,
  illustrative untested Go pseudocode). Decision already made: **not**
  attempting a real Fabric/Caliper deployment before Sept 20 — this doc
  is what the paper cites instead, with honest Limitations wording
  already drafted inside it.
- `README.md` — full file-by-file map and run instructions.

## What's NOT done yet

1. `gee_extract.py` has never actually been run against real Earth
   Engine. Needs: `pip install earthengine-api`, `earthengine
   authenticate` (needs a Google Cloud project with the EE API enabled),
   then `python3 gee_extract.py --project YOUR_PROJECT_ID`. Debug
   whatever breaks — it's a straight JS→Python translation, so bugs are
   likely (band names, `.getInfo()` on large sample sizes timing out,
   `bestEffort=True` behavior, etc.) rather than logic errors.
2. Once real data loads cleanly, run `load_real_episode.py` against it
   and sanity-check the numbers make sense (e.g. `changed_pixels_est`
   isn't absurd for a 10km AOI at 100m scale).
3. The actual paper text (IEEE two-column, 6 pages, structure is in
   `BSS2026_Project_Brief.md` if present, otherwise ask the user for it
   — Abstract, Introduction, Related Work, Threat Model, Architecture,
   Implementation, Evaluation, Discussion/Limitations, Conclusion).
   None of this has been written yet. The code and the mapping doc are
   the evidence base for Architecture/Implementation/Evaluation/
   Limitations sections — pull numbers from `evaluation_summary.json`
   and (once generated) `real_episode_evaluation.json`.
4. `benchmark.py` numbers are sandbox-timing artifacts (noisy at ms
   scale) — if rerun on this machine for the paper's actual reported
   numbers, increase `N_TRIALS` and note in the paper that these are
   single-machine relative-overhead trends, not absolute performance
   claims.

## Ground rules

- Don't attempt a real Hyperledger Fabric deployment before Sept 20 —
  already decided against it given the timeline. `HYPERLEDGER_FABRIC_MAPPING.md`
  is the deliverable for that instead.
- Self-citation to the SIST 2026 paper: third person only, anywhere in
  paper text.
- If something in the code turns out to be wrong once run against real
  data (e.g. a mistranslated GEE operation), fix it and note the fix —
  don't silently change the numbers already in `evaluation_summary.json`
  without flagging that they were synthetic-data numbers to begin with.
