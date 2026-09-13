from __future__ import annotations

import base64
import json
import math
import zlib
from pathlib import Path
from typing import cast

import numpy as np
import numpy.typing as npt
import pytest

from tools import import_kncc_longitudinal_gbm as base
from tools import import_kncc_reactome_complex_transition_model as importer

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
SOURCE_ARTIFACT = (
    REPOSITORY_ROOT
    / "src"
    / "glio_proteogen"
    / "research"
    / "longitudinal_gbm_complex_transition"
    / "data"
    / "kncc_reactome_complex_transition_source.v1.json"
)
MODEL_ARTIFACT = SOURCE_ARTIFACT.with_name("kncc_reactome_complex_transition_model.v1.json")
PDC_SOURCE = WORKSPACE_ROOT / ".tmp-longitudinal-gbm-source"
HGNC_SOURCE = WORKSPACE_ROOT / ".tmp-neftel-source" / "hgnc_complete_set.txt"

EXPECTED_SOURCE_BYTES = 96_157
EXPECTED_SOURCE_SHA256 = "sha256:03fc954944af058d6f8d4ec629e16615555791642b7d91bc1d0d1455e1dbcf30"
EXPECTED_SOURCE_CONTENT_DIGEST = (
    "sha256:5719f23be05e7b1603cd5ba56deb638f90300686ada786bec22a2201a7f99124"
)
EXPECTED_MODEL_BYTES = 245_014
EXPECTED_MODEL_SHA256 = "sha256:f0895efa245ddaaeb324ce3d6c32c8bab9b2abd612a8ad51bd086af97c440676"
EXPECTED_MODEL_CONTENT_DIGEST = (
    "sha256:8465d0c5db70e1cdd3dab08b3646a7c023078c746c96c054bfa3888e8e80e0d2"
)
EXPECTED_BOOTSTRAP_SEED_NAMESPACE_DIGEST = (
    "sha256:98e49ff6c56de72273f11f89a4f6ce3496becab28c7b3231fc2f9131cadd1758"
)


