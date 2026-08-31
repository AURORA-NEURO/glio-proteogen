from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections import Counter
from importlib.resources import files
from typing import cast

import pytest

from glio_proteogen.research.gbm_master_kinases import catalog as catalog_module
from glio_proteogen.research.gbm_master_kinases.catalog import (
    EXPECTED_ALIAS_DIGEST,
    EXPECTED_BACKGROUND_LABEL_COUNT,
    EXPECTED_BACKGROUND_TUPLE_COUNT,
    EXPECTED_EDGE_COUNTS,
    EXPECTED_KINASE_COUNTS,
    EXPECTED_REPEATED_KINASE_SITE_EXTRA_ROWS,
    EXPECTED_UNIQUE_TARGET_COUNTS,
    master_kinase_catalog,
)
from glio_proteogen.research.gbm_master_kinases.errors import CatalogIntegrityError
from tools import import_sphinks_master_kinases as importer


def test_catalog_locks_source_identity_and_exact_author_tables() -> None:
    catalog = master_kinase_catalog()
    assert catalog.article_doi == "10.1038/s43018-022-00510-x"
    assert catalog.source_sha256 == (
        "sha256:865a2db1ec99dcf047d6ff56b313a21607b840e5239bb9184739f6f6f217fb88"
    )
    resource = files(catalog_module.__package__).joinpath(catalog_module.CATALOG_RESOURCE)
    document = json.loads(resource.read_bytes())
    source = document["source"]
    assert source["article_authors"] == "Migliozzi et al."
    assert source["article_year"] == 2023
    assert source["pmcid"] == "PMC9970878"
    assert source["article_title"] == (
        "Integrative multi-omics networks identify PKCδ and DNA-PK as master kinases of "
        "glioblastoma subtypes and guide targeted cancer therapy"
    )
    assert source["license"] == "CC-BY-4.0"
    assert source["license_url"] == "https://creativecommons.org/licenses/by/4.0/"
    assert source["copyright"] == "© The Author(s) 2023"
    assert source["transformation_notice"].startswith("Adapted projection:")
    assert "receives no computational privilege" in source["third_party_notice"]
    assert source["source_archive_url"].startswith("https://www.ebi.ac.uk/europepmc/")


def test_table5a_background_and_ambiguity_inventory_are_exact() -> None:
    catalog = master_kinase_catalog()
    assert len(catalog.background_tuples) == EXPECTED_BACKGROUND_TUPLE_COUNT == 34_098
    assert len(catalog.background_labels) == EXPECTED_BACKGROUND_LABEL_COUNT == 30_175
    assert len(catalog.background_tuples) - len(catalog.background_labels) == 3_923
    label_counts = Counter(item.source_site_label for item in catalog.background_tuples)
    assert sum(count > 1 for count in label_counts.values()) == 3_358
    assert max(label_counts.values()) > 1


def test_table5d_preserves_rows_but_exposes_independent_site_inventory() -> None:
    catalog = master_kinase_catalog()
    assert Counter(item.subtype for item in catalog.edges) == Counter(EXPECTED_EDGE_COUNTS)
    assert {
        subtype: len({item.source_site_label for item in catalog.edges if item.subtype == subtype})
        for subtype in EXPECTED_EDGE_COUNTS
    } == EXPECTED_UNIQUE_TARGET_COUNTS
    assert len({item.source_row_id for item in catalog.edges}) == len(catalog.edges) == 3_560
    pair_counts = Counter((item.hgnc_symbol, item.source_site_label) for item in catalog.edges)
    assert sum(count - 1 for count in pair_counts.values()) == (
        EXPECTED_REPEATED_KINASE_SITE_EXTRA_ROWS
    )
    assert all(item.source_site_label in catalog.background_labels for item in catalog.edges)


def test_table5e_author_oracles_and_exact_24_label_mapping() -> None:
    catalog = master_kinase_catalog()
    assert Counter(item.subtype for item in catalog.masters) == Counter(EXPECTED_KINASE_COUNTS)
    assert catalog.alias_digest == EXPECTED_ALIAS_DIGEST
    assert catalog.aliases == importer.KINASE_LABEL_TO_HGNC
    pkcd = next(item for item in catalog.masters if item.source_kinase_label == "PKCD")
    assert pkcd.hgnc_symbol == "PRKCD"
    assert pkcd.subtype == "GPM"
    assert pkcd.source_reference.kinase_activity_mww_score == pytest.approx(2.887525)
    assert pkcd.source_reference.log2fc_activity_subtype_vs_others == pytest.approx(0.5073794)
    assert pkcd.source_reference.p_value == pytest.approx(1.204836e-7)
    dnapk = next(item for item in catalog.masters if item.source_kinase_label == "DNAPK")
    assert dnapk.hgnc_symbol == "PRKDC"
    assert dnapk.subtype == "PPR"
    first_edge = catalog.edges[0]
    assert (
        first_edge.source_row_id,
        first_edge.source_kinase_label,
        first_edge.source_site_label,
    ) == ("table5d:GPM:00005", "PKCD", "ARHGAP15-S43s")
    assert first_edge.svm_probability == pytest.approx(0.953183977521012)


