"""Bounded progress replacement without changing scientific payloads or resuming.

The caller must complete its aggregate privacy guard and canonical encoding
before supplying payload bytes. Only replacement of that one newly written
temporary file is retried. No retry observations enter persisted artifacts.
"""

from __future__ import annotations

import errno
import math
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = [
    "DEFAULT_POLICY",
    "MAX_ATTEMPTS",
    "MAX_PROGRESS_BYTES",
    "MAX_WAIT_SECONDS",
    "RETRYABLE_WINERRORS",
    "RETRY_INTERVAL_SECONDS",
    "ProgressReplacementExhaustedError",
    "ProgressRetryPolicy",
    "write_progress_snapshot",
]

MAX_PROGRESS_BYTES: Final = 64 * 1024
MAX_WAIT_SECONDS: Final = 2.0
MAX_ATTEMPTS: Final = 101
RETRY_INTERVAL_SECONDS: Final = 0.02
RETRYABLE_WINERRORS: Final = frozenset({5, 32, 33})
_WINDOWS: Final = os.name == "nt"


class ProgressReplacementExhaustedError(TimeoutError):
    """An operational interruption; the old and pending files remain intact."""

    def __init__(self) -> None:
        super().__init__("bounded Windows progress replacement retries exhausted")


@dataclass(frozen=True, slots=True)
class ProgressRetryPolicy:
    """Finite limits; caller overrides may only tighten the default limits."""

    max_wait_seconds: float = MAX_WAIT_SECONDS
    max_attempts: int = MAX_ATTEMPTS
    retry_interval_seconds: float = RETRY_INTERVAL_SECONDS

    def __post_init__(self) -> None:
        if (
            type(self.max_wait_seconds) is not float
            or not math.isfinite(self.max_wait_seconds)
            or not 0.0 <= self.max_wait_seconds <= MAX_WAIT_SECONDS
            or type(self.max_attempts) is not int
            or not 1 <= self.max_attempts <= MAX_ATTEMPTS
            or type(self.retry_interval_seconds) is not float
            or not math.isfinite(self.retry_interval_seconds)
            or not 0.0 < self.retry_interval_seconds <= RETRY_INTERVAL_SECONDS
        ):
            raise ValueError("invalid bounded progress replacement policy")


DEFAULT_POLICY: Final = ProgressRetryPolicy()


def _is_retryable_replacement(error: OSError) -> bool:
    winerror = getattr(error, "winerror", None)
    return (
        _WINDOWS
        and isinstance(error, PermissionError)
        and error.errno == errno.EACCES
        and type(winerror) is int
        and winerror in RETRYABLE_WINERRORS
    )


def _replace_pending(
    temporary: Path,
    destination: Path,
    *,
    policy: ProgressRetryPolicy,
    cancel: Callable[[], None] | None,
) -> None:
    """A deadline bounds retry scheduling, not an uninterruptible OS call."""
    deadline = time.monotonic() + policy.max_wait_seconds
    for attempt in range(policy.max_attempts):
        if cancel is not None:
            cancel()
        try:
            temporary.replace(destination)
        except OSError as error:
            if not _is_retryable_replacement(error):
                raise
            remaining = deadline - time.monotonic()
            if attempt + 1 == policy.max_attempts or remaining <= 0.0:
                raise ProgressReplacementExhaustedError from None
            if cancel is not None:
                cancel()
            time.sleep(min(policy.retry_interval_seconds, remaining))
            if cancel is not None:
                cancel()
            if time.monotonic() >= deadline:
                raise ProgressReplacementExhaustedError from None
        else:
            return


def write_progress_snapshot(
    output: Path,
    payload: bytes,
    *,
    cancel: Callable[[], None] | None = None,
    policy: ProgressRetryPolicy = DEFAULT_POLICY,
) -> None:
    """Publish already privacy-checked canonical bytes without overwrite/resume.

    A previous pending file causes FileExistsError. The payload is written
    exactly once with exclusive creation; failures outside the replacement
    operation propagate immediately. Cancellation may raise before the write,
    each replacement attempt, and either side of a wait of at most 20 ms.
    Exhaustion or cancellation after the write retains the pending payload.

    Encoding and privacy checks belong to the caller and must run before this
    function. No timing, attempt count, model data or recovery state is added.
    """
    if (
        not isinstance(output, Path)
        or type(payload) is not bytes
        or not 1 <= len(payload) <= MAX_PROGRESS_BYTES
        or type(policy) is not ProgressRetryPolicy
        or (cancel is not None and not callable(cancel))
    ):
        raise ValueError("invalid bounded progress snapshot arguments")
    if cancel is not None:
        cancel()
    temporary = output / "progress.json.tmp"
    with temporary.open("xb") as stream:
        stream.write(payload)
    _replace_pending(temporary, output / "progress.json", policy=policy, cancel=cancel)
