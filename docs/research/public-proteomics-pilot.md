# Public proteomics research pilot

This pilot composes the additive research primitives on the current research
foundation. It is intentionally not a M03/M04 route, a governed module ABI, or
a clinical analysis service. The pilot accepts caller-supplied bytes only:

1. a bounded PDC study-metadata response;
2. a local FASTA search space; and
3. a local mzML document.

No network transport is reachable from `run_pilot`. The checked-in PDC record
is metadata for `PDC000204`; the representative external file is not fetched
or redistributed. The checked-in mzML has no MS2 arrays, so the fixture-bound
run abstains with `NO_MS2_SPECTRA`. Tests also exercise a tiny synthetic MS2
document to prove the full search path without representing it as public-cohort
evidence.

## Computation boundary

The pilot content-addresses the metadata response, local FASTA/mzML bytes,
source manifest, structural evidence aggregate, and result receipt. It then:

- digests the caller-declared FASTA with bounded tryptic rules;
- decodes only bounded mzML arrays and searches MS2 spectra with explicit
  fragment tolerance and minimum-ion parameters;
- performs target/decoy competition and records exploratory q-values;
- preserves shared-peptide ambiguity in deterministic research protein groups;
- computes a median-normalized total-peak signal proxy, explicitly not an
  abundance estimate; and
- abstains when there are no MS2 spectra or no supported PSM.

`verify_pilot_replay` reruns the same offline bytes and rejects any changed
payload or digest. The result policy is closed: research-only and owner review
are true, network access and clinical/disease/treatment/mechanistic claims are
false. Protein-group objects remain exploratory research objects and are not
production identity assertions.

## Promotion gate

Promotion requires owner approval of the search-space/reference version,
digestion and modification rules, precursor/fragment tolerances, scoring and
FDR calibration, quantification units and normalization, ambiguity and
missingness policy, consent/DUA, privacy, replay, review, and safe-abstention
contracts. Until those are frozen, this pilot must remain outside governed
module request/result models and its receipts must not be used as biological,
glioma-specific, treatment, or clinical claims.
