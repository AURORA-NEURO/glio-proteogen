"""Replay-safe M15-05 longitudinal and evolutionary model.

The dossier leaves the scientific model ABI open. This implementation therefore
replays only caller-declared ordered observations into a time-indexed trajectory.
It never reads source bytes, fits a model, detects a biological change point,
infers identity, performs all-omics fusion, emits kinase state, or recommends
treatment. Change points are explicit not-evaluable records until owner-frozen
models and calibrated evidence are available.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_05 import (
    M1505_CONTRACT_VERSION,
    M1505_MODULE_ID,
    M1505_PARENT,
    ChangePoint,
    ChangePointStatus,
    ComplexActivityLongitudinalEvolutionResult,
    LongitudinalDiagnostic,
    LongitudinalDiagnosticCode,
    ModelComplexActivityLongitudinalEvolutionRequest,
    TrajectoryState,
    TrajectoryStatus,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
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

_REQUEST_ADAPTER: Final = TypeAdapter(ModelComplexActivityLongitudinalEvolutionRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityLongitudinalEvolutionResult)
_EXPECTED_CONTROLS: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_EVIDENCE_CLAIM: Final = (
    "Caller-declared M15-05 longitudinal observation or control material; "
    "issuer authority is not authenticated."
)
_LIMITATIONS: Final = (
    Limitation(
        code="opaque_references",
        statement=(
            "Source, upstream, and feature artifacts remain immutable references; "
            "M15-05 never reads their bytes."
        ),
    ),
    Limitation(
        code="metadata_replay_only",
        statement=(
            "Trajectory states preserve caller-declared observation order and references; "
            "they are not biological state estimates."
        ),
    ),
    Limitation(
        code="change_points_not_estimable",
        statement=(
            "Change points are explicit not-evaluable records until an owner-frozen model "
            "and calibrated evidence are available."
        ),
    ),
    Limitation(
        code="provisional_abi",
        statement=(
            "The public ABI remains provisional pending Bioinformatics owner confirmation "
            "of the dossier slice."
        ),
    ),
)


class M1505AuthorizationError(PermissionError):
    """Caller-owned controls do not authorize longitudinal replay."""

    def __init__(self) -> None:
        super().__init__(
            "M15-05 requires accepted controls, resolved identity, and granted consent"
        )


class M1505ReplayVerificationError(ValueError):
    """A result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M15-05 replay verification failed")


