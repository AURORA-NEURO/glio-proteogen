"""Hostile-input, replay, and safe-abstention closure for M25-07."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from evals.m25_07.fixture import build_request
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m25_07 import (
    EvaluateProteotypeHumanFactorsRequest,
    FallbackScenario,
    HumanFactorsOperationalReport,
    OperationalConfiguration,
    OperationalDimension,
    OperationalMetric,
    OperationalStatus,
    ProteotypeHumanFactorsResult,
    result_payload_digest,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c21_reference_material import (
    m25_07_human_factors_operational_evaluator as m2507,
)

if TYPE_CHECKING:
    from pathlib import Path


def _request_data() -> dict[str, Any]:
    return build_request().model_dump(mode="python")


def test_unknown_request_field_is_rejected() -> None:
    data = _request_data()
    data["unexpected"] = "hostile"

    with pytest.raises(ValidationError):
        EvaluateProteotypeHumanFactorsRequest.model_validate(data, strict=True)


def test_metric_target_tolerance_is_closed() -> None:
    metric = (
        build_request()
        .metrics[0]
        .model_copy(update={"observed_value": 0.5, "target_value": 0.9, "tolerance": 0.1})
    )

    with pytest.raises(ValidationError, match="target tolerance"):
        OperationalMetric.model_validate(metric.model_dump(mode="python"), strict=True)


def test_unavailable_fallback_cannot_pass() -> None:
    fallback = (
        build_request()
        .fallbacks[0]
        .model_copy(update={"fallback_available": False, "status": OperationalStatus.PASS})
    )

    with pytest.raises(ValidationError, match="unavailable fallback"):
        FallbackScenario.model_validate(fallback.model_dump(mode="python"), strict=True)


def test_duplicate_metric_and_fallback_ids_are_rejected() -> None:
    request = build_request()
    data = request.model_dump(mode="python")
    data["metrics"] = (request.metrics[0], request.metrics[0], *request.metrics[2:])
    with pytest.raises(ValidationError, match="operational metric ids"):
        EvaluateProteotypeHumanFactorsRequest.model_validate(data, strict=True)

    data = request.model_dump(mode="python")
    data["fallbacks"] = (request.fallbacks[0], request.fallbacks[0], *request.fallbacks[2:])
    with pytest.raises(ValidationError, match="fallback scenario ids"):
        EvaluateProteotypeHumanFactorsRequest.model_validate(data, strict=True)


def test_duplicate_source_artifact_ids_are_rejected() -> None:
    request = build_request()
    data = request.model_dump(mode="python")
    data["source_artifacts"] = (request.source_artifacts[0], request.source_artifacts[0])

    with pytest.raises(ValidationError, match="source artifact"):
        EvaluateProteotypeHumanFactorsRequest.model_validate(data, strict=True)


def test_wrong_media_and_context_identity_are_rejected() -> None:
    request = build_request()
    wrong_media = request.model_copy(
        update={
            "upstream_result": request.upstream_result.model_copy(
                update={"media_type": "application/json"}
            )
        }
    )
    with pytest.raises(ValidationError, match="M25-06"):
        EvaluateProteotypeHumanFactorsRequest.model_validate(
            wrong_media.model_dump(mode="python"), strict=True
        )

    wrong_context = request.model_copy(
        update={"context": request.context.model_copy(update={"request_id": "different-request"})}
    )
    with pytest.raises(ValidationError, match="context request_id"):
        EvaluateProteotypeHumanFactorsRequest.model_validate(
            wrong_context.model_dump(mode="python"), strict=True
        )


def test_missing_required_operational_dimensions_are_rejected() -> None:
    request = build_request()
    dimensions = tuple(OperationalDimension)
    configuration = request.configuration.model_copy(
        update={"required_dimensions": (*dimensions[:-1], OperationalDimension.THROUGHPUT)}
    )
    with pytest.raises(ValidationError, match="all operational dimensions"):
        OperationalConfiguration.model_validate(
            configuration.model_dump(mode="python"), strict=True
        )


def test_non_finite_numeric_input_is_rejected() -> None:
    data = _request_data()
    data["metrics"][0]["observed_value"] = float("nan")

    with pytest.raises(ValidationError):
        EvaluateProteotypeHumanFactorsRequest.model_validate(data, strict=True)


def test_result_digest_and_identifier_tampering_are_rejected() -> None:
    service = m2507.M2507Service()
    result = service.execute(build_request())
    tampered_digest = result.model_copy(update={"result_digest": "sha256:" + ("f" * 64)})
    with pytest.raises((m2507.M2507ReplayError, ValidationError)):
        service.verify_replay(tampered_digest)

    tampered_id = result.model_copy(update={"result_id": "forged-result"})
    tampered_id = tampered_id.model_copy(
        update={"result_digest": result_payload_digest(tampered_id)}
    )
    with pytest.raises((m2507.M2507ReplayError, ValidationError)):
        service.verify_replay(tampered_id)


def test_result_finding_ids_and_terminal_states_are_closed() -> None:
    service = m2507.M2507Service()
    result = service.execute(build_request(metric_status=OperationalStatus.FAIL))
    assert result.findings
    duplicate = result.model_copy(update={"findings": (result.findings[0], result.findings[0])})
    duplicate = duplicate.model_copy(update={"result_digest": result_payload_digest(duplicate)})
    with pytest.raises(ValidationError, match="finding identifiers"):
        ProteotypeHumanFactorsResult.model_validate(
            duplicate.model_dump(mode="python"), strict=True
        )

    bad_support = result.support_decision.model_copy(update={"status": SupportStatus.SUPPORTED})
    bad_result = result.model_copy(update={"support_decision": bad_support})
    with pytest.raises(ValidationError, match="abstained result"):
        ProteotypeHumanFactorsResult.model_validate(
            bad_result.model_dump(mode="python"), strict=True
        )


def test_duplicate_json_and_hostile_preflight_fail_closed() -> None:
    with pytest.raises(StrictJsonError):
        strict_json_loads(b'{"request_id":"one","request_id":"two"}')
    with pytest.raises(m2507.M2507AuthorizationError):
        m2507.M2507Service().execute({"context": {"references": {}}})


def test_plugin_rejects_unvalidated_tokens_and_wrappers() -> None:
    plugin = m2507.M2507Plugin(m2507.M2507Service())
    with pytest.raises(TypeError, match="validated request"):
        plugin.run(build_request())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="submission"):
        plugin.validate(build_request())


def test_plugin_rejects_forged_cross_instance_and_nested_mutated_tokens() -> None:
    plugin = m2507.M2507Plugin(m2507.M2507Service())
    other = m2507.M2507Plugin(m2507.M2507Service())
    token = plugin.validate(m2507.HumanFactorsSubmission(build_request()))

    forged = m2507.ValidatedM2507Request(token.request, object())
    with pytest.raises(TypeError, match="validated request"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request"):
        other.run(token)

    object.__setattr__(token.request.metrics[0], "metric_name", "forged operational metric")
    with pytest.raises(TypeError, match="validated request"):
        plugin.run(token)

    replaced = plugin.validate(m2507.HumanFactorsSubmission(build_request()))
    object.__setattr__(replaced, "request", replaced.request.model_copy())
    with pytest.raises(TypeError, match="validated request"):
        plugin.run(replaced)


def test_cli_abstention_is_nonzero_and_result_has_no_report(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(
        build_request(metric_status=OperationalStatus.FAIL).model_dump_json(), encoding="utf-8"
    )

    result = CliRunner().invoke(
        m2507.cli.app, ["evaluate", str(request_path), "--output", str(output_path)]
    )

    assert result.exit_code == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "abstained"
    assert payload["report"] is None


def test_report_closure_rejects_duplicate_or_missing_paths() -> None:
    service = m2507.M2507Service()
    report = service.execute(build_request()).report
    assert report is not None

    duplicate_fallback = report.model_copy(
        update={"fallbacks": (report.fallbacks[0], report.fallbacks[0], *report.fallbacks[2:])}
    )
    with pytest.raises(ValidationError, match="fallback scenario ids"):
        HumanFactorsOperationalReport.model_validate(
            duplicate_fallback.model_dump(mode="python"), strict=True
        )

    missing_metric = report.model_copy(update={"metrics": tuple(report.metrics[:-1])})
    with pytest.raises(ValidationError, match="every configured"):
        HumanFactorsOperationalReport.model_validate(
            missing_metric.model_dump(mode="python"), strict=True
        )

    missing_fallback = report.model_copy(update={"fallbacks": tuple(report.fallbacks[:1])})
    with pytest.raises(ValidationError, match="downtime, recovery"):
        HumanFactorsOperationalReport.model_validate(
            missing_fallback.model_dump(mode="python"), strict=True
        )


def test_request_required_dimensions_and_result_digest_closures() -> None:
    request = build_request()
    missing_metric = request.model_copy(update={"metrics": tuple(request.metrics[:-1])})
    with pytest.raises(ValidationError, match="every configured"):
        EvaluateProteotypeHumanFactorsRequest.model_validate(
            missing_metric.model_dump(mode="python"), strict=True
        )
    missing_fallback = request.model_copy(update={"fallbacks": tuple(request.fallbacks[:1])})
    with pytest.raises(ValidationError, match="downtime, recovery"):
        EvaluateProteotypeHumanFactorsRequest.model_validate(
            missing_fallback.model_dump(mode="python"), strict=True
        )

    result = m2507.M2507Service().execute(request)
    bad_digest = result.model_copy(update={"request_digest": "sha256:" + ("f" * 64)})
    with pytest.raises(ValidationError, match="request digest"):
        ProteotypeHumanFactorsResult.model_validate(
            bad_digest.model_dump(mode="python"), strict=True
        )
    bad_id = result.model_copy(update={"result_id": "forged"})
    with pytest.raises(ValidationError, match="result id"):
        ProteotypeHumanFactorsResult.model_validate(bad_id.model_dump(mode="python"), strict=True)


def test_service_json_validation_and_cli_replay_errors(tmp_path: Path) -> None:
    service = m2507.M2507Service()
    assert service.validate_request(build_request().model_dump_json()).request_id
    bad_path = tmp_path / "bad-result.json"
    bad_path.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(m2507.cli.app, ["verify", str(bad_path)])
    assert result.exit_code != 0
