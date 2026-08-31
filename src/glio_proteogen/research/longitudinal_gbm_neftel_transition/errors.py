"""Errors raised by the Neftel transition source catalog."""


class NeftelTransitionSourceIntegrityError(RuntimeError):
    """The packaged Neftel/PDC000514 binding failed a locked invariant."""


class NeftelConditionalModelIntegrityError(RuntimeError):
    """The fitted conditional-transition model failed a locked invariant."""


class NeftelConditionalInferenceError(RuntimeError):
    """Conditional-transition inference could not produce a valid result."""
