from __future__ import annotations

import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, cast

import pytest

import glio_proteogen.research.longitudinal_gbm.catalog as catalog_module
import glio_proteogen.research.longitudinal_gbm.profile as profile_module
from glio_proteogen.research.longitudinal_gbm import REQUIRED_ASSAY_COMPATIBILITY
from glio_proteogen.research.longitudinal_gbm.canonical import canonical_json_bytes
from glio_proteogen.research.longitudinal_gbm.catalog import (
    EXPECTED_ARTIFACT_BYTE_DIGEST,
    EXPECTED_BOOTSTRAP_DIGEST,
    EXPECTED_CONTENT_DIGEST,
    EXPECTED_FEATURE_COUNT,
    EXPECTED_SOURCE_PROCESSING_PROJECTION_DIGEST,
    is_frozen_hgnc_symbol,
    longitudinal_gbm_catalog,
)
from glio_proteogen.research.longitudinal_gbm.demo import (
    EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST,
    demo_request_digest,
    synthetic_demo_request,
)
from glio_proteogen.research.longitudinal_gbm.errors import SourceProfileIntegrityError
from glio_proteogen.research.longitudinal_gbm.profile import (
    EXPECTED_NUMPY_VERSION,
    algorithm_profile,
    engine_semantic_digest,
)


def _artifact_document() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(catalog_module._resource_bytes()))


def _topology_copy(document: dict[str, Any]) -> dict[str, Any]:
    result = dict(document)
    result["features"] = list(document["features"])
    bootstrap = dict(document["bootstrap"])
    ensemble = dict(bootstrap["coefficient_ensemble"])
    ensemble["replicates"] = list(ensemble["replicates"])
    bootstrap["coefficient_ensemble"] = ensemble
    result["bootstrap"] = bootstrap
    return result


def _source_copy(document: dict[str, Any]) -> dict[str, Any]:
    result = dict(document)
    result["cohort_oracles"] = dict(document["cohort_oracles"])
    result["source_lock"] = dict(document["source_lock"])
    result["gene_identity"] = dict(document["gene_identity"])
    return result


def _processing_copy(document: dict[str, Any]) -> dict[str, Any]:
    result = dict(document)
    processing = dict(document["ordinary_log_ablation"])
    processing["frozen_projection"] = dict(processing["frozen_projection"])
    result["ordinary_log_ablation"] = processing
    return result


def _replicate_copy(document: dict[str, Any], index: int = 0) -> dict[str, Any]:
    source = document["bootstrap"]["coefficient_ensemble"]["replicates"][index]
    result = dict(source)
    result["feature_indices"] = list(source["feature_indices"])
    result["coefficients"] = list(source["coefficients"])
    return result


def _seal_replicate(replicate: dict[str, Any]) -> None:
    projection = dict(replicate)
    projection.pop("replicate_digest", None)
    replicate["replicate_digest"] = catalog_module.sha256_digest(projection)


def _seal_processing_projection(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, Any],
) -> None:
    projection = document["ordinary_log_ablation"]["frozen_projection"]
    digest_projection = dict(projection)
    digest_projection.pop("projection_digest", None)
    digest = catalog_module.sha256_digest(digest_projection)
    projection["projection_digest"] = digest
    monkeypatch.setattr(
        catalog_module,
        "EXPECTED_SOURCE_PROCESSING_PROJECTION_DIGEST",
        digest,
    )


