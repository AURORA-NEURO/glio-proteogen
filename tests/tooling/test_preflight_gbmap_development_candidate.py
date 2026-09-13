"""Safety and provenance tests for the private GBmap structural preflight."""

# ruff: noqa: PLR2004, TRY003

from __future__ import annotations

import json
from functools import lru_cache
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pytest
from tools.fit_gbmap_development_candidate import GbmapDevelopmentFitDriverError

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.gbmap_deconvolution import (
    AggregateReference,
    DonorLabelAggregate,
    GbmapExtractionReceipt,
    GbmapExtractionResult,
    build_validation_split_plan,
    production_extraction_recipe,
    production_label_taxonomy,
    production_reduction_recipe_digest,
)
from tools import preflight_gbmap_development_candidate as preflight

if TYPE_CHECKING:
    from pathlib import Path

_REVIEWED_SHA256 = "sha256:" + "a" * 64
_SOURCE_BYTES = 8_975_644_082


@lru_cache(maxsize=1)
def _reference() -> AggregateReference:
    feature_ids = tuple(f"ENSG{index:05d}" for index in range(24))
    mes_like = np.asarray([1_500] * 12 + [166] * 11 + [174], dtype=np.int64)
    npc_like = np.asarray([166] * 11 + [174] + [1_500] * 12, dtype=np.int64)
    studies = ("Bhaduri2020", "Couturier2020", "Darmanis2017", "Goswami2019")
    records: list[DonorLabelAggregate] = []
    for study_index, study in enumerate(studies):
        for donor_index in range(3):
            donor = f"private-donor-{study_index}-{donor_index:02d}"
            for label, counts in (("MES-like", mes_like), ("NPC-like", npc_like)):
                records.append(
                    DonorLabelAggregate(
                        donor_key=donor,
                        study_key=study,
                        modeled_label=label,
                        source_labels=(label,),
                        cell_count=40,
                        gene_counts=counts,
                        detected_cell_counts=np.asarray([30] * 24, dtype=np.int32),
                        total_umis=20_000,
                    )
                )
    return AggregateReference(
        feature_ids=feature_ids,
        gene_symbols=feature_ids,
        records=tuple(records),
        source_file_sha256=_REVIEWED_SHA256,
        source_bytes=_SOURCE_BYTES,
        taxonomy_digest=production_label_taxonomy().taxonomy_digest,
        extraction_recipe_digest=production_reduction_recipe_digest(),
    )


@lru_cache(maxsize=1)
def _extraction() -> GbmapExtractionResult:
    reference = _reference()
    fields: dict[str, object] = {
        "receipt_id": "gbmap-extraction-receipt/1.0.0",
        "source_sha256": _REVIEWED_SHA256,
        "source_bytes": _SOURCE_BYTES,
        "extraction_recipe_digest": reference.extraction_recipe_digest,
        "taxonomy_digest": reference.taxonomy_digest,
        "feature_order_digest": reference.feature_order_digest,
        "h5py_version": "3.16.0",
        "cell_count": 338_564,
        "retained_cell_count": 338_564,
        "explicitly_excluded_cell_count": 0,
        "source_donor_category_count": 113,
        "grouped_donor_category_count": 110,
        "source_study_category_count": 17,
        "grouped_study_count": 16,
        "source_label_count": 20,
        "modeled_label_count": 20,
        "record_count": len(reference.records),
        "cell_level_material_retained": False,
        "donor_identifiers_retained": False,
        "donor_hashes_retained": False,
        "donor_profiles_retained": False,
        "aggregate_content_digest_retained": False,
    }
    receipt = GbmapExtractionReceipt(
        receipt_digest=sha256_digest(fields),
        **fields,  # type: ignore[arg-type]
    )
    return GbmapExtractionResult(reference=reference, receipt=receipt)


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "private-source" / "scarches_core_GBmap.h5ad"
    source.parent.mkdir()
    source.write_bytes(b"small mocked source; exact extractor is replaced")
    return source


def _install_extractor(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[str], dict[str, object]]:
    events: list[str] = []
    captured: dict[str, object] = {}

    def fake_extract(source: Path, **kwargs: object) -> GbmapExtractionResult:
        events.append("extract")
        captured["source"] = source
        captured.update(kwargs)
        return _extraction()

    original_plan = build_validation_split_plan

    def observed_plan(reference: AggregateReference):  # type: ignore[no-untyped-def]
        events.append("split")
        captured["split_reference"] = reference
        return original_plan(reference)

    monkeypatch.setattr(preflight, "extract_pinned_gbmap_reference", fake_extract)
    monkeypatch.setattr(preflight, "build_validation_split_plan", observed_plan)
    return events, captured


