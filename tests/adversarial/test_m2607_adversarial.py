"""Adversarial closure for M26-07 identity, replay, and parser boundaries."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m26_07 import (
    ChangePackage,
    ControlProteinSubtypeChangeRequest,
    ProteinSubtypeChangeControlResult,
    RevalidationRecord,
    RolloutStage,
    ShadowComparison,
    canonical_request_digest,
    normalized_request,
    result_payload_digest,
)
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c20_biomarker_panel.m26_07_change_control_rollback import (
    M2607ChangeControlEngine,
    M2607ChangeControlService,
    M2607Plugin,
    M2607ReplayError,
    RollbackSubmission,
    ValidatedM2607Request,
    app,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_07_change_control_rollback import (
    plugin as plugin_module,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_07_change_control_rollback.cli import (
    app as cli_app,
)
from tests.runtime.test_m2607_runtime import _request

HTTP_UNPROCESSABLE = 422
HTTP_OK = 200

if TYPE_CHECKING:
    from pathlib import Path


def test_plugin_rejects_duplicate_json_keys_before_model_validation() -> None:
    plugin = M2607Plugin()

    with pytest.raises(StrictJsonError):
        plugin.validate(RollbackSubmission(b'{"request_id":"a","request_id":"b"}'))


def test_plugin_rejects_malformed_json_without_partial_parse() -> None:
    with pytest.raises((StrictJsonError, ValueError)):
        M2607Plugin().validate(RollbackSubmission(b'{"request_id":'))


def test_forged_validated_request_token_is_rejected() -> None:
    request = _request()
    forged = ValidatedM2607Request(request, object())

    with pytest.raises(TypeError, match="validated request token"):
        M2607Plugin().run(forged)


def test_revalidation_cross_proposal_is_rejected_at_request_boundary() -> None:
    request = _request()
    record = request.revalidations[0].model_copy(update={"proposal_id": "proposal.other"})

    with pytest.raises(ValidationError, match="different proposal"):
        ControlProteinSubtypeChangeRequest.model_validate(
            request.model_dump(mode="python")
            | {"revalidations": (record.model_dump(mode="python"),)}
        )


def test_request_binds_nested_rollback_and_evidence_artifacts_exactly() -> None:
    request = _request()
    missing_restore = tuple(
        artifact
        for artifact in request.source_artifacts
        if artifact.artifact_id != "artifact.restore"
    )
    forged_evidence = request.source_artifacts[-1].model_copy(
        update={"digest": "sha256:" + "f" * 64}
    )

    with pytest.raises(ValidationError, match="bind every declared"):
        ControlProteinSubtypeChangeRequest.model_validate(
            request.model_dump(mode="python") | {"source_artifacts": missing_restore}
        )
    with pytest.raises(ValidationError, match="bind every declared"):
        ControlProteinSubtypeChangeRequest.model_validate(
            request.model_dump(mode="python")
            | {
                "source_artifacts": (
                    *request.source_artifacts[:-1],
                    forged_evidence,
                )
            }
        )


def test_request_rejects_duplicate_source_artifact_identifiers() -> None:
    request = _request()

    with pytest.raises(ValidationError, match="identifiers must be unique"):
        ControlProteinSubtypeChangeRequest.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (*request.source_artifacts, request.source_artifacts[0])}
        )


def test_result_id_tamper_is_rejected_even_when_digest_shape_is_valid() -> None:
    service = M2607ChangeControlService()
    result = service.control(_request())
    tampered = result.model_copy(update={"result_id": "result.m2607.forged"})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})

    with pytest.raises(M2607ReplayError):
        service.verify(tampered)


def test_self_rehashed_approved_package_cannot_change_request_controls() -> None:
    result = M2607ChangeControlService().control(_request())
    assert result.change_package is not None
    forged_proposal = result.change_package.proposal.model_copy(
        update={"rationale": "forged change rationale"}
    )
    forged_package = result.change_package.model_copy(update={"proposal": forged_proposal})
    forged = result.model_copy(update={"change_package": forged_package})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    with pytest.raises(ValidationError, match="exact request change controls"):
        ProteinSubtypeChangeControlResult.model_validate(forged.model_dump(mode="python"))


def test_request_digest_tamper_is_rejected() -> None:
    service = M2607ChangeControlService()
    result = service.control(_request())
    tampered = result.model_copy(update={"request_digest": "sha256:" + "f" * 64})

    with pytest.raises(M2607ReplayError):
        service.verify(tampered)


def test_api_sanitizes_non_object_and_tampered_replay_errors() -> None:
    service = M2607ChangeControlService()
    result = service.control(_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})

    with TestClient(app) as client:
        non_object = client.post("/v1/modules/M26-07/validate", content=b"[]")
        replay = client.post(
            "/v1/modules/M26-07/verify",
            content=json.dumps({"result": tampered.model_dump(mode="json")}),
        )

    assert non_object.status_code == HTTP_UNPROCESSABLE
    assert replay.status_code == HTTP_UNPROCESSABLE
    assert "Traceback" not in replay.text


def test_plugin_strict_json_decode_is_called_once(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request()
    original = plugin_module.strict_json_loads  # type: ignore[attr-defined]
    calls = 0

    def counting_decode(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(plugin_module, "strict_json_loads", counting_decode)
    M2607Plugin().validate(RollbackSubmission(request.model_dump_json()))

    assert calls == 1


def test_api_covers_schema_lookup_and_sanitized_parse_errors() -> None:
    request = _request()
    rejected = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    rejected_context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": rejected})}
    )
    denied_request = request.model_copy(update={"context": rejected_context})
    with TestClient(app) as client:
        schema = client.get("/v1/modules/M26-07/schemas/request")
        malformed = client.post("/v1/modules/M26-07/verify", content=b"{")
        denied_validate = client.post(
            "/v1/modules/M26-07/validate", content=denied_request.model_dump_json()
        )
        denied_control = client.post(
            "/v1/modules/M26-07/control", content=denied_request.model_dump_json()
        )

    assert schema.status_code == HTTP_OK
    assert schema.json()["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M26-07"
    assert malformed.status_code == HTTP_UNPROCESSABLE
    assert denied_validate.status_code == HTTP_UNPROCESSABLE
    assert denied_control.status_code == HTTP_UNPROCESSABLE


def test_cli_covers_stdout_and_sanitized_invalid_inputs(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    invalid_path = tmp_path / "invalid.json"
    request_path.write_bytes(_request().model_dump_json().encode())
    invalid_path.write_text("{}", encoding="utf-8")

    schema = runner.invoke(cli_app, ["export-schema", "request"])
    unknown = runner.invoke(cli_app, ["export-schema", "unknown"])
    validated = runner.invoke(cli_app, ["validate", str(request_path)])
    invalid = runner.invoke(cli_app, ["validate", str(invalid_path)])

    assert schema.exit_code == 0
    assert "GLIO-PROTEOGEN-M26-07" in schema.stdout
    assert unknown.exit_code != 0
    assert validated.exit_code == 0
    assert invalid.exit_code != 0


def test_contract_gate_variants_are_all_rejected() -> None:
    request = _request()
    passed = request.revalidations[0]
    failed = passed.model_copy(update={"passed": False})
    wrong_revalidation = passed.model_copy(update={"proposal_id": "proposal.other"})
    wrong_comparison = request.comparisons[0].model_copy(update={"proposal_id": "proposal.other"})
    regression = request.comparisons[0].model_copy(update={"no_regression": False})

    def package(
        *,
        revalidations: tuple[RevalidationRecord, ...] = (passed,),
        comparisons: tuple[ShadowComparison, ...] = request.comparisons,
        rollout_stage: RolloutStage = RolloutStage.SHADOW,
    ) -> ChangePackage:
        return ChangePackage(
            package_id="package.m2607.invalid",
            version="1.1.0",
            proposal=request.proposal,
            revalidations=revalidations,
            comparisons=comparisons,
            rollout_stage=rollout_stage,
            rollback_point=request.rollback_point,
            package_digest="sha256:" + "a" * 64,
        )

    with pytest.raises(ValidationError, match="passing required"):
        package(revalidations=(failed,))
    with pytest.raises(ValidationError, match="different proposal"):
        package(revalidations=(wrong_revalidation,))
    with pytest.raises(ValidationError, match="different proposal"):
        package(comparisons=(wrong_comparison,))
    with pytest.raises(ValidationError, match="critical regression"):
        package(comparisons=(regression,))
    with pytest.raises(ValidationError, match="approver"):
        package(rollout_stage=RolloutStage.STAGED)

    with pytest.raises(ValidationError, match="passing required"):
        ControlProteinSubtypeChangeRequest.model_validate(
            request.model_dump(mode="python")
            | {"revalidations": (failed.model_dump(mode="python"),)}
        )
    with pytest.raises(ValidationError, match="different proposal"):
        ControlProteinSubtypeChangeRequest.model_validate(
            request.model_dump(mode="python")
            | {"revalidations": (wrong_revalidation.model_dump(mode="python"),)}
        )
    with pytest.raises(ValidationError, match="different proposal"):
        ControlProteinSubtypeChangeRequest.model_validate(
            request.model_dump(mode="python")
            | {"comparisons": (wrong_comparison.model_dump(mode="python"),)}
        )
    with pytest.raises(ValidationError, match="critical regression"):
        ControlProteinSubtypeChangeRequest.model_validate(
            request.model_dump(mode="python")
            | {"comparisons": (regression.model_dump(mode="python"),)}
        )


def test_result_closure_and_canonical_mapping_variants_are_rejected() -> None:
    request = _request()
    result = M2607ChangeControlService().control(request)
    payload = result.model_dump(mode="python")

    with pytest.raises(ValidationError, match="request digest"):
        ProteinSubtypeChangeControlResult.model_validate(
            payload | {"request_digest": "sha256:" + "f" * 64}
        )
    with pytest.raises(ValidationError, match="supported package"):
        ProteinSubtypeChangeControlResult.model_validate(
            payload | {"change_package": None, "rollback_point": None}
        )

    abstained = M2607ChangeControlService().control(
        request.model_copy(
            update={
                "revalidations": (
                    *request.revalidations,
                    request.revalidations[0].model_copy(
                        update={"revalidation_id": "revalidation.extra", "passed": False}
                    ),
                )
            }
        )
    )
    with pytest.raises(ValidationError, match="no package"):
        ProteinSubtypeChangeControlResult.model_validate(
            abstained.model_dump(mode="python") | {"change_package": result.change_package}
        )
    with pytest.raises(ValidationError, match="result digest"):
        ProteinSubtypeChangeControlResult.model_validate(
            payload | {"result_digest": "sha256:" + "f" * 64}
        )
    assert normalized_request(request) == request.model_dump(mode="json")
    assert canonical_request_digest(request).startswith("sha256:")


def test_public_engine_entry_points_and_replay_are_covered() -> None:
    request = _request()
    engine = M2607ChangeControlEngine()
    result = engine.control(request)

    assert engine.verify(result) == result
