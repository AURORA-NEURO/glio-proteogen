# M03-04: quality metric computation

M03-04 converts one authorized, content-addressed M03-03 raw-admission handoff and one bounded
synthetic fact ledger into a deterministic protein-inference evidence-graph quality result. It
closes the exact public M01-02 -> M03-01 -> M03-02 -> M03-03 chain, recomputes eight rational
metadata-quality metrics, applies one exact assay profile, and emits only quality status,
findings, provenance, uncertainty, evidence, limitations, and a disposition for the later
`complex_activity` workflow.

## Quality boundary

1. Authorize approved configuration, resolved identity/lineage, provenance, consent, upstream
   quality, support, and intended use before traversing the request or fact ledger. Each denial
   control has a hostile-input oracle with zero governed-ledger traversal.
2. In executable evidence, close over genuine self-validating public M01-02, M03-01, M03-02, and
   M03-03 outputs. The exact
   M03-03 admission result, request and receipt digests, protocol/search-space identity, lineage
   claim receipts, admitted source summaries, diagnostics, disposition, and parent target must
   agree. Handwritten upstream result envelopes are forbidden in that evidence chain. The public
   M03-04 request itself carries a caller-declared, self-content-addressed compact projection; it
   proves internal receipt/control/ledger consistency, not M03-03 execution or signer authenticity.
3. Reconstruct a privacy-safe aggregate evidence-graph view from content-addressed metadata facts.
   Exact source and claim projections plus their canonical binding digests retain metric, control,
   and provenance closure without copying source bytes, peptide sequences, accessions, abundance
   values, or patient facts into the result.
4. Compute exactly eight closed dimensions: `admitted_source_completeness`,
   `peptide_assignment_coverage`, `protein_group_ambiguity_burden`,
   `proteoform_discrimination_coverage`, `protein_group_detection_support`,
   `protein_group_competition_closure`, `control_group_recovery`, and
   `sample_context_binding_coherence`.
5. Derive metric rates from bounded integer fact counts on the locked 1,000,000 rate scale. A
   caller cannot submit a trusted precomputed rate. Numerators, denominators, reduced values,
   directions, thresholds, statuses, findings, and the final disposition are recomputed. Exact
   `at_least` and `at_most` boundaries include below, equal, above, and first-excess oracles.
6. Preserve ambiguity. Shared peptides, competing groups, and proteoform ambiguity contribute only
   to their governed counts and are not double-counted or resolved into a preferred protein.
   Censored, missing, not-applicable, unsupported, and zero-denominator observations remain
   distinct; none is converted into zero, absence, or threshold success.
7. Select exactly one policy profile through protocol, controlled-vocabulary, unit-system,
   search-space, control-group, and sample-context coherence. No exact match abstains as
   unsupported; multiple matches make the policy invalid. Profile labels never override digests
   or governed versions.
8. Propagate genuine M03-03 rejected, quarantined, or abstained dispositions before fact-ledger
   traversal and metric evaluation. Receipt/ledger binding mismatch, unsupported lineage shape,
   unsupported assay profile, missing required metrics, warnings, and threshold failures remain
   distinct typed findings. Deterministic precedence chooses the disposition without erasing
   safely established disagreement.
9. Require strict JSON and immutable typed contracts. Duplicate object keys, scalar coercion,
   non-finite numbers, unknown fields or controlled terms, silent defaults, stale derived values,
   collection excess, and the first byte past the canonical ingress cap fail closed.
10. Canonicalize only semantically unordered values. Equivalent source, claim, evidence, profile,
    and finding ordering produces a completely equal result. Typed, dictionary, and strict-JSON
    requests agree. Re-signing an outer receipt, ledger, graph, or result digest cannot legitimize
    an inner contradiction. Coherently re-authored caller declarations remain outside authenticity
    attestation and are stated as a limitation.
11. Expose the computation through the public library operation, engine, service, plugin,
    `POST /v1/modules/M03-04/quality`, and `protein-inference-quality compute REQUEST`. Expose
    bounded replay verification through `POST /v1/modules/M03-04/quality/verify` and
    `protein-inference-quality verify RESULT`; verification replays the embedded request and
    rejects duplicate keys, oversize documents, stale digests, forged metric values, and
    contradictory support/uncertainty/provenance. Exact
    installed schemas are exported through `GET /v1/contracts/M03-04/{name}/schema` and
    `protein-inference-quality export-schema NAME`.
12. Recover append-only. A corrected fact ledger, policy, threshold, or upstream handoff creates a
    new content-addressed quality result with explicit supersession provenance; a prior result is
    never edited or silently promoted.
13. Emit no direct patient identifier, raw identity token, observed peptide sequence, accession,
    protein-presence or protein-absence assertion, proteoform assignment, abundance, complex-
    activity score, subtype, proteotype, kinase state, fused-omics conclusion, treatment
    recommendation, or clinical decision.

M03-04 is a deterministic evidence-graph quality computation, not a raw parser, spectrum-search
engine, peptide-to-protein inference algorithm, protein-group or proteoform resolver, abundance
estimator, complex-activity model, assay validator, biological truth authority, or clinical
decision-support system. Qualification means that submitted synthetic metadata satisfies the
locked profile and thresholds. It does not authenticate external authorities, prove laboratory
execution, establish a protein observation, or qualify clinical performance.

## Evidence gate

Gate G1 contains exactly 57 executable cases in eight groups: genuine handoff and evidence-graph
closure; exact rational calculations and thresholds; ambiguity, proteoform censoring, and zero
denominators; assay-profile, control, and reference coherence; safe-failure precedence and zero
ledger traversal; strict ingress, capacity, and hostile authorization; canonical privacy and
re-signed forgery resistance; and interfaces, recovery, evidence, and benchmark timing.

The executable builder must call public M01-02, feed that exact result into public M03-01, feed
both genuine results into public M03-02, build real bytes and invoke public M03-03, then construct
the bounded fact ledger and invoke public M03-04. Upstream construction occurs outside the
representative benchmark clock; only `compute_protein_inference_quality` is timed. Its broad
ceiling is a regression tripwire, not evidence of assay, inferential, biological, or clinical
performance.

See the [module manifest](M03-04.manifest.md),
[evidence inventory](../evidence/M03-04.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M03-04.csv).
