"""Deep negative-path coverage for M20-04 policy and replay closure."""

# ruff: noqa: E501, PLR2004

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
from typer.testing import CliRunner

from glio_proteogen.adapters.m2004 import app, m2004_app
from glio_proteogen.contracts.m20_04 import (
    AdapterFindingCode,
    DisplaySemantics,
    ProteinSubtypeIntendedUseAdapterResult,
    result_payload_digest,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m20_04_intended_use_adapter import (
    M2004Engine,
    M2004ReplayError,
)
from tests.contract.test_m20_04_hardening import _request


def test_display_semantics_failure_is_explicit_and_safe() -> None:
    request = _request()
    semantics = DisplaySemantics(
        section_order=("support",),
        safe_default="Show safe context.",
        evidence=request.registration.display_semantics.evidence,
    )
    result = M2004Engine().adapt(
        request.model_copy(
            update={
                "registration": request.registration.model_copy(
                    update={"display_semantics": semantics}
                )
            }
        )
    )
    assert result.adapted_object is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert any(
        item.code is AdapterFindingCode.DISPLAY_SEMANTICS_INCOMPLETE for item in result.findings
    )


def test_diagnosis_and_kinase_claims_are_not_relabelled_as_supported() -> None:
    request = _request()
    claim_ceiling = request.registration.claim_ceiling.model_copy(
        update={"maximum_claim": "Diagnosis and kinase activity are established."}
    )
    result = M2004Engine().adapt(
        request.model_copy(
            update={
                "registration": request.registration.model_copy(
                    update={"claim_ceiling": claim_ceiling}
                )
            }
        )
    )
    assert result.adapted_object is None
    assert any(item.code is AdapterFindingCode.CLAIM_EXCEEDS_CEILING for item in result.findings)


def test_replay_rejects_request_digest_and_result_digest_tampering() -> None:
    engine = M2004Engine()
    result = engine.adapt(_request())
    with pytest.raises(M2004ReplayError, match="request digest"):
        engine.replay(result.model_copy(update={"request_digest": "sha256:" + "1" * 64}))
    with pytest.raises(M2004ReplayError, match="payload digest"):
        engine.replay(result.model_copy(update={"result_digest": "sha256:" + "0" * 64}))


def test_replay_rederives_payload_after_digest_rebinding() -> None:
    engine = M2004Engine()
    result = engine.adapt(_request())
    forged = result.model_copy(
        update={
            "limitations": (
                result.limitations[0].model_copy(update={"statement": "forged statement"}),
                *result.limitations[1:],
            )
        }
    )
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(M2004ReplayError, match="deterministic replay"):
        engine.replay(forged)


def test_result_contract_revalidates_finding_and_evidence_uniqueness() -> None:
    result = M2004Engine().adapt(_request())
    payload = result.model_dump()
    payload["evidence"] = (*payload["evidence"], payload["evidence"][0])
    with pytest.raises(ValidationError, match="evidence digests"):
        TypeAdapter(ProteinSubtypeIntendedUseAdapterResult).validate_python(payload, strict=True)


def test_fastapi_strict_media_schema_and_invalid_body_errors() -> None:
    client = TestClient(app)
    assert client.get("/v1/m20-04/schema/request").status_code == 200
    assert client.get("/v1/m20-04/schema/unknown").status_code == 404
    assert (
        client.post(
            "/v1/modules/M20-04/adapt",
            content=b"{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == 415
    )
    response = client.post(
        "/v1/modules/M20-04/adapt",
        content=b"{not-json}",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid JSON request"
    invalid_model = client.post(
        "/v1/modules/M20-04/adapt",
        json=_request().model_dump(mode="json") | {"upstream_result": {"media_type": "bad"}},
    )
    assert invalid_model.status_code == 422


def test_fastapi_adapt_and_verify_round_trip() -> None:
    client = TestClient(app)
    request = _request()
    response = client.post("/v1/modules/M20-04/adapt", json=request.model_dump(mode="json"))
    assert response.status_code == 200
    verified = client.post(
        "/v1/modules/M20-04/verify",
        json=response.json(),
    )
    assert verified.status_code == 200
    assert verified.json()["result_digest"] == response.json()["result_digest"]
    assert (
        client.post(
            "/v1/modules/M20-04/verify",
            content=b"{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/v1/modules/M20-04/verify",
            content=b"{}",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )


def test_typer_no_overwrite_and_unknown_schema_are_safe(tmp_path) -> None:
    runner = CliRunner()
    assert runner.invoke(m2004_app, ["export-schema", "not-a-schema"]).exit_code == 2
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    output = tmp_path / "result.json"
    output.write_text("existing", encoding="utf-8")
    result = runner.invoke(m2004_app, ["adapt", str(request_path), "--output", str(output)])
    assert result.exit_code != 0
    assert output.read_text(encoding="utf-8") == "existing"


def test_typer_adapt_and_verify_round_trip(tmp_path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    result_path = tmp_path / "result.json"
    adapted = runner.invoke(m2004_app, ["adapt", str(request_path), "--output", str(result_path)])
    assert adapted.exit_code == 0
    verified = runner.invoke(m2004_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert (
        json.loads(verified.stdout)["result_digest"]
        == json.loads(result_path.read_text(encoding="utf-8"))["result_digest"]
    )
    printed = runner.invoke(m2004_app, ["adapt", str(request_path)])
    assert printed.exit_code == 0
    bad_request = tmp_path / "bad.json"
    bad_request.write_text("{}", encoding="utf-8")
    assert runner.invoke(m2004_app, ["adapt", str(bad_request)]).exit_code != 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_text("{}", encoding="utf-8")
    assert runner.invoke(m2004_app, ["verify", str(bad_result)]).exit_code != 0
