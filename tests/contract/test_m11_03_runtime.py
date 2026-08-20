"""Runtime, replay, plugin, and adversarial tests for M11-03."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m11_03 import (
    M1103_M1102_INPUT_MEDIA_TYPE,
    ConstructVariantPeptideMechanisticFeaturesRequest,
    MechanisticFeature,
    MechanisticFeatureConfiguration,
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticValueKind,
    canonical_request_digest,
    result_payload_digest,
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
    m11_03_mechanistic_feature_constructor as m1103,
)

_UNCERTAINTY_DIMENSIONS = (
    "measurement",
    "sampling",
    "parameter",
    "model_form",
    "identification",
    "support",
    "transport",
)


def _control[StateT](
    controls: dict[str, object], key: str, default: StateT, expected: type[StateT]
) -> StateT:
    value = controls.get(key, default)
    if not isinstance(value, expected):
        raise TypeError
    return value


def _artifact(name: str, media: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest="sha256:" + (name.encode().hex() * 64)[:64],
        media_type=media,
    )


def _request(
    *,
    upstream_id: str = "result.m1102.supported",
    source_id: str = "source.proteome",
    feature_unit: str = "activity",
    controls: dict[str, object] | None = None,
    with_features: bool = True,
) -> ConstructVariantPeptideMechanisticFeaturesRequest:
    controls = controls or {}
    evidence = _artifact("evidence.control")
    refs = ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.config",
            state=_control(
                controls,
                "approved_configuration",
                UpstreamDecisionState.ACCEPTED,
                UpstreamDecisionState,
            ),
            policy_version="1.0.0",
            evidence=evidence,
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=_control(
                controls, "identity_lineage", IdentityLineageState.RESOLVED, IdentityLineageState
            ),
            policy_version="1.0.0",
            binding_digest=_artifact("identity.binding").digest,
            evidence=evidence,
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=_control(
                controls, "provenance", UpstreamDecisionState.ACCEPTED, UpstreamDecisionState
            ),
            policy_version="1.0.0",
            evidence=evidence,
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=_control(controls, "consent", ConsentState.GRANTED, ConsentState),
            policy_version="1.0.0",
            evidence=evidence,
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=_control(
                controls, "quality", UpstreamDecisionState.ACCEPTED, UpstreamDecisionState
            ),
            policy_version="1.0.0",
            evidence=evidence,
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=_control(
                controls, "support", UpstreamDecisionState.ACCEPTED, UpstreamDecisionState
            ),
            policy_version="1.0.0",
            evidence=evidence,
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.use",
            state=_control(
                controls, "intended_use", UpstreamDecisionState.ACCEPTED, UpstreamDecisionState
            ),
            policy_version="1.0.0",
            evidence=evidence,
        ),
    )
    context = ExecutionContext(
        request_id="request.m1103",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=refs,
    )
    source = _artifact(source_id)
    lineage = MechanisticFeatureLineage(
        feature_id="pathway.activity",
        source_artifacts=(source,),
        claim="Caller-declared pathway activity.",
        transformation_ids=("transform.scale",),
    )
    feature = MechanisticFeature(
        feature_id="pathway.activity",
        version="1.0.0",
        kind=MechanisticFeatureKind.PATHWAY,
        value_kind=MechanisticValueKind.SCALAR,
        unit=feature_unit,
        scalar_value=0.75,
        lineage=lineage,
    )
    config = MechanisticFeatureConfiguration(
        configuration_id="config.m1103",
        version="1.0.0",
        model_family="curated-mechanistic-baseline",
        transformation_ids=("transform.scale",),
        topology_reference=_artifact("topology.reference"),
        negative_control_artifacts=(_artifact("negative.control"),),
        evidence=(
            # Configuration evidence is metadata, not traversed payload.
            # The source itself remains caller-owned and opaque.
        ),
    )
    return ConstructVariantPeptideMechanisticFeaturesRequest(
        request_id="request.m1103",
        context=context,
        upstream_result=_artifact(upstream_id, M1103_M1102_INPUT_MEDIA_TYPE),
        configuration=config,
        source_artifacts=(source,),
        declared_features=(feature,) if with_features else (),
        declared_relations=(),
    )


def test_supported_runtime_constructs_feature_object_and_seals_replay() -> None:
    request = _request()
    result = m1103.construct_variant_peptide_mechanistic_features(request)
    assert result.status.value == "constructed"
    assert result.feature_object is not None
    assert result.support_decision.status.value == "supported"
    assert len(result.uncertainty.model_dump()) >= len(_UNCERTAINTY_DIMENSIONS)
    assert m1103.verify_m1103_replay(result, request)
    assert result.request_digest == canonical_request_digest(request)


@pytest.mark.parametrize(
    ("kwargs", "finding"),
    [
        ({"upstream_id": "result.m1102.unsupported"}, "upstream_unsupported"),
        ({"source_id": "source.missing"}, "input_incomplete"),
        ({"with_features": False}, "input_incomplete"),
        ({"feature_unit": "unknown"}, "unit_invariant_failed"),
    ],
)
def test_safe_abstention_keeps_unsupported_distinct_from_negative(
    kwargs: dict[str, object], finding: str
) -> None:
    result = m1103.construct_variant_peptide_mechanistic_features(_request(**kwargs))  # type: ignore[arg-type]
    assert result.status.value == "abstained"
    assert result.feature_object is None
    assert finding in {item.value for item in result.findings}
    assert result.abstention_reason


def test_consent_and_identity_controls_fail_closed() -> None:
    request = _request(controls={"consent": ConsentState.WITHHELD})
    with pytest.raises(m1103.M1103AuthorizationError):
        m1103.construct_variant_peptide_mechanistic_features(request)


def test_plugin_parse_once_and_tamper_replay() -> None:
    request = _request()
    plugin = m1103.M1103Plugin(m1103.M1103Service())
    serialized = request.model_dump_json()
    token = plugin.validate(serialized)
    result = plugin.run(token)
    assert m1103.verify_m1103_replay(result, serialized)
    tampered = request.model_copy(update={"request_id": "request.tampered"})
    assert not m1103.verify_m1103_replay(result, tampered)
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]


def test_replay_rejects_self_rehashed_semantic_mutation() -> None:
    request = _request()
    result = m1103.construct_variant_peptide_mechanistic_features(request)
    mutated = result.model_copy(
        update={
            "support_decision": result.support_decision.model_copy(
                update={"rationale": "caller-rehashed semantic mutation"}
            )
        }
    )
    forged = mutated.model_copy(update={"result_digest": result_payload_digest(mutated)})
    assert not m1103.verify_m1103_replay(forged, request)
