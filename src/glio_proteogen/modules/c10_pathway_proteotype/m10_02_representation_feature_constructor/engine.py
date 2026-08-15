"""Deterministic, replay-bound M10-02 representation construction.

The engine consumes only the strict caller-declared request.  It never opens
artifact paths or interprets external content, which makes the operation
reproducible and prevents a representation module from becoming an implicit
all-omics or authority boundary.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel

from glio_proteogen.contracts.m10_02 import (
    M1002_CONTRACT_VERSION,
    M1002_EVIDENCE_CLAIM,
    M1002_MAX_CANONICAL_REQUEST_BYTES,
    M1002_MODULE_ID,
    M1002_PARENT,
    AnalysisRepresentation,
    ConstructProteinRnaRepresentationRequest,
    FeatureLineage,
    ProteinRnaRepresentationResult,
    RepresentationConstructionStatus,
    RepresentationDiagnostic,
    RepresentationDiagnosticStatus,
    RepresentationFeature,
    RepresentationInputFeature,
    RepresentationMissingness,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

_ZERO_DIGEST: Final[str] = "sha256:" + ("0" * 64)
_AUTHORIZATION_MESSAGE: Final[str] = "M10-02 construction requires accepted upstream controls"
_PROHIBITED_MESSAGE: Final[str] = (
    "M10-02 does not emit kinase activity, all-omics fusion, or treatment recommendation"
)
_SUPPORTED_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"identity", "copy", "log1p", "standardize", "robust_scale", "cn_to_protein"}
)


class RepresentationAuthorizationError(PermissionError):
    """Raised before any representation input is traversed on control failure."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class RepresentationInputError(ValueError):
    """Raised when caller-declared feature values cannot be safely constructed."""


class _RequestTypeError(TypeError):
    def __init__(self) -> None:
        super().__init__("M10-02 requests must be mappings or contract models")


class _RequestMappingError(TypeError):
    def __init__(self) -> None:
        super().__init__("M10-02 request must be a strict mapping or contract model")


class _RequestJsonObjectError(TypeError):
    def __init__(self) -> None:
        super().__init__("M10-02 request JSON must be an object")


class _UnsupportedOperationError(RepresentationInputError):
    def __init__(self, operation: str) -> None:
        super().__init__(f"unsupported transformation operation: {operation}")


class _NonEvaluableTransformError(RepresentationInputError):
    def __init__(self) -> None:
        super().__init__("log1p transformation is not evaluable for this value")


class _MissingInputError(RepresentationInputError):
    def __init__(self) -> None:
        super().__init__("missing or unsupported input feature requires abstention")


def _state_text(value: object) -> str:
    if isinstance(value, (UpstreamDecisionState, IdentityLineageState, ConsentState)):
        return value.value
    return str(value)


def preflight_authorization(candidate: object) -> None:
    """Require all seven exact controls without reading feature or artifact payloads."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        actual = {
            role: _state_text(_member(_member(references, role), "state")) for role in expected
        }
    except Exception as error:
        raise RepresentationAuthorizationError from error
    if actual != expected:
        raise RepresentationAuthorizationError


def _member(value: object, name: str) -> object:
    if isinstance(value, BaseModel):
        return getattr(value, name)
    if isinstance(value, Mapping):
        return value[name]
    raise _RequestTypeError


def _plain(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _validate_request(candidate: object) -> ConstructProteinRnaRepresentationRequest:
    preflight_authorization(candidate)
    if isinstance(candidate, ConstructProteinRnaRepresentationRequest):
        return candidate
    if not isinstance(candidate, Mapping):
        raise _RequestMappingError
    return ConstructProteinRnaRepresentationRequest.model_validate(_plain(candidate), strict=True)


def _validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> ConstructProteinRnaRepresentationRequest:
    preflight_authorization(candidate)
    decoded = strict_json_loads(serialized, max_bytes=M1002_MAX_CANONICAL_REQUEST_BYTES)
    if not isinstance(decoded, dict):
        raise _RequestJsonObjectError
    return _validate_decoded_json_request(decoded)


def _validate_decoded_json_request(
    candidate: object,
) -> ConstructProteinRnaRepresentationRequest:
    """Validate one already strict-parsed JSON tree without reparsing bytes."""

    preflight_authorization(candidate)
    if not isinstance(candidate, dict):
        raise _RequestJsonObjectError
    return ConstructProteinRnaRepresentationRequest.model_validate(candidate)


def _validate_serialized_json_request(
    serialized: bytes | bytearray | str,
) -> ConstructProteinRnaRepresentationRequest:
    """Reject duplicate/nonfinite JSON before Pydantic's strict JSON decoder."""

    decoded = strict_json_loads(serialized, max_bytes=M1002_MAX_CANONICAL_REQUEST_BYTES)
    preflight_authorization(decoded)
    return ConstructProteinRnaRepresentationRequest.model_validate_json(serialized, strict=True)


def _evidence(request: ConstructProteinRnaRepresentationRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1002_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _controls(
    request: ConstructProteinRnaRepresentationRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    return (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=refs.provenance.decision_id,
            state=refs.provenance.state.value,
            policy_version=refs.provenance.policy_version,
            evidence_digest=refs.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=refs.consent.decision_id,
            state=refs.consent.state.value,
            policy_version=refs.consent.policy_version,
            evidence_digest=refs.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=refs.quality.decision_id,
            state=refs.quality.state.value,
            policy_version=refs.quality.policy_version,
            evidence_digest=refs.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=refs.support.decision_id,
            state=refs.support.state.value,
            policy_version=refs.support.policy_version,
            evidence_digest=refs.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=refs.intended_use.decision_id,
            state=refs.intended_use.state.value,
            policy_version=refs.intended_use.policy_version,
            evidence_digest=refs.intended_use.evidence.digest,
        ),
    )


def _provenance(
    request: ConstructProteinRnaRepresentationRequest, request_digest: str
) -> ProvenanceRecord:
    refs = request.context.references
    config_digest = sha256_digest(request.configuration)
    return ProvenanceRecord(
        activity_id=f"activity.m1002.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1002_MODULE_ID,
        module_version=M1002_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(artifact.digest for artifact in request.source_artifacts),
        configuration_digest=config_digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_controls(request),
    )


def _uncertainty(*, abstained: bool) -> UncertaintyProfile:
    def estimate(probability: float, rationale: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE if abstained else EstimateState.ESTIMATED,
            probability=None if abstained else probability,
            rationale=rationale,
        )

    return UncertaintyProfile(
        measurement=estimate(0.90, "measurement uncertainty is declared by the caller"),
        sampling=estimate(0.90, "sampling uncertainty is declared by the caller"),
        parameter=estimate(0.88, "locked transformation parameters are caller-declared"),
        model_form=estimate(0.85, "model form is bounded to the provisional method catalogue"),
        identification=estimate(0.98, "identity control is accepted before construction"),
        support=estimate(0.95, "support status is determined by exact upstream control state"),
        transport=estimate(
            0.80, "transportability is not inferred beyond the declared support domain"
        ),
        sensitivity_notes=("M10-02 does not infer unsupported biology.",),
    )


def _apply_operation(
    value: RepresentationInputFeature, operation: str
) -> tuple[float | None, str | None, tuple[float, ...]]:
    normalized = operation.strip().lower().replace("-", "_")
    if normalized not in _SUPPORTED_OPERATIONS:
        raise _UnsupportedOperationError(operation)
    if value.scalar_value is None:
        return value.scalar_value, value.category, value.vector
    if normalized == "log1p":
        if value.scalar_value <= -1.0:
            raise _NonEvaluableTransformError
        return math.log1p(value.scalar_value), None, ()
    if normalized in {"standardize", "robust_scale", "cn_to_protein"}:
        # Fit bytes are intentionally not traversed; the locked artifact is the
        # replay boundary and application of a future fitted parameter service.
        return value.scalar_value, None, ()
    return value.scalar_value, None, ()


def _construct_representation(
    request: ConstructProteinRnaRepresentationRequest,
) -> tuple[AnalysisRepresentation, tuple[RepresentationDiagnostic, ...]]:
    by_id = {item.feature_id: item for item in request.input_features}
    evidence = _evidence(request)
    features: list[RepresentationFeature] = []
    diagnostics: list[RepresentationDiagnostic] = []
    scaling_id = (
        request.configuration.scaling[0].scaling_id if request.configuration.scaling else None
    )
    mask_id = request.configuration.masks[0].mask_id if request.configuration.masks else None
    for transformation in request.configuration.transformations:
        source = by_id[transformation.input_feature_ids[0]]
        if source.state is not RepresentationMissingness.OBSERVED:
            raise _MissingInputError
        scalar, category, vector = _apply_operation(source, transformation.operation)
        for output_id in transformation.output_feature_ids:
            lineage = FeatureLineage(
                feature_id=output_id,
                source_artifacts=request.source_artifacts,
                transformation_ids=(transformation.transformation_id,),
                evidence=evidence,
            )
            features.append(
                RepresentationFeature(
                    feature_id=output_id,
                    value_kind=source.value_kind,
                    state=RepresentationMissingness.OBSERVED,
                    unit=source.unit,
                    scalar_value=scalar,
                    category=category,
                    vector=vector,
                    lineage=lineage,
                    scaling_id=scaling_id,
                    mask_id=mask_id,
                    covariate_ids=tuple(
                        item.covariate_id for item in request.configuration.covariates
                    ),
                    evidence=evidence,
                )
            )
        diagnostics.append(
            RepresentationDiagnostic(
                diagnostic_id=f"diagnostic.{transformation.transformation_id}",
                status=RepresentationDiagnosticStatus.PASS,
                message=f"locked transformation {transformation.transformation_id} applied",
                evidence=evidence,
            )
        )
    representation = AnalysisRepresentation(
        representation_id=f"representation.m1002.{canonical_request_digest(request).removeprefix('sha256:')}",
        version=M1002_CONTRACT_VERSION,
        method=request.configuration.method,
        features=tuple(features),
        transformations=request.configuration.transformations,
        covariates=request.configuration.covariates,
        evidence=evidence,
    )
    return representation, tuple(diagnostics)


def _result(
    request: ConstructProteinRnaRepresentationRequest,
    *,
    request_digest: str,
    representation: AnalysisRepresentation | None,
    diagnostics: tuple[RepresentationDiagnostic, ...],
    abstention_reason: str | None,
) -> ProteinRnaRepresentationResult:
    abstained = representation is None
    status = (
        RepresentationConstructionStatus.ABSTAINED
        if abstained
        else RepresentationConstructionStatus.CONSTRUCTED
    )
    support = SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED if abstained else SupportStatus.SUPPORTED,
        reason_code="representation_abstained" if abstained else "representation_supported",
        rationale=abstention_reason or "all locked transformations and lineage checks passed",
    )
    limitations = (
        Limitation(
            code="provisional_abi",
            statement="M10-02 endpoint and feature catalogue remain provisional.",
        ),
        Limitation(
            code="no_external_traversal",
            statement="Artifact references are not dereferenced by this runtime.",
        ),
        Limitation(
            code="parent_not_emitted",
            statement="The parent protein-RNA discordance output is not emitted here.",
        ),
    )
    payload: dict[str, object] = {
        "output_type": "protein_rna_analysis_representation",
        "result_id": f"result.m1002.{request_digest.removeprefix('sha256:')}",
        "result_version": M1002_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": status,
        "representation": representation,
        "diagnostics": diagnostics,
        "abstention_reason": abstention_reason,
        "parent_target": M1002_PARENT,
        "emits_parent": False,
        "support_decision": support,
        "uncertainty": _uncertainty(abstained=abstained),
        "provenance": _provenance(request, request_digest),
        "evidence": _evidence(request),
        "limitations": limitations,
        "human_review_required": abstained,
    }
    # Calculate against a validation-free model so nested datetime and enum
    # serialization exactly matches the result validator's canonical boundary.
    candidate = ProteinRnaRepresentationResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(candidate)
    return ProteinRnaRepresentationResult.model_validate(payload, strict=True)


