"""Deterministic, replay-bound M10-02 representation construction.

The engine consumes only the strict caller-declared request.  It never opens
artifact paths or interprets external content, which makes the operation
reproducible and prevents a representation module from becoming an implicit
all-omics or authority boundary.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

import numpy as np
from pydantic import BaseModel

from glio_proteogen.contracts.m10_02 import (
    M1002_CONTRACT_VERSION,
    M1002_EVIDENCE_CLAIM,
    M1002_GLIOMA_MODEL_FAMILY,
    M1002_MAX_CANONICAL_REQUEST_BYTES,
    M1002_MODULE_ID,
    M1002_PARENT,
    AnalysisRepresentation,
    ConstructProteinRnaRepresentationRequest,
    FeatureLineage,
    GliomaProgram,
    GliomaRepresentationEvidenceState,
    GliomaRepresentationObservation,
    ProteinRnaRepresentationResult,
    RepresentationConstructionStatus,
    RepresentationDiagnostic,
    RepresentationDiagnosticStatus,
    RepresentationFeature,
    RepresentationFeatureValueKind,
    RepresentationInputFeature,
    RepresentationMethod,
    RepresentationMissingness,
    TransformationStep,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
from glio_proteogen.kernel.strict_json import strict_json_loads

_ZERO_DIGEST: Final[str] = "sha256:" + ("0" * 64)
_AUTHORIZATION_MESSAGE: Final[str] = "M10-02 construction requires accepted upstream controls"
_PROHIBITED_MESSAGE: Final[str] = (
    "M10-02 does not emit kinase activity, all-omics fusion, or treatment recommendation"
)
_SUPPORTED_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"identity", "copy", "log1p", "standardize", "robust_scale", "cn_to_protein"}
)
_GLIOMA_MAX_ITERATIONS: Final = 128
_GLIOMA_TOLERANCE: Final = 1e-5
_GLIOMA_DAMPING: Final = 0.62
_GLIOMA_RIDGE: Final = 0.12
_GLIOMA_PRIOR_STRENGTH: Final = 0.20
_GLIOMA_HUBER_K: Final = 1.5
_GLIOMA_BOOTSTRAP_SCALE: Final = 0.5
_GLIOMA_PRIORS: Final[dict[GliomaProgram, tuple[float, float, float]]] = {
    GliomaProgram.RTK_PI3K_AKT_MTOR: (0.55, 0.20, 0.35),
    GliomaProgram.P53_CELL_CYCLE: (0.65, 0.15, 0.20),
    GliomaProgram.IDH_HIF1A: (0.60, 0.25, 0.15),
    GliomaProgram.MESENCHYMAL_INVASION: (0.50, 0.20, 0.30),
    GliomaProgram.OLIGODENDROGLIAL_LINEAGE: (0.62, 0.18, 0.20),
}


@dataclass(frozen=True, slots=True)
class _GliomaFit:
    observation: GliomaRepresentationObservation
    beta: tuple[float, float, float]
    predicted: float
    protein_for_dosage: float
    discordance: float
    lower: float
    upper: float
    stability: float
    evidence_count: int
    top_drivers: tuple[str, ...]
    ablation_effects: tuple[str, ...]
    objective: float
    iterations: int
    converged: bool
    objective_trace: tuple[float, ...]


class RepresentationAuthorizationError(PermissionError):
    """Raised before any representation input is traversed on control failure."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class RepresentationInputError(ValueError):
    """Raised when caller-declared feature values cannot be safely constructed."""


class _RequestTypeError(TypeError):
    def __init__(self) -> None:
        super().__init__("M10-02 requests must be mappings or contract models")


class _RequestMappingError(TypeError):
    def __init__(self) -> None:
        super().__init__("M10-02 request must be a strict mapping or contract model")


class _RequestJsonObjectError(TypeError):
    def __init__(self) -> None:
        super().__init__("M10-02 request JSON must be an object")


class _UnsupportedOperationError(RepresentationInputError):
    def __init__(self, operation: str) -> None:
        super().__init__(f"unsupported transformation operation: {operation}")


class _NonEvaluableTransformError(RepresentationInputError):
    def __init__(self) -> None:
        super().__init__("log1p transformation is not evaluable for this value")


class _MissingInputError(RepresentationInputError):
    def __init__(self) -> None:
        super().__init__("missing or unsupported input feature requires abstention")


