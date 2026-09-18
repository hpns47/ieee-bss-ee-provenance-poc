# Figure captions and integration notes for BSS2026_Provenance_Paper.docx

Generated per `BSS2026_Final_Hardening_Brief.md` Priority 0/1. The docx
itself was not found on this machine, so nothing below has been inserted
into it -- paste directly into Section VII where noted.

## Fig. A — `fig_A_detection_vs_magnitude.png`

> Fig. A. Detection rate vs. attack magnitude for a Type-2 (parameter-level)
> attack on `change_mask`'s tau, expressed as a percentage of tau's
> baseline value. The proposed scheme detects 100% of tamper attempts at
> every magnitude tested (2%-75% of baseline); the naive sign-only-the-
> output baseline detects 0%, since it never inspects tau at all.

Per brief Section 1.3, add this interpretive sentence in the body text
(Section VII-C) near Fig. A, not just the caption:

> The flat 100%/0% curves are expected given hash-based verification is
> magnitude-invariant by construction (SHA-256's avalanche property
> guarantees any nonzero perturbation changes the hash); the informative
> result is that detection holds uniformly down to a 1% relative
> magnitude, not that it varies with attack size.

## Fig. B — `fig_B_localization_heatmap.png`

> Fig. B. Localization accuracy (%) by pipeline stage and attack type,
> averaged over all tested magnitudes and 40 seeds per combination.
> Type-2 (parameter-level) attacks are only naturally defined for
> `risk_index` and `change_mask` (the two stages with governance
> parameters); cells marked N/A reflect this, not a measurement gap.
> The proposed scheme localizes correctly 100% of the time across all 9
> stages under Type-3, demonstrating that localization is a systemic
> property of the multi-level design, not an artifact of the earlier
> single-stage (`change_mask`-only) example.

## Fig. C — `fig_C_type1_detection.png`

> Fig. C. Type-1 (data-level) scene-replay detection rate for the two
> data-acquisition stages (Sentinel-2, Sentinel-1). The proposed scheme
> detects 100% of simulated scene-ID substitutions; the naive baseline
> detects 0%, since it anchors only the final `change_mask` output and
> never inspects the data-acquisition commitment at all.

## Fig. D — `fig_D_latency_loglog.png`

> Fig. D. Pipeline compute time vs. hash+Merkle+sign overhead across 5
> simulated resolutions (100m-10m proxy), log-log scale. Anchoring
> overhead grows far more slowly than pipeline compute as resolution
> increases, because hashing touches only per-stage summaries, not every
> pixel.

## Fig. E — `fig_E_storage_growth.png`

> Fig. E. Projected on-chain storage (Merkle root + signature only) over a
> 1/2/5-year monitoring period at three monitoring cadences. Growth is
> O(episodes), independent of AOI size or resolution, since raw rasters
> never go on-chain.

## Fig. F — `fig_F_false_positive_rate.png` (new, Priority 1.1)

> Fig. F. False positive rate across four legitimate-activity scenarios
> (40 trials each). "Old episode, naive check" cross-checks an episode's
> recorded parameter against the ledger's *current* governance state; it
> false-flags 100% of legitimately-anchored older episodes as soon as any
> later, valid governance change is appended -- a genuine timestamp-
> scoping bug in the verification logic, not a hypothetical, found by this
> sweep. "Old episode, scoped check" is the fix (cross-checking against
> the governance state *as of the episode's own timestamp* instead), and
> restores 0% false positives. All other legitimate scenarios were 0%
> throughout.

Suggested Section VIII (Limitations) wording for this finding, since it
should be reported honestly rather than silently folded into "already
correct": *"An earlier version of the parameter cross-check compared an
episode's recorded governance parameters against the ledger's current
state rather than its state as of the episode's own timestamp, which
would falsely flag legitimately-anchored older episodes after any later
governance change; Section [ref fp_sweep.py] reports this as found and
fixed (`ledger.py`'s `params_as_of`), and the false-positive sweep now
reports 0% across all four tested legitimate scenarios."*

## Combined-attack finding (Priority 2, `combined_attack_results.json`)

Not assigned a figure (page budget) -- report as a sentence in Section
VII-C or VIII: a simultaneous Type-2 (risk_index) + Type-3 (change_mask)
attack in the same episode is detected 100% of the time (root mismatch),
but the *original* single-stage localizer (`find_mismatched_stage`)
would only ever have named one of the two tampered stages (confirmed:
40/40 trials), since it stops at the first divergence in stage order.
The fix, `find_all_mismatched_stages` (added to `merkle.py`), correctly
names both tampered stages in all 40/40 trials. Worth stating explicitly
as a found-and-fixed limitation rather than an assumed property.

## Section VII-C replacement paragraph (per brief 0.1.1)

> Across 64 attack_type x target_stage x magnitude combinations (40
> trials each, N=2560 episodes total; see Fig. A-C), the proposed scheme
> achieved 100% detection and 100% localization accuracy across all 9
> pipeline stages, versus the naive baseline's 0% detection rate for
> Type-2 (parameter-level) tampering and its structural inability to
> localize even the Type-3 tampering it does catch. A complementary
> false-positive sweep (Fig. F, N=160 trials across 4 legitimate-activity
> scenarios) found and fixed a timestamp-scoping bug in the parameter
> cross-check (Section VIII), after which false positives were 0% across
> all tested legitimate scenarios. A combined-attack test further showed
> that simultaneous multi-stage tampering is always detected, and, after
> a corresponding localization fix, always fully localized to both
> affected stages.
