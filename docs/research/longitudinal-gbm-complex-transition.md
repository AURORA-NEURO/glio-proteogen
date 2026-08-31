# Longitudinal GBM Reactome participant-set transition model

## Status and claim ceiling

`kncc-reactome-complex-transition/1.0.0` is an independent, research-only
protein-transition concordance lane. Its fitted model is
`kncc-reactome-complex-transition-factor-model/1.0.0`. For each of 28 frozen
Reactome participant sets, it asks whether consecutive caller-supplied protein
changes agree with a robust rank-one member-transition pattern fitted from 104
strict PDC000514 primary/recurrent GBM pairs.

It is independent as an algorithm and receipt, not as an evidence source: it
reuses the admitted PDC000514 cohort and therefore does not add an independent
validation population.

The supported claim is **source-cohort Reactome participant-set protein-transition
concordance only**. A participant-set coordinate is not evidence of physical
complex assembly, biochemical activity, member essentiality, stoichiometric
occupancy, pathway flux, causal mechanism, clinical state, recurrence, prognosis,
or treatment response. Reactome names can encode phosphorylation, nucleotide,
ligand, and compartment states that bulk protein abundance cannot establish.
Internal held-patient/held-member reconstruction is not external validation.

## Exact source binding and privacy boundary

The protein evidence comes from Kim et al., *Integrated proteogenomic
characterization of glioblastoma evolution*, Cancer Cell 2024, DOI
`10.1016/j.ccell.2023.12.015`, through PDC study `PDC000514`. The source catalog
binds study-version UUID `524d5116-b6de-4e36-892a-e35dba7d0170`, the exact
104-pair parent protein model `kncc-paired-protein-transition/1.0.0`, and these
parent locks:

| Bound parent object | Digest |
|---|---|
| Versioned PDC source manifest | `sha256:03d41fffeb04749296a95bd5cd5dd5829ddedc5f8f791941c011b94d6836a247` |
| Parent source-file lock | `sha256:0f96d71db83a90934f38960ebd41e7580e817c435bf7e03479b061a0a68d6964` |
| Parent fitted artifact bytes | `sha256:cc965d9e9d0f7ab3e1ec7dda151bc3d5b442bbbd8cab12ee4b0f3497e860ae40` |
| Parent fitted content | `sha256:5583ee3a1d75bcd3997d12ff2102ec19fd83e49b2ec98f4f2bd9a0b6475d92a3` |
| Parent 11,312-gene feature space | `sha256:d585de04d6da666f03cc66e2d3ae8395e9b9cbb1cf2409a7e0721f8b9e3ea148` |

Complex membership and direct pathway annotations come from exact local
Reactome release 97 files. The release number is an explicit local-cache
attestation; the following bytes are authoritative:

| Reactome V97 file | Bytes | SHA-256 |
|---|---:|---|
| `ComplexParticipantsPubMedIdentifiers_human.txt` | 3,690,987 | `ad536e76c39772964a4e225a848acfce6c1e0f3232393d903bc59358a1c8987c` |
| `Complex_2_Pathway_human.txt` | 1,168,246 | `99af18181f9e79f54a136235339142421d1a4ccaa7535f92abad63c0dfde95c3` |
| `ReactomePathways.txt` | 1,592,393 | `f6d7a2bf89b5bcfe0250a0bc7f51bff94641447911712b8ff129f5b55e52df3a` |

Exact UniProt identifiers are projected to approved HGNC symbols with
`hgnc_complete_set.txt` (16,948,224 bytes, SHA-256
`854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270`).
PDC material is attributed as CC-BY-4.0; the Reactome annotations and HGNC
identifier set are recorded as CC0-1.0.

The canonical source artifact
`kncc_reactome_complex_transition_source.v1.json` is 96,157 bytes, with byte
SHA-256 `03fc954944af058d6f8d4ec629e16615555791642b7d91bc1d0d1455e1dbcf30`
and content digest
`sha256:5719f23be05e7b1603cd5ba56deb638f90300686ada786bec22a2201a7f99124`.
The fitted artifact `kncc_reactome_complex_transition_model.v1.json` is 245,014
bytes, with byte SHA-256
`f0895efa245ddaaeb324ce3d6c32c8bab9b2abd612a8ad51bd086af97c440676`
and content digest
`sha256:8465d0c5db70e1cdd3dab08b3646a7c023078c746c96c054bfa3888e8e80e0d2`.

