"""Deep adversarial closure for M22-05 runtime and interface boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from evals.m22_05.fixture import denied_request, unsupported_request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m22_05 import (
    CoverageStatus,
    CoverageSummary,
    EvaluationStatus,
    ProteinRnaDiscordanceSubgroupEvaluationResult,
    canonical_request_digest,
    normalized_request,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import SupportDecision, SupportStatus
from glio_proteogen.modules.c21_reference_material.m22_05_subgroup_equity_evaluator import (
    EquityEvaluationSubmission,
    M2205Plugin,
    M2205Service,
    cli_app,
    create_app,
)
from glio_proteogen.modules.c21_reference_material.m22_05_subgroup_equity_evaluator import (
    cli as cli_module,
)
from tests.contract.test_m22_05_hardening import (
    _completed_result,
    _coverage,
    _request,
    _request_update,
    _result_update,
)

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_UNPROCESSABLE = 422


def _self_rehashed(
    result: ProteinRnaDiscordanceSubgroupEvaluationResult,
    updates: dict[str, Any],
) -> ProteinRnaDiscordanceSubgroupEvaluationResult:
    forged = result.model_copy(update=updates)
    return type(forged).model_construct(
        **{**forged.__dict__, "result_digest": result_payload_digest(forged)}
    )


def test_canonical_dict_projection_and_identity_are_stable() -> None:
    request = _request()
    document = normalized_request(request)
    assert canonical_request_digest(document) == canonical_request_digest(request)
    assert result_identifier(document) == result_identifier(request)


def test_bounds_and_coverage_arithmetic_reject_adversarial_values() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="within bounds"):
        _request_update(
            request,
            performance=(request.performance[0].model_copy(update={"value": 0.9}),),
        )
    with pytest.raises(ValidationError, match="supported examples"):
        CoverageSummary.model_validate(
            _coverage().model_dump(mode="python") | {"supported_examples": 11}, strict=True
        )


def test_source_artifact_with_reused_id_but_changed_digest_is_rejected() -> None:
    request = _request()
    upstream = request.upstream_result
    forged_source = upstream.model_copy(update={"digest": sha256_digest("forged-upstream")})
    with pytest.raises(ValidationError, match="exactly bind the upstream result"):
        _request_update(
            request,
            source_artifacts=(forged_source, request.source_artifacts[1]),
        )


def test_provenance_covers_nested_subgroup_evidence() -> None:
    request = _request()
    result = M2205Service().evaluate(request)
    nested_evidence = (
        *(item for performance in request.performance for item in performance.evidence),
        *(item for calibration in request.calibration for item in calibration.evidence),
        *(item for coverage in request.coverage for item in coverage.evidence),
        *request.configuration.evidence,
    )

    assert {item.reference.digest for item in nested_evidence} <= set(
        result.provenance.input_digests
    )


def test_engine_abstains_for_unsupported_performance_coverage() -> None:
    performance = (
        _request().performance[0].model_copy(update={"coverage_status": CoverageStatus.UNSUPPORTED})
    )
    result = M2205Service().evaluate(_request().model_copy(update={"performance": (performance,)}))
    assert result.status is EvaluationStatus.ABSTAINED
    assert result.report is None


def test_result_digest_request_and_status_closures_reject_tampering() -> None:
    request = _request()
    result = _completed_result(request)
    with pytest.raises(ValidationError, match="request digest"):
        _result_update(result, request_digest=sha256_digest("wrong"))
    with pytest.raises(ValidationError, match="evaluated result"):
        _result_update(result, report=None)
    with pytest.raises(ValidationError, match="abstained result"):
        _result_update(
            result,
            status=EvaluationStatus.ABSTAINED,
            report=None,
            abstention_reason=None,
            support_decision=SupportDecision(
                status=SupportStatus.UNSUPPORTED,
                reason_code="unsupported",
                rationale="unsupported",
            ),
        )


@pytest.mark.parametrize(
    "region",
    [
        "report",
        "findings",
        "support",
        "provenance",
        "evidence",
        "limitations",
        "human_review_required",
        "abstention_reason",
    ],
)
def test_self_rehashed_output_mutations_are_rejected_by_replay(region: str) -> None:
    result = M2205Service().evaluate(
        unsupported_request() if region in {"findings", "abstention_reason"} else _request()
    )
    updates: dict[str, Any]
    if region == "report":
        assert result.report is not None
        updates = {"report": result.report.model_copy(update={"report_id": "forged-report"})}
    elif region == "findings":
        assert result.findings
        finding = result.findings[0].model_copy(update={"message": "forged finding"})
        updates = {"findings": (finding, *result.findings[1:])}
    elif region == "support":
        updates = {
            "support_decision": result.support_decision.model_copy(
                update={"rationale": "forged support rationale"}
            )
        }
    elif region == "provenance":
        updates = {"provenance": result.provenance.model_copy(update={"actor_id": "forged-actor"})}
    elif region == "evidence":
        evidence = result.evidence[0].model_copy(update={"claim": "forged evidence claim"})
        updates = {"evidence": (evidence, *result.evidence[1:])}
    elif region == "limitations":
        limitation = result.limitations[0].model_copy(update={"statement": "forged limitation"})
        updates = {"limitations": (limitation, *result.limitations[1:])}
    elif region == "human_review_required":
        updates = {"human_review_required": not result.human_review_required}
    else:
        assert result.abstention_reason is not None
        updates = {"abstention_reason": "forged abstention reason"}
    forged = _self_rehashed(result, updates)
    with pytest.raises(ValueError, match="replay verification failed"):
        M2205Service().replay(forged)


def test_self_rehashed_request_mutation_is_rejected_by_replay() -> None:
    result = M2205Service().evaluate(_request())
    request = result.request.model_copy(
        update={
            "configuration": result.request.configuration.model_copy(update={"safety_floor": 0.61})
        }
    )
    forged = result.model_copy(
        update={"request": request, "request_digest": canonical_request_digest(request)}
    )
    forged = type(forged).model_construct(
        **{
            **forged.__dict__,
            "request": request,
            "request_digest": canonical_request_digest(request),
            "result_digest": result_payload_digest(forged),
        }
    )
    with pytest.raises(ValueError, match="identifier"):
        M2205Service().replay(forged)


def test_fastapi_non_object_replay_is_sanitized() -> None:
    response = TestClient(create_app(M2205Service())).post(
        "/v1/modules/M22-05/verify", content=b"[]"
    )
    assert response.status_code == _HTTP_UNPROCESSABLE


def test_plugin_typed_submission_and_cli_stdout_paths(tmp_path: Path) -> None:
    request = _request()
    plugin = M2205Plugin(M2205Service())
    validated = plugin.validate(EquityEvaluationSubmission(request=request))
    assert plugin.run(validated).result_digest.startswith("sha256:")
    runner = CliRunner()
    assert runner.invoke(cli_app, ["export-schema", "request"]).exit_code == 0
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["validate", str(bad)]).exit_code != 0


def test_cli_abstention_denial_and_replay_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    denied = tmp_path / "denied.json"
    denied.write_bytes(denied_request().model_dump_json().encode())
    assert runner.invoke(cli_app, ["validate", str(denied)]).exit_code != 0
    assert runner.invoke(cli_app, ["evaluate", str(denied)]).exit_code != 0
    unsupported = tmp_path / "unsupported.json"
    unsupported.write_bytes(unsupported_request().model_dump_json().encode())
    assert runner.invoke(cli_app, ["evaluate", str(unsupported)]).exit_code != 0
    valid = tmp_path / "valid.json"
    valid.write_bytes(_completed_result(_request()).model_dump_json().encode())

    class Mismatch:
        result_digest = "sha256:" + "0" * 64

    class Service:
        def replay(self, _result: object) -> Mismatch:
            return Mismatch()

    monkeypatch.setattr(cli_module, "_SERVICE", Service())
    assert runner.invoke(cli_app, ["verify", str(valid)]).exit_code != 0


__all__ = []
