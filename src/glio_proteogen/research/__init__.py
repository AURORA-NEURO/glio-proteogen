"""Research-only scientific foundations awaiting a frozen production ABI.

The package is deliberately separate from the contract modules.  It provides bounded,
reproducible primitives for inspecting public proteomics evidence, but it does not publish
protein, disease, or clinical claims and is not wired into the M03/M04 execution surfaces.
"""

from .cohort import (
    CohortGroupQc,
    CohortSampleQc,
    ResearchCohortRequest,
    ResearchCohortResult,
    ResearchCohortSample,
    replay_research_cohort,
    run_research_cohort,
)
from .evidence import EvidenceBundle, EvidenceRecord, aggregate_evidence
from .fasta import FastaEntry, digest_trypsin, read_fasta
from .mzml import Spectrum, parse_mzml
from .pdc import PdcClient, PdcFile, PdcSourceReceipt, PdcStudySnapshot
from .pipeline import (
    ResearchRunRequest,
    ResearchRunResult,
    bind_pdc_mzml_source,
    replay_research_protein_inference,
    run_research_protein_inference,
)
from .protein import (
    ProteinGroup,
    ProteinGroupCandidate,
    ProteinGroupFdrSummary,
    infer_protein_group_candidates,
    infer_protein_groups,
)
from .public_proteomics.provenance import SourceReference
from .quantification import (
    PeptideQuant,
    ProteinGroupQuant,
    median_normalize,
    quantify_matched_ions,
    quantify_protein_groups,
)
from .search import (
    FdrSummary,
    Psm,
    SearchParameters,
    search_spectrum,
    summarize_target_decoy,
    target_decoy_qvalues,
)

__all__ = [
    "CohortGroupQc",
    "CohortSampleQc",
    "EvidenceBundle",
    "EvidenceRecord",
    "FastaEntry",
    "FdrSummary",
    "PdcClient",
    "PdcFile",
    "PdcSourceReceipt",
    "PdcStudySnapshot",
    "PeptideQuant",
    "ProteinGroup",
    "ProteinGroupCandidate",
    "ProteinGroupFdrSummary",
    "ProteinGroupQuant",
    "Psm",
    "ResearchCohortRequest",
    "ResearchCohortResult",
    "ResearchCohortSample",
    "ResearchRunRequest",
    "ResearchRunResult",
    "SearchParameters",
    "SourceReference",
    "Spectrum",
    "aggregate_evidence",
    "bind_pdc_mzml_source",
    "digest_trypsin",
    "infer_protein_group_candidates",
    "infer_protein_groups",
    "median_normalize",
    "parse_mzml",
    "quantify_matched_ions",
    "quantify_protein_groups",
    "read_fasta",
    "replay_research_cohort",
    "replay_research_protein_inference",
    "run_research_cohort",
    "run_research_protein_inference",
    "search_spectrum",
    "summarize_target_decoy",
    "target_decoy_qvalues",
]
