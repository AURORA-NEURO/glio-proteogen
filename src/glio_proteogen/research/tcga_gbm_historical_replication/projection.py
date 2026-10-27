"""Private historical-population count projection, without model authority.

Source qualification and an independently reviewed RNA acquisition lock precede
the unchanged native projector. Only availability and coverage summaries are
exportable; neither the population receipt nor numerical readiness authorizes
the original clinical inference lane.
"""

from __future__ import annotations

import hashlib
from typing import Annotated, Final, Literal, NoReturn, Self, SupportsIndex

import numpy as np
import numpy.typing as npt
from pydantic import Field, field_validator, model_validator

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import FrozenModel
from glio_proteogen.research.cptac_gbm_external_admission.contracts import SourceLock
from glio_proteogen.research.cptac_gbm_rna_purity_execution.identity import (
    ModelInputAxis,
    validate_model_axis,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution.native_counts import (
    MAX_NATIVE_COUNT,
    STATES,
    NativeCountSample,
    project_native_star_counts,
)
from glio_proteogen.research.gbm_rna_purity.contracts import (
    MINIMUM_MODEL_GENE_COVERAGE,
    MODEL_FEATURE_COUNT,
    SUPPORTED_MODEL_GENE_COVERAGE,
)

from .contracts import (
    HistoricalPopulationQualification,
    HistoricalPopulationReceipt,
    HistoricalSourceError,
)
from .source import verify_rna_payload

CountArray = npt.NDArray[np.int64]
StateArray = npt.NDArray[np.uint8]
_Count = Annotated[int, Field(ge=0, le=MODEL_FEATURE_COUNT)]
_StateCounts = tuple[_Count, _Count, _Count, _Count, _Count, _Count]
_STORAGE_VERSION: Final = b"tcga-historical-private-count-projection/1.0.0\0"


class HistoricalProjectionError(HistoricalSourceError):
    """Sanitized source, coordinate or native-count projection rejection."""


class HistoricalCountProjectionReceipt(FrozenModel):
    """Closed one-projection coverage summary, with no numerical source seal.

    Even availability counts can disclose specimen information. An explicit
    export of this receipt is not a privacy guarantee or clinical qualification.
    """

    schema_version: Literal["tcga-historical-native-count-summary/1.0.0"] = (
        "tcga-historical-native-count-summary/1.0.0"
    )
    population: HistoricalPopulationReceipt
    axis: Literal["star_raw_unstranded_gene_counts"] = "star_raw_unstranded_gene_counts"
    annotation_release: Literal["GENCODE v36"] = "GENCODE v36"
    model_feature_count: Literal[5_829] = 5_829
    state_counts: _StateCounts
    recognized_model_gene_count: _Count
    nonzero_model_gene_count: _Count
    observed_zero_model_gene_count: _Count
    unavailable_model_gene_count: _Count
    coverage_fraction: float = Field(ge=0.0, le=1.0)
    count_ready: bool
    coverage_supported: bool
    inference_executed: Literal[False] = False
    clinical_qualification_granted: Literal[False] = False
    original_cptac_gate_changed: Literal[False] = False
    model_invocation_permitted: Literal[False] = False

    @field_validator(
        "inference_executed",
        "clinical_qualification_granted",
        "original_cptac_gate_changed",
        "model_invocation_permitted",
        mode="before",
    )
    @classmethod
    def exact_false(cls, value: object) -> object:
        if value is not False:
            raise ValueError("historical projection cannot grant inference authority")
        return value

    @model_validator(mode="after")
    def conserved_availability_and_readiness(self) -> Self:
        recognized = self.state_counts[0] + self.state_counts[1]
        coverage = recognized / MODEL_FEATURE_COUNT
        if (
            sum(self.state_counts) != MODEL_FEATURE_COUNT
            or self.state_counts[3] != 0
            or self.recognized_model_gene_count != recognized
            or self.nonzero_model_gene_count != self.state_counts[0]
            or self.observed_zero_model_gene_count != self.state_counts[1]
            or self.unavailable_model_gene_count != MODEL_FEATURE_COUNT - recognized
            or self.coverage_fraction != coverage
            or self.count_ready
            != (coverage >= MINIMUM_MODEL_GENE_COVERAGE and self.nonzero_model_gene_count > 0)
            or self.coverage_supported != (coverage >= SUPPORTED_MODEL_GENE_COVERAGE)
        ):
            raise ValueError("historical projection summary does not conserve native states")
        return self


def _storage_digest(counts: bytes, states: bytes, receipt: bytes) -> bytes:
    # This private corruption check is never included in the public summary.
    return hashlib.sha256(_STORAGE_VERSION + counts + states + receipt).digest()


class HistoricalCountProjection:
    """Private immutable count/state buffers; explicit receipt export only."""

    __slots__ = ("_count_bytes", "_integrity", "_receipt_bytes", "_state_bytes")
    _count_bytes: bytes
    _state_bytes: bytes
    _receipt_bytes: bytes
    _integrity: bytes

    def __init__(self) -> None:
        raise HistoricalProjectionError("historical count projections require source admission")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("historical count projection is immutable")

    def __delattr__(self, _name: str) -> NoReturn:
        raise AttributeError("historical count projection is immutable")

    @property
    def counts(self) -> CountArray:
        counts, _, _ = _checked_storage(self)
        return counts

    @property
    def states(self) -> StateArray:
        _, states, _ = _checked_storage(self)
        return states

    @property
    def receipt(self) -> HistoricalCountProjectionReceipt:
        _, _, receipt = _checked_storage(self)
        return receipt

    def __repr__(self) -> str:
        return "<HistoricalCountProjection private>"

    def __getstate__(self) -> NoReturn:
        raise TypeError("private historical counts cannot be implicitly serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("private historical counts cannot be implicitly serialized")


def _checked_storage(
    projection: HistoricalCountProjection,
) -> tuple[CountArray, StateArray, HistoricalCountProjectionReceipt]:
    try:
        if (
            type(projection) is not HistoricalCountProjection
            or type(projection._count_bytes) is not bytes
            or type(projection._state_bytes) is not bytes
            or type(projection._receipt_bytes) is not bytes
            or type(projection._integrity) is not bytes
            or len(projection._count_bytes) != MODEL_FEATURE_COUNT * np.dtype(np.int64).itemsize
            or len(projection._state_bytes) != MODEL_FEATURE_COUNT
            or _storage_digest(
                projection._count_bytes, projection._state_bytes, projection._receipt_bytes
            )
            != projection._integrity
        ):
            raise HistoricalProjectionError("historical projection storage is invalid")
        receipt = HistoricalCountProjectionReceipt.model_validate_json(projection._receipt_bytes)
        if canonical_json_bytes(receipt.model_dump(mode="json")) != projection._receipt_bytes:
            raise HistoricalProjectionError("historical projection storage is invalid")
        counts = np.frombuffer(projection._count_bytes, dtype=np.int64)
        states = np.frombuffer(projection._state_bytes, dtype=np.uint8)
        state_counts = tuple(int(np.count_nonzero(states == state)) for state in range(len(STATES)))
        if (
            bool(np.any(states >= len(STATES)))
            or bool(np.any((states == 0) & ((counts <= 0) | (counts > MAX_NATIVE_COUNT))))
            or bool(np.any((states == 1) & (counts != 0)))
            or bool(np.any((states >= 2) & (counts != -1)))
            or state_counts != receipt.state_counts
        ):
            raise HistoricalProjectionError("historical projection storage is invalid")
    except (AttributeError, TypeError, ValueError):
        failed = True
    else:
        failed = False
    if failed:
        raise HistoricalProjectionError("historical projection storage was not accepted") from None
    return counts, states, receipt


def _build_projection(
    native: NativeCountSample,
    *,
    population: HistoricalPopulationReceipt,
    lock: SourceLock,
    axis_digest: str,
) -> HistoricalCountProjection:
    if type(native) is not NativeCountSample or type(population) is not HistoricalPopulationReceipt:
        raise HistoricalProjectionError("historical projection requires verified native counts")
    snapshot = NativeCountSample(native.counts, native.states, native.receipt)
    if (
        snapshot.binding_digest != native.binding_digest
        or snapshot.receipt.input_bytes != lock.bytes
        or snapshot.receipt.input_sha256 != "sha256:" + lock.sha256.removeprefix("sha256:")
        or snapshot.receipt.model_axis_digest != axis_digest
    ):
        raise HistoricalProjectionError("native counts differ from the qualified source and axis")
    receipt = HistoricalCountProjectionReceipt(
        population=HistoricalPopulationReceipt.model_validate(population.model_dump(mode="python")),
        state_counts=snapshot.receipt.state_counts,
        recognized_model_gene_count=snapshot.receipt.recognized_model_gene_count,
        nonzero_model_gene_count=snapshot.receipt.nonzero_model_gene_count,
        observed_zero_model_gene_count=snapshot.receipt.observed_zero_model_gene_count,
        unavailable_model_gene_count=snapshot.receipt.unavailable_model_gene_count,
        coverage_fraction=snapshot.receipt.coverage_fraction,
        count_ready=snapshot.receipt.count_ready,
        coverage_supported=snapshot.receipt.coverage_supported,
    )
    counts = snapshot.counts.tobytes()
    states = snapshot.states.tobytes()
    receipt_bytes = canonical_json_bytes(receipt.model_dump(mode="json"))
    result = object.__new__(HistoricalCountProjection)
    object.__setattr__(result, "_count_bytes", counts)
    object.__setattr__(result, "_state_bytes", states)
    object.__setattr__(result, "_receipt_bytes", receipt_bytes)
    object.__setattr__(result, "_integrity", _storage_digest(counts, states, receipt_bytes))
    _checked_storage(result)
    return result


def _project_historical_star_counts(
    payload: bytes,
    *,
    qualification: HistoricalPopulationQualification,
    model_axis: ModelInputAxis,
) -> HistoricalCountProjection:
    lock = verify_rna_payload(payload, qualification=qualification)
    if type(lock) is not SourceLock:
        raise HistoricalProjectionError("historical projection requires a reviewed source lock")
    validate_model_axis(model_axis)
    axis_digest = model_axis.digest
    population = HistoricalPopulationReceipt.model_validate(
        qualification.receipt.model_dump(mode="python")
    )
    native = project_native_star_counts(payload, lock=lock, model_axis=model_axis)
    if verify_rna_payload(payload, qualification=qualification) != lock:
        raise HistoricalProjectionError("historical source qualification changed during projection")
    validate_model_axis(model_axis)
    if model_axis.digest != axis_digest or qualification.receipt != population:
        raise HistoricalProjectionError("historical source or model axis changed during projection")
    result = _build_projection(native, population=population, lock=lock, axis_digest=axis_digest)
    if verify_rna_payload(payload, qualification=qualification) != lock:
        raise HistoricalProjectionError("historical source qualification changed during projection")
    validate_model_axis(model_axis)
    if model_axis.digest != axis_digest or qualification.receipt != population:
        raise HistoricalProjectionError("historical source or model axis changed during projection")
    return result


def project_historical_star_counts(
    payload: bytes,
    *,
    qualification: HistoricalPopulationQualification,
    model_axis: ModelInputAxis,
) -> HistoricalCountProjection:
    """Project one reviewed historical source without constructing an inference request.

    The source-owned verifier rejects unreviewed acquisition bytes and synthetic
    fixture qualifications. Numerical coverage does not change its historical
    basis, unknown specimen timing or explicit lack of clinical authority.
    """
    try:
        result = _project_historical_star_counts(
            payload, qualification=qualification, model_axis=model_axis
        )
    except (AttributeError, TypeError, ValueError, OverflowError, IndexError):
        failed = True
    else:
        failed = False
    if failed:
        del payload, qualification, model_axis
        raise HistoricalProjectionError("historical STAR projection was not accepted") from None
    return result


__all__ = [
    "HistoricalCountProjection",
    "HistoricalCountProjectionReceipt",
    "HistoricalProjectionError",
    "project_historical_star_counts",
]
