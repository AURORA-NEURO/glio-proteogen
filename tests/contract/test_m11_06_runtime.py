"""Adversarial contract, runtime, replay, and adapter coverage for M11-06."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1106 import app, m1106_app
from glio_proteogen.contracts.m11_06 import (
    M1106_M1105_INPUT_MEDIA_TYPE,
    M1106_OUTPUT_MEDIA_TYPE,
    PerturbationKind,
    PerturbationSpecification,
    SensitivitySimulationConfiguration,
    SensitivitySimulationStatus,
    SimulateVariantPeptidePerturbationsRequest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c11_protein_native_subtype import (
    m11_06_perturbation_sensitivity_simulator as m1106,
)

if TYPE_CHECKING:
    from pathlib import Path

_CONTROL_COUNT = 7
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_HTTP_OK = 200
_HTTP_UNSUPPORTED_MEDIA = 415
M1106AuthorizationError = m1106.M1106AuthorizationError
M1106ReplayVerificationError = m1106.M1106ReplayVerificationError
M1106SensitivityEngine = m1106.M1106SensitivityEngine
M1106Plugin = m1106.M1106Plugin
M1106Service = m1106.M1106Service


def _digest(number: int) -> str:
    return f"sha256:{number:064x}"


def _artifact(
    name: str, media_type: str = "application/vnd.aurora.artifact+json"
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=f"sha256:{hashlib.sha256(name.encode()).hexdigest()}",
        media_type=media_type,
    )


def _controls(
    *, state: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
) -> ContextReferences:
    accepted = UpstreamDecisionReference(
        decision_id="decision.accepted",
        state=state,
        policy_version="1.0.0",
        evidence=_artifact("control.accepted"),
    )
    return ContextReferences(
        approved_configuration=accepted,
        identity_lineage=IdentityLineageReference(
            decision_id="identity.resolved",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=_digest(99),
            evidence=_artifact("control.identity"),
        ),
        provenance=accepted.model_copy(update={"decision_id": "provenance.accepted"}),
        consent=ConsentReference(
            decision_id="consent.granted",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=_artifact("control.consent"),
        ),
        quality=accepted.model_copy(update={"decision_id": "quality.accepted"}),
        support=accepted.model_copy(update={"decision_id": "support.accepted"}),
        intended_use=accepted.model_copy(update={"decision_id": "use.accepted"}),
    )


def _perturbation(
    name: str = "scenario.baseline",
    *,
    kind: PerturbationKind = PerturbationKind.IN_SILICO,
    parameter: str = "protein_abundance",
    baseline: str = "1.0",
    perturbed: str = "1.2",
) -> PerturbationSpecification:
    return PerturbationSpecification(
        perturbation_id=name,
        kind=kind,
        target_ids=("variant-peptide-1",),
        parameter=parameter,
        baseline_value=baseline,
        perturbed_value=perturbed,
        rationale="Stress-test a declared protein-native variant-peptide response.",
        alternative_prior=(
            _artifact(f"prior.{name}") if kind is PerturbationKind.ALTERNATIVE_PRIOR else None
        ),
        assay_artifact=(
            _artifact(f"assay.{name}") if kind is PerturbationKind.ASSAY_PERTURBATION else None
        ),
    )


def _request(
    perturbations: tuple[PerturbationSpecification, ...] | None = None,
    *,
    negative_control: bool = True,
    controls: ContextReferences | None = None,
) -> SimulateVariantPeptidePerturbationsRequest:
    config = SensitivitySimulationConfiguration(
        configuration_id="config.m1106",
        version="1.0.0",
        model_family="deterministic-bounded-reference",
        reference_artifact=_artifact("config.reference"),
        maximum_scenarios=8,
        negative_control_artifact=_artifact("control.negative") if negative_control else None,
    )
    upstream = _artifact("upstream.m1105", M1106_M1105_INPUT_MEDIA_TYPE)
    return SimulateVariantPeptidePerturbationsRequest(
        request_id="request.m1106",
        context=ExecutionContext(
            request_id="request.m1106",
            actor_id="actor.test",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=controls or _controls(),
        ),
        upstream_result=upstream,
        configuration=config,
        perturbations=perturbations or (_perturbation(),),
        source_artifacts=(_artifact("source.proteome"), _artifact("source.genome")),
    )


def test_supported_surface_is_bounded_and_replayable() -> None:
    request = _request()
    result = M1106SensitivityEngine().register(request)
    assert result.status is SensitivitySimulationStatus.SIMULATED
    assert result.surface is not None
    assert len(result.surface.responses) == len(request.perturbations)
    response = result.surface.responses[0]
    assert response.lower_bound <= response.response_value <= response.upper_bound
    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    verified = M1106SensitivityEngine().verify(result)
    assert verified.model_dump(mode="json") == result.model_dump(mode="json")


@pytest.mark.parametrize(
    ("kind", "parameter"),
    [
        (PerturbationKind.PARAMETER_SWEEP, "sampling_fraction"),
        (PerturbationKind.ALTERNATIVE_PRIOR, "prior_weight"),
        (PerturbationKind.ASSAY_PERTURBATION, "assay_noise"),
        (PerturbationKind.MECHANISM_STRESS, "mechanism_edge"),
    ],
)
def test_all_declared_perturbation_kinds_are_supported(
    kind: PerturbationKind, parameter: str
) -> None:
    result = M1106SensitivityEngine().register(
        _request((_perturbation(kind=kind, parameter=parameter),))
    )
    assert result.status is SensitivitySimulationStatus.SIMULATED


@pytest.mark.parametrize("marker", ["unsupported", "ood", "novel", "missing"])
def test_unsupported_or_novel_perturbations_abstain_without_surface(marker: str) -> None:
    request = _request((_perturbation(perturbed=marker),))
    result = M1106SensitivityEngine().register(request)
    assert result.status is SensitivitySimulationStatus.ABSTAINED
    assert result.surface is None
    assert result.human_review_required is True
    assert result.support_decision.status.value == "unsupported"


def test_negative_control_gate_abstains() -> None:
    result = M1106SensitivityEngine().register(_request(negative_control=False))
    assert result.status is SensitivitySimulationStatus.ABSTAINED
    assert "negative_control_failed" in {finding.value for finding in result.findings}


def test_identity_or_consent_control_failure_is_rejected_before_traversal() -> None:
    controls = _controls()
    withheld = controls.consent.model_copy(update={"state": ConsentState.WITHHELD})
    denied = controls.model_copy(update={"consent": withheld})
    with pytest.raises(M1106AuthorizationError):
        M1106SensitivityEngine().register(_request(controls=denied))


def test_prohibited_ownership_terms_abstain() -> None:
    result = M1106SensitivityEngine().register(
        _request((_perturbation(parameter="kinase_activity"),))
    )
    assert result.status is SensitivitySimulationStatus.ABSTAINED


def test_plugin_is_parse_once_and_token_bound() -> None:
    request = _request()
    plugin = M1106Plugin(M1106Service())
    token = plugin.validate(request.model_dump_json())
    result = plugin.run(token)
    assert result.status is SensitivitySimulationStatus.SIMULATED
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]


def test_replay_detects_tampering() -> None:
    result = M1106SensitivityEngine().register(_request())
    tampered = result.model_dump(mode="json")
    tampered["result_digest"] = _digest(1234)
    with pytest.raises(M1106ReplayVerificationError):
        M1106SensitivityEngine().verify(tampered)


def test_api_cli_and_schema_parity(tmp_path: Path) -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    with TestClient(app) as client:
        response = client.post("/v1/modules/M11-06/perturbations", json=payload)
        assert response.status_code == _HTTP_OK
        result_payload = response.json()
        assert result_payload["status"] == "simulated"
        schema_response = client.get("/v1/m11-06/schema/output")
        assert schema_response.status_code == _HTTP_OK
        assert (
            schema_response.json()["x-glio-contract"]["outputMediaType"] == M1106_OUTPUT_MEDIA_TYPE
        )
        assert client.get("/v1/m11-06/schema/nope").status_code == _HTTP_NOT_FOUND
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    cli = CliRunner().invoke(
        m1106_app, ["simulate", str(request_path), "--output", str(result_path)]
    )
    assert cli.exit_code == 0, cli.output
    verified = CliRunner().invoke(m1106_app, ["verify", str(result_path)])
    assert verified.exit_code == 0, verified.output


def test_api_rejects_wrong_content_type_and_denied_controls() -> None:
    request = _request()
    with TestClient(app) as client:
        assert (
            client.post(
                "/v1/modules/M11-06/perturbations",
                content=json.dumps(request.model_dump(mode="json")),
                headers={"content-type": "text/plain"},
            ).status_code
            == _HTTP_UNSUPPORTED_MEDIA
        )
        controls = _controls()
        denied = controls.approved_configuration.model_copy(
            update={"state": UpstreamDecisionState.REJECTED}
        )
        denied_request = _request(
            controls=controls.model_copy(update={"approved_configuration": denied})
        )
        response = client.post(
            "/v1/modules/M11-06/perturbations",
            json=denied_request.model_dump(mode="json"),
        )
        assert response.status_code == _HTTP_FORBIDDEN


def test_contract_rejects_duplicate_perturbation_ids() -> None:
    with pytest.raises(ValueError, match="identifiers must be unique"):
        _request((_perturbation("same"), _perturbation("same", parameter="other")))


def test_request_is_strict_and_rejects_wrong_upstream_media_type() -> None:
    payload: dict[str, Any] = _request().model_dump(mode="python")
    payload["upstream_result"]["media_type"] = "application/vnd.wrong+json"
    with pytest.raises(ValueError, match="M11-05 upstream"):
        SimulateVariantPeptidePerturbationsRequest.model_validate(payload, strict=True)
