"""Ownership, standards, privacy, and resource boundaries for M01-02."""

from __future__ import annotations

import csv
import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.policy import (
    DEMULTIPLEXABLE_KINDS,
    ENTITY_KINDS,
    MAX_ABSOLUTE_DEPTH,
    ORDINARY_TRANSITIONS,
    POOLABLE_KINDS,
    ordinary_transition_allowed,
)

pytestmark = pytest.mark.policy

ROOT = Path(__file__).parents[2]
FIXTURE_DIRECTORY = ROOT / "tests" / "fixtures" / "m01_02"
MANIFEST_PATH = FIXTURE_DIRECTORY / "manifest.json"
MODULE_DOCUMENT = ROOT / "docs" / "modules" / "M01-02.md"
HUMAN_MANIFEST = ROOT / "docs" / "modules" / "M01-02.manifest.md"
EVIDENCE_DOCUMENT = ROOT / "docs" / "evidence" / "M01-02.md"
TRACEABILITY_MATRIX = ROOT / "docs" / "traceability" / "M01-02.csv"

EXPECTED_KINDS = {
    "patient",
    "specimen",
    "aliquot",
    "section",
    "analyte",
    "run",
    "derived_object",
}
EXPECTED_TRANSITIONS = {
    ("collected_from", "patient", "specimen"),
    ("subdivided_from", "specimen", "specimen"),
    ("subdivided_from", "specimen", "aliquot"),
    ("subdivided_from", "aliquot", "aliquot"),
    ("sectioned_from", "specimen", "section"),
    ("sectioned_from", "aliquot", "section"),
    ("extracted_from", "specimen", "analyte"),
    ("extracted_from", "aliquot", "analyte"),
    ("extracted_from", "section", "analyte"),
    ("acquired_from", "analyte", "run"),
    ("computed_from", "run", "derived_object"),
    ("computed_from", "derived_object", "derived_object"),
}
EXPECTED_ADAPTER_PINS = {
    "W3C PROV-DM, PROV-O, and PROV-CONSTRAINTS": "2013-04-30 Recommendation",
    "SDRF-Proteomics": "1.0.1",
    "GA4GH Phenopacket schema": "2.0.0",
    "GA4GH Variation Representation Specification": "2.0.1",
    "DICOM PS3": "2026c",
    "ISA Model and Serialization Specifications": "1.0 (2016-10-28)",
}
EXPECTED_CAPS = {
    "request_bytes": 4_194_304,
    "nodes": 10_000,
    "lineage_edges": 40_000,
    "identity_assertions": 20_000,
    "component_nodes": 256,
    "evidence_total": 50_000,
    "evidence_per_assertion": 64,
    "lineage_depth_policy_ceiling": 64,
    "reported_issues": 1_000,
}
EXPECTED_SPECIAL_KINDS = {"aliquot", "analyte"}
FORBIDDEN_OUTPUT_PROPERTIES = {
    "all_omics_fusion",
    "all_omics_fusions",
    "ancestry",
    "date_of_birth",
    "diagnosis",
    "direct_patient_id",
    "genotype",
    "kinase_state",
    "kinship",
    "medical_record_number",
    "mrn",
    "patient_name",
    "raw_allele_counts",
    "raw_reads",
    "recommended_treatment",
    "sex",
    "treatment_recommendation",
}
FORBIDDEN_FIXTURE_KEYS = re.compile(
    r'"(?:date_of_birth|diagnosis|medical_record_number|mrn|patient_name|treatment)"\s*:',
    re.IGNORECASE,
)


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _property_names(node: Any) -> set[str]:
    if isinstance(node, dict):
        names = set(node.get("properties", {}))
        for value in node.values():
            names.update(_property_names(value))
        return names
    if isinstance(node, list):
        names: set[str] = set()
        for value in node:
            names.update(_property_names(value))
        return names
    return set()


def test_exact_entity_kinds_and_ordinary_transition_table_are_closed() -> None:
    assert ENTITY_KINDS == EXPECTED_KINDS
    assert ORDINARY_TRANSITIONS == EXPECTED_TRANSITIONS
    assert POOLABLE_KINDS == EXPECTED_SPECIAL_KINDS
    assert DEMULTIPLEXABLE_KINDS == EXPECTED_SPECIAL_KINDS
    assert EXPECTED_CAPS["lineage_depth_policy_ceiling"] == MAX_ABSOLUTE_DEPTH


@pytest.mark.parametrize("transition", sorted(EXPECTED_TRANSITIONS))
def test_every_declared_ordinary_transition_is_allowed(
    transition: tuple[str, str, str],
) -> None:
    assert ordinary_transition_allowed(*transition) is True


