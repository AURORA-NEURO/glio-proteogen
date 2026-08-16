"""Hostile-input and safe-abstention coverage for M14-01."""

from __future__ import annotations

import json

import pytest
from evals.m14_01.run import build_scenario_request
from fastapi.testclient import TestClient

from glio_proteogen.adapters.m1401 import app
from glio_proteogen.contracts.m14_01 import HypothesisFindingCode, HypothesisStatus
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution import (
    m14_01_biological_hypothesis_registry as module,
)

_UNPROCESSABLE = 422


def test_preflight_rejects_opaque_candidate_before_hypothesis_traversal() -> None:
    candidate = {
        "context": {"references": {"consent": {"state": "withheld"}}},
        "hypotheses": _ExplodingHypotheses(),
    }
    with pytest.raises(module.M1401HypothesisAuthorizationError):
        module.preflight_hypothesis_authorization(candidate)


class _ExplodingHypotheses:
    def __iter__(self) -> object:
        raise AssertionError


def test_withheld_consent_abstains_before_runtime_evaluation() -> None:
    request = build_scenario_request()
    references = request.context.references
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": references.model_copy(
                        update={
                            "consent": references.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(module.M1401HypothesisAuthorizationError):
        module.M1401HypothesisEngine().register(denied)


def test_unknown_statement_never_becomes_negative_finding() -> None:
    result = module.M1401HypothesisEngine().register(build_scenario_request("unknown_hypothesis"))
    assert result.status is HypothesisStatus.ABSTAINED
    assert all(
        item.code is not HypothesisFindingCode.PROHIBITED_INTERPRETATION for item in result.findings
    )
    assert result.registry is None
    assert result.human_review_required


def test_duplicate_json_keys_are_rejected_without_echoing_payload() -> None:
    request = canonical_json_bytes(build_scenario_request())
    duplicate = request[:-1] + b',"request_id":"attacker"}'
    response = TestClient(app).post(
        "/v1/modules/M14-01/hypotheses",
        content=duplicate,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == _UNPROCESSABLE
    assert "attacker" not in json.dumps(response.json())


def test_nested_registry_tamper_is_rejected_by_replay() -> None:
    engine = module.M1401HypothesisEngine()
    result = engine.register(build_scenario_request())
    assert result.registry is not None
    tampered = result.model_copy(
        update={"registry": result.registry.model_copy(update={"reviewed_by": "attacker"})}
    )
    with pytest.raises(module.M1401ReplayVerificationError):
        engine.verify(tampered)
