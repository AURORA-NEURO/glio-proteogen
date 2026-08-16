"""Transparent deterministic kernel for the provisional M06-03 estimator."""

from __future__ import annotations

from dataclasses import dataclass

from glio_proteogen.contracts.m06_01 import FormalStateMissingness
from glio_proteogen.contracts.m06_03 import (
    BaselineDiagnostic,
    BaselineDiagnosticStatus,
    BaselineEstimate,
    BaselineEstimateKind,
    EstimateProteinAbundanceBaselineRequest,
)


@dataclass(frozen=True, slots=True)
class BaselineKernelOutput:
    estimates: tuple[BaselineEstimate, ...]
    diagnostics: tuple[BaselineDiagnostic, ...]
    abstention_reason: str | None


class M0603BaselineKernel:
    """Run only caller-declared preprocessing and transparent value reduction."""

    def estimate(self, request: EstimateProteinAbundanceBaselineRequest) -> BaselineKernelOutput:
        definitions = {item.feature_id: item for item in request.state_schema.features}
        estimates: list[BaselineEstimate] = []
        diagnostics: list[BaselineDiagnostic] = []
        for value in request.feature_values:
            definition = definitions[value.feature_id]
            if value.state is not FormalStateMissingness.OBSERVED:
                diagnostics.append(
                    BaselineDiagnostic(
                        diagnostic_id=f"diagnostic.{value.feature_id}",
                        status=BaselineDiagnosticStatus.NOT_EVALUABLE,
                        message="Feature is not observed; baseline estimation abstains.",
                        metric_name="missingness",
                    )
                )
                return BaselineKernelOutput(
                    estimates=(),
                    diagnostics=tuple(diagnostics),
                    abstention_reason="formal-state feature is missing or unsupported",
                )
            if definition.value_kind.value == "scalar":
                estimates.append(
                    BaselineEstimate(
                        feature_id=value.feature_id,
                        kind=BaselineEstimateKind.SCALAR,
                        unit=value.unit,
                        estimate_value=value.scalar_value,
                    )
                )
            elif definition.value_kind.value == "interval":
                if value.interval_lower is None or value.interval_upper is None:
                    return BaselineKernelOutput(
                        estimates=(),
                        diagnostics=tuple(diagnostics),
                        abstention_reason="interval feature lacks ordered bounds",
                    )
                estimates.append(
                    BaselineEstimate(
                        feature_id=value.feature_id,
                        kind=BaselineEstimateKind.INTERVAL,
                        unit=value.unit,
                        estimate_value=(value.interval_lower + value.interval_upper) / 2,
                        lower_bound=value.interval_lower,
                        upper_bound=value.interval_upper,
                    )
                )
            else:
                estimates.append(
                    BaselineEstimate(
                        feature_id=value.feature_id,
                        kind=BaselineEstimateKind.CATEGORICAL,
                        unit=value.unit,
                        category=value.category,
                    )
                )
            diagnostics.append(
                BaselineDiagnostic(
                    diagnostic_id=f"diagnostic.{value.feature_id}",
                    status=BaselineDiagnosticStatus.PASS,
                    message=(
                        "Transparent baseline reduction completed with "
                        f"{request.configuration.estimator_family.value} family."
                    ),
                    metric_name="feature_observed",
                    metric_value=1.0,
                )
            )
        return BaselineKernelOutput(
            estimates=tuple(estimates),
            diagnostics=tuple(diagnostics),
            abstention_reason=None,
        )


__all__ = ["BaselineKernelOutput", "M0603BaselineKernel"]
