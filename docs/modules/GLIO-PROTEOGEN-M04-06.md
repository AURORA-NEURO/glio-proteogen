# GLIO-PROTEOGEN-M04-06 - harmonization and normalization engine

M04-06 owns deterministic technical harmonization beneath Proteoform/isoform inference. It
consumes the complete replay-closed public M04-05 artifact result, its exact target receipt, and a bounded,
content-addressed ledger of caller-declared fixed-point support coordinates. Its owned analytical
outputs are only a harmonized analysis object and transformation manifest for the
`protein_rna_discordance` workflow; the result envelope also carries replay diagnostics and
governance metadata. A support coordinate is neither protein abundance nor a calibrated probability.

## Locked behavior

1. Authorize approved configuration, identity/lineage, provenance, consent, quality, support, and
   intended use before traversing the embedded M04-05 result, receipt, or support ledger. Withheld or
   unresolved authorization fails closed even when later accessors are hostile or malformed.
2. Consume and fully replay the exact M04-05 result before projecting its receipt. It binds the M04-05 result, request, policy,
   configuration, disposition, support, M04-04 quality receipt, artifact ledger, active profile,
   applicability, version domains, projected targets, all seven posterior digests per target, and
   exclusion-mask action. Production validates content-addressed self-consistency; it does not
   attest an external issuer or prove that an upstream runtime executed.
3. Close the support ledger over the artifact-result digest, artifact-receipt digest, exact target
   binding, one observation per projected target, all three protected invariant kinds, evidence,
   recorded time, and ledger digest. Every observation must preserve its M04-05 unit kind,
   aggregate target state, seven-posterior binding, contamination flags, exclusion state, and
   retain/review/exclude action. Request, policy, profile, ledger, target, anchor, group, level,
   invariant, stage, reviewer, and owned
   evidence identifiers
   are content-derived and match exactly `<namespace>.<64 lowercase hex>`; every reflected
   cross-reference reuses the same derived identifier.
4. Require exactly one level for each of the eight technical factors on every observation:
   `platform`, `batch`, `laboratory`, `build`, `depth`, `purity`, `composition`, and `preanalytic`.
   The reviewed profile contains exactly one ordered stage for every factor.
5. Enforce the M04-05 artifact firewall. Only retained targets with evaluable observed support may
   contribute to shift estimation or receive a correction. Targets held for review or exclusion
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
    distinct anchors in one biological context; composition fraction uses matched proteoform-candidate
    and spectral-feature anchors. A missing invariant abstains and an evaluable violation quarantines.
11. Select exactly one reviewed profile by applicability, assay-protocol version,
    specimen-processing version,
    controlled-vocabulary version, and unit-system version. Profile domains are pairwise disjoint;
    labels cannot override governed versions, stage structure, evidence, or content digests.
12. Apply deterministic safe-failure precedence. Quarantined or abstained M04-05 state
    propagates before ledger traversal. Unsupported shape, receipt-ledger mismatch, an artifact
    exclusion or review action, unsupported profile, inadequate control pairs, capped shifts,
    clipping, held-out failure, or invariant failure cannot emit an accepted result.
13. Preserve the complete embedded M04-05 receipt through its exact 64-target ceiling while
    limiting installed M04-06 processing to 32 targets and 32 observations. A cleared 33- through
    64-target upstream result is retained without truncation and produces a typed
    `UPSTREAM_SHAPE_UNSUPPORTED` abstention with no support ledger, analysis, or manifest. Enforce
    the remaining installed ceilings for stages, levels, shifts, estimation and validation
    anchors, invariants, invariant members, per-observation evidence, adjustments, profiles,
    approved versions, result evidence, findings, coordinates, the exact 2,000,000
    post-validation-residual ceiling, and the 4 MiB canonical request. The exact 32-target maximum,
    the genuine 33-target safe-failure boundary, and every owned first excess are executable.
14. Accept strict immutable JSON only: reject duplicate keys, scalar coercion, non-finite values,
    unknown fields or terms, missing required fields, stale derived values, contradictory nested
    state, and re-signed forgery. Semantic reordering preserves complete result equality and
    stable field-owned digests.
15. Expose one operation across library, engine, service, plugin, API, and CLI:
    `harmonize_proteoform_analysis`, `POST /v1/modules/M04-06/harmonization`, and
    `proteoform-harmonization harmonize REQUEST`. Exact installed schemas are exported
    through `GET /v1/contracts/M04-06/{name}/schema` and
    `proteoform-harmonization export-schema NAME`.
16. Recover append-only. Corrected support evidence, policy, profile, invariant, or upstream
    artifact result creates a new immutable content-addressed result with explicit supersession
    provenance. Prior results are never edited or silently promoted.
17. Emit no direct identifier, raw identity token, observed peptide sequence, accession, protein
    presence or absence assertion, proteoform assignment, protein abundance, calibrated
    probability, protein-RNA discordance score, subtype, proteotype, kinase state, fused-omics conclusion,
    treatment recommendation, or clinical decision.

No representative training set, calibration set, transport cohort, or biological reference label
is available at this gate. M04-06 therefore uses a preregistered exact lower-median fixed-point
fallback. No masked foundation model, autoencoder, cross-attention model, probabilistic estimator,
or learned parameter is executed.

## Evidence gate

Gate G1 contains exactly 56 executable cases in eight groups allocated `7/9/7/7/7/7/6/6`:
genuine M04-01 through M04-05 handoff and support-ledger closure; exact fixed-point normalization
for all eight factors plus sequential/cap/clamp boundaries; artifact firewall and typed-state
fidelity; held-out technical and protected biological invariants; safe failure, profiles, and
precedence; strict ingress, capacity, and hostile authorization; canonical privacy and re-signed
forgery resistance; and interfaces, recovery, evidence, and benchmark timing.

The conformant synthetic panel requires exact integer replay for all eight factors, reduction of
every held-out technical residual within tolerance, preservation of direction, rank, and composition
fraction, and zero adjustments for M04-05 review or excluded targets. Those criteria are software
invariants for a small finite corpus, not estimates of assay performance, batch removal in a
population, biological preservation, probability calibration, or clinical utility.

The executable builder calls public M04-05, whose builder executes the genuine public M04-01
through M04-04 chain. It then adds only bounded synthetic fixed-point support coordinates,
technical-factor levels, held-out anchors, and protected invariants before invoking public M04-06.
Upstream construction occurs outside the representative benchmark clock; only
`harmonize_proteoform_analysis` is timed. The representative installed-maximum workload contains
32 receipt targets and 32 support observations. It executes exactly one untimed warmup followed by
25 timed public calls under a 2-second mean and 3-second p95 regression ceiling. These latency
ceilings are regression tripwires, not performance qualification.

See the [module manifest](M04-06.manifest.md),
[evidence inventory](../evidence/M04-06.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M04-06.csv).
