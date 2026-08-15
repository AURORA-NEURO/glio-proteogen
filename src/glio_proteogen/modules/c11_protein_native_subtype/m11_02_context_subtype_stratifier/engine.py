"""Deterministic, support-gated M11-02 context and mechanism stratifier."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final, cast

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m11_02 import (
    M1102_CONTRACT_VERSION,
    M1102_EVIDENCE_CLAIM,
    M1102_PARENT,
    ContextDimension,
    ContextObservation,
    ContextProfile,
    ContextStratificationStatus,
    ContextStratifierDiagnostic,
    MechanismApplicability,
    MechanismApplicabilityStatus,
    StratifyVariantPeptideContextRequest,
    VariantPeptideContextStratificationResult,
    canonical_request_digest,
    expected_provenance,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER: Final = TypeAdapter(StratifyVariantPeptideContextRequest)
_RESULT_ADAPTER: Final = TypeAdapter(VariantPeptideContextStratificationResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_AUTHORIZED_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}


class M1102AuthorizationError(PermissionError):
    """Caller-owned controls are not authorized for context stratification."""

    def __init__(self) -> None:
        super().__init__(
            "M11-02 requires accepted controls, resolved identity, and granted consent"
        )


class M1102ReplayVerificationError(ValueError):
    """A context result cannot be reconstructed from its exact request."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"M11-02 replay verification failed: {detail}")


def _member(value: object, field: str) -> object:
    """Read only ordinary mappings/models; never traverse arbitrary accessors."""

    value_type = type(value)
    if isinstance(value, Mapping):
        return value.get(field)
    if isinstance(value, BaseModel):
        storage = object.__getattribute__(value, "__dict__")
        return cast("dict[str, object]", storage).get(field)
    if value_type is StrEnum:
        return None
    return None


def _state(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    return value


def preflight_context_authorization(candidate: object) -> None:
    """Check seven controls before reading policy, observations, or opaque artifacts."""

    try:
        supported = type(candidate) is StratifyVariantPeptideContextRequest or isinstance(
            candidate, Mapping
        )
        context = _member(candidate, "context") if supported else None
        references = _member(context, "references")
        states = {
            role: _state(_member(_member(references, role), "state")) for role in _AUTHORIZED_STATES
        }
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise M1102AuthorizationError from None
    if states != _AUTHORIZED_STATES:
        raise M1102AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_context_authorization(candidate)
    return candidate


def _evidence(request: StratifyVariantPeptideContextRequest) -> tuple[EvidenceReference, ...]:
    """Index source and control references without opening external content."""

    refs = request.context.references
    artifacts = (
        *request.source_artifacts,
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        *(item.source_artifact for item in request.observations),
        *(item.reference for item in request.policy.evidence),
    )
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1102_EVIDENCE_CLAIM)
        for artifact in artifacts[:64]
    )


def _normal(value: str) -> str:
    return value.casefold()


def _observation_map(
    observations: tuple[ContextObservation, ...],
) -> dict[ContextDimension, ContextObservation]:
    return {item.dimension: item for item in observations}


