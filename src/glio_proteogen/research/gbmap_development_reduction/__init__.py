"""Pure, complete-checkpoint GBmap development selection; no source I/O or fit."""

from .contracts import (
    LINEAGE_POLICY_ID,
    REDUCTION_PROFILE_ID,
    SHRINKAGE_GRID,
    CandidateSelectionReceipt,
    EvaluationOutput,
    FoldPreparation,
    LineageValidationCoverage,
    PlanningFeasibilityReceipt,
    ReducedCandidate,
    ReducedFold,
    ReductionError,
    ValidationCheckpoint,
    ValidationRunManifest,
    ValidationTask,
)
from .reduction import assess_manifest_feasibility, reduce_completed_validation

__all__ = [
    "LINEAGE_POLICY_ID",
    "REDUCTION_PROFILE_ID",
    "SHRINKAGE_GRID",
    "CandidateSelectionReceipt",
    "EvaluationOutput",
    "FoldPreparation",
    "LineageValidationCoverage",
    "PlanningFeasibilityReceipt",
    "ReducedCandidate",
    "ReducedFold",
    "ReductionError",
    "ValidationCheckpoint",
    "ValidationRunManifest",
    "ValidationTask",
    "assess_manifest_feasibility",
    "reduce_completed_validation",
]
