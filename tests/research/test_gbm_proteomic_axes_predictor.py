from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest

from glio_proteogen.research.gbm_proteomic_axes.data.predictor import (
    ARTIFACT_SHA256,
    MODEL_FEATURE_COUNT,
    MODEL_SOURCE_SHA256,
    ORACLE_FIXTURE_SHA256,
    SOURCE_COMMIT,
    SUPPORTED_SIGNATURES,
    TREES_PER_SIGNATURE,
    feature_names,
    load_artifact,
    model_catalog,
    predict_axes,
    predict_lfq,
    scale_positive_lfq,
)

DATA = (
    Path(__file__).parents[2]
    / "src"
    / "glio_proteogen"
    / "research"
    / "gbm_proteomic_axes"
    / "data"
)

EXPECTED = {
    "SWEET_KRAS_TARGETS_UP": (-0.5897, -0.5879, -0.6713, -0.8208),
    "HALLMARK_MYC_TARGETS_V1": (-0.3933, 0.2610, -0.0983, 1.1780),
    "WINTER_HYPOXIA_UP": (-0.1878, -0.5913, -1.0292, -1.4135),
    "VERHAAK_GLIOBLASTOMA_MESENCHYMAL": (-1.0937, -0.5485, -0.7079, -0.6857),
    "VERHAAK_GLIOBLASTOMA_NEURAL": (0.9894, 0.3719, 0.9090, -0.5499),
    "VERHAAK_GLIOBLASTOMA_PRONEURAL": (0.8723, 0.3809, 0.7147, 0.7143),
    "EGFR_UP.V1_UP": (-1.2940, -0.6399, -0.7530, -1.1709),
}


def _oracle_fixture() -> dict[str, object]:
    raw = (DATA / "diamandis_sample_proteomics_v1.json.gz").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ORACLE_FIXTURE_SHA256
    return json.loads(gzip.decompress(raw))


def test_artifact_is_bound_to_the_pinned_upstream_source() -> None:
    artifact_path = DATA / "diamandis_gbm_proteomic_axes_v1.json"
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == ARTIFACT_SHA256

    artifact = load_artifact()
    assert artifact.source_commit == SOURCE_COMMIT
    assert artifact.schema_version == "glio-gbm-proteomic-axes-artifact/1.0.0"
    assert len(artifact.feature_names) == MODEL_FEATURE_COUNT
    assert feature_names(SUPPORTED_SIGNATURES[0]) is artifact.feature_names
    assert tuple(item.signature_name for item in model_catalog()) == SUPPORTED_SIGNATURES
    assert all(item.feature_count == MODEL_FEATURE_COUNT for item in model_catalog())
    assert all(item.tree_count == TREES_PER_SIGNATURE for item in model_catalog())

    document = json.loads(artifact_path.read_bytes())
    assert document["source"]["paper"]["doi"] == "10.1038/s41467-021-27667-w"
    assert document["source"]["license_spdx"] == "MIT"
    assert document["source"]["selection"]["names"] == list(SUPPORTED_SIGNATURES)
    assert document["source"]["files"]["protein_models"]["sha256"] == MODEL_SOURCE_SHA256
    assert hashlib.sha256((DATA / "DIAMANDIS-LAB-LICENSE.txt").read_bytes()).hexdigest() == (
        document["source"]["files"]["LICENSE"]["sha256"]
    )
    assert document["conversion"] == {
        "legacy_xgboost_version": "1.4.2",
        "numpy_version": "1.26.4",
        "tree_representation": "ordered_depth_one_stumps_float32_accumulation",
    }
    assert document["oracle"]["maximum_absolute_error_vs_xgboost_1_4_2"] == 0.0
    assert document["oracle"]["maximum_published_score_error"] == 0.0


