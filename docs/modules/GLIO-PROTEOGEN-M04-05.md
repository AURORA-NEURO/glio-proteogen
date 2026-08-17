# GLIO-PROTEOGEN-M04-05 - artifact and contamination detector

M04-05 deterministically reduces caller-declared aggregate artifact events beneath
proteoform/isoform inference. It replays the exact full public M04-04 result, selects one reviewed
detector profile compatible with both the M04-04 contract and configuration, and emits only
categorical artifact posteriors, triggered contamination flags, and excluded-only mask entries.
It never opens scientific content, identifies a protein/proteoform/isoform/PTM, computes
protein-RNA discordance, infers kinase activity, performs all-omics fusion, or recommends treatment.

## Locked behavior

1. Inspect approved configuration, resolved identity/lineage, provenance, consent, quality,
   support, and intended use before reading the embedded M04-04 result, policy, or ledger. Only an
   exact request model or built-in dict family is accepted. Built-in access bypasses subclass
   hooks, exact-string keys and node/collection caps are checked before lookup or copying, arbitrary
   mappings reject, ordinary exceptions fail closed, and `BaseException` propagates.
2. Bind operation `detect_proteoform_artifacts`, contract 1.0.0, and one opaque `request.*`
   identifier shared with the context. Replay the complete M04-04 result and its full upstream
   chain. Weakly registered internal capabilities bind exact object identity and the canonical full
   snapshot; copied seals, stale digest fields, and mutated upstream objects reject.
3. Preserve M04-04 identity, consent, provenance, support, and intended-use controls verbatim.
   Bind quality evidence to the M04-04 result, approved configuration to the M04-05 policy, and
   receipt fields to the exact M04-04 result/request/policy/configuration/receipt, identity,
   protocol, reference-bundle, coordinate-policy, and intended-use digests.
4. Match a profile only when both `result_version` and `configuration_digest` are explicitly
   approved. The upstream configuration digest closes assay, specimen, applicability, unit, and
   selected-profile context. Unsupported version or configuration abstains before ledger access.
5. A qualified and supported M04-04 result accepts one ledger. Quarantined, abstained, or
   unsupported input accepts no ledger and produces a typed zero-output safe failure. A ledger
   bound to another M04-04 result is reduced to a six-field non-traversing binding and quarantined;
   its event collection is never materialized. A correctly bound ledger is fully validated,
   including its canonical self-digest.
6. Support at most 64 targets and 448 events. Every full-ledger target has exactly one event for
   each of seven classes: technical artifact, contamination, barcode/index, batch effect,
   low complexity, mapping error, and context-specific false positive. Event sequences are
   contiguous and `(target, detector class)` pairs are unique.
7. Accept only six aggregate unit kinds: spectral feature, peptide feature, proteoform candidate,
   PTM site, batch partition, and sample-context binding. Events contain bounded scalar counts and
   content-addressed evidence, never spectra, sequences, accessions, abundance rows, filenames, or
   external content.
8. Preserve `observed`, `missing`, `not_applicable`, and `unsupported` exactly. Only observed
   events carry a positive denominator. Missing, unsupported, and not-applicable evidence has zero
   counts and becomes `indeterminate`, never clear or negative.
9. For an observed event compute the integer evidence fraction
   `(supporting_count * 1_000_000 + evaluated_count // 2) // evaluated_count`. This number and its
   one-count-resolution bounds are deterministic fractions, explicitly not calibrated probability,
   confidence, biological posterior, or scientific uncertainty.
10. Compare the fraction with the exact reviewed class threshold: below review is `clear`, at or
    above review is `suspected`, and at or above exclusion is `detected`. Emit one posterior for
    every traversable event. An explicitly observed clear posterior represents a clear target;
    absence of a flag or mask entry alone is never negative evidence.
11. Emit contamination flags only for suspected or detected `contamination` and `barcode_index`
    posteriors. Suspected flags require review; detected flags require exclusion. Other detector
    classes can trigger exclusion but never acquire contamination authority.
12. Emit an exclusion-mask entry only for a target with at least one detected posterior. It binds
    the exact triggering posterior digests, applicable flag identifiers, evidence, reason, and
    review state. It is not a retained/excluded partition and never silently fills missing targets.
