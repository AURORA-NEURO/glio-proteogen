"""Fail-closed catalog for the fitted KNCC Reactome transition model."""

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
    EXPECTED_PATHWAY_COUNT,
    PROFILE_ID,
    ReactomeTransitionSourceCatalog,
    reactome_transition_source_catalog,
)
from .errors import ReactomeConditionalModelIntegrityError

FloatArray = NDArray[np.float64]
Float32Array = NDArray[np.float32]
IntArray = NDArray[np.int64]
Int16Array = NDArray[np.int16]
BoolArray = NDArray[np.bool_]

ARTIFACT_RESOURCE: Final = "data/kncc_reactome_conditional_transition_model.v1.json"
MODEL_ID: Final = "kncc-reactome-conditional-transition-model/1.0.0"
SCHEMA_VERSION: Final = (
    "glio-proteogen.kncc-reactome-conditional-transition-model/1.0.0"
)
EXPECTED_ARTIFACT_BYTES: Final = 4_434_141
EXPECTED_ARTIFACT_SHA256: Final = (
    "sha256:16f2e417f82d6c45dc413ed5516e073ee6c17de26cc0156db8918cfd57eca27f"
)
EXPECTED_CONTENT_DIGEST: Final = (
    "sha256:74cb8b63dbdd7d321fb55e1439bb7cf73bfae415edbdd53fab150f06a00dfd7b"
)
EXPECTED_TRAINING_RECIPE_DIGEST: Final = (
    "sha256:08397554469edfab42318dc819ddabae910885a0cca00b160819254264540960"
)
EXPECTED_UNION_FEATURE_DIGEST: Final = (
    "sha256:70914c9ad594dcb91c2ce05f151ebc844fa855fb041b2fc3ff56513586833e18"
)
EXPECTED_REFERENCE_TENSOR_DIGEST: Final = (
    "sha256:a3b71346a57a81446f6a7f227085e52cc74c1ac5eb8203b80fbac96a46612059"
)
EXPECTED_CENTERING_SCALING_DIGEST: Final = (
    "sha256:c09fee9acd5a3e44809b2853021fb44ca791fc084bccf8e13a0018477138bf84"
)
EXPECTED_REFERENCE_DESIGN_DIGEST: Final = (
    "sha256:1ede6b62b9d07d7c3910edde63890bf2fa9c61c1e1d5f7c785de228f401fd628"
)
EXPECTED_GLOBAL_LOADING_DIGEST: Final = (
    "sha256:500e2eaf66168a42f42385c572081f795914ee01def4184c9eba997865ebd171"
)
EXPECTED_CONDITIONAL_LOADING_DIGEST: Final = (
    "sha256:5dd54df9457e31db22cb266cbe2e13b5fb2da8fffafd656765d3693a5c365764"
)
EXPECTED_FOLD_POLICY_DIGEST: Final = (
    "sha256:c4be27c67a6df739d59feb15e6f04105b67b87d0cc0099d9371a3a6ef3db5977"
)
EXPECTED_SOURCE_PROCESSING_ABLATION_DIGEST: Final = (
    "sha256:533122392865e596e2fed0abdab0a0d2a191293067eef28b00fc6aaac47522a3"
)
EXPECTED_BOOTSTRAP_ENSEMBLE_DIGEST: Final = (
    "sha256:53e44131ea0bb159175a889dcfdc07d941f568e59439a807ad5d82fc38707a3f"
)
EXPECTED_EVALUATION_DIGEST: Final = (
    "sha256:6bf513badfd1c005e70718d98e1dd83c6b987b32596d1f13fc33909f2ce8ea69"
)
EXPECTED_UNION_FEATURE_COUNT: Final = 1_872
EXPECTED_BOOTSTRAP_REPLICATES: Final = 256
EXPECTED_DESIGN_COLUMNS: Final = EXPECTED_PATHWAY_COUNT + 1
EXPECTED_SOLVER_MAX_ITERATIONS: Final = 200


@dataclass(frozen=True, slots=True)
class FittedPathwayLoading:
    """One fitted conditional loading and its transparent decomposition."""

    panel_index: int
    domain_id: str
    reactome_id: str
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
class ReactomeConditionalFittedCatalog:
    """Verified fitted aggregate model with no patient-level source values."""

    profile_id: str
    model_id: str
    source_catalog: ReactomeTransitionSourceCatalog
    union_feature_indices: tuple[int, ...]
    union_gene_symbols: tuple[str, ...]
    local_index_by_feature: Mapping[int, int]
    membership_degree: FloatArray
    pathways: tuple[FittedPathwayLoading, ...]
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
    training_recipe_digest: str
    union_feature_digest: str
    reference_tensor_digest: str
    centering_scaling_digest: str
    reference_design_digest: str
    global_loading_digest: str
    conditional_loading_digest: str
    fold_policy_digest: str
    source_processing_ablation_digest: str
    bootstrap_ensemble_digest: str
    evaluation_digest: str
    numpy_version: str

    @property
    def union_feature_count(self) -> int:
        return len(self.union_feature_indices)

    @property
    def pathway_count(self) -> int:
        return len(self.pathways)

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
            tuple(item.member_local_indices for item in self.pathways),
            self.membership_degree,
        )
        return _readonly(design)


