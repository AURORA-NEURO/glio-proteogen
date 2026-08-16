"""Deterministic, leakage-safe M14-05 temporal metadata replay.

The dossier leaves the longitudinal model ABI open.  This implementation therefore
replays only caller-declared, ordered observation references into a time-indexed
trajectory.  It never reads source bytes, fits a model, infers a biological state,
or promotes a change point.  Every boundary is explicit about uncertainty and
owner review.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_05 import (
    M1405_CONTRACT_VERSION,
    M1405_EVIDENCE_CLAIM,
    M1405_MODULE_ID,
    M1405_PARENT,
    ChangePoint,
    ChangePointStatus,
    LongitudinalDiagnostic,
    LongitudinalDiagnosticCode,
    ModelProteinSubtypeLongitudinalEvolutionRequest,
    ProteinSubtypeLongitudinalEvolutionResult,
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

_REQUEST_ADAPTER: Final = TypeAdapter(ModelProteinSubtypeLongitudinalEvolutionRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeLongitudinalEvolutionResult)
_EXPECTED_CONTROLS: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_LIMITATIONS: Final = (
    Limitation(
        code="opaque_references",
        statement=(
            "Source and upstream artifacts remain immutable references; this module never "
            "reads their bytes."
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
            "The public ABI remains provisional pending Computational biology confirmation "
            "of the dossier slice."
        ),
    ),
)


class M1405AuthorizationError(PermissionError):
    """Caller-owned controls do not authorize longitudinal replay."""

    def __init__(self) -> None:
        super().__init__(
            "M14-05 requires accepted controls, resolved identity, and granted consent"
        )


class M1405ReplayVerificationError(ValueError):
    """A result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M14-05 replay verification failed")


