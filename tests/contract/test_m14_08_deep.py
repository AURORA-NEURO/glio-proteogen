"""Contract, runtime, adapter, and adversarial coverage for M14-08."""

# The matrix intentionally uses hostile wire inputs and literal protocol states.
# ruff: noqa: E501, ARG005, PLR2004, PT011, PT007, TC003, TRY003

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from evals.m14_08.run import (
    _artifact,
    build_scenario_request,
    run_evaluator,
)
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.modules.c14_microenvironment_protein_deconvolution.m14_08_mechanism_evidence_dossier.engine as engine_module
from glio_proteogen.adapters.m1408 import app, m1408_app
from glio_proteogen.contracts.m14_08 import (
    M1408_OUTPUT_MEDIA_TYPE,
    ClaimLevel,
    DossierStatus,
    EvidenceDisposition,
    EvidenceLink,
    EvidenceLinkKind,
    MechanismEvidenceDossier,
    ProteinSubtypeMechanismEvidenceDossierResult,
    ValidationRouteStatus,
    contract_json_schema,
    contract_json_schemas,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.contracts.m14_08.canonical import normalized_request
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution.m14_08_mechanism_evidence_dossier import (
    M1408DossierAuthorizationError,
    M1408DossierEngine,
    M1408Plugin,
    M1408ReplayVerificationError,
    M1408Service,
    ValidatedM1408Request,
)


def test_schema_metadata_and_unknown_schema_are_closed() -> None:
    schemas = contract_json_schemas()
    assert set(schemas) == {
        "request",
        "output",
        "evidence-link",
        "claim",
        "validation-route",
        "dossier",
        "configuration",
        "finding",
    }
    assert all(
        cast("dict[str, object]", item["x-glio-contract"])["provisionalAbi"]
        for item in schemas.values()
    )
    assert (
        cast("dict[str, object]", schemas["output"]["x-glio-contract"])["outputMediaType"]
        == M1408_OUTPUT_MEDIA_TYPE
    )
    with pytest.raises(KeyError):
        contract_json_schema("unknown")  # type: ignore[arg-type]


def test_supported_link_requires_evidence() -> None:
    with pytest.raises(ValueError, match="requires evidence"):
        EvidenceLink(
            link_id="link.invalid",
            kind=EvidenceLinkKind.MECHANISM,
            source_artifact=_artifact("source.invalid"),
            target_id="mechanism.alpha",
            claim="Missing evidence is not supported.",
            disposition=EvidenceDisposition.SUPPORTED,
        )


def test_dossier_link_claim_and_upstream_closures_reject_tampering() -> None:
    request = build_scenario_request()
    result = M1408DossierEngine().infer(request)
    assert result.dossier is not None
    dossier = result.dossier
    duplicate_links = dossier.model_dump(mode="python")
    duplicate_links["links"] = duplicate_links["links"] * 2
    with pytest.raises(ValueError, match="link ids"):
        MechanismEvidenceDossier.model_validate(duplicate_links, strict=True)
    duplicate_claims = dossier.model_dump(mode="python")
    duplicate_claims["claims"] = duplicate_claims["claims"] * 2
    with pytest.raises(ValueError, match="claim ids"):
        MechanismEvidenceDossier.model_validate(duplicate_claims, strict=True)
    missing_link = dossier.model_dump(mode="python")
    missing_link["claims"][0]["required_link_ids"] = ("link.missing",)
    with pytest.raises(ValueError, match="unavailable evidence link"):
        MechanismEvidenceDossier.model_validate(missing_link, strict=True)
    forged = request.model_dump(mode="python")
    forged["upstream_mechanism_result"]["media_type"] = "application/octet-stream"
    with pytest.raises(ValueError, match="M14-07"):
        type(request).model_validate(forged, strict=True)
    duplicate_routes = dossier.model_copy(
        update={"validation_routes": dossier.validation_routes + dossier.validation_routes}
    )
    with pytest.raises(ValueError, match="validation route ids"):
        MechanismEvidenceDossier.model_validate(
            duplicate_routes.model_dump(mode="python"), strict=True
        )


def test_uncertainty_is_explicit_on_supported_and_abstained_paths() -> None:
    supported = expected_uncertainty(supported=True)
    abstained = expected_uncertainty(supported=False)
    assert supported.measurement.probability == 0.9
    assert abstained.measurement.probability is None
    assert len(supported.sensitivity_notes) == 2


def test_review_ready_dossier_has_provenance_and_claim_ceiling() -> None:
    result = M1408DossierEngine().infer(build_scenario_request())
    assert result.status is DossierStatus.REVIEW_READY
    assert result.dossier is not None
    assert result.dossier.claims[0].level is ClaimLevel.SUPPORTED_MECHANISM
    assert result.dossier.claim_ceiling
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M14-08"
    assert result.parent_target == "protein_subtype"
    assert result.emits_parent is False


@pytest.mark.parametrize(
    "scenario_request",
    (
        build_scenario_request(route_status=ValidationRouteStatus.REQUIRED),
        build_scenario_request(disposition=EvidenceDisposition.UNRESOLVED),
        build_scenario_request(method="unregistered_method"),
    ),
)
def test_unsafe_dossier_states_abstain(scenario_request: object) -> None:
    result = M1408DossierEngine().infer(scenario_request)
    assert result.status is DossierStatus.ABSTAINED
    assert result.dossier is None
    assert result.human_review_required
    assert result.findings


def test_result_closure_rejects_forged_digest_id_evidence_and_review() -> None:
    engine = M1408DossierEngine()
    result = engine.infer(build_scenario_request())
    payload = result.model_dump(mode="python")
    payload["request_digest"] = "sha256:" + "0" * 64
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="request digest"):
        ProteinSubtypeMechanismEvidenceDossierResult.model_validate(payload, strict=True)
    payload = result.model_dump(mode="python")
    payload["result_id"] = "result.forged"
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="identifier"):
        ProteinSubtypeMechanismEvidenceDossierResult.model_validate(payload, strict=True)
    abstained = engine.infer(build_scenario_request(method="unregistered_method"))
    no_review = abstained.model_dump(mode="python")
    no_review["human_review_required"] = False
    no_review["result_digest"] = result_payload_digest(no_review)
    with pytest.raises(ValueError, match="human review"):
        ProteinSubtypeMechanismEvidenceDossierResult.model_validate(no_review, strict=True)
    no_evidence = result.model_dump(mode="python")
    no_evidence["evidence"] = ()
    no_evidence["result_digest"] = result_payload_digest(no_evidence)
    with pytest.raises(ValueError, match="result evidence"):
        ProteinSubtypeMechanismEvidenceDossierResult.model_validate(no_evidence, strict=True)
    invalid_ready = result.model_dump(mode="python")
    invalid_ready["dossier"] = None
    invalid_ready["support_decision"]["status"] = SupportStatus.UNSUPPORTED
    invalid_ready["result_digest"] = result_payload_digest(invalid_ready)
    with pytest.raises(ValueError, match="review-ready result"):
        ProteinSubtypeMechanismEvidenceDossierResult.model_validate(invalid_ready, strict=True)
    invalid_abstained = abstained.model_dump(mode="python")
    invalid_abstained["dossier"] = (
        result.dossier.model_dump(mode="python") if result.dossier else None
    )
    invalid_abstained["result_digest"] = result_payload_digest(invalid_abstained)
    with pytest.raises(ValueError, match="abstained result"):
        ProteinSubtypeMechanismEvidenceDossierResult.model_validate(invalid_abstained, strict=True)


