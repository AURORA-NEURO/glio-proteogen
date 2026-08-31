"""Sanitized failures for source-independent GBmap deconvolution numerics."""


class GbmapDeconvolutionError(ValueError):
    """Base class for fail-closed GBmap deconvolution errors."""


class GbmapInputError(GbmapDeconvolutionError):
    """A numerical input violates the GBmap model domain."""


class GbmapNumericalError(GbmapDeconvolutionError):
    """A valid-domain calculation cannot produce a finite result."""


class GbmapSourceAdmissionError(GbmapInputError):
    """The offline source bytes do not satisfy the reviewed source lock."""


class GbmapExtractionError(GbmapInputError):
    """The offline source cannot be reduced to the strict aggregate boundary."""


__all__ = [
    "GbmapDeconvolutionError",
    "GbmapExtractionError",
    "GbmapInputError",
    "GbmapNumericalError",
    "GbmapSourceAdmissionError",
]
