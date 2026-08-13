"""Replay the locked M04-03 synthetic raw-manifest corpus."""

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

from evals.m04_02.run import (
    DERIVATION_MEDIA_TYPE,
    _canonical_claims,
    _claim_with,
    _genuine_identity_resolution,
    _genuine_protocol_result,
)
from evals.m04_02.run import (
    _artifact as _m0402_artifact,
)
from evals.m04_02.run import (
    _context as _m0402_context,
)
from evals.m04_02.run import (
    _oid as _m0402_oid,
)
from evals.m04_02.run import (
    _policy as _m0402_policy,
)
from glio_proteogen.adapters import cli as cli_adapter
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m04_01 import (
    ModificationLocalizationState,
    ProteoformProtocolConformanceResult,
)
from glio_proteogen.contracts.m04_02 import (
    ProteoformIdentityLineageResolution,
    ProteoformLineageArtifactClaim,
    ProteoformLineageArtifactDerivation,
    ProteoformLineageArtifactRole,
    ReconcileProteoformIdentityLineageRequest,
)
from glio_proteogen.contracts.m04_02 import (
    result_payload_digest as m0402_result_payload_digest,
)
from glio_proteogen.contracts.m04_03 import (
    M0403_DIAGNOSTIC_CODE_COUNT,
    M0403_LIMITATION_COUNT,
    M0403_MAX_APPROVED_PARSERS,
    M0403_MAX_CANONICAL_REQUEST_BYTES,
    M0403_MAX_DECLARED_RECORD_COUNT,
    M0403_MAX_DIAGNOSTICS,
    M0403_MAX_DOCUMENT_BYTES,
    M0403_MAX_EVIDENCE,
    M0403_MIN_EVIDENCE,
    M0403_ROLE_COUNT,
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
    ProteoformRawInputRole,
    ProteoformRawInputValidationResult,
    ProteoformRawParentQualityState,
    ProteoformRawParseDiagnostic,
    PtmAnnotationInputDocument,
    TranscriptomeInputDocument,
    configuration_digest,
    expected_receipt,
    normalized_document,
    opaque_proteoform_raw_input_identifier,
    receipt_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, EstimateState, ExecutionContext
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage import (
    reconcile_proteoform_identity_lineage,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_03_raw_ingestion import (
    M0403Plugin,
    M0403Service,
    M0403Submission,
    ProteoformRawInputAuthorizationError,
    ProteoformRawInputError,
    ProteoformRawInputErrorCode,
    ingest_proteoform_raw_inputs,
    preflight_proteoform_raw_input_authorization,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_03_raw_ingestion import (
    engine as m0403_engine,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m04_03.v1 import ProteoformRawInputDocument

MODULE_ID: Final = "GLIO-PROTEOGEN-M04-03"
SCENARIO_PATH: Final = Path("tests/fixtures/m04_03/scenarios.json")
EXPECTED_CASE_COUNT: Final = 72
EXPECTED_ALLOCATION: Final = (7, 9, 8, 8, 8, 7, 7, 18)
EXPECTED_GROUP_COUNT: Final = len(EXPECTED_ALLOCATION)
EXPECTED_UNCERTAINTY_DIMENSIONS: Final = 7
EXPECTED_CLI_REFUSALS: Final = 5
CHECK_PASSED: Final = True
CHECK_FAILED: Final = False
FIXED_TIME: Final = datetime(2026, 8, 13, 15, tzinfo=UTC)
CONTROL_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.control+json"
POLICY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-03.policy+json"
PARSER_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-03.parser+json"
ROLE_CONTENT_MEDIA_TYPES: Final = {
    ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
        "application/vnd.glio-proteogen.m04-03.proteome-input+json"
    ),
    ProteoformRawInputRole.GENOME: "application/vnd.glio-proteogen.m04-03.genome-input+json",
    ProteoformRawInputRole.TRANSCRIPTOME: (
        "application/vnd.glio-proteogen.m04-03.transcriptome-input+json"
    ),
    ProteoformRawInputRole.PTM_ANNOTATIONS: (
        "application/vnd.glio-proteogen.m04-03.ptm-annotation-input+json"
    ),
}
ROLE_FORMATS: Final = {
    ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
        ProteoformRawDocumentFormat.PROTEOME_MANIFEST_JSON
    ),
    ProteoformRawInputRole.GENOME: ProteoformRawDocumentFormat.GENOME_MANIFEST_JSON,
    ProteoformRawInputRole.TRANSCRIPTOME: (ProteoformRawDocumentFormat.TRANSCRIPTOME_MANIFEST_JSON),
    ProteoformRawInputRole.PTM_ANNOTATIONS: (
        ProteoformRawDocumentFormat.PTM_ANNOTATION_MANIFEST_JSON
    ),
}
ROLE_PROJECTION: Final = {
    ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
        ProteoformLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST
    ),
    ProteoformRawInputRole.GENOME: ProteoformLineageArtifactRole.GENOME_MANIFEST,
    ProteoformRawInputRole.TRANSCRIPTOME: (ProteoformLineageArtifactRole.TRANSCRIPTOME_MANIFEST),
    ProteoformRawInputRole.PTM_ANNOTATIONS: (ProteoformLineageArtifactRole.PTM_ANNOTATION_MANIFEST),
}


@dataclass(frozen=True, slots=True)
class Scenario:
    """One strict request and its separately supplied immutable manifest bytes."""

    request: IngestProteoformRawInputsRequest
    artifacts_by_role: dict[ProteoformRawInputRole, bytes]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    """One named executable assertion in the locked corpus."""

    name: str
    passed: bool
    detail: str


class _UnsupportedScenarioError(ValueError):
    pass


def _oid(namespace: str, label: object) -> str:
    value = f"{namespace}.{sha256_digest({'m0403': label}).removeprefix('sha256:')}"
    return opaque_proteoform_raw_input_identifier(cast("Any", namespace), value)


def _reference(label: str, *, media_type: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_oid("input", label),
        version="1.0.0",
        digest=sha256_digest({"m0403_content": label}),
        media_type=media_type,
    )


def _parser_evidence(role: ProteoformRawInputRole) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_oid("evidence", f"parser-{role.value}"),
        version="1.0.0",
        digest=sha256_digest({"m0403_parser": role}),
        media_type=PARSER_MEDIA_TYPE,
    )


