"""Deterministic, replay-bound M11-05 trajectory runtime.

The dossier leaves the public ABI provisional.  This implementation therefore
uses a transparent baseline: caller-declared territory and treatment-era
labels define state boundaries, while feature artifacts remain opaque,
content-addressed references.  No upstream payload is traversed or mutated.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import pairwise
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m11_05 import (
    M1105_CONTRACT_VERSION,
    M1105_EVIDENCE_CLAIM,
    M1105_PARENT,
    ChangePoint,
    ChangePointStatus,
    LongitudinalDiagnostic,
    LongitudinalDiagnosticCode,
    ModelVariantPeptideLongitudinalEvolutionRequest,
    TrajectoryState,
    TrajectoryStatus,
    VariantPeptideLongitudinalEvolutionResult,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m11_05.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    EvidenceReference as KernelEvidenceReference,
)
from glio_proteogen.kernel.models import (
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ModelVariantPeptideLongitudinalEvolutionRequest)
_RESULT_ADAPTER: Final = TypeAdapter(VariantPeptideLongitudinalEvolutionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M1105AuthorizationError(PermissionError):
    """Caller-owned controls are not authorized for trajectory evaluation."""

    def __init__(self) -> None:
        super().__init__(
            "M11-05 requires accepted configuration, resolved identity, accepted provenance, "
            "granted consent, accepted quality/support/intended-use controls"
        )


class M1105ReplayVerificationError(ValueError):
    """A trajectory result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M11-05 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1105_authorization(candidate: object) -> None:
    """Check seven controls before touching observation or upstream fields."""

    expected = {
        "approved_configuration": "accepted",
        "identity_lineage": "resolved",
        "provenance": "accepted",
        "consent": "granted",
        "quality": "accepted",
        "support": "accepted",
        "intended_use": "accepted",
    }
    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {role: _state(_member(_member(references, role), "state")) for role in expected}
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise M1105AuthorizationError from None
    if states != expected:
        raise M1105AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_m1105_authorization(candidate)
    return candidate


def _evidence(
    request: ModelVariantPeptideLongitudinalEvolutionRequest,
) -> tuple[KernelEvidenceReference, ...]:
    refs = request.context.references
    artifacts = (
        request.network_state_result,
        *request.source_artifacts,
        *(observation.feature_artifact for observation in request.observations),
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    )
    return tuple(
        KernelEvidenceReference(
            reference=artifact,
            role="evidence",
            claim=M1105_EVIDENCE_CLAIM,
        )
        for artifact in artifacts[:64]
    )


def _state_label(territory: str, treatment_era: str) -> str:
    """Encode only explicit caller labels; this function never reads artifacts."""

    return f"territory={territory};treatment_era={treatment_era}"


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="opaque_feature_artifacts",
            statement=(
                "Feature and upstream artifacts are immutable references and are never traversed."
            ),
        ),
        Limitation(
            code="caller_declared_state_labels",
            statement=(
                "The provisional baseline uses explicit territory and treatment-era labels only."
            ),
        ),
        Limitation(
            code="prohibited_outputs",
            statement=(
                "No kinase activity, all-omics fusion, treatment recommendation, identity "
                "inference, consent inference, or parent-output mutation is emitted."
            ),
        ),
    ]
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement="No trajectory or change point is published after a failed quality gate.",
            )
        )
    return tuple(values)


class M1105LongitudinalEngine:
    """Evaluate a strictly ordered, caller-declared longitudinal history."""

    __slots__ = ()

    def infer(self, request: object) -> VariantPeptideLongitudinalEvolutionResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self,
        request: ModelVariantPeptideLongitudinalEvolutionRequest,
    ) -> VariantPeptideLongitudinalEvolutionResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        trajectory: list[TrajectoryState] = []
        previous_label: str | None = None
        for observation in request.observations:
            label = _state_label(observation.territory, observation.treatment_era)
            if label == previous_label:
                trajectory[-1] = trajectory[-1].model_copy(
                    update={
                        "observation_ids": (
                            *trajectory[-1].observation_ids,
                            observation.observation_id,
                        ),
                        "evidence": (
                            *trajectory[-1].evidence,
                            *observation.evidence,
                        ),
                    }
                )
            else:
                trajectory.append(
                    TrajectoryState(
                        state_id=f"state.{observation.sequence}",
                        sequence=observation.sequence,
                        label=label,
                        posterior_probability=1.0,
                        observation_ids=(observation.observation_id,),
                        evidence=(
                            KernelEvidenceReference(
                                reference=observation.feature_artifact,
                                role="evidence",
                                claim=M1105_EVIDENCE_CLAIM,
                            ),
                            *observation.evidence,
                        ),
                    )
                )
            previous_label = label

        change_points: list[ChangePoint] = []
        for before, after in pairwise(trajectory):
            change_points.append(
                ChangePoint(
                    change_point_id=f"change.{after.sequence}",
                    sequence=after.sequence,
                    status=ChangePointStatus.DETECTED,
                    before_state_id=before.state_id,
                    after_state_id=after.state_id,
                    posterior_probability=0.9,
                    rationale=(
                        "Explicit territory or treatment-era label changed between ordered "
                        "observations."
                    ),
                    evidence=after.evidence,
                )
            )
        diagnostics = (
            LongitudinalDiagnostic(
                diagnostic_id="diagnostic.temporal-order",
                code=LongitudinalDiagnosticCode.TEMPORAL_ORDERING_VERIFIED,
                message="Observation sequence and aware timestamps are strictly ordered.",
                evidence=evidence[:1],
            ),
            LongitudinalDiagnostic(
                diagnostic_id="diagnostic.future-leakage",
                code=LongitudinalDiagnosticCode.FUTURE_LEAKAGE_BLOCKED,
                message="Only caller-declared ordered observations are used by the baseline.",
                evidence=evidence[:1],
            ),
            LongitudinalDiagnostic(
                diagnostic_id="diagnostic.provisional-abi",
                code=LongitudinalDiagnosticCode.PROVISIONAL_ABI_PENDING_REVIEW,
                message="Public module ABI remains provisional pending owner confirmation.",
                evidence=(),
            ),
        )
        payload: dict[str, object] = {
            "output_type": "variant_peptide_longitudinal_evolution",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1105_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": TrajectoryStatus.MODELED,
            "trajectory": tuple(trajectory),
            "change_points": tuple(change_points),
            "diagnostics": diagnostics,
            "abstention_reason": None,
            "parent_target": M1105_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m1105_trajectory_supported",
                rationale="All temporal, future-leakage, and caller-control gates passed.",
            ),
            "uncertainty": expected_uncertainty(supported=True),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=True),
            "human_review_required": True,
        }
        constructed = VariantPeptideLongitudinalEvolutionResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideLongitudinalEvolutionResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1105ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1105ReplayVerificationError
        if replay:
            try:
                expected = self.infer(validated.request)
            except Exception as error:
                raise M1105ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1105ReplayVerificationError
        return validated


def infer_variant_peptide_longitudinal_evolution(
    request: object,
) -> VariantPeptideLongitudinalEvolutionResult:
    """Public provisional M11-05 operation."""

    return M1105LongitudinalEngine().infer(request)


__all__ = [
    "M1105AuthorizationError",
    "M1105LongitudinalEngine",
    "M1105ReplayVerificationError",
    "infer_variant_peptide_longitudinal_evolution",
    "preflight_m1105_authorization",
]
