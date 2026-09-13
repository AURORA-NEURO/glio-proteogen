"""Local-only CPTAC GBM transcript--protein discordance evidence."""

from .artifact import TranscriptProteinDiscordanceArtifact, load_artifact
from .contracts import (
    MAX_ARTIFACT_BYTES,
    MAX_QUERY_GENES,
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    PROFILE_ID,
    FitReceipt,
    ReplayVerificationRequest,
    ReplayVerificationResult,
    TranscriptProteinDiscordanceProfile,
    TranscriptProteinDiscordanceRequest,
    TranscriptProteinDiscordanceResult,
)
from .fitter import fit_local_artifact
from .profile import algorithm_profile
from .service import (
    analyze_transcript_protein_discordance,
    verify_transcript_protein_discordance_replay,
)

__all__ = [
    "MAX_ARTIFACT_BYTES",
    "MAX_QUERY_GENES",
    "MAX_REPLAY_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "PROFILE_ID",
    "FitReceipt",
    "ReplayVerificationRequest",
    "ReplayVerificationResult",
    "TranscriptProteinDiscordanceArtifact",
    "TranscriptProteinDiscordanceProfile",
    "TranscriptProteinDiscordanceRequest",
    "TranscriptProteinDiscordanceResult",
    "algorithm_profile",
    "analyze_transcript_protein_discordance",
    "fit_local_artifact",
    "load_artifact",
    "verify_transcript_protein_discordance_replay",
]
