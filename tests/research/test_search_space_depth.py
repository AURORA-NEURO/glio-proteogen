"""Adversarial tests for research-only target/decoy search-space receipts."""

from __future__ import annotations

from dataclasses import replace

import pytest
from evals.research_proteomics.run import build_scenario_request, scenarios

from glio_proteogen.research import (
    FastaEntry,
    SearchSpaceReceipt,
    build_search_space_receipt,
    replay_research_protein_inference,
    run_research_protein_inference,
    verify_search_space_receipt,
)


def test_receipt_binds_cleavage_aware_target_decoy_pairs() -> None:
    source = b">P1\nMPEPTIDER\n>DECOY_P1\nMPEPTIDER\n>P2\nPEPTIDEK\n>DECOY_ORPHAN\nPEPTIDEK\n"
    entries = (
        FastaEntry("P1", "MPEPTIDER"),
        FastaEntry("DECOY_P1", "MPEPTIDER"),
        FastaEntry("P2", "PEPTIDEK"),
        FastaEntry("DECOY_ORPHAN", "PEPTIDEK"),
    )
    receipt = build_search_space_receipt(
        source,
        entries,
        min_peptide_length=7,
        max_peptide_length=12,
    )
    assert receipt.version == "search-space-receipt-1"
    assert receipt.target_proteins == 2
    assert receipt.decoy_proteins == 2
    assert receipt.paired_proteins == 1
    assert receipt.cleavage_compatible_pairs == 1
    assert receipt.unmatched_target_proteins == 1
    assert receipt.unmatched_decoy_proteins == 1
    assert receipt.target_decoy_overlap_peptides == 2
    assert receipt.pairs[0].status == "cleavage_compatible"
    assert verify_search_space_receipt(receipt) == receipt


def test_receipt_marks_cleavage_mismatch_without_dropping_the_pair() -> None:
    entries = (
        FastaEntry("P1", "MPEPTIDERAARPEPTIDEK"),
        FastaEntry("DECOY_P1", "MPEPTIDER"),
    )
    receipt = build_search_space_receipt(
        b">P1\nMPEPTIDERAARPEPTIDEK\n>DECOY_P1\nMPEPTIDER\n",
        entries,
        min_peptide_length=7,
        max_peptide_length=20,
    )
    assert receipt.paired_proteins == 1
    assert receipt.cleavage_compatible_pairs == 0
    assert receipt.pairs[0].status == "cleavage_mismatch"


def test_receipt_is_order_stable_and_source_bound() -> None:
    entries = (FastaEntry("P1", "MPEPTIDER"), FastaEntry("DECOY_P1", "MPEPTIDER"))
    forward = build_search_space_receipt(b"fixture-a", entries)
    reverse = build_search_space_receipt(b"fixture-a", tuple(reversed(entries)))
    changed_source = build_search_space_receipt(b"fixture-b", entries)
    assert forward.as_dict() == reverse.as_dict()
    assert forward.search_space_digest != changed_source.search_space_digest
    assert forward.source_sha256 != changed_source.source_sha256


def test_receipt_rejects_duplicate_accessions_and_bad_source() -> None:
    entry = FastaEntry("P1", "MPEPTIDER")
    with pytest.raises(ValueError, match="unique"):
        build_search_space_receipt(b"fixture", (entry, entry))
    with pytest.raises(TypeError, match="immutable bytes"):
        build_search_space_receipt(bytearray(b"fixture"), (entry,))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="prefix"):
        build_search_space_receipt(b"fixture", (entry,), decoy_prefix=" ")


def test_receipt_verifier_rejects_pairing_and_outer_tampering() -> None:
    entries = (FastaEntry("P1", "MPEPTIDER"), FastaEntry("DECOY_P1", "MPEPTIDER"))
    receipt = build_search_space_receipt(b"fixture", entries)
    with pytest.raises(ValueError, match="pairing digest"):
        verify_search_space_receipt(replace(receipt, pairing_digest="0" * 64))
    with pytest.raises(ValueError, match="search-space digest"):
        verify_search_space_receipt(replace(receipt, search_space_digest="0" * 64))
    assert isinstance(receipt, SearchSpaceReceipt)


def test_pipeline_result_and_evidence_bind_search_space_receipt() -> None:
    scenario = scenarios()[0]
    result = run_research_protein_inference(build_scenario_request(scenario))
    receipt = result.search_space_receipt
    assert receipt is not None
    assert receipt.source_sha256 == result.fasta_sha256
    assert receipt.target_proteins == 1
    assert receipt.decoy_proteins == 0
    assert receipt.target_peptides == result.search_space_peptides
    assert result.as_dict()["search_space_receipt"] == receipt.as_dict()
    search_receipts = [
        item for item in result.evidence.records if item.evidence_id == "search-space:receipt"
    ]
    assert len(search_receipts) == 1
    assert search_receipts[0].payload_jsonable == receipt.as_dict()
    replayed = replay_research_protein_inference(build_scenario_request(scenario), result)
    assert replayed.search_space_receipt == receipt
