"""Replay the locked M05-03 synthetic raw-manifest corpus."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections.abc import Callable, Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, Final, NoReturn, cast
from unittest.mock import patch

from pydantic import BaseModel, TypeAdapter, ValidationError
from typer.testing import CliRunner

from evals.m05_02.run import build_scenario_request as build_m0502_request
from glio_proteogen.adapters import cli as cli_adapter
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m05_01 import (
    PtmLocalizationInputRole,
    PtmLocalizationProtocolConformanceResult,
)
from glio_proteogen.contracts.m05_02 import (
    PtmLocalizationIdentityLineageResolution,
    PtmLocalizationLineageArtifactClaim,
    PtmLocalizationLineageArtifactRole,
    ReconcilePtmLocalizationIdentityLineageRequest,
)
from glio_proteogen.contracts.m05_02 import (
    result_payload_digest as m0502_result_payload_digest,
)
from glio_proteogen.contracts.m05_03 import (
    M0503_DIAGNOSTIC_CODE_COUNT,
    M0503_LIMITATION_COUNT,
    M0503_MAX_APPROVED_PARSERS,
    M0503_MAX_CANONICAL_REQUEST_BYTES,
    M0503_MAX_DECLARED_RECORD_COUNT,
    M0503_MAX_DIAGNOSTICS,
    M0503_MAX_DOCUMENT_BYTES,
    M0503_MAX_EVIDENCE,
    M0503_MIN_EVIDENCE,
    M0503_MIN_RECONCILED_EVIDENCE,
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
    PtmLocalizationRawInputRole,
    PtmLocalizationRawInputValidationResult,
    PtmLocalizationRawParentQualityState,
    PtmLocalizationRawParseDiagnostic,
    PtmLocalizationRawReferenceRole,
    PtmLocalizationRawVocabularyBinding,
    TranscriptomeInputDocument,
    configuration_digest,
    expected_receipt,
    normalized_document,
    opaque_ptm_localization_raw_input_identifier,
    receipt_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, EstimateState, ExecutionContext
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c05_ptm_localization.m05_02_identity_lineage import (
    reconcile_ptm_localization_identity_lineage,
)
from glio_proteogen.modules.c05_ptm_localization.m05_03_raw_ingestion import (
    M0503Plugin,
    M0503Service,
    M0503Submission,
    PtmLocalizationRawInputAuthorizationError,
    PtmLocalizationRawInputError,
    PtmLocalizationRawInputErrorCode,
    ingest_ptm_localization_raw_inputs,
    preflight_ptm_localization_raw_input_authorization,
)
from glio_proteogen.modules.c05_ptm_localization.m05_03_raw_ingestion import (
    engine as m0503_engine,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m05_03.v1 import PtmLocalizationRawInputDocument

MODULE_ID: Final = "GLIO-PROTEOGEN-M05-03"
SCENARIO_PATH: Final = Path("tests/fixtures/m05_03/scenarios.json")
EXPECTED_CASE_COUNT: Final = 72
EXPECTED_ALLOCATION: Final = (7, 9, 8, 8, 8, 7, 7, 18)
EXPECTED_GROUP_COUNT: Final = len(EXPECTED_ALLOCATION)
EXPECTED_UNCERTAINTY_DIMENSIONS: Final = 7
EXPECTED_CLI_REFUSALS: Final = 5
CHECK_PASSED: Final = True
CHECK_FAILED: Final = False
FIXED_TIME: Final = datetime(2026, 8, 13, 15, tzinfo=UTC)
CONTROL_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.control+json"
POLICY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-03.policy+json"
PARSER_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-03.parser+json"
ROLE_CONTENT_MEDIA_TYPES: Final = {
    PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
        "application/vnd.glio-proteogen.m05-03.proteome-input+json"
    ),
    PtmLocalizationRawInputRole.GENOME: "application/vnd.glio-proteogen.m05-03.genome-input+json",
    PtmLocalizationRawInputRole.TRANSCRIPTOME: (
        "application/vnd.glio-proteogen.m05-03.transcriptome-input+json"
    ),
    PtmLocalizationRawInputRole.PTM_ANNOTATIONS: (
        "application/vnd.glio-proteogen.m05-03.ptm-annotation-input+json"
    ),
}
ROLE_FORMATS: Final = {
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
ROLE_PROJECTION: Final = {
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


@dataclass(frozen=True, slots=True)
class Scenario:
    """One strict request and its separately supplied immutable manifest bytes."""

    request: IngestPtmLocalizationRawInputsRequest
    artifacts_by_role: dict[PtmLocalizationRawInputRole, bytes]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    """One named executable assertion in the locked corpus."""

    name: str
    passed: bool
    detail: str


class _UnsupportedScenarioError(ValueError):
    pass


def _oid(namespace: str, label: object) -> str:
    value = f"{namespace}.{sha256_digest({'m0503': label}).removeprefix('sha256:')}"
    return opaque_ptm_localization_raw_input_identifier(cast("Any", namespace), value)


def _reference(label: str, *, media_type: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_oid("input", label),
        version="1.0.0",
        digest=sha256_digest({"m0503_content": label}),
        media_type=media_type,
    )


def _parser_evidence(role: PtmLocalizationRawInputRole) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_oid("evidence", f"parser-{role.value}"),
        version="1.0.0",
        digest=sha256_digest({"m0503_parser": role}),
        media_type=PARSER_MEDIA_TYPE,
    )


def _policy() -> PtmLocalizationRawInputPolicy:
    parsers = tuple(
        ApprovedPtmLocalizationRawParser(
            role=role,
            format=ROLE_FORMATS[role],
            format_version="1.0.0",
            parser_version="1.0.0",
            media_type=ROLE_CONTENT_MEDIA_TYPES[role],
            max_document_bytes=8 * 1024 * 1024,
            evidence=_parser_evidence(role),
        )
        for role in PtmLocalizationRawInputRole
    )
    return PtmLocalizationRawInputPolicy(
        policy_id=_oid("policy", "canonical"),
        version="1.0.0",
        approved_parsers=parsers,
        evidence=ArtifactReference(
            artifact_id=_oid("evidence", "policy"),
            version="1.0.0",
            digest=sha256_digest({"m0503_policy": "canonical"}),
            media_type=POLICY_MEDIA_TYPE,
        ),
        reviewed_by=_oid("reviewer", "synthetic"),
        reviewed_at=FIXED_TIME,
    )


def _documents(
    claims_by_role: dict[PtmLocalizationRawInputRole, PtmLocalizationLineageArtifactClaim],
    protocol: PtmLocalizationProtocolConformanceResult,
) -> dict[PtmLocalizationRawInputRole, PtmLocalizationRawInputDocument]:
    schema = protocol.request.protocol_schema
    assay_policy = schema.assay_specimen_policy
    references = {item.role: item.reference.digest for item in schema.reference_bundle.references}
    common: dict[PtmLocalizationRawInputRole, dict[str, object]] = {}
    for role in PtmLocalizationRawInputRole:
        content = _reference(role.value, media_type=ROLE_CONTENT_MEDIA_TYPES[role])
        common[role] = {
            "input_id": content.artifact_id,
            "lineage_claim_id": claims_by_role[role].claim_id,
            "identity_resolution_digest": protocol.receipt.identity_subject_digest,
            "protocol_result_digest": protocol.result_digest,
            "reference_bundle_digest": protocol.receipt.reference_bundle_digest,
            "assay_specimen_policy_digest": protocol.receipt.assay_specimen_policy_digest,
            "intended_use_evidence_digest": protocol.receipt.intended_use_evidence_digest,
            "assay_protocol_version": assay_policy.assay_protocol_version,
            "specimen_processing_version": assay_policy.specimen_processing_version,
            "unit_system_version": schema.unit_system_version,
            "reference_bundle_version": schema.reference_bundle.version,
            "content_reference": content,
            "declared_record_count": 1,
            "evidence_state": PtmLocalizationRawEvidenceState.AVAILABLE,
            "completeness_state": PtmLocalizationRawCompletenessState.COMPLETE,
            "assay_support_state": PtmLocalizationRawAssaySupportState.SUPPORTED,
            "parent_quality_state": PtmLocalizationRawParentQualityState.ACCEPTED,
        }
    return {
        PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
            MassSpectrometryProteomeInputDocument.model_validate(
                {
                    **common[PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME],
                    "reference_role": (PtmLocalizationRawReferenceRole.MASS_SPECTROMETRY_PROTEOME),
                    "reference_digest": references[
                        PtmLocalizationInputRole.MASS_SPECTROMETRY_PROTEOME
                    ],
                    "assay_kind": assay_policy.assay_kind,
                    "support_domain": assay_policy.support_domain,
                    "declared_units": tuple(item.unit for item in schema.unit_policies),
                },
                strict=True,
            )
        ),
        PtmLocalizationRawInputRole.GENOME: GenomeInputDocument.model_validate(
            {
                **common[PtmLocalizationRawInputRole.GENOME],
                "reference_role": PtmLocalizationRawReferenceRole.GENOME_TRANSCRIPTOME,
                "reference_digest": references[PtmLocalizationInputRole.GENOME_TRANSCRIPTOME],
                "reference_build": schema.reference_bundle.bundle_id,
            },
            strict=True,
        ),
        PtmLocalizationRawInputRole.TRANSCRIPTOME: TranscriptomeInputDocument.model_validate(
            {
                **common[PtmLocalizationRawInputRole.TRANSCRIPTOME],
                "reference_role": PtmLocalizationRawReferenceRole.GENOME_TRANSCRIPTOME,
                "reference_digest": references[PtmLocalizationInputRole.GENOME_TRANSCRIPTOME],
                "annotation_build": schema.reference_bundle.bundle_id,
            },
            strict=True,
        ),
        PtmLocalizationRawInputRole.PTM_ANNOTATIONS: PtmAnnotationInputDocument.model_validate(
            {
                **common[PtmLocalizationRawInputRole.PTM_ANNOTATIONS],
                "reference_role": PtmLocalizationRawReferenceRole.PTM_ANNOTATIONS,
                "reference_digest": references[PtmLocalizationInputRole.PTM_ANNOTATIONS],
                "vocabularies": tuple(
                    PtmLocalizationRawVocabularyBinding(
                        vocabulary_id=item.vocabulary_id,
                        version=item.version,
                    )
                    for item in schema.controlled_vocabularies
                ),
                "vocabularies_digest": sha256_digest(tuple(schema.controlled_vocabularies)),
            },
            strict=True,
        ),
    }


def _genuine_scenario(upstream_case_id: str = "canonical_reconciled") -> Scenario:
    """Build documents first and seal them through all three genuine upstream operations."""

    lineage_request = build_m0502_request(upstream_case_id)
    protocol = lineage_request.protocol_result
    claims = lineage_request.artifact_claims
    if not claims:
        lineage_result = reconcile_ptm_localization_identity_lineage(lineage_request)
        policy = _policy()
        context = _context(lineage_result, policy)
        request = IngestPtmLocalizationRawInputsRequest(
            request_id=context.request_id,
            context=context,
            lineage_result=lineage_result,
            policy=policy,
            artifacts=(),
            supersedes_result_digest=None,
        )
        return Scenario(request=request, artifacts_by_role={})
    source_claims = {
        role: next(item for item in claims if item.role is upstream_role)
        for role, upstream_role in ROLE_PROJECTION.items()
    }
    documents = _documents(source_claims, protocol)
    document_bytes = {
        role: canonical_json_bytes(normalized_document(document))
        for role, document in documents.items()
    }
    updated_claims = tuple(
        claim.model_copy(
            update={
                "artifact": claim.artifact.model_copy(
                    update={"digest": f"sha256:{hashlib.sha256(document_bytes[role]).hexdigest()}"}
                )
            }
        )
        if (role := next((key for key, value in source_claims.items() if value is claim), None))
        is not None
        else claim
        for claim in claims
    )
    lineage_payload = lineage_request.model_dump(mode="python", exclude_none=False)
    lineage_payload["artifact_claims"] = updated_claims
    lineage_request = ReconcilePtmLocalizationIdentityLineageRequest.model_validate(
        lineage_payload, strict=True
    )
    lineage_result = reconcile_ptm_localization_identity_lineage(lineage_request)
    policy = _policy()
    artifacts = tuple(
        PtmLocalizationRawInputArtifact(
            role=role,
            lineage_claim_id=claim.claim_id,
            manifest_reference=claim.artifact,
            content_reference=documents[role].content_reference,
            declared_size_bytes=len(document_bytes[role]),
            format=ROLE_FORMATS[role],
            format_version="1.0.0",
            parser_version="1.0.0",
        )
        for role, claim in source_claims.items()
    )
    artifacts = tuple(
        item.model_copy(
            update={
                "manifest_reference": next(
                    claim.artifact
                    for claim in lineage_result.request.artifact_claims
                    if claim.claim_id == item.lineage_claim_id
                )
            }
        )
        for item in artifacts
    )
    context = _context(lineage_result, policy)
    request = IngestPtmLocalizationRawInputsRequest(
        request_id=context.request_id,
        context=context,
        lineage_result=lineage_result,
        policy=policy,
        artifacts=artifacts,
        supersedes_result_digest=None,
    )
    return Scenario(request=request, artifacts_by_role=document_bytes)


def build_scenario(case_id: str = "canonical_four_role_documents_validated") -> Scenario:
    """Build canonical documents, execute genuine upstream operations, then construct M05-03."""

    if case_id != "canonical_four_role_documents_validated":
        raise _UnsupportedScenarioError(case_id)
    return _genuine_scenario()


def _context(
    lineage: PtmLocalizationIdentityLineageResolution,
    policy: PtmLocalizationRawInputPolicy,
) -> ExecutionContext:
    base = lineage.request.context
    refs = base.references.model_copy(
        update={
            "approved_configuration": base.references.approved_configuration.model_copy(
                update={
                    "evidence": base.references.approved_configuration.evidence.model_copy(
                        update={"digest": configuration_digest(policy)}
                    )
                }
            ),
            "identity_lineage": base.references.identity_lineage.model_copy(
                update={"binding_digest": lineage.identity_resolution_digest}
            ),
            "quality": base.references.quality.model_copy(
                update={
                    "evidence": base.references.quality.evidence.model_copy(
                        update={"digest": lineage.result_digest}
                    )
                }
            ),
            "support": base.references.support.model_copy(
                update={
                    "evidence": base.references.support.evidence.model_copy(
                        update={"digest": lineage.receipt.receipt_digest}
                    )
                }
            ),
            "intended_use": base.references.intended_use.model_copy(
                update={
                    "evidence": base.references.intended_use.evidence.model_copy(
                        update={"digest": lineage.receipt.intended_use_evidence_digest}
                    )
                }
            ),
        }
    )
    return base.model_copy(update={"occurred_at": FIXED_TIME, "references": refs})


def build_scenario_request(
    case_id: str = "canonical_four_role_documents_validated",
) -> IngestPtmLocalizationRawInputsRequest:
    """Return the strict request component of one synthetic scenario."""

    return build_scenario(case_id).request


def canonical_smoke() -> PtmLocalizationRawInputValidationResult:
    scenario = build_scenario()
    return ingest_ptm_localization_raw_inputs(scenario.request, scenario.artifacts_by_role)


_DOCUMENT_MODELS: Final[dict[PtmLocalizationRawInputRole, type[BaseModel]]] = {
    PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: (MassSpectrometryProteomeInputDocument),
    PtmLocalizationRawInputRole.GENOME: GenomeInputDocument,
    PtmLocalizationRawInputRole.TRANSCRIPTOME: TranscriptomeInputDocument,
    PtmLocalizationRawInputRole.PTM_ANNOTATIONS: PtmAnnotationInputDocument,
}
_REQUEST_ADAPTER: Final = TypeAdapter(IngestPtmLocalizationRawInputsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(PtmLocalizationRawInputValidationResult)


def _typed_documents(scenario: Scenario) -> dict[PtmLocalizationRawInputRole, BaseModel]:
    return {
        role: TypeAdapter(_DOCUMENT_MODELS[role]).validate_json(payload, strict=True)
        for role, payload in scenario.artifacts_by_role.items()
    }


def _artifact_with(
    artifact: PtmLocalizationRawInputArtifact,
    **updates: object,
) -> PtmLocalizationRawInputArtifact:
    payload = artifact.model_dump(mode="python", exclude_none=False)
    payload.update(updates)
    return PtmLocalizationRawInputArtifact.model_validate(payload, strict=True)


def _rebind_payloads(
    base: Scenario,
    payloads: dict[PtmLocalizationRawInputRole, bytes],
    *,
    artifact_updates: dict[PtmLocalizationRawInputRole, dict[str, object]] | None = None,
    policy: PtmLocalizationRawInputPolicy | None = None,
) -> Scenario:
    """Re-execute public M05-02 after sealing replacement canonical manifest bytes."""

    lineage_request = base.request.lineage_result.request
    role_by_upstream = {upstream: role for role, upstream in ROLE_PROJECTION.items()}
    claims = tuple(
        claim.model_copy(
            update={
                "artifact": claim.artifact.model_copy(
                    update={
                        "digest": f"sha256:{hashlib.sha256(payloads[role]).hexdigest()}",
                    }
                )
            }
        )
        if (role := role_by_upstream.get(claim.role)) is not None
        else claim
        for claim in lineage_request.artifact_claims
    )
    rebound_lineage_request = ReconcilePtmLocalizationIdentityLineageRequest(
        request_id=lineage_request.request_id,
        context=lineage_request.context,
        identity_resolution=lineage_request.identity_resolution,
        protocol_result=lineage_request.protocol_result,
        policy=lineage_request.policy,
        artifact_claims=claims,
        derivations=lineage_request.derivations,
        supersedes_result_digest=lineage_request.supersedes_result_digest,
    )
    lineage_result = reconcile_ptm_localization_identity_lineage(rebound_lineage_request)
    active_policy = policy or base.request.policy
    updates = artifact_updates or {}
    rebound_artifacts: list[PtmLocalizationRawInputArtifact] = []
    for artifact in base.request.artifacts:
        upstream_claim = next(
            claim for claim in claims if claim.claim_id == artifact.lineage_claim_id
        )
        item_updates: dict[str, object] = {
            "manifest_reference": upstream_claim.artifact,
            "declared_size_bytes": len(payloads[artifact.role]),
        }
        item_updates.update(updates.get(artifact.role, {}))
        rebound_artifacts.append(_artifact_with(artifact, **item_updates))
    context = _context(lineage_result, active_policy)
    request = IngestPtmLocalizationRawInputsRequest(
        request_id=context.request_id,
        context=context,
        lineage_result=lineage_result,
        policy=active_policy,
        artifacts=tuple(rebound_artifacts),
        supersedes_result_digest=base.request.supersedes_result_digest,
    )
    return Scenario(request=request, artifacts_by_role=dict(payloads))


def _with_document_updates(
    base: Scenario,
    updates: dict[PtmLocalizationRawInputRole, dict[str, object]],
    *,
    artifact_updates: dict[PtmLocalizationRawInputRole, dict[str, object]] | None = None,
    policy: PtmLocalizationRawInputPolicy | None = None,
) -> Scenario:
    documents = _typed_documents(base)
    for role, role_updates in updates.items():
        payload = documents[role].model_dump(mode="python", exclude_none=False)
        payload.update(role_updates)
        documents[role] = TypeAdapter(_DOCUMENT_MODELS[role]).validate_python(
            payload,
            strict=True,
        )
    serialized = {
        role: canonical_json_bytes(normalized_document(document))
        for role, document in documents.items()
    }
    return _rebind_payloads(
        base,
        serialized,
        artifact_updates=artifact_updates,
        policy=policy,
    )


def _with_artifact_updates(
    base: Scenario,
    updates: dict[PtmLocalizationRawInputRole, dict[str, object]],
    *,
    policy: PtmLocalizationRawInputPolicy | None = None,
) -> Scenario:
    active_policy = policy or base.request.policy
    artifacts = tuple(
        _artifact_with(item, **updates.get(item.role, {})) for item in base.request.artifacts
    )
    context = _context(base.request.lineage_result, active_policy)
    request = IngestPtmLocalizationRawInputsRequest(
        request_id=context.request_id,
        context=context,
        lineage_result=base.request.lineage_result,
        policy=active_policy,
        artifacts=artifacts,
        supersedes_result_digest=base.request.supersedes_result_digest,
    )
    return Scenario(request=request, artifacts_by_role=dict(base.artifacts_by_role))


def _check(case_id: str, passed: bool, detail: str) -> EvalCheck:  # noqa: FBT001
    return EvalCheck(name=f"scenario.{case_id}", passed=passed, detail=detail)


def _codes(
    result: PtmLocalizationRawInputValidationResult,
) -> set[PtmLocalizationRawDiagnosticCode]:
    codes = {item.code for item in result.diagnostics}
    receipt_codes = set(result.receipt.diagnostic_codes)
    return codes if codes == receipt_codes else set()


def _strict_request(payload: dict[str, Any]) -> IngestPtmLocalizationRawInputsRequest:
    return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(payload), strict=True)


def _validation_rejection(
    case_id: str,
    mutate: Callable[[dict[str, Any]], None],
    *,
    base: Scenario | None = None,
) -> EvalCheck:
    scenario = base or build_scenario()
    payload = scenario.request.model_dump(mode="json", exclude_none=False)
    mutate(payload)
    try:
        request = _strict_request(payload)
        ingest_ptm_localization_raw_inputs(request, scenario.artifacts_by_role)
    except (ValidationError, ValueError) as error:
        return _check(case_id, CHECK_PASSED, f"validation_rejected:{type(error).__name__}")
    return _check(case_id, CHECK_FAILED, "request unexpectedly accepted")


def _canonical_checks() -> list[EvalCheck]:
    scenario = build_scenario()
    result = ingest_ptm_localization_raw_inputs(scenario.request, scenario.artifacts_by_role)
    protocol = scenario.request.lineage_result.request.protocol_result
    exact_bindings = all(
        item.document.protocol_result_digest == protocol.result_digest
        and item.document.reference_bundle_digest == protocol.receipt.reference_bundle_digest
        and item.document.assay_specimen_policy_digest
        == protocol.receipt.assay_specimen_policy_digest
        for item in result.validated_inputs
    )
    exact_role_projection = all(
        item.manifest_reference
        == next(
            claim.artifact
            for claim in scenario.request.lineage_result.request.artifact_claims
            if claim.claim_id == item.lineage_claim_id
        )
        for item in result.validated_inputs
    )
    exact_bytes = all(
        scenario.artifacts_by_role[item.role]
        == canonical_json_bytes(normalized_document(item.document))
        for item in result.validated_inputs
    )
    repeated = ingest_ptm_localization_raw_inputs(scenario.request, scenario.artifacts_by_role)
    canonical = (
        result.disposition is PtmLocalizationRawInputDisposition.VALIDATED
        and len(result.validated_inputs) == M0503_ROLE_COUNT
        and not result.diagnostics
    )
    protocol_bound_count = sum(
        item.document.protocol_result_digest == protocol.result_digest
        for item in result.validated_inputs
    )
    return [
        _check(
            "canonical_four_role_documents_validated",
            canonical,
            f"disposition={result.disposition.value};inputs={len(result.validated_inputs)}",
        ),
        _check(
            "exact_m0502_full_result_replay",
            canonical
            and result.lineage_result_digest == scenario.request.lineage_result.result_digest
            and result.receipt.lineage_receipt_digest
            == scenario.request.lineage_result.receipt.receipt_digest,
            "full embedded M05-02 result and receipt replayed",
        ),
        _check(
            "exact_m0501_transitive_protocol_bindings",
            exact_bindings,
            (f"bound_inputs={protocol_bound_count}/{M0503_ROLE_COUNT}"),
        ),
        _check(
            "exact_role_claim_manifest_bindings",
            exact_role_projection,
            "all four roles retain exact upstream claim artifacts",
        ),
        _check(
            "canonical_document_byte_projection",
            exact_bytes,
            "all supplied bytes equal embedded canonical document bytes",
        ),
        _check(
            "deterministic_full_result_equality",
            result == repeated,
            f"result_digest={result.result_digest}",
        ),
        _check(
            "parent_context_preserved_without_emission",
            result.parent_target == "variant_peptide"
            and result.receipt.parent_target == "variant_peptide"
            and not result.emits_variant_peptide
            and not result.receipt.emits_variant_peptide,
            "parent context retained; emission flags false",
        ),
    ]


class _BytesSubclass(bytes):
    pass


def _input_error_check(
    case_id: str,
    scenario: Scenario,
    supplied: object,
    expected: PtmLocalizationRawInputErrorCode,
) -> EvalCheck:
    try:
        ingest_ptm_localization_raw_inputs(scenario.request, supplied)
    except PtmLocalizationRawInputError as error:
        return _check(
            case_id,
            error.code is expected,
            f"ingress_rejected:{error.code.value}",
        )
    return _check(case_id, CHECK_FAILED, "input unexpectedly accepted")


def _mapping_cap_checks() -> list[EvalCheck]:
    base = build_scenario()
    role = PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME
    missing = dict(base.artifacts_by_role)
    missing.pop(role)
    extra = cast("dict[object, object]", dict(base.artifacts_by_role))
    extra["extra"] = b"{}"
    bytearray_mapping = cast("dict[object, object]", dict(base.artifacts_by_role))
    bytearray_mapping[role] = bytearray(base.artifacts_by_role[role])
    subclass_mapping = cast("dict[object, object]", dict(base.artifacts_by_role))
    subclass_mapping[role] = _BytesSubclass(base.artifacts_by_role[role])
    declared = next(item for item in base.request.artifacts if item.role is role)
    declared_scenario = _with_artifact_updates(
        base,
        {role: {"declared_size_bytes": declared.declared_size_bytes + 1}},
    )
    corrupt = dict(base.artifacts_by_role)
    corrupt[role] = corrupt[role][:-1] + bytes([corrupt[role][-1] ^ 1])
    largest = _with_document_updates(
        base,
        {role: {"declared_record_count": M0503_MAX_DECLARED_RECORD_COUNT}},
    )
    largest_result = ingest_ptm_localization_raw_inputs(
        largest.request,
        largest.artifacts_by_role,
    )
    max_declared = _with_artifact_updates(
        base,
        {
            item.role: {"declared_size_bytes": M0503_MAX_DOCUMENT_BYTES}
            for item in base.request.artifacts
        },
    )
    per_excess = dict(max_declared.artifacts_by_role)
    per_excess[role] = b" " * (M0503_MAX_DOCUMENT_BYTES + 1)
    aggregate_excess = {
        item.role: b" " * M0503_MAX_DOCUMENT_BYTES for item in base.request.artifacts
    }
    aggregate_excess[role] += b" "
    return [
        _input_error_check(
            "missing_role_mapping_rejected",
            base,
            missing,
            PtmLocalizationRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH,
        ),
        _input_error_check(
            "extra_role_mapping_rejected",
            base,
            extra,
            PtmLocalizationRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH,
        ),
        _input_error_check(
            "bytearray_rejected",
            base,
            bytearray_mapping,
            PtmLocalizationRawInputErrorCode.ARTIFACT_TYPE_INVALID,
        ),
        _input_error_check(
            "bytes_subclass_rejected",
            base,
            subclass_mapping,
            PtmLocalizationRawInputErrorCode.ARTIFACT_TYPE_INVALID,
        ),
        _input_error_check(
            "declared_size_mismatch_rejected",
            declared_scenario,
            declared_scenario.artifacts_by_role,
            PtmLocalizationRawInputErrorCode.ARTIFACT_SIZE_MISMATCH,
        ),
        _input_error_check(
            "manifest_digest_mismatch_rejected",
            base,
            corrupt,
            PtmLocalizationRawInputErrorCode.ARTIFACT_DIGEST_MISMATCH,
        ),
        _check(
            "largest_constructible_document_accepted",
            largest_result.disposition is PtmLocalizationRawInputDisposition.VALIDATED
            and next(
                item.document.declared_record_count
                for item in largest_result.validated_inputs
                if item.role is role
            )
            == M0503_MAX_DECLARED_RECORD_COUNT,
            f"declared_record_count={M0503_MAX_DECLARED_RECORD_COUNT}",
        ),
        _input_error_check(
            "per_document_8mib_plus_one_rejected",
            max_declared,
            per_excess,
            PtmLocalizationRawInputErrorCode.ARTIFACT_SIZE_MISMATCH,
        ),
        _input_error_check(
            "aggregate_32mib_plus_one_rejected",
            max_declared,
            aggregate_excess,
            PtmLocalizationRawInputErrorCode.ARTIFACT_SIZE_MISMATCH,
        ),
    ]


def _semantic_result(
    updates: dict[PtmLocalizationRawInputRole, dict[str, object]],
    *,
    artifact_updates: dict[PtmLocalizationRawInputRole, dict[str, object]] | None = None,
) -> PtmLocalizationRawInputValidationResult:
    scenario = _with_document_updates(
        build_scenario(),
        updates,
        artifact_updates=artifact_updates,
    )
    return ingest_ptm_localization_raw_inputs(scenario.request, scenario.artifacts_by_role)


def _code_check(
    case_id: str,
    result: PtmLocalizationRawInputValidationResult,
    code: PtmLocalizationRawDiagnosticCode,
    disposition: PtmLocalizationRawInputDisposition,
) -> EvalCheck:
    codes = _codes(result)
    return _check(
        case_id,
        result.disposition is disposition and code in codes,
        (
            f"disposition={result.disposition.value};"
            f"codes={','.join(item.value for item in sorted(codes))}"
        ),
    )


def _version_reference_checks() -> list[EvalCheck]:
    base = build_scenario()
    schema = base.request.lineage_result.request.protocol_result.request.protocol_schema
    units = tuple(item.unit for item in schema.unit_policies)
    proteome = _semantic_result(
        {PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: {"declared_units": units[:-1]}}
    )
    transcript = _semantic_result(
        {PtmLocalizationRawInputRole.TRANSCRIPTOME: {"unit_system_version": "9.0.0"}}
    )
    stale = sha256_digest({"m0503": "stale"})
    reference = _semantic_result({PtmLocalizationRawInputRole.GENOME: {"reference_digest": stale}})
    assay_policy_binding = _semantic_result(
        {PtmLocalizationRawInputRole.GENOME: {"assay_specimen_policy_digest": stale}}
    )
    assay = _semantic_result(
        {PtmLocalizationRawInputRole.GENOME: {"assay_protocol_version": "9.0.0"}}
    )
    specimen = _semantic_result(
        {PtmLocalizationRawInputRole.GENOME: {"specimen_processing_version": "9.0.0"}}
    )
    role = PtmLocalizationRawInputRole.GENOME
    unsupported_scenario = _with_artifact_updates(
        base,
        {role: {"format_version": "9.0.0"}},
    )
    unsupported = ingest_ptm_localization_raw_inputs(
        unsupported_scenario.request,
        unsupported_scenario.artifacts_by_role,
    )
    swapped = dict(base.artifacts_by_role)
    swapped[role] = base.artifacts_by_role[PtmLocalizationRawInputRole.TRANSCRIPTOME]
    mismatch_scenario = _rebind_payloads(base, swapped)
    role_rejection = _input_error_check(
        "role_document_type_mismatch_rejected",
        mismatch_scenario,
        swapped,
        PtmLocalizationRawInputErrorCode.DOCUMENT_TYPE_MISMATCH,
    )
    return [
        _code_check(
            "proteome_unit_mismatch_quarantines",
            proteome,
            PtmLocalizationRawDiagnosticCode.UNIT_MISMATCH,
            PtmLocalizationRawInputDisposition.QUARANTINED,
        ),
        _code_check(
            "transcript_unit_mismatch_quarantines",
            transcript,
            PtmLocalizationRawDiagnosticCode.UNIT_MISMATCH,
            PtmLocalizationRawInputDisposition.QUARANTINED,
        ),
        _code_check(
            "reference_bundle_mismatch_quarantines",
            reference,
            PtmLocalizationRawDiagnosticCode.REFERENCE_BUNDLE_MISMATCH,
            PtmLocalizationRawInputDisposition.QUARANTINED,
        ),
        _code_check(
            "assay_specimen_policy_mismatch_quarantines",
            assay_policy_binding,
            PtmLocalizationRawDiagnosticCode.ASSAY_SPECIMEN_POLICY_MISMATCH,
            PtmLocalizationRawInputDisposition.QUARANTINED,
        ),
        _code_check(
            "assay_protocol_mismatch_quarantines",
            assay,
            PtmLocalizationRawDiagnosticCode.ASSAY_PROTOCOL_MISMATCH,
            PtmLocalizationRawInputDisposition.QUARANTINED,
        ),
        _code_check(
            "specimen_processing_mismatch_quarantines",
            specimen,
            PtmLocalizationRawDiagnosticCode.SPECIMEN_PROCESSING_MISMATCH,
            PtmLocalizationRawInputDisposition.QUARANTINED,
        ),
        _code_check(
            "unsupported_format_version_quarantines",
            unsupported,
            PtmLocalizationRawDiagnosticCode.UNSUPPORTED_FORMAT_VERSION,
            PtmLocalizationRawInputDisposition.QUARANTINED,
        ),
        role_rejection,
    ]


def _completeness_checks() -> list[EvalCheck]:
    incomplete_results = {
        role: _semantic_result(
            {role: {"completeness_state": PtmLocalizationRawCompletenessState.INCOMPLETE}}
        )
        for role in PtmLocalizationRawInputRole
    }
    assay = _semantic_result(
        {
            PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: {
                "assay_support_state": PtmLocalizationRawAssaySupportState.UNSUPPORTED
            }
        }
    )
    quality = _semantic_result(
        {
            PtmLocalizationRawInputRole.GENOME: {
                "parent_quality_state": PtmLocalizationRawParentQualityState.REJECTED
            }
        }
    )
    abstained = _semantic_result(
        {
            PtmLocalizationRawInputRole.TRANSCRIPTOME: {
                "evidence_state": PtmLocalizationRawEvidenceState.INDETERMINATE
            }
        }
    )
    precedence = _semantic_result(
        {
            PtmLocalizationRawInputRole.PTM_ANNOTATIONS: {
                "evidence_state": PtmLocalizationRawEvidenceState.MISSING,
                "completeness_state": PtmLocalizationRawCompletenessState.INCOMPLETE,
            }
        }
    )
    names = {
        PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: "proteome_incomplete_quarantines",
        PtmLocalizationRawInputRole.GENOME: "genome_incomplete_quarantines",
        PtmLocalizationRawInputRole.TRANSCRIPTOME: "transcriptome_incomplete_quarantines",
        PtmLocalizationRawInputRole.PTM_ANNOTATIONS: "ptm_annotations_incomplete_quarantines",
    }
    checks = [
        _code_check(
            names[role],
            result,
            PtmLocalizationRawDiagnosticCode.INCOMPLETE_MANIFEST,
            PtmLocalizationRawInputDisposition.QUARANTINED,
        )
        for role, result in incomplete_results.items()
    ]
    checks.extend(
        [
            _code_check(
                "assay_unsupported_quarantines",
                assay,
                PtmLocalizationRawDiagnosticCode.ASSAY_UNSUPPORTED,
                PtmLocalizationRawInputDisposition.QUARANTINED,
            ),
            _code_check(
                "parent_quality_rejected_quarantines",
                quality,
                PtmLocalizationRawDiagnosticCode.PARENT_QUALITY_UNACCEPTABLE,
                PtmLocalizationRawInputDisposition.QUARANTINED,
            ),
            _code_check(
                "artifact_not_evaluable_abstains",
                abstained,
                PtmLocalizationRawDiagnosticCode.ARTIFACT_NOT_EVALUABLE,
                PtmLocalizationRawInputDisposition.ABSTAINED,
            ),
            _check(
                "quarantine_precedes_abstention",
                precedence.disposition is PtmLocalizationRawInputDisposition.QUARANTINED
                and {
                    PtmLocalizationRawDiagnosticCode.ARTIFACT_NOT_EVALUABLE,
                    PtmLocalizationRawDiagnosticCode.INCOMPLETE_MANIFEST,
                }.issubset(_codes(precedence)),
                f"disposition={precedence.disposition.value}",
            ),
        ]
    )
    return checks


class _TraversalTrap:
    touched = 0

    def __getattribute__(self, name: str) -> object:
        if name == "touched":
            return object.__getattribute__(self, name)
        type(self).touched += 1
        raise AssertionError(name)


def _upstream_checks() -> list[EvalCheck]:
    canonical = build_scenario()
    canonical_result = ingest_ptm_localization_raw_inputs(
        canonical.request,
        canonical.artifacts_by_role,
    )
    quarantined = _with_artifact_updates(
        _genuine_scenario("upstream_protocol_quarantined"),
        {},
        policy=_maximum_policy(),
    )
    _TraversalTrap.touched = 0
    quarantined_result = ingest_ptm_localization_raw_inputs(quarantined.request, _TraversalTrap())
    quarantined_touches = _TraversalTrap.touched
    abstained = _genuine_scenario("upstream_identity_unresolved")
    _TraversalTrap.touched = 0
    abstained_result = ingest_ptm_localization_raw_inputs(abstained.request, _TraversalTrap())
    abstained_touches = _TraversalTrap.touched
    stale = sha256_digest({"m0503": "stale-binding"})

    def mutate_control(payload: dict[str, Any], role: str, field: str) -> None:
        context = cast("dict[str, Any]", payload["context"])
        refs = cast("dict[str, Any]", context["references"])
        control = cast("dict[str, Any]", refs[role])
        if field == "binding_digest":
            control[field] = stale
        else:
            evidence = cast("dict[str, Any]", control["evidence"])
            evidence["digest"] = stale

    def resigned_lineage(payload: dict[str, Any]) -> None:
        lineage = cast("dict[str, Any]", payload["lineage_result"])
        support = cast("dict[str, Any]", lineage["support"])
        support["rationale"] = "re-signed caller assertion outside the governed replay"
        lineage["result_digest"] = m0502_result_payload_digest(lineage)

    return [
        _check(
            "reconciled_upstream_permits_artifact_traversal",
            canonical_result.disposition is PtmLocalizationRawInputDisposition.VALIDATED
            and len(canonical_result.validated_inputs) == M0503_ROLE_COUNT,
            "reconciled upstream permits exact four-role traversal",
        ),
        _check(
            "quarantined_upstream_zero_artifact_traversal",
            quarantined_result.disposition is PtmLocalizationRawInputDisposition.QUARANTINED
            and _codes(quarantined_result)
            == {PtmLocalizationRawDiagnosticCode.UPSTREAM_LINEAGE_QUARANTINED}
            and quarantined_touches == 0
            and len(quarantined_result.evidence) == M0503_MIN_EVIDENCE
            and len(quarantined.request.policy.approved_parsers) == M0503_MAX_APPROVED_PARSERS,
            (
                f"disposition={quarantined_result.disposition.value};"
                f"traversals={quarantined_touches};evidence={len(quarantined_result.evidence)};"
                f"parsers={len(quarantined.request.policy.approved_parsers)}"
            ),
        ),
        _check(
            "abstained_upstream_zero_artifact_traversal",
            abstained_result.disposition is PtmLocalizationRawInputDisposition.ABSTAINED
            and _codes(abstained_result)
            == {PtmLocalizationRawDiagnosticCode.UPSTREAM_LINEAGE_ABSTAINED}
            and abstained_touches == 0,
            f"disposition={abstained_result.disposition.value};traversals={abstained_touches}",
        ),
        _validation_rejection(
            "stale_identity_binding_rejected",
            lambda payload: mutate_control(payload, "identity_lineage", "binding_digest"),
        ),
        _validation_rejection(
            "stale_quality_result_binding_rejected",
            lambda payload: mutate_control(payload, "quality", "digest"),
        ),
        _validation_rejection(
            "stale_support_receipt_binding_rejected",
            lambda payload: mutate_control(payload, "support", "digest"),
        ),
        _validation_rejection(
            "stale_intended_use_binding_rejected",
            lambda payload: mutate_control(payload, "intended_use", "digest"),
        ),
        _validation_rejection(
            "resigned_m0502_full_result_forgery_rejected",
            resigned_lineage,
        ),
    ]


def _duplicate_scenario() -> Scenario:
    base = build_scenario()
    source_role = PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME
    target_role = PtmLocalizationRawInputRole.GENOME
    source_artifact = next(item for item in base.request.artifacts if item.role is source_role)
    target_artifact = next(item for item in base.request.artifacts if item.role is target_role)
    duplicate_reference = target_artifact.content_reference.model_copy(
        update={"digest": source_artifact.content_reference.digest}
    )
    return _with_document_updates(
        base,
        {target_role: {"content_reference": duplicate_reference}},
        artifact_updates={target_role: {"content_reference": duplicate_reference}},
    )


def _diagnostic_nonmutation_checks() -> list[EvalCheck]:
    action_closure: list[bool] = []
    for code in PtmLocalizationRawDiagnosticCode:
        expected_action = (
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
            code=code,
            action=expected_action,
            evidence_basis_digest=sha256_digest({"m0503_code": code}),
        )
        wrong_action = (
            PtmLocalizationRawDiagnosticAction.RECORD
            if expected_action is not PtmLocalizationRawDiagnosticAction.RECORD
            else PtmLocalizationRawDiagnosticAction.QUARANTINE
        )
        try:
            PtmLocalizationRawParseDiagnostic(
                code=code,
                action=wrong_action,
                evidence_basis_digest=diagnostic.evidence_basis_digest,
            )
        except ValidationError:
            wrong_rejected = True
        else:
            wrong_rejected = False
        action_closure.append(diagnostic.action is expected_action and wrong_rejected)
    base = build_scenario()
    stale = sha256_digest({"m0503": "maximum-discrepancy"})
    document_updates: dict[PtmLocalizationRawInputRole, dict[str, object]] = {}
    for role in PtmLocalizationRawInputRole:
        mismatched_content = _reference(
            f"mismatch-{role.value}",
            media_type=ROLE_CONTENT_MEDIA_TYPES[role],
        )
        document_updates[role] = {
            "input_id": mismatched_content.artifact_id,
            "content_reference": mismatched_content,
            "identity_resolution_digest": stale,
            "protocol_result_digest": stale,
            "reference_bundle_digest": stale,
            "assay_specimen_policy_digest": stale,
            "intended_use_evidence_digest": stale,
            "assay_protocol_version": "9.0.0",
            "specimen_processing_version": "9.0.0",
            "unit_system_version": "9.0.0",
            "reference_bundle_version": "9.0.0",
            "evidence_state": PtmLocalizationRawEvidenceState.MISSING,
            "completeness_state": PtmLocalizationRawCompletenessState.INCOMPLETE,
            "assay_support_state": PtmLocalizationRawAssaySupportState.UNSUPPORTED,
            "parent_quality_state": PtmLocalizationRawParentQualityState.REJECTED,
        }
    artifact_updates = {
        artifact.role: {
            "content_reference": artifact.content_reference.model_copy(update={"digest": stale}),
            "format_version": "9.0.0",
        }
        for artifact in base.request.artifacts
    }
    maximum_discrepancy = _with_document_updates(
        base,
        document_updates,
        artifact_updates=artifact_updates,
    )
    multi = ingest_ptm_localization_raw_inputs(
        maximum_discrepancy.request,
        maximum_discrepancy.artifacts_by_role,
    )
    diagnostics_canonical = (
        tuple(multi.diagnostics) == tuple(sorted(multi.diagnostics, key=canonical_json_bytes))
        and len({(item.code, item.role) for item in multi.diagnostics}) == len(multi.diagnostics)
        and len(multi.diagnostics) <= M0503_MAX_DIAGNOSTICS
        and multi.disposition is PtmLocalizationRawInputDisposition.QUARANTINED
    )
    canonical = canonical_smoke()
    content_exact = all(
        item.content_reference
        == next(
            artifact for artifact in canonical.request.artifacts if artifact.role is item.role
        ).content_reference
        for item in canonical.validated_inputs
    )
    duplicate_scenario = _duplicate_scenario()
    duplicate = ingest_ptm_localization_raw_inputs(
        duplicate_scenario.request,
        duplicate_scenario.artifacts_by_role,
    )
    incomplete = _semantic_result(
        {
            PtmLocalizationRawInputRole.GENOME: {
                "completeness_state": PtmLocalizationRawCompletenessState.INCOMPLETE
            }
        }
    )
    abstained = _semantic_result(
        {
            PtmLocalizationRawInputRole.GENOME: {
                "evidence_state": PtmLocalizationRawEvidenceState.REDACTED
            }
        }
    )
    receipt = expected_receipt(
        canonical.request,
        canonical.validated_inputs,
        canonical.diagnostics,
        canonical.disposition,
    )
    return [
        _check(
            "diagnostic_code_action_closure",
            all(action_closure)
            and len(tuple(PtmLocalizationRawDiagnosticCode)) == M0503_DIAGNOSTIC_CODE_COUNT,
            "17 closed diagnostic codes map to exact precedence actions",
        ),
        _check(
            "diagnostics_unique_and_canonically_ordered",
            diagnostics_canonical,
            f"diagnostics={len(multi.diagnostics)};unique_code_role=true",
        ),
        _check(
            "content_references_preserved_exactly",
            content_exact,
            "all four content references retained without rewrite",
        ),
        _check(
            "duplicate_content_retained_without_deduplication",
            duplicate.disposition is PtmLocalizationRawInputDisposition.VALIDATED
            and _codes(duplicate) == {PtmLocalizationRawDiagnosticCode.DUPLICATE_CONTENT_RETAINED}
            and len(duplicate.validated_inputs) == M0503_ROLE_COUNT,
            f"inputs={len(duplicate.validated_inputs)};diagnostics={len(duplicate.diagnostics)}",
        ),
        _check(
            "quarantine_preserves_validated_documents",
            incomplete.disposition is PtmLocalizationRawInputDisposition.QUARANTINED
            and len(incomplete.validated_inputs) == M0503_ROLE_COUNT,
            f"disposition={incomplete.disposition.value};inputs={len(incomplete.validated_inputs)}",
        ),
        _check(
            "abstention_never_infers_negative",
            abstained.disposition is PtmLocalizationRawInputDisposition.ABSTAINED
            and not abstained.infers_protein
            and not abstained.infers_ptm_localization
            and not abstained.emits_variant_peptide,
            "typed abstention with all biological authority false",
        ),
        _check(
            "exact_compact_receipt_projection",
            canonical.receipt == receipt,
            f"receipt_digest={canonical.receipt.receipt_digest}",
        ),
    ]


def _maximum_policy() -> PtmLocalizationRawInputPolicy:
    base = _policy()
    parsers: list[ApprovedPtmLocalizationRawParser] = list(base.approved_parsers)
    for index in range(M0503_MAX_APPROVED_PARSERS - len(parsers)):
        seed = base.approved_parsers[index % len(base.approved_parsers)]
        parsers.append(
            seed.model_copy(
                update={
                    "parser_version": f"1.{index + 1}.0",
                    "evidence": _parser_evidence(seed.role).model_copy(
                        update={
                            "artifact_id": _oid("evidence", f"max-parser-{index}"),
                            "digest": sha256_digest({"m0503_max_parser": index}),
                        }
                    ),
                }
            )
        )
    return PtmLocalizationRawInputPolicy(
        policy_id=base.policy_id,
        version=base.version,
        max_document_bytes=base.max_document_bytes,
        max_total_bytes=base.max_total_bytes,
        approved_parsers=tuple(parsers),
        evidence=base.evidence,
        reviewed_by=base.reviewed_by,
        reviewed_at=base.reviewed_at,
    )


def _recursive_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {
            *map(str, value),
            *(key for child in value.values() for key in _recursive_keys(child)),
        }
    if isinstance(value, list | tuple):
        return {key for child in value for key in _recursive_keys(child)}
    return set()


def _recursive_strings(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return {item for child in value.values() for item in _recursive_strings(child)}
    if isinstance(value, list | tuple):
        return {item for child in value for item in _recursive_strings(child)}
    return set()


def _authority_exact(result: PtmLocalizationRawInputValidationResult) -> bool:
    fields = {
        "emits_variant_peptide",
        "emits_proteogenomic_state",
        "emits_proteotype",
        "emits_protein_level_subtype",
        "infers_identity",
        "infers_consent",
        "infers_protein",
        "infers_ptm_localization",
        "infers_kinase_activity",
        "performs_cn_to_protein_regression",
        "performs_all_omics_fusion",
        "recommends_treatment",
        "mutates_upstream",
        "executes_model",
    }
    payload = result.model_dump(mode="json", exclude_none=False)
    seen: dict[str, list[object]] = {field: [] for field in fields}

    def collect(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in seen:
                    seen[key].append(child)
                collect(child)
        elif isinstance(value, list | tuple):
            for child in value:
                collect(child)

    collect(payload)
    return all(values and all(item is False for item in values) for values in seen.values())


def _evidence_authority_checks() -> list[EvalCheck]:
    minimum = canonical_smoke()
    maximum_scenario = _with_artifact_updates(
        build_scenario(),
        {},
        policy=_maximum_policy(),
    )
    maximum = ingest_ptm_localization_raw_inputs(
        maximum_scenario.request,
        maximum_scenario.artifacts_by_role,
    )
    estimates = minimum.uncertainty.model_dump(mode="python", exclude_none=False)
    uncertainty_states = [
        value["state"]
        for key, value in estimates.items()
        if key != "sensitivity_notes" and isinstance(value, dict)
    ]
    payload = minimum.model_dump(mode="json", exclude_none=False)
    keys = _recursive_keys(payload)
    strings = _recursive_strings(payload)
    forbidden_raw = {"raw_bytes", "rows", "sequences", "spectra", "measurements"}
    canary = "CANARY_DIRECT_IDENTIFIER_DO_NOT_REFLECT"
    canary_bytes = canary.encode()
    canary_base = build_scenario()
    canary_role = PtmLocalizationRawInputRole.GENOME
    canary_artifact = next(
        item for item in canary_base.request.artifacts if item.role is canary_role
    )
    canary_reference = canary_artifact.content_reference.model_copy(
        update={"digest": f"sha256:{hashlib.sha256(canary_bytes).hexdigest()}"}
    )
    canary_scenario = _with_document_updates(
        canary_base,
        {
            canary_role: {
                "declared_record_count": 424242,
                "content_reference": canary_reference,
            }
        },
        artifact_updates={canary_role: {"content_reference": canary_reference}},
    )
    canary_result = ingest_ptm_localization_raw_inputs(
        canary_scenario.request,
        canary_scenario.artifacts_by_role,
    )
    canary_rendered = canonical_json_bytes(canary_result)
    identifier_canary = "Patient.SSN.123-45-6789"
    genome_document = _typed_documents(build_scenario())[PtmLocalizationRawInputRole.GENOME]
    genome_payload = genome_document.model_dump(mode="python", exclude_none=False)
    genome_payload["reference_build"] = identifier_canary
    try:
        GenomeInputDocument.model_validate(genome_payload, strict=True)
    except ValidationError:
        direct_identifier_rejected = True
    else:
        direct_identifier_rejected = False
    return [
        _check(
            "minimum_20_evidence_entries",
            len(minimum.evidence) == M0503_MIN_RECONCILED_EVIDENCE,
            f"evidence={len(minimum.evidence)}",
        ),
        _check(
            "maximum_48_evidence_entries",
            len(maximum.evidence) == M0503_MAX_EVIDENCE
            and len(maximum.request.policy.approved_parsers) == M0503_MAX_APPROVED_PARSERS,
            (
                f"parsers={len(maximum.request.policy.approved_parsers)};"
                f"evidence={len(maximum.evidence)}"
            ),
        ),
        _check(
            "all_seven_uncertainty_not_estimable",
            len(uncertainty_states) == EXPECTED_UNCERTAINTY_DIMENSIONS
            and all(state is EstimateState.NOT_ESTIMABLE for state in uncertainty_states),
            (
                "not_estimable="
                f"{sum(state is EstimateState.NOT_ESTIMABLE for state in uncertainty_states)}/7"
            ),
        ),
        _check(
            "result_contains_no_raw_bytes_or_rows",
            not forbidden_raw.intersection(keys | strings)
            and b'"raw_bytes"' not in canonical_json_bytes(payload),
            "no raw bytes, rows, spectra, sequences, or measurements",
        ),
        _check(
            "recursive_canary_absent_from_result",
            canary_bytes not in canary_rendered
            and canary_reference.digest.encode() in canary_rendered
            and direct_identifier_rejected
            and identifier_canary.encode() not in canary_rendered,
            "external canary represented only by digest; direct build identifier rejected",
        ),
        _check(
            "zero_model_event_persistence_authority",
            not minimum.executes_model and "event" not in keys and "event_store" not in keys,
            "model execution and event persistence authority absent",
        ),
        _check(
            "exact_three_limitations_and_all_authority_flags_false",
            len(minimum.limitations) == M0503_LIMITATION_COUNT and _authority_exact(minimum),
            (f"limitations={len(minimum.limitations)};authority_false={_authority_exact(minimum)}"),
        ),
    ]


class _ArbitraryMapping(Mapping[str, object]):
    touched = 0

    def __getitem__(self, key: str) -> object:
        type(self).touched += 1
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        type(self).touched += 1
        raise AssertionError("iter")

    def __len__(self) -> int:
        type(self).touched += 1
        raise AssertionError("len")


class _HostileDict(dict[str, object]):
    def get(self, *_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError

    def items(self) -> NoReturn:
        raise AssertionError

    def __iter__(self) -> NoReturn:
        raise AssertionError


class _FirewallBaseException(BaseException):
    pass


def _authorization_check(case_id: str, role: str, state: str) -> EvalCheck:
    payload = build_scenario_request().model_dump(mode="python", exclude_none=False)
    context = cast("dict[str, Any]", payload["context"])
    references = cast("dict[str, Any]", context["references"])
    cast("dict[str, Any]", references[role])["state"] = state
    _TraversalTrap.touched = 0
    payload["artifacts"] = _TraversalTrap()
    try:
        preflight_ptm_localization_raw_input_authorization(payload)
    except PtmLocalizationRawInputAuthorizationError:
        return _check(
            case_id,
            _TraversalTrap.touched == 0,
            f"authorization_rejected;governed_traversals={_TraversalTrap.touched}",
        )
    return _check(case_id, CHECK_FAILED, "authorization unexpectedly accepted")


def _firewall_check() -> EvalCheck:
    canonical = build_scenario()

    def hostile(value: object) -> object:
        if type(value) is dict:
            mapping = cast("dict[str, object]", value)
            return _HostileDict({key: hostile(dict.__getitem__(mapping, key)) for key in mapping})
        if type(value) is list:
            return [hostile(item) for item in list.__iter__(cast("list[object]", value))]
        return value

    candidate = hostile(canonical.request.model_dump(mode="python", exclude_none=False))
    hostile_rejected = False
    try:
        ingest_ptm_localization_raw_inputs(candidate, canonical.artifacts_by_role)
    except PtmLocalizationRawInputAuthorizationError:
        hostile_rejected = True
    exception_closed = False
    with patch.object(m0503_engine, "_member", side_effect=RuntimeError("ordinary")):
        try:
            preflight_ptm_localization_raw_input_authorization(canonical.request)
        except PtmLocalizationRawInputAuthorizationError:
            exception_closed = True
    base_propagated = False
    with patch.object(m0503_engine, "_member", side_effect=_FirewallBaseException()):
        try:
            preflight_ptm_localization_raw_input_authorization(canonical.request)
        except _FirewallBaseException:
            base_propagated = True
    return _check(
        "dict_subclass_exception_baseexception_firewall",
        hostile_rejected and exception_closed and base_propagated,
        (
            f"hostile_dict_rejected={hostile_rejected};"
            f"exception_fail_closed={exception_closed};baseexception_propagated={base_propagated}"
        ),
    )


def _document_error(
    case_id: str,
    payload_mutator: Callable[[dict[str, Any]], None],
    expected: PtmLocalizationRawInputErrorCode,
) -> EvalCheck:
    base = build_scenario()
    role = PtmLocalizationRawInputRole.GENOME
    decoded = cast(
        "dict[str, Any]",
        json.loads(base.artifacts_by_role[role].decode("utf-8")),
    )
    payload_mutator(decoded)
    malformed = canonical_json_bytes(decoded)
    supplied = dict(base.artifacts_by_role)
    supplied[role] = malformed
    rebound = _rebind_payloads(base, supplied)
    return _input_error_check(case_id, rebound, supplied, expected)


def _derived_regions_forgery_check() -> EvalCheck:
    result = _semantic_result(
        {
            PtmLocalizationRawInputRole.GENOME: {
                "completeness_state": PtmLocalizationRawCompletenessState.INCOMPLETE
            }
        }
    )
    stale = sha256_digest({"m0503": "resigned-derived-region"})

    def receipt_region(payload: dict[str, Any]) -> None:
        receipt = cast("dict[str, Any]", payload["receipt"])
        receipt["artifact_mapping_digest"] = stale
        receipt["receipt_digest"] = receipt_digest(receipt)

    def validated_input_region(payload: dict[str, Any]) -> None:
        item = cast("list[dict[str, Any]]", payload["validated_inputs"])[0]
        item["document_digest"] = stale

    def diagnostic_region(payload: dict[str, Any]) -> None:
        item = cast("list[dict[str, Any]]", payload["diagnostics"])[0]
        item["evidence_basis_digest"] = stale

    def provenance_region(payload: dict[str, Any]) -> None:
        provenance = cast("dict[str, Any]", payload["provenance"])
        provenance["configuration_digest"] = stale

    def evidence_region(payload: dict[str, Any]) -> None:
        item = cast("list[dict[str, Any]]", payload["evidence"])[0]
        item["claim"] = "Re-signed caller claim outside the exact evidence index."

    def limitation_region(payload: dict[str, Any]) -> None:
        item = cast("list[dict[str, Any]]", payload["limitations"])[0]
        item["statement"] = "Re-signed limitation outside the exact closed set."

    rejected: list[bool] = []
    for mutation in (
        receipt_region,
        validated_input_region,
        diagnostic_region,
        provenance_region,
        evidence_region,
        limitation_region,
    ):
        payload = copy.deepcopy(result.model_dump(mode="json", exclude_none=False))
        mutation(payload)
        payload["result_digest"] = result_payload_digest(payload)
        try:
            _RESULT_ADAPTER.validate_json(canonical_json_bytes(payload), strict=True)
        except (ValidationError, ValueError):
            rejected.append(True)
        else:
            rejected.append(False)
    return _check(
        "result_derived_regions_forgery_rejected",
        all(rejected),
        f"rejected_regions={sum(rejected)}/{len(rejected)}",
    )


def _semantic_reorder_check() -> EvalCheck:
    scenario = build_scenario()
    canonical_result = ingest_ptm_localization_raw_inputs(
        scenario.request,
        scenario.artifacts_by_role,
    )
    request_payload = scenario.request.model_dump(mode="json", exclude_none=False)
    cast("list[Any]", request_payload["artifacts"]).reverse()
    policy = cast("dict[str, Any]", request_payload["policy"])
    cast("list[Any]", policy["approved_parsers"]).reverse()
    lineage = cast("dict[str, Any]", request_payload["lineage_result"])
    cast("list[Any]", lineage.get("validated_inputs", [])).reverse()
    reordered_request = _strict_request(request_payload)
    reordered_result = ingest_ptm_localization_raw_inputs(
        reordered_request,
        dict(reversed(tuple(scenario.artifacts_by_role.items()))),
    )
    result_payload = canonical_result.model_dump(mode="json", exclude_none=False)
    for field in ("validated_inputs", "diagnostics", "evidence", "limitations"):
        cast("list[Any]", result_payload[field]).reverse()
    provenance = cast("dict[str, Any]", result_payload["provenance"])
    cast("list[Any]", provenance["input_digests"]).reverse()
    cast("list[Any]", provenance["control_decisions"]).reverse()
    reconstructed = _RESULT_ADAPTER.validate_json(
        canonical_json_bytes(result_payload),
        strict=True,
    )
    return _check(
        "semantic_reorder_full_equality",
        reordered_result == canonical_result and reconstructed == canonical_result,
        "request, mapping, result, evidence, provenance reorder invariant",
    )


def _cli_boundary_check() -> EvalCheck:
    scenario = build_scenario()
    filenames = {
        PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: ("mass-spectrometry-proteome.json"),
        PtmLocalizationRawInputRole.GENOME: "genome.json",
        PtmLocalizationRawInputRole.TRANSCRIPTOME: "transcriptome.json",
        PtmLocalizationRawInputRole.PTM_ANNOTATIONS: "ptm-annotations.json",
    }
    refusals: list[bool] = []
    with TemporaryDirectory(prefix="m0503-eval-cli-") as temporary:
        root = Path(temporary)
        request_path = root / "request.json"
        source = root / "source"
        source.mkdir()
        output = root / "result.json"
        request_path.write_bytes(canonical_json_bytes(scenario.request.model_dump(mode="json")))
        for role, filename in filenames.items():
            (source / filename).write_bytes(scenario.artifacts_by_role[role])
        output.write_bytes(b"existing")
        existing = CliRunner().invoke(
            cli_app,
            [
                "ptm_localization-raw",
                "ingest",
                str(request_path),
                str(source),
                "--output",
                str(output),
            ],
        )
        refusals.append(existing.exit_code != 0 and output.read_bytes() == b"existing")
        output.unlink()
        extra = source / "extra.json"
        extra.write_bytes(b"{}")
        unexpected = CliRunner().invoke(
            cli_app,
            [
                "ptm_localization-raw",
                "ingest",
                str(request_path),
                str(source),
                "--output",
                str(output),
            ],
        )
        refusals.append(unexpected.exit_code != 0 and not output.exists())
        extra.unlink()
        target = source / filenames[PtmLocalizationRawInputRole.GENOME]
        original = target.read_bytes()
        target.unlink()
        target.mkdir()
        nonregular = CliRunner().invoke(
            cli_app,
            [
                "ptm_localization-raw",
                "ingest",
                str(request_path),
                str(source),
                "--output",
                str(output),
            ],
        )
        refusals.append(nonregular.exit_code != 0 and not output.exists())
        target.rmdir()
        target.write_bytes(original)
        with patch.object(cli_adapter, "_same_file_receipt", return_value=False):
            changed = CliRunner().invoke(
                cli_app,
                [
                    "ptm_localization-raw",
                    "ingest",
                    str(request_path),
                    str(source),
                    "--output",
                    str(output),
                ],
            )
        refusals.append(changed.exit_code != 0 and not output.exists())
        replacement = source / "replacement.json"
        target.replace(replacement)
        try:
            target.symlink_to(replacement)
        except OSError:
            refusals.append(True)
        else:
            linked = CliRunner().invoke(
                cli_app,
                [
                    "ptm_localization-raw",
                    "ingest",
                    str(request_path),
                    str(source),
                    "--output",
                    str(output),
                ],
            )
            refusals.append(linked.exit_code != 0 and not output.exists())
    return _check(
        "cli_symlink_nonregular_toctou_and_existing_output_refused",
        len(refusals) == EXPECTED_CLI_REFUSALS and all(refusals),
        f"filesystem_refusals={sum(refusals)}/{EXPECTED_CLI_REFUSALS}",
    )


def _strict_boundary_checks() -> list[EvalCheck]:
    controls = (
        ("approved_configuration_denial_zero_traversal", "approved_configuration", "rejected"),
        ("identity_denial_zero_traversal", "identity_lineage", "unresolved"),
        ("provenance_denial_zero_traversal", "provenance", "rejected"),
        ("consent_denial_zero_traversal", "consent", "withheld"),
        ("quality_denial_zero_traversal", "quality", "rejected"),
        ("support_denial_zero_traversal", "support", "rejected"),
        ("intended_use_denial_zero_traversal", "intended_use", "rejected"),
    )
    checks = [_authorization_check(*item) for item in controls]
    _ArbitraryMapping.touched = 0
    try:
        preflight_ptm_localization_raw_input_authorization(_ArbitraryMapping())
    except PtmLocalizationRawInputAuthorizationError:
        checks.append(
            _check(
                "arbitrary_mapping_rejected_without_access",
                _ArbitraryMapping.touched == 0,
                f"authorization_rejected;mapping_access={_ArbitraryMapping.touched}",
            )
        )
    else:
        checks.append(
            _check(
                "arbitrary_mapping_rejected_without_access",
                CHECK_FAILED,
                "mapping accepted",
            )
        )
    checks.append(_firewall_check())
    base = build_scenario()
    role = PtmLocalizationRawInputRole.GENOME
    rendered = base.artifacts_by_role[role].decode("utf-8")
    duplicate = rendered.replace("{", '{"document_type":"genome_input",', 1).encode()
    supplied = dict(base.artifacts_by_role)
    supplied[role] = duplicate
    duplicate_scenario = _rebind_payloads(base, supplied)
    checks.append(
        _input_error_check(
            "duplicate_json_key_rejected",
            duplicate_scenario,
            supplied,
            PtmLocalizationRawInputErrorCode.DOCUMENT_JSON_INVALID,
        )
    )
    checks.extend(
        [
            _document_error(
                "unknown_field_rejected",
                lambda payload: payload.__setitem__("unknown_field", "unexpected"),
                PtmLocalizationRawInputErrorCode.DOCUMENT_JSON_INVALID,
            ),
            _document_error(
                "coercion_rejected",
                lambda payload: payload.__setitem__("declared_record_count", "1"),
                PtmLocalizationRawInputErrorCode.DOCUMENT_JSON_INVALID,
            ),
        ]
    )
    oversized = b"{}" + (b" " * (M0503_MAX_CANONICAL_REQUEST_BYTES - 1))
    try:
        M0503Plugin(M0503Service()).validate(M0503Submission(oversized, {}))
    except StrictJsonError as error:
        checks.append(
            _check(
                "request_4mib_plus_one_rejected",
                error.code.value == "json_too_large",
                f"validation_rejected:{error.code.value};bytes={len(oversized)}",
            )
        )
    else:
        checks.append(_check("request_4mib_plus_one_rejected", CHECK_FAILED, "oversize accepted"))
    checks.append(_semantic_reorder_check())

    def upstream_forgery(payload: dict[str, Any]) -> None:
        lineage = cast("dict[str, Any]", payload["lineage_result"])
        lineage["result_digest"] = sha256_digest({"m0503": "forged-upstream"})

    checks.append(_validation_rejection("embedded_upstream_forgery_rejected", upstream_forgery))

    checks.append(_derived_regions_forgery_check())
    result = canonical_smoke()
    rendered_result = canonical_json_bytes(result)
    checks.append(
        _check(
            "privacy_and_authority_ceiling",
            _authority_exact(result)
            and b"CANARY_DIRECT_IDENTIFIER" not in rendered_result
            and b"raw_bytes" not in rendered_result,
            "recursive privacy and exact authority ceiling",
        )
    )
    checks.append(_cli_boundary_check())
    return checks


def _corpus() -> tuple[dict[str, Any], str]:
    raw = SCENARIO_PATH.read_bytes()
    parsed = strict_json_loads(raw, max_bytes=len(raw))
    if type(parsed) is not dict:
        raise _UnsupportedScenarioError
    return (
        cast("dict[str, Any]", parsed),
        f"sha256:{hashlib.sha256(raw).hexdigest()}",
    )


def _inventory(corpus: dict[str, Any]) -> tuple[list[str], tuple[int, ...], list[EvalCheck]]:
    groups = cast("list[dict[str, Any]]", corpus["scenario_groups"])
    declared = [
        cast("str", case_id)
        for group in groups
        for case_id in cast("list[object]", group["case_ids"])
    ]
    allocation = tuple(len(cast("list[object]", group["case_ids"])) for group in groups)
    closed = (
        len(groups) == EXPECTED_GROUP_COUNT
        and len(declared) == EXPECTED_CASE_COUNT
        and len(set(declared)) == EXPECTED_CASE_COUNT
        and allocation == EXPECTED_ALLOCATION
        and all(
            set(cast("list[object]", group["case_ids"]))
            == set(cast("dict[str, object]", group["case_expectations"]))
            for group in groups
        )
    )
    return (
        declared,
        allocation,
        [
            EvalCheck(
                name="corpus.inventory",
                passed=closed,
                detail=f"groups={len(groups)};cases={len(declared)};allocation={allocation}",
            )
        ],
    )


def run_evaluation() -> dict[str, object]:
    """Execute every locked case through a distinct substantive oracle."""

    corpus, fixture_digest = _corpus()
    declared, _allocation, checks = _inventory(corpus)
    groups = (
        _canonical_checks(),
        _mapping_cap_checks(),
        _version_reference_checks(),
        _completeness_checks(),
        _upstream_checks(),
        _diagnostic_nonmutation_checks(),
        _evidence_authority_checks(),
        _strict_boundary_checks(),
    )
    scenario_checks = [check for group in groups for check in group]
    checks.extend(scenario_checks)
    executed = [check.name.removeprefix("scenario.") for check in scenario_checks]
    missing = sorted(set(declared) - set(executed))
    extra = sorted(set(executed) - set(declared))
    duplicated = sorted(case_id for case_id in set(executed) if executed.count(case_id) != 1)
    checks.append(
        EvalCheck(
            name="corpus.executable_coverage",
            passed=not missing
            and not extra
            and not duplicated
            and len(executed) == EXPECTED_CASE_COUNT
            and tuple(len(group) for group in groups) == EXPECTED_ALLOCATION,
            detail=(
                f"declared={len(declared)};executed={len(executed)};"
                f"allocation={tuple(len(group) for group in groups)};substantive={len(executed)}"
            ),
        )
    )
    return {
        "module_id": MODULE_ID,
        "passed": all(check.passed for check in checks),
        "phase": "locked_executable_corpus",
        "fixture_digest": fixture_digest,
        "declared_case_count": len(declared),
        "executed_case_count": len(executed),
        "missing_case_ids": missing,
        "extra_case_ids": extra,
        "duplicated_case_ids": duplicated,
        "checks": [asdict(check) for check in checks],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    report = run_evaluation()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0 if report["passed"] else 1


__all__ = [
    "Scenario",
    "build_scenario",
    "build_scenario_request",
    "canonical_smoke",
    "main",
    "run_evaluation",
]


if __name__ == "__main__":
    raise SystemExit(main())
