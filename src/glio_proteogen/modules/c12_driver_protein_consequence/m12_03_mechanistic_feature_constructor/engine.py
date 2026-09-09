"""Deterministic, reference-only M12-03 mechanistic feature construction."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, cast

from pydantic import BaseModel

from glio_proteogen.contracts.m12_03 import (
    M1203_CONTRACT_VERSION,
    M1203_EVIDENCE_CLAIM,
    M1203_GLIOMA_MODEL_FAMILY,
    BiomarkerPanelMechanisticFeatureResult,
    ConstructBiomarkerPanelMechanisticFeaturesRequest,
    MechanisticConstructionStatus,
    MechanisticDiagnosticStatus,
    MechanisticFeature,
    MechanisticFeatureDiagnostic,
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticFeatureObject,
    MechanisticFindingCode,
    MechanisticQualityStatus,
    MechanisticRelation,
    MechanisticRelationKind,
    MechanisticValueKind,
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
_MAX_PLAIN_DEPTH: Final = 64
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_SEQUENCE_ITEMS: Final = 4_096
_MAX_PLAIN_NODES: Final = 100_000
_EXPECTED_CONTROLS: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_M1203_RIDGE: Final = 0.03
_M1203_DAMPING: Final = 0.7
_M1203_HUBER_DELTA: Final = 1.5
_M1203_SOLVER_ITERATIONS: Final = 128
_M1203_SOLVER_TOLERANCE: Final = 1e-5
_M1203_MIN_SCALE: Final = 1e-6
_M1203_MIN_NUMERIC: Final = 2


@dataclass(frozen=True, slots=True)
class _TypedFit:
    feature_ids: tuple[str, ...]
    values: tuple[float, ...]
    objective: float
    iterations: int
    converged: bool


def _is_typed(request: ConstructBiomarkerPanelMechanisticFeaturesRequest) -> bool:
    return request.configuration.model_family == M1203_GLIOMA_MODEL_FAMILY


def _feature_numeric(feature: MechanisticFeature) -> tuple[float, float] | None:
    if feature.value_kind is MechanisticValueKind.SCALAR and feature.scalar_value is not None:
        if not math.isfinite(feature.scalar_value):
            return None
        return feature.scalar_value, 1.0
    if (
        feature.value_kind is MechanisticValueKind.INTERVAL
        and feature.lower_bound is not None
        and feature.upper_bound is not None
    ):
        if not math.isfinite(feature.lower_bound) or not math.isfinite(feature.upper_bound):
            return None
        return (
            (feature.lower_bound + feature.upper_bound) / 2.0,
            max(_M1203_MIN_SCALE, (feature.upper_bound - feature.lower_bound) / 2.0),
        )
    return None


def _relation_sign(relation: MechanisticRelation) -> float | None:
    # Typed glioma fitting must never invent an edge magnitude.  The contract
    # keeps ``weight`` optional for legacy, non-numeric callers, but an absent
    # weight is not an estimable signed constraint in the research lane.
    if relation.weight is None:
        return None
    if not math.isfinite(relation.weight):
        return None
    signs = {
        MechanisticRelationKind.ACTIVATES: 1.0,
        MechanisticRelationKind.INHIBITS: -1.0,
        MechanisticRelationKind.PARTICIPATES: 1.0,
        MechanisticRelationKind.PRECEDES: 1.0,
        MechanisticRelationKind.COLOCALIZES: 1.0,
    }
    sign: float | None
    if relation.kind is MechanisticRelationKind.REGULATES:
        sign = 1.0 if relation.weight >= 0.0 else -1.0
    else:
        sign = signs.get(relation.kind)
    if sign is None:
        return None
    return sign * max(_M1203_MIN_SCALE, abs(relation.weight))


def _huber(value: float) -> float:
    absolute = abs(value)
    return (
        0.5 * value * value
        if absolute <= _M1203_HUBER_DELTA
        else _M1203_HUBER_DELTA * (absolute - 0.5 * _M1203_HUBER_DELTA)
    )


def _fit_typed(
    request: ConstructBiomarkerPanelMechanisticFeaturesRequest,
    *,
    perturbation: Mapping[str, float] | None = None,
) -> _TypedFit | None:
    numeric = tuple(
        (feature, measured[0] + (perturbation or {}).get(feature.feature_id, 0.0), measured[1])
        for feature in sorted(request.feature_inputs, key=lambda item: item.feature_id)
        if (measured := _feature_numeric(feature)) is not None
    )
    if len(numeric) < _M1203_MIN_NUMERIC:
        return None
    index = {feature.feature_id: position for position, (feature, _, _) in enumerate(numeric)}
    relations = tuple(
        (index[item.source_feature_id], index[item.target_feature_id], coefficient)
        for item in sorted(request.relations, key=lambda value: value.relation_id)
        if item.source_feature_id in index
        and item.target_feature_id in index
        and (coefficient := _relation_sign(item)) is not None
    )
    if not relations:
        return None
    values = [value for _, value, _ in numeric]
    objective = float("inf")
    for iteration in range(1, _M1203_SOLVER_ITERATIONS + 1):
        previous = values.copy()
        for position, current in enumerate(values):
            gradient = 2.0 * _M1203_RIDGE * current
            hessian = 2.0 * _M1203_RIDGE
            target, uncertainty = numeric[position][1], max(_M1203_MIN_SCALE, numeric[position][2])
            residual = (current - target) / uncertainty
            influence = (
                1.0
                if abs(residual) <= _M1203_HUBER_DELTA
                else _M1203_HUBER_DELTA / max(_M1203_MIN_SCALE, abs(residual))
            )
            information = influence / (uncertainty * uncertainty)
            gradient += information * (current - target)
            hessian += information
            for source, target_index, coefficient in relations:
                if position == source:
                    edge_residual = values[target_index] - coefficient * current
                    gradient -= coefficient * edge_residual
                    hessian += coefficient * coefficient
                elif position == target_index:
                    edge_residual = current - coefficient * values[source]
                    gradient += edge_residual
                    hessian += 1.0
            proposal = current - gradient / max(_M1203_MIN_SCALE, hessian)
            values[position] = current + _M1203_DAMPING * (proposal - current)
        next_objective = _M1203_RIDGE * sum(value * value for value in values)
        next_objective += sum(
            _huber((value - target) / max(_M1203_MIN_SCALE, uncertainty))
            for value, (_, target, uncertainty) in zip(values, numeric, strict=True)
        )
        next_objective += sum(
            0.5 * (values[target] - coefficient * values[source]) ** 2
            for source, target, coefficient in relations
        )
        update = max(abs(after - before) for after, before in zip(values, previous, strict=True))
        if (
            update <= _M1203_SOLVER_TOLERANCE
            and abs(objective - next_objective) <= 2.0 * _M1203_SOLVER_TOLERANCE
        ):
            return _TypedFit(
                feature_ids=tuple(feature.feature_id for feature, _, _ in numeric),
                values=tuple(float(f"{value:.8f}") for value in values),
                objective=float(f"{next_objective:.8f}"),
                iterations=iteration,
                converged=True,
            )
        objective = next_objective
    return _TypedFit(
        feature_ids=tuple(feature.feature_id for feature, _, _ in numeric),
        values=tuple(float(f"{value:.8f}") for value in values),
        objective=float(f"{objective:.8f}"),
        iterations=_M1203_SOLVER_ITERATIONS,
        converged=False,
    )


def _hash_normal(material: str) -> float:
    first = (
        int.from_bytes(hashlib.sha256((material + ":u1").encode()).digest()[:8], "big") + 1.0
    ) / (2.0**64 + 1.0)
    second = (
        int.from_bytes(hashlib.sha256((material + ":u2").encode()).digest()[:8], "big") + 1.0
    ) / (2.0**64 + 1.0)
    return math.sqrt(-2.0 * math.log(max(_M1203_MIN_SCALE, first))) * math.cos(
        2.0 * math.pi * second
    )


def _typed_projection(
    request: ConstructBiomarkerPanelMechanisticFeaturesRequest,
    request_digest: str,
    fit: _TypedFit,
) -> tuple[tuple[MechanisticFeature, ...], tuple[float, float]]:
    numeric = tuple(
        (feature, measured[0], measured[1])
        for feature in sorted(request.feature_inputs, key=lambda item: item.feature_id)
        if (measured := _feature_numeric(feature)) is not None
    )
    index = {feature_id: position for position, feature_id in enumerate(fit.feature_ids)}
    draws: list[float] = []
    for draw in range(request.configuration.bootstrap_replicates):
        perturbation = {
            feature.feature_id: uncertainty
            * _hash_normal(f"{request_digest}:{draw}:{feature.feature_id}")
            for feature, _, uncertainty in numeric
        }
        draw_fit = _fit_typed(request, perturbation=perturbation)
        if draw_fit is None or not draw_fit.converged:
            raise ValueError("typed glioma bootstrap fit did not converge")  # noqa: TRY003
        draws.append(sum(draw_fit.values) / max(_M1203_MIN_SCALE, len(draw_fit.values)))
    projected: list[MechanisticFeature] = []
    for feature in request.feature_inputs:
        measured = _feature_numeric(feature)
        if measured is None:
            projected.append(feature)
            continue
        latent = fit.values[index[feature.feature_id]]
        if feature.value_kind is MechanisticValueKind.SCALAR:
            projected.append(feature.model_copy(update={"scalar_value": float(f"{latent:.8f}")}))
        else:
            half_width = max(_M1203_MIN_SCALE, measured[1])
            projected.append(
                feature.model_copy(
                    update={
                        "lower_bound": float(f"{latent - half_width:.8f}"),
                        "upper_bound": float(f"{latent + half_width:.8f}"),
                    }
                )
            )
    aggregate = sum(fit.values) / max(_M1203_MIN_SCALE, len(fit.values))
    lower = min((*draws, aggregate))
    upper = max((*draws, aggregate))
    source = request.source_artifacts[:1]
    state_id = "feature.glioma.mechanism_state"
    interval_id = "feature.glioma.mechanism_interval"
    projected.extend(
        (
            MechanisticFeature(
                feature_id=state_id,
                version=request.configuration.version,
                kind=MechanisticFeatureKind.STATE,
                value_kind=MechanisticValueKind.SCALAR,
                unit="standardized_glioma_effect",
                scalar_value=float(f"{aggregate:.8f}"),
                lineage=MechanisticFeatureLineage(
                    feature_id=state_id,
                    source_artifacts=source,
                    claim="Robust signed biomarker mechanism state.",
                ),
            ),
            MechanisticFeature(
                feature_id=interval_id,
                version=request.configuration.version,
                kind=MechanisticFeatureKind.STATE,
                value_kind=MechanisticValueKind.INTERVAL,
                unit="standardized_glioma_effect",
                lower_bound=float(f"{lower:.8f}"),
                upper_bound=float(f"{upper:.8f}"),
                lineage=MechanisticFeatureLineage(
                    feature_id=interval_id,
                    source_artifacts=source,
                    claim="Digest-seeded biomarker state interval.",
                ),
            ),
        )
    )
    return tuple(projected), (float(f"{lower:.8f}"), float(f"{upper:.8f}"))


class MechanisticFeatureAuthorizationError(PermissionError):
    """Raised before any caller-declared source reference is traversed."""

    def __init__(self) -> None:
        super().__init__("M12-03 construction requires accepted identity, consent, and controls")


class MechanisticFeatureValidationError(ValueError):
    """Raised when strict request replay or feature invariants fail."""


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
    typed = _is_typed(request)
    typed_fit = _fit_typed(request) if typed else None
    if typed:
        typed_status = (
            MechanisticDiagnosticStatus.PASS
            if typed_fit is not None and typed_fit.converged
            else MechanisticDiagnosticStatus.NOT_EVALUABLE
        )
        diagnostics += (
            MechanisticFeatureDiagnostic(
                diagnostic_id="diagnostic.typed-glioma-model",
                status=typed_status,
                message=(
                    "Typed glioma constraint graph converged."
                    if typed_status is MechanisticDiagnosticStatus.PASS
                    else "Typed glioma constraint graph lacks supported topology or convergence."
                ),
                evidence=_evidence_index(request)[:1],
            ),
        )
    failing = any(
        item.status in {MechanisticDiagnosticStatus.FAIL, MechanisticDiagnosticStatus.NOT_EVALUABLE}
        for item in diagnostics
    )
    safe = (
        request.quality_status is MechanisticQualityStatus.ACCEPTED
        and request.negative_control_status is NegativeControlStatus.PASSED
        and not failing
    )
    typed_features: tuple[MechanisticFeature, ...] | None = None
    interval = None
    if safe and typed and typed_fit is not None and typed_fit.converged:
        typed_features, interval = _typed_projection(request, request_digest, typed_fit)
    feature_object = (
        _feature_object(request, request_digest, typed_features=typed_features) if safe else None
    )
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
        "typed_model": typed and safe,
        "model_profile": request.configuration.model_family if typed else None,
        "solver_iterations": typed_fit.iterations if typed_fit is not None else 0,
        "solver_objective": typed_fit.objective if typed_fit is not None else None,
        "state_interval_lower": interval[0] if interval is not None else None,
        "state_interval_upper": interval[1] if interval is not None else None,
    }
    preliminary = BiomarkerPanelMechanisticFeatureResult.model_construct(
        **payload,  # type: ignore[arg-type]
    )
    payload["result_digest"] = result_payload_digest(preliminary)
    return BiomarkerPanelMechanisticFeatureResult.model_validate(payload)


def request_digest_for(request: ConstructBiomarkerPanelMechanisticFeaturesRequest) -> str:
    return canonical_request_digest(request)


def _feature_object(
    request: ConstructBiomarkerPanelMechanisticFeaturesRequest,
    request_digest: str,
    *,
    typed_features: tuple[MechanisticFeature, ...] | None = None,
) -> MechanisticFeatureObject:
    features = request.feature_inputs
    if typed_features is not None:
        features = typed_features
    return MechanisticFeatureObject(
        object_id=f"feature-object.m1203.{request_digest.removeprefix('sha256:')}",
        version=request.configuration.version,
        features=features,
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


def _plain_value(  # noqa: C901 - exact built-in traversal firewall.
    value: object,
    *,
    _depth: int = 0,
    _budget: list[int] | None = None,
) -> object:
    if _depth > _MAX_PLAIN_DEPTH:
        raise MechanisticFeatureValidationError
    budget = [_MAX_PLAIN_NODES] if _budget is None else _budget
    budget[0] -= 1
    if budget[0] < 0:
        raise MechanisticFeatureValidationError
    mro = type.__getattribute__(type(value), "__mro__")
    if BaseModel in mro:
        storage = cast("dict[object, object]", object.__getattribute__(value, "__dict__"))
        if len(storage) > _MAX_PLAIN_DICT_ITEMS or any(type(key) is not str for key in storage):
            raise MechanisticFeatureValidationError
        return {
            key: _plain_value(item, _depth=_depth + 1, _budget=budget)
            for key, item in storage.items()
        }
    if dict in mro:
        mapping = cast("dict[object, object]", value)
        if len(mapping) > _MAX_PLAIN_DICT_ITEMS or any(type(key) is not str for key in mapping):
            raise MechanisticFeatureValidationError
        return {
            key: _plain_value(item, _depth=_depth + 1, _budget=budget)
            for key, item in mapping.items()
        }
    if list in mro:
        items = cast("list[object]", value)
        if len(items) > _MAX_PLAIN_SEQUENCE_ITEMS:
            raise MechanisticFeatureValidationError
        return [_plain_value(item, _depth=_depth + 1, _budget=budget) for item in items]
    if tuple in mro:
        tuple_items = cast("tuple[object, ...]", value)
        if len(tuple_items) > _MAX_PLAIN_SEQUENCE_ITEMS:
            raise MechanisticFeatureValidationError
        return tuple(_plain_value(item, _depth=_depth + 1, _budget=budget) for item in tuple_items)
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
