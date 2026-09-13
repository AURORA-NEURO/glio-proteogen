"""Fail-closed loader for the fitted Reactome participant-transition model."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import zlib
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from typing import Final, Mapping, Never, cast

import numpy as np
from numpy.typing import NDArray

from .errors import ComplexTransitionModelIntegrityError
from .source_catalog import (
    EXPECTED_ARTIFACT_BYTES as SOURCE_ARTIFACT_BYTES,
)
from .source_catalog import (
    EXPECTED_COMPLEX_COUNT,
    EXPECTED_GENE_COUNT,
    ComplexTransitionSourceCatalog,
    complex_transition_source_catalog,
)

FloatArray = NDArray[np.float64]
Float32Array = NDArray[np.float32]
IntArray = NDArray[np.int64]
Int16Array = NDArray[np.int16]

ARTIFACT_RESOURCE: Final = "data/kncc_reactome_complex_transition_model.v1.json"
MODEL_ID: Final = "kncc-reactome-complex-transition-factor-model/1.0.0"
PROFILE_ID: Final = "kncc-reactome-complex-transition/1.0.0"
SCHEMA_VERSION: Final = "glio-proteogen.kncc-reactome-complex-transition-factor-model/1.0.0"
EXPECTED_ARTIFACT_BYTES: Final = 245_014
EXPECTED_ARTIFACT_SHA256: Final = (
    "sha256:f0895efa245ddaaeb324ce3d6c32c8bab9b2abd612a8ad51bd086af97c440676"
)
EXPECTED_CONTENT_DIGEST: Final = (
    "sha256:8465d0c5db70e1cdd3dab08b3646a7c023078c746c96c054bfa3888e8e80e0d2"
)
EXPECTED_TRAINING_RECIPE_DIGEST: Final = (
    "sha256:a9f9ad759e570f63b5dea5c5be738737117a86bea9cd7a046ed75f20735e53bf"
)
EXPECTED_BOOTSTRAP_SEED_NAMESPACE_DIGEST: Final = (
    "sha256:98e49ff6c56de72273f11f89a4f6ce3496becab28c7b3231fc2f9131cadd1758"
)
EXPECTED_SOURCE_CATALOG_BINDING_DIGEST: Final = (
    "sha256:434ea94db1f05f414f21fca5f7aebb38adb802c817c35e80421d65ae8d341eed"
)
EXPECTED_FOLD_POLICY_DIGEST: Final = (
    "sha256:04d750fcd5504510f7831648f0d4f32b7d01e136c2a8778dd90d7a338e46b260"
)
EXPECTED_UNION_FEATURE_DIGEST: Final = (
    "sha256:273801eb7d42ef03eb1ee1b54421898822a1e79448bbc20df81d7ee877f23f31"
)
EXPECTED_COMPLEX_ORDER_DIGEST: Final = (
    "sha256:ee65348ef9688e26f9853053b2c46e469509a7c5b5ac9ea2cd09387af0a8db02"
)
EXPECTED_REFERENCE_LOADING_DIGEST: Final = (
    "sha256:9f9cad8a9b0274eea5ebae6186e4280e69a4c7da743485f43cda2ff1e4420d34"
)
EXPECTED_SOURCE_PROCESSING_ABLATION_DIGEST: Final = (
    "sha256:8894091a0db2def16191b84dc9eef04e57ca3cde63548fc72fe540000eaf58f0"
)
EXPECTED_BOOTSTRAP_ENSEMBLE_DIGEST: Final = (
    "sha256:aca70980b17e60dd84467d87021c92f2917829b69c2fb899099be7972e2ffafb"
)
EXPECTED_EVALUATION_DIGEST: Final = (
    "sha256:6fd16e0ed075f175d8f2e3f4b9587ba7722e82a1d59aea88574d31703be19a30"
)
EXPECTED_UNION_FEATURE_COUNT: Final = 120
EXPECTED_MEMBER_SLOTS: Final = 146
EXPECTED_BOOTSTRAP_REPLICATES: Final = 128
EXPECTED_NUMPY_VERSION: Final = "2.5.2"


@dataclass(frozen=True, slots=True)
class ComplexOuterEvaluation:
    evaluation_count: int
    model_standardized_mae: float
    model_standardized_rmse: float
    training_center_standardized_mae: float
    training_center_standardized_rmse: float
    zero_transition_standardized_mae: float
    zero_transition_standardized_rmse: float
    relative_mae_gain_vs_training_center: float
    relative_mae_gain_vs_zero_transition: float
    direction_accuracy: float
    direction_evaluation_count: int
    minimum_loading_cosine: float
    median_loading_cosine: float


@dataclass(frozen=True, slots=True)
class FittedComplexModel:
    complex_index: int
    domain_id: str
    reactome_id: str
    name: str
    member_feature_indices: tuple[int, ...]
    member_slot_offset: int
    member_slot_count: int
    member_centers: FloatArray
    member_scales: FloatArray
    member_reliabilities: FloatArray
    member_support: Int16Array
    member_loadings: FloatArray
    source_processing_centers: FloatArray
    source_processing_scales: FloatArray
    source_processing_reliabilities: FloatArray
    source_processing_loadings: FloatArray
    source_processing_loading_cosine: float
    convergence: Mapping[str, object]
    source_processing_convergence: Mapping[str, object]
    evaluation: ComplexOuterEvaluation


@dataclass(frozen=True, slots=True)
class ComplexBootstrapDraw:
    index: int
    member_scales: Float32Array
    member_loadings: Float32Array
    row_digest: str


@dataclass(frozen=True, slots=True)
class ComplexTransitionFittedCatalog:
    profile_id: str
    model_id: str
    source_catalog: ComplexTransitionSourceCatalog
    union_feature_indices: tuple[int, ...]
    union_gene_symbols: tuple[str, ...]
    complexes: tuple[FittedComplexModel, ...]
    bootstrap_member_scales: Float32Array
    bootstrap_member_loadings: Float32Array
    bootstrap_row_digests: tuple[str, ...]
    evaluation: Mapping[str, object]
    training_recipe: Mapping[str, object]
    fold_policy: Mapping[str, object]
    limitations: tuple[str, ...]
    artifact_bytes: int
    artifact_byte_digest: str
    content_digest: str
    training_recipe_digest: str
    bootstrap_seed_namespace_digest: str
    source_catalog_binding_digest: str
    fold_policy_digest: str
    union_feature_digest: str
    complex_order_digest: str
    reference_loading_digest: str
    source_processing_ablation_digest: str
    bootstrap_ensemble_digest: str
    evaluation_digest: str
    numpy_version: str

    @property
    def bootstrap_replicate_count(self) -> int:
        return int(self.bootstrap_member_scales.shape[0])

    @property
    def member_slot_count(self) -> int:
        return int(self.bootstrap_member_scales.shape[1])

    def bootstrap_draw(self, index: int) -> ComplexBootstrapDraw:
        if not 0 <= index < self.bootstrap_replicate_count:
            raise IndexError("complex bootstrap draw index is out of range")
        return ComplexBootstrapDraw(
            index=index,
            member_scales=_readonly(self.bootstrap_member_scales[index]),
            member_loadings=_readonly(self.bootstrap_member_loadings[index]),
            row_digest=self.bootstrap_row_digests[index],
        )

    def bootstrap_complex_parameters(
        self,
        replicate: int,
        complex_index: int,
    ) -> tuple[FloatArray, FloatArray]:
        if not 0 <= complex_index < len(self.complexes):
            raise IndexError("fitted complex index is out of range")
        draw = self.bootstrap_draw(replicate)
        item = self.complexes[complex_index]
        start = item.member_slot_offset
        stop = start + item.member_slot_count
        return (
            _readonly(np.asarray(draw.member_scales[start:stop], dtype=np.float64)),
            _readonly(np.asarray(draw.member_loadings[start:stop], dtype=np.float64)),
        )


def _fail(message: str) -> Never:
    raise ComplexTransitionModelIntegrityError(message)


def _resource_bytes() -> bytes:
    return files(__package__).joinpath(ARTIFACT_RESOURCE).read_bytes()


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _raw_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("fitted complex artifact contains a duplicate JSON key")
        result[key] = value
    return result


def _object(value: object, name: str) -> dict[str, object]:
    if type(value) is not dict:
        _fail(f"fitted complex field {name!r} must be an object")
    return cast("dict[str, object]", value)


def _array(value: object, name: str) -> list[object]:
    if type(value) is not list:
        _fail(f"fitted complex field {name!r} must be an array")
    return cast("list[object]", value)


def _string(value: object, name: str) -> str:
    if type(value) is not str:
        _fail(f"fitted complex field {name!r} must be a string")
    return value


def _integer(value: object, name: str) -> int:
    if type(value) is not int:
        _fail(f"fitted complex field {name!r} must be an integer")
    return value


def _number(value: object, name: str) -> float:
    if type(value) not in {int, float}:
        _fail(f"fitted complex field {name!r} must be numeric")
    result = float(cast("int | float", value))
    if not math.isfinite(result):
        _fail(f"fitted complex field {name!r} must be finite")
    return result


def _bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        _fail(f"fitted complex field {name!r} must be boolean")
    return value


def _readonly[T: np.generic](value: NDArray[T]) -> NDArray[T]:
    result = np.ascontiguousarray(value)
    result.flags.writeable = False
    return result


def _float_array(value: object, name: str, size: int) -> FloatArray:
    values = _array(value, name)
    if len(values) != size:
        _fail(f"fitted complex field {name!r} has the wrong length")
    result = np.asarray([_number(item, name) for item in values], dtype=np.float64)
    if not np.all(np.isfinite(result)):
        _fail(f"fitted complex field {name!r} contains non-finite values")
    return _readonly(result)


def _int_array(value: object, name: str, size: int) -> tuple[int, ...]:
    values = tuple(_integer(item, name) for item in _array(value, name))
    if len(values) != size:
        _fail(f"fitted complex field {name!r} has the wrong length")
    return values


def _decode_tensor(
    value: object,
    name: str,
    expected_shape: tuple[int, int],
) -> Float32Array:
    tensor = _object(value, name)
    shape = tuple(
        _integer(item, f"{name}.shape") for item in _array(tensor.get("shape"), f"{name}.shape")
    )
    if (
        tensor.get("dtype") != "<f4"
        or tensor.get("encoding") != "base64+zlib"
        or shape != expected_shape
    ):
        _fail(f"fitted complex tensor {name!r} metadata mismatch")
    try:
        compressed = base64.b64decode(_string(tensor.get("data"), f"{name}.data"), validate=True)
        payload = zlib.decompress(compressed)
    except (ValueError, zlib.error) as error:
        raise ComplexTransitionModelIntegrityError(
            f"fitted complex tensor {name!r} cannot be decoded"
        ) from error
    expected_bytes = math.prod(expected_shape) * np.dtype("<f4").itemsize
    if (
        len(payload) != expected_bytes
        or tensor.get("raw_bytes") != expected_bytes
        or tensor.get("raw_sha256") != _raw_digest(payload)
    ):
        _fail(f"fitted complex tensor {name!r} payload mismatch")
    result = np.frombuffer(payload, dtype="<f4").reshape(expected_shape).copy()
    if not np.all(np.isfinite(result)):
        _fail(f"fitted complex tensor {name!r} contains non-finite values")
    return _readonly(result)


def _parse_outer_evaluation(value: object, name: str) -> ComplexOuterEvaluation:
    item = _object(value, name)
    return ComplexOuterEvaluation(
        evaluation_count=_integer(item.get("evaluation_count"), f"{name}.count"),
        model_standardized_mae=_number(item.get("model_standardized_mae"), f"{name}.model_mae"),
        model_standardized_rmse=_number(item.get("model_standardized_rmse"), f"{name}.model_rmse"),
        training_center_standardized_mae=_number(
            item.get("training_center_standardized_mae"), f"{name}.center_mae"
        ),
        training_center_standardized_rmse=_number(
            item.get("training_center_standardized_rmse"), f"{name}.center_rmse"
        ),
        zero_transition_standardized_mae=_number(
            item.get("zero_transition_standardized_mae"), f"{name}.zero_mae"
        ),
        zero_transition_standardized_rmse=_number(
            item.get("zero_transition_standardized_rmse"), f"{name}.zero_rmse"
        ),
        relative_mae_gain_vs_training_center=_number(
            item.get("relative_mae_gain_vs_training_center"), f"{name}.center_gain"
        ),
        relative_mae_gain_vs_zero_transition=_number(
            item.get("relative_mae_gain_vs_zero_transition"), f"{name}.zero_gain"
        ),
        direction_accuracy=_number(item.get("direction_accuracy"), f"{name}.direction"),
        direction_evaluation_count=_integer(
            item.get("direction_evaluation_count"), f"{name}.direction_count"
        ),
        minimum_loading_cosine=_number(
            item.get("minimum_loading_cosine"), f"{name}.minimum_cosine"
        ),
        median_loading_cosine=_number(item.get("median_loading_cosine"), f"{name}.median_cosine"),
    )


def _parse_complexes(
    values: object,
    source: ComplexTransitionSourceCatalog,
) -> tuple[FittedComplexModel, ...]:
    raw = _array(values, "complexes")
    if len(raw) != EXPECTED_COMPLEX_COUNT:
        _fail("fitted complex count mismatch")
    result: list[FittedComplexModel] = []
    expected_offset = 0
    for index, (raw_item, source_item) in enumerate(zip(raw, source.complexes, strict=True)):
        item = _object(raw_item, f"complexes[{index}]")
        count = _integer(item.get("member_slot_count"), f"complexes[{index}].slot_count")
        offset = _integer(item.get("member_slot_offset"), f"complexes[{index}].slot_offset")
        members = _int_array(
            item.get("member_feature_indices"),
            f"complexes[{index}].members",
            count,
        )
        if (
            item.get("complex_index") != index
            or item.get("domain_id") != source_item.domain_id
            or item.get("reactome_id") != source_item.reactome_id
            or item.get("name") != source_item.name
            or members != source_item.eligible_feature_indices
            or offset != expected_offset
            or count < 3
        ):
            _fail("fitted complex identity, membership, or slot mismatch")
        reference = _object(item.get("reference"), f"complexes[{index}].reference")
        scales = _float_array(reference.get("member_scales"), f"complexes[{index}].scales", count)
        reliability = _float_array(
            reference.get("member_reliabilities"),
            f"complexes[{index}].reliabilities",
            count,
        )
        loading = _float_array(
            reference.get("member_loadings"), f"complexes[{index}].loadings", count
        )
        support_values = _int_array(
            reference.get("member_support"), f"complexes[{index}].support", count
        )
        normalization = _object(
            reference.get("coordinate_normalization"),
            f"complexes[{index}].normalization",
        )
        convergence = _object(reference.get("convergence"), f"complexes[{index}].convergence")
        if (
            np.any(scales <= 0.0)
            or np.any(reliability <= 0.0)
            or np.any(reliability > 1.0)
            or not math.isclose(float(np.linalg.norm(loading)), 1.0, abs_tol=2e-9)
            or any(not 1 <= value <= 104 for value in support_values)
            or normalization.get("standardization_center_subtracted") is not False
            or not math.isclose(
                _number(normalization.get("loading_l2_norm"), "loading norm"),
                1.0,
                abs_tol=1e-12,
            )
            or convergence.get("converged") is not True
            or convergence.get("objective_monotone") is not True
        ):
            _fail("fitted complex reference numerical domain mismatch")
        ablation = _object(
            item.get("source_processing_ablation"),
            f"complexes[{index}].source_processing",
        )
        ablation_scales = _float_array(
            ablation.get("member_scales"), f"complexes[{index}].ablation_scales", count
        )
        ablation_reliability = _float_array(
            ablation.get("member_reliabilities"),
            f"complexes[{index}].ablation_reliabilities",
            count,
        )
        ablation_loading = _float_array(
            ablation.get("member_loadings"),
            f"complexes[{index}].ablation_loadings",
            count,
        )
        if (
            ablation.get("measure") != "Log"
            or ablation.get("converged") is not True
            or np.any(ablation_scales <= 0.0)
            or np.any(ablation_reliability <= 0.0)
            or np.any(ablation_reliability > 1.0)
            or not math.isclose(float(np.linalg.norm(ablation_loading)), 1.0, abs_tol=2e-9)
        ):
            _fail("fitted source-processing ablation mismatch")
        result.append(
            FittedComplexModel(
                complex_index=index,
                domain_id=source_item.domain_id,
                reactome_id=source_item.reactome_id,
                name=source_item.name,
                member_feature_indices=members,
                member_slot_offset=offset,
                member_slot_count=count,
                member_centers=_float_array(
                    reference.get("member_centers"), f"complexes[{index}].centers", count
                ),
                member_scales=scales,
                member_reliabilities=reliability,
                member_support=_readonly(np.asarray(support_values, dtype=np.int16)),
                member_loadings=loading,
                source_processing_centers=_float_array(
                    ablation.get("member_centers"),
                    f"complexes[{index}].ablation_centers",
                    count,
                ),
                source_processing_scales=ablation_scales,
                source_processing_reliabilities=ablation_reliability,
                source_processing_loadings=ablation_loading,
                source_processing_loading_cosine=_number(
                    ablation.get("loading_cosine_to_primary"),
                    f"complexes[{index}].ablation_cosine",
                ),
                convergence=MappingProxyType(convergence),
                source_processing_convergence=MappingProxyType(ablation),
                evaluation=_parse_outer_evaluation(
                    item.get("outer_fold_held_member_evaluation"),
                    f"complexes[{index}].evaluation",
                ),
            )
        )
        expected_offset += count
    if expected_offset != EXPECTED_MEMBER_SLOTS:
        _fail("fitted complex member-slot total mismatch")
    return tuple(result)


def _validate_bindings_and_digests(
    document: dict[str, object],
    source: ComplexTransitionSourceCatalog,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    source_binding = _object(document.get("source_catalog_binding"), "source binding")
    expected_binding = {
        "artifact_bytes": SOURCE_ARTIFACT_BYTES,
        "artifact_byte_digest": source.artifact_byte_digest,
        "content_digest": source.content_digest,
        "profile_id": source.profile_id,
        "projection_digests": {
            "complex_membership_digest": source.complex_membership_digest,
            "complex_order_digest": source.complex_order_digest,
            "overlap_control_digest": source.overlap_control_digest,
            "pathway_binding_digest": source.pathway_binding_digest,
            "selection_digest": source.selection_digest,
            "source_binding_digest": source.source_binding_digest,
        },
    }
    recipe = _object(document.get("training_recipe"), "training recipe")
    folds = _object(document.get("fold_policy"), "fold policy")
    evaluation = _object(document.get("evaluation"), "evaluation")
    digests = _object(document.get("digests"), "digests")
    expected_digests = {
        "training_recipe_digest": EXPECTED_TRAINING_RECIPE_DIGEST,
        "bootstrap_seed_namespace_digest": EXPECTED_BOOTSTRAP_SEED_NAMESPACE_DIGEST,
        "source_catalog_binding_digest": EXPECTED_SOURCE_CATALOG_BINDING_DIGEST,
        "fold_policy_digest": EXPECTED_FOLD_POLICY_DIGEST,
        "union_feature_digest": EXPECTED_UNION_FEATURE_DIGEST,
        "complex_order_digest": EXPECTED_COMPLEX_ORDER_DIGEST,
        "reference_loading_digest": EXPECTED_REFERENCE_LOADING_DIGEST,
        "source_processing_ablation_digest": EXPECTED_SOURCE_PROCESSING_ABLATION_DIGEST,
        "bootstrap_ensemble_digest": EXPECTED_BOOTSTRAP_ENSEMBLE_DIGEST,
        "evaluation_digest": EXPECTED_EVALUATION_DIGEST,
    }
    if (
        source_binding != expected_binding
        or _digest(source_binding) != EXPECTED_SOURCE_CATALOG_BINDING_DIGEST
        or _digest(recipe) != EXPECTED_TRAINING_RECIPE_DIGEST
        or _digest(folds) != EXPECTED_FOLD_POLICY_DIGEST
        or _digest(evaluation) != EXPECTED_EVALUATION_DIGEST
        or digests != expected_digests
    ):
        _fail("fitted complex source, recipe, fold, evaluation, or digest binding mismatch")
    return recipe, folds, evaluation


def _validate_bootstrap(
    document: dict[str, object],
    complexes: tuple[FittedComplexModel, ...],
) -> tuple[Float32Array, Float32Array, tuple[str, ...]]:
    bootstrap = _object(document.get("bootstrap"), "bootstrap")
    tensors = _object(bootstrap.get("tensors"), "bootstrap.tensors")
    shape = (EXPECTED_BOOTSTRAP_REPLICATES, EXPECTED_MEMBER_SLOTS)
    scales = _decode_tensor(tensors.get("member_scale"), "bootstrap.member_scale", shape)
    loadings = _decode_tensor(tensors.get("member_loading"), "bootstrap.member_loading", shape)
    rows = tuple(
        _string(value, "bootstrap.row_digest")
        for value in _array(bootstrap.get("row_digests"), "bootstrap.row_digests")
    )
    if (
        bootstrap.get("replicates") != EXPECTED_BOOTSTRAP_REPLICATES
        or bootstrap.get("seed_namespace_digest")
        != EXPECTED_BOOTSTRAP_SEED_NAMESPACE_DIGEST
        or len(rows) != EXPECTED_BOOTSTRAP_REPLICATES
        or np.any(scales <= 0.0)
    ):
        _fail("fitted complex bootstrap domain mismatch")
    for replicate, expected in enumerate(rows):
        payload = np.ascontiguousarray(
            np.concatenate((scales[replicate], loadings[replicate])), dtype="<f4"
        ).tobytes()
        if _raw_digest(payload) != expected:
            _fail("fitted complex bootstrap row digest mismatch")
        for item in complexes:
            start = item.member_slot_offset
            stop = start + item.member_slot_count
            if not math.isclose(
                float(np.linalg.norm(loadings[replicate, start:stop])),
                1.0,
                abs_tol=2e-6,
            ):
                _fail("fitted complex bootstrap loading norm mismatch")
    if (
        _digest({"tensors": tensors, "row_digests": list(rows)})
        != EXPECTED_BOOTSTRAP_ENSEMBLE_DIGEST
    ):
        _fail("fitted complex bootstrap ensemble digest mismatch")
    return scales, loadings, rows


@lru_cache(maxsize=1)
def complex_transition_fitted_catalog() -> ComplexTransitionFittedCatalog:
    """Load and fully validate the fitted aggregate model once per process."""

    payload = _resource_bytes()
    byte_digest = _raw_digest(payload)
    if len(payload) != EXPECTED_ARTIFACT_BYTES or byte_digest != EXPECTED_ARTIFACT_SHA256:
        _fail("fitted complex artifact byte lock mismatch")
    try:
        document = json.loads(payload, object_pairs_hook=_reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ComplexTransitionModelIntegrityError(
            "fitted complex artifact is not strict UTF-8 JSON"
        ) from error
    root = _object(document, "root")
    content = dict(root)
    declared_digest = content.pop("artifact_digest", None)
    if declared_digest != EXPECTED_CONTENT_DIGEST or _digest(content) != EXPECTED_CONTENT_DIGEST:
        _fail("fitted complex artifact content digest mismatch")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("profile_id") != PROFILE_ID
        or root.get("model_id") != MODEL_ID
    ):
        _fail("fitted complex artifact identity mismatch")
    source = complex_transition_source_catalog()
    recipe, folds, evaluation = _validate_bindings_and_digests(root, source)
    counts = _object(root.get("counts"), "counts")
    if counts != {
        "bootstrap_replicates": EXPECTED_BOOTSTRAP_REPLICATES,
        "complexes": EXPECTED_COMPLEX_COUNT,
        "member_slots": EXPECTED_MEMBER_SLOTS,
        "source_gene_features": EXPECTED_GENE_COUNT,
        "source_paired_groups": 104,
        "union_features": EXPECTED_UNION_FEATURE_COUNT,
    }:
        _fail("fitted complex artifact count mismatch")
    union = _int_array(
        root.get("union_feature_indices"),
        "union_feature_indices",
        EXPECTED_UNION_FEATURE_COUNT,
    )
    expected_union = tuple(
        sorted({value for item in source.complexes for value in item.eligible_feature_indices})
    )
    if union != expected_union or _digest(list(union)) != EXPECTED_UNION_FEATURE_DIGEST:
        _fail("fitted complex union feature axis mismatch")
    complexes = _parse_complexes(root.get("complexes"), source)
    raw_complexes = _array(root.get("complexes"), "complexes")
    if (
        _digest([_object(item, "complex").get("reference") for item in raw_complexes])
        != EXPECTED_REFERENCE_LOADING_DIGEST
        or _digest(
            [_object(item, "complex").get("source_processing_ablation") for item in raw_complexes]
        )
        != EXPECTED_SOURCE_PROCESSING_ABLATION_DIGEST
    ):
        _fail("fitted complex reference or ablation digest mismatch")
    bootstrap_scales, bootstrap_loadings, row_digests = _validate_bootstrap(root, complexes)
    provenance = _object(root.get("provenance"), "provenance")
    privacy = _object(root.get("privacy"), "privacy")
    claim = _object(root.get("claim_boundary"), "claim boundary")
    if (
        provenance.get("study_id") != "PDC000514"
        or provenance.get("numpy_version") != EXPECTED_NUMPY_VERSION
        or any(value is not False for value in privacy.values())
        or claim.get("supported_claim")
        != "source-cohort complex-member protein-transition concordance"
    ):
        _fail("fitted complex provenance, privacy, or claim boundary mismatch")
    limitations = tuple(
        _string(value, "limitation") for value in _array(root.get("limitations"), "limitations")
    )
    if not limitations:
        _fail("fitted complex artifact must expose limitations")
    return ComplexTransitionFittedCatalog(
        profile_id=PROFILE_ID,
        model_id=MODEL_ID,
        source_catalog=source,
        union_feature_indices=union,
        union_gene_symbols=tuple(source.genes[index] for index in union),
        complexes=complexes,
        bootstrap_member_scales=bootstrap_scales,
        bootstrap_member_loadings=bootstrap_loadings,
        bootstrap_row_digests=row_digests,
        evaluation=MappingProxyType(evaluation),
        training_recipe=MappingProxyType(recipe),
        fold_policy=MappingProxyType(folds),
        limitations=limitations,
        artifact_bytes=len(payload),
        artifact_byte_digest=byte_digest,
        content_digest=EXPECTED_CONTENT_DIGEST,
        training_recipe_digest=EXPECTED_TRAINING_RECIPE_DIGEST,
        bootstrap_seed_namespace_digest=EXPECTED_BOOTSTRAP_SEED_NAMESPACE_DIGEST,
        source_catalog_binding_digest=EXPECTED_SOURCE_CATALOG_BINDING_DIGEST,
        fold_policy_digest=EXPECTED_FOLD_POLICY_DIGEST,
        union_feature_digest=EXPECTED_UNION_FEATURE_DIGEST,
        complex_order_digest=EXPECTED_COMPLEX_ORDER_DIGEST,
        reference_loading_digest=EXPECTED_REFERENCE_LOADING_DIGEST,
        source_processing_ablation_digest=EXPECTED_SOURCE_PROCESSING_ABLATION_DIGEST,
        bootstrap_ensemble_digest=EXPECTED_BOOTSTRAP_ENSEMBLE_DIGEST,
        evaluation_digest=EXPECTED_EVALUATION_DIGEST,
        numpy_version=EXPECTED_NUMPY_VERSION,
    )


__all__ = [
    "ARTIFACT_RESOURCE",
    "EXPECTED_ARTIFACT_BYTES",
    "EXPECTED_ARTIFACT_SHA256",
    "EXPECTED_BOOTSTRAP_ENSEMBLE_DIGEST",
    "EXPECTED_BOOTSTRAP_REPLICATES",
    "EXPECTED_BOOTSTRAP_SEED_NAMESPACE_DIGEST",
    "EXPECTED_CONTENT_DIGEST",
    "EXPECTED_EVALUATION_DIGEST",
    "EXPECTED_FOLD_POLICY_DIGEST",
    "EXPECTED_MEMBER_SLOTS",
    "EXPECTED_NUMPY_VERSION",
    "EXPECTED_REFERENCE_LOADING_DIGEST",
    "EXPECTED_SOURCE_CATALOG_BINDING_DIGEST",
    "EXPECTED_SOURCE_PROCESSING_ABLATION_DIGEST",
    "EXPECTED_TRAINING_RECIPE_DIGEST",
    "EXPECTED_UNION_FEATURE_COUNT",
    "EXPECTED_UNION_FEATURE_DIGEST",
    "MODEL_ID",
    "PROFILE_ID",
    "SCHEMA_VERSION",
    "ComplexBootstrapDraw",
    "ComplexOuterEvaluation",
    "ComplexTransitionFittedCatalog",
    "FittedComplexModel",
    "complex_transition_fitted_catalog",
]
