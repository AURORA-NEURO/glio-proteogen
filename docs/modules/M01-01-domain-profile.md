# M01-01 GLIO preanalytic proteomics profile v1.0.0

This is the first real domain profile for M01-01. It is a packaged, immutable
`ProtocolSchema` for research-use-only conformance checking of declared preanalytic
metadata from human brain solid-tissue, label-free, bottom-up mass-spectrometry
proteomics. It contains no patient observations and makes no biological or clinical
claim.

The machine-readable assets are packaged with the Python distribution:

- `protocol-schema.json` — the directly registrable versioned protocol schema;
- `catalog.json` — support domain, field-group ownership, conditionality, vocabulary
  inventory, privacy policy, and agent extension rules;
- `conformance-corpus.json` — synthetic positive and negative cases expressed as
  deterministic patches over one complete base document;
- `standards-manifest.json` — source versions, immutable pins where available, adoption
  purpose, and the explicit no-runtime-dependency policy;
- `quality-model.json` — a closed feature/view policy and deterministic OOD decision
  thresholds, cryptographically bound to this protocol and its reference corpus;
- `quality-reference-corpus.json` — 12 synthetic, non-clinical reference profiles
  spanning frozen/FFPE tissue and DDA/DIA acquisition;
- `artifact-manifest.json` — exact byte digests, byte counts, and the canonical protocol
  digest.

The canonical protocol identity is
`sha256:1d07ccd51a014702f612cc6d83cd0d67d1bab2f17fa17de61c4e6beb68572391`.
Formatting changes can alter a file digest but cannot alter this canonical protocol
identity unless the parsed contract changes.

## Owned profile surface

The 55 fields are deliberately grouped by ownership rather than by a flat form:

| Group | Fields | What is made machine-validatable |
| --- | ---: | --- |
| Identity and lineage | 4 | Exact analytical sample, immediate source specimen, lineage node, and lineage artifact digest |
| External biological context | 8 | Immutable treatment, genomic, transcriptomic, and PTM reference identifiers plus digests |
| Specimen preanalytics | 13 | Organism, anatomy, material, collection, preservation, replicate, ischemia, stabilization, storage, and fixation |
| Sample preparation | 10 | Approved protocol, input mass, extraction, reduction, alkylation, cleavage, digestion, and fractionation |
| MS acquisition | 13 | Assay, acquisition method, label, instrument, dissociation, raw artifact, fraction, replicate, injection, and LC conditions |
| Preanalytic quality | 7 | Quality-report identity, pathology review state, cellularity, necrosis, protein yield, and concentration |

All fields are mandatory except four whose applicability is explicit and executable:

- fixative and fixation duration are required for FFPE tissue and prohibited for frozen
  tissue;
- tumor cellularity and necrosis are required when pathology review is complete;
- a pending or absent pathology review is not silently failed or passed—it produces a
  human-review decision;
- an unfractionated preparation must use fraction identifier `1`.

This is the profile's interpretation of “zero undocumented optionality”: every
non-required field is cataloged with its triggering rule IDs, and tests prove that no
other optional fields exist.

## Identity, privacy, and biological context

The profile carries only opaque identifiers and content digests. It has no field for a
name, medical-record identifier, contact detail, date of birth, or clinical narrative.
The analytical sample identifier is the sole identity key. Its source-specimen and
lineage-node references identify the separately governed identity-lineage artifact
without copying that artifact. The document's lineage-artifact digest is provenance
only: the resolved execution-context identity decision and its binding digest are the
authority that binds the canonical identity-key set.

Treatment history, genomic context, transcriptome context, and PTM annotations use the
same pointer-plus-digest pattern. An `unknown`, `redacted`, or `unsupported` pointer is
represented explicitly and quarantined. Absence is never converted into “untreated,”
“wild type,” “no PTM,” or another negative finding.

## Quantities and units

Every accepted unit is from a closed subset of UCUM 2.2. Every unitful field declares a
reference unit, and every numeric bound is applied after deterministic conversion into
that reference unit. The profile exercises multiplicative and affine conversions:

- mass: `ug`, `mg`, `g`;
- volume: `uL`, `mL`;
- time: `min`, `h`, `d`;
- temperature: `Cel`, `K`;
- mass concentration: `ug/uL`, `mg/mL`, `ug/mL`;
- dimensionless percentage points: `%`.

The accepted ASCII `u` in `ug` and `uL` is the case-sensitive UCUM code, not a display
typography choice. Celsius-to-kelvin conversion uses the pinned affine semantics. A
valid UCUM expression outside the profile's registered set is still rejected: UCUM
validity does not grant profile support.

## Controlled support domain

Version 1.0.0 is intentionally narrow:

- `NCBITaxon:9606` human brain (`UBERON:0000955`) solid tissue;
- frozen tissue or neutral-buffered-formalin-fixed paraffin-embedded tissue;
- label-free bottom-up DDA (`PRIDE:0000627`) or DIA (`PRIDE:0000450`);
- Trypsin (`MS:1001251`) or Lys-C (`MS:1001309`);
- Q Exactive HF, Orbitrap Fusion Lumos, or timsTOF Pro;
- beam-type CID/HCD or CID;
- vendor-native data bundles or mzML 1.1.1 references.

This closed subset is a support claim, not a statement that other instruments or
workflows are scientifically invalid. New terms require a profile version change,
source review, conformance fixtures, and an explicit support decision. Live ontology
updates cannot expand behavior implicitly.

## Locked conformance corpus

The corpus contains two positive cases and adversarial cases spanning all four public
decisions:

| Case | Expected decision | Boundary exercised |
| --- | --- | --- |
| `frozen_dda_conformant` | conformant | Complete frozen-tissue DDA profile |
| `ffpe_dia_conformant` | conformant | FFPE conditional fields and `K`/`g`/`d` conversion |
| `ffpe_missing_fixation_duration` | quarantined | Missing conditionally mandatory preanalytic evidence |
| `unknown_acquisition_term` | nonconformant | Syntactically valid but unsupported ontology term |
| `missing_treatment_history_pointer` | nonconformant | Missing is not interpreted as untreated |
| `unresolved_genomic_context` | quarantined | Explicit unresolved state remains unresolved |
| `frozen_declares_fixative` | nonconformant | Mutually incompatible preservation metadata |
| `unfractionated_fraction_two` | nonconformant | SDRF-compatible fraction invariant |
| `pathology_review_pending` | review required | Human review is retained as a first-class decision |
| `converted_mass_above_bound` | nonconformant | Bound enforced after `g` to `mg` conversion |
| `unregistered_injection_unit` | nonconformant | Valid but unsupported unit cannot pass |
| `identity_lineage_binding_mismatch` | quarantined | Resolved lineage decision is cryptographically bound to different identity evidence |

Cases use patches rather than copied full documents so common evidence has exactly one
source. The tests materialize every case as a strict `MetadataDocument`, execute the
production validator, and require the exact decision, review flag, and issue-code set.

The executable eval reports a distinct domain-profile section with one schema check and
all 12 cases. A dedicated microbenchmark evaluates the complete 55-field conformant
profile with identity binding under a 10 ms mean regression budget. An isolated SQLite
integration test registers the packaged schema, evaluates its conformant document through
the service, and verifies the resulting two-event chain.

## Privacy-safe quality reference assets

The two quality reference assets drive an integrated deterministic out-of-distribution
(OOD) proximity guard. The guard runs only after ordinary metadata validation produces a
conformant result. An in-domain result preserves that decision; an out-of-domain,
indeterminate, or unavailable result can only downgrade it to quarantine and require
human review. The guard can never promote, cure, or override a nonconformant,
quarantined, or review-required result.

The corpus is a synthetic factorial reference design, not a fitted, optimized,
calibrated, or patient-derived training set. Its four clusters are `frozen_dda`,
`frozen_dia`, `ffpe_dda`, and `ffpe_dia`, with three complete variants per cluster.

`quality-model.json` has the following closed wire shape:

```text
model_id: string
model_version: string
profile_schema_id: string
profile_schema_version: string
canonical_protocol_digest: sha256 digest
reference_corpus_file: "quality-reference-corpus.json"
reference_corpus_digest: sha256 digest
minimum_consensus: number in (0.5, 1]
maximum_mean_distance: number in [0, 1]
minimum_view_coverage: number in (0, 1]
features: [{path, kind: "categorical" | "numeric", minimum?, maximum?}]
views: [{view_id, paths: [path]}]
```

`quality-reference-corpus.json` has the following closed wire shape:

```text
corpus_id: string
corpus_version: string
description: string
profiles: [{profile_id, cluster_id, features: {path: string | number}}]
```

The 18 declared feature paths use only controlled terms and bounded numbers from the
profile schema. Numeric corpus values are already expressed in each field's protocol
reference unit. Identity keys, identifiers, free text, timestamps, external-context
pointers, artifact references, digests, and raw-data pointers are excluded. Automated
tests also prove that every categorical corpus value is a registered term, every number
is within its declared range, no opaque identifier leaks into a feature value, and each
view distinguishes all four legal clusters.

The integrated engine boundary is equivalent to:

```python
load_packaged_quality_consensus() -> LoadedQualityConsensus
assess_quality_consensus(
    schema: ProtocolSchema,
    document: MetadataDocument,
    loaded: LoadedQualityConsensus,
) -> QualityConsensusAssessment
```