def _align_projection_locks(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, Any],
) -> None:
    features = document["features"]
    replicates = document["bootstrap"]["coefficient_ensemble"]["replicates"]
    transition_projection = {
        "preprocessing": document["preprocessing"],
        "hyperparameters": document["hyperparameters"],
        "fit": document["fit"],
        "feature_parameters": catalog_module._feature_projection(
            features,
            catalog_module._TRANSITION_PARAMETER_KEYS,
        ),
    }
    coefficient_projection = {
        "coefficient_normalization": document["fit"]["coefficient_normalization"],
        "coefficients": catalog_module._feature_projection(
            features,
            catalog_module._COEFFICIENT_KEYS,
        ),
    }
    locks = {
        "EXPECTED_SOURCE_FILE_LOCK_DIGEST": catalog_module.sha256_digest(document["source_lock"]),
        "EXPECTED_COHORT_ORACLE_DIGEST": catalog_module.sha256_digest(document["cohort_oracles"]),
        "EXPECTED_FEATURE_SPACE_DIGEST": catalog_module.sha256_digest(
            catalog_module._feature_projection(
                features,
                catalog_module._FEATURE_SPACE_KEYS,
            )
        ),
        "EXPECTED_TRANSITION_MODEL_DIGEST": catalog_module.sha256_digest(transition_projection),
        "EXPECTED_COEFFICIENT_DIGEST": catalog_module.sha256_digest(coefficient_projection),
        "EXPECTED_BOOTSTRAP_DIGEST": catalog_module.sha256_digest(replicates),
        "EXPECTED_SOURCE_PROCESSING_ABLATION_DIGEST": catalog_module.sha256_digest(
            document["ordinary_log_ablation"]
        ),
    }
    for name, value in locks.items():
        monkeypatch.setattr(catalog_module, name, value)


def _install_document(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, Any],
    *,
    seal_content: bool = True,
) -> bytes:
    installed = dict(document)
    content_digest = catalog_module._content_digest(installed)
    if seal_content:
        installed["artifact_digest"] = content_digest
    encoded = canonical_json_bytes(installed) + b"\n"
    monkeypatch.setattr(catalog_module, "_resource_bytes", lambda: encoded)
    monkeypatch.setattr(
        catalog_module,
        "EXPECTED_ARTIFACT_BYTE_DIGEST",
        "sha256:" + hashlib.sha256(encoded).hexdigest(),
    )
    monkeypatch.setattr(catalog_module, "EXPECTED_ARTIFACT_BYTES", len(encoded))
    monkeypatch.setattr(catalog_module, "EXPECTED_CONTENT_DIGEST", content_digest)
    _align_projection_locks(monkeypatch, installed)
    longitudinal_gbm_catalog.cache_clear()
    return encoded


def test_catalog_locks_every_engine_projection() -> None:
    catalog = longitudinal_gbm_catalog()
    assert len(catalog.features) == EXPECTED_FEATURE_COUNT
    assert len(catalog.features_by_symbol) == EXPECTED_FEATURE_COUNT
    assert isinstance(catalog.features_by_symbol, MappingProxyType)
    assert len(catalog.bootstrap_replicates) == 512
    assert catalog.artifact_byte_digest == EXPECTED_ARTIFACT_BYTE_DIGEST
    assert catalog.content_digest == EXPECTED_CONTENT_DIGEST
    assert catalog.bootstrap_digest == EXPECTED_BOOTSTRAP_DIGEST
    assert catalog.source_to_hgnc_mapping_digest == catalog.feature_space_digest
    assert catalog.source_processing_sensitivity.projection_digest == (
        EXPECTED_SOURCE_PROCESSING_PROJECTION_DIGEST
    )
    assert len(catalog.source_processing_sensitivity.feature_indices) == 128
    assert len(catalog.source_processing_sensitivity.coefficients) == 128
    assert len(catalog.source_processing_sensitivity.transition_scales) == 128
    assert "caller observations unchanged" in catalog.source_processing_sensitivity.comparison
    assert is_frozen_hgnc_symbol(catalog.features[0].gene_symbol)
    assert not is_frozen_hgnc_symbol("NOTAREALGENE")


def test_catalog_feature_axis_is_source_ordered_unique_and_cross_referenced() -> None:
    catalog = longitudinal_gbm_catalog()
    assert tuple(feature.index for feature in catalog.features) == tuple(
        range(EXPECTED_FEATURE_COUNT)
    )
    assert len({feature.gene_symbol for feature in catalog.features}) == EXPECTED_FEATURE_COUNT
    assert any(
        catalog.features[index].gene_symbol > catalog.features[index + 1].gene_symbol
        for index in range(EXPECTED_FEATURE_COUNT - 1)
    )
    assert all(
        0 <= index < EXPECTED_FEATURE_COUNT
        for replicate in catalog.bootstrap_replicates
        for index in replicate.feature_indices
    )