def test_numpy_runtime_matches_all_published_selected_sample_scores() -> None:
    fixture = _oracle_fixture()
    symbols = fixture["gene_symbols"]
    samples = fixture["samples"]
    assert isinstance(symbols, list)
    assert isinstance(samples, dict)

    for sample_index in range(4):
        values = samples[f"sample_{sample_index + 1}"]
        assert isinstance(values, list)
        abundances = dict(zip(symbols, values, strict=True))
        result = predict_axes(abundances)
        assert result.input_protein_count == 4_154
        assert result.positive_protein_count > MODEL_FEATURE_COUNT
        for signature_name, expected_values in EXPECTED.items():
            prediction = result.signatures[signature_name]
            assert prediction.score == expected_values[sample_index]
            assert prediction.observed_feature_count == MODEL_FEATURE_COUNT
            assert prediction.missing_feature_count == 0
            assert prediction.missing_feature_ratio == 0.0
            reconstructed = prediction.intercept + math.fsum(prediction.contributions.values())
            assert reconstructed == pytest.approx(prediction.unrounded_score, abs=2.0e-5)


def test_geometric_mean_scaling_includes_non_model_proteins_and_excludes_zeros() -> None:
    scaled, geometric_mean, factor = scale_positive_lfq(
        {"A1BG": 1.0, "NOT_IN_MODEL": 100.0, "A2M": 0.0}
    )
    assert geometric_mean == pytest.approx(10.0)
    assert factor == pytest.approx(1.0e6)
    assert scaled == pytest.approx({"A1BG": 1.0e6, "NOT_IN_MODEL": 1.0e8, "A2M": 0.0})

    prediction = predict_axes(
        {"A1BG": 1.0, "NOT_IN_MODEL": 100.0, "A2M": 0.0},
        ["EGFR_UP.V1_UP"],
    ).signatures["EGFR_UP.V1_UP"]
    assert prediction.observed_feature_count == 2
    assert prediction.missing_feature_count == MODEL_FEATURE_COUNT - 2
    assert prediction.missing_feature_ratio == pytest.approx((MODEL_FEATURE_COUNT - 2) / 3025)


def test_input_and_signature_order_do_not_change_predictions() -> None:
    forward = {"A1BG": 1.0, "A2M": 4.0, "AAAS": 2.0, "NOT_IN_MODEL": 8.0}
    reverse = dict(reversed(tuple(forward.items())))
    selected = ("EGFR_UP.V1_UP", "SWEET_KRAS_TARGETS_UP")
    first = predict_axes(forward, selected)
    second = predict_lfq(reverse, reversed(selected))
    assert first.geometric_mean == second.geometric_mean
    assert first.normalization_factor == second.normalization_factor
    for name in selected:
        assert first.signatures[name] == second.signatures[name]


@pytest.mark.parametrize(
    ("abundances", "message"),
    [
        ({}, "at least one protein"),
        ({"A1BG": 0.0}, "at least one positive"),
        ({"A1BG": -1.0}, "nonnegative"),
        ({"A1BG": float("nan")}, "finite"),
        ({"A1BG": float("inf")}, "finite"),
        ({" A1BG": 1.0}, "exact strings"),
        ({"A1BG": True}, "numeric"),
    ],
)
def test_invalid_abundances_are_rejected(abundances: dict[str, float], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        predict_axes(abundances)


def test_invalid_signature_selection_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one GBM"):
        predict_axes({"A1BG": 1.0}, [])
    with pytest.raises(ValueError, match="unique"):
        predict_axes({"A1BG": 1.0}, ["EGFR_UP.V1_UP", "EGFR_UP.V1_UP"])
    with pytest.raises(ValueError, match="unsupported"):
        predict_axes({"A1BG": 1.0}, ["NOT_A_MODEL"])
    with pytest.raises(ValueError, match="unsupported"):
        feature_names("NOT_A_MODEL")


def test_normalized_model_features_must_fit_the_published_float32_runtime() -> None:
    with pytest.raises(ValueError, match="float32"):
        predict_axes({"A1BG": 1.0e300, "NOT_IN_MODEL": 1.0e-100})
