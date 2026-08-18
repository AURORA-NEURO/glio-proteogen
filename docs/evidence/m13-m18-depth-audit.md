# M13–M18 depth audit

This receipt records the isolated M13–M18 hardening pass based on M26 commit
`e4ae7458`. It is additive evidence for the audit branch; it does not replace
the module-owned provisional receipts or freeze their ABI.

## Concrete fixes

- `24000202` restores `request` and `output` schema exports for the M13-06,
  M16-03, and M18-06 central CLI commands. The API and CLI now expose the same
  schema contract instead of rejecting valid contract names at the CLI parser.
- `daadd7d2` aligns stale M14-06 and M15-06 contract fixtures with the existing
  evidence-reference closure. The fixtures now exercise the required
  counter-evidence/evidence fields rather than relying on invalid construction.

The production change is 6 inserted Python lines. The application plus
regression-fixture diff is 27 insertions and 2 deletions across three files.
The standalone release verifier adds 124 Python lines, for an overall audit
diff of 151 insertions and 2 deletions across four Python files.

## Verification

- 1,054 non-release M13–M18 tests passed. This includes contract, runtime,
  interface, replay/tamper, privacy, evaluator, and adversarial tests. The
  module-owned release tests that require historical generated `dist-*`
  directories are kept separate; those directories are not source-controlled.
- All 47 available M13–M18 evaluator entrypoints passed, and all 47 matching
  benchmark entrypoints completed successfully.
- Aggregate branch-enabled coverage for the M13–M18 source scope is 97%:
  8,557 statements, 1,690 branches, and 91 partial branches, with the
  repository gate `fail-under=95` satisfied.
- Ruff is clean for the M13–M18 source scope and the changed contract tests.
  Strict MyPy is clean for the production CLI and the targeted M13–M18 source
  packages. Existing untyped test-fixture diagnostics remain outside the
  production strict-typing gate.
- `compileall` passed for the audited source/evaluator scope.

## Reproducible package receipt

Two builds were run with Python 3.12.13, Hatchling, `SOURCE_DATE_EPOCH=315532800`,
and external output directories. Wheel and sdist bytes were identical between
the builds. The exact tuple is recorded in
`release-evidence/m13_m18_depth_audit/package.json`.

- Wheel: 3,664,493 bytes,
  `643516db47037692f617882b126577fc6a9722161620704645908225d214d745`
- sdist: 4,203,436 bytes,
  `8612ccab0b9a7670d8538746d3505154a4efb015252446dab448962f98be9bf5`
- Isolated wheel installation and `python -I -c "import glio_proteogen"`
  passed.
- The receipt was checked against both external build directories with
  `uv run python tools/verify_m13_m18_depth_release.py
  release-evidence/m13_m18_depth_audit/package.json <build-one> <build-two>`;
  the verifier checks size, SHA-256, wheel integrity, and byte identity.

The receipt is intentionally tied to the audit base and build controls rather
than claiming that any downstream provisional module has become frozen.
