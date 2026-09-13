# Longitudinal GBM phosphosite foundation

`kncc-paired-phosphosite-transition/1.0.0` is a source-locked, de-identified
research artifact fitted from the PDC000515 KNCC phosphoproteome. It is an
independent phosphosite recurrence-concordance axis exposed through a stateless
research runtime. It does not modify, merge with, or replace the PDC000514
protein model. The protein-adjusted occupancy-like and protein/phosphosite
fusion views are explicitly `not_fitted` in this artifact version.

The artifact is research-use-only. Its held-pair result measures internal
source-cohort direction concordance; it is not external validation, recurrence
prediction, diagnosis, prognosis, treatment guidance, or biochemical occupancy.

## Exact source boundary

The importer is bound to PDC000515 v1, immutable study UUID
`e5e0dd84-f982-46e3-b78a-5cb19eef31a8`. Only the six Protein Assembly files
were acquired. Raw spectra, processed spectra, PSMs, and quality-metric files
were not downloaded.

| File | PDC file UUID | Bytes | MD5 | SHA-256 |
| --- | --- | ---: | --- | --- |
| label | `ee9b645e-092e-4d94-9fb6-0b936e125039` | 522 | `4e6cc0cb78f8e9143abd078694c2e610` | `83f55a385bcc88d8780a75a8535c1e319e1c30633ff700e15ad87df5ae3792f4` |
| peptides | `61f74ed4-77b0-40b9-aa7b-b6eadc0673cd` | 63,695,733 | `e17edd5ac8b045dae10ee900c5f18bbb` | `c8c419582bf4a1e3c011f9c35cf7cbe453bda566f4e18364e9bb6d92e32a206e` |
| phosphopeptide TMT11 | `0bfd4904-153a-4eb0-ae99-7e9667fe79e4` | 39,476,036 | `53fc6e9689d48dcc0875947787b40faf` | `d513fe4ca28b70f873d28ecab563c758a1ffd3fb903fd5ebe7eba2f97b43eba8` |
| phosphosite TMT11 | `dd668a70-2c1d-413e-b439-50d7aa47fd74` | 35,462,701 | `367c076701733fd37b1965f3cb65bd18` | `0bae05b8b80ea68d62acd25d89d2fef4b33d06a747dc8d89399ead62780c29fe` |
| sample map | `355422f5-e199-4f02-a37e-17e9791bc49e` | 203,737 | `0768c7087da1c0b354ea6208b1ff5c77` | `71e6b8e88cb1920b6792c3c7c712fe740516d838b9c7fa8fe5d1c9ccbb82bef1` |
| summary | `73e6eb70-7489-4469-ac7f-20ac095fa63d` | 3,160,731 | `e5f6e2dea921a9560a5e63b03ce5b345` | `e79c8220875713eee3d9ab7956329e1d54b748a0382f0c40abddc6e21f628c3c` |

The canonical metadata lock contains the exact study catalog, versioned study,
180 biospecimen records, all 1,064 study files and their 1,272,495,437,200
total bytes, the protocol record, and 22 experimental-design rows. It excludes
HTTP metadata and expiring signed URLs. Its 708,545 canonical bytes have
SHA-256 `1b248983791886a9b4522de07d96abb517c416d793b789d435544745dbe6ed34`;
an independent live recapture was byte-identical.

## Cohort and measurement semantics

The versioned source contains 178 biological specimens in 89 nominal T1/T2
groups. One sample-type disagreement is excluded, leaving 88 strict paired
patients. Seven specimens occur in more than one plex; their channels are
median-collapsed within the exact specimen before T2-minus-T1 differencing.
They are never counted as independent patients.

The phosphosite matrix contains 24,015 unique ENSP-versioned site groups and
588,984 finite paired deltas. Blank cells stay missing, and a paired delta exists
only when both time points are observed. Source composite groups remain
indivisible: 21,475 single-site, 2,290 two-site, and 250 three-site groups. The
importer never fabricates single-residue measurements from a composite group.

