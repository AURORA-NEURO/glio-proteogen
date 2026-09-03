# KNCC Reactome conditional-transition source admission

## Status and claim boundary

This document describes the independently verified source catalog consumed by
the fitted `kncc-reactome-conditional-transition/1.0.0` research lane. The
catalog binds a repository-authored, glioma-domain panel to exact Reactome
release-97 human pathway records and to the exact ordered HGNC feature axis of
the existing PDC000514 protein model. The compact source artifact itself still
contains no patient measurements, coefficients, effect estimates, or runtime
surface; those concerns are separately bound by the fitted artifact and public
contracts documented in
[`kncc-reactome-conditional-transition-model.md`](kncc-reactome-conditional-transition-model.md).

Pathway membership is annotation. It is not pathway activation, flux, causal
direction, recurrence prediction, treatment response, or clinical evidence.

## Exact source locks

Only locally cached inputs were consumed. No source was downloaded during this
admission.

| Source | Bytes | SHA-256 |
|---|---:|---|
| `ReactomePathways.gmt.zip` | 298,479 | `8c1dbc8578431da5d2d5118262718c60b553a9be3398e93658daa069e4a9afd4` |
| `gmt/ReactomePathways.gmt` | 1,032,186 | `89983d5c1f0af11c52edfeee7323eb425580ac6281d387a528562ab1787ce56b` |
| `ReactomePathways.txt` | 1,592,393 | `f6d7a2bf89b5bcfe0250a0bc7f51bff94641447911712b8ff129f5b55e52df3a` |
| `ReactomePathwaysRelation.txt` | 634,259 | `fd49a624d80c14eb37ae57a02e141d574d5ede3f60022bb99edbd909448a3f1e` |

The zip is required to contain exactly one `ReactomePathways.gmt` member, and
its decompressed bytes must exactly equal the separately cached GMT. The
parser admits exactly 2,883 human metadata records, 2,868 human GMT records,
and 2,899 human hierarchy relations.

The cache directory was labelled release 97 when acquired. The downloaded
files do not independently encode that release number, so the artifact states
this limitation: exact hashes are authoritative; the release label is an
acquisition-context attestation.

The PDC side is inherited through the fail-closed
`kncc-paired-protein-transition/1.0.0` catalog:

- study `PDC000514`, version UUID
  `524d5116-b6de-4e36-892a-e35dba7d0170`;
- parent content digest
  `sha256:5583ee3a1d75bcd3997d12ff2102ec19fd83e49b2ec98f4f2bd9a0b6475d92a3`;
- parent feature-space digest
  `sha256:d585de04d6da666f03cc66e2d3ae8395e9b9cbb1cf2409a7e0721f8b9e3ea148`;
- versioned PDC source-manifest digest
  `sha256:03d41fffeb04749296a95bd5cd5dd5829ddedc5f8f791941c011b94d6836a247`;
- 104 strict primary/recurrent patient groups and 11,312 ordered HGNC protein
  features.

## Pre-outcome panel rule

The ten mechanism slots were frozen before inspecting patient transition
effects. Each slot names one exact physiological Reactome stable ID. Patient
values, recurrence direction, fitted effect, accuracy, or enrichment do not
participate in selection. Assay admission then applies only an exact approved
HGNC-symbol intersection, with a source-size bound of 5–1,500 genes, at least
five mapped genes, and at least 65% mapping.

This is a repository-authored glioma-domain scope pinned to Reactome records;
it is not a Reactome-provided GBM panel.

| Order | Domain | Reactome V97 event | Source genes | PDC mapped | PDC eligible |
|---:|---|---|---:|---:|---:|
| 0 | EGFR | `R-HSA-177929` — Signaling by EGFR | 53 | 42 | 40 |
| 1 | PDGF | `R-HSA-186797` — Signaling by PDGF | 58 | 57 | 49 |
| 2 | PI3K/AKT | `R-HSA-198203` — PI3K/AKT activation | 9 | 7 | 7 |
| 3 | MTOR | `R-HSA-165159` — MTOR signalling | 52 | 50 | 48 |
| 4 | MAPK | `R-HSA-5683057` — MAPK family signaling cascades | 314 | 231 | 216 |
| 5 | cell cycle | `R-HSA-1640170` — Cell Cycle | 657 | 540 | 468 |
| 6 | DNA repair | `R-HSA-73894` — DNA Repair | 346 | 267 | 238 |
| 7 | hypoxia | `R-HSA-1234174` — Cellular response to hypoxia | 62 | 52 | 49 |
| 8 | extracellular matrix | `R-HSA-1474244` — Extracellular matrix organization | 321 | 251 | 221 |
| 9 | innate immunity | `R-HSA-168249` — Innate Immune System | 1,198 | 871 | 817 |

