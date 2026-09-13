from __future__ import annotations

import hashlib
import json
from itertools import pairwise
from pathlib import Path
from typing import cast

import numpy as np
import pytest

from glio_proteogen.research.longitudinal_gbm_kinase_transition.catalog import (
    EXPECTED_ARTIFACT_SHA256,
    EXPECTED_BOOTSTRAP_DIGEST,
    EXPECTED_CONTENT_DIGEST,
    EXPECTED_FITTER_SOURCE_SHA256,
)
from tools import import_kncc_longitudinal_kinase_transition as importer

ARTIFACT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "glio_proteogen"
    / "research"
    / "longitudinal_gbm_kinase_transition"
    / "data"
    / "kncc_sphinks_signature_transition.v1.json"
)


def test_fixed_24_bh_is_monotone_and_rejects_family_drift() -> None:
    p_values = [0.001 * (index + 1) for index in range(24)]
    q_values = importer._bh_fixed_family(p_values)
    assert len(q_values) == 24
    assert all(left <= right for left, right in pairwise(q_values))
    assert all(
        p_value <= q_value <= 1.0 for p_value, q_value in zip(p_values, q_values, strict=True)
    )
    with pytest.raises(ValueError, match="exactly 24"):
        importer._bh_fixed_family(p_values[:-1])


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("NP_000001.1-S10s", "S:1"),
        ("NP_000001.1-S10sT12t", "ST:2"),
        ("NP_000001.1-Y2yS10sT12t", "STY:3"),
    ],
)
def test_residue_cardinality_strata_preserve_composites(label: str, expected: str) -> None:
    assert importer._site_stratum(label) == expected


def test_privacy_guard_rejects_literal_and_low_entropy_identifier_hashes() -> None:
    identifier = "KNCC_GBM0001_T1"
    with pytest.raises(ValueError, match="pseudonym"):
        importer._assert_privacy({"value": identifier}, frozenset({identifier}))
    for algorithm in (hashlib.md5, hashlib.sha1, hashlib.sha256):
        digest = algorithm(identifier.encode(), usedforsecurity=False).hexdigest()
        with pytest.raises(ValueError, match="low-entropy"):
            importer._assert_privacy({"value": digest}, frozenset({identifier}))


def test_canonical_artifact_rewrite_is_byte_identical(tmp_path: Path) -> None:
    document = cast("dict[str, object]", json.loads(ARTIFACT.read_bytes()))
    destination = tmp_path / "artifact.json"
    importer.write_artifact(document, destination)
    assert destination.read_bytes() == ARTIFACT.read_bytes()
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == EXPECTED_ARTIFACT_SHA256


def test_artifact_binds_exact_sources_privacy_and_honest_evaluation() -> None:
    document = cast("dict[str, object]", json.loads(ARTIFACT.read_bytes()))
    assert document["artifact_digest"] == EXPECTED_CONTENT_DIGEST
    bootstrap = cast("dict[str, object]", document["bootstrap"])
    assert bootstrap["ensemble_digest"] == EXPECTED_BOOTSTRAP_DIGEST
    bindings = cast("dict[str, object]", document["source_bindings"])
    assert bindings["fitter_source_sha256"] == EXPECTED_FITTER_SOURCE_SHA256
    assert "sha256:" + hashlib.sha256(Path(importer.__file__).read_bytes()).hexdigest() == (
        EXPECTED_FITTER_SOURCE_SHA256
    )
    assert bindings["pdc_study_version_uuid"] == "e5e0dd84-f982-46e3-b78a-5cb19eef31a8"
    assert bindings["pdc_source_manifest_digest"] == (
        "sha256:1b248983791886a9b4522de07d96abb517c416d793b789d435544745dbe6ed34"
    )
    assert bindings["pdc_hgnc_mapping_digest"] == (
        "sha256:07245f3fe73129607856b1a92671cce13932a53c95a19f16894daf4971449aa4"
    )
    assert bindings["pdc_sphinks_crosswalk_digest"] == (
        "sha256:4d9d62c63361f285b45fff380588b37174663bfc702cef0587b705aaadebe8c4"
    )
    assert bindings["sphinks_background_tuple_digest"] == (
        "sha256:1b2c46dde1965729f913f0bbed61d2ce2e98f029125304f6d417bdb679f406ba"
    )
    assert bindings["sphinks_signature_edge_digest"] == (
        "sha256:2cba909989a33438e5d81c551015300b5de7553fa7275b1d5dffde6bf134b345"
    )
    evaluation = cast("dict[str, object]", document["fit_evaluation"])
    signature = cast("dict[str, object]", evaluation["signature_transition"])
    raw = cast("dict[str, object]", evaluation["raw_phosphosite_axis_same_folds"])
    comparison = cast("dict[str, object]", evaluation["incremental_comparison"])
    assert signature["supported_pairs"] == 88
    assert signature["direction_accuracy"] == 0.7727272727
    assert raw["direction_accuracy"] == 0.7954545455
    assert comparison["adds_independent_evidence"] is False
    assert comparison["signature_only_correct"] == 7
    assert comparison["raw_phosphosite_only_correct"] == 9
    assert comparison["mcnemar_exact_two_sided_p_value"] == 0.8036193848
    assert comparison["score_pearson"] == 0.6109301534
    assert comparison["sign_agreement"] == 0.8181818182
    assert evaluation["outer_validation_preprocessing"] == (
        "feature admission, scaling, competitive nulls, signature selection, and weights "
        "are fit only on outer-training pairs without a full-cohort release-inventory gate"
    )
    assert evaluation["outer_signature_refits_all_converged"] is True
    assert evaluation["nested_raw_comparator_refits_all_converged"] is True
    stability = cast("dict[str, object]", document["stability"])
    assert stability["bootstrap_inventory_policy"] == (
        "exact patient-bootstrap refits condition selection on the frozen full-fit "
        "release-eligible family inventory; stability and uncertainty are not validation"
    )
    bootstrap_jaccard = cast("dict[str, object]", stability["bootstrap_selected_set_jaccard"])
    assert bootstrap_jaccard == {
        "maximum": 1.0,
        "median": 0.8571428571,
        "minimum": 0.5555555556,
    }
    assert stability["bootstrap_full_set_recovery_fraction"] == 0.296875
    assert stability["bootstrap_all_refits_converged"] is True
    gates = cast("dict[str, object]", document["runtime_quality_gates"])
    assert gates["patient_bootstrap_full_refit_convergence_gate_passed"] is True