def test_profile_binds_catalog_engine_demo_and_solver_semantics() -> None:
    profile = algorithm_profile()
    catalog = longitudinal_gbm_catalog()
    assert profile.model_id == catalog.model_id
    assert profile.required_assay_compatibility == REQUIRED_ASSAY_COMPATIBILITY
    assert (
        profile.required_assay_compatibility.source_profile_content_digest == catalog.content_digest
    )
    assert profile.numpy_version == EXPECTED_NUMPY_VERSION
    assert profile.demo_request_digest == demo_request_digest()
    assert profile.demo_request_digest == synthetic_demo_request().request_digest
    assert profile.demo_semantic_oracle_digest == EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST
    assert profile.digests.engine_semantic_digest == engine_semantic_digest()
    assert profile.digests.bootstrap_digest == catalog.bootstrap_digest
    assert profile.digests.source_processing_ablation_digest == (
        catalog.source_processing_ablation_digest
    )
    assert profile.constants.location_solver_iterations == 80
    assert profile.constants.location_ridge == 1e-6
    assert profile.constants.pelt_time_axis_policy == (
        "duration_normalized_transition_rates_per_90_days_v2"
    )
    assert profile.constants.pelt_minimum_segment_transitions == 2
    assert profile.constants.supported_minimum_bootstrap_replicates == 64


def test_profile_rejects_numpy_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(profile_module.np, "__version__", "0.0")
    with pytest.raises(RuntimeError, match="requires NumPy"):
        algorithm_profile()


def test_profile_rejects_assay_attestation_source_model_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incompatible = REQUIRED_ASSAY_COMPATIBILITY.model_copy(
        update={"source_profile_content_digest": "sha256:" + "0" * 64}
    )
    monkeypatch.setattr(profile_module, "REQUIRED_ASSAY_COMPATIBILITY", incompatible)
    with pytest.raises(SourceProfileIntegrityError, match="assay compatibility attestation"):
        algorithm_profile()


def test_catalog_rejects_byte_and_json_tampering(monkeypatch: pytest.MonkeyPatch) -> None:
    original = catalog_module._resource_bytes()
    longitudinal_gbm_catalog.cache_clear()
    monkeypatch.setattr(catalog_module, "_resource_bytes", lambda: original + b" ")
    with pytest.raises(SourceProfileIntegrityError, match="byte length"):
        longitudinal_gbm_catalog()

    same_length_tamper = original[:-1] + b" "
    monkeypatch.setattr(catalog_module, "_resource_bytes", lambda: same_length_tamper)
    monkeypatch.setattr(catalog_module, "EXPECTED_ARTIFACT_BYTES", len(same_length_tamper))
    longitudinal_gbm_catalog.cache_clear()
    with pytest.raises(SourceProfileIntegrityError, match="byte digest"):
        longitudinal_gbm_catalog()

    invalid = b"not-json"
    monkeypatch.setattr(catalog_module, "_resource_bytes", lambda: invalid)
    monkeypatch.setattr(catalog_module, "EXPECTED_ARTIFACT_BYTES", len(invalid))
    monkeypatch.setattr(
        catalog_module,
        "EXPECTED_ARTIFACT_BYTE_DIGEST",
        "sha256:" + hashlib.sha256(invalid).hexdigest(),
    )
    longitudinal_gbm_catalog.cache_clear()
    with pytest.raises(SourceProfileIntegrityError, match="not valid JSON"):
        longitudinal_gbm_catalog()
    longitudinal_gbm_catalog.cache_clear()


