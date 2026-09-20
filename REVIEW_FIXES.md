# Reviewer feedback: paste-ready fixes for the paper

The three points from the review are handled below as text you can paste into the paper. The repository has already been updated to match (see the last section). Nothing here changes any reported number.

## 1. Reframe the claim: architecture, not blockchain

Title options. The current title says "Blockchain-Anchored Audit Framework", which promises more than the prototype implements.

Option A: Verifiable Multi-Level Statistical Provenance: A Merkle-Based Architecture for Trustworthy Optical-Radar Decoupling in Hidden Land-Surface Change Detection, Designed for Permissioned-Ledger Deployment

Option B (shorter): Chain-of-Evidence: Merkle-Based Provenance for Multi-Level Statistical Change Detection Pipelines

Scope paragraph, for the Introduction and again at the start of Evaluation:

This paper does not evaluate a blockchain. It proposes and evaluates a provenance mechanism: per-stage leaf hashing, Merkle aggregation, signed append-only anchoring, and governance-gated parameter changes. The evaluation uses a local, hash-chained, ECDSA-signed log that exposes the interface a permissioned-ledger chaincode would, and Section VI maps that interface onto Hyperledger Fabric as a deployment design. Consensus, endorsement, ordering, replication and fault tolerance are neither implemented nor measured, and none of the reported results should be read as ledger throughput or latency.

Terminology, to apply throughout the text, captions and abstract:

- "blockchain audit layer" and "blockchain-anchored" become "Merkle-based provenance architecture"
- "on-chain" becomes "anchored in the ledger" or "ledger entry"
- "blockchain overhead" becomes "anchoring overhead"
- "smart contract" becomes "chaincode interface (design)"
- "immutable" becomes "tamper-evident"

Add this to Limitations, because it is the substantive gap behind the reviewer's point:

In the evaluated prototype the ledger is a single local log, so an operator holding the signing key could truncate or rewrite it and re-sign. The guarantee against a malicious or colluding operator comes from a deployment in which anchoring requires endorsement by independent parties and the log is replicated. This work specifies that deployment but does not implement it.

## 2. Rename the experiment: coverage, not sensitivity

Replace the name "Attack Sensitivity Sweep" with "Provenance Coverage and Tamper-Injection Validation", and remove the words "sensitivity" and "robustness" from the abstract, section text and captions.

Replacement paragraph:

We validate the implementation by injecting controlled tampering into reference episodes and checking that verification rejects it and names the affected stage. The injection grid covers three attack classes (data, parameter, output), every stage where the class applies, and several perturbation magnitudes, with 40 seeds per cell (64 cells, 2,560 episodes). Because verification compares SHA-256 digests, any nonzero change to an anchored field changes the leaf hash with overwhelming probability, so detection is invariant to magnitude by construction. The experiment therefore measures implementation coverage, meaning that every stage's inputs, parameters and outputs enter its leaf hash and that localization names the correct stage. It is not a sensitivity or ROC analysis and does not estimate the robustness of a detector. Its practical value is that it exposes coverage defects: a combined-attack check showed that the original localizer named only the first tampered stage, and a false positive check showed that the parameter cross-check wrongly flagged legitimate older episodes. Both were fixed.

Fig. A caption:

Fig. A. Tamper-injection coverage for a Type-2 attack on tau. Detection is 100% for the proposed scheme and 0% for the naive baseline at every injected magnitude (2% to 75% of the baseline value). The flat curves follow from digest comparison and document coverage, not sensitivity.

## 3. Formula fixes

### 3a. Merkle tree structure

The current equation nests parent(...parent(parent(H1,H2),H3)...,H9), which is a linear hash chain. The code builds a balanced binary tree. Replace it with the following, and state the duplication rule explicitly.

Let L_0 = (h_1, ..., h_n) be the leaf hashes and m_l = |L_l|, with m_0 = n. For every level with m_l > 1:

```
L_{l+1}[j] = H( L_l[2j-1] || L_l[min(2j, m_l)] ),   j = 1, ..., ceil(m_l / 2)
```

so m_{l+1} = ceil(m_l / 2). When m_l is odd, the last node is paired with itself (the Bitcoin convention). The root is R = L_D[1] with D = ceil(log2 n). For the n = 9 stages the level sizes are 9, 5, 3, 2, 1, so D = 4 and a proof path holds 4 sibling hashes.