def _policy() -> ProteoformRawInputPolicy:
    parsers = tuple(
        ApprovedProteoformRawParser(
            role=role,
            format=ROLE_FORMATS[role],
            format_version="1.0.0",
            parser_version="1.0.0",
            media_type=ROLE_CONTENT_MEDIA_TYPES[role],
            max_document_bytes=8 * 1024 * 1024,
            evidence=_parser_evidence(role),
        )
        for role in ProteoformRawInputRole
    )
    return ProteoformRawInputPolicy(
        policy_id=_oid("policy", "canonical"),
        version="1.0.0",
        approved_parsers=parsers,
        evidence=ArtifactReference(
            artifact_id=_oid("evidence", "policy"),
            version="1.0.0",
            digest=sha256_digest({"m0403_policy": "canonical"}),
            media_type=POLICY_MEDIA_TYPE,
        ),
        reviewed_by=_oid("reviewer", "synthetic"),
        reviewed_at=FIXED_TIME,
    )


def _documents(
    claims_by_role: dict[ProteoformRawInputRole, ProteoformLineageArtifactClaim],
    protocol: ProteoformProtocolConformanceResult,
) -> dict[ProteoformRawInputRole, ProteoformRawInputDocument]:
    schema = protocol.request.protocol_schema
    common: dict[ProteoformRawInputRole, dict[str, object]] = {}
    for role in ProteoformRawInputRole:
        content = _reference(role.value, media_type=ROLE_CONTENT_MEDIA_TYPES[role])
        common[role] = {
            "input_id": content.artifact_id,
            "lineage_claim_id": claims_by_role[role].claim_id,
            "identity_resolution_digest": protocol.receipt.identity_subject_digest,
            "protocol_result_digest": protocol.result_digest,
            "reference_bundle_digest": protocol.receipt.reference_bundle_digest,
            "coordinate_policy_digest": protocol.receipt.coordinate_policy_digest,
            "intended_use_evidence_digest": protocol.receipt.intended_use_evidence_digest,
            "assay_protocol_version": schema.assay_protocol_version,
            "specimen_processing_version": schema.specimen_processing_version,
            "unit_definition_version": schema.unit_system_version,
            "content_reference": content,
            "declared_record_count": 1,
            "evidence_state": ProteoformRawEvidenceState.AVAILABLE,
            "completeness_state": ProteoformRawCompletenessState.COMPLETE,
            "assay_support_state": ProteoformRawAssaySupportState.SUPPORTED,
            "parent_quality_state": ProteoformRawParentQualityState.ACCEPTED,
        }
    return {
        ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
            MassSpectrometryProteomeInputDocument.model_validate(
                {
                    **common[ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME],
                    "applicability": schema.applicability,
                    "protein_unit": schema.quantification.protein_unit,
                    "protein_scale": schema.quantification.protein_scale,
                },
                strict=True,
            )
        ),
        ProteoformRawInputRole.GENOME: GenomeInputDocument.model_validate(
            {
                **common[ProteoformRawInputRole.GENOME],
                "genome_convention": schema.coordinate_policy.genome_convention,
                "genome_reference_digest": schema.reference_bundle.genome_reference.digest,
                "coordinate_mapping_version": schema.coordinate_policy.coordinate_mapping_version,
            },
            strict=True,
        ),
        ProteoformRawInputRole.TRANSCRIPTOME: TranscriptomeInputDocument.model_validate(
            {
                **common[ProteoformRawInputRole.TRANSCRIPTOME],
                "transcript_unit": schema.quantification.transcript_unit,
                "transcript_scale": schema.quantification.transcript_scale,
                "transcript_convention": schema.coordinate_policy.transcript_convention,
                "transcript_annotation_digest": (
                    schema.reference_bundle.transcript_annotation_reference.digest
                ),
                "transcript_protein_mapping_digest": (
                    schema.reference_bundle.transcript_protein_mapping_reference.digest
                ),
            },
            strict=True,
        ),
        ProteoformRawInputRole.PTM_ANNOTATIONS: PtmAnnotationInputDocument.model_validate(
            {
                **common[ProteoformRawInputRole.PTM_ANNOTATIONS],
                "modification_vocabulary_id": schema.controlled_vocabulary_id,
                "modification_vocabulary_version": schema.controlled_vocabulary_version,
                "modification_vocabulary_digest": (
                    schema.reference_bundle.modification_vocabulary_reference.digest
                ),
                "protein_convention": schema.coordinate_policy.protein_convention,
                "coordinate_mapping_version": schema.coordinate_policy.coordinate_mapping_version,
                "localization_states": tuple(ModificationLocalizationState),
            },
            strict=True,
        ),
    }