def _receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, preflight.GbmapDevelopmentPreflightReceipt]:
    _install_extractor(monkeypatch)
    source = _source(tmp_path)
    receipt = preflight.build_development_preflight_receipt(
        source,
        _REVIEWED_SHA256,
        development_only_acknowledged=True,
        sha256_independently_reviewed=True,
    )
    return source, receipt


def _redigest(document: dict[str, object]) -> bytes:
    body = {key: value for key, value in document.items() if key != "receipt_digest"}
    document["receipt_digest"] = sha256_digest(body)
    return canonical_json_bytes(document) + b"\n"


def _as_dict(value: object) -> dict[str, object]:
    assert type(value) is dict
    return cast("dict[str, object]", value)


def test_preflight_runs_exact_extraction_and_split_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events, captured = _install_extractor(monkeypatch)
    source = _source(tmp_path)
    receipt = preflight.build_development_preflight_receipt(
        source,
        _REVIEWED_SHA256,
        development_only_acknowledged=True,
        sha256_independently_reviewed=True,
    )

    assert events == ["extract", "split"]
    assert captured["source"] is source
    assert captured["split_reference"] is _reference()
    lock = cast("Any", captured["lock"])
    assert lock.source_id == "gbmap-core-zenodo-6962901"
    assert lock.expected_bytes == _SOURCE_BYTES
    assert lock.sha256 == _REVIEWED_SHA256
    assert receipt.preflight_state == "structural_extraction_complete_training_not_run"
    assert receipt.hierarchy_training_executed is False
    assert receipt.model_fitted is False
    assert receipt.runtime_mount_permitted is False
    assert receipt.task_summary.validation_fold_count == 7
    assert receipt.task_summary.whole_study_fold_count == 4
    assert receipt.task_summary.within_study_donor_fold_count == 3
    assert receipt.task_summary.shrinkage_candidate_count == 4
    assert receipt.task_summary.validation_hierarchy_fit_upper_bound == 56
    assert receipt.task_summary.total_hierarchy_fit_upper_bound == 58


def test_canonical_receipt_excludes_private_and_feature_material(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, receipt = _receipt(tmp_path, monkeypatch)
    payload = preflight.canonical_preflight_receipt_bytes(receipt)

    assert len(payload) < preflight.MAX_OUTPUT_BYTES
    assert b"private-donor" not in payload
    assert b"ENSG" not in payload
    assert str(source).encode() not in payload
    assert b"aggregate_content_digest" in payload
    assert b'aggregate_content_digest_retained":false' in payload
    assert b"gene_counts" not in payload
    assert b"detected_cell_counts" not in payload
    assert preflight.validate_preflight_json_bytes(payload) == receipt


@pytest.mark.parametrize("private_field", ["donor_key", "feature_id", "source_path"])
def test_unknown_private_fields_are_rejected_even_when_outer_digest_is_recomputed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    private_field: str,
) -> None:
    _, receipt = _receipt(tmp_path, monkeypatch)
    document = cast(
        "dict[str, object]",
        json.loads(preflight.canonical_preflight_receipt_bytes(receipt)),
    )
    document[private_field] = "sensitive"

    with pytest.raises(GbmapDevelopmentFitDriverError):
        preflight.validate_preflight_json_bytes(_redigest(document))


def test_configuration_tamper_fails_after_outer_redigest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, receipt = _receipt(tmp_path, monkeypatch)
    document = cast(
        "dict[str, object]",
        json.loads(preflight.canonical_preflight_receipt_bytes(receipt)),
    )
    document["training_configuration_digest"] = "sha256:" + "b" * 64

    with pytest.raises(GbmapDevelopmentFitDriverError):
        preflight.validate_preflight_json_bytes(_redigest(document))


