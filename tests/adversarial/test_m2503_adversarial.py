"""Hostile-input, digest, and safe-abstention coverage for M25-03."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from evals.m25_03.fixture import build_request
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m25_03 import (
    BenchmarkDossier,
    BenchmarkStatus,
    ComputeMatchedComparison,
    ProteotypeInternalBenchmarkResult,
    RunProteotypeInternalBenchmarkRequest,
    ValidationStatus,
    result_payload_digest,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c21_reference_material.m25_03_internal_benchmark_ablation import (
    M2503AuthorizationError,
    M2503Plugin,
    M2503ReplayError,
    M2503Service,
)
from glio_proteogen.modules.c21_reference_material.m25_03_internal_benchmark_ablation.cli import app

if TYPE_CHECKING:
    from pathlib import Path


def _request_data() -> dict[str, Any]:
    return build_request().model_dump(mode="python")


def _self_rehashed(
    result: ProteotypeInternalBenchmarkResult,
    **updates: Any,
) -> ProteotypeInternalBenchmarkResult:
    """Forge a valid-looking result whose digest covers attacker changes."""

    forged = result.model_copy(update=updates)
    return forged.model_copy(update={"result_digest": result_payload_digest(forged)})


def test_unknown_request_field_is_rejected() -> None:
    data = _request_data()
    data["unexpected"] = "hostile"

    with pytest.raises(ValidationError):
        RunProteotypeInternalBenchmarkRequest.model_validate(data, strict=True)


def test_duplicate_source_artifacts_are_rejected() -> None:
    request = build_request()
    data = request.model_dump(mode="python")
    data["source_artifacts"] = (request.source_artifacts[0], request.source_artifacts[0])

    with pytest.raises(ValidationError, match="source artifact"):
        RunProteotypeInternalBenchmarkRequest.model_validate(data, strict=True)


def test_duplicate_baselines_are_rejected() -> None:
    request = build_request()
    data = request.model_dump(mode="python")
    data["baseline_runs"] = (request.baseline_runs[0], request.baseline_runs[0])

    with pytest.raises(ValidationError, match="baseline run identifiers"):
        RunProteotypeInternalBenchmarkRequest.model_validate(data, strict=True)


def test_unknown_comparison_run_is_rejected() -> None:
    request = build_request()
    data = request.model_dump(mode="python")
    comparison = request.comparisons[0].model_copy(update={"reference_run_id": "unknown-run"})
    data["comparisons"] = (comparison,)

    with pytest.raises(ValidationError, match="declared baseline"):
        RunProteotypeInternalBenchmarkRequest.model_validate(data, strict=True)


def test_wrong_upstream_media_type_is_rejected() -> None:
    request = build_request()
    data = request.model_dump(mode="python")
    data["upstream_result"] = request.upstream_result.model_copy(
        update={"media_type": "application/json"}
    )

    with pytest.raises(ValidationError, match="M25-02"):
        RunProteotypeInternalBenchmarkRequest.model_validate(data, strict=True)


def test_non_finite_numeric_input_is_rejected() -> None:
    data = _request_data()
    data["baseline_runs"][0]["compute_units"] = float("nan")

    with pytest.raises(ValidationError):
        RunProteotypeInternalBenchmarkRequest.model_validate(data, strict=True)


def test_compute_match_tolerance_is_enforced() -> None:
    request = build_request()
    comparison = request.comparisons[0].model_copy(
        update={"candidate_compute_units": 9.0, "compute_tolerance": 0.0}
    )

    with pytest.raises(ValidationError, match="compute-matched"):
        ComputeMatchedComparison.model_validate(comparison.model_dump(mode="python"))


@pytest.mark.parametrize(
    ("candidate_value", "direction"),
    [(0.70, "higher"), (0.90, "lower")],
)
def test_passing_metric_cannot_exceed_directional_tolerance(
    candidate_value: float,
    direction: str,
) -> None:
    request = build_request()
    baseline = request.baseline_runs[0]
    forged_metric = baseline.metrics[0].model_copy(
        update={"candidate_value": candidate_value, "lower_is_better": direction == "lower"}
    )
    forged_baseline = baseline.model_copy(update={"metrics": (forged_metric,)})
    forged_request = request.model_copy(update={"baseline_runs": (forged_baseline,)})

    with pytest.raises(ValidationError, match="directional tolerance"):
        RunProteotypeInternalBenchmarkRequest.model_validate(
            forged_request.model_dump(mode="python"), strict=True
        )


def test_request_duplicate_ablation_ids_are_rejected() -> None:
    request = build_request()
    data = request.model_dump(mode="python")
    data["ablations"] = (request.ablations[0], request.ablations[0])

    with pytest.raises(ValidationError, match="ablation identifiers"):
        RunProteotypeInternalBenchmarkRequest.model_validate(data, strict=True)


def test_dossier_duplicate_ids_and_unknown_candidate_are_rejected() -> None:
    result = M2503Service().execute(build_request())
    assert result.dossier is not None
    dossier = result.dossier
    duplicate = dossier.model_copy(update={"metrics": (dossier.metrics[0], dossier.metrics[0])})
    unknown_comparison = dossier.comparisons[0].model_copy(
        update={"candidate_run_id": "unknown-baseline"}
    )
    unknown = dossier.model_copy(update={"comparisons": (unknown_comparison,)})

    with pytest.raises(ValidationError, match="dossier ids"):
        BenchmarkDossier.model_validate(duplicate.model_dump(mode="python"))
    with pytest.raises(ValidationError, match="candidate run"):
        BenchmarkDossier.model_validate(unknown.model_dump(mode="python"))


def test_result_digest_tampering_is_rejected() -> None:
    service = M2503Service()
    result = service.execute(build_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + ("f" * 64)})

    with pytest.raises((M2503ReplayError, ValidationError)):
        service.verify_replay(tampered)


def test_result_request_digest_tampering_is_rejected() -> None:
    result = M2503Service().execute(build_request())
    tampered = result.model_copy(update={"request_digest": "sha256:" + ("f" * 64)})

    with pytest.raises(ValidationError, match="request digest"):
        ProteotypeInternalBenchmarkResult.model_validate(tampered.model_dump(mode="python"))


def test_completed_result_requires_dossier() -> None:
    result = M2503Service().execute(build_request())
    tampered = result.model_copy(update={"dossier": None})

    with pytest.raises(ValidationError, match="completed result"):
        ProteotypeInternalBenchmarkResult.model_validate(tampered.model_dump(mode="python"))


def test_result_identifier_tampering_is_rejected() -> None:
    service = M2503Service()
    result = service.execute(build_request())
    tampered = result.model_copy(update={"result_id": "result-forged"})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})

    with pytest.raises((M2503ReplayError, ValidationError)):
        service.verify_replay(tampered)


def test_self_rehashed_nested_dossier_mutation_is_rejected() -> None:
    service = M2503Service()
    result = service.execute(build_request())
    assert result.dossier is not None
    metric = result.dossier.metrics[0].model_copy(
        update={"candidate_value": result.dossier.metrics[0].candidate_value + 1.0}
    )
    dossier = result.dossier.model_copy(update={"metrics": (metric, *result.dossier.metrics[1:])})
    tampered = _self_rehashed(result, dossier=dossier)

    with pytest.raises(M2503ReplayError, match="differs from deterministic"):
        service.verify_replay(tampered)


def test_self_rehashed_provenance_mutation_is_rejected() -> None:
    service = M2503Service()
    result = service.execute(build_request())
    tampered = _self_rehashed(
        result,
        provenance=result.provenance.model_copy(update={"activity_id": "forged-activity"}),
    )

    with pytest.raises(M2503ReplayError, match="differs from deterministic"):
        service.verify_replay(tampered)


def test_plugin_rejects_self_rehashed_nested_mutation() -> None:
    service = M2503Service()
    plugin = M2503Plugin(service)
    result = service.execute(build_request())
    assert result.dossier is not None
    dossier = result.dossier.model_copy(
        update={"evidence": (*result.dossier.evidence, result.dossier.evidence[0])}
    )
    tampered = _self_rehashed(result, dossier=dossier)

    with pytest.raises(M2503ReplayError, match="differs from deterministic"):
        plugin.replay(tampered)


def test_result_finding_ids_are_unique() -> None:
    result = M2503Service().execute(build_request(metric_status=ValidationStatus.FAIL))
    assert result.findings
    tampered = result.model_copy(update={"findings": (result.findings[0], result.findings[0])})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})

    with pytest.raises(ValidationError, match="finding identifiers"):
        ProteotypeInternalBenchmarkResult.model_validate(tampered.model_dump(mode="python"))


def test_plugin_rejects_unvalidated_execution_token() -> None:
    plugin = M2503Plugin(M2503Service())

    with pytest.raises(TypeError, match="validated request"):
        plugin.run(build_request())  # type: ignore[arg-type]


def test_plugin_rejects_unknown_submission_wrapper() -> None:
    plugin = M2503Plugin(M2503Service())

    with pytest.raises(TypeError, match="submission"):
        plugin.validate(build_request())


def test_duplicate_json_keys_are_rejected() -> None:
    duplicate = b'{"request_id":"one","request_id":"two"}'

    with pytest.raises(StrictJsonError):
        strict_json_loads(duplicate)


def test_hostile_mapping_preflight_fails_closed() -> None:
    service = M2503Service()

    with pytest.raises(M2503AuthorizationError):
        service.execute({"context": {"references": {}}})


def test_cli_abstention_has_nonzero_exit_and_no_false_success(tmp_path: Path) -> None:
    request = build_request(metric_status=ValidationStatus.FAIL)
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["benchmark", str(request_path), "--output", str(output_path)],
    )

    assert result.exit_code == 1
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "abstained"


def test_result_abstention_never_contains_dossier() -> None:
    result = M2503Service().execute(build_request(comparison_status=ValidationStatus.NOT_EVALUABLE))

    assert result.status is BenchmarkStatus.ABSTAINED
    assert result.dossier is None
    assert result.abstention_reason is not None
