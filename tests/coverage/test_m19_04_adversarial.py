"""Deep branch and adversarial coverage for the M19-04 policy boundary."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m19_04 import IntendedUseKind, PolicyDecisionStatus
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_04_intended_use_adapter import (
    M1904AuthorizationError,
    M1904Engine,
    M1904ReplayError,
)
from tests.runtime.test_m19_04_intended_use import _supported_request


@pytest.mark.parametrize(
    ("control", "state"),
    [
        ("approved_configuration", "rejected"),
        ("identity_lineage", "unresolved"),
        ("provenance", "rejected"),
        ("consent", "revoked"),
        ("quality", "rejected"),
        ("support", "rejected"),
        ("intended_use", "rejected"),
    ],
)
def test_each_upstream_control_is_fail_closed(control: str, state: str) -> None:
    request = _supported_request()
    candidate = request.model_dump(mode="python")
    references = candidate["context"]["references"]
    references[control]["state"] = state

    with pytest.raises(M1904AuthorizationError, match=f"control {control}"):
        M1904Engine().validate_request(candidate)


@pytest.mark.parametrize(
    ("intended_use", "evidence_tier", "expected_status", "expected_review"),
    [
        (IntendedUseKind.INTERNAL_VALIDATION, 2, PolicyDecisionStatus.ALLOWED, 0),
        (IntendedUseKind.INTERNAL_VALIDATION, 1, PolicyDecisionStatus.BLOCKED, 1),
        (IntendedUseKind.RELEASE_REVIEW, 4, PolicyDecisionStatus.REVIEW_REQUIRED, 1),
    ],
)
def test_intended_use_tiers_and_release_review_are_explicit(
    intended_use: IntendedUseKind,
    evidence_tier: int,
    expected_status: PolicyDecisionStatus,
    expected_review: int,
) -> None:
    request = _supported_request()
    registration = request.registration.model_copy(
        update={
            "intended_use": intended_use,
            "evidence_tier": evidence_tier,
            "audience": intended_use.value,
        }
    )
    result = M1904Engine().adapt(request.model_copy(update={"registration": registration}))

    assert result.policy_decision.status is expected_status
    assert result.human_review_required is bool(expected_review)
    if expected_status is PolicyDecisionStatus.BLOCKED:
        assert result.status.value == "abstained"
        assert result.support_decision.status is SupportStatus.UNSUPPORTED
    else:
        assert result.status.value == "adapted"


def test_case_insensitive_supported_audience_does_not_expand_claims() -> None:
    request = _supported_request()
    registration = request.registration.model_copy(update={"audience": "RESEARCH"})
    result = M1904Engine().adapt(request.model_copy(update={"registration": registration}))

    assert result.policy_decision.status is PolicyDecisionStatus.ALLOWED
    assert result.adapted_object is not None
    assert result.adapted_object.registration.audience == "RESEARCH"


def test_replay_rejects_unvalidated_mapping_and_model_tampering() -> None:
    engine = M1904Engine()
    result = engine.adapt(_supported_request())

    tampered_mapping = result.model_dump(mode="python")
    tampered_mapping["result_id"] = "result.tampered"
    with pytest.raises(M1904ReplayError, match="contract validation"):
        engine.replay(tampered_mapping)  # type: ignore[arg-type]

    with pytest.raises(M1904ReplayError, match="result digest"):
        engine.replay(result.model_copy(update={"human_review_required": True}))
