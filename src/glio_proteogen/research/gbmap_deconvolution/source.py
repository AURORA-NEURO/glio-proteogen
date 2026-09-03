"""Pinned GBmap metadata reconciliation and fail-closed source guards.

The expression matrix remains conditionally admitted until its exact Zenodo
bytes have a verified SHA-256. This module resolves a narrower provenance
question without downloading the matrix: the final paper says 109 patients,
whereas its own Table S1 and every CELLxGENE dataset version expose 110 donor
categories. The operational unit is therefore the source donor category; no
category is silently discarded and no biological-person uniqueness claim is
inferred from public identifiers alone.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import Field, field_validator, model_validator

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest

from .errors import GbmapInputError

RECONCILIATION_ID: Final = "gbmap-core-donor-metadata/1.0.0"
PUBLICATION_DOI: Final = "10.1093/neuonc/noaf113"
PUBLICATION_PMCID: Final = "PMC12526130"
PUBLICATION_PROSE_PATIENT_COUNT: Final = 109

SUPPLEMENT_FILENAME: Final = "noaf113_suppl_supplementary_tables_s1-s5.xlsx"
SUPPLEMENT_BYTES: Final = 355_505
SUPPLEMENT_SHA256: Final[Sha256Digest] = (
    "sha256:521aa37db55ec9ecdb6ae2a573fbcc2a9d36c16b44b316917b1b8dbc4efda3fa"
)
SUPPLEMENT_STUDY_PATIENT_COUNTS: Final = (
    ("Yuan2018", 6),
    ("Neftel2019", 23),
    ("Wang2019", 3),
    ("Zhao2020", 1),
    ("Wang2020", 3),
    ("Couturier2020", 11),
    ("Bhaduri2020", 5),
    ("Yu2020", 9),
    ("Wu2020", 4),
    ("Richards2021", 7),
    ("Johnson2020", 5),
    ("Darmanis2017", 4),
    ("Goswami2019", 3),
    ("Sankowski2019", 8),
    ("Mathewson2021", 5),
    ("Pombo2021", 13),
)
SUPPLEMENT_PATIENT_COUNT: Final = sum(count for _, count in SUPPLEMENT_STUDY_PATIENT_COUNTS)

CELLXGENE_COLLECTION_ID: Final = "999f2a15-3d7e-440b-96ae-2c806799c08c"
CELLXGENE_CORE_DATASET_ID: Final = "c888b684-6c51-431f-972a-6c963044cef0"
CELLXGENE_CORE_DATASET_VERSION_ID: Final = "861acfd8-25f0-418b-a445-aa96da232827"
CELLXGENE_SCHEMA_VERSION: Final = "7.1.0"
CELLXGENE_CORE_CELL_COUNT: Final = 338_564
CELLXGENE_CORE_ASSET_BYTES: Final = 8_127_057_404
CELLXGENE_CORE_ASSET_URL: Final = (
    "https://datasets.cellxgene.cziscience.com/861acfd8-25f0-418b-a445-aa96da232827.h5ad"
)
CELLXGENE_CORE_DONOR_IDS: Final = (
    "PJ017",
    "PJ018",
    "PJ025",
    "PJ032",
    "PJ035",
    "PJ048",
    "MGH102",
    "MGH105",
    "MGH114",
    "MGH115",
    "MGH118",
    "MGH124",
    "MGH125",
    "MGH126",
    "MGH143",
    "MGH101",
    "MGH100",
    "MGH104",
    "MGH106",
    "MGH110",
    "MGH113",
    "MGH121",
    "MGH122",
    "MGH128",
    "MGH129",
    "MGH136",
    "MGH151",
    "MGH152",
    "MGH66",
    "SF11644",
    "SF11956",
    "SF11979",
    "GSM4141788",
    "GSM4141789",
    "GSM4141790",
    "PW032",
    "SF11159",
    "SF11209",
    "SF11215",
    "SF11232",
    "SF11247",
    "S2",
    "S1",
    "S11",
    "S12",
    "S13",
    "S15",
    "S3",
    "S5",
    "S6",
    "LWZ",
    "PXC",
    "YCM",
    "ZBY",
    "BT333",
    "BT346",
    "BT363",
    "BT364",
    "BT368",
    "BT389",
    "BT390",
    "BT397",
    "BT402",
    "BT407",
    "BT409",
    "SM006",
    "SM011",
    "SM012",
    "SM017",
    "SM018",
    "G1003",
    "G620",
    "G910",
    "G945",
    "G946",
    "G967",
    "G983",
    "BT_S2",
    "BT_S1",
    "BT_S4",
    "BT_S6",
    "GBM1",
    "GBM2",
    "GBM3",
    "GBM4",
    "Pat13",
    "Pat14",
    "Pat6",
    "Pat9",
    "3182",
    "3282",
    "3295",
    "R1",
    "R2",
    "R3",
    "R4",
    "ND1",
    "ND2",
    "ND3",
    "ND4",
    "ND5",
    "ND6",
    "ND7",
    "ND8",
    "R5",
    "E10",
    "E37",
    "E39",
    "E99",
    "E100",
)


def donor_category_set_digest(donor_ids: tuple[str, ...]) -> Sha256Digest:
    """Hash the donor-category set independently of source presentation order."""

    return sha256_digest(
        {
            "schema": "gbmap-donor-category-set/1.0.0",
            "donor_ids": sorted(donor_ids),
        }
    )


EXPECTED_DONOR_CATEGORY_SET_DIGEST: Final[Sha256Digest] = donor_category_set_digest(
    CELLXGENE_CORE_DONOR_IDS
)


class SourceMetadataMismatch(StrEnum):
    COLLECTION_ID = "collection_id"
    DATASET_ID = "dataset_id"
    DATASET_VERSION_ID = "dataset_version_id"
    SCHEMA_VERSION = "schema_version"
    CELL_COUNT = "cell_count"
    ASSET_BYTES = "asset_bytes"
    ASSET_URL = "asset_url"
    DONOR_CATEGORY_COUNT = "donor_category_count"
    DONOR_CATEGORY_SET = "donor_category_set"


class CellxgeneCoreMetadataSnapshot(FrozenModel):
    """Small public metadata projection; it contains no expression values."""

    collection_id: str = Field(min_length=1, max_length=128)
    dataset_id: str = Field(min_length=1, max_length=128)
    dataset_version_id: str = Field(min_length=1, max_length=128)
    schema_version: str = Field(min_length=1, max_length=32)
    cell_count: int = Field(gt=0)
    asset_bytes: int = Field(gt=0)
    asset_url: str = Field(min_length=1, max_length=512)
    donor_ids: tuple[str, ...] = Field(min_length=1, max_length=512)

    @field_validator(
        "collection_id",
        "dataset_id",
        "dataset_version_id",
        "schema_version",
        "asset_url",
    )
    @classmethod
    def text_is_canonical(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("source metadata text must be non-blank and unpadded")
        return value

    @field_validator("donor_ids")
    @classmethod
    def donor_ids_are_unique_and_canonical(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() or item != item.strip() or len(item) > 128 for item in value):
            raise ValueError("donor IDs must be non-blank, unpadded, and bounded")
        if len(value) != len(set(value)):
            raise ValueError("donor IDs must be unique source categories")
        return value


class SourceMetadataVerification(FrozenModel):
    verification_id: Literal["gbmap-core-donor-metadata/1.0.0"] = "gbmap-core-donor-metadata/1.0.0"
    snapshot_digest: Sha256Digest
    donor_category_set_digest: Sha256Digest
    donor_category_count: int = Field(ge=1)
    supplement_study_count: Literal[16] = 16
    supplement_patient_count: Literal[110] = 110
    publication_prose_patient_count: Literal[109] = 109
    operational_grouping_policy: Literal["retain_all_source_donor_categories"] = (
        "retain_all_source_donor_categories"
    )
    discrepancy_state: Literal[
        "paper_prose_conflicts_with_final_supplement_and_source_metadata"
    ] = "paper_prose_conflicts_with_final_supplement_and_source_metadata"
    biological_person_count_claim_permitted: Literal[False] = False
    exact_metadata_match: bool
    mismatch_codes: tuple[SourceMetadataMismatch, ...]

    @model_validator(mode="after")
    def state_is_consistent(self) -> Self:
        if self.exact_metadata_match != (not self.mismatch_codes):
            raise ValueError("metadata match state and mismatch codes disagree")
        return self


def pinned_cellxgene_snapshot() -> CellxgeneCoreMetadataSnapshot:
    """Return the exact small-metadata snapshot audited on 2026-08-30."""

    return CellxgeneCoreMetadataSnapshot(
        collection_id=CELLXGENE_COLLECTION_ID,
        dataset_id=CELLXGENE_CORE_DATASET_ID,
        dataset_version_id=CELLXGENE_CORE_DATASET_VERSION_ID,
        schema_version=CELLXGENE_SCHEMA_VERSION,
        cell_count=CELLXGENE_CORE_CELL_COUNT,
        asset_bytes=CELLXGENE_CORE_ASSET_BYTES,
        asset_url=CELLXGENE_CORE_ASSET_URL,
        donor_ids=CELLXGENE_CORE_DONOR_IDS,
    )


def verify_cellxgene_metadata(
    snapshot: CellxgeneCoreMetadataSnapshot,
) -> SourceMetadataVerification:
    """Compare public metadata to the pinned core without order-sensitive donor logic."""

    mismatches: list[SourceMetadataMismatch] = []
    scalar_checks: tuple[tuple[object, object, SourceMetadataMismatch], ...] = (
        (
            snapshot.collection_id,
            CELLXGENE_COLLECTION_ID,
            SourceMetadataMismatch.COLLECTION_ID,
        ),
        (snapshot.dataset_id, CELLXGENE_CORE_DATASET_ID, SourceMetadataMismatch.DATASET_ID),
        (
            snapshot.dataset_version_id,
            CELLXGENE_CORE_DATASET_VERSION_ID,
            SourceMetadataMismatch.DATASET_VERSION_ID,
        ),
        (
            snapshot.schema_version,
            CELLXGENE_SCHEMA_VERSION,
            SourceMetadataMismatch.SCHEMA_VERSION,
        ),
        (snapshot.cell_count, CELLXGENE_CORE_CELL_COUNT, SourceMetadataMismatch.CELL_COUNT),
        (
            snapshot.asset_bytes,
            CELLXGENE_CORE_ASSET_BYTES,
            SourceMetadataMismatch.ASSET_BYTES,
        ),
        (snapshot.asset_url, CELLXGENE_CORE_ASSET_URL, SourceMetadataMismatch.ASSET_URL),
    )
    mismatches.extend(code for observed, expected, code in scalar_checks if observed != expected)
    if len(snapshot.donor_ids) != len(CELLXGENE_CORE_DONOR_IDS):
        mismatches.append(SourceMetadataMismatch.DONOR_CATEGORY_COUNT)
    observed_donor_digest = donor_category_set_digest(snapshot.donor_ids)
    if observed_donor_digest != EXPECTED_DONOR_CATEGORY_SET_DIGEST:
        mismatches.append(SourceMetadataMismatch.DONOR_CATEGORY_SET)
    mismatch_codes = tuple(sorted(set(mismatches), key=lambda item: item.value))
    return SourceMetadataVerification(
        snapshot_digest=sha256_digest(snapshot),
        donor_category_set_digest=observed_donor_digest,
        donor_category_count=len(snapshot.donor_ids),
        exact_metadata_match=not mismatch_codes,
        mismatch_codes=mismatch_codes,
    )


def require_pinned_cellxgene_metadata(
    snapshot: CellxgeneCoreMetadataSnapshot,
) -> SourceMetadataVerification:
    """Fail closed before extraction if public source metadata drifted."""

    verification = verify_cellxgene_metadata(snapshot)
    if not verification.exact_metadata_match:
        raise GbmapInputError("GBmap source metadata does not match the pinned core snapshot")
    return verification


def source_reconciliation_receipt() -> SourceMetadataVerification:
    """Return the locked 110-category decision receipt."""

    return require_pinned_cellxgene_metadata(pinned_cellxgene_snapshot())


__all__ = [
    "CELLXGENE_COLLECTION_ID",
    "CELLXGENE_CORE_ASSET_BYTES",
    "CELLXGENE_CORE_ASSET_URL",
    "CELLXGENE_CORE_CELL_COUNT",
    "CELLXGENE_CORE_DATASET_ID",
    "CELLXGENE_CORE_DATASET_VERSION_ID",
    "CELLXGENE_CORE_DONOR_IDS",
    "CELLXGENE_SCHEMA_VERSION",
    "EXPECTED_DONOR_CATEGORY_SET_DIGEST",
    "PUBLICATION_DOI",
    "PUBLICATION_PMCID",
    "PUBLICATION_PROSE_PATIENT_COUNT",
    "RECONCILIATION_ID",
    "SUPPLEMENT_BYTES",
    "SUPPLEMENT_FILENAME",
    "SUPPLEMENT_PATIENT_COUNT",
    "SUPPLEMENT_SHA256",
    "SUPPLEMENT_STUDY_PATIENT_COUNTS",
    "CellxgeneCoreMetadataSnapshot",
    "SourceMetadataMismatch",
    "SourceMetadataVerification",
    "donor_category_set_digest",
    "pinned_cellxgene_snapshot",
    "require_pinned_cellxgene_metadata",
    "source_reconciliation_receipt",
    "verify_cellxgene_metadata",
]