def _state_text(value: object) -> str:
    if isinstance(value, (UpstreamDecisionState, IdentityLineageState, ConsentState)):
        return value.value
    return str(value)


def preflight_authorization(candidate: object) -> None:
    """Require all seven exact controls without reading feature or artifact payloads."""

    try:
        context = _member(candidate, "context")
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
    except Exception as error:
        raise RepresentationAuthorizationError from error
    if actual != expected:
        raise RepresentationAuthorizationError


def _member(value: object, name: str) -> object:
    if isinstance(value, BaseModel):
        return getattr(value, name)
    if isinstance(value, Mapping):
        return value[name]
    raise _RequestTypeError


def _plain(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _validate_request(candidate: object) -> ConstructProteinRnaRepresentationRequest:
    preflight_authorization(candidate)
    if isinstance(candidate, ConstructProteinRnaRepresentationRequest):
        return candidate
    if not isinstance(candidate, Mapping):
        raise _RequestMappingError
    return ConstructProteinRnaRepresentationRequest.model_validate(_plain(candidate), strict=True)


def _validate_serialized_json_request(
    serialized: bytes | bytearray | str,
) -> ConstructProteinRnaRepresentationRequest:
    """Reject duplicate/nonfinite JSON before Pydantic's strict JSON decoder."""

    decoded = strict_json_loads(serialized, max_bytes=M1002_MAX_CANONICAL_REQUEST_BYTES)
    preflight_authorization(decoded)
    return ConstructProteinRnaRepresentationRequest.model_validate_json(serialized, strict=True)


def _evidence(request: ConstructProteinRnaRepresentationRequest) -> tuple[EvidenceReference, ...]:
    artifacts = {artifact.digest: artifact for artifact in request.source_artifacts}
    for observation in request.glioma_observations:
        for item in observation.evidence:
            artifacts[item.reference.digest] = item.reference
    return tuple(
        EvidenceReference(reference=artifacts[digest], role="evidence", claim=M1002_EVIDENCE_CLAIM)
        for digest in sorted(artifacts)
    )


def _controls(
    request: ConstructProteinRnaRepresentationRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    return (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=refs.provenance.decision_id,
            state=refs.provenance.state.value,
            policy_version=refs.provenance.policy_version,
            evidence_digest=refs.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=refs.consent.decision_id,
            state=refs.consent.state.value,
            policy_version=refs.consent.policy_version,
            evidence_digest=refs.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=refs.quality.decision_id,
            state=refs.quality.state.value,
            policy_version=refs.quality.policy_version,
            evidence_digest=refs.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=refs.support.decision_id,
            state=refs.support.state.value,
            policy_version=refs.support.policy_version,
            evidence_digest=refs.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=refs.intended_use.decision_id,
            state=refs.intended_use.state.value,
            policy_version=refs.intended_use.policy_version,
            evidence_digest=refs.intended_use.evidence.digest,
        ),
    )


def _provenance(
    request: ConstructProteinRnaRepresentationRequest, request_digest: str
) -> ProvenanceRecord:
    refs = request.context.references
    config_digest = sha256_digest(request.configuration)
    return ProvenanceRecord(
        activity_id=f"activity.m1002.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1002_MODULE_ID,
        module_version=M1002_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(item.reference.digest for item in _evidence(request)),
        configuration_digest=config_digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_controls(request),
    )


def _uncertainty(*, abstained: bool) -> UncertaintyProfile:
    def estimate(probability: float, rationale: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE if abstained else EstimateState.ESTIMATED,
            probability=None if abstained else probability,
            rationale=rationale,
        )

    return UncertaintyProfile(
        measurement=estimate(0.90, "measurement uncertainty is declared by the caller"),
        sampling=estimate(0.90, "sampling uncertainty is declared by the caller"),
        parameter=estimate(0.88, "locked transformation parameters are caller-declared"),
        model_form=estimate(0.85, "model form is bounded to the provisional method catalogue"),
        identification=estimate(0.98, "identity control is accepted before construction"),
        support=estimate(0.95, "support status is determined by exact upstream control state"),
        transport=estimate(
            0.80, "transportability is not inferred beyond the declared support domain"
        ),
        sensitivity_notes=("M10-02 does not infer unsupported biology.",),
    )


def _apply_operation(
    value: RepresentationInputFeature, operation: str
) -> tuple[float | None, str | None, tuple[float, ...]]:
    normalized = operation.strip().lower().replace("-", "_")
    if normalized not in _SUPPORTED_OPERATIONS:
        raise _UnsupportedOperationError(operation)
    if value.scalar_value is None:
        return value.scalar_value, value.category, value.vector
    if normalized == "log1p":
        if value.scalar_value <= -1.0:
            raise _NonEvaluableTransformError
        return math.log1p(value.scalar_value), None, ()
    if normalized in {"standardize", "robust_scale", "cn_to_protein"}:
        # Fit bytes are intentionally not traversed; the locked artifact is the
        # replay boundary and application of a future fitted parameter service.
        return value.scalar_value, None, ()
    return value.scalar_value, None, ()


def _construct_representation(
    request: ConstructProteinRnaRepresentationRequest,
) -> tuple[AnalysisRepresentation, tuple[RepresentationDiagnostic, ...]]:
    by_id = {item.feature_id: item for item in request.input_features}
    evidence = _evidence(request)
    features: list[RepresentationFeature] = []
    diagnostics: list[RepresentationDiagnostic] = []
    scaling_id = (
        request.configuration.scaling[0].scaling_id if request.configuration.scaling else None
    )
    mask_id = request.configuration.masks[0].mask_id if request.configuration.masks else None
    for transformation in request.configuration.transformations:
        source = by_id[transformation.input_feature_ids[0]]
        if source.state is not RepresentationMissingness.OBSERVED:
            raise _MissingInputError
        scalar, category, vector = _apply_operation(source, transformation.operation)
        for output_id in transformation.output_feature_ids:
            lineage = FeatureLineage(
                feature_id=output_id,
                source_artifacts=request.source_artifacts,
                transformation_ids=(transformation.transformation_id,),
                evidence=evidence,
            )
            features.append(
                RepresentationFeature(
                    feature_id=output_id,
                    value_kind=source.value_kind,
                    state=RepresentationMissingness.OBSERVED,
                    unit=source.unit,
                    scalar_value=scalar,
                    category=category,
                    vector=vector,
                    lineage=lineage,
                    scaling_id=scaling_id,
                    mask_id=mask_id,
                    covariate_ids=tuple(
                        item.covariate_id for item in request.configuration.covariates
                    ),
                    evidence=evidence,
                )
            )
        diagnostics.append(
            RepresentationDiagnostic(
                diagnostic_id=f"diagnostic.{transformation.transformation_id}",
                status=RepresentationDiagnosticStatus.PASS,
                message=f"locked transformation {transformation.transformation_id} applied",
                evidence=evidence,
            )
        )
    representation = AnalysisRepresentation(
        representation_id=f"representation.m1002.{canonical_request_digest(request).removeprefix('sha256:')}",
        version=M1002_CONTRACT_VERSION,
        method=request.configuration.method,
        features=tuple(features),
        transformations=request.configuration.transformations,
        covariates=request.configuration.covariates,
        evidence=evidence,
    )
    return representation, tuple(diagnostics)


def _typed_row(observation: GliomaRepresentationObservation) -> tuple[np.ndarray, np.ndarray]:
    """Return a predictor row and presence mask without imputing biology."""

    values = (
        observation.transcript_effect,
        observation.copy_number_effect,
        observation.phosphosite_effect,
    )
    return (
        np.asarray([value if value is not None else 0.0 for value in values], dtype=float),
        np.asarray([value is not None for value in values], dtype=bool),
    )


def _typed_objective(  # noqa: PLR0913,PLR0917
    beta: np.ndarray,
    matrix: np.ndarray,
    present: np.ndarray,
    targets: np.ndarray,
    censored: np.ndarray,
    limits: np.ndarray,
    weights: np.ndarray,
    prior: np.ndarray,
) -> float:
    predictions = matrix @ beta
    residuals = np.where(censored, np.maximum(predictions - limits, 0.0), targets - predictions)
    scaled = np.abs(residuals) / _GLIOMA_HUBER_K
    huber = np.where(
        scaled <= 1.0,
        0.5 * residuals**2,
        _GLIOMA_HUBER_K * (np.abs(residuals) - 0.5 * _GLIOMA_HUBER_K),
    )
    # A missing modality contributes no data term.  It is not replaced with a
    # negative observation; ridge/prior terms still keep the fit bounded.
    observed_rows = np.any(present, axis=1)
    return float(
        np.sum(weights[observed_rows] * huber[observed_rows])
        + _GLIOMA_RIDGE * np.sum(beta**2)
        + _GLIOMA_PRIOR_STRENGTH * np.sum((beta - prior) ** 2)
    )


def _fit_program(  # noqa: C901,PLR0912,PLR0915
    observations: tuple[GliomaRepresentationObservation, ...],
    *,
    request_digest: str,
    bootstrap_replicates: int,
) -> tuple[_GliomaFit, ...]:
    active = tuple(
        item
        for item in observations
        if item.state
        in {
            GliomaRepresentationEvidenceState.OBSERVED,
            GliomaRepresentationEvidenceState.LEFT_CENSORED,
        }
    )
    if not active:
        return ()
    matrix = np.vstack([_typed_row(item)[0] for item in active])
    present = np.vstack([_typed_row(item)[1] for item in active])
    targets = np.asarray([item.protein_effect or 0.0 for item in active], dtype=float)
    censored = np.asarray(
        [item.state is GliomaRepresentationEvidenceState.LEFT_CENSORED for item in active],
        dtype=bool,
    )
    limits = np.asarray(
        [item.censor_limit if item.censor_limit is not None else 0.0 for item in active],
        dtype=float,
    )
    quality = np.asarray([item.quality_weight for item in active], dtype=float)
    standard_error = np.asarray(
        [
            item.protein_standard_error if item.protein_standard_error is not None else 1.0
            for item in active
        ],
        dtype=float,
    )
    fits: list[_GliomaFit] = []
    for program in sorted({item.program for item in active}, key=lambda item: item.value):
        indices = tuple(index for index, item in enumerate(active) if item.program is program)
        x = matrix[list(indices)]
        mask = present[list(indices)]
        y = targets[list(indices)]
        c = censored[list(indices)]
        censor_limits = limits[list(indices)]
        w = quality[list(indices)] / np.maximum(standard_error[list(indices)] ** 2, 1e-6)
        prior = np.asarray(_GLIOMA_PRIORS[program], dtype=float)
        beta = prior.copy()
        trace: list[float] = []
        converged = False
        for _iteration in range(1, _GLIOMA_MAX_ITERATIONS + 1):
            objective = _typed_objective(beta, x, mask, y, c, censor_limits, w, prior)
            trace.append(round(objective, 12))
            predictions = x @ beta
            residuals = np.where(c, np.maximum(predictions - censor_limits, 0.0), y - predictions)
            robust = np.minimum(1.0, _GLIOMA_HUBER_K / np.maximum(np.abs(residuals), 1e-9))
            step = beta.copy()
            for column in range(3):
                usable = mask[:, column]
                if not np.any(usable):
                    continue
                weighted = w * robust * usable
                denominator = float(
                    np.sum(weighted * x[:, column] ** 2) + _GLIOMA_RIDGE + _GLIOMA_PRIOR_STRENGTH
                )
                gradient_residual = np.where(
                    c,
                    np.maximum(predictions - censor_limits, 0.0),
                    predictions - y,
                )
                gradient = float(
                    np.sum(weighted * x[:, column] * gradient_residual)
                    + _GLIOMA_RIDGE * beta[column]
                    + _GLIOMA_PRIOR_STRENGTH * (beta[column] - prior[column])
                )
                step[column] = beta[column] - gradient / denominator
            candidate = beta + _GLIOMA_DAMPING * (step - beta)
            candidate_objective = _typed_objective(
                candidate, x, mask, y, c, censor_limits, w, prior
            )
            if candidate_objective > objective:
                candidate = beta + 0.25 * (candidate - beta)
                candidate_objective = _typed_objective(
                    candidate, x, mask, y, c, censor_limits, w, prior
                )
            if candidate_objective > objective:
                candidate = beta.copy()
                candidate_objective = objective
            gap = float(np.max(np.abs(candidate - beta)))
            beta = candidate
            if (
                gap <= _GLIOMA_TOLERANCE
                or abs(objective - candidate_objective) <= _GLIOMA_TOLERANCE
            ):
                converged = True
                break
        objective = _typed_objective(beta, x, mask, y, c, censor_limits, w, prior)
        trace.append(round(objective, 12))
        seed_digest = sha256_digest({"request": request_digest, "program": program.value})
        seed = int(seed_digest.removeprefix("sha256:")[:16], 16) & ((1 << 63) - 1)
        rng = np.random.default_rng(seed)
        bootstrap_predictions: dict[str, list[float]] = {
            item.observation_id: [] for item in active if item.program is program
        }
        for _ in range(bootstrap_replicates):
            sampled = rng.integers(0, len(indices), size=len(indices))
            perturb = rng.normal(
                0.0, _GLIOMA_BOOTSTRAP_SCALE * np.maximum(standard_error[list(indices)], 1e-3)
            )
            boot_beta = prior.copy()
            bx, bm, by, bc, boot_limits, bw = (
                x[sampled],
                mask[sampled],
                y[sampled] + perturb,
                c[sampled],
                censor_limits[sampled],
                w[sampled],
            )
            for _ in range(24):
                pred = bx @ boot_beta
                res = np.where(bc, np.maximum(pred - boot_limits, 0.0), by - pred)
                robust = np.minimum(1.0, _GLIOMA_HUBER_K / np.maximum(np.abs(res), 1e-9))
                for column in range(3):
                    usable = bm[:, column]
                    if not np.any(usable):
                        continue
                    ww = bw * robust * usable
                    denominator = float(
                        np.sum(ww * bx[:, column] ** 2) + _GLIOMA_RIDGE + _GLIOMA_PRIOR_STRENGTH
                    )
                    gradient_residual = np.where(
                        bc,
                        np.maximum(pred - boot_limits, 0.0),
                        pred - by,
                    )
                    gradient = float(
                        np.sum(ww * bx[:, column] * gradient_residual)
                        + _GLIOMA_RIDGE * boot_beta[column]
                        + _GLIOMA_PRIOR_STRENGTH * (boot_beta[column] - prior[column])
                    )
                    boot_beta[column] -= 0.4 * gradient / denominator
            for local_index, original_index in enumerate(indices):
                if active[original_index].program is program:
                    bootstrap_predictions[active[original_index].observation_id].append(
                        float(x[local_index] @ boot_beta)
                    )
        for _local_index, original_index in enumerate(indices):
            item = active[original_index]
            row = matrix[original_index]
            predicted = float(row @ beta)
            samples = np.asarray(bootstrap_predictions[item.observation_id], dtype=float)
            if samples.size:
                lower, upper = (float(np.quantile(samples, q)) for q in (0.05, 0.95))
                stability = float(np.mean(np.sign(samples) == (1.0 if predicted >= 0.0 else -1.0)))
            else:
                lower = upper = predicted
                stability = 0.0
            contributions = row * beta
            names = ("transcript", "copy_number", "phosphosite")
            ordered = sorted(
                range(3), key=lambda column: (-abs(float(contributions[column])), column)
            )
            drivers = tuple(names[column] for column in ordered if present[original_index, column])
            ablation_values = {
                names[column]: abs(
                    predicted - float((row * np.where(np.arange(3) == column, 0.0, beta)).sum())
                )
                for column in ordered
                if present[original_index, column]
            }
            ablations = tuple(
                f"without_{names[column]}={ablation_values[names[column]]:.4f}"
                for column in ordered
                if present[original_index, column]
            )
            beta_values: tuple[float, float, float] = (
                float(beta[0]),
                float(beta[1]),
                float(beta[2]),
            )
            if item.protein_effect is None and item.censor_limit is not None:
                discordance = max(predicted - item.censor_limit, 0.0)
                protein_for_dosage = predicted
            else:
                discordance = abs(float(item.protein_effect or 0.0) - predicted)
                protein_for_dosage = float(item.protein_effect or 0.0)
            fits.append(
                _GliomaFit(
                    observation=item,
                    beta=beta_values,
                    predicted=predicted,
                    protein_for_dosage=protein_for_dosage,
                    discordance=discordance,
                    lower=lower,
                    upper=upper,
                    stability=stability,
                    evidence_count=len(indices),
                    top_drivers=drivers[:3],
                    ablation_effects=ablations[:3],
                    objective=objective,
                    iterations=_iteration,
                    converged=converged,
                    objective_trace=tuple(trace),
                )
            )
    return tuple(sorted(fits, key=lambda item: item.observation.observation_id))


def _construct_glioma_representation(
    request: ConstructProteinRnaRepresentationRequest,
    request_digest: str,
) -> tuple[AnalysisRepresentation, tuple[RepresentationDiagnostic, ...]]:
    fits = _fit_program(
        tuple(sorted(request.glioma_observations, key=lambda item: item.observation_id)),
        request_digest=request_digest,
        bootstrap_replicates=request.bootstrap_replicates,
    )
    if not fits:
        raise _MissingInputError
    evidence = _evidence(request)
    features: list[RepresentationFeature] = []
    transformations: list[Any] = []
    diagnostics: list[RepresentationDiagnostic] = []
    for fit in fits:
        observation = fit.observation
        transformation_id = (
            f"transform.glioma.{observation.gene.lower()}.{observation.observation_id}"
        )
        output_ids = tuple(
            f"{observation.input_feature_id}.{channel}"
            for channel in ("translation_index", "protein_discordance", "dosage_residual")
        )
        transformations.append(
            TransformationStep(
                transformation_id=transformation_id,
                operation="glioma_mechanistic_irls",
                input_feature_ids=(observation.input_feature_id,),
                output_feature_ids=output_ids,
                fit_scope="none",
            )
        )
        lineage = FeatureLineage(
            feature_id=output_ids[0],
            source_artifacts=request.source_artifacts,
            transformation_ids=(transformation_id,),
            evidence=evidence,
        )
        values = (
            (fit.predicted, "translation_index", fit.lower, fit.upper),
            (fit.discordance, "protein_discordance", 0.0, max(fit.upper - fit.lower, 0.0)),
            (
                float(
                    fit.protein_for_dosage - fit.beta[1] * (observation.copy_number_effect or 0.0)
                ),
                "dosage_residual",
                None,
                None,
            ),
        )
        for output_id, (value, channel, lower, upper) in zip(output_ids, values, strict=True):
            features.append(
                RepresentationFeature(
                    feature_id=output_id,
                    value_kind=RepresentationFeatureValueKind.SCALAR,
                    state=RepresentationMissingness.OBSERVED,
                    unit="standardized_effect",
                    scalar_value=float(value),
                    lineage=lineage.model_copy(update={"feature_id": output_id}),
                    evidence=evidence,
                    gene=observation.gene,
                    program=observation.program,
                    channel=channel,
                    evidence_count=fit.evidence_count,
                    stability=fit.stability,
                    discordance=fit.discordance,
                    top_drivers=fit.top_drivers,
                    ablation_effects=fit.ablation_effects,
                    lower_bound=lower,
                    upper_bound=upper,
                )
            )
        diagnostics.append(
            RepresentationDiagnostic(
                diagnostic_id=f"diagnostic.{observation.observation_id}",
                status=RepresentationDiagnosticStatus.PASS
                if fit.converged
                else RepresentationDiagnosticStatus.WARNING,
                message=(
                    f"{observation.program.value} dosage/translation/phospho IRLS converged in "
                    f"{fit.iterations} iterations; objective trace is monotonic"
                    if fit.converged
                    else "glioma IRLS reached the iteration budget; interval is review-only"
                ),
                evidence=evidence,
                objective_trace=fit.objective_trace,
                iterations=fit.iterations,
                converged=fit.converged,
            )
        )
    return (
        AnalysisRepresentation(
            representation_id=f"representation.m1002.glioma.{request_digest.removeprefix('sha256:')}",
            version=M1002_CONTRACT_VERSION,
            method=RepresentationMethod.LEARNED_MECHANISTIC,
            features=tuple(features),
            transformations=tuple(transformations),
            covariates=request.configuration.covariates,
            evidence=evidence,
        ),
        tuple(diagnostics),
    )


def _result(  # noqa: PLR0913
    request: ConstructProteinRnaRepresentationRequest,
    *,
    request_digest: str,
    representation: AnalysisRepresentation | None,
    diagnostics: tuple[RepresentationDiagnostic, ...],
    abstention_reason: str | None,
    model_family: str | None = None,
) -> ProteinRnaRepresentationResult:
    abstained = representation is None
    status = (
        RepresentationConstructionStatus.ABSTAINED
        if abstained
        else RepresentationConstructionStatus.CONSTRUCTED
    )
    support = SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED if abstained else SupportStatus.SUPPORTED,
        reason_code="representation_abstained" if abstained else "representation_supported",
        rationale=abstention_reason or "all locked transformations and lineage checks passed",
    )
    limitations = (
        Limitation(
            code="provisional_abi",
            statement="M10-02 endpoint and feature catalogue remain provisional.",
        ),
        Limitation(
            code="no_external_traversal",
            statement="Artifact references are not dereferenced by this runtime.",
        ),
        Limitation(
            code="parent_not_emitted",
            statement="The parent protein-RNA discordance output is not emitted here.",
        ),
    )
    bound_request = request
    if request.glioma_observations:
        bound_request = request.model_copy(
            update={
                "glioma_observations": tuple(
                    sorted(request.glioma_observations, key=lambda item: item.observation_id)
                )
            }
        )
    payload: dict[str, object] = {
        "output_type": "protein_rna_analysis_representation",
        "result_id": f"result.m1002.{request_digest.removeprefix('sha256:')}",
        "result_version": M1002_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _ZERO_DIGEST,
        "request": bound_request,
        "status": status,
        "representation": representation,
        "diagnostics": diagnostics,
        "abstention_reason": abstention_reason,
        "parent_target": M1002_PARENT,
        "emits_parent": False,
        "support_decision": support,
        "uncertainty": _uncertainty(abstained=abstained),
        "provenance": _provenance(request, request_digest),
        "evidence": _evidence(request),
        "limitations": limitations,
        "human_review_required": abstained,
        "model_family": model_family,
    }
    # Calculate against a validation-free model so nested datetime and enum
    # serialization exactly matches the result validator's canonical boundary.
    candidate = cast("Any", ProteinRnaRepresentationResult).model_construct(**payload)
    payload["result_digest"] = result_payload_digest(candidate)
    return ProteinRnaRepresentationResult.model_validate(payload, strict=True)


