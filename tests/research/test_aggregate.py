from __future__ import annotations

import json
from pathlib import Path

from glio_proteogen.research.public_proteomics import (
    PDCMetadataClient,
    SourceManifest,
    SourceReference,
    aggregate_evidence,
    extract_fasta_structure,
    sha256_digest,
)

_ROOT = Path(__file__).parents[2]
_FIXTURE = _ROOT / "research" / "fixtures" / "pdc" / "pdc000204.metadata.json"


def test_aggregate_is_manifest_bound_deterministic_and_claim_free() -> None:
    response = _FIXTURE.read_bytes()

    def fixture_transport(
        _url: str, _payload: bytes, _timeout: float, _user_agent: str, _max_bytes: int
    ) -> tuple[int, bytes, str]:
        return 200, response, "application/json"

    client = PDCMetadataClient(transport=fixture_transport)
    snapshot = client.fetch("PDC000204", retrieved_at="2026-08-17T00:00:00Z")
    fasta = b">sp|P1|alpha\nMPEPTIDE\n"
    fasta_summary = extract_fasta_structure(fasta)
    manifest = SourceManifest(
        "research-pdc000204-v1",
        "2026-08-17T00:00:00Z",
        "metadata and bounded local structural feature research",
        (
            snapshot.source_reference,
            SourceReference(
                "local:fasta",
                "memory:fasta",
                "text/plain",
                sha256_digest(fasta),
                len(fasta),
                "2026-08-17T00:00:00Z",
                "test fixture",
            ),
        ),
        "PDC metadata lookup plus local FASTA structural extraction; no claim emission",
    )
    first = aggregate_evidence(manifest, snapshot, {"local:fasta": fasta_summary})
    second = aggregate_evidence(manifest, snapshot, {"local:fasta": fasta_summary})
    assert first.as_dict() == second.as_dict()
    assert first.structural_counts == (
        ("fasta_byte_length", len(fasta)),
        ("local_source_count", 1),
        ("pdc_aliquots_count", 111),
        ("pdc_cases_count", 111),
    )
    assert "protein" in " ".join(first.limitations)
    assert json.dumps(first.as_dict(), sort_keys=True)
