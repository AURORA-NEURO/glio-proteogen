# Protein-group quantification integrity

This research-only hardening closes the boundary between inferred protein-group
membership and matched-ion quantification. It does not change a governed module
ABI and does not claim calibrated protein abundance, protein/proteoform identity,
glioma biology, mechanism, or clinical validity.

## Closed partition

`quantify_protein_groups` materializes the caller's `ProteinGroup` sequence before
computing signal. It rejects empty or malformed memberships, repeated accessions,
accession overlap, repeated peptides, and peptide overlap across groups. The latter
is important because a peptide mapped into two separately supplied groups would
otherwise contribute to both group totals. The canonical `infer_protein_groups`
output is already disjoint; this validation also protects direct library callers
and future adapters from bypassing that invariant.

Intensity and PSM-count mappings are closed against the union of declared group
peptides. An extra key is rejected rather than ignored. Missing keys remain valid:
they represent absent observations and are scored as zero signal/zero support under
the existing no-imputation policy. Explicit zero and absent values therefore retain
their equivalent estimate semantics while producing different input receipts.

## Replay-bound evidence receipt

Every generated `ProteinGroupQuant` now carries an
`protein-group-quantification-input-1` SHA-256 digest over:

- ordered group accession, unique-peptide, and shared-peptide membership;
- each declared peptide's present-or-missing intensity value; and
- each declared peptide's present-or-missing PSM count.

The digest is included in the result projection, so the pipeline's existing
canonical result digest changes when quantification evidence changes—even when the
derived estimate remains missing or shared-only. Manually constructed cohort
projection objects retain empty compatibility fields and are not presented as
pipeline-computed receipts.

The receipt is evidence about deterministic matched-fragment signal processing. It
is not a spectrum-search confidence measure, protein concentration, protein
inference probability, or independent cohort validation.
