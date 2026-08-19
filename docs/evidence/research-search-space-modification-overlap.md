# Research search-space modification overlap evidence

This research-only hardening closes a provenance gap in the variable-modification search-space
receipt. The previous receipt bound modified target and decoy variant counts, but did not state
whether modified target/decoy variants collided or how many unique modified peptides were actually
searched. That omission made collision-sensitive FDR review and replay evidence incomplete even
though the canonical receipt digest was valid.

The receipt projection now binds two additional derived quantities:

- `modified_target_decoy_overlap_peptides`: the cardinality of the modified target/decoy set
  intersection;
- `modified_peptide_count`: the cardinality of the modified target/decoy union.

The verifier enforces both the overlap upper bound and the union identity, and includes both values
in the canonical digest. A self-rehashed receipt with a forged collision count or unique count is
rejected. The evaluator also requires a positive modified collision and the same union identity.
This is additive research evidence only; it does not widen any governed M03/M04 ABI or make
clinical, glioma, protein, proteoform, or isoform claims.

Validation performed on the current main base:

- 356 research tests pass, including search-space and modification adversarial tests;
- locked variable-modification evaluator: 4/4 scenarios pass;
- scoped research branch coverage: 95.59% (3,362 statements, 1,304 branches);
- Ruff, strict MyPy, format, and compileall pass on touched source/tests/evaluator files;
- two `SOURCE_DATE_EPOCH=315532800` builds are byte-identical: wheel 3,877,919 bytes,
  SHA-256 `a7ce4a09d898f4d28d11d7a4a3185fbc48fe892aaaa7f760725edd81a15d0e1f`; sdist
  4,556,223 bytes, SHA-256 `6ca20f3cf2c510510d1e267a7e32b2022761927b2556bfd5a1f2d8b464caa1c1`.
