"""Deterministic, caller-declared context stratification for M13-02.

The implementation intentionally evaluates only typed observations and opaque
artifact references.  It never opens upstream payloads, infers identity or
consent, performs all-omics fusion, emits kinase state, or turns absent evidence
into a negative biological claim.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final, cast

from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m13_02 import (
    M1302_CONTRACT_VERSION,
    M1302_MODULE_ID,
    ApplicableMechanism,
    ContextDimension,
    ContextFinding,
    ContextFindingCode,
    ContextObservation,
    ContextObservationStatus,
    ContextStratificationStatus,
    MechanismApplicability,
    ProteotypeContextProfile,
    ProteotypeContextStratificationResult,
    StratifyProteotypeContextRequest,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

_TOKEN_SEAL: Final = object()
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_AUTHORIZATION_MESSAGE: Final = "M13-02 context stratification requires accepted upstream controls"
_EXPECTED_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}

DESCRIPTOR: Final = ModuleDescriptor(
    module_id=M1302_MODULE_ID,
    title="Proteotype context and subtype stratifier",
    version=M1302_CONTRACT_VERSION,
    owner="Clinical science",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "kinase activity or kinase-state inference",
        "generic all-omics fusion or direct treatment recommendation",
        "identity or consent inference, upstream mutation, relabeling, or disagreement erasure",
        "unsupported extrapolation converted into a negative biological finding",
    ),
)


class M1302AuthorizationError(PermissionError):
    """Raised before any caller-declared evidence is traversed."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class _InvalidCandidateError(TypeError):
    """Raised when an untrusted object is not a strict mapping/model."""

    def __init__(self) -> None:
        super().__init__("M13-02 requests require exact built-in JSON containers")


class _ReplayDigestError(ValueError):
    def __init__(self) -> None:
        super().__init__("M13-02 request replay digest mismatch")


class M1302ContextStratifier:
    """Compute one immutable stratification result from a validated request."""

    __slots__ = ()

    def descriptor(self) -> ModuleDescriptor:
        return DESCRIPTOR

    def compute(self, request: object) -> ProteotypeContextStratificationResult:
        preflight_context_authorization(request)
        typed = _validate_request(request)
        return _compute(typed)


def compute_proteotype_context(request: object) -> ProteotypeContextStratificationResult:
    """Public stateless M13-02 operation."""

    return M1302ContextStratifier().compute(request)


def preflight_context_authorization(candidate: object) -> None:
    """Require all seven exact controls without reading opaque artifacts."""

    try:
        candidate_type = type(candidate)
        supported = candidate_type is StratifyProteotypeContextRequest or dict in (
            type.__getattribute__(candidate_type, "__mro__")
        )
        context = _member(candidate, "context") if supported else None
        references = _member(context, "references")
        states = {
            role: _state_text(_member(_member(references, role), "state"))
            for role in _EXPECTED_STATES
        }
    except Exception:  # noqa: BLE001 - hostile caller objects fail closed.
        raise M1302AuthorizationError from None
    if not supported or states != _EXPECTED_STATES:
        raise M1302AuthorizationError


def _validate_request(candidate: object) -> StratifyProteotypeContextRequest:
    """Validate strict object input and bind it to its canonical request digest."""

    if type(candidate) is StratifyProteotypeContextRequest:
        return cast("StratifyProteotypeContextRequest", candidate)
    plain = _plain_value(candidate)
    request = StratifyProteotypeContextRequest.model_validate_json(
        canonical_json_bytes(plain), strict=True
    )
    if canonical_request_digest(request) != canonical_request_digest(
        cast("dict[str, object]", plain)
    ):
        raise _ReplayDigestError
    return request


def validate_json_request(serialized: bytes | bytearray | str) -> StratifyProteotypeContextRequest:
    """Strictly decode and validate one JSON request exactly once."""

    decoded = strict_json_loads(serialized)
    preflight_context_authorization(decoded)
    return _validate_request(decoded)


def verify_context_result(result: object) -> bool:
    """Replay and verify an M13-02 result envelope without accepting tampering."""

    try:
        typed = ProteotypeContextStratificationResult.model_validate(result, strict=True)
    except ValidationError:
        return False
    return typed.request_digest == canonical_request_digest(
        typed.request
    ) and typed.result_digest == result_payload_digest(typed)


