"""Runtime, replay, and safe-abstention tests for M10-03."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

import pytest

from glio_proteogen.contracts.m10_03 import (
    M1003_BASELINE_MEDIA_TYPE,
    BaselineConfiguration,
    BaselineEstimateKind,
    BaselineEstimatorFamily,
    BaselinePreprocessingStep,
    BaselineTuningSpec,
    EstimateProteinRnaDiscordanceBaselineRequest,
    canonical_request_digest,
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
from glio_proteogen.modules.c10_pathway_proteotype.m10_03_mature_baseline_estimator import (
    BaselineAuthorizationError,
    M1003Plugin,
    M1003Service,
    estimate_protein_rna_discordance_baseline,
    verify_result_replay,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_03_mature_baseline_estimator.engine import (
    _plain,
    _validate_request,
)

_TWO_TARGETS = 2


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{name}",
        version="1.0.0",
        digest=f"sha256:{sha256(name.encode()).hexdigest()}",
        media_type=media_type,
    )


def _upstream(
    name: str, state: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{name}",
        state=state,
        policy_version="1.0.0",
        evidence=_artifact(f"ev-{name}"),
    )


def _request(
    *, support_state: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
) -> EstimateProteinRnaDiscordanceBaselineRequest:
    return EstimateProteinRnaDiscordanceBaselineRequest(
        request_id="request.m1003",
        context=ExecutionContext(
            request_id="request.m1003",
            actor_id="actor.test",
            occurred_at=datetime(2026, 8, 15, tzinfo=UTC),
            references=ContextReferences(
                approved_configuration=_upstream("configuration"),
                identity_lineage=IdentityLineageReference(
                    decision_id="decision.identity",
                    state=IdentityLineageState.RESOLVED,
                    policy_version="1.0.0",
                    binding_digest=_artifact("identity").digest,
                    evidence=_artifact("identityev"),
                ),
                provenance=_upstream("provenance"),
                consent=ConsentReference(
                    decision_id="decision.consent",
                    state=ConsentState.GRANTED,
                    policy_version="1.0.0",
                    evidence=_artifact("consentev"),
                ),
                quality=_upstream("quality"),
                support=_upstream("support", support_state),
                intended_use=_upstream("intended"),
            ),
        ),
        formal_state_result=_artifact("formal", M1003_BASELINE_MEDIA_TYPE),
        configuration=BaselineConfiguration(
            configuration_id="config.m1003",
            version="1.0.0",
            estimator_family=BaselineEstimatorFamily.ROBUST_LINEAR,
            target_feature_ids=("target.alpha", "target.beta"),
            preprocessing=(
                BaselinePreprocessingStep(
                    sequence=1,
                    operation="robust-scale",
                    parameters_digest=_artifact("preprocess").digest,
                ),
            ),
            tuning=BaselineTuningSpec(
                tuning_id="tuning.m1003",
                protocol="locked-five-fold",
                objective="mean absolute error",
                folds=5,
                benchmark_artifact=_artifact("benchmark"),
            ),
            uncertainty_method="reviewed-bootstrap",
            reference=_artifact("baseline-reference"),
        ),
        source_artifacts=(_artifact("source"),),
    )


def test_estimates_and_replays_deterministically() -> None:
    request = _request()
    result = estimate_protein_rna_discordance_baseline(request)
    assert result.status.value == "estimated"
    assert len(result.estimates) == _TWO_TARGETS
    assert result.request_digest == canonical_request_digest(request)
    assert verify_result_replay(result)
    assert result.emits_parent is False


@pytest.mark.parametrize(
    ("family", "kind"),
    [
        (BaselineEstimatorFamily.ESTABLISHED_STATISTICAL, BaselineEstimateKind.SCALAR),
        (BaselineEstimatorFamily.ROBUST_LINEAR, BaselineEstimateKind.INTERVAL),
        (BaselineEstimatorFamily.RULE_BASED, BaselineEstimateKind.CATEGORICAL),
    ],
)
def test_declared_estimator_family_selects_closed_estimate_shape(
    family: BaselineEstimatorFamily, kind: BaselineEstimateKind
) -> None:
    request = _request()
    configuration = request.configuration.model_copy(update={"estimator_family": family})
    result = estimate_protein_rna_discordance_baseline(
        request.model_copy(update={"configuration": configuration})
    )
    assert {estimate.kind for estimate in result.estimates} == {kind}


def test_unsupported_control_is_rejected_before_traversal() -> None:
    with pytest.raises(BaselineAuthorizationError):
        estimate_protein_rna_discordance_baseline(
            _request(support_state=UpstreamDecisionState.REJECTED)
        )


def test_controls_are_checked_before_execution() -> None:
    request = _request()
    refs = request.context.references.model_copy(
        update={"quality": _upstream("quality", UpstreamDecisionState.REJECTED)}
    )
    blocked = request.model_copy(
        update={"context": request.context.model_copy(update={"references": refs})}
    )
    with pytest.raises(BaselineAuthorizationError):
        M1003Service().validate_request(blocked)


def test_plugin_validates_json_once_and_requires_token() -> None:
    plugin = M1003Plugin(M1003Service())
    token = plugin.validate(_request().model_dump_json())
    assert verify_result_replay(plugin.run(token))
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(_request())  # type: ignore[arg-type]


def test_service_mapping_validation_is_strict() -> None:
    request = _request()
    assert M1003Service().validate_request(request.model_dump(mode="python")) == request


def test_container_firewall_and_invalid_token_paths_are_closed() -> None:
    class HostileDict(dict[str, object]):
        def items(self):  # type: ignore[no-untyped-def]
            raise AssertionError

    class HostileList(list[object]):
        def __iter__(self):  # type: ignore[no-untyped-def]
            raise AssertionError

    with pytest.raises(ValueError, match="container subclasses"):
        _plain(HostileDict())
    with pytest.raises(ValueError, match="container subclasses"):
        _plain(HostileList())
    with pytest.raises(BaselineAuthorizationError):
        _validate_request(object())


def test_reconstructed_token_is_rejected() -> None:
    plugin = M1003Plugin(M1003Service())
    token = plugin.validate(_request())
    copied = type(token)(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(copied)


def test_plain_builtin_paths_and_replay_tamper_are_exercised() -> None:
    request = _request()
    assert isinstance(_plain(request), dict)
    assert _plain([1, 2]) == [1, 2]
    result = estimate_protein_rna_discordance_baseline(request)
    tampered = result.model_copy(update={"result_digest": _artifact("wrong").digest})
    assert verify_result_replay(tampered) is False
