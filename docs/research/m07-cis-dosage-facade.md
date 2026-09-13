# M07 local CPTAC-GBM cis-dosage evidence facade

Status: **implemented as a local compatibility boundary; intentionally not
mounted over HTTP**.

`m07-cptac-gbm-cis-dosage-cohort-evidence/1.0.0` delegates the exact
`cptac-gbm-cis-dosage/1.0.0` request, result, and replay contracts to an
operator-selected same-user local artifact. It adds responsibility and claim
metadata only; numerical output and digests pass through unchanged.

## Why M07-04

The governed M07-04 implementation currently copies scalar declarations,
replaces intervals with midpoints, labels that proxy supported, and reports a
zero-iteration optimizer. The delegated research model instead fits
fold-local Huber-IRLS models over the exact CPTAC GBM cohort:

- `RNA ~ intercept + CNV`;
- `Protein ~ intercept + CNV + RNA`;
- matched RNA-only and CNV-only protein comparators; and
- five outcome-blind patient-grouped folds with convergence, held-out evidence,
  sample-count, and direction-stability gates.

It emits gene-level cohort association evidence for the CNV-to-RNA,
RNA-to-protein conditional, CNV-to-protein conditional, indirect, and total
proxy coordinates. It accepts no patient measurements and emits no patient
score or posterior.

Only `GLIO-PROTEOGEN-M07-04` receives
`cohort_cis_dosage_evidence_substitution_only`, and only for replacing the
declaration/midpoint proxy in research workflows. M07-01, M07-02, M07-03,
M07-07, and M07-08 are evidence-source-only. M07-05 and M07-06 are out of
scope: observational propagated/buffered categories are not mechanistic
constraint integration, and fold diagnostics are not the governed uncertainty
taxonomy. Every responsibility retains
`module_responsibility_superseded=false`.

## Why HTTP remains absent

The exact source snapshots and derived artifact remain
`local_only_terms_unverified`. The underlying profile therefore fixes
`public_http_mounted=false`, and the facade repeats that state as a literal.
The query request contains an artifact content digest but no filesystem path;
only the local operator supplies the artifact path to the wrapper. Accepting an
arbitrary client path is forbidden.

The intended future route is recorded as
`/v2/research/modules/m07/cis-dosage-cohort-evidence`, but no adapter, router,
demo, catalog entry, or deployment operation exists. A route may be added only
after redistribution review admits a specific server-side artifact, its exact
content digest is bound into the facade profile, and cross-user authenticity is
addressed. Governed M07 contracts, routes, and schema digests remain unchanged.

Even after admission, the claim ceiling remains observational cohort evidence,
not causal mediation, patient inference, external calibration, prognosis,
treatment response, or clinical use.
