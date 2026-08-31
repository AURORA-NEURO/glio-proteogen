from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import numpy as np
import pytest
from pydantic import ValidationError

from glio_proteogen.adapters.api import create_app
from glio_proteogen.deployment import DeploymentSettings, _operation_catalog
from glio_proteogen.research import gbmap_deconvolution as gbmap_package
from glio_proteogen.research.gbmap_deconvolution import (
    EXPECTED_FITTED_ARTIFACT_CONTENT_DIGEST,
    AggregateReference,
    DonorLabelAggregate,
    GbmapDevelopmentProfile,
    development_profile,
    donor_label_is_eligible,
    largest_remainder_scale,
    lineage_eligibility,
)
from glio_proteogen.research.gbmap_deconvolution import aggregate as aggregate_module

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64


def _counts(feature_count: int = 12, *, total: int = 20_000) -> np.ndarray[Any, np.dtype[np.int64]]:
    values = np.zeros(feature_count, dtype=np.int64)
    values[0] = total
    return values


def _detected(feature_count: int = 12, *, cells: int = 20) -> np.ndarray[Any, np.dtype[np.int32]]:
    values = np.zeros(feature_count, dtype=np.int32)
    values[0] = cells
    return values


def _record(  # noqa: PLR0913 - compact aggregate fixture factory.
    donor: str,
    study: str,
    label: str,
    *,
    feature_count: int = 12,
    cells: int = 20,
    total: int = 20_000,
) -> DonorLabelAggregate:
    return DonorLabelAggregate(
        donor_key=donor,
        study_key=study,
        modeled_label=label,
        source_labels=(label + "-source",),
        cell_count=cells,
        gene_counts=_counts(feature_count, total=total),
        detected_cell_counts=_detected(feature_count, cells=min(cells, total)),
        total_umis=total,
    )


def _reference(records: tuple[DonorLabelAggregate, ...]) -> AggregateReference:
    feature_count = len(records[0].gene_counts)
    return AggregateReference(
        feature_ids=tuple(f"ENSG{index:05d}" for index in range(feature_count)),
        gene_symbols=tuple(f"GENE{index}" for index in range(feature_count)),
        records=records,
        source_file_sha256=DIGEST_A,
        source_bytes=8_975_644_082,
        taxonomy_digest=DIGEST_B,
        extraction_recipe_digest=DIGEST_C,
    )


def test_donor_label_aggregate_is_defensively_frozen_and_reconciled() -> None:
    counts = np.asarray([12_000, 8_000], dtype=np.int64)
    detected = np.asarray([20, 18], dtype=np.int32)
    record = DonorLabelAggregate(
        donor_key="donor-1",
        study_key="study-1",
        modeled_label="myeloid",
        source_labels=("microglia", "macrophage"),
        cell_count=20,
        gene_counts=counts,
        detected_cell_counts=detected,
        total_umis=20_000,
    )

    counts[0] = 0
    detected[0] = 0
    assert record.gene_counts.tolist() == [12_000, 8_000]
    assert record.detected_cell_counts.tolist() == [20, 18]
    assert not record.gene_counts.flags.writeable
    assert not record.detected_cell_counts.flags.writeable
    assert record.source_labels == ("macrophage", "microglia")
    assert record.eligible_for_reference
    with pytest.raises(ValueError, match="read-only"):
        record.gene_counts[0] = 1
    with pytest.raises(FrozenInstanceError):
        record.cell_count = 21  # type: ignore[misc]


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"gene_counts": [20_000, 0]}, "exact NumPy ndarray"),
        ({"gene_counts": np.asarray([20_000, 0], dtype=np.int32)}, "exact int64"),
        ({"gene_counts": np.asarray([20_000.0, 0.0])}, "exact int64"),
        ({"gene_counts": np.asarray([True, False])}, "exact int64"),
        ({"gene_counts": np.asarray([[20_000, 0]], dtype=np.int64)}, "one-dimensional"),
        ({"gene_counts": np.asarray([20_001, -1], dtype=np.int64)}, "negative"),
        ({"detected_cell_counts": np.asarray([20, 0], dtype=np.int64)}, "exact int32"),
        ({"detected_cell_counts": np.asarray([21, 0], dtype=np.int32)}, "cell_count"),
        (
            {
                "cell_count": 20_000,
                "detected_cell_counts": np.asarray([19_999, 1], dtype=np.int32),
            },
            "detected cell",
        ),
        ({"total_umis": 19_999}, "reconcile"),
        ({"cell_count": True}, "exact positive integer"),
        ({"total_umis": False}, "exact nonnegative integer"),
        ({"source_labels": ("source", "source")}, "unique"),
    ],
)
def test_donor_label_aggregate_rejects_coercion_and_inconsistent_counts(
    update: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "donor_key": "donor-1",
        "study_key": "study-1",
        "modeled_label": "myeloid",
        "source_labels": ("source",),
        "cell_count": 20,
        "gene_counts": np.asarray([20_000, 0], dtype=np.int64),
        "detected_cell_counts": np.asarray([20, 0], dtype=np.int32),
        "total_umis": 20_000,
    }
    values.update(update)
    with pytest.raises(ValueError, match=message):
        DonorLabelAggregate(**values)  # type: ignore[arg-type]


