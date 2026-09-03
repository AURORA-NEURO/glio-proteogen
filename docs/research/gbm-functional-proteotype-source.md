# GBM functional-proteotype source admission

## Admitted source

This catalog is an aggregate-only projection of Supplementary Tables 2d and 2e from
Migliozzi et al., “Integrative multi-omics networks identify PKCδ and DNA-PK as master
kinases of glioblastoma subtypes and guide targeted cancer therapy,” *Nature Cancer*
(2023), [DOI 10.1038/s43018-022-00510-x](https://doi.org/10.1038/s43018-022-00510-x),
PMCID `PMC9970878`.

The article and supplement are distributed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), subject to source credit
lines for any third-party material. The projection is an adaptation by GLIO-PROTEOGEN;
it is not endorsed by the source authors.

| Lock | Value |
|---|---|
| Source file | `43018_2022_510_MOESM2_ESM.xlsx` |
| Source size | `7,635,280` bytes |
| Source SHA-256 | `865a2db1ec99dcf047d6ff56b313a21607b840e5239bb9184739f6f6f217fb88` |
| Canonical catalog content digest | `sha256:1d4099b6d04bf3ea85ea268e551464b5aba220a081b6dffd69282bbb28cafb8b` |
| Catalog byte SHA-256 | `67dd0d660fcd88a4aa309dd398e3d5b9fec8c018bea1cad88158463edf6d8d6d` |

The source workbook is available from the
[PMC supplement endpoint](https://pmc.ncbi.nlm.nih.gov/articles/instance/9970878/bin/43018_2022_510_MOESM2_ESM.xlsx).
The workbook is not redistributed by this repository.

## Exact admitted tables

`Tab 14 - Supplementary Table 2d` (`A1:O154`) contains four independently ranked
protein blocks with the exact headers `Gene`, `Protein`, and `MWW score`:

- Glycolytic/plurimetabolic (`GPM`): 150 proteins
- Mitochondrial (`MTC`): 150 proteins
- Neuronal (`NEU`): 150 proteins
- Proliferative/progenitor (`PPR`): 150 proteins

All 600 source gene identifiers are pairwise disjoint across the four lists. No block
contains a duplicate gene or source protein label. Scores are finite, positive, and
non-increasing in source-row order. `gene_symbol` preserves the source `Gene` cell;
`source_protein_label` preserves the source `Protein` cell. The latter is deliberately
not called a protein symbol because the source includes descriptive or legacy labels such
as `profilin 1`, `ECGF1`, and `mGluR7`. No identifier normalization is performed here.

`Tab 15 - Supplementary Table 2e` (`A1:S276`) contains the exact headers
`Biological pathway`, `logitNES`, `pValue`, and `qValue`. Its aggregate pathway counts are:

- `GPM`: 243
- `MTC`: 107
- `NEU`: 272
- `PPR`: 204

Every block is contiguous and has no within-block duplicate or partial row. All `logitNES`,
`pValue`, and `qValue` cells are finite; each p value is in `(0, 1]`, and each q value is in
`[pValue, 1]`. Forty-nine rows repeat a pathway label already present under another axis;
these cross-axis occurrences are legitimate source context and remain separate source-ranked
records.

## Admission and interpretation boundary

The catalog contains only the 600 aggregate Table 2d signature rows and 826 aggregate
Table 2e pathway rows. It contains no patient identifier, sample identifier, specimen
metadata, per-sample measurement, or patient-by-feature matrix. Other workbook sheets are
not projected.

Table 2d MWW scores are source ranking scores, not probabilities or calibrated effect sizes.
Table 2e values are cohort-level source results and do not provide gene-set memberships or
sample-level pathway measurements. Runtime code should therefore treat Table 2e as source
cohort pathway context/anchors, not as direct evidence for an individual request and not as
independent validation of Table 2d.

The builder checks exact source bytes before parsing, rejects formulas and malformed or
partial rows, locks worksheet titles/dimensions/headers/counts, rejects non-finite numbers and
duplicate identifiers, and preserves source list order. It binds a canonical content digest
over the whole catalog except the digest field itself.

Reproduce or verify the checked artifact with:

```powershell
python tools/import_gbm_functional_proteotype.py `
  --source C:\path\to\43018_2022_510_MOESM2_ESM.xlsx `
  --output src/glio_proteogen/research/gbm_functional_proteotype/data/gbm_functional_proteotype_catalog.v1.json `
  --check
```
