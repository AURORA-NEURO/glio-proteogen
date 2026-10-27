"""Private transient parameters and a closed checkpoint-reproduction receipt.

The private producer constructs these objects after guarded source replay and
exact fit/trace/checkpoint comparisons. Saved receipt integrity and direct calls
to internal Python builders cannot establish that provenance on their own.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, NoReturn, Self, SupportsIndex

import numpy as np
import numpy.typing as npt
from pydantic import Field, field_validator, model_validator

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS
from glio_proteogen.research.gbmap_development_reduction.contracts import SHRINKAGE_GRID
from glio_proteogen.research.gbmap_held_mixture_truth import (
    HeldMixtureTruth,
    HeldMixtureTruthReceipt,
)

FloatArray = npt.NDArray[np.float64]


class SelectedFoldReplayError(ValueError):
    """A sanitized failure to recover an exact selected development fold."""


class SelectedFoldReplayReceipt(FrozenModel):
    """Reproduction evidence; no signatures, case values or source identifiers."""

    scope_version: Literal["selected-fold-checkpoint-reproduction/1.0.0"] = (
        "selected-fold-checkpoint-reproduction/1.0.0"
    )
    fold_id: str = Field(pattern=r"^(?:whole-study|within-study-donor)-[0-9]{4}$")
    kind: Literal["whole_study", "within_study_donor"]
    selected_shrinkage_index: Annotated[int, Field(ge=0, le=3)]
    selected_shrinkage: Annotated[float, Field(gt=0.0)]
    selected_feature_count: Annotated[int, Field(ge=2, le=512)]
    known_labels: tuple[str, ...] = Field(min_length=2, max_length=20)
    manifest_digest: Sha256Digest
    selection_receipt_digest: Sha256Digest
    checkpoint_set_digest: Sha256Digest
    reviewed_sha256: Sha256Digest
    feature_order_digest: Sha256Digest
    selected_feature_axis_digest: Sha256Digest
    profile_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest
    training_configuration_digest: Sha256Digest
    replayed_checkpoint_count: Annotated[int, Field(ge=2, le=20)]
    held_truth: HeldMixtureTruthReceipt
    unbiased_performance_established: Literal[False] = False
    mixture_accuracy_established: Literal[False] = False
    production_artifact_permitted: Literal[False] = False

    @field_validator("selected_shrinkage", mode="before")
    @classmethod
    def exact_float(cls, value: object) -> object:
        if type(value) is not float:
            raise ValueError("selected shrinkage requires an exact finite float")
        return value

    @field_validator(
        "unbiased_performance_established",
        "mixture_accuracy_established",
        "production_artifact_permitted",
        mode="before",
    )
    @classmethod
    def exact_false(cls, value: object) -> object:
        if value is not False:
            raise ValueError("checkpoint reproduction cannot establish a broader model claim")
        return value

    @model_validator(mode="after")
    def consistent_context(self) -> Self:
        prefix = "whole-study-" if self.kind == "whole_study" else "within-study-donor-"
        if (
            not self.fold_id.startswith(prefix)
            or self.selected_shrinkage != SHRINKAGE_GRID[self.selected_shrinkage_index]
            or self.known_labels != tuple(sorted(set(self.known_labels)))
            or set(self.known_labels) - set(PRODUCTION_SOURCE_LABELS)
            or self.replayed_checkpoint_count != len(self.known_labels)
            or self.held_truth.fold_id != self.fold_id
            or self.held_truth.kind != self.kind
            or not self.held_truth.fold_evaluable
            or self.held_truth.selected_feature_count != self.selected_feature_count
            or self.held_truth.known_label_count != len(self.known_labels)
            or any(
                row.known_in_context != (row.modeled_label in self.known_labels)
                for row in self.held_truth.labels
            )
        ):
            raise ValueError("replayed fold receipt does not conserve its context")
        return self


class SelectedFoldReplayResult:
    """Private arrays and raw held truth, created by the replaying producer.

    Explicitly retrieved arrays and coordinate tuples remain private. Hierarchy
    concentrations describe the reproduced lineage fits; they do not define a
    pooled-mixture concentration. No fitted study keys or training rows survive.
    """

    __slots__ = (
        "_background",
        "_feature_indices",
        "_held_truth",
        "_hierarchy_concentrations",
        "_receipt",
        "_signatures",
    )
    _receipt: SelectedFoldReplayReceipt
    _feature_indices: tuple[int, ...]
    _signatures: FloatArray
    _background: FloatArray
    _hierarchy_concentrations: tuple[float, ...]
    _held_truth: HeldMixtureTruth

    def __init__(self) -> None:
        raise TypeError("recover the private context through the selected-fold producer")

    def __repr__(self) -> str:
        return "<SelectedFoldReplayResult: private reproduced fold context>"

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("private replayed context is immutable")

    def __delattr__(self, _name: str) -> NoReturn:
        raise AttributeError("private replayed context is immutable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("private replayed context cannot be serialized")

    def __reduce__(self) -> NoReturn:
        raise TypeError("private replayed context cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("private replayed context cannot be serialized")

    @property
    def receipt(self) -> SelectedFoldReplayReceipt:
        return self._receipt

    @property
    def feature_indices(self) -> tuple[int, ...]:
        return self._feature_indices

    @property
    def known_labels(self) -> tuple[str, ...]:
        return self._receipt.known_labels

    @property
    def signatures(self) -> FloatArray:
        return self._signatures

    @property
    def background(self) -> FloatArray:
        return self._background

    @property
    def hierarchy_concentrations(self) -> tuple[float, ...]:
        return self._hierarchy_concentrations

    @property
    def held_truth(self) -> HeldMixtureTruth:
        return self._held_truth


def _frozen_probabilities(values: npt.ArrayLike, shape: tuple[int, ...]) -> FloatArray:
    if np.ma.isMaskedArray(values):
        raise SelectedFoldReplayError("replayed probabilities cannot discard masked coordinates")
    raw = np.asarray(values)
    if raw.dtype.kind not in "fiu" or raw.shape != shape:
        raise SelectedFoldReplayError("replayed probabilities do not match the selected axes")
    array = np.asarray(raw, dtype=np.float64)
    if (
        not np.all(np.isfinite(array))
        or np.any(array <= 0.0)
        or not np.allclose(np.sum(array, axis=0), 1.0, rtol=0.0, atol=1e-12)
    ):
        raise SelectedFoldReplayError("replayed probabilities require positive simplex columns")
    return np.frombuffer(array.tobytes(order="C"), dtype=np.float64).reshape(shape)


def _build_result(
    *,
    receipt: SelectedFoldReplayReceipt,
    feature_indices: tuple[int, ...],
    signatures: npt.ArrayLike,
    background: npt.ArrayLike,
    hierarchy_concentrations: tuple[float, ...],
    held_truth: HeldMixtureTruth,
) -> SelectedFoldReplayResult:
    if type(receipt) is not SelectedFoldReplayReceipt or type(held_truth) is not HeldMixtureTruth:
        raise SelectedFoldReplayError("replayed context requires exact internal evidence types")
    checked = SelectedFoldReplayReceipt.model_validate(receipt)
    if (
        type(feature_indices) is not tuple
        or len(feature_indices) != checked.selected_feature_count
        or any(
            type(index) is not int or not 0 <= index < checked.held_truth.source_feature_count
            for index in feature_indices
        )
        or len(set(feature_indices)) != len(feature_indices)
        or sha256_digest(
            {
                "schema": "gbmap-selected-feature-axis/1.0.0",
                "feature_order_digest": checked.feature_order_digest,
                "feature_indices": list(feature_indices),
            }
        )
        != checked.selected_feature_axis_digest
        or type(hierarchy_concentrations) is not tuple
        or len(hierarchy_concentrations) != len(checked.known_labels)
        or any(
            type(value) is not float or not math.isfinite(value) or value <= 0.0
            for value in hierarchy_concentrations
        )
        or held_truth.receipt != checked.held_truth
        or any(
            case.selected_counts.size != checked.selected_feature_count
            or case.reclassify().remaining_known_labels != checked.known_labels
            for case in held_truth.cases
        )
    ):
        raise SelectedFoldReplayError("replayed context differs from its declared axes or truth")
    result = object.__new__(SelectedFoldReplayResult)
    for name, value in (
        ("_receipt", checked),
        ("_feature_indices", feature_indices),
        (
            "_signatures",
            _frozen_probabilities(signatures, (len(feature_indices), len(checked.known_labels))),
        ),
        ("_background", _frozen_probabilities(background, (len(feature_indices),))),
        ("_hierarchy_concentrations", hierarchy_concentrations),
        ("_held_truth", held_truth),
    ):
        object.__setattr__(result, name, value)
    return result