Neither artifact bundles patient measurements, identifiers or identifier
hashes, fold assignments, patient factor coordinates, predictions, residuals,
or bootstrap resample indices. The importer uses those records only inside the
controlled local build.

## Repository-authored pilot panel

The panel is repository-authored pilot coverage, not a Reactome-provided GBM
complexome and not an exhaustive inventory. It is a prespecified
repository-authored pilot panel informed by public glioma biology and the
PDC000514 source paper. The fixed panel is selected without reading abundance
arrays during import; that procedural separation is not demonstrated outcome
independence. Each of the eleven mechanism domains has one `domain_anchor`;
additional `supporting_mechanism` rows widen the authored source coverage.
Selection prefers physiological entities and excludes mutation-, fusion-,
inhibitor-, and treatment-specific entities.

Every admitted row has an exact stable Reactome identifier and an exact direct
`Complex_2_Pathway_human.txt` binding to its declared anchor. No inferred
transitive pathway membership or descendant closure is added. The assay gate
requires 3--24 source protein genes, at least three mapped parent features, at
least three eligible parent features, and at least 50% parent-feature mapping.
The fitted lane uses 146 eligible member slots across the 28 rows, representing
120 unique parent features; repeated genes remain repeated where Reactome sets
overlap.

| Pilot domain | Reactome ID | Exact source participant-set name | Tier | Fitted features |
|---|---|---|---|---:|
| `egfr_erbb_signaling` | `R-HSA-179791` | EGF-like ligands:p-6Y-EGFR:GRB2:p-5Y-GAB1:PI3K [plasma membrane] | `domain_anchor` | 5 |
| `pdgf_signaling` | `R-HSA-381954` | PDGF:Phospho-PDGFR receptor dimer:Nck [plasma membrane] | `domain_anchor` | 4 |
| `pi3k_akt` | `R-HSA-114540` | RAC1:GTP,RAC2:GTP,RHOG:GTP:PI3K alpha [plasma membrane] | `domain_anchor` | 6 |
| `pi3k_akt` | `R-HSA-437110` | PI3K beta [cytosol] | `supporting_mechanism` | 3 |
| `mtor_energy_sensing` | `R-HSA-377400` | mTORC1 [cytosol] | `domain_anchor` | 3 |
| `mtor_energy_sensing` | `R-HSA-198626` | mTORC2 [cytosol] | `supporting_mechanism` | 5 |
| `mtor_energy_sensing` | `R-HSA-380967` | LKB1:STRAD:MO25 [cytosol] | `supporting_mechanism` | 5 |
| `raf_mapk` | `R-HSA-5672728` | dephosphorylated inactive RAFS:YWHAB dimer [cytosol] | `domain_anchor` | 4 |
| `raf_mapk` | `R-HSA-5674131` | WDR83:LAMTOR2:LAMTOR3:activated RAF:p-2S MAP2K:p-T,Y MAPK complex [endosome membrane] | `supporting_mechanism` | 10 |
| `wnt_pcp` | `R-HSA-4551543` | N4GlycoAsn-PalmS WNT5A:ROR2:VANGL2 [plasma membrane] | `domain_anchor` | 3 |
| `wnt_pcp` | `R-HSA-3858469` | pp-DVL:RAC:GTP [plasma membrane] | `supporting_mechanism` | 6 |
| `wnt_pcp` | `R-HSA-3858472` | ppDVL:DAAM1 [cytosol] | `supporting_mechanism` | 4 |
| `wnt_pcp` | `R-HSA-3965386` | ppDVL:DAAM1:PFN1 [cytosol] | `supporting_mechanism` | 5 |
| `cell_cycle` | `R-HSA-141410` | MCC:APC/C complex [cytosol] | `domain_anchor` | 17 |
| `cell_cycle` | `R-HSA-1363265` | PP2A [nucleoplasm] | `supporting_mechanism` | 6 |
| `cell_cycle` | `R-HSA-2484812` | p-Ac-Cohesin:PDS5:WAPAL [cytosol] | `supporting_mechanism` | 8 |
| `cell_cycle` | `R-HSA-2520845` | CDK1 Phosphorylated Condensin I [cytosol] | `supporting_mechanism` | 5 |
| `dna_repair` | `R-HSA-5358511` | MLH1:PMS2:MSH2:MSH6:ATP:PCNA:DNA containing 1-2 base mismatch [nucleoplasm] | `domain_anchor` | 5 |
| `dna_repair` | `R-HSA-3785763` | DNA DSBs:MRN [nucleoplasm] | `supporting_mechanism` | 3 |
| `dna_repair` | `R-HSA-75907` | PRKDC:XRCC5:XRCC6:DNA DSB ends [nucleoplasm] | `supporting_mechanism` | 3 |
| `hypoxia_vhl` | `R-HSA-1234141` | VHL:EloB,C:CUL2:RBX1 [nucleoplasm] | `domain_anchor` | 5 |
| `hypoxia_vhl` | `R-HSA-1234101` | hydroxyPro-HIF-alpha:VHL:EloB,C:CUL2:RBX1 [nucleoplasm] | `supporting_mechanism` | 5 |
| `ecm_adhesion` | `R-HSA-1604373` | MMP14:TIMP2:MMP2 intermediate form [plasma membrane] | `domain_anchor` | 3 |
| `ecm_adhesion` | `R-HSA-2327790` | Integrin alpha5beta1:Fibronectin matrix [plasma membrane] | `supporting_mechanism` | 3 |
| `ecm_adhesion` | `R-HSA-215995` | Integrin alpha7beta1:Laminin-211, 221, 411, 512, 521 [plasma membrane] | `supporting_mechanism` | 8 |
| `innate_inflammation` | `R-HSA-202513` | CHUK:p-S177,S181-IKBKB:IKBKG [cytosol] | `domain_anchor` | 3 |
| `innate_inflammation` | `R-HSA-1834956` | STING:TBK1:IRF3 [cytoplasmic vesicle membrane] | `supporting_mechanism` | 3 |
| `innate_inflammation` | `R-HSA-9709857` | MAVS:TOMM70:HSP90:TBK1:IRF3 [mitochondrial outer membrane] | `supporting_mechanism` | 6 |

