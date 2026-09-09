"""Runtime, replay, plugin, and adversarial tests for M11-03."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m11_03 import (
    M1103_GLIOMA_MODEL_FAMILY,
    M1103_M1102_INPUT_MEDIA_TYPE,
    ConstructVariantPeptideMechanisticFeaturesRequest,
    MechanisticFeature,
    MechanisticFeatureConfiguration,
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticRelation,
    MechanisticRelationKind,
    MechanisticValueKind,
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
from glio_proteogen.modules.c11_protein_native_subtype import (
    m11_03_mechanistic_feature_constructor as m1103,
)
from glio_proteogen.modules.c11_protein_native_subtype.m11_03_mechanistic_feature_constructor import (  # noqa: E501
    engine as engine_module,
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
    controls: dict[str, str] | None = None,
    with_features: bool = True,
) -> ConstructVariantPeptideMechanisticFeaturesRequest:
    controls = controls or {}
    evidence = _artifact("evidence.control")
    refs = ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.config",
            state=controls.get("approved_configuration", UpstreamDecisionState.ACCEPTED),
            policy_version="1.0.0",
            evidence=evidence,
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=controls.get("identity_lineage", IdentityLineageState.RESOLVED),
            policy_version="1.0.0",
            binding_digest=_artifact("identity.binding").digest,
            evidence=evidence,
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=controls.get("provenance", UpstreamDecisionState.ACCEPTED),
            policy_version="1.0.0",
            evidence=evidence,
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=controls.get("consent", ConsentState.GRANTED),
            policy_version="1.0.0",
            evidence=evidence,
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=controls.get("quality", UpstreamDecisionState.ACCEPTED),
            policy_version="1.0.0",
            evidence=evidence,
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=controls.get("support", UpstreamDecisionState.ACCEPTED),
            policy_version="1.0.0",
            evidence=evidence,
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.use",
            state=controls.get("intended_use", UpstreamDecisionState.ACCEPTED),
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


def test_typed_glioma_feature_graph_projects_state_and_bootstrap_interval() -> None:
    request = _request()
    pathway = request.declared_features[0]
    egfr = pathway.model_copy(
        update={
            "feature_id": "protein.egfr",
            "kind": MechanisticFeatureKind.STATE,
            "scalar_value": 1.2,
            "lineage": pathway.lineage.model_copy(
                update={
                    "feature_id": "protein.egfr",
                    "claim": "Caller-declared EGFR abundance.",
                }
            ),
        }
    )
    typed_request = request.model_copy(
        update={
            "configuration": request.configuration.model_copy(
                update={
                    "model_family": M1103_GLIOMA_MODEL_FAMILY,
                    "bootstrap_replicates": 16,
                }
            ),
            "declared_features": (pathway, egfr),
            "declared_relations": (
                MechanisticRelation(
                    relation_id="relation.egfr.pathway",
                    source_feature_id="protein.egfr",
                    target_feature_id="pathway.activity",
                    kind=MechanisticRelationKind.ACTIVATES,
                    weight=0.8,
                ),
            ),
        }
    )
    result = m1103.construct_variant_peptide_mechanistic_features(typed_request)
    assert result.status.value == "constructed"
    assert result.typed_model is True
    assert result.model_profile == M1103_GLIOMA_MODEL_FAMILY
    assert result.solver_iterations is not None
    assert result.solver_objective is not None
    assert result.feature_object is not None
    feature_ids = {feature.feature_id for feature in result.feature_object.features}
    assert {"feature.glioma.signed_state", "feature.glioma.state_interval"} <= feature_ids
    interval = next(
        feature
        for feature in result.feature_object.features
        if feature.feature_id == "feature.glioma.state_interval"
    )
    assert interval.lower_bound is not None
    assert interval.upper_bound is not None
    assert interval.lower_bound <= interval.upper_bound
    assert m1103.verify_m1103_replay(result, typed_request)


def test_typed_solver_backtracks_objective_increase(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    request = _request()
    pathway = request.declared_features[0]
    egfr = pathway.model_copy(
        update={
            "feature_id": "protein.egfr",
            "kind": MechanisticFeatureKind.STATE,
            "scalar_value": 1.2,
            "lineage": pathway.lineage.model_copy(
                update={
                    "feature_id": "protein.egfr",
                    "claim": "Caller-declared EGFR abundance.",
                }
            ),
        }
    )
    relation = MechanisticRelation(
        relation_id="relation.egfr.pathway",
        source_feature_id="protein.egfr",
        target_feature_id="pathway.activity",
        kind=MechanisticRelationKind.ACTIVATES,
        weight=0.8,
    )
    baseline = engine_module._fit_glioma((pathway, egfr), (relation,))
    assert baseline is not None
    assert baseline.converged
    original = engine_module._glioma_objective
    calls = 0
    first_candidate_call = 2

    def objective(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        value = original(*args, **kwargs)
        return value + 100.0 if calls == first_candidate_call else value

    monkeypatch.setattr(engine_module, "_glioma_objective", objective)
    fit = engine_module._fit_glioma((pathway, egfr), (relation,))
    assert fit is not None
    assert fit.converged
    assert calls > first_candidate_call
    assert fit.objective <= baseline.objective + engine_module._M1103_OBJECTIVE_TOLERANCE


def test_typed_glioma_graph_abstains_without_relation_support() -> None:
    request = _request()
    second = request.declared_features[0].model_copy(
        update={
            "feature_id": "protein.egfr",
            "lineage": request.declared_features[0].lineage.model_copy(
                update={"feature_id": "protein.egfr"}
            ),
        }
    )
    typed_request = request.model_copy(
        update={
            "configuration": request.configuration.model_copy(
                update={"model_family": M1103_GLIOMA_MODEL_FAMILY}
            ),
            "declared_features": (request.declared_features[0], second),
        }
    )
    result = m1103.construct_variant_peptide_mechanistic_features(typed_request)
    assert result.status.value == "abstained"
    assert result.feature_object is None
    assert "signed relation" in (result.abstention_reason or "")


def test_typed_glioma_graph_abstains_for_unweighted_relation() -> None:
    request = _request()
    pathway = request.declared_features[0]
    egfr = pathway.model_copy(
        update={
            "feature_id": "protein.egfr",
            "kind": MechanisticFeatureKind.STATE,
            "scalar_value": 1.2,
            "lineage": pathway.lineage.model_copy(
                update={"feature_id": "protein.egfr", "claim": "Caller-declared EGFR."}
            ),
        }
    )
    typed_request = request.model_copy(
        update={
            "configuration": request.configuration.model_copy(
                update={"model_family": M1103_GLIOMA_MODEL_FAMILY}
            ),
            "declared_features": (pathway, egfr),
            "declared_relations": (
                MechanisticRelation(
                    relation_id="relation.egfr.pathway.unweighted",
                    source_feature_id="protein.egfr",
                    target_feature_id="pathway.activity",
                    kind=MechanisticRelationKind.ACTIVATES,
                ),
            ),
        }
    )
    result = m1103.construct_variant_peptide_mechanistic_features(typed_request)
    assert result.status.value == "abstained"
    assert result.feature_object is None
    assert "signed relation" in (result.abstention_reason or "")


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
    result = m1103.construct_variant_peptide_mechanistic_features(_request(**kwargs))
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