13. Quarantine upstream quarantine, ledger-binding mismatch, suspected/detected evidence, and
    critical discrepancies. Abstain for upstream abstention, unsupported profile/configuration,
    or missing/unsupported required evidence. Quarantine takes precedence over abstention.
14. Return exactly 8 evidence records for safe failure and 17 for a selected profile: seven
    controls, policy, selected profile, seven thresholds, and optional ledger. Embedded upstream
    evidence and per-event references remain in their owning structures and are not recopied into
    the top-level evidence index.
15. Require every M04-05-owned artifact reference to use `evidence.<64 lowercase hex>` and its
    exact owned MIME type. Reused identity/version with contradictory digest or media type rejects.
    Genuine inherited M04-04 references remain unchanged.
16. Emit measurement, sampling, parameter, model-form, identification, support, and transport
    uncertainty as `not_estimable` with no probability. Sensitivity notes state that fractions are
    non-probabilistic and novel/OOD evidence abstains. This narrows the support domain instead of
    making a nominal 90% coverage claim.
17. Emit exactly three limitations: deterministic evidence scores only, no biological or clinical
    inference, and proteoform artifact scope only. Human review is required for quarantine,
    abstention, novel/OOD states, support override, claim promotion, release exception, or
    unresolved conflict.
18. Fully rederive posteriors, flags, mask, findings, disposition, receipt, support, uncertainty,
    provenance, evidence, limitations, review, completion, result/finding/activity identifiers,
    and final result digest during strict validation. Canonical reordering preserves equality;
    a fully re-signed derived-region forgery rejects.
19. Parse JSON exactly once with duplicate detection and a 4 MiB pre-decode cap. Plugin tokens are
    unforgeable issued identities. API, CLI, and plugin execute the already sealed request through
    a private validated path and never replay upstream or the ledger twice.
20. Export exactly 13 JSON Schema 2020-12 contracts. HTTP exposes
    `GET /v1/contracts/M04-05/{name}/schema` and
    `POST /v1/modules/M04-05/artifact-detection`. CLI exposes
    `proteoform-artifacts export-schema NAME` and
    `proteoform-artifacts detect REQUEST --output RESULT`; output is a new atomic regular file.
21. Recover append-only. A corrected request may name a superseded result digest, but M04-05 never
    overwrites, deletes, repairs, relabels, deduplicates, mutates, or silently promotes upstream or
    prior evidence.

Every authority flag for identity, consent, protein, proteoform, isoform, modification
localization, protein-RNA discordance, proteogenomic state, proteotype, subtype, kinase activity,
CN-to-protein regression, all-omics fusion, treatment, upstream mutation, and model execution is
false. `protein_rna_discordance` is context only.

## Architecture and evidence gate

The dossier describes schema-first/latent-class, event-sourced/open-set, and quarantine-first/
semi-supervised options. Gate G1 installs the schema-first contract and quarantine-first
deterministic rules only. It installs no registry, object store, event log, evidence graph,
anomaly model, latent class, semi-supervised classifier, weights, fitting, probability, network
client, or mutable persistence. The installed model count is zero.

The locked synthetic panel has 15 genuine-chain cases and 15 exact result replays. Seven seeded
critical classes produce 1,000,000 ppm sensitivity against a 900,000 ppm floor; canonical clear
produces 0 ppm false exclusion against a 50,000 ppm ceiling. Unsupported version/configuration,
missing, unsupported, and upstream-abstained cases prove typed narrowing/abstention. These are
software acceptance oracles, not scientific accuracy, calibration, transportability, or clinical
qualification.

The representative benchmark constructs the exact installed maximum of 64 targets, 448 events,
and 448 posteriors outside timing. After one warm-up it times 25 public
`detect_proteoform_artifacts` calls. Mean must be at most 2 seconds and nearest-rank p95 at most 3
seconds. Request and result must remain below 4 MiB and 8 MiB respectively.

See the [module manifest](M04-05.manifest.md),
[evidence inventory](../evidence/M04-05.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M04-05.csv).