def _rule_evaluation(
    request: StratifyVariantPeptideContextRequest,
) -> tuple[
    tuple[MechanismApplicability, ...],
    tuple[ContextStratifierDiagnostic, ...],
    bool,
]:
    observations = _observation_map(request.observations)
    mechanisms: list[MechanismApplicability] = []
    diagnostics: list[ContextStratifierDiagnostic] = []
    safe = True
    for rule in request.policy.rules:
        observation = observations.get(rule.dimension)
        mechanism_id = f"mechanism.{rule.rule_id}"
        if observation is None:
            status = MechanismApplicabilityStatus.NOT_EVALUABLE
            rationale = "Required context dimension is absent from the request."
            safe = False
        elif observation.support_score < request.policy.minimum_support_score:
            status = MechanismApplicabilityStatus.ABSTAINED
            rationale = "Context observation support is below the locked policy boundary."
            safe = False
        elif any(_normal(observation.value) == _normal(proxy) for proxy in rule.prohibited_proxies):
            status = MechanismApplicabilityStatus.NOT_EVALUABLE
            rationale = "A prohibited proxy was supplied instead of biological context evidence."
            safe = False
        elif any(_normal(observation.value) == _normal(value) for value in rule.allowed_values):
            status = MechanismApplicabilityStatus.APPLICABLE
            rationale = "Context observation satisfies the locked rule and support boundary."
        else:
            status = MechanismApplicabilityStatus.NOT_EVALUABLE
            rationale = "Context value is outside the locked support catalogue."
            safe = False
        evidence = observation.evidence if observation is not None else ()
        mechanisms.append(
            MechanismApplicability(
                mechanism_id=mechanism_id,
                status=status,
                rationale=rationale,
                context_dimensions=(rule.dimension,),
                evidence=evidence,
            )
        )
        diagnostics.append(
            ContextStratifierDiagnostic(
                diagnostic_id=f"diagnostic.{rule.rule_id}",
                status=status,
                message=rationale,
                evidence=evidence,
            )
        )
    return tuple(mechanisms), tuple(diagnostics), safe


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    limitations = [
        Limitation(
            code="opaque_inputs",
            statement="Source artifacts are immutable references and are never traversed.",
        ),
        Limitation(
            code="context_only",
            statement=(
                "This operation emits typed context and mechanism applicability only; it does "
                "not emit subtype, kinase activity, all-omics fusion, or treatment advice."
            ),
        ),
        Limitation(
            code="unsupported_to_negative_blocked",
            statement="Missing or unsupported context is preserved as not evaluable or abstained.",
        ),
    ]
    if not supported:
        limitations.append(
            Limitation(
                code="safe_abstention",
                statement="No context profile is published outside the locked support boundary.",
            )
        )
    return tuple(limitations)


class M1102ContextEngine:
    """Evaluate caller-declared context against one locked deterministic policy."""

    __slots__ = ()

    def stratify(self, request: object) -> VariantPeptideContextStratificationResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self,
        request: StratifyVariantPeptideContextRequest,
    ) -> VariantPeptideContextStratificationResult:
        request_hash = canonical_request_digest(request)
        mechanisms, diagnostics, safe = _rule_evaluation(request)
        evidence = _evidence(request)
        profile = (
            ContextProfile(
                profile_id=f"profile.{request_hash.removeprefix('sha256:')}",
                version=request.policy.version,
                observations=request.observations,
                applicable_mechanisms=mechanisms,
                evidence=evidence,
            )
            if safe
            else None
        )
        status = (
            ContextStratificationStatus.STRATIFIED
            if safe
            else ContextStratificationStatus.ABSTAINED
        )
        support = (
            SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m1102_context_stratified",
                rationale="Every locked context rule met its declared support boundary.",
            )
            if safe
            else SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m1102_context_abstained",
                rationale="Context mapping is withheld because at least one rule is not evaluable.",
            )
        )
        payload: dict[str, object] = {
            "output_type": "variant_peptide_context_profile",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1102_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "profile": profile,
            "diagnostics": diagnostics,
            "abstention_reason": None
            if safe
            else (
                "At least one context rule is missing, unsupported, proxied, or outside the "
                "locked catalogue."
            ),
            "parent_target": M1102_PARENT,
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": expected_uncertainty(supported=safe),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=safe),
            "human_review_required": not safe,
        }
        constructed = VariantPeptideContextStratificationResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideContextStratificationResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1102ReplayVerificationError(  # noqa: TRY003
                "result is not a strict result envelope"
            ) from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1102ReplayVerificationError(  # noqa: TRY003
                "result digest does not match canonical payload"
            )
        if replay:
            expected = self.stratify(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1102ReplayVerificationError(  # noqa: TRY003
                    "replayed request produced a different result"
                )
        return validated


def stratify_variant_peptide_context(
    request: object,
) -> VariantPeptideContextStratificationResult:
    """Public provisional M11-02 operation."""

    return M1102ContextEngine().stratify(request)


__all__ = [
    "M1102AuthorizationError",
    "M1102ContextEngine",
    "M1102ReplayVerificationError",
    "preflight_context_authorization",
    "stratify_variant_peptide_context",
]