def _document(path: Path) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(path.read_bytes()))


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _records(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return cast("list[dict[str, object]]", value)


def _decode_tensor(value: object) -> npt.NDArray[np.float32]:
    tensor = _mapping(value)
    assert tensor["dtype"] == "<f4"
    compressed = base64.b64decode(cast("str", tensor["data"]), validate=True)
    payload = zlib.decompress(compressed)
    assert len(payload) == tensor["raw_bytes"]
    assert importer._raw_digest(payload) == tensor["raw_sha256"]
    shape = tuple(cast("list[int]", tensor["shape"]))
    return np.frombuffer(payload, dtype="<f4").reshape(shape)


def test_frozen_source_and_model_are_canonical_exact_and_deidentified() -> None:
    source_payload = SOURCE_ARTIFACT.read_bytes()
    model_payload = MODEL_ARTIFACT.read_bytes()
    assert len(source_payload) == EXPECTED_SOURCE_BYTES
    assert importer._raw_digest(source_payload) == EXPECTED_SOURCE_SHA256
    assert len(model_payload) == EXPECTED_MODEL_BYTES
    assert importer._raw_digest(model_payload) == EXPECTED_MODEL_SHA256

    for payload, expected_digest in (
        (source_payload, EXPECTED_SOURCE_CONTENT_DIGEST),
        (model_payload, EXPECTED_MODEL_CONTENT_DIGEST),
    ):
        document = cast("dict[str, object]", json.loads(payload))
        assert importer._canonical_bytes(document) == payload
        content = dict(document)
        assert content.pop("artifact_digest") == expected_digest
        assert importer._digest(content) == expected_digest
        assert b"KNCC_GBM" not in payload
        assert b'"patient_groups"' not in payload
        assert b'"patient_identifiers"' not in payload
        assert b'"fold_assignments"' not in payload
        assert b'"resample_indices"' not in payload
        assert b'"predictions"' not in payload


def test_source_catalog_projection_is_exact_and_rejects_forgery(
    tmp_path: Path,
) -> None:
    source = importer.load_source_catalog()
    assert source.artifact_bytes == EXPECTED_SOURCE_BYTES
    assert source.artifact_byte_digest == EXPECTED_SOURCE_SHA256
    assert source.content_digest == EXPECTED_SOURCE_CONTENT_DIGEST
    assert len(source.complexes) == 28
    assert source.complexes[0].reactome_id == "R-HSA-179791"
    assert source.complexes[-1].reactome_id == "R-HSA-9709857"
    assert tuple(item.complex_index for item in source.complexes) == tuple(range(28))
    assert all(len(item.member_feature_indices) >= 3 for item in source.complexes)
    assert source.projection_digests == {
        "complex_membership_digest": (
            "sha256:eebf2b92fdf60a7075cd625e26a74666c50df70f15e69e64e08c99b6628c3b27"
        ),
        "complex_order_digest": (
            "sha256:ee65348ef9688e26f9853053b2c46e469509a7c5b5ac9ea2cd09387af0a8db02"
        ),
        "overlap_control_digest": (
            "sha256:674e3ebee67e4a6ac53b39bc5e51d9e27bccae15d81d0b84578a9554d450bc2b"
        ),
        "pathway_binding_digest": (
            "sha256:1f9500bf27bde7207c999186c9f4fbb362e9fa2ec2b66864fbc8dbaa20aca92a"
        ),
        "selection_digest": (
            "sha256:6f7e7636bbebbe4cdfd4e91303ef58cdec1286c0de454f6df32a57d1740fa09b"
        ),
        "source_binding_digest": (
            "sha256:ca0b0625142f4640e789b334913e743bf4c24eb84984297c17795a8aa6d2819e"
        ),
    }

    forged = _document(SOURCE_ARTIFACT)
    first = _mapping(_records(forged["complexes"])[0])
    first["name"] = "forged"
    forged_path = tmp_path / "forged.json"
    forged_path.write_bytes(importer._canonical_bytes(forged))
    with pytest.raises(ValueError, match="content digest mismatch"):
        importer.load_source_catalog(forged_path)


def test_bootstrap_seed_namespace_excludes_provenance_content_digest() -> None:
    source = importer.load_source_catalog()
    recipe_digest = importer._digest(importer._recipe())
    expected = importer._bootstrap_seed_namespace(source, recipe_digest)
    assert expected == EXPECTED_BOOTSTRAP_SEED_NAMESPACE_DIGEST

    prose_only_change = importer.SourceCatalog(
        artifact_bytes=source.artifact_bytes + 1,
        artifact_byte_digest="sha256:" + "1" * 64,
        content_digest="sha256:" + "2" * 64,
        profile_id=source.profile_id,
        complexes=source.complexes,
        projection_digests=source.projection_digests,
    )
    assert importer._bootstrap_seed_namespace(prose_only_change, recipe_digest) == expected

    changed_membership = dict(source.projection_digests)
    changed_membership["complex_membership_digest"] = "sha256:" + "3" * 64
    biological_change = importer.SourceCatalog(
        artifact_bytes=source.artifact_bytes,
        artifact_byte_digest=source.artifact_byte_digest,
        content_digest=source.content_digest,
        profile_id=source.profile_id,
        complexes=source.complexes,
        projection_digests=changed_membership,
    )
    assert importer._bootstrap_seed_namespace(biological_change, recipe_digest) != expected

    missing_membership = dict(source.projection_digests)
    del missing_membership["complex_membership_digest"]
    incomplete = importer.SourceCatalog(
        artifact_bytes=source.artifact_bytes,
        artifact_byte_digest=source.artifact_byte_digest,
        content_digest=source.content_digest,
        profile_id=source.profile_id,
        complexes=source.complexes,
        projection_digests=missing_membership,
    )
    with pytest.raises(ValueError, match="lacks bootstrap seed projections"):
        importer._bootstrap_seed_namespace(incomplete, recipe_digest)


def test_rank_one_irls_recovers_latent_direction_with_missingness_and_outlier() -> None:
    generator = np.random.default_rng(20_260_830)
    expected_loading = np.asarray([0.62, -0.44, 0.51, 0.22, -0.31])
    expected_loading /= np.linalg.norm(expected_loading)
    coordinate = generator.normal(0.0, 1.0, size=96)
    values = coordinate[:, None] * expected_loading[None, :]
    values += generator.normal(0.0, 0.045, size=values.shape)
    values[::11, 1] = np.nan
    values[::13, 3] = np.nan
    values[0, 0] = 14.0
    reliability = np.asarray([1.0, 0.94, 0.91, 0.88, 0.84])

    fitted = importer.fit_rank_one(values, reliability, expected_loading)
    replay = importer.fit_rank_one(values.copy(), reliability.copy(), expected_loading.copy())
    assert fitted.converged
    assert fitted.iterations < importer.SOLVER_MAX_ITERATIONS
    assert np.linalg.norm(fitted.loadings) == pytest.approx(1.0, abs=1.0e-12)
    assert np.dot(fitted.loadings, expected_loading) > 0.93
    assert fitted.loadings == pytest.approx(replay.loadings, abs=0.0)
    assert fitted.coordinates == pytest.approx(replay.coordinates, abs=0.0)
    assert fitted.objective_trace == replay.objective_trace
    assert all(
        right <= left + importer.OBJECTIVE_TOLERANCE
        for left, right in zip(
            fitted.objective_trace,
            fitted.objective_trace[1:],
            strict=False,
        )
    )
    finite = np.isfinite(values)
    fitted_error = np.median(
        np.abs(values[finite] - (fitted.coordinates[:, None] * fitted.loadings[None, :])[finite])
    )
    assert fitted_error < 0.075


def test_rank_one_and_coordinate_solvers_fail_closed_on_unsupported_inputs() -> None:
    values = np.ones((4, 3), dtype=np.float64)
    reliability = np.ones(3, dtype=np.float64)
    effect = np.ones(3, dtype=np.float64)
    with pytest.raises(ValueError, match="at least three rows and members"):
        importer.fit_rank_one(values[:, :2], reliability[:2], effect[:2])
    with pytest.raises(ValueError, match="shape mismatch"):
        importer.fit_rank_one(values, reliability[:2], effect[:2])
    with pytest.raises(ValueError, match="finite and non-negative"):
        importer.fit_rank_one(values, np.asarray([1.0, -1.0, 1.0]), effect)
    sparse = values.copy()
    sparse[:2, 0] = np.nan
    with pytest.raises(ValueError, match="three supported observations"):
        importer.fit_rank_one(sparse, reliability, effect)

    unsupported = importer.fit_coordinate(
        np.asarray([1.0, np.nan, np.nan]),
        np.ones(3),
        np.ones(3),
    )
    assert unsupported == importer.CoordinateFit(
        coordinate=0.0,
        iterations=0,
        converged=False,
    )


def test_coordinate_solver_matches_convex_huber_ridge_stationarity() -> None:
    values = np.asarray([1.8, -0.4, 0.7, 12.0], dtype=np.float64)
    loadings = np.asarray([0.6, -0.45, 0.35, 0.55], dtype=np.float64)
    reliability = np.asarray([1.0, 0.9, 0.8, 0.15], dtype=np.float64)
    fitted = importer.fit_coordinate(values, loadings, reliability)
    assert fitted.converged
    residual = values - fitted.coordinate * loadings
    derivative = importer.FACTOR_RIDGE * fitted.coordinate - np.dot(
        reliability * loadings,
        np.clip(residual, -importer.HUBER_K, importer.HUBER_K),
    )
    assert abs(derivative) <= 2.0 * importer.SOLVER_TOLERANCE


def test_fitted_artifact_has_real_nested_evaluation_and_stable_tensors() -> None:
    document = _document(MODEL_ARTIFACT)
    counts = _mapping(document["counts"])
    evaluation = _mapping(document["evaluation"])
    complexes = _records(document["complexes"])
    bootstrap = _mapping(document["bootstrap"])
    tensors = _mapping(bootstrap["tensors"])
    digests = _mapping(document["digests"])

    assert bootstrap["seed_namespace_digest"] == EXPECTED_BOOTSTRAP_SEED_NAMESPACE_DIGEST
    assert (
        digests["bootstrap_seed_namespace_digest"]
        == EXPECTED_BOOTSTRAP_SEED_NAMESPACE_DIGEST
    )

    assert counts == {
        "bootstrap_replicates": 128,
        "complexes": 28,
        "member_slots": 146,
        "source_gene_features": 11_312,
        "source_paired_groups": 104,
        "union_features": 120,
    }
    assert evaluation["held_patient_count"] == 104
    assert evaluation["evaluation_count"] == 14_988
    assert evaluation["held_coordinate_insufficient_support_count"] == 56
    assert evaluation["model_standardized_mae"] == 0.6989814224
    assert evaluation["training_center_standardized_mae"] == 0.8769685109
    assert evaluation["zero_transition_standardized_mae"] == 0.9407301748
    assert evaluation["relative_mae_gain_vs_training_center"] == 0.2029572172
    assert evaluation["direction_accuracy"] == 0.7255137443
    assert _mapping(evaluation["nonconvergence_counts"]) == {
        "factor": 0,
        "held_coordinate": 0,
        "preprocessing": 0,
    }
    cluster = _mapping(evaluation["patient_cluster_bootstrap"])
    assert cluster["nominal_90_percent_interval"] == [0.0990936656, 0.1805654575]
    assert cast("float", cluster["median_relative_mae_gain"]) > 0.14

    assert len(complexes) == 28
    assert (
        sum(
            cast(
                "float",
                _mapping(item["outer_fold_held_member_evaluation"])[
                    "relative_mae_gain_vs_training_center"
                ],
            )
            > 0.0
            for item in complexes
        )
        >= 24
    )
    for index, item in enumerate(complexes):
        assert item["complex_index"] == index
        reference = _mapping(item["reference"])
        convergence = _mapping(reference["convergence"])
        loadings = np.asarray(reference["member_loadings"], dtype=np.float64)
        assert convergence["converged"] is True
        assert convergence["objective_monotone"] is True
        assert np.linalg.norm(loadings) == pytest.approx(1.0, abs=2.0e-10)
        assert len(loadings) == item["member_slot_count"]
        assert len(cast("list[float]", reference["member_scales"])) == len(loadings)
        assert all(value > 0.0 for value in cast("list[float]", reference["member_scales"]))

    scale = _decode_tensor(tensors["member_scale"])
    loading = _decode_tensor(tensors["member_loading"])
    assert scale.shape == loading.shape == (128, 146)
    assert np.all(np.isfinite(scale)) and np.all(scale > 0.0)
    assert np.all(np.isfinite(loading))
    for item in complexes:
        offset = cast("int", item["member_slot_offset"])
        count = cast("int", item["member_slot_count"])
        norms = np.linalg.norm(loading[:, offset : offset + count], axis=1)
        assert norms == pytest.approx(np.ones(128), abs=2.0e-6)


def test_claim_boundary_and_privacy_are_explicitly_non_mechanistic() -> None:
    document = _document(MODEL_ARTIFACT)
    boundary = _mapping(document["claim_boundary"])
    privacy = _mapping(document["privacy"])
    assert boundary["supported_claim"] == (
        "source-cohort complex-member protein-transition concordance"
    )
    unsupported = set(cast("list[str]", boundary["unsupported_claims"]))
    assert {
        "complex assembly",
        "complex biochemical activity",
        "member essentiality",
        "stoichiometric occupancy",
        "causal mechanism",
        "clinical state",
        "treatment response",
    } <= unsupported
    assert privacy == {
        "bootstrap_resample_indices_bundled": False,
        "fold_assignments_bundled": False,
        "patient_factor_coordinates_bundled": False,
        "patient_identifiers_or_hashes_bundled": False,
        "patient_measurements_bundled": False,
        "patient_scores_or_residuals_bundled": False,
    }
    with pytest.raises(ValueError, match="forbidden patient-level field"):
        importer._assert_deidentified({"patient_ids": []}, ())
    with pytest.raises(ValueError, match="patient identifier"):
        importer._assert_deidentified({"value": "KNCC_GBM0001"}, ())


def test_bootstrap_bounds_are_enforced_before_source_access() -> None:
    cohort = cast("base.Cohort", object())
    with pytest.raises(ValueError, match="between 1 and 256"):
        importer.build_artifact(cohort, bootstrap_replicates=0)
    with pytest.raises(ValueError, match="between 1 and 256"):
        importer.build_artifact(cohort, bootstrap_replicates=257)


@pytest.mark.skipif(
    not PDC_SOURCE.is_dir() or not HGNC_SOURCE.is_file(),
    reason="exact locked offline PDC/HGNC sources are not mounted",
)
def test_real_cohort_replay_is_deterministic_for_one_bootstrap() -> None:
    cohort = base.load_cohort(PDC_SOURCE, HGNC_SOURCE)
    first = importer.build_artifact(cohort, bootstrap_replicates=1)
    second = importer.build_artifact(cohort, bootstrap_replicates=1)
    assert importer._canonical_bytes(first) == importer._canonical_bytes(second)
    assert _mapping(first["evaluation"])["evaluation_count"] == 14_988
    assert _mapping(first["counts"])["source_paired_groups"] == 104
    assert _mapping(_mapping(first["bootstrap"])["diagnostics"])["nonconverged_fit_count"] == 0


def test_write_artifact_is_canonical(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "model.json"
    document = {"finite": math.pi, "model": importer.MODEL_ID}
    importer.write_artifact(document, destination)
    assert destination.read_bytes() == importer._canonical_bytes(document)
