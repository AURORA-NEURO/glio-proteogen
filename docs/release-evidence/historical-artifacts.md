# Historical release bundles

The source checkout does not contain the immutable package directories used by
some early release receipts. The following directories are external evidence
inputs, not replacements for the current `dist/` build:

`dist-m10-03`, `dist-m11-04`, `dist-m11_08`, `dist-m12-04`, `dist-m12-05`,
`dist-m12-08`, `dist-m13-02`, `dist-m13-04`, `dist-m13-05`, `dist-m14-04`,
`dist-m14-06`, and `dist-m18-07`.

Place the exact receipt-matching directories at the repository root to run the
acceptance tests marked `historical_artifact`. When they are absent, those
acceptance tests are reported as skipped with the missing directory names;
negative verifier tests still run. The current package receipts are verified
independently from `dist/`.
