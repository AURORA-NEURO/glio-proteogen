"""M27-07 runtime and replay tests."""

import pytest
from evals.m27_07.fixture import build_request

from glio_proteogen.contracts.m27_07 import ChangeControlStatus
from glio_proteogen.modules.c27_complex_activity.m27_07_change_control import (
    ChangeControlSubmission,
    M2707ChangeControlEngine,
    M2707Plugin,
    M2707Service,
)


def test_approved_change_binds_package_and_rollback() -> None:
    result = M2707ChangeControlEngine().evaluate(build_request())
    assert result.status is ChangeControlStatus.APPROVED
    assert result.approved_change_package is not None
    assert result.approved_change_package.rollback_point.tested
    assert result.human_review_required is False


def test_regression_abstains_and_requires_review() -> None:
    result = M2707Service().execute(build_request(challenger_regression=True))
    assert result.status is ChangeControlStatus.ABSTAINED
    assert result.safe_failure_report is not None
    assert result.human_review_required


def test_plugin_issued_token_replays_exact_request() -> None:
    plugin = M2707Plugin()
    request = build_request()
    token = plugin.validate(ChangeControlSubmission(request))
    assert plugin.run(token).status is ChangeControlStatus.APPROVED


def test_service_and_plugin_replay_reject_supplied_request_mismatch() -> None:
    request = build_request()
    service = M2707Service()
    result = service.execute(request)
    altered = request.model_copy(update={"request_id": "m2707.request.mismatch"})
    assert service.verify(result, altered) is False
    with pytest.raises(ValueError, match="replay request mismatch"):
        service.replay(result, altered)
    assert M2707Plugin().verify(result, altered) is False


def test_service_json_roundtrip() -> None:
    request = build_request()
    result = M2707Service().execute_json(request.model_dump_json())
    assert result.status is ChangeControlStatus.APPROVED