def test_cached_catalog_mappings_are_deeply_immutable() -> None:
    catalog = master_kinase_catalog()
    master = catalog.masters[0]
    modality = next(iter(master.source_reference.modality_mww_scores))
    with pytest.raises(TypeError):
        cast("dict[str, str]", catalog.aliases)["forged"] = "FORGED"
    with pytest.raises(TypeError):
        cast("dict[str, tuple[object, ...]]", catalog.edges_by_kinase)["FORGED"] = ()
    with pytest.raises(TypeError):
        cast(
            "dict[str, dict[str, float]]",
            master.source_reference.modality_mww_scores,
        )[modality]["forged"] = 1.0


def test_catalog_artifact_and_semantic_tampering_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = catalog_module._resource_bytes()
    tampered = original.replace(b'"article_year": 2023', b'"article_year": 2024', 1)
    assert tampered != original
    catalog_module.master_kinase_catalog.cache_clear()
    monkeypatch.setattr(catalog_module, "_resource_bytes", lambda: tampered)
    with pytest.raises(CatalogIntegrityError, match="artifact digest mismatch"):
        catalog_module.master_kinase_catalog()
    monkeypatch.setattr(
        catalog_module,
        "EXPECTED_CATALOG_ARTIFACT_DIGEST",
        "sha256:" + hashlib.sha256(tampered).hexdigest(),
    )
    with pytest.raises(CatalogIntegrityError, match="canonical content digest mismatch"):
        catalog_module.master_kinase_catalog()
    catalog_module.master_kinase_catalog.cache_clear()


def _archive_bytes(entries: tuple[tuple[str, bytes], ...]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return output.getvalue()


def test_archive_download_retries_are_bounded_and_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def flaky(_url: str, _limit: int) -> bytes:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError
        return b"archive"

    monkeypatch.setattr(importer, "DOWNLOAD_RETRY_BACKOFF_SECONDS", (0.0, 0.0, 0.0))
    monkeypatch.setattr(importer, "_download_bounded", flaky)
    assert importer._download_with_retry("https://example.test/source", 100) == b"archive"
    assert attempts == 3


def test_europe_pmc_fallback_selects_one_digest_locked_basename(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    workbook = b"exact-test-workbook"
    archive = _archive_bytes((("supp/43018_2022_510_MOESM2_ESM.xlsx", workbook),))
    responses = iter((b"<html>challenge</html>", archive))
    monkeypatch.setattr(importer, "SOURCE_SIZE_BYTES", len(workbook))
    monkeypatch.setattr(importer, "SOURCE_SHA256", hashlib.sha256(workbook).hexdigest())
    monkeypatch.setattr(importer, "_download_bounded", lambda _url, _limit: next(responses))
    destination = tmp_path / "source.xlsx"
    importer._download_source(destination)
    assert destination.read_bytes() == workbook


@pytest.mark.parametrize(
    "entries",
    [
        (
            ("a/43018_2022_510_MOESM2_ESM.xlsx", b"x"),
            ("b/43018_2022_510_MOESM2_ESM.xlsx", b"x"),
        ),
        (("../43018_2022_510_MOESM2_ESM.xlsx", b"x"),),
    ],
)
def test_europe_pmc_fallback_rejects_duplicate_or_traversal_members(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    entries: tuple[tuple[str, bytes], ...],
) -> None:
    archive = _archive_bytes(entries)
    responses = iter((b"challenge", archive))
    monkeypatch.setattr(importer, "SOURCE_SIZE_BYTES", 1)
    monkeypatch.setattr(importer, "SOURCE_SHA256", hashlib.sha256(b"x").hexdigest())
    monkeypatch.setattr(importer, "_download_bounded", lambda _url, _limit: next(responses))
    with pytest.raises(ValueError, match=r"exactly one|unsafe"):
        importer._download_source(tmp_path / "source.xlsx")
