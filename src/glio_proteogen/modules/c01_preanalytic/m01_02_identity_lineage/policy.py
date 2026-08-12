"""Closed lineage-transition policy for M01-02.

The table is intentionally data, not control flow.  It can therefore be audited exhaustively
and cannot acquire a permissive transition through a fall-through branch.
"""

from __future__ import annotations

from typing import Final

from glio_proteogen.contracts.m01_02.v1 import (
    M0102_ORDINARY_TRANSITIONS,
    M0102_SPECIAL_LINEAGE_KINDS,
)

ENTITY_KINDS: Final = frozenset(
    {"patient", "specimen", "aliquot", "section", "analyte", "run", "derived_object"}
)

# Direction is parent -> child.  Each ordinary operation is exactly one parent and one child.
ORDINARY_TRANSITIONS: Final = frozenset(
    (operation.value, source.value, target.value)
    for operation, source, target in M0102_ORDINARY_TRANSITIONS
)

POOLABLE_KINDS: Final = frozenset(kind.value for kind in M0102_SPECIAL_LINEAGE_KINDS)
DEMULTIPLEXABLE_KINDS: Final = POOLABLE_KINDS
MAX_ABSOLUTE_DEPTH: Final = 64


def ordinary_transition_allowed(operation: str, parent_kind: str, child_kind: str) -> bool:
    """Return whether the exact closed transition is allowed."""

    return (operation, parent_kind, child_kind) in ORDINARY_TRANSITIONS
