"""Private, shared patient-bootstrap draws for two-cohort uncertainty methods.

This primitive draws empirical patient multiplicities; it does not create new
biological patients, prove cohort independence or admit any model/support gate.
An original source unit and all its copies remain in its original fixed fold.
Generate one schedule and reuse it for every gene and model to preserve paired,
correlated endpoint comparisons. Only aggregate receipts are serializable.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Final, NoReturn, SupportsIndex

import numpy as np
import numpy.typing as npt

PROFILE_ID: Final = "cptac-gbm-two-cohort-patient-bootstrap/1.0.0"
REPLICATES: Final = 128
MIN_SOURCE_COUNT: Final = 60
MAX_PATIENT_COUNT: Final = 10_000
_FOLDS: Final = (0, 1, 2, 3, 4)
IndexArray = npt.NDArray[np.int64]
FoldArray = npt.NDArray[np.int8]


class ResamplingError(ValueError):
    """Sanitized draw/input rejection without identifiers or row contents."""


@dataclass(frozen=True, slots=True)
class TwoCohortResamplingProfile:
    profile_id: str = PROFILE_ID
    replicates: int = REPLICATES
    source_count_minimum: int = MIN_SOURCE_COUNT
    source_count_maximum: int = MAX_PATIENT_COUNT
    external_count_minimum: int = 1
    external_count_maximum: int = MAX_PATIENT_COUNT
    source_fold_labels: tuple[int, ...] = _FOLDS
    seed_recipe: str = (
        "uint64 big-endian first8 SHA256 bytes of ASCII "
        "profile_id + ':' + request_digest + ':' + domain"
    )
    source_domain: str = "source"
    external_domain: str = "external"
    random_generator: str = "two independent local numpy Generator(PCG64(seed)) streams"
    source_draw: str = (
        "within each original fold0..4, rng.choice(original ascending row indices, "
        "size=original fold size, replace=True); concatenate blocks in fold order"
    )
    external_draw: str = (
        "rng.choice(arange(external_count,int64), size=external_count, replace=True)"
    )
    schedule: str = "consume each independent stream sequentially for128 draws"
    paired_reuse: str = "reuse the exact same128 cohort draws for all genes and models"
    effective_count: str = (
        "Kish frequency ESS n^2/sum(multiplicity^2), unrounded and descriptive only; "
        "not an independent biological patient count or eligibility threshold"
    )
    duplicate_units: str = (
        "expanded rows represent empirical bootstrap multiplicities; an original "
        "source unit and all copies retain their original fold"
    )
    input_bounds_basis: str = "bounded implementation contract; no power or support admission"
    cohort_independence_established: bool = False
    support_or_power_admitted: bool = False


_PROFILE: Final = TwoCohortResamplingProfile()


def resampling_profile() -> TwoCohortResamplingProfile:
    """Return the frozen, aggregate draw policy for a future method binding."""
    return _PROFILE


def _integer(value: object, lower: int, upper: int) -> bool:
    return type(value) is int and lower <= value <= upper


def _effective(value: object, upper: int) -> bool:
    return type(value) is float and math.isfinite(value) and 1.0 <= value <= upper


@dataclass(frozen=True, slots=True)
class TwoCohortDrawReceipt:
    """Counts describe empirical reuse and carry no patient labels or row vectors."""

    draw_ordinal: int
    source_count: int
    external_count: int
    source_unique_count: int
    external_unique_count: int
    source_fold_counts: tuple[int, ...]
    source_fold_unique_counts: tuple[int, ...]
    source_effective_count: float
    external_effective_count: float
    source_fold_effective_counts: tuple[float, ...]

    def __post_init__(self) -> None:
        if not (
            _integer(self.draw_ordinal, 0, REPLICATES - 1)
            and _integer(self.source_count, MIN_SOURCE_COUNT, MAX_PATIENT_COUNT)
            and _integer(self.external_count, 1, MAX_PATIENT_COUNT)
            and _integer(self.source_unique_count, 5, self.source_count)
            and _integer(self.external_unique_count, 1, self.external_count)
        ):
            raise ResamplingError("draw receipt counts are invalid")
        if (
            type(self.source_fold_counts) is not tuple
            or len(self.source_fold_counts) != 5
            or any(not _integer(value, 1, self.source_count) for value in self.source_fold_counts)
            or sum(self.source_fold_counts) != self.source_count
            or type(self.source_fold_unique_counts) is not tuple
            or len(self.source_fold_unique_counts) != 5
            or any(
                not _integer(unique, 1, count)
                for unique, count in zip(
                    self.source_fold_unique_counts, self.source_fold_counts, strict=True
                )
            )
            or sum(self.source_fold_unique_counts) != self.source_unique_count
        ):
            raise ResamplingError("draw receipt fold counts are invalid")
        if (
            not _effective(self.source_effective_count, self.source_unique_count)
            or not _effective(self.external_effective_count, self.external_unique_count)
            or type(self.source_fold_effective_counts) is not tuple
            or len(self.source_fold_effective_counts) != 5
            or any(
                not _effective(effective, unique)
                for effective, unique in zip(
                    self.source_fold_effective_counts,
                    self.source_fold_unique_counts,
                    strict=True,
                )
            )
        ):
            raise ResamplingError("draw receipt effective counts are invalid")


def _array(value: object, dtype: np.dtype[np.signedinteger], count: int) -> bool:
    return (
        type(value) is np.ndarray
        and value.dtype == dtype
        and value.ndim == 1
        and len(value) == count
    )


def _frequency_ess(indices: IndexArray) -> float:
    _, multiplicities = np.unique(indices, return_counts=True)
    squared_mass = int(np.dot(multiplicities, multiplicities))
    return len(indices) ** 2 / squared_mass


def _receipt(
    ordinal: int, source: IndexArray, folds: FoldArray, external: IndexArray
) -> TwoCohortDrawReceipt:
    blocks = tuple(source[folds == label] for label in _FOLDS)
    return TwoCohortDrawReceipt(
        draw_ordinal=ordinal,
        source_count=len(source),
        external_count=len(external),
        source_unique_count=len(np.unique(source)),
        external_unique_count=len(np.unique(external)),
        source_fold_counts=tuple(len(block) for block in blocks),
        source_fold_unique_counts=tuple(len(np.unique(block)) for block in blocks),
        source_effective_count=_frequency_ess(source),
        external_effective_count=_frequency_ess(external),
        source_fold_effective_counts=tuple(_frequency_ess(block) for block in blocks),
    )


@dataclass(frozen=True, slots=True, eq=False)
class TwoCohortDraw:
    """Transient index views backed by immutable bytes; serialize only receipt."""

    source_indices: IndexArray = field(repr=False)
    source_folds: FoldArray = field(repr=False)
    external_indices: IndexArray = field(repr=False)
    receipt: TwoCohortDrawReceipt

    def __post_init__(self) -> None:
        if type(self.receipt) is not TwoCohortDrawReceipt:
            raise ResamplingError("draw receipt is invalid")
        source_count = self.receipt.source_count
        external_count = self.receipt.external_count
        if not (
            _array(self.source_indices, np.dtype(np.int64), source_count)
            and _array(self.source_folds, np.dtype(np.int8), source_count)
            and _array(self.external_indices, np.dtype(np.int64), external_count)
        ):
            raise ResamplingError("draw array contracts are invalid")
        source = np.frombuffer(self.source_indices.tobytes(), dtype=np.int64)
        folds = np.frombuffer(self.source_folds.tobytes(), dtype=np.int8)
        external = np.frombuffer(self.external_indices.tobytes(), dtype=np.int64)
        if (
            np.any(source < 0)
            or np.any(source >= source_count)
            or np.any(external < 0)
            or np.any(external >= external_count)
            or np.any(folds < 0)
            or np.any(folds > 4)
            or np.any(folds[1:] < folds[:-1])
            or {int(value) for value in np.unique(folds)} != set(_FOLDS)
        ):
            raise ResamplingError("draw indices or fold blocks are invalid")
        ordered = np.argsort(source, kind="stable")
        original = source[ordered]
        assigned = folds[ordered]
        if np.any((original[1:] == original[:-1]) & (assigned[1:] != assigned[:-1])):
            raise ResamplingError("copies of an original source unit cross fold blocks")
        if _receipt(self.receipt.draw_ordinal, source, folds, external) != self.receipt:
            raise ResamplingError("draw arrays do not match their aggregate receipt")
        object.__setattr__(self, "source_indices", source)
        object.__setattr__(self, "source_folds", folds)
        object.__setattr__(self, "external_indices", external)

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient patient-bootstrap draws cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient patient-bootstrap draws cannot be serialized")


def _seed(request_digest: str, domain: str) -> int:
    payload = f"{PROFILE_ID}:{request_digest}:{domain}".encode("ascii")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def generate_two_cohort_draws(
    *, source_folds: FoldArray, external_count: int, request_digest: str
) -> tuple[TwoCohortDraw, ...]:
    """Generate one bounded paired schedule, without fitting or assessing support.

    Source positions in each draw are concatenated in original fold0..4 order.
    Source indices reference the caller's original, unsorted row positions.
    Changing external_count never changes source draws, and conversely changing
    the source fold inventory never advances the external random stream.
    """
    if (
        type(source_folds) is not np.ndarray
        or source_folds.dtype != np.dtype(np.int8)
        or source_folds.ndim != 1
        or not MIN_SOURCE_COUNT <= len(source_folds) <= MAX_PATIENT_COUNT
    ):
        raise ResamplingError("source fold array is invalid")
    original_folds = np.array(source_folds, dtype=np.int8, order="C", copy=True)
    if (
        np.any(original_folds < 0)
        or np.any(original_folds > 4)
        or {int(value) for value in np.unique(original_folds)} != set(_FOLDS)
    ):
        raise ResamplingError("source fold labels are invalid")
    if not _integer(external_count, 1, MAX_PATIENT_COUNT):
        raise ResamplingError("external patient count is invalid")
    if (
        type(request_digest) is not str
        or re.fullmatch(r"sha256:[0-9a-f]{64}", request_digest) is None
    ):
        raise ResamplingError("request digest is invalid")
    source_rng = np.random.Generator(np.random.PCG64(_seed(request_digest, "source")))
    external_rng = np.random.Generator(np.random.PCG64(_seed(request_digest, "external")))
    blocks = tuple(np.flatnonzero(original_folds == fold).astype(np.int64) for fold in _FOLDS)
    drawn_folds = np.concatenate(
        tuple(np.full(len(block), fold, dtype=np.int8) for fold, block in enumerate(blocks))
    )
    external_units = np.arange(external_count, dtype=np.int64)
    draws = []
    for ordinal in range(REPLICATES):
        source = np.concatenate(
            tuple(source_rng.choice(block, size=len(block), replace=True) for block in blocks)
        )
        external = external_rng.choice(external_units, size=external_count, replace=True)
        draws.append(
            TwoCohortDraw(
                source_indices=source,
                source_folds=drawn_folds,
                external_indices=external,
                receipt=_receipt(ordinal, source, drawn_folds, external),
            )
        )
    return tuple(draws)


__all__ = [
    "MAX_PATIENT_COUNT",
    "MIN_SOURCE_COUNT",
    "PROFILE_ID",
    "REPLICATES",
    "ResamplingError",
    "TwoCohortDraw",
    "TwoCohortDrawReceipt",
    "TwoCohortResamplingProfile",
    "generate_two_cohort_draws",
    "resampling_profile",
]
