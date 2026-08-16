"""Adversarial and branch-closure tests for provisional M07-06."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m07_06 import (
    CopyNumberDosageUncertaintyDecompositionResult,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyComponent,
    UncertaintyDecomposition,
    UncertaintyDimension,
    UncertaintyFinding,
    UncertaintyFindingCode,
    canonical_result_digest,
    normalized_request,
    verify_result_digest,
)
from glio_proteogen.kernel.models import ArtifactReference, EstimateState, UncertaintyEstimate
from glio_proteogen.modules.c07_copy_number_dosage.m07_06_uncertainty_decomposition import (
    M0706AuthorizationError,
    M0706ReplayVerificationError,
    M0706Service,
    M0706UncertaintyDecompositionEngine,
    ValidatedM0706Request,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_06_uncertainty_decomposition.api import (
    create_app,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_06_uncertainty_decomposition.cli import (
    app as cli_app,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_06_uncertainty_decomposition.plugin import (
    M0706Plugin,
)
from tests.integration.test_m07_06_interfaces import _request as request_dict
from tests.modules.c07_copy_number_dosage.test_m07_06_uncertainty import _request

if TYPE_CHECKING:
    from pathlib import Path

_SEVEN = 7
_NOMINAL_COVERAGE = 0.9
_LOWER_COVERAGE = 0.85
_UPPER_COVERAGE = 0.95
_FORBIDDEN = 403
_UNPROCESSABLE = 422
_CONFLICT = 409

_RESULT = TypeAdapter(CopyNumberDosageUncertaintyDecompositionResult)


def _artifact(
    label: str,
    char: str = "a",
    media_type: str = "application/json",
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=label,
        version="1.0.0",
        digest=f"sha256:{char * 64}",
        media_type=media_type,
    )


def _component(dimension: UncertaintyDimension) -> UncertaintyComponent:
    return UncertaintyComponent(
        dimension=dimension,
        estimate=UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale="No owner-confirmed calibration is available.",
        ),
        rationale="The provisional engine does not estimate this dimension.",
    )


def _decomposition(dimensions: tuple[UncertaintyDimension, ...]) -> UncertaintyDecomposition:
    return UncertaintyDecomposition(
        decomposition_id="decomposition.test",
        components=tuple(_component(item) for item in dimensions),
        method="provisional-rule",
        model_reference=_artifact("model.test"),
    )


def test_canonical_helpers_cover_model_dict_and_invalid_inputs() -> None:
    result = M0706Service().execute(_request())
    assert normalized_request({"b": 2, "a": 1}) == {"b": 2, "a": 1}
    assert canonical_result_digest(result) == result.result_digest
    assert verify_result_digest(result)
    assert not verify_result_digest(object())
    assert not verify_result_digest({"result_digest": "not-a-digest"})
    assert not verify_result_digest({"result_digest": 42})
    assert not verify_result_digest({"result_digest": result.result_digest, "bad": object()})


def test_decomposition_requires_exactly_all_seven_dimensions() -> None:
    dimensions = tuple(UncertaintyDimension)
    valid = _decomposition(dimensions)
    assert len(valid.components) == _SEVEN
    with pytest.raises(ValueError, match="all seven"):
        _decomposition((*dimensions[:-1], dimensions[0]))


def test_sensitivity_envelope_shape_and_coverage_gate_are_closed() -> None:
    with pytest.raises(ValueError, match="requires bounds"):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.EVALUATED,
            nominal_coverage=_NOMINAL_COVERAGE,
            rationale="missing bounds",
        )
    with pytest.raises(ValueError, match="not ordered"):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.EVALUATED,
            nominal_coverage=_NOMINAL_COVERAGE,
            lower_bound=0.8,
            upper_bound=0.7,
            observed_coverage=_NOMINAL_COVERAGE,
            rationale="bad bounds",
        )
    with pytest.raises(ValueError, match="85-95"):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.EVALUATED,
            nominal_coverage=_NOMINAL_COVERAGE,
            lower_bound=0.8,
            upper_bound=_NOMINAL_COVERAGE,
            observed_coverage=0.5,
            rationale="out of gate",
        )
    with pytest.raises(ValueError, match="non-evaluated"):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.NOT_EVALUABLE,
            nominal_coverage=_NOMINAL_COVERAGE,
            lower_bound=0.8,
            rationale="not evaluable",
        )
    evaluated = SensitivityEnvelope(
        status=SensitivityEnvelopeStatus.EVALUATED,
        nominal_coverage=_NOMINAL_COVERAGE,
        lower_bound=_LOWER_COVERAGE,
        upper_bound=_UPPER_COVERAGE,
        observed_coverage=_NOMINAL_COVERAGE,
        rationale="synthetic gate",
    )
    assert evaluated.observed_coverage == _NOMINAL_COVERAGE


def test_result_closure_rejects_digest_context_findings_and_status_mismatches() -> None:
    result = M0706Service().execute(_request())
    document = result.model_dump(mode="json")
    cases: list[tuple[str, object]] = [
        ("result digest", {**document, "result_digest": "sha256:" + "0" * 64}),
        (
            "request context",
            {**document, "request": {**document["request"], "request_id": "other"}},
        ),
        (
            "unique",
            {
                **document,
                "findings": [document["findings"][0], document["findings"][0]],
            },
        ),
        ("machine-readable", {**document, "findings": []}),
        (
            "abstained result",
            {
                **document,
                "sensitivity_envelope": {
                    **document["sensitivity_envelope"],
                    "status": "not_evaluable",
                },
            },
        ),
    ]
    for label, candidate in cases:
        with pytest.raises(ValidationError):
            _RESULT.validate_json(json.dumps(candidate), strict=True)
        assert label


def test_request_binding_rejects_context_media_nominal_and_duplicate_sources() -> None:
    request = _request()
    cases: list[dict[str, object]] = [
        {"context": request.context.model_copy(update={"request_id": "other"})},
        {"constraint_result": _artifact("wrong", "1")},
        {"policy": request.policy.model_copy(update={"nominal_coverage": 0.8})},
        {
            "source_artifacts": (
                request.source_artifacts[0],
                request.source_artifacts[0],
            )
        },
    ]
    for update in cases:
        with pytest.raises(ValidationError):
            M0706Service.validate_request(request.model_copy(update=update))


def test_engine_and_plugin_fail_closed_for_hostile_inputs() -> None:
    engine = M0706UncertaintyDecompositionEngine()
    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile")

    with pytest.raises(
        (M0706AuthorizationError, TypeError, ValidationError, M0706ReplayVerificationError)
    ):
        engine.decompose(Hostile())
    with pytest.raises(M0706ReplayVerificationError):
        engine.verify(object())
    result = engine.decompose(_request())
    with pytest.raises(M0706ReplayVerificationError):
        engine.verify(result.model_copy(update={"request_digest": "sha256:" + "0" * 64}))
    plugin = M0706Plugin(M0706Service())
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        plugin.run(ValidatedM0706Request(request=_request(), _seal=object()))
    raw = json.dumps(request_dict()).encode("utf-8")
    token = plugin.validate(raw)
    assert plugin.run(token).status.value == "abstained"
    assert plugin.validate(raw.decode("utf-8")).request.request_id == "request.m0706.interface"
    assert plugin.validate(_request()).request.request_id == "request.m0706.test"

    class Divergent(M0706UncertaintyDecompositionEngine):
        def decompose(self, request: object) -> CopyNumberDosageUncertaintyDecompositionResult:
            return super().decompose(request).model_copy(
                update={"abstention_reason": "different replay"}
            )

    with pytest.raises(M0706ReplayVerificationError):
        Divergent().verify(result)


def test_api_failure_mapping_covers_auth_tamper_and_strict_json() -> None:
    client = TestClient(create_app())
    denied = request_dict()
    denied["context"]["references"]["consent"]["state"] = "withheld"  # type: ignore[index]
    assert client.post("/v1/modules/M07-06/validate", json=denied).status_code == _FORBIDDEN
    assert client.post("/v1/modules/M07-06/decompose", json=denied).status_code == _FORBIDDEN
    assert (
        client.post(
            "/v1/modules/M07-06/validate",
            content=b"not-json",
            headers={"content-type": "application/json"},
        ).status_code
        == _UNPROCESSABLE
    )
    result = client.post("/v1/modules/M07-06/decompose", json=request_dict()).json()["result"]
    result["abstention_reason"] = "tampered"
    result["result_digest"] = canonical_result_digest(result)
    assert client.post("/v1/modules/M07-06/verify", json=result).status_code == _CONFLICT
    assert client.post("/v1/modules/M07-06/verify", json={}).status_code == _UNPROCESSABLE


def test_cli_failure_mapping_covers_schema_invalid_json_no_overwrite_and_tamper(
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    assert runner.invoke(cli_app, ["export-schema", "nope"]).exit_code != 0
    bad = tmp_path / "bad.json"
    bad.write_text("not-json", encoding="utf-8")
    assert runner.invoke(cli_app, ["validate", str(bad)]).exit_code != 0
    invalid_request = tmp_path / "invalid-request.json"
    invalid_request.write_text("{}", encoding="utf-8")
    assert runner.invoke(cli_app, ["validate", str(invalid_request)]).exit_code != 0
    assert runner.invoke(cli_app, ["export-schema", "output"]).exit_code == 0
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request_dict()), encoding="utf-8")
    result_path = tmp_path / "result.json"
    first = runner.invoke(cli_app, ["decompose", str(request_path), "--output", str(result_path)])
    assert first.exit_code == 1
    assert runner.invoke(cli_app, ["decompose", str(request_path)]).exit_code == 1
    assert runner.invoke(cli_app, ["decompose", str(invalid_request)]).exit_code != 0
    second = runner.invoke(cli_app, ["decompose", str(request_path), "--output", str(result_path)])
    assert second.exit_code != 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["abstention_reason"] = "tampered"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code != 0


def test_finding_contract_accepts_all_machine_codes() -> None:
    for code in UncertaintyFindingCode:
        finding = UncertaintyFinding(
            finding_id=f"finding.{code.value}",
            code=code,
            message="explicit machine-readable finding",
        )
        assert finding.code is code
