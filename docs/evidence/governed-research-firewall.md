# Governed M03/M04/M05 research firewall

## Purpose

The `glio_proteogen.research` package is an additive research workspace.  It
can perform bounded spectrum, target/decoy, quantification, protein-group, and
cohort experiments, but it is not a governed production ABI and it does not
promote those experiments into clinical, glioma, protein, proteoform, or
isoform claims.

M03, M04, and frozen M05-01 through M05-05 are a separate contract surface.
Their manifests intentionally cap behavior at declarations, raw-admission
metadata, deterministic aggregate quality, artifact/support/release metadata,
and PTM-localization protocol metadata.  The frozen result models carry
literal-false authority flags and the recursive `NonInferenceResultModel`
firewall rejects post-validation storage tampering.  This separation is a
safety property, not a missing implementation feature.

## Evidence covered by the regression layer

`tests/architecture/test_governed_research_firewall.py` checks the boundary at
four levels:

1. **Static import graph.** Every Python file beneath frozen M03/M04/M05
   contract and module directories, plus the central FastAPI and Typer
   composers, is parsed with `ast`. Direct and aliased imports of
   `glio_proteogen.research` (including submodules) fail the test.
2. **Fresh-process import isolation.** A clean interpreter imports the central
   FastAPI composer and asserts that no research execution module is loaded.
   This catches an accidental eager import that an in-process test could hide.
3. **Runtime route inventory.** The assembled central FastAPI application is
   inspected through a temporary event store. Every application-owned endpoint
   must be implemented by the adapter composer, and no route may expose
   research-only vocabulary such as spectrum, mzML, PSM, FDR, quantification,
   cohort, or protein-group execution.
4. **CLI callback inventory and manifest claims ceiling.** Root and nested
   Typer callbacks must stay in adapter-owned modules and cannot acquire a
   research operation name. The 20 owner-frozen M03/M04/M05 manifests must
   retain a claims ceiling, explicit non-inference language, and their own
   domain boundary. Provisional M05-06 and M05-08 manifests are deliberately
   excluded from the frozen set.

The existing contract suites remain authoritative for schema-level false
constants, forbidden biological fields, nested mutation firewalls, plugin
validation, and API/CLI parity. This layer adds the architecture check that
those suites cannot provide: it proves research computation has not leaked
into governed composition.

## Running the evidence

From the repository root:

```text
uv run --offline pytest -q -o addopts='' \
  tests/architecture/test_governed_research_firewall.py \
  tests/contract/test_m03_m04_non_inference_boundary.py \
  tests/contract/test_m05_non_inference_boundary.py
```

The route check closes its temporary event store through `TestClient`; no
database, network, cohort bytes, or research fixture is retained. A future
research endpoint must be added under the research namespace and receive its
own explicitly non-governed adapter. It must not be inserted into the central
M03/M04/M05 route or CLI inventories by convenience.

## Promotion gate

This firewall does **not** authorize widening M03/M04/M05 claims. Promotion of
real spectrum search, quantification, peptide-to-protein inference, cohort
evidence, or mechanism discovery requires a separate owner-confirmed dossier
slice and frozen ABI that names licensed inputs, reference/search versions,
FDR/quantification/group semantics, privacy/consent controls, safe abstention,
replay identity, validation data, and allowed claims. Until then, those
computations remain research-only and their evidence must stay outside the
governed route and result envelopes.
