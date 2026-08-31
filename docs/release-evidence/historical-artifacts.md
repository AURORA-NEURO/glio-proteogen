# Historical release bundles

The source checkout does not contain the immutable package directories used by
some early release receipts. The following directories are external evidence
inputs, not replacements for the current `dist/` build:

`dist-m10-03`, `dist-m11-04`, `dist-m11-06`, `dist-m11-07`, `dist-m11_08`,
`dist-m12-04`, `dist-m12-05`, `dist-m12-07`, `dist-m12-08`, `dist-m13-02`,
`dist-m13-04`, `dist-m13-05`, `dist-m14-04`, `dist-m14-06`, and `dist-m18-07`.

Place the exact receipt-matching directories at the repository root to run the
acceptance tests marked `historical_artifact`. When they are absent, those
acceptance tests are individually reported as skipped with their missing directory name;
negative verifier tests still run. The current package receipts are verified
independently from `dist/`.

Three checked-in JSON receipts are also immutable, point-in-time historical
evidence rather than hashes for the next candidate build:

- `release-evidence/m26_08/package.json`;
- `docs/evidence/research-foundation/package.json`;
- `docs/evidence/research_public_proteomics/package.json`.

Their internal claims, fixture bindings, reproducibility records, and member
inventories remain release gates. After the workflow builds the current wheel
and sdist twice, `tools/current_candidate_receipt.py` creates the separate
`evidence/current-candidate-receipt.json`. M26-08 and both research semantic
verifiers explicitly consume that same candidate receipt to bind current bytes;
the historical files are never rewritten or represented as current artifacts.
