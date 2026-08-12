# M02-04: quality metric computation

M02-04 converts already-authorized, typed peptide-identification QC observations into a
deterministic quality profile. The v1 profile is intentionally narrow: identification coverage,
target-decoy FDR, precursor mass-error accuracy, identification completeness, control-material
recovery, and sample-context agreement. Every metric, threshold, requiredness decision, and
evidence link is explicit and versioned.

## Computation boundary

1. Require consent, resolved identity/lineage, and accepted configuration, provenance, quality,
   support, and intended-use controls before traversing observations.
2. Bind the request to one assay profile and one policy containing exactly the six public metric
   thresholds. Unknown metrics, missing controls, duplicate observations, and silent coercions are
   rejected.
3. Preserve `observed`, `missing`, `censored`, `not_applicable`, and `unsupported` as distinct
   states. Censored observations retain only their declared upper bound; no non-observed value is
   converted to zero, absence, or a biological finding.
4. Compare observed scalars and booleans with the policy's inclusive pass and warning bounds.
   Coverage and completeness are lower-bounded; FDR and mass error are upper-bounded; control
   recovery must remain within its reviewed range; sample context requires an explicit match.
5. Quarantine any failed metric and any required metric that is not evaluable. An optional
   censored or not-applicable metric remains visible as `not_evaluable` without manufacturing a
   pass or failure.
6. Emit only a canonical typed quality profile with metric provenance, support, uncertainty,
   evidence, limitations, and parent target `protein_subtype`.

The implementation is a stateless deterministic framework. It does not estimate identifications
or FDR from spectra, parse raw files, correct observations, infer protein subtype or proteotype,
own kinase activity, fuse omics, or recommend treatment.

## Evidence gate

Gate G1 uses eight synthetic reference scenarios: one conformant six-metric profile; low
identification coverage; excessive target-decoy FDR; failed precursor mass-error accuracy;
missing required observations; an optional censored/not-applicable observation; control-material
or sample-context mismatch; and consent denial before observation traversal. Replay also checks
full-result order determinism and recursively scans the output boundary for raw or prohibited
scientific/clinical claims. One broad batch benchmark is a regression tripwire with a generous
budget.

These checks establish deterministic behavior for synthetic inputs and one pinned reference
policy. They do not establish assay validity, identification correctness, FDR calibration,
biological validity, protein subtype accuracy, cohort transportability, clinical readiness, or
treatment suitability.

See the [module manifest](M02-04.manifest.md),
[evidence inventory](../evidence/M02-04.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M02-04.csv).
