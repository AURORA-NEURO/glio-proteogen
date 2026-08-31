# Neftel bulk-protein program evidence (`neftel-bulk-protein-programs/1.0.0`)

## Scope

This research model tests whether a standardized bulk-protein contrast contains evidence for
the eight exact meta-modules published in Neftel et al., “An Integrative Model of Cellular
States, Plasticity, and Genetics for Glioblastoma”
([Cell 2019](https://doi.org/10.1016/j.cell.2019.06.024)). It also exposes five transparent
display families: astrocyte-like, oligodendrocyte-progenitor-like,
neural-progenitor-like, mesenchymal-like, and cell cycle.

The source ontology and marker membership are real GBM single-cell programs. The protein
scoring, uncertainty, null calibration, and support thresholds are repository research methods;
they are not a claim that the original paper trained or validated a bulk-proteomic classifier.
Outputs are therefore named `bulk_protein_program_evidence`. They are not malignant-cell
fractions, clinical subtypes, diagnoses, prognosis, or treatment guidance.

## Exact source and identifier provenance

The importer locks the authors’ Table S2 workbook and the HGNC mapping release used to map
legacy symbols and establish whether an entry has a UniProt protein product.

| Artifact | Locked SHA-256 |
|---|---|
| Neftel Table S2 workbook | `208e73ab3d22c494caf85c867d69dc6be38df3fc62ab1f043d7fcc5441066277` |
| Exact raw program/rank projection | `f3fd4171b07c7b0ac7b001d62fffebe0f613c9c3737ce28cdcbc71b0cd3c013b` |
| HGNC complete-set source | `854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270` |
| Canonical runtime catalog content | `5f0baa349db65f0ee740a318db6aad334b4ab9fa94b9f9d69158441054c1582f` |
| Bundled catalog bytes | `f08b7521ffecb3435bb18a113dc10e306df9a4895b7d4daf3235217468be2a5c` |
| Pinned 20,288-protein HGNC–UniProt rank background | `bc339006d99637bae20d7bcce327b67c31043e6618cb70659a85d7b2b8ff1669` |

The exact source columns contain MES2 (50), MES1 (50), AC (39), OPC (50), NPC1 (50),
NPC2 (50), G1/S (29), and G2/M (45) entries. Raw symbols and ranks are never rewritten.
Canonical symbols, HGNC IDs, UniProt accessions, and eligibility are separate fields. Five
non-protein loci—`SOX2-OT`, `MIAT`, `DLX6-AS1`, `TMEM161B-AS1`, and `LOC150568`—remain in
source provenance but are never turned into missing protein values. The importer validates both
pinned source files and reproduces the vendored catalog byte for byte. Runtime loading rejects any
catalog whose raw bytes or canonical JSON differ from the pinned digests. The same artifact contains
the sorted approved HGNC symbols having at least one UniProt identifier in the pinned authority;
its count and digest are independently checked before it can become a rank background.

Table S2 publishes membership and descending rank, but not the underlying numeric average
log-ratios. Consequently, the primary estimator gives every eligible marker equal prior mass
within its source module. It does not invent rank-decay weights. Combined families give each
source module equal total mass and deduplicate shared proteins.

## Input semantics

Each observation declares an exact gene symbol, standardized log2 abundance contrast,
standard error, quality weight, provenance digest, and one state:

- `observed`: two-sided contrast evidence;
- `left_censored`: an upper-bound contrast retained by a one-sided loss;
- `missing`: no numerical evidence;
- `unsupported`: explicitly outside protein support, also no numerical evidence.

Every request also supplies `effect_reference_id` and the literal scale
`standardized_log2_abundance_contrast`. Therefore `activated` and `suppressed` mean higher or
lower relative to that caller-declared reference—not absolute pathway activity. Duplicate raw
or post-alias symbols are rejected. Missing and unsupported proteins cannot carry a value or
quality weight and cannot alter random draws. Every active (`observed` or `left_censored`)
identifier must resolve exactly—after one of the 16 pinned legacy aliases—to the bundled
HGNC–UniProt background. Regex-shaped inventions and known non-protein loci are rejected before
inference. An unresolved identifier may be retained only as inactive `unsupported` evidence and
never enters a rank, coverage gate, or random draw.

## Two independent estimators

For a program with marker effects $y_i$, standard errors $s_i$, and quality weights $q_i$, the
primary score minimizes a ridge-regularized Huber location objective. Reliability is
$q_i/(s_i^2+s_0^2)$ after equal marker mass. A left-censored upper limit contributes only when
the candidate location exceeds that limit, so censoring cannot manufacture negative evidence.
The one-dimensional convex optimum is solved deterministically by bounded bisection.

The independent rank statistic places exact observed markers in the percentile ranks of the
complete identity-validated observed request proteome, takes a reliability-weighted marker mean, and maps it to
`[-1,+1]`. It excludes censored markers from exact rank placement. Deterministic global-rank
permutations produce a two-sided empirical p-value with a pseudocount. Benjamini–Hochberg is
applied once per unique numerical hypothesis: the display aliases `astrocyte_like` and
`oligodendrocyte_progenitor_like` inherit the AC and OPC p/q values instead of being counted as
duplicate tests. This is a repository-defined weighted
mean-percentile statistic, not ssGSEA or a claim of equivalence to independently validated
enrichment software.

Both estimators receive deterministic measurement-error bootstrap intervals. Seeds derive from
alias-normalized active numerical evidence, requested bootstrap/permutation counts, and the exact
profile digest. Equivalent pinned aliases therefore share numerical draws while their raw-input
receipts remain distinct.
Opaque sample labels, reference labels, provenance, missing declarations, and unsupported
declarations remain receipt-bound but do not perturb numerical random streams.

The interval is a conservative envelope: independent Gaussian perturbations use each caller-supplied
fixed standard error, perturb left-censor limits as limits, take the configured 5th and 95th
quantiles, and then ensure the fitted point lies inside the published interval. It does not model
cross-protein covariance, batch effects, biological replicate variance, cohort heterogeneity, or
external calibration, so it must not be described as a validated biological 90% confidence interval.

## Support, interpretation, and explanations

The exploratory floor is five active markers, three exact observed markers, 10% active
coverage, effective sample size 3, and 20 observed background proteins. Below it, the method
abstains. The conservative `supported` tier additionally requires at least ten active markers,
five exact observed markers, 30% coverage, effective sample size 8, concordant location/rank
direction, and `q <= 0.10` for a non-neutral direction. Results above only the exploratory floor
are labeled `limited`.

Location support counts every exact observed marker but counts a left-censored marker only when its
upper limit constrains the fitted optimum. Nonbinding limits remain visible in evidence counts and
one-sided estimation, but do not inflate coverage or effective sample size used by the support gate.

The location interval controls classification: wholly above `+0.25` is activated, wholly below
`-0.25` is suppressed, wholly within `[-0.25,+0.25]` is neutral, and every crossing interval is
indeterminate. Method disagreement also forces indeterminate/limited output. No winner-take-all
GBM state label is produced; multiple supported programs remain a visible hybrid pattern.

Every program reports raw and effective evidence counts, protein eligibility, coverage,
bootstrap/permutation replicate counts, p/q values, top leave-one-marker influences, source or
rank-band ablations, method agreement, support tier, and abstention reasons. Mesenchymal,
neural, vascular, immune, and hypoxic bulk evidence remains explicitly vulnerable to tissue
origin confounding; this model does not deconvolve that origin.

## Interfaces

- `GET /v1/research/neftel-protein-programs/profile`
- `GET /v1/research/neftel-protein-programs/demo`
- `POST /v1/research/neftel-protein-programs/analyze`
- `POST /v1/research/neftel-protein-programs/verify`
- `glio-proteogen neftel-programs profile|demo|analyze|verify`

All operations are synchronous, bounded, stateless, research-use-only, and non-prescriptive.
Replay recomputes the request and compares profile, catalog/source, result digest, and complete
semantic content. Exact transport ceilings are published by the profile and deployment catalog.
