"""Deep contract, runtime, interface, replay, and adversarial M16-04 coverage."""

# ruff: noqa: E501, ARG005, PLR2004, TC003, TRY003

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from evals.m16_04.run import _policy, build_scenario_request, run_evaluator
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.modules.c16_protein_rna_discordance.m16_04_intended_use_adapter.engine as engine_module
from glio_proteogen.adapters.m1604 import app, m1604_app
from glio_proteogen.contracts.m16_04 import (
    AdapterStatus,
    ClaimCeiling,
    DisplaySemantic,
    EvidenceTier,
    IntendedUseAudience,
    IntendedUseContext,
    IntendedUsePolicy,
    PolicyDecision,
    PolicyDecisionStatus,
    ProteinRnaDiscordanceIntendedUseResult,
    contract_json_schema,
    contract_json_schemas,
    result_payload_digest,
)
from glio_proteogen.contracts.m16_04.canonical import normalized_request
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c16_protein_rna_discordance.m16_04_intended_use_adapter import (
    M1604AuthorizationError,
    M1604IntendedUseAdapterEngine,
    M1604Plugin,
    M1604ReplayVerificationError,
    M1604Service,
    ValidatedM1604Request,
    adapt_protein_rna_discordance_intended_use,
    preflight_m1604_authorization,
)


def test_schema_metadata_and_unknown_schema_are_closed() -> None:
    schemas = contract_json_schemas()
    assert set(schemas) == {
        "request",
        "output",
        "policy",
        "intended-use-object",
        "policy-decision",
        "configuration",
        "finding",
    }
    assert all(cast("dict[str, object]", item["x-glio-contract"])["provisionalAbi"] for item in schemas.values())
    assert cast("dict[str, object]", schemas["output"]["x-glio-contract"])["registeredIntendedUseRequired"] is True
    with pytest.raises(KeyError):
        contract_json_schema("unknown")  # type: ignore[arg-type]


def test_policy_and_object_closures_reject_unsafe_combinations() -> None:
    with pytest.raises(ValueError, match="unique"):
        _policy(permitted=("same", "same"))
    with pytest.raises(ValueError, match="disjoint"):
        _policy(permitted=("Do not infer kinase activity.",))
    with pytest.raises(ValueError, match="clinical review"):
        IntendedUsePolicy.model_validate(
            _policy().model_dump(mode="python")
            | {
                "context": IntendedUseContext.CLINICAL_REVIEW,
                "audience": IntendedUseAudience.SCIENTIFIC_REVIEWER,
            },
            strict=True,
        )
    with pytest.raises(ValueError, match="hidden display"):
        IntendedUsePolicy.model_validate(
            _policy().model_dump(mode="python") | {"display_semantic": DisplaySemantic.HIDDEN},
            strict=True,
        )
    decision = PolicyDecision(
        decision_id="decision.x",
        status=PolicyDecisionStatus.QUALIFIED,
        policy_id="policy.x",
        reasons=("qualified",),
    )
    assert decision.auditable


def test_runtime_adapts_and_preserves_parent_boundary() -> None:
    result = M1604IntendedUseAdapterEngine().infer(build_scenario_request())
    assert result.status is AdapterStatus.ADAPTED
    assert result.intended_use_object is not None
    assert result.parent_target == "protein_rna_discordance"
    assert result.emits_parent is False
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M16-04"
    assert result.uncertainty.transport.probability == 0.9


def test_qualified_and_abstained_policies_are_explicit() -> None:
    engine = M1604IntendedUseAdapterEngine()
    qualified = engine.infer(
        build_scenario_request(policy=_policy(tier=EvidenceTier.EXPLORATORY))
    )
    assert qualified.status is AdapterStatus.ADAPTED
    assert qualified.policy_decision.status is PolicyDecisionStatus.QUALIFIED
    blocked = engine.infer(
        build_scenario_request(policy=_policy(permitted=("Recommend treatment.",)))
    )
    assert blocked.status is AdapterStatus.ABSTAINED
    assert blocked.intended_use_object is None
    assert blocked.human_review_required
    assert blocked.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_request_and_result_closures_reject_tamper() -> None:
    result = M1604IntendedUseAdapterEngine().infer(build_scenario_request())
    payload = result.model_dump(mode="python")
    payload["request_digest"] = "sha256:" + "0" * 64
    payload["result_digest"] = result_payload_digest(
        ProteinRnaDiscordanceIntendedUseResult.model_construct(**payload)
    )
    with pytest.raises(ValueError, match="request digest"):
        ProteinRnaDiscordanceIntendedUseResult.model_validate(payload, strict=True)
    payload = result.model_dump(mode="python")
    payload["status"] = AdapterStatus.ABSTAINED
    payload["intended_use_object"] = None
    payload["abstention_reason"] = "review"
    payload["policy_decision"] = result.policy_decision.model_copy(
        update={"status": PolicyDecisionStatus.BLOCKED}
    )
    payload["support_decision"] = result.support_decision.model_copy(
        update={"status": SupportStatus.REVIEW_REQUIRED}
    )
    payload["human_review_required"] = True
    payload["result_digest"] = result_payload_digest(
        ProteinRnaDiscordanceIntendedUseResult.model_construct(**payload)
    )
    abstained = ProteinRnaDiscordanceIntendedUseResult.model_validate(payload, strict=True)
    assert abstained.status is AdapterStatus.ABSTAINED


