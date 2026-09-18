# Mapping the Provenance PoC onto Hyperledger Fabric

**Status:** design-level mapping, not a running deployment. `ledger.py`
in this PoC implements the exact same *interface* a Fabric chaincode
would expose (same function names, same state transitions, same
invariants); it is executed as a single local process instead of by a
Fabric peer network with ordering-service consensus. This document is
the artifact that lets the paper honestly claim "designed for
Hyperledger Fabric deployment" (Section 4.3 of the brief) while being
explicit in Limitations that the distributed deployment itself is
future work (Section 6 fallback).

This is written to be citable directly in the paper's Architecture and
Implementation sections, and to be dropped near-verbatim into
Limitations.

---

## 1. Why this mapping is a legitimate thing to claim in the paper

A chaincode is, at its core, a deterministic state-transition function
over a key-value world state, invoked via transactions that go through
endorsement → ordering → commitment. `ledger.py`'s `ProvenanceLedger`
already enforces the two properties that matter for the paper's threat
model:

1. **Append-only, hash-chained history** (`prev_entry_hash` on every
   entry) — the same integrity property Fabric gets "for free" from
   its ordering service and block structure.
2. **Every state-changing call is signed by an identity and that
   signature is checked before the state is considered valid**
   (`OperatorDID.sign` / `ProvenanceLedger.verify_entry`) — the same
   role Fabric's MSP (Membership Service Provider) plays via X.509
   client certificates on every transaction proposal.

What Fabric adds that the PoC cannot claim on its own: **distributed
consensus and peer replication** (no single party, including the
monitoring operator, can unilaterally rewrite history because multiple
independent peers must endorse and the ordering service linearizes
commitment), and **channel-based access control** (governance
transactions can be restricted to an endorsement policy requiring
signatures from a separate "oversight" organization, not just the
operator). Both should be named explicitly as the delta between the PoC
and the target deployment — see Section 5 below.

---

## 2. State model (Fabric world state keys)

| Key pattern | Value | Maps to (PoC) |
|---|---|---|
| `EPISODE_ROOT:<episode_id>` | `{root, stage_labels[], operator_msp_id, timestamp, tx_signature}` | one `LedgerEntry` with `entry_type="EPISODE_ROOT"` |
| `PARAM_CURRENT:<param_name>` | `{value, changed_by, timestamp}` | `ProvenanceLedger.latest_params()` |
| `PARAM_HISTORY:<param_name>:<seq>` | `{old, new, operator_msp_id, timestamp, tx_signature}` | one `LedgerEntry` with `entry_type="PARAMETER_CHANGE"` |
| `CHAIN_HEAD` | hash of the most recent committed entry | `ProvenanceLedger._last_hash()` |

`episode_id` and `param_name` are the partitioning keys; Fabric's
built-in key range queries (`GetStateByPartialCompositeKey`) replace
the PoC's linear scan over `self.entries` used in
`latest_params()`/`verify_chain()`.

---

## 3. Function-by-function mapping

| `ledger.py` (PoC, runs locally) | Fabric chaincode (target deployment) | Notes |
|---|---|---|
| `ProvenanceLedger.append("EPISODE_ROOT", payload, operator)` | `AnchorEpisodeRoot(ctx, episodeID, root, stageLabels[])` | Operator's client identity (`ctx.GetClientIdentity()`) replaces the explicit `OperatorDID` object — Fabric authenticates the caller before the function body even runs |
| `ProvenanceLedger.append("PARAMETER_CHANGE", payload, operator)` | `ChangeParameter(ctx, paramName, newValue)` | Should be gated by a **separate endorsement policy** (e.g. requires an "Oversight" org's peer, not just "Operator" org) — this is exactly the governance control the brief's threat model (Type 2) needs, and Fabric gives it natively via `endorsement policy` per chaincode/key |
| `ProvenanceLedger.verify_entry(entry)` | *(implicit)* — Fabric rejects the transaction at endorsement time if the submitter's signature/cert doesn't validate | No separate query needed; this is enforced by the platform, not application logic |
| `ProvenanceLedger.verify_chain()` | `VerifyChainIntegrity(ctx)` *(query)* | On real Fabric this is largely redundant — the block hash chain already guarantees this — but useful for the audit layer's UX (return PASS/FAIL + first broken entry, mirroring the PoC's return value) |
| `ProvenanceLedger.latest_params()` | `GetCurrentParams(ctx)` *(query)* | Reads `PARAM_CURRENT:*` keys directly instead of replaying history |
| `MerkleTree.find_mismatched_stage(...)` | stays **off-chain**, in the Verification/Audit Layer | Chaincode never sees raw stage data or Merkle proofs computed client-side against the on-chain root — this matches the brief's selective-disclosure design (Section 4.1, item 5) exactly: only the root goes on-chain, proofs are verified by the auditor locally |

