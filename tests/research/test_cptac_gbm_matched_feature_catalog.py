from __future__ import annotations

import json
from typing import TYPE_CHECKING

import numpy as np
import pytest

from tools import build_cptac_gbm_matched_feature_catalog as catalog

if TYPE_CHECKING:
    from pathlib import Path


def test_finite_float_preserves_blanks_and_rejects_nonfinite() -> None:
    assert np.isnan(catalog._finite_float(""))
    assert catalog._finite_float("1.25") == 1.25
    with pytest.raises(ValueError, match="non-finite"):
        catalog._finite_float("nan")


def test_huber_location_downweights_a_single_extreme_outlier() -> None:
    center, scale, support = catalog._huber_location(np.asarray([0.0, 0.1, -0.1, 100.0]))
    assert support == 4
    assert abs(center) < 0.2
    assert scale >= catalog.ROBUST_SCALE_FLOOR


@pytest.mark.parametrize(
    ("tumor", "normal", "state", "reason"),
    [
        ([], [], "missing", "no finite"),
        ([1.0], [0.0, 0.1, -0.1], "unsupported", "fewer than three"),
        ([100.0, 100.0, 100.0], [0.0, 0.0, 0.0], "unsupported", "outside"),
        ([1.0, 1.1, 0.9], [0.0, 0.1, -0.1], "observed", None),
    ],
)
def test_contrast_reports_support_and_abstention(
    tumor: list[float], normal: list[float], state: str, reason: str | None
) -> None:
    result = catalog._contrast(
        np.asarray(tumor, dtype=float),
        np.asarray(normal, dtype=float),
        row_id="feature",
        gene="GENE1",
        modality="proteomics",
        source_measure="Unshared Log Ratio",
    )
    assert result["state"] == state
    if reason is not None:
        assert reason in str(result["abstention_reason"])
    else:
        assert result["standardized_effect"] is not None


def test_matrix_columns_distinguish_unshared_suffix() -> None:
    labels = ["A", "B"]
    header = [
        "Gene",
        "A Log Ratio",
        "A Unshared Log Ratio",
        "B Log Ratio",
        "B Unshared Log Ratio",
        "NCBIGeneID",
    ]
    assert catalog._matrix_columns(header, labels, measure="Unshared Log Ratio") == [2, 4]
    assert catalog._matrix_columns(header, labels, measure="Log Ratio") == [1, 3]


def test_read_matrix_skips_protein_aggregate_rows_and_keeps_phosphosite_rows_atomic(
    tmp_path: Path,
) -> None:
    labels = ["T1", "T2", "T3", "N1", "N2", "N3"]
    tumor = np.asarray([0, 1, 2], dtype=np.int64)
    normal = np.asarray([3, 4, 5], dtype=np.int64)
    protein_header = ["Gene"]
    for label in labels:
        protein_header.extend((f"{label} Log Ratio", f"{label} Unshared Log Ratio"))
    protein_header.extend(
        ("NCBIGeneID", "Authority", "Description", "Organism", "Chromosome", "Locus")
    )
    protein_rows = [
        ["Mean", *(["0", "0"] * 6), "", "", "", "", "", ""],
        ["EGFR", *(["1", "1"] * 3 + ["0", "0"] * 3), "", "", "", "", "", ""],
    ]
    protein_path = tmp_path / "protein.tsv"
    protein_path.write_text(
        "\n".join("\t".join(row) for row in [protein_header, *protein_rows]) + "\n",
        encoding="utf-8",
    )
    protein, oracle = catalog._read_matrix(
        protein_path,
        labels=labels,
        tumor_indices=tumor,
        normal_indices=normal,
        modality="proteomics",
        measure="Unshared Log Ratio",
    )
    assert len(protein) == 1
    assert protein[0]["feature_id"] == "EGFR"
    assert oracle["rows"] == 2

    phospho_header = [
        "Phosphosite",
        *(f"{label} Log Ratio" for label in labels),
        "Peptide",
        "Gene",
        "Organism",
    ]
    phospho_row = [
        "EGFR.Y1068;Y1173",
        "1",
        "1",
        "1",
        "0",
        "0",
        "0",
        "PEP;PEP2",
        "EGFR",
        "Homo sapiens",
    ]
    phospho_path = tmp_path / "phosphosite.tsv"
    phospho_path.write_text(
        "\n".join("\t".join(row) for row in [phospho_header, phospho_row]) + "\n",
        encoding="utf-8",
    )
    phosphosite, _ = catalog._read_matrix(
        phospho_path,
        labels=labels,
        tumor_indices=tumor,
        normal_indices=normal,
        modality="phosphoproteomics",
        measure="Log Ratio",
    )
    assert phosphosite[0]["feature_id"] == "EGFR.Y1068;Y1173"
    assert phosphosite[0]["gene"] == "EGFR"


def test_read_matrix_rejects_duplicate_rows_and_abstains_nonhuman_features(tmp_path: Path) -> None:
    labels = ["T1", "T2", "T3", "N1", "N2", "N3"]
    tumor = np.asarray([0, 1, 2], dtype=np.int64)
    normal = np.asarray([3, 4, 5], dtype=np.int64)
    header = [
        "Phosphosite",
        *(f"{label} Log Ratio" for label in labels),
        "Peptide",
        "Gene",
        "Organism",
    ]
    rows = [
        ["S1", "1", "1", "1", "0", "0", "0", "PEP", "GENE", "Mus musculus"],
        ["S1", "1", "1", "1", "0", "0", "0", "PEP", "GENE", "Mus musculus"],
    ]
    path = tmp_path / "phosphosite.tsv"
    path.write_text("\n".join("\t".join(row) for row in [header, *rows]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        catalog._read_matrix(
            path,
            labels=labels,
            tumor_indices=tumor,
            normal_indices=normal,
            modality="phosphoproteomics",
            measure="Log Ratio",
        )
    path.write_text("\n".join("\t".join(row) for row in [header, rows[0]]) + "\n", encoding="utf-8")
    features, _ = catalog._read_matrix(
        path,
        labels=labels,
        tumor_indices=tumor,
        normal_indices=normal,
        modality="phosphoproteomics",
        measure="Log Ratio",
    )
    assert features[0]["state"] == "unsupported"
    assert "Homo sapiens" in str(features[0]["abstention_reason"])


def test_group_indices_retain_disqualified_count_without_using_it_in_fit() -> None:
    labels = [f"A{i}" for i in range(110)]
    metadata = {
        label: {
            "PDC000204:sample_type": "Primary Tumor" if index < 100 else "Solid Tissue Normal",
            "PDC000205:sample_type": "Primary Tumor" if index < 100 else "Solid Tissue Normal",
            "PDC000204:case_status": "Disqualified" if index == 0 else "Qualified",
            "PDC000205:case_status": "Disqualified" if index == 0 else "Qualified",
        }
        for index, label in enumerate(labels)
    }
    tumor, normal, oracle = catalog._group_indices(labels, metadata)
    assert tumor.size == 99
    assert normal.size == 10
    assert oracle == {
        "qualified_primary_tumors": 99,
        "qualified_solid_tissue_normals": 10,
        "excluded_disqualified_aliquots": 1,
    }


def test_manifest_metadata_requires_both_study_fields(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"responses": {"biospecimens": {"PDC000204": [], "PDC000205": []}}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sample metadata"):
        catalog._metadata_from_manifest(manifest)
