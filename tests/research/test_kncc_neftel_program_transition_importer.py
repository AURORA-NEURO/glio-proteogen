from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path
from typing import cast

import numpy as np
import pytest

from glio_proteogen.research.longitudinal_gbm.catalog import longitudinal_gbm_catalog
from glio_proteogen.research.neftel_protein_programs.catalog import marker_catalog
from tools import import_kncc_longitudinal_gbm as base
from tools import import_kncc_neftel_program_transition_model as importer

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
RAW_SOURCE_DIR = WORKSPACE_ROOT / ".tmp-longitudinal-gbm-source"
RAW_HGNC_SOURCE = WORKSPACE_ROOT / ".tmp-neftel-source" / "hgnc_complete_set.txt"
MODEL_ARTIFACT = (
    REPOSITORY_ROOT
    / "src"
    / "glio_proteogen"
    / "research"
    / "longitudinal_gbm_neftel_transition"
    / "data"
    / "kncc_neftel_program_transition_model.v1.json"
)

EXPECTED_PROGRAM_COUNTS = {
    "MES2": (42, 40),
    "MES1": (49, 47),
    "AC": (37, 36),
    "OPC": (47, 46),
    "NPC1": (43, 42),
    "NPC2": (41, 38),
    "G1/S": (26, 14),
    "G2/M": (37, 25),
}
EXPECTED_PROGRAM_ORDER_DIGEST = (
    "sha256:969e39b3516a28996b3c16a3e2dc07d7b347849620aed1338e4d082ff517e711"
)
EXPECTED_PROGRAM_MEMBERSHIP_DIGEST = (
    "sha256:193f2be224e655a4a5522e73ef01f965a76abb449b6af6ef77d67a36a10c195c"
)
EXPECTED_ARTIFACT_BYTES = 357_871
EXPECTED_ARTIFACT_SHA256 = "sha256:cdc00db86c83bee0ff62eb30f4e0130da8621b09ebca298adf16458e073d38a9"
EXPECTED_CONTENT_DIGEST = "sha256:815b4066891c9ddf78b3be374e573be28e299eb15ed612ee3c662f33a84c8e41"
EXPECTED_EVALUATION_DIGEST = (
    "sha256:14a773347547306420d288620b3344f18b1f1100cc97bb5ab12e0c3f4b19ccad"
)
EXPECTED_BOOTSTRAP_DIGEST = (
    "sha256:cea991982fb0e23aa87193cc0c76384908024549c5bf12c2e041cf8d41a697de"
)


def _exact_inputs() -> tuple[tuple[str, ...], np.ndarray, importer.DesignInputs]:
    parent = longitudinal_gbm_catalog()
    genes = tuple(feature.gene_symbol for feature in parent.features)
    eligible = np.asarray([feature.eligible for feature in parent.features], dtype=np.bool_)
    inputs = importer._design_inputs(
        genes,
        marker_catalog(),
        eligible_mask=eligible,
        enforce_source_oracles=True,
    )
    return genes, eligible, inputs


def test_exact_neftel_masks_map_to_the_frozen_256_feature_union() -> None:
    genes, eligible, inputs = _exact_inputs()

    assert len(genes) == 11_312
    assert inputs.union_indices.size == 256
    assert np.all(eligible[inputs.union_indices])
    assert np.array_equal(inputs.union_indices, np.unique(inputs.union_indices))
    assert tuple(program.program_id for program in inputs.programs) == (
        "MES2",
        "MES1",
        "AC",
        "OPC",
        "NPC1",
        "NPC2",
        "G1/S",
        "G2/M",
    )
    assert {
        program.program_id: (
            int(program.mapped_feature_indices.size),
            int(program.member_feature_indices.size),
        )
        for program in inputs.programs
    } == EXPECTED_PROGRAM_COUNTS
    assert inputs.program_order_digest == EXPECTED_PROGRAM_ORDER_DIGEST
    assert inputs.program_membership_digest == EXPECTED_PROGRAM_MEMBERSHIP_DIGEST
    assert float(inputs.degree.min()) == 1.0
    assert float(inputs.degree.max()) > 1.0


def test_global_and_conditional_designs_are_normalized_and_residualized() -> None:
    genes, eligible, inputs = _exact_inputs()
    effect = np.zeros(len(genes), dtype=np.float64)
    local = np.arange(inputs.union_indices.size, dtype=np.float64)
    effect[inputs.union_indices] = 0.35 + np.sin(local * 0.17) + local / 900.0
    fit = importer.FitView(
        scale=np.ones(len(genes), dtype=np.float64),
        support=np.full(len(genes), 104, dtype=np.int64),
        eligible=eligible,
        effect=effect,
        order=inputs.union_indices.copy(),
        intensity_floor=0.01,
        iterations=2,
        converged=True,
    )

    design = importer._design(fit, inputs)
    replay = importer._design(fit, inputs)
    no_degree = importer._design(fit, inputs, degree_normalization=False)
    equal = importer._equal_membership_design(fit, inputs)
    expected_norm = math.sqrt(inputs.union_indices.size)

    assert design.shape == equal.shape == (256, 9)
    assert np.array_equal(design, replay)
    assert np.linalg.norm(design, axis=0) == pytest.approx(np.full(9, expected_norm), abs=1.0e-10)
    assert design[:, 0] @ design[:, 1:] == pytest.approx(np.zeros(8), abs=1.0e-10)
    assert equal[:, 0] @ equal[:, 1:] == pytest.approx(np.zeros(8), abs=1.0e-10)
    assert not np.array_equal(design[:, 1:], equal[:, 1:])
    assert not np.array_equal(design[:, 1:], no_degree[:, 1:])


