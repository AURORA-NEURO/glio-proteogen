"""Caller-owned GBM RNA composition runtime.

This module is deliberately narrower than the source-admission profile in
``profile.py``.  It executes the repository's exact Dirichlet--multinomial
simplex solver only when a caller supplies a complete, positive reference
signature matrix and a count vector.  No GBmap cells, fitted artifact, or
patient data are bundled here.  The returned weights are RNA mixture weights;
they are never relabelled as histologic cell fractions.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Final, Literal, Self

import numpy as np
from pydantic import Field, model_validator

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Identifier, NonEmptyStr, Sha256Digest

from .errors import GbmapInputError
from .evaluation import OodDiagnostics, evaluate_ood_diagnostics
from .simplex import (
    ReferenceMixtureSolution,
    SimplexSolverConfiguration,
    reference_signature_condition_number,
    solve_reference_mixture,
    verify_objective_trace,
)

MIXTURE_ALGORITHM_ID: Final = "gbm-rna-composition"
MIXTURE_ALGORITHM_VERSION: Final = "0.1.0"
MIXTURE_PROFILE_ID: Final = f"{MIXTURE_ALGORITHM_ID}/{MIXTURE_ALGORITHM_VERSION}"
EXPECTED_NUMPY_VERSION: Final = "2.5.2"
MAX_MIXTURE_FEATURES: Final = 512
MAX_MIXTURE_LINEAGES: Final = 32
MAX_MIXTURE_ITERATIONS: Final = 500
MAX_MIXTURE_REQUEST_BYTES: Final = 2 * 1_024 * 1_024
MAX_MIXTURE_RESULT_BYTES: Final = 4 * 1_024 * 1_024
MIXTURE_KKT_TOLERANCE: Final = 1e-5
MIXTURE_L1_STEP_TOLERANCE: Final = 1e-5
MIXTURE_RELATIVE_OBJECTIVE_TOLERANCE: Final = 1e-9
_PROBABILITY_TOLERANCE: Final = 1e-10
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
MAX_MIXTURE_BOOTSTRAP_REPLICATES: Final = 256
MIXTURE_BOOTSTRAP_MIN_REPLICATES: Final = 8
MIXTURE_BOOTSTRAP_LOWER_QUANTILE: Final = 0.05
MIXTURE_BOOTSTRAP_UPPER_QUANTILE: Final = 0.95
MIXTURE_BOOTSTRAP_SAMPLING_POLICY: Final = "fitted_dirichlet_multinomial_posterior_predictive_v1"
MIXTURE_BOOTSTRAP_MAX_ITERATIONS: Final = 2_000
MIXTURE_BOOTSTRAP_KKT_TOLERANCE: Final = 1e-3
MIXTURE_BOOTSTRAP_L1_STEP_TOLERANCE: Final = 1e-8
MIXTURE_BOOTSTRAP_RELATIVE_OBJECTIVE_TOLERANCE: Final = 1e-10


def _finite_probability_vector(values: tuple[float, ...], *, name: str) -> None:
    if len(values) < 2:
        raise ValueError(f"{name} must contain at least two entries")
    if any(not math.isfinite(value) or value <= 0.0 for value in values):
        raise ValueError(f"{name} must contain finite, strictly positive values")
    if not math.isclose(math.fsum(values), 1.0, rel_tol=0.0, abs_tol=_PROBABILITY_TOLERANCE):
        raise ValueError(f"{name} must sum to one")


class GbmMixtureReference(FrozenModel):
    """One caller-provided lineage signature on a shared gene axis."""

    reference_id: Identifier
    signature: tuple[float, ...] = Field(min_length=2, max_length=MAX_MIXTURE_FEATURES)

    @model_validator(mode="after")
    def signature_is_positive_probability(self) -> Self:
        _finite_probability_vector(self.signature, name="reference signature")
        return self


class GbmMixtureRequest(FrozenModel):
    """Strict request for source-independent, count-native GBM composition."""

    profile_id: Literal["gbm-rna-composition/0.1.0"] = "gbm-rna-composition/0.1.0"
    sample_id: Identifier
    feature_ids: tuple[Identifier, ...] = Field(default=(), max_length=MAX_MIXTURE_FEATURES)
    counts: tuple[int, ...] = Field(min_length=2, max_length=MAX_MIXTURE_FEATURES)
    references: tuple[GbmMixtureReference, ...] = Field(
        min_length=1,
        max_length=MAX_MIXTURE_LINEAGES,
    )
    unknown_background: tuple[float, ...] = Field(
        min_length=2,
        max_length=MAX_MIXTURE_FEATURES,
    )
    concentration: float = Field(gt=0.0, le=1_000_000.0)
    lambda_mass: float = Field(ge=0.0, le=1_000_000.0)
    lambda_shape: float = Field(ge=0.0, le=1_000_000.0)
    initial_unknown_mass: float = Field(ge=0.0, lt=1.0)
    max_iterations: int = Field(gt=0, le=MAX_MIXTURE_ITERATIONS)
    bootstrap_replicates: int = Field(default=0, ge=0, le=MAX_MIXTURE_BOOTSTRAP_REPLICATES)
    source_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=32)
    provenance_note: NonEmptyStr

    @model_validator(mode="after")
    def request_is_closed_and_canonical(self) -> Self:
        if len(self.feature_ids) != len(self.counts):
            raise ValueError("feature_ids and counts must share one axis")
        if len(self.feature_ids) != len(self.unknown_background):
            raise ValueError("unknown_background must match the feature axis")
        if len(set(self.feature_ids)) != len(self.feature_ids):
            raise ValueError("feature identifiers must be unique")
        if any(isinstance(value, bool) or value < 0 for value in self.counts):
            raise ValueError("counts must be non-negative integers")
        if sum(self.counts) <= 0:
            raise ValueError("counts must have positive depth")
        if len({item.reference_id for item in self.references}) != len(self.references):
            raise ValueError("reference identifiers must be unique")
        _finite_probability_vector(self.unknown_background, name="unknown background")
        for reference in self.references:
            if len(reference.signature) != len(self.feature_ids):
                raise ValueError("every reference signature must match the feature axis")
        if 0 < self.bootstrap_replicates < MIXTURE_BOOTSTRAP_MIN_REPLICATES:
            raise ValueError(
                "bootstrap replicates must be zero or at least eight"
            )
        matrix = np.asarray(
            [reference.signature for reference in self.references],
            dtype=np.float64,
        ).T
        condition = reference_signature_condition_number(matrix)
        if not math.isfinite(condition):
            raise ValueError("reference signatures are not identifiable")
        return self

    @property
    def request_digest(self) -> Sha256Digest:
        return canonical_request_digest(self)


class GbmMixtureProfile(FrozenModel):
    """Digest-bound profile for the caller-owned composition runtime."""

    profile_id: Literal["gbm-rna-composition/0.1.0"] = "gbm-rna-composition/0.1.0"
    algorithm_id: Literal["gbm-rna-composition"] = MIXTURE_ALGORITHM_ID
    algorithm_version: Literal["0.1.0"] = MIXTURE_ALGORITHM_VERSION
    numpy_version: Literal["2.5.2"] = EXPECTED_NUMPY_VERSION
    execution_scope: Literal["caller_supplied_reference_only"] = "caller_supplied_reference_only"
    output_semantics: Literal["rna_mixture_weights_with_unknown_mass"] = (
        "rna_mixture_weights_with_unknown_mass"
    )
    histologic_fraction_claim_permitted: Literal[False] = False
    clinical_use_permitted: Literal[False] = False
    solver: Literal["dirichlet_multinomial_adaptive_unknown_simplex"] = (
        "dirichlet_multinomial_adaptive_unknown_simplex"
    )
    max_features: Literal[512] = MAX_MIXTURE_FEATURES
    max_lineages: Literal[32] = MAX_MIXTURE_LINEAGES
    max_iterations: Literal[500] = MAX_MIXTURE_ITERATIONS
    kkt_tolerance: float = MIXTURE_KKT_TOLERANCE
    l1_step_tolerance: float = MIXTURE_L1_STEP_TOLERANCE
    relative_objective_tolerance: float = MIXTURE_RELATIVE_OBJECTIVE_TOLERANCE
    bootstrap_sampling_policy: Literal[
        "fitted_dirichlet_multinomial_posterior_predictive_v1"
    ] = MIXTURE_BOOTSTRAP_SAMPLING_POLICY
    bootstrap_lower_quantile: float = Field(
        default=MIXTURE_BOOTSTRAP_LOWER_QUANTILE,
        ge=MIXTURE_BOOTSTRAP_LOWER_QUANTILE,
        le=MIXTURE_BOOTSTRAP_LOWER_QUANTILE,
    )
    bootstrap_upper_quantile: float = Field(
        default=MIXTURE_BOOTSTRAP_UPPER_QUANTILE,
        ge=MIXTURE_BOOTSTRAP_UPPER_QUANTILE,
        le=MIXTURE_BOOTSTRAP_UPPER_QUANTILE,
    )
    max_bootstrap_replicates: Literal[256] = MAX_MIXTURE_BOOTSTRAP_REPLICATES
    bootstrap_max_iterations: Literal[2000] = MIXTURE_BOOTSTRAP_MAX_ITERATIONS
    bootstrap_kkt_tolerance: float = Field(
        default=MIXTURE_BOOTSTRAP_KKT_TOLERANCE,
        ge=MIXTURE_BOOTSTRAP_KKT_TOLERANCE,
        le=MIXTURE_BOOTSTRAP_KKT_TOLERANCE,
    )
    bootstrap_l1_step_tolerance: float = Field(
        default=MIXTURE_BOOTSTRAP_L1_STEP_TOLERANCE,
        ge=MIXTURE_BOOTSTRAP_L1_STEP_TOLERANCE,
        le=MIXTURE_BOOTSTRAP_L1_STEP_TOLERANCE,
    )
    bootstrap_relative_objective_tolerance: float = Field(
        default=MIXTURE_BOOTSTRAP_RELATIVE_OBJECTIVE_TOLERANCE,
        ge=MIXTURE_BOOTSTRAP_RELATIVE_OBJECTIVE_TOLERANCE,
        le=MIXTURE_BOOTSTRAP_RELATIVE_OBJECTIVE_TOLERANCE,
    )
    profile_digest: Sha256Digest

    @model_validator(mode="after")
    def digest_is_bound(self) -> Self:
        if self.profile_digest != profile_digest(self):
            raise ValueError("mixture profile digest does not match its constants")
        return self


class GbmMixtureWeight(FrozenModel):
    reference_id: Identifier
    rna_weight: float = Field(ge=0.0, le=1.0)
    rank: int = Field(ge=1, le=MAX_MIXTURE_LINEAGES)


class GbmMixtureWeightInterval(FrozenModel):
    """Empirical interval for one lineage weight from posterior-predictive draws."""

    reference_id: Identifier
    lower_bound: float = Field(ge=0.0, le=1.0)
    upper_bound: float = Field(ge=0.0, le=1.0)
    @model_validator(mode="after")
    def bounds_are_ordered(self) -> Self:
        if self.lower_bound > self.upper_bound:
            raise ValueError("mixture weight interval bounds must be ordered")
        return self


class GbmMixtureResult(FrozenModel):
    """Replay-closed composition result; weights are not cell fractions."""

    result_id: Identifier
    profile_id: Literal["gbm-rna-composition/0.1.0"] = "gbm-rna-composition/0.1.0"
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    sample_id: Identifier
    feature_ids: tuple[Identifier, ...] = Field(
        min_length=2,
        max_length=MAX_MIXTURE_FEATURES,
    )
    support: Literal["limited", "abstained"]
    known_weights: tuple[GbmMixtureWeight, ...] = Field(default=(), max_length=MAX_MIXTURE_LINEAGES)
    weight_intervals: tuple[GbmMixtureWeightInterval, ...] = Field(
        default=(), max_length=MAX_MIXTURE_LINEAGES
    )
    unknown_gene_mass: tuple[float, ...] = Field(default=(), max_length=MAX_MIXTURE_FEATURES)
    fitted_probabilities: tuple[float, ...] = Field(default=(), max_length=MAX_MIXTURE_FEATURES)
    unknown_mass: float | None = Field(default=None, ge=0.0, le=1.0)
    unknown_mass_lower_bound: float | None = Field(default=None, ge=0.0, le=1.0)
    unknown_mass_upper_bound: float | None = Field(default=None, ge=0.0, le=1.0)
    bootstrap_replicates_used: int = Field(
        default=0, ge=0, le=MAX_MIXTURE_BOOTSTRAP_REPLICATES
    )
    objective: float | None = Field(default=None, ge=0.0)
    initial_objective: float | None = Field(default=None, ge=0.0)
    iterations: int = Field(ge=0, le=MAX_MIXTURE_ITERATIONS)
    kkt_residual: float | None = Field(default=None, ge=0.0)
    signature_condition_number: float | None = Field(default=None, ge=0.0)
    objective_trace: tuple[float, ...] = Field(default=(), max_length=MAX_MIXTURE_ITERATIONS)
    trace_digest: Sha256Digest
    ood: OodDiagnostics | None = None
    abstention_reason: NonEmptyStr | None = None
    source_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=32)
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def result_is_closed(self) -> Self:
        if self.request_digest.startswith("sha256:") is False:
            raise ValueError("request digest must be sha256")
        if len(self.feature_ids) != len(self.unknown_gene_mass):
            raise ValueError("unknown gene mass must match the feature axis")
        if len(self.feature_ids) != len(self.fitted_probabilities):
            raise ValueError("fitted probabilities must match the feature axis")
        if len(set(self.feature_ids)) != len(self.feature_ids):
            raise ValueError("result feature identifiers must be unique")
        if self.support == "limited":
            if self.abstention_reason is not None or not self.known_weights:
                raise ValueError("limited result requires fitted weights")
            if len(self.feature_ids) < 2:
                raise ValueError("limited result requires a feature axis")
            if self.unknown_mass is None or not self.unknown_gene_mass:
                raise ValueError("limited result requires unknown mass")
            if any(
                not math.isfinite(value) or value < 0.0
                for value in (*self.unknown_gene_mass, *self.fitted_probabilities)
            ):
                raise ValueError("limited composition vectors must be finite and non-negative")
            if not math.isclose(
                math.fsum(self.fitted_probabilities),
                1.0,
                rel_tol=0.0,
                abs_tol=2e-10,
            ):
                raise ValueError("fitted probabilities must sum to one")
            if not math.isclose(
                math.fsum(self.unknown_gene_mass),
                self.unknown_mass,
                rel_tol=0.0,
                abs_tol=2e-10,
            ):
                raise ValueError("unknown mass does not match its gene-resolved vector")
            if not math.isclose(
                math.fsum(item.rna_weight for item in self.known_weights) + self.unknown_mass,
                1.0,
                rel_tol=0.0,
                abs_tol=2e-8,
            ):
                raise ValueError("known and unknown weights must share one simplex")
            if self.bootstrap_replicates_used == 0:
                if self.weight_intervals or any(
                    value is not None
                    for value in (self.unknown_mass_lower_bound, self.unknown_mass_upper_bound)
                ):
                    raise ValueError("intervals require bootstrap replicates")
            else:
                if self.bootstrap_replicates_used < MIXTURE_BOOTSTRAP_MIN_REPLICATES:
                    raise ValueError("bootstrap replicates used must be at least eight")
                if len(self.weight_intervals) != len(self.known_weights):
                    raise ValueError("bootstrap intervals must cover every known lineage")
                if self.unknown_mass_lower_bound is None or self.unknown_mass_upper_bound is None:
                    raise ValueError("bootstrap intervals require unknown-mass bounds")
                if self.unknown_mass_lower_bound > self.unknown_mass_upper_bound:
                    raise ValueError("unknown-mass interval bounds must be ordered")
                if not (
                    self.unknown_mass_lower_bound
                    <= self.unknown_mass
                    <= self.unknown_mass_upper_bound
                ):
                    raise ValueError("unknown-mass interval must contain unknown mass")
                interval_ids = tuple(item.reference_id for item in self.weight_intervals)
                weight_ids = tuple(item.reference_id for item in self.known_weights)
                if interval_ids != weight_ids:
                    raise ValueError("bootstrap intervals must follow ranked lineage order")
                for weight, interval in zip(self.known_weights, self.weight_intervals, strict=True):
                    if not interval.lower_bound <= weight.rna_weight <= interval.upper_bound:
                        raise ValueError("bootstrap interval must contain its fitted weight")
        elif self.known_weights or self.unknown_gene_mass or self.fitted_probabilities:
            raise ValueError("abstained result cannot carry fitted composition")
        elif self.weight_intervals or any(
            value is not None
            for value in (self.unknown_mass_lower_bound, self.unknown_mass_upper_bound)
        ) or self.bootstrap_replicates_used:
            raise ValueError("abstained result cannot carry bootstrap uncertainty")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


class GbmMixtureReplayRequest(FrozenModel):
    """Exact request/result envelope used by API and CLI replay verification."""

    request: GbmMixtureRequest
    result: GbmMixtureResult


def canonical_request_digest(request: GbmMixtureRequest) -> Sha256Digest:
    canonical = _canonical_request(request)
    return sha256_digest(canonical.model_dump(mode="json"))


def _canonical_request(request: GbmMixtureRequest) -> GbmMixtureRequest:
    """Sort feature/reference axes without relying on a mutating validator."""

    feature_order = tuple(sorted(range(len(request.feature_ids)), key=request.feature_ids.__getitem__))
    reference_order = tuple(sorted(request.references, key=lambda item: item.reference_id))
    if feature_order == tuple(range(len(request.feature_ids))) and reference_order == request.references:
        return request
    ordered_features = tuple(request.feature_ids[index] for index in feature_order)
    ordered_counts = tuple(request.counts[index] for index in feature_order)
    ordered_background = tuple(request.unknown_background[index] for index in feature_order)
    ordered_references = tuple(
        GbmMixtureReference(
            reference_id=item.reference_id,
            signature=tuple(item.signature[index] for index in feature_order),
        )
        for item in reference_order
    )
    return GbmMixtureRequest(
        sample_id=request.sample_id,
        feature_ids=ordered_features,
        counts=ordered_counts,
        references=ordered_references,
        unknown_background=ordered_background,
        concentration=request.concentration,
        lambda_mass=request.lambda_mass,
        lambda_shape=request.lambda_shape,
        initial_unknown_mass=request.initial_unknown_mass,
        max_iterations=request.max_iterations,
        bootstrap_replicates=request.bootstrap_replicates,
        source_digests=request.source_digests,
        provenance_note=request.provenance_note,
    )


def profile_digest(profile: GbmMixtureProfile | dict[str, object]) -> Sha256Digest:
    payload = (
        profile.model_dump(mode="json")
        if isinstance(profile, GbmMixtureProfile)
        else dict(profile)
    )
    payload.pop("profile_digest", None)
    return sha256_digest(payload)


def result_payload_digest(result: GbmMixtureResult) -> Sha256Digest:
    payload = result.model_dump(mode="json")
    payload.pop("result_digest", None)
    return sha256_digest(payload)


def _trace_digest(trace: tuple[float, ...]) -> Sha256Digest:
    return sha256_digest({"algorithm": MIXTURE_PROFILE_ID, "objective_trace": trace})


def mixture_profile() -> GbmMixtureProfile:
    """Return the immutable profile and reject an unpinned NumPy runtime."""

    if np.__version__ != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("GBM composition runtime requires NumPy 2.5.2")
    payload = {
        "profile_id": MIXTURE_PROFILE_ID,
        "algorithm_id": MIXTURE_ALGORITHM_ID,
        "algorithm_version": MIXTURE_ALGORITHM_VERSION,
        "numpy_version": np.__version__,
        "execution_scope": "caller_supplied_reference_only",
        "output_semantics": "rna_mixture_weights_with_unknown_mass",
        "histologic_fraction_claim_permitted": False,
        "clinical_use_permitted": False,
        "solver": "dirichlet_multinomial_adaptive_unknown_simplex",
        "max_features": MAX_MIXTURE_FEATURES,
        "max_lineages": MAX_MIXTURE_LINEAGES,
        "max_iterations": MAX_MIXTURE_ITERATIONS,
        "kkt_tolerance": MIXTURE_KKT_TOLERANCE,
        "l1_step_tolerance": MIXTURE_L1_STEP_TOLERANCE,
        "relative_objective_tolerance": MIXTURE_RELATIVE_OBJECTIVE_TOLERANCE,
        "bootstrap_sampling_policy": MIXTURE_BOOTSTRAP_SAMPLING_POLICY,
        "bootstrap_lower_quantile": MIXTURE_BOOTSTRAP_LOWER_QUANTILE,
        "bootstrap_upper_quantile": MIXTURE_BOOTSTRAP_UPPER_QUANTILE,
        "max_bootstrap_replicates": MAX_MIXTURE_BOOTSTRAP_REPLICATES,
        "bootstrap_max_iterations": MIXTURE_BOOTSTRAP_MAX_ITERATIONS,
        "bootstrap_kkt_tolerance": MIXTURE_BOOTSTRAP_KKT_TOLERANCE,
        "bootstrap_l1_step_tolerance": MIXTURE_BOOTSTRAP_L1_STEP_TOLERANCE,
        "bootstrap_relative_objective_tolerance": MIXTURE_BOOTSTRAP_RELATIVE_OBJECTIVE_TOLERANCE,
    }
    return GbmMixtureProfile(profile_digest=profile_digest(payload))


def _solver_configuration(request: GbmMixtureRequest) -> SimplexSolverConfiguration:
    return SimplexSolverConfiguration(
        max_iterations=request.max_iterations,
        kkt_tolerance=MIXTURE_KKT_TOLERANCE,
        l1_step_tolerance=MIXTURE_L1_STEP_TOLERANCE,
        relative_objective_tolerance=MIXTURE_RELATIVE_OBJECTIVE_TOLERANCE,
    )


def _matrix(request: GbmMixtureRequest) -> np.ndarray:
    return np.asarray([item.signature for item in request.references], dtype=np.float64).T


def _bootstrap_seed(request: GbmMixtureRequest) -> int:
    """Derive a stable 63-bit seed from the canonical request digest."""

    return int(request.request_digest.removeprefix("sha256:")[:16], 16) % (2**63 - 1)


def _bootstrap_intervals(
    request: GbmMixtureRequest,
    solution: ReferenceMixtureSolution,
) -> tuple[tuple[GbmMixtureWeightInterval, ...], float | None, float | None, int]:
    """Refit deterministic Dirichlet-multinomial posterior-predictive draws.

    The fitted simplex is used as the posterior-predictive mean, while the
    declared concentration controls over-dispersion.  Every accepted draw is
    solved through the same constrained simplex optimizer; failed draws are
    discarded rather than represented as artificial zero weights.
    """

    requested = request.bootstrap_replicates
    if requested == 0:
        return (), None, None, 0
    depth = int(sum(request.counts))
    probabilities = np.asarray(solution.fitted_probabilities, dtype=np.float64)
    if depth <= 0 or probabilities.ndim != 1 or not np.all(np.isfinite(probabilities)):
        return (), None, None, 0
    probabilities = np.maximum(probabilities, 1e-9)
    probabilities /= float(np.sum(probabilities, dtype=np.float64))
    alpha = np.maximum(probabilities * request.concentration, 1e-6)
    rng = np.random.default_rng(_bootstrap_seed(request))
    matrix = _matrix(request)
    base_configuration = _solver_configuration(request)
    configuration = replace(
        base_configuration,
        max_iterations=MIXTURE_BOOTSTRAP_MAX_ITERATIONS,
        kkt_tolerance=MIXTURE_BOOTSTRAP_KKT_TOLERANCE,
        l1_step_tolerance=MIXTURE_BOOTSTRAP_L1_STEP_TOLERANCE,
        relative_objective_tolerance=MIXTURE_BOOTSTRAP_RELATIVE_OBJECTIVE_TOLERANCE,
    )
    known_draws: list[np.ndarray] = []
    unknown_draws: list[float] = []
    for _ in range(requested):
        sampled_probabilities = rng.dirichlet(alpha)
        sampled_counts = rng.multinomial(depth, sampled_probabilities)
        try:
            draw = solve_reference_mixture(
                sampled_counts,
                matrix,
                request.unknown_background,
                concentration=request.concentration,
                lambda_mass=request.lambda_mass,
                lambda_shape=request.lambda_shape,
                initial_unknown_mass=request.initial_unknown_mass,
                configuration=configuration,
            )
        except (ValueError, FloatingPointError):
            continue
        if (
            not draw.trace
            or draw.kkt_residual > MIXTURE_BOOTSTRAP_KKT_TOLERANCE
            or not verify_objective_trace(draw)
        ):
            continue
        known_draws.append(np.asarray(draw.known_rna_weights, dtype=np.float64))
        unknown_draws.append(float(draw.unknown_mass))
    if len(known_draws) < MIXTURE_BOOTSTRAP_MIN_REPLICATES:
        return (), None, None, 0
    known_matrix = np.stack(known_draws, axis=0)
    lower_q, upper_q = np.quantile(
        known_matrix,
        [MIXTURE_BOOTSTRAP_LOWER_QUANTILE, MIXTURE_BOOTSTRAP_UPPER_QUANTILE],
        axis=0,
    )
    unknown_q = np.quantile(
        np.asarray(unknown_draws, dtype=np.float64),
        [MIXTURE_BOOTSTRAP_LOWER_QUANTILE, MIXTURE_BOOTSTRAP_UPPER_QUANTILE],
    )
    # Intervals and point estimates share the result's ten-decimal wire
    # quantization.  Expand against the quantized point so the receipt always
    # proves that its fitted coordinate lies inside the reported interval.
    point_weights = np.asarray(
        [round(float(value), 10) for value in solution.known_rna_weights],
        dtype=np.float64,
    )
    # The existing result contract carries unknown mass at twelve decimals;
    # retain that precision while keeping interval bounds ordered around it.
    point_unknown = round(float(solution.unknown_mass), 12)
    ranked_indices = sorted(
        range(len(request.references)),
        key=lambda index: (-solution.known_rna_weights[index], request.references[index].reference_id),
    )
    intervals = tuple(
        GbmMixtureWeightInterval(
            reference_id=request.references[index].reference_id,
            lower_bound=round(
                min(float(lower_q[index]), float(point_weights[index])), 10
            ),
            upper_bound=round(
                max(float(upper_q[index]), float(point_weights[index])), 10
            ),
        )
        for index in ranked_indices
    )
    return (
        intervals,
        round(min(float(unknown_q[0]), point_unknown), 12),
        round(max(float(unknown_q[1]), point_unknown), 12),
        len(known_draws),
    )


def _limited_result(
    request: GbmMixtureRequest,
    solution: ReferenceMixtureSolution,
    diagnostics: OodDiagnostics,
    *,
    weight_intervals: tuple[GbmMixtureWeightInterval, ...] = (),
    unknown_mass_lower_bound: float | None = None,
    unknown_mass_upper_bound: float | None = None,
    bootstrap_replicates_used: int = 0,
) -> GbmMixtureResult:
    weights = tuple(
        GbmMixtureWeight(
            reference_id=reference.reference_id,
            rna_weight=round(float(solution.known_rna_weights[index]), 10),
            rank=rank,
        )
        for rank, (index, reference) in enumerate(
            sorted(enumerate(request.references), key=lambda item: (-solution.known_rna_weights[item[0]], item[1].reference_id)),
            start=1,
        )
    )
    trace = tuple(round(float(item.objective), 12) for item in solution.trace)
    return GbmMixtureResult.model_construct(
        result_id=f"result.{request.request_digest.removeprefix('sha256:')}",
        profile_digest=mixture_profile().profile_digest,
        request_digest=request.request_digest,
        result_digest=_ZERO_DIGEST,
        sample_id=request.sample_id,
        feature_ids=request.feature_ids,
        support="limited",
        known_weights=weights,
        weight_intervals=weight_intervals,
        unknown_gene_mass=tuple(round(float(value), 12) for value in solution.unknown_gene_mass),
        fitted_probabilities=tuple(round(float(value), 12) for value in solution.fitted_probabilities),
        unknown_mass=round(solution.unknown_mass, 12),
        unknown_mass_lower_bound=unknown_mass_lower_bound,
        unknown_mass_upper_bound=unknown_mass_upper_bound,
        bootstrap_replicates_used=bootstrap_replicates_used,
        objective=round(solution.objective, 12),
        initial_objective=round(solution.initial_objective, 12),
        iterations=solution.iterations,
        kkt_residual=round(solution.kkt_residual, 12),
        signature_condition_number=round(solution.signature_condition_number, 12),
        objective_trace=trace,
        trace_digest=_trace_digest(trace),
        ood=diagnostics,
        source_digests=request.source_digests,
        limitations=(
            "RNA mixture weights are not histologic cell fractions or malignant-cell percentages.",
            "References and source digests are caller supplied; no GBmap fitted artifact is traversed.",
            "Unknown mass is an unexplained RNA channel and is not assigned to a cell lineage.",
            "The composition is a research-use-only signal and not a diagnosis, prognosis, or treatment recommendation.",
            "Optional intervals are deterministic posterior-predictive count perturbations and do not represent external calibration or histologic uncertainty.",
        ),
    )


def _abstained_result(request: GbmMixtureRequest, reason: str) -> GbmMixtureResult:
    empty_trace: tuple[float, ...] = ()
    return GbmMixtureResult.model_construct(
        result_id=f"result.{request.request_digest.removeprefix('sha256:')}",
        profile_digest=mixture_profile().profile_digest,
        request_digest=request.request_digest,
        result_digest=_ZERO_DIGEST,
        sample_id=request.sample_id,
        feature_ids=(),
        support="abstained",
        iterations=0,
        trace_digest=_trace_digest(empty_trace),
        abstention_reason=reason,
        source_digests=request.source_digests,
        limitations=(
            "No RNA mixture weights are emitted when the simplex solver cannot close its diagnostics.",
            "This runtime does not make histologic cell-fraction or clinical claims.",
        ),
    )


def _seal(result: GbmMixtureResult) -> GbmMixtureResult:
    return result.model_copy(update={"result_digest": result_payload_digest(result)})


def analyze_gbm_mixture(request: GbmMixtureRequest) -> GbmMixtureResult:
    """Fit one caller-owned count vector against positive lineage signatures."""

    request = _canonical_request(request)
    if np.__version__ != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("GBM composition runtime requires NumPy 2.5.2")
    request_bytes = canonical_json_bytes(request.model_dump(mode="json"))
    if len(request_bytes) > MAX_MIXTURE_REQUEST_BYTES:
        raise GbmapInputError("GBM composition request exceeds the byte limit")
    matrix = _matrix(request)
    try:
        solution = solve_reference_mixture(
            request.counts,
            matrix,
            request.unknown_background,
            concentration=request.concentration,
            lambda_mass=request.lambda_mass,
            lambda_shape=request.lambda_shape,
            initial_unknown_mass=request.initial_unknown_mass,
            configuration=_solver_configuration(request),
        )
    except (ValueError, FloatingPointError) as error:
        return _seal(_abstained_result(request, f"simplex solver rejected the request: {error}"))
    if not solution.converged or not solution.trace or not verify_objective_trace(solution):
        return _seal(
            _abstained_result(
                request,
                "simplex solver did not close convergence, KKT, and monotonic-trace diagnostics",
            )
        )
    try:
        diagnostics = evaluate_ood_diagnostics(
            request.counts,
            solution.fitted_probabilities,
            concentration=request.concentration,
            unknown_mass=solution.unknown_mass,
        )
    except (ValueError, FloatingPointError) as error:
        return _seal(_abstained_result(request, f"composition diagnostics failed safely: {error}"))
    intervals, unknown_lower, unknown_upper, bootstrap_used = _bootstrap_intervals(request, solution)
    return _seal(
        _limited_result(
            request,
            solution,
            diagnostics,
            weight_intervals=intervals,
            unknown_mass_lower_bound=unknown_lower,
            unknown_mass_upper_bound=unknown_upper,
            bootstrap_replicates_used=bootstrap_used,
        )
    )


def verify_gbm_mixture_replay(
    request: GbmMixtureRequest,
    result: GbmMixtureResult,
) -> bool:
    """Recompute and compare the complete deterministic result."""

    request = _canonical_request(request)
    if result.request_digest != request.request_digest:
        return False
    expected = analyze_gbm_mixture(request)
    return expected.model_dump(mode="json") == result.model_dump(mode="json")


def synthetic_gbm_mixture_request() -> GbmMixtureRequest:
    """Return a small glioma-like synthetic mixture for smoke tests and demos."""

    features = ("EGFR", "SOX2", "OLIG2", "PTPRC", "LST1", "CD3D", "PECAM1", "VWF")
    references = (
        GbmMixtureReference(
            reference_id="malignant_gbm",
            signature=(0.31, 0.23, 0.19, 0.03, 0.03, 0.03, 0.10, 0.08),
        ),
        GbmMixtureReference(
            reference_id="myeloid",
            signature=(0.035, 0.035, 0.035, 0.24, 0.27, 0.12, 0.14, 0.125),
        ),
        GbmMixtureReference(
            reference_id="t_cell",
            signature=(0.03, 0.03, 0.03, 0.25, 0.08, 0.32, 0.14, 0.12),
        ),
        GbmMixtureReference(
            reference_id="endothelial",
            signature=(0.04, 0.035, 0.035, 0.06, 0.06, 0.04, 0.39, 0.34),
        ),
    )
    source_digest = sha256_digest(
        {
            "catalog": "synthetic_gbm_marker_signatures",
            "version": "1.0.0",
            "features": features,
            "references": [item.model_dump(mode="json") for item in references],
        }
    )
    return _canonical_request(GbmMixtureRequest(
        sample_id="synthetic-gbm-mixture-001",
        feature_ids=features,
        counts=(620, 470, 360, 180, 220, 120, 180, 150),
        references=references,
        unknown_background=(0.125,) * len(features),
        concentration=120.0,
        # Keep the unexplained channel learnable in the demo; a mass penalty
        # would intentionally drive it to the simplex floor for this compact
        # marker panel and obscure the solver's adaptive-unknown behavior.
        lambda_mass=0.0,
        lambda_shape=0.03,
        initial_unknown_mass=0.05,
        max_iterations=500,
        source_digests=(source_digest,),
        provenance_note=(
            "Synthetic glioma-like marker signatures for algorithm smoke testing; no patient "
            "or GBmap cell data are embedded."
        ),
    ))


__all__ = [
    "EXPECTED_NUMPY_VERSION",
    "MAX_MIXTURE_FEATURES",
    "MAX_MIXTURE_ITERATIONS",
    "MAX_MIXTURE_LINEAGES",
    "MAX_MIXTURE_REQUEST_BYTES",
    "MAX_MIXTURE_RESULT_BYTES",
    "MIXTURE_ALGORITHM_ID",
    "MIXTURE_ALGORITHM_VERSION",
    "MIXTURE_KKT_TOLERANCE",
    "MIXTURE_L1_STEP_TOLERANCE",
    "MIXTURE_PROFILE_ID",
    "MIXTURE_RELATIVE_OBJECTIVE_TOLERANCE",
    "GbmMixtureProfile",
    "GbmMixtureReference",
    "GbmMixtureReplayRequest",
    "GbmMixtureRequest",
    "GbmMixtureResult",
    "GbmMixtureWeight",
    "analyze_gbm_mixture",
    "canonical_request_digest",
    "mixture_profile",
    "profile_digest",
    "result_payload_digest",
    "synthetic_gbm_mixture_request",
    "verify_gbm_mixture_replay",
]
