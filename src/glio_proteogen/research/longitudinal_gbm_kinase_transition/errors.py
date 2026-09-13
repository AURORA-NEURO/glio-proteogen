"""Sanitized errors for the signature-transition lane."""


class LongitudinalGbmKinaseTransitionError(ValueError):
    """Base class for caller-safe failures."""


class SourceProfileIntegrityError(LongitudinalGbmKinaseTransitionError):
    """The packaged fitted profile failed an exact integrity lock."""


class UnknownPhosphositeError(LongitudinalGbmKinaseTransitionError):
    """An observation is outside the exact PDC000515 inventory."""


class PhosphositeIdentityMismatchError(LongitudinalGbmKinaseTransitionError):
    """An exact PDC phosphosite is paired with the wrong HGNC symbol."""


__all__ = [
    "LongitudinalGbmKinaseTransitionError",
    "PhosphositeIdentityMismatchError",
    "SourceProfileIntegrityError",
    "UnknownPhosphositeError",
]
