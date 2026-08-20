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

## mzML precursor ambiguity

The parser requires the document root to be `mzML` (including namespace-qualified
roots) before walking nested spectra. A well-formed XML document with a spectrum-like
child but a different root is rejected before precursor/search evidence can be emitted.

The parser now examines each `selectedIon` independently. Distinct precursor
m/z/charge pairs in one spectrum are marked `precursor_ambiguous` instead of
silently selecting whichever descendant CV parameter happened to appear last.
The research pipeline treats that spectrum as a missing/unsupported precursor
and abstains before fragment search. Identical repeated selected-ion metadata
remains valid.

Effective spectrum IDs must also be unique. The downstream target/decoy
competition is keyed by spectrum identity; accepting two distinct spectra with
one ID would collapse their contenders into one winner and distort spectral
counts and FDR evidence. Duplicate IDs therefore fail at mzML admission
before fragment search.

The search primitive supports precursor charges 1--20. An mzML file may carry a
larger positive charge value, so parsing preserves that metadata, but the
pipeline treats it as unsupported precursor evidence and abstains the MS2 before
constructing search parameters. This prevents an otherwise valid XML document
from turning a bounded search-control limit into a whole-run failure. Boolean
values are also rejected for direct numeric search controls
(`fragment_tolerance_da` and `min_matched_ions`) rather than being accepted
through Python's `bool`-subclass-of-`int` behavior.

The parser also requires one physical m/z array and one physical intensity
array per spectrum when those arrays are declared: duplicate role arrays are
rejected instead of selecting the last XML descendant. m/z values must be
finite and positive, intensities finite and non-negative, retention time
non-negative, and MS level positive. Invalid measurements fail before fragment
search so malformed signal cannot be silently converted into an empty result.

## Validation

- 349 research tests pass without repository coverage add-ons.
- Branch-enabled research coverage is 95.57% (3,345 statements; 1,300
  branches; fail-under 95).
- Ruff check/format, strict MyPy, and the focused replay/pipeline tests pass.

These gates validate bounded parsing and deterministic safe failure, not
scientific calibration or clinical utility.