def test_authorization_runs_before_typed_traversal() -> None:
    with pytest.raises(M1408DossierAuthorizationError):
        M1408DossierEngine().infer(build_scenario_request(accepted=False))
    with pytest.raises(M1408DossierAuthorizationError):
        M1408DossierEngine().infer({"context": {"references": {}}})

    class Exploding:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile traversal")

    with pytest.raises(M1408DossierAuthorizationError):
        M1408DossierEngine().infer(Exploding())


def test_counter_evidence_and_claim_gate_are_explicit() -> None:
    request = build_scenario_request()
    assert engine_module._counter_evidence(request)
    assert engine_module._evaluate_dossier(request)[0] is True
    assert request.dossier.claims
    broken_claim = request.dossier.claims[0].model_copy(
        update={"counter_evidence": (), "evidence": ()}
    )
    broken_dossier = request.dossier.model_copy(update={"claims": (broken_claim,)})
    broken_request = request.model_copy(update={"dossier": broken_dossier})
    assert engine_module._evaluate_dossier(broken_request)[0] is False


def test_replay_and_tamper_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = M1408DossierEngine()
    result = engine.infer(build_scenario_request())
    assert engine.verify(result) == result
    assert engine.verify(result, replay=False) == result
    with pytest.raises(M1408ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    original_digest = engine_module.result_payload_digest
    try:
        engine_module.result_payload_digest = lambda value: "sha256:" + "e" * 64
        with pytest.raises(M1408ReplayVerificationError):
            engine.verify(result)
    finally:
        engine_module.result_payload_digest = original_digest
    original_infer = engine_module.M1408DossierEngine.infer
    monkeypatch.setattr(
        engine_module.M1408DossierEngine,
        "infer",
        lambda self, request: original_infer(
            self, build_scenario_request(method="unregistered_method")
        ),
    )
    with pytest.raises(M1408ReplayVerificationError):
        engine.verify(result)
    monkeypatch.undo()
    assert (
        engine_module.publish_protein_subtype_mechanism_dossier(result.request).status
        is DossierStatus.REVIEW_READY
    )


def test_plugin_is_parse_once_and_token_bound() -> None:
    service = M1408Service()
    plugin = M1408Plugin(service)
    request = build_scenario_request()
    token = plugin.validate(canonical_json_bytes(request))
    assert isinstance(token, ValidatedM1408Request)
    assert plugin.run(token).status is DossierStatus.REVIEW_READY
    with pytest.raises(TypeError):
        plugin.run(ValidatedM1408Request(request=request, _seal=object()))
    with pytest.raises(TypeError):
        plugin.run({})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        plugin.validate("{")
    assert plugin.validate(request).request == request
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M14-08"


def test_service_validation_and_evaluator() -> None:
    service = M1408Service()
    request = service.validate_request(build_scenario_request().model_dump(mode="json"))
    assert service.execute(request).status is DossierStatus.REVIEW_READY
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == 7


def test_http_schema_dossier_verify_and_sanitized_errors() -> None:
    client = TestClient(app)
    request = build_scenario_request()
    payload = request.model_dump(mode="json")
    assert client.get("/v1/m14-08/schema/request").status_code == 200
    assert client.get("/v1/m14-08/schema/nope").status_code == 404
    response = client.post("/v1/modules/M14-08/dossier", json=payload)
    assert response.status_code == 200
    result_payload = response.json()
    assert client.post("/v1/modules/M14-08/verify", json=result_payload).status_code == 200
    assert (
        client.post(
            "/v1/modules/M14-08/dossier",
            content=b"{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/v1/modules/M14-08/dossier",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    invalid = request.model_dump(mode="json")
    invalid["request_id"] = 1
    assert client.post("/v1/modules/M14-08/dossier", json=invalid).status_code == 422
    assert (
        client.post(
            "/v1/modules/M14-08/verify",
            content=b"{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == 415
    )


def test_http_denies_controls_and_service_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    denied = build_scenario_request(accepted=False)
    assert (
        client.post("/v1/modules/M14-08/dossier", json=denied.model_dump(mode="json")).status_code
        == 403
    )
    result = M1408DossierEngine().infer(build_scenario_request()).model_dump(mode="json")
    result["result_digest"] = "sha256:" + "f" * 64
    assert client.post("/v1/modules/M14-08/verify", json=result).status_code == 422

    def deny_execute(self: object, request: object) -> object:  # noqa: ARG001
        raise M1408DossierAuthorizationError

    monkeypatch.setattr(M1408Service, "_execute_validated", deny_execute)
    assert (
        client.post(
            "/v1/modules/M14-08/dossier",
            json=build_scenario_request().model_dump(mode="json"),
        ).status_code
        == 403
    )


def test_cli_export_infer_verify_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    assert runner.invoke(m1408_app, ["export-schema", "request"]).exit_code == 0
    inferred = runner.invoke(m1408_app, ["infer", str(request_path), "--output", str(result_path)])
    assert inferred.exit_code == 0
    assert runner.invoke(m1408_app, ["infer", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(
            m1408_app, ["infer", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(m1408_app, ["verify", str(result_path)]).exit_code == 0
    result_path.write_text("{", encoding="utf-8")
    assert runner.invoke(m1408_app, ["verify", str(result_path)]).exit_code != 0
    assert runner.invoke(m1408_app, ["export-schema", "bad"]).exit_code == 2


def test_strict_json_duplicate_keys_are_rejected(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "duplicate.json"
    request_path.write_text('{"request_id":"a","request_id":"b"}', encoding="utf-8")
    result = runner.invoke(m1408_app, ["infer", str(request_path)])
    assert result.exit_code != 0


def test_result_payload_is_canonical_json() -> None:
    result = M1408DossierEngine().infer(build_scenario_request())
    first = canonical_json_bytes(result)
    second = canonical_json_bytes(result)
    assert first == second
    assert json.loads(first)["result_digest"] == result.result_digest
    assert normalized_request({"request_id": "dict"}) == {"request_id": "dict"}