The source catalog preserves exact UniProt/HGNC member bindings, direct pathway
rows, PubMed identifiers, selected parent/child nesting, same-family eligible
member Jaccard overlap, inverse panel-membership degree, and eleven
leave-family-out definitions. Those are transparent sensitivity metadata. They
do not identify essential subunits or biological knockout interventions.

## Robust source fit

For source patient group \(i\) and eligible member \(j\), the input transition is

\[
\Delta_{ij}=T2_{ij}^{\mathrm{recurrent}}-T1_{ij}^{\mathrm{primary}},
\qquad z_{ij}=\Delta_{ij}/s_j.
\]

`Unshared Log` protein abundance is primary. The training-only member scale
\(s_j\) is MAD-derived with a support-adjusted floor; the Huber training location
is retained only as a baseline. It is **not** subtracted from \(\Delta_{ij}\).
Blank values remain missing.

Each participant set is fitted independently with a missing-aware, uncentered
rank-one model. For patient coordinates \(f_i\), member loadings \(l_j\), and
source reliabilities \(r_j\), the fitted objective is

\[
\sum_{(i,j)\;\mathrm{finite}} r_j\,
\rho_{1.345}(z_{ij}-f_i l_j)
+\tfrac12(0.075)\sum_i f_i^2
+\tfrac12(0.025)\sum_j l_j^2.
\]

Deterministic alternating Huber IRLS updates coordinates and loadings. Each
sweep uses damping `0.8` and backtracking down to `0.000244140625`; objective
increase is rejected above `1e-12`. The solver permits 160 iterations and
requires either maximum parameter change at most `1e-6`, or relative objective
drop at most `1e-5` with maximum change at most `0.005`. An analytic reciprocal
rescaling minimizes the two ridge penalties without changing predictions.

