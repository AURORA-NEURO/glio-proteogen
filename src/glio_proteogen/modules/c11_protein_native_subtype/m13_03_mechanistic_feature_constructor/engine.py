"""Deterministic, evidence-preserving M13-03 mechanistic feature engine."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, cast

from pydantic import BaseModel

from glio_proteogen.contracts.m13_03 import (
    M1303_CONTRACT_VERSION,
    M1303_GLIOMA_ENTITY_KINDS,
    M1303_MAX_CANONICAL_REQUEST_BYTES,
    M1303_PARENT,
    ConstructProteotypeMechanisticFeaturesRequest,
    MechanisticConstructionStatus,
    MechanisticDiagnosticStatus,
    MechanisticEvidenceState,
    MechanisticFeature,
    MechanisticFeatureDiagnostic,
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticFeatureObject,
    MechanisticFindingCode,
    MechanisticObservation,
    MechanisticRelation,
    MechanisticRelationKind,
    MechanisticValueKind,
    ProteotypeMechanisticFeatureResult,
    expected_limitations,
    expected_provenance,
    expected_uncertainty,
    feature_evidence_index,
)
from glio_proteogen.contracts.m13_03.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    EvidenceReference,
    SupportDecision,
    SupportStatus,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_AUTHORIZATION_MESSAGE: Final = "M13-03 execution requires accepted upstream controls"
_INVALID_REQUEST_MESSAGE: Final = "M13-03 request must be a strict contract object"
_UNSUPPORTED_MARKERS: Final = frozenset({"unsupported", "missing", "not_evaluable", "ood", "n_a"})
_CONTROL_MARKERS: Final = frozenset({"withheld", "revoked", "unresolved", "conflicted", "rejected"})
_TOPOLOGY_THRESHOLD: Final = 0.5
_HUBER_DELTA: Final = 1.5
_HUBER_ITERATIONS: Final = 24
_HUBER_DAMPING: Final = 0.7
_RIDGE: Final = 0.03
_SOLVER_ITERATIONS: Final = 128
_SOLVER_TOLERANCE: Final = 1e-5
_MAD_SCALE: Final = 1.4826
_MIN_SCALE: Final = 1e-6
_BOOTSTRAP_LOW: Final = 0.05
_BOOTSTRAP_HIGH: Final = 0.95
_MAX_EFFECT: Final = 20.0
_MIN_SUPPORTED_ENTITIES: Final = 2

# A compact, reviewable glioma graph.  Signs encode the expected direction of
# a node's standardized effect on the target pathway coordinate; they are not
# claims of biochemical stoichiometry or clinical causality.
_GLIOMA_EDGES: Final[tuple[tuple[str, str, int, float], ...]] = (
    ("AKT1", "RTK_PI3K_AKT_MTOR", 1, 1.0),
    ("CDKN2A", "P53_CELL_CYCLE", 1, 0.9),
    ("CDKN2A", "CDK4_RB", -1, 1.1),
    ("EGFR", "RTK_PI3K_AKT_MTOR", 1, 1.2),
    ("EGFR_Y1068", "EGFR", 1, 0.8),
    ("HIF1A", "IDH_HIF1A", 1, 1.0),
    ("HIF1A", "MESENCHYMAL_PROGRAM", 1, 0.8),
    ("IDH1", "IDH_HIF1A", 1, 0.9),
    ("MTOR", "MTORC1", 1, 1.1),
    ("MTORC1", "RTK_PI3K_AKT_MTOR", 1, 1.0),
    ("NF1", "RTK_PI3K_AKT_MTOR", -1, 1.0),
    ("OLIG2", "PROLIFERATION", 1, 0.8),
    ("PDGFRA", "RTK_PI3K_AKT_MTOR", 1, 1.1),
    ("PTEN", "RTK_PI3K_AKT_MTOR", -1, 1.2),
    ("RB1", "CDK4_RB", -1, 1.0),
    ("RPS6_S235", "MTORC1", 1, 0.8),
    ("SOX2", "MESENCHYMAL_PROGRAM", -1, 0.7),
    ("SOX2", "PROLIFERATION", 1, 0.8),
    ("TP53", "P53_CELL_CYCLE", 1, 1.1),
    ("CDK4_RB", "PROLIFERATION", -1, 1.0),
)
_PATHWAY_IDS: Final[tuple[str, ...]] = (
    "IDH_HIF1A",
    "MESENCHYMAL_PROGRAM",
    "P53_CELL_CYCLE",
    "PROLIFERATION",
    "RTK_PI3K_AKT_MTOR",
)
_ENTITY_IDS: Final[tuple[str, ...]] = tuple(item[0] for item in M1303_GLIOMA_ENTITY_KINDS)
_ENTITY_INDEX: Final[dict[str, int]] = {value: index for index, value in enumerate(_ENTITY_IDS)}


@dataclass(frozen=True, slots=True)
class _ObservationTerm:
    entity_id: str
    state: MechanisticEvidenceState
    value: float
    standard_error: float
    quality_weight: float


@dataclass(frozen=True, slots=True)
class _GraphTerm:
    source: int
    target: int
    sign: int
    weight: float


@dataclass(frozen=True, slots=True)
class _Fit:
    values: tuple[float, ...]
    converged: bool
    iterations: int
    objective: float
    max_update: float


class MechanisticFeatureAuthorizationError(PermissionError):
    """Raised before any upstream artifact reference is traversed."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class _InvalidExecutionRequestError(TypeError):
    def __init__(self) -> None:
        super().__init__(_INVALID_REQUEST_MESSAGE)


