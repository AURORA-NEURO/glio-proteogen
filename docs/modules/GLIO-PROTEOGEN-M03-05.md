# GLIO-PROTEOGEN-M03-05 — artifact and contamination detector

M03-05 owns deterministic artifact-evidence reduction beneath Protein inference/ambiguity
control. It consumes an exact compact projection of a public M03-04 quality result plus a bounded,
content-addressed metadata evidence ledger. It emits only categorical artifact posteriors,
contamination flags, and a retain/review/exclude mask for the `complex_activity` workflow. Its
integer evidence scores are explicitly not calibrated probabilities.

## Locked behavior

1. Authorize approved configuration, identity/lineage, provenance, consent, quality, support, and
   intended use before traversing the artifact ledger. Withheld or unresolved authorization fails
   closed even when later content is hostile or malformed.
2. Consume the exact compact M03-04 projection. The receipt binds the M03-04 result, request,
   policy, configuration, M03-03 admission, protocol, search space, identity resolution, source
   manifest, projected sources, projected claims, and all eight quality metrics. Production
   validates caller-declared content-addressed self-consistency; it does not attest that an
   external issuer or upstream runtime is authentic. The executable gate separately constructs a
   genuine public M01-02 through M03-04 chain.
3. Admit exactly six evidence-unit kinds: `peptide_evidence`, `protein_group`,
   `ambiguity_class`, `proteoform_claim`, `control_group`, and `sample_context_binding`. Every
   unit cites only source and claim roles allowed for its kind and carries exactly the eight locked
   signal codes.
4. Score exactly `contaminant_reference_support`, `decoy_competition_failure`,
   `low_complexity_evidence`, `nonunique_mapping`, `batch_inconsistency`,
   `barcode_index_collision`, `technical_carryover`, and `sample_context_discordance`. Each signal
   has a locked applicability matrix over the six unit kinds; an out-of-domain signal is exactly
   `not_applicable` with zero counts.
5. For an observed signal with a positive denominator, derive the evidence score as
   `(supporting_count * 1_000_000 + evaluated_count // 2) // evaluated_count`. This is bounded
   half-up integer rounding. No binary-floating-point comparison, fitted coefficient, hidden
   classifier, caller-supplied rate, or probability interpretation is permitted.
6. Apply the reviewed thresholds exactly: below review is `clear`; review through immediately
   below exclusion is `suspected`; exclusion or higher is `detected`. Review cannot exceed
   exclusion. A required observed signal with zero denominator is `indeterminate`.
7. Preserve `missing`, `unsupported`, `not_applicable`, and zero-denominator `indeterminate`
   states. Missing or unsupported evidence never becomes a clear, negative, absent, or zero-risk
   finding. A required missing, unsupported, or unevaluable signal triggers abstention unless a
   quarantining artifact finding has higher precedence.
8. Reduce unit-level categorical artifact state with the exact precedence `detected` >
   `suspected` > `indeterminate` > `clear`. `detected` units are excluded, `suspected` or
   `indeterminate` units require review, and a unit is retained only when every required applicable
   signal is evaluable and clear.
9. Emit contamination flags only for applicable suspected or detected
   `contaminant_reference_support`, `barcode_index_collision`, or `technical_carryover` signals.
   An indeterminate contamination signal causes review and abstention but is not a contamination
   flag. Non-contamination artifact signals never become contamination claims.
10. Apply deterministic outcome precedence. An M03-04 rejected, quarantined, or abstained receipt,
    an unsupported compact shape, a receipt-ledger mismatch, an unsupported profile, or a
    role-incompatible unit cannot emit successful scores, posteriors, flags, or mask membership.
    Quarantine outranks a coexisting abstention when a suspected or detected artifact exists.
11. Select one and only one reviewed profile by applicability, assay-protocol version,
    controlled-vocabulary version, and unit-system version. The policy rejects overlapping match
    domains; labels cannot override governed versions or content digests.
12. Enforce installed ceilings for sources, claims, upstream claims, unit references, units,
    signal scores, contamination flags, profiles, approved-version domains, evidence references,
    35 findings, fact counts, the 4 MiB canonical request, and the 8 MiB canonical result. Exact
    maxima and every first excess are executable. The exact reachable result-evidence ceiling is
    18: seven controls, the policy,
    the active profile, eight thresholds, and the ledger.
13. Accept strict immutable JSON only: reject duplicate keys, scalar coercion, non-finite values,
    unknown fields or terms, missing required fields, stale derived values, contradictory nested
    state, and re-signed forgery. Semantic reordering of unordered collections preserves complete
    result equality and stable content digests.
14. Expose one operation across library, engine, service, plugin, API, and CLI:
    `detect_protein_inference_artifacts`, `POST /v1/modules/M03-05/artifacts`, and
    `protein-inference-artifacts detect REQUEST`. Exact installed schemas are exported through
    `GET /v1/contracts/M03-05/{name}/schema` and
    `protein-inference-artifacts export-schema NAME`.
15. Recover append-only. Corrected evidence, policy, or upstream quality creates a new immutable,
    content-addressed result with explicit supersession provenance. Prior results are never edited
    or silently promoted.
16. Project source, claim, and unit identities only as namespaced content-derived 64-hex aliases,
    and emit no direct identifier, raw identity token, observed peptide sequence, accession, protein
    presence or absence assertion, proteoform assignment, abundance, complex-activity score,
    subtype, proteotype, kinase state, fused-omics conclusion, treatment recommendation, or
    clinical decision.

The dossier permits classifier architectures, but no representative training set, calibration
set, transport validation, or reference labels are available at this gate. M03-05 therefore uses
the preregistered deterministic fallback. The field named `artifact_posteriors` is a categorical
evidence-state envelope retained from the required output vocabulary; it is not a Bayesian or
frequentist posterior probability and every score-bearing output carries
`score_is_calibrated_probability: false`.

## Evidence gate

Gate G1 contains exactly 56 executable cases in eight groups: genuine M01-02 through M03-04
handoff and graph closure; exact integer scoring and thresholds; contamination, exclusion masks,
and seeded acceptance; missingness, signal domains, profiles, and disagreement; safe-failure
precedence with zero ledger traversal; strict ingress, capacity, and hostile authorization;
canonical privacy and re-signed forgery resistance; and interfaces, recovery, evidence, and
benchmark timing.

The finite synthetic acceptance panel seeds every one of the eight signal classes at the exact
exclusion threshold or above and requires detection in 8 of 8 cases. Canonical clean units must
produce zero exclusions. These preregistered corpus criteria are software invariants, not estimates
of population sensitivity, specificity, classifier calibration, assay performance, biological
validity, or clinical utility.

The executable builder calls public M03-04, whose builder executes the genuine public M01-02,
M03-01, M03-02, and M03-03 chain. It then constructs only bounded synthetic counts and role-bound
metadata units before invoking public M03-05. Upstream construction occurs outside the
representative benchmark clock; only `detect_protein_inference_artifacts` is timed. The broad
ceiling is a regression tripwire, not performance qualification.

See the [module manifest](M03-05.manifest.md),
[evidence inventory](../evidence/M03-05.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M03-05.csv).
