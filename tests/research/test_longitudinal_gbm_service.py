from __future__ import annotations

from glio_proteogen.research.longitudinal_gbm.contracts import (
    ReplayVerificationRequest,
    UnverifiedLongitudinalGbmResult,
)
from glio_proteogen.research.longitudinal_gbm.demo import synthetic_demo_request
from glio_proteogen.research.longitudinal_gbm.service import (
    LongitudinalGbmService,
    analyze_longitudinal_gbm,
    verify_longitudinal_gbm_replay,
    verify_replay,
)


def test_service_exact_replay_and_aliases() -> None:
    request = synthetic_demo_request()
    service = LongitudinalGbmService()
    result = service.analyze(request)
    direct = analyze_longitudinal_gbm(request)
    assert result == direct
    verification = ReplayVerificationRequest(request=request, result=result)
    checked = service.verify(verification)
    assert checked == verify_longitudinal_gbm_replay(verification)
    assert checked == verify_replay(verification)
    assert checked.verified
    assert checked.request_digest_match
    assert checked.profile_digest_match
    assert checked.result_digest_match
    assert checked.transition_semantic_match
    assert checked.pelt_semantic_match
    assert checked.semantic_match
    assert "exactly matches" in checked.message


def test_replay_rejects_forged_topology_and_receipt() -> None:
    request = synthetic_demo_request()
    result = analyze_longitudinal_gbm(request)
    document = result.model_dump(mode="python")
    document["series_id"] = "forged.series"
    forged = UnverifiedLongitudinalGbmResult.model_validate(document)
    checked = verify_replay(ReplayVerificationRequest(request=request, result=forged))
    assert not checked.verified
    assert checked.request_digest_match
    assert checked.profile_digest_match
    assert not checked.result_digest_match
    assert checked.transition_semantic_match
    assert checked.pelt_semantic_match
    assert not checked.semantic_match
    assert "differs" in checked.message
