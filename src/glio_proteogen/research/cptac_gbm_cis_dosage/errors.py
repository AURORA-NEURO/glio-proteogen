"""Sanitized errors for local CPTAC GBM cis-dosage evidence."""


class CisDosageError(RuntimeError):
    """Base class for safe cis-dosage failures."""


class SourceLockError(CisDosageError):
    """A local source does not match its exact admitted snapshot."""


class ArtifactIntegrityError(CisDosageError):
    """A fitted artifact is malformed, oversized, or content-mismatched."""


class FitNotEvaluableError(CisDosageError):
    """The locked local sources cannot support a bounded fit."""


__all__ = [
    "ArtifactIntegrityError",
    "CisDosageError",
    "FitNotEvaluableError",
    "SourceLockError",
]