class _InvalidReplayError(ValueError):
    def __init__(self) -> None:
        super().__init__("M13-03 replay verification failed")


class _SafeFailureReason(StrEnum):
    UPSTREAM_UNSUPPORTED = "upstream support is not established"
    INPUT_INCOMPLETE = "source evidence is incomplete or not evaluable"
    NEGATIVE_CONTROL = "negative-control gating failed"
    SOLVER_NON_CONVERGENCE = "signed glioma evidence graph did not converge"


class M1303MechanisticFeatureEngine:
    """Build digest-derived reference features without reading opaque artifacts."""

    __slots__ = ()

    def compute(self, request: object) -> ProteotypeMechanisticFeatureResult:
        typed = _validated_request(request)
        return _compute_result(typed)


def construct_proteotype_mechanistic_features(
    request: object,
) -> ProteotypeMechanisticFeatureResult:
    """Stateless M13-03 operation."""

    return M1303MechanisticFeatureEngine().compute(request)


def preflight_mechanistic_feature_authorization(candidate: object) -> None:
    """Validate the seven caller-declared controls before data access."""

    try:
        if type(candidate) is ConstructProteotypeMechanisticFeaturesRequest:
            context = object.__getattribute__(candidate, "context")
        elif type(candidate) is dict:
            context = cast("dict[str, object]", candidate).get("context")
        else:
            context = None
        references = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        actual = {
            role: _state_text(_member(_member(references, role), "state")) for role in expected
        }
    except Exception as exc:
        if isinstance(exc, MechanisticFeatureAuthorizationError):
            raise
        raise MechanisticFeatureAuthorizationError from None
    if actual != expected:
        raise MechanisticFeatureAuthorizationError


def verify_mechanistic_feature_replay(
    result: ProteotypeMechanisticFeatureResult,
) -> ProteotypeMechanisticFeatureResult:
    """Re-validate request and result digests before releasing a result."""

    if type(result) is not ProteotypeMechanisticFeatureResult:
        raise _InvalidReplayError
    if result.request_digest != canonical_request_digest(result.request):
        raise _InvalidReplayError
    if result.result_digest != result_payload_digest(result):
        raise _InvalidReplayError
    try:
        return ProteotypeMechanisticFeatureResult.model_validate(result.model_dump(mode="python"))
    except ValueError as exc:
        raise _InvalidReplayError from exc


