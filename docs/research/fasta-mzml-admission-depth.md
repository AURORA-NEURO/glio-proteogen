# Research FASTA and precursor-admission depth

This lane strengthens the additive, non-governed research namespace only. It
does not change M03/M04 contracts, publish a production ABI, or make a
clinical/glioma/proteoform claim.

## FASTA admission

`research.read_fasta` now applies explicit byte, entry, and residue ceilings.
Byte and text inputs are measured before decoding; binary streams are read once
with `max_bytes + 1`, so oversized content is rejected before UTF-8 parsing or
sequence materialization. Stream return types, malformed UTF-8, empty entries,
duplicate accessions, and the existing residue alphabet checks remain
fail-closed.

The same bounded entry validator is applied to direct `FastaEntry` inputs used
by digestion and search-space construction: accessions are non-empty,
control-free, and length-limited; sequences are uppercase, non-empty, and
restricted to the admitted alphabet. Digestion controls reject booleans and
out-of-range values consistently across both public search-space builders, and
decoy prefixes use one shared minimum length so a receipt cannot be built that
its verifier would reject.

## mzML precursor ambiguity

The parser now examines each `selectedIon` independently. Distinct precursor
m/z/charge pairs in one spectrum are marked `precursor_ambiguous` instead of
silently selecting whichever descendant CV parameter happened to appear last.
The research pipeline treats that spectrum as a missing/unsupported precursor
and abstains before fragment search. Identical repeated selected-ion metadata
remains valid.

## Validation

- 349 research tests pass without repository coverage add-ons.
- Branch-enabled research coverage is 95.57% (3,345 statements; 1,300
  branches; fail-under 95).
- Ruff check/format, strict MyPy, and the focused replay/pipeline tests pass.

These gates validate bounded parsing and deterministic safe failure, not
scientific calibration or clinical utility.
