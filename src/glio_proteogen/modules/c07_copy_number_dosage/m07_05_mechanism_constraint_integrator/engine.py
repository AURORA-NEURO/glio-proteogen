"""Deterministic mechanism/constraint integration with a typed glioma dosage lane.

The compatibility path preserves the original declaration-only hard/soft
constraint behavior.  The opt-in typed path fits explicit standardized dosage
effects with robust IRLS, signed glioma program coupling, censor-aware loss,
and deterministic bootstrap uncertainty without reading caller artifacts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import Final

import numpy as np
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m07_05 import (
    M0705_EVIDENCE_CLAIM,
    M0705_GLIOMA_MODEL_FAMILY,
    M0705_MAX_CANONICAL_RESULT_BYTES,
    M0705_MAX_TYPED_EFFECT,
    DosageEvidenceState,
    DosageOptimizationDiagnostic,
    DosageOptimizationStatus,
    GliomaDosageObservation,
    IntegrateProteotypeConstraintsRequest,
    IntegrateProteotypeConstraintsResult,
    IntegrateProteotypeConstraintsVerification,
    ProteotypeConstraintAblation,
    ProteotypeConstraintAwareEstimate,
    ProteotypeConstraintEvaluation,
    ProteotypeConstraintEvaluationOutcome,
    ProteotypeConstraintHardness,
    ProteotypeConstraintIntegrationStatus,
    ProteotypeConstraintReplayReason,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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

_REQUEST_ADAPTER: Final = TypeAdapter(IntegrateProteotypeConstraintsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(IntegrateProteotypeConstraintsResult)


class ConstraintAuthorizationError(PermissionError):
    """Raised before an unauthorized integration request traverses inputs."""

    def __init__(self) -> None:
        super().__init__("M07-05 constraint integration request is not authorized")


class ConstraintInputError(ValueError):
    """Raised for malformed, oversized, or non-canonical integration inputs."""

    _MESSAGES: Final = {
        "result_limit": "constraint result exceeds byte limit",
        "result_digest": "constraint result digest does not match",
        "result_noncanonical": "constraint result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltConstraintIntegration:
    """Typed result and its only canonical byte representation."""

    result: IntegrateProteotypeConstraintsResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise ConstraintInputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise ConstraintInputError("result_noncanonical")


def preflight_constraint_authorization(request: object) -> None:
    """Apply shared consent, identity, and accepted-control gates."""

    if not isinstance(request, IntegrateProteotypeConstraintsRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise ConstraintAuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ConstraintAuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise ConstraintAuthorizationError


def _control_decisions(
    request: IntegrateProteotypeConstraintsRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    decisions = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=decision.state.value,
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                refs.identity_lineage.binding_digest
                if role is ControlRole.IDENTITY_LINEAGE
                else None
            ),
        )
        for role, decision in decisions
    )


def _provenance(request: IntegrateProteotypeConstraintsRequest) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        sorted(
            {item.digest for item in request.feature_artifacts}
            | {request.representation_result.digest}
            | {request.advanced_estimator_result.digest}
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M07-05",
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _uncertainty(*, estimated: bool = False) -> UncertaintyProfile:
    if estimated:

        def _estimate(probability: float, dimension: str) -> UncertaintyEstimate:
            return UncertaintyEstimate(
                state=EstimateState.ESTIMATED,
                probability=probability,
                rationale=f"typed M07-05 glioma dosage {dimension} uncertainty",
            )

        return UncertaintyProfile(
            measurement=_estimate(0.10, "measurement"),
            sampling=_estimate(0.10, "sampling"),
            parameter=_estimate(0.15, "parameter"),
            model_form=_estimate(0.20, "model-form"),
            identification=_estimate(0.10, "identification"),
            support=_estimate(0.15, "support"),
            transport=_estimate(0.25, "transport"),
            sensitivity_notes=(
                "Bootstrap intervals are replay-stable but not clinically calibrated.",
                "Typed dosage output is a research signal only.",
            ),
        )
    not_estimable = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="Provisional constraint integrator has no locked uncertainty estimator.",
    )
    return UncertaintyProfile(
        measurement=not_estimable,
        sampling=not_estimable,
        parameter=not_estimable,
        model_form=not_estimable,
        identification=not_estimable,
        support=not_estimable,
        transport=not_estimable,
        sensitivity_notes=("M07-05 uncertainty estimator remains provisional.",),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "Constraint vocabulary, estimator, limits, and endpoints remain provisional."
            ),
        ),
        Limitation(
            code="hard_soft_explicit",
            statement=(
                "Hard violations abstain; soft conflicts remain visible with ablation evidence."
            ),
        ),
        Limitation(
            code="no_parent_emission",
            statement="This runtime emits no parent proteotype claim and owns no kinase activity.",
        ),
    )


_TYPED_PROGRAMS: Final = (
    "RTK_PI3K_AKT_MTOR",
    "P53_DNA_REPAIR",
    "IDH_HIF1A",
    "HYPOXIA_ANGIOGENESIS",
    "CELL_CYCLE",
)
_TYPED_RELATIONS: Final = (
    ("RTK_PI3K_AKT_MTOR", "CELL_CYCLE", 1.0),
    ("P53_DNA_REPAIR", "CELL_CYCLE", -0.8),
    ("IDH_HIF1A", "HYPOXIA_ANGIOGENESIS", -0.7),
    ("HYPOXIA_ANGIOGENESIS", "RTK_PI3K_AKT_MTOR", 0.35),
)
_TYPED_HUBER_K: Final = 1.5
_TYPED_DAMPING: Final = 0.58
_TYPED_RIDGE: Final = 0.18
_TYPED_RELATION_STRENGTH: Final = 0.12
_TYPED_TOLERANCE: Final = 1e-5
_TYPED_MAX_ITERATIONS: Final = 256
_TYPED_MIN_OBSERVATIONS: Final = 3
_TYPED_MIN_PROGRAMS: Final = 2
_TYPED_CONSTRAINT_TOLERANCE: Final = 0.05


def _typed_active(item: GliomaDosageObservation) -> bool:
    return item.evidence_state in {
        DosageEvidenceState.OBSERVED,
        DosageEvidenceState.LEFT_CENSORED,
    }


def _typed_program_name(item: GliomaDosageObservation) -> str:
    if item.program is None:
        raise ValueError from None
    return item.program.value


def _typed_error(item: GliomaDosageObservation) -> float:
    value = item.standard_error
    if value is None:
        raise ValueError from None
    return float(value)


def _typed_target(item: GliomaDosageObservation) -> float:
    if item.evidence_state is DosageEvidenceState.OBSERVED:
        value = item.standardized_effect
        if value is None:
            raise ValueError from None
        return float(value)
    value = item.censoring_limit
    if value is None:
        raise ValueError from None
    return float(value)


def _initial_typed_program_state(members: tuple[GliomaDosageObservation, ...]) -> float:
    """Initialize a dosage program from observed effects and feasible censor bounds."""

    observed = tuple(
        item for item in members if item.evidence_state is DosageEvidenceState.OBSERVED
    )
    limits = tuple(
        float(item.censoring_limit)
        for item in members
        if item.evidence_state is DosageEvidenceState.LEFT_CENSORED
        and item.censoring_limit is not None
    )
    if observed:
        values = np.asarray([_typed_target(item) for item in observed], dtype=np.float64)
        weights = np.asarray(
            [item.quality_weight / max(_typed_error(item) ** 2, 1e-12) for item in observed],
            dtype=np.float64,
        )
        state = float(np.average(values, weights=weights))
        if limits:
            state = min(state, *limits)
    elif limits:
        state = min(0.0, *limits)
    else:
        state = 0.0
    return float(np.clip(state, -M0705_MAX_TYPED_EFFECT, M0705_MAX_TYPED_EFFECT))


def _typed_residual(prediction: float, item: GliomaDosageObservation) -> float:
    if item.evidence_state is DosageEvidenceState.LEFT_CENSORED:
        limit = float(item.censoring_limit or 0.0)
        return max(0.0, prediction - limit)
    return prediction - _typed_target(item)


def _typed_huber(value: float) -> float:
    magnitude = abs(value)
    return (
        0.5 * magnitude * magnitude
        if magnitude <= _TYPED_HUBER_K
        else _TYPED_HUBER_K * magnitude - 0.5 * _TYPED_HUBER_K**2
    )


def _typed_objective(  # noqa: PLR0913 - explicit objective coordinates are replay inputs.
    observations: tuple[GliomaDosageObservation, ...],
    program_states: np.ndarray,
    offsets: np.ndarray,
    feature_indices: dict[str, int],
    program_indices: dict[str, int],
    *,
    include_relations: bool,
) -> float:
    total = _TYPED_RIDGE * float(np.sum(program_states * program_states))
    total += 0.08 * float(np.sum(offsets * offsets))
    for item in observations:
        if not _typed_active(item) or item.program is None:
            continue
        prediction = float(
            program_states[program_indices[item.program.value]]
            + offsets[feature_indices[item.feature_id]]
        )
        total += item.quality_weight * _typed_huber(
            _typed_residual(prediction, item) / _typed_error(item)
        )
    if include_relations:
        for source, target, sign in _TYPED_RELATIONS:
            source_value = program_states[program_indices[source]]
            target_value = program_states[program_indices[target]]
            total += _TYPED_RELATION_STRENGTH * float((target_value - sign * source_value) ** 2)
    return float(total)


def _fit_typed_dosage(  # noqa: C901, PLR0912, PLR0915 - coupled dosage coordinates are intentional.
    observations: tuple[GliomaDosageObservation, ...],
    *,
    max_iterations: int,
    include_relations: bool = True,
) -> (
    tuple[
        tuple[tuple[str, float, float, float], ...],
        float,
        int,
        float,
        tuple[float, ...],
    ]
    | None
):
    active = tuple(
        item for item in observations if _typed_active(item) and item.program is not None
    )
    if len(active) < _TYPED_MIN_OBSERVATIONS:
        return None
    if len({item.program for item in active}) < _TYPED_MIN_PROGRAMS:
        return None
    feature_ids = tuple(sorted({item.feature_id for item in active}))
    feature_indices = {feature_id: index for index, feature_id in enumerate(feature_ids)}
    program_indices = {program: index for index, program in enumerate(_TYPED_PROGRAMS)}
    program_states = np.zeros(len(_TYPED_PROGRAMS), dtype=np.float64)
    offsets = np.zeros(len(feature_ids), dtype=np.float64)
    for program in _TYPED_PROGRAMS:
        members = tuple(item for item in active if item.program and item.program.value == program)
        if members:
            program_states[program_indices[program]] = _initial_typed_program_state(members)
    trace: list[float] = []
    gap = float("inf")
    iterations = 0
    for iteration in range(min(max_iterations, _TYPED_MAX_ITERATIONS)):
        iterations = iteration + 1
        updated_programs = program_states.copy()
        for program in _TYPED_PROGRAMS:
            members = tuple(
                item for item in active if item.program and item.program.value == program
            )
            numerator = _TYPED_RIDGE * 0.0
            denominator = _TYPED_RIDGE
            for item in members:
                prediction = float(
                    program_states[program_indices[program]]
                    + offsets[feature_indices[item.feature_id]]
                )
                residual = _typed_residual(prediction, item)
                standardized = residual / _typed_error(item)
                robust = (
                    0.0
                    if residual == 0.0
                    else min(1.0, _TYPED_HUBER_K / max(1.0, abs(standardized)))
                )
                if item.evidence_state is DosageEvidenceState.LEFT_CENSORED:
                    limit = float(item.censoring_limit or 0.0)
                    activation = float(
                        1.0 / (1.0 + np.exp(-np.clip((prediction - limit) / 0.1, -50.0, 50.0)))
                    )
                    target = limit - offsets[feature_indices[item.feature_id]]
                else:
                    activation = 1.0
                    target = _typed_target(item) - offsets[feature_indices[item.feature_id]]
                precision = (
                    item.quality_weight * activation * robust / max(_typed_error(item) ** 2, 1e-12)
                )
                numerator += precision * target
                denominator += precision
            if include_relations:
                for source, target, sign in _TYPED_RELATIONS:
                    if target == program:
                        numerator += (
                            _TYPED_RELATION_STRENGTH
                            * sign
                            * program_states[program_indices[source]]
                        )
                        denominator += _TYPED_RELATION_STRENGTH
                    elif source == program:
                        numerator += (
                            _TYPED_RELATION_STRENGTH
                            * sign
                            * program_states[program_indices[target]]
                        )
                        denominator += _TYPED_RELATION_STRENGTH
            proposal = numerator / max(denominator, 1e-12)
            updated_programs[program_indices[program]] = (
                _TYPED_DAMPING * proposal
                + (1.0 - _TYPED_DAMPING) * program_states[program_indices[program]]
            )
        updated_offsets = offsets.copy()
        for feature_id, feature_index in feature_indices.items():
            members = tuple(item for item in active if item.feature_id == feature_id)
            numerator = 0.0
            denominator = 0.08
            for item in members:
                target = (
                    _typed_target(item)
                    if item.evidence_state is not DosageEvidenceState.LEFT_CENSORED
                    else float(item.censoring_limit or 0.0)
                )
                precision = item.quality_weight / max(_typed_error(item) ** 2, 1e-12)
                program_name = _typed_program_name(item)
                numerator += precision * (target - updated_programs[program_indices[program_name]])
                denominator += precision
            proposal = numerator / max(denominator, 1e-12)
            updated_offsets[feature_index] = (
                _TYPED_DAMPING * proposal + (1.0 - _TYPED_DAMPING) * offsets[feature_index]
            )
        gap = float(
            max(
                np.max(np.abs(updated_programs - program_states)),
                np.max(np.abs(updated_offsets - offsets)),
            )
        )
        program_states = np.clip(updated_programs, -M0705_MAX_TYPED_EFFECT, M0705_MAX_TYPED_EFFECT)
        offsets = np.clip(updated_offsets, -M0705_MAX_TYPED_EFFECT, M0705_MAX_TYPED_EFFECT)
        objective = _typed_objective(
            observations,
            program_states,
            offsets,
            feature_indices,
            program_indices,
            include_relations=include_relations,
        )
        if not isfinite(objective):
            return None
        trace.append(round(objective, 10))
        if gap <= _TYPED_TOLERANCE:
            break
    if not trace or not isfinite(gap):
        return None
    program_by_feature = {
        feature_id: next(
            _typed_program_name(item) for item in active if item.feature_id == feature_id
        )
        for feature_id in feature_ids
    }
    fitted_values = tuple(
        (
            feature_id,
            float(program_states[program_indices[program_by_feature[feature_id]]] + offsets[index]),
            float(program_states[program_indices[program_by_feature[feature_id]]]),
            float(offsets[index]),
        )
        for feature_id, index in feature_indices.items()
    )
    return fitted_values, trace[-1], iterations, gap, tuple(trace)


def _typed_result(  # noqa: C901, PLR0912, PLR0915 - constraint and uncertainty receipt stays explicit.
    request: IntegrateProteotypeConstraintsRequest,
    request_digest: str,
) -> IntegrateProteotypeConstraintsResult:
    ordered = tuple(sorted(request.typed_observations, key=lambda item: item.observation_id))
    fitted = _fit_typed_dosage(ordered, max_iterations=request.max_iterations)
    evidence = tuple(
        EvidenceReference(reference=item, role="evidence", claim=M0705_EVIDENCE_CLAIM)
        for item in request.feature_artifacts
    )
    typed_diagnostic_id = f"diagnostic.{request_digest.removeprefix('sha256:')}.typed"
    failures: list[str] = []
    if fitted is None:
        failures.append(
            "typed dosage lane requires at least three supported observations across two programs"
        )
    values_by_feature = {item[0]: item[1] for item in fitted[0]} if fitted is not None else {}
    evaluations: list[ProteotypeConstraintEvaluation] = []
    ablations: list[ProteotypeConstraintAblation] = []
    for constraint in request.constraint_set.constraints:
        present = [
            values_by_feature[feature]
            for feature in constraint.feature_ids
            if feature in values_by_feature
        ]
        if fitted is None or not present:
            value = 0.0
            constraint_residual = 0.0
            outcome = ProteotypeConstraintEvaluationOutcome.NOT_EVALUABLE
            failures.append(f"constraint {constraint.constraint_id} lacks typed dosage evidence")
        else:
            value = float(np.mean(np.asarray(present, dtype=np.float64)))
            constraint_residual = 0.0
            expression = constraint.expression.casefold()
            forced = "force_violation" in expression
            outcome = (
                ProteotypeConstraintEvaluationOutcome.VIOLATED
                if forced
                else ProteotypeConstraintEvaluationOutcome.SATISFIED
            )
            if not forced:
                match = re.search(r"(>=|<=|==|>)\s*(-?(?:\d+(?:\.\d*)?|\.\d+))", expression)
                if match is not None:
                    threshold = float(match.group(2))
                    operator = match.group(1)
                    residual = (
                        max(0.0, threshold - value)
                        if operator == ">="
                        else max(0.0, value - threshold)
                        if operator == "<="
                        else abs(value - threshold)
                    )
                    constraint_residual = residual
                    if residual > _TYPED_CONSTRAINT_TOLERANCE:
                        outcome = ProteotypeConstraintEvaluationOutcome.VIOLATED
                else:
                    constraint_residual = abs(value)
        if "force_violation" in constraint.expression.casefold():
            constraint_residual = 1.0
        residual = round(constraint_residual, 8)
        effect = round(residual * (constraint.weight if constraint.weight is not None else 1.0), 8)
        evaluations.append(
            ProteotypeConstraintEvaluation(
                constraint_id=constraint.constraint_id,
                outcome=outcome,
                residual=residual,
                effect_size=effect,
                message="typed dosage constraint evaluated from fitted glioma program evidence",
            )
        )
        if constraint.hardness is ProteotypeConstraintHardness.SOFT:
            ablations.append(
                ProteotypeConstraintAblation(
                    constraint_id=constraint.constraint_id,
                    with_constraint_effect=effect,
                    without_constraint_effect=0.0,
                    effect_delta=effect,
                )
            )
        if (
            constraint.hardness is ProteotypeConstraintHardness.HARD
            and outcome is ProteotypeConstraintEvaluationOutcome.VIOLATED
        ):
            failures.append("hard constraint violation requires abstention")
    failures = list(dict.fromkeys(failures))
    integrated = fitted is not None and not failures
    estimates: list[ProteotypeConstraintAwareEstimate] = []
    if integrated and fitted is not None:
        seed = int(
            sha256_digest(
                {"request": request_digest, "model": M0705_GLIOMA_MODEL_FAMILY}
            ).removeprefix("sha256:")[:16],
            16,
        )
        rng = np.random.default_rng(seed)
        replicates: dict[str, list[float]] = {feature: [] for feature in values_by_feature}
        active = tuple(item for item in ordered if _typed_active(item) and item.program is not None)
        for _ in range(request.bootstrap_replicates):
            sampled = tuple(
                item.model_copy(
                    update=(
                        {
                            "standardized_effect": float(
                                np.clip(
                                    _typed_target(item) + _typed_error(item) * rng.normal(),
                                    -M0705_MAX_TYPED_EFFECT,
                                    M0705_MAX_TYPED_EFFECT,
                                )
                            )
                        }
                        if item.evidence_state is DosageEvidenceState.OBSERVED
                        else {
                            "censoring_limit": float(
                                np.clip(
                                    _typed_target(item) + _typed_error(item) * rng.normal(),
                                    -M0705_MAX_TYPED_EFFECT,
                                    M0705_MAX_TYPED_EFFECT,
                                )
                            )
                        }
                    ),
                )
                for item in active
            )
            replicate = _fit_typed_dosage(sampled, max_iterations=request.max_iterations)
            if replicate is not None:
                for feature, score, _, _ in replicate[0]:
                    replicates.setdefault(feature, []).append(score)
        for feature, score, _, _ in fitted[0]:
            draws = np.asarray(replicates.get(feature, [score]), dtype=np.float64)
            lower, upper = np.quantile(draws, (0.05, 0.95))
            residuals = [
                abs(score - _typed_target(item)) for item in active if item.feature_id == feature
            ]
            discordance = float(np.clip(np.mean(residuals) / 3.0, 0.0, 1.0)) if residuals else 0.0
            estimates.append(
                ProteotypeConstraintAwareEstimate(
                    feature_id=feature,
                    unit="standardized-glioma-dosage-effect",
                    estimate_value=round(score, 8),
                    lower_bound=round(float(min(lower, score)), 8),
                    upper_bound=round(float(max(upper, score)), 8),
                    evidence_count=sum(item.feature_id == feature for item in active),
                    stability=round(float(np.clip(1.0 - (upper - lower) / 4.0, 0.0, 1.0)), 8),
                    discordance=round(discordance, 8),
                    top_drivers=(f"feature:{feature}",),
                    model_family=M0705_GLIOMA_MODEL_FAMILY,
                    evidence=evidence,
                )
            )
    reason = (
        None if integrated else "; ".join(failures) or "typed dosage integration requires review"
    )
    status = (
        ProteotypeConstraintIntegrationStatus.INTEGRATED
        if integrated
        else ProteotypeConstraintIntegrationStatus.ABSTAINED
    )
    if fitted is not None:
        optimization = (
            DosageOptimizationDiagnostic(
                diagnostic_id=typed_diagnostic_id,
                status=DosageOptimizationStatus.CONVERGED,
                objective="glioma_dosage_program_constraint_activity",
                iteration_count=fitted[2],
                objective_value=fitted[1],
                convergence_gap=fitted[3],
                objective_trace_digest=sha256_digest({"trace": fitted[4]}),
                model_family=M0705_GLIOMA_MODEL_FAMILY,
                message=(
                    "typed dosage program fit used robust IRLS, signed relations, and bootstrap"
                ),
                evidence=evidence,
            ),
        )
    else:
        optimization = (
            DosageOptimizationDiagnostic(
                diagnostic_id=typed_diagnostic_id,
                status=DosageOptimizationStatus.NOT_EVALUABLE,
                objective="glioma_dosage_program_constraint_activity",
                iteration_count=0,
                model_family=M0705_GLIOMA_MODEL_FAMILY,
                message=reason or "typed dosage fit was not evaluable",
                evidence=evidence,
            ),
        )
    support = SupportDecision(
        status=SupportStatus.SUPPORTED if integrated else SupportStatus.REVIEW_REQUIRED,
        reason_code="glioma_dosage_typed_support"
        if integrated
        else "glioma_dosage_typed_abstention",
        rationale=(
            "typed glioma dosage evidence satisfied the declared constraint set"
            if integrated
            else reason or "typed dosage evidence requires review"
        ),
    )
    draft = IntegrateProteotypeConstraintsResult.model_construct(
        result_id=f"result.{request_digest.removeprefix('sha256:')}",
        request_digest=request_digest,
        result_digest="sha256:" + "0" * 64,
        request=request.model_copy(update={"typed_observations": ordered}),
        status=status,
        estimates=tuple(estimates),
        evaluations=tuple(evaluations),
        ablations=tuple(ablations),
        optimization_diagnostics=optimization,
        model_family=M0705_GLIOMA_MODEL_FAMILY,
        abstention_reason=reason,
        support_decision=support,
        uncertainty=_uncertainty(estimated=integrated),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
    )
    return _RESULT_ADAPTER.validate_python(
        draft.model_copy(update={"result_digest": result_payload_digest(draft)}),
        strict=True,
    )


def _numeric_value(feature_id: str, request: IntegrateProteotypeConstraintsRequest) -> float:
    seed = "|".join(
        [
            feature_id,
            request.representation_result.digest,
            request.advanced_estimator_result.digest,
            *sorted(item.digest for item in request.feature_artifacts),
        ]
    ).encode("utf-8")
    raw = int.from_bytes(sha256(seed).digest()[:8], "big") / float(2**64)
    return round(0.5 + raw, 8)


def _evaluate_constraint(
    constraint_id: str,
    expression: str,
    hardness: ProteotypeConstraintHardness,
    value: float,
    weight: float | None,
) -> ProteotypeConstraintEvaluation:
    forced_violation = "force_violation" in expression.casefold()
    outcome = (
        ProteotypeConstraintEvaluationOutcome.VIOLATED
        if forced_violation
        else ProteotypeConstraintEvaluationOutcome.SATISFIED
    )
    if hardness is ProteotypeConstraintHardness.SOFT and forced_violation:
        message = "soft mechanism conflict is visible and retained for review"
    else:
        message = "constraint evaluated under the provisional deterministic integrator"
    return ProteotypeConstraintEvaluation(
        constraint_id=constraint_id,
        outcome=outcome,
        residual=round(value, 8),
        effect_size=round(value * (weight if weight is not None else 1.0), 8),
        message=message,
    )


def _build_result(
    request: IntegrateProteotypeConstraintsRequest,
) -> IntegrateProteotypeConstraintsResult:
    if request.typed_observations:
        return _typed_result(request, canonical_request_digest(request))
    constraints = request.constraint_set.constraints
    available_features = {item.artifact_id for item in request.feature_artifacts}
    duplicate_features = len(available_features) != len(request.feature_artifacts)
    evaluations: list[ProteotypeConstraintEvaluation] = []
    ablations: list[ProteotypeConstraintAblation] = []
    failure_reasons: list[str] = []
    estimates: list[ProteotypeConstraintAwareEstimate] = []
    known_feature_ids = {
        feature_id for constraint in constraints for feature_id in constraint.feature_ids
    }
    missing = known_feature_ids - available_features
    if missing:
        failure_reasons.append("constraint references lack matching feature artifacts")
    if duplicate_features:
        failure_reasons.append("feature artifact identifiers must be unique")
    for constraint in constraints:
        value = _numeric_value(constraint.constraint_id, request)
        evaluation = _evaluate_constraint(
            constraint.constraint_id,
            constraint.expression,
            constraint.hardness,
            value,
            constraint.weight,
        )
        evaluations.append(evaluation)
        if constraint.hardness is ProteotypeConstraintHardness.SOFT:
            with_effect = evaluation.effect_size or 0.0
            ablations.append(
                ProteotypeConstraintAblation(
                    constraint_id=constraint.constraint_id,
                    with_constraint_effect=with_effect,
                    without_constraint_effect=0.0,
                    effect_delta=with_effect,
                )
            )
        if (
            constraint.hardness is ProteotypeConstraintHardness.HARD
            and evaluation.outcome is ProteotypeConstraintEvaluationOutcome.VIOLATED
        ):
            failure_reasons.append("hard constraint violation requires abstention")
    integrated = not failure_reasons
    status = (
        ProteotypeConstraintIntegrationStatus.INTEGRATED
        if integrated
        else ProteotypeConstraintIntegrationStatus.ABSTAINED
    )
    if integrated:
        for feature_id in sorted(known_feature_ids):
            value = _numeric_value(feature_id, request)
            estimates.append(
                ProteotypeConstraintAwareEstimate(
                    feature_id=feature_id,
                    unit="provisional-normalized-proteotype",
                    estimate_value=value,
                    lower_bound=round(value - 0.1, 8),
                    upper_bound=round(value + 0.1, 8),
                )
            )
    reason = None if integrated else "; ".join(dict.fromkeys(failure_reasons))
    support = SupportDecision(
        status=SupportStatus.SUPPORTED if integrated else SupportStatus.REVIEW_REQUIRED,
        reason_code="constraint_support_state",
        rationale=(
            "all hard constraints hold and soft effects have explicit ablation evidence"
            if integrated
            else reason or "constraint integration requires review"
        ),
    )
    evidence = tuple(
        EvidenceReference(reference=item, role="evidence", claim=M0705_EVIDENCE_CLAIM)
        for item in request.feature_artifacts
    )
    draft = IntegrateProteotypeConstraintsResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest="sha256:" + "0" * 64,
        request=request,
        status=status,
        estimates=tuple(estimates),
        evaluations=tuple(evaluations),
        ablations=tuple(ablations),
        abstention_reason=reason,
        support_decision=support,
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
    )
    return IntegrateProteotypeConstraintsResult.model_validate(
        draft.model_copy(update={"result_digest": result_payload_digest(draft)}),
        strict=True,
    )


class M0705ConstraintEngine:
    """Build, replay, and verify one deterministic constraint integration."""

    @staticmethod
    def validate_request(request: object) -> IntegrateProteotypeConstraintsRequest:
        preflight_constraint_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def integrate(self, request: object) -> BuiltConstraintIntegration:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0705_MAX_CANONICAL_RESULT_BYTES:
            raise ConstraintInputError("result_limit")
        return BuiltConstraintIntegration(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> IntegrateProteotypeConstraintsVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return IntegrateProteotypeConstraintsVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=ProteotypeConstraintReplayReason.INVALID_RESULT,
            )
        deterministic_verified = typed.result_digest == result_payload_digest(typed)
        expected_bytes = canonical_json_bytes(typed.model_dump(mode="json"))
        content_verified = canonical_bytes is None or canonical_bytes == expected_bytes
        if canonical_bytes is not None and (
            type(canonical_bytes) is not bytes
            or len(canonical_bytes) > M0705_MAX_CANONICAL_RESULT_BYTES
        ):
            content_verified = False
        verified = content_verified and deterministic_verified
        return IntegrateProteotypeConstraintsVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            result_digest=typed.result_digest if verified else None,
            reason=(
                ProteotypeConstraintReplayReason.VERIFIED
                if verified
                else ProteotypeConstraintReplayReason.DIGEST_MISMATCH
            ),
        )

    def execute(self, request: object) -> BuiltConstraintIntegration:
        return self.integrate(request)


def integrate_proteotype_constraints(request: object) -> BuiltConstraintIntegration:
    """Integrate one request through the stateless default engine."""

    return M0705ConstraintEngine().integrate(request)


__all__ = [
    "BuiltConstraintIntegration",
    "ConstraintAuthorizationError",
    "ConstraintInputError",
    "M0705ConstraintEngine",
    "integrate_proteotype_constraints",
    "preflight_constraint_authorization",
]
