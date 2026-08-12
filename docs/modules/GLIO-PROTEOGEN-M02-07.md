# M02-07: identification support-domain and abstention routing

M02-07 decides whether one already-quality-controlled, harmonized identification analysis lies
inside one reviewed support envelope. It evaluates the joint assay, specimen, disease-class,
quality, completeness, platform, reference, and intended-use declaration and emits only a support
decision, typed abstention reasons, and reviewed remediation paths. Protein subtype is downstream
workflow context; the router neither infers a subtype nor interprets protein biology.

This module is specific to the C02 identification-QC chain. Its request carries compact,
digest-bound receipts derived from genuine M02-04 and M02-06 public results. It does not embed or
re-evaluate the full harmonization result, repair an unreleasable prerequisite, or accept a
caller-authored prerequisite boolean.

## Routing boundary

1. Authorize consent, identity/lineage, configuration, provenance, quality, support, and intended
   use before traversing prerequisite receipts or support evidence.
2. Require releasable M02-04 quality and M02-06 harmonization receipts bound to the same analysis
   lineage. An absent, mismatched, quarantined, or abstained prerequisite produces an explicit
   support abstention; it never becomes a supported analysis.
3. Evaluate the complete eight-dimensional declaration against each closed, versioned envelope.
   Support requires one envelope to admit the joint declaration; matches assembled from different
   envelopes cannot be combined into support.
4. Treat platform and reference declarations as all-member constraints. Every declared member
   must be admitted by the same supporting envelope; a single supported member cannot mask an
   unsupported companion.
5. Preserve missing and unknown evidence as distinct typed states. Neither becomes absence,
   normality, a biological negative, or an inferred supported value.
6. Report every failing dimension in canonical order and attach only the remediation reviewed for
   that envelope/dimension. No arbitrary first-error collapse or nearest-value inference is used.
7. Canonicalize declarations and envelope membership sets so semantically equivalent ordering
   produces the complete same typed result and digest.
8. Emit the decision, typed reasons, remediations, compact upstream receipts, uncertainty,
   provenance, evidence, and limitations. Inputs and upstream results remain immutable.

The implementation is a deterministic joint-envelope router, not a classifier, anomaly detector,
transport model, or support-domain learner. It does not authenticate source evidence, revise
quality or harmonization, infer identity/consent, fuse omics, resolve transcript-protein
discordance, infer proteotype or kinase activity, recommend treatment, or make a clinical claim.

## Evidence gate

Gate G1 locks eight synthetic, non-clinical scenario groups: exact joint-envelope support; an
isolated outside-envelope case for each of the eight dimensions; missing and unknown evidence;
unreleasable M02-04/M02-06 receipts; platform/reference all-member enforcement; rejection of a
cross-envelope composite; complete result equality under semantic reordering; and consent denial
before hostile evidence traversal. The fixture constructs genuine public M02-04 and M02-06
results, then reduces them through the public compact-receipt helper used by callers.

These checks establish deterministic routing behavior for reviewed synthetic envelopes only.
They do not validate a real support domain, estimate population coverage or transportability,
calibrate uncertainty, qualify an assay, or establish biological or clinical performance.

See the [module manifest](M02-07.manifest.md),
[evidence inventory](../evidence/M02-07.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M02-07.csv).