The stored loading has Euclidean norm one. Its sign is oriented to have a
non-negative dot product with the training source recurrence effect; the
lexically maximal absolute loading breaks an exact zero tie. This resolves the
otherwise arbitrary factor sign and scale. It does not give the coordinate a
biochemical direction beyond agreement with the fitted source transition.

## Patient-grouped held-member evaluation

The internal evaluation uses eight deterministic outer folds of 13 patient
groups. Fold assignment is a salted SHA-256 ordering followed by balanced
round-robin allocation. All preprocessing, scales, reliabilities, and rank-one
loadings are refitted on the seven training folds.

For every finite member in each held patient, that member is masked. A convex
Huber-ridge coordinate is solved by derivative bisection from at least two other
finite members, and the masked member is reconstructed. Training-center and
zero-transition predictions are evaluated on the same held values. Direction
accuracy is the sign agreement between the held standardized transition and
its reconstruction; exact zeros do not enter its denominator.

| Locked internal metric | Value |
|---|---:|
| Held patient groups | 104 |
| Evaluated held members | 14,988 |
| Insufficient-support held coordinates | 56 |
| Factor-model standardized MAE / RMSE | 0.6989814224 / 0.9942393988 |
| Training-center standardized MAE / RMSE | 0.8769685109 / 1.1877179373 |
| Zero-transition standardized MAE / RMSE | 0.9407301748 / 1.2532743202 |
| Relative MAE gain over training center | 0.2029572172 |
| Relative MAE gain over zero transition | 0.2569799065 |
| Held-member direction accuracy | 0.7255137443 |
| Median / minimum outer loading cosine | 0.9984219613 / 0.2436759429 |
| Patient-cluster median relative gain | 0.1489483703 |
| Nominal patient-cluster 90% interval | [0.0990936656, 0.1805654575] |
| Patient groups with positive relative gain | 0.8173076923 |
| Nonconverged preprocessing / factor / coordinate fits | 0 / 0 / 0 |

The patient-cluster interval uses 20,000 deterministic patient-group resamples
with seed `20260830`; neither cluster values nor resample indices are bundled.
The low minimum outer loading cosine shows that at least one participant set is
unstable in an outer fold even though the panel aggregate improves both
baselines. Per-set gain and loading-stability evidence therefore remains part of
the runtime support decision. These metrics are same-cohort reconstruction
evidence, not external predictive validation.

## Runtime coordinate and evidence semantics

Runtime accepts two to sixteen ordered protein profiles on the exact
PDC000514-compatible TMT11, unshared-peptide, log2-ratio scale. For each
consecutive pair:

- observed to observed gives an exact delta;
- observed to left-censored gives an upper bound;
- left-censored to observed gives a lower bound;
- two censored limits are uninformative;
- a participant set with only one-sided bounds abstains because the ridge-selected
  minimum-norm point is not a two-sided identification interval; and
- missing and unsupported observations are excluded and never become zero or
  negative evidence.

For active member \(j\), runtime again uses \(z_j=\Delta_j/s_j\), without
subtracting the stored training center. Its reliability is the geometric mean
of endpoint quality, multiplied by source reliability and divided by
\(1+(\mathrm{SE}(\Delta_j)/s_j)^2\), then bounded to \((0,1]\). Against the
locked rank-one loading \(l_j\), it minimizes

\[
\sum_j w_j\,\rho_{1.345}(l_j f-z_j)+\tfrac12(0.075)f^2.
\]

Upper- and lower-bound residuals contribute only when a prediction violates
their one-sided constraint. Deterministic NumPy IRLS uses damping `0.7`, at most
200 iterations, coordinate tolerance `1e-9`, objective-increase tolerance
`1e-10`, and explicit backtracking. The result exposes convergence, iteration,
objective, coherence/discordance, coefficient-mass, effective-sample-size, and
top exact-member contribution diagnostics.