class _InvalidRequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M14-05 request must be a strict request model or mapping")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1405_authorization(candidate: object) -> None:
    """Check all seven controls before traversing observations or configuration."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {
            role: _state(_member(_member(references, role), "state"))
            for role in _EXPECTED_CONTROLS
        }
    except Exception as error:
        raise M1405AuthorizationError from error
    if states != _EXPECTED_CONTROLS:
        raise M1405AuthorizationError


def _as_request(candidate: object) -> ModelProteinSubtypeLongitudinalEvolutionRequest:
    preflight_m1405_authorization(candidate)
    if type(candidate) is ModelProteinSubtypeLongitudinalEvolutionRequest:
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    if isinstance(candidate, Mapping):
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    raise _InvalidRequestError


def _evidence(
    request: ModelProteinSubtypeLongitudinalEvolutionRequest,
) -> tuple[EvidenceReference, ...]:
    references = (
        request.network_state_result,
        *request.source_artifacts,
        request.policy.configuration.model_reference,
        *(item.reference for item in request.policy.configuration.evidence),
        *(observation.feature_artifact for observation in request.observations),
        *(
            evidence.reference
            for observation in request.observations
            for evidence in observation.evidence
        ),
        request.context.references.approved_configuration.evidence,
        request.context.references.identity_lineage.evidence,
        request.context.references.provenance.evidence,
        request.context.references.consent.evidence,
        request.context.references.quality.evidence,
        request.context.references.support.evidence,
        request.context.references.intended_use.evidence,
    )
    unique: list[ArtifactReference] = []
    seen: set[tuple[str, str, str, str]] = set()
    for reference in references:
        key = (reference.artifact_id, reference.version, reference.digest, reference.media_type)
        if key not in seen:
            seen.add(key)
            unique.append(reference)
    return tuple(
        EvidenceReference(reference=reference, role="evidence", claim=M1405_EVIDENCE_CLAIM)
        for reference in unique
    )


def _controls(
    request: ModelProteinSubtypeLongitudinalEvolutionRequest,
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
        "identification": "Protein subtype and identity are not inferred.",
        "support": "Support reflects caller controls, not external evidence authenticity.",
        "transport": "Transport across cohorts, assays, or treatment eras is not estimable.",
    }
    estimate = {
        name: UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=reason)
        for name, reason in values.items()
    }
    return UncertaintyProfile(
        **estimate,
        sensitivity_notes=(
            "Trajectory ordering is replay-stable but contains no quantitative state estimate.",
            "Owner review is required before any change-point or subtype claim is promoted.",
        ),
    )


def _provenance(
    request: ModelProteinSubtypeLongitudinalEvolutionRequest,
    request_hash: str,
) -> ProvenanceRecord:
    references = request.context.references
    input_digests = (
        request.network_state_result.digest,
        *(artifact.digest for artifact in request.source_artifacts),
        *(observation.feature_artifact.digest for observation in request.observations),
        request.policy.configuration.model_reference.digest,
    )
    return ProvenanceRecord(
        activity_id=f"activity.m1405.{request_hash.removeprefix('sha256:')[:32]}",
        actor_id=request.context.actor_id,
        module_id=M1405_MODULE_ID,
        module_version=M1405_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=sha256_digest(request.policy.model_dump(mode="json")),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=_controls(request),
    )


def _trajectory(
    request: ModelProteinSubtypeLongitudinalEvolutionRequest,
    evidence: tuple[EvidenceReference, ...],
    request_hash: str,
) -> tuple[tuple[TrajectoryState, ...], tuple[ChangePoint, ...]]:
    states = tuple(
        TrajectoryState(
            state_id=f"state.m1405.{request_hash.removeprefix('sha256:')[:12]}.{observation.sequence}",
            sequence=observation.sequence,
            label=f"caller_declared:{observation.feature_artifact.artifact_id}",
            posterior_probability=1.0,
            observation_ids=(observation.observation_id,),
            evidence=(
                EvidenceReference(
                    reference=observation.feature_artifact,
                    role="evidence",
                    claim=M1405_EVIDENCE_CLAIM,
                ),
            ),
        )
        for observation in request.observations
    )
    change_points = tuple(
        ChangePoint(
            change_point_id=(
                f"change-point.m1405.{request_hash.removeprefix('sha256:')[:12]}."
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


class M1405EvolutionEngine:
    """Replay ordered observation metadata without temporal or biological inference."""

    __slots__ = ()

    def construct(
        self, request: object
    ) -> ProteinSubtypeLongitudinalEvolutionResult:
        validated = _as_request(request)
        request_hash = canonical_request_digest(validated)
        evidence = _evidence(validated)
        trajectory, change_points = _trajectory(validated, evidence, request_hash)
        diagnostics = tuple(
            LongitudinalDiagnostic(
                diagnostic_id=f"diagnostic.m1405.{request_hash.removeprefix('sha256:')[:12]}.{code}",
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
            "output_type": "protein_subtype_longitudinal_evolution",
            "result_id": f"result.m1405.{request_hash.removeprefix('sha256:')[:32]}",
            "result_version": M1405_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": "sha256:" + "0" * 64,
            "request": validated,
            "status": TrajectoryStatus.MODELED,
            "trajectory": trajectory,
            "change_points": change_points,
            "diagnostics": diagnostics,
            "abstention_reason": None,
            "parent_target": M1405_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m1405_metadata_replay_supported",
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
        constructed = ProteinSubtypeLongitudinalEvolutionResult.model_construct(
            **payload  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeLongitudinalEvolutionResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1405ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1405ReplayVerificationError
        expected = self.construct(validated.request).model_dump(mode="json")
        if replay and expected != validated.model_dump(mode="json"):
            raise M1405ReplayVerificationError
        return validated


def infer_protein_subtype_longitudinal_evolution(
    request: object,
) -> ProteinSubtypeLongitudinalEvolutionResult:
    """Public provisional M14-05 operation."""

    return M1405EvolutionEngine().construct(request)


__all__ = [
    "M1405AuthorizationError",
    "M1405EvolutionEngine",
    "M1405ReplayVerificationError",
    "infer_protein_subtype_longitudinal_evolution",
    "preflight_m1405_authorization",
]
