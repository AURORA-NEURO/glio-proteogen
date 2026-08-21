"""Contract, runtime, adapter, evaluator, and adversarial coverage for M16-01."""

# ruff: noqa: E501, ARG005, PLR2004, TC003, TRY003

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from evals.m16_01.run import _candidate, _evidence, build_scenario_request, run_evaluator
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.modules.c16_protein_rna_discordance.m16_01_upstream_contract_resolver.engine as engine_module
from glio_proteogen.adapters.m1601 import app, m1601_app
from glio_proteogen.contracts.m16_01 import (
    CompatibilityIssue,
    CompatibilityIssueCode,
    CompatibilityReport,
    CompatibilityStatus,
    ProteinRnaDiscordanceUpstreamResolutionResult,
    ResolverPolicy,
    ResolverStatus,
    UpstreamCandidate,
    UpstreamObjectKind,
    ValidatedUpstreamBundle,
    contract_json_schema,
    contract_json_schemas,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c16_protein_rna_discordance.m16_01_upstream_contract_resolver import (
    M1601AuthorizationError,
    M1601Plugin,
    M1601ReplayVerificationError,
    M1601Service,
    M1601UpstreamContractResolverEngine,
    ValidatedM1601Request,
    preflight_m1601_authorization,
    resolve_protein_rna_discordance_upstream_contracts,
)


def test_schema_metadata_and_unknown_schema_are_closed() -> None:
    schemas = contract_json_schemas()
    assert set(schemas) == {
        "request",
        "output",
        "candidate",
        "compatibility-report",
        "bundle",
        "configuration",
        "policy",
        "issue",
    }
    assert all(
        cast("dict[str, object]", item["x-glio-contract"])["provisionalAbi"]
        for item in schemas.values()
    )
    assert (
        cast("dict[str, object]", schemas["output"]["x-glio-contract"])["typedRejectionsRequired"]
        is True
    )
    with pytest.raises(KeyError):
        contract_json_schema("unknown")  # type: ignore[arg-type]


def test_report_and_bundle_closures_reject_duplicates_and_mismatch() -> None:
    with pytest.raises(ValueError, match="accepted candidate ids"):
        CompatibilityReport(
            report_id="report.x",
            version="1.0.0",
            status=CompatibilityStatus.ACCEPTED,
            accepted_candidate_ids=("candidate.a", "candidate.a"),
            evidence=_evidence("report"),
        )
    candidate = _candidate(
        UpstreamObjectKind.MASS_SPECTROMETRY_PROTEOME, label="mass-spectrometry-proteome"
    )
    report = CompatibilityReport(
        report_id="report.x",
        version="1.0.0",
        status=CompatibilityStatus.ACCEPTED,
        accepted_candidate_ids=(candidate.candidate_id,),
        evidence=_evidence("report"),
    )
    with pytest.raises(ValueError, match="accepted report requires"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.x",
            version="1.0.0",
            accepted_candidates=(candidate,),
            compatibility_report=report.model_copy(update={"accepted_candidate_ids": ()}),
            evidence=_evidence("bundle"),
        )
    mismatched_report = report.model_copy(update={"accepted_candidate_ids": ("candidate.other",)})
    with pytest.raises(ValueError, match="match"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.x",
            version="1.0.0",
            accepted_candidates=(candidate,),
            compatibility_report=mismatched_report,
            evidence=_evidence("bundle"),
        )
    blocking = CompatibilityIssue(
        issue_id="issue.x",
        code=CompatibilityIssueCode.VERSION_MISMATCH,
        message="version",
        evidence=_evidence("issue"),
    )
    with pytest.raises(ValueError, match="blocking"):
        CompatibilityReport(
            report_id="report.x",
            version="1.0.0",
            status=CompatibilityStatus.ACCEPTED,
            accepted_candidate_ids=(candidate.candidate_id,),
            issues=(blocking,),
            evidence=_evidence("report"),
        )
    with pytest.raises(ValueError, match="required upstream kinds"):
        ResolverPolicy(
            required_kinds=(
                UpstreamObjectKind.MASS_SPECTROMETRY_PROTEOME,
                UpstreamObjectKind.MASS_SPECTROMETRY_PROTEOME,
            ),
            configuration=build_scenario_request().policy.configuration,
        )
    with pytest.raises(ValueError, match="bundle candidate ids"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.x",
            version="1.0.0",
            accepted_candidates=(candidate, candidate),
            compatibility_report=report,
            evidence=_evidence("bundle"),
        )
    with pytest.raises(ValueError, match="accepted compatibility"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.x",
            version="1.0.0",
            accepted_candidates=(candidate,),
            compatibility_report=report.model_copy(
                update={"status": CompatibilityStatus.REVIEW_REQUIRED}
            ),
            evidence=_evidence("bundle"),
        )


def test_resolved_result_has_bundle_parent_provenance_and_uncertainty() -> None:
    result = M1601UpstreamContractResolverEngine().infer(build_scenario_request())
    assert result.status is ResolverStatus.RESOLVED
    assert result.bundle is not None
    assert result.parent_target == "protein_rna_discordance"
    assert result.emits_parent is False
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M16-01"
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required is True
    assert result.uncertainty.measurement.probability is None
    assert len(result.bundle.accepted_candidates) == 3


@pytest.mark.parametrize(
    "candidate",
    [
        _candidate(
            UpstreamObjectKind.MASS_SPECTROMETRY_PROTEOME,
            label="mass-spectrometry-proteome",
            version="2.0.0",
        ),
        _candidate(
            UpstreamObjectKind.MASS_SPECTROMETRY_PROTEOME,
            label="mass-spectrometry-proteome",
            media_type="application/octet-stream",
            required_media_type="application/vnd.glio-proteogen.mass+json",
        ),
    ],
)
def test_incompatible_candidates_abstain(candidate: UpstreamCandidate) -> None:
    result = M1601UpstreamContractResolverEngine().infer(
        build_scenario_request(candidates=(candidate,))
    )
    assert result.status is ResolverStatus.ABSTAINED
    assert result.bundle is None
    assert result.human_review_required
    assert result.findings


def test_missing_required_kind_abstains() -> None:
    candidate = _candidate(
        UpstreamObjectKind.MASS_SPECTROMETRY_PROTEOME, label="mass-spectrometry-proteome"
    )
    result = M1601UpstreamContractResolverEngine().infer(
        build_scenario_request(candidates=(candidate,))
    )
    assert result.status is ResolverStatus.ABSTAINED
    assert any(item.code is CompatibilityIssueCode.SUPPORT_MISSING for item in result.findings)


def test_request_and_result_closures_reject_tamper() -> None:
    request = build_scenario_request()
    duplicate = request.model_dump(mode="python")
    duplicate["candidates"] = duplicate["candidates"] * 2
    with pytest.raises(ValueError, match="candidate ids"):
        type(request).model_validate(duplicate, strict=True)
    result = M1601UpstreamContractResolverEngine().infer(request)
    payload = result.model_dump(mode="python")
    payload["request_digest"] = "sha256:" + "0" * 64
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="request digest"):
        ProteinRnaDiscordanceUpstreamResolutionResult.model_validate(payload, strict=True)
    payload = result.model_dump(mode="python")
    payload["result_id"] = "result.forged"
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValueError, match="identifier"):
        ProteinRnaDiscordanceUpstreamResolutionResult.model_validate(payload, strict=True)
    abstained = M1601UpstreamContractResolverEngine().infer(
        build_scenario_request(candidates=(candidate_for_bad(),))
    )
    no_review = abstained.model_dump(mode="python")
    no_review["human_review_required"] = False
    no_review["result_digest"] = result_payload_digest(no_review)
    with pytest.raises(ValueError, match="human review"):
        ProteinRnaDiscordanceUpstreamResolutionResult.model_validate(no_review, strict=True)
    no_result_evidence = result.model_dump(mode="python")
    no_result_evidence["evidence"] = ()
    no_result_evidence["result_digest"] = result_payload_digest(no_result_evidence)
    with pytest.raises(ValueError, match="result evidence"):
        ProteinRnaDiscordanceUpstreamResolutionResult.model_validate(
            no_result_evidence, strict=True
        )
    resolved_invalid = result.model_dump(mode="python")
        resolved_invalid["support_decision"] = result.support_decision.model_copy(
            update={"status": SupportStatus.SUPPORTED}
        )
    resolved_invalid["result_digest"] = result_payload_digest(resolved_invalid)
    with pytest.raises(ValueError, match="resolved result"):
        ProteinRnaDiscordanceUpstreamResolutionResult.model_validate(resolved_invalid, strict=True)
    abstained_invalid = abstained.model_dump(mode="python")
    abstained_invalid["bundle"] = result.bundle
    abstained_invalid["result_digest"] = result_payload_digest(abstained_invalid)
    with pytest.raises(ValueError, match="abstained result"):
        ProteinRnaDiscordanceUpstreamResolutionResult.model_validate(abstained_invalid, strict=True)


