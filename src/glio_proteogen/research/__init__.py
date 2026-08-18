"""Research-only scientific foundations awaiting a frozen production ABI.

The package is deliberately separate from the contract modules.  It provides bounded,
reproducible primitives for inspecting public proteomics evidence, but it does not publish
protein, disease, or clinical claims and is not wired into the M03/M04 execution surfaces.
"""

from .evidence import EvidenceBundle, EvidenceRecord, aggregate_evidence
from .fasta import FastaEntry, digest_trypsin, read_fasta
from .mzml import Spectrum, parse_mzml
from .pdc import PdcClient, PdcFile, PdcStudySnapshot
from .protein import ProteinGroup, infer_protein_groups
from .quantification import PeptideQuant, median_normalize
from .search import Psm, SearchParameters, search_spectrum, target_decoy_qvalues

__all__ = [
    "EvidenceBundle",
    "EvidenceRecord",
    "FastaEntry",
    "PdcClient",
    "PdcFile",
    "PdcStudySnapshot",
    "PeptideQuant",
    "ProteinGroup",
    "Psm",
    "SearchParameters",
    "Spectrum",
    "aggregate_evidence",
    "digest_trypsin",
    "infer_protein_groups",
    "median_normalize",
    "parse_mzml",
    "read_fasta",
    "search_spectrum",
    "target_decoy_qvalues",
]
