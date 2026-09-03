# CPTAC GBM cis-dosage cohort evidence

`cptac-gbm-cis-dosage/1.0.0` is a fitted, local-only research lane for querying
gene-level copy-number-to-RNA-to-protein evidence learned from the exact CPTAC
GBM discovery-cohort supplements. It is not a patient scorer, a causal mediation
model, a clinical subtype classifier, or a treatment model. No public HTTP route
is mounted while the supplement redistribution terms remain unverified.

## Locked local sources

The fitter accepts only these exact snapshots:

| Source | Bytes | SHA-256 |
| --- | ---: | --- |
| CPTAC GBM Table S2 | 129,239,538 | `59c33b6140c88c394da50fd7461774233074dda12361df7989fe51b8b8e28a13` |
| CPTAC GBM Table S3 (optional) | 357,622 | `098b596756a84c4744b934f25dc5b9a1e49f992827e2d1223179dfb4655f08f5` |
| HGNC approved-symbol snapshot | 16,948,224 | `854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270` |

Table S2 and HGNC are required. Table S3 is optional and is never used for
eligibility, fitting, folds, thresholds, or tuning. Its `1` values become
`reported_positive`; a `0` or absent row becomes `not_reported_positive`, never
negative, tested-null, or biological absence.

## Estimator

The fitter first copies each source into a private operating-system temporary
directory while enforcing its exact byte count and SHA-256 lock in the same
bounded streaming pass. Only those staged, verified bytes are parsed. The fitter
then streams the CNV GISTIC, FPKM-UQ RNA, and normalized proteome OOXML members;
it does not extract worksheets. The private staging area contains ephemeral
whole-source snapshots, including the source workbooks' headers and rows. It is
cleaned on normal success and failure. An abnormal process or host termination
can leave private crash residue in the operating-system temporary directory, so
ordinary host temporary-file cleanup remains part of local operation.

Exact HGNC mapping uses version-stripped Ensembl IDs for RNA, strips only a
terminal CNV `|chr...` suffix, and requires an exact approved symbol for protein.
Collisions, aliases, non-text keys, and inferred Excel-date repairs are excluded.
The parser does not return or separately persist sample headers or patient rows,
and the final artifact and query receipts never contain them.

Patient groups are assigned to five deterministic outcome-blind outer folds.
Every fold learns these models using training complete cases only:

- `RNA ~ intercept + CNV`
- `Protein ~ intercept + CNV + RNA`
- matched RNA-only and CNV-only protein baselines

Each model uses median and `1.4826 × MAD` scaling with an SD fallback, Huber IRLS
(`k=1.345`, at most 30 iterations), and a `1e-8` slope ridge. A gene needs at
least 48 training and 3 held-out complete cases, four valid folds, and 60
aggregate held-out predictions. Reported metrics are held-out Pearson,
tie-aware Spearman, R² versus each fold's training median, direction accuracy,
and the full protein model's incremental R² over each single-predictor model.

The fold coefficients provide the observational decomposition
`a = CNV→RNA`, `b = RNA→protein | CNV`, `c′ = CNV→protein | RNA`,
`indirect = a×b`, and `total proxy = indirect+c′`. This is a cohort association
decomposition only. It is not an individual mediation effect.

## Abstention and support

The runtime accepts only an artifact digest and one or more exact HGNC symbols;
there are no patient-measurement fields. It:

- abstains when a cross-validated fit is unavailable;
- abstains and withholds fitted values when fewer than four estimator sets
  converged;
- abstains and withholds fitted values when indirect or total direction is
  stable in fewer than 80% of valid folds;
- reports `limited` when a stable, converged fit misses either prespecified
  held-out evidence gate; and
- reports `supported` only when both RNA and protein evidence gates pass.

Even `supported` means supported within the locked cohort, not validated
causality, transportability, or clinical utility.

## Artifact privacy and replay

The canonical JSON artifact is capped at 8 MiB and stores compact, quantized
gene-level aggregates. The artifact and every runtime output explicitly contain
no measurement vectors, sample headers, patient identifiers or
identifier-derived hashes, patient rows, or fold membership. They bind the
exact source locks, algorithm/profile, cohort counts, derivation status, and a
canonical content digest. Production artifacts are marked
`locally_verified_exact_sources` only after parsing the staged exact snapshots
and reproducing all locked cohort invariants: 96 common measurement columns, 96
patient groups, 10,430 mapped common genes, and 9,457 fitted genes. Internal
prepared/synthetic artifacts are marked `synthetic_unverified`; the analyzer
fails closed and never reports them as CPTAC cohort evidence.

Hash-while-copy staging plus parse-only-staged bytes closes the source pathname
swap window between verification and parsing. It does not claim that no
temporary source bytes are written: private whole-source snapshots exist in the
operating-system temporary directory for the duration of fitting and are cleaned
on ordinary exit, with the crash-residue limitation described above. Artifact
reads stream at most 8 MiB plus one overflow-detection byte. Publication uses an
fsynced same-directory temporary artifact file and an exclusive hard-link
create, so an existing destination—or one created during a race—is never
overwritten.

`verify-source` is a diagnostic report about the paths at the time it runs, not
a reusable authorization token. `fit-local` independently performs the bounded
hash-while-copy staging pass and never parses a path merely because an earlier
diagnostic verification succeeded.

These locks and self-hashes provide replay and accidental-corruption integrity
inside a same-user local trust boundary. They are not proof of authorship or
cross-user authenticity: a user who can replace the artifact can also mint a
new self-consistent digest and derivation-status field. Cross-user or shared-host
trust would require a signed manifest, a separately trusted verification key,
and an authenticated distribution process; this lane provides none of those.

The isolated Typer adapter exports:

```text
fit-local --table-s2 ... --hgnc ... [--table-s3 ...] --output ...
profile
analyze REQUEST.json --artifact ARTIFACT.json
verify RECEIPT.json --artifact ARTIFACT.json
verify-source --table-s2 ... --hgnc ... [--table-s3 ...]
```

Requests and results are exact content-bound receipts. Replay recomputes the
query and checks request, profile, artifact, result, and semantic equality. The
artifact and all derived output remain
`redistribution_status=local_only_terms_unverified` and must not be published or
served from a shared deployment until source terms are affirmatively admitted.
