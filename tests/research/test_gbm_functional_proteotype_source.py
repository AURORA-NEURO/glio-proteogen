"""Focused admission tests for the aggregate GBM functional-proteotype source."""

from __future__ import annotations

import hashlib
import io
import json
import math
import zipfile
from collections import Counter
from itertools import pairwise
from pathlib import Path
from typing import cast

import pytest

from tools import import_gbm_functional_proteotype as importer

ARTIFACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "glio_proteogen"
    / "research"
    / "gbm_functional_proteotype"
    / "data"
    / "gbm_functional_proteotype_catalog.v1.json"
)
RAW_SOURCE = (
    Path(__file__).resolve().parents[4]
    / ".tmp-makina-source"
    / importer.SOURCE_FILENAME
)
EXPECTED_ARTIFACT_SHA256 = "67dd0d660fcd88a4aa309dd398e3d5b9fec8c018bea1cad88158463edf6d8d6d"
EXPECTED_CONTENT_DIGEST = (
    "sha256:1d4099b6d04bf3ea85ea268e551464b5aba220a081b6dffd69282bbb28cafb8b"
)


@pytest.fixture(scope="module")
def artifact() -> dict[str, object]:
    return cast("dict[str, object]", json.loads(ARTIFACT_PATH.read_bytes()))


def _valid_table_2d_cells() -> importer.CellMap:
    cells: importer.CellMap = {
        (1, "A"): importer.COMMON_TABLE_TITLE,
        (2, "A"): importer.TABLE_2D_TITLE,
    }
    for axis_index, axis in enumerate(importer.AXES):
        columns = importer.TABLE_2D_COLUMNS[axis]
        cells[(3, columns[0])] = importer.AXIS_TITLES[axis]
        for column, header in zip(columns, importer.TABLE_2D_HEADERS, strict=True):
            cells[(4, column)] = header
        for source_rank, row in enumerate(
            range(5, importer.TABLE_2D_LAST_ROW + 1),
            start=1,
        ):
            cells[(row, columns[0])] = f"GENE_{axis_index}_{source_rank:03d}"
            cells[(row, columns[1])] = f"protein-{axis_index}-{source_rank:03d}"
            cells[(row, columns[2])] = str(1000.0 - source_rank)
    return cells


def _valid_table_2e_cells() -> importer.CellMap:
    cells: importer.CellMap = {
        (1, "A"): importer.COMMON_TABLE_TITLE,
        (2, "A"): importer.TABLE_2E_TITLE,
    }
    for axis_index, axis in enumerate(importer.AXES):
        columns = importer.TABLE_2E_COLUMNS[axis]
        cells[(3, columns[0])] = importer.AXIS_TITLES[axis]
        for column, header in zip(columns, importer.TABLE_2E_HEADERS, strict=True):
            cells[(4, column)] = header
        count = importer.EXPECTED_PATHWAY_COUNTS[axis]
        for source_rank, row in enumerate(range(5, 5 + count), start=1):
            p_value = source_rank / 100_000.0
            cells[(row, columns[0])] = f"PATHWAY_{axis_index}_{source_rank:03d}"
            cells[(row, columns[1])] = str(1.0 + source_rank / 1000.0)
            cells[(row, columns[2])] = str(p_value)
            cells[(row, columns[3])] = str(p_value * 2.0)
    return cells


def test_catalog_is_canonical_and_binds_source_identity(
    artifact: dict[str, object],
) -> None:
    payload = ARTIFACT_PATH.read_bytes()
    assert len(payload) == 283_232
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_ARTIFACT_SHA256
    assert payload == importer.render_catalog(artifact)
    assert artifact["schema_version"] == importer.SCHEMA_VERSION
    assert artifact["content_digest"] == EXPECTED_CONTENT_DIGEST
    digest_payload = dict(artifact)
    del digest_payload["content_digest"]
    assert importer.canonical_digest(digest_payload) == EXPECTED_CONTENT_DIGEST

    source = cast("dict[str, object]", artifact["source"])
    assert source["article_doi"] == importer.ARTICLE_DOI
    assert source["pmcid"] == "PMC9970878"
    assert source["source_filename"] == importer.SOURCE_FILENAME
    assert source["source_size_bytes"] == importer.SOURCE_SIZE_BYTES
    assert source["source_sha256"] == f"sha256:{importer.SOURCE_SHA256}"
    assert source["license"] == "CC-BY-4.0"
    assert source["license_url"] == "https://creativecommons.org/licenses/by/4.0/"
    worksheets = cast("dict[str, dict[str, object]]", source["worksheets"])
    assert worksheets["table_2d"] == {
        "dimension": importer.TABLE_2D_DIMENSION,
        "headers": list(importer.TABLE_2D_HEADERS),
        "record_counts": importer.EXPECTED_SIGNATURE_COUNTS,
        "table_title": importer.TABLE_2D_TITLE,
        "worksheet_name": importer.TABLE_2D_WORKSHEET,
    }
    assert worksheets["table_2e"] == {
        "dimension": importer.TABLE_2E_DIMENSION,
        "headers": list(importer.TABLE_2E_HEADERS),
        "record_counts": importer.EXPECTED_PATHWAY_COUNTS,
        "table_title": importer.TABLE_2E_TITLE,
        "worksheet_name": importer.TABLE_2E_WORKSHEET,
    }


