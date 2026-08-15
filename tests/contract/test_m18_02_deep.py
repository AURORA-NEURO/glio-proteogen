"""Adversarial contract, runtime, plugin, API, and CLI coverage for M18-02."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from evals.m18_02.run import build_scenario_request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.adapters.m1802 import cli, create_app
from glio_proteogen.contracts.m18_02 import (
    M1802_M1801_INPUT_MEDIA_TYPE,
    AlignBiomarkerPanelSourcesRequest,
    AlignedEvidenceBundle,
    AlignmentConfiguration,
    AlignmentDimension,
    AlignmentFindingCode,
    AlignmentObservationStatus,
    AlignmentStatus,
    BiomarkerPanelAlignmentResult,
    DiscrepancyMapEntry,
    DiscrepancySeverity,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c18_spatial_proteomics.m18_02_cross_source_alignment import (
    M1802AuthorizationError,
    M1802CrossSourceAlignmentEngine,
    M1802Plugin,
    M1802ReplayVerificationError,
    M1802Service,
    ValidatedM1802Request,
    align_biomarker_panel_sources,
    preflight_m1802_authorization,
)
from glio_proteogen.modules.c18_spatial_proteomics.m18_02_cross_source_alignment.engine import (
    _classify,
)

if TYPE_CHECKING:
    from pathlib import Path


HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_FORBIDDEN = 403
HTTP_UNPROCESSABLE_ENTITY = 422
CLI_ERROR = 1
CLI_REFUSED = 2
SEVEN_DIMENSIONS = 7
ESTIMATED_PROBABILITY = 0.9


def _request_payload(request: object) -> dict[str, object]:
    return request.model_dump(mode="json")  # type: ignore[union-attr]


def _validated_request(request: object, **updates: object) -> AlignBiomarkerPanelSourcesRequest:
    payload = request.model_dump(mode="python")  # type: ignore[union-attr]
    payload.update(updates)
    return AlignBiomarkerPanelSourcesRequest.model_validate(payload, strict=True)


def _validated_result(result: object, **updates: object) -> BiomarkerPanelAlignmentResult:
    payload = result.model_dump(mode="python")  # type: ignore[union-attr]
    payload.update(updates)
    return BiomarkerPanelAlignmentResult.model_validate(payload, strict=True)


def test_runtime_aligns_all_dimensions_and_preserves_parent_boundary() -> None:
    result = M1802CrossSourceAlignmentEngine().infer(build_scenario_request())

    assert result.status is AlignmentStatus.ALIGNED
    assert result.aligned_bundle is not None
    assert len(result.aligned_bundle.observations) == SEVEN_DIMENSIONS
    assert result.parent_target == "biomarker panel"
    assert result.emits_parent is False
    assert result.aligned_bundle.configuration.locked is True
    assert result.uncertainty.measurement.probability == ESTIMATED_PROBABILITY
    assert result.uncertainty.transport.probability == ESTIMATED_PROBABILITY
    assert len(result.provenance.control_decisions) == SEVEN_DIMENSIONS
    assert result.findings[0].code is AlignmentFindingCode.PROVISIONAL_ABI_PENDING_REVIEW


@pytest.mark.parametrize(
    ("scenario", "finding"),
    [
        ("conflict", "dimension_conflict"),
        ("incomplete", "input_incomplete"),
        ("unsupported", "upstream_unsupported"),
    ],
)
def test_runtime_abstains_and_preserves_conflict_or_support_findings(
    scenario: str, finding: str
) -> None:
    result = M1802CrossSourceAlignmentEngine().infer(build_scenario_request(scenario))

    assert result.status is AlignmentStatus.ABSTAINED
    assert result.aligned_bundle is None
    assert result.human_review_required is True
    assert result.abstention_reason
    assert finding in {item.code.value for item in result.findings}
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.uncertainty.measurement.probability is None
    assert any(item.code == "safe_abstention" for item in result.limitations)


def test_service_accepts_bytes_mapping_and_typed_inputs_but_rejects_duplicate_json() -> None:
    service = M1802Service()
    request = build_scenario_request()
    payload = canonical_json_bytes(request)
    assert service.execute(payload) == service.execute(_request_payload(request))
    assert service.execute(request).status is AlignmentStatus.ALIGNED

    with pytest.raises(ValueError, match="duplicate"):
        service.execute(b'{"request_id":"first","request_id":"second"}')


def test_service_verify_accepts_bytes_mapping_and_typed_result() -> None:
    service = M1802Service()
    result = service.execute(build_scenario_request())
    assert service.verify(canonical_json_bytes(result)) == result
    assert service.verify(result.model_dump(mode="json")) == result
    assert service.verify(result) == result
    assert service.verify(result, replay=False) == result


def test_plugin_requires_issued_parse_once_token() -> None:
    service = M1802Service()
    plugin = M1802Plugin(service)
    token = plugin.validate(canonical_json_bytes(build_scenario_request()))
    assert isinstance(token, ValidatedM1802Request)
    assert plugin.run(token).status is AlignmentStatus.ALIGNED
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M18-02"
    assert plugin.validate(build_scenario_request()).request == token.request
    assert plugin.verify(plugin.run(token)) == plugin.run(token)

    forged = ValidatedM1802Request(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]

    object.__setattr__(token, "request", build_scenario_request("conflict"))
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_authorization_is_fail_closed_for_mapping_and_broken_context() -> None:
    states = {
        "approved_configuration": "accepted",
        "identity_lineage": "resolved",
        "provenance": "accepted",
        "consent": "granted",
        "quality": "accepted",
        "support": "accepted",
        "intended_use": "accepted",
    }
    preflight_m1802_authorization(
        {"context": {"references": {role: {"state": state} for role, state in states.items()}}}
    )

    class BrokenMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError

    with pytest.raises(M1802AuthorizationError):
        preflight_m1802_authorization({"context": BrokenMapping()})


def test_classification_preserves_conflict_without_auth_traversal() -> None:
    request = build_scenario_request("conflict")
    status, findings = _classify(request)
    assert status is AlignmentStatus.ABSTAINED
    assert AlignmentFindingCode.DIMENSION_CONFLICT in findings
    assert AlignmentFindingCode.DISCREPANCY_UNRESOLVED in findings


def test_request_closure_rejects_wrong_media_duplicate_and_unknown_bindings() -> None:
    request = build_scenario_request()
    bad_upstream = request.upstream_result.model_copy(
        update={"media_type": "application/octet-stream"}
    )
    with pytest.raises(ValidationError, match="M18-01 resolver"):
        _validated_request(request, upstream_result=bad_upstream)

    with pytest.raises(ValidationError, match="source artifacts"):
        _validated_request(request, source_artifacts=(request.source_artifacts[0],) * 3)
    with pytest.raises(ValidationError, match="upstream result"):
        _validated_request(request, source_artifacts=request.source_artifacts[1:])

    unknown_observation = request.observations[0].model_copy(
        update={"source_ids": ("source.unknown", "source.genome")}
    )
    with pytest.raises(ValidationError, match="unknown source"):
        _validated_request(request, observations=(unknown_observation, *request.observations[1:]))

    unknown_discrepancy = DiscrepancyMapEntry(
        discrepancy_id="discrepancy.unknown",
        dimension=AlignmentDimension.SAMPLE,
        source_ids=("source.unknown", "source.genome"),
        severity=DiscrepancySeverity.ROUTINE,
        description="Unknown source discrepancy.",
        evidence=request.configuration.evidence,
    )
    with pytest.raises(ValidationError, match="discrepancy"):
        _validated_request(request, discrepancies=(unknown_discrepancy,))


def test_request_closure_rejects_duplicate_observation_and_discrepancy_ids() -> None:
    request = build_scenario_request()
    duplicate_observation = request.observations[1].model_copy(
        update={"observation_id": request.observations[0].observation_id}
    )
    with pytest.raises(ValidationError, match="observation ids"):
        _validated_request(
            request,
            observations=(
                request.observations[0],
                duplicate_observation,
                *request.observations[2:],
            ),
        )

    conflict = build_scenario_request("conflict")
    duplicate_discrepancy = conflict.discrepancies[0].model_copy(
        update={"discrepancy_id": conflict.discrepancies[0].discrepancy_id}
    )
    with pytest.raises(ValidationError, match="discrepancy ids"):
        _validated_request(
            conflict, discrepancies=(conflict.discrepancies[0], duplicate_discrepancy)
        )

    duplicate_sources = conflict.discrepancies[0].model_copy(
        update={"source_ids": ("source.proteome", "source.proteome")}
    )
    with pytest.raises(ValidationError, match="discrepancy source ids"):
        type(duplicate_sources).model_validate(
            duplicate_sources.model_dump(mode="python"), strict=True
        )


def test_observation_and_configuration_contracts_reject_invalid_shapes() -> None:
    request = build_scenario_request()
    duplicate_sources = request.observations[0].model_copy(
        update={"source_ids": ("source.proteome", "source.proteome")}
    )
    with pytest.raises(ValidationError, match="source ids"):
        type(request.observations[0]).model_validate(
            duplicate_sources.model_dump(mode="python"), strict=True
        )

    with pytest.raises(ValidationError, match="all seven"):
        AlignmentConfiguration.model_validate(
            request.configuration.model_copy(
                update={
                    "required_dimensions": (
                        *tuple(AlignmentDimension)[:-1],
                        AlignmentDimension.SAMPLE,
                    )
                }
            ).model_dump(mode="python"),
            strict=True,
        )


def test_bundle_closure_rejects_duplicates_missing_dimensions_and_mismatch() -> None:
    result = M1802CrossSourceAlignmentEngine().infer(build_scenario_request())
    assert result.aligned_bundle is not None
    bundle = result.aligned_bundle

    def validate(candidate: AlignedEvidenceBundle) -> None:
        AlignedEvidenceBundle.model_validate(candidate.model_dump(mode="python"), strict=True)

    duplicate_source = bundle.model_copy(
        update={"source_artifacts": (bundle.source_artifacts[0],) * 2}
    )
    with pytest.raises(ValidationError, match="source artifacts"):
        validate(duplicate_source)

    duplicate_observation = bundle.model_copy(
        update={"observations": (bundle.observations[0], *bundle.observations)}
    )
    with pytest.raises(ValidationError, match="observation ids"):
        validate(duplicate_observation)

    duplicate_dimension = bundle.model_copy(
        update={"observations": (bundle.observations[0], *bundle.observations[1:])}
    )
    with pytest.raises(ValidationError, match="alignment dimensions"):
        validate(duplicate_dimension.model_copy(update={"observations": bundle.observations[:-1]}))

    mismatched = bundle.observations[0].model_copy(update={"observed_values": ("different",)})
    with pytest.raises(ValidationError, match="equal their reference"):
        validate(bundle.model_copy(update={"observations": (mismatched, *bundle.observations[1:])}))

    unknown_source = bundle.observations[0].model_copy(
        update={"source_ids": ("source.unknown", "source.genome")}
    )
    with pytest.raises(ValidationError, match="unknown source"):
        validate(
            bundle.model_copy(update={"observations": (unknown_source, *bundle.observations[1:])})
        )

    unknown_discrepancy = (
        build_scenario_request("conflict")
        .discrepancies[0]
        .model_copy(update={"source_ids": ("source.unknown", "source.genome")})
    )
    with pytest.raises(ValidationError, match="unknown source"):
        validate(bundle.model_copy(update={"discrepancies": (unknown_discrepancy,)}))


def test_bundle_and_result_closure_reject_duplicate_discrepancies_and_findings() -> None:
    conflict = M1802CrossSourceAlignmentEngine().infer(build_scenario_request("conflict"))
    aligned = M1802CrossSourceAlignmentEngine().infer(build_scenario_request())
    assert conflict.status is AlignmentStatus.ABSTAINED
    assert aligned.aligned_bundle is not None

    duplicate_discrepancy = aligned.aligned_bundle.model_copy(
        update={
            "discrepancies": (
                conflict.request.discrepancies[0],
                conflict.request.discrepancies[0].model_copy(
                    update={"discrepancy_id": conflict.request.discrepancies[0].discrepancy_id}
                ),
            )
        }
    )
    with pytest.raises(ValidationError, match="discrepancy ids"):
        AlignedEvidenceBundle.model_validate(
            duplicate_discrepancy.model_dump(mode="python"), strict=True
        )

    finding = aligned.findings[0]
    with pytest.raises(ValidationError, match="finding ids"):
        _validated_result(aligned, findings=(finding, finding))
    same_code = finding.model_copy(update={"finding_id": "finding.other"})
    with pytest.raises(ValidationError, match="finding codes"):
        _validated_result(aligned, findings=(finding, same_code))


def test_result_closure_rejects_digest_and_status_drift() -> None:
    engine = M1802CrossSourceAlignmentEngine()
    aligned = engine.infer(build_scenario_request())
    abstained = engine.infer(build_scenario_request("unsupported"))

    with pytest.raises(ValidationError, match="request digest"):
        _validated_result(aligned, request_digest="sha256:" + "a" * 64)
    with pytest.raises(ValidationError, match="aligned result"):
        _validated_result(aligned, aligned_bundle=None)
    with pytest.raises(ValidationError, match="abstained result"):
        _validated_result(abstained, aligned_bundle=aligned.aligned_bundle)
    with pytest.raises(ValidationError, match="abstained result"):
        _validated_result(abstained, abstention_reason=None)
    with pytest.raises(ValidationError, match="result digest"):
        _validated_result(aligned, result_digest="sha256:" + "b" * 64)


def test_replay_tamper_and_public_wrapper_are_canonical() -> None:
    engine = M1802CrossSourceAlignmentEngine()
    request = build_scenario_request()
    result = engine.infer(request)
    assert align_biomarker_panel_sources(request) == result
    assert engine.verify(result) == result
    assert engine.verify(result, replay=False) == result
    assert canonical_request_digest(request.model_dump(mode="json")) == canonical_request_digest(
        request
    )

    tampered = result.model_copy(update={"result_digest": "sha256:" + "a" * 64})
    with pytest.raises(M1802ReplayVerificationError):
        engine.verify(tampered)
    with pytest.raises(M1802ReplayVerificationError):
        engine.verify({"not": "a result"})

    altered_request = build_scenario_request("conflict")
    altered_shell = result.model_copy(
        update={
            "request": altered_request,
            "request_digest": canonical_request_digest(altered_request),
        }
    )
    object.__setattr__(altered_shell, "result_digest", result_payload_digest(altered_shell))
    with pytest.raises(M1802ReplayVerificationError):
        engine.verify(altered_shell)


def test_api_schema_export_and_route_parity() -> None:
    request = build_scenario_request()
    with TestClient(create_app()) as client:
        schema = client.get("/v1/m18-02/schema/request")
        assert schema.status_code == HTTP_OK
        assert schema.json()["x-glio-contract"]["parentTarget"] == "biomarker panel"
        assert client.get("/v1/m18-02/schema/unknown").status_code == HTTP_NOT_FOUND

        exported = client.post("/v1/modules/M18-02/align", json=_request_payload(request))
        assert exported.status_code == HTTP_OK
        body = exported.json()
        assert body["status"] == "aligned"
        verified = client.post("/v1/modules/M18-02/verify", json=body)
        assert verified.status_code == HTTP_OK
        assert verified.json()["result_digest"] == body["result_digest"]


def test_api_sanitizes_auth_malformed_and_tamper_failures() -> None:
    with TestClient(create_app()) as client:
        denied = client.post(
            "/v1/modules/M18-02/align",
            json=_request_payload(build_scenario_request(accepted=False)),
        )
        assert denied.status_code == HTTP_FORBIDDEN
        assert "requires accepted controls" not in denied.text

        malformed = client.post("/v1/modules/M18-02/align", content=b"{not-json")
        assert malformed.status_code == HTTP_UNPROCESSABLE_ENTITY
        assert "Traceback" not in malformed.text

        result = M1802Service().execute(build_scenario_request())
        tampered = result.model_dump(mode="json")
        tampered["result_digest"] = "sha256:" + "a" * 64
        replay = client.post("/v1/modules/M18-02/verify", json=tampered)
        assert replay.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_api_maps_explicit_replay_error() -> None:
    class ReplayService(M1802Service):
        def verify(
            self,
            result: object,
            *,
            replay: bool = True,
        ) -> BiomarkerPanelAlignmentResult:
            del result, replay
            raise M1802ReplayVerificationError

    with TestClient(create_app(ReplayService())) as client:
        response = client.post("/v1/modules/M18-02/verify", json={"ignored": True})
        assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
        assert response.json()["detail"] == "M18-02 replay verification failed"


def test_cli_schema_align_verify_overwrite_and_stdin(tmp_path: Path) -> None:
    runner = CliRunner()
    schema = runner.invoke(cli, ["export-schema", "request"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M18-02"

    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    exported = runner.invoke(cli, ["align", str(request_path), "--output", str(output_path)])
    assert exported.exit_code == 0
    verified = runner.invoke(cli, ["verify", str(output_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["status"] == "aligned"

    refused = runner.invoke(cli, ["align", str(request_path), "--output", str(output_path)])
    assert refused.exit_code == CLI_REFUSED
    stdin = runner.invoke(
        cli, ["align", "-"], input=canonical_json_bytes(build_scenario_request()).decode()
    )
    assert stdin.exit_code == 0

    invalid = runner.invoke(cli, ["align", str(tmp_path / "missing.json")])
    assert invalid.exit_code == CLI_ERROR
    assert "Traceback" not in invalid.output

    denied_path = tmp_path / "denied.json"
    denied_path.write_bytes(canonical_json_bytes(build_scenario_request(accepted=False)))
    denied = runner.invoke(cli, ["align", str(denied_path)])
    assert denied.exit_code == CLI_REFUSED
    assert "authorization denied" in denied.output


def test_cli_rejects_tampered_result(tmp_path: Path) -> None:
    runner = CliRunner()
    result = M1802Service().execute(build_scenario_request()).model_dump(mode="json")
    result["result_digest"] = "sha256:" + "b" * 64
    result_path = tmp_path / "tampered.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    verified = runner.invoke(cli, ["verify", str(result_path)])
    assert verified.exit_code == CLI_ERROR
    assert "Traceback" not in verified.output


def test_explicit_media_and_status_catalogue() -> None:
    assert build_scenario_request().upstream_result.media_type == M1802_M1801_INPUT_MEDIA_TYPE
    assert set(AlignmentObservationStatus) == {
        AlignmentObservationStatus.ALIGNED,
        AlignmentObservationStatus.CONFLICTED,
        AlignmentObservationStatus.NOT_EVALUABLE,
    }
