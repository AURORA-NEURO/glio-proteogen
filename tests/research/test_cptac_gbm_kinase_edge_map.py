from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from tools import build_cptac_gbm_kinase_edge_map as edge_map

if TYPE_CHECKING:
    from pathlib import Path


def test_site_key_preserves_ordered_residue_tokens() -> None:
    assert edge_map._site_key("AKT1", "S473s") == ("AKT1", "s473")
    assert edge_map._site_key("RB1", "S807sS811s") == ("RB1", "s807s811")
    assert edge_map._source_site_key("MAPK1-T185tY187y") == ("MAPK1", "t185y187")
    assert edge_map._site_key("", "S1") is None
    assert edge_map._source_site_key("not-a-site") is None


def test_edge_map_aggregates_repeated_source_rows_without_matrix_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    phosphosite = tmp_path / "phosphosite.tsv"
    phosphosite.write_text(
        "Phosphosite\tS1 Log Ratio\tPeptide\tGene\tOrganism\n"
        "NP_1.1:s43\t1.0\tPEP\tGENE1\tHomo sapiens\n"
        "NP_2.1:s17\t1.0\tPEP\tGENE2\tMus musculus\n",
        encoding="utf-8",
    )
    factor = tmp_path / "factor.json"
    factor.write_text(
        json.dumps(
            {
                "source_manifest_digest": "sha256:" + "4" * 64,
                "factors": [
                    {
                        "phosphosite": {
                            "features": [
                                {"feature_id": "NP_1.1:s43"},
                                {"feature_id": "NP_2.1:s17"},
                            ]
                        }
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    fake_edges = (
        SimpleNamespace(
            source_site_label="GENE1-S43s",
            hgnc_symbol="KIN1",
            source_row_id="row-2",
            svm_probability=0.8,
            rho_spearman=0.5,
            known_phosphosite_plus_substrate=True,
        ),
        SimpleNamespace(
            source_site_label="GENE1-S43s",
            hgnc_symbol="KIN1",
            source_row_id="row-1",
            svm_probability=0.6,
            rho_spearman=0.3,
            known_phosphosite_plus_substrate=False,
        ),
        SimpleNamespace(
            source_site_label="GENE2-S17s",
            hgnc_symbol="KIN2",
            source_row_id="row-3",
            svm_probability=0.9,
            rho_spearman=0.9,
            known_phosphosite_plus_substrate=True,
        ),
    )
    fake_catalog = SimpleNamespace(
        edges=fake_edges,
        content_digest="sha256:" + "1" * 64,
        signature_edge_digest="sha256:" + "2" * 64,
        alias_digest="sha256:" + "3" * 64,
        source_license="CC-BY-4.0",
        source_license_url="https://creativecommons.org/licenses/by/4.0/",
    )
    monkeypatch.setattr(edge_map, "master_kinase_catalog", lambda: fake_catalog)

    payload = edge_map.build_edge_map(
        phosphosite,
        factor,
        source_manifest_digest="sha256:" + "4" * 64,
    )
    assert payload["selected_feature_count"] == 2
    assert payload["mapped_feature_count"] == 1
    assert payload["kinase_count"] == 1
    assert payload["edge_count"] == 1
    record = cast("list[dict[str, object]]", payload["edges"])[0]
    assert record["source_edge_ids"] == ["row-1", "row-2"]
    assert record["source_edge_count"] == 2
    assert record["mean_svm_probability"] == 0.7
    assert record["mean_spearman_rho"] == 0.4
    assert record["known_substrate_fraction"] == 0.5
    assert record["edge_weight"] == 0.28
    assert "receipt_digest" in payload


def test_edge_map_rejects_duplicate_matrix_feature_ids(tmp_path: Path) -> None:
    phosphosite = tmp_path / "phosphosite.tsv"
    phosphosite.write_text(
        "Phosphosite\tS1 Log Ratio\tPeptide\tGene\tOrganism\n"
        "NP_1.1:s43\t1.0\tPEP\tGENE1\tHomo sapiens\n"
        "NP_1.1:s43\t2.0\tPEP\tGENE1\tHomo sapiens\n",
        encoding="utf-8",
    )
    factor = tmp_path / "factor.json"
    factor.write_text(
        json.dumps(
            {
                "source_manifest_digest": "sha256:" + "4" * 64,
                "factors": [{"phosphosite": {"features": [{"feature_id": "NP_1.1:s43"}]}}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate or empty"):
        edge_map.build_edge_map(
            phosphosite,
            factor,
            source_manifest_digest="sha256:" + "4" * 64,
        )


def _minimal_edge_map_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    phosphosite = tmp_path / "phosphosite.tsv"
    phosphosite.write_text(
        "Phosphosite\tS1 Log Ratio\tPeptide\tGene\tOrganism\n"
        "NP_1.1:s43\t1.0\tPEP\tGENE1\tHomo sapiens\n",
        encoding="utf-8",
    )
    factor = tmp_path / "factor.json"
    factor.write_text(
        json.dumps(
            {
                "source_manifest_digest": "sha256:" + "4" * 64,
                "factors": [{"phosphosite": {"features": [{"feature_id": "NP_1.1:s43"}]}}],
            }
        ),
        encoding="utf-8",
    )
    fake_edge = SimpleNamespace(
        source_site_label="GENE1-S43s",
        hgnc_symbol="KIN1",
        source_row_id="row-1",
        svm_probability=0.8,
        rho_spearman=0.5,
        known_phosphosite_plus_substrate=True,
    )
    fake_catalog = SimpleNamespace(
        edges=(fake_edge,),
        content_digest="sha256:" + "1" * 64,
        signature_edge_digest="sha256:" + "2" * 64,
        alias_digest="sha256:" + "3" * 64,
        source_license="CC-BY-4.0",
        source_license_url="https://creativecommons.org/licenses/by/4.0/",
    )
    monkeypatch.setattr(edge_map, "master_kinase_catalog", lambda: fake_catalog)
    return phosphosite, factor


def test_edge_map_receipt_replay_verification_detects_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    phosphosite, factor = _minimal_edge_map_inputs(tmp_path, monkeypatch)
    manifest = "sha256:" + "4" * 64
    receipt = edge_map.build_edge_map(phosphosite, factor, source_manifest_digest=manifest)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_bytes(edge_map._canonical_bytes(receipt))

    verified = edge_map.verify_edge_map_receipt(
        phosphosite,
        factor,
        source_manifest_digest=manifest,
        receipt_path=receipt_path,
    )
    assert verified["verified"] is True
    assert cast("dict[str, bool]", verified["checks"])["semantic_equal"] is True

    tampered = dict(receipt)
    tampered["edges"] = [
        dict(cast("list[dict[str, object]]", receipt["edges"])[0], edge_weight=0.99)
    ]
    receipt_path.write_bytes(edge_map._canonical_bytes(tampered))
    rejected = edge_map.verify_edge_map_receipt(
        phosphosite,
        factor,
        source_manifest_digest=manifest,
        receipt_path=receipt_path,
    )
    assert rejected["verified"] is False
    mismatches = cast("list[str]", rejected["mismatches"])
    assert "edges" in mismatches
    assert "receipt_digest" in mismatches
    assert "semantic_equal" in mismatches


def test_edge_map_receipt_verifier_reports_malformed_json(tmp_path: Path) -> None:
    phosphosite = tmp_path / "phosphosite.tsv"
    factor = tmp_path / "factor.json"
    receipt = tmp_path / "receipt.json"
    phosphosite.write_text("", encoding="utf-8")
    factor.write_text("{}", encoding="utf-8")
    receipt.write_text("not-json", encoding="utf-8")
    report = edge_map.verify_edge_map_receipt(
        phosphosite,
        factor,
        source_manifest_digest="sha256:" + "4" * 64,
        receipt_path=receipt,
    )
    assert report["verified"] is False
    assert report["mismatches"] == ["receipt_json"]