def test_every_unlisted_operation_and_kind_pair_is_forbidden() -> None:
    operation_names = {transition[0] for transition in EXPECTED_TRANSITIONS} | {
        "pooled_from",
        "demultiplexed_from",
        "derived_from",
        "same_as",
        "unknown",
    }
    candidates = {
        (operation, parent, child)
        for operation in operation_names
        for parent in EXPECTED_KINDS
        for child in EXPECTED_KINDS
    }
    forbidden = candidates - EXPECTED_TRANSITIONS

    assert forbidden
    assert all(not ordinary_transition_allowed(*transition) for transition in forbidden)


def test_fixture_manifest_is_closed_synthetic_and_locks_resource_caps() -> None:
    manifest = _manifest()
    declared = {case["file"] for case in manifest["cases"]}
    actual = {path.name for path in FIXTURE_DIRECTORY.glob("*.json")} - {"manifest.json"}

    assert manifest["module_id"] == "GLIO-PROTEOGEN-M01-02"
    assert manifest["data_classification"] == "synthetic_non_clinical"
    assert manifest["strict_json"] is True
    assert manifest["data_inventory"] == {
        "source": "repository_locked_synthetic_fixtures",
        "clinical_records": False,
        "external_datasets": [],
    }
    assert declared == actual
    assert len({case["case_id"] for case in manifest["cases"]}) == len(manifest["cases"])
    assert manifest["locked_semantics"]["caps"] == EXPECTED_CAPS


def test_fixture_manifest_locks_only_primary_adapter_versions() -> None:
    inventory = _manifest()["runtime_reference_inventory"]
    pins = {entry["name"]: entry["version"] for entry in inventory}

    assert pins == EXPECTED_ADAPTER_PINS
    assert all(entry["runtime_fetch"] is False for entry in inventory)
    assert all(
        "adapter" in entry["purpose"].lower() or "never person" in entry["purpose"]
        for entry in inventory
    )
    assert "1.1.0" not in MANIFEST_PATH.read_text(encoding="utf-8")


def test_deterministic_model_inventory_cannot_claim_training_or_promotion() -> None:
    assert _manifest()["model_inventory"] == [
        {
            "model_id": "deterministic_identity_lineage_reconciler",
            "model_version": "1.0.0",
            "algorithm": (
                "sorted_authorized_dsu_plus_iterative_kahn_lineage_and_"
                "provenance_deduplicated_concordance"
            ),
            "trained": False,
            "calibrated": False,
            "runtime_fetch": False,
            "clinical_claim": False,
            "identity_promotion": False,
            "output_effect": "retain_quarantine_or_human_review_never_relabel",
        }
    ]


def test_module_document_separates_external_adapters_from_internal_authority() -> None:
    document = MODULE_DOCUMENT.read_text(encoding="utf-8")

    assert "sole authority for identity semantics" in document
    assert "External standards" in document
    assert "SDRF-Proteomics v1.0.1" in document
    assert "unreleased v1.1 development text is not normative" in document
    assert "no GPL validator code" in document
    assert "Phenopacket schema 2.0.0" in document
    assert "VRS 2.0.1" in document
    assert "DICOM PS3 2026c" in document
    assert "ISA Model and Serialization Specifications 1.0" in document


def test_human_manifest_locks_module_ownership_and_output_ceiling() -> None:
    manifest = HUMAN_MANIFEST.read_text(encoding="utf-8")

    assert "GLIO-PROTEOGEN-M01-02" in manifest
    assert "C01 Preanalytic proteomics registry" in manifest
    assert "Computational biology" in manifest
    assert "`S2`" in manifest
    assert "`G0`" in manifest
    assert "Immutable identity-lineage resolution" in manifest
    assert "Runtime model | None" in manifest


def test_traceability_and_evidence_cover_every_g0_requirement() -> None:
    with TRACEABILITY_MATRIX.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    evidence = EVIDENCE_DOCUMENT.read_text(encoding="utf-8")

    assert [row["requirement_id"] for row in rows] == [
        f"M01-02-R{index:02d}" for index in range(1, 27)
    ]
    assert {row["gate"] for row in rows} == {"G0"}
    for category in (
        "Locked tests",
        "Benchmark report",
        "Traceability",
        "Risk-control verification",
        "Data manifest",
        "Model manifest",
        "Reference manifest",
        "Rollback evidence",
        "Reviewer sign-off",
    ):
        assert f"| {category} |" in evidence
    assert "never self-attested" in evidence
    assert "Named person or governed review identity" in evidence


def test_fixtures_contain_no_direct_phi_shaped_keys() -> None:
    for fixture in FIXTURE_DIRECTORY.glob("*.json"):
        assert FORBIDDEN_FIXTURE_KEYS.search(fixture.read_text(encoding="utf-8")) is None


def test_public_output_schema_excludes_forbidden_responsibilities_when_available() -> None:
    contract = importlib.import_module("glio_proteogen.contracts.m01_02.v1")

    properties = _property_names(
        contract.IdentityLineageResolution.model_json_schema(mode="serialization")
    )

    assert properties.isdisjoint(FORBIDDEN_OUTPUT_PROPERTIES)
