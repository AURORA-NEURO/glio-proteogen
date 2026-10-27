"""Closed private scalar diagnostics for a request-bound simplex endpoint.

These per-fit values are not an aggregate privacy guarantee. No request vectors
or content-derived request identifiers are retained, and no admission is granted.
"""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Annotated, Final, Literal, Self

from pydantic import Field, field_validator, model_validator

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.gbmap_deconvolution.simplex import SimplexSolverConfiguration
from glio_proteogen.research.gbmap_mixture_benchmark import (
    MixturePointPolicy,  # noqa: TC001 - Pydantic runtime field.
)

AUDIT_VERSION: Final = "gbmap-simplex-endpoint-audit/1.0.0"
ENDPOINT_TOLERANCE: Final = 2e-12
DIAGNOSTIC_TOLERANCE: Final = 1e-10
SOLVER_CONFIGURATION_DIGEST: Final = sha256_digest(asdict(SimplexSolverConfiguration()))
Count = Annotated[int, Field(ge=0)]
Nonnegative = Annotated[float, Field(ge=0.0)]
ComputationStatus = Literal["available", "numerical_failure"]


class SimplexAuditError(ValueError):
    """Sanitized invalid domain or type at the private audit boundary."""


class SimplexEndpointAudit(FrozenModel):
    """Endpoint equations and unchanged legacy gates, without an acceptance flag.

    A code binding does not authenticate caller request provenance. Scalar trace
    consistency does not authenticate intermediate iterates. Frank-Wolfe gaps
    are float64 diagnostics, not rigorously rounded objective-gap certificates.
    """

    audit_version: Literal["gbmap-simplex-endpoint-audit/1.0.0"] = AUDIT_VERSION
    policy: MixturePointPolicy
    method_digest: Sha256Digest
    solver_configuration_digest: Sha256Digest
    feature_count: Annotated[int, Field(ge=2)]
    known_label_count: Annotated[int, Field(ge=1)]
    count_depth: Annotated[int, Field(ge=1, le=9223372036854775807)]
    iterations: Count
    reported_converged: bool
    reported_initial_objective: Nonnegative
    reported_objective: Nonnegative
    reported_unknown_mass: Nonnegative
    reported_kkt_residual: Nonnegative
    reported_signature_condition_number: Nonnegative
    legacy_trace_consistent: bool
    legacy_benchmark_status: Literal[
        "signature_conditioning_rejected", "solver_trace_invalid", "solver_not_converged", "scored"
    ]

    weight_simplex_sum: Nonnegative
    weight_simplex_absolute_error: Nonnegative
    fitted_probability_simplex_absolute_error: Nonnegative
    reconstructed_probability_simplex_absolute_error: Nonnegative
    fitted_probability_max_absolute_error: Nonnegative
    reconstructed_probabilities_match: bool
    recomputed_unknown_mass: Nonnegative
    unknown_mass_absolute_error: Nonnegative
    unknown_mass_matches: bool

    objective_status: ComputationStatus
    recomputed_nll: float | None
    recomputed_mass_penalty: float | None
    recomputed_shape_divergence: float | None
    recomputed_shape_penalty: float | None
    recomputed_objective: float | None
    objective_absolute_error: Nonnegative | None
    objective_matches: bool | None
    initial_objective_status: ComputationStatus
    recomputed_initial_objective: float | None
    initial_objective_absolute_error: Nonnegative | None
    initial_objective_matches: bool | None

    gradient_status: Literal["available", "boundary_unknown_zero", "numerical_failure"]
    recomputed_kkt_residual: Nonnegative | None
    kkt_absolute_error: Nonnegative | None
    kkt_matches: bool | None
    default_stationary: bool | None
    raw_frank_wolfe_gap: float | None
    stable_frank_wolfe_gap: Nonnegative | None
    frank_wolfe_gap_difference: float | None

    conditioning_status: ComputationStatus
    recomputed_signature_condition_number: Nonnegative | None
    smallest_signature_contrast: Nonnegative | None
    default_conditioning_passed: bool
    condition_number_absolute_error: Nonnegative | None
    condition_number_matches: bool

    initial_endpoint_max_absolute_error: Nonnegative
    endpoint_matches_initial: bool
    zero_step_endpoint_matches_initial: bool | None
    zero_step_stationary: bool | None

    admission_changed: Literal[False] = False
    source_provenance_authenticated: Literal[False] = False
    trajectory_replayed: Literal[False] = False
    production_artifact_permitted: Literal[False] = False
    numerical_interval_certified: Literal[False] = False

    @field_validator(
        "admission_changed",
        "source_provenance_authenticated",
        "trajectory_replayed",
        "production_artifact_permitted",
        "numerical_interval_certified",
        mode="before",
    )
    @classmethod
    def exact_false(cls, value: object) -> object:
        if value is not False:
            raise ValueError("endpoint audit cannot grant authority")
        return value

    @model_validator(mode="after")
    def closed_scalar_relations(self) -> Self:  # noqa: PLR0915 - closed scalar feasibility checks.
        config = SimplexSolverConfiguration()
        if self.solver_configuration_digest != SOLVER_CONFIGURATION_DIGEST:
            raise ValueError("endpoint audit requires the unchanged default solver configuration")
        if self.iterations == 0 and self.legacy_trace_consistent:
            raise ValueError("the original trace verifier rejects every empty trace")
        if (
            self.weight_simplex_absolute_error != abs(self.weight_simplex_sum - 1.0)
            or self.reconstructed_probabilities_match
            != (self.fitted_probability_max_absolute_error <= ENDPOINT_TOLERANCE)
            or self.unknown_mass_absolute_error
            != abs(self.reported_unknown_mass - self.recomputed_unknown_mass)
            or self.unknown_mass_matches != (self.unknown_mass_absolute_error <= ENDPOINT_TOLERANCE)
            or self.endpoint_matches_initial
            != (self.initial_endpoint_max_absolute_error <= ENDPOINT_TOLERANCE)
            or self.zero_step_endpoint_matches_initial
            != (self.endpoint_matches_initial if self.iterations == 0 else None)
            or self.zero_step_stationary
            != (self.default_stationary if self.iterations == 0 else None)
        ):
            raise ValueError("endpoint scalar comparisons are inconsistent")
        objective = (
            self.recomputed_nll,
            self.recomputed_mass_penalty,
            self.recomputed_shape_divergence,
            self.recomputed_shape_penalty,
            self.recomputed_objective,
            self.objective_absolute_error,
            self.objective_matches,
        )
        if any(
            (value is not None) != (self.objective_status == "available") for value in objective
        ):
            raise ValueError("objective availability must be explicit")
        if self.objective_status == "available":
            if (
                self.recomputed_nll is None
                or self.recomputed_mass_penalty is None
                or self.recomputed_shape_divergence is None
                or self.recomputed_shape_penalty is None
                or self.recomputed_objective is None
                or self.objective_absolute_error is None
            ):
                raise ValueError("available objective requires finite terms")
            expected = (
                self.recomputed_nll + self.recomputed_mass_penalty + self.recomputed_shape_penalty
            )
            if (
                self.recomputed_mass_penalty
                != self.policy.lambda_mass * self.recomputed_unknown_mass
                or self.recomputed_shape_penalty
                != self.policy.lambda_shape * self.recomputed_shape_divergence
                or self.recomputed_objective != expected
                or self.objective_absolute_error
                != abs(self.reported_objective - self.recomputed_objective)
                or self.objective_matches != (self.objective_absolute_error <= DIAGNOSTIC_TOLERANCE)
            ):
                raise ValueError("objective terms do not reconstruct the reported comparison")
        initial = (
            self.recomputed_initial_objective,
            self.initial_objective_absolute_error,
            self.initial_objective_matches,
        )
        if any(
            (value is not None) != (self.initial_objective_status == "available")
            for value in initial
        ):
            raise ValueError("initial objective availability must be explicit")
        if self.recomputed_initial_objective is not None and (
            self.initial_objective_absolute_error
            != abs(self.reported_initial_objective - self.recomputed_initial_objective)
            or self.initial_objective_matches
            != (
                self.initial_objective_absolute_error is not None
                and self.initial_objective_absolute_error <= DIAGNOSTIC_TOLERANCE
            )
        ):
            raise ValueError("initial objective comparison is inconsistent")
        gradient = (
            self.recomputed_kkt_residual,
            self.kkt_absolute_error,
            self.kkt_matches,
            self.default_stationary,
            self.raw_frank_wolfe_gap,
            self.stable_frank_wolfe_gap,
            self.frank_wolfe_gap_difference,
        )
        if any((value is not None) != (self.gradient_status == "available") for value in gradient):
            raise ValueError("boundary or failed gradient diagnostics must remain unavailable")
        if self.recomputed_kkt_residual is not None:
            if (
                self.raw_frank_wolfe_gap is None
                or self.stable_frank_wolfe_gap is None
                or self.kkt_absolute_error is None
            ):
                raise ValueError("available gradient requires finite diagnostics")
            if (
                self.kkt_absolute_error
                != abs(self.reported_kkt_residual - self.recomputed_kkt_residual)
                or self.kkt_matches != (self.kkt_absolute_error <= DIAGNOSTIC_TOLERANCE)
                or self.default_stationary != (self.recomputed_kkt_residual <= config.kkt_tolerance)
                or self.frank_wolfe_gap_difference
                != self.raw_frank_wolfe_gap - self.stable_frank_wolfe_gap
            ):
                raise ValueError("gradient diagnostics are inconsistent")
        if self.conditioning_status == "numerical_failure":
            if (
                any(
                    value is not None
                    for value in (
                        self.recomputed_signature_condition_number,
                        self.smallest_signature_contrast,
                        self.condition_number_absolute_error,
                    )
                )
                or self.default_conditioning_passed
                or self.condition_number_matches
            ):
                raise ValueError("failed conditioning must not fabricate numeric evidence")
        else:
            condition = self.recomputed_signature_condition_number
            if self.known_label_count == 1:
                if condition != 1.0 or self.smallest_signature_contrast is not None:
                    raise ValueError("a single signature has unit condition and no contrast axis")
                passed = True
            else:
                if self.smallest_signature_contrast is None:
                    raise ValueError("multiple signatures require a contrast diagnostic")
                if condition is not None and (
                    condition < 1.0 or self.smallest_signature_contrast == 0.0
                ):
                    raise ValueError("finite signature conditioning requires a positive contrast")
                passed = (
                    condition is not None
                    and condition <= config.signature_condition_limit
                    and self.smallest_signature_contrast >= config.minimum_signature_contrast
                )
            if self.default_conditioning_passed != passed:
                raise ValueError("conditioning gate must preserve the original default constants")
            expected_error = (
                abs(self.reported_signature_condition_number - condition)
                if condition is not None
                else None
            )
            if (
                self.condition_number_absolute_error != expected_error
                or self.condition_number_matches
                != (expected_error is not None and expected_error <= DIAGNOSTIC_TOLERANCE)
            ):
                raise ValueError("condition comparison is inconsistent")
        expected_status = (
            "signature_conditioning_rejected"
            if not self.default_conditioning_passed
            else "solver_trace_invalid"
            if not self.legacy_trace_consistent
            else "solver_not_converged"
            if (not self.reported_converged or self.reported_kkt_residual > config.kkt_tolerance)
            else "scored"
        )
        if self.legacy_benchmark_status != expected_status:
            raise ValueError("the diagnostic cannot change the original benchmark gate")
        # All finite values are already enforced by FrozenModel. This bound is
        # about a simplex sum, not a numerical interval or scientific guarantee.
        if not math.isclose(self.weight_simplex_sum, 1.0, rel_tol=0.0, abs_tol=ENDPOINT_TOLERANCE):
            raise ValueError("audited endpoint must have the original structural simplex domain")
        return self
