"""Fail-closed catalog for the fitted KNCC Neftel transition model."""

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

from .catalog import (
    EXPECTED_GENE_COUNT,
    EXPECTED_PROGRAM_COUNT,
    PROFILE_ID,
    NeftelTransitionSourceCatalog,
    neftel_transition_source_catalog,
)
from .errors import NeftelConditionalModelIntegrityError

FloatArray = NDArray[np.float64]
Float32Array = NDArray[np.float32]
IntArray = NDArray[np.int64]
Int16Array = NDArray[np.int16]
BoolArray = NDArray[np.bool_]

ARTIFACT_RESOURCE: Final = "data/kncc_neftel_program_transition_model.v1.json"
MODEL_ID: Final = "kncc-neftel-program-transition-model/1.0.0"
SCHEMA_VERSION: Final = "glio-proteogen.kncc-neftel-program-transition-model/1.0.0"
EXPECTED_ARTIFACT_BYTES: Final = 357_871
EXPECTED_ARTIFACT_SHA256: Final = (
    "sha256:cdc00db86c83bee0ff62eb30f4e0130da8621b09ebca298adf16458e073d38a9"
)
EXPECTED_CONTENT_DIGEST: Final = (
    "sha256:815b4066891c9ddf78b3be374e573be28e299eb15ed612ee3c662f33a84c8e41"
)
EXPECTED_UNION_FEATURE_COUNT: Final = 256
EXPECTED_BOOTSTRAP_REPLICATES: Final = 128
EXPECTED_DESIGN_COLUMNS: Final = EXPECTED_PROGRAM_COUNT + 1
EXPECTED_SOLVER_MAX_ITERATIONS: Final = 200


@dataclass(frozen=True, slots=True)
class FittedProgramLoading:
    """One fitted conditional loading and its transparent decomposition."""

    program_index: int
    domain_id: str
    program_id: str
    name: str
    member_local_indices: tuple[int, ...]
    unique_member_local_indices: tuple[int, ...]
    unadjusted_loading: FloatArray
    global_projection: float
    residual_norm: float
    global_adjustment_loading: FloatArray
    conditional_loading: FloatArray
    ordinary_conditional_loading: FloatArray
    no_degree_conditional_loading: FloatArray
    cross_fitted_mad_scale: float


@dataclass(frozen=True, slots=True)
class FittedBootstrapDraw:
    """One immutable source-bootstrap scale/effect draw."""

    index: int
    scale: Float32Array
    effect: Float32Array
    row_digest: str


@dataclass(frozen=True, slots=True)
class NeftelProgramFittedCatalog:
    """Verified fitted aggregate model with no patient-level source values."""

    profile_id: str
    model_id: str
    source_catalog: NeftelTransitionSourceCatalog
    union_feature_indices: tuple[int, ...]
    union_gene_symbols: tuple[str, ...]
    local_index_by_feature: Mapping[int, int]
    membership_degree: FloatArray
    programs: tuple[FittedProgramLoading, ...]
    reference_scale: FloatArray
    reference_effect: FloatArray
    reference_support: Int16Array
    reference_eligible: BoolArray
    reference_design: FloatArray
    ordinary_design: FloatArray
    no_degree_design: FloatArray
    bootstrap_scales: Float32Array
    bootstrap_effects: Float32Array
    bootstrap_row_digests: tuple[str, ...]
    cross_fitted_coordinate_scales: Mapping[str, float]
    evaluation: Mapping[str, object]
    limitations: tuple[str, ...]
    artifact_bytes: int
    artifact_byte_digest: str
    content_digest: str
    source_catalog_binding_digest: str
    training_recipe_digest: str
    union_feature_digest: str
    program_inventory_digest: str
    membership_degree_digest: str
    reference_tensor_digest: str
    centering_scaling_digest: str
    reference_design_digest: str
    equal_membership_design_digest: str
    global_loading_digest: str
    conditional_loading_digest: str
    fold_policy_digest: str
    source_processing_ablation_digest: str
    bootstrap_seed_namespace_digest: str
    bootstrap_ensemble_digest: str
    evaluation_digest: str
    numpy_version: str

    @property
    def union_feature_count(self) -> int:
        return len(self.union_feature_indices)

    @property
    def program_count(self) -> int:
        return len(self.programs)

    @property
    def bootstrap_replicate_count(self) -> int:
        return int(self.bootstrap_scales.shape[0])

    def bootstrap_draw(self, index: int) -> FittedBootstrapDraw:
        if not 0 <= index < self.bootstrap_replicate_count:
            raise IndexError("bootstrap draw index is out of range")
        return FittedBootstrapDraw(
            index=index,
            scale=_readonly(self.bootstrap_scales[index]),
            effect=_readonly(self.bootstrap_effects[index]),
            row_digest=self.bootstrap_row_digests[index],
        )

    def design_for_bootstrap(self, index: int) -> FloatArray:
        draw = self.bootstrap_draw(index)
        # The offline importer refits the coverage gate inside every patient
        # bootstrap.  ``AxisFit.effect`` is exactly zero for features that are
        # ineligible in that draw, so the non-zero effect mask reconstructs the
        # draw-local eligibility needed by the locked ``_design`` recipe.  A
        # reference-fit mask would silently discard features that become
        # eligible in a resample and would no longer reproduce the fitted
        # source-bootstrap model.
        draw_eligible = np.asarray(draw.effect != 0.0, dtype=np.bool_)
        design, _ = _derive_design(
            np.asarray(draw.effect, dtype=np.float64),
            draw_eligible,
            tuple(item.member_local_indices for item in self.programs),
            self.membership_degree,
        )
        return _readonly(design)


