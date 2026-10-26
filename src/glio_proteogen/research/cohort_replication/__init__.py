"""Exploratory aggregate cohort replication with exact replay."""

from .canonical import canonical_request_digest, result_payload_digest
from .contracts import (
    ALGORITHM_ID,
    ALGORITHM_VERSION,
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    PROFILE_ID,
    ReplayRequest,
    ReplayResult,
    ReplicationProfile,
    ReplicationRequest,
    ReplicationResult,
)
from .demo import synthetic_demo_request
from .engine import analyze_replication, verify_replay
from .profile import algorithm_profile

__all__ = [
    "ALGORITHM_ID",
    "ALGORITHM_VERSION",
    "MAX_REPLAY_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "PROFILE_ID",
    "ReplayRequest",
    "ReplayResult",
    "ReplicationProfile",
    "ReplicationRequest",
    "ReplicationResult",
    "algorithm_profile",
    "analyze_replication",
    "canonical_request_digest",
    "result_payload_digest",
    "synthetic_demo_request",
    "verify_replay",
]