def test_catalog_contains_only_aggregate_ranked_rows(
    artifact: dict[str, object],
) -> None:
    assert set(artifact) == {
        "axes",
        "content_digest",
        "schema_version",
        "source",
        "source_cohort_pathway_context",
    }
    axes = cast("dict[str, list[dict[str, object]]]", artifact["axes"])
    pathways = cast(
        "dict[str, list[dict[str, object]]]",
        artifact["source_cohort_pathway_context"],
    )
    assert tuple(axes) == importer.AXES
    assert tuple(pathways) == importer.AXES

    all_genes: set[str] = set()
    all_protein_labels: set[str] = set()
    for axis in importer.AXES:
        rows = axes[axis]
        assert len(rows) == importer.EXPECTED_SIGNATURE_COUNTS[axis] == 150
        assert [row["source_rank"] for row in rows] == list(range(1, 151))
        scores = [cast("float", row["source_mww_score"]) for row in rows]
        assert all(math.isfinite(score) and score > 0.0 for score in scores)
        assert all(left >= right for left, right in pairwise(scores))
        genes = [cast("str", row["gene_symbol"]) for row in rows]
        protein_labels = [cast("str", row["source_protein_label"]) for row in rows]
        assert len(genes) == len(set(genes))
        assert len(protein_labels) == len(set(protein_labels))
        assert all_genes.isdisjoint(genes)
        assert all_protein_labels.isdisjoint(protein_labels)
        all_genes.update(genes)
        all_protein_labels.update(protein_labels)
        assert all(
            set(row)
            == {"gene_symbol", "source_mww_score", "source_protein_label", "source_rank"}
            for row in rows
        )

    all_pathway_labels: list[str] = []
    for axis in importer.AXES:
        rows = pathways[axis]
        assert len(rows) == importer.EXPECTED_PATHWAY_COUNTS[axis]
        assert [row["source_rank"] for row in rows] == list(range(1, len(rows) + 1))
        labels = [cast("str", row["pathway"]) for row in rows]
        assert len(labels) == len(set(labels))
        all_pathway_labels.extend(labels)
        for row in rows:
            assert set(row) == {"logit_nes", "p_value", "pathway", "q_value", "source_rank"}
            logit_nes = cast("float", row["logit_nes"])
            p_value = cast("float", row["p_value"])
            q_value = cast("float", row["q_value"])
            assert math.isfinite(logit_nes) and logit_nes > 0.0
            assert math.isfinite(p_value) and 0.0 < p_value <= 1.0
            assert math.isfinite(q_value) and p_value <= q_value <= 1.0
    assert len(all_genes) == 600
    assert len(all_pathway_labels) == 826
    assert len(set(all_pathway_labels)) == 777
    assert sum(count - 1 for count in Counter(all_pathway_labels).values()) == 49

    forbidden_row_keys = {
        "patient",
        "patient_id",
        "patients",
        "sample",
        "sample_id",
        "samples",
        "specimen",
        "specimen_id",
        "matrix",
        "measurements",
    }
    row_keys = {
        key
        for group in (*axes.values(), *pathways.values())
        for row in group
        for key in row
    }
    assert row_keys.isdisjoint(forbidden_row_keys)


