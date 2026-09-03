"""Exact NumPy evaluator for selected published GBM proteomic XGBoost models.

The authors' legacy XGBoost ensembles contain only constant trees and depth-one
stumps.  The bundled artifact stores those leaves in training order so NumPy
``float32`` accumulation reproduces XGBoost 1.4.2 without importing xgboost.

This code intentionally preserves the published missing-feature convention:
model features absent from an input sample are filled with zero.  Coverage is
reported explicitly so callers can abstain instead of treating that convention
as evidence of biological absence.

The scores are research-only bulk-tissue signature activations.  They are not
diagnoses, cell fractions, patient subtype assignments, or treatment guidance.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from typing import cast

import numpy as np

SOURCE_REPOSITORY_URL = "https://github.com/diamandis-lab/paper-prot-atlas-gbm"
SOURCE_COMMIT = "8d8c5725a82ef9505562e25fe2c5ea19fe608195"
MODEL_SOURCE_SHA256 = "56aee53d2b247bb5dbaec7f876c0574ac0f89eccd98eade8f9437e1f1684a76c"
ARTIFACT_SHA256 = "2cd772b24a34c8f4fda56d932f40930f312750915c49695caad0e50dd9a5309d"
ORACLE_FIXTURE_SHA256 = "ac5d185b2645c51dafbde8dd2daebd567a7d05c607c45d8e152900b4949ba475"
MODEL_FEATURE_COUNT = 3_025
TREES_PER_SIGNATURE = 600
GEOMETRIC_MEAN_TARGET = 1.0e7
PUBLISHED_OUTPUT_OFFSET = 10.0
PUBLISHED_DECIMAL_PLACES = 4

SUPPORTED_SIGNATURES = (
    "SWEET_KRAS_TARGETS_UP",
    "HALLMARK_MYC_TARGETS_V1",
    "WINTER_HYPOXIA_UP",
    "VERHAAK_GLIOBLASTOMA_MESENCHYMAL",
    "VERHAAK_GLIOBLASTOMA_NEURAL",
    "VERHAAK_GLIOBLASTOMA_PRONEURAL",
    "EGFR_UP.V1_UP",
)

_ARTIFACT_NAME = "diamandis_gbm_proteomic_axes_v1.json"
_ARTIFACT_SCHEMA = "glio-gbm-proteomic-axes-artifact/1.0.0"
_FLOAT32_MAX = float(np.finfo(np.float32).max)


class ModelArtifactError(RuntimeError):
    """The pinned converted model artifact failed integrity validation."""


class PredictionInputError(ValueError):
    """An LFQ sample or signature selection violates predictor preconditions."""


@dataclass(frozen=True, slots=True)
class SignatureModel:
    """One immutable ordered ensemble decoded from the upstream model."""

    signature_name: str
    base_score: float
    output_offset: float
    split_feature: tuple[int, ...]
    split_condition: tuple[float, ...]
    yes_leaf: tuple[float, ...]
    no_leaf: tuple[float, ...]
    missing_leaf: tuple[float, ...]
    source_r_raw_sha256: str
    source_xgboost_binary_sha256: str


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    """Validated in-memory representation of the bundled model artifact."""

    schema_version: str
    source_repository: str
    source_commit: str
    feature_names: tuple[str, ...]
    feature_index: Mapping[str, int]
    models: Mapping[str, SignatureModel]


@dataclass(frozen=True, slots=True)
class SignatureModelMetadata:
    """Small catalog record suitable for profiles and API metadata."""

    signature_name: str
    feature_count: int
    tree_count: int
    split_tree_count: int
    constant_tree_count: int
    source_r_raw_sha256: str
    source_xgboost_binary_sha256: str


@dataclass(frozen=True, slots=True)
class SignaturePrediction:
    """A published score plus unrounded values and selected path-leaf sums.

    ``contributions`` groups the leaves selected from split stumps by the
    feature used at each root.  They are deterministic audit explanations, not
    SHAP values, causal importance, or an independently calibrated attribution.
    """

    signature_name: str
    score: float
    unrounded_score: float
    raw_margin: float
    intercept: float
    contributions: Mapping[str, float]
    model_feature_count: int
    observed_feature_count: int
    missing_feature_count: int
    missing_feature_ratio: float


@dataclass(frozen=True, slots=True)
class PredictionResult:
    """Predictions from one LFQ sample after the authors' normalization."""

    geometric_mean: float
    normalization_factor: float
    input_protein_count: int
    positive_protein_count: int
    signatures: Mapping[str, SignaturePrediction]


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _as_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ModelArtifactError(f"invalid bundled model artifact: {label} must be an object")
    return cast("dict[str, object]", value)


