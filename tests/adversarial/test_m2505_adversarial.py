"""Hostile-input, schema, replay, and safe-abstention closure for M25-05."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from evals.m25_05.fixture import build_request
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m25_05 import (
    CoverageStatus,
    EquityStatus,
    EvaluateProteotypeSubgroupEquityRequest,
    ProteotypeSubgroupEvaluationResult,
    result_payload_digest,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c21_reference_material.m25_05_subgroup_equity_evaluator import (
    M2505AuthorizationError,
    M2505Plugin,
    M2505ReplayError,
    M2505Service,
)
from glio_proteogen.modules.c21_reference_material.m25_05_subgroup_equity_evaluator.cli import app

if TYPE_CHECKING:
    from pathlib import Path


def _request_data() -> dict[str, Any]:
    return build_request().model_dump(mode="python")


def test_unknown_request_field_is_rejected() -> None:
    data = _request_data()
    data["unexpected"] = "hostile"

    with pytest.raises(ValidationError):
        EvaluateProteotypeSubgroupEquityRequest.model_validate(data, strict=True)


def test_duplicate_subgroup_metric_ids_are_rejected() -> None:
    request = build_request()
    data = request.model_dump(mode="python")
    data["performance"] = (request.performance[0], request.performance[0], *request.performance[2:])

    with pytest.raises(ValidationError, match="subgroup request ids"):
        EvaluateProteotypeSubgroupEquityRequest.model_validate(data, strict=True)


def test_duplicate_source_artifacts_are_rejected() -> None:
    request = build_request()
    data = request.model_dump(mode="python")
    data["source_artifacts"] = (request.source_artifacts[0], request.source_artifacts[0])

    with pytest.raises(ValidationError, match="source artifact"):
        EvaluateProteotypeSubgroupEquityRequest.model_validate(data, strict=True)


def test_wrong_upstream_media_type_is_rejected() -> None:
    request = build_request()
    data = request.model_dump(mode="python")
    data["upstream_result"] = request.upstream_result.model_copy(
        update={"media_type": "application/json"}
    )

    with pytest.raises(ValidationError, match="M25-04"):
        EvaluateProteotypeSubgroupEquityRequest.model_validate(data, strict=True)


def test_non_finite_numeric_input_is_rejected() -> None:
    data = _request_data()
    data["performance"][0]["value"] = float("nan")

    with pytest.raises(ValidationError):
        EvaluateProteotypeSubgroupEquityRequest.model_validate(data, strict=True)


def test_context_request_id_mismatch_is_rejected() -> None:
    request = build_request()
    data = request.model_dump(mode="python")
    data["context"] = request.context.model_copy(update={"request_id": "m2505-other-request"})

    with pytest.raises(ValidationError, match="context request_id"):
        EvaluateProteotypeSubgroupEquityRequest.model_validate(data, strict=True)


def test_result_digest_tampering_is_rejected() -> None:
    service = M2505Service()
    result = service.execute(build_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + ("f" * 64)})

    with pytest.raises((M2505ReplayError, ValidationError)):
        service.verify_replay(tampered)


def test_result_identifier_tampering_is_rejected() -> None:
    service = M2505Service()
    result = service.execute(build_request())
    tampered = result.model_copy(update={"result_id": "forged-result"})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})

    with pytest.raises((M2505ReplayError, ValidationError)):
        service.verify_replay(tampered)


def test_result_finding_ids_are_unique() -> None:
    result = M2505Service().execute(build_request(performance_status=EquityStatus.BELOW_FLOOR))
    assert result.findings
    tampered = result.model_copy(update={"findings": (result.findings[0], result.findings[0])})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})

    with pytest.raises(ValidationError, match="finding identifiers"):
        ProteotypeSubgroupEvaluationResult.model_validate(tampered.model_dump(mode="python"))


def test_plugin_rejects_unvalidated_execution_token() -> None:
    plugin = M2505Plugin(M2505Service())

    with pytest.raises(TypeError, match="validated request"):
        plugin.run(build_request())  # type: ignore[arg-type]


def test_plugin_rejects_unknown_submission_wrapper() -> None:
    plugin = M2505Plugin(M2505Service())

    with pytest.raises(TypeError, match="submission"):
        plugin.validate(build_request())


def test_duplicate_json_keys_are_rejected() -> None:
    duplicate = b'{"request_id":"one","request_id":"two"}'

    with pytest.raises(StrictJsonError):
        strict_json_loads(duplicate)


def test_hostile_mapping_preflight_fails_closed() -> None:
    service = M2505Service()

    with pytest.raises(M2505AuthorizationError):
        service.execute({"context": {"references": {}}})


def test_cli_abstention_has_nonzero_exit_and_no_false_success(tmp_path: Path) -> None:
    request = build_request(performance_status=EquityStatus.BELOW_FLOOR)
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")

    result = CliRunner().invoke(app, ["evaluate", str(request_path), "--output", str(output_path)])

    assert result.exit_code == 1
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "abstained"


def test_result_abstention_never_contains_report() -> None:
    result = M2505Service().execute(build_request(coverage_status=CoverageStatus.LIMITED))

    assert result.status.value == "abstained"
    assert result.report is None
    assert result.abstention_reason is not None
