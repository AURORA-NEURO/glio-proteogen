"""Contract freeze tests for M04-02 identity-lineage reconciliation."""

from __future__ import annotations

from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from glio_proteogen.contracts.m04_02 import (
    M0402_ARTIFACT_ROLE_COUNT,
    M0402_CONTRACT_VERSION,
    M0402_DERIVATION_COUNT,
    M0402_FINDING_CODE_COUNT,
    M0402_LIMITATION_COUNT,
    M0402_MAX_APPROVED_METHODS,
    M0402_MAX_ARTIFACT_CLAIMS,
    M0402_MAX_CANONICAL_REQUEST_BYTES,
    M0402_MAX_DERIVATION_SOURCES,
    M0402_MAX_EVIDENCE,
    M0402_MAX_FINDINGS,
    M0402_MAX_SUBJECT_COMPONENT_IDS,
    M0402_MIN_ARTIFACT_CLAIMS,
    M0402_MIN_DERIVATION_SOURCES,
    M0402_MIN_EVIDENCE,
    M0402_MODULE_ID,
    M0402_OPERATION,
    M0402_PARENT,
    M0402_PHYSICAL_ENTITY_KIND_COUNT,
    ProteoformIdentityLineageFindingAction,
    ProteoformIdentityLineageFindingCode,
    ProteoformLineageArtifactRole,
    ProteoformLineageDisposition,
    ProteoformLineageEvidenceState,
    contract_json_schema,
    contract_json_schemas,
    expected_limitations,
    expected_support,
    expected_uncertainty,
    opaque_proteoform_lineage_identifier,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import EstimateState, SupportStatus

SCHEMA_NAMES = (
    "request",
    "output",
    "policy",
    "artifact-claim",
    "derivation",
    "graph",
    "finding",
    "receipt",
)


@pytest.mark.contract
def test_identity_and_installed_caps_are_exact() -> None:
    assert (M0402_MODULE_ID, M0402_CONTRACT_VERSION, M0402_OPERATION, M0402_PARENT) == (
        "GLIO-PROTEOGEN-M04-02",
        "1.0.0",
        "reconcile_proteoform_identity_lineage",
        "protein_rna_discordance",
    )
    assert (
        M0402_PHYSICAL_ENTITY_KIND_COUNT,
        M0402_ARTIFACT_ROLE_COUNT,
        M0402_MIN_ARTIFACT_CLAIMS,
        M0402_MAX_ARTIFACT_CLAIMS,
        M0402_DERIVATION_COUNT,
        M0402_MIN_DERIVATION_SOURCES,
        M0402_MAX_DERIVATION_SOURCES,
    ) == (7, 5, 5, 256, 1, 4, 255)
    assert (
        M0402_MAX_SUBJECT_COMPONENT_IDS,
        M0402_MAX_APPROVED_METHODS,
        M0402_MAX_CANONICAL_REQUEST_BYTES,
        M0402_LIMITATION_COUNT,
        M0402_MIN_EVIDENCE,
        M0402_MAX_EVIDENCE,
        M0402_FINDING_CODE_COUNT,
        M0402_MAX_FINDINGS,
    ) == (256, 64, 4 * 1024 * 1024, 3, 15, 329, 14, 2435)


@pytest.mark.contract
def test_closed_enumerations_are_exact() -> None:
    assert tuple(item.value for item in ProteoformLineageArtifactRole) == (
        "mass_spectrometry_proteome_manifest",
        "genome_manifest",
        "transcriptome_manifest",
        "ptm_annotation_manifest",
        "protein_rna_discordance_input_bundle",
    )
    assert tuple(item.value for item in ProteoformLineageEvidenceState) == (
        "observed",
        "missing",
        "indeterminate",
        "unsupported",
        "redacted",
    )
    assert tuple(item.value for item in ProteoformLineageDisposition) == (
        "reconciled",
        "quarantined",
        "abstained",
    )
    assert tuple(item.value for item in ProteoformIdentityLineageFindingAction) == (
        "record",
        "quarantine",
        "abstain",
    )
    assert tuple(item.value for item in ProteoformIdentityLineageFindingCode) == (
        "upstream_identity_unresolved",
        "upstream_protocol_nonconformant",
        "identity_not_evaluable",
        "identity_swap",
        "cross_patient_link",
        "artifact_lineage_collision",
        "artifact_identity_collision",
        "binding_scope_collision",
        "duplicate_content_retained",
        "producer_identity_drift",
        "producer_protocol_drift",
        "producer_reference_bundle_drift",
        "producer_coordinate_policy_drift",
        "artifact_evidence_not_evaluable",
    )


@pytest.mark.contract
def test_all_eight_schemas_are_strict_and_authority_bounded() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == SCHEMA_NAMES
    for name, schema in schemas.items():
        Draft202012Validator.check_schema(schema)
        assert cast("str", schema["$id"]).endswith(f":{name}")
        metadata = cast("dict[str, Any]", schema["x-glio-contract"])
        assert metadata == {
            "moduleId": M0402_MODULE_ID,
            "contractVersion": M0402_CONTRACT_VERSION,
            "strict": True,
            "rawPayload": False,
            "identityInference": False,
            "consentInference": False,
            "proteinInference": False,
            "proteoformInference": False,
            "isoformInference": False,
            "gliomaSpecificBiologyInference": False,
            "copyNumberRegression": False,
            "proteinRnaDiscordanceInference": False,
            "kinaseActivityInference": False,
            "allOmicsFusion": False,
            "treatmentRecommendation": False,
            "parentTarget": M0402_PARENT,
            **({"maxRequestBytes": M0402_MAX_CANONICAL_REQUEST_BYTES} if name == "request" else {}),
        }
        assert contract_json_schema(cast("Any", name)) == schema


@pytest.mark.contract
@pytest.mark.parametrize(
    "disposition",
    tuple(ProteoformLineageDisposition),
)
def test_support_review_envelope_is_closed(
    disposition: ProteoformLineageDisposition,
) -> None:
    support = expected_support(disposition)
    expected = {
        ProteoformLineageDisposition.RECONCILED: (
            SupportStatus.SUPPORTED,
            "proteoform_identity_lineage_reconciled",
        ),
        ProteoformLineageDisposition.QUARANTINED: (
            SupportStatus.REVIEW_REQUIRED,
            "proteoform_identity_lineage_quarantined",
        ),
        ProteoformLineageDisposition.ABSTAINED: (
            SupportStatus.UNSUPPORTED,
            "proteoform_identity_lineage_abstained",
        ),
    }[disposition]
    assert (support.status, support.reason_code) == expected


@pytest.mark.contract
def test_uncertainty_and_limitations_preserve_the_authority_ceiling() -> None:
    uncertainty = expected_uncertainty()
    estimates = (
        uncertainty.measurement,
        uncertainty.sampling,
        uncertainty.parameter,
        uncertainty.model_form,
        uncertainty.identification,
        uncertainty.support,
        uncertainty.transport,
    )
    assert all(
        item.state is EstimateState.NOT_ESTIMABLE and item.probability is None for item in estimates
    )
    assert {item.code for item in expected_limitations()} == {
        "deterministic_identity_lineage_reconciliation_only",
        "caller_declared_authority_not_authenticated",
        "no_identity_protein_discordance_or_clinical_inference",
    }


@pytest.mark.contract
@pytest.mark.parametrize(
    "namespace",
    [
        "request",
        "actor",
        "decision",
        "policy",
        "method",
        "claim",
        "derivation",
        "evidence",
        "reviewer",
    ],
)
def test_opaque_identifier_helper_requires_exact_namespace(namespace: str) -> None:
    identifier = f"{namespace}.{sha256_digest(namespace).removeprefix('sha256:')}"
    assert opaque_proteoform_lineage_identifier(cast("Any", namespace), identifier) == identifier
    with pytest.raises(ValueError, match="must be opaque"):
        opaque_proteoform_lineage_identifier(cast("Any", namespace), f"{namespace}.biological")
