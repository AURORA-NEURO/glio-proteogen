"""Strict byte-locked native STAR count admission, without model execution.

All rows and all columns are validated; only the explicit unstranded integer
coordinate is projected. Unavailable features retain -1, never supplied zero.
The aggregate receipt is exportable; the aligned counts and states are not.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Annotated, Final, Literal, NoReturn, Self, SupportsIndex, cast

import numpy as np
import numpy.typing as npt
from pydantic import Field, model_validator

from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.cptac_gbm_external_admission import assays as schema
from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    SourceLock,
    SourceVerificationError,
)
from glio_proteogen.research.gbm_rna_purity.contracts import (
    MINIMUM_MODEL_GENE_COVERAGE,
    MODEL_FEATURE_COUNT,
    SUPPORTED_MODEL_GENE_COVERAGE,
)

from .contracts import ExecutionError, digest
from .identity import ModelInputAxis, validate_model_axis

MAX_NATIVE_COUNT: Final = 10**15
MAX_ASSAY_BYTES: Final = schema.MAX_ASSAY_BYTES
MAX_ASSAY_ROWS: Final = schema.MAX_ASSAY_ROWS
STATES: Final = (
    "observed_positive",
    "observed_zero",
    "absent_feature",
    "annotation_version_disagreement",
    "ambiguous_identity",
    "symbol_disagreement",
)
CountArray = npt.NDArray[np.int64]
StateArray = npt.NDArray[np.uint8]
_Count = Annotated[int, Field(ge=0, le=MODEL_FEATURE_COUNT)]
_StateCounts = tuple[_Count, _Count, _Count, _Count, _Count, _Count]


class NativeCountFormatError(ExecutionError):
    """Sanitized structural rejection without paths, source rows or identifiers."""


class NativeCountDomainError(ExecutionError):
    """A source count exceeds the unchanged runtime's safe count magnitude."""


class NativeCountReceipt(FrozenModel):
    """One-file aggregate schema/readiness receipt; no count or state vectors."""

    schema_version: Literal["glio-proteogen.source-qualified-native-count-receipt/1.0.0"] = (
        "glio-proteogen.source-qualified-native-count-receipt/1.0.0"
    )
    profile_id: Literal["cptac-gbm-native-star-purity-execution/1.0.0"] = (
        "cptac-gbm-native-star-purity-execution/1.0.0"
    )
    axis: Literal["star_raw_unstranded_gene_counts"] = "star_raw_unstranded_gene_counts"
    workflow: Literal["STAR - Counts"] = "STAR - Counts"
    annotation_release: Literal["GENCODE v36"] = "GENCODE v36"
    input_bytes: int = Field(ge=1, le=MAX_ASSAY_BYTES)
    input_sha256: Sha256Digest
    model_axis_digest: Sha256Digest
    data_rows: int = Field(ge=5, le=MAX_ASSAY_ROWS)
    gene_rows: int = Field(ge=1, le=MAX_ASSAY_ROWS - 4)
    summary_rows: Literal[4] = 4
    versioned_gene_rows: int = Field(ge=0, le=MAX_ASSAY_ROWS)
    par_y_gene_rows: int = Field(ge=0, le=MAX_ASSAY_ROWS)
    duplicate_gene_symbol_groups: int = Field(ge=0, le=MAX_ASSAY_ROWS)
    ambiguous_reference_gene_ids: int = Field(ge=0, le=MAX_ASSAY_ROWS)
    observed_zero_gene_rows: int = Field(ge=0, le=MAX_ASSAY_ROWS)
    model_feature_count: Literal[5_829] = 5_829
    state_counts: _StateCounts
    recognized_model_gene_count: _Count
    nonzero_model_gene_count: _Count
    observed_zero_model_gene_count: _Count
    unavailable_model_gene_count: _Count
    recognized_raw_count_sum: int = Field(ge=0, le=MODEL_FEATURE_COUNT * MAX_NATIVE_COUNT)
    coverage_fraction: float = Field(ge=0.0, le=1.0)
    count_ready: bool
    coverage_supported: bool
    inference_executed: Literal[False] = False

    @model_validator(mode="after")
    def conserved_counts_and_gates(self) -> Self:
        recognized = self.state_counts[0] + self.state_counts[1]
        coverage = recognized / MODEL_FEATURE_COUNT
        if (
            sum(self.state_counts) != MODEL_FEATURE_COUNT
            or self.data_rows != self.gene_rows + self.summary_rows
            or any(
                count > self.gene_rows
                for count in (
                    self.versioned_gene_rows,
                    self.par_y_gene_rows,
                    self.ambiguous_reference_gene_ids,
                    self.observed_zero_gene_rows,
                    self.recognized_model_gene_count,
                )
            )
            or self.duplicate_gene_symbol_groups > self.gene_rows // 2
            or self.ambiguous_reference_gene_ids != 0
            or self.state_counts[3] != 0
            or recognized + self.state_counts[5] > self.gene_rows
            or self.observed_zero_model_gene_count > self.observed_zero_gene_rows
            or self.recognized_model_gene_count != recognized
            or self.nonzero_model_gene_count != self.state_counts[0]
            or self.observed_zero_model_gene_count != self.state_counts[1]
            or self.unavailable_model_gene_count != MODEL_FEATURE_COUNT - recognized
            or not self.nonzero_model_gene_count
            <= self.recognized_raw_count_sum
            <= self.nonzero_model_gene_count * MAX_NATIVE_COUNT
            or self.coverage_fraction != coverage
            or self.count_ready
            != (coverage >= MINIMUM_MODEL_GENE_COVERAGE and self.recognized_raw_count_sum > 0)
            or self.coverage_supported != (coverage >= SUPPORTED_MODEL_GENE_COVERAGE)
        ):
            raise ValueError("native count receipt does not conserve its schema, states and gates")
        return self


