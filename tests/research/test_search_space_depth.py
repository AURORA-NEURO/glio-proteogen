"""Adversarial tests for research-only target/decoy search-space receipts."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from typing import Any

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


def _rehashed(receipt: SearchSpaceReceipt, **changes: Any) -> SearchSpaceReceipt:
    candidate = replace(receipt, **changes)
    try:
        payload = candidate.as_dict()
    except AttributeError:
        return candidate
    payload.pop("search_space_digest")
    return replace(
        candidate,
        search_space_digest=sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
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


def test_pair_compatibility_is_independent_of_variable_modification_expansion() -> None:
    """Modification eligibility must not masquerade as cleavage mismatch."""

    entries = (
        FastaEntry("P1", "MSTPEPTIDER"),
        FastaEntry("DECOY_P1", "STPEPTIDER"),
    )
    receipt = build_search_space_receipt(
        b">P1\nMSTPEPTIDER\n>DECOY_P1\nSTPEPTIDER\n",
        entries,
        min_peptide_length=7,
        max_peptide_length=20,
        modification_rules=("UNIMOD:35",),
        max_variable_modifications=1,
    )

    assert receipt.pairs[0].target_peptides == receipt.pairs[0].decoy_peptides == 1
    assert receipt.pairs[0].status == "cleavage_compatible"
    assert receipt.modified_target_peptides > receipt.modified_decoy_peptides
    assert verify_search_space_receipt(receipt) == receipt


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


def test_receipt_rejects_unsupported_generation_and_modification_controls() -> None:
    entry = FastaEntry("P1", "MPEPTIDER")
    with pytest.raises(ValueError, match="unsupported decoy_strategy"):
        build_search_space_receipt(b"fixture", (entry,), decoy_strategy="random")
    with pytest.raises(ValueError, match="at least one"):
        build_search_space_receipt(b"fixture", ())
    with pytest.raises(ValueError, match="between zero and three"):
        build_search_space_receipt(b"fixture", (entry,), max_variable_modifications=4)
    with pytest.raises(ValueError, match="positive site limit"):
        build_search_space_receipt(
            b"fixture",
            (entry,),
            modification_rules=("UNIMOD:35",),
            max_variable_modifications=0,
        )
    with pytest.raises(ValueError, match="non-empty"):
        build_search_space_receipt(b"fixture", (FastaEntry(" ", "MPEPTIDER"),))


def test_receipt_verifier_rejects_strategy_and_digest_alias_tampering() -> None:
    receipt = build_search_space_receipt(
        b">P1\nMPEPTIDER\n",
        (FastaEntry("P1", "MPEPTIDER"),),
        decoy_strategy="reverse_protein",
    )
    with pytest.raises(ValueError, match="decoy strategy"):
        verify_search_space_receipt(_rehashed(receipt, decoy_strategy="random"))
    with pytest.raises(ValueError, match="digest alias"):
        verify_search_space_receipt(replace(receipt, digest="0" * 64))


def test_receipt_verifier_rejects_pairing_and_outer_tampering() -> None:
    entries = (FastaEntry("P1", "MPEPTIDER"), FastaEntry("DECOY_P1", "MPEPTIDER"))
    receipt = build_search_space_receipt(b"fixture", entries)
    with pytest.raises(ValueError, match="pairing digest"):
        verify_search_space_receipt(replace(receipt, pairing_digest="0" * 64))
    with pytest.raises(ValueError, match="search-space digest"):
        verify_search_space_receipt(replace(receipt, search_space_digest="0" * 64))
    assert isinstance(receipt, SearchSpaceReceipt)


def test_receipt_verifier_rejects_forged_source_identity_and_controls() -> None:
    entries = (FastaEntry("P1", "MPEPTIDER"), FastaEntry("DECOY_P1", "MPEPTIDER"))
    receipt = build_search_space_receipt(b"fixture", entries)
    with pytest.raises(ValueError, match="source SHA-256"):
        verify_search_space_receipt(_rehashed(receipt, source_sha256="g" * 64))
    with pytest.raises(ValueError, match="version"):
        verify_search_space_receipt(_rehashed(receipt, version="search-space-forged"))
    with pytest.raises(ValueError, match="unmatched protein"):
        verify_search_space_receipt(_rehashed(receipt, unmatched_target_proteins=1))


def test_receipt_verifier_rejects_noncanonical_pair_identity_and_status() -> None:
    entries = (FastaEntry("P1", "MPEPTIDER"), FastaEntry("DECOY_P1", "MPEPTIDER"))
    receipt = build_search_space_receipt(b"fixture", entries)
    forged_identity = replace(
        receipt,
        pairs=(replace(receipt.pairs[0], decoy_accession="DECOY_OTHER"),),
    )
    with pytest.raises(ValueError, match="pair target/decoy identity"):
        verify_search_space_receipt(_rehashed(forged_identity))
    forged_status = replace(
        receipt,
        pairs=(replace(receipt.pairs[0], status="cleavage_mismatch"),),
    )
    with pytest.raises(ValueError, match="pair status"):
        verify_search_space_receipt(_rehashed(forged_status))


def test_receipt_verifier_closes_every_structural_control_boundary() -> None:
    entries = (
        FastaEntry("P1", "MPEPTIDER"),
        FastaEntry("DECOY_P1", "MPEPTIDER"),
        FastaEntry("P2", "PEPTIDEK"),
        FastaEntry("DECOY_P2", "PEPTIDEK"),
    )
    receipt = build_search_space_receipt(b"fixture", entries)
    reversed_pairs = tuple(reversed(receipt.pairs))
    cases: tuple[tuple[dict[str, Any], str], ...] = (
        ({"digestion_enzyme": "pepsin"}, "enzyme"),
        ({"missed_cleavages": 99}, "digestion controls"),
        ({"pairs": []}, "pairs must be a tuple"),
        ({"pairs": reversed_pairs}, "canonically ordered"),
        ({"pairs": ("not-a-pair",)}, "DecoyPair"),
        ({"pairs": (replace(receipt.pairs[0], status="unknown"), *receipt.pairs[1:])}, "status"),
        ({"pairs": (replace(receipt.pairs[0], target_peptides=-1), *receipt.pairs[1:])}, "count"),
        ({"target_decoy_overlap_peptides": receipt.target_peptides + 1}, "overlap"),
        (
            {
                "modification_rules": ("invalid-rule",),
                "version": "search-space-receipt-3-modification-overlap",
                "max_variable_modifications": 1,
            },
            "modification rules",
        ),
        (
            {
                "modification_rules": ("UNIMOD:35",),
                "version": "search-space-receipt-3-modification-overlap",
                "max_variable_modifications": 0,
            },
            "modification controls",
        ),
        ({"max_variable_modifications": 1}, "modification controls"),
    )
    for changes, message in cases:
        with pytest.raises((TypeError, ValueError), match=message):
            verify_search_space_receipt(_rehashed(receipt, **changes))


def test_modified_receipt_rejects_self_rehashed_collision_and_unique_count_tampering() -> None:
    entries = (FastaEntry("P1", "MSTPEPTIDER"), FastaEntry("DECOY_P1", "MSTPEPTIDER"))
    receipt = build_search_space_receipt(
        b">P1\nMSTPEPTIDER\n>DECOY_P1\nMSTPEPTIDER\n",
        entries,
        min_peptide_length=7,
        max_peptide_length=20,
        modification_rules=("UNIMOD:35",),
        max_variable_modifications=1,
    )
    with pytest.raises(ValueError, match="modified overlap count"):
        verify_search_space_receipt(
            _rehashed(
                receipt,
                modified_target_decoy_overlap_peptides=receipt.modified_target_peptides + 1,
            )
        )
    with pytest.raises(ValueError, match="modified peptide count"):
        verify_search_space_receipt(
            _rehashed(receipt, modified_peptide_count=receipt.modified_peptide_count + 1)
        )


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
