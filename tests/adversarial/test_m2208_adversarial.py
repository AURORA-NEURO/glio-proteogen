"""Adversarial boundary and tamper tests for M22-08."""

import json
from http import HTTPStatus
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m22_08 import (
    AdjudicateProteinRnaDiscordanceEvidenceGateRequest,
    ApprovalDecision,
    BenchmarkOutcome,
    GateConfiguration,
    GateFinding,
    GateFindingCode,
    GateRunStatus,
    ProteinRnaDiscordanceEvidenceGateResult,
    RequirementCategory,
    RiskSeverity,
    SignedReleaseRecord,
    result_identifier,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.kernel.strict_json import StrictJsonError, StrictJsonErrorCode
from glio_proteogen.modules.c21_reference_material.m22_08_evidence_gate_release_adjudicator import (
    EvidenceGateSubmission,
    M2208AuthorizationError,
    M2208EvidenceGateEngine,
    M2208Plugin,
    M2208Service,
    adjudicate_protein_rna_discordance_evidence_gate,
)
from glio_proteogen.modules.c21_reference_material.m22_08_evidence_gate_release_adjudicator import (
    api as m2208_api,
)
from glio_proteogen.modules.c21_reference_material.m22_08_evidence_gate_release_adjudicator import (
    cli as m2208_cli,
)
from tests.contract.test_m2208_contract import (
    _evidence,
    _release_record,
    _request,
    _result,
)


def test_plugin_rejects_duplicate_json_keys_before_contract_parse() -> None:
    plugin = M2208Plugin(M2208Service())
    duplicate = b'{"request_id":"first","request_id":"second"}'
    with pytest.raises(StrictJsonError) as error:
        plugin.validate(EvidenceGateSubmission(duplicate))
    assert error.value.code is StrictJsonErrorCode.DUPLICATE_KEY


def test_plugin_rejects_unwrapped_submission_and_unvalidated_token() -> None:
    plugin = M2208Plugin(M2208Service())
    with pytest.raises(TypeError, match="submission"):
        plugin.validate(_request())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_service_fails_closed_on_unknown_control_mapping() -> None:
    service = M2208Service()
    with pytest.raises(M2208AuthorizationError):
        service.validate_request({"context": {"references": {}}})


def test_contract_rejects_duplicate_requirement_id_and_unlocked_config() -> None:
    request = _request()
    duplicate = request.requirements[0].model_copy(
        update={"category": RequirementCategory.TRACEABILITY}
    )
    payload = request.model_dump(mode="python")
    payload["requirements"] = (*request.requirements[:-1], duplicate)
    with pytest.raises(ValidationError, match="identifiers"):
        AdjudicateProteinRnaDiscordanceEvidenceGateRequest.model_validate(payload)

    with pytest.raises(ValidationError):
        GateConfiguration(
            configuration_id="configuration-unlocked",
            version="1.0.0",
            locked=False,  # type: ignore[arg-type]
            evidence=(_evidence("config-unlocked"),),
        )


def test_contract_rejects_source_artifact_digest_substitution() -> None:
    request = _request()
    substituted = request.source_artifacts[0].model_copy(update={"digest": "sha256:" + "f" * 64})
    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = (substituted, *request.source_artifacts[1:])
    with pytest.raises(ValidationError, match="bind every declared input"):
        AdjudicateProteinRnaDiscordanceEvidenceGateRequest.model_validate(payload)


def test_api_replay_rejects_nonobject_and_tampered_result() -> None:
    request = _request()
    client = TestClient(m2208_api.create_app())
    response = client.post("/v1/modules/M22-08/verify", json=["not-an-object"])
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    result = client.post(
        "/v1/modules/M22-08/adjudicate",
        content=request.model_dump_json(),
        headers={"content-type": "application/json"},
    ).json()
    result["result_digest"] = "sha256:" + "f" * 64
    tampered = client.post("/v1/modules/M22-08/verify", json=result)
    assert tampered.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "replay envelope" in tampered.text


def test_api_rejects_duplicate_key_without_echoing_payload() -> None:
    client = TestClient(m2208_api.create_app())
    response = client.post(
        "/v1/modules/M22-08/validate",
        content=b'{"request_id":"a","request_id":"sensitive-second"}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "sensitive-second" not in response.text


def test_cli_unknown_schema_and_missing_input_are_sanitized(tmp_path: object) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m2208_cli.app, ["export-schema", "unknown"])
    assert unknown.exit_code != 0
    assert "unknown M22-08 contract" in unknown.output
    missing = runner.invoke(m2208_cli.app, ["validate", str(tmp_path) + "\\missing.json"])
    assert missing.exit_code != 0


def test_json_result_is_deterministic_across_service_boundaries() -> None:
    request = _request()
    service = M2208Service()
    first = service.adjudicate(request.model_dump_json())
    second = service.adjudicate(json.dumps(request.model_dump(mode="json"), sort_keys=True))
    assert first == second


def test_public_entry_point_and_preflight_hostile_mapping_fail_closed() -> None:
    request = _request()
    assert (
        adjudicate_protein_rna_discordance_evidence_gate(request).result_digest
        == M2208EvidenceGateEngine().adjudicate(request).result_digest
    )

    class BrokenMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError from None

    with pytest.raises(M2208AuthorizationError):
        M2208Service().validate_request(BrokenMapping())


def test_plugin_descriptor_and_replay_boundary() -> None:
    service = M2208Service()
    plugin = M2208Plugin(service)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M22-08"
    result = service.adjudicate(_request())
    assert plugin.replay(result) == result


def test_cli_schema_output_and_read_validation_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    output = tmp_path / "schema.json"
    exported = runner.invoke(
        m2208_cli.app,
        ["export-schema", "request", "--output", str(output)],
    )
    assert exported.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["$id"].endswith(":request")
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_text("{not-json", encoding="utf-8")
    invalid = runner.invoke(m2208_cli.app, ["validate", str(bad_request)])
    assert invalid.exit_code != 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_text("{}", encoding="utf-8")
    invalid_result = runner.invoke(m2208_cli.app, ["verify", str(bad_result)])
    assert invalid_result.exit_code != 0


def test_api_auth_and_json_parse_errors_are_sanitized() -> None:
    request = _request()
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "consent": request.context.references.consent.model_copy(
                        update={"state": "revoked"}
                    )
                }
            )
        }
    )
    denied = request.model_copy(update={"context": denied_context})
    client = TestClient(m2208_api.create_app())
    for route in ("validate", "adjudicate"):
        response = client.post(
            f"/v1/modules/M22-08/{route}",
            content=denied.model_dump_json(),
            headers={"content-type": "application/json"},
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    malformed = client.post("/v1/modules/M22-08/verify", content=b"not-json")
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_signed_record_closure_rejects_each_invalid_pass_condition() -> None:
    request = _request()
    record_payload = _release_record(request).model_dump(mode="python")
    cases = (
        (
            request.requirements[0].model_copy(
                update={"requirement_id": request.requirements[1].requirement_id}
            ),
            *request.requirements[1:],
        ),
        request.requirements[:-1],
    )
    for requirements in cases:
        candidate = dict(record_payload)
        candidate["requirements"] = requirements
        with pytest.raises(ValidationError):
            SignedReleaseRecord.model_validate(candidate)
    unsatisfied = request.requirements[0].model_copy(update={"satisfied": False})
    candidate = dict(record_payload)
    candidate["requirements"] = (unsatisfied, *request.requirements[1:])
    with pytest.raises(ValidationError, match="unsatisfied"):
        SignedReleaseRecord.model_validate(candidate)
    original_benchmark = request.benchmarks[0]
    failed_benchmark = BenchmarkOutcome(
        benchmark_id=original_benchmark.benchmark_id,
        name=original_benchmark.name,
        metric_name=original_benchmark.metric_name,
        observed_value=0.2,
        required_floor=0.95,
        passed=False,
        report_artifact=original_benchmark.report_artifact,
        evidence=original_benchmark.evidence,
    )
    candidate = dict(record_payload)
    candidate["benchmarks"] = (failed_benchmark,)
    with pytest.raises(ValidationError, match="failed benchmarks"):
        SignedReleaseRecord.model_validate(candidate)
    open_critical = request.residual_risks[0].model_copy(
        update={"severity": RiskSeverity.CRITICAL, "accepted": False}
    )
    candidate = dict(record_payload)
    candidate["residual_risks"] = (open_critical,)
    with pytest.raises(ValidationError, match="critical risk"):
        SignedReleaseRecord.model_validate(candidate)
    deferred = request.approvals[0].model_copy(update={"decision": ApprovalDecision.DEFER})
    candidate = dict(record_payload)
    candidate["approvals"] = (deferred,)
    with pytest.raises(ValidationError, match="approval records"):
        SignedReleaseRecord.model_validate(candidate)


def test_result_closure_rejects_tampered_request_record_and_abstention() -> None:
    request = _request()
    result = _result(
        request,
        status=GateRunStatus.ADJUDICATED,
        support_status=SupportStatus.SUPPORTED,
        release_record=_release_record(request),
    )
    assert result.release_record is not None
    release_record = result.release_record
    cases = (
        {"request_digest": "sha256:" + "0" * 64},
        {"support_decision": result.support_decision.model_copy(update={"status": "unsupported"})},
        {
            "findings": (
                GateFinding(
                    finding_id="finding-empty",
                    code=GateFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                    message="missing evidence",
                ),
            )
        },
        {
            "release_record": release_record.model_copy(
                update={
                    "requirements": (
                        request.requirements[0].model_copy(update={"statement": "changed"}),
                        *request.requirements[1:],
                    )
                }
            )
        },
    )
    for update in cases:
        candidate = result.model_copy(update=update)
        with pytest.raises(ValidationError):
            ProteinRnaDiscordanceEvidenceGateResult.model_validate(
                candidate.model_dump(mode="python")
            )
    abstained = result.model_copy(
        update={
            "status": GateRunStatus.ABSTAINED,
            "release_record": None,
            "abstention_reason": "review required",
            "support_decision": result.support_decision.model_copy(
                update={"status": "unsupported"}
            ),
            "result_id": result_identifier(result.request_digest),
        }
    )
    with pytest.raises(ValidationError):
        ProteinRnaDiscordanceEvidenceGateResult.model_validate(abstained.model_dump(mode="python"))
