# Security and responsible use

GLIO-PROTEOGEN is research software. It is not a clinical decision system and must not be used
to recommend treatment or infer consent, identity, or unsupported biological findings.

Report suspected vulnerabilities privately to the AURORA-NEURO repository maintainers through
GitHub's private vulnerability-reporting channel when available. Do not include credentials,
patient data, or exploitable production details in a public issue.

The repository accepts only synthetic, non-clinical fixtures. Inputs are bounded before parsing,
unknown fields are rejected, evidence references are content-addressed, and persistent audit
events exclude submitted metadata values. Dependency, static-analysis, test, and provenance
checks are release gates; an attestation establishes build origin, not scientific validity.

## Integrity threat model

The SQLite event digest chain is tamper evidence relative to a head digest already trusted by the
running process or retained independently of the database. It is not a signature or a
secret-authenticated log. A fresh process cannot distinguish an authentic database from a raw
database file whose events, digests, checkpoint, schema, and triggers were all rewritten and
recomputed by an attacker. For recovery, retain the accepted head outside the SQLite files in a
separately governed, append-only or signed system and supply that value explicitly; a checkpoint
read from the same database is not an external trust anchor.

SQLite does not enforce host authorization. Deployments must use operating-system ACLs to limit
the database, `-wal`, `-shm`, journal, backup, and external-head records to the dedicated service
identity and governed operators. Volume encryption, durable backups, and monitoring are separate
controls. They reduce exposure but cannot make an administrator with raw-file access unable to
replace history. A running process can notice an externally changed file before accepting more
writes; after restart, that protection depends on the independently retained head.

Do not copy a live database as if its main file were a complete snapshot. Quiesce writers or use
the SQLite backup API, preserve the related WAL state when required, verify the copied chain
against the external head, and only then reopen writes. Recovery may rebuild derived projections
after that verification; it never repairs, rewrites, or reauthorizes source events. Build
attestations likewise bind artifacts to a workflow identity and do not authenticate runtime event
history or constitute external scientific review.
