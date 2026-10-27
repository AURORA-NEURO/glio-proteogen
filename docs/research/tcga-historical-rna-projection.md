# Historical TCGA source qualification and native RNA projection

`tcga_gbm_historical_replication` supplies a separate source-and-count boundary
for historical author-classified research material. It does not construct the
original CPTAC clinical context, invoke its qualification or inference service,
or assert an integrated clinical diagnosis. Existing unresolved CPTAC cases
retain their original disposition.

The fixed source is the author Table S1A discovery workbook linked as AWG
Clinical Supplementary Info on the
[official 2016 GDC publication page](https://gdc.cancer.gov/about-data/publications/lgggbm_2016).
That study includes diffuse gliomas across grades II–IV. The new policy requires
the same exact author row to state GBM study membership, RNA availability,
glioblastoma histology, G4 grade, WT IDH status and IDHwt molecular subtype.
It uses positive author classification, not absent mutations or negative IHC.
This is a historical research-population basis; it performs no WHO 2021
reclassification. Current harmonized STAR measurements are not the original
paper's RNASeqV2 measurements, and this boundary establishes no independent
validation or clinical accuracy.

The source factory requires five separately locked resources: the fixed public
workbook, original clinical XML, original biospecimen XML, current selected-file
GDC metadata, and a direct file-associated entity response. It reparses the raw
resources and joins the exact case and every sample, portion, RNA analyte and
aliquot using both UUID and submitter barcode. An exact aliquot elsewhere in a
case tree cannot replace the selected file's explicit direct association. The
[GDC API documentation](https://docs.gdc.cancer.gov/API/Users_Guide/Search_and_Retrieval/)
distinguishes case-wide retrieval from file metadata; associated entities use
the supported expansion and leaf-field syntax. Provider errors, warnings,
ambiguous identities, role aliases and changed source files reject admission.

The clinical record must explicitly report de-novo GBM, no neoadjuvant history
and no prior glioma. These remain case-level observations. This first profile
requires the original selected-sample collection/procurement fields to be blank
and retains unknown specimen timing and exposure. Blank original XML material
descriptors remain unknown even when the exact file-associated GDC sample says
Tumor/Primary; conflicting nonblank values reject the join. The original XML
sample role must explicitly be Primary Tumor. No case-level treatment statement
becomes a selected-specimen untreated assertion.

`ReviewedHistoricalSourceAuthority` is trusted operator configuration, separate
from an untrusted source request. It records reviewed acquisition origins,
versions and byte locks; the public workbook anchor cannot be caller-replaced.
Checksums establish integrity, not the issuer. Origin review is an explicit
trust boundary. A saved feasibility report, eligibility flag, private test
builder or exported receipt cannot grant this authority. Ordinary source paths,
distinct file identities, before/after snapshots, raw joins and retained private
evidence are revalidated. Qualification objects deny mutation and implicit
serialization. The workbook reader parses metadata cells, including existing
assay-derived summaries; only the specified classification fields enter this
policy. This is not a raw expression-matrix reader.

Count projection additionally requires an independently reviewed acquisition
SHA-256 plus the selected file's issuer size and MD5. A hash freshly computed
from arbitrary supplied bytes cannot replace that authority. The public
projection rejects synthetic fixture qualifications and rechecks the live source
qualification before and after native parsing and private result construction.

The unchanged native STAR projector validates the complete payload before
selecting raw unstranded counts. Its exact 5,829-feature axis retains original
names, order and lengths, pinned GENCODE v36 coordinates, and verified HGNC
links. Axis preparation reads and verifies encoded artifact metadata without
decoding parameters or loading the model. Observed zeros remain distinct from
unavailable coordinates. Private count/state arrays use immutable byte storage
and deny implicit serialization. The closed receipt contains six-state counts
and coverage, with no count vector, count sum, case/file identifiers or private
input hashes. Availability counts may still disclose specimen information;
receipt export provides no privacy guarantee.

The inherited numerical readiness rule requires at least 80% recognized model
features and positive recognized count mass; the separate coverage-supported
flag uses the inherited 99% threshold. Neither flag grants inference authority.
Clinical qualification, original CPTAC gate changes, inference execution and
model invocation permission remain literal false. No point-inference function,
HTTP endpoint or public CLI is added in this milestone.

Tests separate fixed-publication-anchor rejection from controlled source
orchestration with a mocked verified-reader boundary. The latter exercises raw
parsers, snapshots, re-admission and tamper rejection; it does not authenticate a
synthetic workbook as published material. Native projection parity is tested
with explicitly synthetic inputs and an explicitly controlled source boundary.
Actual source and projection evidence stays private outside Git.
