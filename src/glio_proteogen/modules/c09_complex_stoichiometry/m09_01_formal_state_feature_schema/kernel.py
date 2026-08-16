"""Safe declarative invariant evaluator for M09-01 formal complex activity state."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from glio_proteogen.contracts.m09_01 import (
    ComplexActivityFeatureValue,
    ComplexActivityInvariant,
    ComplexActivityInvariantStatus,
    ComplexActivityMissingness,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

_COMPARISON = re.compile(
    r"^feature:(?P<feature>[a-zA-Z][a-zA-Z0-9._:-]{0,127})\s*"
    r"(?P<operator>>=|<=|==|>|<)\s*"
    r"(?P<bound>-?(?:\d+(?:\.\d*)?|\.\d+))$"
)


class M0901FormalStateKernel:
    """Evaluate only the bounded M09-01 expression language.

    Expressions are data, never executable code. Unknown expressions and
    non-observed values remain ``not_evaluable`` so an absence of evidence is
    never represented as a negative biological finding.
    """

    __slots__ = ()

    def evaluate_invariant(  # noqa: PLR0911
        self,
        invariant: ComplexActivityInvariant,
        values: Mapping[str, ComplexActivityFeatureValue],
    ) -> tuple[ComplexActivityInvariantStatus, str]:
        if invariant.expression == "all_values_observed":
            missing = [
                feature_id
                for feature_id in invariant.feature_ids
                if values[feature_id].state is not ComplexActivityMissingness.OBSERVED
            ]
            if missing:
                return (
                    ComplexActivityInvariantStatus.NOT_EVALUABLE,
                    "required feature values are not all observed",
                )
            return (
                ComplexActivityInvariantStatus.SATISFIED,
                "all required feature values are observed",
            )

        match = _COMPARISON.fullmatch(invariant.expression)
        if match is None:
            return (
                ComplexActivityInvariantStatus.NOT_EVALUABLE,
                "invariant expression is outside the bounded declarative language",
            )
        feature_id = match.group("feature")
        if feature_id not in values or feature_id not in invariant.feature_ids:
            return ComplexActivityInvariantStatus.NOT_EVALUABLE, "invariant feature is not bound"
        value = values[feature_id]
        if value.state is not ComplexActivityMissingness.OBSERVED or value.scalar_value is None:
            return (
                ComplexActivityInvariantStatus.NOT_EVALUABLE,
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
                ComplexActivityInvariantStatus.SATISFIED,
                f"{feature_id} satisfies {operator} {bound:g}",
            )
        return (
            ComplexActivityInvariantStatus.VIOLATED,
            f"{feature_id} does not satisfy {operator} {bound:g}",
        )


__all__ = ["M0901FormalStateKernel"]
