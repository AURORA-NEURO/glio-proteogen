"""M01-05 deterministic artifact-detection framework."""

from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection.engine import (
    M0105DetectionEngine,
    detect_artifacts,
)
from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection.kernel import (
    Detection,
    FlagDecision,
    Predicate,
    Rule,
    Signal,
    SignalState,
    evaluate_rules,
)
from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection.plugin import (
    M0105Plugin,
    ValidatedM0105Request,
)
from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection.service import (
    M0105Service,
)

__all__ = [
    "Detection",
    "FlagDecision",
    "M0105DetectionEngine",
    "M0105Plugin",
    "M0105Service",
    "Predicate",
    "Rule",
    "Signal",
    "SignalState",
    "ValidatedM0105Request",
    "detect_artifacts",
    "evaluate_rules",
]
