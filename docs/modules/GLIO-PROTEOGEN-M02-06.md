# M02-06: identification harmonization and normalization

M02-06 transforms authorized peptide-identification abundance observations into a harmonized
analysis object and an exact transformation manifest. Its eight-stage profile is closed over
`platform`, `batch`, `laboratory`, `build`, `depth`, `purity`, `composition`, and `preanalytic`
effects. Corrections are deterministic, additive on `log2_abundance`, control-derived, bounded,
and accepted only when technical spread is reduced without breaking declared biological direction
or rank controls.

The module is deliberately specific to the C02 identification-QC chain. A request embeds the exact
M02-01 through M02-05 prerequisite results. In particular, the M02-05 exclusion mask is an
authoritative firewall: excluded targets cannot train a level shift, cannot receive a repaired
value, and remain explicitly `excluded` in the result. This is not a generic normalization
platform and it does not reinterpret an upstream decision.

## Harmonization boundary

1. Authorize consent, identity/lineage, configuration, provenance, quality, support, and intended
   use before traversing prerequisites or observations.
2. Verify the exact, digest-bound M02-01 through M02-05 result chain. A failed or unsupported
   prerequisite yields an explicit abstention/review outcome; it never becomes an apparently valid
   harmonized object.
3. Require one ordered stage for each of the eight technical factors and a common additive unit.
   Each stage estimates non-reference shifts only from declared control samples and features that
   are observed, eligible, and not excluded upstream.
4. Preserve `missing`, `censored`, `not_applicable`, `unsupported`, and `excluded` as separate
   states. None is imputed, treated as zero, or converted into a biological negative. Censoring
   bounds remain attached to censored values.
5. Apply each evaluable shift in manifest order and cap its magnitude at the reviewed policy
   limit. An insufficient-control stage abstains; a capped stage quarantines. Neither is silently
   accepted.
6. Compare pre/post level spread for every technical factor. Acceptance requires actual reduction
   to the configured tolerance, not merely successful arithmetic.
7. Re-evaluate protected biological controls after all eight stages. Direction and rank must keep
   their non-zero sign and remain within tolerance; a failure quarantines the object.
8. Emit exact stage adjustments, input/output digests, prerequisite receipts, diagnostics,
   uncertainty, provenance, evidence, and limitations. Upstream artifacts and caller inputs remain
   immutable.

The parent target `protein_subtype` is workflow context only. M02-06 does not infer a subtype,
proteotype, kinase activity, identity, consent, mutation, treatment response, or recommendation;
it does not fuse omics or resolve transcript-protein disagreement. No learned encoder,
autoencoder, database, event store, or external reference is used at runtime. The implementation
may reuse the already-verified pure additive normalization kernel where its semantics match, while
the C02 contracts, prerequisite closure, exclusion firewall, diagnostics, and evidence are unique
to this module.

## Evidence gate

Gate G1 locks ten synthetic, non-clinical scenarios. The conformant scenario exercises all eight
technical factors, proves positive pre/post spread reduction for each, and preserves one direction
and one rank control. Separate cases prove typed non-observed-state fidelity; the M02-05 exclusion
firewall; inadequate-control abstention; a capped-shift quarantine; direction and rank
quarantines; upstream
prerequisite abstention; canonical full-output equality under semantic reordering; and consent
denial before hostile observation traversal. A recursive boundary check rejects raw assay content
and scientific or clinical ownership leakage. One broad public-engine benchmark covers 128
observations, eight stages, and both invariant kinds with a generous 500 ms regression tripwire.
The prerequisite objects are not hand-built stand-ins: the fixture calls the public M02-01 through
M02-05 implementations, and the detector evaluates every target admitted to harmonization.

These checks establish deterministic behavior for a small synthetic fixture and a pinned policy.
They do not establish a learned model, uncertainty calibration, biological validity, assay
qualification, cohort transportability, subtype performance, clinical validity, or clinical
readiness.

See the [module manifest](M02-06.manifest.md),
[evidence inventory](../evidence/M02-06.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M02-06.csv).
