"""Bounded immutable gene axes and transient measurements; no patient exports."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Final, Literal, NoReturn, SupportsIndex

import numpy as np
import numpy.typing as npt

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission.contracts import GeneIdentity

PROFILE_ID: Final = "cptac-gbm-source-defined-feature-space/1.0.0"
MAX_FEATURES: Final = 20_000
MAX_CASES: Final = 1_000
MAX_CELLS: Final = 2_000_000
RNA_AXIS: Final = "star_fpkm_uq_unstranded"
CNV_AXIS: Final = "ascat_total_copy_number"
PROTEIN_AXIS: Final = "cdap_unshared_log2_specimen_reference_ratio"
STATES: Final = (
    "observed",
    "absent_feature",
    "unresolved_reference",
    "ambiguous_identity",
    "symbol_disagreement",
    "missing_measurement",
)
AssayAxis = Literal["star_fpkm_uq_unstranded", "ascat_total_copy_number"]
FloatArray = npt.NDArray[np.float64]
StateArray = npt.NDArray[np.uint8]


class FeatureSpaceError(ValueError):
    """A sanitized feature-space contract failure, without source records or IDs."""


def require_digest(value: str) -> str:
    if type(value) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise FeatureSpaceError("a canonical feature-space digest is required")
    return value


def immutable[Scalar: np.generic](values: npt.NDArray[Scalar]) -> npt.NDArray[Scalar]:
    return np.frombuffer(np.ascontiguousarray(values).tobytes(), dtype=values.dtype).reshape(
        values.shape
    )


@dataclass(frozen=True, slots=True)
class FeatureAxis:
    identities: tuple[GeneIdentity, ...] = field(repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.identities) is not tuple
            or not 1 <= len(self.identities) <= MAX_FEATURES
            or any(not isinstance(identity, GeneIdentity) for identity in self.identities)
        ):
            raise FeatureSpaceError("feature axis requires bounded approved gene identities")
        keys = tuple(identity.hgnc_id for identity in self.identities)
        symbols = tuple(identity.symbol for identity in self.identities)
        if (
            keys != tuple(sorted(keys))
            or len(set(keys)) != len(keys)
            or len(set(symbols)) != len(keys)
        ):
            raise FeatureSpaceError(
                "feature axis identities must be unique and canonically ordered"
            )

    @property
    def hgnc_ids(self) -> tuple[str, ...]:
        return tuple(identity.hgnc_id for identity in self.identities)

    @property
    def digest(self) -> str:
        return sha256_digest(tuple(asdict(identity) for identity in self.identities))


@dataclass(frozen=True, slots=True)
class ProjectionReceipt:
    axis: AssayAxis
    workflow: str
    annotation_release: str | None
    input_bytes: int
    data_rows: int
    gene_rows: int
    summary_rows: int
    versioned_gene_rows: int
    par_y_gene_rows: int
    duplicate_gene_symbol_groups: int
    ambiguous_reference_gene_ids: int
    missing_gene_rows: int
    observed_zero_gene_rows: int
    feature_axis_digest: str
    feature_count: int
    state_counts: tuple[int, ...]

    def __post_init__(self) -> None:
        require_digest(self.feature_axis_digest)
        numbers = (
            self.input_bytes,
            self.data_rows,
            self.gene_rows,
            self.summary_rows,
            self.versioned_gene_rows,
            self.par_y_gene_rows,
            self.duplicate_gene_symbol_groups,
            self.ambiguous_reference_gene_ids,
            self.missing_gene_rows,
            self.observed_zero_gene_rows,
            self.feature_count,
        )
        if (
            self.axis not in (RNA_AXIS, CNV_AXIS)
            or self.workflow != ("STAR - Counts" if self.axis == RNA_AXIS else "AscatNGS")
            or self.annotation_release != ("GENCODE v36" if self.axis == RNA_AXIS else None)
            or any(type(value) is not int or value < 0 for value in numbers)
            or not 1 <= self.feature_count <= MAX_FEATURES
            or not 1 <= self.gene_rows <= 100_000
            or self.data_rows != self.gene_rows + self.summary_rows
            or self.summary_rows != (4 if self.axis == RNA_AXIS else 0)
            or not 1 <= self.input_bytes <= 10_000_000
            or type(self.state_counts) is not tuple
            or len(self.state_counts) != len(STATES)
            or any(type(count) is not int or count < 0 for count in self.state_counts)
            or sum(self.state_counts) != self.feature_count
        ):
            raise FeatureSpaceError(
                "projection receipt does not satisfy the declared assay contract"
            )


def _check_values(values: FloatArray, states: StateArray, *, nonnegative: bool) -> None:
    if (
        type(values) is not np.ndarray
        or values.dtype != np.dtype(np.float64)
        or type(states) is not np.ndarray
        or states.dtype != np.dtype(np.uint8)
        or values.shape != states.shape
        or bool(np.any(np.isinf(values)))
        or bool(np.any(states >= len(STATES)))
        or not np.array_equal(np.isfinite(values), states == 0)
        or (nonnegative and bool(np.any(values[np.isfinite(values)] < 0)))
    ):
        raise FeatureSpaceError("measurement values and availability states disagree")


@dataclass(frozen=True, slots=True, eq=False)
class ProjectedAssay:
    receipt: ProjectionReceipt
    values: FloatArray = field(repr=False)
    states: StateArray = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.receipt, ProjectionReceipt):
            raise FeatureSpaceError("a validated projection receipt is required")
        _check_values(self.values, self.states, nonnegative=True)
        if (
            self.values.shape != (self.receipt.feature_count,)
            or tuple(int(np.sum(self.states == code)) for code in range(len(STATES)))
            != self.receipt.state_counts
        ):
            raise FeatureSpaceError("projection dimensions or state counts disagree")
        object.__setattr__(self, "values", immutable(self.values))
        object.__setattr__(self, "states", immutable(self.states))

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient gene measurements cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient gene measurements cannot be serialized")


@dataclass(frozen=True, slots=True, eq=False)
class GeneMeasurements:
    cnv: FloatArray = field(repr=False)
    rna: FloatArray = field(repr=False)
    protein: FloatArray = field(repr=False)

    def __post_init__(self) -> None:
        arrays = (self.cnv, self.rna, self.protein)
        if (
            any(
                type(value) is not np.ndarray or value.dtype != np.dtype(np.float64)
                for value in arrays
            )
            or len({value.shape for value in arrays}) != 1
            or self.cnv.ndim != 1
            or not 1 <= len(self.cnv) <= MAX_CASES
            or any(bool(np.any(np.isinf(value))) for value in arrays)
            or any(bool(np.any(value[np.isfinite(value)] < 0)) for value in arrays[:2])
        ):
            raise FeatureSpaceError("transient gene input dimensions or coordinates are invalid")
        for name, value in zip(("cnv", "rna", "protein"), arrays, strict=True):
            object.__setattr__(self, name, immutable(value))

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient gene measurements cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient gene measurements cannot be serialized")


@dataclass(frozen=True, slots=True, eq=False)
class FeatureMatrix:
    axis: FeatureAxis = field(repr=False)
    candidate_digest: str
    cnv: FloatArray = field(repr=False)
    rna: FloatArray = field(repr=False)
    protein: FloatArray = field(repr=False)
    cnv_states: StateArray = field(repr=False)
    rna_states: StateArray = field(repr=False)
    protein_states: StateArray = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.axis, FeatureAxis):
            raise FeatureSpaceError("a validated feature axis is required")
        require_digest(self.candidate_digest)
        for name, values, states in (
            ("cnv", self.cnv, self.cnv_states),
            ("rna", self.rna, self.rna_states),
            ("protein", self.protein, self.protein_states),
        ):
            _check_values(values, states, nonnegative=name != "protein")
            if (
                values.ndim != 2
                or values.shape[0] != len(self.axis.identities)
                or not 1 <= values.shape[1] <= MAX_CASES
                or values.size > MAX_CELLS
                or values.shape != self.cnv.shape
            ):
                raise FeatureSpaceError("feature matrix exceeds its bounded aligned dimensions")
            object.__setattr__(self, name, immutable(values))
            object.__setattr__(self, name + "_states", immutable(states))

    @property
    def case_count(self) -> int:
        return int(self.cnv.shape[1])

    @property
    def measurement_bytes(self) -> int:
        return sum(value.nbytes for value in (self.cnv, self.rna, self.protein))

    def gene(self, hgnc_id: str) -> GeneMeasurements:
        try:
            index = self.axis.hgnc_ids.index(hgnc_id)
        except ValueError:
            raise FeatureSpaceError("requested gene is outside the frozen feature axis") from None
        return GeneMeasurements(self.cnv[index], self.rna[index], self.protein[index])

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient cohort measurements cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient cohort measurements cannot be serialized")
