"""Errors for local CPTAC GBM transcript--protein discordance evidence."""


class TranscriptProteinDiscordanceError(ValueError):
    """Base error for this research-only cohort model."""


class DiscordanceInputError(TranscriptProteinDiscordanceError):
    """Raised when a strict model or query input is invalid."""


class DiscordanceFitNotEvaluableError(TranscriptProteinDiscordanceError):
    """Raised when no gene clears the prespecified held-out support gates."""


class DiscordanceSourceLockError(TranscriptProteinDiscordanceError):
    """Raised when local fitting inputs do not match their exact source locks."""


class DiscordanceArtifactIntegrityError(TranscriptProteinDiscordanceError):
    """Raised when local artifact bytes or their bound semantics are invalid."""


__all__ = [
    "DiscordanceArtifactIntegrityError",
    "DiscordanceFitNotEvaluableError",
    "DiscordanceInputError",
    "DiscordanceSourceLockError",
    "TranscriptProteinDiscordanceError",
]