---

## 4. Illustrative chaincode sketch (Go, `fabric-contract-api-go` style)

This is **pseudocode for the paper's Implementation section**, written
in Fabric's idiomatic contract style — it has not been compiled or run
against a real Fabric SDK/network (no Fabric toolchain in this
environment). Treat it as a specification, not tested code.

```go
package chaincode

import (
    "encoding/json"
    "fmt"
    "time"

    "github.com/hyperledger/fabric-contract-api-go/contractapi"
)

type ProvenanceContract struct {
    contractapi.Contract
}

type EpisodeRoot struct {
    EpisodeID    string   `json:"episodeId"`
    Root         string   `json:"root"`         // hex SHA-256 Merkle root
    StageLabels  []string `json:"stageLabels"`
    OperatorMSP  string   `json:"operatorMsp"`  // from ctx.GetClientIdentity()
    Timestamp    int64    `json:"timestamp"`
}

type ParamChange struct {
    Param       string  `json:"param"`
    OldValue    float64 `json:"oldValue"`
    NewValue    float64 `json:"newValue"`
    OperatorMSP string  `json:"operatorMsp"`
    Timestamp   int64   `json:"timestamp"`
}

// AnchorEpisodeRoot: called by the monitoring operator's identity after
// running the off-chain statistical pipeline + building the Merkle tree
// over its per-stage leaf hashes (see merkle.py / pipeline.py). Only the
// root is written on-chain -- raw rasters and per-stage outputs never
// leave the off-chain Statistical Computation Layer.
func (c *ProvenanceContract) AnchorEpisodeRoot(
    ctx contractapi.TransactionContextInterface,
    episodeID string, root string, stageLabelsJSON string,
) error {
    clientMSP, err := ctx.GetClientIdentity().GetMSPID()
    if err != nil {
        return fmt.Errorf("identity error: %v", err)
    }
    var stageLabels []string
    if err := json.Unmarshal([]byte(stageLabelsJSON), &stageLabels); err != nil {
        return err
    }

    key := "EPISODE_ROOT:" + episodeID
    existing, _ := ctx.GetStub().GetState(key)
    if existing != nil {
        return fmt.Errorf("episode %s already anchored (append-only)", episodeID)
    }

    entry := EpisodeRoot{
        EpisodeID: episodeID, Root: root, StageLabels: stageLabels,
        OperatorMSP: clientMSP, Timestamp: time.Now().Unix(),
    }
    bytes, _ := json.Marshal(entry)
    return ctx.GetStub().PutState(key, bytes)
}

// ChangeParameter: governance transaction for alpha/beta/lambda/tau.
// In the channel's endorsement policy, this function's key range
// ("PARAM_CURRENT:*", "PARAM_HISTORY:*") should require endorsement
// from a distinct "Oversight" organization's peer -- NOT the operator
// org alone -- which is what makes Attack Type 2 (silent tau change)
// structurally impossible to commit without a second, independent
// signer. The PoC (ledger.py) cannot express this separation-of-duty;
// it is the single concrete capability this mapping adds over the PoC.
func (c *ProvenanceContract) ChangeParameter(
    ctx contractapi.TransactionContextInterface,
    param string, newValue float64,
) error {
    clientMSP, err := ctx.GetClientIdentity().GetMSPID()
    if err != nil {
        return err
    }
    curKey := "PARAM_CURRENT:" + param
    curBytes, _ := ctx.GetStub().GetState(curKey)
    var oldValue float64
    if curBytes != nil {
        var cur map[string]interface{}
        json.Unmarshal(curBytes, &cur)
        oldValue, _ = cur["value"].(float64)
    }

    change := ParamChange{
        Param: param, OldValue: oldValue, NewValue: newValue,
        OperatorMSP: clientMSP, Timestamp: time.Now().Unix(),
    }
    changeBytes, _ := json.Marshal(change)

    histKey, _ := ctx.GetStub().CreateCompositeKey("PARAM_HISTORY", []string{param, fmt.Sprint(time.Now().UnixNano())})
    if err := ctx.GetStub().PutState(histKey, changeBytes); err != nil {
        return err
    }

    curPayload, _ := json.Marshal(map[string]interface{}{
        "value": newValue, "changedBy": clientMSP, "timestamp": time.Now().Unix(),
    })
    return ctx.GetStub().PutState(curKey, curPayload)
}

// GetCurrentParams: read-only query, used by the off-chain auditor to
// cross-check a reported episode's claimed params against what
// governance actually approved (this is the check demo_tamper_detection.py
// performs against ledger.latest_params() in the PoC).
func (c *ProvenanceContract) GetCurrentParams(
    ctx contractapi.TransactionContextInterface,
) (map[string]float64, error) {
    iterator, err := ctx.GetStub().GetStateByPartialCompositeKey("PARAM_CURRENT", []string{})
    if err != nil {
        return nil, err
    }
    defer iterator.Close()

    result := map[string]float64{}
    for iterator.HasNext() {
        kv, err := iterator.Next()
        if err != nil {
            return nil, err
        }
        var v map[string]interface{}
        json.Unmarshal(kv.Value, &v)
        result[kv.Key] = v["value"].(float64)
    }
    return result, nil
}
```

