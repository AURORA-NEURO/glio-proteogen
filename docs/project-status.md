# GLIO-PROTEOGEN project status

Status date: 2026-08-23

## Completion estimate

The current planning estimate uses the inferred 28-module by 8-cell delivery
matrix: 224 cells total.

| Measure | Complete | Total | Estimate |
| --- | ---: | ---: | ---: |
| Concrete implementation inventory | 214 | 224 | 95.5% |
| End-to-end artifact completeness | 214 | 224 | 95.5% |

These are engineering-completion estimates, not a claim of clinical readiness.
The remaining cells require upstream contract or ABI decisions that are not
present in this checkout. Implementing invented interfaces would make the
estimate less reliable, so those boundaries remain explicitly provisional.

Remaining provisional source IDs:

`M23_06`, `M24_01`, `M27_01`, `M28_01`, `M28_02`, `M28_03`, `M28_05`,
`M28_06`, `M28_07`, `M28_08`.

The artifact-closure cells on otherwise implemented surfaces are now closed for
M26-05, M26-06, and M27-03 with machine-readable evaluation, benchmark,
coverage, and package evidence. The remaining ten cells are opaque ABI
decisions, not missing test or deployment work.

## Current hardening evidence

- Thirty-eight concrete model APIs across M15, M23, M24, M25, M26, M27, and M28
  are composed in the canonical application; both the legacy API set and the
  expanded newer API set are at 100% aggregate branch-enabled coverage, with
  1,613 targeted model-matrix tests passing without deselected tests.
- The M26-05 observability bundle now passes 43 focused tests at 100% branch
  coverage; M26-06 security/access passes 45 focused tests at 100% branch
  coverage, with semantic replay recomputation
  and self-rehashed-result rejection executable in the evaluator. The M27-03
  release record now passes 31 focused tests at 100% branch coverage with
  two byte-identical external builds. The M24-08 evidence-gate bundle now passes 48 focused tests at 100% branch
  coverage across its contract, API, CLI, engine, plugin, and service; the
  M25-04 transport bundle passes 60 focused tests at 100%; the M25-06
  robustness bundle passes 35 focused tests at 100%; and the M27-03
  orchestration bundle passes 29 focused tests at 100%. The M27-07 change
  control and M27-08 retirement bundle passes 122 focused tests at 100% across
  the same deployed surfaces. The M27-05 observability and M27-06 security
  bundles pass 76 focused tests at 100% across their contracts, APIs, CLIs,
  engines, plugins, and services.
- The full contract suite passes 4,875 tests, and the M04-07 interface suite
  passes 38 tests after the canonical app gained an explicit route-level 4 MiB
  transport ceiling for that historical support route.
- The deployment suite now has 68 passing tests, including a subprocess smoke
  test for `python -m glio_proteogen.asgi`, readiness, a real M01-01 protocol
  route, deployed M15/M24/M25/M26/M27 schema and operation routes, route-specific
  body limits, and SQLite creation.
- The canonical production app includes M15-05, M23-01/02/03/04/05/07/08,
  M24-02/03/04/05/06/07/08, M25-01/02/03/04/05/06/07/08, M26-01 through M26-08,
  M27-03 through M27-08, and M28-04, preserving their contract-specific
  transport paths and limits, including body-reading APIs whose standalone
  middleware is not inherited when routers are composed.
- M15-05 also has an explicit `m15-05-longitudinal-evolution` CLI namespace;
  the pre-existing `longitudinal-evolution` namespace remains M14-05-compatible.
- The container CI smoke test builds the image, checks `/livez` and `/readyz`,
  validates the catalog digest and empty unmounted-route list, verifies the
  persistent database volume, and asserts the runtime user is not root.
- The deployment catalog recursively inspects included FastAPI routers and
  reports mounted model paths plus request/result byte ceilings, including the
  legacy lowercase M26-02 route prefix and the central M27-02 lineage lane.
- Dedicated 100% branch-coverage gates now cover 22 middleware-backed concrete
  API adapters across the M23, M24, M25, M26, and M27 surfaces; their route
  handlers now rely on the centralized request-size middleware rather than
  duplicated streaming readers. M23-02 also now preserves its declared 8 MiB
  verification-result ceiling at the middleware boundary.
- CI now runs the targeted model matrix with branch coverage and enforces the
  100% concrete-API gate plus full M24-08, M25-04, M25-06, M27-03, M27-05,
  M27-06, M27-07, and M27-08 contract/runtime bundle gates; the M27-05,
  M27-06, M27-07, and M27-08 bundles are enforced at 100%. The M23/M24/M25
  and M26/M27 API families also have dedicated 100% gates. A separate
  deployment-quality job enforces 100% branch coverage for
  `src/glio_proteogen/deployment.py`.
- The full CI and release-evidence jobs execute the complete repository test
  suite; the focused M03-04/M04-07 worker validation also passed 103 tests
  under two isolated xdist workers.
- A local four-worker repository run passed 12,045 tests with 15 expected skips
  and 80 warnings; pytest-benchmark cases were automatically disabled by xdist
  for that parallel verification.
- Ruff, mypy, Vulture, lockfile validation, Compose validation, secret scan,
  and dependency audit are green.

The Docker daemon was unavailable in the local Windows environment, so the
actual image runtime remains CI-verified rather than locally executed.