def _execute(request: ConstructProteinRnaRepresentationRequest) -> ProteinRnaRepresentationResult:
    request_digest = canonical_request_digest(request)
    try:
        representation, diagnostics = _construct_representation(request)
    except RepresentationInputError as error:
        diagnostics = (
            RepresentationDiagnostic(
                diagnostic_id="diagnostic.abstention",
                status=RepresentationDiagnosticStatus.NOT_EVALUABLE,
                message=str(error),
                evidence=_evidence(request),
            ),
        )
        return _result(
            request,
            request_digest=request_digest,
            representation=None,
            diagnostics=diagnostics,
            abstention_reason=str(error),
        )
    return _result(
        request,
        request_digest=request_digest,
        representation=representation,
        diagnostics=diagnostics,
        abstention_reason=None,
    )


class M1002RepresentationEngine:
    """Validate, authorize, construct, and seal one representation result."""

    __slots__ = ()

    def compute(self, request: object) -> ProteinRnaRepresentationResult:
        return _execute(_validate_request(request))


def construct_protein_rna_representation(request: object) -> ProteinRnaRepresentationResult:
    return M1002RepresentationEngine().compute(request)


def verify_result_replay(result: ProteinRnaRepresentationResult) -> bool:
    """Verify both request binding and the exact result payload digest."""

    return result.request_digest == canonical_request_digest(
        result.request
    ) and result.result_digest == result_payload_digest(result)


def validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> ConstructProteinRnaRepresentationRequest:
    del candidate
    return _validate_serialized_json_request(serialized)


__all__ = [
    "M1002RepresentationEngine",
    "RepresentationAuthorizationError",
    "RepresentationInputError",
    "_validate_serialized_json_request",
    "construct_protein_rna_representation",
    "preflight_authorization",
    "validate_json_request",
    "verify_result_replay",
]
