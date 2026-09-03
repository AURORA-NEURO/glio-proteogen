"""Locked source and normalization oracles for Neftel Table S2."""

from __future__ import annotations

from glio_proteogen.research.neftel_protein_programs import algorithm_profile
from glio_proteogen.research.neftel_protein_programs.catalog import (
    EXACT_SOURCE_PROGRAM_DIGEST,
    EXPECTED_CATALOG_ARTIFACT_DIGEST,
    EXPECTED_CATALOG_CONTENT_DIGEST,
    EXPECTED_PROGRAM_COUNTS,
    EXPECTED_PROTEIN_BACKGROUND_COUNT,
    EXPECTED_PROTEIN_BACKGROUND_DIGEST,
    HGNC_SHA256,
    SOURCE_SHA256,
    marker_catalog,
    normalize_symbol,
)


def test_exact_table_s2_source_programs_are_content_locked() -> None:
    catalog = marker_catalog()
    assert catalog.source_sha256 == SOURCE_SHA256
    assert catalog.hgnc_sha256 == HGNC_SHA256
    assert catalog.source_program_digest == EXACT_SOURCE_PROGRAM_DIGEST
    assert catalog.content_digest == EXPECTED_CATALOG_CONTENT_DIGEST
    assert catalog.artifact_digest == EXPECTED_CATALOG_ARTIFACT_DIGEST
    assert len(catalog.protein_background_symbols) == EXPECTED_PROTEIN_BACKGROUND_COUNT
    assert catalog.protein_background_digest == EXPECTED_PROTEIN_BACKGROUND_DIGEST
    assert {key: len(value) for key, value in catalog.programs.items()} == (
        EXPECTED_PROGRAM_COUNTS
    )
    assert {
        key: (markers[0].raw_symbol, markers[-1].raw_symbol)
        for key, markers in catalog.programs.items()
    } == {
        "MES2": ("HILPDA", "HSPA9"),
        "MES1": ("CHI3L1", "WWTR1"),
        "AC": ("CST3", "TSPAN7"),
        "OPC": ("BCAN", "GPR37L1"),
        "NPC1": ("DLL3", "SOX11"),
        "NPC2": ("STMN2", "BLCAP"),
        "G1/S": ("RRM2", "ZWINT"),
        "G2/M": ("CCNB1", "H2AFZ"),
    }


def test_hgnc_aliases_and_uniprot_eligibility_are_explicit() -> None:
    catalog = marker_catalog()
    assert normalize_symbol("WARS") == "WARS1"
    assert normalize_symbol("HMP19") == "NSG2"
    assert normalize_symbol("LPPR1") == "PLPPR1"
    assert normalize_symbol("PCDHGC3") == "PCDHGC3"
    pcdhgc3 = next(
        marker
        for marker in catalog.programs["OPC"]
        if marker.normalized_symbol == "PCDHGC3"
    )
    assert pcdhgc3.protein_eligible is True
    assert pcdhgc3.hgnc_id == "HGNC:8716"
    assert pcdhgc3.uniprot_ids == ("Q9UN70",)
    assert set(catalog.unsupported_non_protein_loci) == {
        "DLX6-AS1",
        "LOC150568",
        "MIAT",
        "SOX2-OT",
        "TMEM161B-AS1",
    }
    assert all(
        marker.uniprot_ids
        for markers in catalog.programs.values()
        for marker in markers
        if marker.protein_eligible
    )
    assert "CST3" in catalog.protein_background_symbols
    assert "SOX2-OT" not in catalog.protein_background_symbols


def test_profile_binds_equal_marker_policy_and_both_support_tiers() -> None:
    profile = algorithm_profile()
    constants = profile.constants
    assert constants.family_pooling_policy == "equal_source_program_equal_marker_mass_v1"
    assert constants.exploratory_minimum_active_markers == 5
    assert constants.exploratory_minimum_active_coverage == 0.10
    assert constants.exploratory_minimum_effective_sample_size == 3.0
    assert constants.supported_minimum_active_markers == 10
    assert constants.supported_minimum_active_coverage == 0.30
    assert constants.supported_minimum_effective_sample_size == 8.0
    assert profile.exact_source_program_digest == EXACT_SOURCE_PROGRAM_DIGEST
