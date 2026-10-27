"""Aggregate-only conservation contracts for the complete planned RNA axis."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from glio_proteogen.kernel.models import FrozenModel, Sha256Digest

from .contracts import ExecutionPolicy  # noqa: TC001 -- Pydantic resolves this field at runtime

OUTCOMES = (
    "source_hold",
    "schema_rejected",
    "domain_rejected",
    "estimated",
    "context_unknown",
    "context_out_of_scope",
    "context_conflicting",
    "below_coverage_gate",
    "zero_recognized_sum",
    "limited_support_disallowed",
)
_Count = Annotated[int, Field(strict=True, ge=0, le=72)]


class OutcomeCounts(FrozenModel):
    source_hold: _Count = 0
    schema_rejected: _Count = 0
    domain_rejected: _Count = 0
    estimated: _Count = 0
    context_unknown: _Count = 0
    context_out_of_scope: _Count = 0
    context_conflicting: _Count = 0
    below_coverage_gate: _Count = 0
    zero_recognized_sum: _Count = 0
    limited_support_disallowed: _Count = 0


class ExecutionProtocol(FrozenModel):
    schema_version: Literal["cptac-gbm-native-star-purity-execution-protocol/1.0.0"] = (
        "cptac-gbm-native-star-purity-execution-protocol/1.0.0"
    )
    profile_digest: Sha256Digest
    protocol_digest: Sha256Digest
    planned_files: Literal[72] = 72
    planned_rna_bytes: int = Field(strict=True, ge=72)
    metadata_binding_digest: Sha256Digest
    ordered_rna_input_inventory_digest: Sha256Digest
    model_axis_digest: Sha256Digest
    clinical_receipt_digest: Sha256Digest
    processing_source_digest: Sha256Digest
    policy: ExecutionPolicy


class ExecutionReport(FrozenModel):
    schema_version: Literal["cptac-gbm-native-star-purity-execution-report/1.0.0"] = (
        "cptac-gbm-native-star-purity-execution-report/1.0.0"
    )
    complete: Literal[True] = True
    protocol_digest: Sha256Digest
    report_digest: Sha256Digest
    planned_files: Literal[72] = 72
    planned_rna_bytes: int = Field(strict=True, ge=72)
    verified_rna_bytes: int = Field(strict=True, ge=0)
    read_rna_files: _Count
    projected_files: _Count
    coverage_supported_files: _Count
    numerically_ready_files: _Count
    model_executions: _Count
    outcomes: OutcomeCounts
    feature_state_totals: tuple[
        Annotated[int, Field(strict=True, ge=0, le=72 * 5829)],
        Annotated[int, Field(strict=True, ge=0, le=72 * 5829)],
        Annotated[int, Field(strict=True, ge=0, le=72 * 5829)],
        Annotated[int, Field(strict=True, ge=0, le=72 * 5829)],
        Annotated[int, Field(strict=True, ge=0, le=72 * 5829)],
        Annotated[int, Field(strict=True, ge=0, le=72 * 5829)],
    ]
    model_axis_digest: Sha256Digest
    clinical_receipt_digest: Sha256Digest
    ordered_execution_inventory_digest: Sha256Digest
    individual_results_exported: Literal[False] = False
    new_scientific_inference_lane: Literal[False] = False
    clinical_validation: Literal[False] = False

    @model_validator(mode="after")
    def conserve_axis(self) -> Self:
        rejected = self.outcomes.schema_rejected + self.outcomes.domain_rejected
        if (
            sum(self.outcomes.model_dump().values()) != self.planned_files
            or self.read_rna_files != self.planned_files - self.outcomes.source_hold
            or self.projected_files != self.read_rna_files - rejected
            or sum(self.feature_state_totals) != self.projected_files * 5829
            or self.coverage_supported_files > self.projected_files
            or self.numerically_ready_files > self.projected_files
            or self.model_executions != self.outcomes.estimated
            or self.model_executions > self.numerically_ready_files
            or sum(self.feature_state_totals[:2]) < 4664 * self.numerically_ready_files
            or sum(self.feature_state_totals[:2]) < 5771 * self.coverage_supported_files
            or self.feature_state_totals[0] < self.numerically_ready_files
            or not self.read_rna_files <= self.verified_rna_bytes <= self.planned_rna_bytes
            or self.verified_rna_bytes > self.read_rna_files * 10_000_000
            or self.planned_rna_bytes > 72 * 10_000_000
            or self.planned_rna_bytes - self.verified_rna_bytes < self.outcomes.source_hold
            or (self.read_rna_files == 72 and self.verified_rna_bytes != self.planned_rna_bytes)
        ):
            raise ValueError("execution report does not conserve the planned axis")
        return self


__all__ = ["OUTCOMES", "ExecutionProtocol", "ExecutionReport", "OutcomeCounts"]