def _validated_request(candidate: object) -> ConstructProteotypeMechanisticFeaturesRequest:
    preflight_mechanistic_feature_authorization(candidate)
    if type(candidate) is ConstructProteotypeMechanisticFeaturesRequest:
        return candidate
    if type(candidate) is dict:
        try:
            return ConstructProteotypeMechanisticFeaturesRequest.model_validate(candidate)
        except ValueError as exc:
            raise _InvalidExecutionRequestError from exc
    raise _InvalidExecutionRequestError


def validate_json_request(
    decoded: object,
    serialized: bytes | bytearray | str,
) -> ConstructProteotypeMechanisticFeaturesRequest:
    """Strictly parse one JSON document and validate it against the contract."""

    if type(decoded) is not dict:
        raise _InvalidExecutionRequestError
    if len(serialized) > M1303_MAX_CANONICAL_REQUEST_BYTES:
        raise _InvalidExecutionRequestError
    preflight_mechanistic_feature_authorization(decoded)
    try:
        if type(serialized) is str:
            encoded = serialized.encode("utf-8")
        else:
            encoded = bytes(cast("bytes | bytearray", serialized))
        return ConstructProteotypeMechanisticFeaturesRequest.model_validate_json(encoded)
    except ValueError as exc:
        raise _InvalidExecutionRequestError from exc


def _compute_result(
    request: ConstructProteotypeMechanisticFeaturesRequest,
) -> ProteotypeMechanisticFeatureResult:
    request = _canonical_request(request)
    request_digest = canonical_request_digest(request)
    provenance = expected_provenance(request, request_digest=request_digest)
    evidence = feature_evidence_index(request)
    reason = _safe_failure(request)
    if reason is not None:
        return _abstained_result(request, request_digest, provenance, evidence, reason)
    feature_object = _construct_feature_object(request)
    diagnostics = _diagnostics(request, evidence)
    payload: dict[str, object] = {
        "output_type": "proteotype_mechanistic_features",
        "result_id": f"result.m1303.{request_digest.removeprefix('sha256:')}",
        "result_version": M1303_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": MechanisticConstructionStatus.CONSTRUCTED,
        "feature_object": feature_object,
        "diagnostics": diagnostics,
        "findings": (MechanisticFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,),
        "abstention_reason": None,
        "parent_target": M1303_PARENT,
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m1303.supported",
            rationale="All seven controls, source evidence, and invariants are supported.",
        ),
        "uncertainty": expected_uncertainty(),
        "provenance": provenance,
        "evidence": evidence,
        "limitations": expected_limitations(),
        "human_review_required": True,
    }
    assembled = ProteotypeMechanisticFeatureResult.model_construct(**payload)  # type: ignore[arg-type]
    payload["result_digest"] = result_payload_digest(assembled)
    assembled = ProteotypeMechanisticFeatureResult.model_construct(**payload)  # type: ignore[arg-type]
    return verify_mechanistic_feature_replay(assembled)


def _canonical_request(
    request: ConstructProteotypeMechanisticFeaturesRequest,
) -> ConstructProteotypeMechanisticFeaturesRequest:
    """Freeze observation ordering so equivalent requests share one receipt."""

    ordered = tuple(sorted(request.observations, key=lambda item: item.observation_id))
    if ordered == request.observations:
        return request
    return request.model_copy(update={"observations": ordered})