def _compute(request: StratifyProteotypeContextRequest) -> ProteotypeContextStratificationResult:
    request_digest = canonical_request_digest(request)
    by_dimension = _observations_by_dimension(request.observations)
    unresolved = tuple(
        dimension
        for dimension in request.policy.required_dimensions
        if not _dimension_supported(by_dimension.get(dimension, ()))
    )
    conflict = any(
        item.status in {ContextObservationStatus.CONFLICTED, ContextObservationStatus.UNRESOLVED}
        for item in request.observations
    )
    stratified = not unresolved and not conflict
    findings = _findings(unresolved, conflict=conflict)
    uncertainty = _uncertainty(supported=stratified)
    provenance = _provenance(request)
    evidence = _unique_evidence(request.observations)
    limitations = _limitations()
    if stratified:
        profile = ProteotypeContextProfile(
            profile_id=f"profile.m1302.{request_digest.removeprefix('sha256:')}",
            version=request.policy.configuration.version,
            observations=request.observations,
            unresolved_dimensions=tuple(
                item.dimension
                for item in request.observations
                if item.status
                in {ContextObservationStatus.CONFLICTED, ContextObservationStatus.UNRESOLVED}
            ),
            evidence=evidence,
        )
        mechanisms = _mechanisms(request, by_dimension)
        status = ContextStratificationStatus.STRATIFIED
        support = SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m1302_context_supported",
            rationale=(
                "All policy-required dimensions have supported or limited "
                "caller-declared observations."
            ),
        )
        abstention_reason = None
    else:
        profile = None
        mechanisms = ()
        status = ContextStratificationStatus.ABSTAINED
        support = SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED if conflict else SupportStatus.UNSUPPORTED,
            reason_code="m1302_context_quarantined",
            rationale="Unresolved, conflicted, or missing required context remains quarantined.",
        )
        missing = (
            ", ".join(dimension.value for dimension in unresolved) or "conflicted observations"
        )
        abstention_reason = (
            f"Context stratification abstained; unresolved support boundary: {missing}."
        )

    payload: dict[str, object] = {
        "output_type": "proteotype_context_stratification",
        "result_id": f"result.m1302.{request_digest.removeprefix('sha256:')}",
        "result_version": M1302_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": status,
        "context_profile": profile,
        "applicable_mechanisms": mechanisms,
        "findings": findings,
        "abstention_reason": abstention_reason,
        "parent_target": "proteotype",
        "emits_parent": False,
        "support_decision": support,
        "uncertainty": uncertainty,
        "provenance": provenance,
        "evidence": evidence,
        "limitations": limitations,
        "human_review_required": True,
    }
    # Calculate over the same typed envelope the public validator will replay.
    assembled = ProteotypeContextStratificationResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(assembled)
    return ProteotypeContextStratificationResult.model_validate(payload, strict=True)


def _mechanisms(
    request: StratifyProteotypeContextRequest,
    by_dimension: dict[ContextDimension, tuple[ContextObservation, ...]],
) -> tuple[ApplicableMechanism, ...]:
    output: list[ApplicableMechanism] = []
    for candidate in request.mechanism_candidates:
        observations = tuple(
            item
            for dimension in candidate.required_dimensions
            for item in by_dimension.get(dimension, ())
        )
        statuses = {item.status for item in observations}
        if statuses and statuses <= {ContextObservationStatus.SUPPORTED}:
            applicability = MechanismApplicability.APPLICABLE
        elif ContextObservationStatus.CONFLICTED in statuses:
            applicability = MechanismApplicability.UNKNOWN
        else:
            applicability = MechanismApplicability.UNKNOWN
        output.append(
            ApplicableMechanism(
                mechanism_id=candidate.mechanism_id,
                label=candidate.label,
                applicability=applicability,
                rationale=candidate.rationale,
                evidence=_unique_evidence(observations) or candidate.evidence,
            )
        )
    return tuple(output)


def _findings(
    unresolved: tuple[ContextDimension, ...],
    *,
    conflict: bool,
) -> tuple[ContextFinding, ...]:
    findings: list[ContextFinding] = []
    if conflict:
        findings.append(
            ContextFinding(
                finding_id="finding.m1302.context-conflict",
                code=ContextFindingCode.CONTEXT_CONFLICT,
                message="Conflicting or unresolved observations were preserved and quarantined.",
            )
        )
    if unresolved:
        findings.append(
            ContextFinding(
                finding_id="finding.m1302.support-boundary",
                code=ContextFindingCode.UNSUPPORTED_PROXY_BLOCKED,
                message="Required context dimensions lack a supported observation.",
            )
        )
    findings.append(
        ContextFinding(
            finding_id="finding.m1302.provisional-abi",
            code=ContextFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
            message=(
                "The public ABI remains provisional pending owner confirmation; "
                "this output is not a frozen endpoint."
            ),
        )
    )
    return tuple(findings)


def _uncertainty(*, supported: bool) -> UncertaintyProfile:
    state = EstimateState.ESTIMATED if supported else EstimateState.NOT_ESTIMABLE
    probability = 0.9 if supported else None
    rationale = (
        "Deterministic caller-declared support envelope; calibration is provisional."
        if supported
        else "Input support boundary prevents a defensible estimate."
    )

    def estimate() -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=state,
            probability=probability,
            rationale=rationale,
        )

    return UncertaintyProfile(
        measurement=estimate(),
        sampling=estimate(),
        parameter=estimate(),
        model_form=estimate(),
        identification=estimate(),
        support=estimate(),
        transport=estimate(),
        sensitivity_notes=(
            "Nominal 90% target is provisional; monitor coverage by context stratum.",
            "No unsupported value is converted to a negative finding.",
        ),
    )