HGNC mapping accepts an exact approved symbol or exactly one previous/alias
target; ambiguous and unresolved mappings abstain. The optional SPHINKS
crosswalk additionally requires exact site-group and modified-peptide agreement.
It maps 8,779 rows exactly, 608 of which have a current frozen signature
membership. Gene plus residue number alone is never sufficient.

## Fitted model and honest evaluation

For each training fold, the importer:

1. estimates a robust paired T2-minus-T1 center with iterative Huber weights;
2. estimates a MAD scale with a training-derived lower floor;
3. admits sites observed in at least 60% of training pairs;
4. ranks standardized effects after support shrinkage;
5. chooses 32, 64, 128, or 256 retained features inside three-fold inner
   patient-grouped validation; and
6. scores held patients only when at least half of the selected absolute weight
   and the corresponding feature-count floor are observed.

The five outer folds hold patients out before every data-dependent center,
scale, floor, eligibility, ranking, and feature-count choice. A leakage-spy test
checks all 15 inner fits and five outer fits. Adaptive nested validation supports
all 88 held pairs and gets 67 directions concordant (`0.761364`), with pooled
median sign margin `1.537256`. The outer folds choose 32 features three times and
64 twice. Those values quantify internal cohort consistency only. The balanced
label-swap value is the same `0.761364` derived sign-symmetry oracle, not
independent evidence.

The release-size selection repeats grouped five-fold selection under 20
deterministic alternate patient partitions. The modal choice is 32 features in
17/20 repeats (`0.85`); its Wilson 95% interval is
`[0.639581, 0.947631]`, above the locked `0.60` lower-bound gate. Repeated
predictions from one patient are not treated as independent. Because the
deterministic partition choices are correlated rather than independent
Bernoulli trials, this Wilson calculation is an internal, preliminary
partition-reproducibility heuristic—not a calibrated confidence interval or an
external stability guarantee. The final artifact therefore selects 32 of 4,225
eligible sites, and the full Huber fit converges in 18 iterations. As a
post-selection descriptive check only, a fixed 32-feature outer projection
supports 88/88 pairs and gets 66 directions concordant (`0.75`) with median sign
margin `1.602366`.

Sixty-four deterministic patient multinomial bootstrap replicates refit Huber
center, scale, support, eligibility, top-k selection, and coefficients. Each
sparse replicate carries its own aligned positive scales, and its selected
features are restricted to the full-fit release-eligible inventory. This is a
coupled coefficient and feature-selection uncertainty ensemble, not validation.
All 64 refits converge, but median selected-set Jaccard to the release model is
only `0.254902` (minimum `0.0`), below the `0.50` stability gate, and no
independent interval-coverage calibration cohort exists. Consequently the
runtime never upgrades an otherwise estimable result above `limited` under this
artifact; insufficient overlap instead produces `abstained`.

## Privacy, integrity, and licenses

The 14,712,589-byte packaged artifact contains aggregate feature statistics and
sparse coefficient replicates only. Numerical centers and scales are released
only for the 4,225 features meeting the 60%/53-pair floor. The other 19,790
features retain identity and support metadata but carry the explicit
`suppressed_insufficient_support` state with null center and scale. Bootstrap
selections cannot reference them. The artifact contains no patient matrix,
patient label, sample/case/aliquot UUID, or common unsalted
MD5/SHA-1/SHA-256/SHA-512 transform of the enumerated KNCC labels. Its only
UUIDs are the study UUID and six public file UUIDs. Production import requires
`verified_exact_snapshots`: parsing consumes the exact bytes whose locks were
validated, rather than reopening mutable source paths. Full source rebuild is
byte-identical.

Locked artifact identities:

- file SHA-256: `5060d34d214582395f55ef66f9026303f781019230e91cd01d51d60c4fd6255e`;
- canonical content: `sha256:d31635cc2c9f634679ebd913cf2e0911b0bdff1fb66d53533239e870d4b8624a`;
- source profile: `sha256:81901f97d258f500dfc0aa31bf533e5bf45fa7d0e611820a58756e7ed8b64216`;
- HGNC mapping: `sha256:07245f3fe73129607856b1a92671cce13932a53c95a19f16894daf4971449aa4`;
- SPHINKS crosswalk: `sha256:4d9d62c63361f285b45fff380588b37174663bfc702cef0587b705aaadebe8c4`;
- bootstrap ensemble: `sha256:75238c55a615d01301d96f4240933aab2c283f72892d48ac8d1c6521195de488`.

## Runtime boundary

The research router exposes `profile`, `demo`, `analyze`, and exact replay
`verify` operations under `/v1/research/longitudinal-gbm-phospho`. Matching CLI
commands live under `glio-proteogen longitudinal-gbm-phospho`. Requests require
an explicit assay attestation for TMT11 phosphoproteome sample-to-reference
`log2_ratio` values, exact ENSP-versioned source site groups, and indivisible
composite groups. The service is synchronous, bounded, cancellable, stateless,
and does not retain caller observations.

The point estimate projects exact consecutive-timepoint deltas through the
frozen sparse source axis. Missing and unsupported evidence is ignored rather
than made negative. One-sided censored evidence is retained as a signed bound
but excluded from the point estimate. Uncertainty directly projects the same
deterministic observation perturbation through each bootstrap replicate using
that replicate's coefficients and scales. Receipts expose measurement,
coefficient, and interaction variances, all three covariances, and a quantized
JSON-level decomposition residual. Measurement perturbations assume
featurewise-independent Gaussians and combine marginal from/to standard errors
in quadrature; this request cannot represent shared-reference, TMT, or batch
covariance. A future fully supported lane needs covariance blocks or another
correlated-error model. Drivers and composite/SPHINKS/top-driver
ablations are explanations of raw phosphosite concordance only. SPHINKS labels
are exact-identity annotations; this lane does not infer kinase activity.

PDC data use is CC BY 4.0 with attribution and change disclosure. Cite
[PDC000515](https://pdc.cancer.gov/pdc/study/PDC000515), the
[PDC data-use guidelines](https://pdc.cancer.gov/pdc/data-use-guidelines), and
Kim et al., *Cancer Cell* 2024,
[doi:10.1016/j.ccell.2023.12.015](https://doi.org/10.1016/j.ccell.2023.12.015).
HGNC mapping uses the source-locked complete set under CC0-1.0.
Downloaded profiles and results also carry direct CC-BY-4.0 attribution and the
adaptation notice for Migliozzi et al., *Nature Cancer* 2023,
[doi:10.1038/s43018-022-00510-x](https://doi.org/10.1038/s43018-022-00510-x),
because exact SPHINKS site labels and signature memberships may appear on
drivers. Those annotations do not turn this runtime into a SPHINKS or kinase
activity estimator.

## Cross-assay feasibility audit

A development-only exact join found all 88 PDC000515 pairs in PDC000514 and 178
shared biospecimen records with matching join fields. The protein and
phosphosite assay reference UUID sets nevertheless had zero overlap, so their
raw values cannot be pooled or described as biochemical occupancy. Of 23,463
phosphosite rows with an exact cognate protein, 4,086 rows across 1,847 genes met
the joint 53/88 support floor.

Leakage-safe 5x3 patient-grouped nested cross-validation recovered 71/88 held
directions with protein alone, 66/88 with phosphosite alone, 66/88 with the
direct protein-adjusted proxy, and 67/88 with nested late fusion. Fusion-only
and protein-only correct calls were 2 and 6 (exact McNemar `p=.289`). The strong
cross-view rank correlation (`rho=.856`) did not translate into incremental
held-pair evidence. Consequently, no adjusted or fusion model was admitted to
the release artifact. These numbers are a negative development feasibility
audit, not external validation; the runtime continues to emit no occupancy,
adjusted score, or fusion claim.