def _fail(message: str) -> Never:
    raise NeftelConditionalModelIntegrityError(message)


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


def _object(value: object, name: str) -> dict[str, object]:
    if type(value) is not dict:
        _fail(f"fitted artifact field {name!r} must be an object")
    return cast("dict[str, object]", value)


def _array(value: object, name: str) -> list[object]:
    if type(value) is not list:
        _fail(f"fitted artifact field {name!r} must be an array")
    return cast("list[object]", value)


def _integer(value: object, name: str) -> int:
    if type(value) is not int:
        _fail(f"fitted artifact field {name!r} must be an integer")
    return value


def _finite(value: object, name: str) -> float:
    if type(value) not in {int, float}:
        _fail(f"fitted artifact field {name!r} must be numeric")
    result = float(cast("int | float", value))
    if not math.isfinite(result):
        _fail(f"fitted artifact field {name!r} must be finite")
    return result


def _readonly[DType: np.generic](array: NDArray[DType]) -> NDArray[DType]:
    contiguous = np.ascontiguousarray(array)
    contiguous.flags.writeable = False
    return contiguous


def _deep_freeze(value: object) -> object:
    if type(value) is dict:
        document = cast("dict[str, object]", value)
        return MappingProxyType({key: _deep_freeze(child) for key, child in document.items()})
    if type(value) is list:
        return tuple(_deep_freeze(child) for child in cast("list[object]", value))
    return value


def _decode_tensor(
    value: object,
    name: str,
    *,
    expected_dtype: str,
    expected_shape: tuple[int, ...],
) -> NDArray[np.generic]:
    tensor = _object(value, name)
    if (
        tensor.get("dtype") != expected_dtype
        or tensor.get("shape") != list(expected_shape)
        or tensor.get("encoding") != "base64+zlib"
    ):
        _fail(f"fitted tensor metadata mismatch: {name}")
    encoded = tensor.get("data")
    if type(encoded) is not str:
        _fail(f"fitted tensor data must be text: {name}")
    try:
        compressed = base64.b64decode(encoded, validate=True)
        payload = zlib.decompress(compressed)
    except (ValueError, zlib.error) as error:
        raise NeftelConditionalModelIntegrityError(
            f"fitted tensor encoding is invalid: {name}"
        ) from error
    expected_bytes = int(np.prod(expected_shape)) * np.dtype(expected_dtype).itemsize
    if (
        tensor.get("raw_bytes") != expected_bytes
        or len(payload) != expected_bytes
        or tensor.get("raw_sha256") != _raw_digest(payload)
    ):
        _fail(f"fitted tensor byte lock mismatch: {name}")
    result = np.frombuffer(payload, dtype=np.dtype(expected_dtype)).reshape(expected_shape)
    return _readonly(result)