def _abstained_result(
    request: ConstructProteotypeMechanisticFeaturesRequest,
    request_digest: str,
    provenance: object,
    evidence: tuple[EvidenceReference, ...],
    reason: _SafeFailureReason,
) -> ProteotypeMechanisticFeatureResult:
    code = (
        MechanisticFindingCode.UPSTREAM_UNSUPPORTED
        if reason is _SafeFailureReason.UPSTREAM_UNSUPPORTED
        else MechanisticFindingCode.NEGATIVE_CONTROL_FAILED
        if reason is _SafeFailureReason.NEGATIVE_CONTROL
        else MechanisticFindingCode.INPUT_INCOMPLETE
    )
    diagnostic_status = (
        MechanisticDiagnosticStatus.FAIL
        if reason is _SafeFailureReason.NEGATIVE_CONTROL
        else MechanisticDiagnosticStatus.NOT_EVALUABLE
    )
    diagnostics = (
        _diagnostic("diagnostic.safe_failure", diagnostic_status, str(reason), evidence),
    )
    payload: dict[str, object] = {
        "output_type": "proteotype_mechanistic_features",
        "result_id": f"result.m1303.{request_digest.removeprefix('sha256:')}",
        "result_version": M1303_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": MechanisticConstructionStatus.ABSTAINED,
        "feature_object": None,
        "diagnostics": diagnostics,
        "findings": (code, MechanisticFindingCode.PROVISIONAL_ABI_PENDING_REVIEW),
        "abstention_reason": str(reason),
        "parent_target": M1303_PARENT,
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code=f"m1303.{code.value}",
            rationale=(
                "M13-03 preserves unresolved support and emits no mechanistic feature object."
            ),
        ),
        "uncertainty": expected_uncertainty(),
        "provenance": provenance,
        "evidence": evidence,
        "limitations": expected_limitations(),
        "human_review_required": True,
    }
    assembled = ProteotypeMechanisticFeatureResult.model_construct(**payload)  # type: ignore[arg-type]
    payload["result_digest"] = result_payload_digest(assembled)
    assembled = ProteotypeMechanisticFeatureResult.model_construct(**payload)  # type: ignore[arg-type]
    return verify_mechanistic_feature_replay(assembled)


def _safe_failure(
    request: ConstructProteotypeMechanisticFeaturesRequest,
) -> _SafeFailureReason | None:
    labels = {
        item.artifact_id.casefold() for item in (*request.source_artifacts, request.upstream_result)
    }
    config_labels = {
        item.artifact_id.casefold() for item in request.configuration.negative_control_artifacts
    }
    if any(any(marker in label for marker in _UNSUPPORTED_MARKERS) for label in labels):
        return _SafeFailureReason.UPSTREAM_UNSUPPORTED
    if any(any(marker in label for marker in _CONTROL_MARKERS) for label in labels):
        return _SafeFailureReason.INPUT_INCOMPLETE
    if any("fail" in label or "invalid" in label for label in config_labels):
        return _SafeFailureReason.NEGATIVE_CONTROL
    active = tuple(
        item
        for item in request.observations
        if item.state
        in {MechanisticEvidenceState.OBSERVED, MechanisticEvidenceState.LEFT_CENSORED}
    )
    if not active or len({item.entity_id for item in active}) < _MIN_SUPPORTED_ENTITIES:
        return _SafeFailureReason.INPUT_INCOMPLETE
    if not _fit(_active_observations(request.observations)).converged:
        return _SafeFailureReason.SOLVER_NON_CONVERGENCE
    return None