Estimation requires at least three active member transitions, at least one exact
delta, at least three members with effective reliability `>= 0.05`, 50% of
quality-adjusted fitted absolute loading mass, effective sample size at least
two, a converged monotone solve, and at least 32 successful perturbation paths.
Effective reliability combines request quality, frozen source-member
reliability, and relative measurement error. The `0.05` cutoff is a
version-bound numerical support gate, not a biological quality threshold, and
is applied before output quantization. Consequently, uniformly negligible
quality weights cannot be promoted by a scale-invariant effective-sample-size
calculation. The nominal 90% interval determines the label:

- `source_recurrence_aligned` only when the lower bound is above `+0.25`;
- `source_primary_aligned` only when the upper bound is below `-0.25`;
- `stable` only when the whole interval lies inside `[-0.25,+0.25]`; and
- otherwise `indeterminate`.

Here `stable` is only an interval class around the fitted coordinate, not a
clinical stable-disease label. Full `supported` status additionally requires at
least 80% bootstrap class stability, minimum outer loading cosine at least
`0.8`, positive per-set held-member gain, a positive lower bound for the panel
patient-cluster gain interval, and no declared nesting or high same-family
overlap. An estimate that fails any of those maturity gates remains numeric but
`limited`; inadequate base evidence abstains.

## Bootstrap and ablation behavior

The fitted artifact stores 128 deterministic strict-patient-group bootstrap
fits generated by NumPy `PCG64`. Each seed uses the first 64 bits of an explicit
versioned seed-namespace digest plus the zero-based replicate index. The
namespace binds the exact source-file identity, complex order, complex
membership, and training recipe while excluding provenance prose, so a wording
correction cannot silently choose different resamples. Its digest is
`sha256:98e49ff6c56de72273f11f89a4f6ce3496becab28c7b3231fc2f9131cadd1758`.
All 128 fits converged. Their median loading cosine to the reference fit is
`0.9900832045`, but the minimum is `0.0042668415`; this source instability is
retained rather than hidden.

Runtime defaults to 64 perturbations and accepts 32--256. Each complex and
replicate uses three paired solves:

- measurement-only perturbs caller deltas at their reported standard errors
  while retaining the reference source model;
- fitted-model-only uses a deterministic source-bootstrap scale/loading draw
  with caller values unchanged; and
- combined uses the same measurement perturbation and source draw.

The 5th and 95th percentiles of successful combined solves form the interval,
widened if necessary to contain the point estimate. The result reports
measurement, fitted-model, and combined standard errors; the direct paired
sample covariance of the measurement-only and fitted-model-only streams; and
the absolute residual in
`Var(combined) = Var(measurement) + Var(fitted) + 2 Cov(measurement, fitted)`.
Because the combined solve is nonlinear, that closure residual need not be zero.
These quantities are sensitivity summaries, not calibrated posterior
probabilities.

Four request-level ablations are recomputed from active evidence:

1. replace primary `Unshared Log` source preprocessing with the independently
   fitted ordinary-`Log` source model;
2. replace fitted magnitudes with signed-uniform member loadings;
3. remove the request's highest-ranked exact member contribution; and
4. for overlapping families, remove active members shared with other selected
   participant sets in the same domain.

An ablation that leaves fewer than three informative members abstains rather
than fabricating a comparison. The offline ordinary-`Log` sensitivity fit
converged; its median and minimum loading cosine to the primary fit are
`0.9956991302` and `0.5771922777`, respectively. Source-catalog inverse-degree
weights and leave-family-out definitions remain separately available as overlap
metadata; they are not represented as biological interventions.

## Reproducibility boundary

Loading fails closed on canonical JSON, exact byte/content locks, duplicate
keys, tensor encoding and shape, every source/projection digest, member and
complex order, training recipe, bootstrap seed namespace, fold policy,
evaluation values, bootstrap row digests, privacy declarations, and NumPy
`2.5.2`. Runtime replay additionally
binds the input schema, algorithm constants, semantic engine AST, profile,
request, result, provenance, solver diagnostics, bootstrap semantics, and
ablation semantics.

The source importer is
`tools/import_kncc_reactome_complex_transition_source.py`; the fitted-model
importer is `tools/import_kncc_reactome_complex_transition_model.py`. Both use
only admitted local exact sources and perform no network access during the
reproducible build.
