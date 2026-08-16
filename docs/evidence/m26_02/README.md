# M26-02 evidence index

This directory records the release evidence for the provisional data/model/version
lineage service. The executable evaluator is `evals/m26_02/evaluate.py`; its frozen
fixture and scenario digest is recorded in `evaluation.json`. The benchmark wrapper
is `benchmarks/m26_02_lineage.py`; locked timing is recorded in `benchmark.json`.

The release package evidence is recorded in `package.json` after the wheel and sdist
have been built twice, hashed, and imported from an isolated target. The independent
standard-library verifier is `tools/verify_m26_02_release.py` and checks that the
evidence, source module set, and distribution hashes agree.

Evidence is intentionally explicit about the M26-01 boundary: no M26-01 runtime
service is imported because only its caller-declared media boundary is available in
this provisional lane.
