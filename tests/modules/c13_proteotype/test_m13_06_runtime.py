"""Adversarial runtime coverage for the provisional M13-06 simulator."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from glio_proteogen.adapters.cli import app
from glio_proteogen.contracts.m13_06 import canonical_request_digest, result_payload_digest
from glio_proteogen.contracts.m13_06.v1 import (
    M1306_OPERATION,
    PerturbationKind,
    PerturbationPolicy,
    PerturbationScenario,
    PerturbationStatus,
    SimulateProteotypePerturbationRequest,
    SimulatorConfiguration,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c13_proteotype.m13_06_perturbation_sensitivity import (
    M1306AuthorizationError,
    M1306Plugin,
    M1306ReplayError,
    M1306Service,
    preflight_m1306_authorization,
    simulate_proteotype_perturbation_sensitivity,
)

if TYPE_CHECKING:
    from pathlib import Path

_DIGEST = "sha256:" + "a" * 64
_EXPECTED_DELTA = 0.3
_CONTROL_COUNT = 7


def _artifact(identifier: str = "variant") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=identifier,
        version="1.0.0",
        digest=_DIGEST,
        media_type="application/json",
    )


def _request(
    *,
    status: PerturbationStatus = PerturbationStatus.SUPPORTED,
    baseline: float = 0.2,
    perturbed: float = 0.5,
    quality: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED,
) -> SimulateProteotypePerturbationRequest:
    evidence = EvidenceReference(
        reference=_artifact("fixture-evidence"),
        role="evidence",
        claim="Synthetic bounded perturbation fixture.",
    )
    references = ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="config-decision",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact("config"),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="identity-decision",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=_DIGEST,
            evidence=_artifact("identity"),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="provenance-decision",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact("provenance"),
        ),
        consent=ConsentReference(
            decision_id="consent-decision",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=_artifact("consent"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="quality-decision",
            state=quality,
            policy_version="1.0.0",
            evidence=_artifact("quality"),
        ),
        support=UpstreamDecisionReference(
            decision_id="support-decision",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact("support"),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="use-decision",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact("use"),
        ),
    )
    context = ExecutionContext(
        request_id="request.m1306.fixture",
        actor_id="actor.fixture",
        occurred_at=datetime(2026, 8, 15, tzinfo=UTC),
        references=references,
    )
    configuration = SimulatorConfiguration(
        configuration_id="config.m1306.fixture",
        version="1.0.0",
        method="bounded replay",
        model_reference=_artifact("model"),
        units_reference=_artifact("units"),
    )
    policy = PerturbationPolicy(
        maximum_scenarios=2,
        response_lower_bound=0.0,
        response_upper_bound=1.0,
        configuration=configuration,
    )
    scenario = PerturbationScenario(
        scenario_id="scenario.fixture",
        kind=PerturbationKind.IN_SILICO,
        parameter="variant-peptide.response",
        baseline_value=baseline,
        perturbed_value=perturbed,
        unit="fraction",
        status=status,
        assumption="Synthetic fixture is within the declared response envelope.",
        source_artifact=_artifact("scenario"),
        evidence=(evidence,),
    )
    return SimulateProteotypePerturbationRequest(
        operation=M1306_OPERATION,
        request_id=context.request_id,
        context=context,
        variant_peptide_result=_artifact(),
        policy=policy,
        scenarios=(scenario,),
        source_artifacts=(_artifact("source"),),
    )


def test_supported_request_is_replayable_and_sealed() -> None:
    request = _request()
    first = simulate_proteotype_perturbation_sensitivity(request)
    second = M1306Service().execute(request)
    assert first.status.value == "simulated"
    assert first.sensitivity_surface is not None
    assert first.sensitivity_surface.responses[0].delta == _EXPECTED_DELTA
    assert first.result_digest == second.result_digest
    assert first.request_digest == canonical_request_digest(request)
    assert first.parent_target == "proteotype"
    assert first.emits_parent is False
    assert first.human_review_required is True
    assert len(first.provenance.control_decisions) == _CONTROL_COUNT
    service = M1306Service()
    assert service.verify(first) == first
    tampered = first.model_copy(update={"human_review_required": False})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})
    with pytest.raises(M1306ReplayError):
        service.verify(tampered)


def test_unsupported_scenario_abstains_without_surface() -> None:
    result = M1306Service().execute(_request(status=PerturbationStatus.UNSUPPORTED))
    assert result.status.value == "abstained"
    assert result.sensitivity_surface is None
    assert result.abstention_reason
    assert result.support_decision.status.value == "unsupported"


def test_out_of_envelope_scenario_abstains() -> None:
    result = M1306Service().execute(_request(perturbed=1.1))
    assert result.status.value == "abstained"
    assert result.sensitivity_surface is None
    assert any(item.code.value == "outside_support_envelope" for item in result.findings)


def test_authorization_fails_before_execution() -> None:
    with pytest.raises(M1306AuthorizationError):
        M1306Service().execute(_request(quality=UpstreamDecisionState.REJECTED))


def test_authorization_and_request_boundaries_fail_closed() -> None:
    with pytest.raises(M1306AuthorizationError):
        preflight_m1306_authorization({})
    with pytest.raises(TypeError):
        M1306Service().validate_request(42)


def test_mapping_boundary_is_strict_and_unknown_fields_are_rejected() -> None:
    request = _request().model_dump(mode="python")
    request["unexpected"] = True
    with pytest.raises(ValueError, match="unexpected"):
        M1306Service().validate_request(request)


def test_plugin_requires_capability_token() -> None:
    plugin = M1306Plugin(M1306Service())
    token = plugin.validate(_request())
    assert plugin.run(token).status.value == "simulated"
    serialized = canonical_json_bytes(_request().model_dump(mode="json"))
    assert plugin.validate(serialized).request == _request()
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M13-06"
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_cli_schema_export_is_available() -> None:
    result = CliRunner().invoke(app, ["proteotype-sensitivity", "export-schema", "request"])
    assert result.exit_code == 0
    assert "GLIO-PROTEOGEN-M13-06" in result.stdout


def test_cli_simulation_replays_fixture(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    path.write_bytes(
        __import__("glio_proteogen.kernel.canonical", fromlist=["canonical_json_bytes"])
        .canonical_json_bytes(_request())
    )
    result = CliRunner().invoke(app, ["proteotype-sensitivity", "simulate", str(path)])
    assert result.exit_code == 0
    assert '"status":"simulated"' in result.stdout
