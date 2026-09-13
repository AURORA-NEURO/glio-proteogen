from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import numpy as np
import pytest

from tools import bootstrap_cptac_gbm_source_factors as bootstrap

if TYPE_CHECKING:
    from pathlib import Path


def test_interval_requires_eight_successful_replicates() -> None:
    assert bootstrap._interval([0.1] * 7)["lower"] is None
    result = bootstrap._interval([0.1 + 0.01 * index for index in range(8)])
    assert cast("int", result["support"]) == 8
    assert cast("float", result["lower"]) <= cast("float", result["median"])
    assert cast("float", result["median"]) <= cast("float", result["upper"])


def test_cosine_rejects_invalid_or_zero_vectors() -> None:
    assert bootstrap._cosine(np.ones(1), np.ones(1)) is None
    assert bootstrap._cosine(np.ones(2), np.ones(3)) is None
    assert bootstrap._cosine(np.zeros(2), np.ones(2)) is None
    assert bootstrap._cosine(np.array([1.0, 0.0]), np.array([1.0, 0.0])) == 1.0


def test_factor_map_rejects_missing_and_duplicate_identifiers() -> None:
    with pytest.raises(ValueError, match="missing factors"):
        bootstrap._factor_map({}, "factors")
    with pytest.raises(ValueError, match="duplicate"):
        bootstrap._factor_map(
            {"factors": [{"complex_id": "R1"}, {"complex_id": "R1"}]}, "factors"
        )


