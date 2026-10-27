# Historical TCGA research purity application

The separate `tcga_gbm_historical_replication.inference` adapter applies the
unchanged published GBMPurity estimator to explicitly accepted historical
research material. Its input is the original, reviewed native STAR payload,
an actual live historical source qualification, the fixed released feature
axis, and an explicit historical inference policy. A saved projection, a
coverage receipt or a caller-supplied eligibility flag cannot authorize a run.

The [source qualification and projection boundary](tcga-historical-rna-projection.md)
requires positive author classification in the fixed 2016 supplement, exact
selected-file biospecimen linkage, and the case's explicit de-novo GBM record.
The inference policy separately accepts this historical research population
mapping, unknown selected-specimen timing and treatment exposure, and the
published missing-feature behavior. It never asserts an integrated clinical
diagnosis or performs WHO reclassification. The original CPTAC clinical
qualification and execution path remain unchanged.

The [published model](https://pmc.ncbi.nlm.nih.gov/articles/PMC12309721/) has a
primary IDH-wildtype GBM bulk-RNA scope and includes primary/recurrent research
collections. Its existing caller-owned context declaration describes model
scope and research use. After the explicit historical mapping and live source
checks, this adapter supplies that unchanged declaration to the published
service; it does not create an original CPTAC clinical context or diagnosis
review. Unknown specimen timing and exposure remain disclosed. The paper
already evaluated TCGA bulk RNA. Applying its model to a TCGA sample supplies
no independent new validation, accuracy estimate, or evidence of cohort novelty.

The adapter obtains a fresh source-bound count projection internally. Before
loading parameters or invoking the estimator, it requires at least 4,664 of
the 5,829 original features to be recognized and a positive recognized raw
count sum. Recognized features include observed positive counts and observed
zeros. The default additionally requires at least 5,771 recognized features;
limited coverage requires explicit policy acceptance. These are the inherited
80% and 99% numerical coverage thresholds, not clinical eligibility criteria.

Only recognized features are supplied under their exact original names.
Unavailable coordinates remain unsupplied. The unchanged service performs its
published zero fill, length normalization, RPK-share scaling by 10,000,
`log2(x + 1)` transformation, released float32 MLP, and clipping to `[0,1]`.
It does not substitute transformed GDC columns, conventional TPM scaling or a
new fitted network. The pinned
[author implementation](https://github.com/scmpht/GBMPurity/tree/af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950)
and the [existing model lane](gbm-rna-purity.md) describe that computation.

Source qualification, payload identity and the fixed model axis are checked
around projection, before the model call, after the call and after construction
of the private result. Result checks bind the exact request, released model,
profile, provenance, recognized-feature coverage and numerical outcome. A late
integrity failure discards the result; it does not imply that no computation
occurred. Cancellation and input failures do not grant an alternative path.

The new result has its own historical research type. Individual estimates and
their bindings remain private and cannot be implicitly serialized. Its closed
summary describes historical population basis, numerical disposition and
coverage separately from clinical support. Clinical qualification, original
CPTAC gate changes, integrated diagnosis, WHO reclassification, independent
validation and calibrated uncertainty remain false. Coverage is not an accuracy
estimate, and the single published network supplies no calibrated interval.
The nested population receipt describes the earlier source-only stage; its
inference flag remains false. The result's `model_executed` field records the
later point computation.
An estimate is not histological truth, a diagnosis, a treatment recommendation,
or an immune/stromal composition measurement.

Tests distinguish controlled source-boundary fixtures from real source
authentication, exercise pre-call abstention and late integrity rejection, and
check numerical handoff against the unchanged published service. Actual source
packets, RNA, per-sample outcomes and execution receipts stay outside Git.
No HTTP endpoint, public CLI, or UI is added.
