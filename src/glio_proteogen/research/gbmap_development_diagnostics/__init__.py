"""Aggregate, non-fitting diagnostics for the unchanged GBmap development core."""

from .audit import audit_reference
from .contracts import (
    GATE_ORDER,
    POLICY_DIGEST,
    PROFILE_ID,
    ComparatorCounts,
    DiagnosticsError,
    GatePassCounts,
    LabelAttrition,
    MarkerAttrition,
    PartitionAttrition,
    ReferenceAttritionReceipt,
    SupportCounts,
)

__all__ = [
    "GATE_ORDER",
    "POLICY_DIGEST",
    "PROFILE_ID",
    "ComparatorCounts",
    "DiagnosticsError",
    "GatePassCounts",
    "LabelAttrition",
    "MarkerAttrition",
    "PartitionAttrition",
    "ReferenceAttritionReceipt",
    "SupportCounts",
    "audit_reference",
]
