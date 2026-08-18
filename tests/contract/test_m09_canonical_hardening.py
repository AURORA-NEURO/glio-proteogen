"""Adversarial canonicalization tests for the integrated M09 replay surface."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Any

import pytest

from glio_proteogen.contracts.m09_01.canonical import normalized_request as normalize_m0901
from glio_proteogen.contracts.m09_02.canonical import normalized_request as normalize_m0902
from glio_proteogen.contracts.m09_03.canonical import normalized_request as normalize_m0903
from glio_proteogen.contracts.m09_04.canonical import normalized_request as normalize_m0904
from glio_proteogen.contracts.m09_05.canonical import normalized_request as normalize_m0905
from glio_proteogen.contracts.m09_06.canonical import normalized_request as normalize_m0906
from glio_proteogen.contracts.m09_07.canonical import normalized_request as normalize_m0907
from glio_proteogen.contracts.m09_08.canonical import normalized_request as normalize_m0908


class HostileMapping(Mapping[str, object]):
    """Mapping whose accessors prove whether canonicalization traversed it."""

    def __init__(self) -> None:
        self.accesses = 0

    def __getitem__(self, key: str) -> object:
        del key
        self.accesses += 1
        raise AssertionError

    def __iter__(self) -> Iterator[str]:
        self.accesses += 1
        raise AssertionError

    def __len__(self) -> int:
        self.accesses += 1
        raise AssertionError


class DictSubclass(dict[str, object]):
    """Dict subclass rejected so overridden mapping behavior cannot be trusted."""


@pytest.mark.parametrize(
    "normalizer",
    [
        normalize_m0901,
        normalize_m0902,
        normalize_m0903,
        normalize_m0904,
        normalize_m0905,
        normalize_m0906,
        normalize_m0907,
        normalize_m0908,
    ],
)
def test_canonicalizers_reject_hostile_mapping_without_access(
    normalizer: Callable[[Any], Any],
) -> None:
    candidate = HostileMapping()

    with pytest.raises(TypeError, match="exact dicts"):
        normalizer(candidate)

    assert candidate.accesses == 0


@pytest.mark.parametrize(
    "normalizer",
    [
        normalize_m0901,
        normalize_m0902,
        normalize_m0903,
        normalize_m0904,
        normalize_m0905,
        normalize_m0906,
        normalize_m0907,
        normalize_m0908,
    ],
)
def test_canonicalizers_reject_dict_subclasses_and_copy_exact_dict(
    normalizer: Callable[[Any], Any],
) -> None:
    with pytest.raises(TypeError, match="exact dicts"):
        normalizer(DictSubclass(request_id="request.m09"))

    source = {"request_id": "request.m09"}
    normalized = normalizer(source)
    assert normalized == source
    assert normalized is not source
