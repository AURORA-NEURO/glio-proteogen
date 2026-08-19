"""Deterministic, replay-bound M13-05 longitudinal trajectory runtime.

The public estimator ABI is intentionally provisional.  Runtime behavior is
therefore limited to a closed caller-declared objective grammar.  References
are treated as opaque: this module never reads an artifact, infers consent or
identity, joins unrelated omics, or turns an unsupported request into a
negative biological finding.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m13_05 import (
    M1305_CONTRACT_VERSION,
    M1305_PARENT,
    ChangePoint,
    ChangePointStatus,
    LongitudinalDiagnostic,
    LongitudinalDiagnosticCode,
    ModelProteotypeLongitudinalEvolutionRequest,
    ProteotypeLongitudinalEvolutionResult,
    TimePointObservation,
    TrajectoryState,
    TrajectoryStatus,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m13_05.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)
from glio_proteogen.kernel.models import (
    EvidenceReference as KernelEvidenceReference,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ModelProteotypeLongitudinalEvolutionRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteotypeLongitudinalEvolutionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SUPPORTED_OBJECTIVES: Final = frozenset(
    {
        "stable",
        "alternating",
        "territory",
        "treatment_era",
        "time_course",
        "primary_recurrence",
        "clone",
        "state_transition",
    }
)
_TWO_PART_OBJECTIVE: Final = 2
_CHANGE_POINT_PARTS: Final = 4


class M1305AuthorizationError(PermissionError):
    """Caller-owned controls do not authorize longitudinal inference."""

    def __init__(self) -> None:
        super().__init__(
            "M13-05 requires accepted controls, resolved identity, and granted consent"
        )


class M1305ReplayVerificationError(ValueError):
    """A trajectory result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M13-05 replay verification failed")


class M1305InferenceError(ValueError):
    """A caller-declared trajectory objective cannot be evaluated safely."""


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_longitudinal_authorization(candidate: object) -> None:
    """Check every control before traversing typed or opaque request data."""

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
    except Exception as error:
        raise M1305AuthorizationError from error
    if states != expected:
        raise M1305AuthorizationError


def _evidence(
    request: ModelProteotypeLongitudinalEvolutionRequest,
) -> tuple[KernelEvidenceReference, ...]:
    refs = request.context.references
    artifacts = (
        request.network_state_result,
        *request.source_artifacts,
        *(item.feature_artifact for item in request.observations),
        request.policy.configuration.model_reference,
        *(item.reference for item in request.policy.configuration.evidence),
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    )
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        KernelEvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared longitudinal observation, model, control, and upstream "
                "evidence; artifact content is not authenticated by this module."
            ),
        )
        for artifact in tuple(unique.values())[:64]
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="opaque_artifacts",
            statement="Artifact references are immutable and their content is never traversed.",
        ),
        Limitation(
            code="future_leakage_blocked",
            statement=(
                "Only caller-declared ordered observations are projected; future values are "
                "not read."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "The result emits only a time-indexed trajectory and change-point object; "
                "it does not infer kinase activity, treatment, identity, or consent."
            ),
        ),
        Limitation(
            code="provisional_abi",
            statement=(
                "The estimator grammar and endpoint metadata remain provisional pending "
                "owner confirmation."
            ),
        ),
    ]
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement=(
                    "Unsupported objectives and unresolved histories are quarantined for human "
                    "review."
                ),
            )
        )
    return tuple(values)


def _objective_kind(objective: str) -> tuple[str, int | None, str | None, str | None]:
    """Parse the closed deterministic objective grammar."""

    parts = objective.split(":")
    if len(parts) == 1 and parts[0] in _SUPPORTED_OBJECTIVES:
        return parts[0], None, None, None
    if (
        len(parts) == _TWO_PART_OBJECTIVE
        and parts[0] in {"trajectory", "mode"}
        and parts[1] in (_SUPPORTED_OBJECTIVES - {"time_course"})
    ):
        return parts[1], None, None, None
    if len(parts) == _CHANGE_POINT_PARTS and parts[0] in {"change_point", "changepoint"}:
        try:
            sequence = int(parts[1])
        except ValueError:
            return "", None, None, None
        if sequence < 1 or not parts[2] or not parts[3]:
            return "", None, None, None
        return "change_point", sequence, parts[2], parts[3]
    return "", None, None, None


def _label_for(  # noqa: PLR0911 - each supported dimension has an explicit label policy.
    kind: str,
    observation: TimePointObservation,
    index: int,
    *,
    change_spec: tuple[int, str, str] | None = None,
) -> str:
    if kind == "stable":
        return "stable"
    if kind in {"alternating", "clone"}:
        return "state_a" if index % 2 == 0 else "state_b"
    if kind == "territory":
        return observation.territory
    if kind == "treatment_era":
        return observation.treatment_era
    if kind == "primary_recurrence":
        return "primary" if index == 0 else "recurrence"
    if kind == "state_transition":
        return f"state_{observation.sequence}"
    if kind == "change_point":
        if change_spec is None:
            raise M1305InferenceError
        before_sequence, before_label, after_label = change_spec
        return before_label if observation.sequence < before_sequence else after_label
    return "time_course"


