"""Contract freeze tests for M05-03 ptm_localization raw-input ingestion."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from typing import Any, ClassVar, NoReturn, cast

import pytest
from evals.m05_02.run import build_scenario_request as build_m0502_request
from evals.m05_03.run import build_scenario as build_m0503_scenario
from evals.m05_03.run import canonical_smoke
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts import m05_03
from glio_proteogen.contracts.m05_01 import (
    PtmLocalizationInputRole,
)
from glio_proteogen.contracts.m05_02 import (
    PtmLocalizationIdentityLineageResolution,
    PtmLocalizationLineageArtifactRole,
)
from glio_proteogen.contracts.m05_02 import (
    result_payload_digest as m0502_result_payload_digest,
)
from glio_proteogen.contracts.m05_03 import (
    M0503_CONTRACT_VERSION,
    M0503_DIAGNOSTIC_CODE_COUNT,
    M0503_LIMITATION_COUNT,
    M0503_MAX_APPROVED_PARSERS,
    M0503_MAX_CANONICAL_REQUEST_BYTES,
    M0503_MAX_DECLARED_RECORD_COUNT,
    M0503_MAX_DIAGNOSTICS,
    M0503_MAX_DOCUMENT_BYTES,
    M0503_MAX_EVIDENCE,
    M0503_MAX_TOTAL_DOCUMENT_BYTES,
    M0503_MIN_APPROVED_PARSERS,
    M0503_MIN_EVIDENCE,
    M0503_MIN_RECONCILED_EVIDENCE,
    M0503_MODULE_ID,
    M0503_OPERATION,
    M0503_PARENT,
    M0503_ROLE_COUNT,
    ApprovedPtmLocalizationRawParser,
    GenomeInputDocument,
    IngestPtmLocalizationRawInputsRequest,
    MassSpectrometryProteomeInputDocument,
    PtmAnnotationInputDocument,
    PtmLocalizationRawAssaySupportState,
    PtmLocalizationRawCompletenessState,
    PtmLocalizationRawDiagnosticAction,
    PtmLocalizationRawDiagnosticCode,
    PtmLocalizationRawDocumentFormat,
    PtmLocalizationRawEvidenceState,
    PtmLocalizationRawInputArtifact,
    PtmLocalizationRawInputDisposition,
    PtmLocalizationRawInputPolicy,
    PtmLocalizationRawInputReceipt,
    PtmLocalizationRawInputRole,
    PtmLocalizationRawInputValidationResult,
    PtmLocalizationRawParentQualityState,
    PtmLocalizationRawParseDiagnostic,
    PtmLocalizationRawReferenceRole,
    PtmLocalizationRawVocabularyBinding,
    TranscriptomeInputDocument,
    ValidatedPtmLocalizationRawInput,
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
    normalized_parser,
    normalized_request,
    normalized_result,
    parser_digest,
    policy_digest,
    raw_input_evidence_index,
    receipt_digest,
    result_payload_digest,
    validated_input_digest,
    validated_inputs_digest,
)
from glio_proteogen.contracts.m05_03 import canonical as m0503_canonical
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ContextReferences,
    EstimateState,
    ExecutionContext,
    SupportStatus,
)
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c05_ptm_localization.m05_02_identity_lineage import (
    reconcile_ptm_localization_identity_lineage,
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
SCENARIO_PATH = Path(__file__).parents[1] / "fixtures" / "m05_03" / "scenarios.json"
EXPECTED_GROUP_COUNT = 8
EXPECTED_CASE_COUNT = 72
MAXIMUM_DISCREPANCY_DIAGNOSTIC_COUNT = 56
EXPECTED_MIN_RECONCILED_EVIDENCE = 20
EXPECTED_MIN_SAFE_EVIDENCE = 12
_ZERO_DIGEST = "sha256:" + ("0" * 64)

PUBLIC_CONTRACT_SYMBOLS = {
    "CONTRACT_VERSION",
    "M0503_CONTRACT_VERSION",
    "M0503_DIAGNOSTIC_CODE_COUNT",
    "M0503_LIMITATION_COUNT",
    "M0503_MAX_APPROVED_PARSERS",
    "M0503_MAX_CANONICAL_REQUEST_BYTES",
    "M0503_MAX_DECLARED_RECORD_COUNT",
    "M0503_MAX_DIAGNOSTICS",
    "M0503_MAX_DOCUMENT_BYTES",
    "M0503_MAX_EVIDENCE",
    "M0503_MAX_TOTAL_DOCUMENT_BYTES",
    "M0503_MIN_APPROVED_PARSERS",
    "M0503_MIN_EVIDENCE",
    "M0503_MIN_RECONCILED_EVIDENCE",
    "M0503_MODULE_ID",
    "M0503_OPERATION",
    "M0503_PARENT",
    "M0503_ROLE_COUNT",
    "SCHEMA_ID_PREFIX",
    "ApprovedPtmLocalizationRawParser",
    "ContractName",
    "GenomeInputDocument",
    "IngestPtmLocalizationRawInputsRequest",
    "MassSpectrometryProteomeInputDocument",
    "PtmLocalizationRawAssaySupportState",
    "PtmLocalizationRawCompletenessState",
    "PtmLocalizationRawDiagnosticAction",
    "PtmLocalizationRawDiagnosticCode",
    "PtmLocalizationRawDocumentFormat",
    "PtmLocalizationRawEvidenceState",
    "PtmLocalizationRawInputArtifact",
    "PtmLocalizationRawInputDisposition",
    "PtmLocalizationRawInputOpaqueNamespace",
    "PtmLocalizationRawInputPolicy",
    "PtmLocalizationRawInputReceipt",
    "PtmLocalizationRawInputRole",
    "PtmLocalizationRawInputValidationResult",
    "PtmLocalizationRawParentQualityState",
    "PtmLocalizationRawParseDiagnostic",
    "PtmLocalizationRawReferenceRole",
    "PtmLocalizationRawVocabularyBinding",
    "PtmAnnotationInputDocument",
    "TranscriptomeInputDocument",
    "ValidatedPtmLocalizationRawInput",
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
    "opaque_ptm_localization_raw_input_identifier",
    "parser_digest",
    "policy_digest",
    "raw_input_evidence_index",
    "receipt_digest",
    "result_payload_digest",
    "validated_input_digest",
    "validated_inputs_digest",
}

QUARANTINE_CODES = (
    PtmLocalizationRawDiagnosticCode.UPSTREAM_LINEAGE_QUARANTINED,
    PtmLocalizationRawDiagnosticCode.MANIFEST_CLAIM_MISMATCH,
    PtmLocalizationRawDiagnosticCode.IDENTITY_BINDING_MISMATCH,
    PtmLocalizationRawDiagnosticCode.PROTOCOL_BINDING_MISMATCH,
    PtmLocalizationRawDiagnosticCode.REFERENCE_BUNDLE_MISMATCH,
    PtmLocalizationRawDiagnosticCode.ASSAY_SPECIMEN_POLICY_MISMATCH,
    PtmLocalizationRawDiagnosticCode.UNSUPPORTED_MEDIA_TYPE,
    PtmLocalizationRawDiagnosticCode.UNSUPPORTED_FORMAT_VERSION,
    PtmLocalizationRawDiagnosticCode.UNIT_MISMATCH,
    PtmLocalizationRawDiagnosticCode.ASSAY_PROTOCOL_MISMATCH,
    PtmLocalizationRawDiagnosticCode.SPECIMEN_PROCESSING_MISMATCH,
    PtmLocalizationRawDiagnosticCode.INCOMPLETE_MANIFEST,
    PtmLocalizationRawDiagnosticCode.ASSAY_UNSUPPORTED,
    PtmLocalizationRawDiagnosticCode.PARENT_QUALITY_UNACCEPTABLE,
)


def _digest(label: str) -> str:
    return sha256_digest({"m0503_contract_test": label})


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
    PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
        PtmLocalizationRawDocumentFormat.PROTEOME_MANIFEST_JSON
    ),
    PtmLocalizationRawInputRole.GENOME: PtmLocalizationRawDocumentFormat.GENOME_MANIFEST_JSON,
    PtmLocalizationRawInputRole.TRANSCRIPTOME: (
        PtmLocalizationRawDocumentFormat.TRANSCRIPTOME_MANIFEST_JSON
    ),
    PtmLocalizationRawInputRole.PTM_ANNOTATIONS: (
        PtmLocalizationRawDocumentFormat.PTM_ANNOTATION_MANIFEST_JSON
    ),
}
ROLE_CONTENT_MEDIA_TYPES = {
    PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
        "application/vnd.glio-proteogen.m05-03.proteome-input+json"
    ),
    PtmLocalizationRawInputRole.GENOME: ("application/vnd.glio-proteogen.m05-03.genome-input+json"),
    PtmLocalizationRawInputRole.TRANSCRIPTOME: (
        "application/vnd.glio-proteogen.m05-03.transcriptome-input+json"
    ),
    PtmLocalizationRawInputRole.PTM_ANNOTATIONS: (
        "application/vnd.glio-proteogen.m05-03.ptm-annotation-input+json"
    ),
}
ROLE_PROJECTION = {
    PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
        PtmLocalizationLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST
    ),
    PtmLocalizationRawInputRole.GENOME: PtmLocalizationLineageArtifactRole.GENOME_MANIFEST,
    PtmLocalizationRawInputRole.TRANSCRIPTOME: (
        PtmLocalizationLineageArtifactRole.TRANSCRIPTOME_MANIFEST
    ),
    PtmLocalizationRawInputRole.PTM_ANNOTATIONS: (
        PtmLocalizationLineageArtifactRole.PTM_ANNOTATION_MANIFEST
    ),
}


def _genuine_lineage(
    case_id: str = "canonical_reconciled",
) -> PtmLocalizationIdentityLineageResolution:
    return reconcile_ptm_localization_identity_lineage(build_m0502_request(case_id))


def _genuine_request(
    lineage: PtmLocalizationIdentityLineageResolution | None = None,
) -> IngestPtmLocalizationRawInputsRequest:
    if lineage is None:
        return build_m0503_scenario().request
    lineage = lineage or _genuine_lineage()
    parsers = tuple(
        ApprovedPtmLocalizationRawParser(
            role=role,
            format=ROLE_FORMATS[role],
            format_version="1.0.0",
            parser_version="1.0.0",
            media_type=ROLE_CONTENT_MEDIA_TYPES[role],
            max_document_bytes=M0503_MAX_DOCUMENT_BYTES,
            evidence=_reference(
                "evidence",
                f"parser-{role.value}",
                "application/vnd.glio-proteogen.m05-03.parser+json",
            ),
        )
        for role in PtmLocalizationRawInputRole
    )
    policy = PtmLocalizationRawInputPolicy(
        policy_id=_opaque("policy", "canonical"),
        version="1.0.0",
        approved_parsers=parsers,
        evidence=_reference(
            "evidence",
            "policy",
            "application/vnd.glio-proteogen.m05-03.policy+json",
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
    for role in PtmLocalizationRawInputRole if lineage.disposition.value == "reconciled" else ():
        claim = next(
            item for item in lineage.request.artifact_claims if item.role is ROLE_PROJECTION[role]
        )
        artifacts.append(
            PtmLocalizationRawInputArtifact(
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
    return IngestPtmLocalizationRawInputsRequest(
        request_id=context.request_id,
        context=context,
        lineage_result=lineage,
        policy=policy,
        artifacts=tuple(artifacts),
    )


def _request_with_policy(
    request: IngestPtmLocalizationRawInputsRequest,
    policy: PtmLocalizationRawInputPolicy,
    *,
    artifacts: tuple[PtmLocalizationRawInputArtifact, ...] | None = None,
) -> IngestPtmLocalizationRawInputsRequest:
    references = request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    context = request.context.model_copy(
        update={"references": references.model_copy(update={"approved_configuration": approved})}
    )
    return IngestPtmLocalizationRawInputsRequest(
        request_id=context.request_id,
        context=context,
        lineage_result=request.lineage_result,
        policy=policy,
        artifacts=request.artifacts if artifacts is None else artifacts,
        supersedes_result_digest=request.supersedes_result_digest,
    )


def _documents(
    request: IngestPtmLocalizationRawInputsRequest,
) -> tuple[
    MassSpectrometryProteomeInputDocument
    | GenomeInputDocument
    | TranscriptomeInputDocument
    | PtmAnnotationInputDocument,
    ...,
]:
    protocol = request.lineage_result.request.protocol_result.request.protocol_schema
    assay_policy = protocol.assay_specimen_policy
    references = {item.role: item.reference.digest for item in protocol.reference_bundle.references}
    artifacts = {item.role: item for item in request.artifacts}

    def common(role: PtmLocalizationRawInputRole) -> dict[str, object]:
        artifact = artifacts[role]
        return {
            "input_id": artifact.content_reference.artifact_id,
            "lineage_claim_id": artifact.lineage_claim_id,
            "identity_resolution_digest": request.lineage_result.identity_resolution_digest,
            "protocol_result_digest": request.lineage_result.protocol_result_digest,
            "reference_bundle_digest": request.lineage_result.receipt.reference_bundle_digest,
            "assay_specimen_policy_digest": (
                request.lineage_result.receipt.assay_specimen_policy_digest
            ),
            "intended_use_evidence_digest": (
                request.lineage_result.receipt.intended_use_evidence_digest
            ),
            "assay_protocol_version": assay_policy.assay_protocol_version,
            "specimen_processing_version": assay_policy.specimen_processing_version,
            "unit_system_version": protocol.unit_system_version,
            "reference_bundle_version": protocol.reference_bundle.version,
            "content_reference": artifact.content_reference,
            "declared_record_count": 1,
            "evidence_state": PtmLocalizationRawEvidenceState.AVAILABLE,
            "completeness_state": PtmLocalizationRawCompletenessState.COMPLETE,
            "assay_support_state": PtmLocalizationRawAssaySupportState.SUPPORTED,
            "parent_quality_state": PtmLocalizationRawParentQualityState.ACCEPTED,
        }

    proteome = MassSpectrometryProteomeInputDocument.model_validate(
        {
            **common(PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME),
            "reference_role": PtmLocalizationRawReferenceRole.MASS_SPECTROMETRY_PROTEOME,
            "reference_digest": references[PtmLocalizationInputRole.MASS_SPECTROMETRY_PROTEOME],
            "assay_kind": assay_policy.assay_kind,
            "support_domain": assay_policy.support_domain,
            "declared_units": tuple(item.unit for item in protocol.unit_policies),
        },
        strict=True,
    )
    genome = GenomeInputDocument.model_validate(
        {
            **common(PtmLocalizationRawInputRole.GENOME),
            "reference_role": PtmLocalizationRawReferenceRole.GENOME_TRANSCRIPTOME,
            "reference_digest": references[PtmLocalizationInputRole.GENOME_TRANSCRIPTOME],
            "reference_build": protocol.reference_bundle.bundle_id,
        },
        strict=True,
    )
    transcriptome = TranscriptomeInputDocument.model_validate(
        {
            **common(PtmLocalizationRawInputRole.TRANSCRIPTOME),
            "reference_role": PtmLocalizationRawReferenceRole.GENOME_TRANSCRIPTOME,
            "reference_digest": references[PtmLocalizationInputRole.GENOME_TRANSCRIPTOME],
            "annotation_build": protocol.reference_bundle.bundle_id,
        },
        strict=True,
    )
    ptm = PtmAnnotationInputDocument.model_validate(
        {
            **common(PtmLocalizationRawInputRole.PTM_ANNOTATIONS),
            "reference_role": PtmLocalizationRawReferenceRole.PTM_ANNOTATIONS,
            "reference_digest": references[PtmLocalizationInputRole.PTM_ANNOTATIONS],
            "vocabularies": tuple(
                PtmLocalizationRawVocabularyBinding(
                    vocabulary_id=item.vocabulary_id,
                    version=item.version,
                )
                for item in protocol.controlled_vocabularies
            ),
            "vocabularies_digest": sha256_digest(tuple(protocol.controlled_vocabularies)),
        },
        strict=True,
    )
    return (proteome, genome, transcriptome, ptm)


def _result(
    request: IngestPtmLocalizationRawInputsRequest,
    documents: tuple[
        MassSpectrometryProteomeInputDocument
        | GenomeInputDocument
        | TranscriptomeInputDocument
        | PtmAnnotationInputDocument,
        ...,
    ]
    | None = None,
) -> PtmLocalizationRawInputValidationResult:
    if documents is None:
        documents = (
            _documents(request) if request.lineage_result.disposition.value == "reconciled" else ()
        )
    diagnostics = expected_diagnostics(request, documents)
    inputs = expected_validated_inputs(request, documents, diagnostics)
    actions = {item.action for item in diagnostics}
    disposition = (
        PtmLocalizationRawInputDisposition.QUARANTINED
        if PtmLocalizationRawDiagnosticAction.QUARANTINE in actions
        else PtmLocalizationRawInputDisposition.ABSTAINED
        if PtmLocalizationRawDiagnosticAction.ABSTAIN in actions
        else PtmLocalizationRawInputDisposition.VALIDATED
    )
    request_hash = canonical_request_digest(request)
    payload: dict[str, object] = {
        "output_type": "ptm_localization_raw_input_validation_result",
        "result_id": f"result.m0503.{request_hash.removeprefix('sha256:')}",
        "result_version": "1.0.0",
        "request_digest": request_hash,
        "lineage_result_digest": request.lineage_result.result_digest,
        "policy_digest": policy_digest(request.policy),
        "configuration_digest": configuration_digest(request.policy),
        "context_digest": context_digest(request),
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "receipt": expected_receipt(request, inputs, diagnostics, disposition),
        "validated_inputs": inputs,
        "diagnostics": diagnostics,
        "disposition": disposition,
        "parent_target": M0503_PARENT,
        "emits_variant_peptide": False,
        "emits_proteogenomic_state": False,
        "emits_proteotype": False,
        "emits_protein_level_subtype": False,
        "infers_identity": False,
        "infers_consent": False,
        "infers_protein": False,
        "infers_proteoform": False,
        "infers_ptm_localization": False,
        "infers_kinase_activity": False,
        "performs_cn_to_protein_regression": False,
        "performs_all_omics_fusion": False,
        "recommends_treatment": False,
        "mutates_upstream": False,
        "executes_model": False,
        "persists_events": False,
        "support": expected_support(disposition),
        "uncertainty": expected_uncertainty(),
        "provenance": expected_provenance(request, request_hash, inputs),
        "evidence": raw_input_evidence_index(request),
        "limitations": expected_limitations(),
        "human_review_required": disposition is not PtmLocalizationRawInputDisposition.VALIDATED,
        "completed_at": request.context.occurred_at,
    }
    payload["result_digest"] = result_payload_digest(payload)
    return PtmLocalizationRawInputValidationResult.model_validate(payload, strict=True)


def _receipt_payload(
    *,
    codes: tuple[PtmLocalizationRawDiagnosticCode, ...] = (),
    disposition: PtmLocalizationRawInputDisposition = PtmLocalizationRawInputDisposition.VALIDATED,
) -> dict[str, object]:
    digest_fields = (
        "identity_resolution_digest",
        "protocol_result_digest",
        "protocol_receipt_digest",
        "lineage_result_digest",
        "lineage_receipt_digest",
        "lineage_graph_digest",
        "reference_bundle_digest",
        "assay_specimen_policy_digest",
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
            "parent_target": "variant_peptide",
            "emits_variant_peptide": False,
            "disposition": disposition,
            "receipt_digest": _ZERO_DIGEST,
        }
    )
    payload["receipt_digest"] = receipt_digest(payload)
    return payload


@pytest.mark.contract
def test_identity_and_installed_caps_are_exact() -> None:
    assert (M0503_MODULE_ID, M0503_CONTRACT_VERSION, M0503_OPERATION, M0503_PARENT) == (
        "GLIO-PROTEOGEN-M05-03",
        "1.0.0",
        "ingest_ptm_localization_raw_inputs",
        "variant_peptide",
    )
    assert (
        M0503_ROLE_COUNT,
        M0503_MIN_APPROVED_PARSERS,
        M0503_MAX_APPROVED_PARSERS,
        M0503_MAX_CANONICAL_REQUEST_BYTES,
        M0503_MAX_DOCUMENT_BYTES,
        M0503_MAX_TOTAL_DOCUMENT_BYTES,
        M0503_MAX_DECLARED_RECORD_COUNT,
    ) == (4, 4, 32, 4 * 1024 * 1024, 8 * 1024 * 1024, 32 * 1024 * 1024, 2**63 - 1)
    assert (
        M0503_DIAGNOSTIC_CODE_COUNT,
        M0503_MAX_DIAGNOSTICS,
        M0503_LIMITATION_COUNT,
        M0503_MIN_EVIDENCE,
        M0503_MAX_EVIDENCE,
    ) == (17, 60, 3, 12, 48)
    assert M0503_MIN_RECONCILED_EVIDENCE == EXPECTED_MIN_RECONCILED_EVIDENCE


@pytest.mark.contract
def test_public_contract_surface_is_explicit_and_exact() -> None:
    assert set(m05_03.__all__) == PUBLIC_CONTRACT_SYMBOLS


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
    assert tuple(item.value for item in PtmLocalizationRawInputRole) == (
        "mass_spectrometry_proteome",
        "genome",
        "transcriptome",
        "ptm_annotations",
    )
    assert tuple(item.value for item in PtmLocalizationRawDocumentFormat) == (
        "proteome_manifest_json",
        "genome_manifest_json",
        "transcriptome_manifest_json",
        "ptm_annotation_manifest_json",
    )
    assert tuple(item.value for item in PtmLocalizationRawEvidenceState) == (
        "available",
        "missing",
        "indeterminate",
        "unsupported",
        "redacted",
    )
    assert tuple(item.value for item in PtmLocalizationRawCompletenessState) == (
        "complete",
        "incomplete",
        "not_evaluable",
    )
    assert tuple(item.value for item in PtmLocalizationRawAssaySupportState) == (
        "supported",
        "unsupported",
        "not_evaluable",
    )
    assert tuple(item.value for item in PtmLocalizationRawParentQualityState) == (
        "accepted",
        "rejected",
        "not_evaluable",
    )
    assert tuple(item.value for item in PtmLocalizationRawInputDisposition) == (
        "validated",
        "quarantined",
        "abstained",
    )
    assert tuple(item.value for item in PtmLocalizationRawDiagnosticAction) == (
        "record",
        "quarantine",
        "abstain",
    )
    assert tuple(item.value for item in PtmLocalizationRawDiagnosticCode) == (
        "upstream_lineage_quarantined",
        "upstream_lineage_abstained",
        "artifact_not_evaluable",
        "manifest_claim_mismatch",
        "identity_binding_mismatch",
        "protocol_binding_mismatch",
        "reference_bundle_mismatch",
        "assay_specimen_policy_mismatch",
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
        assert metadata["moduleId"] == M0503_MODULE_ID
        assert metadata["contractVersion"] == M0503_CONTRACT_VERSION
        assert metadata["strict"] is True
        assert metadata["rawPayload"] is False
        assert metadata["externalContentTraversal"] is False
        assert metadata["parentTarget"] == M0503_PARENT
        for key in (
            "identityInference",
            "consentInference",
            "proteinInference",
            "ptm_localizationInference",
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
@pytest.mark.parametrize("code", tuple(PtmLocalizationRawDiagnosticCode))
def test_diagnostic_code_action_mapping_is_closed(code: PtmLocalizationRawDiagnosticCode) -> None:
    expected = (
        PtmLocalizationRawDiagnosticAction.RECORD
        if code is PtmLocalizationRawDiagnosticCode.DUPLICATE_CONTENT_RETAINED
        else PtmLocalizationRawDiagnosticAction.ABSTAIN
        if code
        in {
            PtmLocalizationRawDiagnosticCode.UPSTREAM_LINEAGE_ABSTAINED,
            PtmLocalizationRawDiagnosticCode.ARTIFACT_NOT_EVALUABLE,
        }
        else PtmLocalizationRawDiagnosticAction.QUARANTINE
    )
    diagnostic = PtmLocalizationRawParseDiagnostic(
        role=None,
        code=code,
        action=expected,
        evidence_basis_digest=_digest(code.value),
    )
    assert diagnostic.action is expected
    wrong = (
        PtmLocalizationRawDiagnosticAction.RECORD
        if expected is not PtmLocalizationRawDiagnosticAction.RECORD
        else PtmLocalizationRawDiagnosticAction.QUARANTINE
    )
    with pytest.raises(ValidationError):
        PtmLocalizationRawParseDiagnostic(
            role=None,
            code=code,
            action=wrong,
            evidence_basis_digest=_digest(f"wrong-{code.value}"),
        )


@pytest.mark.contract
def test_receipt_uses_scalar_aggregate_digests_and_closed_precedence() -> None:
    codes = (
        PtmLocalizationRawDiagnosticCode.ARTIFACT_NOT_EVALUABLE,
        PtmLocalizationRawDiagnosticCode.MANIFEST_CLAIM_MISMATCH,
    )
    payload = _receipt_payload(
        codes=codes,
        disposition=PtmLocalizationRawInputDisposition.QUARANTINED,
    )
    receipt = PtmLocalizationRawInputReceipt.model_validate(payload, strict=True)
    assert receipt.diagnostic_codes == tuple(sorted(codes))
    assert receipt.disposition is PtmLocalizationRawInputDisposition.QUARANTINED
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
        PtmLocalizationRawInputReceipt.model_validate(stale, strict=True)

    wrong_disposition = dict(payload)
    wrong_disposition["disposition"] = PtmLocalizationRawInputDisposition.ABSTAINED
    wrong_disposition["receipt_digest"] = receipt_digest(wrong_disposition)
    with pytest.raises(ValidationError):
        PtmLocalizationRawInputReceipt.model_validate(wrong_disposition, strict=True)


@pytest.mark.contract
def test_support_uncertainty_and_limitations_are_exact() -> None:
    expected_status = {
        PtmLocalizationRawInputDisposition.VALIDATED: SupportStatus.SUPPORTED,
        PtmLocalizationRawInputDisposition.QUARANTINED: SupportStatus.REVIEW_REQUIRED,
        PtmLocalizationRawInputDisposition.ABSTAINED: SupportStatus.UNSUPPORTED,
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
                "no_variant_peptide_or_clinical_inference",
            )
        )
    )


@pytest.mark.contract
def test_every_quarantine_code_is_accounted_for() -> None:
    assert set(QUARANTINE_CODES) == set(PtmLocalizationRawDiagnosticCode) - {
        PtmLocalizationRawDiagnosticCode.UPSTREAM_LINEAGE_ABSTAINED,
        PtmLocalizationRawDiagnosticCode.ARTIFACT_NOT_EVALUABLE,
        PtmLocalizationRawDiagnosticCode.DUPLICATE_CONTENT_RETAINED,
    }


@pytest.mark.contract
def test_genuine_m0502_projection_and_semantic_reorder_are_exact() -> None:
    request = _genuine_request()
    upstream = {item.claim_id: item for item in request.lineage_result.request.artifact_claims}
    assert len(request.artifacts) == M0503_ROLE_COUNT
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
    reordered = IngestPtmLocalizationRawInputsRequest.model_validate(payload, strict=True)
    assert reordered == request
    assert canonical_request_digest(reordered) == canonical_request_digest(request)


@pytest.mark.contract
def test_public_m0503_builder_is_genuine_and_fully_replayable() -> None:
    scenario = build_m0503_scenario()
    result = canonical_smoke()
    assert set(scenario.artifacts_by_role) == set(PtmLocalizationRawInputRole)
    assert all(type(value) is bytes for value in scenario.artifacts_by_role.values())
    assert result.request == scenario.request
    assert result.disposition is PtmLocalizationRawInputDisposition.VALIDATED
    assert len(result.validated_inputs) == M0503_ROLE_COUNT
    assert result.diagnostics == ()
    assert len(result.evidence) == M0503_MIN_RECONCILED_EVIDENCE
    replay = PtmLocalizationRawInputValidationResult.model_validate_json(
        canonical_json_bytes(result),
        strict=True,
    )
    assert replay == result
    normalized_replay = PtmLocalizationRawInputValidationResult.model_validate_json(
        canonical_json_bytes(normalized_result(result)),
        strict=True,
    )
    assert normalized_replay == result
    assert normalized_replay.receipt.receipt_digest == result.receipt.receipt_digest


@pytest.mark.contract
def test_request_enforces_active_parser_and_aggregate_declared_size_caps() -> None:
    request = _genuine_request()
    largest = max(item.declared_size_bytes for item in request.artifacts)

    policy_cap = largest
    policy = PtmLocalizationRawInputPolicy.model_validate(
        request.policy.model_copy(
            update={
                "max_document_bytes": policy_cap,
                "approved_parsers": tuple(
                    item.model_copy(update={"max_document_bytes": policy_cap})
                    for item in request.policy.approved_parsers
                ),
            }
        ).model_dump(mode="python", exclude_none=False),
        strict=True,
    )
    target = request.artifacts[0]
    policy_overflow = tuple(
        item.model_copy(update={"declared_size_bytes": policy_cap + 1})
        if item.role is target.role
        else item
        for item in request.artifacts
    )
    with pytest.raises(ValidationError, match="active document policy cap"):
        _request_with_policy(request, policy, artifacts=policy_overflow)

    parser_cap = target.declared_size_bytes - 1
    parser_policy = PtmLocalizationRawInputPolicy.model_validate(
        request.policy.model_copy(
            update={
                "approved_parsers": tuple(
                    item.model_copy(update={"max_document_bytes": parser_cap})
                    if item.role is target.role
                    else item
                    for item in request.policy.approved_parsers
                )
            }
        ).model_dump(mode="python", exclude_none=False),
        strict=True,
    )
    with pytest.raises(ValidationError, match="matching parser cap"):
        _request_with_policy(request, parser_policy)

    aggregate_policy = PtmLocalizationRawInputPolicy.model_validate(
        request.policy.model_copy(
            update={
                "max_document_bytes": largest,
                "max_total_bytes": largest,
                "approved_parsers": tuple(
                    item.model_copy(update={"max_document_bytes": largest})
                    for item in request.policy.approved_parsers
                ),
            }
        ).model_dump(mode="python", exclude_none=False),
        strict=True,
    )
    assert sum(item.declared_size_bytes for item in request.artifacts) > largest
    with pytest.raises(ValidationError, match="aggregate policy cap"):
        _request_with_policy(request, aggregate_policy)


@pytest.mark.contract
def test_ptm_vocabulary_identifier_versions_remain_bound_and_swaps_are_diagnostic() -> None:
    request = _genuine_request()
    documents = _documents(request)
    original = cast("PtmAnnotationInputDocument", documents[-1])
    first = original.vocabularies[0]
    second = PtmLocalizationRawVocabularyBinding(
        vocabulary_id=_opaque("vocabulary", "second-bound-vocabulary"),
        version="2.0.0",
    )
    paired = PtmAnnotationInputDocument.model_validate(
        original.model_copy(update={"vocabularies": (first, second)}).model_dump(
            mode="python", exclude_none=False
        ),
        strict=True,
    )
    swapped = PtmAnnotationInputDocument.model_validate(
        original.model_copy(
            update={
                "vocabularies": (
                    first.model_copy(update={"version": second.version}),
                    second.model_copy(update={"version": first.version}),
                )
            }
        ).model_dump(mode="python", exclude_none=False),
        strict=True,
    )
    assert {(item.vocabulary_id, item.version) for item in paired.vocabularies} != {
        (item.vocabulary_id, item.version) for item in swapped.vocabularies
    }
    assert document_digest(paired) != document_digest(swapped)
    diagnostics = expected_diagnostics(request, (*documents[:-1], swapped))
    assert any(
        item.role is PtmLocalizationRawInputRole.PTM_ANNOTATIONS
        and item.code is PtmLocalizationRawDiagnosticCode.REFERENCE_BUNDLE_MISMATCH
        for item in diagnostics
    )


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
        IngestPtmLocalizationRawInputsRequest.model_validate(payload, strict=True)

    ambiguous = _genuine_lineage("duplicate_content_recorded")
    retained = _genuine_request(ambiguous)
    assert len(retained.artifacts) == M0503_ROLE_COUNT
    assert len({item.lineage_claim_id for item in retained.artifacts}) == M0503_ROLE_COUNT


@pytest.mark.contract
def test_resigned_full_m0502_forgery_rejects() -> None:
    request = _genuine_request()
    payload = request.model_dump(mode="python", exclude_none=False)
    lineage = cast("dict[str, object]", payload["lineage_result"])
    support = cast("dict[str, object]", lineage["support"])
    support["rationale"] = "A valid-shaped but forged M05-02 support projection."
    lineage["result_digest"] = m0502_result_payload_digest(lineage)
    with pytest.raises(ValidationError):
        IngestPtmLocalizationRawInputsRequest.model_validate(payload, strict=True)


@pytest.mark.contract
def test_exact_dict_embedded_m0502_replays_and_stale_model_mutation_rejects() -> None:
    request = _genuine_request()
    payload = request.model_dump(mode="python", exclude_none=False)
    replayed = IngestPtmLocalizationRawInputsRequest.model_validate(payload, strict=True)
    assert replayed == request
    assert replayed.lineage_result == request.lineage_result

    stale = request.lineage_result.model_copy(deep=True)
    object.__setattr__(
        stale,
        "support",
        stale.support.model_copy(update={"rationale": "stale nested model mutation"}),
    )
    forged = request.model_dump(mode="python", exclude_none=False)
    forged["lineage_result"] = stale
    with pytest.raises(ValidationError):
        IngestPtmLocalizationRawInputsRequest.model_validate(forged, strict=True)

    class LineageSubclass(PtmLocalizationIdentityLineageResolution):
        pass

    subclassed = LineageSubclass.model_validate(
        request.lineage_result.model_dump(mode="python", exclude_none=False),
        strict=True,
    )
    forged["lineage_result"] = subclassed
    with pytest.raises(ValidationError, match="exact model or built-in object"):
        IngestPtmLocalizationRawInputsRequest.model_validate(forged, strict=True)


@pytest.mark.contract
def test_canonical_ingress_never_invokes_overridable_container_or_model_hooks() -> None:
    calls = {"dict": 0, "list": 0, "model": 0}

    class HostileDict(dict[object, object]):
        def items(self) -> NoReturn:
            calls["dict"] += 1
            raise AssertionError

        def __iter__(self) -> NoReturn:
            calls["dict"] += 1
            raise AssertionError

        def __deepcopy__(self, memo: object) -> NoReturn:
            del memo
            calls["dict"] += 1
            raise AssertionError

    class HostileList(list[object]):
        def __iter__(self) -> NoReturn:
            calls["list"] += 1
            raise AssertionError

        def __deepcopy__(self, memo: object) -> NoReturn:
            del memo
            calls["list"] += 1
            raise AssertionError

    class HostileModel(BaseModel):
        value: int
        hook_calls: ClassVar[dict[str, int]] = calls

        def model_dump(self, *args: object, **kwargs: object) -> dict[str, object]:
            del args, kwargs
            self.hook_calls["model"] += 1
            raise AssertionError

        def __deepcopy__(self, memo: dict[int, Any] | None = None) -> NoReturn:
            del memo
            self.hook_calls["model"] += 1
            raise AssertionError

    request_payload = _genuine_request().model_dump(mode="python", exclude_none=False)
    request_payload["policy"] = HostileDict(cast("dict[object, object]", request_payload["policy"]))
    with pytest.raises(TypeError, match="exact built-ins"):
        normalized_request(request_payload)
    with pytest.raises(TypeError, match="exact built-ins"):
        normalized_parser({"values": HostileList([1])})
    assert normalized_parser(HostileModel(value=1)) == {"value": 1}
    exact_request_payload = _genuine_request().model_dump(mode="python", exclude_none=False)
    exact_request_payload["lineage_result"] = HostileDict(
        cast("dict[object, object]", exact_request_payload["lineage_result"])
    )
    with pytest.raises(ValidationError, match="exact model or built-in object"):
        IngestPtmLocalizationRawInputsRequest.model_validate(
            exact_request_payload,
            strict=True,
        )
    assert calls == {"dict": 0, "list": 0, "model": 0}


@pytest.mark.contract
def test_result_replay_rejects_resigned_derived_regions_and_partial_inputs() -> None:
    result = _result(_genuine_request())
    assert result.disposition is PtmLocalizationRawInputDisposition.VALIDATED
    assert len(result.validated_inputs) == M0503_ROLE_COUNT
    assert result.diagnostics == ()

    forged = result.model_dump(mode="python", exclude_none=False)
    cast("dict[str, object]", forged["support"])["rationale"] = (
        "A valid-shaped but forged local support projection."
    )
    forged["result_digest"] = result_payload_digest(forged)
    with pytest.raises(ValidationError):
        PtmLocalizationRawInputValidationResult.model_validate(forged, strict=True)

    partial = result.model_dump(mode="python", exclude_none=False)
    partial_inputs = result.validated_inputs[:-1]
    partial_documents = tuple(item.document for item in partial_inputs)
    partial_diagnostics = expected_diagnostics(result.request, partial_documents)
    replay_inputs = expected_validated_inputs(
        result.request,
        partial_documents,
        partial_diagnostics,
    )
    disposition = PtmLocalizationRawInputDisposition.VALIDATED
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
        PtmLocalizationRawInputValidationResult.model_validate(partial, strict=True)


@pytest.mark.contract
def test_standalone_validated_input_closes_every_relational_projection() -> None:
    result = _result(_genuine_request())
    by_role = {item.role: item for item in result.validated_inputs}
    canonical = by_role[PtmLocalizationRawInputRole.GENOME]
    other = by_role[PtmLocalizationRawInputRole.TRANSCRIPTOME]
    base = canonical.model_dump(mode="python", exclude_none=False)

    mutations: tuple[dict[str, object], ...] = (
        {
            "role": other.role,
            "manifest_reference": other.manifest_reference,
            "format": other.format,
        },
        {"lineage_claim_id": other.lineage_claim_id},
        {"content_reference": other.content_reference},
        {"format": other.format},
        {"manifest_reference": other.manifest_reference},
    )
    for update in mutations:
        candidate = deepcopy(base)
        candidate.update(update)
        with pytest.raises(ValidationError):
            ValidatedPtmLocalizationRawInput.model_validate(candidate, strict=True)

    document_payload = canonical.document.model_dump(mode="python", exclude_none=False)
    document_payload["input_id"] = other.content_reference.artifact_id
    mutated_document = GenomeInputDocument.model_validate(document_payload, strict=True)
    candidate = deepcopy(base)
    candidate["document"] = mutated_document
    candidate["document_digest"] = document_digest(mutated_document)
    with pytest.raises(ValidationError):
        ValidatedPtmLocalizationRawInput.model_validate(candidate, strict=True)


@pytest.mark.contract
def test_resigned_document_projection_cannot_escape_upstream_manifest_digest() -> None:
    result = _result(_genuine_request())
    forged = result.model_dump(mode="python", exclude_none=False)
    inputs = list(cast("tuple[dict[str, object], ...]", forged["validated_inputs"]))
    mutated_input = deepcopy(inputs[0])
    document_payload = deepcopy(cast("dict[str, object]", mutated_input["document"]))
    document_payload["declared_record_count"] = (
        cast("int", document_payload["declared_record_count"]) + 1
    )
    document_type = type(result.validated_inputs[0].document)
    mutated_document = document_type.model_validate(document_payload, strict=True)
    mutated_input["document"] = mutated_document
    mutated_input["document_digest"] = document_digest(mutated_document)
    inputs[0] = mutated_input
    forged_inputs = tuple(inputs)
    forged["validated_inputs"] = forged_inputs
    forged["receipt"] = expected_receipt(
        result.request,
        cast("tuple[ValidatedPtmLocalizationRawInput, ...]", forged_inputs),
        result.diagnostics,
        result.disposition,
    )
    forged["provenance"] = expected_provenance(
        result.request,
        result.request_digest,
        cast("tuple[ValidatedPtmLocalizationRawInput, ...]", forged_inputs),
    )
    forged["result_digest"] = result_payload_digest(forged)
    with pytest.raises(ValidationError):
        PtmLocalizationRawInputValidationResult.model_validate(forged, strict=True)


@pytest.mark.contract
def test_result_semantic_reorder_preserves_full_equality() -> None:
    result = _result(_genuine_request())
    payload = deepcopy(result.model_dump(mode="python", exclude_none=False))
    for field in ("validated_inputs", "diagnostics", "evidence", "limitations"):
        payload[field] = tuple(reversed(cast("tuple[object, ...]", payload[field])))
    provenance = cast("dict[str, object]", payload["provenance"])
    for field in ("input_digests", "control_decisions"):
        provenance[field] = tuple(reversed(cast("tuple[object, ...]", provenance[field])))
    reordered = PtmLocalizationRawInputValidationResult.model_validate(payload, strict=True)
    assert reordered == result
    assert canonical_json_bytes(reordered) == canonical_json_bytes(result)


@pytest.mark.contract
def test_maximum_discrepancy_diagnostics_are_aggregated_and_total() -> None:
    request = _genuine_request()
    shared_content_digest = _digest("maximum-discrepancy-shared-content")
    artifacts = tuple(
        PtmLocalizationRawInputArtifact.model_validate(
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
    maximum_request = IngestPtmLocalizationRawInputsRequest.model_validate(
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
            assay_specimen_policy_digest=_digest(f"maximum-discrepancy-assay-specimen-{index}"),
            intended_use_evidence_digest=stale_intended_use_digest,
            assay_protocol_version="9.9.9",
            specimen_processing_version="9.9.9",
            unit_system_version="9.9.9",
            reference_bundle_version="9.9.9",
            evidence_state=PtmLocalizationRawEvidenceState.MISSING,
            completeness_state=PtmLocalizationRawCompletenessState.INCOMPLETE,
            assay_support_state=PtmLocalizationRawAssaySupportState.UNSUPPORTED,
            parent_quality_state=PtmLocalizationRawParentQualityState.REJECTED,
        )
        if isinstance(document, MassSpectrometryProteomeInputDocument):
            payload.update(
                reference_digest=_digest("maximum-discrepancy-proteome-reference"),
                declared_units=(document.declared_units[0],),
            )
        elif isinstance(document, GenomeInputDocument):
            payload.update(
                reference_digest=_digest("maximum-discrepancy-genome-reference"),
                reference_build=_opaque("bundle", "maximum-discrepancy-genome-build"),
            )
        elif isinstance(document, TranscriptomeInputDocument):
            payload.update(
                reference_digest=_digest("maximum-discrepancy-transcript-reference"),
                annotation_build=_opaque("bundle", "maximum-discrepancy-annotation-build"),
            )
        else:
            payload.update(
                reference_digest=_digest("maximum-discrepancy-ptm-reference"),
                vocabularies_digest=_digest("maximum-discrepancy-vocabularies"),
            )
        documents.append(document_types[index].model_validate(payload, strict=True))

    maximum_documents = tuple(documents)
    diagnostics = expected_diagnostics(maximum_request, maximum_documents)
    keys = tuple((item.code, item.role) for item in diagnostics)
    assert len(diagnostics) == MAXIMUM_DISCREPANCY_DIAGNOSTIC_COUNT
    assert len(diagnostics) <= M0503_MAX_DIAGNOSTICS
    assert len(keys) == len(set(keys))
    assert expected_diagnostics(maximum_request, tuple(reversed(maximum_documents))) == diagnostics

    protocol_diagnostic = next(
        item
        for item in diagnostics
        if item.code is PtmLocalizationRawDiagnosticCode.PROTOCOL_BINDING_MISMATCH
        and item.role is PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME
    )
    inner_bases = tuple(
        sorted(
            {
                sha256_digest(
                    {
                        "code": PtmLocalizationRawDiagnosticCode.PROTOCOL_BINDING_MISMATCH,
                        "role": PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME,
                        "basis": basis,
                    }
                )
                for basis in (stale_protocol_digest, stale_intended_use_digest)
            }
        )
    )
    assert protocol_diagnostic.evidence_basis_digest == sha256_digest(
        {
            "code": PtmLocalizationRawDiagnosticCode.PROTOCOL_BINDING_MISMATCH,
            "role": PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME,
            "bases": inner_bases,
        }
    )

    with pytest.raises(ValidationError):
        _result(maximum_request, maximum_documents)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("case_id", "expected_disposition", "expected_code"),
    [
        (
            "upstream_protocol_quarantined",
            PtmLocalizationRawInputDisposition.QUARANTINED,
            PtmLocalizationRawDiagnosticCode.UPSTREAM_LINEAGE_QUARANTINED,
        ),
        (
            "upstream_identity_unresolved",
            PtmLocalizationRawInputDisposition.ABSTAINED,
            PtmLocalizationRawDiagnosticCode.UPSTREAM_LINEAGE_ABSTAINED,
        ),
    ],
)
def test_genuine_nonreconciled_upstream_closes_to_zero_inputs(
    case_id: str,
    expected_disposition: PtmLocalizationRawInputDisposition,
    expected_code: PtmLocalizationRawDiagnosticCode,
) -> None:
    request = _genuine_request(_genuine_lineage(case_id))
    result = _result(request)
    assert request.artifacts == ()
    assert result.disposition is expected_disposition
    assert result.validated_inputs == ()
    assert M0503_MIN_EVIDENCE == EXPECTED_MIN_SAFE_EVIDENCE
    assert len(result.evidence) == EXPECTED_MIN_SAFE_EVIDENCE
    assert tuple(item.code for item in result.diagnostics) == (expected_code,)
    assert result.receipt.diagnostic_codes == (expected_code,)
    assert result.human_review_required is True

    forged = result.model_dump(mode="python", exclude_none=False)
    canonical_input = _result(_genuine_request()).validated_inputs[0]
    forged_diagnostics = expected_diagnostics(request, ())
    forged_inputs = (canonical_input,)
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
        PtmLocalizationRawInputValidationResult.model_validate(forged, strict=True)


@pytest.mark.contract
def test_public_digest_helpers_cover_every_canonical_region() -> None:
    request = _genuine_request()
    result = _result(request)
    parser = request.policy.approved_parsers[0]
    artifact = request.artifacts[0]
    validated_input = result.validated_inputs[0]
    diagnostic = PtmLocalizationRawParseDiagnostic(
        role=None,
        code=PtmLocalizationRawDiagnosticCode.DUPLICATE_CONTENT_RETAINED,
        action=PtmLocalizationRawDiagnosticAction.RECORD,
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
    assert normalized_result(result) == normalized_result(
        result.model_dump(mode="python", exclude_none=False)
    )


@pytest.mark.contract
def test_parser_policy_and_artifact_role_constraints_reject_independently() -> None:
    request = _genuine_request()
    parser = request.policy.approved_parsers[0]

    wrong_format = parser.model_dump(mode="python", exclude_none=False)
    wrong_format["format"] = PtmLocalizationRawDocumentFormat.GENOME_MANIFEST_JSON
    with pytest.raises(ValidationError):
        ApprovedPtmLocalizationRawParser.model_validate(wrong_format, strict=True)

    wrong_media_type = parser.model_dump(mode="python", exclude_none=False)
    wrong_media_type["media_type"] = ROLE_CONTENT_MEDIA_TYPES[PtmLocalizationRawInputRole.GENOME]
    with pytest.raises(ValidationError):
        ApprovedPtmLocalizationRawParser.model_validate(wrong_media_type, strict=True)

    duplicate_parsers = request.policy.model_dump(mode="python", exclude_none=False)
    approved_parsers = list(
        cast("tuple[dict[str, object], ...]", duplicate_parsers["approved_parsers"])
    )
    approved_parsers[-1] = approved_parsers[0]
    duplicate_parsers["approved_parsers"] = tuple(approved_parsers)
    with pytest.raises(ValidationError):
        PtmLocalizationRawInputPolicy.model_validate(duplicate_parsers, strict=True)

    total_below_document = request.policy.model_dump(mode="python", exclude_none=False)
    total_below_document["max_total_bytes"] = M0503_ROLE_COUNT
    with pytest.raises(ValidationError):
        PtmLocalizationRawInputPolicy.model_validate(total_below_document, strict=True)

    parser_above_policy = request.policy.model_dump(mode="python", exclude_none=False)
    parser_above_policy["max_document_bytes"] = M0503_MAX_DOCUMENT_BYTES - 1
    with pytest.raises(ValidationError):
        PtmLocalizationRawInputPolicy.model_validate(parser_above_policy, strict=True)

    artifact = request.artifacts[0]
    wrong_manifest_type = artifact.model_dump(mode="python", exclude_none=False)
    manifest_reference = cast("dict[str, object]", wrong_manifest_type["manifest_reference"])
    manifest_reference["media_type"] = "application/json"
    with pytest.raises(ValidationError):
        PtmLocalizationRawInputArtifact.model_validate(wrong_manifest_type, strict=True)

    wrong_artifact_format = artifact.model_dump(mode="python", exclude_none=False)
    wrong_artifact_format["format"] = next(
        value for value in PtmLocalizationRawDocumentFormat if value is not artifact.format
    )
    with pytest.raises(ValidationError):
        PtmLocalizationRawInputArtifact.model_validate(wrong_artifact_format, strict=True)


@pytest.mark.contract
def test_canonical_firewall_rejects_nonsemantic_storage_and_collections() -> None:
    class CanonicalProbe(BaseModel):
        value: int

    probe = CanonicalProbe(value=1)
    storage = object.__getattribute__(probe, "__dict__")
    storage[1] = "non-string-storage-key"
    with pytest.raises(TypeError, match="model storage"):
        m0503_canonical._python(probe)

    with pytest.raises(TypeError, match="exact string keys"):
        m0503_canonical._python({1: "non-string-object-key"})
    with pytest.raises(TypeError, match="unsupported"):
        m0503_canonical._python(object())
    with pytest.raises(TypeError, match="must be an object"):
        m0503_canonical._dump(cast("Any", []))
    assert m0503_canonical._sequence(["a", "b"]) == ("a", "b")
    with pytest.raises(TypeError, match="exact lists or tuples"):
        m0503_canonical._sequence(cast("Any", {"not", "a", "sequence"}))


@pytest.mark.contract
def test_owned_identifiers_evidence_and_role_collections_reject_independently() -> None:
    request = _genuine_request()
    with pytest.raises(ValueError, match="opaque local namespace"):
        m05_03.opaque_ptm_localization_raw_input_identifier(
            "policy",
            _opaque("actor", "wrong-owned-namespace"),
        )

    parser_payload = request.policy.approved_parsers[0].model_dump(
        mode="python", exclude_none=False
    )
    parser_evidence = cast("dict[str, object]", parser_payload["evidence"])
    parser_evidence["media_type"] = "application/json"
    with pytest.raises(ValidationError, match="artifact media type"):
        ApprovedPtmLocalizationRawParser.model_validate(parser_payload, strict=True)

    missing_role = request.policy.model_dump(mode="python", exclude_none=False)
    parsers = list(cast("tuple[dict[str, object], ...]", missing_role["approved_parsers"]))
    replacement = deepcopy(parsers[-1])
    replacement.update(
        role=PtmLocalizationRawInputRole.GENOME,
        format=PtmLocalizationRawDocumentFormat.GENOME_MANIFEST_JSON,
        format_version="9.9.8",
        parser_version="9.9.8",
        media_type=ROLE_CONTENT_MEDIA_TYPES[PtmLocalizationRawInputRole.GENOME],
    )
    parsers[-1] = replacement
    missing_role["approved_parsers"] = tuple(parsers)
    with pytest.raises(ValidationError, match="cover all four"):
        PtmLocalizationRawInputPolicy.model_validate(missing_role, strict=True)

    duplicate_evidence = request.policy.model_dump(mode="python", exclude_none=False)
    parsers = list(cast("tuple[dict[str, object], ...]", duplicate_evidence["approved_parsers"]))
    parsers[-1] = deepcopy(parsers[-1])
    parsers[-1]["evidence"] = deepcopy(parsers[0]["evidence"])
    duplicate_evidence["approved_parsers"] = tuple(parsers)
    with pytest.raises(ValidationError, match="evidence identities and digests"):
        PtmLocalizationRawInputPolicy.model_validate(duplicate_evidence, strict=True)


@pytest.mark.contract
def test_document_local_media_and_bound_collection_validators_reject() -> None:
    request = _genuine_request()
    artifact_payload = request.artifacts[0].model_dump(mode="python", exclude_none=False)
    artifact_content = cast("dict[str, object]", artifact_payload["content_reference"])
    artifact_content["media_type"] = "Application/JSON"
    with pytest.raises(ValidationError, match="lowercase"):
        PtmLocalizationRawInputArtifact.model_validate(artifact_payload, strict=True)

    documents = _documents(request)
    proteome_payload = documents[0].model_dump(mode="python", exclude_none=False)
    document_content = cast("dict[str, object]", proteome_payload["content_reference"])
    document_content["media_type"] = "Application/JSON"
    with pytest.raises(ValidationError, match="lowercase"):
        MassSpectrometryProteomeInputDocument.model_validate(proteome_payload, strict=True)

    proteome_payload = documents[0].model_dump(mode="python", exclude_none=False)
    unit = cast("tuple[object, ...]", proteome_payload["declared_units"])[0]
    proteome_payload["declared_units"] = (unit, unit)
    with pytest.raises(ValidationError, match="unit declarations must be unique"):
        MassSpectrometryProteomeInputDocument.model_validate(proteome_payload, strict=True)

    ptm_payload = documents[-1].model_dump(mode="python", exclude_none=False)
    vocabulary = cast("tuple[object, ...]", ptm_payload["vocabularies"])[0]
    ptm_payload["vocabularies"] = (vocabulary, vocabulary)
    with pytest.raises(ValidationError, match="vocabulary identifiers must be unique"):
        PtmAnnotationInputDocument.model_validate(ptm_payload, strict=True)

    direct_identifier_canary = "Patient.SSN.123-45-6789"
    for document_type, field_name in (
        (GenomeInputDocument, "reference_build"),
        (TranscriptomeInputDocument, "annotation_build"),
    ):
        build_payload = next(
            item for item in documents if isinstance(item, document_type)
        ).model_dump(mode="python", exclude_none=False)
        build_payload[field_name] = direct_identifier_canary
        with pytest.raises(ValidationError, match="bundle"):
            document_type.model_validate(build_payload, strict=True)


@pytest.mark.contract
def test_request_chronology_identity_and_safe_shape_reject_independently() -> None:
    request = _genuine_request()

    mismatched_id = request.model_dump(mode="python", exclude_none=False)
    context = cast("dict[str, object]", mismatched_id["context"])
    context["request_id"] = _opaque("request", "mismatched-context-request")
    with pytest.raises(ValidationError, match="identifier must equal"):
        IngestPtmLocalizationRawInputsRequest.model_validate(mismatched_id, strict=True)

    future_policy = request.model_dump(mode="python", exclude_none=False)
    policy = cast("dict[str, object]", future_policy["policy"])
    policy["reviewed_at"] = request.context.occurred_at + timedelta(microseconds=1)
    with pytest.raises(ValidationError, match="policy cannot postdate"):
        IngestPtmLocalizationRawInputsRequest.model_validate(future_policy, strict=True)

    stale_context = request.model_dump(mode="python", exclude_none=False)
    context = cast("dict[str, object]", stale_context["context"])
    occurred_at = request.lineage_result.completed_at - timedelta(microseconds=1)
    context["occurred_at"] = occurred_at
    policy = cast("dict[str, object]", stale_context["policy"])
    policy["reviewed_at"] = occurred_at - timedelta(microseconds=1)
    with pytest.raises(ValidationError, match="result cannot postdate"):
        IngestPtmLocalizationRawInputsRequest.model_validate(stale_context, strict=True)

    safe_request = _genuine_request(_genuine_lineage("upstream_protocol_quarantined"))
    safe_payload = safe_request.model_dump(mode="python", exclude_none=False)
    safe_payload["artifacts"] = request.artifacts
    with pytest.raises(ValidationError, match="cannot submit raw-input artifacts"):
        IngestPtmLocalizationRawInputsRequest.model_validate(safe_payload, strict=True)


@pytest.mark.contract
def test_duplicate_derived_codes_and_resigned_digest_reject_independently() -> None:
    result = _result(_genuine_request())
    code = PtmLocalizationRawDiagnosticCode.DUPLICATE_CONTENT_RETAINED

    validated_payload = result.validated_inputs[0].model_dump(mode="python", exclude_none=False)
    validated_payload["diagnostic_codes"] = (code, code)
    with pytest.raises(ValidationError, match="diagnostic codes must be unique"):
        ValidatedPtmLocalizationRawInput.model_validate(validated_payload, strict=True)

    receipt_payload = result.receipt.model_dump(mode="python", exclude_none=False)
    receipt_payload["diagnostic_codes"] = (code, code)
    with pytest.raises(ValidationError, match="diagnostic codes must be unique"):
        PtmLocalizationRawInputReceipt.model_validate(receipt_payload, strict=True)

    with pytest.raises(ValueError, match="disposition contradicts"):
        expected_receipt(
            result.request,
            result.validated_inputs,
            result.diagnostics,
            PtmLocalizationRawInputDisposition.QUARANTINED,
        )

    forged = result.model_dump(mode="python", exclude_none=False)
    forged["result_digest"] = _digest("resigned-result-digest")
    with pytest.raises(ValidationError, match="result digest"):
        PtmLocalizationRawInputValidationResult.model_validate(forged, strict=True)
