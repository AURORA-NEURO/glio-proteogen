# Research search-space and decoy receipt

The research pipeline now records the exact target/decoy search space that was
digested for a run. A FASTA SHA-256 alone is not enough: changing tryptic
missed-cleavage or peptide-length controls changes the candidate population
without changing the bytes. `SearchSpaceReceipt` therefore binds the source
digest, enzyme and digestion controls, target/decoy protein and peptide counts,
target/decoy peptide overlap, and deterministic accession pair evidence into
the result and its `EvidenceBundle`.

## Cleavage-aware pairing

The research primitive does not manufacture a decoy database or claim that a
caller-supplied one is statistically calibrated. It pairs `DECOY_<target>`
accessions only when both entries are present, digests each entry independently
with the declared trypsin settings, and records either `cleavage_compatible` or
`cleavage_mismatch`. Unmatched target and decoy proteins remain explicit counts.
This prevents a global peptide map from hiding that a decoy was absent, used a
different cleavage policy, or produced no admissible peptides.

## Replay and limitations

The receipt has a pair digest and an outer search-space digest. It is included
in the pipeline result projection, the configuration/evidence records, and the
result digest; `replay_research_protein_inference` verifies all three before
accepting a replay. A forged pairing, changed source bytes, altered digestion
controls, or changed decoy prefix therefore cannot replay as the same result.
The standalone verifier also checks the source SHA-256 syntax, receipt/version
and modification-policy compatibility, canonical pair order, exact
target-to-`DECOY_<target>` identity, cleavage-status derivation, target/decoy
and unmatched-protein closure, non-negative bounded counts, and overlap bounds
before accepting either digest. Recomputing an outer digest is therefore not
enough to turn a structurally invalid receipt into accepted evidence.

For each accession-matched target/decoy pair, `cleavage_compatible` compares
the unmodified tryptic product counts. Variable-modification expansion is a
separate search-space projection recorded by the `modified_*` fields; residue
eligibility must not turn identical cleavage into a reported cleavage mismatch
or make the FDR search-space receipt depend on an optional PTM policy.

Custom decoy prefixes use the same bounded one-to-32-character,
non-whitespace rule at construction and verification, so a valid one-character
namespace remains replayable.

This remains a research-only receipt. It does not infer protein identity,
calibrate FDR, validate a search engine, authenticate a public data provider,
or support clinical, glioma, mechanism, proteoform, or isoform claims. A future
governed computation lane must freeze the allowed reference catalogue, decoy
construction method, search parameters, validation data, and claim ceiling
before this evidence can be promoted beyond research use.
