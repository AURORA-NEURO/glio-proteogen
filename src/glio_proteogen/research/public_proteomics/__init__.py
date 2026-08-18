"""Bounded public-proteomics research primitives.

These helpers summarize public metadata and local file structure. They do not
emit protein identity, abundance, proteoform, clinical, or glioma claims.
"""

from glio_proteogen.research.public_proteomics.aggregate import (
    EvidenceAggregate,
    FeatureRecord,
    aggregate_evidence,
)
from glio_proteogen.research.public_proteomics.formats import (
    FastaStructure,
    FormatError,
    MzIdentMlStructure,
    MzMlStructure,
    extract_fasta_structure,
    extract_mzidentml_structure,
    extract_mzml_structure,
)
from glio_proteogen.research.public_proteomics.pdc import (
    PDCClientConfig,
    PDCError,
    PDCMetadataClient,
    PDCSnapshot,
    PDCStudyMetadata,
)
from glio_proteogen.research.public_proteomics.provenance import (
    ProvenanceError,
    SourceManifest,
    SourceReference,
    canonical_json_bytes,
    sha256_digest,
    verify_file_reference,
)

__all__ = [
    "EvidenceAggregate",
    "FastaStructure",
    "FeatureRecord",
    "FormatError",
    "MzIdentMlStructure",
    "MzMlStructure",
    "PDCClientConfig",
    "PDCError",
    "PDCMetadataClient",
    "PDCSnapshot",
    "PDCStudyMetadata",
    "ProvenanceError",
    "SourceManifest",
    "SourceReference",
    "aggregate_evidence",
    "canonical_json_bytes",
    "extract_fasta_structure",
    "extract_mzidentml_structure",
    "extract_mzml_structure",
    "sha256_digest",
    "verify_file_reference",
]
