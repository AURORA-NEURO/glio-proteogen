"""M02-04 deterministic identification-quality framework."""

from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics.engine import (
    IdentificationQualityAuthorizationError,
    M0204IdentificationQualityEngine,
    compute_identification_quality,
    preflight_identification_quality_authorization,
)
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics.kernel import (
    IdentificationMetricInput,
    IdentificationMetricOutcome,
    compute_identification_metric,
)
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics.plugin import (
    M0204Plugin,
    ValidatedM0204Request,
)
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics.service import (
    M0204Service,
)

__all__ = [
    "IdentificationMetricInput",
    "IdentificationMetricOutcome",
    "IdentificationQualityAuthorizationError",
    "M0204IdentificationQualityEngine",
    "M0204Plugin",
    "M0204Service",
    "ValidatedM0204Request",
    "compute_identification_metric",
    "compute_identification_quality",
    "preflight_identification_quality_authorization",
]