The service invokes the guard only for an already conformant document. The engine
extracts only declared model features and converts accepted quantities to their protocol
reference units. For each view, it computes observed-path coverage, skips the view below
`minimum_view_coverage` (0.75), and otherwise performs deterministic nearest-medoid
classification using Gower distance. Consensus must meet 0.66 (explicitly two of three
views) and mean distance must not exceed 0.35. Missing or unresolved values are never imputed. Artifact failures and
insufficient evidence fail closed to a generic quarantine/review result.

The returned assessment is deliberately coarse: status, evaluated- and total-view counts,
model identity/version, model and corpus digests, and a bounded reason code. Exact consensus
and distance values remain internal decision intermediates; they are intentionally absent from
the public assessment because repeated adaptive queries could otherwise reveal the locked
reference geometry. Cluster labels, neighbors, candidate feature values, and per-view votes
also never cross the module boundary. Deterministic tie-breaking, deep-frozen reference maps,
bounded asset reads, canonical digest pins, replay behavior, and privacy controls are covered by
the engine and service tests.

The executable evidence gate separately locks artifact identity, in-domain retention,
out-of-domain quarantine, insufficient-evidence abstention, input-order invariance, and the
coarse public envelope. A dedicated microbenchmark measures the complete 18-feature, 3-view,
12-profile nearest-medoid guard under a 10 ms mean regression budget; this is an engineering
tripwire, not a throughput or clinical-performance claim.

This integrated guard remains research-use-only synthetic reference-domain proximity.
It makes no trained or calibrated model claim and no claim about cohort
representativeness, biological subtype, biological or assay quality, diagnosis,
prognosis, treatment response, or clinical fitness. Its sole decision authority is a
one-way quarantine/review downgrade after deterministic conformance.

## Standards provenance

The profile is informed by the following primary sources. Exact versions, commits, and
the field groups influenced by each source are locked in `standards-manifest.json`.

- [SDRF-Proteomics 1.1.0](https://github.com/bigbio/proteomics-sample-metadata/blob/03df7bc728dc740a7e9aa2a56262cf32848545f6/sdrf-proteomics/README.adoc)
  for sample-to-file relationships, replicate/fraction semantics, required acquisition
  metadata, preparation categories, and treatment-history reporting;
- [HUPO-PSI MS CV 4.1.258](https://github.com/HUPO-PSI/psi-ms-CV/blob/6a9fd09937c0e64fd441bbbbf78d6ec1a9f408f6/psi-ms.obo)
  for cleavage agents, labels, instrument models, and dissociation methods;
- [PRIDE ontology release 2026-06-19](https://github.com/PRIDE-Archive/pride-ontology/blob/7cd30c13a035247ccbc86f0b4efa8f8a7cc3f1e3/pride_cv.obo)
  for DDA and DIA accessions;
- [UCUM 2.2](https://ucum.org/ucum) for case-sensitive unit syntax, dimensions,
  equivalence, and conversion semantics;
- [HUPO-PSI mzML 1.1.1 schema](https://github.com/HUPO-PSI/mzML/blob/c43c4ea57ad73abd72ff3b55ebd78827a73fab61/schema/schema_1.1/mzML1.1.1.xsd)
  for the open data-format declaration;
- [MIAPE](https://doi.org/10.1038/nbt1329) for minimum experimental protocol and
  acquisition reporting;
- [BRISQ](https://pubmed.ncbi.nlm.nih.gov/21433001/) for consistent reporting of
  biospecimen collection, processing, storage, and privacy-aware context;
- [NCI Best Practices, fourth edition](https://dctd.cancer.gov/data-tools-biospecimens/biospecimens-biobanks/resources/best-practices/biospecimen-resources/technical-operational)
  for unique non-identifying specimen identity, lineage tracking, storage, pathology
  review, and quality documentation;
- [NCI GDC biospecimen data standardization](https://gdc.cancer.gov/about-data/gdc-data-processing/biospecimen-data-standardization)
  for case-sample-aliquot provenance separation and linked QC metadata.

These sources inform a purpose-built profile. The repository does not claim that this
JSON artifact is itself a complete SDRF file, mzML document, MIAPE report, clinical
standard, or accreditation checklist. External sources are not fetched during
validation, so network availability cannot change a decision.

## Interpretation ceiling

Conformance means only that the declared metadata satisfies this versioned profile. It
does not verify laboratory truth, raw-file contents, tissue quality, diagnosis,
prognosis, treatment response, or assay fitness for a different intended use. M01-01
does not infer or own kinase state, generic multi-omics fusion, treatment
recommendations, or protein-level subtype claims. Those boundaries are encoded as
machine-readable limitations, not left to prose alone.