def test_source_rank_oracles_preserve_exact_first_and_last_rows(
    artifact: dict[str, object],
) -> None:
    axes = cast("dict[str, list[dict[str, object]]]", artifact["axes"])
    pathways = cast(
        "dict[str, list[dict[str, object]]]",
        artifact["source_cohort_pathway_context"],
    )
    assert {
        axis: (rows[0]["gene_symbol"], rows[-1]["gene_symbol"])
        for axis, rows in axes.items()
    } == {
        "GPM": ("CSTA", "CD68"),
        "MTC": ("PNPO", "WDR4"),
        "NEU": ("CRHBP", "PPP3CB"),
        "PPR": ("ZNF219", "PHC1"),
    }
    assert {
        axis: (rows[0]["pathway"], rows[-1]["pathway"])
        for axis, rows in pathways.items()
    } == {
        "GPM": ("GO_CYTOSOLIC_PART", "HALLMARK_ANGIOGENESIS"),
        "MTC": ("GO_MITOCHONDRIAL_TRANSLATION", "GO_ENERGY_RESERVE_METABOLIC_PROCESS"),
        "NEU": ("GO_EXCITATORY_SYNAPSE", "GO_AMMONIUM_TRANSPORT"),
        "PPR": ("GO_SPLICEOSOMAL_COMPLEX", "GO_SKELETAL_MUSCLE_CELL_DIFFERENTIATION"),
    }


@pytest.mark.skipif(
    not RAW_SOURCE.is_file(),
    reason="raw digest-locked source workbook is not distributed with the package",
)
def test_local_pinned_workbook_rebuilds_byte_identically() -> None:
    first = importer.render_catalog(importer.build_catalog(RAW_SOURCE))
    second = importer.render_catalog(importer.build_catalog(RAW_SOURCE))
    assert first == second == ARTIFACT_PATH.read_bytes()


def test_builder_rejects_non_disjoint_gene_ids_and_nonfinite_scores() -> None:
    cells = _valid_table_2d_cells()
    mtc_gene_column = importer.TABLE_2D_COLUMNS["MTC"][0]
    cells[(5, mtc_gene_column)] = cells[(5, importer.TABLE_2D_COLUMNS["GPM"][0])]
    with pytest.raises(ValueError, match="not disjoint"):
        importer._protein_signatures(cells)

    cells = _valid_table_2d_cells()
    cells[(5, importer.TABLE_2D_COLUMNS["GPM"][2])] = "nan"
    with pytest.raises(ValueError, match="not finite"):
        importer._protein_signatures(cells)


def test_builder_rejects_pathway_duplicates_partial_rows_and_bad_q_values() -> None:
    cells = _valid_table_2e_cells()
    columns = importer.TABLE_2E_COLUMNS["GPM"]
    cells[(6, columns[0])] = cells[(5, columns[0])]
    with pytest.raises(ValueError, match="duplicate Table 2e pathway"):
        importer._pathway_context(cells)

    cells = _valid_table_2e_cells()
    del cells[(5, columns[3])]
    with pytest.raises(ValueError, match="partial row"):
        importer._pathway_context(cells)

    cells = _valid_table_2e_cells()
    cells[(5, columns[3])] = "0.000001"
    with pytest.raises(ValueError, match="qValue is invalid"):
        importer._pathway_context(cells)


def test_builder_rejects_source_size_hash_and_header_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.xlsx"
    source.write_bytes(b"not-the-pinned-workbook")
    with pytest.raises(ValueError, match="source size mismatch"):
        importer.build_catalog(source)

    monkeypatch.setattr(importer, "SOURCE_SIZE_BYTES", source.stat().st_size)
    with pytest.raises(ValueError, match="source SHA-256 mismatch"):
        importer.build_catalog(source)

    cells = _valid_table_2d_cells()
    cells[(4, importer.TABLE_2D_COLUMNS["NEU"][0])] = "Gene label"
    with pytest.raises(ValueError, match="unexpected NEU table headers"):
        importer._protein_signatures(cells)


def test_ooxml_reader_rejects_formula_cells() -> None:
    worksheet = f"""
        <worksheet xmlns="{importer._MAIN_NS}">
          <dimension ref="A1:A1"/>
          <sheetData><row r="1"><c r="A1"><f>1+1</f><v>2</v></c></row></sheetData>
        </worksheet>
    """.encode()
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("xl/worksheets/sheet.xml", worksheet)
    archive_bytes.seek(0)
    with (
        zipfile.ZipFile(archive_bytes) as archive,
        pytest.raises(ValueError, match="formula cell is not admissible"),
    ):
        importer._worksheet_cells(archive, "xl/worksheets/sheet.xml", ())


def test_write_and_check_are_deterministic(tmp_path: Path, artifact: dict[str, object]) -> None:
    output = tmp_path / "catalog.json"
    importer._write_or_check(artifact, output, check=False)
    first = output.read_bytes()
    importer._write_or_check(artifact, output, check=False)
    assert output.read_bytes() == first == ARTIFACT_PATH.read_bytes()
    importer._write_or_check(artifact, output, check=True)
    output.write_bytes(first + b" ")
    with pytest.raises(ValueError, match="not the canonical projection"):
        importer._write_or_check(artifact, output, check=True)
