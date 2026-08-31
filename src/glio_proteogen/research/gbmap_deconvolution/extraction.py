"""Fail-closed offline extraction of GBmap raw counts into donor aggregates.

This module is deliberately outside every HTTP and CLI runtime.  It accepts an
exactly locked H5AD only, validates the sparse raw-count representation, and
reduces it to :class:`AggregateReference`.  Cell barcodes and donor-level
profiles never cross that aggregate boundary, and the retained receipt contains
neither donor identifiers nor donor-derived digests.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import stat
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import IO, Any, Final, Literal, Self, cast

import numpy as np
import numpy.typing as npt
from pydantic import Field, field_validator, model_validator

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .aggregate import AggregateReference, DonorLabelAggregate
from .errors import GbmapExtractionError, GbmapSourceAdmissionError
from .source import (
    CELLXGENE_CORE_DONOR_IDS,
    EXPECTED_DONOR_CATEGORY_SET_DIGEST,
    donor_category_set_digest,
)

EXPECTED_H5PY_VERSION: Final = "3.16.0"
EXTRACTION_RECIPE_ID: Final = "gbmap-h5ad-csr-aggregate/1.0.0"
PRODUCTION_CELL_COUNT: Final = 338_564
PRODUCTION_FEATURE_COUNT: Final = 5_000
PRODUCTION_SOURCE_DONOR_CATEGORY_COUNT: Final = 113
PRODUCTION_GROUPED_DONOR_CATEGORY_COUNT: Final = 110
# The Zenodo H5AD predates the curated donor grouping.  It retains three
# separately named PW032 samples and a non-core R4 specimen.  Every other
# category is an identity mapping to the fixed CELLxGENE donor vocabulary.
PRODUCTION_SOURCE_DONOR_CATEGORIES: Final = tuple(
    source
    for donor in CELLXGENE_CORE_DONOR_IDS
    for source in (
        ("PW032-701", "PW032-702", "PW032-712")
        if donor == "PW032"
        else (("R4", "R4 n.c.") if donor == "R4" else (donor,))
    )
)
PRODUCTION_SOURCE_STUDY_CATEGORY_COUNT: Final = 17
PRODUCTION_GROUPED_STUDY_COUNT: Final = 16
PRODUCTION_SOURCE_LABEL_COUNT: Final = 20
PRODUCTION_SOURCE_STUDY_CATEGORIES: Final = (
    "Bhaduri2020",
    "Couturier2020",
    "Darmanis2017",
    "Goswami2019",
    "Johnson2020",
    "Mathewson2021",
    "Neftel2019_10x",
    "Neftel2019_smart",
    "Pombo2021",
    "Richards2021",
    "Sankowski2019",
    "Wang2019",
    "Wang2020",
    "Wu2020",
    "Yu2020",
    "Yuan2018",
    "Zhao2020",
)
PRODUCTION_SOURCE_LABELS: Final = (
    "AC-like",
    "Astrocyte",
    "B cell",
    "CD4/CD8",
    "DC",
    "Endothelial",
    "MES-like",
    "Mast",
    "Mono",
    "Mural cell",
    "NK",
    "NPC-like",
    "Neuron",
    "OPC",
    "OPC-like",
    "Oligodendrocyte",
    "Plasma B",
    "RG",
    "TAM-BDM",
    "TAM-MG",
)
DEFAULT_ROW_BLOCK_SIZE: Final = 2_048
MIN_ROW_BLOCK_SIZE: Final = 1
MAX_ROW_BLOCK_SIZE: Final = 8_192
HASH_BLOCK_BYTES: Final = 4 * 1024 * 1024
ZENODO_SOURCE_ID: Final = "gbmap-core-zenodo-6962901"
ZENODO_SOURCE_BYTES: Final = 8_975_644_082
ZENODO_SOURCE_MD5: Final = "308f143ba384bd9a8acb0fbf2ea005fc"
_INT64_MAX: Final = np.iinfo(np.int64).max
_INT32_MAX: Final = np.iinfo(np.int32).max
_MD5_PATTERN: Final = r"^[0-9a-f]{32}$"

Int64Vector = npt.NDArray[np.int64]


def _canonical_text(value: object, name: str, *, maximum: int = 256) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{name} must be nonempty, unpadded text")
    if len(value) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return value


class ExactGbmapH5adLock(FrozenModel):
    """Reviewed byte-level lock required before H5AD parsing is permitted."""

    source_id: str = Field(min_length=1, max_length=128)
    expected_bytes: int = Field(gt=0)
    md5: str = Field(pattern=_MD5_PATTERN)
    sha256: Sha256Digest
    sha256_independently_reviewed: Literal[True] = True

    @field_validator("source_id")
    @classmethod
    def source_id_is_canonical(cls, value: str) -> str:
        return _canonical_text(value, "source_id", maximum=128)


class SourceFingerprint(FrozenModel):
    """Non-admitting byte fingerprint used to discover a candidate SHA-256."""

    fingerprint_id: Literal["gbmap-source-fingerprint/1.0.0"] = "gbmap-source-fingerprint/1.0.0"
    source_bytes: int = Field(gt=0)
    md5: str = Field(pattern=_MD5_PATTERN)
    sha256: Sha256Digest
    admission_granted: Literal[False] = False


class GbmapTaxonomyRule(FrozenModel):
    """One explicit source-label mapping or one explicit exclusion."""

    source_label: str = Field(min_length=1, max_length=256)
    modeled_label: str | None = Field(default=None, min_length=1, max_length=256)
    exclusion_reason: str | None = Field(default=None, min_length=1, max_length=256)

    @field_validator("source_label", "modeled_label", "exclusion_reason")
    @classmethod
    def text_is_canonical(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _canonical_text(value, "taxonomy text")

    @model_validator(mode="after")
    def exactly_one_disposition(self) -> Self:
        if (self.modeled_label is None) == (self.exclusion_reason is None):
            raise ValueError("taxonomy rule requires exactly one mapping or exclusion")
        return self


class GbmapLabelTaxonomy(FrozenModel):
    """Complete, versioned disposition of every observed GBmap source label."""

    taxonomy_id: str = Field(min_length=1, max_length=128)
    rules: tuple[GbmapTaxonomyRule, ...] = Field(min_length=1, max_length=256)

    @field_validator("taxonomy_id")
    @classmethod
    def taxonomy_id_is_canonical(cls, value: str) -> str:
        return _canonical_text(value, "taxonomy_id", maximum=128)

    @field_validator("rules")
    @classmethod
    def rules_are_unique_and_canonical(
        cls, value: tuple[GbmapTaxonomyRule, ...]
    ) -> tuple[GbmapTaxonomyRule, ...]:
        labels = tuple(rule.source_label for rule in value)
        if len(labels) != len(set(labels)):
            raise ValueError("taxonomy source labels must be unique")
        return tuple(sorted(value, key=lambda rule: rule.source_label))

    @property
    def taxonomy_digest(self) -> Sha256Digest:
        return sha256_digest(
            {
                "schema": "gbmap-label-taxonomy/1.0.0",
                "taxonomy": self.model_dump(mode="json"),
            }
        )

    @property
    def source_labels(self) -> frozenset[str]:
        return frozenset(rule.source_label for rule in self.rules)

    @property
    def modeled_labels(self) -> frozenset[str]:
        return frozenset(
            rule.modeled_label for rule in self.rules if rule.modeled_label is not None
        )

    def resolve(self, source_label: str) -> str | None:
        for rule in self.rules:
            if rule.source_label == source_label:
                return rule.modeled_label
        raise GbmapExtractionError("GBmap source label is absent from the reviewed taxonomy")


class GbmapDonorCrosswalkRule(FrozenModel):
    """One explicit source-H5AD patient category to grouped donor key mapping."""

    source_donor_category: str = Field(min_length=1, max_length=256)
    grouped_donor_key: str = Field(min_length=1, max_length=256)

    @field_validator("source_donor_category", "grouped_donor_key")
    @classmethod
    def donor_text_is_canonical(cls, value: str) -> str:
        return _canonical_text(value, "donor crosswalk text")


class GbmapDonorCrosswalk(FrozenModel):
    """Complete reviewed source-category grouping used before donor-level fitting."""

    crosswalk_id: str = Field(min_length=1, max_length=128)
    rules: tuple[GbmapDonorCrosswalkRule, ...] = Field(min_length=1, max_length=512)

    @field_validator("crosswalk_id")
    @classmethod
    def crosswalk_id_is_canonical(cls, value: str) -> str:
        return _canonical_text(value, "crosswalk_id", maximum=128)

    @field_validator("rules")
    @classmethod
    def source_categories_are_unique(
        cls, value: tuple[GbmapDonorCrosswalkRule, ...]
    ) -> tuple[GbmapDonorCrosswalkRule, ...]:
        sources = tuple(rule.source_donor_category for rule in value)
        if len(sources) != len(set(sources)):
            raise ValueError("donor crosswalk source categories must be unique")
        return tuple(sorted(value, key=lambda rule: rule.source_donor_category))

    @property
    def source_categories(self) -> frozenset[str]:
        return frozenset(rule.source_donor_category for rule in self.rules)

    @property
    def grouped_donor_keys(self) -> frozenset[str]:
        return frozenset(rule.grouped_donor_key for rule in self.rules)

    @property
    def crosswalk_digest(self) -> Sha256Digest:
        return sha256_digest(
            {
                "schema": "gbmap-donor-crosswalk/1.0.0",
                "crosswalk": self.model_dump(mode="json"),
            }
        )

    def resolve(self, source_donor_category: str) -> str:
        for rule in self.rules:
            if rule.source_donor_category == source_donor_category:
                return rule.grouped_donor_key
        raise GbmapExtractionError(
            "GBmap patient category is absent from the reviewed donor crosswalk"
        )


class GbmapStudyCrosswalkRule(FrozenModel):
    """One raw author/batch category to biological study mapping."""

    source_study_category: str = Field(min_length=1, max_length=256)
    grouped_study_key: str = Field(min_length=1, max_length=256)

    @field_validator("source_study_category", "grouped_study_key")
    @classmethod
    def study_text_is_canonical(cls, value: str) -> str:
        return _canonical_text(value, "study crosswalk text")


class GbmapStudyCrosswalk(FrozenModel):
    """Complete mapping that prevents Neftel batches leaking across study folds."""

    crosswalk_id: str = Field(min_length=1, max_length=128)
    rules: tuple[GbmapStudyCrosswalkRule, ...] = Field(min_length=1, max_length=128)

    @field_validator("crosswalk_id")
    @classmethod
    def crosswalk_id_is_canonical(cls, value: str) -> str:
        return _canonical_text(value, "crosswalk_id", maximum=128)

    @field_validator("rules")
    @classmethod
    def source_categories_are_unique(
        cls, value: tuple[GbmapStudyCrosswalkRule, ...]
    ) -> tuple[GbmapStudyCrosswalkRule, ...]:
        sources = tuple(rule.source_study_category for rule in value)
        if len(sources) != len(set(sources)):
            raise ValueError("study crosswalk source categories must be unique")
        return tuple(sorted(value, key=lambda rule: rule.source_study_category))

    @property
    def source_categories(self) -> frozenset[str]:
        return frozenset(rule.source_study_category for rule in self.rules)

    @property
    def grouped_study_keys(self) -> frozenset[str]:
        return frozenset(rule.grouped_study_key for rule in self.rules)

    @property
    def crosswalk_digest(self) -> Sha256Digest:
        return sha256_digest(
            {
                "schema": "gbmap-study-crosswalk/1.0.0",
                "crosswalk": self.model_dump(mode="json"),
            }
        )

    def resolve(self, source_study_category: str) -> str:
        for rule in self.rules:
            if rule.source_study_category == source_study_category:
                return rule.grouped_study_key
        raise GbmapExtractionError(
            "GBmap author category is absent from the reviewed study crosswalk"
        )


class GbmapExtractionRecipe(FrozenModel):
    """Version-bound structural and dimensional expectations for one H5AD."""

    recipe_id: Literal["gbmap-h5ad-csr-aggregate/1.0.0"] = EXTRACTION_RECIPE_ID
    source_profile: Literal["generic_fixture", "gbmap-core-zenodo-6962901"]
    h5py_version: Literal["3.16.0"] = EXPECTED_H5PY_VERSION
    matrix_path: str = Field(min_length=1, max_length=128)
    donor_path: str = Field(min_length=1, max_length=128)
    donor_categories_path: str | None = Field(default=None, min_length=1, max_length=128)
    study_path: str = Field(min_length=1, max_length=128)
    study_categories_path: str | None = Field(default=None, min_length=1, max_length=128)
    source_label_path: str = Field(min_length=1, max_length=128)
    source_label_categories_path: str | None = Field(default=None, min_length=1, max_length=128)
    feature_id_path: str = Field(min_length=1, max_length=128)
    gene_symbol_path: str | None = Field(default=None, min_length=1, max_length=128)
    expected_cell_count: int = Field(gt=0)
    expected_feature_count: int = Field(gt=0)
    expected_source_donor_category_count: int = Field(gt=0)
    expected_grouped_donor_category_count: int = Field(gt=0)
    expected_source_study_category_count: int = Field(gt=0)
    expected_grouped_study_count: int = Field(gt=0)
    expected_source_label_count: int = Field(gt=0)
    expected_grouped_donor_category_set_digest: Sha256Digest | None = None
    reviewed_donor_crosswalk_digest: Sha256Digest | None
    reviewed_study_crosswalk_digest: Sha256Digest
    reviewed_label_taxonomy_digest: Sha256Digest
    expected_nnz: int = Field(gt=0)
    row_block_size: int = Field(ge=MIN_ROW_BLOCK_SIZE, le=MAX_ROW_BLOCK_SIZE)
    matrix_encoding: Literal["csr_matrix"] = "csr_matrix"
    matrix_encoding_version: Literal["0.1.0"] = "0.1.0"
    count_data_dtype: Literal["float32"] = "float32"
    column_index_dtype: Literal["int32"] = "int32"
    row_pointer_dtype: Literal["int32"] = "int32"
    feature_identity_semantics: Literal["source_feature_key_not_stable_gene_id"] = (
        "source_feature_key_not_stable_gene_id"
    )
    count_semantics: Literal["finite_nonnegative_exact_integer_raw_counts"] = (
        "finite_nonnegative_exact_integer_raw_counts"
    )
    explicit_zero_policy: Literal["reject"] = "reject"
    duplicate_column_policy: Literal["reject"] = "reject"
    missing_annotation_policy: Literal["reject"] = "reject"

    @field_validator(
        "matrix_path",
        "donor_path",
        "donor_categories_path",
        "study_path",
        "study_categories_path",
        "source_label_path",
        "source_label_categories_path",
        "feature_id_path",
        "gene_symbol_path",
    )
    @classmethod
    def paths_are_canonical(cls, value: str | None) -> str | None:
        if value is None:
            return None
        canonical = _canonical_text(value, "H5AD path", maximum=128)
        if canonical.startswith("/") or "//" in canonical or canonical.endswith("/"):
            raise ValueError("H5AD paths must be canonical relative paths")
        return canonical

    @model_validator(mode="after")
    def paths_are_distinct(self) -> Self:
        paths = (
            self.matrix_path,
            self.donor_path,
            self.study_path,
            self.source_label_path,
            self.feature_id_path,
        )
        if len(paths) != len(set(paths)):
            raise ValueError("required H5AD paths must be distinct")
        if self.gene_symbol_path is not None and self.gene_symbol_path in paths:
            raise ValueError("gene_symbol_path must be distinct when provided")
        category_paths = tuple(
            path
            for path in (
                self.donor_categories_path,
                self.study_categories_path,
                self.source_label_categories_path,
            )
            if path is not None
        )
        if len(category_paths) != len(set(category_paths)) or set(category_paths) & set(paths):
            raise ValueError("legacy category paths must be unique and distinct")
        return self

    @property
    def extraction_recipe_digest(self) -> Sha256Digest:
        return sha256_digest(
            {
                "schema": "gbmap-extraction-recipe/1.0.0",
                "recipe": self.model_dump(mode="json"),
            }
        )


def production_extraction_recipe() -> GbmapExtractionRecipe:
    """Return structural locks evidenced by the pinned GBmap build notebooks."""

    return GbmapExtractionRecipe(
        source_profile="gbmap-core-zenodo-6962901",
        matrix_path="layers/counts",
        donor_path="obs/patient",
        donor_categories_path="obs/__categories/patient",
        study_path="obs/author",
        study_categories_path="obs/__categories/author",
        source_label_path="obs/CellID",
        source_label_categories_path="obs/__categories/CellID",
        feature_id_path="var/_index",
        gene_symbol_path=None,
        expected_cell_count=PRODUCTION_CELL_COUNT,
        expected_feature_count=PRODUCTION_FEATURE_COUNT,
        expected_source_donor_category_count=PRODUCTION_SOURCE_DONOR_CATEGORY_COUNT,
        expected_grouped_donor_category_count=PRODUCTION_GROUPED_DONOR_CATEGORY_COUNT,
        expected_source_study_category_count=PRODUCTION_SOURCE_STUDY_CATEGORY_COUNT,
        expected_grouped_study_count=PRODUCTION_GROUPED_STUDY_COUNT,
        expected_source_label_count=PRODUCTION_SOURCE_LABEL_COUNT,
        expected_grouped_donor_category_set_digest=EXPECTED_DONOR_CATEGORY_SET_DIGEST,
        reviewed_donor_crosswalk_digest=production_donor_crosswalk().crosswalk_digest,
        reviewed_study_crosswalk_digest=production_study_crosswalk().crosswalk_digest,
        reviewed_label_taxonomy_digest=production_label_taxonomy().taxonomy_digest,
        expected_nnz=196_660_428,
        row_block_size=DEFAULT_ROW_BLOCK_SIZE,
    )


def production_donor_crosswalk() -> GbmapDonorCrosswalk:
    """Group source samples to donors using reviewed primary-source semantics."""

    return GbmapDonorCrosswalk(
        crosswalk_id="gbmap-zenodo-patient-to-donor/1.0.0",
        rules=tuple(
            GbmapDonorCrosswalkRule(
                source_donor_category=source,
                grouped_donor_key=(
                    "PW032"
                    if source in {"PW032-701", "PW032-702", "PW032-712"}
                    else ("R4" if source == "R4 n.c." else source)
                ),
            )
            for source in PRODUCTION_SOURCE_DONOR_CATEGORIES
        ),
    )


def production_label_taxonomy() -> GbmapLabelTaxonomy:
    """Preserve all 20 source-annotated GBmap states without inferred collapse."""

    return GbmapLabelTaxonomy(
        taxonomy_id="gbmap-cellid-identity/1.0.0",
        rules=tuple(
            GbmapTaxonomyRule(source_label=label, modeled_label=label)
            for label in PRODUCTION_SOURCE_LABELS
        ),
    )


def production_study_crosswalk() -> GbmapStudyCrosswalk:
    """Collapse the two Neftel technical batches to their biological study."""

    return GbmapStudyCrosswalk(
        crosswalk_id="gbmap-author-to-study/1.0.0",
        rules=tuple(
            GbmapStudyCrosswalkRule(
                source_study_category=source,
                grouped_study_key=(
                    "Neftel2019" if source in {"Neftel2019_10x", "Neftel2019_smart"} else source
                ),
            )
            for source in PRODUCTION_SOURCE_STUDY_CATEGORIES
        ),
    )


def _reduction_recipe_digest(
    recipe: GbmapExtractionRecipe,
    donor_crosswalk: GbmapDonorCrosswalk,
    study_crosswalk: GbmapStudyCrosswalk,
) -> Sha256Digest:
    return sha256_digest(
        {
            "schema": "gbmap-source-reduction/1.0.0",
            "extraction_recipe_digest": recipe.extraction_recipe_digest,
            "donor_crosswalk_digest": donor_crosswalk.crosswalk_digest,
            "study_crosswalk_digest": study_crosswalk.crosswalk_digest,
        }
    )


def production_reduction_recipe_digest() -> Sha256Digest:
    """Return the exact production extraction-plus-crosswalk semantic digest."""

    return _reduction_recipe_digest(
        production_extraction_recipe(),
        production_donor_crosswalk(),
        production_study_crosswalk(),
    )


def _exact_index_vector(value: object, name: str) -> Int64Vector:
    if type(value) is not np.ndarray:
        raise ValueError(f"{name} must be an exact NumPy ndarray")
    array = cast("npt.NDArray[np.generic]", value)
    if array.ndim != 1 or array.dtype.kind not in "iu" or array.dtype.kind == "b":
        raise ValueError(f"{name} must be a one-dimensional integer array")
    if array.dtype.kind == "u":
        unsigned = np.asarray(array, dtype=np.uint64)
        if unsigned.size and int(unsigned.max()) > _INT64_MAX:
            raise ValueError(f"{name} exceeds signed int64")
    converted = np.asarray(array, dtype=np.int64)
    if bool(np.any(converted < 0)):
        raise ValueError(f"{name} cannot be negative")
    frozen = np.array(converted, dtype=np.int64, order="C", copy=True)
    frozen.flags.writeable = False
    return frozen


def _exact_count_vector(value: object, name: str) -> Int64Vector:
    if type(value) is not np.ndarray:
        raise ValueError(f"{name} must be an exact NumPy ndarray")
    array = cast("npt.NDArray[np.generic]", value)
    if array.ndim != 1 or array.dtype.kind not in "iuf" or array.dtype.kind == "b":
        raise ValueError(f"{name} must be a numeric one-dimensional array")
    if array.dtype.kind == "f":
        floating = np.asarray(array, dtype=np.float64)
        if not bool(np.all(np.isfinite(floating))):
            raise ValueError(f"{name} contains a non-finite value")
        # ``float(INT64_MAX)`` rounds upward to 2**63.  Equality therefore is
        # already outside the signed-int64 domain and must be rejected before
        # NumPy's cast can wrap it to INT64_MIN.
        if bool(np.any(floating < 0.0)) or bool(np.any(floating >= float(_INT64_MAX))):
            raise ValueError(f"{name} is outside the signed-int64 count domain")
        if not bool(np.all(floating == np.floor(floating))):
            raise ValueError(f"{name} contains a fractional count")
    elif array.dtype.kind == "u":
        unsigned = np.asarray(array, dtype=np.uint64)
        if unsigned.size and int(unsigned.max()) > _INT64_MAX:
            raise ValueError(f"{name} exceeds signed int64")
    else:
        signed = np.asarray(array, dtype=np.int64)
        if bool(np.any(signed < 0)):
            raise ValueError(f"{name} contains a negative count")
    converted = np.asarray(array, dtype=np.int64)
    if bool(np.any(converted == 0)):
        raise ValueError(f"{name} contains an explicit sparse zero")
    frozen = np.array(converted, dtype=np.int64, order="C", copy=True)
    frozen.flags.writeable = False
    return frozen


@dataclass(frozen=True, slots=True)
class SparseCountBlock:
    """One bounded contiguous CSR row block plus aligned source annotations."""

    row_start: int
    donor_keys: tuple[str, ...]
    study_keys: tuple[str, ...]
    source_labels: tuple[str, ...]
    indptr: Int64Vector
    indices: Int64Vector
    data: Int64Vector

    def __post_init__(self) -> None:
        if type(self.row_start) is not int or self.row_start < 0:
            raise ValueError("row_start must be an exact nonnegative integer")
        if type(self.donor_keys) is not tuple or not self.donor_keys:
            raise ValueError("donor_keys must be a nonempty tuple")
        row_count = len(self.donor_keys)
        if type(self.study_keys) is not tuple or len(self.study_keys) != row_count:
            raise ValueError("study_keys must align with donor_keys")
        if type(self.source_labels) is not tuple or len(self.source_labels) != row_count:
            raise ValueError("source_labels must align with donor_keys")
        object.__setattr__(
            self,
            "donor_keys",
            tuple(_canonical_text(item, "donor_key") for item in self.donor_keys),
        )
        object.__setattr__(
            self,
            "study_keys",
            tuple(_canonical_text(item, "study_key") for item in self.study_keys),
        )
        object.__setattr__(
            self,
            "source_labels",
            tuple(_canonical_text(item, "source_label") for item in self.source_labels),
        )
        indptr = _exact_index_vector(self.indptr, "indptr")
        indices = _exact_index_vector(self.indices, "indices")
        data = _exact_count_vector(self.data, "data")
        if len(indptr) != row_count + 1 or int(indptr[0]) != 0:
            raise ValueError("indptr must start at zero and contain one pointer per row boundary")
        if bool(np.any(indptr[1:] < indptr[:-1])):
            raise ValueError("indptr must be monotone nondecreasing")
        if int(indptr[-1]) != len(indices) or len(indices) != len(data):
            raise ValueError("CSR pointer, index, and data lengths do not reconcile")
        for row in range(row_count):
            start = int(indptr[row])
            end = int(indptr[row + 1])
            if end - start > 1 and bool(
                np.any(indices[start + 1 : end] <= indices[start : end - 1])
            ):
                raise ValueError("CSR column indices must be strictly increasing within every row")
        object.__setattr__(self, "indptr", indptr)
        object.__setattr__(self, "indices", indices)
        object.__setattr__(self, "data", data)

    @property
    def row_count(self) -> int:
        return len(self.donor_keys)


class GbmapExtractionReceipt(FrozenModel):
    """Retainable projection that excludes donor and cell-level information."""

    receipt_id: Literal["gbmap-extraction-receipt/1.0.0"] = "gbmap-extraction-receipt/1.0.0"
    receipt_digest: Sha256Digest
    source_sha256: Sha256Digest
    source_bytes: int = Field(gt=0)
    extraction_recipe_digest: Sha256Digest
    taxonomy_digest: Sha256Digest
    feature_order_digest: Sha256Digest
    h5py_version: Literal["3.16.0"] = EXPECTED_H5PY_VERSION
    cell_count: int = Field(gt=0)
    retained_cell_count: int = Field(ge=0)
    explicitly_excluded_cell_count: int = Field(ge=0)
    source_donor_category_count: int = Field(gt=0)
    grouped_donor_category_count: int = Field(gt=0)
    source_study_category_count: int = Field(gt=0)
    grouped_study_count: int = Field(gt=0)
    source_label_count: int = Field(gt=0)
    modeled_label_count: int = Field(gt=0)
    record_count: int = Field(gt=0)
    cell_level_material_retained: Literal[False] = False
    donor_identifiers_retained: Literal[False] = False
    donor_hashes_retained: Literal[False] = False
    donor_profiles_retained: Literal[False] = False
    aggregate_content_digest_retained: Literal[False] = False

    @model_validator(mode="after")
    def receipt_is_consistent(self) -> Self:
        if self.retained_cell_count + self.explicitly_excluded_cell_count != self.cell_count:
            raise ValueError("retained and excluded cells do not reconcile")
        payload = self.model_dump(mode="json", exclude={"receipt_digest"})
        if self.receipt_digest != sha256_digest(payload):
            raise ValueError("GBmap extraction receipt digest mismatch")
        return self


@dataclass(frozen=True, slots=True)
class GbmapExtractionResult:
    """Transient aggregate plus its deidentified, retainable receipt."""

    reference: AggregateReference
    receipt: GbmapExtractionReceipt

    def __post_init__(self) -> None:
        if type(self.reference) is not AggregateReference:
            raise ValueError("reference must be an exact AggregateReference")
        if type(self.receipt) is not GbmapExtractionReceipt:
            raise ValueError("receipt must be an exact GbmapExtractionReceipt")
        if self.reference.source_file_sha256 != self.receipt.source_sha256:
            raise ValueError("reference and receipt source digests disagree")
        if self.reference.source_bytes != self.receipt.source_bytes:
            raise ValueError("reference and receipt source lengths disagree")
        if self.reference.taxonomy_digest != self.receipt.taxonomy_digest:
            raise ValueError("reference and receipt taxonomy digests disagree")
        if self.reference.extraction_recipe_digest != self.receipt.extraction_recipe_digest:
            raise ValueError("reference and receipt recipe digests disagree")
        if self.reference.feature_order_digest != self.receipt.feature_order_digest:
            raise ValueError("reference and receipt feature-order digests disagree")


@dataclass(slots=True)
class _MutableAggregate:
    study_key: str
    gene_counts: Int64Vector
    detected_cell_counts: npt.NDArray[np.int32]
    cell_count: int = 0
    total_umis: int = 0
    source_labels: set[str] = field(default_factory=set)


def _require_reviewed_reduction_semantics(
    *,
    recipe: GbmapExtractionRecipe,
    taxonomy: GbmapLabelTaxonomy,
    donor_crosswalk: GbmapDonorCrosswalk,
    study_crosswalk: GbmapStudyCrosswalk,
) -> None:
    expected_donor = recipe.reviewed_donor_crosswalk_digest
    if expected_donor is None:
        raise GbmapSourceAdmissionError(
            "GBmap production donor crosswalk is unresolved and not admitted"
        )
    if donor_crosswalk.crosswalk_digest != expected_donor:
        raise GbmapSourceAdmissionError("GBmap donor crosswalk differs from its reviewed digest")
    if study_crosswalk.crosswalk_digest != recipe.reviewed_study_crosswalk_digest:
        raise GbmapSourceAdmissionError("GBmap study crosswalk differs from its reviewed digest")
    if taxonomy.taxonomy_digest != recipe.reviewed_label_taxonomy_digest:
        raise GbmapSourceAdmissionError("GBmap label taxonomy differs from its reviewed digest")


class _AggregateBuilder:
    def __init__(
        self,
        *,
        feature_ids: tuple[str, ...],
        gene_symbols: tuple[str | None, ...],
        source_sha256: Sha256Digest,
        source_bytes: int,
        taxonomy: GbmapLabelTaxonomy,
        donor_crosswalk: GbmapDonorCrosswalk,
        study_crosswalk: GbmapStudyCrosswalk,
        recipe: GbmapExtractionRecipe,
        cancellation: CancellationContext | None,
    ) -> None:
        _require_reviewed_reduction_semantics(
            recipe=recipe,
            taxonomy=taxonomy,
            donor_crosswalk=donor_crosswalk,
            study_crosswalk=study_crosswalk,
        )
        self._feature_ids = feature_ids
        self._gene_symbols = gene_symbols
        self._source_sha256 = source_sha256
        self._source_bytes = source_bytes
        self._taxonomy = taxonomy
        self._donor_crosswalk = donor_crosswalk
        self._study_crosswalk = study_crosswalk
        self._recipe = recipe
        self._cancellation = cancellation
        self._next_row = 0
        self._donor_studies: dict[str, str] = {}
        self._observed_source_donors: set[str] = set()
        self._observed_grouped_donors: set[str] = set()
        self._observed_source_studies: set[str] = set()
        self._observed_grouped_studies: set[str] = set()
        self._observed_source_labels: set[str] = set()
        self._retained_cells = 0
        self._excluded_cells = 0
        self._aggregates: dict[tuple[str, str], _MutableAggregate] = {}

    def ingest(self, block: SparseCountBlock) -> None:  # noqa: PLR0915
        checkpoint(self._cancellation)
        if block.row_start != self._next_row:
            raise GbmapExtractionError("CSR blocks must cover rows contiguously in source order")
        if block.indices.size and int(np.max(block.indices)) >= len(self._feature_ids):
            raise GbmapExtractionError("CSR column index exceeds the feature boundary")
        for local_row in range(block.row_count):
            checkpoint(self._cancellation)
            source_donor = block.donor_keys[local_row]
            source_study = block.study_keys[local_row]
            donor = self._donor_crosswalk.resolve(source_donor)
            study = self._study_crosswalk.resolve(source_study)
            source_label = block.source_labels[local_row]
            prior_study = self._donor_studies.setdefault(donor, study)
            if prior_study != study:
                raise GbmapExtractionError("one source donor category maps to multiple studies")
            self._observed_source_donors.add(source_donor)
            self._observed_grouped_donors.add(donor)
            self._observed_source_studies.add(source_study)
            self._observed_grouped_studies.add(study)
            self._observed_source_labels.add(source_label)
            modeled_label = self._taxonomy.resolve(source_label)
            if modeled_label is None:
                self._excluded_cells += 1
                continue
            self._retained_cells += 1
            key = (donor, modeled_label)
            aggregate = self._aggregates.get(key)
            if aggregate is None:
                aggregate = _MutableAggregate(
                    study_key=study,
                    gene_counts=np.zeros(len(self._feature_ids), dtype=np.int64),
                    detected_cell_counts=np.zeros(len(self._feature_ids), dtype=np.int32),
                )
                self._aggregates[key] = aggregate
            elif aggregate.study_key != study:
                raise GbmapExtractionError("aggregate donor/study assignment drifted")
            start = int(block.indptr[local_row])
            end = int(block.indptr[local_row + 1])
            columns = block.indices[start:end]
            counts = block.data[start:end]
            if counts.size:
                current = aggregate.gene_counts[columns]
                if bool(np.any(counts > _INT64_MAX - current)):
                    raise GbmapExtractionError("gene-count accumulation exceeds signed int64")
                detections = aggregate.detected_cell_counts[columns]
                if bool(np.any(detections == _INT32_MAX)):
                    raise GbmapExtractionError("detection-count accumulation exceeds signed int32")
                aggregate.gene_counts[columns] = current + counts
                aggregate.detected_cell_counts[columns] = detections + 1
                row_total = sum((int(value) for value in counts), start=0)
                if row_total > _INT64_MAX - aggregate.total_umis:
                    raise GbmapExtractionError("UMI accumulation exceeds signed int64")
                aggregate.total_umis += row_total
            aggregate.cell_count += 1
            aggregate.source_labels.add(source_label)
        self._next_row += block.row_count

    def finish(self) -> GbmapExtractionResult:
        checkpoint(self._cancellation)
        recipe = self._recipe
        if self._next_row != recipe.expected_cell_count:
            raise GbmapExtractionError("source cell count differs from the extraction recipe")
        if len(self._observed_source_donors) != recipe.expected_source_donor_category_count:
            raise GbmapExtractionError("source patient-category count differs from the recipe")
        if len(self._observed_grouped_donors) != recipe.expected_grouped_donor_category_count:
            raise GbmapExtractionError("grouped donor-category count differs from the recipe")
        if len(self._observed_source_studies) != recipe.expected_source_study_category_count:
            raise GbmapExtractionError("source author-category count differs from the recipe")
        if len(self._observed_grouped_studies) != recipe.expected_grouped_study_count:
            raise GbmapExtractionError("grouped study count differs from the extraction recipe")
        if len(self._observed_source_labels) != recipe.expected_source_label_count:
            raise GbmapExtractionError("source label count differs from the extraction recipe")
        if self._observed_source_labels != self._taxonomy.source_labels:
            raise GbmapExtractionError(
                "taxonomy must exactly cover every and only observed source label"
            )
        if self._observed_source_donors != self._donor_crosswalk.source_categories:
            raise GbmapExtractionError(
                "donor crosswalk must exactly cover every and only observed patient category"
            )
        if self._observed_grouped_donors != self._donor_crosswalk.grouped_donor_keys:
            raise GbmapExtractionError("donor crosswalk grouped-key closure failed")
        if self._observed_source_studies != self._study_crosswalk.source_categories:
            raise GbmapExtractionError(
                "study crosswalk must exactly cover every and only observed author category"
            )
        if self._observed_grouped_studies != self._study_crosswalk.grouped_study_keys:
            raise GbmapExtractionError("study crosswalk grouped-key closure failed")
        expected_donor_digest = recipe.expected_grouped_donor_category_set_digest
        if expected_donor_digest is not None:
            observed_digest = donor_category_set_digest(tuple(self._observed_grouped_donors))
            if observed_digest != expected_donor_digest:
                raise GbmapExtractionError("source donor-category set differs from the pinned set")
        if not self._aggregates:
            raise GbmapExtractionError("taxonomy excluded every source cell")

        records: list[DonorLabelAggregate] = []
        for donor, modeled_label in sorted(self._aggregates):
            aggregate = self._aggregates.pop((donor, modeled_label))
            records.append(
                DonorLabelAggregate(
                    donor_key=donor,
                    study_key=aggregate.study_key,
                    modeled_label=modeled_label,
                    source_labels=tuple(aggregate.source_labels),
                    cell_count=aggregate.cell_count,
                    gene_counts=aggregate.gene_counts,
                    detected_cell_counts=aggregate.detected_cell_counts,
                    total_umis=aggregate.total_umis,
                )
            )
        reference = AggregateReference(
            feature_ids=self._feature_ids,
            gene_symbols=self._gene_symbols,
            records=tuple(records),
            source_file_sha256=self._source_sha256,
            source_bytes=self._source_bytes,
            taxonomy_digest=self._taxonomy.taxonomy_digest,
            extraction_recipe_digest=_reduction_recipe_digest(
                recipe,
                self._donor_crosswalk,
                self._study_crosswalk,
            ),
        )
        receipt_payload: dict[str, object] = {
            "receipt_id": "gbmap-extraction-receipt/1.0.0",
            "source_sha256": self._source_sha256,
            "source_bytes": self._source_bytes,
            "extraction_recipe_digest": reference.extraction_recipe_digest,
            "taxonomy_digest": self._taxonomy.taxonomy_digest,
            "feature_order_digest": reference.feature_order_digest,
            "h5py_version": EXPECTED_H5PY_VERSION,
            "cell_count": self._next_row,
            "retained_cell_count": self._retained_cells,
            "explicitly_excluded_cell_count": self._excluded_cells,
            "source_donor_category_count": len(self._observed_source_donors),
            "grouped_donor_category_count": len(self._observed_grouped_donors),
            "source_study_category_count": len(self._observed_source_studies),
            "grouped_study_count": len(self._observed_grouped_studies),
            "source_label_count": len(self._observed_source_labels),
            "modeled_label_count": len(reference.modeled_labels),
            "record_count": len(reference.records),
            "cell_level_material_retained": False,
            "donor_identifiers_retained": False,
            "donor_hashes_retained": False,
            "donor_profiles_retained": False,
            "aggregate_content_digest_retained": False,
        }
        receipt = GbmapExtractionReceipt.model_validate(
            {
                "receipt_digest": sha256_digest(receipt_payload),
                **receipt_payload,
            },
            strict=True,
        )
        return GbmapExtractionResult(reference=reference, receipt=receipt)


def _validated_features(
    feature_ids: Sequence[str],
    gene_symbols: Sequence[str | None],
    recipe: GbmapExtractionRecipe,
) -> tuple[tuple[str, ...], tuple[str | None, ...]]:
    if len(feature_ids) != recipe.expected_feature_count:
        raise GbmapExtractionError("source feature count differs from the extraction recipe")
    if len(gene_symbols) != len(feature_ids):
        raise GbmapExtractionError("gene symbols must align with feature identifiers")
    identifiers = tuple(_canonical_text(value, "feature_id") for value in feature_ids)
    if len(identifiers) != len(set(identifiers)):
        raise GbmapExtractionError("source feature identifiers must be unique")
    symbols = tuple(
        None if value is None else _canonical_text(value, "gene_symbol") for value in gene_symbols
    )
    return identifiers, symbols


def aggregate_sparse_count_blocks(
    *,
    blocks: Iterable[SparseCountBlock],
    feature_ids: Sequence[str],
    gene_symbols: Sequence[str | None],
    source_sha256: Sha256Digest,
    source_bytes: int,
    taxonomy: GbmapLabelTaxonomy,
    donor_crosswalk: GbmapDonorCrosswalk,
    study_crosswalk: GbmapStudyCrosswalk,
    recipe: GbmapExtractionRecipe,
    cancellation: CancellationContext | None = None,
) -> GbmapExtractionResult:
    """Reduce validated bounded CSR blocks without retaining any cell records."""

    checkpoint(cancellation)
    _require_reviewed_reduction_semantics(
        recipe=recipe,
        taxonomy=taxonomy,
        donor_crosswalk=donor_crosswalk,
        study_crosswalk=study_crosswalk,
    )
    identifiers, symbols = _validated_features(feature_ids, gene_symbols, recipe)
    builder = _AggregateBuilder(
        feature_ids=identifiers,
        gene_symbols=symbols,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        taxonomy=taxonomy,
        donor_crosswalk=donor_crosswalk,
        study_crosswalk=study_crosswalk,
        recipe=recipe,
        cancellation=cancellation,
    )
    block_count = 0
    for block in blocks:
        if type(block) is not SparseCountBlock:
            raise GbmapExtractionError("blocks must contain exact SparseCountBlock instances")
        builder.ingest(block)
        block_count += 1
    if block_count == 0:
        raise GbmapExtractionError("at least one sparse count block is required")
    return builder.finish()


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return (int(info.st_dev), int(info.st_ino), int(info.st_size), int(info.st_mtime_ns))


def _require_same_identity(
    first: os.stat_result,
    second: os.stat_result,
    message: str,
) -> None:
    if _file_identity(first) != _file_identity(second):
        raise GbmapSourceAdmissionError(message)


def _require_open_length(fingerprint: SourceFingerprint, info: os.stat_result) -> None:
    if fingerprint.source_bytes != info.st_size:
        raise GbmapSourceAdmissionError("GBmap source length disagrees with its open handle")


def _require_regular_source(source: Path) -> os.stat_result:
    try:
        info = source.stat(follow_symlinks=False)
    except OSError as exc:
        raise GbmapSourceAdmissionError("GBmap source is unavailable") from exc
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    file_attributes = int(getattr(info, "st_file_attributes", 0))
    if source.is_symlink() or (reparse_flag and file_attributes & reparse_flag):
        raise GbmapSourceAdmissionError("GBmap source must not be a link or reparse point")
    if not stat.S_ISREG(info.st_mode):
        raise GbmapSourceAdmissionError("GBmap source must be a regular file")
    if info.st_size <= 0:
        raise GbmapSourceAdmissionError("GBmap source must be nonempty")
    return info


def _hash_open_handle(
    handle: IO[bytes],
    cancellation: CancellationContext | None,
) -> SourceFingerprint:
    checkpoint(cancellation)
    handle.seek(0)
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    total = 0
    while True:
        checkpoint(cancellation)
        chunk = handle.read(HASH_BLOCK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        md5.update(chunk)
        sha256.update(chunk)
    if total <= 0:
        raise GbmapSourceAdmissionError("GBmap source must be nonempty")
    return SourceFingerprint(
        source_bytes=total,
        md5=md5.hexdigest(),
        sha256=f"sha256:{sha256.hexdigest()}",
    )


def fingerprint_gbmap_source(
    source: Path,
    *,
    cancellation: CancellationContext | None = None,
) -> SourceFingerprint:
    """Fingerprint candidate bytes without conferring source admission."""

    initial = _require_regular_source(source)
    try:
        with source.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if _file_identity(initial) != _file_identity(opened):
                raise GbmapSourceAdmissionError("GBmap source changed while it was opened")
            fingerprint = _hash_open_handle(handle, cancellation)
            final = os.fstat(handle.fileno())
    except OSError as exc:
        raise GbmapSourceAdmissionError("GBmap source could not be fingerprinted") from exc
    if _file_identity(opened) != _file_identity(final):
        raise GbmapSourceAdmissionError("GBmap source changed during fingerprinting")
    if fingerprint.source_bytes != final.st_size:
        raise GbmapSourceAdmissionError("GBmap source length changed during fingerprinting")
    return fingerprint


def _require_locked_fingerprint(
    fingerprint: SourceFingerprint,
    lock: ExactGbmapH5adLock,
) -> None:
    if (
        fingerprint.source_bytes != lock.expected_bytes
        or fingerprint.md5 != lock.md5
        or fingerprint.sha256 != lock.sha256
    ):
        raise GbmapSourceAdmissionError("GBmap source bytes do not match the reviewed lock")


def _require_recipe_source_lock(
    recipe: GbmapExtractionRecipe,
    lock: ExactGbmapH5adLock,
) -> None:
    if recipe.source_profile == "generic_fixture":
        return
    if (
        lock.source_id != ZENODO_SOURCE_ID
        or lock.expected_bytes != ZENODO_SOURCE_BYTES
        or lock.md5 != ZENODO_SOURCE_MD5
    ):
        raise GbmapSourceAdmissionError("GBmap Zenodo source lock metadata is not exact")


def _load_h5py(recipe: GbmapExtractionRecipe) -> ModuleType:
    try:
        module = importlib.import_module("h5py")
    except ImportError as exc:
        raise GbmapSourceAdmissionError(
            "offline GBmap extraction requires the locked source dependency group"
        ) from exc
    version = getattr(module, "__version__", None)
    if version != recipe.h5py_version:
        raise GbmapSourceAdmissionError("installed h5py version differs from the recipe lock")
    return module


def _decode_scalar_text(value: object, name: str) -> str:
    if isinstance(value, str):
        return _canonical_text(value, name)
    if isinstance(value, (bytes, np.bytes_)):
        try:
            decoded = bytes(value).decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise GbmapExtractionError(f"{name} is not valid UTF-8") from exc
        return _canonical_text(decoded, name)
    raise GbmapExtractionError(f"{name} must contain UTF-8 text")


def _decode_text_array(value: object, name: str) -> tuple[str, ...]:
    if type(value) is not np.ndarray:
        raise GbmapExtractionError(f"{name} must be an HDF5 vector")
    array = cast("npt.NDArray[np.generic]", value)
    if array.ndim != 1:
        raise GbmapExtractionError(f"{name} must be one-dimensional")
    return tuple(_decode_scalar_text(item, name) for item in array)


class _H5TextReader:
    def __init__(
        self,
        obj: object,
        *,
        length: int,
        name: str,
        categories_obj: object | None = None,
    ) -> None:
        dynamic = cast("Any", obj)
        self._name = name
        self._length = length
        self._dataset: Any | None = None
        self._codes: Any | None = None
        self._categories: tuple[str, ...] | None = None
        if categories_obj is not None:
            categories_dynamic = cast("Any", categories_obj)
            if hasattr(dynamic, "keys") or tuple(dynamic.shape) != (length,):
                raise GbmapExtractionError(f"{name} legacy categorical codes have the wrong shape")
            category_values = _decode_text_array(
                np.asarray(categories_dynamic[:]), f"{name} categories"
            )
            if not category_values or len(category_values) != len(set(category_values)):
                raise GbmapExtractionError(f"{name} categories must be nonempty and unique")
            reference = dynamic.attrs.get("categories")
            if reference is None:
                raise GbmapExtractionError(f"{name} lacks its legacy categories reference")
            try:
                referenced = dynamic.file[reference]
            except (KeyError, TypeError, ValueError) as exc:
                raise GbmapExtractionError(f"{name} has an invalid categories reference") from exc
            if referenced.name != categories_dynamic.name:
                raise GbmapExtractionError(f"{name} categories reference points elsewhere")
            if bool(categories_dynamic.attrs.get("ordered", True)):
                raise GbmapExtractionError(f"{name} categories must be explicitly unordered")
            self._codes = dynamic
            self._categories = category_values
        elif hasattr(dynamic, "keys"):
            keys = set(dynamic.keys())
            if not {"codes", "categories"}.issubset(keys):
                raise GbmapExtractionError(f"{name} categorical encoding is incomplete")
            codes = dynamic["codes"]
            categories = dynamic["categories"]
            if tuple(codes.shape) != (length,):
                raise GbmapExtractionError(f"{name} categorical codes have the wrong shape")
            category_values = _decode_text_array(np.asarray(categories[:]), f"{name} categories")
            if not category_values or len(category_values) != len(set(category_values)):
                raise GbmapExtractionError(f"{name} categories must be nonempty and unique")
            self._codes = codes
            self._categories = category_values
        else:
            if tuple(dynamic.shape) != (length,):
                raise GbmapExtractionError(f"{name} has the wrong shape")
            self._dataset = dynamic

    def read(self, start: int, end: int) -> tuple[str, ...]:
        if start < 0 or end < start or end > self._length:
            raise GbmapExtractionError(f"{self._name} slice is outside its source boundary")
        if self._dataset is not None:
            return _decode_text_array(np.asarray(self._dataset[start:end]), self._name)
        if self._codes is None or self._categories is None:
            raise GbmapExtractionError(f"{self._name} reader is not initialized")
        codes = np.asarray(self._codes[start:end])
        if codes.ndim != 1 or codes.dtype.kind not in "iu" or codes.dtype.kind == "b":
            raise GbmapExtractionError(f"{self._name} categorical codes must be integers")
        categories = self._categories
        values: list[str] = []
        for raw_code in codes:
            code = int(raw_code)
            if code < 0 or code >= len(categories):
                raise GbmapExtractionError(f"{self._name} contains a missing or invalid code")
            values.append(categories[code])
        return tuple(values)

    @property
    def declared_categories(self) -> frozenset[str] | None:
        if self._categories is None:
            return None
        return frozenset(self._categories)


def _required_h5_object(h5: object, path: str) -> object:
    dynamic = cast("Any", h5)
    try:
        return cast("object", dynamic[path])
    except KeyError as exc:
        raise GbmapExtractionError("GBmap H5AD is missing a required object") from exc


def _encoding_type(group: object) -> str:
    dynamic = cast("Any", group)
    raw = dynamic.attrs.get("encoding-type")
    return _decode_scalar_text(raw, "matrix encoding-type")


def _encoding_version(group: object) -> str:
    dynamic = cast("Any", group)
    raw = dynamic.attrs.get("encoding-version")
    return _decode_scalar_text(raw, "matrix encoding-version")


def _matrix_shape(group: object) -> tuple[int, int]:
    dynamic = cast("Any", group)
    raw = np.asarray(dynamic.attrs.get("shape"))
    if raw.shape != (2,) or raw.dtype.kind not in "iu" or raw.dtype.kind == "b":
        raise GbmapExtractionError("sparse matrix shape attribute is invalid")
    rows, columns = (int(raw[0]), int(raw[1]))
    if rows <= 0 or columns <= 0:
        raise GbmapExtractionError("sparse matrix shape must be positive")
    return rows, columns


def _read_all_text(obj: object, *, length: int, name: str) -> tuple[str, ...]:
    return _H5TextReader(obj, length=length, name=name).read(0, length)


def _extract_open_h5ad(  # noqa: PLR0915
    h5: object,
    *,
    source_fingerprint: SourceFingerprint,
    taxonomy: GbmapLabelTaxonomy,
    donor_crosswalk: GbmapDonorCrosswalk,
    study_crosswalk: GbmapStudyCrosswalk,
    recipe: GbmapExtractionRecipe,
    cancellation: CancellationContext | None,
) -> GbmapExtractionResult:
    checkpoint(cancellation)
    matrix_object = _required_h5_object(h5, recipe.matrix_path)
    matrix = cast("Any", matrix_object)
    if (
        not hasattr(matrix, "keys")
        or _encoding_type(matrix_object) != recipe.matrix_encoding
        or _encoding_version(matrix_object) != recipe.matrix_encoding_version
    ):
        raise GbmapExtractionError("GBmap count layer must use the locked CSR encoding")
    rows, columns = _matrix_shape(matrix_object)
    if (rows, columns) != (recipe.expected_cell_count, recipe.expected_feature_count):
        raise GbmapExtractionError("GBmap count-layer shape differs from the extraction recipe")
    keys = set(matrix.keys())
    if not {"data", "indices", "indptr"}.issubset(keys):
        raise GbmapExtractionError("GBmap CSR layer is incomplete")
    data_dataset = matrix["data"]
    indices_dataset = matrix["indices"]
    indptr_dataset = matrix["indptr"]
    if len(data_dataset.shape) != 1 or len(indices_dataset.shape) != 1:
        raise GbmapExtractionError("GBmap CSR data and indices must be vectors")
    if tuple(indptr_dataset.shape) != (rows + 1,):
        raise GbmapExtractionError("GBmap CSR indptr has the wrong shape")
    if tuple(data_dataset.shape) != tuple(indices_dataset.shape):
        raise GbmapExtractionError("GBmap CSR data and index lengths disagree")
    if int(data_dataset.shape[0]) != recipe.expected_nnz:
        raise GbmapExtractionError("GBmap CSR stored-entry count differs from the recipe")
    if np.dtype(data_dataset.dtype) != np.dtype(recipe.count_data_dtype):
        raise GbmapExtractionError("GBmap count data dtype differs from the recipe")
    if np.dtype(indices_dataset.dtype) != np.dtype(recipe.column_index_dtype):
        raise GbmapExtractionError("GBmap column-index dtype differs from the recipe")
    if np.dtype(indptr_dataset.dtype) != np.dtype(recipe.row_pointer_dtype):
        raise GbmapExtractionError("GBmap row-pointer dtype differs from the recipe")
    indptr = _exact_index_vector(np.asarray(indptr_dataset[:]), "H5AD indptr")
    if int(indptr[0]) != 0 or bool(np.any(indptr[1:] < indptr[:-1])):
        raise GbmapExtractionError("GBmap CSR indptr is not canonical")
    if int(indptr[-1]) != int(data_dataset.shape[0]):
        raise GbmapExtractionError("GBmap CSR indptr does not close over stored entries")

    feature_ids = _read_all_text(
        _required_h5_object(h5, recipe.feature_id_path),
        length=columns,
        name="feature identifiers",
    )
    if recipe.gene_symbol_path is None:
        gene_symbols: tuple[str | None, ...] = (None,) * columns
    else:
        gene_symbols = _read_all_text(
            _required_h5_object(h5, recipe.gene_symbol_path),
            length=columns,
            name="gene symbols",
        )
    identifiers, symbols = _validated_features(feature_ids, gene_symbols, recipe)
    donor_categories = (
        None
        if recipe.donor_categories_path is None
        else _required_h5_object(h5, recipe.donor_categories_path)
    )
    study_categories = (
        None
        if recipe.study_categories_path is None
        else _required_h5_object(h5, recipe.study_categories_path)
    )
    label_categories = (
        None
        if recipe.source_label_categories_path is None
        else _required_h5_object(h5, recipe.source_label_categories_path)
    )
    donor_reader = _H5TextReader(
        _required_h5_object(h5, recipe.donor_path),
        length=rows,
        name="donor categories",
        categories_obj=donor_categories,
    )
    study_reader = _H5TextReader(
        _required_h5_object(h5, recipe.study_path),
        length=rows,
        name="study categories",
        categories_obj=study_categories,
    )
    label_reader = _H5TextReader(
        _required_h5_object(h5, recipe.source_label_path),
        length=rows,
        name="source labels",
        categories_obj=label_categories,
    )
    declared_expectations = (
        (donor_reader.declared_categories, donor_crosswalk.source_categories),
        (study_reader.declared_categories, study_crosswalk.source_categories),
        (label_reader.declared_categories, taxonomy.source_labels),
    )
    if any(
        observed is not None and observed != expected
        for observed, expected in declared_expectations
    ):
        raise GbmapExtractionError(
            "GBmap declared category vocabulary differs from its source lock"
        )
    builder = _AggregateBuilder(
        feature_ids=identifiers,
        gene_symbols=symbols,
        source_sha256=source_fingerprint.sha256,
        source_bytes=source_fingerprint.source_bytes,
        taxonomy=taxonomy,
        donor_crosswalk=donor_crosswalk,
        study_crosswalk=study_crosswalk,
        recipe=recipe,
        cancellation=cancellation,
    )
    for row_start in range(0, rows, recipe.row_block_size):
        checkpoint(cancellation)
        row_end = min(rows, row_start + recipe.row_block_size)
        entry_start = int(indptr[row_start])
        entry_end = int(indptr[row_end])
        local_indptr = np.asarray(indptr[row_start : row_end + 1] - entry_start)
        try:
            block = SparseCountBlock(
                row_start=row_start,
                donor_keys=donor_reader.read(row_start, row_end),
                study_keys=study_reader.read(row_start, row_end),
                source_labels=label_reader.read(row_start, row_end),
                indptr=local_indptr,
                indices=np.asarray(indices_dataset[entry_start:entry_end]),
                data=np.asarray(data_dataset[entry_start:entry_end]),
            )
        except ValueError as exc:
            raise GbmapExtractionError(str(exc)) from exc
        builder.ingest(block)
    return builder.finish()


def extract_pinned_gbmap_reference(
    source: Path,
    *,
    lock: ExactGbmapH5adLock,
    taxonomy: GbmapLabelTaxonomy,
    donor_crosswalk: GbmapDonorCrosswalk,
    study_crosswalk: GbmapStudyCrosswalk,
    recipe: GbmapExtractionRecipe,
    cancellation: CancellationContext | None = None,
) -> GbmapExtractionResult:
    """Extract one exact reviewed H5AD through a same-handle, two-pass guard."""

    if not isinstance(source, Path):
        raise GbmapSourceAdmissionError("source must be a pathlib path")
    _require_recipe_source_lock(recipe, lock)
    _require_reviewed_reduction_semantics(
        recipe=recipe,
        taxonomy=taxonomy,
        donor_crosswalk=donor_crosswalk,
        study_crosswalk=study_crosswalk,
    )
    initial_path_stat = _require_regular_source(source)
    h5py = _load_h5py(recipe)
    try:
        with source.open("rb") as handle:
            initial_handle_stat = os.fstat(handle.fileno())
            _require_same_identity(
                initial_path_stat,
                initial_handle_stat,
                "GBmap source changed while it was opened",
            )
            first = _hash_open_handle(handle, cancellation)
            _require_locked_fingerprint(first, lock)
            _require_open_length(first, initial_handle_stat)
            handle.seek(0)
            with h5py.File(handle, "r", driver="fileobj") as h5:
                result = _extract_open_h5ad(
                    h5,
                    source_fingerprint=first,
                    taxonomy=taxonomy,
                    donor_crosswalk=donor_crosswalk,
                    study_crosswalk=study_crosswalk,
                    recipe=recipe,
                    cancellation=cancellation,
                )
            second = _hash_open_handle(handle, cancellation)
            final_handle_stat = os.fstat(handle.fileno())
    except GbmapSourceAdmissionError:
        raise
    except GbmapExtractionError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise GbmapExtractionError("GBmap H5AD extraction failed closed") from exc
    if first != second:
        raise GbmapSourceAdmissionError("GBmap source changed during H5AD extraction")
    if _file_identity(initial_handle_stat) != _file_identity(final_handle_stat):
        raise GbmapSourceAdmissionError("GBmap source identity changed during H5AD extraction")
    final_path_stat = _require_regular_source(source)
    if _file_identity(initial_path_stat) != _file_identity(final_path_stat):
        raise GbmapSourceAdmissionError("GBmap source path changed during H5AD extraction")
    _require_locked_fingerprint(second, lock)
    return result


__all__ = [
    "DEFAULT_ROW_BLOCK_SIZE",
    "EXPECTED_H5PY_VERSION",
    "EXTRACTION_RECIPE_ID",
    "HASH_BLOCK_BYTES",
    "MAX_ROW_BLOCK_SIZE",
    "MIN_ROW_BLOCK_SIZE",
    "PRODUCTION_CELL_COUNT",
    "PRODUCTION_FEATURE_COUNT",
    "PRODUCTION_GROUPED_DONOR_CATEGORY_COUNT",
    "PRODUCTION_GROUPED_STUDY_COUNT",
    "PRODUCTION_SOURCE_DONOR_CATEGORIES",
    "PRODUCTION_SOURCE_DONOR_CATEGORY_COUNT",
    "PRODUCTION_SOURCE_LABELS",
    "PRODUCTION_SOURCE_LABEL_COUNT",
    "PRODUCTION_SOURCE_STUDY_CATEGORIES",
    "PRODUCTION_SOURCE_STUDY_CATEGORY_COUNT",
    "ExactGbmapH5adLock",
    "GbmapDonorCrosswalk",
    "GbmapDonorCrosswalkRule",
    "GbmapExtractionReceipt",
    "GbmapExtractionRecipe",
    "GbmapExtractionResult",
    "GbmapLabelTaxonomy",
    "GbmapStudyCrosswalk",
    "GbmapStudyCrosswalkRule",
    "GbmapTaxonomyRule",
    "SourceFingerprint",
    "SparseCountBlock",
    "aggregate_sparse_count_blocks",
    "extract_pinned_gbmap_reference",
    "fingerprint_gbmap_source",
    "production_donor_crosswalk",
    "production_extraction_recipe",
    "production_label_taxonomy",
    "production_reduction_recipe_digest",
    "production_study_crosswalk",
]
