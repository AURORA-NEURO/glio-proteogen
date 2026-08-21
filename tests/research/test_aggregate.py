from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from glio_proteogen.research.public_proteomics import (
    FastaStructure,
    FeatureRecord,
    MzIdentMlStructure,
    MzMlStructure,
    PDCMetadataClient,
    SourceManifest,
    SourceReference,
    aggregate_evidence,
    extract_fasta_structure,
    extract_mzidentml_structure,
    extract_mzml_structure,
    sha256_digest,
)
from glio_proteogen.research.public_proteomics.aggregate import _feature_record

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

    mismatched_reference = SourceReference(
        "local:fasta",
        "memory:fasta",
        "application/mzml",
        sha256_digest(fasta),
        len(fasta),
        "2026-08-17T00:00:00Z",
        "test fixture",
    )
    mismatched_manifest = SourceManifest(
        "research-pdc000204-media-mismatch-v1",
        "2026-08-17T00:00:00Z",
        "metadata and bounded local structural feature research",
        (snapshot.source_reference, mismatched_reference),
        "PDC metadata lookup plus local FASTA structural extraction",
    )
    with pytest.raises(ValueError, match="media type"):
        aggregate_evidence(mismatched_manifest, snapshot, {"local:fasta": fasta_summary})


def test_aggregate_accepts_each_supported_local_format() -> None:
    response = _FIXTURE.read_bytes()

    def fixture_transport(
        _url: str, _payload: bytes, _timeout: float, _user_agent: str, _max_bytes: int
    ) -> tuple[int, bytes, str]:
        return 200, response, "application/json"

    snapshot = PDCMetadataClient(transport=fixture_transport).fetch(
        "PDC000204", retrieved_at="2026-08-17T00:00:00Z"
    )
    local_payloads = {
        "local:fasta": b">x\nMPEP\n",
        "local:mzml": b"<mzML><spectrum id='s1'/></mzML>",
        "local:mzidentml": b"<MzIdentML><PeptideEvidence id='pe1'/></MzIdentML>",
    }
    summaries: dict[str, FastaStructure | MzMlStructure | MzIdentMlStructure] = {
        "local:fasta": extract_fasta_structure(local_payloads["local:fasta"]),
        "local:mzml": extract_mzml_structure(local_payloads["local:mzml"]),
        "local:mzidentml": extract_mzidentml_structure(local_payloads["local:mzidentml"]),
    }
    local_references = tuple(
        SourceReference(
            source_id,
            f"memory:{source_id}",
            "application/octet-stream",
            sha256_digest(payload),
            len(payload),
            "2026-08-17T00:00:00Z",
            "test fixture",
        )
        for source_id, payload in local_payloads.items()
    )
    manifest = SourceManifest(
        "research-pdc000204-all-formats-v1",
        "2026-08-17T00:00:00Z",
        "bounded format structure",
        (snapshot.source_reference, *local_references),
        "metadata plus local structural extraction",
    )
    aggregate = aggregate_evidence(manifest, snapshot, summaries)
    assert {record.format for record in aggregate.feature_records} == {
        "fasta",
        "mzidentml",
        "mzml",
    }
    assert aggregate.digest == sha256_digest(aggregate.as_dict())


def test_structural_receipts_reject_boolean_numeric_fields() -> None:
    boolean_length: object = True
    with pytest.raises(ValueError, match="byte_length"):
        FeatureRecord("local:fasta", "fasta", boolean_length, "sha256:" + "a" * 64, ())  # type: ignore[arg-type]
    boolean_attribute: object = True
    with pytest.raises(TypeError, match="string/integer"):
        FeatureRecord(
            "local:fasta",
            "fasta",
            1,
            "sha256:" + "a" * 64,
            (("record_count", boolean_attribute),),  # type: ignore[arg-type]
        )

    summary = extract_fasta_structure(b">x\nMPEP\n")
    forged = replace(summary, record_count=cast("int", True))  # noqa: FBT003
    with pytest.raises(TypeError, match="boolean structural attribute"):
        _feature_record("local:fasta", forged)


def test_public_receipt_constructors_close_identity_and_canonicalization() -> None:
    digest = "sha256:" + "a" * 64
    with pytest.raises(ValueError, match="unique names"):
        FeatureRecord(
            "local:fasta",
            "fasta",
            1,
            digest,
            (("record_count", 1), ("record_count", 2)),
        )
    with pytest.raises(ValueError, match="canonically ordered"):
        FeatureRecord(
            "local:fasta",
            "fasta",
            1,
            digest,
            (("total_residues", 1), ("record_count", 1)),
        )

    response = _FIXTURE.read_bytes()

    def fixture_transport(
        _url: str, _payload: bytes, _timeout: float, _user_agent: str, _max_bytes: int
    ) -> tuple[int, bytes, str]:
        return 200, response, "application/json"

    snapshot = PDCMetadataClient(transport=fixture_transport).fetch(
        "PDC000204", retrieved_at="2026-08-17T00:00:00Z"
    )
    fasta = b">x\nMPEP\n"
    manifest = SourceManifest(
        "research-pdc000204-constructor-closure-v1",
        "2026-08-17T00:00:00Z",
        "constructor closure",
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
        "PDC metadata plus local FASTA structural extraction",
    )
    aggregate = aggregate_evidence(
        manifest, snapshot, {"local:fasta": extract_fasta_structure(fasta)}
    )
    with pytest.raises(ValueError, match="aggregate_id"):
        replace(aggregate, aggregate_id="sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="structural_counts"):
        replace(
            aggregate,
            structural_counts=(
                ("fasta_byte_length", len(fasta) + 1),
                ("local_source_count", 1),
                ("pdc_aliquots_count", 111),
                ("pdc_cases_count", 111),
            ),
        )
    with pytest.raises(ValueError, match="limitations"):
        replace(aggregate, limitations=("forged",))