class M1305LongitudinalEngine:
    """Infer a caller-declared longitudinal trajectory with deterministic replay."""

    __slots__ = ()

    def infer(self, request: object) -> ProteotypeLongitudinalEvolutionResult:
        preflight_longitudinal_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return self._result(validated)

    def _result(  # noqa: C901 - explicit closure is branch-rich by design.
        self, request: ModelProteotypeLongitudinalEvolutionRequest
    ) -> ProteotypeLongitudinalEvolutionResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        kind, change_sequence, before_label, after_label = _objective_kind(
            request.policy.configuration.objective
        )
        supported = kind in _SUPPORTED_OBJECTIVES or kind == "change_point"
        reason = ""
        if supported and kind == "change_point":
            if change_sequence is None:
                raise M1305InferenceError
            sequences = tuple(item.sequence for item in request.observations)
            supported = min(sequences) < change_sequence <= max(sequences)
            if not supported:
                reason = "Change-point objective is outside the observed temporal support domain."
        if not supported:
            reason = reason or (
                "Objective is outside the closed provisional longitudinal grammar; no trajectory "
                "or negative biological finding is emitted."
            )
        trajectory: tuple[TrajectoryState, ...] = ()
        changes: tuple[ChangePoint, ...] = ()
        diagnostics: list[LongitudinalDiagnostic] = [
            LongitudinalDiagnostic(
                diagnostic_id="diagnostic.temporal-ordering",
                code=LongitudinalDiagnosticCode.TEMPORAL_ORDERING_VERIFIED,
                message="Observation sequences and timestamps are strictly ordered.",
                evidence=evidence[:1],
            )
        ]
        if supported:
            change_spec: tuple[int, str, str] | None = None
            if kind == "change_point":
                if change_sequence is None or before_label is None or after_label is None:
                    raise M1305InferenceError
                change_spec = (change_sequence, before_label, after_label)
            states: list[TrajectoryState] = []
            for index, observation in enumerate(request.observations):
                label = _label_for(kind, observation, index, change_spec=change_spec)
                states.append(
                    TrajectoryState(
                        state_id=f"state.{observation.observation_id}",
                        sequence=observation.sequence,
                        label=label,
                        posterior_probability=0.9,
                        observation_ids=(observation.observation_id,),
                        evidence=evidence[:1],
                    )
                )
            trajectory = tuple(states)
            if kind == "change_point":
                if change_sequence is None:
                    raise M1305InferenceError
                before = next(
                    (state for state in trajectory if state.sequence < change_sequence), None
                )
                after = next(
                    (state for state in trajectory if state.sequence >= change_sequence), None
                )
                if before is None or after is None:
                    raise M1305InferenceError
                changes = (
                    ChangePoint(
                        change_point_id=f"change-point.{change_sequence}",
                        sequence=change_sequence,
                        status=ChangePointStatus.DETECTED,
                        before_state_id=before.state_id,
                        after_state_id=after.state_id,
                        posterior_probability=0.9,
                        rationale=(
                            "The locked change-point objective separates ordered pre/post states."
                        ),
                        evidence=evidence[:1],
                    ),
                )
            diagnostics.append(
                LongitudinalDiagnostic(
                    diagnostic_id="diagnostic.provisional-abi",
                    code=LongitudinalDiagnosticCode.PROVISIONAL_ABI_PENDING_REVIEW,
                    message=(
                        "Trajectory labels and probabilities use the provisional deterministic "
                        "grammar."
                    ),
                    evidence=evidence[:1],
                )
            )
        else:
            diagnostics.append(
                LongitudinalDiagnostic(
                    diagnostic_id="diagnostic.not-evaluable",
                    code=LongitudinalDiagnosticCode.INSUFFICIENT_HISTORY,
                    message=reason,
                    evidence=evidence[:1],
                )
            )
        payload: dict[str, Any] = {
            "output_type": "proteotype_longitudinal_evolution",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1305_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": TrajectoryStatus.MODELED if supported else TrajectoryStatus.NOT_EVALUABLE,
            "trajectory": trajectory,
            "change_points": changes,
            "diagnostics": tuple(diagnostics),
            "abstention_reason": None if supported else reason,
            "parent_target": M1305_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code=(
                    "m1305_trajectory_modeled" if supported else "m1305_trajectory_abstained"
                ),
                rationale=(
                    "Ordered observations, locked configuration, and closed objective grammar "
                    "passed."
                    if supported
                    else (
                        "The trajectory is outside the safely evaluable support domain and "
                        "requires review."
                    )
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = ProteotypeLongitudinalEvolutionResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeLongitudinalEvolutionResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1305ReplayVerificationError from error
        try:
            validated = _RESULT_ADAPTER.validate_python(
                validated.model_dump(mode="python", warnings=False), strict=True
            )
        except Exception as error:
            raise M1305ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1305ReplayVerificationError
        if replay:
            try:
                expected = self.infer(validated.request)
            except Exception as error:
                raise M1305ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1305ReplayVerificationError
        return validated


def infer_proteotype_longitudinal_evolution(
    request: object,
) -> ProteotypeLongitudinalEvolutionResult:
    """Public provisional M13-05 operation."""

    return M1305LongitudinalEngine().infer(request)


__all__ = [
    "M1305AuthorizationError",
    "M1305InferenceError",
    "M1305LongitudinalEngine",
    "M1305ReplayVerificationError",
    "infer_proteotype_longitudinal_evolution",
    "preflight_longitudinal_authorization",
]
