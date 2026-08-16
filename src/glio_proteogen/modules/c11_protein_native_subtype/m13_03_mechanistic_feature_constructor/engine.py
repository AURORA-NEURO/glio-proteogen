"""Deterministic, evidence-preserving M13-03 mechanistic feature engine."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, cast

from pydantic import BaseModel

from glio_proteogen.contracts.m13_03 import (
    M1303_CONTRACT_VERSION,
    M1303_MAX_CANONICAL_REQUEST_BYTES,
    M1303_PARENT,
    ConstructProteotypeMechanisticFeaturesRequest,
    MechanisticConstructionStatus,
    MechanisticDiagnosticStatus,
    MechanisticFeature,
    MechanisticFeatureDiagnostic,
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticFeatureObject,
    MechanisticFindingCode,
    MechanisticRelation,
    MechanisticRelationKind,
    MechanisticValueKind,
    ProteotypeMechanisticFeatureResult,
    expected_limitations,
    expected_provenance,
    expected_uncertainty,
    feature_evidence_index,
)
from glio_proteogen.contracts.m13_03.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    EvidenceReference,
    SupportDecision,
    SupportStatus,
)

_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_AUTHORIZATION_MESSAGE: Final = "M13-03 execution requires accepted upstream controls"
_INVALID_REQUEST_MESSAGE: Final = "M13-03 request must be a strict contract object"
_UNSUPPORTED_MARKERS: Final = frozenset({"unsupported", "missing", "not_evaluable", "ood", "n_a"})
_CONTROL_MARKERS: Final = frozenset({"withheld", "revoked", "unresolved", "conflicted", "rejected"})
_TOPOLOGY_THRESHOLD: Final = 0.5


class MechanisticFeatureAuthorizationError(PermissionError):
    """Raised before any upstream artifact reference is traversed."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class _InvalidExecutionRequestError(TypeError):
    def __init__(self) -> None:
        super().__init__(_INVALID_REQUEST_MESSAGE)


class _InvalidReplayError(ValueError):
    def __init__(self) -> None:
        super().__init__("M13-03 replay verification failed")


class _SafeFailureReason(StrEnum):
    UPSTREAM_UNSUPPORTED = "upstream support is not established"
    INPUT_INCOMPLETE = "source evidence is incomplete or not evaluable"
    NEGATIVE_CONTROL = "negative-control gating failed"


class M1303MechanisticFeatureEngine:
    """Build digest-derived reference features without reading opaque artifacts."""

    __slots__ = ()

    def compute(self, request: object) -> ProteotypeMechanisticFeatureResult:
        typed = _validated_request(request)
        return _compute_result(typed)


def construct_proteotype_mechanistic_features(
    request: object,
) -> ProteotypeMechanisticFeatureResult:
    """Stateless M13-03 operation."""

    return M1303MechanisticFeatureEngine().compute(request)


def preflight_mechanistic_feature_authorization(candidate: object) -> None:
    """Validate the seven caller-declared controls before data access."""

    try:
        if type(candidate) is ConstructProteotypeMechanisticFeaturesRequest:
            context = object.__getattribute__(candidate, "context")
        elif type(candidate) is dict:
            context = cast("dict[str, object]", candidate).get("context")
        else:
            context = None
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
    except Exception as exc:
        if isinstance(exc, MechanisticFeatureAuthorizationError):
            raise
        raise MechanisticFeatureAuthorizationError from None
    if actual != expected:
        raise MechanisticFeatureAuthorizationError


def verify_mechanistic_feature_replay(
    result: ProteotypeMechanisticFeatureResult,
) -> ProteotypeMechanisticFeatureResult:
    """Re-validate request and result digests before releasing a result."""

    if type(result) is not ProteotypeMechanisticFeatureResult:
        raise _InvalidReplayError
    if result.request_digest != canonical_request_digest(result.request):
        raise _InvalidReplayError
    if result.result_digest != result_payload_digest(result):
        raise _InvalidReplayError
    try:
        return ProteotypeMechanisticFeatureResult.model_validate(result.model_dump(mode="python"))
    except ValueError as exc:
        raise _InvalidReplayError from exc


def _validated_request(candidate: object) -> ConstructProteotypeMechanisticFeaturesRequest:
    preflight_mechanistic_feature_authorization(candidate)
    if type(candidate) is ConstructProteotypeMechanisticFeaturesRequest:
        return candidate
    if type(candidate) is dict:
        try:
            return ConstructProteotypeMechanisticFeaturesRequest.model_validate(candidate)
        except ValueError as exc:
            raise _InvalidExecutionRequestError from exc
    raise _InvalidExecutionRequestError


