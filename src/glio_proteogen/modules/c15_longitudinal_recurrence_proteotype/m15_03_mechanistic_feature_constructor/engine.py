"""Deterministic, replay-bound M15-03 mechanistic feature construction."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_03 import (
    M1503_CONTRACT_VERSION,
    M1503_PARENT,
    ComplexActivityMechanisticFeatureResult,
    ConstructComplexActivityMechanisticFeaturesRequest,
    FeatureConstructorStatus,
    FeatureFinding,
    FeatureFindingCode,
    FeatureSupportStatus,
    MechanisticFeatureObject,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m15_03.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ConstructComplexActivityMechanisticFeaturesRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityMechanisticFeatureResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SUPPORTED_METHODS: Final = frozenset(
    {
        "curated_rule",
        "enrichment",
        "mechanistic_baseline",
        "orthogonal_consensus",
        "bayesian_graph",
        "state_space",
        "mechanistic_model",
        "foundation_assisted",
    }
)
_ALLOWED_UNITS: Final = frozenset(
    {
        "dimensionless",
        "fraction",
        "activity",
        "abundance",
        "rate",
        "score",
        "state_probability",
        "spatial_index",
        "timepoint",
    }
)


class M1503AuthorizationError(PermissionError):
    """Caller controls do not authorize feature construction."""

    def __init__(self) -> None:
        super().__init__(
            "M15-03 requires accepted controls, resolved identity, and granted consent"
        )


class M1503ReplayVerificationError(ValueError):
    """A feature result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M15-03 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1503_authorization(candidate: object) -> None:
    """Check all seven controls before typed traversal of feature material."""

    try:
        context = _member(candidate, "context")
        refs = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {role: _state(_member(_member(refs, role), "state")) for role in expected}
    except Exception:  # noqa: BLE001
        raise M1503AuthorizationError from None
    if states != expected:
        raise M1503AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_m1503_authorization(candidate)
    return candidate


def _evidence(
    request: ConstructComplexActivityMechanisticFeaturesRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        request.longitudinal_recurrence_result,
        *request.source_artifacts,
        request.policy.configuration.model_reference,
        request.policy.configuration.units_reference,
        *(item.reference for item in request.policy.configuration.evidence),
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    ]
    for feature in request.candidate_features:
        artifacts.extend(feature.source_artifacts)
        artifacts.extend(item.reference for item in feature.evidence)
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared mechanistic feature evidence; issuer authority is not "
                "authenticated."
            ),
        )
        for artifact in tuple(unique.values())[:64]
    )


def _failure(
    request: ConstructComplexActivityMechanisticFeaturesRequest,
    *,
    code: FeatureFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[FeatureFinding, ...]:
    return (
        FeatureFinding(
            finding_id=f"finding.{request.request_id}",
            code=code,
            message=message,
            evidence=evidence,
        ),
    )


def _evaluate_features(
    request: ConstructComplexActivityMechanisticFeaturesRequest,
) -> tuple[bool, FeatureFindingCode | None, str | None]:
    method = request.policy.configuration.method
    if method not in _SUPPORTED_METHODS:
        return (
            False,
            FeatureFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
            "Feature construction method is outside the closed provisional support domain.",
        )
    if any(feature.unit not in _ALLOWED_UNITS for feature in request.candidate_features):
        return (
            False,
            FeatureFindingCode.UNIT_INVARIANT_FAILED,
            "Every mechanistic feature unit must be in the locked unit domain.",
        )
    if any(
        feature.support_status
        in {
            FeatureSupportStatus.CONFLICTED,
            FeatureSupportStatus.UNRESOLVED,
            FeatureSupportStatus.ABSTAINED,
        }
        for feature in request.candidate_features
    ):
        return (
            False,
            FeatureFindingCode.UPSTREAM_UNSUPPORTED,
            "Unresolved or abstained feature evidence requires safe abstention.",
        )
    if (
        request.policy.configuration.model_dump(mode="python").get("topology_invariants_required")
        is not True
    ):
        return (
            False,
            FeatureFindingCode.TOPOLOGY_INVARIANT_FAILED,
            "Topology invariant was not required.",
        )
    if (
        request.policy.configuration.model_dump(mode="python").get(
            "perturbation_invariants_required"
        )
        is not True
    ):
        return (
            False,
            FeatureFindingCode.PERTURBATION_INVARIANT_FAILED,
            "Perturbation invariant was not required.",
        )
    return True, None, None


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="caller_declared_features",
            statement=(
                "Feature values and source artifacts are caller-declared and not externally "
                "authenticated."
            ),
        ),
        Limitation(
            code="invariant_scope",
            statement=(
                "Unit, topology, and perturbation flags are deterministic gates, not "
                "biological validation."
            ),
        ),
        Limitation(
            code="prohibited_outputs",
            statement=(
                "No kinase activity, generic all-omics fusion, treatment recommendation, "
                "identity inference, or consent inference is emitted."
            ),
        ),
    ]
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement=(
                    "No mechanistic feature object is published outside the closed support domain."
                ),
            )
        )
    return tuple(values)


class M1503FeatureConstructorEngine:
    """Construct a deterministic feature object with replay and safe abstention."""

    __slots__ = ()

    def infer(self, request: object) -> ComplexActivityMechanisticFeatureResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: ConstructComplexActivityMechanisticFeaturesRequest
    ) -> ComplexActivityMechanisticFeatureResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        supported, failure_code, failure_message = _evaluate_features(request)
        findings = (
            ()
            if supported
            else _failure(
                request,
                code=failure_code or FeatureFindingCode.UPSTREAM_UNSUPPORTED,
                message=failure_message
                or "Mechanistic feature construction was not safely evaluable.",
                evidence=evidence,
            )
        )
        feature_object = (
            MechanisticFeatureObject(
                feature_object_id=f"feature-object.{request_hash.removeprefix('sha256:')}",
                version=request.policy.configuration.version,
                features=request.candidate_features,
                material_assumptions=(
                    "Caller-declared feature values are preserved without external content "
                    "traversal.",
                    "Topology and perturbation invariants are deterministic release gates.",
                ),
                locked_reference=request.policy.configuration.model_reference,
                evidence=evidence,
            )
            if supported
            else None
        )
        payload: dict[str, object] = {
            "output_type": "complex_activity_mechanistic_features",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1503_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": FeatureConstructorStatus.CONSTRUCTED
            if supported
            else FeatureConstructorStatus.ABSTAINED,
            "feature_object": feature_object,
            "findings": findings,
            "abstention_reason": None
            if supported
            else (failure_message or "Mechanistic feature construction was not safely evaluable."),
            "parent_target": M1503_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1503_features_constructed"
                if supported
                else "m1503_features_abstained",
                rationale=(
                    "Units, topology, perturbation, parent binding, and source evidence are closed."
                    if supported
                    else "The feature request is outside the safely constructed support domain."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = ComplexActivityMechanisticFeatureResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityMechanisticFeatureResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1503ReplayVerificationError from error
        try:
            validated = _RESULT_ADAPTER.validate_python(
                validated.model_dump(mode="python", warnings=False), strict=True
            )
        except Exception as error:
            raise M1503ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1503ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1503ReplayVerificationError
        return validated


def construct_complex_activity_mechanistic_features(
    request: object,
) -> ComplexActivityMechanisticFeatureResult:
    """Public provisional M15-03 operation."""

    return M1503FeatureConstructorEngine().infer(request)


__all__ = [
    "M1503AuthorizationError",
    "M1503FeatureConstructorEngine",
    "M1503ReplayVerificationError",
    "construct_complex_activity_mechanistic_features",
    "preflight_m1503_authorization",
]
