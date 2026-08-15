"""Scenario evaluator for the M08-01 safety and replay boundary."""

from __future__ import annotations

from dataclasses import dataclass

from glio_proteogen.contracts.m08_01 import TranscriptProteinMissingness
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c08_transcript_protein.m08_01_formal_state import (
    M0801FormalStateAuthorizationError,
    M0801Service,
)

from .fixtures import request


@dataclass(frozen=True, slots=True)
class M0801Scenario:
    name: str
    expected_status: str
    request: object


@dataclass(frozen=True, slots=True)
class M0801Evaluation:
    scenario: str
    observed_status: str
    passed: bool
    support_status: str


def scenarios() -> tuple[M0801Scenario, ...]:
    return (
        M0801Scenario("observed-satisfied", "valid", request()),
        M0801Scenario("observed-violated", "invalid", request(scalar=0.5)),
        M0801Scenario(
            "missing-abstain",
            "abstained",
            request(missingness=TranscriptProteinMissingness.MISSING),
        ),
        M0801Scenario(
            "unknown-expression-abstain",
            "abstained",
            request(expression="caller-defined"),
        ),
        M0801Scenario(
            "withheld-consent",
            "authorization_error",
            request(consent=ConsentState.WITHHELD),
        ),
    )


def evaluate_all() -> tuple[M0801Evaluation, ...]:
    service = M0801Service()
    records: list[M0801Evaluation] = []
    for scenario in scenarios():
        try:
            result = service.execute(scenario.request)
        except M0801FormalStateAuthorizationError:
            records.append(
                M0801Evaluation(
                    scenario.name,
                    "authorization_error",
                    scenario.expected_status == "authorization_error",
                    "unsupported",
                )
            )
            continue
        records.append(
            M0801Evaluation(
                scenario.name,
                result.status.value,
                result.status.value == scenario.expected_status,
                result.support_decision.status.value,
            )
        )
    return tuple(records)
