# CPTAC native STAR count and source-context preflight

Profile: `cptac-gbm-native-star-purity-preflight/1.0.0`.
Namespace: `research.cptac_gbm_rna_purity_admission`.
Driver: `tools/evaluate_cptac_gbm_rna_purity_preflight.py`.

This source-only backend inventories numerical inputs for the existing
`gbm-rna-tumor-purity/1.0.0` runtime. It runs no purity prediction, neural-network
preprocessing, explanation, training or clinical classification. Every planned
RNA file remains in the inventory, including unknown/conflicting context and
schema/domain rejections. Positive clinical evidence is not required for count
preflight. Existing weights, feature names/lengths, 80%/99% gates, missing-gene
policy, runtime context attestation and cohort eligibility flags stay unchanged.

The axis is the exact RNA-file axis of the admitted CPTAC discovery plan. That
axis originated in an existing paired proteome/RNA/CNV selection; it does not
represent an unselected RNA cohort. This execution profile requires the complete
inherited 72-file RNA axis. That fixed input cardinality is not an accuracy or
clinical-eligibility threshold. Resource navigation does not qualify current
cases. Freeze code, source bindings and this policy before a new real preflight;
this method promises no coverage yield or purity outcome.

## Released reference and native coordinate

Build the model axis from the pinned released artifact and locked HGNC reference,
preserving all 5,829 original ordered names and positive source lengths. Require
exact approved symbol/HGNC identity and unique Ensembl agreement. Retain unresolved
or ambiguous identities; do not guess aliases, rename model inputs, use a protein
intersection or lower a threshold to overcome annotation differences. Reference
admission executes no model. The [pinned author repository](https://github.com/scmpht/GBMPurity/tree/af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950)
defines the original input and research-use scope.

Verify each local STAR file's bounded exact byte length, MD5 and SHA256 on the
bytes used for parsing. Hashes establish integrity, not issuer authenticity.
Require UTF-8, the exact GENCODE v36 preamble and nine ordered tab-separated
columns: `gene_id`, `gene_name`, `gene_type`, `unstranded`, `stranded_first`,
`stranded_second`, `tpm_unstranded`, `fpkm_unstranded`, `fpkm_uq_unstranded`.
Select only `unstranded`. Validate all three raw columns as unsigned decimal
integers in `0..10^15`; reject blank, signed, fractional, exponential, nonfinite
or excessive counts without rounding/clipping. Valid zero is observed. Validate
transformed columns for schema integrity but never convert them to native counts.
The [GDC pipeline documentation](https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/Expression_mRNA_Pipeline/)
distinguishes raw counts from FPKM/FPKM-UQ/TPM and documents unstranded processing.

Require the four exact STAR summary rows once each and exclude them from genes
and coverage. Validate every gene row, including off-model rows. Reject malformed
rows and duplicate exact/version-normalized Ensembl IDs. Strip only the numeric
Ensembl version, preserving `_PAR_Y`. Alternative identifiers sharing a symbol
are ambiguous, not summed or selected. Source symbol and unique approved stable
identity must agree. The six states are `observed_positive`, `observed_zero`,
`absent_feature`, `unresolved_reference`, `ambiguous_identity` and
`symbol_disagreement`.

For recognized positive-plus-zero count `r` and recognized native sum `s`,
`count_ready` means `r / 5829 >= 0.80` and `s > 0`. `coverage_supported` separately
records `r / 5829 >= 0.99`. The exact boundaries are 4,664 and 5,771 recognized
features. Neither flag proves biological scope or completed inference. Missing
features are not silently filled here; the old runtime's later zero fill remains
outside this preflight. No reconstruction OOF/cohort-size gate is imported.

## Reviewed source context without a diagnostic algorithm

Context has a complete inventory over the same RNA axis. With no admitted
clinical sources, use an empty source allowlist and no evidence entries. Every
planned file is `unknown` with reason `not_provided`; no fictitious clinical lock
is generated and count parsing proceeds over the entire axis.

`ContextTarget(rna_key, lineage_digest)` binds a private RNA key to the caller's
already admitted full specimen/file lineage digest. Both must match exactly.
`assess_context_inventory` accepts typed private evidence; `parse_context_evidence`
accepts a previously bounded/hash-verified private JSON document. Orchestration
verifies each referenced source before supplying `verified_source_digests`.
Unlisted digests reject. Matching bytes do not authenticate the source, independently
reprove lineage or verify diagnosis.

Private records preserve exact source digest/location/original value, reviewed
semantic assertion, review basis and lineage scope. The software does not interpret
clinical strings, expression, age, isolated negative single-marker staining,
missing mutation entries or cohort labels as diagnosis. The initial positive
disease path is an explicit reviewed source-integrated IDH-wildtype GBM diagnosis;
separate histology/test observations are not automatically combined. Preserve
historical terminology and assay limitations. Do not introduce age/IHC diagnostic
rules or recode cases under a newer taxonomy. The [EANO integrated-diagnosis
discussion](https://www.nature.com/articles/s41571-020-00447-z) illustrates why a
reviewed integrated diagnosis differs from an isolated negative stain; no clinical
decision rule from the guideline is implemented.

Five components determine overall source context:

| Component | Explicit reviewed target assertion |
| --- | --- |
| `organism` | Human source material |
| `disease_population` | Source-integrated IDH-wildtype glioblastoma |
| `primary_population_mapping` | Explicit source-supported interpretation mapping disease/origin to the model's primary GBM population |
| `specimen_material` | Bulk tumor tissue |
| `assay_context` | Bulk RNA sequencing linked to that material |

Disease/population and primary-origin interpretation differ from specimen
collection timing and treatment exposure. `Primary Tumor`, an initial collection,
or `diagnosis_is_primary_disease` does not supply the entire mapping. Preserve
unknown when the mapping is unresolved. The [GBMPurity paper](https://doi.org/10.1093/neuonc/noaf026)
includes primary/recurrent collections; the [original Stead/Tanner accession](https://ega-archive.org/studies/EGAS00001006871)
includes recurrent material after treatment. These sources do not justify an
untreated-only or first-surgery-only exclusion.

`raw_count_coordinate` and `batch_correction` have separate source-provenance
partitions, targeting native raw counts and no batch correction. They do not
diagnose disease. `collection_timepoint` retains initial/recurrent/other/unknown/
conflicting categories; `treatment_exposure` retains unexposed/exposed/other/
unknown/conflicting categories. Neither descriptive partition changes the overall
disease state automatically. Operational research-use and zero-fill declarations
belong to a separate execution policy; no clinical record supplies them. This
preflight constructs or uses no per-specimen runtime attestation or inference
request to qualify a case, and produces no prediction. Importing unchanged
legacy contracts may initialize their existing module-level context constant;
that does not create a specimen-level claim.

For each component, active support plus opposition is `conflicting`; opposition
alone is `out_of_scope`; support without opposition is `source_supported`;
otherwise it is `unknown`. Unresolved observations remain retained even when an
explicit support exists; records are not votes. Ambiguous linkage is conflicting;
unresolved linkage cannot support a claim. Across the five required components,
precedence is conflict, opposition, unknown, then all support. Thus overall
`source_supported` describes reviewed source assertions and does not establish
the processing/operational portions of the full runtime attestation or clinical
eligibility. Processing/descriptive disagreements remain separately visible.

Retain all competing records privately. Exact duplicate records do not vote;
a record key with different payloads is malformed and rejects. Only an explicit
source-attested correction, with its source location and exact predecessor
references, can supersede a record. Relations must remain within the same target
lineage/component, be acyclic, and retain predecessors and their source bindings.
Newer or favorable rows cannot automatically resolve conflict; competing active
corrections can still contradict each other. Separate reason codes retain absent
resources, empty entries, missing components, absent/not-reported/not-tested
values, insufficient assay scope, unresolved population mapping and unresolved/
ambiguous linkage.

The closed private evidence schema has `schema_version` equal to
`cptac-gbm-reviewed-context-evidence/1.0.0` and an `entries` list. An entry has
exactly `rna_key`, `lineage_digest` and `records`. Each record requires
`record_key`, `source_digest`, `source_location`, `source_value`, `component`,
`assertion`, `review_basis`, `lineage_scope`. The only optional fields are
`reason_code`, `descriptive_value`, `supersedes`, `supersession_source_location`.
Reject extra fields, duplicate JSON keys, unbound sources, extra/duplicate RNA
keys and mismatched lineage. Original values/identifiers never enter public
receipts. Assertions are reviewed semantic inputs, not a claim that the parser
reproduces a pathologist's reasoning from the original text.

## Execution, privacy and release

The runner admits the source plan, references and optional context inventory,
then attempts every planned RNA file. Expected schema/domain failures receive
sanitized categories; unexpected valid-input exceptions leave the run incomplete.
A complete seal accounts for every planned file. Count-readiness-by-context
cross-tables conserve the full axis, separately retaining rejected-file classes.
Changing clinical context cannot change native counts, states or readiness.

The strict context receipt conserves planned/provided/not-provided totals, all
four overall states, nine component partitions, descriptive categories, input/
distinct/duplicate/superseded records, verified/used sources and per-specimen
reason occurrences. It binds only whole ordered-axis, normalized-evidence and
verified-source-set digests. No per-patient hash/status/readiness list is emitted.
It fixes issuer authentication, independently reproved lineage, clinical
validation, model execution, inferred operational declarations and overwritten
eligibility to false.

Private context wrappers are immutable, hidden from repr and reject pickle,
JSON and dataclass export. Count/state vectors are transient and immutable.
Public outputs contain no individual values, clinical strings, file paths,
source rows, patient identifiers or predictions; redistribution remains
`local_only_terms_unverified`. The generic context inventory bound is 256 targets, while this execution profile
requires its exact inherited 72-file axis. Other limits are 256 context sources,
16,384 context records, 32 MiB context bytes, 8 MiB metadata/output envelopes and
the inherited bounded STAR limits. No serializable patient cache is created.

The driver does no network acquisition or clinical adjudication. [CPTAC discovery
Table S1](https://pmc.ncbi.nlm.nih.gov/articles/PMC8044053/#SD2) is a candidate for
separately reviewed exact-byte admission; a shared GBM label or a different
validation cohort cannot bind clinical rows to this source axis.

Release requires independent synthetic native-column/identity/zero oracles,
80%/99% boundaries, context conflict/correction/lineage/privacy tests, count/context
independence and spies showing no preprocessing/inference call. Freeze before
actual preflight, require two complete repeat runs and an independent aggregate/
privacy audit before packaging. Success establishes no purity accuracy,
calibrated uncertainty, external biological validation, training-donor independence,
causal effect, clinical utility or biological discovery.


## Actual local API, commands and artifacts

The public orchestration API is `profile()`, `frozen_protocol(inputs)`,
`evaluate_preflight(inputs, *, output_dir, expected_protocol_digest)` and
`verify_preflight(directory)` in `preflight.py`. `load_inputs(path, *, sha256)`
loads a separately hash-locked private configuration. `prepare` admits metadata,
the locked reference and optional context sources/evidence, then returns a
whole-axis protocol without reading RNA payloads. Save this protocol privately
before execution. `preflight` re-admits those bindings and compares the entire
regenerated protocol digest with the supplied frozen value before any RNA read.
Neither command constructs an inference request.

From the repository root, substitute real local paths and the indicated digest
placeholders before invoking these commands:

```powershell
uv run python tools/evaluate_cptac_gbm_rna_purity_preflight.py profile
uv run python tools/evaluate_cptac_gbm_rna_purity_preflight.py prepare --inputs ../purity-inputs.private.json --inputs-sha256 CONFIG_RAW_SHA256
uv run python tools/evaluate_cptac_gbm_rna_purity_preflight.py preflight --inputs ../purity-inputs.private.json --inputs-sha256 CONFIG_RAW_SHA256 --expected-protocol-digest sha256:FROZEN_PROTOCOL_HEX --output-dir ../purity-preflight-run-1
uv run python tools/evaluate_cptac_gbm_rna_purity_preflight.py verify ../purity-preflight-run-1
```

`CONFIG_RAW_SHA256` denotes the exact 64 lowercase hexadecimal config-byte hash;
`FROZEN_PROTOCOL_HEX` denotes the 64 lowercase hexadecimal portion of the
namespaced `protocol_digest` returned by `prepare`. The placeholders are not
executable values. The existing parent of a fresh output directory must exist;
output must be disjoint from source measurement directories. Neither an old
output folder nor an incomplete run is resumed or overwritten.

The private JSON configuration has exactly these top-level fields:

| Field | Contract |
| --- | --- |
| `schema_version` | `cptac-gbm-rna-purity-inputs/1.0.0` |
| `discovery` | Exact `choices_path`, `choices_sha256`, `map_bindings_path`, `map_bindings_sha256`, `files_manifest_path`, `files_manifest_sha256` fields |
| `hgnc_path` | Exact local locked HGNC reference path |
| `context_evidence` | `null` or a local object with `path`, `bytes`, `md5`, `sha256` |
| `context_sources` | A list of the same closed local lock objects; empty when none is provided |

Source-lock MD5/SHA256 and discovery/config hashes use raw lowercase hex;
context records and the protocol use namespaced `sha256:` digests. Explicit
local absolute source paths are supported, including a previously locked
reference outside the current work folder. Relative paths resolve beneath the
configuration's parent and cannot escape that root. URLs are rejected. Every
input still undergoes its applicable bounded exact-byte checks; accepting a local
absolute path does not authenticate or clinically qualify its contents. Keep
configuration, identifiers, file choices and context originals private.

A complete run contains exactly `profile.json`, `protocol.json` and
`preflight.json`. The profile binds current method/code and fixed rules; the
protocol binds the complete input inventory, references, context and pre-RNA
freeze; the report binds the aggregate results to that protocol. Publication of
the completed report is the final seal after validation. A fatal integrity/I/O
or unexpected failure leaves incomplete evidence, not a valid complete report.
`verify` requires that exact artifact set, canonical digest chain, current method
bindings and closed aggregate conservation. It performs no source reparse,
context adjudication, model execution or independent accuracy validation.

Schema-valid files receive exactly one numerical outcome: `ready`,
`below_coverage_gate` or `zero_recognized_sum`. Below-80% takes precedence over
a zero sum, so `zero_recognized_sum_files` independently counts all valid zero-sum
files, including those below coverage. The other outcomes are `schema_rejected`
and `domain_rejected`, which remain in every full-axis/readiness-context total.
The ten fixed coverage bins describe valid files only: [0%,10%), through
[80%,90%), then [90%,100%]. Rejected files have no fabricated coverage bin or
feature-state vector. Six-state totals are over valid files times 5,829; schema
row/byte totals likewise cover valid files, while verified bytes cover every
planned file, including accounted rejections. Aggregate validation links histogram
support, zero-sum/positive-feature counts, reference-state totals and all four
context cross-table margins to their fixed numerical policies.