class NativeCountSample:
    """Private, immutable native integers; receipt-only JSON export is explicit."""

    __slots__ = ("_binding_digest", "_count_bytes", "_receipt", "_state_bytes")
    _binding_digest: str
    _count_bytes: bytes
    _receipt: NativeCountReceipt
    _state_bytes: bytes

    def __init__(self, counts: CountArray, states: StateArray, receipt: NativeCountReceipt) -> None:
        if type(receipt) is not NativeCountReceipt:
            raise NativeCountFormatError("a validated native count receipt is required")
        try:
            checked = NativeCountReceipt.model_validate(
                receipt.model_dump(mode="python"), strict=True
            )
        except ValueError:
            raise NativeCountFormatError("native count receipt is invalid") from None
        if (
            type(counts) is not np.ndarray
            or counts.dtype != np.dtype(np.int64)
            or counts.shape != (MODEL_FEATURE_COUNT,)
            or type(states) is not np.ndarray
            or states.dtype != np.dtype(np.uint8)
            or states.shape != counts.shape
        ):
            raise NativeCountFormatError("native count and availability buffers are inconsistent")
        # Snapshot caller-owned storage before validation and digesting. Later
        # mutation must affect neither the admitted payload nor its binding.
        count_bytes = np.ascontiguousarray(counts).tobytes()
        state_bytes = np.ascontiguousarray(states).tobytes()
        counts = np.frombuffer(count_bytes, dtype=np.int64)
        states = np.frombuffer(state_bytes, dtype=np.uint8)
        if (
            bool(np.any(states >= len(STATES)))
            or bool(np.any((states == 0) & ((counts <= 0) | (counts > MAX_NATIVE_COUNT))))
            or bool(np.any((states == 1) & (counts != 0)))
            or bool(np.any((states >= 2) & (counts != -1)))
        ):
            raise NativeCountFormatError("native count and availability buffers are inconsistent")
        expected = tuple(int(np.sum(states == code)) for code in range(len(STATES)))
        recognized_sum = sum(int(value) for value in counts[counts >= 0])
        if expected != checked.state_counts or recognized_sum != checked.recognized_raw_count_sum:
            raise NativeCountFormatError(
                "native count buffers disagree with their aggregate receipt"
            )
        binding = digest(
            {
                "receipt": checked.model_dump(mode="json"),
                "counts": counts.tolist(),
                "states": states.tolist(),
            }
        )
        object.__setattr__(self, "_count_bytes", count_bytes)
        object.__setattr__(self, "_state_bytes", state_bytes)
        object.__setattr__(self, "_receipt", checked)
        object.__setattr__(self, "_binding_digest", binding)

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("native count sample is immutable")

    @property
    def counts(self) -> CountArray:
        return np.frombuffer(self._count_bytes, dtype=np.int64)

    @property
    def states(self) -> StateArray:
        return np.frombuffer(self._state_bytes, dtype=np.uint8)

    @property
    def receipt(self) -> NativeCountReceipt:
        return self._receipt

    @property
    def binding_digest(self) -> str:
        return self._binding_digest

    def __repr__(self) -> str:
        return "NativeCountSample(private_measurements=True)"

    def __getstate__(self) -> NoReturn:
        raise TypeError("private native counts cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("private native counts cannot be serialized")


def _raw_count(token: str) -> int:
    count = schema._unsigned_integer(token)
    if count > MAX_NATIVE_COUNT:
        raise NativeCountDomainError("native count exceeds the frozen safe magnitude domain")
    return count


def _verified_payload(payload: bytes, lock: SourceLock) -> None:
    if type(lock) is not SourceLock:
        raise SourceVerificationError("a validated native count source lock is required")
    try:
        checked = SourceLock(lock.bytes, lock.md5, lock.sha256)
    except (AttributeError, TypeError, ValueError):
        raise SourceVerificationError("native count source lock is invalid") from None
    if (
        type(payload) is not bytes
        or not 1 <= len(payload) <= MAX_ASSAY_BYTES
        or checked.bytes != len(payload)
        or checked.bytes > MAX_ASSAY_BYTES
        or hashlib.md5(payload, usedforsecurity=False).hexdigest() != checked.md5
        or hashlib.sha256(payload).hexdigest() != checked.sha256
    ):
        raise SourceVerificationError("native count source bytes do not match their bounded lock")


def _project_genes(
    genes: dict[str, tuple[str, str, int]], symbols: Counter[str], model_axis: ModelInputAxis
) -> tuple[CountArray, StateArray]:
    values = np.full(MODEL_FEATURE_COUNT, -1, dtype=np.int64)
    states = np.empty(MODEL_FEATURE_COUNT, dtype=np.uint8)
    for index, feature in enumerate(model_axis.features):
        gene_row = genes.get(feature.ensembl_gene_id)
        if gene_row is None:
            state = 2
        elif gene_row[0] not in {feature.release_gene_id, feature.ensembl_gene_id}:
            raise NativeCountFormatError(
                "native STAR annotation version differs from the fixed release"
            )
        elif gene_row[1] != feature.source_symbol:
            state = 5
        elif symbols[feature.source_symbol] != 1:
            state = 4
        else:
            values[index] = gene_row[2]
            state = 1 if gene_row[2] == 0 else 0
        states[index] = state
    return values, states


def _parse_native_counts(payload: bytes, *, model_axis: ModelInputAxis) -> NativeCountSample:
    try:
        records = schema._records(payload, rna=True)
        genes: dict[str, tuple[str, str, int]] = {}
        originals: set[str] = set()
        symbols: Counter[str] = Counter()
        summaries: set[str] = set()
        versioned = par_y = zeros = 0
        for row in records:
            counts = tuple(_raw_count(token) for token in row[3:6])
            if row[0] in schema.RNA_SUMMARY_LABELS:
                if row[0] in summaries or any(row[index] for index in (1, 2, 6, 7, 8)):
                    raise NativeCountFormatError(
                        "native STAR summary inventory or fields are invalid"
                    )
                summaries.add(row[0])
                continue
            gene_id = schema._identifier(row[0])
            if row[0] in originals or gene_id in genes:
                raise NativeCountFormatError(
                    "native STAR source contains duplicate exact or normalized gene IDs"
                )
            schema._name(row[1])
            schema._name(row[2])
            for token in row[6:9]:
                schema._nonnegative_finite(token)
            originals.add(row[0])
            genes[gene_id] = (row[0], row[1], counts[0])
            symbols[row[1]] += 1
            versioned += row[0] != gene_id
            par_y += gene_id.endswith("_PAR_Y")
            zeros += counts[0] == 0
        if summaries != schema.RNA_SUMMARY_LABELS or not genes:
            raise NativeCountFormatError(
                "native STAR source lacks genes or the exact four summaries"
            )
    except schema.AssayFormatError:
        raise NativeCountFormatError(
            "native STAR source violates the required count schema"
        ) from None
    values, states = _project_genes(genes, symbols, model_axis)
    state_counts = cast(
        "_StateCounts", tuple(int(np.sum(states == code)) for code in range(len(STATES)))
    )
    recognized = state_counts[0] + state_counts[1]
    coverage = recognized / MODEL_FEATURE_COUNT
    total = sum(int(value) for value in values[values >= 0])
    receipt = NativeCountReceipt(
        input_bytes=len(payload),
        input_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
        model_axis_digest=model_axis.digest,
        data_rows=len(records),
        gene_rows=len(genes),
        versioned_gene_rows=versioned,
        par_y_gene_rows=par_y,
        duplicate_gene_symbol_groups=sum(count > 1 for count in symbols.values()),
        ambiguous_reference_gene_ids=0,
        observed_zero_gene_rows=zeros,
        state_counts=state_counts,
        recognized_model_gene_count=recognized,
        nonzero_model_gene_count=state_counts[0],
        observed_zero_model_gene_count=state_counts[1],
        unavailable_model_gene_count=MODEL_FEATURE_COUNT - recognized,
        recognized_raw_count_sum=total,
        coverage_fraction=coverage,
        count_ready=coverage >= MINIMUM_MODEL_GENE_COVERAGE and total > 0,
        coverage_supported=coverage >= SUPPORTED_MODEL_GENE_COVERAGE,
    )
    return NativeCountSample(values, states, receipt)


def project_native_star_counts(
    payload: bytes, *, lock: SourceLock, model_axis: ModelInputAxis
) -> NativeCountSample:
    """Verify caller-read bytes, then project without zero fill or inference."""
    _verified_payload(payload, lock)
    validate_model_axis(model_axis)
    return _parse_native_counts(payload, model_axis=model_axis)


__all__ = [
    "MAX_ASSAY_BYTES",
    "MAX_ASSAY_ROWS",
    "MAX_NATIVE_COUNT",
    "STATES",
    "NativeCountDomainError",
    "NativeCountFormatError",
    "NativeCountReceipt",
    "NativeCountSample",
    "project_native_star_counts",
]