def test_case_groups_excludes_pooled_reference_and_preserves_case_order(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    rows = [
        {"aliquot_submitter_id": "A", "case_id": "case-2", "pool": "No"},
        {"aliquot_submitter_id": "B", "case_id": "case-1", "pool": "No"},
        {"aliquot_submitter_id": "ref", "case_id": "pool", "pool": "Yes"},
    ]
    manifest.write_text(
        json.dumps({"responses": {"biospecimens": {"PDC000204": rows, "PDC000205": rows}}}),
        encoding="utf-8",
    )
    groups = bootstrap._case_groups(manifest, ["A", "B"])
    assert [group.tolist() for group in groups] == [[1], [0]]


def test_factor_bootstrap_cosine_refits_protein_and_phosphosite_modalities() -> None:
    protein = np.array(
        [
            [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            [2.0, 2.0, 3.0, 4.0, 4.0, 6.0, 7.0, 7.5],
            [1.0, 1.5, 2.5, 4.0, 5.0, 5.5, 7.0, 8.0],
        ],
        dtype=np.float64,
    )
    factor = {
        "protein_members": ["G1", "G2", "G3"],
        "protein_factor": {"loadings": [0.57735027, 0.57735027, 0.57735027]},
        "phosphosite": {
            "features": [
                {"feature_id": "S1", "loading": 0.57735027},
                {"feature_id": "S2", "loading": 0.57735027},
                {"feature_id": "S3", "loading": 0.57735027},
            ]
        },
    }
    sample_indices = np.arange(8, dtype=np.int64)
    phosphosite_values = {
        "S1": protein[0] + 0.1,
        "S2": protein[1] - 0.2,
        "S3": protein[2] + 0.3,
    }
    phosphosite_gene = {"S1": "G1", "S2": "G2", "S3": "G3"}
    protein_score = bootstrap._factor_bootstrap_cosine(
        factor,
        protein_matrix=protein,
        gene_index={"G1": 0, "G2": 1, "G3": 2},
        phosphosite_values=phosphosite_values,
        phosphosite_gene=phosphosite_gene,
        sample_indices=sample_indices,
        modality="protein",
    )
    phosphosite_score = bootstrap._factor_bootstrap_cosine(
        factor,
        protein_matrix=protein,
        gene_index={"G1": 0, "G2": 1, "G3": 2},
        phosphosite_values=phosphosite_values,
        phosphosite_gene=phosphosite_gene,
        sample_indices=sample_indices,
        modality="phosphosite",
    )
    assert protein_score is not None and -1.0 <= protein_score <= 1.0
    assert phosphosite_score is not None and -1.0 <= phosphosite_score <= 1.0


def test_point_site_features_accepts_pathway_receipt_shape() -> None:
    identifiers, loadings = bootstrap._point_site_features(
        {
            "phosphosite_features": [
                {"feature_id": "S1", "loading": 0.5},
                {"feature_id": "S2", "loading": -0.5},
            ],
            "phosphosite_factor": {"loadings": [0.7, -0.7]},
        }
    ) or ([], np.array([], dtype=np.float64))
    assert identifiers == ["S1", "S2"]
    assert loadings.tolist() == [0.5, -0.5]


def test_factor_bootstrap_cosine_abstains_for_unknown_protein() -> None:
    factor = {
        "protein_members": ["UNKNOWN", "G2", "G3"],
        "protein_factor": {"loadings": [1.0, 0.0, 0.0]},
    }
    result = bootstrap._factor_bootstrap_cosine(
        factor,
        protein_matrix=np.ones((3, 4), dtype=np.float64),
        gene_index={"G2": 1, "G3": 2},
        phosphosite_values={},
        phosphosite_gene={},
        sample_indices=np.arange(4, dtype=np.int64),
        modality="protein",
    )
    assert result is None


def test_bootstrap_receipt_replay_reports_digest_and_semantic_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = {
        "schema_version": bootstrap.MODEL_ID,
        "algorithm_profile": {"numpy_version": "2.5.2", "replicates": 8},
        "algorithm_profile_digest": "sha256:profile",
        "source_manifest_digest": "sha256:manifest",
        "source_complex_catalog_digest": "sha256:catalog",
        "seed_material_digest": "sha256:seed",
        "factor_receipts": {"complex": "sha256:complex", "pathway": "sha256:pathway"},
        "source_files": {"protein": {"sha256": "protein"}},
        "replicates_requested": 8,
        "case_group_count": 2,
        "complexes": [],
        "pathways": [],
        "limitations": [],
    }
    expected["receipt_digest"] = bootstrap._receipt_digest(expected)
    monkeypatch.setattr(bootstrap, "bootstrap_factors", lambda *_args, **_kwargs: expected)
    receipt = tmp_path / "receipt.json"
    receipt.write_bytes(bootstrap._canonical_bytes(expected))

    verified = bootstrap.verify_bootstrap_receipt(
        tmp_path / "source",
        tmp_path / "manifest.json",
        tmp_path / "complex.json",
        tmp_path / "pathway.json",
        receipt,
    )
    assert verified["verified"] is True
    checks = cast("dict[str, bool]", verified["checks"])
    assert checks["receipt_digest"] is True
    assert checks["semantic_equal"] is True
    assert verified["request_digest"] == "sha256:seed"

    forged = dict(expected)
    forged["seed_material_digest"] = "sha256:forged"
    receipt.write_bytes(bootstrap._canonical_bytes(forged))
    rejected = bootstrap.verify_bootstrap_receipt(
        tmp_path / "source",
        tmp_path / "manifest.json",
        tmp_path / "complex.json",
        tmp_path / "pathway.json",
        receipt,
    )
    assert rejected["verified"] is False
    assert "seed_material_digest" in cast("list[str]", rejected["mismatches"])
    assert "semantic_equal" in cast("list[str]", rejected["mismatches"])


def test_bootstrap_receipt_replay_rejects_invalid_replicate_bounds(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"replicates_requested": 2}), encoding="utf-8")
    report = bootstrap.verify_bootstrap_receipt(
        tmp_path / "source",
        tmp_path / "manifest.json",
        tmp_path / "complex.json",
        tmp_path / "pathway.json",
        receipt,
    )
    assert report["verified"] is False
    assert report["mismatches"] == ["replicates_requested"]
