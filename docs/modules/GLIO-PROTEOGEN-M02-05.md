# M02-05: artifact and contamination detection

M02-05 evaluates already-authorized, typed peptide-identification QC signals under one reviewed
detector profile. It emits bounded configured posteriors, technical flags, and a deduplicated
exclusion mask for seven closed classes: technical artifact, contamination, barcode/index error,
batch effect, low complexity, mapping artifact, and context-specific false positive. The parent
target `protein_subtype` is workflow context only; this module does not infer a subtype.

## Detection boundary

1. Require consent, resolved identity/lineage, and accepted configuration, provenance, quality,
   support, and intended-use controls before traversing signals.
2. Bind the request to the pinned identification-artifact profile, policy, and explicit rules.
   Every rule is scoped to one signal and artifact class.
3. Preserve `observed`, `missing`, `not_applicable`, and `unsupported` as distinct states. A
   required missing/not-applicable signal or any unsupported/OOD signal is not evaluable and
   quarantines its target for review; it never becomes a clear or negative finding.
4. Evaluate observed signals deterministically. Triggered rules retain the maximum configured
   posterior; independent values are not added or presented as learned probabilities.
5. Apply inclusive review and exclusion thresholds. Exclusion requires both threshold
   satisfaction and exclusion eligibility; otherwise a sufficiently elevated posterior requires
   review.
6. Build the exclusion mask from unique target identifiers. Several artifact classes can flag one
   target without duplicating it in the mask.
7. Emit only the typed artifact result, bounded uncertainty, support, provenance, evidence, and
   limitations. Inputs and upstream decisions remain immutable.

This is a compact, stateless, deterministic framework. It does not parse spectra, estimate false
discovery rates, repair measurements, infer biology, own KINOPHOS kinase state, fuse omics,
recommend treatment, or treat absence of evidence as evidence of absence.

## Evidence gate

Gate G1 uses exactly eight synthetic, non-clinical scenarios: a conformant clean target; a compact
batch seeding all seven artifact classes; a clean batch with zero false exclusions; required
missing and unsupported/OOD signals; a multi-class target proving mask deduplication; a reordered
request proving full-output determinism; and consent denial before hostile signal traversal. A
recursive boundary check excludes raw assay content and prohibited scientific or clinical claims.
One broad batch benchmark uses a generous 500 ms regression budget.

The locked seeded-class criterion is sensitivity at least `0.95` (expected `7/7 = 1.0`) and the
clean-target false-exclusion ceiling is `0.05` (expected `0.0`). These are deterministic regression
criteria for one small fixture. They do not establish calibration, assay validity, clinical
sensitivity or specificity, cohort transportability, subtype accuracy, or clinical readiness.

See the [module manifest](M02-05.manifest.md),
[evidence inventory](../evidence/M02-05.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M02-05.csv).
