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
from glio_proteogen.modules.c27_complex_activity.m27_07_change_control.engine import (
    _is_regression_artifact,
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


@pytest.mark.parametrize(
    ("artifact_id", "expected_value"),
    [
        ("m2707.source.regression", 1),
        ("m2707.source-regression-a", 1),
        ("m2707.source.non-regression", 0),
        ("m2707.source.regressionary", 0),
    ],
)
def test_regression_marker_requires_a_standalone_token(
    artifact_id: str, expected_value: int
) -> None:
    assert _is_regression_artifact(artifact_id) is bool(expected_value)


def test_non_regression_artifact_does_not_abstain() -> None:
    request = build_request()
    source = request.source_artifacts[0].model_copy(
        update={"artifact_id": "m2707.source.non-regression"}
    )
    result = M2707ChangeControlEngine().evaluate(
        request.model_copy(update={"source_artifacts": (source, request.source_artifacts[1])})
    )
    assert result.status is ChangeControlStatus.APPROVED


def test_result_finding_and_evidence_identity_is_closed() -> None:
    result = M2707ChangeControlEngine().evaluate(build_request(challenger_regression=True))
    assert result.findings
    duplicate_findings = result.model_copy(
        update={"findings": (result.findings[0], result.findings[0])}
    )
    with pytest.raises(ValueError, match="change finding ids must be unique"):
        type(result).model_validate(duplicate_findings.model_dump(mode="python"), strict=True)

    duplicate_evidence = result.model_copy(
        update={"evidence": (result.evidence[0], result.evidence[0])}
    )
    with pytest.raises(ValueError, match="change result evidence must be unique"):
        type(result).model_validate(duplicate_evidence.model_dump(mode="python"), strict=True)

    forged_id = result.model_copy(update={"result_id": "result.m2707.forged"})
    with pytest.raises(ValueError, match="result id must be derived"):
        type(result).model_validate(forged_id.model_dump(mode="python"), strict=True)


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
    assert service.replay(result) == result
    assert M2707Plugin().verify(result, altered) is False


def test_service_json_roundtrip() -> None:
    request = build_request()
    result = M2707Service().execute_json(request.model_dump_json())
    assert result.status is ChangeControlStatus.APPROVED
