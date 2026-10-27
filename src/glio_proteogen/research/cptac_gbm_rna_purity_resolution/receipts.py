"""Aggregate evidence counts for the locked, nonqualifying clinical source review.

Historical pathology, a single IDH1 assay result, specimen ancestry and descriptive
field availability remain separate observations. These receipts never infer an
IDH-wildtype diagnosis or admit a case to the purity model.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, field_validator, model_validator

from glio_proteogen.kernel.models import FrozenModel, Sha256Digest

_Count = Annotated[int, Field(strict=True, ge=0, le=65)]


class Idh1Counts(FrozenModel):
    """The source IDH1 R132H field, without extending its assay scope."""

    negative: _Count
    not_performed: _Count
    unknown: _Count
    positive: _Count

    @model_validator(mode="after")
    def conserve_targeted_cases(self) -> Self:
        if sum(self.model_dump().values()) != 65:
            raise ValueError("IDH1 observations do not conserve the targeted axis")
        return self


class SpecimenCounts(FrozenModel):
    """Exact selected-specimen evidence, separately from a case-level match."""

    exact_specimen: _Count
    specimen_mismatch: _Count
    unresolved: _Count

    @model_validator(mode="after")
    def conserve_targeted_cases(self) -> Self:
        if sum(self.model_dump().values()) != 65:
            raise ValueError("specimen observations do not conserve the targeted axis")
        return self


class FieldAvailability(FrozenModel):
    """Reported descriptive fields; availability carries no eligibility claim."""

    reported_age: _Count
    sex: _Count
    mgmt_status: _Count
    vital_status: _Count
    survival_days: _Count
    treatment_history: _Count


class ClinicalSourceReceipt(FrozenModel):
    """The exact published Table S1 review, with its claim ceiling frozen."""

    SEAL_FIELD: ClassVar[str] = "source_receipt_digest"
    schema_version: Literal["cptac-gbm-2024-clinical-table-s1/1.0.0"] = (
        "cptac-gbm-2024-clinical-table-s1/1.0.0"
    )
    publication_doi: Literal["10.1016/j.ccell.2024.06.004"] = "10.1016/j.ccell.2024.06.004"
    source_url: Literal[
        "https://ars.els-cdn.com/content/image/1-s2.0-S1535610824002290-mmc2.xlsx"
    ] = "https://ars.els-cdn.com/content/image/1-s2.0-S1535610824002290-mmc2.xlsx"
    source_sha256: Literal[
        "sha256:f91ab4ee136e2a9baf75b72213e63bad2b7b606ead60cd1ef24bf8ae76ed0d27"
    ] = "sha256:f91ab4ee136e2a9baf75b72213e63bad2b7b606ead60cd1ef24bf8ae76ed0d27"
    source_bytes: Literal[69_098] = 69_098
    reviewed_cases: Literal[65] = 65
    historical_pathology_cases: Literal[65] = 65
    explicit_idh_wildtype_cases: Literal[0] = 0
    explicit_idh2_scope_cases: Literal[0] = 0
    explicit_integrated_diagnosis_cases: Literal[0] = 0
    idh1_r132h: Idh1Counts
    specimen: SpecimenCounts
    field_availability: FieldAvailability
    source_qualified_cases: Literal[0] = 0
    source_receipt_digest: Sha256Digest

    @field_validator(
        "source_bytes",
        "reviewed_cases",
        "historical_pathology_cases",
        "explicit_idh_wildtype_cases",
        "explicit_idh2_scope_cases",
        "explicit_integrated_diagnosis_cases",
        "source_qualified_cases",
        mode="before",
    )
    @staticmethod
    def literal_counts_are_integers(value: object) -> object:
        if type(value) is not int:
            raise ValueError("source review counts must be integers")
        return value


class ClinicalResolutionReceipt(FrozenModel):
    """A complete-axis source review that preserves the inherited abstentions."""

    SEAL_FIELD: ClassVar[str] = "receipt_digest"
    schema_version: Literal["cptac-gbm-clinical-gap-review/1.0.0"] = (
        "cptac-gbm-clinical-gap-review/1.0.0"
    )
    profile_id: Literal["cptac-gbm-clinical-gap-review/1.0.0"] = (
        "cptac-gbm-clinical-gap-review/1.0.0"
    )
    planned_cases: Literal[72] = 72
    targeted_unknown_cases: Literal[65] = 65
    preserved_out_of_scope_cases: Literal[6] = 6
    preserved_source_hold_cases: Literal[1] = 1
    baseline_clinical_receipt_digest: Sha256Digest
    ordered_case_axis_digest: Sha256Digest
    ordered_target_bindings_digest: Sha256Digest
    source_receipt_digest: Sha256Digest
    resolution_evidence_digest: Sha256Digest
    source_qualified_cases: Literal[0] = 0
    clinical_diagnosis_inferred: Literal[False] = False
    research_population_inferred: Literal[False] = False
    eligibility_admitted: Literal[False] = False
    rna_read: Literal[False] = False
    model_executed: Literal[False] = False
    individual_results_exported: Literal[False] = False
    research_use_only: Literal[True] = True
    receipt_digest: Sha256Digest

    @field_validator(
        "planned_cases",
        "targeted_unknown_cases",
        "preserved_out_of_scope_cases",
        "preserved_source_hold_cases",
        "source_qualified_cases",
        mode="before",
    )
    @staticmethod
    def literal_counts_are_integers(value: object) -> object:
        if type(value) is not int:
            raise ValueError("resolution review counts must be integers")
        return value

    @field_validator(
        "clinical_diagnosis_inferred",
        "research_population_inferred",
        "eligibility_admitted",
        "rna_read",
        "model_executed",
        "individual_results_exported",
        "research_use_only",
        mode="before",
    )
    @staticmethod
    def literal_declarations_are_booleans(value: object) -> object:
        if type(value) is not bool:
            raise ValueError("resolution review declarations must be boolean")
        return value


__all__ = [
    "ClinicalResolutionReceipt",
    "ClinicalSourceReceipt",
    "FieldAvailability",
    "Idh1Counts",
    "SpecimenCounts",
]