LaTeX:

```
L_{\ell+1}[j] = \mathrm{H}\!\left(L_{\ell}[2j-1] \,\Vert\, L_{\ell}[\min(2j,\,m_\ell)]\right),
\quad j = 1,\dots,\lceil m_\ell/2 \rceil, \qquad R = L_D[1],\; D = \lceil \log_2 n \rceil
```

Proof verification, equation (5), can be written as a fold over the path. With c_0 = h_i and sibling s_k at step k:

```
c_k = H(s_k || c_{k-1})  if s_k is a left sibling,   c_k = H(c_{k-1} || s_k)  otherwise
Verify(h_i, path_i, R) = [ c_D = R ]
```

In the duplicated-node case s_k equals c_{k-1} and sits on the right.

One sentence for Limitations: duplicating the last node means trees over (a, b, c) and (a, b, c, c) share a root. This does not arise here because the stage set is fixed at 9 and each leaf commits to its own input_ref, but it would need handling if episodes ever had a variable number of stages.

### 3b. Storage formula

The current formula gives b_root = 32 bytes, but the reported numbers are computed with 96 bytes per episode. Show the signature as its own term:

```
b_ep = b_root + b_sig = 32 + 64 = 96 B,     S(N) = N * b_ep
```

For 260 episodes (weekly monitoring over 5 years): S = 24,960 B. The code divides by 1024, so the reported 24.38 is KiB. Write "24.38 KiB", or write "24.96 kB" in decimal units, but do not write 24.38 KB. For monthly monitoring over 1, 2 and 5 years the values are 1.12, 2.25 and 5.62 KiB.

Caveats to state in a footnote or the Limitations text:

- 64 B is the fixed-size raw (r || s) form of an ECDSA P-256 signature. The prototype serializes DER signatures, which measured 70 to 72 bytes over 50 signatures, so 64 B is a nominal figure.
- The 32 B hash-chain link and entry metadata are not counted, so 96 B is a lower bound on the per-episode ledger cost.
- A real Fabric world-state entry adds a key and transaction envelope overhead on top of this.

## 4. One more number to check: the "89% reduction" figure

The earlier storage comparison used 288 B of leaf hashes (9 x 32 B) against a 32 B root only: 1 - 32/288 = 88.9%. With the signature counted, the anchored cost is 96 B: 1 - 96/288 = 66.7%. If the paper still says 89%, either define it as root only ("nine leaf hashes replaced by one 32 B root") or change it to 66.7%. A reviewer who caught the 32 B versus 96 B mismatch will check this next.

## 5. What changed in the repository

- ledger.py: docstrings now say this is not a blockchain and list what is missing. New constants ROOT_BYTES, SIGNATURE_BYTES and ANCHORED_BYTES_PER_EPISODE hold the storage model in one place.
- benchmark.py and demo_tamper_detection.py: use those constants and drop the "on-chain" wording. The storage numbers are identical to the committed results, checked by running both in a scratch copy.
- evaluation_summary.json: the key on_chain_storage_bytes_per_episode (32) is replaced by anchored_root_bytes_per_episode (32), anchored_signature_bytes_per_episode (64) and anchored_bytes_per_episode (96). Timings and every other value are untouched.
- merkle.py: the docstring now gives the exact level definition and duplication rule.
- attack_sweep.py: renamed in its framing, with an explicit statement of what the experiment does and does not show. Its seeds now come from a deterministic function. Before, they came from Python's salted hash(), so every run used different episodes. The output files are byte-identical to the previous run, and reruns now reproduce them.
- make_figures.py: Fig. A and Fig. E titles and labels changed. Regenerated from the existing JSON, so the data is the same.
- architecture.dot: the harness node and the ledger layer are relabeled.
- README.md and BRIEF.md: reframed to match.

## 6. Actions outside the repository

- Re-export Fig. A and Fig. E into the paper. Only their titles and labels changed.
- Re-render the architecture figure from architecture.dot, since the harness and ledger layer labels changed.
- benchmark_results.txt is the captured output of the earlier run and still uses the old "on-chain" label wording. The numbers are correct. Rerunning benchmark.py fixes the wording but changes the timing values slightly, so only do it if the paper does not quote them yet.