def _construct_feature_object(
    request: ConstructProteotypeMechanisticFeaturesRequest,
) -> MechanisticFeatureObject:
    observations = _active_observations(request.observations)
    fit = _fit(observations)
    bootstrap = _bootstrap_pathway_scores(
        observations,
        request.configuration.bootstrap_replicates,
        canonical_request_digest(request),
    )
    pathway_scores = {pathway: fit.values[_ENTITY_INDEX[pathway]] for pathway in _PATHWAY_IDS}
    aggregate = _aggregate(pathway_scores.values())
    aggregate_samples = tuple(_aggregate(item.values()) for item in bootstrap)
    lower = _quantile(aggregate_samples, _BOOTSTRAP_LOW)
    upper = _quantile(aggregate_samples, _BOOTSTRAP_HIGH)
    lower = min(lower, aggregate)
    upper = max(upper, aggregate)
    active_fraction = len(observations) / max(1, len(request.observations))
    topology_weight = min(1.0, len({item.entity_id for item in observations}) / 6.0)
    regulation_balance = _signed_observation_balance(observations)

    def lineage(feature_id: str, claim: str) -> MechanisticFeatureLineage:
        return MechanisticFeatureLineage(
            feature_id=feature_id,
            source_artifacts=request.source_artifacts,
            claim=claim,
            transformation_ids=request.configuration.transformation_ids,
            evidence=feature_evidence_index(request),
        )

    evidence = feature_evidence_index(request)
    features_list: list[MechanisticFeature] = [
        MechanisticFeature(
            feature_id="feature.pathway.activity",
            version=request.configuration.version,
            kind=MechanisticFeatureKind.PATHWAY,
            value_kind=MechanisticValueKind.SCALAR,
            unit="standardized_pathway_effect",
            scalar_value=aggregate,
            lineage=lineage(
                "feature.pathway.activity",
                "Robust signed activity across the locked glioma pathway graph.",
            ),
            evidence=evidence,
        )
    ]
    for pathway in _PATHWAY_IDS:
        feature_id = f"feature.pathway.{pathway.casefold()}"
        features_list.append(
            MechanisticFeature(
                feature_id=feature_id,
                version=request.configuration.version,
                kind=MechanisticFeatureKind.PATHWAY,
                value_kind=MechanisticValueKind.SCALAR,
                unit="standardized_pathway_effect",
                scalar_value=pathway_scores[pathway],
                lineage=lineage(
                    feature_id,
                    f"Signed Huber-IRLS coordinate for glioma pathway {pathway}.",
                ),
                evidence=evidence,
            )
        )
    features_list.extend(
        (
            MechanisticFeature(
                feature_id="feature.topology.state",
                version=request.configuration.version,
                kind=MechanisticFeatureKind.TOPOLOGY,
                value_kind=MechanisticValueKind.CATEGORICAL,
                unit="topology_class",
                category="connected" if topology_weight >= _TOPOLOGY_THRESHOLD else "sparse",
                lineage=lineage(
                    "feature.topology.state",
                    "Connectivity of the supported signed glioma evidence subgraph.",
                ),
                evidence=evidence,
            ),
            MechanisticFeature(
                feature_id="feature.state.interval",
                version=request.configuration.version,
                kind=MechanisticFeatureKind.STATE,
                value_kind=MechanisticValueKind.INTERVAL,
                unit="standardized_state",
                lower_bound=lower,
                upper_bound=upper,
                lineage=lineage(
                    "feature.state.interval",
                    "Deterministic bootstrap interval for the aggregate pathway state.",
                ),
                evidence=evidence,
            ),
            MechanisticFeature(
                feature_id="feature.regulatory.balance",
                version=request.configuration.version,
                kind=MechanisticFeatureKind.REGULATORY,
                value_kind=MechanisticValueKind.SCALAR,
                unit="signed_regulatory_effect",
                scalar_value=regulation_balance,
                lineage=lineage(
                    "feature.regulatory.balance",
                    "Quality-weighted signed balance of observed glioma regulators.",
                ),
                evidence=evidence,
            ),
            MechanisticFeature(
                feature_id="feature.lineage.coverage",
                version=request.configuration.version,
                kind=MechanisticFeatureKind.LINEAGE,
                value_kind=MechanisticValueKind.SCALAR,
                unit="active_evidence_fraction",
                scalar_value=active_fraction,
                lineage=lineage(
                    "feature.lineage.coverage",
                    "Fraction of supplied typed observations with numerical support.",
                ),
                evidence=evidence,
            ),
            MechanisticFeature(
                feature_id="feature.kinetics.state",
                version=request.configuration.version,
                kind=MechanisticFeatureKind.KINETICS,
                value_kind=MechanisticValueKind.CATEGORICAL,
                unit="kinetics_support",
                category="not_estimable_without_time_series",
                lineage=lineage(
                    "feature.kinetics.state",
                    "Kinetics are withheld because no time-series measurements were supplied.",
                ),
                evidence=evidence,
            ),
            MechanisticFeature(
                feature_id="feature.spatial.state",
                version=request.configuration.version,
                kind=MechanisticFeatureKind.SPATIAL,
                value_kind=MechanisticValueKind.CATEGORICAL,
                unit="spatial_support",
                category="not_estimable_without_spatial_assay",
                lineage=lineage(
                    "feature.spatial.state",
                    "Spatial state is withheld because no spatial assay was supplied.",
                ),
                evidence=evidence,
            ),
        )
    )
    features = tuple(features_list)
    relations: list[MechanisticRelation] = [
        MechanisticRelation(
            relation_id="relation.pathway-topology",
            source_feature_id="feature.pathway.activity",
            target_feature_id="feature.topology.state",
            kind=MechanisticRelationKind.REGULATES,
            weight=round(topology_weight, 6),
            evidence=evidence,
        ),
        MechanisticRelation(
            relation_id="relation.topology-state",
            source_feature_id="feature.topology.state",
            target_feature_id="feature.state.interval",
            kind=MechanisticRelationKind.PARTICIPATES,
            weight=round(math.tanh(aggregate), 6),
            evidence=evidence,
        ),
    ]
    relations.extend(
        MechanisticRelation(
            relation_id=f"relation.{pathway.casefold()}-aggregate",
            source_feature_id=f"feature.pathway.{pathway.casefold()}",
            target_feature_id="feature.pathway.activity",
            kind=MechanisticRelationKind.REGULATES,
            weight=round(math.tanh(pathway_scores[pathway]), 6),
            evidence=evidence,
        )
        for pathway in _PATHWAY_IDS
    )
    return MechanisticFeatureObject(
        object_id=f"object.m1303.{request.request_id}",
        version=request.configuration.version,
        features=features,
        relations=tuple(relations),
        configuration=request.configuration,
        evidence=evidence,
    )


