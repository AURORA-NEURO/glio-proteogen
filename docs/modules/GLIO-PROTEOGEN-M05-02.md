# GLIO-PROTEOGEN-M05-02 — PTM-localization identity and lineage reconciliation

M05-02 is the strict G0 identity-lineage boundary beneath PTM localization. It consumes an exact
public M01-02 `IdentityLineageResolution`, an exact public M05-01
`PtmLocalizationProtocolConformanceResult`, a reviewed M05-02 policy, and content-addressed artifact
claims. It emits only an immutable reconciliation result and privacy-minimized artifact lineage
graph. The parent target is the literal context `variant_peptide`; the module does not emit a
variant peptide or perform PTM localization.

## Public surface

- Python: `reconcile_ptm_localization_identity_lineage(request)`
- Service/plugin: `M0502Service`, `M0502Plugin`
- HTTP: `POST /v1/modules/M05-02/identity-lineage-reconciliation`
- Schema HTTP: `GET /v1/contracts/M05-02/{name}/schema`
- CLI: `m05-02-reconcile REQUEST` and `m05-02-export-schema NAME`
- Schemas: exactly `request`, `output`, `policy`, `approved-configuration`, `artifact-claim`,
  `derivation`, `graph`, `finding`, and `receipt`

All request and result models are strict, frozen, versioned, and extra-forbidden. Identifiers are
opaque, role-scoped values. Canonical JSON is duplicate-free, bounded to 4 MiB, and shared by the
library, plugin, API, and CLI paths.

## Identity and lineage closure

The embedded M01-02 resolution owns patient, specimen, aliquot, section, analyte, run, and
derived-object identity. M05-02 does not reconstruct or override that authority. Every submitted
artifact must anchor to a governed derived object with a complete seven-kind physical path. The
five exact artifact roles are mass-spectrometry proteome manifest, genome manifest, transcriptome
manifest, PTM annotation manifest, and variant-peptide input bundle. One reviewed 4-to-1 or N-to-1
derivation consumes every non-bundle claim and targets the single bundle.

The deterministic reconciliation records or quarantines:

- declared-subject swaps and cross-patient propagation;
- artifact lineage, artifact-identity, and binding-scope collisions;
- duplicate content, which is retained and recorded rather than silently merged;
- drift from the exact M01-02 resolution, M05-01 result, reference bundle, configuration, or
  assay/specimen policy;
- missing, indeterminate, unsupported, or redacted artifact evidence, which causes abstention and
  never becomes a negative finding.

Every result embeds the exact request and rederives its result/activity/finding identifiers, graph,
findings, disposition, receipt, support, uncertainty, provenance, evidence, limitations, review
state, completion time, and final digest. Re-signed derived-region substitutions reject.

## Authorization and safe failure

The runtime performs a content-free seven-control preflight before upstream, policy, claim, or
derivation traversal. Approved configuration, provenance, quality, support, and intended use must
be accepted; identity must be resolved; consent must be granted. It then fully replays M01-02 and
M05-01 and checks the reviewed configuration tuple: M05-01 result version, configuration digest,
reference-bundle digest, and assay/specimen-policy digest.

An unresolved upstream identity or unsupported configuration returns a typed empty-graph
abstention. A nonconformant M05-01 result returns a typed empty-graph quarantine. Those outcomes do
not traverse artifact claims. Ordinary hostile exceptions are sanitized, exact built-in container
caps are enforced before copying, arbitrary mappings/accessors are not invoked, and `BaseException`
is not swallowed. Plugin execution requires an issued weak token bound to the original request
identity and canonical byte snapshot.

## Claims and uncertainty ceiling

All authority flags are literal false. M05-02 emits no new identity or consent, protein identity,
PTM localization, variant peptide, proteogenomic state, proteotype, protein-level subtype, kinase
activity, copy-number-to-protein regression, all-omics fusion, treatment recommendation, or
upstream mutation. It preserves upstream disagreement and never silently merges duplicate content.

All seven uncertainty dimensions are explicit and `not_estimable`. No fitted parameter,
probability, calibration curve, consequence model, or population transport claim exists. The
support domain is explicitly narrowed to exact reviewed M01-02/M05-01 bindings and declared
artifact lineage; unsupported and OOD configurations abstain. This is the dossier's G3 alternative
to claiming nominal 90% coverage.

## Architecture decision

The dossier names event-sourced, schema-first, quarantine-first, elastic-net, and CN-to-protein
variants. The installed G0 implementation selects the schema-first deterministic reconciliation
portion only. Event storage, object storage, elastic-net fitting, anomaly training, CN-to-protein
regression, and offline job machinery are `declared_not_executed`: the dossier provides no governed
training data, fitted artifact, threshold, persistence authority, or scientific target that could
be installed without inventing claims.

## Verification

The locked corpus contains exactly 70 unique cases in eight groups and requires 70/70 success. It
includes genuine M01-02 and M05-01 public replay, a genuine two-patient physical lineage, all
installed finding classes, strict ingress, authorization firewalls, DAG invariants, re-signed
forgery, privacy, uncertainty narrowing, and append-only recovery. The benchmark performs one
untimed warm-up and exactly 25 timed public calls on the maximum reconciled five-role graph;
construction is outside timing, mean must be at most 400 ms, and nearest-rank p95 at most 750 ms.
The release verifier rejects incomplete corpus, wrong workload shape, altered budgets, invalid
digests, or incoherent timings.

See [the module manifest](M05-02.manifest.md), [evidence inventory](../evidence/M05-02.md), and
[traceability matrix](../traceability/GLIO-PROTEOGEN-M05-02.csv).