def _derive_design(
    effect: FloatArray,
    eligible: BoolArray,
    members: tuple[tuple[int, ...], ...],
    degree: FloatArray,
    *,
    use_degree: bool = True,
) -> tuple[FloatArray, tuple[tuple[FloatArray, float, float, FloatArray], ...]]:
    norm = float(np.linalg.norm(effect))
    if not math.isfinite(norm) or norm <= 0.0:
        _fail("fitted global effect has invalid norm")
    global_loading = effect / norm
    columns = [global_loading]
    decompositions: list[tuple[FloatArray, float, float, FloatArray]] = []
    for positions_value in members:
        positions = np.asarray(positions_value, dtype=np.int64)
        raw = np.zeros(effect.size, dtype=np.float64)
        active = eligible[positions]
        selected = positions[active]
        divisor = np.sqrt(degree[selected]) if use_degree else 1.0
        raw[selected] = effect[selected] / divisor
        projection = float(np.dot(global_loading, raw))
        residual = raw - projection * global_loading
        residual_norm = float(np.linalg.norm(residual))
        if not math.isfinite(residual_norm) or residual_norm <= 0.0:
            _fail("fitted conditional loading has invalid norm")
        conditional = residual / residual_norm
        columns.append(conditional)
        decompositions.append((raw / residual_norm, projection, residual_norm, conditional))
    design = np.column_stack(columns) * math.sqrt(effect.size)
    return design, tuple(decompositions)


def _derive_equal_membership_design(
    effect: FloatArray,
    eligible: BoolArray,
    members: tuple[tuple[int, ...], ...],
    degree: FloatArray,
) -> FloatArray:
    """Reconstruct the prespecified equal-membership comparison dictionary."""

    norm = float(np.linalg.norm(effect))
    if not math.isfinite(norm) or norm <= 0.0:
        _fail("fitted global effect has invalid norm")
    global_loading = effect / norm
    columns = [global_loading]
    for positions_value in members:
        positions = np.asarray(positions_value, dtype=np.int64)
        raw = np.zeros(effect.size, dtype=np.float64)
        selected = positions[eligible[positions]]
        raw[selected] = 1.0 / np.sqrt(degree[selected])
        raw -= global_loading * float(np.dot(global_loading, raw))
        residual_norm = float(np.linalg.norm(raw))
        if not math.isfinite(residual_norm) or residual_norm <= 0.0:
            _fail("fitted equal-membership loading has invalid norm")
        columns.append(raw / residual_norm)
    return np.column_stack(columns) * math.sqrt(effect.size)


def _loading_cosines(left: FloatArray, right: FloatArray) -> tuple[float, ...]:
    if left.shape != right.shape:
        _fail("fitted ablation loading shape mismatch")
    result: list[float] = []
    for index in range(left.shape[1]):
        left_column = left[:, index]
        right_column = right[:, index]
        denominator = float(np.linalg.norm(left_column) * np.linalg.norm(right_column))
        if not math.isfinite(denominator) or denominator <= 0.0:
            _fail("fitted ablation loading norm is invalid")
        result.append(float(abs(np.dot(left_column, right_column)) / denominator))
    return tuple(result)


def _source_binding(
    document: dict[str, object],
    source: NeftelTransitionSourceCatalog,
    expected_digest: str,
) -> None:
    binding = _object(document.get("source_catalog_binding"), "source_catalog_binding")
    if binding != dict(source.source_catalog_binding) or _digest(binding) != expected_digest:
        _fail("fitted artifact source-catalog binding mismatch")


def _locked_digests(document: dict[str, object]) -> dict[str, str]:
    values = _object(document.get("digests"), "digests")
    expected_keys = {
        "source_catalog_binding_digest",
        "training_recipe_digest",
        "union_feature_digest",
        "program_inventory_digest",
        "membership_degree_digest",
        "reference_tensor_digest",
        "centering_scaling_digest",
        "reference_design_digest",
        "equal_membership_design_digest",
        "global_loading_digest",
        "conditional_loading_digest",
        "fold_policy_digest",
        "source_processing_ablation_digest",
        "bootstrap_seed_namespace_digest",
        "bootstrap_ensemble_digest",
        "evaluation_digest",
    }
    if set(values) != expected_keys or any(
        not isinstance(values[key], str)
        or not str(values[key]).startswith("sha256:")
        or len(str(values[key])) != 71
        for key in expected_keys
    ):
        _fail("fitted artifact locked digest inventory mismatch")
    return {key: str(values[key]) for key in expected_keys}