def test_authorization_precedes_hostile_traversal() -> None:
    with pytest.raises(M1604AuthorizationError):
        M1604IntendedUseAdapterEngine().infer(build_scenario_request(accepted=False))

    class Exploding:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile traversal")

    with pytest.raises(M1604AuthorizationError):
        preflight_m1604_authorization(Exploding())


def test_replay_and_plugin_service_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = M1604IntendedUseAdapterEngine()
    request = build_scenario_request()
    result = engine.infer(request)
    assert engine.verify(result) == result
    assert engine.verify(result, replay=False) == result
    with pytest.raises(M1604ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    monkeypatch.setattr(engine_module, "result_payload_digest", lambda value: "sha256:" + "e" * 64)
    with pytest.raises(M1604ReplayVerificationError):
        engine.verify(result)
    monkeypatch.undo()
    service = M1604Service()
    plugin = M1604Plugin(service)
    token = plugin.validate(request)
    assert plugin.run(token).model_dump(mode="json") == service.execute(token.request).model_dump(mode="json")
    with pytest.raises(TypeError):
        plugin.run(cast("ValidatedM1604Request", request))
    json_token = plugin.validate(canonical_json_bytes(request))
    assert plugin.run(json_token).status is AdapterStatus.ADAPTED
    assert plugin.verify(result).status is AdapterStatus.ADAPTED
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M16-04"
    assert adapt_protein_rna_discordance_intended_use(request).status is AdapterStatus.ADAPTED


def test_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == report["executed_cases"] == 6


def test_fastapi_interfaces_and_sanitized_errors() -> None:
    client = TestClient(app)
    assert client.get("/v1/m16-04/schema/request").status_code == 200
    assert client.get("/v1/m16-04/schema/unknown").status_code == 404
    request_payload = build_scenario_request().model_dump(mode="json")
    response = client.post("/v1/modules/M16-04/adapt", json=request_payload)
    assert response.status_code == 200
    assert client.post("/v1/modules/M16-04/verify", json=response.json()).status_code == 200
    assert client.post(
        "/v1/modules/M16-04/adapt",
        json=build_scenario_request(accepted=False).model_dump(mode="json"),
    ).status_code == 403
    assert client.post(
        "/v1/modules/M16-04/adapt", content=b"{", headers={"content-type": "application/json"}
    ).status_code == 422
    invalid_payload = dict(request_payload)
    invalid_payload.pop("policy")
    assert client.post("/v1/modules/M16-04/adapt", json=invalid_payload).status_code == 422
    assert client.post(
        "/v1/modules/M16-04/adapt", content=b"{}", headers={"content-type": "text/plain"}
    ).status_code == 415
    assert client.post("/v1/modules/M16-04/verify", json={}).status_code == 422
    assert client.post(
        "/v1/modules/M16-04/verify", content=b"{}", headers={"content-type": "text/plain"}
    ).status_code == 415


def test_cli_adapt_verify_schema_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    assert runner.invoke(m1604_app, ["export-schema", "output"]).exit_code == 0
    assert runner.invoke(m1604_app, ["export-schema", "unknown"]).exit_code != 0
    assert runner.invoke(
        m1604_app, ["adapt", str(request_path), "--output", str(output_path)]
    ).exit_code == 0
    assert runner.invoke(
        m1604_app, ["adapt", str(request_path), "--output", str(output_path)]
    ).exit_code != 0
    assert runner.invoke(m1604_app, ["adapt", str(request_path)]).exit_code == 0
    assert runner.invoke(m1604_app, ["verify", str(output_path)]).exit_code == 0
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    assert runner.invoke(m1604_app, ["verify", str(bad)]).exit_code != 0


def test_adversarial_policy_and_object_validator_branches() -> None:
    base = _policy().model_dump(mode="python")
    duplicate_prohibited = dict(base)
    duplicate_prohibited["prohibited_claims"] = ("same", "same")
    with pytest.raises(ValueError, match="prohibited claims"):
        IntendedUsePolicy.model_validate(duplicate_prohibited, strict=True)
    clinical_exploratory = dict(base)
    clinical_exploratory.update(
        context=IntendedUseContext.CLINICAL_REVIEW,
        audience=IntendedUseAudience.CLINICAL_REVIEWER,
        minimum_evidence_tier=EvidenceTier.EXPLORATORY,
    )
    with pytest.raises(ValueError, match="clinical review"):
        IntendedUsePolicy.model_validate(clinical_exploratory, strict=True)
    mechanism_exploratory = dict(base)
    mechanism_exploratory.update(
        maximum_claim_ceiling=ClaimCeiling.SUPPORTED_MECHANISM,
        minimum_evidence_tier=EvidenceTier.EXPLORATORY,
    )
    with pytest.raises(ValueError, match="supported mechanism"):
        IntendedUsePolicy.model_validate(mechanism_exploratory, strict=True)
    with pytest.raises(ValueError, match="allowed policy"):
        PolicyDecision(
            decision_id="decision.allowed",
            status=PolicyDecisionStatus.ALLOWED,
            policy_id="policy.allowed",
            reasons=("allowed",),
        )
    with pytest.raises(ValueError, match="blocked or abstained"):
        PolicyDecision(
            decision_id="decision.blocked",
            status=PolicyDecisionStatus.BLOCKED,
            policy_id="policy.blocked",
            reasons=(),
        )
    object_value = M1604IntendedUseAdapterEngine().infer(build_scenario_request()).intended_use_object
    assert object_value is not None
    object_data = object_value.model_dump(mode="python")
    object_data["claim_ceiling"] = ClaimCeiling.ABSTAIN
    with pytest.raises(ValueError, match="cannot be allowed"):
        type(object_value).model_validate(object_data, strict=True)
    for field, message in (
        ("permitted_claims", "object permitted claims"),
        ("blocked_claims", "object blocked claims"),
    ):
        duplicate = object_value.model_dump(mode="python")
        duplicate[field] = ("same", "same")
        with pytest.raises(ValueError, match=message):
            type(object_value).model_validate(duplicate, strict=True)
    overlap = object_value.model_dump(mode="python")
    overlap["permitted_claims"] = ("overlap",)
    overlap["blocked_claims"] = ("overlap",)
    with pytest.raises(ValueError, match="disjoint"):
        type(object_value).model_validate(overlap, strict=True)


def test_adversarial_request_result_and_adapter_error_branches(tmp_path: Path) -> None:
    request = build_scenario_request()
    bad_request = request.model_dump(mode="python")
    bad_request["upstream_resolution_result"] = request.source_artifacts[0]
    with pytest.raises(ValueError, match="bind the provisional"):
        type(request).model_validate(bad_request, strict=True)
    engine = M1604IntendedUseAdapterEngine()
    adapted = engine.infer(request)

    def validate_payload(payload: dict[str, Any], message: str) -> None:
        payload["result_digest"] = result_payload_digest(
            ProteinRnaDiscordanceIntendedUseResult.model_construct(**payload)
        )
        with pytest.raises(ValueError, match=message):
            ProteinRnaDiscordanceIntendedUseResult.model_validate(payload, strict=True)

    payload = adapted.model_dump(mode="python")
    payload["intended_use_object"] = None
    validate_payload(payload, "adapted result")
    payload = adapted.model_dump(mode="python")
    payload["human_review_required"] = True
    validate_payload(payload, "evidence and no mandatory review")
    blocked = engine.infer(build_scenario_request(policy=_policy(permitted=("Recommend treatment.",))))
    payload = blocked.model_dump(mode="python")
    payload["intended_use_object"] = adapted.intended_use_object
    validate_payload(payload, "abstained result")
    payload = blocked.model_dump(mode="python")
    payload["human_review_required"] = False
    validate_payload(payload, "human review")
    payload = blocked.model_dump(mode="python")
    payload["findings"] = blocked.findings + blocked.findings
    validate_payload(payload, "unique identifiers")
    with pytest.raises(M1604ReplayVerificationError):
        engine.verify({})
    assert normalized_request({"a": 1}) == {"a": 1}
    runner = CliRunner()
    bad_request_path = tmp_path / "bad-request.json"
    bad_request_path.write_text("{}", encoding="utf-8")
    assert runner.invoke(m1604_app, ["adapt", str(bad_request_path)]).exit_code != 0
    assert runner.invoke(m1604_app, ["adapt", str(tmp_path / "missing.json")]).exit_code != 0
    with pytest.raises(TypeError):
        M1604Plugin(M1604Service()).run(object())  # type: ignore[arg-type]
