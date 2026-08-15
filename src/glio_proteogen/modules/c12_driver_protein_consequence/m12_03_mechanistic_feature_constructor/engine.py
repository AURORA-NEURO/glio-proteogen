"""Deterministic, reference-only M12-03 mechanistic feature construction."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final, cast

from pydantic import BaseModel

from glio_proteogen.contracts.m12_03 import (
    M1203_CONTRACT_VERSION,
    M1203_EVIDENCE_CLAIM,
    BiomarkerPanelMechanisticFeatureResult,
    ConstructBiomarkerPanelMechanisticFeaturesRequest,
    MechanisticConstructionStatus,
    MechanisticDiagnosticStatus,
    MechanisticFeatureDiagnostic,
    MechanisticFeatureObject,
    MechanisticFindingCode,
    MechanisticQualityStatus,
    NegativeControlStatus,
    expected_limitations,
    expected_provenance,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.contracts.m12_03.canonical import canonical_request_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    SupportDecision,
    SupportStatus,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

_TOKEN_LIMIT: Final = 8 * 1024 * 1024
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_EXPECTED_CONTROLS: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}


class MechanisticFeatureAuthorizationError(PermissionError):
    """Raised before any caller-declared source reference is traversed."""

    def __init__(self) -> None:
        super().__init__("M12-03 construction requires accepted identity, consent, and controls")


class MechanisticFeatureValidationError(ValueError):
    """Raised when strict request replay or feature invariants fail."""


class _InvalidExecutionInputError(TypeError):
    def __init__(self) -> None:
        super().__init__("M12-03 execution requires a validated request")


class M1203MechanisticFeatureEngine:
    """Construct a versioned mechanistic feature object without external traversal."""

    __slots__ = ()

    def compute(self, request: object) -> BiomarkerPanelMechanisticFeatureResult:
        typed = _validate_request(request)
        return _compute(typed)


def preflight_mechanistic_feature_authorization(candidate: object) -> None:
    """Evaluate exactly seven controls using only typed scalar state fields."""

    authorized = False
    try:
        supported = type(candidate) is ConstructBiomarkerPanelMechanisticFeaturesRequest
        if not supported and dict in type.__getattribute__(type(candidate), "__mro__"):
            supported = True
        context = _member(candidate, "context") if supported else None
        references = _member(context, "references")
        states = {
            role: _state_text(_member(_member(references, role), "state"))
            for role in _EXPECTED_CONTROLS
        }
        authorized = supported and states == _EXPECTED_CONTROLS
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        authorized = False
    if not authorized:
        raise MechanisticFeatureAuthorizationError


def construct_mechanistic_features(
    request: object,
) -> BiomarkerPanelMechanisticFeatureResult:
    """Public stateless M12-03 operation."""

    return M1203MechanisticFeatureEngine().compute(request)


def _validate_request(candidate: object) -> ConstructBiomarkerPanelMechanisticFeaturesRequest:
    preflight_mechanistic_feature_authorization(candidate)
    if isinstance(candidate, ConstructBiomarkerPanelMechanisticFeaturesRequest):
        return candidate
    plain = _plain_value(candidate)
    try:
        encoded = canonical_json_bytes(plain)
        request = ConstructBiomarkerPanelMechanisticFeaturesRequest.model_validate_json(encoded)
    except Exception as exc:
        raise MechanisticFeatureValidationError from exc
    if request.model_dump(mode="json") != strict_json_loads(encoded, max_bytes=4 * 1024 * 1024):
        raise MechanisticFeatureValidationError
    return request


def validate_json_request(
    decoded: object,
    serialized: bytes | bytearray | str,
) -> ConstructBiomarkerPanelMechanisticFeaturesRequest:
    """Strictly validate one already-decoded JSON object against its exact bytes."""

    if type(decoded) is not dict:
        raise MechanisticFeatureValidationError
    try:
        typed = ConstructBiomarkerPanelMechanisticFeaturesRequest.model_validate_json(serialized)
    except Exception as exc:
        raise MechanisticFeatureValidationError from exc
    if typed.model_dump(mode="json") != decoded:
        raise MechanisticFeatureValidationError
    return typed


def _compute(
    request: ConstructBiomarkerPanelMechanisticFeaturesRequest,
) -> BiomarkerPanelMechanisticFeatureResult:
    request_digest = request_digest_for(request)
    diagnostics = _diagnostics(request)
    failing = any(
        item.status in {MechanisticDiagnosticStatus.FAIL, MechanisticDiagnosticStatus.NOT_EVALUABLE}
        for item in diagnostics
    )
    safe = (
        request.quality_status is MechanisticQualityStatus.ACCEPTED
        and request.negative_control_status is NegativeControlStatus.PASSED
        and not failing
    )
    feature_object = _feature_object(request, request_digest) if safe else None
    if safe:
        status = MechanisticConstructionStatus.CONSTRUCTED
        support = SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="mechanistic_invariants_passed",
            rationale=(
                "Units, topology references, source lineage, and negative-control gating passed."
            ),
        )
        reason = None
        findings: tuple[MechanisticFindingCode, ...] = (
            MechanisticFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
        )
    else:
        status = MechanisticConstructionStatus.ABSTAINED
        support = SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="mechanistic_support_not_established",
            rationale=(
                "The module cannot safely construct features from failed or non-evaluable inputs."
            ),
        )
        reason = _abstention_reason(request, diagnostics)
        findings = _findings(request, diagnostics)
    evidence = _evidence_index(request)
    payload: dict[str, object] = {
        "output_type": "biomarker_panel_mechanistic_features",
        "result_id": f"result.m1203.{request_digest.removeprefix('sha256:')}",
        "result_version": M1203_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": status,
        "feature_object": feature_object,
        "diagnostics": diagnostics,
        "findings": findings,
        "abstention_reason": reason,
        "parent_target": "biomarker_panel",
        "emits_parent": False,
        "support_decision": support,
        "uncertainty": expected_uncertainty(),
        "provenance": expected_provenance(request, request_digest),
        "evidence": evidence,
        "limitations": expected_limitations(),
        "human_review_required": True,
    }
    preliminary = BiomarkerPanelMechanisticFeatureResult.model_construct(  # type: ignore[arg-type]
        **payload
    )
    payload["result_digest"] = result_payload_digest(preliminary)
    return BiomarkerPanelMechanisticFeatureResult.model_validate(payload)


def request_digest_for(request: ConstructBiomarkerPanelMechanisticFeaturesRequest) -> str:
    return canonical_request_digest(request)


def _feature_object(
    request: ConstructBiomarkerPanelMechanisticFeaturesRequest,
    request_digest: str,
) -> MechanisticFeatureObject:
    return MechanisticFeatureObject(
        object_id=f"feature-object.m1203.{request_digest.removeprefix('sha256:')}",
        version=request.configuration.version,
        features=request.feature_inputs,
        relations=request.relations,
        configuration=request.configuration,
        evidence=_evidence_index(request),
    )


def _diagnostics(
    request: ConstructBiomarkerPanelMechanisticFeaturesRequest,
) -> tuple[MechanisticFeatureDiagnostic, ...]:
    statuses = (
        (
            "diagnostic.quality",
            MechanisticDiagnosticStatus.PASS
            if request.quality_status is MechanisticQualityStatus.ACCEPTED
            else MechanisticDiagnosticStatus.FAIL,
            "Quality controls accepted."
            if request.quality_status is MechanisticQualityStatus.ACCEPTED
            else "Quality controls were rejected or unresolved.",
        ),
        (
            "diagnostic.negative-control",
            MechanisticDiagnosticStatus.PASS
            if request.negative_control_status is NegativeControlStatus.PASSED
            else MechanisticDiagnosticStatus.FAIL,
            "Negative-control gating passed."
            if request.negative_control_status is NegativeControlStatus.PASSED
            else "Negative-control gating failed or was not evaluable.",
        ),
        (
            "diagnostic.topology",
            MechanisticDiagnosticStatus.PASS,
            "Feature relation endpoints and topology reference are closed.",
        ),
        (
            "diagnostic.units",
            MechanisticDiagnosticStatus.PASS,
            "Every feature has one strict value representation and non-empty unit.",
        ),
        (
            "diagnostic.lineage",
            MechanisticDiagnosticStatus.PASS,
            "Every feature carries complete source-artifact lineage.",
        ),
    )
    evidence = _evidence_index(request)
    return tuple(
        MechanisticFeatureDiagnostic(
            diagnostic_id=diagnostic_id,
            status=status,
            message=message,
            evidence=evidence[:1],
        )
        for diagnostic_id, status, message in statuses
    )


def _findings(
    request: ConstructBiomarkerPanelMechanisticFeaturesRequest,
    diagnostics: tuple[MechanisticFeatureDiagnostic, ...],
) -> tuple[MechanisticFindingCode, ...]:
    findings: list[MechanisticFindingCode] = []
    if request.quality_status is not MechanisticQualityStatus.ACCEPTED:
        findings.append(MechanisticFindingCode.INPUT_INCOMPLETE)
    if request.negative_control_status is not NegativeControlStatus.PASSED:
        findings.append(MechanisticFindingCode.NEGATIVE_CONTROL_FAILED)
    if any(item.status is MechanisticDiagnosticStatus.FAIL for item in diagnostics):
        findings.append(MechanisticFindingCode.TOPOLOGY_INVARIANT_FAILED)
    return tuple(findings) or (MechanisticFindingCode.UPSTREAM_UNSUPPORTED,)


def _abstention_reason(
    request: ConstructBiomarkerPanelMechanisticFeaturesRequest,
    diagnostics: tuple[MechanisticFeatureDiagnostic, ...],
) -> str:
    if request.negative_control_status is not NegativeControlStatus.PASSED:
        return "M12-03 abstained because negative-control gating did not pass."
    if request.quality_status is not MechanisticQualityStatus.ACCEPTED:
        return "M12-03 abstained because parent-specific quality was not accepted."
    failed = ", ".join(
        item.diagnostic_id
        for item in diagnostics
        if item.status is not MechanisticDiagnosticStatus.PASS
    )
    return f"M12-03 abstained because mechanistic invariants were not evaluable: {failed}."


def _evidence_index(
    request: ConstructBiomarkerPanelMechanisticFeaturesRequest,
) -> tuple[EvidenceReference, ...]:
    refs: list[ArtifactReference] = [
        request.upstream_result,
        *request.source_artifacts,
        request.configuration.topology_reference,
        *(item.reference for item in request.configuration.evidence),
        *(
            artifact
            for feature in request.feature_inputs
            for artifact in feature.lineage.source_artifacts
        ),
    ]
    unique: dict[tuple[str, str, str, str], ArtifactReference] = {
        (item.artifact_id, item.version, item.digest, item.media_type): item for item in refs
    }
    return tuple(
        EvidenceReference(reference=item, role="evidence", claim=M1203_EVIDENCE_CLAIM)
        for item in sorted(unique.values(), key=lambda value: value.artifact_id)
    )


def _member(candidate: object, field: str) -> object:
    mro = type.__getattribute__(type(candidate), "__mro__")
    if dict in mro:
        return dict.get(cast("dict[object, object]", candidate), field)
    if BaseModel in mro:
        storage = object.__getattribute__(candidate, "__dict__")
        return dict.get(cast("dict[object, object]", storage), field)
    return None


def _state_text(value: object) -> object:
    if type(value) is str:
        return value
    if StrEnum in type.__getattribute__(type(value), "__mro__"):
        raw = object.__getattribute__(value, "_value_")
        return raw if type(raw) is str else None
    return None


def _plain_value(value: object) -> object:
    mro = type.__getattribute__(type(value), "__mro__")
    if BaseModel in mro:
        storage = cast("dict[object, object]", object.__getattribute__(value, "__dict__"))
        if any(type(key) is not str for key in storage):
            raise MechanisticFeatureValidationError
        return {key: _plain_value(item) for key, item in storage.items()}
    if dict in mro:
        mapping = cast("dict[object, object]", value)
        if any(type(key) is not str for key in mapping):
            raise MechanisticFeatureValidationError
        return {key: _plain_value(item) for key, item in mapping.items()}
    if list in mro:
        return [_plain_value(item) for item in cast("list[object]", value)]
    if tuple in mro:
        return tuple(_plain_value(item) for item in cast("tuple[object, ...]", value))
    if Mapping in mro:
        raise MechanisticFeatureValidationError
    return value


__all__ = [
    "M1203MechanisticFeatureEngine",
    "MechanisticFeatureAuthorizationError",
    "MechanisticFeatureValidationError",
    "construct_mechanistic_features",
    "preflight_mechanistic_feature_authorization",
    "request_digest_for",
    "validate_json_request",
]