def test_catalog_independent_projection_catches_self_consistent_tamper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = json.loads(catalog_module._resource_bytes())
    document["features"][0]["transition_scale"] += 0.01
    without_digest = dict(document)
    without_digest.pop("artifact_digest")
    content_digest = (
        "sha256:" + hashlib.sha256(canonical_json_bytes(without_digest) + b"\n").hexdigest()
    )
    document["artifact_digest"] = content_digest
    encoded = canonical_json_bytes(document) + b"\n"
    monkeypatch.setattr(catalog_module, "_resource_bytes", lambda: encoded)
    monkeypatch.setattr(
        catalog_module,
        "EXPECTED_ARTIFACT_BYTE_DIGEST",
        "sha256:" + hashlib.sha256(encoded).hexdigest(),
    )
    monkeypatch.setattr(catalog_module, "EXPECTED_CONTENT_DIGEST", content_digest)
    longitudinal_gbm_catalog.cache_clear()
    with pytest.raises(SourceProfileIntegrityError, match="transition model projection"):
        longitudinal_gbm_catalog()
    longitudinal_gbm_catalog.cache_clear()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("schema", "schema"),
        ("model", "identifier"),
        ("features_type", "inventory"),
        ("bootstrap_type", "inventory"),
        ("ensemble_type", "ensemble"),
        ("replicates_type", "inventory"),
        ("feature_count", "feature count"),
        ("replicate_count", "replicate count"),
    ],
)
def test_topology_validator_rejects_every_malformed_dimension(
    case: str,
    message: str,
) -> None:
    document = _topology_copy(_artifact_document())
    if case == "schema":
        document["schema_version"] = "unsupported"
    elif case == "model":
        document["model_id"] = "wrong-model"
    elif case == "features_type":
        document["features"] = {}
    elif case == "bootstrap_type":
        document["bootstrap"] = []
    elif case == "ensemble_type":
        document["bootstrap"]["coefficient_ensemble"] = []
    elif case == "replicates_type":
        document["bootstrap"]["coefficient_ensemble"]["replicates"] = {}
    elif case == "feature_count":
        document["features"].pop()
    else:
        document["bootstrap"]["coefficient_ensemble"]["replicates"].pop()

    with pytest.raises(SourceProfileIntegrityError, match=message):
        catalog_module._validate_topology(document)


@pytest.mark.parametrize(
    "case",
    [
        "cohort_count",
        "study_id",
        "study_version",
        "source_files_type",
        "source_files_count",
        "source_file_binding",
        "source_manifest_type",
        "source_manifest_schema",
        "source_manifest_digest",
        "source_manifest_bytes",
        "source_manifest_biospecimens",
        "source_manifest_files",
        "hgnc_authority",
        "hgnc_authority_digest",
        "gene_mapping_digest",
        "cohort_mapping_digest",
    ],
)
def test_source_invariant_validator_rejects_each_independent_lock(  # noqa: C901
    case: str,
) -> None:
    document = _source_copy(_artifact_document())
    cohort = document["cohort_oracles"]
    source_lock = document["source_lock"]
    gene_identity = document["gene_identity"]
    expected_message = ""
    if case == "cohort_count":
        cohort["strict_t1_t2_pairs"] = 103
        expected_message = "cardinality"
    elif case == "study_id":
        source_lock["pdc_study_id"] = "PDC000000"
        expected_message = "source lock"
    elif case == "study_version":
        source_lock["pdc_study_version_uuid"] = "wrong"
        expected_message = "source lock"
    elif case == "source_files_type":
        source_lock["files"] = {}
        expected_message = "source lock"
    elif case == "source_files_count":
        source_lock["files"] = list(source_lock["files"][:-1])
        expected_message = "source lock"
    elif case == "source_file_binding":
        source_files = list(source_lock["files"])
        source_file = dict(source_files[0])
        source_file["uuid_size_md5_binding"] = "wrong"
        source_files[0] = source_file
        source_lock["files"] = source_files
        expected_message = "source lock"
    elif case == "source_manifest_type":
        source_lock["versioned_source_manifest"] = []
        expected_message = "source lock"
    elif case.startswith("source_manifest_"):
        manifest = dict(source_lock["versioned_source_manifest"])
        source_lock["versioned_source_manifest"] = manifest
        manifest_field = {
            "source_manifest_schema": "schema_version",
            "source_manifest_digest": "sha256",
            "source_manifest_bytes": "bytes",
            "source_manifest_biospecimens": "biospecimen_response_records",
            "source_manifest_files": "file_manifest_response_records",
        }[case]
        manifest[manifest_field] = "wrong"
        expected_message = "manifest lock"
    elif case == "hgnc_authority":
        gene_identity["authority"] = "wrong"
        expected_message = "HGNC"
    elif case == "hgnc_authority_digest":
        gene_identity["authority_sha256"] = "sha256:wrong"
        expected_message = "HGNC"
    elif case == "gene_mapping_digest":
        gene_identity["mapping_digest"] = "sha256:wrong"
        expected_message = "HGNC"
    else:
        cohort["hgnc_mapping_digest"] = "sha256:wrong"
        expected_message = "HGNC"

    with pytest.raises(SourceProfileIntegrityError, match=expected_message):
        catalog_module._validate_source_invariants(document)


