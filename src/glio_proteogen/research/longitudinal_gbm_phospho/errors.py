"""Sanitized domain errors for the longitudinal phosphosite lane."""


class LongitudinalGbmPhosphoError(ValueError):
    """Base class for safe caller-facing inference failures."""


class SourceProfileIntegrityError(LongitudinalGbmPhosphoError):
    """Raised when the packaged source model fails a content lock."""


class UnknownPhosphositeError(LongitudinalGbmPhosphoError):
    """Raised when input uses a site outside the exact frozen feature inventory."""


class PhosphositeIdentityMismatchError(LongitudinalGbmPhosphoError):
    """Raised when an exact source site is paired with the wrong approved HGNC symbol."""


__all__ = [
    "LongitudinalGbmPhosphoError",
    "PhosphositeIdentityMismatchError",
    "SourceProfileIntegrityError",
    "UnknownPhosphositeError",
]
