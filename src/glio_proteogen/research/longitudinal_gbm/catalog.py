"""Fail-closed access to the frozen KNCC protein-transition artifact.

The catalog deliberately exposes only de-identified protein model parameters.  It
verifies the packaged bytes and every projection used by the numerical engine before
constructing immutable Python objects.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from typing import Final, Literal, Mapping, Never, cast

from .canonical import canonical_json_bytes, sha256_digest
from .errors import SourceProfileIntegrityError

CATALOG_RESOURCE: Final = "data/kncc_paired_protein_transition.v1.json"
EXPECTED_ARTIFACT_BYTE_DIGEST: Final = (
    "sha256:cc965d9e9d0f7ab3e1ec7dda151bc3d5b442bbbd8cab12ee4b0f3497e860ae40"
)
EXPECTED_ARTIFACT_BYTES: Final = 5_328_605
EXPECTED_CONTENT_DIGEST: Final = (
    "sha256:5583ee3a1d75bcd3997d12ff2102ec19fd83e49b2ec98f4f2bd9a0b6475d92a3"
)
EXPECTED_SOURCE_FILE_LOCK_DIGEST: Final = (
    "sha256:0f96d71db83a90934f38960ebd41e7580e817c435bf7e03479b061a0a68d6964"
)
EXPECTED_COHORT_ORACLE_DIGEST: Final = (
    "sha256:a0b8ed89e9149210c8651770c6b4a2a0cc43e455a69d4af4390af4b2307409ea"
)
EXPECTED_FEATURE_SPACE_DIGEST: Final = (
    "sha256:d585de04d6da666f03cc66e2d3ae8395e9b9cbb1cf2409a7e0721f8b9e3ea148"
)
EXPECTED_TRANSITION_MODEL_DIGEST: Final = (
    "sha256:81cbb9ddc56ddf0925dccac748151c4459e6209ba5bdcb9d7962eae081c0988e"
)
EXPECTED_COEFFICIENT_DIGEST: Final = (
    "sha256:8e8dfb9d33a65d4fe02008ef878fa80ba1bbc9ad2c22381e0d9e33504f0833a0"
)
EXPECTED_BOOTSTRAP_DIGEST: Final = (
    "sha256:ce51e5a35eeee523283f6b22638afc341b48694ea4beebb28fa95e436db26f36"
)
EXPECTED_SOURCE_PROCESSING_ABLATION_DIGEST: Final = (
    "sha256:d7ca30bd3aba82f61970549fb7f739ffe6db99d0d1623f80cac73a369db7c72c"
)
EXPECTED_SOURCE_PROCESSING_PROJECTION_DIGEST: Final = (
    "sha256:8a412506a2d946976c7d60f83d6f18a929800177f5702942943ab6ce7edb3368"
)
EXPECTED_HGNC_COMPLETE_SET_DIGEST: Final = (
    "sha256:854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270"
)
EXPECTED_SCHEMA_VERSION: Final = "glio-proteogen.kncc-paired-protein-transition-artifact/1.0.0"
EXPECTED_MODEL_ID: Final = "kncc-paired-protein-transition/1.0.0"
EXPECTED_FEATURE_COUNT: Final = 11_312
EXPECTED_ELIGIBLE_FEATURE_COUNT: Final = 10_002
EXPECTED_SELECTED_FEATURE_COUNT: Final = 128
EXPECTED_BOOTSTRAP_REPLICATES: Final = 512
EXPECTED_SOURCE_PAIR_COUNT: Final = 104
EXPECTED_SOURCE_MANIFEST_DIGEST: Final = (
    "sha256:03d41fffeb04749296a95bd5cd5dd5829ddedc5f8f791941c011b94d6836a247"
)

_FEATURE_SPACE_KEYS: Final = (
    "gene_symbol",
    "hgnc_id",
    "source_gene_label",
    "mapping_basis",
)
_TRANSITION_PARAMETER_KEYS: Final = (
    "gene_symbol",
    "transition_center",
    "transition_scale",
    "paired_support",
    "paired_coverage",
    "unshared_peptides",
    "eligible",
)
_COEFFICIENT_KEYS: Final = ("gene_symbol", "selected", "coefficient")
_SEED_PATTERN: Final = re.compile(r"^[0-9a-f]{16}$")


@dataclass(frozen=True, slots=True)
class KnccProteinFeature:
    """One approved HGNC protein feature and its frozen source-model parameters."""

    index: int
    gene_symbol: str
    hgnc_id: str
    source_gene_label: str
    mapping_basis: str
    transition_center: float
    transition_scale: float
    paired_support: int
    paired_coverage: float
    unshared_peptides: int
    eligible: bool
    selected: bool
    coefficient: float
    bootstrap_selection_stability: float
    coefficient_interval_90: tuple[float, float, float]
    ensemble_mean_coefficient: float
    ensemble_mean_absolute_coefficient: float


@dataclass(frozen=True, slots=True)
class SparseCoefficientReplicate:
    """One immutable, sparse source-cohort bootstrap coefficient vector."""

    replicate_index: int
    seed_hex: str
    intercept: float
    feature_indices: tuple[int, ...]
    coefficients: tuple[float, ...]
    replicate_digest: str


@dataclass(frozen=True, slots=True)
class SourceProcessingSensitivity:
    """Locked aggregate ordinary-Log versus Unshared-Log sensitivity evidence."""

    comparison: str
    ablation_id: str
    ablation_kind: str
    feature_indices: tuple[int, ...]
    coefficients: tuple[float, ...]
    transition_scales: tuple[float, ...]
    projection_digest: str
    coefficient_cosine: float
    paired_score_rank_correlation: float
    selected_feature_jaccard: float
    selected_feature_overlap: int
    supported_pair_count: int


@dataclass(frozen=True, slots=True)
class KnccLongitudinalCatalog:
    """Verified model material consumed by the longitudinal inference engine."""

    model_id: str
    features: tuple[KnccProteinFeature, ...]
    features_by_symbol: Mapping[str, KnccProteinFeature]
    bootstrap_replicates: tuple[SparseCoefficientReplicate, ...]
    ensemble_feature_indices: frozenset[int]
    source_processing_sensitivity: SourceProcessingSensitivity
    artifact_byte_digest: str
    content_digest: str
    source_file_lock_digest: str
    cohort_oracle_digest: str
    feature_space_digest: str
    transition_model_digest: str
    coefficient_digest: str
    bootstrap_digest: str
    source_processing_ablation_digest: str
    hgnc_complete_set_digest: str
    source_to_hgnc_mapping_digest: str
    source_file_count: int
    excluded_specimen_label_count: Literal[6]
    excluded_patient_group_count: Literal[5]
    fitted_feature_count: int
    nonzero_coefficient_count: int
    nested_cv_outer_folds: int
    nested_cv_inner_folds: int
    source_attribution: str
    source_license: str
    source_license_url: str
    source_transformation_notice: str


def _resource_bytes() -> bytes:
    return files(__package__).joinpath(CATALOG_RESOURCE).read_bytes()


def _fail(message: str) -> Never:
    raise SourceProfileIntegrityError(message)


def _content_digest(document: dict[str, object]) -> str:
    projection = dict(document)
    projection.pop("artifact_digest", None)
    payload = canonical_json_bytes(projection) + b"\n"
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _feature_projection(
    feature_documents: list[dict[str, object]],
    keys: tuple[str, ...],
) -> list[dict[str, object]]:
    return [{key: item[key] for key in keys} for item in feature_documents]


def _validate_topology(
    document: dict[str, object],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, object],
    dict[str, object],
]:
    if document.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        _fail("unsupported KNCC protein-transition artifact schema")
    if document.get("model_id") != EXPECTED_MODEL_ID:
        _fail("KNCC protein-transition model identifier mismatch")
    feature_value = document.get("features")
    bootstrap_value = document.get("bootstrap")
    if not isinstance(feature_value, list) or not isinstance(bootstrap_value, dict):
        _fail("KNCC artifact feature or bootstrap inventory is malformed")
    ensemble_value = bootstrap_value.get("coefficient_ensemble")
    if not isinstance(ensemble_value, dict):
        _fail("KNCC artifact sparse bootstrap ensemble is malformed")
    replicate_value = ensemble_value.get("replicates")
    if not isinstance(replicate_value, list):
        _fail("KNCC artifact feature or bootstrap inventory is malformed")
    feature_documents = cast("list[dict[str, object]]", feature_value)
    bootstrap = cast("dict[str, object]", bootstrap_value)
    ensemble = cast("dict[str, object]", ensemble_value)
    replicate_documents = cast("list[dict[str, object]]", replicate_value)
    if len(feature_documents) != EXPECTED_FEATURE_COUNT:
        _fail("KNCC HGNC feature count mismatch")
    if len(replicate_documents) != EXPECTED_BOOTSTRAP_REPLICATES:
        _fail("KNCC bootstrap replicate count mismatch")
    return feature_documents, replicate_documents, bootstrap, ensemble


def _validate_projection_digests(
    document: dict[str, object],
    feature_documents: list[dict[str, object]],
    replicate_documents: list[dict[str, object]],
    ensemble: dict[str, object],
) -> tuple[str, str, str, str, str, str, str]:
    source_lock = cast("dict[str, object]", document["source_lock"])
    cohort_oracles = cast("dict[str, object]", document["cohort_oracles"])
    feature_digest = sha256_digest(_feature_projection(feature_documents, _FEATURE_SPACE_KEYS))
    transition_digest = sha256_digest(
        {
            "preprocessing": document["preprocessing"],
            "hyperparameters": document["hyperparameters"],
            "fit": document["fit"],
            "feature_parameters": _feature_projection(
                feature_documents,
                _TRANSITION_PARAMETER_KEYS,
            ),
        }
    )
    coefficient_digest = sha256_digest(
        {
            "coefficient_normalization": cast("dict[str, object]", document["fit"])[
                "coefficient_normalization"
            ],
            "coefficients": _feature_projection(feature_documents, _COEFFICIENT_KEYS),
        }
    )
    source_lock_digest = sha256_digest(source_lock)
    cohort_digest = sha256_digest(cohort_oracles)
    bootstrap_digest = sha256_digest(replicate_documents)
    source_processing_digest = sha256_digest(document["ordinary_log_ablation"])
    expected = (
        (source_lock_digest, EXPECTED_SOURCE_FILE_LOCK_DIGEST, "source-file lock"),
        (cohort_digest, EXPECTED_COHORT_ORACLE_DIGEST, "cohort oracle"),
        (feature_digest, EXPECTED_FEATURE_SPACE_DIGEST, "HGNC feature-space"),
        (transition_digest, EXPECTED_TRANSITION_MODEL_DIGEST, "transition model"),
        (coefficient_digest, EXPECTED_COEFFICIENT_DIGEST, "central coefficient"),
        (bootstrap_digest, EXPECTED_BOOTSTRAP_DIGEST, "bootstrap ensemble"),
        (
            source_processing_digest,
            EXPECTED_SOURCE_PROCESSING_ABLATION_DIGEST,
            "source-processing ablation",
        ),
    )
    for actual, locked, label in expected:
        if actual != locked:
            _fail(f"KNCC {label} projection digest mismatch")
    if ensemble.get("ensemble_digest") != bootstrap_digest:
        _fail("KNCC self-declared bootstrap ensemble digest mismatch")
    return (
        source_lock_digest,
        cohort_digest,
        feature_digest,
        transition_digest,
        coefficient_digest,
        bootstrap_digest,
        source_processing_digest,
    )


def _validate_source_invariants(document: dict[str, object]) -> None:
    cohort = cast("dict[str, object]", document["cohort_oracles"])
    expected_counts = {
        "matrix_unique_row_labels": 11_323,
        "source_biological_gene_labels": 11_320,
        "aggregate_rows_excluded_from_fit": ["Mean", "Median", "StdDev"],
        "strict_t1_t2_pairs": EXPECTED_SOURCE_PAIR_COUNT,
        "source_biological_specimen_labels": 214,
        "excluded_specimen_labels": 6,
        "excluded_patient_groups": 5,
        "incomplete_patient_groups_excluded": 4,
        "sample_type_mismatch_patient_groups_excluded": 1,
        "official_versioned_biospecimen_records": 216,
        "official_versioned_biological_specimen_labels": 214,
        "official_sample_type_mismatch_patient_groups": 1,
        "official_versioned_file_manifest_records": 2_503,
        "hgnc_exact_approved_symbols": 11_232,
        "hgnc_unique_previous_or_alias_mappings": 80,
        "hgnc_ambiguous_labels_excluded": 4,
        "hgnc_unresolved_labels_excluded": 4,
        "hgnc_colliding_approved_symbols_excluded": 0,
        "hgnc_admitted_unique_approved_symbols": EXPECTED_FEATURE_COUNT,
    }
    if any(cohort.get(key) != value for key, value in expected_counts.items()):
        _fail("KNCC audited source/cohort cardinality mismatch")
    source_lock = cast("dict[str, object]", document["source_lock"])
    source_files = cast("list[dict[str, object]]", source_lock.get("files"))
    source_manifest = source_lock.get("versioned_source_manifest")
    if (
        source_lock.get("pdc_study_id") != "PDC000514"
        or source_lock.get("pdc_study_version_uuid") != "524d5116-b6de-4e36-892a-e35dba7d0170"
        or not isinstance(source_files, list)
        or len(source_files) != 3
        or any(
            item.get("uuid_size_md5_binding") != "versioned_source_manifest"
            for item in source_files
        )
        or not isinstance(source_manifest, dict)
    ):
        _fail("KNCC PDC source lock mismatch")
    manifest = cast("dict[str, object]", source_manifest)
    if (
        manifest.get("schema_version") != "glio-proteogen.pdc000514-source-manifest/1.0.0"
        or manifest.get("sha256") != EXPECTED_SOURCE_MANIFEST_DIGEST
        or manifest.get("bytes") != 1_362_739
        or manifest.get("biospecimen_response_records") != 216
        or manifest.get("file_manifest_response_records") != 2_503
    ):
        _fail("KNCC versioned biospecimen/file manifest lock mismatch")
    gene_identity = cast("dict[str, object]", document["gene_identity"])
    if (
        gene_identity.get("authority") != "HGNC complete set"
        or gene_identity.get("authority_sha256") != EXPECTED_HGNC_COMPLETE_SET_DIGEST
        or gene_identity.get("mapping_digest") != EXPECTED_FEATURE_SPACE_DIGEST
        or cohort.get("hgnc_mapping_digest") != EXPECTED_FEATURE_SPACE_DIGEST
    ):
        _fail("KNCC HGNC authority or mapping lock mismatch")


def _validate_feature_documents(feature_documents: list[dict[str, object]]) -> None:
    symbols = [cast("str", item.get("gene_symbol")) for item in feature_documents]
    source_labels = [cast("str", item.get("source_gene_label")) for item in feature_documents]
    hgnc_ids = [cast("str", item.get("hgnc_id")) for item in feature_documents]
    if len(set(symbols)) != EXPECTED_FEATURE_COUNT:
        _fail("KNCC ordered HGNC feature axis must contain unique symbols")
    if len(set(source_labels)) != EXPECTED_FEATURE_COUNT:
        _fail("KNCC source protein labels must be unique")
    if len(set(hgnc_ids)) != EXPECTED_FEATURE_COUNT:
        _fail("KNCC HGNC identifiers must be unique")
    eligible_count = 0
    selected_count = 0
    coefficient_l1 = 0.0
    for item in feature_documents:
        scale = float(cast("float | int", item.get("transition_scale")))
        center = float(cast("float | int", item.get("transition_center")))
        support = cast("int", item.get("paired_support"))
        coverage = float(cast("float | int", item.get("paired_coverage")))
        coefficient = float(cast("float | int", item.get("coefficient")))
        interval = cast("list[float]", item.get("coefficient_interval_90"))
        eligible = item.get("eligible") is True
        selected = item.get("selected") is True
        if (
            not math.isfinite(scale)
            or scale <= 0.0
            or not math.isfinite(center)
            or type(support) is not int
            or not 0 <= support <= EXPECTED_SOURCE_PAIR_COUNT
            or not math.isclose(
                coverage,
                support / EXPECTED_SOURCE_PAIR_COUNT,
                abs_tol=5e-9,
            )
            or type(interval) is not list
            or len(interval) != 3
            or any(not math.isfinite(float(value)) for value in interval)
            or list(interval) != sorted(interval)
            or not math.isfinite(coefficient)
            or (selected != (coefficient != 0.0))
            or (selected and not eligible)
        ):
            _fail("KNCC feature parameter invariant mismatch")
        eligible_count += eligible
        selected_count += selected
        coefficient_l1 += abs(coefficient)
    if (
        eligible_count != EXPECTED_ELIGIBLE_FEATURE_COUNT
        or selected_count != EXPECTED_SELECTED_FEATURE_COUNT
        or not math.isclose(coefficient_l1, 1.0, abs_tol=2e-7)
    ):
        _fail("KNCC fitted feature/coefficient inventory mismatch")


def _validate_source_processing_projection(document: dict[str, object]) -> None:
    ablation = cast("dict[str, object]", document["ordinary_log_ablation"])
    projection_value = ablation.get("frozen_projection")
    if not isinstance(projection_value, dict):
        _fail("KNCC source-processing frozen projection is malformed")
    projection = cast("dict[str, object]", projection_value)
    declared_digest = cast("str", projection.get("projection_digest"))
    digest_projection = dict(projection)
    digest_projection.pop("projection_digest", None)
    indices = cast("list[int]", projection.get("feature_indices"))
    coefficients = cast("list[float]", projection.get("coefficients"))
    scales = cast("list[float]", projection.get("transition_scales"))
    if (
        ablation.get("ablation_family") != "source_processing"
        or ablation.get("ablation_kind") != "identification_ambiguity_and_shared_peptide_inclusion"
        or declared_digest != EXPECTED_SOURCE_PROCESSING_PROJECTION_DIGEST
        or sha256_digest(digest_projection) != EXPECTED_SOURCE_PROCESSING_PROJECTION_DIGEST
        or not isinstance(indices, list)
        or not isinstance(coefficients, list)
        or not isinstance(scales, list)
        or len(indices) != EXPECTED_SELECTED_FEATURE_COUNT
        or len(coefficients) != EXPECTED_SELECTED_FEATURE_COUNT
        or len(scales) != EXPECTED_SELECTED_FEATURE_COUNT
        or indices != sorted(set(indices))
        or any(
            type(index) is not int or not 0 <= index < EXPECTED_FEATURE_COUNT for index in indices
        )
        or any(not math.isfinite(float(value)) or float(value) == 0.0 for value in coefficients)
        or any(not math.isfinite(float(value)) or float(value) <= 0.0 for value in scales)
        or not math.isclose(
            math.fsum(abs(float(value)) for value in coefficients),
            1.0,
            abs_tol=2e-7,
        )
        or projection.get("intercept") != 0.0
    ):
        _fail("KNCC source-processing projection invariant mismatch")


def _parse_replicates(
    replicate_documents: list[dict[str, object]],
) -> tuple[SparseCoefficientReplicate, ...]:
    parsed: list[SparseCoefficientReplicate] = []
    seeds: set[str] = set()
    for expected_index, item in enumerate(replicate_documents):
        projection = dict(item)
        declared_digest = cast("str", projection.pop("replicate_digest", None))
        indices = cast("list[int]", item.get("feature_indices"))
        coefficients = cast("list[float]", item.get("coefficients"))
        seed_hex = cast("str", item.get("seed_hex"))
        if (
            item.get("replicate_index") != expected_index
            or sha256_digest(projection) != declared_digest
            or not isinstance(indices, list)
            or not isinstance(coefficients, list)
            or len(indices) != EXPECTED_SELECTED_FEATURE_COUNT
            or len(coefficients) != EXPECTED_SELECTED_FEATURE_COUNT
            or indices != sorted(set(indices))
            or any(
                type(index) is not int or not 0 <= index < EXPECTED_FEATURE_COUNT
                for index in indices
            )
            or any(not math.isfinite(float(value)) or float(value) == 0.0 for value in coefficients)
            or not math.isclose(
                math.fsum(abs(float(value)) for value in coefficients),
                1.0,
                abs_tol=2e-7,
            )
            or item.get("intercept") != 0.0
            or not isinstance(seed_hex, str)
            or _SEED_PATTERN.fullmatch(seed_hex) is None
            or seed_hex in seeds
        ):
            _fail("KNCC sparse bootstrap replicate invariant mismatch")
        seeds.add(seed_hex)
        parsed.append(
            SparseCoefficientReplicate(
                replicate_index=expected_index,
                seed_hex=seed_hex,
                intercept=0.0,
                feature_indices=tuple(indices),
                coefficients=tuple(float(value) for value in coefficients),
                replicate_digest=declared_digest,
            )
        )
    return tuple(parsed)


def _build_features(
    feature_documents: list[dict[str, object]],
    replicates: tuple[SparseCoefficientReplicate, ...],
) -> tuple[KnccProteinFeature, ...]:
    coefficient_sums = [0.0] * EXPECTED_FEATURE_COUNT
    absolute_sums = [0.0] * EXPECTED_FEATURE_COUNT
    for replicate in replicates:
        for index, coefficient in zip(
            replicate.feature_indices,
            replicate.coefficients,
            strict=True,
        ):
            coefficient_sums[index] += coefficient
            absolute_sums[index] += abs(coefficient)
    denominator = float(len(replicates))
    result: list[KnccProteinFeature] = []
    for index, item in enumerate(feature_documents):
        interval = cast("list[float]", item["coefficient_interval_90"])
        result.append(
            KnccProteinFeature(
                index=index,
                gene_symbol=cast("str", item["gene_symbol"]),
                hgnc_id=cast("str", item["hgnc_id"]),
                source_gene_label=cast("str", item["source_gene_label"]),
                mapping_basis=cast("str", item["mapping_basis"]),
                transition_center=float(cast("float | int", item["transition_center"])),
                transition_scale=float(cast("float | int", item["transition_scale"])),
                paired_support=cast("int", item["paired_support"]),
                paired_coverage=float(cast("float | int", item["paired_coverage"])),
                unshared_peptides=cast("int", item["unshared_peptides"]),
                eligible=cast("bool", item["eligible"]),
                selected=cast("bool", item["selected"]),
                coefficient=float(cast("float | int", item["coefficient"])),
                bootstrap_selection_stability=float(
                    cast("float | int", item["bootstrap_selection_stability"])
                ),
                coefficient_interval_90=tuple(float(value) for value in interval),  # type: ignore[arg-type]
                ensemble_mean_coefficient=coefficient_sums[index] / denominator,
                ensemble_mean_absolute_coefficient=absolute_sums[index] / denominator,
            )
        )
    return tuple(result)


@lru_cache(maxsize=1)
def longitudinal_gbm_catalog() -> KnccLongitudinalCatalog:
    """Load and independently verify the packaged KNCC protein model."""

    raw_bytes = _resource_bytes()
    if len(raw_bytes) != EXPECTED_ARTIFACT_BYTES:
        _fail("KNCC protein-transition artifact byte length mismatch")
    artifact_byte_digest = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
    if artifact_byte_digest != EXPECTED_ARTIFACT_BYTE_DIGEST:
        _fail("KNCC protein-transition artifact byte digest mismatch")
    try:
        document = cast("dict[str, object]", json.loads(raw_bytes))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SourceProfileIntegrityError(
            "KNCC protein-transition artifact is not valid JSON"
        ) from error
    if type(document) is not dict:
        _fail("KNCC protein-transition artifact root must be an object")
    content_digest = _content_digest(document)
    if (
        content_digest != EXPECTED_CONTENT_DIGEST
        or document.get("artifact_digest") != EXPECTED_CONTENT_DIGEST
    ):
        _fail("KNCC protein-transition canonical content digest mismatch")
    feature_documents, replicate_documents, bootstrap, ensemble = _validate_topology(document)
    _validate_source_invariants(document)
    projection_digests = _validate_projection_digests(
        document,
        feature_documents,
        replicate_documents,
        ensemble,
    )
    _validate_feature_documents(feature_documents)
    _validate_source_processing_projection(document)
    if (
        bootstrap.get("requested_replicates") != EXPECTED_BOOTSTRAP_REPLICATES
        or bootstrap.get("completed_replicates") != EXPECTED_BOOTSTRAP_REPLICATES
        or ensemble.get("feature_index_basis") != "zero-based index into artifact features array"
        or ensemble.get("coefficient_quantization_decimal_places") != 8
        or ensemble.get("scale_policy")
        != "frozen full-cohort feature transition_scale; uncertainty approximation only"
        or bootstrap.get("validation_role") != "none"
        or bootstrap.get("uncertainty_role")
        != "fixed-scale one-step coefficient uncertainty approximation; not model validation"
    ):
        _fail("KNCC bootstrap metadata invariant mismatch")
    replicates = _parse_replicates(replicate_documents)
    parsed_features = _build_features(feature_documents, replicates)
    feature_mapping = MappingProxyType(
        {feature.gene_symbol: feature for feature in parsed_features}
    )
    processing = cast("dict[str, object]", document["ordinary_log_ablation"])
    source_processing_sensitivity = SourceProcessingSensitivity(
        comparison=(
            "caller observations unchanged; frozen ordinary-Log source-processing/model "
            "projection versus the primary frozen Unshared-Log projection"
        ),
        ablation_id=cast(
            "str", cast("dict[str, object]", processing["frozen_projection"])["ablation_id"]
        ),
        ablation_kind=cast("str", processing["ablation_kind"]),
        feature_indices=tuple(
            cast(
                "list[int]",
                cast("dict[str, object]", processing["frozen_projection"])["feature_indices"],
            )
        ),
        coefficients=tuple(
            float(value)
            for value in cast(
                "list[float]",
                cast("dict[str, object]", processing["frozen_projection"])["coefficients"],
            )
        ),
        transition_scales=tuple(
            float(value)
            for value in cast(
                "list[float]",
                cast("dict[str, object]", processing["frozen_projection"])["transition_scales"],
            )
        ),
        projection_digest=cast(
            "str",
            cast("dict[str, object]", processing["frozen_projection"])["projection_digest"],
        ),
        coefficient_cosine=float(cast("float", processing["coefficient_cosine"])),
        paired_score_rank_correlation=float(
            cast("float", processing["paired_score_rank_correlation"])
        ),
        selected_feature_jaccard=float(cast("float", processing["selected_feature_jaccard"])),
        selected_feature_overlap=cast("int", processing["selected_feature_overlap"]),
        supported_pair_count=cast("int", processing["supported_pair_count"]),
    )
    fit = cast("dict[str, object]", document["fit"])
    evaluation = cast("dict[str, object]", document["fit_evaluation"])
    cohort = cast("dict[str, object]", document["cohort_oracles"])
    provenance = cast("dict[str, object]", document["provenance"])
    source_lock = cast("dict[str, object]", document["source_lock"])
    return KnccLongitudinalCatalog(
        model_id=EXPECTED_MODEL_ID,
        features=parsed_features,
        features_by_symbol=feature_mapping,
        bootstrap_replicates=replicates,
        ensemble_feature_indices=frozenset(
            index for replicate in replicates for index in replicate.feature_indices
        ),
        source_processing_sensitivity=source_processing_sensitivity,
        artifact_byte_digest=artifact_byte_digest,
        content_digest=content_digest,
        source_file_lock_digest=projection_digests[0],
        cohort_oracle_digest=projection_digests[1],
        feature_space_digest=projection_digests[2],
        transition_model_digest=projection_digests[3],
        coefficient_digest=projection_digests[4],
        bootstrap_digest=projection_digests[5],
        source_processing_ablation_digest=projection_digests[6],
        hgnc_complete_set_digest=EXPECTED_HGNC_COMPLETE_SET_DIGEST,
        source_to_hgnc_mapping_digest=EXPECTED_FEATURE_SPACE_DIGEST,
        source_file_count=len(cast("list[object]", source_lock["files"])),
        excluded_specimen_label_count=cast("Literal[6]", cohort["excluded_specimen_labels"]),
        excluded_patient_group_count=cast("Literal[5]", cohort["excluded_patient_groups"]),
        fitted_feature_count=cast("int", fit["eligible_feature_count"]),
        nonzero_coefficient_count=sum(feature.coefficient != 0.0 for feature in parsed_features),
        nested_cv_outer_folds=cast("int", evaluation["outer_fold_count"]),
        nested_cv_inner_folds=cast("int", evaluation["inner_fold_count"]),
        source_attribution=(
            f"{cast('str', provenance['article_authors'])}, "
            f"{cast('str', provenance['article_title'])}"
        ),
        source_license=cast("str", provenance["license"]),
        source_license_url=cast("str", provenance["license_url"]),
        source_transformation_notice=cast("str", provenance["transformation_notice"]),
    )


def is_frozen_hgnc_symbol(gene_symbol: str) -> bool:
    """Return whether a symbol is in the exact frozen 11,312-feature inventory."""

    return gene_symbol in longitudinal_gbm_catalog().features_by_symbol


__all__ = [
    "CATALOG_RESOURCE",
    "EXPECTED_ARTIFACT_BYTES",
    "EXPECTED_ARTIFACT_BYTE_DIGEST",
    "EXPECTED_BOOTSTRAP_DIGEST",
    "EXPECTED_BOOTSTRAP_REPLICATES",
    "EXPECTED_COEFFICIENT_DIGEST",
    "EXPECTED_COHORT_ORACLE_DIGEST",
    "EXPECTED_CONTENT_DIGEST",
    "EXPECTED_ELIGIBLE_FEATURE_COUNT",
    "EXPECTED_FEATURE_COUNT",
    "EXPECTED_FEATURE_SPACE_DIGEST",
    "EXPECTED_HGNC_COMPLETE_SET_DIGEST",
    "EXPECTED_MODEL_ID",
    "EXPECTED_SCHEMA_VERSION",
    "EXPECTED_SELECTED_FEATURE_COUNT",
    "EXPECTED_SOURCE_FILE_LOCK_DIGEST",
    "EXPECTED_SOURCE_MANIFEST_DIGEST",
    "EXPECTED_SOURCE_PAIR_COUNT",
    "EXPECTED_SOURCE_PROCESSING_ABLATION_DIGEST",
    "EXPECTED_SOURCE_PROCESSING_PROJECTION_DIGEST",
    "EXPECTED_TRANSITION_MODEL_DIGEST",
    "KnccLongitudinalCatalog",
    "KnccProteinFeature",
    "SourceProcessingSensitivity",
    "SparseCoefficientReplicate",
    "is_frozen_hgnc_symbol",
    "longitudinal_gbm_catalog",
]
