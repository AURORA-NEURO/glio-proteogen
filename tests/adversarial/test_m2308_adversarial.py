"""Adversarial boundary and replay tests for M23-08."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m23_08 import (
    AdjudicateVariantPeptideEvidenceGateRequest,
    ApprovalDecision,
    BenchmarkOutcome,
    GateConfiguration,
    GateFinding,
    GateFindingCode,
    GateRunStatus,
    RequirementCategory,
    RiskSeverity,
    SignedReleaseRecord,
    VariantPeptideEvidenceGateResult,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.models import ConsentState, SupportStatus
from glio_proteogen.kernel.strict_json import StrictJsonError, StrictJsonErrorCode
from glio_proteogen.modules.c21_reference_material.m23_08_evidence_gate_release_adjudicator import (
    EvidenceGateSubmission,
    M2308AuthorizationError,
    M2308EvidenceGateEngine,
    M2308Plugin,
    M2308ReplayError,
    M2308Service,
    M2308TokenError,
    adjudicate_variant_peptide_evidence_gate,
)
from glio_proteogen.modules.c21_reference_material.m23_08_evidence_gate_release_adjudicator import (
    api as m2308_api,
)
from glio_proteogen.modules.c21_reference_material.m23_08_evidence_gate_release_adjudicator import (
    cli as m2308_cli,
)
from tests.contract.test_m2308_deep import _evidence, _request

if TYPE_CHECKING:
    from pathlib import Path


def _self_rehashed(
    result: VariantPeptideEvidenceGateResult,
    **updates: Any,
) -> VariantPeptideEvidenceGateResult:
    """Forge a valid-looking result whose digest covers attacker changes."""

    forged = result.model_copy(update=updates)
    return forged.model_copy(update={"result_digest": result_payload_digest(forged)})


def test_plugin_rejects_duplicate_json_keys_before_contract_parse() -> None:
    plugin = M2308Plugin(M2308Service())
    duplicate = b'{"request_id":"first","request_id":"second"}'
    with pytest.raises(StrictJsonError) as error:
        plugin.validate(EvidenceGateSubmission(duplicate))
    assert error.value.code is StrictJsonErrorCode.DUPLICATE_KEY


def test_plugin_rejects_unwrapped_submission_and_unvalidated_token() -> None:
    plugin = M2308Plugin(M2308Service())
    with pytest.raises(M2308TokenError):
        plugin.validate(_request())  # type: ignore[arg-type]
    with pytest.raises(M2308TokenError):
        plugin.run(object())  # type: ignore[arg-type]


def test_service_fails_closed_on_unknown_control_mapping() -> None:
    with pytest.raises(M2308AuthorizationError):
        M2308Service().validate_request({"context": {"references": {}}})


def test_contract_rejects_duplicate_requirement_id_and_unlocked_config() -> None:
    request = _request()
    duplicate = request.requirements[0].model_copy(
        update={"category": RequirementCategory.TRACEABILITY}
    )
    payload = request.model_dump(mode="python")
    payload["requirements"] = (*request.requirements[:-1], duplicate)
    with pytest.raises(ValidationError, match="identifiers"):
        AdjudicateVariantPeptideEvidenceGateRequest.model_validate(payload)

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
        AdjudicateVariantPeptideEvidenceGateRequest.model_validate(payload)
    duplicate_payload = request.model_dump(mode="python")
    duplicate_payload["source_artifacts"] = (
        request.source_artifacts[0],
        request.source_artifacts[0],
        *request.source_artifacts[2:],
    )
    with pytest.raises(ValidationError, match="unique artifact IDs"):
        AdjudicateVariantPeptideEvidenceGateRequest.model_validate(duplicate_payload)


def test_api_replay_rejects_nonobject_and_tampered_result() -> None:
    request = _request()
    client = TestClient(m2308_api.create_app())
    response = client.post("/v1/modules/M23-08/verify", json=["not-an-object"])
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    result = client.post(
        "/v1/modules/M23-08/adjudicate",
        content=request.model_dump_json(),
        headers={"content-type": "application/json"},
    ).json()
    result["result_digest"] = "sha256:" + "f" * 64
    tampered = client.post("/v1/modules/M23-08/verify", json=result)
    assert tampered.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "replay envelope" in tampered.text


def test_api_rejects_duplicate_key_without_echoing_payload() -> None:
    client = TestClient(m2308_api.create_app())
    response = client.post(
        "/v1/modules/M23-08/validate",
        content=b'{"request_id":"a","request_id":"sensitive-second"}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "sensitive-second" not in response.text


def test_cli_unknown_schema_and_missing_input_are_sanitized(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m2308_cli.app, ["export-schema", "unknown"])
    assert unknown.exit_code != 0
    assert "unknown M23-08 contract" in unknown.output
    missing = runner.invoke(m2308_cli.app, ["validate", str(tmp_path / "missing.json")])
    assert missing.exit_code != 0


def test_json_result_is_deterministic_across_service_boundaries() -> None:
    request = _request()
    service = M2308Service()
    first = service.adjudicate(request.model_dump_json())
    second = service.adjudicate(json.dumps(request.model_dump(mode="json"), sort_keys=True))
    assert first == second


def test_public_entry_point_and_preflight_hostile_mapping_fail_closed() -> None:
    request = _request()
    assert (
        adjudicate_variant_peptide_evidence_gate(request).result_digest
        == M2308EvidenceGateEngine().adjudicate(request).result_digest
    )

    class BrokenMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError from None

    with pytest.raises(M2308AuthorizationError):
        M2308Service().validate_request(BrokenMapping())


def test_plugin_descriptor_and_replay_boundary() -> None:
    service = M2308Service()
    plugin = M2308Plugin(service)
    assert plugin.descriptor.module_id == "GLIO-PROTEOGEN-M23-08"
    assert plugin.descriptor.unsupported_to_negative is False
    assert plugin.descriptor.kinase_activity is False
    result = service.adjudicate(_request())
    assert plugin.validate(EvidenceGateSubmission(_request())).request.request_id == (
        "m2308.request.1"
    )
    assert plugin.replay(result) == result


def test_replay_rejects_self_rehashed_release_record_mutation() -> None:
    service = M2308Service()
    result = service.adjudicate(_request())
    assert result.release_record is not None
    release_record = result.release_record.model_copy(
        update={"signature_digest": "sha256:" + "f" * 64}
    )
    tampered = _self_rehashed(result, release_record=release_record)

    with pytest.raises(M2308ReplayError):
        service.replay(tampered)


def test_strict_result_validation_rejects_self_rehashed_signature_mutation() -> None:
    result = M2308EvidenceGateEngine().adjudicate(_request())
    assert result.release_record is not None
    release_record = result.release_record.model_copy(
        update={"signature_digest": "sha256:" + "f" * 64}
    )
    forged = _self_rehashed(result, release_record=release_record)

    with pytest.raises(ValidationError, match="signature digest"):
        type(result).model_validate(forged.model_dump(mode="python"), strict=True)


def test_replay_rejects_self_rehashed_finding_and_evidence_mutations() -> None:
    service = M2308Service()
    result = service.adjudicate(_request())
    finding = result.findings[0].model_copy(update={"message": "forged gate message"})
    finding_tampered = _self_rehashed(result, findings=(finding, *result.findings[1:]))
    evidence = result.evidence[0].model_copy(update={"claim": "forged evidence claim"})
    evidence_tampered = _self_rehashed(result, evidence=(evidence, *result.evidence[1:]))

    with pytest.raises(M2308ReplayError):
        service.replay(finding_tampered)
    with pytest.raises(M2308ReplayError):
        service.replay(evidence_tampered)


def test_plugin_rejects_self_rehashed_provenance_mutation() -> None:
    service = M2308Service()
    result = service.adjudicate(_request())
    tampered = _self_rehashed(
        result,
        provenance=result.provenance.model_copy(update={"activity_id": "forged-activity"}),
    )

    with pytest.raises(M2308ReplayError):
        M2308Plugin(service).replay(tampered)


def test_cli_schema_output_and_read_validation_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    output = tmp_path / "schema.json"
    exported = runner.invoke(
        m2308_cli.app,
        ["export-schema", "request", "--output", str(output)],
    )
    assert exported.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["$id"].endswith(":request")
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_text("{not-json", encoding="utf-8")
    invalid = runner.invoke(m2308_cli.app, ["validate", str(bad_request)])
    assert invalid.exit_code != 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_text("{}", encoding="utf-8")
    invalid_result = runner.invoke(m2308_cli.app, ["verify", str(bad_result)])
    assert invalid_result.exit_code != 0


def test_api_auth_and_json_parse_errors_are_sanitized() -> None:
    request = _request()
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "consent": request.context.references.consent.model_copy(
                        update={"state": ConsentState.WITHHELD}
                    )
                }
            )
        }
    )
    denied = request.model_copy(update={"context": denied_context})
    client = TestClient(m2308_api.create_app())
    for route in ("validate", "adjudicate"):
        response = client.post(
            f"/v1/modules/M23-08/{route}",
            content=denied.model_dump_json(),
            headers={"content-type": "application/json"},
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    malformed = client.post("/v1/modules/M23-08/verify", content=b"not-json")
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_signed_record_closure_rejects_each_invalid_pass_condition() -> None:
    result = M2308EvidenceGateEngine().adjudicate(_request())
    assert result.release_record is not None
    record_payload = result.release_record.model_dump(mode="python")
    duplicate = dict(record_payload)
    duplicate["requirements"] = (
        result.request.requirements[0].model_copy(
            update={"requirement_id": result.request.requirements[1].requirement_id}
        ),
        *result.request.requirements[1:],
    )
    with pytest.raises(ValidationError, match="identifiers"):
        SignedReleaseRecord.model_validate(duplicate)

    unsatisfied = result.request.requirements[0].model_copy(update={"satisfied": False})
    candidate = dict(record_payload)
    candidate["requirements"] = (unsatisfied, *result.request.requirements[1:])
    with pytest.raises(ValidationError, match="unsatisfied"):
        SignedReleaseRecord.model_validate(candidate)

    original = result.request.benchmarks[0]
    failed_benchmark = BenchmarkOutcome(
        benchmark_id=original.benchmark_id,
        name=original.name,
        metric_name=original.metric_name,
        observed_value=0.2,
        required_floor=0.95,
        passed=False,
        report_artifact=original.report_artifact,
        evidence=original.evidence,
    )
    candidate = dict(record_payload)
    candidate["benchmarks"] = (failed_benchmark,)
    with pytest.raises(ValidationError, match="failed benchmarks"):
        SignedReleaseRecord.model_validate(candidate)

    open_critical = result.request.residual_risks[0].model_copy(
        update={"severity": RiskSeverity.CRITICAL, "accepted": False}
    )
    candidate = dict(record_payload)
    candidate["residual_risks"] = (open_critical,)
    with pytest.raises(ValidationError, match="critical risk"):
        SignedReleaseRecord.model_validate(candidate)

    deferred = result.request.approvals[0].model_copy(update={"decision": ApprovalDecision.DEFER})
    candidate = dict(record_payload)
    candidate["approvals"] = (deferred,)
    with pytest.raises(ValidationError, match="approval records"):
        SignedReleaseRecord.model_validate(candidate)


def test_result_closure_rejects_tampered_request_record_and_finding() -> None:
    result = M2308EvidenceGateEngine().adjudicate(_request())
    release_record = result.release_record
    assert release_record is not None
    cases = (
        {"request_digest": "sha256:" + "0" * 64},
        {
            "support_decision": result.support_decision.model_copy(
                update={"status": SupportStatus.UNSUPPORTED}
            )
        },
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
                        result.request.requirements[0].model_copy(update={"statement": "changed"}),
                        *result.request.requirements[1:],
                    )
                }
            )
        },
    )
    for update in cases:
        candidate = result.model_copy(update=update)
        with pytest.raises(ValidationError):
            type(result).model_validate(candidate.model_dump(mode="python"))
    for field, value in (
        (
            "benchmarks",
            (result.request.benchmarks[0].model_copy(update={"name": "changed"}),),
        ),
        (
            "residual_risks",
            (result.request.residual_risks[0].model_copy(update={"statement": "changed"}),),
        ),
        (
            "approvals",
            (result.request.approvals[0].model_copy(update={"role": "changed"}),),
        ),
        (
            "post_release_obligations",
            (result.request.post_release_obligations[0].model_copy(update={"action": "changed"}),),
        ),
    ):
        replacement = release_record.model_copy(update={field: value})
        candidate = result.model_copy(update={"release_record": replacement})
        with pytest.raises(ValidationError):
            type(result).model_validate(candidate.model_dump(mode="python"))
    abstained = result.model_copy(
        update={
            "status": GateRunStatus.ABSTAINED,
            "release_record": None,
            "abstention_reason": "review required",
            "support_decision": result.support_decision.model_copy(
                update={"status": SupportStatus.UNSUPPORTED}
            ),
            "result_id": result_identifier(result.request_digest),
        }
    )
    with pytest.raises(ValidationError):
        type(result).model_validate(abstained.model_dump(mode="python"))
    no_record = result.model_copy(
        update={
            "status": GateRunStatus.ABSTAINED,
            "release_record": None,
            "abstention_reason": "review required",
            "support_decision": result.support_decision.model_copy(
                update={"status": SupportStatus.UNSUPPORTED}
            ),
            "findings": (),
        }
    )
    with pytest.raises(ValidationError):
        type(result).model_validate(no_record.model_dump(mode="python"))


def test_control_states_do_not_become_negative_biological_findings() -> None:
    request = _request(satisfied=False)
    result = M2308EvidenceGateEngine().adjudicate(request)
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert all(item.code is not GateFindingCode.UPSTREAM_UNSUPPORTED for item in result.findings)
    assert result.limitations
    assert canonical_request_digest(result.request) == result.request_digest
    assert canonical_request_digest(result.request.model_dump(mode="json")) == result.request_digest


def test_replay_checks_each_digest_identifier_and_recomputed_result() -> None:
    engine = M2308EvidenceGateEngine()
    result = engine.adjudicate(_request())
    cases = (
        result.model_copy(update={"request_digest": "sha256:" + "0" * 64}),
        result.model_copy(update={"result_id": "gate.m2308.forged"}),
        result.model_copy(update={"result_digest": "sha256:" + "f" * 64}),
    )
    for candidate in cases:
        with pytest.raises(M2308ReplayError):
            engine.replay(candidate)

    other_request = _request(request_id="m2308.request.other")
    changed = result.model_copy(
        update={
            "request": other_request,
            "request_digest": canonical_request_digest(other_request),
            "result_id": result_identifier(canonical_request_digest(other_request)),
        }
    )
    changed = changed.model_copy(update={"result_digest": result_payload_digest(changed)})
    with pytest.raises(M2308ReplayError):
        engine.replay(changed)


def test_service_replays_json_bytes_and_canonical_dicts() -> None:
    service = M2308Service()
    result = service.adjudicate(_request())
    assert service.replay(result.model_dump_json()) == result
    assert service.replay(result.model_dump(mode="json")) == result


def test_individual_schema_route_and_cli_stdout_adjudication(tmp_path: Path) -> None:
    client = TestClient(m2308_api.create_app())
    schema = client.get("/v1/modules/M23-08/schemas/request")
    assert schema.status_code == HTTPStatus.OK
    assert schema.json()["$id"].endswith(":request")

    path = tmp_path / "m2308-adversarial-request.json"
    path.write_text(_request().model_dump_json(), encoding="utf-8")
    response = CliRunner().invoke(m2308_cli.app, ["adjudicate", str(path)])
    assert response.exit_code == 0
    assert json.loads(response.stdout)["parent_target"] == "variant peptide"