class _InvalidRequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M15-05 request must be a strict request model or mapping")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1505_authorization(candidate: object) -> None:
    """Check all seven controls before traversing observations or configuration."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {
            role: _state(_member(_member(references, role), "state")) for role in _EXPECTED_CONTROLS
        }
    except Exception as error:
        raise M1505AuthorizationError from error
    if states != _EXPECTED_CONTROLS:
        raise M1505AuthorizationError


def _as_request(candidate: object) -> ModelComplexActivityLongitudinalEvolutionRequest:
    preflight_m1505_authorization(candidate)
    if type(candidate) is ModelComplexActivityLongitudinalEvolutionRequest:
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    if isinstance(candidate, Mapping):
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    raise _InvalidRequestError


def _evidence(
    request: ModelComplexActivityLongitudinalEvolutionRequest,
) -> tuple[EvidenceReference, ...]:
    references: list[ArtifactReference] = [
        request.network_state_result,
        *request.source_artifacts,
        request.policy.configuration.model_reference,
    ]
    references.extend(evidence.reference for evidence in request.policy.configuration.evidence)
    references.extend(observation.feature_artifact for observation in request.observations)
    references.extend(
        evidence.reference
        for observation in request.observations
        for evidence in observation.evidence
    )
    controls = request.context.references
    references.extend(
        (
            controls.approved_configuration.evidence,
            controls.identity_lineage.evidence,
            controls.provenance.evidence,
            controls.consent.evidence,
            controls.quality.evidence,
            controls.support.evidence,
            controls.intended_use.evidence,
        )
    )
    unique: list[ArtifactReference] = []
    seen: set[tuple[str, str, str, str]] = set()
    for reference in references:
        key = (reference.artifact_id, reference.version, reference.digest, reference.media_type)
        if key not in seen:
            seen.add(key)
            unique.append(reference)
    return tuple(
        EvidenceReference(reference=reference, role="evidence", claim=_EVIDENCE_CLAIM)
        for reference in unique
    )


def _controls(
    request: ModelComplexActivityLongitudinalEvolutionRequest,
) -> tuple[ControlDecisionRecord, ...]:
    references = request.context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.CONSENT, references.consent),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=str(_state(reference.state)),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=getattr(reference, "binding_digest", None),
        )
        for role, reference in values
    )


def _uncertainty() -> UncertaintyProfile:
    values = {
        "measurement": "Measurement values are not read from opaque references.",
        "sampling": "Sampling coverage is not available at this metadata-only boundary.",
        "parameter": "No fitted parameters or parameter uncertainty are evaluated.",
        "model_form": "The dossier leaves the longitudinal model ABI open.",
        "identification": "Identity, lineage, and biological state are not inferred.",
        "support": "Support reflects caller controls, not external evidence authenticity.",
        "transport": (
            "Transport across cohorts, assays, territories, or treatment eras is not estimable."
        ),
    }
    estimates = {
        name: UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=reason)
        for name, reason in values.items()
    }
    return UncertaintyProfile(
        **estimates,
        sensitivity_notes=(
            "Trajectory ordering is replay-stable but contains no quantitative state estimate.",
            "Owner review is required before any change-point or evolutionary claim is promoted.",
        ),
    )


def _provenance(
    request: ModelComplexActivityLongitudinalEvolutionRequest,
    request_hash: str,
) -> ProvenanceRecord:
    references = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m1505.{request_hash.removeprefix('sha256:')[:32]}",
        actor_id=request.context.actor_id,
        module_id=M1505_MODULE_ID,
        module_version=M1505_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request.network_state_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
            *(observation.feature_artifact.digest for observation in request.observations),
            request.policy.configuration.model_reference.digest,
        ),
        configuration_digest=sha256_digest(request.policy.model_dump(mode="json")),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=_controls(request),
    )


def _trajectory(
    request: ModelComplexActivityLongitudinalEvolutionRequest,
    evidence: tuple[EvidenceReference, ...],
    request_hash: str,
) -> tuple[tuple[TrajectoryState, ...], tuple[ChangePoint, ...]]:
    states = tuple(
        TrajectoryState(
            state_id=f"state.m1505.{request_hash.removeprefix('sha256:')[:12]}.{observation.sequence}",
            sequence=observation.sequence,
            label=f"caller_declared:{observation.feature_artifact.artifact_id}",
            posterior_probability=1.0,
            observation_ids=(observation.observation_id,),
            evidence=(
                EvidenceReference(
                    reference=observation.feature_artifact,
                    role="evidence",
                    claim=_EVIDENCE_CLAIM,
                ),
            ),
        )
        for observation in request.observations
    )
    change_points = tuple(
        ChangePoint(
            change_point_id=(
                f"change-point.m1505.{request_hash.removeprefix('sha256:')[:12]}."
                f"{left.sequence}-{right.sequence}"
            ),
            sequence=right.sequence,
            status=ChangePointStatus.NOT_EVALUABLE,
            rationale=(
                "Opaque caller-declared references do not support calibrated change-point "
                "estimation."
            ),
            evidence=evidence[:1],
        )
        for left, right in zip(request.observations[:-1], request.observations[1:], strict=True)
    )
    return states, change_points


class M1505EvolutionEngine:
    """Replay ordered observation metadata without temporal or biological inference."""

    __slots__ = ()

    def construct(self, request: object) -> ComplexActivityLongitudinalEvolutionResult:
        validated = _as_request(request)
        request_hash = canonical_request_digest(validated)
        evidence = _evidence(validated)
        trajectory, change_points = _trajectory(validated, evidence, request_hash)
        diagnostics = tuple(
            LongitudinalDiagnostic(
                diagnostic_id=(
                    f"diagnostic.m1505.{request_hash.removeprefix('sha256:')[:12]}.{code}"
                ),
                code=code,
                message=message,
                evidence=evidence[:1],
            )
            for code, message in (
                (
                    LongitudinalDiagnosticCode.TEMPORAL_ORDERING_VERIFIED,
                    "Observation sequence and aware timestamps are strictly ordered.",
                ),
                (
                    LongitudinalDiagnosticCode.FUTURE_LEAKAGE_BLOCKED,
                    "The replay consumes each observation only in caller-declared order.",
                ),
                (
                    LongitudinalDiagnosticCode.PROVISIONAL_ABI_PENDING_REVIEW,
                    "No owner-frozen scientific model or calibrated change-point ABI executes.",
                ),
            )
        )
        payload: dict[str, object] = {
            "output_type": "complex_activity_longitudinal_evolution",
            "result_id": f"result.m1505.{request_hash.removeprefix('sha256:')[:32]}",
            "result_version": M1505_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": "sha256:" + "0" * 64,
            "request": validated,
            "status": TrajectoryStatus.MODELED,
            "trajectory": trajectory,
            "change_points": change_points,
            "diagnostics": diagnostics,
            "abstention_reason": None,
            "parent_target": M1505_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m1505_metadata_replay_supported",
                rationale=(
                    "Ordered caller-declared trajectory metadata was replayed; no biological "
                    "state or change point was inferred."
                ),
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(validated, request_hash),
            "evidence": evidence,
            "limitations": _LIMITATIONS,
            "temporal_order_verified": True,
            "future_leakage_checked": True,
            "human_review_required": True,
        }
        constructed = ComplexActivityLongitudinalEvolutionResult.model_construct(
            **payload  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityLongitudinalEvolutionResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1505ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1505ReplayVerificationError
        expected = self.construct(validated.request).model_dump(mode="json")
        if replay and expected != validated.model_dump(mode="json"):
            raise M1505ReplayVerificationError
        return validated


def infer_complex_activity_longitudinal_evolution(
    request: object,
) -> ComplexActivityLongitudinalEvolutionResult:
    """Public provisional M15-05 operation."""

    return M1505EvolutionEngine().construct(request)


__all__ = [
    "M1505AuthorizationError",
    "M1505EvolutionEngine",
    "M1505ReplayVerificationError",
    "infer_complex_activity_longitudinal_evolution",
    "preflight_m1505_authorization",
]
