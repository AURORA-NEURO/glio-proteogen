"""Runtime and replay tests for provisional M10-07."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m10_07 import (
    CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
    CalibrationConfiguration,
    CalibrationFindingCode,
    CalibrationMethod,
    CalibrationScope,
    CalibrationStatus,
    PredictionSet,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_07_calibration_selective_prediction import (
    M1007AuthorizationError,
    M1007CalibrationEngine,
    M1007Plugin,
    M1007Service,
    M1007TokenError,
)

_DIGEST = "sha256:" + ("a" * 64)
_MEDIA = "application/vnd.glio-proteogen.fixture+json"
_CONTROL_COUNT = 7
_SCHEMA_COUNT = 7


def _artifact(name: str, media_type: str = _MEDIA) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{name}",
        version="1.0.0-provisional",
        digest=_DIGEST,
        media_type=media_type,
    )


def _upstream(
    name: str, state: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{name}",
        state=state,
        policy_version="1.0.0",
        evidence=_artifact(f"control-{name}"),
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        request_id="request.context",
        actor_id="actor.test",
        occurred_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_upstream("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_DIGEST,
                evidence=_artifact("identity"),
            ),
            provenance=_upstream("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=_upstream("quality"),
            support=_upstream("support"),
            intended_use=_upstream("intended-use"),
        ),
    )


def _request(
    *, support_threshold: float = 0.0, ood_threshold: float = 1.0, source_media: str = _MEDIA
) -> CalibrateProteinRnaDiscordanceSelectivePredictionRequest:
    scope = CalibrationScope(
        site="site.alpha",
        platform="platform.ms",
        disease_class="glioma",
        subgroup="adult",
    )
    configuration = CalibrationConfiguration(
        configuration_id="configuration.m10-07",
        version="1.0.0-provisional",
        method=CalibrationMethod.CONFORMAL,
        scopes=(scope,),
        support_threshold=support_threshold,
        ood_threshold=ood_threshold,
        calibration_artifact=_artifact(
            "calibration", "application/vnd.glio-proteogen.calibration+json"
        ),
        benchmark_artifact=_artifact("benchmark", "application/vnd.glio-proteogen.benchmark+json"),
    )
    return CalibrateProteinRnaDiscordanceSelectivePredictionRequest(
        request_id="request.m10-07",
        context=_context(),
        uncertainty_result=_artifact("uncertainty", "application/vnd.glio-proteogen.m10-06+json"),
        configuration=configuration,
        source_artifacts=(_artifact("source", source_media),),
    )


def test_supported_runtime_is_scoped_calibrated_and_replayable() -> None:
    service = M1007Service()
    first = service.execute(_request())
    second = service.execute(_request())

    assert first.result.status is CalibrationStatus.CALIBRATED
    assert first.result.estimate is not None
    assert first.result.prediction_set == PredictionSet(
        labels=("discordant", "concordant"),
        nominal_coverage=0.9,
        evidence=first.result.prediction_set.evidence,
    )
    assert first.result.uncertainty.model_form.probability is not None
    assert len(first.result.provenance.control_decisions) == _CONTROL_COUNT
    assert first.canonical_bytes == second.canonical_bytes
    replay = service.verify(first.result, first.canonical_bytes)
    assert replay.verified is True
    assert replay.result_digest == first.result.result_digest


def test_runtime_abstains_for_support_ood_and_unsupported_inputs() -> None:
    engine = M1007CalibrationEngine()
    support = engine.execute(_request(support_threshold=1.0)).result
    ood = engine.execute(_request(ood_threshold=0.0)).result
    unsupported = engine.execute(_request(source_media="application/unsupported+json")).result

    assert support.status is CalibrationStatus.ABSTAINED
    assert support.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert CalibrationFindingCode.SUPPORT_THRESHOLD_NOT_MET in support.findings
    assert ood.support_decision.status is SupportStatus.UNSUPPORTED
    assert CalibrationFindingCode.OOD_UNSUPPORTED in ood.findings
    assert unsupported.support_decision.status is SupportStatus.UNSUPPORTED
    assert unsupported.human_review_required is True


def test_runtime_fails_closed_on_control_and_token_violations() -> None:
    request = _request()
    rejected_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={"quality": _upstream("quality", UpstreamDecisionState.REJECTED)}
            )
        }
    )
    with pytest.raises(M1007AuthorizationError):
        M1007CalibrationEngine().execute(request.model_copy(update={"context": rejected_context}))

    plugin = M1007Plugin(M1007Service())
    token = plugin.validate(request.model_dump_json())
    assert plugin.run(token).result.status is CalibrationStatus.CALIBRATED
    with pytest.raises(M1007TokenError):
        plugin.run(request)  # type: ignore[arg-type]


def test_contract_closes_duplicate_scopes_labels_and_invalid_coverage() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="scopes must be unique"):
        CalibrationConfiguration.model_validate(
            request.configuration.model_dump(mode="python")
            | {"scopes": (request.configuration.scopes[0], request.configuration.scopes[0])}
        )
    with pytest.raises(ValidationError, match="labels must be unique"):
        PredictionSet(labels=("discordant", "discordant"), nominal_coverage=0.9)
    with pytest.raises(ValidationError, match="nominal 90 percent"):
        CalibrationConfiguration.model_validate(
            request.configuration.model_dump(mode="python") | {"nominal_coverage": 0.91}
        )
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())


def test_replay_rejects_tampering_and_noncanonical_bytes() -> None:
    engine = M1007CalibrationEngine()
    built = engine.execute(_request())
    tampered = built.canonical_bytes.replace(b"discordant", b"concordant", 1)
    result = engine.verify(built.result, tampered)
    assert result.verified is False
    assert "invalid" in result.reason or "differs" in result.reason
    noncanonical = b" {" + built.canonical_bytes[1:]
    result = engine.verify(built.result, noncanonical)
    assert result.verified is False