@pytest.mark.parametrize(
    ("field", "value", "feature_index"),
    [
        ("transition_scale", math.nan, 0),
        ("transition_scale", 0.0, 0),
        ("transition_center", math.nan, 0),
        ("paired_support", True, 0),
        ("paired_support", -1, 0),
        ("paired_coverage", -1.0, 0),
        ("coefficient_interval_90", (0.0, 0.0, 0.0), 0),
        ("coefficient_interval_90", [0.0, 0.0], 0),
        ("coefficient_interval_90", [0.0, math.nan, 0.0], 0),
        ("coefficient_interval_90", [0.0, 1.0, 0.0], 0),
        ("coefficient", math.nan, 0),
        ("selected", True, 0),
        ("selected", True, 2),
    ],
)
def test_feature_validator_rejects_each_parameter_invariant(
    field: str,
    value: object,
    feature_index: int,
) -> None:
    features = list(_artifact_document()["features"])
    feature = dict(features[feature_index])
    features[feature_index] = feature
    feature[field] = value
    if field == "selected" and feature_index == 2:
        feature["coefficient"] = 0.01

    with pytest.raises(SourceProfileIntegrityError, match="feature parameter"):
        catalog_module._validate_feature_documents(features)


def test_feature_validator_rejects_duplicate_identifiers() -> None:
    source = _artifact_document()["features"]
    for field, message in (
        ("gene_symbol", "unique symbols"),
        ("source_gene_label", "protein labels"),
        ("hgnc_id", "identifiers"),
    ):
        features = list(source)
        feature = dict(features[1])
        feature[field] = features[0][field]
        features[1] = feature
        with pytest.raises(SourceProfileIntegrityError, match=message):
            catalog_module._validate_feature_documents(features)


@pytest.mark.parametrize("case", ["eligible_count", "selected_count", "coefficient_l1"])
def test_feature_validator_rejects_aggregate_inventory_drift(case: str) -> None:
    features = list(_artifact_document()["features"])
    if case == "eligible_count":
        index = next(index for index, item in enumerate(features) if not item["eligible"])
        feature = dict(features[index])
        feature["eligible"] = True
    else:
        index = next(index for index, item in enumerate(features) if item["selected"])
        feature = dict(features[index])
        if case == "selected_count":
            feature["selected"] = False
            feature["coefficient"] = 0.0
        else:
            feature["coefficient"] = float(feature["coefficient"]) * 2.0
    features[index] = feature

    with pytest.raises(SourceProfileIntegrityError, match="inventory"):
        catalog_module._validate_feature_documents(features)


def test_source_processing_validator_rejects_malformed_projection() -> None:
    document = _processing_copy(_artifact_document())
    document["ordinary_log_ablation"]["frozen_projection"] = []
    with pytest.raises(SourceProfileIntegrityError, match="malformed"):
        catalog_module._validate_source_processing_projection(document)


