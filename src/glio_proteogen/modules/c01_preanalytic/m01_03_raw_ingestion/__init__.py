"""M01-03 raw-format ingestion framework."""

from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion.parser import (
    DEFAULT_REGISTRY,
    IngestionLimits,
    ParserRegistry,
    StructuralParse,
    StructuralParser,
    parse_raw_input,
)
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion.plugin import (
    M0103Plugin,
    RawIngestionSubmission,
    ValidatedM0103Request,
)
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion.service import (
    M0103Service,
    RawIngestionAuthorizationError,
    RawIngestionInputError,
    RawIngestionInputErrorCode,
    RawInputSource,
    preflight_raw_ingestion_authorization,
    reconcile_raw_input_admission,
)

__all__ = [
    "DEFAULT_REGISTRY",
    "IngestionLimits",
    "M0103Plugin",
    "M0103Service",
    "ParserRegistry",
    "RawIngestionAuthorizationError",
    "RawIngestionInputError",
    "RawIngestionInputErrorCode",
    "RawIngestionSubmission",
    "RawInputSource",
    "StructuralParse",
    "StructuralParser",
    "ValidatedM0103Request",
    "parse_raw_input",
    "preflight_raw_ingestion_authorization",
    "reconcile_raw_input_admission",
]
