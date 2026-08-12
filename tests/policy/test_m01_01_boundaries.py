"""Ownership, safety, and quarantine boundaries for M01-01."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_01.v1 import (
    ConformanceDecision,
    ConformanceProfile,
    EvaluateMetadataRequest,
    M0101Output,
    ProtocolSchemaReceipt,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.validator import (
    validate_metadata,
)
from tests.m01_01_support import (
    FIXTURE_DIRECTORY,
    load_manifest,
    load_protocol_schema,
    load_request,
)

ROOT = Path(__file__).parents[2]
HUMAN_MANIFEST = ROOT / "docs" / "modules" / "M01-01.manifest.md"
TRACEABILITY_MATRIX = ROOT / "docs" / "traceability" / "M01-01.md"
EVIDENCE_INVENTORY = ROOT / "docs" / "evidence" / "M01-01.md"
DOSSIER_EVIDENCE_CATEGORIES = {
    "Locked tests",
    "Benchmark report",
    "Traceability",
    "Risk-control verification",
    "Data manifest",
    "Model manifest",
    "Reference manifest",
    "Rollback evidence",
    "Reviewer sign-off",
}
FORBIDDEN_OUTPUT_PROPERTIES = {
    "all_omics_fusion",
    "kinase_state",
    "recommended_treatment",
    "treatment_recommendation",
}
REQUIRED_OUTPUT_ENVELOPE = {
    "support",
    "uncertainty",
    "provenance",
    "evidence",
    "limitations",
}
PHI_LIKE_KEYS = re.compile(
    r'"(?:date_of_birth|diagnosis|medical_record_number|mrn|patient_id|treatment)"\s*:',
    re.IGNORECASE,
)


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


def test_human_manifest_locks_module_ownership_and_output_ceiling() -> None:
    manifest = HUMAN_MANIFEST.read_text(encoding="utf-8")

    assert "GLIO-PROTEOGEN-M01-01" in manifest
    assert "C01 Preanalytic proteomics registry" in manifest
    assert "Scientific engineering" in manifest
    assert "`S2`" in manifest
    assert "`G0`" in manifest
    assert "Versioned protocol schema receipt or conformance profile" in manifest


def test_traceability_and_evidence_inventory_cover_the_dossier_g0_gate() -> None:
    traceability = TRACEABILITY_MATRIX.read_text(encoding="utf-8")
    evidence = EVIDENCE_INVENTORY.read_text(encoding="utf-8")
    rows = re.findall(r"^\| (M01-01-R\d{2}) \|.*\| (G0) \|$", traceability, re.MULTILINE)

    assert rows == [(f"M01-01-R{index:02d}", "G0") for index in range(1, 18)]
    assert all(f"| {category} |" in evidence for category in DOSSIER_EVIDENCE_CATEGORIES)
    assert "never self-attested by implementation code" in evidence
    assert "Named person or governed review identity" in evidence


def test_public_output_schema_has_no_forbidden_responsibility() -> None:
    properties = _property_names(TypeAdapter(M0101Output).json_schema(mode="serialization"))

    assert properties.isdisjoint(FORBIDDEN_OUTPUT_PROPERTIES)


@pytest.mark.parametrize(
    ("output_type", "version_field"),
    [
        (ProtocolSchemaReceipt, "receipt_version"),
        (ConformanceProfile, "profile_version"),
    ],
)
def test_every_output_variant_has_typed_evidence_envelope(
    output_type: type[ProtocolSchemaReceipt | ConformanceProfile],
    version_field: str,
) -> None:
    fields = set(output_type.model_fields)

    assert fields >= REQUIRED_OUTPUT_ENVELOPE
    assert version_field in fields
    assert "output_type" in fields


def test_fixture_corpus_is_declared_synthetic_and_has_no_phi_shaped_keys() -> None:
    manifest = load_manifest()
    assert manifest["data_classification"] == "synthetic_non_clinical"
    assert manifest["data_inventory"] == {
        "source": "repository_locked_synthetic_fixtures",
        "clinical_records": False,
        "external_datasets": [],
    }
    assert manifest["model_inventory"] == [
        {
            "model_id": "glio_preanalytic_quality_consensus",
            "model_version": "1.0.0",
            "model_content_digest": (
                "sha256:c0d8b536f2d162a41fb7ff6d3de9941f7debad31aa15bc39444a993e16ab869b"
            ),
            "model_artifact_digest": (
                "sha256:c4876ea329e65fff63e992c8697bd9eea64a75614116a46a980ff0c2e364c81f"
            ),
            "reference_corpus_id": "glio_preanalytic_quality_reference",
            "reference_corpus_version": "1.0.0",
            "reference_corpus_content_digest": (
                "sha256:9ae807d745cbda935222758a2ce29d0d6855cd6452dd16adf9c694fed6145940"
            ),
            "reference_corpus_artifact_digest": (
                "sha256:1f33cf9c074231de29f77b957ad241bbb9045764fabcda03d90553a6dba237b9"
            ),
            "algorithm": (
                "deterministic_multi_view_nearest_medoid_gower_consensus_with_abstention"
            ),
            "data_classification": "synthetic_non_clinical",
            "trained": False,
            "calibrated": False,
            "runtime_fetch": False,
            "clinical_claim": False,
            "output_effect": (
                "retain_ordinary_conformance_or_quarantine_for_review_never_promote"
            ),
        }
    ]
    assert manifest["runtime_reference_inventory"] == [
        {
            "name": "Unified Code for Units of Measure supported subset",
            "version": "2.2",
            "source": "https://ucum.org/ucum",
            "license": "https://ucum.org/license",
            "runtime_fetch": False,
            "purpose": (
                "Closed unit-code validation and deterministic affine quantity conversion."
            ),
        }
    ]

    for case in manifest["cases"]:
        contents = (FIXTURE_DIRECTORY / case["file"]).read_text(encoding="utf-8")
        assert PHI_LIKE_KEYS.search(contents) is None


def test_validation_preserves_all_upstream_references_byte_for_byte() -> None:
    request = load_request("evaluate_conformant.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)
    references_before = request.context.references.model_dump_json()

    validate_metadata(
        load_protocol_schema(),
        request.document,
        consent_state=request.context.references.consent.state,
    )

    assert request.context.references.model_dump_json() == references_before


def test_compatibility_quarantine_cannot_masquerade_as_conformant() -> None:
    request = load_request("evaluate_quarantine.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)

    report = validate_metadata(
        load_protocol_schema(),
        request.document,
        consent_state=ConsentState.GRANTED,
    )

    assert report.decision is ConformanceDecision.QUARANTINED
    assert report.human_review_required is True
    assert {issue.action.value for issue in report.issues} == {"quarantine"}


def test_critical_identity_rejection_always_requires_human_review() -> None:
    request = load_request("evaluate_reject.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)

    report = validate_metadata(
        load_protocol_schema(),
        request.document,
        consent_state=ConsentState.GRANTED,
    )

    assert report.decision is ConformanceDecision.NONCONFORMANT
    assert report.human_review_required is True
    assert [
        (issue.code, issue.severity.value, issue.action.value) for issue in report.issues
    ] == [("identity.missing", "critical", "reject")]


def test_unknown_consent_quarantines_without_inference() -> None:
    request = load_request("evaluate_conformant.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)

    report = validate_metadata(
        load_protocol_schema(),
        request.document,
        consent_state=ConsentState.UNKNOWN,
    )

    assert report.decision is ConformanceDecision.QUARANTINED
    assert [(issue.code, issue.path) for issue in report.issues] == [
        ("consent.unknown", "/context/references/consent/state")
    ]