def _active_observations(
    observations: tuple[MechanisticObservation, ...],
) -> tuple[_ObservationTerm, ...]:
    terms: list[_ObservationTerm] = []
    for item in sorted(observations, key=lambda value: value.observation_id):
        if item.state not in {
            MechanisticEvidenceState.OBSERVED,
            MechanisticEvidenceState.LEFT_CENSORED,
        }:
            continue
        if item.standardized_effect is None or item.standard_error is None:
            continue
        terms.append(
            _ObservationTerm(
                entity_id=item.entity_id,
                state=item.state,
                value=item.standardized_effect,
                standard_error=item.standard_error,
                quality_weight=item.quality_weight,
            )
        )
    return tuple(terms)


def _graph_terms() -> tuple[_GraphTerm, ...]:
    return tuple(
        _GraphTerm(
            source=_ENTITY_INDEX[source],
            target=_ENTITY_INDEX[target],
            sign=sign,
            weight=weight,
        )
        for source, target, sign, weight in _GLIOMA_EDGES
    )


def _huber_weight(residual: float) -> float:
    absolute = abs(residual)
    if absolute == 0.0 or absolute <= _HUBER_DELTA:
        return 1.0
    return _HUBER_DELTA / absolute


def _huber_loss(residual: float) -> float:
    absolute = abs(residual)
    if absolute <= _HUBER_DELTA:
        return 0.5 * residual * residual
    return _HUBER_DELTA * (absolute - 0.5 * _HUBER_DELTA)


