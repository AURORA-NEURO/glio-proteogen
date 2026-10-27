"""Closed aggregate receipts with conserved context, readiness and feature states."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from glio_proteogen.kernel.models import FrozenModel, Sha256Digest

from .context import ContextInventoryReceipt, ContextState
from .identity import ModelAxisReceipt  # noqa: TC001 -- Pydantic evaluates this field type

OUTCOMES = (
    "ready",
    "below_coverage_gate",
    "zero_recognized_sum",
    "schema_rejected",
    "domain_rejected",
)
COVERAGE_BINS = tuple(
    f"coverage_{lower:02d}_to_{lower + 10:03d}_percent" for lower in range(0, 100, 10)
)


class OutcomeCounts(FrozenModel):
    ready: int = Field(ge=0, le=256)
    below_coverage_gate: int = Field(ge=0, le=256)
    zero_recognized_sum: int = Field(ge=0, le=256)
    schema_rejected: int = Field(ge=0, le=256)
    domain_rejected: int = Field(ge=0, le=256)

    @property
    def total(self) -> int:
        return sum(getattr(self, name) for name in OUTCOMES)

    @property
    def schema_valid(self) -> int:
        return self.ready + self.below_coverage_gate + self.zero_recognized_sum


class ContextReadinessCounts(FrozenModel):
    context_state: ContextState
    outcomes: OutcomeCounts


class CoverageBin(FrozenModel):
    label: str
    files: int = Field(ge=0, le=256)


class FeatureStateTotals(FrozenModel):
    observed_positive: int = Field(ge=0)
    observed_zero: int = Field(ge=0)
    absent_feature: int = Field(ge=0)
    unresolved_reference: int = Field(ge=0)
    ambiguous_identity: int = Field(ge=0)
    symbol_disagreement: int = Field(ge=0)

    @property
    def total(self) -> int:
        return sum(self.model_dump().values())


class NativeSchemaTotals(FrozenModel):
    input_bytes: int = Field(ge=0)
    data_rows: int = Field(ge=0)
    gene_rows: int = Field(ge=0)
    summary_rows: int = Field(ge=0)
    versioned_gene_rows: int = Field(ge=0)
    par_y_gene_rows: int = Field(ge=0)
    duplicate_gene_symbol_groups: int = Field(ge=0)
    ambiguous_reference_gene_ids: int = Field(ge=0)
    observed_zero_gene_rows: int = Field(ge=0)


class PreflightProtocol(FrozenModel):
    schema_version: Literal["cptac-gbm-native-star-purity-preflight-protocol/1.0.0"] = (
        "cptac-gbm-native-star-purity-preflight-protocol/1.0.0"
    )
    profile_id: Literal["cptac-gbm-native-star-purity-preflight/1.0.0"] = (
        "cptac-gbm-native-star-purity-preflight/1.0.0"
    )
    protocol_digest: Sha256Digest
    profile_digest: Sha256Digest
    selection_profile: Literal["cptac-gbm-discovery-metadata-plan/1.0.0"] = (
        "cptac-gbm-discovery-metadata-plan/1.0.0"
    )
    planned_files: Literal[72] = 72
    planned_rna_bytes: int = Field(ge=72, le=720_000_000)
    metadata_binding_digest: Sha256Digest
    ordered_rna_input_inventory_digest: Sha256Digest
    model_axis_digest: Sha256Digest
    context_axis_digest: Sha256Digest
    context_evidence_digest: Sha256Digest
    context_source_set_digest: Sha256Digest
    context_input_binding_digest: Sha256Digest
    previous_selection_requires_paired_proteome_cnv: Literal[True] = True
    metadata_plan_stats_cnv_files: Literal[True] = True
    context_filters_count_preflight: Literal[False] = False
    source_plan_eligibility_admitted: Literal[False] = False
    rna_payloads_read_at_protocol_preparation: Literal[False] = False
    models_executed: Literal[False] = False
    redistribution_status: Literal["local_only_terms_unverified"] = "local_only_terms_unverified"


class PreflightReport(FrozenModel):
    schema_version: Literal["cptac-gbm-native-star-purity-preflight-report/1.0.0"] = (
        "cptac-gbm-native-star-purity-preflight-report/1.0.0"
    )
    profile_id: Literal["cptac-gbm-native-star-purity-preflight/1.0.0"] = (
        "cptac-gbm-native-star-purity-preflight/1.0.0"
    )
    complete: Literal[True] = True
    protocol_digest: Sha256Digest
    report_digest: Sha256Digest
    planned_files: Literal[72] = 72
    planned_rna_bytes: int = Field(ge=72, le=720_000_000)
    verified_rna_bytes: int = Field(ge=72, le=720_000_000)
    outcomes: OutcomeCounts
    schema_totals: NativeSchemaTotals
    feature_state_totals: FeatureStateTotals
    recognized_raw_count_sum: int = Field(ge=0)
    coverage_supported_files: int = Field(ge=0, le=256)
    zero_recognized_sum_files: int = Field(ge=0, le=256)
    coverage_histogram: tuple[CoverageBin, ...]
    context_by_readiness: tuple[ContextReadinessCounts, ...]
    model_axis: ModelAxisReceipt
    context: ContextInventoryReceipt
    ordered_projection_inventory_digest: Sha256Digest
    source_plan_eligibility_admitted: Literal[False] = False
    context_qualification_is_clinical_validation: Literal[False] = False
    inference_requests_constructed: Literal[False] = False
    models_executed: Literal[False] = False
    biological_validation: Literal[False] = False
    clinical_validation: Literal[False] = False
    redistribution_status: Literal["local_only_terms_unverified"] = "local_only_terms_unverified"

    @model_validator(mode="after")
    def conservation(self) -> Self:
        valid = self.outcomes.schema_valid
        recognized = (
            self.feature_state_totals.observed_positive + self.feature_state_totals.observed_zero
        )
        # Each bin constrains integer recognized slots, not just file counts.
        # Integer ceiling preserves exact boundaries without float rounding.
        histogram_minimum = sum(
            row.files * ((index * 5_829 + 9) // 10)
            for index, row in enumerate(self.coverage_histogram)
        )
        histogram_maximum = sum(
            row.files * (5_829 if index == 9 else ((index + 1) * 5_829 + 9) // 10 - 1)
            for index, row in enumerate(self.coverage_histogram)
        )
        if (
            self.planned_files != self.outcomes.total
            or self.planned_files != self.context.planned_count
            or self.planned_rna_bytes != self.verified_rna_bytes
            or self.planned_rna_bytes > self.planned_files * 10_000_000
            or not valid <= self.schema_totals.input_bytes <= valid * 10_000_000
            or self.schema_totals.input_bytes > self.verified_rna_bytes
            or self.feature_state_totals.total != valid * 5_829
            or self.schema_totals.data_rows
            != self.schema_totals.gene_rows + self.schema_totals.summary_rows
            or self.schema_totals.summary_rows != valid * 4
            or not valid <= self.schema_totals.gene_rows <= valid * 99_996
            or any(
                getattr(self.schema_totals, name) > self.schema_totals.gene_rows
                for name in (
                    "versioned_gene_rows",
                    "par_y_gene_rows",
                    "ambiguous_reference_gene_ids",
                    "observed_zero_gene_rows",
                )
            )
            or self.schema_totals.duplicate_gene_symbol_groups > self.schema_totals.gene_rows // 2
            or self.feature_state_totals.unresolved_reference
            != valid * self.model_axis.unresolved_reference_features
            or self.feature_state_totals.ambiguous_identity
            < valid * self.model_axis.ambiguous_identity_features
            or recognized > self.schema_totals.gene_rows
            or recognized > valid * self.model_axis.resolved_features
            or self.feature_state_totals.observed_zero > self.schema_totals.observed_zero_gene_rows
            or not self.feature_state_totals.observed_positive
            <= self.recognized_raw_count_sum
            <= self.feature_state_totals.observed_positive * 10**15
            or self.coverage_supported_files > valid
            or self.zero_recognized_sum_files > valid
            or self.outcomes.zero_recognized_sum > self.zero_recognized_sum_files
            or self.zero_recognized_sum_files + self.outcomes.ready > valid
            or self.zero_recognized_sum_files
            > self.outcomes.zero_recognized_sum + self.outcomes.below_coverage_gate
            or self.feature_state_totals.observed_positive < valid - self.zero_recognized_sum_files
            or self.feature_state_totals.observed_positive
            > (valid - self.zero_recognized_sum_files) * self.model_axis.resolved_features
            or self.feature_state_totals.observed_zero < self.outcomes.zero_recognized_sum * 4_664
            or (
                self.zero_recognized_sum_files == valid
                and self.feature_state_totals.observed_positive != 0
            )
            or (self.model_axis.resolved_features < 5_771 and self.coverage_supported_files != 0)
            or self.coverage_supported_files
            > self.outcomes.ready + self.outcomes.zero_recognized_sum
            or self.feature_state_totals.observed_positive < self.outcomes.ready
            or tuple(row.label for row in self.coverage_histogram) != COVERAGE_BINS
            or sum(row.files for row in self.coverage_histogram) != valid
            or not histogram_minimum <= recognized <= histogram_maximum
            or sum(row.files for row in self.coverage_histogram[:8])
            != self.outcomes.below_coverage_gate
            or sum(row.files for row in self.coverage_histogram[8:])
            != self.outcomes.ready + self.outcomes.zero_recognized_sum
            or (
                self.coverage_histogram
                and self.coverage_supported_files > self.coverage_histogram[-1].files
            )
            or tuple(row.context_state for row in self.context_by_readiness) != tuple(ContextState)
            or any(
                row.outcomes.total != getattr(self.context.state_counts, row.context_state.value)
                for row in self.context_by_readiness
            )
            or any(
                sum(getattr(row.outcomes, name) for row in self.context_by_readiness)
                != getattr(self.outcomes, name)
                for name in OUTCOMES
            )
        ):
            raise ValueError("preflight report does not conserve its complete input axis")
        return self


__all__ = [
    "COVERAGE_BINS",
    "OUTCOMES",
    "ContextReadinessCounts",
    "CoverageBin",
    "FeatureStateTotals",
    "NativeSchemaTotals",
    "OutcomeCounts",
    "PreflightProtocol",
    "PreflightReport",
]