def _provenance(request: StratifyProteotypeContextRequest) -> ProvenanceRecord:
    refs = request.context.references
    records = (
        _control(ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        _control(ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        _control(ControlRole.PROVENANCE, refs.provenance),
        _control(ControlRole.CONSENT, refs.consent),
        _control(ControlRole.QUALITY, refs.quality),
        _control(ControlRole.SUPPORT, refs.support),
        _control(ControlRole.INTENDED_USE, refs.intended_use),
    )
    inputs = tuple(
        dict.fromkeys(
            [request.variant_peptide_result.digest]
            + [artifact.digest for artifact in request.source_artifacts]
            + [request.policy.configuration.model_reference.digest]
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.m1302.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1302_MODULE_ID,
        module_version=M1302_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=inputs,
        configuration_digest=request.policy.configuration.model_reference.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=records,
    )


def _control(role: ControlRole, ref: object) -> ControlDecisionRecord:
    evidence = _member(_member(ref, "evidence"), "digest")
    state = _state_text(_member(ref, "state"))
    decision_id = _member(ref, "decision_id")
    policy = _member(ref, "policy_version")
    subject = _member(ref, "binding_digest") if role is ControlRole.IDENTITY_LINEAGE else None
    return ControlDecisionRecord(
        role=role,
        decision_id=cast("str", decision_id),
        state=cast("str", state),
        policy_version=cast("str", policy),
        evidence_digest=cast("str", evidence),
        subject_digest=cast("str | None", subject),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="kinase_state_excluded",
            statement=(
                "Kinase activity and kinase-state claims are owned by KINOPHOS and are not emitted."
            ),
        ),
        Limitation(
            code="all_omics_fusion_excluded",
            statement=(
                "This operation does not perform generic all-omics fusion or "
                "mutate upstream evidence."
            ),
        ),
        Limitation(
            code="treatment_recommendation_excluded",
            statement="No direct treatment recommendation is produced.",
        ),
    )


def _observations_by_dimension(
    observations: tuple[ContextObservation, ...],
) -> dict[ContextDimension, tuple[ContextObservation, ...]]:
    grouped: dict[ContextDimension, list[ContextObservation]] = {}
    for item in observations:
        grouped.setdefault(item.dimension, []).append(item)
    return {key: tuple(value) for key, value in grouped.items()}


def _dimension_supported(observations: tuple[ContextObservation, ...]) -> bool:
    return bool(observations) and all(
        item.status in {ContextObservationStatus.SUPPORTED, ContextObservationStatus.LIMITED}
        for item in observations
    )


def _unique_evidence(observations: tuple[ContextObservation, ...]) -> tuple[EvidenceReference, ...]:
    seen: set[tuple[str, str, str, str]] = set()
    output: list[EvidenceReference] = []
    for observation in observations:
        for evidence in observation.evidence:
            key = (
                evidence.reference.artifact_id,
                evidence.reference.version,
                evidence.reference.digest,
                evidence.claim,
            )
            if key not in seen:
                seen.add(key)
                output.append(evidence)
    return tuple(output)


def _member(candidate: object, field: str) -> object:
    candidate_type = type(candidate)
    mro = type.__getattribute__(candidate_type, "__mro__")
    if dict in mro:
        return dict.get(cast("dict[object, object]", candidate), field)
    if BaseModel in mro:
        storage = object.__getattribute__(candidate, "__dict__")
        return dict.get(cast("dict[object, object]", storage), field)
    return None


def _state_text(candidate: object) -> object:
    if type(candidate) is str:
        return candidate
    if StrEnum in type.__getattribute__(type(candidate), "__mro__"):
        value = object.__getattribute__(candidate, "_value_")
        return value if type(value) is str else None
    return None


def _plain_value(candidate: object) -> object:
    candidate_type = type(candidate)
    mro = type.__getattribute__(candidate_type, "__mro__")
    if BaseModel in mro:
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        if type(storage) is not dict or any(type(key) is not str for key in storage):
            raise _InvalidCandidateError
        return {key: _plain_value(value) for key, value in storage.items()}
    if dict in mro:
        mapping = cast("dict[object, object]", candidate)
        if any(type(key) is not str for key in mapping):
            raise _InvalidCandidateError
        return {key: _plain_value(value) for key, value in mapping.items()}
    if list in mro:
        return [_plain_value(item) for item in cast("list[object]", candidate)]
    if tuple in mro:
        return tuple(_plain_value(item) for item in cast("tuple[object, ...]", candidate))
    if Mapping in mro:
        raise _InvalidCandidateError
    return candidate


__all__ = [
    "DESCRIPTOR",
    "M1302AuthorizationError",
    "M1302ContextStratifier",
    "compute_proteotype_context",
    "preflight_context_authorization",
    "validate_json_request",
    "verify_context_result",
]