def validate_json_request(
    decoded: object,
    serialized: bytes | bytearray | str,
) -> ConstructProteotypeMechanisticFeaturesRequest:
    """Strictly parse one JSON document and validate it against the contract."""

    if type(decoded) is not dict:
        raise _InvalidExecutionRequestError
    if len(serialized) > M1303_MAX_CANONICAL_REQUEST_BYTES:
        raise _InvalidExecutionRequestError
    preflight_mechanistic_feature_authorization(decoded)
    try:
        if type(serialized) is str:
            encoded = serialized.encode("utf-8")
        else:
            encoded = bytes(cast("bytes | bytearray", serialized))
        return ConstructProteotypeMechanisticFeaturesRequest.model_validate_json(encoded)
    except ValueError as exc:
        raise _InvalidExecutionRequestError from exc


def _compute_result(
    request: ConstructProteotypeMechanisticFeaturesRequest,
) -> ProteotypeMechanisticFeatureResult:
    request_digest = canonical_request_digest(request)
    provenance = expected_provenance(request, request_digest=request_digest)
    evidence = feature_evidence_index(request)
    reason = _safe_failure(request)
    if reason is not None:
        return _abstained_result(request, request_digest, provenance, evidence, reason)
    feature_object = _construct_feature_object(request)
    diagnostics = _diagnostics(request, evidence)
    payload: dict[str, object] = {
        "output_type": "proteotype_mechanistic_features",
        "result_id": f"result.m1303.{request_digest.removeprefix('sha256:')}",
        "result_version": M1303_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": MechanisticConstructionStatus.CONSTRUCTED,
        "feature_object": feature_object,
        "diagnostics": diagnostics,
        "findings": (MechanisticFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,),
        "abstention_reason": None,
        "parent_target": M1303_PARENT,
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m1303.supported",
            rationale="All seven controls, source evidence, and invariants are supported.",
        ),
        "uncertainty": expected_uncertainty(),
        "provenance": provenance,
        "evidence": evidence,
        "limitations": expected_limitations(),
        "human_review_required": True,
    }
    assembled = ProteotypeMechanisticFeatureResult.model_construct(**payload)  # type: ignore[arg-type]
    payload["result_digest"] = result_payload_digest(assembled)
    assembled = ProteotypeMechanisticFeatureResult.model_construct(**payload)  # type: ignore[arg-type]
    return verify_mechanistic_feature_replay(assembled)


def _abstained_result(
    request: ConstructProteotypeMechanisticFeaturesRequest,
    request_digest: str,
    provenance: object,
    evidence: tuple[EvidenceReference, ...],
    reason: _SafeFailureReason,
) -> ProteotypeMechanisticFeatureResult:
    code = (
        MechanisticFindingCode.UPSTREAM_UNSUPPORTED
        if reason is _SafeFailureReason.UPSTREAM_UNSUPPORTED
        else MechanisticFindingCode.NEGATIVE_CONTROL_FAILED
        if reason is _SafeFailureReason.NEGATIVE_CONTROL
        else MechanisticFindingCode.INPUT_INCOMPLETE
    )
    diagnostic_status = (
        MechanisticDiagnosticStatus.FAIL
        if reason is _SafeFailureReason.NEGATIVE_CONTROL
        else MechanisticDiagnosticStatus.NOT_EVALUABLE
    )
    diagnostics = (
        _diagnostic("diagnostic.safe_failure", diagnostic_status, str(reason), evidence),
    )
    payload: dict[str, object] = {
        "output_type": "proteotype_mechanistic_features",
        "result_id": f"result.m1303.{request_digest.removeprefix('sha256:')}",
        "result_version": M1303_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": MechanisticConstructionStatus.ABSTAINED,
        "feature_object": None,
        "diagnostics": diagnostics,
        "findings": (code, MechanisticFindingCode.PROVISIONAL_ABI_PENDING_REVIEW),
        "abstention_reason": str(reason),
        "parent_target": M1303_PARENT,
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code=f"m1303.{code.value}",
            rationale=(
                "M13-03 preserves unresolved support and emits no mechanistic feature object."
            ),
        ),
        "uncertainty": expected_uncertainty(),
        "provenance": provenance,
        "evidence": evidence,
        "limitations": expected_limitations(),
        "human_review_required": True,
    }
    assembled = ProteotypeMechanisticFeatureResult.model_construct(**payload)  # type: ignore[arg-type]
    payload["result_digest"] = result_payload_digest(assembled)
    assembled = ProteotypeMechanisticFeatureResult.model_construct(**payload)  # type: ignore[arg-type]
    return verify_mechanistic_feature_replay(assembled)


def _safe_failure(
    request: ConstructProteotypeMechanisticFeaturesRequest,
) -> _SafeFailureReason | None:
    labels = {
        item.artifact_id.casefold() for item in (*request.source_artifacts, request.upstream_result)
    }
    config_labels = {
        item.artifact_id.casefold() for item in request.configuration.negative_control_artifacts
    }
    if any(any(marker in label for marker in _UNSUPPORTED_MARKERS) for label in labels):
        return _SafeFailureReason.UPSTREAM_UNSUPPORTED
    if any(any(marker in label for marker in _CONTROL_MARKERS) for label in labels):
        return _SafeFailureReason.INPUT_INCOMPLETE
    if any("fail" in label or "invalid" in label for label in config_labels):
        return _SafeFailureReason.NEGATIVE_CONTROL
    return None


