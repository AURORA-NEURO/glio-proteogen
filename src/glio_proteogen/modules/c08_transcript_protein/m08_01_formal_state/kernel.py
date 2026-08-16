"""Safe declarative invariant kernel for M08-01.

Only the documented comparison and observation languages are interpreted.  The
caller-provided expression is never passed to ``eval`` or another interpreter;
unknown syntax becomes ``not_evaluable`` and therefore cannot produce a false
negative biological claim.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from glio_proteogen.contracts.m08_01 import (
    TranscriptProteinFeatureValue,
    TranscriptProteinInvariant,
    TranscriptProteinInvariantStatus,
    TranscriptProteinMissingness,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

_NUMBER = r"-?(?:\d+(?:\.\d*)?|\.\d+)"
_COMPARISON: Final = re.compile(
    rf"^feature:(?P<feature>[a-zA-Z][a-zA-Z0-9._:-]{{0,127}})\s*"
    rf"(?P<operator>>=|<=|==|>|<)\s*(?P<bound>{_NUMBER})$"
)
_CATEGORY: Final = re.compile(
    r"^feature:(?P<feature>[a-zA-Z][a-zA-Z0-9._:-]{0,127})\s+category\s*==\s*"
    r'"(?P<category>[^"]{1,512})"$'
)


class M0801FormalStateKernel:
    """Evaluate finite, auditable invariant expressions."""

    __slots__ = ()

    def evaluate_invariant(  # noqa: C901, PLR0911 - explicit finite grammar branches.
        self,
        invariant: TranscriptProteinInvariant,
        values: Mapping[str, TranscriptProteinFeatureValue],
    ) -> tuple[TranscriptProteinInvariantStatus, str]:
        expression = invariant.expression
        if expression == "all_values_observed":
            missing = [
                feature_id
                for feature_id in invariant.feature_ids
                if values[feature_id].state is not TranscriptProteinMissingness.OBSERVED
            ]
            if missing:
                return (
                    TranscriptProteinInvariantStatus.NOT_EVALUABLE,
                    "required feature values are not all observed",
                )
            return (
                TranscriptProteinInvariantStatus.SATISFIED,
                "all required feature values are observed",
            )

        category_match = _CATEGORY.fullmatch(expression)
        if category_match is not None:
            feature_id = category_match.group("feature")
            category = category_match.group("category")
            if feature_id not in values or feature_id not in invariant.feature_ids:
                return (
                    TranscriptProteinInvariantStatus.NOT_EVALUABLE,
                    "invariant feature is not bound",
                )
            value = values[feature_id]
            if value.state is not TranscriptProteinMissingness.OBSERVED or value.category is None:
                return (
                    TranscriptProteinInvariantStatus.NOT_EVALUABLE,
                    "category feature is not observed",
                )
            if value.category == category:
                return TranscriptProteinInvariantStatus.SATISFIED, f"{feature_id} matches category"
            return (
                TranscriptProteinInvariantStatus.VIOLATED,
                f"{feature_id} does not match category",
            )

        match = _COMPARISON.fullmatch(expression)
        if match is None:
            return (
                TranscriptProteinInvariantStatus.NOT_EVALUABLE,
                "invariant expression is outside the declarative language",
            )
        feature_id = match.group("feature")
        if feature_id not in values or feature_id not in invariant.feature_ids:
            return TranscriptProteinInvariantStatus.NOT_EVALUABLE, "invariant feature is not bound"
        value = values[feature_id]
        if value.state is not TranscriptProteinMissingness.OBSERVED or value.scalar_value is None:
            return (
                TranscriptProteinInvariantStatus.NOT_EVALUABLE,
                "comparison feature is not an observed scalar",
            )
        bound = float(match.group("bound"))
        actual = value.scalar_value
        operator = match.group("operator")
        satisfied = {
            ">=": actual >= bound,
            "<=": actual <= bound,
            "==": actual == bound,
            ">": actual > bound,
            "<": actual < bound,
        }[operator]
        if satisfied:
            return (
                TranscriptProteinInvariantStatus.SATISFIED,
                f"{feature_id} satisfies {operator} {bound:g}",
            )
        return (
            TranscriptProteinInvariantStatus.VIOLATED,
            f"{feature_id} does not satisfy {operator} {bound:g}",
        )


__all__ = ["M0801FormalStateKernel"]