def _genuine_scenario(upstream_case_id: str = "canonical_all_seven_entity_chain") -> Scenario:
    """Build documents first and seal them through all three genuine upstream operations."""

    identity = _genuine_identity_resolution(upstream_case_id)
    protocol = _genuine_protocol_result(
        identity,
        case_id=upstream_case_id,
    )
    lineage_policy = _m0402_policy()
    claims = _canonical_claims(identity, protocol)
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
        _claim_with(
            claim,
            artifact=claim.artifact.model_copy(
                update={
                    "digest": f"sha256:{hashlib.sha256(document_bytes[role]).hexdigest()}",
                }
            ),
        )
        if (role := next((key for key, value in source_claims.items() if value is claim), None))
        is not None
        else claim
        for claim in claims
    )
    bundle = next(
        item
        for item in updated_claims
        if item.role is ProteoformLineageArtifactRole.PROTEIN_RNA_DISCORDANCE_INPUT_BUNDLE
    )
    method = lineage_policy.approved_derivation_methods[0]
    derivation = ProteoformLineageArtifactDerivation(
        derivation_id=_m0402_oid("derivation", "m0403-canonical"),
        source_claim_ids=tuple(item.claim_id for item in updated_claims if item is not bundle),
        target_claim_id=bundle.claim_id,
        method_id=method.method_id,
        method_version=method.version,
        evidence=_m0402_artifact("m0403-derivation", media_type=DERIVATION_MEDIA_TYPE),
    )
    lineage_context = _m0402_context(protocol, identity, lineage_policy)
    lineage_request = ReconcileProteoformIdentityLineageRequest(
        request_id=lineage_context.request_id,
        context=lineage_context,
        identity_resolution=identity,
        protocol_result=protocol,
        policy=lineage_policy,
        artifact_claims=updated_claims,
        derivations=(derivation,),
        supersedes_result_digest=None,
    )
    lineage_result = reconcile_proteoform_identity_lineage(lineage_request)
    policy = _policy()
    artifacts = tuple(
        ProteoformRawInputArtifact(
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
                    for claim in updated_claims
                    if claim.claim_id == item.lineage_claim_id
                )
            }
        )
        for item in artifacts
    )
    context = _context(lineage_result, policy)
    request = IngestProteoformRawInputsRequest(
        request_id=context.request_id,
        context=context,
        lineage_result=lineage_result,
        policy=policy,
        artifacts=artifacts,
        supersedes_result_digest=None,
    )
    return Scenario(request=request, artifacts_by_role=document_bytes)


def build_scenario(case_id: str = "canonical_four_role_documents_validated") -> Scenario:
    """Build canonical documents, execute genuine upstream operations, then construct M04-03."""

    if case_id != "canonical_four_role_documents_validated":
        raise _UnsupportedScenarioError(case_id)
    return _genuine_scenario()


def _context(
    lineage: ProteoformIdentityLineageResolution,
    policy: ProteoformRawInputPolicy,
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
) -> IngestProteoformRawInputsRequest:
    """Return the strict request component of one synthetic scenario."""

    return build_scenario(case_id).request


def canonical_smoke() -> ProteoformRawInputValidationResult:
    scenario = build_scenario()
    return ingest_proteoform_raw_inputs(scenario.request, scenario.artifacts_by_role)


_DOCUMENT_MODELS: Final[dict[ProteoformRawInputRole, type[BaseModel]]] = {
    ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME: (MassSpectrometryProteomeInputDocument),
    ProteoformRawInputRole.GENOME: GenomeInputDocument,
    ProteoformRawInputRole.TRANSCRIPTOME: TranscriptomeInputDocument,
    ProteoformRawInputRole.PTM_ANNOTATIONS: PtmAnnotationInputDocument,
}
_REQUEST_ADAPTER: Final = TypeAdapter(IngestProteoformRawInputsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteoformRawInputValidationResult)


def _typed_documents(scenario: Scenario) -> dict[ProteoformRawInputRole, BaseModel]:
    return {
        role: TypeAdapter(_DOCUMENT_MODELS[role]).validate_json(payload, strict=True)
        for role, payload in scenario.artifacts_by_role.items()
    }


def _artifact_with(
    artifact: ProteoformRawInputArtifact,
    **updates: object,
) -> ProteoformRawInputArtifact:
    payload = artifact.model_dump(mode="python", exclude_none=False)
    payload.update(updates)
    return ProteoformRawInputArtifact.model_validate(payload, strict=True)


