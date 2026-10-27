# Source-attributed clinical gap review

`cptac-gbm-clinical-gap-review/1.0.0` adds a reproducible backend review of the
author's 2024 Table S1 to the unchanged native STAR purity execution path. It
retains the complete inherited axis, prior mutation exclusions and historical
withdrawal hold. It adds no UI, model weights, model calibration or inference lane.

The primary source is [Liu et al., Cancer Cell 2024](https://doi.org/10.1016/j.ccell.2024.06.004),
[Table S1](https://ars.els-cdn.com/content/image/1-s2.0-S1535610824002290-mmc2.xlsx).
Exact source size, MD5, SHA-256, workbook inventory, README description, clinical
headers and source row associations are checked. The bounded workbook reader
rejects formulas, active content, external relationships and ambiguous joins.
The baseline case/sample/aliquot lineage and previous clinical evidence are
revalidated. A new source path, content hash, symlink or hard-link alias to a
protected assay/metadata input is rejected before reading the new source.

`ClinicalContextFact.source_value(field)` exposes parsed source text privately,
retaining field names and missingness tokens. It does not replace the original
clinical ledger. `selected_specimen_value(field)` additionally requires the source
row to name the exact selected parent specimen. A case-level join alone is
insufficient. Source row values, binding and exact-specimen result contribute to
one ordered evidence seal; individual rows and identifiers are never exported.

Historical `path_diagnosis=Glioblastoma`, grade IV and Primary Tumor labels do not
establish an IDH-wildtype integrated diagnosis. The source's IDH1 R132H field does
not establish IDH2 assay scope. A negative result, absent mutation call or missing
test never becomes wildtype. This fixed review records zero qualifications from
this source, with diagnosis inference and population inference explicitly false.
It cannot enable purity execution or supersede prior positive mutation evidence.

Descriptive availability is separate: reported age, sex, MGMT results, vital
status, follow-up/death interval values and treatment history. Empty, NA, N/A,
Unknown and Not Performed values do not count as available results. Interval
availability requires a finite nonnegative reported value; original negative or
missing source values remain unchanged privately. No survival endpoint, censoring
rule, diagnosis-time age or treatment-naivety inference is introduced.

Use `tools/evaluate_cptac_gbm_clinical_resolution.py` with a private closed config:
`schema_version=cptac-gbm-clinical-gap-review-inputs/1.0.0`, a `baseline_inputs`
object containing its exact `path` and raw `sha256`, and a `clinical_source` object
containing exact `path`, `bytes`, `md5`, and raw `sha256`. `prepare --inputs ...
--inputs-sha256 ...` returns the frozen protocol. `review` additionally requires
that protocol's `receipt_digest` as `--expected-protocol-digest` and a fresh
`--output-dir`. It publishes four canonical aggregate documents: profile,
protocol, source and resolution. `verify <directory>` checks saved integrity,
current method and cross-document bindings. Saved verification does not replay
the clinical source. A fresh second review is required to demonstrate replay.

This review does not read RNA, decode model parameters, construct model requests
or execute inference. Baseline model input metadata is revalidated. Existing purity execution retains
its independent source, clinical, numerical coverage and research-policy gates.
Actual source rows, identifiers, individual clinical values, raw measurements and
individual model predictions remain private. Capture hashes bind bytes, while
issuer/source association requires the separately recorded primary-source review.
Local receipts retain the inherited unverified redistribution status.
