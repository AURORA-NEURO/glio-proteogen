# CPTAC GBM confirmatory multimodal admission

`cptac-gbm-confirmatory-multimodal-admission/1.0.0` adds an executable local
source-admission workflow to the existing glioma proteogenomic feature space.
It reads the exact PDC000446 CDAP protein output and a frozen set of matched
open GDC STAR and AscatNGS files. Its result is aggregate measured coverage,
with one explicit measurement axis per assay. It does not fit a model or
promote these inputs into an existing Table S2 artifact.

This stage answers a necessary question before external evaluation: which
predeclared gene/specimen observations actually exist on all three assays,
with the intended identities and source processing? A successful checksum or
parser does not establish prediction quality, molecular disease eligibility,
donor independence, or compatible cohort effects.

## Sources and trust boundary

The protein and sample-map byte counts, MD5s, and SHA256s are fixed in
`protein.py`. The HGNC approved-identity snapshot has an independent fixed
size/SHA256 lock in `identity.py`; its separately pinned MD5 is a local
integrity cross-check, not a publisher signature. The specific PDC protein
matrix is gene-level relative CDAP output, distinct from the publication's
jointly processed ComBat/DreamAI archive. Source format and ratio semantics
are documented in the primary [PDC analysis guide](https://pdc.cancer.gov/pdc-docs/data-analysis-guides)
and [CDAP protein report specification](https://pdc.cancer.gov/pdc/assets/CDAP_ProteinReports_description_20160503.pdf).

Two private, caller-trusted captures supply the specimen crosswalk and the
per-file locks. Both require explicit expected SHA256 values before parsing:

1. The frozen metadata choices capture records the exact official case,
   sample UUID, protein aliquot, RNA file, and gene-CNV file associations.
   It contains the previously reviewed source-map-qualified candidate set.
2. The private download manifest records each local file's declared bytes,
   official MD5, independently computed SHA256, workflow, and local basename.
   Its `source_plan_sha256` must equal the metadata capture's exact hash.

These expected digests bind the supplied capture and permit deterministic
replay. They do **not** authenticate GDC/PDC as issuer or independently
re-prove the captured joins. An operator must acquire and review the official
metadata before freezing these inputs. The receipt explicitly preserves this
trust boundary. The numerical readers never infer participant identity from
filenames, prefixes, gene measurements, or cohort performance.

The fixed source plan requires 56 distinct metadata candidates and exactly
112 distinct open file choices, one STAR and one AscatNGS file per candidate.
It retains the `metadata_candidate_not_admitted` state. This is a bounded
source profile, not a general claim that the publication contains only that
many patients or that every such candidate is eligible for a biological
analysis. Nonunique official ancestry remains withheld; a normal workflow
reference is not another tumor observation.

The plan checks exact identifiers and unique roles, expected workflow and
assay labels, source-map occurrence, file count, byte totals, checksum
agreement, safe UUID basenames, regular local files, and complete one-to-one
coverage. The source reader verifies the same opened bytes with both hashes
before decoding, rejects leaf links/reparse points, and detects binding or
file changes during the read. Per-file failures stop the workflow; it does
not silently replace a file or drop a difficult specimen.

## Gene identity and measurements

The fixed panel is the same sixteen literature-defined genes used by the
existing source-cohort evaluation. No gene is replaced after inspecting
coverage or any downstream outcome.

HGNC identity indexes retain exact approved HGNC, NCBI, and Ensembl bindings.
Ambiguous Ensembl mappings remain ambiguous; missing cross-reference IDs
remain absent. Gene-symbol aliases are not guessed. Version normalization
removes only the numeric Ensembl version, preserving the distinct `_PAR_Y`
identity suffix. Duplicate exact or normalized gene identifiers fail closed.
Matching gene names alone cannot merge distinct Ensembl rows.

The protein decoder verifies the exact channel map, nonreference assignment,
active specimen headers, fixed annotation positions, excluded source summary
rows, row widths, organism, and stable HGNC/NCBI agreement. It selects only
`Unshared Log Ratio`, using uniquely mapped peptide evidence. All-peptide
`Log Ratio` is retained solely as an aggregate coverage comparator. It cannot
fill missing unshared values or silently change the measurement policy.
Withdrawn and pooled-reference targets are not candidate observations.

The STAR reader requires the declared GENCODE v36 schema. It validates all
six numeric columns and excludes the four explicitly named mapping-summary
rows, then exposes only `fpkm_uq_unstranded` for this profile. Counts, TPM,
FPKM, and FPKM-UQ remain different axes. A matching FPKM-UQ column name does
not establish equivalence to the original publication's RNA pipeline. The
primary processing reference is the [GDC RNA workflow](https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/Expression_mRNA_Pipeline/).

The AscatNGS reader exposes total `copy_number` and validates the accompanying
minimum and maximum segment-derived copy numbers. It does not invent major
or minor copy-number fields or infer an annotation release from the RNA
file. Absolute copy number is distinct from the original GISTIC2 scores and
from log2 segment means. See the [GDC copy-number workflow](https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/CNV_Pipeline/).

Every parser distinguishes observed numeric zero from a blank measurement.
Protein blank cells and entirely blank CNV triplets remain unavailable;
partial CNV triplets and nonfinite or invalid numeric tokens fail. There is
no imputation, log transformation, threshold conversion, scale alignment,
batch correction, or source-value subtraction across assay axes.

Transient matrices and panel vectors use immutable byte-backed NumPy arrays,
hide values in representations, and reject pickling. They remain private
development objects. Only aggregate receipts are intended for serialization;
the runner never serializes the transient objects or their participant order.

## Joint coverage and evidence gates

One ordered frozen plan supplies the protein aliquots and every paired RNA
and CNV read. The runner preserves this same order throughout. The pure
coverage function has no participant identifiers and cannot independently
detect a caller's permutation; the orchestration contract owns that binding.

For each panel gene the report contains:

- Counts observed on each assay and jointly finite on all three.
- All eight finite/unavailable patterns in explicit CNV/RNA/protein order.
- Separate observed-zero counts, with zeros included in observed support.
- Counts by observed, absent feature, unresolved reference, ambiguous
  identity, disagreeing symbol, and missing measurement states.
- Structural absence of a protein feature, distinct from blank cells in a
  present feature.
- Whether the unchanged legacy minimum of 60 common OOF observations could
  possibly be met by the measured joint support.

These are measured coverage counts, not model accuracy or discovery tests.
The candidate set cannot reach the legacy OOF minimum; no support threshold
is lowered to accommodate its size. The original model additionally requires
its own exact source locks and processing. This workflow never invokes that
fitter and always reports legacy fitting and source-axis compatibility as
unadmitted. A future external analysis needs an independently justified,
frozen protocol with explicit processing and disease eligibility.

## Execute and replay locally

Keep all source files, capture JSONs, and source-derived outputs outside Git.
The private download manifest must reside alongside its UUID-named `.bin`
files. Use the exact locked HGNC, protein, and sample-map snapshots.

```powershell
uv sync --locked --group dev
uv run python -m tools.evaluate_cptac_gbm_confirmatory_admission `
  --choices <private-frozen-metadata-choices.json> `
  --choices-sha256 <raw-lowercase-64-hex> `
  --files-manifest <private-verified-files.json> `
  --files-manifest-sha256 <raw-lowercase-64-hex> `
  --protein <exact-PDC000446-tmt11.tsv> `
  --sample-map <exact-PDC000446-sample.txt> `
  --hgnc <exact-HGNC-snapshot.txt> `
  --output-dir <new-private-directory>
```

The output directory must be new. The runner first validates the frozen
capture bindings, then persists `protocol.json` before opening assay
measurements. That protocol binds the method source modules, tool source,
runtime versions, source locks, metadata digests, chosen axes, and panel.
It then reads every declared file, writes `evaluation.json` with an aggregate
report digest, and writes `summary.csv`. A source failure leaves no partial
coverage result; the already frozen protocol may remain for audit. Existing
output files are never overwritten. CLI failures omit input paths and IDs.

Repeat the command into another new private directory. Identical source
captures, source bytes, method, and pinned environment should produce
byte-identical protocol, report, and CSV. Keep the failure of any such replay
visible and resolve its cause before using the aggregate evidence.

All inputs and real-data derivatives remain `local_only_terms_unverified`.
Do not upload them or substitute them for committed tests. The repository's
small synthetic fixtures test parser, numerical-support, privacy, and failure
contracts; they are not glioma measurements or external validation.

## Verification map

The foundation tests cover bounded reads, checksums, path/file changes,
approved identity indexes, ambiguity, and missing cross-references. Protein
and assay tests cover schema, exact measurement choice, zeros and blanks,
reference assignments, identity conflicts, and transient serialization.
Plan tests cover private-capture integrity, one-to-one bindings, safe paths,
and trust-boundary receipts. Coverage and runner tests verify joint pattern
arithmetic, candidate order, protocol timing, all-file execution, fail-closed
behavior, deterministic digests, and aggregate-only exports. Real full-source
execution and repeat receipts remain private local evidence.
