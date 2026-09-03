"""Typed failures for the GBMPurity research lane."""


class GbmRnaPurityError(RuntimeError):
    """Base failure sanitized by transport adapters."""


class GbmRnaPurityArtifactError(GbmRnaPurityError):
    """The converted source model failed an integrity check."""


class GbmRnaPurityInferenceError(GbmRnaPurityError):
    """Validated input could not be evaluated safely."""


__all__ = [
    "GbmRnaPurityArtifactError",
    "GbmRnaPurityError",
    "GbmRnaPurityInferenceError",
]
