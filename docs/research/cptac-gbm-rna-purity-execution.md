# Native RNA purity execution

`cptac-gbm-native-star-purity-execution/1.0.0` adds a source-qualified backend
path to the existing `gbm-rna-tumor-purity/1.0.0` research estimator. It preserves
the frozen preflight and model implementations and adds no scientific lane or UI.

The original author's exact 5,829 source names, order and lengths remain the model
inputs. The separate coordinate policy joins every feature to one GENCODE v36
CHR gene and consistent release transcript-to-HGNC linkage. All original 5,735
current-reference coordinates agree. The remaining 94 consist of 89 current HGNC
previous-symbol renames, one historical name link, three historical coordinates
without current HGNC Ensembl assertions, and one current nomenclature conflict.
These categories do not assert that all historical symbols are current approved
names. In particular ALOX12-AS1 retains its historical locus; MIR497HG is not a
substitute. Source lengths are retained even when annotation exon lengths differ.

The reference policy pins the [author repository](https://github.com/scmpht/GBMPurity/tree/af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950),
[GENCODE v36](https://www.gencodegenes.org/human/release_36.html), its official
transcript HGNC metadata, and the existing locked HGNC index. The author CSV's
LF bytes are independently locked and its CRLF conversion must equal the original
model importer lock. No current alias guessing, alternate locus, transcript sum,
length substitution, or absent-feature zero is admitted by the raw projector.

Clinical admission parses exact locked PDC author archives, PDC biospecimen/status
responses and GDC case/specimen/status responses. Joins use the complete inherited
case, sample and protein aliquot lineage. Bounded TAR/GZIP/XLSX/JSON readers reject
ambiguous joins, active workbook content, external relationships and malformed
tables. Reported clinical mutation results, methods, somatic alteration summaries,
specimen QC and source withdrawal remain distinct observations. A combined negative
IDH header and generic testing method do not establish integrated IDH-wildtype
diagnosis. Missing mutation calls do not establish wildtype. Primary disease and
Primary Tumor labels do not establish the model's full primary-GBM population
mapping. Historical withdrawal and current release disagreement produces a source
hold before RNA reads or model execution.

The [GDC workflow](https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/Expression_mRNA_Pipeline/)
defines STAR native unstranded gene counts separately from transformed columns.
The projector verifies complete source bytes, all count columns, summary rows,
v36 versions, gene names and normalized columns, then selects only the unchanged
unstranded integer column. Missing features remain unavailable. Clinical eligibility
and numerical readiness are independent. Valid nonheld count files may be projected
even when their diagnosis remains unknown; that never authorizes model execution.

The inference bridge copies and seals immutable input snapshots, binds seven
context components and policy to exact lineage, and enforces context, 80% coverage,
positive recognized sum and optional limited-support gates before constructing a
request or loading model weights. Qualified requests use original model symbols
and lengths. The existing estimator performs its published missing-feature zero
fill only after the coverage gate. Results are checked against the unchanged model,
profile, coverage and request bindings. There is no newly calibrated uncertainty or
clinical validation claim.

Use the private closed config with `tools/evaluate_cptac_gbm_rna_purity_execution.py`:
`prepare --inputs ... --inputs-sha256 ...` freezes all sources, context, policy and
the complete ordered axis before RNA reads. Then `execute` requires that exact
`--expected-protocol-digest` and a fresh `--output-dir`. Integrity/I/O errors stop
incomplete; known count schema/domain failures are separately conserved. Completion
is published only after validating all five canonical aggregate documents and
atomically renaming the staged execution report. `verify <directory>` checks saved
integrity, current method and conservation without replaying private sources.

The local output consists of `profile.json`, `protocol.json`, `identity.json`,
`clinical-context.json`, and `execution.json`. It contains aggregate receipts and
whole-axis seals only. Case/file IDs, clinical rows, raw assay values, aligned
vectors, individual estimates, explanations and signed URLs remain private.
Checksums bind captured content; they do not authenticate a source issuer or
independently validate clinical truth. Dataset redistribution terms remain
unverified and these execution outputs stay local.