def test_all_bootstrap_rows_are_sparse_released_and_digest_bound() -> None:
    document = cast("dict[str, object]", json.loads(ARTIFACT.read_bytes()))
    families = cast("list[dict[str, object]]", document["families"])
    released = {int(cast("int", item["family_index"])) for item in families}
    bootstrap = cast("dict[str, object]", document["bootstrap"])
    replicates = cast("list[dict[str, object]]", bootstrap["replicates"])
    assert len(replicates) == 64
    for index, replicate in enumerate(replicates):
        assert replicate["replicate_index"] == index
        family_indices = cast("list[int]", replicate["family_indices"])
        scales = cast("list[float]", replicate["scales"])
        assert family_indices == sorted(set(family_indices))
        assert set(family_indices).issubset(released)
        assert len(family_indices) == len(scales)
        assert all(value > 0.0 for value in scales)
        content = dict(replicate)
        supplied = content.pop("replicate_digest")
        assert importer._digest(content) == supplied


def test_outer_fit_is_invariant_to_held_support_and_variance_changes() -> None:
    rows = np.arange(10, dtype=np.float64)[:, None]
    columns = np.arange(8, dtype=np.float64)[None, :]
    baseline = 0.15 * rows + 0.03 * columns + np.sin(rows + columns) * 0.01
    baseline[4:8, 6] = np.nan
    left = baseline.copy()
    right = baseline.copy()
    left[8:, 6] = np.nan
    left[8:, 7] = -1.0e6
    right[8:, 6] = (4.0, 5.0)
    right[8:, 7] = 1.0e6
    labels = tuple(f"NP_TEST-{index}S" for index in range(8))
    strata = np.asarray(["S:1"] * 8, dtype=object)
    specs = tuple(
        importer.KinaseSpec(
            symbol=f"K{index:02d}",
            subtype="NEU",
            site_indices=np.asarray([0, 1, 2], dtype=np.int64),
            source_weights=np.ones(3, dtype=np.float64),
        )
        for index in range(24)
    )
    training = np.arange(8, dtype=np.int64)

    left_outer = importer._fit_signature_model(
        left,
        labels,
        strata,
        specs,
        training,
        permutations=15,
        seed_component="held-invariance",
    )
    right_outer = importer._fit_signature_model(
        right,
        labels,
        strata,
        specs,
        training,
        permutations=15,
        seed_component="held-invariance",
    )
    np.testing.assert_array_equal(left_outer.eligible, right_outer.eligible)
    np.testing.assert_array_equal(left_outer.support, right_outer.support)
    np.testing.assert_array_equal(left_outer.scale, right_outer.scale)
    assert left_outer.all_results == right_outer.all_results
    assert tuple(item.symbol for item in left_outer.selected) == tuple(
        item.symbol for item in right_outer.selected
    )

    all_rows = np.arange(10, dtype=np.int64)
    left_full = importer._fit_signature_model(
        left,
        labels,
        strata,
        specs,
        all_rows,
        permutations=15,
        seed_component="held-invariance-full",
    )
    right_full = importer._fit_signature_model(
        right,
        labels,
        strata,
        specs,
        all_rows,
        permutations=15,
        seed_component="held-invariance-full",
    )
    assert not left_full.eligible[6]
    assert right_full.eligible[6]
    assert left_full.scale[7] != right_full.scale[7]
