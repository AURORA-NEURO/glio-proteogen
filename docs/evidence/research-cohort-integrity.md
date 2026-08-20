# Research cohort provenance-integrity evidence

This research-only hardening closes a replay/provenance gap in the cohort evidence path. A
`CohortSourceManifest` for an external PDC sample is now bound to the exact
`PdcSourceReceipt` carried by the run request. Validation compares the caller-declared source
ID, catalog-response SHA-256, file name, file locator, study ID, and receipt digest. A manifest
that preserves the source bytes and receipt digest but forges any of those identity fields is
rejected before matrix, QC, or evidence aggregation.

The change remains additive and research-only. It does not authenticate the public-data issuer,
download raw cohort bytes, promote the research namespace into a governed module, or make
protein/proteoform/isoform, clinical, glioma, treatment, or mechanistic claims. Existing M03/M04
non-inference contracts are unchanged.

## Executable closure

- `369` research tests pass without coverage instrumentation.
- The cohort evaluator executes `10/10` locked scenarios, including
  `pdc_manifest_receipt_identity`.
- Adversarial unit coverage rejects forged source ID, catalog-response digest, and PDC file-name
  bindings; the existing replay and tamper checks remain active.
- Current consolidated research namespace branch coverage is `95.61%` (`3,443` statements,
  `1,344` branches, `106` missed statements, `104` missed branch arcs, fail-under `95`).
- `tools/verify_research_pipeline.py` passes after the evaluator and cohort fixture digests are
  refreshed.

The evidence is a computation/replay receipt, not scientific validation of the external study.
