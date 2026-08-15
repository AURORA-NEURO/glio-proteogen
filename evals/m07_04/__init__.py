"""Evaluator package for provisional M07-04.

The evaluator remains lazy so ``python -m evals.m07_04.run`` does not load
the module before ``runpy`` executes it, which would produce a false warning.
"""

from collections.abc import Callable
from typing import Final

_EVALUATE_NAME: Final = "evaluate"


def __getattr__(name: str) -> Callable[[], dict[str, object]]:
    if name != _EVALUATE_NAME:
        raise AttributeError(name)
    from .run import evaluate  # noqa: PLC0415

    return evaluate


__all__ = ["evaluate"]
