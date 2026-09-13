"""Sanitized failures for the KNCC GBM factor-graph research lane."""


class KnccGbmFactorGraphError(RuntimeError):
    """Base class for errors safe to map at the research transport boundary."""


class KnccGbmFactorGraphProfileIntegrityError(KnccGbmFactorGraphError):
    """A locked child artifact, topology, or profile binding failed validation."""


class KnccGbmFactorGraphInferenceError(KnccGbmFactorGraphError):
    """Independent child inference could not produce a complete receipt."""


class KnccGbmFactorGraphReplayError(KnccGbmFactorGraphError):
    """Exact independent-block replay could not be completed."""


__all__ = [
    "KnccGbmFactorGraphError",
    "KnccGbmFactorGraphInferenceError",
    "KnccGbmFactorGraphProfileIntegrityError",
    "KnccGbmFactorGraphReplayError",
]