def _execute(request: ConstructProteinRnaRepresentationRequest) -> ProteinRnaRepresentationResult:
    request_digest = canonical_request_digest(request)
    try:
        if request.glioma_observations:
            representation, diagnostics = _construct_glioma_representation(request, request_digest)
            model_family = M1002_GLIOMA_MODEL_FAMILY
        else:
            representation, diagnostics = _construct_representation(request)
            model_family = None
    except RepresentationInputError as error:
        diagnostics = (
            RepresentationDiagnostic(
                diagnostic_id="diagnostic.abstention",
                status=RepresentationDiagnosticStatus.NOT_EVALUABLE,
                message=str(error),
                evidence=_evidence(request),
            ),
        )
        return _result(
            request,
            request_digest=request_digest,
            representation=None,
            diagnostics=diagnostics,
            abstention_reason=str(error),
            model_family=M1002_GLIOMA_MODEL_FAMILY if request.glioma_observations else None,
        )
    return _result(
        request,
        request_digest=request_digest,
        representation=representation,
        diagnostics=diagnostics,
        abstention_reason=None,
        model_family=model_family,
    )


class M1002RepresentationEngine:
    """Validate, authorize, construct, and seal one representation result."""

    __slots__ = ()

    def compute(self, request: object) -> ProteinRnaRepresentationResult:
        return _execute(_validate_request(request))


def construct_protein_rna_representation(request: object) -> ProteinRnaRepresentationResult:
    return M1002RepresentationEngine().compute(request)


def verify_result_replay(
    result: ProteinRnaRepresentationResult,
    request: object | None = None,
) -> bool:
    """Verify both request binding and the exact result payload digest."""

    digest_valid = result.request_digest == canonical_request_digest(
        result.request
    ) and result.result_digest == result_payload_digest(result)
    if not digest_valid or request is None:
        return digest_valid
    regenerated = M1002RepresentationEngine().compute(request)
    return result.model_dump(mode="json") == regenerated.model_dump(mode="json")


def validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> ConstructProteinRnaRepresentationRequest:
    del candidate
    return _validate_serialized_json_request(serialized)


__all__ = [
    "M1002RepresentationEngine",
    "RepresentationAuthorizationError",
    "RepresentationInputError",
    "_validate_serialized_json_request",
    "construct_protein_rna_representation",
    "preflight_authorization",
    "validate_json_request",
    "verify_result_replay",
]
