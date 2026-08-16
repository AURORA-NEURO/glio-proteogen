"""Deep branch and wrapper coverage for M18-01 runtime."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m18_01 import (
    CompatibilityStatus,
    ResolverFindingCode,
    UpstreamCandidate,
)
from glio_proteogen.kernel.models import ConsentState, SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m18_01_upstream_contract_resolver as m1801,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m18_01_upstream_contract_resolver.engine import (  # noqa: E501
    _decision_for,
)
from tests.modules.c17_metabolomic_lipidomic_integration.test_m18_01_engine import (
    _candidate,
    _request,
)


def _unsafe_candidate(**updates: object) -> UpstreamCandidate:
    candidate = _candidate()
    return candidate.model_copy(update=updates)


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({"consent_state": ConsentState.UNKNOWN}, ResolverFindingCode.CONSENT_NOT_GRANTED),
        ({"support_status": SupportStatus.LIMITED}, ResolverFindingCode.SUPPORT_NOT_AVAILABLE),
        ({"provenance_artifact": None}, ResolverFindingCode.PROVENANCE_MISSING),
    ],
)
def test_decision_for_exposes_control_specific_rejections(
    updates: dict[str, object],
    expected: ResolverFindingCode,
) -> None:
    request = _request()
    decision, bucket = _decision_for(_unsafe_candidate(**updates), request)
    assert decision.reason_code is expected
    assert decision.status is CompatibilityStatus.INCOMPATIBLE
    assert bucket == "rejected"


def test_decision_for_exposes_intended_use_rejection_after_rule_match() -> None:
    request = _request()
    candidate = _unsafe_candidate(intended_use="restricted export")
    rule = request.configuration.rules[0].model_copy(
        update={"required_intended_use": "restricted export"}
    )
    configured = request.configuration.model_copy(update={"rules": (rule,)})
    decision, bucket = _decision_for(
        candidate, request.model_copy(update={"configuration": configured})
    )
    assert decision.reason_code is ResolverFindingCode.INTENDED_USE_MISMATCH
    assert bucket == "rejected"


def test_public_wrapper_and_plugin_service_validate_and_replay() -> None:
    request = _request()
    result = m1801.resolve_biomarker_panel_upstream_contracts(request)
    service = m1801.M1801Service()
    plugin = m1801.M1801Plugin()
    assert service.validate_request(request) == request
    assert plugin.validate_request(request) == request
    assert plugin.replay(result) == result


def test_engine_replay_rejects_result_identifier_tamper() -> None:
    result = m1801.M1801Engine().resolve(_request())
    with pytest.raises(m1801.M1801ReplayError, match="identifier"):
        m1801.M1801Engine().replay(result.model_copy(update={"result_id": "result.tampered"}))