def test_irls_coordinate_solver_matches_direct_ridge_solution_in_quadratic_region() -> None:
    design = np.asarray(
        [[1.0, 0.0], [0.5, 1.0], [-0.5, 1.0], [1.0, -1.0]],
        dtype=np.float64,
    )
    values = np.asarray([0.2, 0.1, -0.1, 0.3], dtype=np.float64)
    solved = importer._solve(design, values)
    penalty = np.diag([importer.GLOBAL_RIDGE_MULTIPLIER, 1.0])
    direct = np.linalg.solve(
        design.T @ design + importer.RIDGE_LAMBDA * penalty,
        design.T @ values,
    )

    assert solved.converged
    assert solved.iterations < importer.SOLVER_MAX_ITERATIONS
    assert solved.coordinates == pytest.approx(direct, abs=1.0e-9)
    with pytest.raises(ValueError, match="shape mismatch"):
        importer._solve(design, values[:-1])
    with pytest.raises(ValueError, match="finite overdetermined"):
        importer._solve(design, np.asarray([0.1, np.nan, 0.2, 0.3]))


def _synthetic_cohort() -> tuple[base.Cohort, importer.DesignInputs]:
    parent_genes, _, exact = _exact_inputs()
    genes = tuple(parent_genes[int(index)] for index in exact.union_indices)
    inputs = importer._design_inputs(genes, marker_catalog())
    patient_count = 40
    gene_count = len(genes)
    generator = np.random.default_rng(20_260_830)
    membership = np.zeros((gene_count, len(inputs.programs)), dtype=np.float64)
    for program in inputs.programs:
        positions = program.member_local_indices
        membership[positions, program.program_index] = 1.0 / np.sqrt(inputs.degree[positions])
    gene_shape = 0.3 + 0.2 * np.sin(np.arange(gene_count) * 0.13)
    program_means = np.linspace(-0.35, 0.45, len(inputs.programs))
    mean = gene_shape + membership @ program_means
    coordinates = generator.normal(0.0, 0.35, size=(patient_count, len(inputs.programs)))
    global_coordinates = generator.normal(0.0, 0.25, size=patient_count)
    primary = (
        mean[None, :]
        + global_coordinates[:, None] * gene_shape[None, :]
        + coordinates @ membership.T
        + generator.normal(0.0, 0.08, size=(patient_count, gene_count))
    )
    missing = generator.random(primary.shape) < 0.015
    primary[missing] = np.nan
    ordinary = primary + generator.normal(0.0, 0.02, size=primary.shape)
    cohort = base.Cohort(
        genes=genes,
        hgnc_ids=tuple(f"HGNC:{index + 1}" for index in range(gene_count)),
        source_gene_labels=genes,
        mapping_basis=("synthetic_exact_symbol",) * gene_count,
        patient_groups=tuple(f"opaque-group-{index:03d}" for index in range(patient_count)),
        primary_delta=primary,
        ordinary_delta=ordinary,
        unshared_peptides=np.full(gene_count, 3, dtype=np.int64),
        oracles={"synthetic": True},
    )
    return cohort, inputs


def test_nested_patient_and_held_marker_evaluation_is_deterministic() -> None:
    cohort, inputs = _synthetic_cohort()
    fit = importer._view(base._fit_axis(cohort.primary_delta, cohort.genes))
    design = importer._design(fit, inputs)
    equal = importer._equal_membership_design(fit, inputs)

    first, coordinates = importer._evaluation(cohort, inputs, design, equal)
    second, replay = importer._evaluation(cohort, inputs, design, equal)

    assert first == second
    assert np.array_equal(coordinates, replay)
    assert first["patient_count"] == 40
    assert first["evaluation_count"] == 200
    assert first["outer_fold_sizes"] == [5] * 8
    assert first["patient_cluster_bootstrap_replicates"] == 20_000
    assert set(cast("dict[str, int]", first["solver_nonconverged_by_role"])) == {
        "full_patient",
        "global_held_marker",
        "equal_membership_held_marker",
        "joint_held_marker",
        "leave_program_out",
    }
    for field in (
        "zero_prediction_median_standardized_mae",
        "global_only_median_standardized_mae",
        "equal_membership_median_standardized_mae",
        "joint_median_standardized_mae",
    ):
        assert math.isfinite(cast("float", first[field]))
    assert len(cast("list[dict[str, object]]", first["leave_program_out"])) == 8
    assert len(cast("list[dict[str, object]]", first["cross_fitted_coordinate_scales"])) == 9


