"""Integrity and inference failures for the complex-transition lane."""


class ComplexTransitionSourceIntegrityError(RuntimeError):
    """The packaged Reactome/PDC000514 source binding failed an invariant."""


class ComplexTransitionModelIntegrityError(RuntimeError):
    """The fitted complex-member model failed a locked invariant."""


class ComplexTransitionInferenceError(RuntimeError):
    """Complex-member inference could not safely produce a result."""


__all__ = [
    "ComplexTransitionInferenceError",
    "ComplexTransitionModelIntegrityError",
    "ComplexTransitionSourceIntegrityError",
]
