"""Errors owned by the longitudinal GBM research lane."""


class LongitudinalGbmError(RuntimeError):
    """Base error for protein-level longitudinal concordance inference."""


class SourceProfileIntegrityError(LongitudinalGbmError):
    """Raised when the frozen KNCC source/model profile fails a content lock."""


class LongitudinalInferenceError(LongitudinalGbmError):
    """Raised when a validated request cannot be evaluated deterministically."""


__all__ = [
    "LongitudinalGbmError",
    "LongitudinalInferenceError",
    "SourceProfileIntegrityError",
]
