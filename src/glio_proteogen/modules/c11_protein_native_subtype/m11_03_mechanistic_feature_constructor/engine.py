"""Deterministic, evidence-preserving M11-03 feature construction runtime."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, cast

from pydantic import ValidationError

from glio_proteogen.contracts.m11_03 import (
    M1103_CONTRACT_VERSION,
    M1103_EVIDENCE_CLAIM,
    M1103_GLIOMA_MODEL_FAMILY,
    M1103_MODULE_ID,
    M1103_PARENT,
    ConstructVariantPeptideMechanisticFeaturesRequest,
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
    VariantPeptideMechanisticFeatureResult,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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
from glio_proteogen.kernel.strict_json import strict_json_loads

if TYPE_CHECKING:
    from collections.abc import Mapping

_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_AUTHORIZED_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_FAIL_MARKERS: Final = ("fail", "invalid", "missing", "unknown", "unsupported")
_M1103_MIN_SCALE: Final = 1e-6
_M1103_HUBER_DELTA: Final = 1.5
_M1103_RIDGE: Final = 0.03
_M1103_DAMPING: Final = 0.7
_M1103_SOLVER_ITERATIONS: Final = 256
_M1103_SOLVER_TOLERANCE: Final = 1e-5
_M1103_OBJECTIVE_TOLERANCE: Final = 1e-10
_M1103_BACKTRACKING_STEPS: Final = 18
_M1103_BACKTRACKING_FACTOR: Final = 0.5
_M1103_LOW_QUANTILE: Final = 0.05
_M1103_HIGH_QUANTILE: Final = 0.95
_M1103_SCORE_LIMIT: Final = 8.0
_M1103_MIN_NUMERIC_FEATURES: Final = 2


@dataclass(frozen=True, slots=True)
class _GliomaFit:
    feature_ids: tuple[str, ...]
    values: tuple[float, ...]
    objective: float
    iterations: int
    converged: bool


def _is_glioma_model(request: ConstructVariantPeptideMechanisticFeaturesRequest) -> bool:
    return request.configuration.model_family == M1103_GLIOMA_MODEL_FAMILY


def _median(values: tuple[float, ...]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2.0


def _robust_location_scale(values: tuple[float, ...]) -> tuple[float, float]:
    center = _median(values)
    mad = _median(tuple(abs(value - center) for value in values))
    return center, max(_M1103_MIN_SCALE, 1.4826 * mad if mad > _M1103_MIN_SCALE else 1.0)


def _hash_normal(material: str) -> float:
    def uniform(suffix: str) -> float:
        digest = hashlib.sha256((material + suffix).encode("utf-8")).digest()
        return (int.from_bytes(digest[:8], "big") + 1.0) / (2.0**64 + 1.0)

    first = max(_M1103_MIN_SCALE, uniform(":u1"))
    second = uniform(":u2")
    return math.sqrt(-2.0 * math.log(first)) * math.cos(2.0 * math.pi * second)


def _feature_numeric(feature: MechanisticFeature) -> tuple[float, float] | None:
    if feature.value_kind is MechanisticValueKind.SCALAR and feature.scalar_value is not None:
        return feature.scalar_value, 1.0
    if (
        feature.value_kind is MechanisticValueKind.INTERVAL
        and feature.lower_bound is not None
        and feature.upper_bound is not None
    ):
        midpoint = (feature.lower_bound + feature.upper_bound) / 2.0
        half_width = max(_M1103_MIN_SCALE, (feature.upper_bound - feature.lower_bound) / 2.0)
        return midpoint, half_width
    return None


def _relation_sign(relation: MechanisticRelation) -> float | None:
    # The provisional contract keeps relation weights optional for callers
    # that only declare topology. Numeric glioma fitting cannot turn absent
    # topology evidence into an invented edge magnitude.
    if relation.weight is None or not math.isfinite(relation.weight):
        return None
    coefficient: float | None
    if relation.kind is MechanisticRelationKind.REGULATES:
        coefficient = 1.0 if relation.weight >= 0.0 else -1.0
    else:
        signs = {
            MechanisticRelationKind.INHIBITS: -1.0,
            MechanisticRelationKind.ACTIVATES: 1.0,
            MechanisticRelationKind.PARTICIPATES: 1.0,
            MechanisticRelationKind.PRECEDES: 1.0,
            MechanisticRelationKind.COLOCALIZES: 1.0,
        }
        coefficient = signs.get(relation.kind)
    if coefficient is None:
        return None
    return coefficient * max(_M1103_MIN_SCALE, abs(relation.weight))


def _huber_loss(value: float) -> float:
    absolute = abs(value)
    return (
        0.5 * value * value
        if absolute <= _M1103_HUBER_DELTA
        else _M1103_HUBER_DELTA * (absolute - 0.5 * _M1103_HUBER_DELTA)
    )


def _glioma_objective(
    values: list[float],
    targets: tuple[float, ...],
    uncertainties: tuple[float, ...],
    relations: tuple[tuple[int, int, float], ...],
) -> float:
    objective = _M1103_RIDGE * sum(value * value for value in values)
    for value, target, uncertainty in zip(values, targets, uncertainties, strict=True):
        objective += _huber_loss((value - target) / max(_M1103_MIN_SCALE, uncertainty))
    for source, target, coefficient in relations:
        objective += 0.5 * (values[target] - coefficient * values[source]) ** 2
    return objective


def _fit_glioma(  # noqa: C901, PLR0912, PLR0915 - solver safeguards are explicit.
    features: tuple[MechanisticFeature, ...],
    relations: tuple[MechanisticRelation, ...],
    *,
    perturbation: Mapping[str, float] | None = None,
) -> _GliomaFit | None:
    numeric: list[tuple[MechanisticFeature, float, float]] = []
    for feature in sorted(features, key=lambda item: item.feature_id):
        measured = _feature_numeric(feature)
        if measured is not None:
            value, uncertainty = measured
            if perturbation is not None:
                value += perturbation.get(feature.feature_id, 0.0)
            numeric.append((feature, value, uncertainty))
    if len(numeric) < _M1103_MIN_NUMERIC_FEATURES:
        return None
    index = {feature.feature_id: position for position, (feature, _, _) in enumerate(numeric)}
    edge_terms = tuple(
        (index[item.source_feature_id], index[item.target_feature_id], coefficient)
        for item in relations
        if item.source_feature_id in index
        and item.target_feature_id in index
        and (coefficient := _relation_sign(item)) is not None
    )
    if not edge_terms:
        return None
    center, scale = _robust_location_scale(tuple(value for _, value, _ in numeric))
    targets = tuple(
        max(_M1103_SCORE_LIMIT, min(_M1103_SCORE_LIMIT, (value - center) / scale))
        for _, value, _ in numeric
    )
    uncertainties = tuple(
        max(_M1103_MIN_SCALE, uncertainty / scale) for _, _, uncertainty in numeric
    )
    values = list(targets)
    initial_objective = _glioma_objective(values, targets, uncertainties, edge_terms)
    if not math.isfinite(initial_objective):
        return _GliomaFit(
            feature_ids=tuple(feature.feature_id for feature, _, _ in numeric),
            values=tuple(float(f"{value:.8f}") for value in values),
            objective=0.0,
            iterations=0,
            converged=False,
        )
    objective = initial_objective
    for iteration in range(1, _M1103_SOLVER_ITERATIONS + 1):
        previous = values.copy()
        proposals = previous.copy()
        for position in range(len(values)):
            current = previous[position]
            gradient = 2.0 * _M1103_RIDGE * current
            hessian = 2.0 * _M1103_RIDGE
            residual = (current - targets[position]) / uncertainties[position]
            absolute = abs(residual)
            huber_weight = (
                1.0
                if absolute <= _M1103_HUBER_DELTA
                else _M1103_HUBER_DELTA / max(_M1103_MIN_SCALE, absolute)
            )
            information = huber_weight / (uncertainties[position] ** 2)
            gradient += information * (current - targets[position])
            hessian += information
            for source, target, coefficient in edge_terms:
                if position == source:
                    edge_residual = previous[target] - coefficient * current
                    gradient += -coefficient * edge_residual
                    hessian += coefficient * coefficient
                elif position == target:
                    edge_residual = current - coefficient * previous[source]
                    gradient += edge_residual
                    hessian += 1.0
            proposal = current - gradient / max(_M1103_MIN_SCALE, hessian)
            proposals[position] = current + _M1103_DAMPING * (proposal - current)
        next_objective = _glioma_objective(proposals, targets, uncertainties, edge_terms)
        accepted = proposals
        if not math.isfinite(next_objective) or (
            next_objective > objective + _M1103_OBJECTIVE_TOLERANCE
        ):
            accepted = previous.copy()
            next_objective = objective
            delta = [after - before for after, before in zip(proposals, previous, strict=True)]
            step = _M1103_DAMPING
            for _ in range(_M1103_BACKTRACKING_STEPS):
                step *= _M1103_BACKTRACKING_FACTOR
                trial = [
                    before + step * change
                    for before, change in zip(previous, delta, strict=True)
                ]
                trial_objective = _glioma_objective(trial, targets, uncertainties, edge_terms)
                if math.isfinite(trial_objective) and (
                    trial_objective <= objective + _M1103_OBJECTIVE_TOLERANCE
                ):
                    accepted = trial
                    next_objective = trial_objective
                    break
            else:
                return _GliomaFit(
                    feature_ids=tuple(feature.feature_id for feature, _, _ in numeric),
                    values=tuple(float(f"{value:.8f}") for value in previous),
                    objective=float(f"{objective:.8f}"),
                    iterations=iteration,
                    converged=False,
                )
        values = accepted
        update = max(abs(after - before) for after, before in zip(values, previous, strict=True))
        if update <= _M1103_SOLVER_TOLERANCE and abs(objective - next_objective) <= (
            2.0 * _M1103_SOLVER_TOLERANCE
        ):
            return _GliomaFit(
                feature_ids=tuple(feature.feature_id for feature, _, _ in numeric),
                values=tuple(float(f"{value:.8f}") for value in values),
                objective=float(f"{next_objective:.8f}"),
                iterations=iteration,
                converged=True,
            )
        objective = next_objective
    return _GliomaFit(
        feature_ids=tuple(feature.feature_id for feature, _, _ in numeric),
        values=tuple(float(f"{value:.8f}") for value in values),
        objective=float(f"{objective:.8f}"),
        iterations=_M1103_SOLVER_ITERATIONS,
        converged=False,
    )


def _quantile(values: tuple[float, ...], probability: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return float(f"{ordered[index]:.8f}")


def _typed_model_failure(
    request: ConstructVariantPeptideMechanisticFeaturesRequest,
) -> str | None:
    if not _is_glioma_model(request):
        return None
    numeric = tuple(
        item for item in request.declared_features if _feature_numeric(item) is not None
    )
    if len(numeric) < _M1103_MIN_NUMERIC_FEATURES:
        return "typed glioma model requires at least two numeric features"
    fit = _fit_glioma(request.declared_features, request.declared_relations)
    if fit is None:
        return "typed glioma model requires a signed relation between numeric features"
    if not fit.converged:
        return "typed glioma signed feature graph did not converge"
    return None


def _typed_feature_projection(  # noqa: C901 - projection, bootstrap, and lineage stay auditable.
    request: ConstructVariantPeptideMechanisticFeaturesRequest,
    request_hash: str,
) -> tuple[tuple[MechanisticFeature, ...], _GliomaFit, tuple[float, float]]:
    fit = _fit_glioma(request.declared_features, request.declared_relations)
    if fit is None or not fit.converged:
        raise ValueError(  # noqa: TRY003 - this cannot cross the service boundary.
            "typed glioma model cannot construct a feature projection"
        )
    numeric_values: list[tuple[MechanisticFeature, float, float]] = []
    for feature in sorted(request.declared_features, key=lambda item: item.feature_id):
        measured = _feature_numeric(feature)
        if measured is not None:
            numeric_values.append((feature, measured[0], measured[1]))
    numeric = tuple(numeric_values)
    center, scale = _robust_location_scale(tuple(value for _, value, _ in numeric))
    index = {feature_id: position for position, feature_id in enumerate(fit.feature_ids)}
    aggregate_draws: list[float] = []
    for draw in range(request.configuration.bootstrap_replicates):
        perturbation = {
            feature.feature_id: uncertainty
            * _hash_normal(f"{request_hash}:{draw}:{feature.feature_id}")
            for feature, _, uncertainty in numeric
        }
        draw_fit = _fit_glioma(
            request.declared_features,
            request.declared_relations,
            perturbation=perturbation,
        )
        if draw_fit is None or not draw_fit.converged:
            raise ValueError(  # noqa: TRY003 - this cannot cross the service boundary.
                "typed glioma bootstrap fit did not converge"
            )
        aggregate_draws.append(sum(draw_fit.values) / max(_M1103_MIN_SCALE, len(draw_fit.values)))

    def lineage(feature_id: str, claim: str) -> MechanisticFeatureLineage:
        return MechanisticFeatureLineage(
            feature_id=feature_id,
            source_artifacts=request.source_artifacts,
            claim=claim,
            transformation_ids=request.configuration.transformation_ids,
        )

    projected: list[MechanisticFeature] = []
    for feature in request.declared_features:
        measured = _feature_numeric(feature)
        if measured is None:
            projected.append(feature)
            continue
        position = index[feature.feature_id]
        latent = center + scale * fit.values[position]
        if feature.value_kind is MechanisticValueKind.SCALAR:
            projected.append(feature.model_copy(update={"scalar_value": float(f"{latent:.8f}")}))
        else:
            half_width = max(_M1103_MIN_SCALE, measured[1])
            projected.append(
                feature.model_copy(
                    update={
                        "lower_bound": float(f"{latent - half_width:.8f}"),
                        "upper_bound": float(f"{latent + half_width:.8f}"),
                    }
                )
            )
    aggregate = sum(fit.values) / max(_M1103_MIN_SCALE, len(fit.values))
    lower = min(_quantile(tuple(aggregate_draws), _M1103_LOW_QUANTILE), aggregate)
    upper = max(_quantile(tuple(aggregate_draws), _M1103_HIGH_QUANTILE), aggregate)
    existing_ids = {feature.feature_id for feature in projected}
    state_id = "feature.glioma.signed_state"
    interval_id = "feature.glioma.state_interval"
    if state_id in existing_ids:
        state_id = "feature.glioma.signed_state.derived"
    if interval_id in existing_ids or interval_id == state_id:
        interval_id = "feature.glioma.state_interval.derived"
    evidence = _evidence(request)
    projected.extend(
        (
            MechanisticFeature(
                feature_id=state_id,
                version=request.configuration.version,
                kind=MechanisticFeatureKind.STATE,
                value_kind=MechanisticValueKind.SCALAR,
                unit="standardized_glioma_effect",
                scalar_value=float(f"{aggregate:.8f}"),
                lineage=lineage(
                    state_id,
                    "Robust signed state from the glioma mechanistic feature graph.",
                ),
                evidence=evidence,
            ),
            MechanisticFeature(
                feature_id=interval_id,
                version=request.configuration.version,
                kind=MechanisticFeatureKind.STATE,
                value_kind=MechanisticValueKind.INTERVAL,
                unit="standardized_glioma_effect",
                lower_bound=lower,
                upper_bound=upper,
                lineage=lineage(
                    interval_id,
                    "Digest-seeded bootstrap interval for the signed glioma state.",
                ),
                evidence=evidence,
            ),
        )
    )
    return tuple(projected), fit, (lower, upper)


class M1103AuthorizationError(PermissionError):
    """Raised before any upstream or opaque evidence reference is traversed."""

    def __init__(self) -> None:
        super().__init__(
            "M11-03 requires accepted identity, consent, quality, support, and use controls"
        )


class _InvalidRequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M11-03 request must be an exact contract type or plain JSON object")


def preflight_m1103_authorization(candidate: object) -> None:
    """Check the seven caller-declared controls without reading evidence payloads."""

    states: dict[str, str] | None = None
    if type(candidate) is ConstructVariantPeptideMechanisticFeaturesRequest:
        references = candidate.context.references
        states = {
            "approved_configuration": references.approved_configuration.state.value,
            "identity_lineage": references.identity_lineage.state.value,
            "provenance": references.provenance.state.value,
            "consent": references.consent.state.value,
            "quality": references.quality.state.value,
            "support": references.support.state.value,
            "intended_use": references.intended_use.state.value,
        }
    elif type(candidate) is dict:
        raw = cast("dict[object, object]", candidate)
        context = raw.get("context")
        refs = context.get("references") if type(context) is dict else None
        if type(refs) is dict:
            ref_map = cast("dict[object, object]", refs)
            states = {}
            for role in _AUTHORIZED_STATES:
                item = ref_map.get(role)
                state = item.get("state") if type(item) is dict else None
                if type(state) is not str:
                    states = None
                    break
                states[role] = state
    if states != _AUTHORIZED_STATES:
        raise M1103AuthorizationError


def _validate_request(candidate: object) -> ConstructVariantPeptideMechanisticFeaturesRequest:
    if type(candidate) not in {ConstructVariantPeptideMechanisticFeaturesRequest, dict}:
        raise _InvalidRequestError
    preflight_m1103_authorization(candidate)
    if type(candidate) is ConstructVariantPeptideMechanisticFeaturesRequest:
        return ConstructVariantPeptideMechanisticFeaturesRequest.model_validate(
            candidate, strict=True
        )
    return ConstructVariantPeptideMechanisticFeaturesRequest.model_validate_json(
        canonical_json_bytes(candidate), strict=True
    )


def _validate_json_request(
    decoded: object,
    serialized: bytes | bytearray | str,
) -> ConstructVariantPeptideMechanisticFeaturesRequest:
    """Validate the exact duplicate-free JSON bytes after control preflight."""

    preflight_m1103_authorization(decoded)
    return ConstructVariantPeptideMechanisticFeaturesRequest.model_validate_json(
        serialized, strict=True
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M11-03 provisional ABI has no locked calibration for {dimension} uncertainty"
            ),
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model-form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("transport"),
        sensitivity_notes=(
            "Perturbation and topology sensitivity are declared, but calibration is not frozen.",
            "Novel or out-of-domain mechanistic states require human review.",
        ),
    )


def _controls(
    request: ConstructVariantPeptideMechanisticFeaturesRequest,
) -> tuple[ControlDecisionRecord, ...]:
    references = request.context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration, None),
        (
            ControlRole.IDENTITY_LINEAGE,
            references.identity_lineage,
            references.identity_lineage.binding_digest,
        ),
        (ControlRole.PROVENANCE, references.provenance, None),
        (ControlRole.CONSENT, references.consent, None),
        (ControlRole.QUALITY, references.quality, None),
        (ControlRole.SUPPORT, references.support, None),
        (ControlRole.INTENDED_USE, references.intended_use, None),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject,
        )
        for role, reference, subject in values
    )


def _provenance(
    request: ConstructVariantPeptideMechanisticFeaturesRequest,
    request_hash: str,
    configuration_hash: str,
) -> ProvenanceRecord:
    references = request.context.references
    controls = _controls(request)
    return ProvenanceRecord(
        activity_id=f"activity.m1103.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1103_MODULE_ID,
        module_version=M1103_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted(
                {
                    request_hash,
                    configuration_hash,
                    request.upstream_result.digest,
                    *(item.digest for item in request.source_artifacts),
                    *(item.evidence_digest for item in controls),
                }
            )
        ),
        configuration_digest=configuration_hash,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _evidence(
    request: ConstructVariantPeptideMechanisticFeaturesRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=item, role="evidence", claim=M1103_EVIDENCE_CLAIM)
        for item in (
            request.upstream_result,
            *request.source_artifacts,
            request.configuration.topology_reference,
            *request.configuration.negative_control_artifacts,
        )
    )


def _diagnostic(
    code: str, status: MechanisticDiagnosticStatus, message: str
) -> MechanisticFeatureDiagnostic:
    return MechanisticFeatureDiagnostic(
        diagnostic_id=f"diagnostic.{code}", status=status, message=message
    )


def _marker(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in _FAIL_MARKERS)


def _evaluate(  # noqa: C901 - legacy invariant checks and typed model gate are co-evaluated.
    request: ConstructVariantPeptideMechanisticFeaturesRequest,
) -> tuple[
    tuple[MechanisticFeatureDiagnostic, ...],
    tuple[MechanisticFindingCode, ...],
    str | None,
    SupportStatus,
]:
    findings: list[MechanisticFindingCode] = []
    diagnostics: list[MechanisticFeatureDiagnostic] = []
    upstream_bad = _marker(request.upstream_result.artifact_id)
    source_bad = any(_marker(item.artifact_id) for item in request.source_artifacts)
    diagnostics.append(
        _diagnostic(
            "upstream",
            MechanisticDiagnosticStatus.NOT_EVALUABLE
            if upstream_bad
            else MechanisticDiagnosticStatus.PASS,
            "Upstream M11-02 support is unavailable."
            if upstream_bad
            else "Upstream M11-02 reference is accepted.",
        )
    )
    if upstream_bad:
        findings.append(MechanisticFindingCode.UPSTREAM_UNSUPPORTED)
    if not request.declared_features:
        diagnostics.append(
            _diagnostic(
                "input",
                MechanisticDiagnosticStatus.NOT_EVALUABLE,
                "No caller-declared mechanistic features were supplied.",
            )
        )
        findings.append(MechanisticFindingCode.INPUT_INCOMPLETE)
    else:
        diagnostics.append(
            _diagnostic(
                "input", MechanisticDiagnosticStatus.PASS, "Feature declarations are present."
            )
        )
    source_keys = {
        (item.artifact_id, item.version, item.digest, item.media_type)
        for item in request.source_artifacts
    }
    transform_ids = set(request.configuration.transformation_ids)
    lineage_ok = all(
        {
            (item.artifact_id, item.version, item.digest, item.media_type) in source_keys
            for item in feature.lineage.source_artifacts
        }
        and set(feature.lineage.transformation_ids) <= transform_ids
        for feature in request.declared_features
    )
    unit_ok = all(
        feature.unit.casefold() not in {"", "unknown", "invalid", "na", "n/a"}
        for feature in request.declared_features
    )
    diagnostics.append(
        _diagnostic(
            "units",
            MechanisticDiagnosticStatus.PASS
            if unit_ok and lineage_ok
            else MechanisticDiagnosticStatus.FAIL,
            "Unit and lineage invariants pass."
            if unit_ok and lineage_ok
            else "Unit or lineage closure failed.",
        )
    )
    if not unit_ok or not lineage_ok:
        findings.append(MechanisticFindingCode.UNIT_INVARIANT_FAILED)
    topology_ok = not _marker(request.configuration.topology_reference.artifact_id)
    topology_ok = topology_ok and not any(
        _marker(item.artifact_id) for item in request.configuration.negative_control_artifacts
    )
    try:
        MechanisticFeatureObject(
            object_id="probe.m1103",
            version=M1103_CONTRACT_VERSION,
            features=request.declared_features or (),
            relations=request.declared_relations,
            configuration=request.configuration,
        )
    except (TypeError, ValueError, ValidationError):
        topology_ok = False
    diagnostics.append(
        _diagnostic(
            "topology",
            MechanisticDiagnosticStatus.PASS if topology_ok else MechanisticDiagnosticStatus.FAIL,
            "Topology and negative-control invariants pass."
            if topology_ok
            else "Topology or negative-control invariant failed.",
        )
    )
    if not topology_ok:
        findings.append(MechanisticFindingCode.TOPOLOGY_INVARIANT_FAILED)
        if any(
            _marker(item.artifact_id) for item in request.configuration.negative_control_artifacts
        ):
            findings.append(MechanisticFindingCode.NEGATIVE_CONTROL_FAILED)
    typed_failure = _typed_model_failure(request)
    if _is_glioma_model(request):
        diagnostics.append(
            _diagnostic(
                "glioma_model",
                MechanisticDiagnosticStatus.NOT_EVALUABLE
                if typed_failure is not None
                else MechanisticDiagnosticStatus.PASS,
                typed_failure
                or "Signed glioma feature graph converged with deterministic bootstrap support.",
            )
        )
        if typed_failure is not None:
            findings.append(MechanisticFindingCode.INPUT_INCOMPLETE)
    bad = (
        upstream_bad
        or source_bad
        or not request.declared_features
        or not unit_ok
        or not lineage_ok
        or not topology_ok
        or typed_failure is not None
    )
    if source_bad and MechanisticFindingCode.INPUT_INCOMPLETE not in findings:
        findings.append(MechanisticFindingCode.INPUT_INCOMPLETE)
    if bad:
        reason = (
            typed_failure
            or "; ".join(item.value for item in findings)
            or ("mechanistic invariant failed")
        )
        support = (
            SupportStatus.UNSUPPORTED
            if upstream_bad or source_bad
            else SupportStatus.REVIEW_REQUIRED
        )
        return tuple(diagnostics), tuple(dict.fromkeys(findings)), reason, support
    return tuple(diagnostics), (), None, SupportStatus.SUPPORTED


def _build_result(
    request: ConstructVariantPeptideMechanisticFeaturesRequest,
) -> VariantPeptideMechanisticFeatureResult:
    request_hash = canonical_request_digest(request)
    configuration_hash = sha256_digest(request.configuration)
    diagnostics, findings, reason, support_status = _evaluate(request)
    constructed = support_status is SupportStatus.SUPPORTED
    typed_model = _is_glioma_model(request)
    typed_fit: _GliomaFit | None = None
    projected_features = request.declared_features
    if constructed and typed_model:
        try:
            projected_features, typed_fit, _ = _typed_feature_projection(request, request_hash)
        except ValueError:
            constructed = False
            support_status = SupportStatus.REVIEW_REQUIRED
            reason = "typed glioma bootstrap projection did not converge"
            findings = tuple(dict.fromkeys((*findings, MechanisticFindingCode.INPUT_INCOMPLETE)))
    limitations = [
        Limitation(
            code="provisional_abi",
            statement=(
                "Feature catalogue and estimator ABI remain provisional pending owner confirmation."
            ),
        ),
        Limitation(
            code="no_kinase_state",
            statement=(
                "KINOPHOS owns kinase-state inference; this module emits no kinase activity."
            ),
        ),
    ]
    if typed_model:
        limitations.append(
            Limitation(
                code="typed_glioma_graph",
                statement=(
                    "The opt-in typed lane uses robust signed relation fitting and is a "
                    "research-use-only mechanistic signal."
                ),
            )
        )
    feature_object = (
        MechanisticFeatureObject(
            object_id=f"object.m1103.{request_hash.removeprefix('sha256:')}",
            version=M1103_CONTRACT_VERSION,
            features=projected_features,
            relations=request.declared_relations,
            configuration=request.configuration,
            evidence=_evidence(request),
        )
        if constructed
        else None
    )
    support = SupportDecision(
        status=support_status,
        reason_code="mechanistic_features_constructed"
        if constructed
        else "mechanistic_features_quarantined",
        rationale="All locked invariants pass."
        if constructed
        else "Feature construction is quarantined pending review.",
    )
    payload: dict[str, Any] = {
        "output_type": "variant_peptide_mechanistic_features",
        "result_id": f"result.m1103.{request_hash.removeprefix('sha256:')}",
        "result_version": M1103_CONTRACT_VERSION,
        "request_digest": request_hash,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": MechanisticConstructionStatus.CONSTRUCTED
        if constructed
        else MechanisticConstructionStatus.ABSTAINED,
        "feature_object": feature_object,
        "typed_model": typed_model,
        "model_profile": M1103_GLIOMA_MODEL_FAMILY if typed_model else None,
        "solver_iterations": typed_fit.iterations if typed_fit is not None else None,
        "solver_objective": typed_fit.objective if typed_fit is not None else None,
        "diagnostics": diagnostics,
        "findings": findings,
        "abstention_reason": reason,
        "parent_target": M1103_PARENT,
        "emits_parent": False,
        "support_decision": support,
        "uncertainty": _uncertainty(),
        "provenance": _provenance(request, request_hash, configuration_hash),
        "evidence": _evidence(request),
        "limitations": tuple(limitations),
        "human_review_required": not constructed,
    }
    candidate = VariantPeptideMechanisticFeatureResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(candidate)
    return VariantPeptideMechanisticFeatureResult.model_validate(payload, strict=True)


class M1103MechanisticFeatureEngine:
    """Construct one deterministic feature object or abstain safely."""

    __slots__ = ()

    def compute(self, request: object) -> VariantPeptideMechanisticFeatureResult:
        return _build_result(_validate_request(request))


def construct_variant_peptide_mechanistic_features(
    request: object,
) -> VariantPeptideMechanisticFeatureResult:
    return M1103MechanisticFeatureEngine().compute(request)


def verify_m1103_replay(
    result: VariantPeptideMechanisticFeatureResult,
    request: object,
) -> bool:
    """Verify exact request binding and regenerate the complete result."""

    try:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            decoded = strict_json_loads(serialized)
            typed = _validate_json_request(decoded, serialized)
        else:
            typed = _validate_request(request)
        if result.request_digest != canonical_request_digest(typed):
            return False
        if result.request != typed:
            return False
        if result.result_digest != result_payload_digest(result):
            return False
        regenerated = M1103MechanisticFeatureEngine().compute(typed)
        return result.model_dump(mode="json") == regenerated.model_dump(mode="json")
    except (AttributeError, TypeError, ValueError, ValidationError):
        return False


__all__ = [
    "M1103AuthorizationError",
    "M1103MechanisticFeatureEngine",
    "construct_variant_peptide_mechanistic_features",
    "preflight_m1103_authorization",
    "verify_m1103_replay",
]