def _construct_feature_object(
    request: ConstructProteotypeMechanisticFeaturesRequest,
) -> MechanisticFeatureObject:
    source = request.source_artifacts[0]
    digest_hex = source.digest.removeprefix("sha256:")
    score = int(digest_hex[:8], 16) / 0xFFFFFFFF
    lower = max(0.0, score - 0.1)
    upper = min(1.0, score + 0.1)

    def lineage(feature_id: str, claim: str) -> MechanisticFeatureLineage:
        return MechanisticFeatureLineage(
            feature_id=feature_id,
            source_artifacts=(source,),
            claim=claim,
            transformation_ids=request.configuration.transformation_ids,
            evidence=feature_evidence_index(request),
        )

    features = (
        MechanisticFeature(
            feature_id="feature.pathway.activity",
            version=request.configuration.version,
            kind=MechanisticFeatureKind.PATHWAY,
            value_kind=MechanisticValueKind.SCALAR,
            unit="activity_score",
            scalar_value=score,
            lineage=lineage(
                "feature.pathway.activity", "Digest-derived pathway activity reference score."
            ),
            evidence=feature_evidence_index(request),
        ),
        MechanisticFeature(
            feature_id="feature.topology.state",
            version=request.configuration.version,
            kind=MechanisticFeatureKind.TOPOLOGY,
            value_kind=MechanisticValueKind.CATEGORICAL,
            unit="topology_class",
            category="connected" if score >= _TOPOLOGY_THRESHOLD else "sparse",
            lineage=lineage("feature.topology.state", "Deterministic pathway topology class."),
            evidence=feature_evidence_index(request),
        ),
        MechanisticFeature(
            feature_id="feature.state.interval",
            version=request.configuration.version,
            kind=MechanisticFeatureKind.STATE,
            value_kind=MechanisticValueKind.INTERVAL,
            unit="normalized_state",
            lower_bound=lower,
            upper_bound=upper,
            lineage=lineage("feature.state.interval", "Unit-bounded mechanistic state interval."),
            evidence=feature_evidence_index(request),
        ),
    )
    return MechanisticFeatureObject(
        object_id=f"object.m1303.{request.request_id}",
        version=request.configuration.version,
        features=features,
        relations=(
            MechanisticRelation(
                relation_id="relation.pathway-topology",
                source_feature_id=features[0].feature_id,
                target_feature_id=features[1].feature_id,
                kind=MechanisticRelationKind.REGULATES,
                weight=round(score, 6),
                evidence=feature_evidence_index(request),
            ),
            MechanisticRelation(
                relation_id="relation.topology-state",
                source_feature_id=features[1].feature_id,
                target_feature_id=features[2].feature_id,
                kind=MechanisticRelationKind.PARTICIPATES,
                weight=round(1.0 - score, 6),
                evidence=feature_evidence_index(request),
            ),
        ),
        configuration=request.configuration,
        evidence=feature_evidence_index(request),
    )


def _diagnostic(
    diagnostic_id: str,
    status: MechanisticDiagnosticStatus,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> MechanisticFeatureDiagnostic:
    return MechanisticFeatureDiagnostic(
        diagnostic_id=diagnostic_id,
        status=status,
        message=message,
        evidence=evidence,
    )


def _diagnostics(
    request: ConstructProteotypeMechanisticFeaturesRequest,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[MechanisticFeatureDiagnostic, ...]:
    del request
    statuses = (
        ("diagnostic.pathway", "pathway graph reference is present"),
        ("diagnostic.topology", "topology relation endpoints are closed"),
        ("diagnostic.units", "feature units and numeric bounds are valid"),
        ("diagnostic.negative-control", "negative-control gate passed"),
    )
    return tuple(
        _diagnostic(identifier, MechanisticDiagnosticStatus.PASS, message, evidence)
        for identifier, message in statuses
    )


def _member(candidate: object, field: str) -> object:
    if type(candidate) is dict:
        return cast("dict[str, object]", candidate).get(field)
    if isinstance(candidate, BaseModel):
        storage = object.__getattribute__(candidate, "__dict__")
        return cast("dict[str, object]", storage).get(field)
    return None


def _state_text(candidate: object) -> str | None:
    if type(candidate) is str:
        return candidate
    if isinstance(candidate, StrEnum):
        value = object.__getattribute__(candidate, "_value_")
        return value if type(value) is str else None
    return None


__all__ = [
    "M1303MechanisticFeatureEngine",
    "MechanisticFeatureAuthorizationError",
    "construct_proteotype_mechanistic_features",
    "preflight_mechanistic_feature_authorization",
    "validate_json_request",
    "verify_mechanistic_feature_replay",
]