def test_patient_bootstrap_refits_are_deterministic_and_do_not_return_indices() -> None:
    cohort, inputs = _synthetic_cohort()
    namespace = importer._bootstrap_seed_namespace(
        inputs, marker_catalog(), importer._digest(importer._recipe())
    )
    first = importer._bootstrap_ensemble(
        cohort, inputs, seed_namespace_digest=namespace, replicates=3
    )
    second = importer._bootstrap_ensemble(
        cohort, inputs, seed_namespace_digest=namespace, replicates=3
    )

    assert np.array_equal(first[0], second[0])
    assert np.array_equal(first[1], second[1])
    assert first[2] == second[2]
    assert first[0].shape == first[1].shape == (3, 256)
    assert len(first[2]) == 3


def test_bootstrap_seed_namespace_ignores_prose_only_catalog_content_changes() -> None:
    _, _, inputs = _exact_inputs()
    source = marker_catalog()
    recipe_digest = importer._digest(importer._recipe())
    expected = importer._bootstrap_seed_namespace(inputs, source, recipe_digest)
    prose_only = replace(source, content_digest="sha256:" + "f" * 64)
    biological_change = replace(source, source_program_digest="sha256:" + "e" * 64)

    assert importer._bootstrap_seed_namespace(inputs, prose_only, recipe_digest) == expected
    assert importer._bootstrap_seed_namespace(inputs, biological_change, recipe_digest) != expected


@pytest.mark.skipif(
    not RAW_SOURCE_DIR.is_dir() or not RAW_HGNC_SOURCE.is_file(),
    reason="raw digest-locked PDC/HGNC sources are not distributed with the package",
)
def test_exact_local_sources_build_a_canonical_deidentified_artifact() -> None:
    cohort = base.load_cohort(RAW_SOURCE_DIR, RAW_HGNC_SOURCE)
    artifact = importer.build_artifact(cohort, bootstrap_replicates=1)
    payload = importer._canonical_bytes(artifact)

    assert artifact["schema_version"] == importer.SCHEMA_VERSION
    assert artifact["model_id"] == "kncc-neftel-program-transition-model/1.0.0"
    assert artifact["profile_id"] == "kncc-neftel-program-transition/1.0.0"
    assert cast("dict[str, int]", artifact["counts"]) == {
        "source_patient_pairs": 104,
        "source_gene_features": 11_312,
        "union_features": 256,
        "reference_eligible_union_features": 256,
        "programs": 8,
        "bootstrap_replicates": 1,
    }
    content = dict(artifact)
    assert content.pop("artifact_digest") == importer._digest(content)
    assert b"KNCC_GBM" not in payload
    assert b'"patient_groups"' not in payload
    assert b'"fold_membership"' not in payload
    assert b'"bootstrap_indices"' not in payload


def test_checked_artifact_is_canonical_and_digest_locked() -> None:
    payload = MODEL_ARTIFACT.read_bytes()
    document = cast("dict[str, object]", json.loads(payload))
    assert len(payload) == EXPECTED_ARTIFACT_BYTES
    assert importer._raw_digest(payload) == EXPECTED_ARTIFACT_SHA256
    assert importer._canonical_bytes(document) == payload
    content = dict(document)
    assert content.pop("artifact_digest") == EXPECTED_CONTENT_DIGEST
    assert importer._digest(content) == EXPECTED_CONTENT_DIGEST
    digests = cast("dict[str, str]", document["digests"])
    assert digests["evaluation_digest"] == EXPECTED_EVALUATION_DIGEST
    assert digests["bootstrap_ensemble_digest"] == EXPECTED_BOOTSTRAP_DIGEST
    evaluation = cast("dict[str, object]", document["evaluation"])
    assert evaluation["patient_count"] == 104
    assert evaluation["evaluation_count"] == 520
    assert evaluation["global_only_median_standardized_mae"] == 0.6039095267
    assert evaluation["equal_membership_median_standardized_mae"] == 0.5177467313
    assert evaluation["joint_median_standardized_mae"] == 0.5754778047
    assert evaluation["joint_vs_global_median_relative_mae_gain"] == 0.0261168032
    assert evaluation["joint_vs_equal_median_relative_mae_gain"] == -0.105617713
    assert evaluation["release_gate"] == (
        "limited_fitted_dictionary_not_preferred_to_equal_membership"
    )
    assert evaluation["joint_vs_global_patient_cluster_interval_supports_positive_gain"] is True
    assert evaluation["joint_vs_equal_patient_cluster_interval_supports_positive_gain"] is False
    assert evaluation["individually_supported_program_ids"] == []
    assert evaluation["patient_cluster_joint_vs_global_median_gain_90_interval"] == [
        0.015326555,
        0.0380342956,
    ]
    assert evaluation["patient_cluster_joint_vs_equal_median_gain_90_interval"] == [
        -0.1155036986,
        -0.0777444485,
    ]
    assert all(
        cast("float", item["q05"]) <= 0.0 <= cast("float", item["q95"])
        for item in cast("list[dict[str, object]]", evaluation["leave_program_out"])
    )
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_ARTIFACT_SHA256.removeprefix("sha256:")