---

## 5. What Fabric adds that the PoC explicitly cannot claim

State this plainly in Limitations — it is the honest boundary of the
PoC's contribution:

1. **No single point of write authority.** In `ledger.py`, one
   `OperatorDID` process appends entries; nothing stops that same
   process from *not* appending (silent withholding), even though it
   can't retroactively edit what's already appended without detection.
   Fabric's endorsement policy (e.g. 2-of-3 across Operator + Oversight
   + Auditor orgs) is what would make a withheld or single-party-forged
   episode commitment structurally impossible, not just detectable
   after the fact.
2. **No consensus / ordering service.** The PoC's `prev_entry_hash`
   chain proves *an* order was recorded, not that it's the order
   multiple independent parties agreed on. Fabric's ordering service
   (Raft) provides that.
3. **No peer replication.** The PoC's ledger is one JSON-serializable
   Python object in one process's memory. A real deployment replicates
   the ledger across peers from different organizations, so no single
   compromised host can make the ledger disappear or diverge silently.
4. **No measured performance under real network/consensus latency.**
   The `benchmark.py` overhead numbers in this PoC are single-machine,
   no-network timings — real Fabric transaction latency (endorsement +
   ordering + commit) is on the order of 100s of ms–low seconds per
   transaction depending on batch size, which is why Hyperledger
   Caliper exists as the standard benchmarking tool for this claim; not
   run here.

Suggested Limitations wording:

> The provenance layer is implemented as a local, cryptographically
> signed, hash-chained log (`ledger.py`) that exposes the same
> interface a Hyperledger Fabric chaincode would (Section [X], Table
> [Y]); it captures the append-only and signed-transaction properties
> central to the threat model but does not itself provide distributed
> consensus, peer replication, or a Caliper-benchmarked deployment.
> Full permissioned-ledger deployment, in particular an endorsement
> policy separating operator and oversight identities for governance
> transactions (Section [X]), is left as future work.

---

## 6. If time allows before camera-ready (Oct 22), not before submission (Sep 20)

Not attempted now given the Sep 20 deadline, but worth noting as a
concrete "future work" pointer with specifics (reviewers respond well
to specificity over "we will deploy this on blockchain"):

- Stand up Fabric's `test-network` (2 orgs, 1 channel) via the sample
  scripts in `fabric-samples`, deploy the chaincode above, and rerun
  `demo_tamper_detection.py`'s four scenarios against real transactions
  instead of the local ledger.
- Run Hyperledger Caliper against it for the latency/throughput numbers
  Section 5 (item 5, optional) of the brief mentions as a nice-to-have.