@lru_cache(maxsize=1)
def neftel_program_fitted_catalog() -> NeftelProgramFittedCatalog:  # noqa: PLR0915
    """Load and independently verify the aggregate fitted model."""

    payload = _resource_bytes()
    if len(payload) != EXPECTED_ARTIFACT_BYTES:
        _fail("fitted artifact byte length mismatch")
    artifact_byte_digest = _raw_digest(payload)
    if artifact_byte_digest != EXPECTED_ARTIFACT_SHA256:
        _fail("fitted artifact byte digest mismatch")
    try:
        raw = cast("object", json.loads(payload))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NeftelConditionalModelIntegrityError("fitted artifact is not valid JSON") from error
    if type(raw) is not dict:
        _fail("fitted artifact root must be an object")
    document = cast("dict[str, object]", raw)
    if _canonical_bytes(document) != payload:
        _fail("fitted artifact must be canonical JSON")
    content = dict(document)
    declared_digest = content.pop("artifact_digest", None)
    content_digest = _digest(content)
    if content_digest != EXPECTED_CONTENT_DIGEST or declared_digest != content_digest:
        _fail("fitted artifact canonical content digest mismatch")
    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("model_id") != MODEL_ID
        or document.get("profile_id") != PROFILE_ID
        or document.get("artifact_role")
        != ("de-identified fitted conditional bulk-protein program-transition concordance model")
    ):
        _fail("fitted artifact identity mismatch")
    digests = _locked_digests(document)
    source = neftel_transition_source_catalog()
    _source_binding(document, source, digests["source_catalog_binding_digest"])

    recipe = _object(document.get("training_recipe"), "training_recipe")
    fold_policy = _object(document.get("fold_policy"), "fold_policy")
    if (
        _digest(recipe) != digests["training_recipe_digest"]
        or recipe.get("solver_max_iterations") != EXPECTED_SOLVER_MAX_ITERATIONS
        or recipe.get("solver_huber_k") != 1.345
        or recipe.get("solver_ridge_lambda") != 1.0
        or recipe.get("solver_global_ridge_multiplier") != 0.25
        or recipe.get("solver_damping") != 0.7
        or recipe.get("solver_tolerance") != 1.0e-9
        or _digest(fold_policy) != digests["fold_policy_digest"]
        or fold_policy.get("outer_folds") != 8
        or fold_policy.get("held_marker_folds") != 5
        or fold_policy.get("outer_fold_salt") != "kncc-neftel-program-outer-v1"
        or fold_policy.get("marker_fold_salt") != "kncc-neftel-marker-fold-v1"
        or recipe.get("program_order") != [program.program_id for program in source.programs]
        or recipe.get("held_marker_folds") != 5
        or recipe.get("marker_fold_salt") != "kncc-neftel-marker-fold-v1"
    ):
        _fail("fitted training recipe or fold policy mismatch")

    counts = _object(document.get("counts"), "counts")
    if counts != {
        "source_patient_pairs": 104,
        "source_gene_features": EXPECTED_GENE_COUNT,
        "union_features": EXPECTED_UNION_FEATURE_COUNT,
        "reference_eligible_union_features": EXPECTED_UNION_FEATURE_COUNT,
        "programs": EXPECTED_PROGRAM_COUNT,
        "bootstrap_replicates": EXPECTED_BOOTSTRAP_REPLICATES,
    }:
        _fail("fitted model count inventory mismatch")
    union = tuple(
        _integer(value, "union feature index")
        for value in _array(document.get("union_feature_indices"), "union features")
    )
    expected_union = tuple(
        sorted(set().union(*(set(program.member_feature_indices) for program in source.programs)))
    )
    if union != expected_union or _digest(list(union)) != digests["union_feature_digest"]:
        _fail("fitted union feature axis mismatch")
    local = {feature: index for index, feature in enumerate(union)}
    program_documents = _array(document.get("programs"), "programs")
    if (
        len(program_documents) != EXPECTED_PROGRAM_COUNT
        or _digest(program_documents) != digests["program_inventory_digest"]
    ):
        _fail("fitted program inventory digest mismatch")
    members_list: list[tuple[int, ...]] = []
    for program, value in zip(source.programs, program_documents, strict=True):
        row = _object(value, "program")
        member_indices = tuple(
            _integer(item, "program member feature index")
            for item in _array(row.get("member_feature_indices"), "program members")
        )
        member_local_indices = tuple(
            _integer(item, "program member local index")
            for item in _array(row.get("member_local_indices"), "program member local indices")
        )
        mapped_indices = tuple(
            _integer(item, "program mapped feature index")
            for item in _array(row.get("mapped_feature_indices"), "program mapped feature indices")
        )
        expected_local = tuple(local[index] for index in member_indices)
        expected_row = {
            "program_index": program.program_index,
            "program_id": program.program_id,
            "source_marker_count": program.source_member_count,
            "protein_eligible_marker_count": program.protein_eligible_marker_count,
            "mapped_feature_count": program.mapped_feature_count,
            "reference_eligible_feature_count": program.eligible_feature_count,
            "mapped_feature_indices": list(program.mapped_feature_indices),
            "member_feature_indices": list(program.member_feature_indices),
            "member_local_indices": list(expected_local),
            "member_symbol_digest": program.member_symbol_digest,
            "member_index_digest": program.member_index_digest,
        }
        if (
            row != expected_row
            or member_indices != program.member_feature_indices
            or mapped_indices != program.mapped_feature_indices
            or member_local_indices != expected_local
        ):
            _fail(f"fitted program inventory mismatch: {program.program_id}")
        members_list.append(member_local_indices)
    members = tuple(members_list)

    degree_tensor = document.get("membership_degree")
    degree_int = cast(
        "Int16Array",
        _decode_tensor(
            degree_tensor,
            "membership degree",
            expected_dtype="<i2",
            expected_shape=(len(union),),
        ),
    )
    expected_degree = np.zeros(len(union), dtype=np.int16)
    for positions in members:
        expected_degree[np.asarray(positions, dtype=np.int64)] += 1
    if (
        _digest(degree_tensor) != digests["membership_degree_digest"]
        or np.any(expected_degree < 1)
        or not np.array_equal(degree_int, expected_degree)
    ):
        _fail("fitted membership degree is invalid")
    degree = np.asarray(degree_int, dtype=np.float64)

    reference = _object(document.get("reference_fit"), "reference_fit")
    tensors = _object(reference.get("tensors"), "reference_fit.tensors")
    reference_scale = cast(
        "FloatArray",
        _decode_tensor(
            tensors.get("scale"),
            "reference scale",
            expected_dtype="<f8",
            expected_shape=(len(union),),
        ),
    )
    reference_effect = cast(
        "FloatArray",
        _decode_tensor(
            tensors.get("effect"),
            "reference effect",
            expected_dtype="<f8",
            expected_shape=(len(union),),
        ),
    )
    reference_support = cast(
        "Int16Array",
        _decode_tensor(
            tensors.get("support"),
            "reference support",
            expected_dtype="<i2",
            expected_shape=(len(union),),
        ),
    )
    reference_eligible = cast(
        "BoolArray",
        _decode_tensor(
            tensors.get("eligible"),
            "reference eligibility",
            expected_dtype="|b1",
            expected_shape=(len(union),),
        ),
    )
    if (
        not np.all(np.isfinite(reference_scale))
        or np.any(reference_scale <= 0.0)
        or not np.all(np.isfinite(reference_effect))
        or np.any(reference_support < 0)
        or np.any(reference_support > 104)
        or not np.all(reference_effect[~reference_eligible] == 0.0)
        or not np.all(reference_eligible)
        or reference.get("converged") is not True
        or _integer(reference.get("iterations"), "reference iterations") <= 0
    ):
        _fail("fitted reference tensor domain mismatch")
    if _digest(tensors) != digests["reference_tensor_digest"]:
        _fail("fitted reference tensor digest mismatch")
    centering_scaling = {key: tensors[key] for key in ("scale", "support", "eligible")}
    if _digest(centering_scaling) != digests["centering_scaling_digest"]:
        _fail("fitted centering/scaling digest mismatch")
    design, decompositions = _derive_design(
        reference_effect,
        reference_eligible,
        members,
        degree,
    )
    equal_membership_design = _derive_equal_membership_design(
        reference_effect,
        reference_eligible,
        members,
        degree,
    )
    design_bytes = np.ascontiguousarray(design, dtype="<f8").tobytes()
    equal_design_bytes = np.ascontiguousarray(
        equal_membership_design,
        dtype="<f8",
    ).tobytes()
    if (
        _raw_digest(design_bytes) != digests["reference_design_digest"]
        or reference.get("design_raw_sha256") != digests["reference_design_digest"]
        or _raw_digest(equal_design_bytes) != digests["equal_membership_design_digest"]
        or reference.get("equal_membership_design_raw_sha256")
        != digests["equal_membership_design_digest"]
        or _raw_digest(np.ascontiguousarray(design[:, 0], dtype="<f8").tobytes())
        != digests["global_loading_digest"]
        or _raw_digest(np.ascontiguousarray(design[:, 1:], dtype="<f8").tobytes())
        != digests["conditional_loading_digest"]
        or not math.isclose(
            _finite(reference.get("design_condition_number"), "design condition"),
            float(np.linalg.cond(design)),
            abs_tol=5.0e-11,
        )
        or not math.isclose(
            _finite(
                reference.get("equal_membership_design_condition_number"),
                "equal-membership design condition",
            ),
            float(np.linalg.cond(equal_membership_design)),
            abs_tol=5.0e-11,
        )
    ):
        _fail("fitted reference loading digest or condition mismatch")

    processing = _object(document.get("source_processing_ablation"), "source processing ablation")
    ordinary_tensor = processing.get("effect")
    ordinary_effect = cast(
        "FloatArray",
        _decode_tensor(
            ordinary_tensor,
            "ordinary effect",
            expected_dtype="<f8",
            expected_shape=(len(union),),
        ),
    )
    if (
        _digest(ordinary_tensor) != digests["source_processing_ablation_digest"]
        or processing.get("measure") != "Log"
        or processing.get("converged") is not True
        or _integer(processing.get("iterations"), "source ablation iterations") <= 0
    ):
        _fail("fitted source-processing digest mismatch")
    ordinary_design, _ = _derive_design(
        ordinary_effect,
        ordinary_effect != 0.0,
        members,
        degree,
    )
    no_degree_design, _ = _derive_design(
        reference_effect,
        reference_eligible,
        members,
        degree,
        use_degree=False,
    )
    source_cosines = tuple(
        _finite(value, "source-processing loading cosine")
        for value in _array(
            processing.get("loading_cosines"),
            "source-processing loading cosines",
        )
    )
    degree_ablation = _object(
        document.get("degree_normalization_ablation"),
        "degree-normalization ablation",
    )
    degree_cosines = tuple(
        _finite(value, "degree-normalization loading cosine")
        for value in _array(
            degree_ablation.get("loading_cosines"),
            "degree-normalization loading cosines",
        )
    )
    if (
        len(source_cosines) != EXPECTED_DESIGN_COLUMNS
        or len(degree_cosines) != EXPECTED_DESIGN_COLUMNS
        or any(
            not math.isclose(actual, expected, abs_tol=5.0e-11)
            for actual, expected in zip(
                source_cosines,
                _loading_cosines(design, ordinary_design),
                strict=True,
            )
        )
        or any(
            not math.isclose(actual, expected, abs_tol=5.0e-11)
            for actual, expected in zip(
                degree_cosines,
                _loading_cosines(design, no_degree_design),
                strict=True,
            )
        )
    ):
        _fail("fitted loading-ablation oracle mismatch")

    bootstrap = _object(document.get("bootstrap"), "bootstrap")
    bootstrap_tensors = _object(bootstrap.get("tensors"), "bootstrap.tensors")
    bootstrap_scales = cast(
        "Float32Array",
        _decode_tensor(
            bootstrap_tensors.get("scale"),
            "bootstrap scale",
            expected_dtype="<f4",
            expected_shape=(EXPECTED_BOOTSTRAP_REPLICATES, len(union)),
        ),
    )
    bootstrap_effects = cast(
        "Float32Array",
        _decode_tensor(
            bootstrap_tensors.get("effect"),
            "bootstrap effect",
            expected_dtype="<f4",
            expected_shape=(EXPECTED_BOOTSTRAP_REPLICATES, len(union)),
        ),
    )
    row_digests = tuple(
        str(value) for value in _array(bootstrap.get("row_digests"), "bootstrap row digests")
    )
    if (
        bootstrap.get("replicates") != EXPECTED_BOOTSTRAP_REPLICATES
        or bootstrap.get("resample_unit") != "strict paired patient group"
        or bootstrap.get("patient_indices_or_hashes_bundled") is not False
        or bootstrap.get("seed_namespace_digest") != digests["bootstrap_seed_namespace_digest"]
        or len(row_digests) != EXPECTED_BOOTSTRAP_REPLICATES
        or not np.all(np.isfinite(bootstrap_scales))
        or np.any(bootstrap_scales <= 0.0)
        or not np.all(np.isfinite(bootstrap_effects))
    ):
        _fail("fitted bootstrap tensor domain mismatch")
    for index, row_digest in enumerate(row_digests):
        expected = _raw_digest(
            bootstrap_scales[index].tobytes() + bootstrap_effects[index].tobytes()
        )
        if row_digest != expected:
            _fail("fitted bootstrap row digest mismatch")
    if (
        _digest({"tensors": bootstrap_tensors, "row_digests": list(row_digests)})
        != digests["bootstrap_ensemble_digest"]
    ):
        _fail("fitted bootstrap ensemble digest mismatch")

    evaluation = _object(document.get("evaluation"), "evaluation")
    nonconverged = _object(
        evaluation.get("solver_nonconverged_by_role"),
        "evaluation solver nonconvergence",
    )
    leave_program_out = _array(
        evaluation.get("leave_program_out"),
        "leave-program-out evaluation",
    )
    leave_ids: list[str] = []
    all_leave_intervals_cross_zero = True
    for item in leave_program_out:
        row = _object(item, "leave-program-out row")
        leave_ids.append(str(row.get("program_id")))
        lower = _finite(row.get("q05"), "leave-program-out q05")
        upper = _finite(row.get("q95"), "leave-program-out q95")
        all_leave_intervals_cross_zero = all_leave_intervals_cross_zero and lower <= 0.0 <= upper
    zero_mae = _finite(
        evaluation.get("zero_prediction_median_standardized_mae"),
        "zero prediction MAE",
    )
    global_mae = _finite(
        evaluation.get("global_only_median_standardized_mae"),
        "global-only MAE",
    )
    equal_mae = _finite(
        evaluation.get("equal_membership_median_standardized_mae"),
        "equal-membership MAE",
    )
    joint_mae = _finite(
        evaluation.get("joint_median_standardized_mae"),
        "joint MAE",
    )
    global_interval = tuple(
        _finite(value, "patient-cluster joint-vs-global interval")
        for value in _array(
            evaluation.get("patient_cluster_joint_vs_global_median_gain_90_interval"),
            "patient-cluster joint-vs-global interval",
        )
    )
    equal_interval = tuple(
        _finite(value, "patient-cluster joint-vs-equal interval")
        for value in _array(
            evaluation.get("patient_cluster_joint_vs_equal_median_gain_90_interval"),
            "patient-cluster joint-vs-equal interval",
        )
    )
    if (
        _digest(evaluation) != digests["evaluation_digest"]
        or evaluation.get("evaluation_count") != 520
        or evaluation.get("patient_count") != 104
        or evaluation.get("union_feature_count") != EXPECTED_UNION_FEATURE_COUNT
        or evaluation.get("minimum_finite_held_marker_count") != 43
        or evaluation.get("minimum_finite_inference_marker_count") != 185
        or evaluation.get("minimum_structural_marker_fold_count") != 48
        or evaluation.get("release_gate")
        != "limited_fitted_dictionary_not_preferred_to_equal_membership"
        or evaluation.get("joint_vs_global_patient_cluster_interval_supports_positive_gain")
        is not True
        or evaluation.get("joint_vs_equal_patient_cluster_interval_supports_positive_gain")
        is not False
        or evaluation.get("individually_supported_program_ids") != []
        or set(nonconverged)
        != {
            "equal_membership_held_marker",
            "full_patient",
            "global_held_marker",
            "joint_held_marker",
            "leave_program_out",
        }
        or any(value != 0 for value in nonconverged.values())
        or leave_ids != [program.program_id for program in source.programs]
        or not all_leave_intervals_cross_zero
        or not (equal_mae < joint_mae < global_mae < zero_mae)
        or _finite(
            evaluation.get("joint_vs_global_median_relative_mae_gain"),
            "joint-vs-global median gain",
        )
        <= 0.0
        or _finite(
            evaluation.get("joint_vs_equal_median_relative_mae_gain"),
            "joint-vs-equal median gain",
        )
        >= 0.0
        or len(global_interval) != 2
        or not (0.0 < global_interval[0] <= global_interval[1])
        or len(equal_interval) != 2
        or not (equal_interval[0] <= equal_interval[1] < 0.0)
    ):
        _fail("fitted evaluation digest or oracle mismatch")
    scales: dict[str, float] = {}
    for value in _array(
        evaluation.get("cross_fitted_coordinate_scales"),
        "cross-fitted coordinate scales",
    ):
        row = _object(value, "cross-fitted coordinate scale")
        component = str(row.get("component_id"))
        scale = _finite(row.get("mad_scale"), "cross-fitted MAD scale")
        if component in scales or scale <= 0.0:
            _fail("cross-fitted coordinate scale inventory mismatch")
        scales[component] = scale
    expected_components = {"global_recurrence"} | {item.program_id for item in source.programs}
    if set(scales) != expected_components:
        _fail("cross-fitted coordinate component inventory mismatch")

    program_loadings: list[FittedProgramLoading] = []
    for program, positions, decomposition in zip(
        source.programs,
        members,
        decompositions,
        strict=True,
    ):
        unadjusted, projection, residual_norm, conditional = decomposition
        unique = tuple(index for index in positions if degree[index] == 1.0)
        adjustment = unadjusted - conditional
        arrays = (unadjusted, adjustment, conditional)
        for array_value in arrays:
            array_value.flags.writeable = False
        program_loadings.append(
            FittedProgramLoading(
                program_index=program.program_index,
                domain_id=program.domain_id,
                program_id=program.program_id,
                name=program.name,
                member_local_indices=positions,
                unique_member_local_indices=unique,
                unadjusted_loading=unadjusted,
                global_projection=projection,
                residual_norm=residual_norm,
                global_adjustment_loading=adjustment,
                conditional_loading=conditional,
                ordinary_conditional_loading=_readonly(
                    ordinary_design[:, program.program_index + 1] / math.sqrt(len(union))
                ),
                no_degree_conditional_loading=_readonly(
                    no_degree_design[:, program.program_index + 1] / math.sqrt(len(union))
                ),
                cross_fitted_mad_scale=scales[program.program_id],
            )
        )
    for array_value in (design, ordinary_design, no_degree_design, degree):
        array_value.flags.writeable = False

    privacy = _object(document.get("privacy"), "privacy")
    if any(value is not False for value in privacy.values()) or len(privacy) != 5:
        _fail("fitted artifact privacy declaration mismatch")
    limitations = tuple(str(value) for value in _array(document.get("limitations"), "limitations"))
    if len(limitations) < 8 or not all(limitations):
        _fail("fitted artifact limitation inventory mismatch")
    provenance = _object(document.get("provenance"), "provenance")
    numpy_version = str(provenance.get("numpy_version"))
    if numpy_version != np.__version__:
        _fail("fitted artifact NumPy version mismatch")
    return NeftelProgramFittedCatalog(
        profile_id=PROFILE_ID,
        model_id=MODEL_ID,
        source_catalog=source,
        union_feature_indices=union,
        union_gene_symbols=tuple(source.genes[index] for index in union),
        local_index_by_feature=MappingProxyType(local),
        membership_degree=_readonly(degree),
        programs=tuple(program_loadings),
        reference_scale=reference_scale,
        reference_effect=reference_effect,
        reference_support=reference_support,
        reference_eligible=reference_eligible,
        reference_design=_readonly(design),
        ordinary_design=_readonly(ordinary_design),
        no_degree_design=_readonly(no_degree_design),
        bootstrap_scales=bootstrap_scales,
        bootstrap_effects=bootstrap_effects,
        bootstrap_row_digests=row_digests,
        cross_fitted_coordinate_scales=MappingProxyType(
            {
                "global_transition": scales["global_recurrence"],
                **{item.program_id: scales[item.program_id] for item in source.programs},
            }
        ),
        evaluation=cast("Mapping[str, object]", _deep_freeze(evaluation)),
        limitations=limitations,
        artifact_bytes=len(payload),
        artifact_byte_digest=artifact_byte_digest,
        content_digest=content_digest,
        source_catalog_binding_digest=digests["source_catalog_binding_digest"],
        training_recipe_digest=digests["training_recipe_digest"],
        union_feature_digest=digests["union_feature_digest"],
        program_inventory_digest=digests["program_inventory_digest"],
        membership_degree_digest=digests["membership_degree_digest"],
        reference_tensor_digest=digests["reference_tensor_digest"],
        centering_scaling_digest=digests["centering_scaling_digest"],
        reference_design_digest=digests["reference_design_digest"],
        equal_membership_design_digest=digests["equal_membership_design_digest"],
        global_loading_digest=digests["global_loading_digest"],
        conditional_loading_digest=digests["conditional_loading_digest"],
        fold_policy_digest=digests["fold_policy_digest"],
        source_processing_ablation_digest=digests["source_processing_ablation_digest"],
        bootstrap_seed_namespace_digest=digests["bootstrap_seed_namespace_digest"],
        bootstrap_ensemble_digest=digests["bootstrap_ensemble_digest"],
        evaluation_digest=digests["evaluation_digest"],
        numpy_version=numpy_version,
    )


__all__ = [
    "FittedBootstrapDraw",
    "FittedProgramLoading",
    "NeftelProgramFittedCatalog",
    "neftel_program_fitted_catalog",
]
