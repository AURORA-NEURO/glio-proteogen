"""Shared strict replay-validation helpers.

Pydantic deliberately does not revalidate an existing model instance by
default.  Replay verifiers must therefore round-trip through a plain Python
mapping before accepting a model supplied by a caller, including a
``model_copy(update=...)`` value.
"""

from __future__ import annotations

from pydantic import BaseModel, TypeAdapter


def revalidate_replay_result[ModelT: BaseModel](
    adapter: TypeAdapter[ModelT],
    value: object,
) -> ModelT:
    """Freshly validate a replay result, even when ``value`` is a model.

    The first validation preserves the adapter's strict input policy.  The
    second validation consumes a plain Python mapping, bypassing Pydantic's
    ``revalidate_instances='never'`` fast path and re-running every model
    validator against a potentially tampered instance.
    """

    validated = adapter.validate_python(value, strict=True)
    return adapter.validate_python(
        validated.model_dump(mode="python", warnings=False),
        strict=True,
    )