def test_aggregate_reference_canonicalizes_order_and_binds_content() -> None:
    first_record = _record("donor-b", "study-b", "lineage-b")
    second_record = _record("donor-a", "study-a", "lineage-a")
    first = _reference((first_record, second_record))
    second = _reference((second_record, first_record))

    assert first.records == second.records
    assert first.feature_order_digest == second.feature_order_digest
    assert first.aggregate_content_digest == second.aggregate_content_digest
    assert first.modeled_labels == ("lineage-a", "lineage-b")
    assert first.donor_count == 2
    assert first.study_count == 2

    changed = _record("donor-a", "study-a", "lineage-a", total=20_001)
    changed_reference = _reference((first_record, changed))
    assert changed_reference.aggregate_content_digest != first.aggregate_content_digest


def test_aggregate_reference_computes_content_digests_once() -> None:
    records = (
        _record("donor-b", "study-b", "lineage-b"),
        _record("donor-a", "study-a", "lineage-a"),
    )
    digest_module = cast("Any", aggregate_module)
    with (
        patch.object(
            aggregate_module,
            "_feature_order_digest",
            wraps=digest_module._feature_order_digest,
        ) as feature_digest,
        patch.object(
            aggregate_module,
            "_aggregate_content_digest",
            wraps=digest_module._aggregate_content_digest,
        ) as content_digest,
    ):
        reference = _reference(records)
        expected_feature = reference.feature_order_digest
        expected_content = reference.aggregate_content_digest
        assert reference.feature_order_digest == expected_feature
        assert reference.aggregate_content_digest == expected_content
        assert reference.feature_order_digest == expected_feature
        assert reference.aggregate_content_digest == expected_content

    assert feature_digest.call_count == 1
    assert content_digest.call_count == 1


def test_aggregate_reference_rejects_ambiguous_structure() -> None:
    record = _record("donor-1", "study-1", "lineage-a")
    base: dict[str, object] = {
        "feature_ids": tuple(f"ENSG{index:05d}" for index in range(12)),
        "gene_symbols": tuple(f"GENE{index}" for index in range(12)),
        "records": (record,),
        "source_file_sha256": DIGEST_A,
        "source_bytes": 8_975_644_082,
        "taxonomy_digest": DIGEST_B,
        "extraction_recipe_digest": DIGEST_C,
    }

    cases: tuple[tuple[dict[str, object], str], ...] = (
        ({"feature_ids": ("ENSG1", "ENSG1")}, "unique"),
        ({"gene_symbols": ("GENE1",)}, "aligned"),
        ({"records": (_record("donor-1", "study-1", "lineage-a", feature_count=11),)}, "align"),
        ({"source_file_sha256": "pending"}, "SHA-256"),
        ({"source_bytes": True}, "exact positive integer"),
    )
    for update, message in cases:
        values = {**base, **update}
        with pytest.raises(ValueError, match=message):
            AggregateReference(**values)  # type: ignore[arg-type]

    duplicate = _record("donor-1", "study-1", "lineage-a")
    with pytest.raises(ValueError, match="donor and modeled-label"):
        _reference((record, duplicate))

    other_study = _record("donor-1", "study-2", "lineage-b")
    with pytest.raises(ValueError, match="more than one study"):
        _reference((record, other_study))


def test_largest_remainder_scaling_is_exact_and_feature_tie_broken() -> None:
    counts = np.asarray([1, 1, 1], dtype=np.int64)
    scaled = largest_remainder_scale(counts, ("B", "A", "C"), target_depth=2)

    assert scaled.tolist() == [1, 1, 0]
    assert int(np.sum(scaled)) == 2
    assert counts.tolist() == [1, 1, 1]
    assert not scaled.flags.writeable
    same = largest_remainder_scale(
        np.asarray([12_000, 8_000], dtype=np.int64),
        ("A", "B"),
    )
    assert same.tolist() == [12_000, 8_000]
    assert not same.flags.writeable


