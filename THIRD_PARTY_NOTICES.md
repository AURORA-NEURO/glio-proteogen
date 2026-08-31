# Third-party research data notices

The GLIO-PROTEOGEN source code is distributed under the repository owner's
stated license. That license does not replace the licenses or attribution terms
of bundled research-data derivatives. The following notices apply to the
identified assets and their transformed projections.

## PDC000514 and PDC000515 longitudinal GBM derivatives

- Source: Kim et al., *Integrated proteogenomic characterization of
  glioblastoma evolution*, Cancer Cell 42(3):358-377.e8 (2024),
  DOI `10.1016/j.ccell.2023.12.015`, PMCID `PMC10939876`.
- Data authority: NCI Proteomic Data Commons studies PDC000514 and PDC000515.
- License/data-use terms: CC BY 4.0 and the PDC data-use guidelines.
- Changes: GLIO-PROTEOGEN verifies exact PDC source files and metadata, excludes
  patient-level measurements and identifiers, and redistributes canonical
  de-identified aggregate coefficients, uncertainty ensembles, crosswalks, and
  validation summaries. These transformations are not endorsed by PDC or the
  source authors.

## SPHINKS/MK supplementary-table derivatives

- Source: Migliozzi et al., *Integrative multi-omics networks identify PKCdelta
  and DNA-PK as master kinases of glioblastoma subtypes and guide targeted
  cancer therapy*, Nature Cancer (2023), DOI `10.1038/s43018-022-00510-x`,
  PMCID `PMC9970878`.
- Copyright: The Author(s) 2023.
- License: CC BY 4.0.
- Changes: Supplementary Tables 5a, 5d, and 5e are transformed into canonical
  sorted site/peptide and kinase-signature projections with explicit HGNC
  mapping and duplicate-row preservation. The GLIO-PROTEOGEN master-kinase
  concordance, longitudinal phosphosite, and longitudinal signature-transition
  estimators are newly authored and are not ports or retrainings of SPHINKS/MK.
  The signature-transition view uses the same PDC000515 assay as its source fit
  and is explicitly not independent evidence.

## Neftel Table S2 marker projection

- Source: Neftel et al., *An Integrative Model of Cellular States, Plasticity,
  and Genetics for Glioblastoma*, Cell 178(4):835-849.e21 (2019), DOI
  `10.1016/j.cell.2019.06.024`.
- Source-use terms: no separate workbook license is asserted by this
  repository. The exact source bytes, citation, transformation, and marker
  catalog digests are recorded independently; downstream users remain
  responsible for the source terms.
- Changes: GLIO-PROTEOGEN extracts the exact ranked MES2, MES1, AC, OPC, NPC1,
  NPC2, G1/S, and G2/M marker identities, resolves them against a pinned HGNC
  authority, and projects them into bulk-protein concordance models. These
  independently authored models are not ports of a source estimator and do not
  convert bulk tissue into single-cell states or cell fractions.

## Diamandis GBM proteomic-axis source code

- The converted GBM proteomic-axis assets retain the upstream MIT notice and
  license embedded with that research package. See
  `docs/research/gbm-proteomic-axes.md` for the exact source and license digests.

## GBMPurity pretrained model and feature table

- Source: Thomas et al., *GBMPurity: A machine learning tool for estimating
  glioblastoma tumor purity from bulk RNA-sequencing data*, Neuro-Oncology
  27(6):1458-1473 (2025), DOI `10.1093/neuonc/noaf026`.
- Software/model authority: `https://github.com/scmpht/GBMPurity`, commit
  `af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950`.
- License: MIT; the complete upstream copyright and permission notice is
  retained inside the converted model artifact.
- Changes: GLIO-PROTEOGEN verifies the complete pinned Git tree and converts
  the six exact float32 PyTorch storages plus the ordered 5,829-gene length
  table into deterministic JSON. Runtime inference is an independently
  implemented NumPy forward pass; no source pickle is executed, no model is
  retrained, and no source single-cell or pseudobulk training records are
  redistributed. This adaptation is not endorsed by the source authors.

## Reactome pathway- and complex-annotation projections

- Source: Reactome human pathway annotation, locally admitted as release 97
  and pinned by exact GMT, pathway-metadata, hierarchy-relation,
  complex-participant, and complex-to-pathway hashes.
- Annotation license: CC0 1.0.
- Changes: GLIO-PROTEOGEN projects ten explicitly repository-authored,
  pre-outcome glioma mechanism slots onto zero-based indices in the locked
  PDC000514 HGNC feature axis. Only pathway identifiers, names, hierarchy
  parents, member counts/digests, and de-identified feature indices are
  redistributed. This is not a Reactome-provided GBM panel, and membership is
  not represented as activation, flux, causality, or clinical evidence.
- The complex-transition pilot separately projects 28 exact human complex
  annotations across 11 repository-authored pilot domains. It retains selected
  participant identifiers, direct pathway bindings, publication identifiers,
  nesting/overlap metadata, and de-identified PDC000514 feature indices. The
  panel is not an exhaustive GBM complexome. Membership is not represented as
  in-sample assembly, activity, essentiality, stoichiometry, or mechanism.

CC BY 4.0 text: <https://creativecommons.org/licenses/by/4.0/>.
PDC data-use guidelines: <https://pdc.cancer.gov/pdc/data-use-guidelines>.
CC0 1.0 text: <https://creativecommons.org/publicdomain/zero/1.0/>.
