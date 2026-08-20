"""Adversarial tests for deterministic one-to-one fragment matching."""

from __future__ import annotations

from typing import TYPE_CHECKING

import glio_proteogen.research.search as search_module

if TYPE_CHECKING:
    import pytest


def test_fragment_matching_maximizes_cardinality_under_ambiguous_peaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A flexible ion must not consume the only peak for a constrained ion."""

    # The first ion is within tolerance of both peaks; the second can only use
    # the first. A nearest-unused loop reports one match, while a valid
    # one-to-one assignment reports two.
    monkeypatch.setattr(search_module, "_is_finite_real", lambda value: True)
    assignments = search_module._assign_fragment_peaks(
        (100.0, 100.4), (100.3, 99.5), 0.6
    )

    assert len(assignments) == 2
    assert assignments == ((0, 1), (1, 0))