The artifact also retains 12 explicit nonselections. These include narrower,
broader, disease-mutant, and cancer-genotype alternatives. In particular,
`R-HSA-2173791` (TGF-beta receptor signaling in epithelial-to-mesenchymal
transition) is excluded because GBM is not epithelial, and `R-HSA-109581`
(Apoptosis) is not added post hoc merely to improve effect performance.

## Ordering and privacy

- The gene axis is the exact ordered parent feature array; its independent
  order digest is
  `sha256:db1c48250032a6ea68211dcfa388acc8fea5b874c13a75198b3eec15f0234c65`.
- The pathway order digest is
  `sha256:c8a1acae9b080feecb68d530b81f79ba673fcc6a7799baddb424349dcb1d95a0`.
- The pathway membership projection digest is
  `sha256:7a801d5787c16e40e6824965ef5c7a78d819e09c4a11da0700a5e319c64f37c1`.
- The patient axis is reproduced by lexicographically ordering complete T1/T2
  patient groups after the official versioned sample-type exclusions. The
  policy digest is
  `sha256:e9339a2020313ccd2c1ea7bf300ed8229ec9112d3e6f358aa1968762b761b4cf`.

Patient labels and hashes of individual patient/specimen labels are
deliberately not stored. Exact raw source hashes plus the deterministic policy
bind the patient ordering without creating a low-entropy pseudonym table.

All exposed arrays are tuples and all lookup maps are read-only mapping
proxies. Member indices are sorted, unique, in range, and independently
checked against the parent eligibility axis.

## Packaged artifact and replay

The canonical artifact is 34,279 bytes:

- file SHA-256:
  `8446a9d923e047f0d4df9d190daca18f20faa932c471710efb733b8e2b1e631c`;
- content digest:
  `sha256:0d0ad7b572aabed7049f302a44380166135cb2fed1527fe845a19457a8cbcdc6`;
- source-binding digest:
  `sha256:84732b0bb2c89e82285c7b10fd567c3612eb89ae3a36846df0d7b88b6be59584`;
- selection-candidate digest:
  `sha256:c7ae590f4a1a13bea24de8bb8e6c2bed0369f4d54ca0081bbef373071d766a7c`.

With the exact local sources present, regenerate it with:

```powershell
uv run python tools/import_kncc_reactome_transition_source.py `
  --pdc-source-dir ..\..\.tmp-longitudinal-gbm-source `
  --hgnc-source ..\..\.tmp-neftel-source\hgnc_complete_set.txt `
  --reactome-source-dir ..\..\.tmp-reactome-v97
```

The local replay test replaces both patient-transition arrays with unusable
sentinels before building the artifact; byte-identical reproduction therefore
also verifies that source admission never consults patient effects.

## Fitted-lane handoff

The fitted implementation remains additive and research-only. It refits
centering, scaling, global-transition adjustment, and conditional pathway
loadings inside patient-grouped training folds; packages a de-identified
patient-bootstrap ensemble; preserves one-sided censoring and missingness; and
exposes intervals, source-processing, global-axis, degree, unique-member,
overlap, and leave-pathway-out sensitivity plus deterministic replay.

The source catalog alone is not numerical evidence. The separate fitted
artifact, runtime engine, contracts, and same-cohort evaluation satisfy the
implementation requirements under the stricter claim name **conditional
source-cohort transition concordance**, never pathway activation or flux. See
[`kncc-reactome-conditional-transition-model.md`](kncc-reactome-conditional-transition-model.md)
for the exact recipe, modest evaluation result, gates, and limitations.