@pytest.mark.parametrize(
    ("counts", "features", "depth", "message"),
    [
        (np.asarray([0, 0], dtype=np.int64), ("A", "B"), 1, "zero-total"),
        (np.asarray([1, 0], dtype=np.int64), ("A", "B"), 2, "never upsamples"),
        (np.asarray([2, 0], dtype=np.int32), ("A", "B"), 1, "exact int64"),
        (np.asarray([2, 0], dtype=np.int64), ("A", "A"), 1, "unique"),
        (np.asarray([2, 0], dtype=np.int64), ("A",), 1, "align"),
        (np.asarray([2, 0], dtype=np.int64), ("A", "B"), True, "exact positive integer"),
    ],
)
def test_largest_remainder_scaling_rejects_invalid_domains(
    counts: np.ndarray[Any, Any],
    features: tuple[str, ...],
    depth: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        largest_remainder_scale(counts, features, target_depth=depth)


def test_lineage_eligibility_uses_only_usable_donors_and_fixed_floors() -> None:
    lineage_a = tuple(
        _record(f"a-{index}", f"study-{index % 3}", "lineage-a") for index in range(8)
    )
    lineage_b = tuple(
        _record(f"b-{index}", f"study-{index % 2}", "lineage-b") for index in range(7)
    )
    low_depth = _record("b-low", "study-2", "lineage-b", total=19_999)
    reference = _reference((*lineage_a, *lineage_b, low_depth))

    results = lineage_eligibility(reference, {"lineage-a": 12, "lineage-b": 11})
    assert results[0].modeled_label == "lineage-a"
    assert results[0].eligible
    assert results[0].usable_donor_count == 8
    assert results[0].usable_study_count == 3
    assert results[0].reasons == ()
    assert not results[1].eligible
    assert results[1].usable_donor_count == 7
    assert results[1].usable_study_count == 2
    assert results[1].reasons == (
        "insufficient_usable_donors",
        "insufficient_usable_studies",
        "insufficient_stable_genes",
    )
    assert not donor_label_is_eligible(low_depth)

    with pytest.raises(ValueError, match="unknown modeled lineage"):
        lineage_eligibility(reference, {"lineage-a": 12, "lineage-c": 12})
    with pytest.raises(ValueError, match="cannot exceed"):
        lineage_eligibility(reference, {"lineage-a": 13, "lineage-b": 11})
    with pytest.raises(ValueError, match="exact nonnegative integer"):
        lineage_eligibility(reference, {"lineage-a": True, "lineage-b": 11})


def test_development_profile_cryptographically_proves_the_model_is_unavailable() -> None:
    profile = development_profile()

    assert profile.fit_state == "development_unfitted"
    assert profile.source.verified_sha256 == (
        "sha256:cb48db2e31299b41d2fe2b6004fadbabe49957bf7d6d72396139db12366ecd8a"
    )
    assert profile.source.exact_source_admitted
    assert profile.expected_fitted_artifact_content_digest is None
    assert EXPECTED_FITTED_ARTIFACT_CONTENT_DIGEST is None
    assert profile.intended_output == (
        "reference_constrained_rna_mixture_weights_with_unexplained_mass"
    )
    assert profile.maximum_support == "limited"
    assert not profile.supported_output_permitted
    assert not profile.model_available
    assert not profile.analysis_runtime_available
    assert not profile.public_http_mounted
    assert not profile.public_cli_mounted
    assert not profile.bundled_fitted_artifact
    assert not profile.histologic_cell_fraction_claim_permitted
    assert not profile.clinical_use_permitted
    assert development_profile() == profile

    forged = profile.model_dump(mode="python")
    forged["profile_digest"] = DIGEST_A
    with pytest.raises(ValidationError, match="profile digest"):
        GbmapDevelopmentProfile.model_validate(forged, strict=True)


def test_unfitted_package_has_only_identity_data_and_no_runtime_route(tmp_path: Path) -> None:
    package_path = Path(gbmap_package.__file__).parent
    assert not {
        "adapter.py",
        "catalog.py",
        "demo.py",
        "engine.py",
        "service.py",
    } & {path.name for path in package_path.iterdir()}
    packaged_data = {
        path.relative_to(package_path).as_posix()
        for path in (package_path / "data").rglob("*")
        if path.is_file()
    }
    assert packaged_data == {gbmap_package.FEATURE_IDENTITY_RESOURCE}

    database_path = tmp_path / "events.sqlite3"
    app = create_app(database_path)
    paths = {str(getattr(route, "path", "")) for route in app.routes}
    assert not any("gbmap" in path.lower() or "deconvolution" in path.lower() for path in paths)

    catalog = _operation_catalog(
        app,
        DeploymentSettings(database_path=database_path, environment="test"),
    )
    operations = cast("list[dict[str, object]]", catalog["operations"])
    assert not any(
        "gbmap" in str(operation["path"]).lower()
        or "deconvolution" in str(operation["path"]).lower()
        for operation in operations
    )
