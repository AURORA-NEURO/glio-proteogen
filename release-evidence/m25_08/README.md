# M25-08 release evidence

This directory records the provisional M25-08 evidence-gate and release
adjudicator, locked nine-scenario matrix, four adversarial cases,
branch-enabled coverage, independent release verifier, and reproducible
package records. Authority is dossier SHA-256
`0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181`, exact
slice `8984-9024`. The immediate stack parent is published M25-07
`883527648b51272cbc5d2f3e829ff83f3d945329`; M25-06 remains media-only until
its ABI is frozen.

Replay verification is mandatory and semantic. The verifier regenerates the
complete adjudication from the bound request and compares the canonical result
envelope; `replay=False` is rejected. Evaluator and interface tests include a
self-rehashed support-decision mutation, proving that a forged release payload
cannot bypass regeneration by repairing its embedded digest.
