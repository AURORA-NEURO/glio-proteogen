# Research-only variable-modification search

The research namespace now supports a bounded, explicit residue-local
modification catalogue. This is an additive scientific primitive; it is not a
governed M03/M04 ABI and it does not produce clinical, glioma, proteoform, or
mechanistic claims.

## Declared catalogue

Only these residue-local entries are accepted:

| Identifier | Name | Residues | Delta mass (Da) |
| --- | --- | --- | ---: |
| `UNIMOD:4` | Carbamidomethyl | C | 57.021464 |
| `UNIMOD:21` | Phospho | S, T, Y | 79.966331 |
| `UNIMOD:35` | Oxidation | M | 15.994915 |

Peptides use the constrained form `M[UNIMOD:35]PEPTIDE`. Terminal
annotations, arbitrary numeric shifts, multiple modifications on one residue,
unknown catalogue entries, and residue-incompatible placements are rejected.
The caller must declare every allowed identifier. An undeclared or malformed
annotation is never interpreted as an arbitrary mass delta.

`ResearchRunRequest.variable_modifications` and
`max_variable_modifications` expand the unmodified tryptic map deterministically.
The unmodified form is retained, variants are bounded, and expansion fails
closed at the research variant limit. The search-space receipt records the
declared rules and final target/decoy variant counts.

## Mass and replay semantics

Residue-local deltas are applied to both theoretical b/y fragments and the
precursor neutral mass before precursor-ppm filtering. `SearchParameters`
requires the same declared identifiers and site limit for direct candidate
search. Therefore a modified candidate cannot match merely because its string
appears in a caller map, and a modified precursor cannot be accepted using the
unmodified mass.

When a run declares modifications, its configuration binds the catalogue
version, canonical rule list, and site limit; its search-space receipt binds
the same controls and variant counts. Result replay consequently rejects a
changed modification policy or a forged receipt. These values are evidence of
the computation performed, not a calibrated probability of peptide identity.

The supported surface remains deliberately narrower than a full ProForma/UniMod
implementation. Future expansion requires an owner-approved catalogue,
localization semantics, validation fixtures, and a frozen computation ABI.

The search-space receipt also records `research-unimod-catalogue-1` and its
SHA-256 content digest. This binds the actual delta masses and residue
compatibility map, not merely the caller's rule names; a catalogue mutation
cannot replay as the same modified search. Direct modification parsing is
bounded to 200 residues before expansion so malformed or adversarially large
annotations fail closed.
