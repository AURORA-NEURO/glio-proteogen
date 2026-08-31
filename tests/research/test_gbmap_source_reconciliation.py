from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.research.gbmap_deconvolution import (
    CELLXGENE_COLLECTION_ID,
    CELLXGENE_CORE_DATASET_ID,
    CELLXGENE_CORE_DATASET_VERSION_ID,
    CELLXGENE_CORE_DONOR_IDS,
    EXPECTED_DONOR_CATEGORY_SET_DIGEST,
    SUPPLEMENT_STUDY_PATIENT_COUNTS,
    CellxgeneCoreMetadataSnapshot,
    GbmapInputError,
    SourceMetadataMismatch,
    development_profile,
    donor_category_set_digest,
    pinned_cellxgene_snapshot,
    require_pinned_cellxgene_metadata,
    source_reconciliation_receipt,
    verify_cellxgene_metadata,
)


def _snapshot(**updates: object) -> CellxgeneCoreMetadataSnapshot:
    payload = pinned_cellxgene_snapshot().model_dump(mode="python")
    payload.update(updates)
    return CellxgeneCoreMetadataSnapshot.model_validate(payload)


def test_locked_sources_agree_on_110_operational_categories() -> None:
    receipt = source_reconciliation_receipt()
    assert len(CELLXGENE_CORE_DONOR_IDS) == len(set(CELLXGENE_CORE_DONOR_IDS)) == 110
    assert sum(count for _, count in SUPPLEMENT_STUDY_PATIENT_COUNTS) == 110
    assert len(SUPPLEMENT_STUDY_PATIENT_COUNTS) == 16
    assert receipt.exact_metadata_match
    assert receipt.mismatch_codes == ()
    assert receipt.donor_category_count == 110
    assert receipt.donor_category_set_digest == EXPECTED_DONOR_CATEGORY_SET_DIGEST
    assert receipt.publication_prose_patient_count == 109
    assert receipt.supplement_patient_count == 110
    assert receipt.operational_grouping_policy == "retain_all_source_donor_categories"
    assert not receipt.biological_person_count_claim_permitted


def test_donor_verification_is_order_invariant_but_snapshot_receipt_is_not() -> None:
    expected = verify_cellxgene_metadata(pinned_cellxgene_snapshot())
    reversed_snapshot = _snapshot(donor_ids=tuple(reversed(CELLXGENE_CORE_DONOR_IDS)))
    observed = verify_cellxgene_metadata(reversed_snapshot)
    assert observed.exact_metadata_match
    assert observed.donor_category_set_digest == expected.donor_category_set_digest
    assert observed.snapshot_digest != expected.snapshot_digest
    assert donor_category_set_digest(reversed_snapshot.donor_ids) == (
        EXPECTED_DONOR_CATEGORY_SET_DIGEST
    )


@pytest.mark.parametrize(
    ("updates", "expected_code"),
    [
        ({"collection_id": "other-collection"}, SourceMetadataMismatch.COLLECTION_ID),
        ({"dataset_id": "other-dataset"}, SourceMetadataMismatch.DATASET_ID),
        ({"dataset_version_id": "other-version"}, SourceMetadataMismatch.DATASET_VERSION_ID),
        ({"schema_version": "8.0.0"}, SourceMetadataMismatch.SCHEMA_VERSION),
        ({"cell_count": 338_563}, SourceMetadataMismatch.CELL_COUNT),
        ({"asset_bytes": 8_127_057_403}, SourceMetadataMismatch.ASSET_BYTES),
        ({"asset_url": "https://example.invalid/core.h5ad"}, SourceMetadataMismatch.ASSET_URL),
        (
            {"donor_ids": CELLXGENE_CORE_DONOR_IDS[:-1]},
            SourceMetadataMismatch.DONOR_CATEGORY_COUNT,
        ),
        (
            {"donor_ids": (*CELLXGENE_CORE_DONOR_IDS[:-1], "UNEXPECTED")},
            SourceMetadataMismatch.DONOR_CATEGORY_SET,
        ),
    ],
)
def test_metadata_drift_is_explicit_and_fails_closed(
    updates: dict[str, object],
    expected_code: SourceMetadataMismatch,
) -> None:
    snapshot = _snapshot(**updates)
    verification = verify_cellxgene_metadata(snapshot)
    assert not verification.exact_metadata_match
    assert expected_code in verification.mismatch_codes
    with pytest.raises(GbmapInputError, match="does not match the pinned core snapshot"):
        require_pinned_cellxgene_metadata(snapshot)


@pytest.mark.parametrize(
    "donor_ids",
    [
        (*CELLXGENE_CORE_DONOR_IDS, CELLXGENE_CORE_DONOR_IDS[0]),
        (*CELLXGENE_CORE_DONOR_IDS[:-1], ""),
        (*CELLXGENE_CORE_DONOR_IDS[:-1], " padded "),
    ],
)
def test_malformed_donor_categories_are_rejected(donor_ids: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        _snapshot(donor_ids=donor_ids)


def test_profile_admits_reconciled_source_only_for_private_offline_development() -> None:
    profile = development_profile()
    assert profile.source.cellxgene_collection_id == CELLXGENE_COLLECTION_ID
    assert profile.source.cellxgene_core_dataset_id == CELLXGENE_CORE_DATASET_ID
    assert profile.source.cellxgene_core_dataset_version_id == (CELLXGENE_CORE_DATASET_VERSION_ID)
    assert profile.source.source_donor_category_count == 110
    assert profile.source.donor_category_set_digest == EXPECTED_DONOR_CATEGORY_SET_DIGEST
    assert profile.source.publication_prose_patient_count == 109
    assert profile.source.final_supplement_patient_count == 110
    assert not profile.source.biological_person_count_claim_permitted
    assert profile.source.verified_sha256 == (
        "sha256:cb48db2e31299b41d2fe2b6004fadbabe49957bf7d6d72396139db12366ecd8a"
    )
    assert profile.source.exact_source_admitted
    assert profile.feature_identity_state == "admitted_stable_hgnc_crosswalk_only"
    assert profile.source_feature_count == 5_000
    assert profile.stable_hgnc_mapping_count == 4_924
    assert profile.unique_model_eligible_hgnc_count == 4_923
    assert profile.unresolved_feature_count == 76
    assert not profile.unresolved_feature_in_model_permitted
    assert not profile.model_available
    assert not profile.analysis_runtime_available
