# GLIO-PROTEOGEN-M03-06 - protein-inference support harmonization

M03-06 owns deterministic technical harmonization beneath Protein inference/ambiguity control. It
consumes an exact compact projection of a public M03-05 artifact result plus a bounded,
content-addressed ledger of caller-declared fixed-point support coordinates. It emits only a
replayable technical transformation and diagnostics for the `complex_activity` workflow. A support
coordinate is neither protein abundance nor a calibrated probability.

## Locked behavior

1. Authorize approved configuration, identity/lineage, provenance, consent, quality, support, and
   intended use before traversing the compact M03-05 receipt or support ledger. Withheld or
   unresolved authorization fails closed even when later accessors are hostile or malformed.
2. Consume the exact compact M03-05 projection. It binds the M03-05 result, request, policy,
   configuration, disposition, support, M03-04 quality receipt, artifact ledger, active profile,
   applicability, version domains, projected units, signal-score digests, posterior digests, and
   exclusion-mask action. Production validates content-addressed self-consistency; it does not
   attest an external issuer or prove that an upstream runtime executed.
3. Close the support ledger over the artifact-result digest, artifact-receipt digest, exact unit
   binding, one observation per projected unit, all three protected invariant kinds, evidence,
   recorded time, and ledger digest. Every observation must preserve its M03-05 unit kind,
   posterior state, signal-score digest, posterior digest, and retain/review/exclude action.
   Request, policy, profile, ledger, unit, anchor, group, level, invariant, stage, reviewer, and owned
   evidence identifiers
   are content-derived and match exactly `<namespace>.<64 lowercase hex>`; every reflected
   cross-reference reuses the same derived identifier.
4. Require exactly one level for each of the eight technical factors on every observation:
   `platform`, `batch`, `laboratory`, `build`, `depth`, `purity`, `composition`, and `preanalytic`.
   The reviewed profile contains exactly one ordered stage for every factor.
5. Enforce the M03-05 artifact firewall. Only retained units with evaluable observed support may
   contribute to shift estimation or receive a correction. Units held for review or exclusion
   never train a shift, receive an adjustment, or emerge as repaired support.
6. Preserve `observed`, `missing`, `censored`, `not_applicable`, and `unsupported` as distinct
   states. Missing or unsupported support is not zero; a censored coordinate retains its exact
   upper bound; observed integer zero remains a valid numeric coordinate.
7. For every non-reference technical level, derive the signed correction from the exact lower
   median of paired estimation-anchor differences against the reviewed reference level. All
   arithmetic is bounded integer arithmetic on the 1,000,000 support-coordinate scale. No
   binary-floating-point estimate, caller-supplied shift, fitted coefficient, or hidden model is
   trusted.
8. Apply stages sequentially in the declared order. Each stage binds its pre-stage coordinates,
   derived level shifts, applied adjustments, and post-stage coordinates. A shift reaching its
   reviewed cap or a coordinate reaching the fixed-point boundary is explicit and quarantines; it
   is never silently accepted.
9. Keep estimation and validation anchors unique and disjoint. Each technical diagnostic compares
   the held-out pre/post level residual and accepts only actual reduction to the configured
   tolerance. Insufficient pairs are not evaluable; an evaluable unreduced effect quarantines.
10. Replay the three protected invariant kinds before and after the complete eight-stage pipeline.
    Support direction uses matched anchors across distinct biological groups; support rank uses
    distinct anchors in one biological context; ambiguity fraction uses matched ambiguity-class
    and protein-group anchors. A missing invariant abstains and an evaluable violation quarantines.
11. Select exactly one reviewed profile by applicability, assay-protocol version,
    controlled-vocabulary version, and unit-system version. Profile domains are pairwise disjoint;
    labels cannot override governed versions, stage structure, evidence, or content digests.
12. Apply deterministic safe-failure precedence. Rejected, quarantined, or abstained M03-05 state
    propagates before ledger traversal. Unsupported shape, receipt-ledger mismatch, an artifact
    exclusion or review action, unsupported profile, inadequate control pairs, capped shifts,
    clipping, held-out failure, or invariant failure cannot emit an accepted result.
13. Enforce installed ceilings for stages, units, observations, levels, shifts, estimation and
    validation anchors, invariants, invariant members, per-observation evidence, adjustments,
    profiles, approved versions, result evidence, findings, coordinates, the exact 2,000,000
    post-validation-residual ceiling, and the 4 MiB canonical request. Exact maxima and every
    first excess are executable.
14. Accept strict immutable JSON only: reject duplicate keys, scalar coercion, non-finite values,
    unknown fields or terms, missing required fields, stale derived values, contradictory nested
    state, and re-signed forgery. Semantic reordering preserves complete result equality and
    stable field-owned digests.
15. Expose one operation across library, engine, service, plugin, API, and CLI:
    `harmonize_protein_inference_support`, `POST /v1/modules/M03-06/harmonization`, and
    `protein-inference-harmonization harmonize REQUEST`. Exact installed schemas are exported
    through `GET /v1/contracts/M03-06/{name}/schema` and
    `protein-inference-harmonization export-schema NAME`.
16. Recover append-only. Corrected support evidence, policy, profile, invariant, or upstream
    artifact result creates a new immutable content-addressed result with explicit supersession
    provenance. Prior results are never edited or silently promoted.
17. Emit no direct identifier, raw identity token, observed peptide sequence, accession, protein
    presence or absence assertion, proteoform assignment, protein abundance, calibrated
    probability, complex-activity score, subtype, proteotype, kinase state, fused-omics conclusion,
    treatment recommendation, or clinical decision.

No representative training set, calibration set, transport cohort, or biological reference label
is available at this gate. M03-06 therefore uses a preregistered exact lower-median fixed-point
fallback. No masked foundation model, autoencoder, cross-attention model, probabilistic estimator,
or learned parameter is executed.

## Evidence gate

Gate G1 contains exactly 56 executable cases in eight groups allocated `7/9/7/7/7/7/6/6`:
genuine M01-02 through M03-05 handoff and support-ledger closure; exact fixed-point normalization
for all eight factors plus sequential/cap/clamp boundaries; artifact firewall and typed-state
fidelity; held-out technical and protected biological invariants; safe failure, profiles, and
precedence; strict ingress, capacity, and hostile authorization; canonical privacy and re-signed
forgery resistance; and interfaces, recovery, evidence, and benchmark timing.

The conformant synthetic panel requires exact integer replay for all eight factors, reduction of
every held-out technical residual within tolerance, preservation of direction, rank, and ambiguity
fraction, and zero adjustments for M03-05 review or excluded units. Those criteria are software
invariants for a small finite corpus, not estimates of assay performance, batch removal in a
population, biological preservation, probability calibration, or clinical utility.

The executable builder calls public M03-05, whose builder executes the genuine public M01-02
through M03-04 chain. It then adds only bounded synthetic fixed-point support coordinates,
technical-factor levels, held-out anchors, and protected invariants before invoking public M03-06.
Upstream construction occurs outside the representative benchmark clock; only
`harmonize_protein_inference_support` is timed. The broad latency ceiling is a regression tripwire,
not performance qualification.

See the [module manifest](M03-06.manifest.md),
[evidence inventory](../evidence/M03-06.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M03-06.csv).
