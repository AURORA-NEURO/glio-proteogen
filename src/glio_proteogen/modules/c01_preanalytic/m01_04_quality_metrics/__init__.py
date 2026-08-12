"""M01-04 deterministic quality-metric framework."""

from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics.calculations import (
    ScalarObservation,
    ScalarResult,
    ScalarState,
    ScalarStatus,
    Thresholds,
    calculate_scalar,
    classify_scalar,
)
from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics.engine import (
    M0104MetricEngine,
    compute_quality_profile,
)
from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics.plugin import (
    M0104Plugin,
    ValidatedM0104Request,
)
from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics.service import (
    M0104Service,
)

__all__ = [
    "M0104MetricEngine",
    "M0104Plugin",
    "M0104Service",
    "ScalarObservation",
    "ScalarResult",
    "ScalarState",
    "ScalarStatus",
    "Thresholds",
    "ValidatedM0104Request",
    "calculate_scalar",
    "classify_scalar",
    "compute_quality_profile",
]
