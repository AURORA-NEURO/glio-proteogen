# M24-02 release evidence

This directory freezes the evaluator, locked benchmark, scoped branch coverage,
release verifier, and package records for the provisional M24-02 synthetic truth
simulation generator. Values are generated from the committed source and must
be verified with `tools/verify_m2402_release.py` before publication.

The module is reachable through the canonical FastAPI schema/module routes and
the `m2402-synthetic-truth` Typer group. Central registration is covered by the
integration suite, while request/result ceilings remain enforced at the
transport boundary.

The M24-01 relationship is media-only and caller-declared. No unpublished
upstream runtime ABI is imported. The implementation emits benchmark material,
not a biomarker panel or biological truth claim.
