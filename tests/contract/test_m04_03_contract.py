"""Contract freeze tests for M04-03 proteoform raw-input ingestion."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from evals.m04_02.run import build_scenario_request as build_m0402_request
from evals.m04_03.run import build_scenario as build_m0403_scenario
from evals.m04_03.run import canonical_smoke
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import ValidationError

from glio_proteogen.contracts import m04_03
from glio_proteogen.contracts.m04_01 import (
    CoordinateConvention,
    ProteinQuantificationUnit,
    ProteoformApplicability,
    ProteoformQuantificationScale,
    TranscriptQuantificationUnit,
)
from glio_proteogen.contracts.m04_02 import (
    ProteoformIdentityLineageResolution,
    ProteoformLineageArtifactRole,
)
from glio_proteogen.contracts.m04_02 import (
    result_payload_digest as m0402_result_payload_digest,
)
from glio_proteogen.contracts.m04_03 import (
    M0403_CONTRACT_VERSION,
    M0403_DIAGNOSTIC_CODE_COUNT,
    M0403_LIMITATION_COUNT,
    M0403_MAX_APPROVED_PARSERS,
    M0403_MAX_CANONICAL_REQUEST_BYTES,
    M0403_MAX_DECLARED_RECORD_COUNT,
    M0403_MAX_DIAGNOSTICS,
    M0403_MAX_DOCUMENT_BYTES,
    M0403_MAX_EVIDENCE,
    M0403_MAX_TOTAL_DOCUMENT_BYTES,
    M0403_MIN_APPROVED_PARSERS,
    M0403_MIN_EVIDENCE,
    M0403_MODULE_ID,
    M0403_OPERATION,
    M0403_PARENT,
    M0403_ROLE_COUNT,
    M0403_ZERO_DIGEST,
    ApprovedProteoformRawParser,
    GenomeInputDocument,
    IngestProteoformRawInputsRequest,
    MassSpectrometryProteomeInputDocument,
    ProteoformRawAssaySupportState,
    ProteoformRawCompletenessState,
    ProteoformRawDiagnosticAction,
    ProteoformRawDiagnosticCode,
    ProteoformRawDocumentFormat,
    ProteoformRawEvidenceState,
    ProteoformRawInputArtifact,
    ProteoformRawInputDisposition,
    ProteoformRawInputPolicy,
    ProteoformRawInputReceipt,
    ProteoformRawInputRole,
    ProteoformRawInputValidationResult,
    ProteoformRawParentQualityState,
    ProteoformRawParseDiagnostic,
    PtmAnnotationInputDocument,
    TranscriptomeInputDocument,
    artifact_digest,
    artifact_mapping_digest,
    canonical_request_digest,
    configuration_digest,
    context_digest,
    contract_json_schema,
    contract_json_schemas,
    diagnostic_digest,
    document_digest,
    expected_diagnostics,
    expected_limitations,
    expected_provenance,
    expected_receipt,
    expected_support,
    expected_uncertainty,
    expected_validated_inputs,
    normalized_result,
    parser_digest,
    policy_digest,
    raw_input_evidence_index,
    receipt_digest,
    result_payload_digest,
    validated_input_digest,
    validated_inputs_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ContextReferences,
    EstimateState,
    ExecutionContext,
    SupportStatus,
)
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage import (
    reconcile_proteoform_identity_lineage,
)

SCHEMA_NAMES = (
    "request",
    "output",
    "policy",
    "parser-profile",
    "input-artifact",
    "proteome-document",
    "genome-document",
    "transcriptome-document",
    "ptm-document",
    "validated-input",
    "diagnostic",
    "receipt",
)
SCENARIO_PATH = Path(__file__).parents[1] / "fixtures" / "m04_03" / "scenarios.json"
EXPECTED_GROUP_COUNT = 8
EXPECTED_CASE_COUNT = 72
MAXIMUM_DISCREPANCY_DIAGNOSTIC_COUNT = 56

PUBLIC_CONTRACT_SYMBOLS = {
    "CONTRACT_VERSION",
    "M0403_CONTRACT_VERSION",
    "M0403_DIAGNOSTIC_CODE_COUNT",
    "M0403_LIMITATION_COUNT",
    "M0403_MAX_APPROVED_PARSERS",
    "M0403_MAX_CANONICAL_REQUEST_BYTES",
    "M0403_MAX_DECLARED_RECORD_COUNT",
    "M0403_MAX_DIAGNOSTICS",
    "M0403_MAX_DOCUMENT_BYTES",
    "M0403_MAX_EVIDENCE",
    "M0403_MAX_TOTAL_DOCUMENT_BYTES",
    "M0403_MIN_APPROVED_PARSERS",
    "M0403_MIN_EVIDENCE",
    "M0403_MODULE_ID",
    "M0403_OPERATION",
    "M0403_PARENT",
    "M0403_ROLE_COUNT",
    "M0403_ZERO_DIGEST",
    "SCHEMA_ID_PREFIX",
    "ApprovedProteoformRawParser",
    "ContractName",
    "GenomeInputDocument",
    "IngestProteoformRawInputsRequest",
    "MassSpectrometryProteomeInputDocument",
    "ProteoformRawAssaySupportState",
    "ProteoformRawCompletenessState",
    "ProteoformRawDiagnosticAction",
    "ProteoformRawDiagnosticCode",
    "ProteoformRawDocumentFormat",
    "ProteoformRawEvidenceState",
    "ProteoformRawInputArtifact",
    "ProteoformRawInputDisposition",
    "ProteoformRawInputOpaqueNamespace",
    "ProteoformRawInputPolicy",
    "ProteoformRawInputReceipt",
    "ProteoformRawInputRole",
    "ProteoformRawInputValidationResult",
    "ProteoformRawParentQualityState",
    "ProteoformRawParseDiagnostic",
    "PtmAnnotationInputDocument",
    "TranscriptomeInputDocument",
    "ValidatedProteoformRawInput",
    "artifact_digest",
    "artifact_mapping_digest",
    "canonical_request_digest",
    "configuration_digest",
    "context_digest",
    "contract_json_schema",
    "contract_json_schemas",
    "diagnostic_digest",
    "document_digest",
    "expected_control_decisions",
    "expected_diagnostics",
    "expected_limitations",
    "expected_provenance",
    "expected_receipt",
    "expected_support",
    "expected_uncertainty",
    "expected_validated_inputs",
    "normalized_artifact",
    "normalized_diagnostic",
    "normalized_document",
    "normalized_lineage_result",
    "normalized_parser",
    "normalized_policy",
    "normalized_receipt",
    "normalized_request",
    "normalized_result",
    "normalized_result_payload",
    "normalized_validated_input",
    "opaque_proteoform_raw_input_identifier",
    "parser_digest",
    "policy_digest",
    "raw_input_evidence_index",
    "receipt_digest",
    "result_payload_digest",
    "validated_input_digest",
    "validated_inputs_digest",
}

QUARANTINE_CODES = (
    ProteoformRawDiagnosticCode.UPSTREAM_LINEAGE_QUARANTINED,
    ProteoformRawDiagnosticCode.MANIFEST_CLAIM_MISMATCH,
    ProteoformRawDiagnosticCode.IDENTITY_BINDING_MISMATCH,
    ProteoformRawDiagnosticCode.PROTOCOL_BINDING_MISMATCH,
    ProteoformRawDiagnosticCode.REFERENCE_BUNDLE_MISMATCH,
    ProteoformRawDiagnosticCode.COORDINATE_POLICY_MISMATCH,
    ProteoformRawDiagnosticCode.UNSUPPORTED_MEDIA_TYPE,
    ProteoformRawDiagnosticCode.UNSUPPORTED_FORMAT_VERSION,
    ProteoformRawDiagnosticCode.UNIT_MISMATCH,
    ProteoformRawDiagnosticCode.ASSAY_PROTOCOL_MISMATCH,
    ProteoformRawDiagnosticCode.SPECIMEN_PROCESSING_MISMATCH,
    ProteoformRawDiagnosticCode.INCOMPLETE_MANIFEST,
    ProteoformRawDiagnosticCode.ASSAY_UNSUPPORTED,
    ProteoformRawDiagnosticCode.PARENT_QUALITY_UNACCEPTABLE,
)


def _digest(label: str) -> str:
    return sha256_digest({"m0403_contract_test": label})


def _opaque(namespace: str, label: str) -> str:
    return f"{namespace}.{_digest(f'{namespace}-{label}').removeprefix('sha256:')}"


def _reference(
    namespace: str,
    label: str,
    media_type: str,
    *,
    digest: str | None = None,
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_opaque(namespace, label),
        version="1.0.0",
        digest=digest or _digest(f"reference-{label}"),
        media_type=media_type,
    )


ROLE_FORMATS = {
    ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
        ProteoformRawDocumentFormat.PROTEOME_MANIFEST_JSON
    ),
    ProteoformRawInputRole.GENOME: ProteoformRawDocumentFormat.GENOME_MANIFEST_JSON,
    ProteoformRawInputRole.TRANSCRIPTOME: ProteoformRawDocumentFormat.TRANSCRIPTOME_MANIFEST_JSON,
    ProteoformRawInputRole.PTM_ANNOTATIONS: (
        ProteoformRawDocumentFormat.PTM_ANNOTATION_MANIFEST_JSON
    ),
}
ROLE_CONTENT_MEDIA_TYPES = {
    ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
        "application/vnd.glio-proteogen.m04-03.proteome-input+json"
    ),
    ProteoformRawInputRole.GENOME: ("application/vnd.glio-proteogen.m04-03.genome-input+json"),
    ProteoformRawInputRole.TRANSCRIPTOME: (
        "application/vnd.glio-proteogen.m04-03.transcriptome-input+json"
    ),
    ProteoformRawInputRole.PTM_ANNOTATIONS: (
        "application/vnd.glio-proteogen.m04-03.ptm-annotation-input+json"
    ),
}
ROLE_PROJECTION = {
    ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
        ProteoformLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST
    ),
    ProteoformRawInputRole.GENOME: ProteoformLineageArtifactRole.GENOME_MANIFEST,
    ProteoformRawInputRole.TRANSCRIPTOME: ProteoformLineageArtifactRole.TRANSCRIPTOME_MANIFEST,
    ProteoformRawInputRole.PTM_ANNOTATIONS: (ProteoformLineageArtifactRole.PTM_ANNOTATION_MANIFEST),
}


def _genuine_lineage(
    case_id: str = "canonical_all_seven_entity_chain",
) -> ProteoformIdentityLineageResolution:
    return reconcile_proteoform_identity_lineage(build_m0402_request(case_id))


def _genuine_request(
    lineage: ProteoformIdentityLineageResolution | None = None,
) -> IngestProteoformRawInputsRequest:
    lineage = lineage or _genuine_lineage()
    parsers = tuple(
        ApprovedProteoformRawParser(
            role=role,
            format=ROLE_FORMATS[role],
            format_version="1.0.0",
            parser_version="1.0.0",
            media_type=ROLE_CONTENT_MEDIA_TYPES[role],
            max_document_bytes=M0403_MAX_DOCUMENT_BYTES,
            evidence=_reference(
                "evidence",
                f"parser-{role.value}",
                "application/vnd.glio-proteogen.m04-03.parser+json",
            ),
        )
        for role in ProteoformRawInputRole
    )
    policy = ProteoformRawInputPolicy(
        policy_id=_opaque("policy", "canonical"),
        version="1.0.0",
        approved_parsers=parsers,
        evidence=_reference(
            "evidence",
            "policy",
            "application/vnd.glio-proteogen.m04-03.policy+json",
        ),
        reviewed_by=_opaque("reviewer", "canonical"),
        reviewed_at=lineage.completed_at,
    )
    base = lineage.request.context.references
    control_media_type = "application/vnd.glio-proteogen.control+json"

    def local_control(control: Any, label: str, digest: str) -> Any:
        return control.model_copy(
            update={
                "decision_id": _opaque("decision", label),
                "evidence": _reference(
                    "evidence",
                    f"control-{label}",
                    control_media_type,
                    digest=digest,
                ),
            }
        )

    references = ContextReferences(
        approved_configuration=local_control(
            base.approved_configuration,
            "configuration",
            configuration_digest(policy),
        ),
        identity_lineage=local_control(
            base.identity_lineage,
            "identity",
            _digest("identity-control-evidence"),
        ).model_copy(update={"binding_digest": lineage.identity_resolution_digest}),
        provenance=local_control(
            base.provenance,
            "provenance",
            _digest("provenance-control-evidence"),
        ),
        consent=local_control(
            base.consent,
            "consent",
            _digest("consent-control-evidence"),
        ),
        quality=local_control(base.quality, "quality", lineage.result_digest),
        support=local_control(base.support, "support", lineage.receipt.receipt_digest),
        intended_use=local_control(
            base.intended_use,
            "intended-use",
            lineage.receipt.intended_use_evidence_digest,
        ),
    )
    context = ExecutionContext(
        request_id=_opaque("request", "canonical"),
        actor_id=_opaque("actor", "canonical"),
        occurred_at=lineage.completed_at,
        references=references,
    )
    artifacts = []
    for role in ProteoformRawInputRole:
        claim = next(
            item for item in lineage.request.artifact_claims if item.role is ROLE_PROJECTION[role]
        )
        artifacts.append(
            ProteoformRawInputArtifact(
                role=role,
                lineage_claim_id=claim.claim_id,
                manifest_reference=claim.artifact,
                content_reference=_reference(
                    "input",
                    f"content-{role.value}",
                    ROLE_CONTENT_MEDIA_TYPES[role],
                ),
                declared_size_bytes=1,
                format=ROLE_FORMATS[role],
                format_version="1.0.0",
                parser_version="1.0.0",
            )
        )
    return IngestProteoformRawInputsRequest(
        request_id=context.request_id,
        context=context,
        lineage_result=lineage,
        policy=policy,
        artifacts=tuple(artifacts),
    )


def _documents(
    request: IngestProteoformRawInputsRequest,
) -> tuple[
    MassSpectrometryProteomeInputDocument
    | GenomeInputDocument
    | TranscriptomeInputDocument
    | PtmAnnotationInputDocument,
    ...,
]:
    protocol = request.lineage_result.request.protocol_result.request.protocol_schema
    artifacts = {item.role: item for item in request.artifacts}

    def common(role: ProteoformRawInputRole) -> dict[str, object]:
        artifact = artifacts[role]
        return {
            "input_id": artifact.content_reference.artifact_id,
            "lineage_claim_id": artifact.lineage_claim_id,
            "identity_resolution_digest": request.lineage_result.identity_resolution_digest,
            "protocol_result_digest": request.lineage_result.protocol_result_digest,
            "reference_bundle_digest": request.lineage_result.receipt.reference_bundle_digest,
            "coordinate_policy_digest": request.lineage_result.receipt.coordinate_policy_digest,
            "intended_use_evidence_digest": (
                request.lineage_result.receipt.intended_use_evidence_digest
            ),
            "assay_protocol_version": protocol.assay_protocol_version,
            "specimen_processing_version": protocol.specimen_processing_version,
            "unit_definition_version": protocol.unit_system_version,
            "content_reference": artifact.content_reference,
            "declared_record_count": 1,
            "evidence_state": ProteoformRawEvidenceState.AVAILABLE,
            "completeness_state": ProteoformRawCompletenessState.COMPLETE,
            "assay_support_state": ProteoformRawAssaySupportState.SUPPORTED,
            "parent_quality_state": ProteoformRawParentQualityState.ACCEPTED,
        }

    proteome = MassSpectrometryProteomeInputDocument.model_validate(
        {
            **common(ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME),
            "applicability": protocol.applicability,
            "protein_unit": protocol.quantification.protein_unit,
            "protein_scale": protocol.quantification.protein_scale,
        },
        strict=True,
    )
    genome = GenomeInputDocument.model_validate(
        {
            **common(ProteoformRawInputRole.GENOME),
            "genome_convention": protocol.coordinate_policy.genome_convention,
            "genome_reference_digest": protocol.reference_bundle.genome_reference.digest,
            "coordinate_mapping_version": protocol.coordinate_policy.coordinate_mapping_version,
        },
        strict=True,
    )
    transcriptome = TranscriptomeInputDocument.model_validate(
        {
            **common(ProteoformRawInputRole.TRANSCRIPTOME),
            "transcript_unit": protocol.quantification.transcript_unit,
            "transcript_scale": protocol.quantification.transcript_scale,
            "transcript_convention": protocol.coordinate_policy.transcript_convention,
            "transcript_annotation_digest": (
                protocol.reference_bundle.transcript_annotation_reference.digest
            ),
            "transcript_protein_mapping_digest": (
                protocol.reference_bundle.transcript_protein_mapping_reference.digest
            ),
        },
        strict=True,
    )
    ptm = PtmAnnotationInputDocument.model_validate(
        {
            **common(ProteoformRawInputRole.PTM_ANNOTATIONS),
            "modification_vocabulary_id": protocol.controlled_vocabulary_id,
            "modification_vocabulary_version": protocol.controlled_vocabulary_version,
            "modification_vocabulary_digest": (
                protocol.reference_bundle.modification_vocabulary_reference.digest
            ),
            "protein_convention": protocol.coordinate_policy.protein_convention,
            "coordinate_mapping_version": protocol.coordinate_policy.coordinate_mapping_version,
            "localization_states": protocol.modification_localization.declared_states,
        },
        strict=True,
    )
    return (proteome, genome, transcriptome, ptm)


def _result(
    request: IngestProteoformRawInputsRequest,
    documents: tuple[
        MassSpectrometryProteomeInputDocument
        | GenomeInputDocument
        | TranscriptomeInputDocument
        | PtmAnnotationInputDocument,
        ...,
    ]
    | None = None,
) -> ProteoformRawInputValidationResult:
    if documents is None:
        documents = (
            _documents(request) if request.lineage_result.disposition.value == "reconciled" else ()
        )
    diagnostics = expected_diagnostics(request, documents)
    inputs = expected_validated_inputs(request, documents, diagnostics)
    actions = {item.action for item in diagnostics}
    disposition = (
        ProteoformRawInputDisposition.QUARANTINED
        if ProteoformRawDiagnosticAction.QUARANTINE in actions
        else ProteoformRawInputDisposition.ABSTAINED
        if ProteoformRawDiagnosticAction.ABSTAIN in actions
        else ProteoformRawInputDisposition.VALIDATED
    )
    request_hash = canonical_request_digest(request)
    payload: dict[str, object] = {
        "output_type": "proteoform_raw_input_validation_result",
        "result_id": f"result.m0403.{request_hash.removeprefix('sha256:')}",
        "result_version": "1.0.0",
        "request_digest": request_hash,
        "lineage_result_digest": request.lineage_result.result_digest,
        "policy_digest": policy_digest(request.policy),
        "configuration_digest": configuration_digest(request.policy),
        "context_digest": context_digest(request),
        "result_digest": M0403_ZERO_DIGEST,
        "request": request,
        "receipt": expected_receipt(request, inputs, diagnostics, disposition),
        "validated_inputs": inputs,
        "diagnostics": diagnostics,
        "disposition": disposition,
        "parent_target": M0403_PARENT,
        "emits_protein_rna_discordance": False,
        "emits_proteogenomic_state": False,
        "emits_proteotype": False,
        "emits_protein_level_subtype": False,
        "infers_identity": False,
        "infers_consent": False,
        "infers_protein": False,
        "infers_proteoform": False,
        "infers_kinase_activity": False,
        "performs_cn_to_protein_regression": False,
        "performs_all_omics_fusion": False,
        "recommends_treatment": False,
        "mutates_upstream": False,
        "executes_model": False,
        "support": expected_support(disposition),
        "uncertainty": expected_uncertainty(),
        "provenance": expected_provenance(request, request_hash, inputs),
        "evidence": raw_input_evidence_index(request),
        "limitations": expected_limitations(),
        "human_review_required": disposition is not ProteoformRawInputDisposition.VALIDATED,
        "completed_at": request.context.occurred_at,
    }
    payload["result_digest"] = result_payload_digest(payload)
    return ProteoformRawInputValidationResult.model_validate(payload, strict=True)


def _receipt_payload(
    *,
    codes: tuple[ProteoformRawDiagnosticCode, ...] = (),
    disposition: ProteoformRawInputDisposition = ProteoformRawInputDisposition.VALIDATED,
) -> dict[str, object]:
    digest_fields = (
        "identity_resolution_digest",
        "protocol_result_digest",
        "protocol_receipt_digest",
        "lineage_result_digest",
        "lineage_receipt_digest",
        "lineage_graph_digest",
        "reference_bundle_digest",
        "coordinate_policy_digest",
        "intended_use_evidence_digest",
        "policy_digest",
        "configuration_digest",
        "context_digest",
        "artifact_mapping_digest",
        "validated_inputs_digest",
    )
    payload: dict[str, object] = {field: _digest(field) for field in digest_fields}
    payload.update(
        {
            "diagnostic_codes": codes,
            "parent_target": "protein_rna_discordance",
            "emits_parent": False,
            "disposition": disposition,
            "receipt_digest": M0403_ZERO_DIGEST,
        }
    )
    payload["receipt_digest"] = receipt_digest(payload)
    return payload


@pytest.mark.contract
def test_identity_and_installed_caps_are_exact() -> None:
    assert (M0403_MODULE_ID, M0403_CONTRACT_VERSION, M0403_OPERATION, M0403_PARENT) == (
        "GLIO-PROTEOGEN-M04-03",
        "1.0.0",
        "ingest_proteoform_raw_inputs",
        "protein_rna_discordance",
    )
    assert (
        M0403_ROLE_COUNT,
        M0403_MIN_APPROVED_PARSERS,
        M0403_MAX_APPROVED_PARSERS,
        M0403_MAX_CANONICAL_REQUEST_BYTES,
        M0403_MAX_DOCUMENT_BYTES,
        M0403_MAX_TOTAL_DOCUMENT_BYTES,
        M0403_MAX_DECLARED_RECORD_COUNT,
    ) == (4, 4, 32, 4 * 1024 * 1024, 8 * 1024 * 1024, 32 * 1024 * 1024, 2**63 - 1)
    assert (
        M0403_DIAGNOSTIC_CODE_COUNT,
        M0403_MAX_DIAGNOSTICS,
        M0403_LIMITATION_COUNT,
        M0403_MIN_EVIDENCE,
        M0403_MAX_EVIDENCE,
    ) == (17, 60, 3, 20, 48)


@pytest.mark.contract
def test_public_contract_surface_is_explicit_and_exact() -> None:
    assert set(m04_03.__all__) == PUBLIC_CONTRACT_SYMBOLS


@pytest.mark.contract
def test_locked_corpus_capacity_and_cli_names_are_constructible() -> None:
    corpus = cast("dict[str, Any]", strict_json_loads(SCENARIO_PATH.read_bytes()))
    groups = cast("list[dict[str, Any]]", corpus["scenario_groups"])
    case_ids = [
        cast("str", case_id)
        for group in groups
        for case_id in cast("list[object]", group["case_ids"])
    ]
    assert len(groups) == EXPECTED_GROUP_COUNT
    assert len(case_ids) == EXPECTED_CASE_COUNT == len(set(case_ids))
    assert "largest_constructible_document_accepted" in case_ids
    assert "per_document_exact_8mib_accepted" not in case_ids
    assert corpus["cli_source_filenames"] == [
        "mass-spectrometry-proteome.json",
        "genome.json",
        "transcriptome.json",
        "ptm-annotations.json",
    ]


@pytest.mark.contract
def test_closed_enumerations_are_exact() -> None:
    assert tuple(item.value for item in ProteoformRawInputRole) == (
        "mass_spectrometry_proteome",
        "genome",
        "transcriptome",
        "ptm_annotations",
    )
    assert tuple(item.value for item in ProteoformRawDocumentFormat) == (
        "proteome_manifest_json",
        "genome_manifest_json",
        "transcriptome_manifest_json",
        "ptm_annotation_manifest_json",
    )
    assert tuple(item.value for item in ProteoformRawEvidenceState) == (
        "available",
        "missing",
        "indeterminate",
        "unsupported",
        "redacted",
    )
    assert tuple(item.value for item in ProteoformRawCompletenessState) == (
        "complete",
        "incomplete",
        "not_evaluable",
    )
    assert tuple(item.value for item in ProteoformRawAssaySupportState) == (
        "supported",
        "unsupported",
        "not_evaluable",
    )
    assert tuple(item.value for item in ProteoformRawParentQualityState) == (
        "accepted",
        "rejected",
        "not_evaluable",
    )
    assert tuple(item.value for item in ProteoformRawInputDisposition) == (
        "validated",
        "quarantined",
        "abstained",
    )
    assert tuple(item.value for item in ProteoformRawDiagnosticAction) == (
        "record",
        "quarantine",
        "abstain",
    )
    assert tuple(item.value for item in ProteoformRawDiagnosticCode) == (
        "upstream_lineage_quarantined",
        "upstream_lineage_abstained",
        "artifact_not_evaluable",
        "manifest_claim_mismatch",
        "identity_binding_mismatch",
        "protocol_binding_mismatch",
        "reference_bundle_mismatch",
        "coordinate_policy_mismatch",
        "unsupported_media_type",
        "unsupported_format_version",
        "unit_mismatch",
        "assay_protocol_mismatch",
        "specimen_processing_mismatch",
        "incomplete_manifest",
        "assay_unsupported",
        "parent_quality_unacceptable",
        "duplicate_content_retained",
    )


@pytest.mark.contract
def test_all_twelve_schemas_are_strict_draft_2020_12() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == SCHEMA_NAMES
    for name, schema in schemas.items():
        Draft202012Validator.check_schema(schema)
        assert schema == contract_json_schema(name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert cast("str", schema["$id"]).endswith(f":{name}")
        metadata = cast("dict[str, Any]", schema["x-glio-contract"])
        assert metadata["moduleId"] == M0403_MODULE_ID
        assert metadata["contractVersion"] == M0403_CONTRACT_VERSION
        assert metadata["strict"] is True
        assert metadata["rawPayload"] is False
        assert metadata["externalContentTraversal"] is False
        assert metadata["parentTarget"] == M0403_PARENT
        for key in (
            "identityInference",
            "consentInference",
            "proteinInference",
            "proteoformInference",
            "copyNumberRegression",
            "proteinRnaDiscordanceInference",
            "kinaseActivityInference",
            "allOmicsFusion",
            "treatmentRecommendation",
            "modelExecution",
            "eventPersistence",
        ):
            assert metadata[key] is False


@pytest.mark.contract
@pytest.mark.parametrize("code", tuple(ProteoformRawDiagnosticCode))
def test_diagnostic_code_action_mapping_is_closed(code: ProteoformRawDiagnosticCode) -> None:
    expected = (
        ProteoformRawDiagnosticAction.RECORD
        if code is ProteoformRawDiagnosticCode.DUPLICATE_CONTENT_RETAINED
        else ProteoformRawDiagnosticAction.ABSTAIN
        if code
        in {
            ProteoformRawDiagnosticCode.UPSTREAM_LINEAGE_ABSTAINED,
            ProteoformRawDiagnosticCode.ARTIFACT_NOT_EVALUABLE,
        }
        else ProteoformRawDiagnosticAction.QUARANTINE
    )
    diagnostic = ProteoformRawParseDiagnostic(
        role=None,
        code=code,
        action=expected,
        evidence_basis_digest=_digest(code.value),
    )
    assert diagnostic.action is expected
    wrong = (
        ProteoformRawDiagnosticAction.RECORD
        if expected is not ProteoformRawDiagnosticAction.RECORD
        else ProteoformRawDiagnosticAction.QUARANTINE
    )
    with pytest.raises(ValidationError):
        ProteoformRawParseDiagnostic(
            role=None,
            code=code,
            action=wrong,
            evidence_basis_digest=_digest(f"wrong-{code.value}"),
        )


@pytest.mark.contract
def test_receipt_uses_scalar_aggregate_digests_and_closed_precedence() -> None:
    codes = (
        ProteoformRawDiagnosticCode.ARTIFACT_NOT_EVALUABLE,
        ProteoformRawDiagnosticCode.MANIFEST_CLAIM_MISMATCH,
    )
    payload = _receipt_payload(
        codes=codes,
        disposition=ProteoformRawInputDisposition.QUARANTINED,
    )
    receipt = ProteoformRawInputReceipt.model_validate(payload, strict=True)
    assert receipt.diagnostic_codes == tuple(sorted(codes))
    assert receipt.disposition is ProteoformRawInputDisposition.QUARANTINED
    assert set(type(receipt).model_fields) >= {
        "artifact_mapping_digest",
        "validated_inputs_digest",
        "diagnostic_codes",
        "receipt_digest",
    }
    assert not {
        "artifact_digests",
        "validated_input_digests",
        "diagnostic_digests",
    }.intersection(type(receipt).model_fields)

    stale = dict(payload)
    stale["receipt_digest"] = _digest("stale-receipt")
    with pytest.raises(ValidationError):
        ProteoformRawInputReceipt.model_validate(stale, strict=True)

    wrong_disposition = dict(payload)
    wrong_disposition["disposition"] = ProteoformRawInputDisposition.ABSTAINED
    wrong_disposition["receipt_digest"] = receipt_digest(wrong_disposition)
    with pytest.raises(ValidationError):
        ProteoformRawInputReceipt.model_validate(wrong_disposition, strict=True)


@pytest.mark.contract
def test_support_uncertainty_and_limitations_are_exact() -> None:
    expected_status = {
        ProteoformRawInputDisposition.VALIDATED: SupportStatus.SUPPORTED,
        ProteoformRawInputDisposition.QUARANTINED: SupportStatus.REVIEW_REQUIRED,
        ProteoformRawInputDisposition.ABSTAINED: SupportStatus.UNSUPPORTED,
    }
    for disposition, status in expected_status.items():
        assert expected_support(disposition).status is status

    uncertainty = expected_uncertainty()
    assert all(
        estimate.state is EstimateState.NOT_ESTIMABLE
        for estimate in (
            uncertainty.measurement,
            uncertainty.sampling,
            uncertainty.parameter,
            uncertainty.model_form,
            uncertainty.identification,
            uncertainty.support,
            uncertainty.transport,
        )
    )
    assert tuple(item.code for item in expected_limitations()) == tuple(
        sorted(
            (
                "deterministic_raw_manifest_validation_only",
                "external_content_and_authority_not_authenticated",
                "no_protein_discordance_or_clinical_inference",
            )
        )
    )


@pytest.mark.contract
def test_every_quarantine_code_is_accounted_for() -> None:
    assert set(QUARANTINE_CODES) == set(ProteoformRawDiagnosticCode) - {
        ProteoformRawDiagnosticCode.UPSTREAM_LINEAGE_ABSTAINED,
        ProteoformRawDiagnosticCode.ARTIFACT_NOT_EVALUABLE,
        ProteoformRawDiagnosticCode.DUPLICATE_CONTENT_RETAINED,
    }


@pytest.mark.contract
def test_genuine_m0402_projection_and_semantic_reorder_are_exact() -> None:
    request = _genuine_request()
    upstream = {item.claim_id: item for item in request.lineage_result.request.artifact_claims}
    assert len(request.artifacts) == M0403_ROLE_COUNT
    for artifact in request.artifacts:
        claim = upstream[artifact.lineage_claim_id]
        assert claim.role is ROLE_PROJECTION[artifact.role]
        assert artifact.manifest_reference == claim.artifact

    payload = request.model_dump(mode="python", exclude_none=False)
    payload["artifacts"] = tuple(reversed(cast("tuple[object, ...]", payload["artifacts"])))
    policy = cast("dict[str, object]", payload["policy"])
    policy["approved_parsers"] = tuple(
        reversed(cast("tuple[object, ...]", policy["approved_parsers"]))
    )
    reordered = IngestProteoformRawInputsRequest.model_validate(payload, strict=True)
    assert reordered == request
    assert canonical_request_digest(reordered) == canonical_request_digest(request)


@pytest.mark.contract
def test_public_m0403_builder_is_genuine_and_fully_replayable() -> None:
    scenario = build_m0403_scenario()
    result = canonical_smoke()
    assert set(scenario.artifacts_by_role) == set(ProteoformRawInputRole)
    assert all(type(value) is bytes for value in scenario.artifacts_by_role.values())
    assert result.request == scenario.request
    assert result.disposition is ProteoformRawInputDisposition.VALIDATED
    assert len(result.validated_inputs) == M0403_ROLE_COUNT
    assert result.diagnostics == ()
    assert len(result.evidence) == M0403_MIN_EVIDENCE
    replay = ProteoformRawInputValidationResult.model_validate_json(
        canonical_json_bytes(result),
        strict=True,
    )
    assert replay == result


@pytest.mark.contract
def test_upstream_claim_substitution_and_ambiguity_reject() -> None:
    request = _genuine_request()
    payload = request.model_dump(mode="python", exclude_none=False)
    artifacts = list(cast("tuple[dict[str, object], ...]", payload["artifacts"]))
    artifacts[0]["lineage_claim_id"], artifacts[1]["lineage_claim_id"] = (
        artifacts[1]["lineage_claim_id"],
        artifacts[0]["lineage_claim_id"],
    )
    payload["artifacts"] = tuple(artifacts)
    with pytest.raises(ValidationError):
        IngestProteoformRawInputsRequest.model_validate(payload, strict=True)

    ambiguous = _genuine_lineage("duplicate_content_same_scope_retained")
    with pytest.raises(ValidationError):
        _genuine_request(ambiguous)


@pytest.mark.contract
def test_resigned_full_m0402_forgery_rejects() -> None:
    request = _genuine_request()
    payload = request.model_dump(mode="python", exclude_none=False)
    lineage = cast("dict[str, object]", payload["lineage_result"])
    support = cast("dict[str, object]", lineage["support"])
    support["rationale"] = "A valid-shaped but forged M04-02 support projection."
    lineage["result_digest"] = m0402_result_payload_digest(lineage)
    with pytest.raises(ValidationError):
        IngestProteoformRawInputsRequest.model_validate(payload, strict=True)


@pytest.mark.contract
def test_result_replay_rejects_resigned_derived_regions_and_partial_inputs() -> None:
    result = _result(_genuine_request())
    assert result.disposition is ProteoformRawInputDisposition.VALIDATED
    assert len(result.validated_inputs) == M0403_ROLE_COUNT
    assert result.diagnostics == ()

    forged = result.model_dump(mode="python", exclude_none=False)
    cast("dict[str, object]", forged["support"])["rationale"] = (
        "A valid-shaped but forged local support projection."
    )
    forged["result_digest"] = result_payload_digest(forged)
    with pytest.raises(ValidationError):
        ProteoformRawInputValidationResult.model_validate(forged, strict=True)

    partial = result.model_dump(mode="python", exclude_none=False)
    partial_inputs = result.validated_inputs[:-1]
    partial_documents = tuple(item.document for item in partial_inputs)
    partial_diagnostics = expected_diagnostics(result.request, partial_documents)
    replay_inputs = expected_validated_inputs(
        result.request,
        partial_documents,
        partial_diagnostics,
    )
    disposition = ProteoformRawInputDisposition.VALIDATED
    partial["validated_inputs"] = replay_inputs
    partial["diagnostics"] = partial_diagnostics
    partial["receipt"] = expected_receipt(
        result.request,
        replay_inputs,
        partial_diagnostics,
        disposition,
    )
    partial["provenance"] = expected_provenance(
        result.request,
        result.request_digest,
        replay_inputs,
    )
    partial["result_digest"] = result_payload_digest(partial)
    with pytest.raises(ValidationError):
        ProteoformRawInputValidationResult.model_validate(partial, strict=True)


@pytest.mark.contract
def test_result_semantic_reorder_preserves_full_equality() -> None:
    result = _result(_genuine_request())
    payload = deepcopy(result.model_dump(mode="python", exclude_none=False))
    for field in ("validated_inputs", "diagnostics", "evidence", "limitations"):
        payload[field] = tuple(reversed(cast("tuple[object, ...]", payload[field])))
    provenance = cast("dict[str, object]", payload["provenance"])
    for field in ("input_digests", "control_decisions"):
        provenance[field] = tuple(reversed(cast("tuple[object, ...]", provenance[field])))
    reordered = ProteoformRawInputValidationResult.model_validate(payload, strict=True)
    assert reordered == result
    assert canonical_json_bytes(reordered) == canonical_json_bytes(result)


@pytest.mark.contract
def test_maximum_discrepancy_diagnostics_are_aggregated_and_total() -> None:
    request = _genuine_request()
    shared_content_digest = _digest("maximum-discrepancy-shared-content")
    artifacts = tuple(
        ProteoformRawInputArtifact.model_validate(
            artifact.model_copy(
                update={
                    "content_reference": artifact.content_reference.model_copy(
                        update={
                            "digest": shared_content_digest,
                            "media_type": "application/vnd.example.unsupported+json",
                        }
                    )
                }
            ).model_dump(mode="python", exclude_none=False),
            strict=True,
        )
        for artifact in request.artifacts
    )
    maximum_request = IngestProteoformRawInputsRequest.model_validate(
        request.model_copy(update={"artifacts": artifacts}).model_dump(
            mode="python", exclude_none=False
        ),
        strict=True,
    )
    stale_protocol_digest = _digest("maximum-discrepancy-protocol")
    stale_intended_use_digest = _digest("maximum-discrepancy-intended-use")
    document_types = (
        MassSpectrometryProteomeInputDocument,
        GenomeInputDocument,
        TranscriptomeInputDocument,
        PtmAnnotationInputDocument,
    )
    documents: list[
        MassSpectrometryProteomeInputDocument
        | GenomeInputDocument
        | TranscriptomeInputDocument
        | PtmAnnotationInputDocument
    ] = []
    for index, document in enumerate(_documents(request)):
        payload = document.model_dump(mode="python", exclude_none=False)
        payload.update(
            identity_resolution_digest=_digest(f"maximum-discrepancy-identity-{index}"),
            protocol_result_digest=stale_protocol_digest,
            reference_bundle_digest=_digest(f"maximum-discrepancy-reference-{index}"),
            coordinate_policy_digest=_digest(f"maximum-discrepancy-coordinate-{index}"),
            intended_use_evidence_digest=stale_intended_use_digest,
            assay_protocol_version="9.9.9",
            specimen_processing_version="9.9.9",
            unit_definition_version="9.9.9",
            evidence_state=ProteoformRawEvidenceState.MISSING,
            completeness_state=ProteoformRawCompletenessState.INCOMPLETE,
            assay_support_state=ProteoformRawAssaySupportState.UNSUPPORTED,
            parent_quality_state=ProteoformRawParentQualityState.REJECTED,
        )
        if isinstance(document, MassSpectrometryProteomeInputDocument):
            payload.update(
                applicability=ProteoformApplicability.TOP_DOWN,
                protein_unit=ProteinQuantificationUnit.MOLAR_FRACTION,
                protein_scale=ProteoformQuantificationScale.LINEAR,
            )
        elif isinstance(document, GenomeInputDocument):
            payload.update(
                genome_convention=CoordinateConvention.ZERO_BASED_HALF_OPEN,
                genome_reference_digest=_digest("maximum-discrepancy-genome-reference"),
                coordinate_mapping_version="9.9.9",
            )
        elif isinstance(document, TranscriptomeInputDocument):
            payload.update(
                transcript_unit=TranscriptQuantificationUnit.NORMALIZED_COUNT,
                transcript_scale=ProteoformQuantificationScale.LINEAR,
                transcript_convention=CoordinateConvention.ZERO_BASED_HALF_OPEN,
                transcript_annotation_digest=_digest("maximum-discrepancy-transcript-annotation"),
                transcript_protein_mapping_digest=_digest(
                    "maximum-discrepancy-transcript-protein-mapping"
                ),
            )
        else:
            payload.update(
                modification_vocabulary_id=_opaque("vocabulary", "maximum-discrepancy-vocabulary"),
                modification_vocabulary_version="9.9.9",
                modification_vocabulary_digest=_digest(
                    "maximum-discrepancy-modification-vocabulary"
                ),
                protein_convention=CoordinateConvention.ZERO_BASED_HALF_OPEN,
                coordinate_mapping_version="9.9.9",
            )
        documents.append(document_types[index].model_validate(payload, strict=True))

    maximum_documents = tuple(documents)
    diagnostics = expected_diagnostics(maximum_request, maximum_documents)
    keys = tuple((item.code, item.role) for item in diagnostics)
    assert len(diagnostics) == MAXIMUM_DISCREPANCY_DIAGNOSTIC_COUNT
    assert len(diagnostics) <= M0403_MAX_DIAGNOSTICS
    assert len(keys) == len(set(keys))
    assert expected_diagnostics(maximum_request, tuple(reversed(maximum_documents))) == diagnostics

    protocol_diagnostic = next(
        item
        for item in diagnostics
        if item.code is ProteoformRawDiagnosticCode.PROTOCOL_BINDING_MISMATCH
        and item.role is ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME
    )
    inner_bases = tuple(
        sorted(
            {
                sha256_digest(
                    {
                        "code": ProteoformRawDiagnosticCode.PROTOCOL_BINDING_MISMATCH,
                        "role": ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME,
                        "basis": basis,
                    }
                )
                for basis in (stale_protocol_digest, stale_intended_use_digest)
            }
        )
    )
    assert protocol_diagnostic.evidence_basis_digest == sha256_digest(
        {
            "code": ProteoformRawDiagnosticCode.PROTOCOL_BINDING_MISMATCH,
            "role": ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME,
            "bases": inner_bases,
        }
    )

    result = _result(maximum_request, maximum_documents)
    assert isinstance(result, ProteoformRawInputValidationResult)
    assert result.disposition is ProteoformRawInputDisposition.QUARANTINED
    assert result.diagnostics == diagnostics
    assert len(result.validated_inputs) == M0403_ROLE_COUNT


@pytest.mark.contract
@pytest.mark.parametrize(
    ("case_id", "expected_disposition", "expected_code"),
    [
        (
            "valid_quarantined_m0401_quarantines",
            ProteoformRawInputDisposition.QUARANTINED,
            ProteoformRawDiagnosticCode.UPSTREAM_LINEAGE_QUARANTINED,
        ),
        (
            "valid_unresolved_identity_abstains",
            ProteoformRawInputDisposition.ABSTAINED,
            ProteoformRawDiagnosticCode.UPSTREAM_LINEAGE_ABSTAINED,
        ),
    ],
)
def test_genuine_nonreconciled_upstream_closes_to_zero_inputs(
    case_id: str,
    expected_disposition: ProteoformRawInputDisposition,
    expected_code: ProteoformRawDiagnosticCode,
) -> None:
    request = _genuine_request(_genuine_lineage(case_id))
    result = _result(request)
    assert result.disposition is expected_disposition
    assert result.validated_inputs == ()
    assert tuple(item.code for item in result.diagnostics) == (expected_code,)
    assert result.receipt.diagnostic_codes == (expected_code,)
    assert result.human_review_required is True

    forged = result.model_dump(mode="python", exclude_none=False)
    canonical_document = _documents(_genuine_request())[0]
    forged_diagnostics = expected_diagnostics(request, ())
    forged_inputs = expected_validated_inputs(
        request,
        (canonical_document,),
        forged_diagnostics,
    )
    forged["validated_inputs"] = forged_inputs
    forged["receipt"] = expected_receipt(
        request,
        forged_inputs,
        forged_diagnostics,
        expected_disposition,
    )
    forged["provenance"] = expected_provenance(
        request,
        result.request_digest,
        forged_inputs,
    )
    forged["result_digest"] = result_payload_digest(forged)
    with pytest.raises(ValidationError):
        ProteoformRawInputValidationResult.model_validate(forged, strict=True)


@pytest.mark.contract
def test_public_digest_helpers_cover_every_canonical_region() -> None:
    request = _genuine_request()
    result = _result(request)
    parser = request.policy.approved_parsers[0]
    artifact = request.artifacts[0]
    validated_input = result.validated_inputs[0]
    diagnostic = ProteoformRawParseDiagnostic(
        role=None,
        code=ProteoformRawDiagnosticCode.DUPLICATE_CONTENT_RETAINED,
        action=ProteoformRawDiagnosticAction.RECORD,
        evidence_basis_digest=_digest("canonical-helper-diagnostic"),
    )

    assert parser_digest(parser) == sha256_digest(parser.model_dump(mode="python"))
    assert artifact_digest(artifact) == sha256_digest(artifact.model_dump(mode="python"))
    assert artifact_mapping_digest(request.artifacts) == result.receipt.artifact_mapping_digest
    assert document_digest(validated_input.document) == validated_input.document_digest
    assert validated_input_digest(validated_input).startswith("sha256:")
    assert (
        validated_inputs_digest(result.validated_inputs) == result.receipt.validated_inputs_digest
    )
    assert diagnostic_digest(diagnostic) == sha256_digest(diagnostic.model_dump(mode="python"))
    assert normalized_result(result) == result.model_dump(mode="python", exclude_none=False)


@pytest.mark.contract
def test_parser_policy_and_artifact_role_constraints_reject_independently() -> None:
    request = _genuine_request()
    parser = request.policy.approved_parsers[0]

    wrong_format = parser.model_dump(mode="python", exclude_none=False)
    wrong_format["format"] = ProteoformRawDocumentFormat.GENOME_MANIFEST_JSON
    with pytest.raises(ValidationError):
        ApprovedProteoformRawParser.model_validate(wrong_format, strict=True)

    wrong_media_type = parser.model_dump(mode="python", exclude_none=False)
    wrong_media_type["media_type"] = ROLE_CONTENT_MEDIA_TYPES[ProteoformRawInputRole.GENOME]
    with pytest.raises(ValidationError):
        ApprovedProteoformRawParser.model_validate(wrong_media_type, strict=True)

    duplicate_parsers = request.policy.model_dump(mode="python", exclude_none=False)
    approved_parsers = list(
        cast("tuple[dict[str, object], ...]", duplicate_parsers["approved_parsers"])
    )
    approved_parsers[-1] = approved_parsers[0]
    duplicate_parsers["approved_parsers"] = tuple(approved_parsers)
    with pytest.raises(ValidationError):
        ProteoformRawInputPolicy.model_validate(duplicate_parsers, strict=True)

    total_below_document = request.policy.model_dump(mode="python", exclude_none=False)
    total_below_document["max_total_bytes"] = M0403_ROLE_COUNT
    with pytest.raises(ValidationError):
        ProteoformRawInputPolicy.model_validate(total_below_document, strict=True)

    parser_above_policy = request.policy.model_dump(mode="python", exclude_none=False)
    parser_above_policy["max_document_bytes"] = M0403_MAX_DOCUMENT_BYTES - 1
    with pytest.raises(ValidationError):
        ProteoformRawInputPolicy.model_validate(parser_above_policy, strict=True)

    artifact = request.artifacts[0]
    wrong_manifest_type = artifact.model_dump(mode="python", exclude_none=False)
    manifest_reference = cast("dict[str, object]", wrong_manifest_type["manifest_reference"])
    manifest_reference["media_type"] = "application/json"
    with pytest.raises(ValidationError):
        ProteoformRawInputArtifact.model_validate(wrong_manifest_type, strict=True)

    wrong_artifact_format = artifact.model_dump(mode="python", exclude_none=False)
    wrong_artifact_format["format"] = ProteoformRawDocumentFormat.GENOME_MANIFEST_JSON
    with pytest.raises(ValidationError):
        ProteoformRawInputArtifact.model_validate(wrong_artifact_format, strict=True)
