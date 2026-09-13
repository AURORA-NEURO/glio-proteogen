"""Integrity-checked NumPy access to the converted published GBMPurity model."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from typing import Final, Never, cast

import numpy as np
from numpy.typing import NDArray

from .canonical import canonical_json_bytes, sha256_digest
from .contracts import MODEL_FEATURE_COUNT, MODEL_ID
from .errors import GbmRnaPurityArtifactError

CATALOG_RESOURCE: Final = "data/gbm_purity_mlp.v1.json"
EXPECTED_SCHEMA: Final = "glio-proteogen.gbmpurity-mlp-artifact/1.0.0"
EXPECTED_SOURCE_COMMIT: Final = "af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950"
EXPECTED_SOURCE_MODEL_SHA256: Final = (
    "sha256:80abd8d8f4875799f839701bec655d2e4753c750e63e60b9119b8b66342025c7"
)
EXPECTED_SOURCE_FEATURE_SHA256: Final = (
    "sha256:de148837ab4d487b3fd86436f63e95b451fa4a305c5bf8d5eb094c117941884b"
)
EXPECTED_ARTIFACT_SHA256: Final = (
    "sha256:2999d845c602c7b8b44d45c37a7f43bea57ad6a930af12f9c7b56cc221ffccc2"
)
EXPECTED_CONTENT_DIGEST: Final = (
    "sha256:651fa1ea9100650d8b34cec3c980624e42bada1ec3ff9cfe23fdf13049585722"
)
EXPECTED_FEATURE_ORDER_DIGEST: Final = (
    "sha256:8a2e26d736fb8e1eb2a0ddf5799e2368acb1b6798275d75ef9c60f0c49204112"
)
EXPECTED_WEIGHT_TENSOR_DIGEST: Final = (
    "sha256:2d9ceef433761d9b68419bce4c9c7ed4fb1009b9b195f1b1ea2d81f8913a30f4"
)
EXPECTED_PARAMETER_SHAPES: Final = {
    "fc1.weight": (32, 5_829),
    "fc1.bias": (32,),
    "fc2.weight": (16, 32),
    "fc2.bias": (16,),
    "out.weight": (1, 16),
    "out.bias": (1,),
}

FloatArray = NDArray[np.float32]
FloatLengths = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class GbmRnaPurityCatalog:
    artifact_digest: str
    content_digest: str
    feature_order_digest: str
    weight_tensor_digest: str
    feature_names: tuple[str, ...]
    feature_lengths: FloatLengths
    feature_index: Mapping[str, int]
    parameters: Mapping[str, FloatArray]
    source: Mapping[str, object]
    transformation_notice: str


def _fail(message: str) -> Never:
    raise GbmRnaPurityArtifactError(message)


def _resource_bytes() -> bytes:
    try:
        return files(__package__).joinpath(CATALOG_RESOURCE).read_bytes()
    except FileNotFoundError:
        _fail("converted GBMPurity artifact is absent")


def _string(document: dict[str, object], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        _fail(f"GBMPurity artifact {key} is invalid")
    return value


def _source_string(source: dict[str, object], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        _fail(f"GBMPurity artifact source.{key} is invalid")
    return value


def _decode_parameter(name: str, value: object) -> tuple[FloatArray, str]:
    if not isinstance(value, dict):
        _fail(f"GBMPurity parameter {name} is not an object")
    tensor = cast("dict[str, object]", value)
    if tensor.get("dtype") != "<f4":
        _fail(f"GBMPurity parameter {name} must use little-endian float32")
    expected_shape = EXPECTED_PARAMETER_SHAPES[name]
    raw_shape = tensor.get("shape")
    if not isinstance(raw_shape, list) or tuple(raw_shape) != expected_shape:
        _fail(f"GBMPurity parameter {name} shape mismatch")
    encoded = tensor.get("data_base64")
    if not isinstance(encoded, str):
        _fail(f"GBMPurity parameter {name} base64 payload is invalid")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except ValueError:
        _fail(f"GBMPurity parameter {name} base64 payload is malformed")
    expected_bytes = int(np.prod(expected_shape, dtype=np.int64)) * 4
    if len(payload) != expected_bytes:
        _fail(f"GBMPurity parameter {name} byte count mismatch")
    actual_digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    if tensor.get("sha256") != actual_digest:
        _fail(f"GBMPurity parameter {name} digest mismatch")
    array = np.frombuffer(payload, dtype="<f4").reshape(expected_shape)
    if not np.all(np.isfinite(array)):
        _fail(f"GBMPurity parameter {name} contains non-finite values")
    array.flags.writeable = False
    return array, actual_digest


@lru_cache(maxsize=1)
def gbm_rna_purity_catalog() -> GbmRnaPurityCatalog:  # noqa: PLR0915
    """Load and validate every identity, shape, digest, and numeric invariant."""

    payload = _resource_bytes()
    artifact_digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    if artifact_digest != EXPECTED_ARTIFACT_SHA256:
        _fail("converted GBMPurity artifact file digest mismatch")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail("converted GBMPurity artifact is not valid JSON")
    if not isinstance(value, dict):
        _fail("converted GBMPurity artifact root is not an object")
    document = cast("dict[str, object]", value)
    if document.get("schema_version") != EXPECTED_SCHEMA:
        _fail("converted GBMPurity artifact schema mismatch")
    if document.get("model_id") != MODEL_ID:
        _fail("converted GBMPurity artifact model identity mismatch")
    declared_content = _string(document, "content_digest")
    if declared_content != EXPECTED_CONTENT_DIGEST:
        _fail("converted GBMPurity artifact is not the admitted content")
    digest_document = dict(document)
    digest_document.pop("content_digest")
    if declared_content != sha256_digest(digest_document):
        _fail("converted GBMPurity artifact content digest mismatch")

    raw_input = document.get("input")
    if not isinstance(raw_input, dict):
        _fail("GBMPurity input metadata is invalid")
    raw_names = raw_input.get("feature_names")
    raw_lengths = raw_input.get("feature_lengths")
    if not isinstance(raw_names, list) or not all(isinstance(item, str) for item in raw_names):
        _fail("GBMPurity feature names are invalid")
    feature_names = tuple(cast("list[str]", raw_names))
    if len(feature_names) != MODEL_FEATURE_COUNT or len(set(feature_names)) != len(feature_names):
        _fail("GBMPurity feature order must contain 5,829 unique symbols")
    if not isinstance(raw_lengths, list) or len(raw_lengths) != MODEL_FEATURE_COUNT:
        _fail("GBMPurity feature lengths are invalid")
    try:
        feature_lengths = np.asarray(raw_lengths, dtype=np.float64)
    except (TypeError, ValueError):
        _fail("GBMPurity feature lengths are not numeric")
    if not np.all(np.isfinite(feature_lengths)) or np.any(feature_lengths <= 0.0):
        _fail("GBMPurity feature lengths must be finite and positive")
    feature_lengths.flags.writeable = False

    feature_order_digest = _string(document, "feature_order_digest")
    if feature_order_digest != EXPECTED_FEATURE_ORDER_DIGEST:
        _fail("GBMPurity feature order is not the admitted feature vector")
    if feature_order_digest != sha256_digest(feature_names):
        _fail("GBMPurity feature-order digest mismatch")

    raw_parameters = document.get("parameters")
    if not isinstance(raw_parameters, dict) or set(raw_parameters) != set(
        EXPECTED_PARAMETER_SHAPES
    ):
        _fail("GBMPurity parameter inventory mismatch")
    parameters: dict[str, FloatArray] = {}
    tensor_digests: dict[str, str] = {}
    for name in EXPECTED_PARAMETER_SHAPES:
        parameter, digest = _decode_parameter(name, raw_parameters[name])
        parameters[name] = parameter
        tensor_digests[name] = digest
    weight_tensor_digest = _string(document, "weight_tensor_digest")
    if weight_tensor_digest != EXPECTED_WEIGHT_TENSOR_DIGEST:
        _fail("GBMPurity weights are not the admitted tensor bundle")
    if weight_tensor_digest != sha256_digest(tensor_digests):
        _fail("GBMPurity weight-tensor digest mismatch")

    raw_source = document.get("source")
    if not isinstance(raw_source, dict):
        _fail("GBMPurity artifact source metadata is invalid")
    source = cast("dict[str, object]", raw_source)
    if _source_string(source, "commit") != EXPECTED_SOURCE_COMMIT:
        _fail("GBMPurity source commit mismatch")
    if _source_string(source, "model_sha256") != EXPECTED_SOURCE_MODEL_SHA256:
        _fail("GBMPurity source model digest mismatch")
    if _source_string(source, "gene_table_sha256") != EXPECTED_SOURCE_FEATURE_SHA256:
        _fail("GBMPurity source feature-table digest mismatch")
    if _source_string(source, "license_spdx_id") != "MIT":
        _fail("GBMPurity source license mismatch")

    raw_provenance = document.get("provenance")
    if not isinstance(raw_provenance, dict):
        _fail("GBMPurity provenance metadata is invalid")
    transformation_notice = raw_provenance.get("transformation_notice")
    if not isinstance(transformation_notice, str) or not transformation_notice:
        _fail("GBMPurity transformation notice is invalid")

    # Re-encoding is a guard against JSON scalar oddities such as non-finite extensions.
    canonical_json_bytes(document)
    return GbmRnaPurityCatalog(
        artifact_digest=artifact_digest,
        content_digest=declared_content,
        feature_order_digest=feature_order_digest,
        weight_tensor_digest=weight_tensor_digest,
        feature_names=feature_names,
        feature_lengths=feature_lengths,
        feature_index=MappingProxyType(
            {symbol: index for index, symbol in enumerate(feature_names)}
        ),
        parameters=MappingProxyType(parameters),
        source=MappingProxyType(source),
        transformation_notice=transformation_notice,
    )


__all__ = [
    "CATALOG_RESOURCE",
    "EXPECTED_ARTIFACT_SHA256",
    "EXPECTED_CONTENT_DIGEST",
    "EXPECTED_FEATURE_ORDER_DIGEST",
    "EXPECTED_PARAMETER_SHAPES",
    "EXPECTED_WEIGHT_TENSOR_DIGEST",
    "GbmRnaPurityCatalog",
    "gbm_rna_purity_catalog",
]
