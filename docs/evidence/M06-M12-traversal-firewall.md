# M06-M12 plain-value traversal firewall

This additive hardening closes a transport-boundary denial-of-service gap in
five existing M06-M12 engines. Their replay and canonicalization paths accept
JSON-like caller values, so validation must reject hostile nesting and
container sizes before recursive materialization. The change preserves every
request, result, status, digest, and estimator field in the existing ABI; it
does not add biological, clinical, protein, proteoform, isoform, glioma,
treatment, or kinase inference.

## Enforced limits

Each affected engine applies the same fail-closed limits while converting
plain values for validation and replay:

- maximum nesting depth: **64**
- maximum mapping items per mapping: **512**
- maximum sequence items per sequence: **4,096**
- maximum aggregate visited nodes: **100,000**

The limits cover dictionaries, lists, and tuples and retain the pre-existing
rejection of non-string mapping keys and arbitrary mapping objects. A limit
violation raises the module's existing typed input/validation error, so API,
CLI, plugin, and service callers receive sanitized failure rather than a
`RecursionError` or unbounded traversal.

## Scope

The affected engines are M06-01 formal state schema, M06-04 probabilistic
advanced estimator, M07-04 probabilistic advanced estimator, M11-07
plausibility adjudicator, and M12-03 mechanistic feature constructor. The
firewall is private transport validation; no contract schema or scientific
claim ceiling changed.

## Evidence

The focused lifecycle/runtime selection passes **45 tests**, including
70-level nested dictionaries and 4,097-item sequences for every affected
engine. The broader contract, hardening, evaluator, adversarial, and
interface selection passes **115 tests**. Source Ruff check/format and strict
MyPy pass for all five engines. These tests exercise the new rejection path
without depending on raw scientific data or inferring caller-declared values.