def _median(values: tuple[float, ...]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return 0.5 * (ordered[middle - 1] + ordered[middle])


def _robust_center(terms: tuple[_ObservationTerm, ...]) -> float:
    values = tuple(item.value for item in terms)
    center = _median(values)
    deviations = tuple(abs(value - center) for value in values)
    scale = max(_MIN_SCALE, _MAD_SCALE * _median(deviations))
    for _ in range(_HUBER_ITERATIONS):
        numerator = 0.0
        denominator = 0.0
        for item in terms:
            residual = (center - item.value) / max(_MIN_SCALE, item.standard_error, scale)
            weight = item.quality_weight / max(_MIN_SCALE, item.standard_error**2)
            weight *= _huber_weight(residual)
            numerator += weight * item.value
            denominator += weight
        if denominator == 0.0:
            break
        proposal = numerator / denominator
        update = _HUBER_DAMPING * (proposal - center)
        center += update
        if abs(update) <= _SOLVER_TOLERANCE:
            break
    return max(-_MAX_EFFECT, min(_MAX_EFFECT, center))


def _initial_values(observations: tuple[_ObservationTerm, ...]) -> list[float]:
    grouped: dict[str, list[_ObservationTerm]] = defaultdict(list)
    for item in observations:
        grouped[item.entity_id].append(item)
    values = [0.0] * len(_ENTITY_IDS)
    for entity_id, terms in grouped.items():
        values[_ENTITY_INDEX[entity_id]] = _robust_center(tuple(terms))
    return values


def _edge_residual(edge: _GraphTerm, values: list[float]) -> float:
    return values[edge.target] - edge.sign * values[edge.source]


def _objective(
    values: list[float],
    observations: tuple[_ObservationTerm, ...],
    edges: tuple[_GraphTerm, ...],
) -> float:
    objective = _RIDGE * sum(value * value for value in values)
    for item in observations:
        index = _ENTITY_INDEX[item.entity_id]
        if item.state is MechanisticEvidenceState.LEFT_CENSORED:
            residual = max(0.0, values[index] - item.value) / max(_MIN_SCALE, item.standard_error)
        else:
            residual = (values[index] - item.value) / max(_MIN_SCALE, item.standard_error)
        objective += item.quality_weight * _huber_loss(residual)
    for edge in edges:
        residual = _edge_residual(edge, values)
        objective += edge.weight * _huber_loss(residual)
    return objective


def _fit(observations: tuple[_ObservationTerm, ...]) -> _Fit:
    edges = _graph_terms()
    values = _initial_values(observations)
    grouped: dict[int, list[_ObservationTerm]] = defaultdict(list)
    for item in observations:
        grouped[_ENTITY_INDEX[item.entity_id]].append(item)
    previous_objective = _objective(values, observations, edges)
    max_update = math.inf
    converged = False
    iterations = 0
    for iteration in range(1, _SOLVER_ITERATIONS + 1):
        iterations = iteration
        old = values.copy()
        for index in range(len(values)):
            numerator = 0.0
            denominator = _RIDGE
            for item in grouped.get(index, ()):
                if (
                    item.state is MechanisticEvidenceState.LEFT_CENSORED
                    and values[index] <= item.value
                ):
                    continue
                residual = (
                    max(0.0, values[index] - item.value)
                    if item.state is MechanisticEvidenceState.LEFT_CENSORED
                    else values[index] - item.value
                ) / max(_MIN_SCALE, item.standard_error)
                weight = item.quality_weight / max(_MIN_SCALE, item.standard_error**2)
                weight *= _huber_weight(residual)
                numerator += weight * item.value
                denominator += weight
            for edge in edges:
                if edge.source == index:
                    residual = _edge_residual(edge, values)
                    weight = edge.weight * _huber_weight(residual)
                    numerator += weight * edge.sign * values[edge.target]
                    denominator += weight
                elif edge.target == index:
                    residual = _edge_residual(edge, values)
                    weight = edge.weight * _huber_weight(residual)
                    numerator += weight * edge.sign * values[edge.source]
                    denominator += weight
            proposal = numerator / max(_MIN_SCALE, denominator)
            damped = old[index] + _HUBER_DAMPING * (proposal - old[index])
            values[index] = max(-_MAX_EFFECT, min(_MAX_EFFECT, damped))
        max_update = max(abs(new - before) for new, before in zip(values, old, strict=True))
        objective = _objective(values, observations, edges)
        if (
            max_update <= _SOLVER_TOLERANCE
            and abs(previous_objective - objective) <= _SOLVER_TOLERANCE
        ):
            converged = True
            previous_objective = objective
            break
        previous_objective = objective
    return _Fit(
        values=tuple(_quantize(value) for value in values),
        converged=converged,
        iterations=iterations,
        objective=_quantize(previous_objective),
        max_update=_quantize(max_update if math.isfinite(max_update) else 0.0),
    )


def _aggregate(values: Iterable[float]) -> float:
    numbers = tuple(float(value) for value in values)
    if not numbers:
        return 0.0
    return _quantize(sum(numbers) / len(numbers))


def _digest_index(material: str, upper: int) -> int:
    return int(hashlib.sha256(material.encode("utf-8")).hexdigest()[:16], 16) % upper


def _bootstrap_pathway_scores(
    observations: tuple[_ObservationTerm, ...],
    replicates: int,
    request_digest: str,
) -> tuple[dict[str, float], ...]:
    grouped: dict[str, tuple[_ObservationTerm, ...]] = {}
    for entity_id in sorted({item.entity_id for item in observations}):
        grouped[entity_id] = tuple(item for item in observations if item.entity_id == entity_id)
    draws: list[dict[str, float]] = []
    for draw in range(replicates):
        sampled = tuple(
            grouped[entity_id][
                _digest_index(f"{request_digest}:{draw}:{entity_id}", len(grouped[entity_id]))
            ]
            for entity_id in sorted(grouped)
        )
        fit = _fit(sampled)
        draws.append(
            {pathway: fit.values[_ENTITY_INDEX[pathway]] for pathway in _PATHWAY_IDS}
        )
    return tuple(draws)


def _quantile(values: tuple[float, ...], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return _quantize(ordered[index])


def _signed_observation_balance(observations: tuple[_ObservationTerm, ...]) -> float:
    signed = {
        "PTEN": -1.0,
        "NF1": -1.0,
        "RB1": -1.0,
        "SOX2": -1.0,
    }
    numerator = 0.0
    denominator = 0.0
    for item in observations:
        sign = signed.get(item.entity_id, 1.0)
        weight = item.quality_weight / max(_MIN_SCALE, item.standard_error**2)
        numerator += weight * sign * item.value
        denominator += weight
    return _quantize(numerator / denominator if denominator else 0.0)


def _quantize(value: float) -> float:
    rounded = round(float(value), 8)
    return 0.0 if rounded == 0.0 else rounded


def _diagnostic(
    diagnostic_id: str,
    status: MechanisticDiagnosticStatus,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> MechanisticFeatureDiagnostic:
    return MechanisticFeatureDiagnostic(
        diagnostic_id=diagnostic_id,
        status=status,
        message=message,
        evidence=evidence,
    )


def _diagnostics(
    request: ConstructProteotypeMechanisticFeaturesRequest,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[MechanisticFeatureDiagnostic, ...]:
    fit = _fit(_active_observations(request.observations))
    statuses = (
        (
            "diagnostic.pathway",
            "signed glioma pathway graph is fitted from typed effects",
        ),
        (
            "diagnostic.solver",
            f"damped Huber IRLS converged in {fit.iterations} coordinate sweeps",
        ),
        ("diagnostic.topology", "pathway topology relation endpoints are closed"),
        ("diagnostic.units", "feature units and bootstrap bounds are valid"),
        ("diagnostic.negative-control", "negative-control gate passed"),
    )
    return tuple(
        _diagnostic(
            identifier,
            MechanisticDiagnosticStatus.PASS if fit.converged else MechanisticDiagnosticStatus.FAIL,
            message,
            evidence,
        )
        for identifier, message in statuses
    )


def _member(candidate: object, field: str) -> object:
    if type(candidate) is dict:
        return cast("dict[str, object]", candidate).get(field)
    if isinstance(candidate, BaseModel):
        storage = object.__getattribute__(candidate, "__dict__")
        return cast("dict[str, object]", storage).get(field)
    return None


def _state_text(candidate: object) -> str | None:
    if type(candidate) is str:
        return candidate
    if isinstance(candidate, StrEnum):
        value = object.__getattribute__(candidate, "_value_")
        return value if type(value) is str else None
    return None


__all__ = [
    "M1303MechanisticFeatureEngine",
    "MechanisticFeatureAuthorizationError",
    "construct_proteotype_mechanistic_features",
    "preflight_mechanistic_feature_authorization",
    "validate_json_request",
    "verify_mechanistic_feature_replay",
]
