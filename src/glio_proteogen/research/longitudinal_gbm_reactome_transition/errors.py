"""Errors raised by the Reactome transition source catalog."""


class ReactomeTransitionSourceIntegrityError(RuntimeError):
    """The packaged Reactome/PDC000514 binding failed a locked invariant."""


class ReactomeConditionalModelIntegrityError(RuntimeError):
    """The fitted conditional-transition model failed a locked invariant."""


class ReactomeConditionalInferenceError(RuntimeError):
    """Conditional-transition inference could not produce a valid result."""