def _as_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ModelArtifactError(f"invalid bundled model artifact: {label} must be a string")
    return value


def _as_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelArtifactError(f"invalid bundled model artifact: {label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ModelArtifactError(f"invalid bundled model artifact: {label} must be finite")
    return number


def _as_float_tuple(value: object, label: str) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise ModelArtifactError(f"invalid bundled model artifact: {label} must be an array")
    return tuple(_as_float(item, label) for item in value)


def _as_index_tuple(value: object, label: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ModelArtifactError(f"invalid bundled model artifact: {label} must be an array")
    indices: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ModelArtifactError(
                f"invalid bundled model artifact: {label} must contain integers"
            )
        indices.append(item)
    return tuple(indices)


def _parse_model(signature_name: str, value: object) -> SignatureModel:
    model = _as_mapping(value, f"model {signature_name}")
    split_feature = _as_index_tuple(model.get("split_feature"), "split_feature")
    split_condition = _as_float_tuple(model.get("split_condition"), "split_condition")
    yes_leaf = _as_float_tuple(model.get("yes_leaf"), "yes_leaf")
    no_leaf = _as_float_tuple(model.get("no_leaf"), "no_leaf")
    missing_leaf = _as_float_tuple(model.get("missing_leaf"), "missing_leaf")
    lengths = {
        len(split_feature),
        len(split_condition),
        len(yes_leaf),
        len(no_leaf),
        len(missing_leaf),
    }
    if lengths != {TREES_PER_SIGNATURE}:
        raise ModelArtifactError(
            f"invalid bundled model artifact: {signature_name} tree arrays differ"
        )
    if any(index < -1 or index >= MODEL_FEATURE_COUNT for index in split_feature):
        raise ModelArtifactError(
            f"invalid bundled model artifact: {signature_name} feature index"
        )
    if any(
        index == -1 and not (yes == no == missing)
        for index, yes, no, missing in zip(
            split_feature,
            yes_leaf,
            no_leaf,
            missing_leaf,
            strict=True,
        )
    ):
        raise ModelArtifactError(
            f"invalid bundled model artifact: {signature_name} constant tree"
        )
    return SignatureModel(
        signature_name=signature_name,
        base_score=_as_float(model.get("base_score"), "base_score"),
        output_offset=_as_float(model.get("output_offset"), "output_offset"),
        split_feature=split_feature,
        split_condition=split_condition,
        yes_leaf=yes_leaf,
        no_leaf=no_leaf,
        missing_leaf=missing_leaf,
        source_r_raw_sha256=_as_string(
            model.get("source_r_raw_sha256"), "source_r_raw_sha256"
        ),
        source_xgboost_binary_sha256=_as_string(
            model.get("source_xgboost_binary_sha256"), "source_xgboost_binary_sha256"
        ),
    )


@lru_cache(maxsize=1)
def load_artifact() -> ModelArtifact:
    """Load and fully validate the pinned model artifact once per process."""

    raw = files(__package__).joinpath(_ARTIFACT_NAME).read_bytes()
    actual_digest = _digest(raw)
    if actual_digest != ARTIFACT_SHA256:
        raise ModelArtifactError(
            f"bundled GBM model artifact digest mismatch: {actual_digest} != {ARTIFACT_SHA256}"
        )
    document = _as_mapping(json.loads(raw), "root")
    schema_version = _as_string(document.get("schema_version"), "schema_version")
    if schema_version != _ARTIFACT_SCHEMA:
        raise ModelArtifactError("unsupported bundled GBM model artifact schema")
    source = _as_mapping(document.get("source"), "source")
    repository = _as_string(source.get("repository"), "source.repository")
    commit = _as_string(source.get("commit"), "source.commit")
    if repository != SOURCE_REPOSITORY_URL or commit != SOURCE_COMMIT:
        raise ModelArtifactError("bundled GBM model artifact source binding mismatch")
    source_files = _as_mapping(source.get("files"), "source.files")
    protein_models = _as_mapping(source_files.get("protein_models"), "source protein model")
    if _as_string(protein_models.get("sha256"), "protein model digest") != MODEL_SOURCE_SHA256:
        raise ModelArtifactError("bundled GBM model artifact RData digest mismatch")

    feature_value = document.get("feature_names")
    if not isinstance(feature_value, list) or not all(
        isinstance(feature, str) for feature in feature_value
    ):
        raise ModelArtifactError("invalid bundled model artifact: feature_names")
    feature_names = tuple(cast("list[str]", feature_value))
    if (
        len(feature_names) != MODEL_FEATURE_COUNT
        or feature_names != tuple(sorted(feature_names))
        or len(set(feature_names)) != MODEL_FEATURE_COUNT
    ):
        raise ModelArtifactError("invalid bundled model artifact: feature universe")

    model_values = _as_mapping(document.get("models"), "models")
    if set(model_values) != set(SUPPORTED_SIGNATURES):
        raise ModelArtifactError("invalid bundled model artifact: supported signature set")
    parsed_models = {
        signature_name: _parse_model(signature_name, model_values[signature_name])
        for signature_name in SUPPORTED_SIGNATURES
    }
    return ModelArtifact(
        schema_version=schema_version,
        source_repository=repository,
        source_commit=commit,
        feature_names=feature_names,
        feature_index=MappingProxyType(
            {feature_name: index for index, feature_name in enumerate(feature_names)}
        ),
        models=MappingProxyType(parsed_models),
    )


def model_catalog() -> tuple[SignatureModelMetadata, ...]:
    """Return deterministic provenance and shape metadata for all selected models."""

    artifact = load_artifact()
    return tuple(
        SignatureModelMetadata(
            signature_name=name,
            feature_count=len(artifact.feature_names),
            tree_count=len(model.split_feature),
            split_tree_count=sum(index != -1 for index in model.split_feature),
            constant_tree_count=sum(index == -1 for index in model.split_feature),
            source_r_raw_sha256=model.source_r_raw_sha256,
            source_xgboost_binary_sha256=model.source_xgboost_binary_sha256,
        )
        for name in SUPPORTED_SIGNATURES
        for model in (artifact.models[name],)
    )


def feature_names(signature_name: str) -> tuple[str, ...]:
    """Return the exact ordered feature universe for a selected signature."""

    artifact = load_artifact()
    if signature_name not in artifact.models:
        raise PredictionInputError(f"unsupported GBM proteomic signature: {signature_name}")
    return artifact.feature_names


def _validated_abundances(abundances: Mapping[str, float]) -> dict[str, float]:
    if not abundances:
        raise PredictionInputError("at least one protein abundance is required")
    validated: dict[str, float] = {}
    for protein, raw_value in abundances.items():
        if not isinstance(protein, str) or not protein or protein != protein.strip():
            raise PredictionInputError("protein identifiers must be non-empty exact strings")
        if isinstance(raw_value, bool):
            raise PredictionInputError(f"protein abundance for {protein} must be numeric")
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as error:
            raise PredictionInputError(
                f"protein abundance for {protein} must be numeric"
            ) from error
        if not math.isfinite(value):
            raise PredictionInputError(f"protein abundance for {protein} must be finite")
        if value < 0.0:
            raise PredictionInputError(f"protein abundance for {protein} must be nonnegative")
        validated[protein] = value
    return validated


def scale_positive_lfq(
    abundances: Mapping[str, float],
) -> tuple[dict[str, float], float, float]:
    """Apply the authors' positive-LFQ geometric-mean normalization.

    Every positive input protein participates, including proteins outside the
    3,025-model feature universe.  Zeros are retained but excluded from the
    geometric mean, exactly matching ``predictXGB.R``.
    """

    validated = _validated_abundances(abundances)
    positive = [value for value in validated.values() if value > 0.0]
    if not positive:
        raise PredictionInputError("at least one positive protein abundance is required")
    mean_log = math.fsum(math.log(value) for value in positive) / len(positive)
    geometric_mean = math.exp(mean_log)
    try:
        normalization_factor = math.exp(math.log(GEOMETRIC_MEAN_TARGET) - mean_log)
    except OverflowError as error:
        raise PredictionInputError(
            "protein abundance scale is outside the supported numeric range"
        ) from error
    if not math.isfinite(geometric_mean) or not math.isfinite(normalization_factor):
        raise PredictionInputError("protein abundance scale is outside the supported numeric range")
    scaled = {protein: value * normalization_factor for protein, value in validated.items()}
    if not all(math.isfinite(value) for value in scaled.values()):
        raise PredictionInputError(
            "normalized protein abundance is outside the supported numeric range"
        )
    return scaled, geometric_mean, normalization_factor


def _selected_signatures(signature_names: Iterable[str] | None) -> tuple[str, ...]:
    selected = SUPPORTED_SIGNATURES if signature_names is None else tuple(signature_names)
    if not selected:
        raise PredictionInputError("at least one GBM proteomic signature must be selected")
    if len(selected) != len(set(selected)):
        raise PredictionInputError("GBM proteomic signature selections must be unique")
    unknown = [name for name in selected if name not in SUPPORTED_SIGNATURES]
    if unknown:
        raise PredictionInputError(f"unsupported GBM proteomic signature: {unknown[0]}")
    return selected


def _predict_signature(
    artifact: ModelArtifact,
    model: SignatureModel,
    vector: np.ndarray,
    observed_feature_count: int,
) -> SignaturePrediction:
    margin = np.float32(model.base_score)
    constant_leaves: list[float] = []
    contribution_values: defaultdict[str, list[float]] = defaultdict(list)
    for feature_index, threshold, yes_leaf, no_leaf in zip(
        model.split_feature,
        model.split_condition,
        model.yes_leaf,
        model.no_leaf,
        strict=True,
    ):
        if feature_index == -1:
            leaf = yes_leaf
            constant_leaves.append(leaf)
        else:
            leaf = yes_leaf if vector[feature_index] < np.float32(threshold) else no_leaf
            contribution_values[artifact.feature_names[feature_index]].append(leaf)
        margin = np.float32(margin + np.float32(leaf))
    raw_margin = float(margin)
    unrounded_score = raw_margin - model.output_offset
    intercept = model.base_score - model.output_offset + math.fsum(constant_leaves)
    contributions = MappingProxyType(
        {
            feature_name: math.fsum(values)
            for feature_name, values in sorted(contribution_values.items())
        }
    )
    missing_feature_count = MODEL_FEATURE_COUNT - observed_feature_count
    return SignaturePrediction(
        signature_name=model.signature_name,
        score=round(unrounded_score, PUBLISHED_DECIMAL_PLACES),
        unrounded_score=unrounded_score,
        raw_margin=raw_margin,
        intercept=intercept,
        contributions=contributions,
        model_feature_count=MODEL_FEATURE_COUNT,
        observed_feature_count=observed_feature_count,
        missing_feature_count=missing_feature_count,
        missing_feature_ratio=missing_feature_count / MODEL_FEATURE_COUNT,
    )


def predict_axes(
    abundances: Mapping[str, float],
    signature_names: Iterable[str] | None = None,
) -> PredictionResult:
    """Predict selected published GBM proteomic signature activities.

    The returned ``score`` is rounded to four decimals exactly as the authors'
    script reports it.  ``unrounded_score`` is suitable for perturbation and
    interval calculations; ``raw_margin`` is the XGBoost value before the
    published ``-10`` offset.
    """

    selected = _selected_signatures(signature_names)
    scaled, geometric_mean, normalization_factor = scale_positive_lfq(abundances)
    artifact = load_artifact()
    vector = np.zeros(MODEL_FEATURE_COUNT, dtype=np.float32)
    observed_feature_count = 0
    for protein, value in scaled.items():
        index = artifact.feature_index.get(protein)
        if index is not None:
            if value > _FLOAT32_MAX:
                raise PredictionInputError(
                    "normalized model feature is outside the published float32 range"
                )
            vector[index] = np.float32(value)
            observed_feature_count += 1
    predictions = {
        name: _predict_signature(
            artifact,
            artifact.models[name],
            vector,
            observed_feature_count,
        )
        for name in selected
    }
    return PredictionResult(
        geometric_mean=geometric_mean,
        normalization_factor=normalization_factor,
        input_protein_count=len(scaled),
        positive_protein_count=sum(value > 0.0 for value in scaled.values()),
        signatures=MappingProxyType(predictions),
    )


predict_lfq = predict_axes


__all__ = [
    "ARTIFACT_SHA256",
    "GEOMETRIC_MEAN_TARGET",
    "MODEL_FEATURE_COUNT",
    "MODEL_SOURCE_SHA256",
    "ORACLE_FIXTURE_SHA256",
    "PUBLISHED_DECIMAL_PLACES",
    "PUBLISHED_OUTPUT_OFFSET",
    "SOURCE_COMMIT",
    "SOURCE_REPOSITORY_URL",
    "SUPPORTED_SIGNATURES",
    "TREES_PER_SIGNATURE",
    "ModelArtifact",
    "ModelArtifactError",
    "PredictionInputError",
    "PredictionResult",
    "SignatureModelMetadata",
    "SignaturePrediction",
    "feature_names",
    "load_artifact",
    "model_catalog",
    "predict_axes",
    "predict_lfq",
    "scale_positive_lfq",
]
