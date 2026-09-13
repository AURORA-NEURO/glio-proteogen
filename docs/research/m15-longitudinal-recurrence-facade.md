# M15 longitudinal-recurrence evidence facade

`m15-longitudinal-recurrence-protein-concordance-evidence/1.0.0` is an
additive research-only compatibility surface. It delegates every numerical
operation to `kncc-gbm-longitudinal-concordance/1.0.0`; it is not a new model
and does not modify any governed M15 schema, digest, route, or result.

The delegated engine was fitted from 104 strict PDC000514 primary/recurrent
GBM pairs. It performs bound-aware robust inference, propagates measurement
and fitted-coefficient uncertainty, exposes source-processing and driver
ablations, and can run exact Huber-PELT segmentation for sufficiently long
series. The facade passes the exact request and result contracts through, so
the delegated request, profile, result, and replay digests remain authoritative.
The facade profile adds a separate digest binding the M15 responsibility map
and claim ceiling.

## HTTP surface

The central application mounts:

- `GET /v2/research/modules/m15/longitudinal-recurrence-proteotype/profile`
- `GET /v2/research/modules/m15/longitudinal-recurrence-proteotype/demo`
- `POST /v2/research/modules/m15/longitudinal-recurrence-proteotype/analyze`
- `POST /v2/research/modules/m15/longitudinal-recurrence-proteotype/verify`

The profile, demo, analysis, and replay responses carry both
`X-GLIO-Facade-Profile-Digest` and the delegated
`X-GLIO-Profile-Digest`. Analysis and replay retain the delegated request and
result digest headers. The v2 deployment catalog derives all four operations
from the mounted routes and publishes the same transport bounds as the
underlying longitudinal engine.

## Responsibility and claim boundary

The fitted transition coordinate may replace only a synthetic,
caller-declared, or digest-derived score beneath M15-05. Other M15 duties may
cite the receipt as evidence where the facade profile says so, but none is
superseded.

The output is same-source-cohort protein transition concordance. It is not:

- a prediction of future recurrence, outcome, or survival;
- a clonal-evolution, network-state, pathway-activity, or causal-mechanism
  posterior;
- a treatment perturbation or counterfactual simulation;
- external or cross-cohort validation;
- a clinical class, recommendation, or governed M15 replacement.

Driver and processing ablations describe sensitivity of the fitted model, not
interventions. Research use, non-prescriptive behavior, abstention gates, and
the delegated assay-compatibility requirements remain mandatory.

See [longitudinal GBM protein concordance](longitudinal-gbm-protein-concordance.md)
for the source model and evaluation details.