def _fail(message: str) -> Never:
    raise ReactomeConditionalModelIntegrityError(message)


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
        return MappingProxyType(
            {key: _deep_freeze(child) for key, child in document.items()}
        )
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
        raise ReactomeConditionalModelIntegrityError(
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


def _source_binding(
    document: dict[str, object],
    source: ReactomeTransitionSourceCatalog,
) -> None:
    binding = _object(document.get("source_catalog_binding"), "source_catalog_binding")
    expected = {
        "artifact_byte_digest": source.artifact_byte_digest,
        "content_digest": source.content_digest,
        "source_binding_digest": source.source_binding_digest,
        "selection_candidate_digest": source.selection_candidate_digest,
        "pathway_order_digest": source.pathway_order_digest,
        "pathway_membership_digest": source.pathway_membership_digest,
        "gene_order_digest": source.gene_order_digest,
        "patient_order_rule_digest": source.patient_order_rule_digest,
    }
    if binding != expected:
        _fail("fitted artifact source-catalog binding mismatch")


def _locked_digests(document: dict[str, object]) -> dict[str, str]:
    values = _object(document.get("digests"), "digests")
    expected = {
        "training_recipe_digest": EXPECTED_TRAINING_RECIPE_DIGEST,
        "union_feature_digest": EXPECTED_UNION_FEATURE_DIGEST,
        "reference_tensor_digest": EXPECTED_REFERENCE_TENSOR_DIGEST,
        "centering_scaling_digest": EXPECTED_CENTERING_SCALING_DIGEST,
        "reference_design_digest": EXPECTED_REFERENCE_DESIGN_DIGEST,
        "global_loading_digest": EXPECTED_GLOBAL_LOADING_DIGEST,
        "conditional_loading_digest": EXPECTED_CONDITIONAL_LOADING_DIGEST,
        "fold_policy_digest": EXPECTED_FOLD_POLICY_DIGEST,
        "source_processing_ablation_digest": EXPECTED_SOURCE_PROCESSING_ABLATION_DIGEST,
        "bootstrap_ensemble_digest": EXPECTED_BOOTSTRAP_ENSEMBLE_DIGEST,
        "evaluation_digest": EXPECTED_EVALUATION_DIGEST,
    }
    if values != expected:
        _fail("fitted artifact locked digest inventory mismatch")
    return expected


@lru_cache(maxsize=1)
def reactome_conditional_fitted_catalog() -> ReactomeConditionalFittedCatalog:  # noqa: PLR0915
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
        raise ReactomeConditionalModelIntegrityError(
            "fitted artifact is not valid JSON"
        ) from error
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
        != "de-identified fitted conditional protein-transition concordance model"
    ):
        _fail("fitted artifact identity mismatch")
    source = reactome_transition_source_catalog()
    _source_binding(document, source)
    digests = _locked_digests(document)

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
        or fold_policy.get("held_gene_folds") != 5
    ):
        _fail("fitted training recipe or fold policy mismatch")

    counts = _object(document.get("counts"), "counts")
    if counts != {
        "source_patient_pairs": 104,
        "source_gene_features": EXPECTED_GENE_COUNT,
        "union_features": EXPECTED_UNION_FEATURE_COUNT,
        "pathways": EXPECTED_PATHWAY_COUNT,
        "bootstrap_replicates": EXPECTED_BOOTSTRAP_REPLICATES,
    }:
        _fail("fitted model count inventory mismatch")
    union = tuple(
        _integer(value, "union feature index")
        for value in _array(document.get("union_feature_indices"), "union features")
    )
    expected_union = tuple(
        sorted(
            set().union(
                *(set(pathway.member_feature_indices) for pathway in source.pathways)
            )
        )
    )
    if union != expected_union or _digest(list(union)) != digests["union_feature_digest"]:
        _fail("fitted union feature axis mismatch")
    local = {feature: index for index, feature in enumerate(union)}
    members = tuple(
        tuple(local[index] for index in pathway.member_feature_indices)
        for pathway in source.pathways
    )
    degree = np.zeros(len(union), dtype=np.float64)
    for positions in members:
        degree[np.asarray(positions, dtype=np.int64)] += 1.0
    if np.any(degree < 1.0):
        _fail("fitted membership degree is invalid")

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
    ):
        _fail("fitted reference tensor domain mismatch")
    if _digest(tensors) != digests["reference_tensor_digest"]:
        _fail("fitted reference tensor digest mismatch")
    centering_scaling = {
        key: tensors[key] for key in ("scale", "support", "eligible")
    }
    if _digest(centering_scaling) != digests["centering_scaling_digest"]:
        _fail("fitted centering/scaling digest mismatch")
    design, decompositions = _derive_design(
        reference_effect,
        reference_eligible,
        members,
        degree,
    )
    design_bytes = np.ascontiguousarray(design, dtype="<f8").tobytes()
    if (
        _raw_digest(design_bytes) != digests["reference_design_digest"]
        or reference.get("design_raw_sha256") != digests["reference_design_digest"]
        or _raw_digest(
            np.ascontiguousarray(design[:, 0], dtype="<f8").tobytes()
        )
        != digests["global_loading_digest"]
        or _raw_digest(
            np.ascontiguousarray(design[:, 1:], dtype="<f8").tobytes()
        )
        != digests["conditional_loading_digest"]
        or not math.isclose(
            _finite(reference.get("design_condition_number"), "design condition"),
            float(np.linalg.cond(design)),
            abs_tol=5.0e-11,
        )
    ):
        _fail("fitted reference loading digest or condition mismatch")

    processing = _object(
        document.get("source_processing_ablation"), "source processing ablation"
    )
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
    if _digest(ordinary_tensor) != digests["source_processing_ablation_digest"]:
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
        str(value)
        for value in _array(bootstrap.get("row_digests"), "bootstrap row digests")
    )
    if (
        len(row_digests) != EXPECTED_BOOTSTRAP_REPLICATES
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
    if (
        _digest(evaluation) != digests["evaluation_digest"]
        or evaluation.get("evaluation_count") != 520
        or evaluation.get("minimum_finite_held_gene_count") != 310
        or evaluation.get("minimum_finite_inference_gene_count") != 1_279
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
    expected_components = {"global_recurrence"} | {
        item.reactome_id for item in source.pathways
    }
    if set(scales) != expected_components:
        _fail("cross-fitted coordinate component inventory mismatch")

    pathway_loadings: list[FittedPathwayLoading] = []
    for pathway, positions, decomposition in zip(
        source.pathways,
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
        pathway_loadings.append(
            FittedPathwayLoading(
                panel_index=pathway.panel_index,
                domain_id=pathway.domain_id,
                reactome_id=pathway.reactome_id,
                name=pathway.name,
                member_local_indices=positions,
                unique_member_local_indices=unique,
                unadjusted_loading=unadjusted,
                global_projection=projection,
                residual_norm=residual_norm,
                global_adjustment_loading=adjustment,
                conditional_loading=conditional,
                ordinary_conditional_loading=_readonly(
                    ordinary_design[:, pathway.panel_index + 1]
                    / math.sqrt(len(union))
                ),
                no_degree_conditional_loading=_readonly(
                    no_degree_design[:, pathway.panel_index + 1]
                    / math.sqrt(len(union))
                ),
                cross_fitted_mad_scale=scales[pathway.reactome_id],
            )
        )
    for array_value in (design, ordinary_design, no_degree_design, degree):
        array_value.flags.writeable = False

    privacy = _object(document.get("privacy"), "privacy")
    if any(value is not False for value in privacy.values()) or len(privacy) != 5:
        _fail("fitted artifact privacy declaration mismatch")
    limitations = tuple(
        str(value) for value in _array(document.get("limitations"), "limitations")
    )
    if len(limitations) < 8 or not all(limitations):
        _fail("fitted artifact limitation inventory mismatch")
    provenance = _object(document.get("provenance"), "provenance")
    numpy_version = str(provenance.get("numpy_version"))
    if numpy_version != np.__version__:
        _fail("fitted artifact NumPy version mismatch")
    return ReactomeConditionalFittedCatalog(
        profile_id=PROFILE_ID,
        model_id=MODEL_ID,
        source_catalog=source,
        union_feature_indices=union,
        union_gene_symbols=tuple(source.genes[index] for index in union),
        local_index_by_feature=MappingProxyType(local),
        membership_degree=_readonly(degree),
        pathways=tuple(pathway_loadings),
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
        cross_fitted_coordinate_scales=MappingProxyType(scales),
        evaluation=cast("Mapping[str, object]", _deep_freeze(evaluation)),
        limitations=limitations,
        artifact_bytes=len(payload),
        artifact_byte_digest=artifact_byte_digest,
        content_digest=content_digest,
        training_recipe_digest=digests["training_recipe_digest"],
        union_feature_digest=digests["union_feature_digest"],
        reference_tensor_digest=digests["reference_tensor_digest"],
        centering_scaling_digest=digests["centering_scaling_digest"],
        reference_design_digest=digests["reference_design_digest"],
        global_loading_digest=digests["global_loading_digest"],
        conditional_loading_digest=digests["conditional_loading_digest"],
        fold_policy_digest=digests["fold_policy_digest"],
        source_processing_ablation_digest=digests[
            "source_processing_ablation_digest"
        ],
        bootstrap_ensemble_digest=digests["bootstrap_ensemble_digest"],
        evaluation_digest=digests["evaluation_digest"],
        numpy_version=numpy_version,
    )


__all__ = [
    "FittedBootstrapDraw",
    "FittedPathwayLoading",
    "ReactomeConditionalFittedCatalog",
    "reactome_conditional_fitted_catalog",
]
