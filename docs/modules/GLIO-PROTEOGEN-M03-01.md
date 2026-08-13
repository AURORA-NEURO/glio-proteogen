# M03-01: protein-inference protocol and metadata specification

M03-01 validates one pinned protocol for declaring how peptide evidence may be interpreted as
protein groups beneath C03 protein-inference and ambiguity control. It owns the versioned
vocabulary and relational rules joining a search-space build, target-decoy error control,
peptide eligibility, unique/shared/razor assignment policy, protein grouping, ambiguity
preservation, and a seven-role downstream handoff. It emits a compact conformance result and
protocol receipt supporting the parent `complex_activity` workflow. It does not execute a
database search, assign observed peptides, infer proteins or complexes, estimate an error rate,
or score activity.

## Protocol boundary

1. Authorize approved configuration, resolved identity/lineage, provenance, consent, quality,
   support, and intended use before traversing any protocol section.
2. Bind the request to one reviewed profile and one exact protocol version. The declared
   profile covers exactly these sections: applicability, search space, error control, peptide
   eligibility, assignment, grouping, ambiguity, and complex handoff.
3. Close the search-space build over declared sequence, contaminant, decoy, and optional pinned
   isoform/variant reference receipts. Database build identifiers, versions, digests, and
   target/decoy composition remain explicit; aliases and free text never select a build.
4. Require compatible error-control declarations. The decoy construction used by the search
   space must agree with the target-decoy and competition strategy named by error control. This
   is metadata compatibility checking, not false-discovery-rate estimation or calibration.
5. Declare peptide evidence semantics. Uniqueness is evaluated only relative to the exact
   search space; shared evidence supports group claims only; and a razor rule may select a
   deterministic parsimony representative but never authorize a member-specific claim. M03-01
   validates those rules without classifying an observed peptide.
6. Preserve indistinguishable protein groups. A representative accession is a stable display
   and handoff identifier only. It cannot erase co-members, create member-specific evidence, or
   imply that the representative alone was observed.
7. Require any later isoform- or variant-specific claim to have both an exact pinned reference
   and eligible discriminating evidence. Missing, ineligible, shared, or unresolved
   discriminating evidence must remain unresolved rather than become a negative finding or a
   member-specific claim. M03-01 records this rule; it does not evaluate observed peptides.
8. Emit exactly seven declared handoff roles for downstream complex-activity work. The handoff
   carries protocol receipts and ambiguity semantics only; it contains no complex-activity,
   subtype, proteotype, kinase-state, fusion, treatment, or clinical interpretation.

All external controls, references, review identifiers, and content digests are caller-declared.
Their inclusion makes the conformance result reproducible and auditable; it does not authenticate
an issuer, prove reference truth, or confer review authority.

M03-01 is a deterministic schema-first conformance validator. It is not the dossier's later
protein-inference engine, multi-block PLS model, event log, identity resolver, peptide-search
engine, FDR estimator, protein-group caller, reference registry, or biological interpretation
service. Reviewed-domain mismatches produce typed quarantine findings. Structural contract violations,
unsafe ownership claims, and invalid authorization input are rejected rather than repaired.

## Evidence gate

Gate G0 uses exactly eight synthetic scenario groups. The corpus fixes search-space composition
and build identity; unique/shared/razor declarations and indistinguishable-group preservation;
isoform/variant discrimination rules; target-decoy compatibility; required alias and unresolved
state declarations; semantic reordering and strict reconstruction; consent-first authorization; and
the seven-role privacy/ownership handoff. The executable eval uses only public strict
constructors and the public M03-01 evaluator. It validates declarations and their relationships;
it does not fabricate inference outputs or claim calibrated probabilities.

The benchmark evaluates one representative maximum-useful protocol shape through the public
evaluator. Its latency ceiling is a regression tripwire, not evidence of proteomic accuracy,
error-rate calibration, biological validity, transportability, or clinical readiness.

See the [module manifest](M03-01.manifest.md),
[evidence inventory](../evidence/M03-01.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M03-01.csv).
