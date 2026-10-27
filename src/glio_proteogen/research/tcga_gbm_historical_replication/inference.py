"""Historical research mapping to the unchanged published GBMPurity service.

Positive author classification supports this separately versioned research
population. It is never converted into the original integrated-diagnosis review
basis. A fresh source-bound payload is required; saved count receipts are not
authority. All individual outcomes remain private and have no calibrated interval.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Final, Literal, NoReturn, Self, SupportsIndex

import numpy as np
from pydantic import Field, field_validator, model_validator

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import FrozenModel
from glio_proteogen.research.cptac_gbm_external_admission.contracts import SourceLock
from glio_proteogen.research.cptac_gbm_rna_purity_execution.identity import (
    ModelInputAxis,
    validate_model_axis,
)
from glio_proteogen.research.gbm_rna_purity.catalog import (
    EXPECTED_ARTIFACT_SHA256,
    EXPECTED_CONTENT_DIGEST,
    EXPECTED_FEATURE_ORDER_DIGEST,
    EXPECTED_SOURCE_FEATURE_SHA256,
    EXPECTED_SOURCE_MODEL_SHA256,
    EXPECTED_WEIGHT_TENSOR_DIGEST,
)
from glio_proteogen.research.gbm_rna_purity.contracts import (
    REQUIRED_CONTEXT,
    ClippingState,
    GbmRnaPurityProfile,
    GbmRnaPurityRequest,
    GbmRnaPurityResult,
    PuritySupport,
    RawGeneCount,
    request_digest,
)
from glio_proteogen.research.gbm_rna_purity.profile import algorithm_profile
from glio_proteogen.research.gbm_rna_purity.service import analyze_gbm_rna_purity
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
    checkpoint,
)

from .contracts import (
    POPULATION_BASIS,
    HistoricalPopulationQualification,
    HistoricalPopulationReceipt,
    HistoricalSourceError,
)
from .projection import (
    HistoricalCountProjection,
    HistoricalCountProjectionReceipt,
    _checked_storage,
    project_historical_star_counts,
)
from .source import verify_rna_payload

_FEATURES: Final = 5_829
_MINIMUM: Final = 4_664
_SUPPORTED: Final = 5_771
_MAX_PRIVATE_BYTES: Final = 8_192
_Count = Annotated[int, Field(ge=0, le=_FEATURES)]
_States = tuple[_Count, _Count, _Count, _Count, _Count, _Count]
HistoricalOutcome = Literal[
    "estimated", "below_coverage_gate", "zero_recognized_sum", "limited_support_disallowed"
]


class HistoricalInferenceError(HistoricalSourceError):
    """Sanitized historical scope, source, numerical or service rejection."""


def _require(condition: bool) -> None:  # noqa: FBT001 - private invariant expression.
    if not condition:
        raise HistoricalInferenceError("historical research inference binding was not accepted")


class HistoricalInferencePolicy(FrozenModel):
    """Explicit research mapping; none of these fields supplies clinical evidence."""

    schema_version: Literal["tcga-historical-research-purity-policy/1.0.0"] = (
        "tcga-historical-research-purity-policy/1.0.0"
    )
    historical_population_mapping: Literal["author2016_histologic_gbm_g4_idhwt_and_case_denovo"]
    unknown_specimen_timing_and_exposure_accepted: Literal[True]
    research_use_only: Literal[True]
    caller_authorizes_missing_gene_zero_fill: Literal[True]
    allow_limited_support: bool = False

    @field_validator(
        "unknown_specimen_timing_and_exposure_accepted",
        "research_use_only",
        "caller_authorizes_missing_gene_zero_fill",
        "allow_limited_support",
        mode="before",
    )
    @classmethod
    def exact_booleans(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("historical policy declarations require exact booleans")
        return value


def _policy(policy: HistoricalInferencePolicy) -> HistoricalInferencePolicy:
    _require(type(policy) is HistoricalInferencePolicy)
    return HistoricalInferencePolicy.model_validate(
        policy.model_dump(mode="python", warnings="none"), strict=True
    )


class HistoricalInferenceReceipt(FrozenModel):
    """Identifier/hash-free disposition; individual availability remains private.

    This summary is not a privacy guarantee, clinical support, or an accuracy
    certificate. The estimate itself is accessible only through the private result.
    """

    schema_version: Literal["tcga-historical-research-purity-summary/1.0.0"] = (
        "tcga-historical-research-purity-summary/1.0.0"
    )
    population: HistoricalPopulationReceipt
    outcome: HistoricalOutcome
    state_counts: _States
    recognized_model_gene_count: _Count
    nonzero_model_gene_count: _Count
    observed_zero_model_gene_count: _Count
    unavailable_model_gene_count: _Count
    coverage_fraction: float = Field(ge=0.0, le=1.0)
    feature_coverage_support: PuritySupport
    limited_support_allowed: bool
    model_executed: bool
    clipping_state: ClippingState | None
    research_use_only: Literal[True] = True
    clinical_qualification_granted: Literal[False] = False
    formal_integrated_diagnosis_established: Literal[False] = False
    who2021_reclassification_performed: Literal[False] = False
    original_cptac_gate_changed: Literal[False] = False
    independent_validation_established: Literal[False] = False
    calibrated_uncertainty_available: Literal[False] = False

    @field_validator(
        "clinical_qualification_granted",
        "formal_integrated_diagnosis_established",
        "who2021_reclassification_performed",
        "original_cptac_gate_changed",
        "independent_validation_established",
        "calibrated_uncertainty_available",
        mode="before",
    )
    @classmethod
    def exact_false(cls, value: object) -> object:
        if value is not False:
            raise ValueError("historical inference cannot establish clinical or validation claims")
        return value

    @field_validator("research_use_only", mode="before")
    @classmethod
    def exact_true(cls, value: object) -> object:
        if value is not True:
            raise ValueError("historical inference is research only")
        return value

    @model_validator(mode="after")
    def disposition_and_coverage_agree(self) -> Self:
        recognized = self.state_counts[0] + self.state_counts[1]
        estimated = self.outcome == "estimated"
        expected_support = (
            PuritySupport.SUPPORTED if recognized >= _SUPPORTED else PuritySupport.LIMITED
        )
        _require(
            sum(self.state_counts) == _FEATURES
            and self.state_counts[3] == 0
            and self.recognized_model_gene_count == recognized
            and self.nonzero_model_gene_count == self.state_counts[0]
            and self.observed_zero_model_gene_count == self.state_counts[1]
            and self.unavailable_model_gene_count == _FEATURES - recognized
            and self.coverage_fraction == recognized / _FEATURES
            and self.model_executed is estimated
            and (self.clipping_state is not None) is estimated
            and self.clipping_state is not ClippingState.NOT_APPLICABLE
            and self.feature_coverage_support
            is (expected_support if estimated else PuritySupport.ABSTAINED)
        )
        if estimated:
            _require(
                recognized >= _MINIMUM
                and self.nonzero_model_gene_count > 0
                and (recognized >= _SUPPORTED or self.limited_support_allowed)
            )
        elif self.outcome == "below_coverage_gate":
            _require(recognized < _MINIMUM)
        elif self.outcome == "zero_recognized_sum":
            _require(recognized >= _MINIMUM and self.nonzero_model_gene_count == 0)
        else:
            _require(
                _MINIMUM <= recognized < _SUPPORTED
                and self.nonzero_model_gene_count > 0
                and not self.limited_support_allowed
            )
        return self


class _Point(FrozenModel):
    receipt: HistoricalInferenceReceipt
    estimate: float | None = Field(default=None, ge=0.0, le=1.0)
    raw_unclipped_output: float | None = None

    @model_validator(mode="after")
    def scalar_presence(self) -> Self:
        estimated = self.receipt.outcome == "estimated"
        _require((self.estimate is not None) is estimated)
        _require((self.raw_unclipped_output is not None) is estimated)
        if self.estimate is not None and self.raw_unclipped_output is not None:
            raw, estimate = self.raw_unclipped_output, self.estimate
            clipping = self.receipt.clipping_state
            if clipping is ClippingState.LOWER_BOUND:
                _require(raw <= 0.0 and estimate == 0.0)
            elif clipping is ClippingState.UPPER_BOUND:
                _require(raw >= 1.0 and estimate == 1.0)
            else:
                _require(clipping is ClippingState.NONE and 0.0 <= raw <= 1.0 and raw == estimate)
        return self


class HistoricalPurityResult:
    """Private scalar historical research outcome, with no retained legacy result."""

    __slots__ = ("_payload",)
    _payload: bytes

    def __init__(self) -> None:
        raise HistoricalInferenceError("historical results require fresh source-bound inference")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("historical research outcomes are immutable")

    def __delattr__(self, _name: str) -> NoReturn:
        raise AttributeError("historical research outcomes are immutable")

    def _checked(self) -> _Point:
        document = None
        try:
            _require(
                type(self) is HistoricalPurityResult
                and type(self._payload) is bytes
                and 0 < len(self._payload) <= _MAX_PRIVATE_BYTES
            )
            checked = _Point.model_validate_json(self._payload)
            _require(
                canonical_json_bytes(checked.model_dump(mode="json", warnings="none"))
                == self._payload
            )
            document = checked
        except (AttributeError, TypeError, ValueError):
            pass
        if document is None:
            raise HistoricalInferenceError("historical result storage was not accepted")
        return document

    @property
    def receipt(self) -> HistoricalInferenceReceipt:
        return self._checked().receipt

    @property
    def outcome(self) -> HistoricalOutcome:
        return self._checked().receipt.outcome

    @property
    def estimate(self) -> float | None:
        return self._checked().estimate

    @property
    def raw_unclipped_output(self) -> float | None:
        return self._checked().raw_unclipped_output

    @property
    def feature_coverage_support(self) -> PuritySupport:
        return self._checked().receipt.feature_coverage_support

    @property
    def clipping_state(self) -> ClippingState | None:
        return self._checked().receipt.clipping_state

    def __repr__(self) -> str:
        return "<HistoricalPurityResult private>"

    def __getstate__(self) -> NoReturn:
        raise TypeError("private historical outcomes cannot be implicitly serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("private historical outcomes cannot be implicitly serialized")


@dataclass(frozen=True, slots=True, repr=False)
class _Binding:
    lock: SourceLock
    axis_digest: str
    names: tuple[str, ...]
    population: HistoricalPopulationReceipt


def _binding(
    payload: bytes,
    qualification: HistoricalPopulationQualification,
    model_axis: ModelInputAxis,
) -> _Binding:
    _require(type(payload) is bytes and type(qualification) is HistoricalPopulationQualification)
    lock = verify_rna_payload(payload, qualification=qualification)
    _require(type(lock) is SourceLock)
    validate_model_axis(model_axis)
    population = HistoricalPopulationReceipt.model_validate(
        qualification.receipt.model_dump(mode="python", warnings="none"), strict=True
    )
    _require(population.population_basis == POPULATION_BASIS)
    return _Binding(
        lock,
        model_axis.digest,
        tuple(feature.source_symbol for feature in model_axis.features),
        population,
    )


def _snapshot(
    projection: HistoricalCountProjection,
) -> tuple[bytes, bytes, HistoricalCountProjectionReceipt]:
    counts, states, receipt = _checked_storage(projection)
    return counts.tobytes(), states.tobytes(), receipt


def _outcome(
    receipt: HistoricalCountProjectionReceipt, policy: HistoricalInferencePolicy
) -> HistoricalOutcome:
    if receipt.recognized_model_gene_count < _MINIMUM:
        return "below_coverage_gate"
    if receipt.nonzero_model_gene_count == 0:
        return "zero_recognized_sum"
    if not policy.allow_limited_support and receipt.recognized_model_gene_count < _SUPPORTED:
        return "limited_support_disallowed"
    return "estimated"


def _checked_profile() -> GbmRnaPurityProfile:
    profile = algorithm_profile()
    _require(type(profile) is GbmRnaPurityProfile)
    checked = GbmRnaPurityProfile.model_validate(
        profile.model_dump(mode="python", warnings="none"), strict=True
    )
    _require(
        checked.converted_artifact_file_sha256 == EXPECTED_ARTIFACT_SHA256
        and checked.converted_artifact_digest == EXPECTED_CONTENT_DIGEST
        and checked.feature_order_digest == EXPECTED_FEATURE_ORDER_DIGEST
        and checked.weight_tensor_digest == EXPECTED_WEIGHT_TENSOR_DIGEST
        and checked.source_model_sha256 == EXPECTED_SOURCE_MODEL_SHA256
        and checked.source_gene_lengths_sha256 == EXPECTED_SOURCE_FEATURE_SHA256
    )
    return checked


def _checked_result(
    result: GbmRnaPurityResult,
    request: GbmRnaPurityRequest,
    profile: GbmRnaPurityProfile,
    snapshot: tuple[bytes, bytes, HistoricalCountProjectionReceipt],
) -> GbmRnaPurityResult:
    _require(type(result) is GbmRnaPurityResult)
    checked = GbmRnaPurityResult.model_validate(
        result.model_dump(mode="python", warnings="none"), strict=True
    )
    _require(
        canonical_json_bytes(result.model_dump(mode="json", warnings="none"))
        == canonical_json_bytes(checked.model_dump(mode="json", warnings="none"))
    )
    counts = np.frombuffer(snapshot[0], dtype=np.int64)
    states = np.frombuffer(snapshot[1], dtype=np.uint8)
    native = snapshot[2]
    recognized = native.recognized_model_gene_count
    values = np.where(states < 2, counts, 0).astype(np.float64)
    coverage, provenance = checked.coverage, checked.provenance
    _require(
        checked.sample_id == request.sample_id
        and checked.request_digest == request_digest(request)
        and checked.profile_digest == profile.profile_digest
        and checked.support
        is (PuritySupport.SUPPORTED if native.coverage_supported else PuritySupport.LIMITED)
        and checked.estimate is not None
        and checked.explanation is not None
        and checked.diagnostics.finite_inference
        and checked.diagnostics.hidden_trace is not None
        and coverage.supplied_gene_count == recognized
        and coverage.recognized_model_gene_count == recognized
        and coverage.missing_model_gene_count == _FEATURES - recognized
        and coverage.ignored_non_model_gene_count == 0
        and coverage.nonzero_model_gene_count == native.nonzero_model_gene_count
        and coverage.coverage_fraction == recognized / _FEATURES
        and coverage.recognized_raw_count_sum == float(np.sum(values, dtype=np.float64))
        and provenance.converted_artifact_file_sha256 == EXPECTED_ARTIFACT_SHA256
        and provenance.converted_artifact_digest == EXPECTED_CONTENT_DIGEST
        and provenance.feature_order_digest == EXPECTED_FEATURE_ORDER_DIGEST
        and provenance.weight_tensor_digest == EXPECTED_WEIGHT_TENSOR_DIGEST
        and provenance.source_model_sha256 == EXPECTED_SOURCE_MODEL_SHA256
        and provenance.source_gene_lengths_sha256 == EXPECTED_SOURCE_FEATURE_SHA256
    )
    return checked


def _build_result(
    native: HistoricalCountProjectionReceipt,
    policy: HistoricalInferencePolicy,
    outcome: HistoricalOutcome,
    result: GbmRnaPurityResult | None,
) -> HistoricalPurityResult:
    point = None if result is None else result.estimate
    receipt = HistoricalInferenceReceipt(
        population=native.population,
        outcome=outcome,
        state_counts=native.state_counts,
        recognized_model_gene_count=native.recognized_model_gene_count,
        nonzero_model_gene_count=native.nonzero_model_gene_count,
        observed_zero_model_gene_count=native.observed_zero_model_gene_count,
        unavailable_model_gene_count=native.unavailable_model_gene_count,
        coverage_fraction=native.coverage_fraction,
        feature_coverage_support=PuritySupport.ABSTAINED if result is None else result.support,
        limited_support_allowed=policy.allow_limited_support,
        model_executed=result is not None,
        clipping_state=None if point is None else point.clipping_state,
    )
    document = _Point(
        receipt=receipt,
        estimate=None if point is None else point.malignant_cell_fraction,
        raw_unclipped_output=None if point is None else point.raw_unclipped_output,
    )
    built = object.__new__(HistoricalPurityResult)
    object.__setattr__(
        built, "_payload", canonical_json_bytes(document.model_dump(mode="json", warnings="none"))
    )
    built._checked()
    return built


def _estimate(
    payload: bytes,
    qualification: HistoricalPopulationQualification,
    model_axis: ModelInputAxis,
    policy: HistoricalInferencePolicy,
    cancellation: CancellationContext | None,
) -> HistoricalPurityResult:
    checkpoint(cancellation)
    checked_policy = _policy(policy)
    bound = _binding(payload, qualification, model_axis)
    projected = project_historical_star_counts(
        payload, qualification=qualification, model_axis=model_axis
    )
    snapshot = _snapshot(projected)
    _require(snapshot[2].population == bound.population)
    _require(_binding(payload, qualification, model_axis) == bound)
    _require(_policy(policy) == checked_policy)
    outcome = _outcome(snapshot[2], checked_policy)
    legacy = None
    if outcome == "estimated":
        counts = np.frombuffer(snapshot[0], dtype=np.int64)
        states = np.frombuffer(snapshot[1], dtype=np.uint8)
        # This unchanged declaration is model research scope, justified by this
        # explicit historical mapping. It is not an old clinical diagnosis review.
        request = GbmRnaPurityRequest(
            sample_id="historical-research-purity",
            context=REQUIRED_CONTEXT,
            counts_provenance_digest="sha256:" + bound.lock.sha256,
            counts=tuple(
                RawGeneCount(gene_symbol=name, raw_count=float(counts[index]))
                for index, name in enumerate(bound.names)
                if states[index] < 2
            ),
        )
        expected_profile = _checked_profile()
        _require(_binding(payload, qualification, model_axis) == bound)
        _require(_snapshot(projected) == snapshot and _policy(policy) == checked_policy)
        checkpoint(cancellation)
        legacy = _checked_result(
            analyze_gbm_rna_purity(request, cancellation=cancellation),
            request,
            expected_profile,
            snapshot,
        )
        checkpoint(cancellation)
        _require(_checked_profile() == expected_profile)
    _require(_binding(payload, qualification, model_axis) == bound)
    _require(_snapshot(projected) == snapshot and _policy(policy) == checked_policy)
    built = _build_result(snapshot[2], checked_policy, outcome, legacy)
    _require(type(built) is HistoricalPurityResult)
    built._checked()
    _require(_binding(payload, qualification, model_axis) == bound)
    _require(_snapshot(projected) == snapshot and _policy(policy) == checked_policy)
    checkpoint(cancellation)
    return built


def estimate_historical_star_counts(
    payload: bytes,
    *,
    qualification: HistoricalPopulationQualification,
    model_axis: ModelInputAxis,
    policy: HistoricalInferencePolicy,
    cancellation: CancellationContext | None = None,
) -> HistoricalPurityResult:
    """Estimate only under the explicit historical research policy and live source.

    Source/axis failures discard outcomes even after a model call occurred.
    Cancellation and process interrupts propagate; ordinary errors are sanitized
    outside the exception handler so private payloads cannot enter error messages.
    """
    result = None
    try:
        result = _estimate(payload, qualification, model_axis, policy, cancellation)
    except (InferenceCancelledError, InferenceDeadlineExceededError):
        raise
    except Exception:  # noqa: BLE001, S110 - no private callee messages at this boundary.
        pass
    if result is None:
        del payload, qualification, model_axis, policy, cancellation
        raise HistoricalInferenceError("historical research inference was not accepted")
    return result


__all__ = [
    "HistoricalInferenceError",
    "HistoricalInferencePolicy",
    "HistoricalInferenceReceipt",
    "HistoricalOutcome",
    "HistoricalPurityResult",
    "estimate_historical_star_counts",
]