def candidate_for_bad() -> UpstreamCandidate:
    return _candidate(
        UpstreamObjectKind.MASS_SPECTROMETRY_PROTEOME,
        label="mass-spectrometry-proteome",
        version="2.0.0",
    )


def test_authorization_precedes_hostile_traversal() -> None:
    with pytest.raises(M1601AuthorizationError):
        M1601UpstreamContractResolverEngine().infer(build_scenario_request(accepted=False))

    class Exploding:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile traversal")

    with pytest.raises(M1601AuthorizationError):
        preflight_m1601_authorization(Exploding())


def test_replay_and_plugin_service_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = M1601UpstreamContractResolverEngine()
    result = engine.infer(build_scenario_request())
    assert engine.verify(result) == result
    assert engine.verify(result, replay=False) == result
    with pytest.raises(M1601ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    monkeypatch.setattr(engine_module, "result_payload_digest", lambda value: "sha256:" + "e" * 64)
    with pytest.raises(M1601ReplayVerificationError):
        engine.verify(result)
    monkeypatch.undo()
    service = M1601Service()
    plugin = M1601Plugin(service)
    token = plugin.validate(build_scenario_request())
    assert plugin.run(token).model_dump(mode="json") == service.execute(token.request).model_dump(
        mode="json"
    )
    with pytest.raises(TypeError):
        plugin.run(cast("ValidatedM1601Request", build_scenario_request()))
    json_token = plugin.validate(canonical_json_bytes(build_scenario_request()))
    assert plugin.run(json_token).status is ResolverStatus.RESOLVED
    assert plugin.verify(result).status is ResolverStatus.RESOLVED
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M16-01"
    assert (
        resolve_protein_rna_discordance_upstream_contracts(build_scenario_request()).status
        is ResolverStatus.RESOLVED
    )
    monkeypatch.setattr(
        engine_module.M1601UpstreamContractResolverEngine,
        "infer",
        lambda self, request: engine_module.M1601UpstreamContractResolverEngine()._result(
            build_scenario_request(candidates=(candidate_for_bad(),))
        ),
    )
    with pytest.raises(M1601ReplayVerificationError):
        engine.verify(result)


def test_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == report["executed_cases"] == 6


def test_fastapi_interfaces_and_sanitized_errors() -> None:
    client = TestClient(app)
    assert client.get("/v1/m16-01/schema/request").status_code == 200
    assert client.get("/v1/m16-01/schema/unknown").status_code == 404
    request_payload = build_scenario_request().model_dump(mode="json")
    response = client.post("/v1/modules/M16-01/resolve", json=request_payload)
    assert response.status_code == 200
    assert client.post("/v1/modules/M16-01/verify", json=response.json()).status_code == 200
    assert (
        client.post(
            "/v1/modules/M16-01/resolve",
            json=build_scenario_request(accepted=False).model_dump(mode="json"),
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/modules/M16-01/resolve", content=b"{", headers={"content-type": "application/json"}
        ).status_code
        == 422
    )
    invalid_payload = dict(request_payload)
    invalid_payload.pop("candidates")
    assert client.post("/v1/modules/M16-01/resolve", json=invalid_payload).status_code == 422
    assert (
        client.post(
            "/v1/modules/M16-01/resolve",
            content=b"{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == 415
    )
    assert client.post("/v1/modules/M16-01/verify", json={}).status_code == 422
    assert (
        client.post(
            "/v1/modules/M16-01/verify", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )


def test_cli_resolve_verify_schema_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    assert runner.invoke(m1601_app, ["export-schema", "output"]).exit_code == 0
    assert runner.invoke(m1601_app, ["export-schema", "unknown"]).exit_code != 0
    assert (
        runner.invoke(
            m1601_app, ["resolve", str(request_path), "--output", str(output_path)]
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            m1601_app, ["resolve", str(request_path), "--output", str(output_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(m1601_app, ["resolve", str(request_path)]).exit_code == 0
    assert runner.invoke(m1601_app, ["verify", str(output_path)]).exit_code == 0
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    assert runner.invoke(m1601_app, ["verify", str(bad)]).exit_code != 0
