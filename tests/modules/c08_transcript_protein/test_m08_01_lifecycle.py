"""Deep lifecycle coverage for M08-01 runtime, replay, and sealed plugin."""

from __future__ import annotations

import pytest
from evals.m08_01.evaluator import evaluate_all
from evals.m08_01.fixtures import request

from glio_proteogen.contracts.m08_01 import (
    TranscriptProteinInvariantSeverity,
    TranscriptProteinMissingness,
    TranscriptProteinValidationStatus,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c08_transcript_protein.m08_01_formal_state import (
    M0801FormalStateAuthorizationError,
    M0801Plugin,
    M0801Service,
)

EXPECTED_SCENARIOS = 5


def test_satisfied_and_violated_states_are_distinct() -> None:
    service = M0801Service()
    assert service.execute(request()).status is TranscriptProteinValidationStatus.VALID
    assert service.execute(request(scalar=0.5)).status is TranscriptProteinValidationStatus.INVALID


def test_missingness_abstains_without_negative_conversion() -> None:
    result = M0801Service().execute(request(missingness=TranscriptProteinMissingness.MISSING))
    assert result.status is TranscriptProteinValidationStatus.ABSTAINED
    assert result.support_decision.status.value == "unsupported"


def test_unknown_expression_abstains() -> None:
    result = M0801Service().execute(request(expression="caller-owned expression"))
    assert result.status is TranscriptProteinValidationStatus.ABSTAINED
    assert result.invariant_results[0].status.value == "not_evaluable"


def test_warning_violation_is_not_hard_invalid() -> None:
    result = M0801Service().execute(
        request(scalar=0.5, severity=TranscriptProteinInvariantSeverity.WARNING)
    )
    assert result.status is TranscriptProteinValidationStatus.VALID


def test_authorization_fails_before_execution() -> None:
    candidate = request().model_dump(mode="json")
    candidate["context"]["references"]["consent"]["state"] = "withheld"
    with pytest.raises(M0801FormalStateAuthorizationError):
        M0801Service().execute(candidate)


def test_replay_and_tamper_verification() -> None:
    service = M0801Service()
    candidate = request()
    result = service.execute(candidate)
    assert service.replay(candidate, result).result_digest == result.result_digest
    tampered = result.model_dump(mode="json")
    tampered["status"] = "invalid"
    with pytest.raises(ValueError, match="digest"):
        service.verify(tampered)


def test_plugin_parse_once_and_json_parity() -> None:
    service = M0801Service()
    plugin = M0801Plugin(service)
    typed = plugin.run(plugin.validate(request()))
    encoded = canonical_json_bytes(request().model_dump(mode="json"))
    decoded = plugin.run(plugin.validate(encoded))
    assert decoded.model_dump(mode="json") == typed.model_dump(mode="json")
    assert typed.request_digest == canonical_request_digest(typed.request)


def test_plugin_rejects_forged_token() -> None:
    plugin = M0801Plugin(M0801Service())
    token = plugin.validate(request())
    assert plugin.run(token).result_digest.startswith("sha256:")
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]


def test_evaluator_matrix_passes() -> None:
    records = evaluate_all()
    assert len(records) == EXPECTED_SCENARIOS
    assert all(record.passed for record in records)
