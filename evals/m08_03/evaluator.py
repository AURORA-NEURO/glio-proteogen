"""M08-03 baseline safety scenario evaluator."""

from __future__ import annotations

from dataclasses import dataclass

from glio_proteogen.contracts.m08_03 import BaselineFeatureState
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator import (
    M0803BaselineAuthorizationError,
    M0803Service,
)

from .fixtures import request


@dataclass(frozen=True, slots=True)
class M0803Scenario:
    name: str
    expected_status: str
    request: object


@dataclass(frozen=True, slots=True)
class M0803Evaluation:
    scenario: str
    observed_status: str
    passed: bool
    support_status: str


def scenarios() -> tuple[M0803Scenario, ...]:
    return (
        M0803Scenario("observed-baseline", "estimated", request()),
        M0803Scenario(
            "missing-feature-abstain",
            "abstained",
            request(feature_state=BaselineFeatureState.MISSING),
        ),
        M0803Scenario(
            "unsupported-domain-abstain",
            "abstained",
            request(source_name="source.unsupported.ood"),
        ),
        M0803Scenario(
            "withheld-consent",
            "authorization_error",
            request(consent=ConsentState.WITHHELD),
        ),
    )


def evaluate_all() -> tuple[M0803Evaluation, ...]:
    service = M0803Service()
    records: list[M0803Evaluation] = []
    for scenario in scenarios():
        try:
            result = service.execute(scenario.request)
        except M0803BaselineAuthorizationError:
            records.append(
                M0803Evaluation(
                    scenario.name,
                    "authorization_error",
                    scenario.expected_status == "authorization_error",
                    "unsupported",
                )
            )
            continue
        records.append(
            M0803Evaluation(
                scenario.name,
                result.status.value,
                result.status.value == scenario.expected_status,
                result.support_decision.status.value,
            )
        )
    return tuple(records)
