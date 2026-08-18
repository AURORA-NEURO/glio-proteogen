"""Hostile-input, schema, replay, and safe-abstention closure for M25-05."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from evals.m25_05.fixture import build_request
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m25_05 import (
    CalibrationSummary,
    CoverageStatus,
    CoverageSummary,
    EquityStatus,
    EvaluateProteotypeSubgroupEquityRequest,
    EvaluationConfiguration,
    ProteotypeSubgroupEvaluationResult,
    SubgroupDimension,
    SubgroupEvaluationReport,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import SupportDecision, SupportStatus
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


@pytest.mark.parametrize("mutation", ["report", "evidence"])
def test_replay_rejects_self_rehashed_semantic_mutations(mutation: str) -> None:
    """A forged digest must not make a changed report or evidence replayable."""

    service = M2505Service()
    result = service.execute(build_request())
    if mutation == "report":
        assert result.report is not None
        changed_report = result.report.model_copy(update={"version": "1.0.1"})
        forged = result.model_copy(update={"report": changed_report})
    else:
        assert result.evidence
        changed_evidence = result.evidence[0].model_copy(
            update={"claim": "forged evidence claim"}
        )
        forged = result.model_copy(update={"evidence": (changed_evidence,)})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    with pytest.raises(M2505ReplayError):
        service.verify_replay(forged)


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


def test_performance_bounds_and_floor_states_are_closed() -> None:
    performance = build_request().performance[0]
    cases = (
        performance.model_copy(update={"lower_bound": 0.9, "upper_bound": 0.8}),
        performance.model_copy(update={"value": 0.95}),
        performance.model_copy(update={"equity_status": EquityStatus.BELOW_FLOOR}),
        performance.model_copy(
            update={
                "equity_status": EquityStatus.WITHIN_FLOOR,
                "value": 0.6,
                "lower_bound": 0.5,
                "upper_bound": 0.65,
            }
        ),
    )

    for candidate in cases:
        with pytest.raises(ValidationError):
            type(performance).model_validate(candidate.model_dump(mode="python"), strict=True)


def test_calibration_coverage_and_configuration_closures_are_strict() -> None:
    request = build_request()
    calibration = request.calibration[0].model_copy(
        update={"nominal_coverage": 0.8, "coverage_target": 0.9}
    )
    with pytest.raises(ValidationError, match="nominal coverage"):
        CalibrationSummary.model_validate(calibration.model_dump(mode="python"), strict=True)

    coverage = request.coverage[0].model_copy(
        update={"supported_examples": 11, "total_examples": 10, "coverage_fraction": 1.0}
    )
    with pytest.raises(ValidationError, match="supported examples"):
        CoverageSummary.model_validate(coverage.model_dump(mode="python"), strict=True)
    coverage = request.coverage[0].model_copy(update={"coverage_fraction": 0.8})
    with pytest.raises(ValidationError, match="coverage fraction"):
        CoverageSummary.model_validate(coverage.model_dump(mode="python"), strict=True)

    configuration = request.configuration.model_copy(
        update={"required_dimensions": (*tuple(SubgroupDimension)[:-1], SubgroupDimension.AGE)}
    )
    with pytest.raises(ValidationError, match="all subgroup dimensions"):
        EvaluationConfiguration.model_validate(configuration.model_dump(mode="python"), strict=True)


def test_report_and_request_dimension_alignment_are_closed() -> None:
    request = build_request()
    report = M2505Service().execute(request).report
    assert report is not None
    duplicate = report.model_copy(
        update={
            "calibration": (report.calibration[0], report.calibration[0], *report.calibration[2:])
        }
    )
    with pytest.raises(ValidationError, match="report ids"):
        SubgroupEvaluationReport.model_validate(duplicate.model_dump(mode="python"), strict=True)

    missing_report = report.model_copy(update={"performance": tuple(request.performance[:-1])})
    with pytest.raises(ValidationError, match="every required"):
        SubgroupEvaluationReport.model_validate(
            missing_report.model_dump(mode="python"), strict=True
        )

    dimensions = tuple(SubgroupDimension)
    changed = dimensions[1]
    replacement = dimensions[2]

    def changed_dimension(items: tuple[Any, ...]) -> tuple[Any, ...]:
        return tuple(
            item.model_copy(update={"dimension": replacement})
            if item.dimension is changed
            else item
            for item in items
        )

    with pytest.raises(ValidationError, match="every required subgroup"):
        EvaluateProteotypeSubgroupEquityRequest.model_validate(
            request.model_copy(
                update={
                    "performance": changed_dimension(request.performance),
                    "calibration": changed_dimension(request.calibration),
                    "coverage": changed_dimension(request.coverage),
                }
            ).model_dump(mode="python"),
            strict=True,
        )

    shifted_calibration = tuple(
        item.model_copy(update={"dimension": SubgroupDimension.SEX})
        if item.dimension is SubgroupDimension.AGE
        else item
        for item in request.calibration
    )
    with pytest.raises(ValidationError, match="performance and calibration"):
        EvaluateProteotypeSubgroupEquityRequest.model_validate(
            request.model_copy(update={"calibration": shifted_calibration}).model_dump(
                mode="python"
            ),
            strict=True,
        )
    shifted_coverage = tuple(
        item.model_copy(update={"dimension": SubgroupDimension.SEX})
        if item.dimension is SubgroupDimension.AGE
        else item
        for item in request.coverage
    )
    with pytest.raises(ValidationError, match="performance and coverage"):
        EvaluateProteotypeSubgroupEquityRequest.model_validate(
            request.model_copy(update={"coverage": shifted_coverage}).model_dump(mode="python"),
            strict=True,
        )


def test_result_request_digest_and_terminal_state_closures_are_strict() -> None:
    service = M2505Service()
    result = service.execute(build_request())
    bad_request_digest = result.model_copy(update={"request_digest": "sha256:" + ("f" * 64)})
    with pytest.raises(ValidationError, match="request digest"):
        ProteotypeSubgroupEvaluationResult.model_validate(
            bad_request_digest.model_dump(mode="python"), strict=True
        )

    bad_support = result.support_decision.model_copy(
        update={"status": SupportStatus.REVIEW_REQUIRED}
    )
    bad_evaluated = result.model_copy(update={"support_decision": bad_support})
    with pytest.raises(ValidationError, match="evaluated result"):
        ProteotypeSubgroupEvaluationResult.model_validate(
            bad_evaluated.model_dump(mode="python"), strict=True
        )

    abstained = service.execute(build_request(performance_status=EquityStatus.BELOW_FLOOR))
    bad_abstention = abstained.model_copy(
        update={
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="bad-support",
                rationale="This deliberately violates abstention closure.",
            )
        }
    )
    with pytest.raises(ValidationError, match="abstained result"):
        ProteotypeSubgroupEvaluationResult.model_validate(
            bad_abstention.model_dump(mode="python"), strict=True
        )


def test_canonical_projection_accepts_mapping_input() -> None:
    request = build_request()

    assert canonical_request_digest(request.model_dump(mode="json")).startswith("sha256:")