@pytest.mark.parametrize(
    "case",
    [
        "family",
        "kind",
        "declared_digest",
        "computed_digest",
        "indices_type",
        "coefficients_type",
        "scales_type",
        "indices_count",
        "coefficients_count",
        "scales_count",
        "indices_order",
        "index_type",
        "index_range",
        "coefficient_zero",
        "scale_zero",
        "coefficient_l1",
        "intercept",
    ],
)
def test_source_processing_validator_rejects_every_projection_invariant(  # noqa: C901, PLR0912
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    document = _processing_copy(_artifact_document())
    processing = document["ordinary_log_ablation"]
    projection = processing["frozen_projection"]
    reseal = True
    if case == "family":
        processing["ablation_family"] = "wrong"
    elif case == "kind":
        processing["ablation_kind"] = "wrong"
    elif case == "declared_digest":
        _seal_processing_projection(monkeypatch, document)
        projection["projection_digest"] = "sha256:wrong"
        reseal = False
    elif case == "computed_digest":
        _seal_processing_projection(monkeypatch, document)
        projection["ablation_id"] = "changed-after-sealing"
        reseal = False
    elif case == "indices_type":
        projection["feature_indices"] = tuple(projection["feature_indices"])
    elif case == "coefficients_type":
        projection["coefficients"] = tuple(projection["coefficients"])
    elif case == "scales_type":
        projection["transition_scales"] = tuple(projection["transition_scales"])
    elif case == "indices_count":
        projection["feature_indices"] = projection["feature_indices"][:-1]
    elif case == "coefficients_count":
        projection["coefficients"] = projection["coefficients"][:-1]
    elif case == "scales_count":
        projection["transition_scales"] = projection["transition_scales"][:-1]
    elif case == "indices_order":
        projection["feature_indices"] = list(reversed(projection["feature_indices"]))
    elif case == "index_type":
        projection["feature_indices"][0] = True
    elif case == "index_range":
        projection["feature_indices"][0] = -1
    elif case == "coefficient_zero":
        projection["coefficients"][0] = 0.0
    elif case == "scale_zero":
        projection["transition_scales"][0] = 0.0
    elif case == "coefficient_l1":
        projection["coefficients"][0] *= 2.0
    else:
        projection["intercept"] = 1.0
    if reseal:
        _seal_processing_projection(monkeypatch, document)

    with pytest.raises(SourceProfileIntegrityError, match="projection invariant"):
        catalog_module._validate_source_processing_projection(document)


@pytest.mark.parametrize(
    "case",
    [
        "replicate_index",
        "digest",
        "indices_type",
        "coefficients_type",
        "indices_count",
        "coefficients_count",
        "indices_order",
        "index_type",
        "index_range",
        "coefficient_zero",
        "coefficient_l1",
        "intercept",
        "seed_type",
        "seed_format",
    ],
)
def test_sparse_replicate_parser_rejects_every_local_invariant(  # noqa: C901, PLR0912
    case: str,
) -> None:
    document = _artifact_document()
    replicate = _replicate_copy(document)
    reseal = True
    if case == "replicate_index":
        replicate["replicate_index"] = 1
    elif case == "digest":
        replicate["replicate_digest"] = "sha256:wrong"
        reseal = False
    elif case == "indices_type":
        replicate["feature_indices"] = tuple(replicate["feature_indices"])
    elif case == "coefficients_type":
        replicate["coefficients"] = tuple(replicate["coefficients"])
    elif case == "indices_count":
        replicate["feature_indices"] = replicate["feature_indices"][:-1]
    elif case == "coefficients_count":
        replicate["coefficients"] = replicate["coefficients"][:-1]
    elif case == "indices_order":
        replicate["feature_indices"] = list(reversed(replicate["feature_indices"]))
    elif case == "index_type":
        replicate["feature_indices"][0] = True
    elif case == "index_range":
        replicate["feature_indices"][0] = -1
    elif case == "coefficient_zero":
        replicate["coefficients"][0] = 0.0
    elif case == "coefficient_l1":
        replicate["coefficients"][0] *= 2.0
    elif case == "intercept":
        replicate["intercept"] = 1.0
    elif case == "seed_type":
        replicate["seed_hex"] = 123
    else:
        replicate["seed_hex"] = "not-hex"
    if reseal:
        _seal_replicate(replicate)

    with pytest.raises(SourceProfileIntegrityError, match="replicate invariant"):
        catalog_module._parse_replicates([replicate])


def test_sparse_replicate_parser_rejects_duplicate_seed() -> None:
    document = _artifact_document()
    first = _replicate_copy(document, 0)
    second = _replicate_copy(document, 1)
    second["seed_hex"] = first["seed_hex"]
    _seal_replicate(second)
    with pytest.raises(SourceProfileIntegrityError, match="replicate invariant"):
        catalog_module._parse_replicates([first, second])


def test_projection_validator_rejects_self_declared_ensemble_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _artifact_document()
    _align_projection_locks(monkeypatch, document)
    features, replicates, _, ensemble = catalog_module._validate_topology(document)
    ensemble = dict(ensemble)
    ensemble["ensemble_digest"] = "sha256:wrong"
    with pytest.raises(SourceProfileIntegrityError, match="self-declared"):
        catalog_module._validate_projection_digests(
            document,
            features,
            replicates,
            ensemble,
        )


def test_catalog_rejects_non_object_root(monkeypatch: pytest.MonkeyPatch) -> None:
    encoded = b"[]"
    monkeypatch.setattr(catalog_module, "_resource_bytes", lambda: encoded)
    monkeypatch.setattr(
        catalog_module,
        "EXPECTED_ARTIFACT_BYTE_DIGEST",
        "sha256:" + hashlib.sha256(encoded).hexdigest(),
    )
    monkeypatch.setattr(catalog_module, "EXPECTED_ARTIFACT_BYTES", len(encoded))
    longitudinal_gbm_catalog.cache_clear()
    with pytest.raises(SourceProfileIntegrityError, match="root must be an object"):
        longitudinal_gbm_catalog()
    longitudinal_gbm_catalog.cache_clear()


@pytest.mark.parametrize("case", ["computed", "declared"])
def test_catalog_rejects_each_content_digest_failure(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    original = _artifact_document()
    document = dict(original)
    expected_content = catalog_module._content_digest(original)
    if case == "computed":
        provenance = dict(document["provenance"])
        provenance["transformation_notice"] += " tampered"
        document["provenance"] = provenance
    else:
        document["artifact_digest"] = "sha256:wrong"
    encoded = canonical_json_bytes(document) + b"\n"
    monkeypatch.setattr(catalog_module, "_resource_bytes", lambda: encoded)
    monkeypatch.setattr(
        catalog_module,
        "EXPECTED_ARTIFACT_BYTE_DIGEST",
        "sha256:" + hashlib.sha256(encoded).hexdigest(),
    )
    monkeypatch.setattr(catalog_module, "EXPECTED_ARTIFACT_BYTES", len(encoded))
    monkeypatch.setattr(catalog_module, "EXPECTED_CONTENT_DIGEST", expected_content)
    longitudinal_gbm_catalog.cache_clear()
    with pytest.raises(SourceProfileIntegrityError, match="content digest"):
        longitudinal_gbm_catalog()
    longitudinal_gbm_catalog.cache_clear()


@pytest.mark.parametrize(
    "case",
    [
        "requested_replicates",
        "completed_replicates",
        "feature_index_basis",
        "quantization",
        "scale_policy",
    ],
)
def test_catalog_rejects_each_bootstrap_metadata_invariant(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    document = _topology_copy(_artifact_document())
    bootstrap = document["bootstrap"]
    ensemble = bootstrap["coefficient_ensemble"]
    if case == "requested_replicates":
        bootstrap["requested_replicates"] = 511
    elif case == "completed_replicates":
        bootstrap["completed_replicates"] = 511
    elif case == "feature_index_basis":
        ensemble["feature_index_basis"] = "wrong"
    elif case == "quantization":
        ensemble["coefficient_quantization_decimal_places"] = 7
    else:
        ensemble["scale_policy"] = "wrong"
    _install_document(monkeypatch, document)
    with pytest.raises(SourceProfileIntegrityError, match="bootstrap metadata"):
        longitudinal_gbm_catalog()
    longitudinal_gbm_catalog.cache_clear()