def _rebind_payloads(
    base: Scenario,
    payloads: dict[ProteoformRawInputRole, bytes],
    *,
    artifact_updates: dict[ProteoformRawInputRole, dict[str, object]] | None = None,
    policy: ProteoformRawInputPolicy | None = None,
) -> Scenario:
    """Re-execute public M04-02 after sealing replacement canonical manifest bytes."""

    lineage_request = base.request.lineage_result.request
    role_by_upstream = {upstream: role for role, upstream in ROLE_PROJECTION.items()}
    claims = tuple(
        _claim_with(
            claim,
            artifact=claim.artifact.model_copy(
                update={
                    "digest": f"sha256:{hashlib.sha256(payloads[role]).hexdigest()}",
                }
            ),
        )
        if (role := role_by_upstream.get(claim.role)) is not None
        else claim
        for claim in lineage_request.artifact_claims
    )
    rebound_lineage_request = ReconcileProteoformIdentityLineageRequest(
        request_id=lineage_request.request_id,
        context=lineage_request.context,
        identity_resolution=lineage_request.identity_resolution,
        protocol_result=lineage_request.protocol_result,
        policy=lineage_request.policy,
        artifact_claims=claims,
        derivations=lineage_request.derivations,
        supersedes_result_digest=lineage_request.supersedes_result_digest,
    )
    lineage_result = reconcile_proteoform_identity_lineage(rebound_lineage_request)
    active_policy = policy or base.request.policy
    updates = artifact_updates or {}
    rebound_artifacts: list[ProteoformRawInputArtifact] = []
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
    request = IngestProteoformRawInputsRequest(
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
    updates: dict[ProteoformRawInputRole, dict[str, object]],
    *,
    artifact_updates: dict[ProteoformRawInputRole, dict[str, object]] | None = None,
    policy: ProteoformRawInputPolicy | None = None,
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
    updates: dict[ProteoformRawInputRole, dict[str, object]],
    *,
    policy: ProteoformRawInputPolicy | None = None,
) -> Scenario:
    active_policy = policy or base.request.policy
    artifacts = tuple(
        _artifact_with(item, **updates.get(item.role, {})) for item in base.request.artifacts
    )
    context = _context(base.request.lineage_result, active_policy)
    request = IngestProteoformRawInputsRequest(
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


def _codes(result: ProteoformRawInputValidationResult) -> set[ProteoformRawDiagnosticCode]:
    codes = {item.code for item in result.diagnostics}
    receipt_codes = set(result.receipt.diagnostic_codes)
    return codes if codes == receipt_codes else set()


def _strict_request(payload: dict[str, Any]) -> IngestProteoformRawInputsRequest:
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
        ingest_proteoform_raw_inputs(request, scenario.artifacts_by_role)
    except (ValidationError, ValueError) as error:
        return _check(case_id, CHECK_PASSED, f"validation_rejected:{type(error).__name__}")
    return _check(case_id, CHECK_FAILED, "request unexpectedly accepted")


def _canonical_checks() -> list[EvalCheck]:
    scenario = build_scenario()
    result = ingest_proteoform_raw_inputs(scenario.request, scenario.artifacts_by_role)
    protocol = scenario.request.lineage_result.request.protocol_result
    exact_bindings = all(
        item.document.protocol_result_digest == protocol.result_digest
        and item.document.reference_bundle_digest == protocol.receipt.reference_bundle_digest
        and item.document.coordinate_policy_digest == protocol.receipt.coordinate_policy_digest
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
    repeated = ingest_proteoform_raw_inputs(scenario.request, scenario.artifacts_by_role)
    canonical = (
        result.disposition is ProteoformRawInputDisposition.VALIDATED
        and len(result.validated_inputs) == M0403_ROLE_COUNT
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
            "exact_m0402_full_result_replay",
            canonical
            and result.lineage_result_digest == scenario.request.lineage_result.result_digest
            and result.receipt.lineage_receipt_digest
            == scenario.request.lineage_result.receipt.receipt_digest,
            "full embedded M04-02 result and receipt replayed",
        ),
        _check(
            "exact_m0401_transitive_protocol_bindings",
            exact_bindings,
            (f"bound_inputs={protocol_bound_count}/{M0403_ROLE_COUNT}"),
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
            result.parent_target == "protein_rna_discordance"
            and result.receipt.parent_target == "protein_rna_discordance"
            and not result.emits_protein_rna_discordance
            and not result.receipt.emits_parent,
            "parent context retained; emission flags false",
        ),
    ]


class _BytesSubclass(bytes):
    pass


def _input_error_check(
    case_id: str,
    scenario: Scenario,
    supplied: object,
    expected: ProteoformRawInputErrorCode,
) -> EvalCheck:
    try:
        ingest_proteoform_raw_inputs(scenario.request, supplied)
    except ProteoformRawInputError as error:
        return _check(
            case_id,
            error.code is expected,
            f"ingress_rejected:{error.code.value}",
        )
    return _check(case_id, CHECK_FAILED, "input unexpectedly accepted")


def _mapping_cap_checks() -> list[EvalCheck]:
    base = build_scenario()
    role = ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME
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
        {role: {"declared_record_count": M0403_MAX_DECLARED_RECORD_COUNT}},
    )
    largest_result = ingest_proteoform_raw_inputs(
        largest.request,
        largest.artifacts_by_role,
    )
    max_declared = _with_artifact_updates(
        base,
        {
            item.role: {"declared_size_bytes": M0403_MAX_DOCUMENT_BYTES}
            for item in base.request.artifacts
        },
    )
    per_excess = dict(max_declared.artifacts_by_role)
    per_excess[role] = b" " * (M0403_MAX_DOCUMENT_BYTES + 1)
    aggregate_excess = {
        item.role: b" " * M0403_MAX_DOCUMENT_BYTES for item in base.request.artifacts
    }
    aggregate_excess[role] += b" "
    return [
        _input_error_check(
            "missing_role_mapping_rejected",
            base,
            missing,
            ProteoformRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH,
        ),
        _input_error_check(
            "extra_role_mapping_rejected",
            base,
            extra,
            ProteoformRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH,
        ),
        _input_error_check(
            "bytearray_rejected",
            base,
            bytearray_mapping,
            ProteoformRawInputErrorCode.ARTIFACT_TYPE_INVALID,
        ),
        _input_error_check(
            "bytes_subclass_rejected",
            base,
            subclass_mapping,
            ProteoformRawInputErrorCode.ARTIFACT_TYPE_INVALID,
        ),
        _input_error_check(
            "declared_size_mismatch_rejected",
            declared_scenario,
            declared_scenario.artifacts_by_role,
            ProteoformRawInputErrorCode.ARTIFACT_SIZE_MISMATCH,
        ),
        _input_error_check(
            "manifest_digest_mismatch_rejected",
            base,
            corrupt,
            ProteoformRawInputErrorCode.ARTIFACT_DIGEST_MISMATCH,
        ),
        _check(
            "largest_constructible_document_accepted",
            largest_result.disposition is ProteoformRawInputDisposition.VALIDATED
            and next(
                item.document.declared_record_count
                for item in largest_result.validated_inputs
                if item.role is role
            )
            == M0403_MAX_DECLARED_RECORD_COUNT,
            f"declared_record_count={M0403_MAX_DECLARED_RECORD_COUNT}",
        ),
        _input_error_check(
            "per_document_8mib_plus_one_rejected",
            max_declared,
            per_excess,
            ProteoformRawInputErrorCode.ARTIFACT_SIZE_MISMATCH,
        ),
        _input_error_check(
            "aggregate_32mib_plus_one_rejected",
            max_declared,
            aggregate_excess,
            ProteoformRawInputErrorCode.ARTIFACT_SIZE_MISMATCH,
        ),
    ]