def test_task_count_tamper_fails_after_outer_redigest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, receipt = _receipt(tmp_path, monkeypatch)
    document = cast(
        "dict[str, object]",
        json.loads(preflight.canonical_preflight_receipt_bytes(receipt)),
    )
    summary = _as_dict(document["task_summary"])
    summary["total_hierarchy_fit_upper_bound"] = 59

    with pytest.raises(GbmapDevelopmentFitDriverError):
        preflight.validate_preflight_json_bytes(_redigest(document))


def test_plain_recipe_digest_cannot_replace_exact_reduction_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, receipt = _receipt(tmp_path, monkeypatch)
    document = cast(
        "dict[str, object]",
        json.loads(preflight.canonical_preflight_receipt_bytes(receipt)),
    )
    wrong = production_extraction_recipe().extraction_recipe_digest
    assert wrong != production_reduction_recipe_digest()
    extraction = _as_dict(document["extraction_receipt"])
    extraction["extraction_recipe_digest"] = wrong
    extraction_body = {key: value for key, value in extraction.items() if key != "receipt_digest"}
    extraction["receipt_digest"] = sha256_digest(extraction_body)
    split = _as_dict(document["validation_split_receipt"])
    split["extraction_recipe_digest"] = wrong

    with pytest.raises(GbmapDevelopmentFitDriverError):
        preflight.validate_preflight_json_bytes(_redigest(document))


def test_extraction_error_is_sanitized_without_path_or_donor_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(tmp_path)

    def failed_extract(*args: object, **kwargs: object) -> GbmapExtractionResult:
        del args, kwargs
        raise RuntimeError(f"{source}: private-donor-secret")

    monkeypatch.setattr(preflight, "extract_pinned_gbmap_reference", failed_extract)
    with pytest.raises(GbmapDevelopmentFitDriverError) as raised:
        preflight.build_development_preflight_receipt(
            source,
            _REVIEWED_SHA256,
            development_only_acknowledged=True,
            sha256_independently_reviewed=True,
        )
    assert str(raised.value) == "GBmap preflight extraction failed closed"
    assert raised.value.__cause__ is None
    assert str(source) not in str(raised.value)
    assert "private-donor" not in str(raised.value)


def test_atomic_publication_is_idempotent_and_refuses_different_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, receipt = _receipt(tmp_path, monkeypatch)
    destination = tmp_path / "receipts" / "gbmap-preflight.json"
    expected = preflight.canonical_preflight_receipt_bytes(receipt)

    assert preflight.write_preflight_receipt(destination, receipt, source=source) == len(expected)
    assert preflight.write_preflight_receipt(destination, receipt, source=source) == len(expected)
    assert destination.read_bytes() == expected

    conflict = tmp_path / "receipts" / "conflict.json"
    conflict.write_bytes(b"different")
    with pytest.raises(GbmapDevelopmentFitDriverError) as raised:
        preflight.write_preflight_receipt(conflict, receipt, source=source)
    assert str(raised.value) == "GBmap preflight receipt publication failed closed"
    assert conflict.read_bytes() == b"different"


def test_main_reports_only_stable_generic_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _source(tmp_path)

    def failed_run(*args: object, **kwargs: object) -> preflight.GbmapDevelopmentPreflightReceipt:
        del args, kwargs
        raise GbmapDevelopmentFitDriverError(f"{source}: private-donor-secret")

    monkeypatch.setattr(preflight, "run", failed_run)
    result = preflight.main(
        [
            str(source),
            "--reviewed-sha256",
            _REVIEWED_SHA256,
            "--output",
            str(tmp_path / "receipt.json"),
            "--acknowledge-development-only",
            "--acknowledge-sha256-independently-reviewed",
        ]
    )
    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err == "error: GBmap structural preflight failed closed\n"


@pytest.mark.parametrize(
    "acks",
    [(False, True), (True, False), (False, False)],
)
def test_acknowledgements_are_required_before_source_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    acks: tuple[bool, bool],
) -> None:
    development_ack, sha_ack = acks
    called = False

    def forbidden_snapshot(source: Path) -> object:
        del source
        nonlocal called
        called = True
        raise AssertionError("source was accessed")

    monkeypatch.setattr(preflight, "_capture_source_snapshot", forbidden_snapshot)
    with pytest.raises(GbmapDevelopmentFitDriverError):
        preflight.build_development_preflight_receipt(
            tmp_path / "missing.h5ad",
            _REVIEWED_SHA256,
            development_only_acknowledged=development_ack,
            sha256_independently_reviewed=sha_ack,
        )
    assert called is False
