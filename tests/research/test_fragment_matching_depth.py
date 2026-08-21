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
    assignments = search_module._assign_fragment_peaks((100.0, 100.4), (100.3, 99.5), 0.6)

    assert len(assignments) == 2
    assert assignments == ((0, 1), (1, 0))


def test_equal_mz_peak_ties_are_intensity_canonicalized() -> None:
    """Paired peak-array permutations must not change the matched signal."""

    peptide = "MPEPTIDER"
    fragment = search_module._fragments(peptide)[0][0]
    parameters = search_module.SearchParameters(fragment_tolerance_da=0.001, min_matched_ions=1)
    forward = search_module.search_spectrum_candidates(
        "duplicate-mz",
        1.0,
        {peptide: ("P1",)},
        (fragment, fragment),
        (1.0, 10.0),
        parameters=parameters,
    )
    reverse = search_module.search_spectrum_candidates(
        "duplicate-mz",
        1.0,
        {peptide: ("P1",)},
        (fragment, fragment),
        (10.0, 1.0),
        parameters=parameters,
    )

    assert forward == reverse
    assert forward[0].matched_intensity == 10.0