def _semantic_result(
    updates: dict[ProteoformRawInputRole, dict[str, object]],
    *,
    artifact_updates: dict[ProteoformRawInputRole, dict[str, object]] | None = None,
) -> ProteoformRawInputValidationResult:
    scenario = _with_document_updates(
        build_scenario(),
        updates,
        artifact_updates=artifact_updates,
    )
    return ingest_proteoform_raw_inputs(scenario.request, scenario.artifacts_by_role)


def _code_check(
    case_id: str,
    result: ProteoformRawInputValidationResult,
    code: ProteoformRawDiagnosticCode,
    disposition: ProteoformRawInputDisposition,
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
    proteome = _semantic_result(
        {
            ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME: {
                "protein_unit": next(
                    item
                    for item in type(schema.quantification.protein_unit)
                    if item is not schema.quantification.protein_unit
                )
            }
        }
    )
    transcript = _semantic_result(
        {
            ProteoformRawInputRole.TRANSCRIPTOME: {
                "transcript_unit": next(
                    item
                    for item in type(schema.quantification.transcript_unit)
                    if item is not schema.quantification.transcript_unit
                )
            }
        }
    )
    stale = sha256_digest({"m0403": "stale"})
    reference = _semantic_result(
        {ProteoformRawInputRole.GENOME: {"genome_reference_digest": stale}}
    )
    alternate_convention = next(
        item
        for item in type(schema.coordinate_policy.genome_convention)
        if item is not schema.coordinate_policy.genome_convention
    )
    coordinate = _semantic_result(
        {ProteoformRawInputRole.GENOME: {"genome_convention": alternate_convention}}
    )
    assay = _semantic_result({ProteoformRawInputRole.GENOME: {"assay_protocol_version": "9.0.0"}})
    specimen = _semantic_result(
        {ProteoformRawInputRole.GENOME: {"specimen_processing_version": "9.0.0"}}
    )
    role = ProteoformRawInputRole.GENOME
    unsupported_scenario = _with_artifact_updates(
        base,
        {role: {"format_version": "9.0.0"}},
    )
    unsupported = ingest_proteoform_raw_inputs(
        unsupported_scenario.request,
        unsupported_scenario.artifacts_by_role,
    )
    swapped = dict(base.artifacts_by_role)
    swapped[role] = base.artifacts_by_role[ProteoformRawInputRole.TRANSCRIPTOME]
    mismatch_scenario = _rebind_payloads(base, swapped)
    role_rejection = _input_error_check(
        "role_document_type_mismatch_rejected",
        mismatch_scenario,
        swapped,
        ProteoformRawInputErrorCode.DOCUMENT_TYPE_MISMATCH,
    )
    return [
        _code_check(
            "proteome_unit_mismatch_quarantines",
            proteome,
            ProteoformRawDiagnosticCode.UNIT_MISMATCH,
            ProteoformRawInputDisposition.QUARANTINED,
        ),
        _code_check(
            "transcript_unit_mismatch_quarantines",
            transcript,
            ProteoformRawDiagnosticCode.UNIT_MISMATCH,
            ProteoformRawInputDisposition.QUARANTINED,
        ),
        _code_check(
            "reference_bundle_mismatch_quarantines",
            reference,
            ProteoformRawDiagnosticCode.REFERENCE_BUNDLE_MISMATCH,
            ProteoformRawInputDisposition.QUARANTINED,
        ),
        _code_check(
            "coordinate_policy_mismatch_quarantines",
            coordinate,
            ProteoformRawDiagnosticCode.COORDINATE_POLICY_MISMATCH,
            ProteoformRawInputDisposition.QUARANTINED,
        ),
        _code_check(
            "assay_protocol_mismatch_quarantines",
            assay,
            ProteoformRawDiagnosticCode.ASSAY_PROTOCOL_MISMATCH,
            ProteoformRawInputDisposition.QUARANTINED,
        ),
        _code_check(
            "specimen_processing_mismatch_quarantines",
            specimen,
            ProteoformRawDiagnosticCode.SPECIMEN_PROCESSING_MISMATCH,
            ProteoformRawInputDisposition.QUARANTINED,
        ),
        _code_check(
            "unsupported_format_version_quarantines",
            unsupported,
            ProteoformRawDiagnosticCode.UNSUPPORTED_FORMAT_VERSION,
            ProteoformRawInputDisposition.QUARANTINED,
        ),
        role_rejection,
    ]


def _completeness_checks() -> list[EvalCheck]:
    incomplete_results = {
        role: _semantic_result(
            {role: {"completeness_state": ProteoformRawCompletenessState.INCOMPLETE}}
        )
        for role in ProteoformRawInputRole
    }
    assay = _semantic_result(
        {
            ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME: {
                "assay_support_state": ProteoformRawAssaySupportState.UNSUPPORTED
            }
        }
    )
    quality = _semantic_result(
        {
            ProteoformRawInputRole.GENOME: {
                "parent_quality_state": ProteoformRawParentQualityState.REJECTED
            }
        }
    )
    abstained = _semantic_result(
        {
            ProteoformRawInputRole.TRANSCRIPTOME: {
                "evidence_state": ProteoformRawEvidenceState.INDETERMINATE
            }
        }
    )
    precedence = _semantic_result(
        {
            ProteoformRawInputRole.PTM_ANNOTATIONS: {
                "evidence_state": ProteoformRawEvidenceState.MISSING,
                "completeness_state": ProteoformRawCompletenessState.INCOMPLETE,
            }
        }
    )
    names = {
        ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME: "proteome_incomplete_quarantines",
        ProteoformRawInputRole.GENOME: "genome_incomplete_quarantines",
        ProteoformRawInputRole.TRANSCRIPTOME: "transcriptome_incomplete_quarantines",
        ProteoformRawInputRole.PTM_ANNOTATIONS: "ptm_annotations_incomplete_quarantines",
    }
    checks = [
        _code_check(
            names[role],
            result,
            ProteoformRawDiagnosticCode.INCOMPLETE_MANIFEST,
            ProteoformRawInputDisposition.QUARANTINED,
        )
        for role, result in incomplete_results.items()
    ]
    checks.extend(
        [
            _code_check(
                "assay_unsupported_quarantines",
                assay,
                ProteoformRawDiagnosticCode.ASSAY_UNSUPPORTED,
                ProteoformRawInputDisposition.QUARANTINED,
            ),
            _code_check(
                "parent_quality_rejected_quarantines",
                quality,
                ProteoformRawDiagnosticCode.PARENT_QUALITY_UNACCEPTABLE,
                ProteoformRawInputDisposition.QUARANTINED,
            ),
            _code_check(
                "artifact_not_evaluable_abstains",
                abstained,
                ProteoformRawDiagnosticCode.ARTIFACT_NOT_EVALUABLE,
                ProteoformRawInputDisposition.ABSTAINED,
            ),
            _check(
                "quarantine_precedes_abstention",
                precedence.disposition is ProteoformRawInputDisposition.QUARANTINED
                and {
                    ProteoformRawDiagnosticCode.ARTIFACT_NOT_EVALUABLE,
                    ProteoformRawDiagnosticCode.INCOMPLETE_MANIFEST,
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
    canonical_result = ingest_proteoform_raw_inputs(
        canonical.request,
        canonical.artifacts_by_role,
    )
    quarantined = _genuine_scenario("valid_quarantined_m0401_quarantines")
    _TraversalTrap.touched = 0
    quarantined_result = ingest_proteoform_raw_inputs(quarantined.request, _TraversalTrap())
    quarantined_touches = _TraversalTrap.touched
    abstained = _genuine_scenario("valid_unresolved_identity_abstains")
    _TraversalTrap.touched = 0
    abstained_result = ingest_proteoform_raw_inputs(abstained.request, _TraversalTrap())
    abstained_touches = _TraversalTrap.touched
    stale = sha256_digest({"m0403": "stale-binding"})

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
        lineage["result_digest"] = m0402_result_payload_digest(lineage)

    return [
        _check(
            "reconciled_upstream_permits_artifact_traversal",
            canonical_result.disposition is ProteoformRawInputDisposition.VALIDATED
            and len(canonical_result.validated_inputs) == M0403_ROLE_COUNT,
            "reconciled upstream permits exact four-role traversal",
        ),
        _check(
            "quarantined_upstream_zero_artifact_traversal",
            quarantined_result.disposition is ProteoformRawInputDisposition.QUARANTINED
            and _codes(quarantined_result)
            == {ProteoformRawDiagnosticCode.UPSTREAM_LINEAGE_QUARANTINED}
            and quarantined_touches == 0,
            f"disposition={quarantined_result.disposition.value};traversals={quarantined_touches}",
        ),
        _check(
            "abstained_upstream_zero_artifact_traversal",
            abstained_result.disposition is ProteoformRawInputDisposition.ABSTAINED
            and _codes(abstained_result) == {ProteoformRawDiagnosticCode.UPSTREAM_LINEAGE_ABSTAINED}
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
            "resigned_m0402_full_result_forgery_rejected",
            resigned_lineage,
        ),
    ]


def _duplicate_scenario() -> Scenario:
    base = build_scenario()
    source_role = ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME
    target_role = ProteoformRawInputRole.GENOME
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
    for code in ProteoformRawDiagnosticCode:
        expected_action = (
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
            code=code,
            action=expected_action,
            evidence_basis_digest=sha256_digest({"m0403_code": code}),
        )
        wrong_action = (
            ProteoformRawDiagnosticAction.RECORD
            if expected_action is not ProteoformRawDiagnosticAction.RECORD
            else ProteoformRawDiagnosticAction.QUARANTINE
        )
        try:
            ProteoformRawParseDiagnostic(
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
    stale = sha256_digest({"m0403": "maximum-discrepancy"})
    document_updates = {
        role: {
            "content_reference": _reference(
                f"mismatch-{role.value}",
                media_type=ROLE_CONTENT_MEDIA_TYPES[role],
            ),
            "identity_resolution_digest": stale,
            "protocol_result_digest": stale,
            "reference_bundle_digest": stale,
            "coordinate_policy_digest": stale,
            "intended_use_evidence_digest": stale,
            "assay_protocol_version": "9.0.0",
            "specimen_processing_version": "9.0.0",
            "unit_definition_version": "9.0.0",
            "evidence_state": ProteoformRawEvidenceState.MISSING,
            "completeness_state": ProteoformRawCompletenessState.INCOMPLETE,
            "assay_support_state": ProteoformRawAssaySupportState.UNSUPPORTED,
            "parent_quality_state": ProteoformRawParentQualityState.REJECTED,
        }
        for role in ProteoformRawInputRole
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
    multi = ingest_proteoform_raw_inputs(
        maximum_discrepancy.request,
        maximum_discrepancy.artifacts_by_role,
    )
    diagnostics_canonical = (
        tuple(multi.diagnostics) == tuple(sorted(multi.diagnostics, key=canonical_json_bytes))
        and len({(item.code, item.role) for item in multi.diagnostics}) == len(multi.diagnostics)
        and len(multi.diagnostics) <= M0403_MAX_DIAGNOSTICS
        and multi.disposition is ProteoformRawInputDisposition.QUARANTINED
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
    duplicate = ingest_proteoform_raw_inputs(
        duplicate_scenario.request,
        duplicate_scenario.artifacts_by_role,
    )
    incomplete = _semantic_result(
        {
            ProteoformRawInputRole.GENOME: {
                "completeness_state": ProteoformRawCompletenessState.INCOMPLETE
            }
        }
    )
    abstained = _semantic_result(
        {ProteoformRawInputRole.GENOME: {"evidence_state": ProteoformRawEvidenceState.REDACTED}}
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
            and len(tuple(ProteoformRawDiagnosticCode)) == M0403_DIAGNOSTIC_CODE_COUNT,
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
            duplicate.disposition is ProteoformRawInputDisposition.VALIDATED
            and _codes(duplicate) == {ProteoformRawDiagnosticCode.DUPLICATE_CONTENT_RETAINED}
            and len(duplicate.validated_inputs) == M0403_ROLE_COUNT,
            f"inputs={len(duplicate.validated_inputs)};diagnostics={len(duplicate.diagnostics)}",
        ),
        _check(
            "quarantine_preserves_validated_documents",
            incomplete.disposition is ProteoformRawInputDisposition.QUARANTINED
            and len(incomplete.validated_inputs) == M0403_ROLE_COUNT,
            f"disposition={incomplete.disposition.value};inputs={len(incomplete.validated_inputs)}",
        ),
        _check(
            "abstention_never_infers_negative",
            abstained.disposition is ProteoformRawInputDisposition.ABSTAINED
            and not abstained.infers_protein
            and not abstained.infers_proteoform
            and not abstained.emits_protein_rna_discordance,
            "typed abstention with all biological authority false",
        ),
        _check(
            "exact_compact_receipt_projection",
            canonical.receipt == receipt,
            f"receipt_digest={canonical.receipt.receipt_digest}",
        ),
    ]


def _maximum_policy() -> ProteoformRawInputPolicy:
    base = _policy()
    parsers: list[ApprovedProteoformRawParser] = list(base.approved_parsers)
    for index in range(M0403_MAX_APPROVED_PARSERS - len(parsers)):
        seed = base.approved_parsers[index % len(base.approved_parsers)]
        parsers.append(
            seed.model_copy(
                update={
                    "parser_version": f"1.{index + 1}.0",
                    "evidence": _parser_evidence(seed.role).model_copy(
                        update={
                            "artifact_id": _oid("evidence", f"max-parser-{index}"),
                            "digest": sha256_digest({"m0403_max_parser": index}),
                        }
                    ),
                }
            )
        )
    return ProteoformRawInputPolicy(
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


def _authority_exact(result: ProteoformRawInputValidationResult) -> bool:
    fields = {
        "emits_protein_rna_discordance",
        "emits_proteogenomic_state",
        "emits_proteotype",
        "emits_protein_level_subtype",
        "infers_identity",
        "infers_consent",
        "infers_protein",
        "infers_proteoform",
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
    maximum = ingest_proteoform_raw_inputs(
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
    canary_role = ProteoformRawInputRole.GENOME
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
    canary_result = ingest_proteoform_raw_inputs(
        canary_scenario.request,
        canary_scenario.artifacts_by_role,
    )
    canary_rendered = canonical_json_bytes(canary_result)
    return [
        _check(
            "minimum_20_evidence_entries",
            len(minimum.evidence) == M0403_MIN_EVIDENCE,
            f"evidence={len(minimum.evidence)}",
        ),
        _check(
            "maximum_48_evidence_entries",
            len(maximum.evidence) == M0403_MAX_EVIDENCE
            and len(maximum.request.policy.approved_parsers) == M0403_MAX_APPROVED_PARSERS,
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
            and canary_reference.digest.encode() in canary_rendered,
            "external canary represented only by its opaque content digest",
        ),
        _check(
            "zero_model_event_persistence_authority",
            not minimum.executes_model and "event" not in keys and "event_store" not in keys,
            "model execution and event persistence authority absent",
        ),
        _check(
            "exact_three_limitations_and_all_authority_flags_false",
            len(minimum.limitations) == M0403_LIMITATION_COUNT and _authority_exact(minimum),
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
        preflight_proteoform_raw_input_authorization(payload)
    except ProteoformRawInputAuthorizationError:
        return _check(
            case_id,
            _TraversalTrap.touched == 0,
            f"authorization_rejected;governed_traversals={_TraversalTrap.touched}",
        )
    return _check(case_id, CHECK_FAILED, "authorization unexpectedly accepted")


def _firewall_check() -> EvalCheck:
    canonical = build_scenario()
    expected = ingest_proteoform_raw_inputs(
        canonical.request,
        canonical.artifacts_by_role,
    )

    def hostile(value: object) -> object:
        if isinstance(value, dict):
            return _HostileDict({key: hostile(item) for key, item in value.items()})
        if isinstance(value, list):
            return [hostile(item) for item in value]
        return value

    candidate = hostile(canonical.request.model_dump(mode="python", exclude_none=False))
    actual = ingest_proteoform_raw_inputs(candidate, canonical.artifacts_by_role)
    exception_closed = False
    with patch.object(m0403_engine, "_member", side_effect=RuntimeError("ordinary")):
        try:
            preflight_proteoform_raw_input_authorization(canonical.request)
        except ProteoformRawInputAuthorizationError:
            exception_closed = True
    base_propagated = False
    with patch.object(m0403_engine, "_member", side_effect=_FirewallBaseException()):
        try:
            preflight_proteoform_raw_input_authorization(canonical.request)
        except _FirewallBaseException:
            base_propagated = True
    return _check(
        "dict_subclass_exception_baseexception_firewall",
        actual == expected and exception_closed and base_propagated,
        (
            f"hostile_dict_equality={actual == expected};"
            f"exception_fail_closed={exception_closed};baseexception_propagated={base_propagated}"
        ),
    )


def _document_error(
    case_id: str,
    payload_mutator: Callable[[dict[str, Any]], None],
    expected: ProteoformRawInputErrorCode,
) -> EvalCheck:
    base = build_scenario()
    role = ProteoformRawInputRole.GENOME
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
            ProteoformRawInputRole.GENOME: {
                "completeness_state": ProteoformRawCompletenessState.INCOMPLETE
            }
        }
    )
    stale = sha256_digest({"m0403": "resigned-derived-region"})

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
    canonical_result = ingest_proteoform_raw_inputs(
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
    reordered_result = ingest_proteoform_raw_inputs(
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
        ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME: ("mass-spectrometry-proteome.json"),
        ProteoformRawInputRole.GENOME: "genome.json",
        ProteoformRawInputRole.TRANSCRIPTOME: "transcriptome.json",
        ProteoformRawInputRole.PTM_ANNOTATIONS: "ptm-annotations.json",
    }
    refusals: list[bool] = []
    with TemporaryDirectory(prefix="m0403-eval-cli-") as temporary:
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
                "proteoform-raw",
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
                "proteoform-raw",
                "ingest",
                str(request_path),
                str(source),
                "--output",
                str(output),
            ],
        )
        refusals.append(unexpected.exit_code != 0 and not output.exists())
        extra.unlink()
        target = source / filenames[ProteoformRawInputRole.GENOME]
        original = target.read_bytes()
        target.unlink()
        target.mkdir()
        nonregular = CliRunner().invoke(
            cli_app,
            [
                "proteoform-raw",
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
                    "proteoform-raw",
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
                    "proteoform-raw",
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
        preflight_proteoform_raw_input_authorization(_ArbitraryMapping())
    except ProteoformRawInputAuthorizationError:
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
    role = ProteoformRawInputRole.GENOME
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
            ProteoformRawInputErrorCode.DOCUMENT_JSON_INVALID,
        )
    )
    checks.extend(
        [
            _document_error(
                "unknown_field_rejected",
                lambda payload: payload.__setitem__("unknown_field", "unexpected"),
                ProteoformRawInputErrorCode.DOCUMENT_JSON_INVALID,
            ),
            _document_error(
                "coercion_rejected",
                lambda payload: payload.__setitem__("declared_record_count", "1"),
                ProteoformRawInputErrorCode.DOCUMENT_JSON_INVALID,
            ),
        ]
    )
    oversized = b"{}" + (b" " * (M0403_MAX_CANONICAL_REQUEST_BYTES - 1))
    try:
        M0403Plugin(M0403Service()).validate(M0403Submission(oversized, {}))
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
        lineage["result_digest"] = sha256_digest({"m0403": "forged-upstream"})

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


def _corpus() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(SCENARIO_PATH.read_text(encoding="utf-8")))


def _inventory() -> tuple[list[str], tuple[int, ...], list[EvalCheck]]:
    corpus = _corpus()
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

    declared, _allocation, checks = _inventory()
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
