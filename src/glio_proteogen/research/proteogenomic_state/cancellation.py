"""Cooperative execution control for bounded research inference."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event
from time import monotonic


class InferenceCancelledError(RuntimeError):
    """Raised when the caller disconnects or explicitly cancels inference."""


class InferenceDeadlineExceededError(RuntimeError):
    """Raised when inference crosses its monotonic execution deadline."""


@dataclass(slots=True)
class CancellationContext:
    """Thread-safe cancellation flag plus an optional monotonic deadline."""

    deadline: float | None = None
    clock: Callable[[], float] = monotonic
    _cancelled: Event = field(default_factory=Event, init=False, repr=False)

    @classmethod
    def with_timeout(cls, timeout_seconds: float) -> CancellationContext:
        if timeout_seconds <= 0.0:
            raise ValueError("timeout_seconds must be positive")
        return cls(deadline=monotonic() + timeout_seconds)

    def cancel(self) -> None:
        """Request cancellation from an ASGI disconnect watcher."""

        self._cancelled.set()

    def remaining_seconds(self) -> float | None:
        """Return the non-negative time remaining before the deadline."""

        if self.deadline is None:
            return None
        return max(0.0, self.deadline - self.clock())

    def checkpoint(self) -> None:
        """Fail at a deterministic algorithm boundary when execution must stop."""

        if self._cancelled.is_set():
            raise InferenceCancelledError("research inference was cancelled")
        if self.deadline is not None and self.clock() >= self.deadline:
            raise InferenceDeadlineExceededError("research inference exceeded its deadline")


def checkpoint(context: CancellationContext | None) -> None:
    """Run one optional cooperative checkpoint."""

    if context is not None:
        context.checkpoint()


__all__ = [
    "CancellationContext",
    "InferenceCancelledError",
    "InferenceDeadlineExceededError",
    "checkpoint",
]
