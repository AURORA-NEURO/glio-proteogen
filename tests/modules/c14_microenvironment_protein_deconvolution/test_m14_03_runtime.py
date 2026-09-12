"""Adversarial runtime, replay, and plugin tests for provisional M14-03."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m14_03 import (
    M1403_M1402_INPUT_MEDIA_TYPE,
    ConstructProteinSubtypeMechanisticFeaturesRequest,
    GliomaMicroenvironmentProgram,
    MechanisticConstructionStatus,
    MechanisticEvidenceState,
    MechanisticFeature,
    MechanisticFeatureConfiguration,
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticFindingCode,
    MechanisticRelation,
    MechanisticRelationKind,
    MechanisticValueKind,
    ProteinSubtypeMechanisticFeatureResult,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution import (
    m14_03_mechanistic_feature_constructor as m1403,
)
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution.m14_03_mechanistic_feature_constructor import (  # noqa: E501
    engine as engine_module,
)
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution.m14_03_mechanistic_feature_constructor.engine import (  # noqa: E501
    _initial_typed_values,
    _TypedTerm,
)

_FEATURE_COUNT = 7
_RELATION_COUNT = 6
_CONTROL_COUNT = 7
_TYPED_BOOTSTRAP_PROBABILITY = 0.9
_FIRST_CANDIDATE_CALL = 2


def _typed_request(
    observations: list[dict[str, object]],
    *,
    bootstrap_replicates: int = 16,
) -> ConstructProteinSubtypeMechanisticFeaturesRequest:
    payload = _request().model_dump(mode="json")
    configuration = dict(payload["configuration"])
    configuration["bootstrap_replicates"] = bootstrap_replicates
    payload["configuration"] = configuration
    payload["typed_observations"] = observations
    return ConstructProteinSubtypeMechanisticFeaturesRequest.model_validate_json(
        json.dumps(payload), strict=True
    )


def _artifact(label: str, *, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m1403.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1403": label}),
        media_type=media_type,
    )


def _context(
    *,
    quality: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED,
) -> ExecutionContext:
    return ExecutionContext(
        request_id="context.m1403.request",
        actor_id="actor.m1403.fixture",
        occurred_at=datetime(2026, 8, 15, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="decision.m1403.config",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact("control-config"),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m1403.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"identity": "fixture"}),
                evidence=_artifact("control-identity"),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="decision.m1403.provenance",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact("control-provenance"),
            ),
            consent=ConsentReference(
                decision_id="decision.m1403.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control-consent"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="decision.m1403.quality",
                state=quality,
                policy_version="1.0.0",
                evidence=_artifact("control-quality"),
            ),
            support=UpstreamDecisionReference(
                decision_id="decision.m1403.support",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact("control-support"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="decision.m1403.use",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact("control-use"),
            ),
        ),
    )


def _request(
    *,
    model_family: str = "deterministic_metadata_replay",
    quality: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED,
) -> ConstructProteinSubtypeMechanisticFeaturesRequest:
    return ConstructProteinSubtypeMechanisticFeaturesRequest(
        request_id="request.m1403.fixture",
        context=_context(quality=quality),
        upstream_result=_artifact("m1402-result", media_type=M1403_M1402_INPUT_MEDIA_TYPE),
        configuration=MechanisticFeatureConfiguration(
            configuration_id="configuration.m1403.fixture",
            version="1.0.0",
            model_family=model_family,
            transformation_ids=("transform.m1403.normalize", "transform.m1403.project"),
            stoichiometry_reference=_artifact("stoichiometry"),
            negative_control_artifacts=(_artifact("negative-control"),),
            evidence=(),
        ),
        source_artifacts=(_artifact("source-alpha"), _artifact("source-beta")),
    )


def test_constructs_all_declared_feature_kinds_and_replays() -> None:
    service = m1403.M1403Service()
    request = _request()
    result = service.construct(request)

    assert result.status is MechanisticConstructionStatus.CONSTRUCTED
    assert result.feature_object is not None
    assert len(result.feature_object.features) == _FEATURE_COUNT
    assert len(result.feature_object.relations) == _RELATION_COUNT
    assert {feature.kind for feature in result.feature_object.features} == set(
        MechanisticFeatureKind
    )
    assert all(
        feature.value_kind is MechanisticValueKind.CATEGORICAL
        for feature in result.feature_object.features
    )
    assert all(
        feature.category is not None and feature.category.startswith("caller_declared:")
        for feature in result.feature_object.features
    )
    assert result.human_review_required is True
    assert service.verify(result).model_dump(mode="json") == result.model_dump(mode="json")


def test_unsupported_configuration_abstains_without_feature_object() -> None:
    result = m1403.M1403Service().construct(
        _request(model_family="scientific_model_not_frozen")
    )

    assert result.status is MechanisticConstructionStatus.ABSTAINED
    assert result.feature_object is None
    assert result.findings == (MechanisticFindingCode.UPSTREAM_UNSUPPORTED,)
    assert result.abstention_reason is not None


def test_denied_control_fails_before_configuration_traversal() -> None:
    with pytest.raises(m1403.M1403AuthorizationError):
        m1403.M1403Service().construct(_request(quality=UpstreamDecisionState.REJECTED))
    with pytest.raises(m1403.M1403AuthorizationError):
        m1403.preflight_m1403_authorization({})


def test_plugin_requires_validated_token_and_supports_strict_json() -> None:
    plugin = m1403.M1403Plugin(m1403.M1403Service())
    request = _request()
    token = plugin.validate(request.model_dump_json())
    assert plugin.run(token).status is MechanisticConstructionStatus.CONSTRUCTED
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_unknown_fields_and_wrong_upstream_media_type_reject() -> None:
    payload = _request().model_dump(mode="python")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        m1403.M1403Service().validate_request(payload)
    wrong_upstream = _request().model_dump(mode="python")
    wrong_upstream["upstream_result"] = _artifact("wrong", media_type="application/json")
    with pytest.raises(ValidationError, match="M14-02"):
        m1403.M1403Service().validate_request(wrong_upstream)


def test_result_tampering_and_contract_relation_boundaries_fail_closed() -> None:
    service = m1403.M1403Service()
    result = service.construct(_request())
    forged = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    with pytest.raises(m1403.M1403ReplayVerificationError):
        service.verify(forged)

    lineage = MechanisticFeatureLineage(
        feature_id="feature.m1403.one",
        source_artifacts=(_artifact("lineage"),),
        claim="Caller-declared feature.",
    )
    feature = MechanisticFeature(
        feature_id="feature.m1403.one",
        version="1.0.0",
        kind=MechanisticFeatureKind.PATHWAY,
        value_kind=MechanisticValueKind.CATEGORICAL,
        unit="caller_declared",
        category="caller_declared:pathway",
        lineage=lineage,
    )
    with pytest.raises(ValueError, match="self-loop"):
        MechanisticRelation(
            relation_id="relation.m1403.self",
            source_feature_id=feature.feature_id,
            target_feature_id=feature.feature_id,
            kind=MechanisticRelationKind.PARTICIPATES,
        )


def test_public_result_is_provenance_bound_and_claims_ceiling_is_visible() -> None:
    result = m1403.M1403Service().construct(_request())
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M14-03"
    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert all(
        item.state in {"accepted", "resolved", "granted"}
        for item in result.provenance.control_decisions
    )
    limitation_text = " ".join(item.statement for item in result.limitations)
    assert "do not infer biological mechanism" in limitation_text
    assert "kinase" not in result.model_dump_json().lower()


def test_mapping_reconstruction_and_invalid_candidate_paths_fail_closed() -> None:
    service = m1403.M1403Service()
    request = _request()
    payload = request.model_dump(mode="python")
    assert service.construct(payload).status is MechanisticConstructionStatus.CONSTRUCTED
    with pytest.raises(TypeError, match="strict request model or mapping"):
        service.validate_request(42)

    class _Candidate:
        context = _context()

    with pytest.raises(TypeError, match="strict request model or mapping"):
        m1403.M1403MechanisticFeatureEngine().construct(_Candidate())

    class _ExplodingMapping(Mapping[str, Any]):
        def __getitem__(self, key: str) -> object:
            raise RuntimeError(key)

        def __iter__(self) -> Iterator[str]:
            return iter(())

        def __len__(self) -> int:
            return 0

        def get(self, key: str, _default: object = None) -> object:
            raise RuntimeError(key)

    with pytest.raises(m1403.M1403AuthorizationError):
        m1403.preflight_m1403_authorization(_ExplodingMapping())


def test_duplicate_evidence_and_negative_controls_are_not_silently_accepted() -> None:
    request = _request().model_copy(
        update={
            "source_artifacts": (_artifact("control-config"),),
        }
    )
    result = m1403.M1403Service().construct(request)
    assert len(result.evidence) < len(result.request.source_artifacts) + 10

    duplicate_configuration = request.configuration.model_copy(
        update={
            "negative_control_artifacts": (
                _artifact("same-negative"),
                _artifact("same-negative"),
            )
        }
    )
    duplicate = request.model_copy(update={"configuration": duplicate_configuration})
    abstained = m1403.M1403Service().construct(duplicate)
    assert abstained.status is MechanisticConstructionStatus.ABSTAINED


def test_plugin_descriptor_model_validation_and_service_replay_modes() -> None:
    service = m1403.M1403Service()
    plugin = m1403.M1403Plugin(service)
    request = _request()
    token = plugin.validate(request)
    result = plugin.run(token)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M14-03"
    assert plugin.verify(result, replay=False).result_id == result.result_id


def test_replay_mismatch_is_detected_after_valid_digest_reconstruction() -> None:
    service = m1403.M1403Service()
    result = service.construct(_request())
    altered = result.model_copy(update={"human_review_required": False})
    constructed = ProteinSubtypeMechanisticFeatureResult.model_construct(
        **altered.__dict__
    )
    altered = altered.model_copy(update={"result_digest": result_payload_digest(constructed)})
    with pytest.raises(m1403.M1403ReplayVerificationError):
        service.verify(altered)


def test_typed_glioma_microenvironment_graph_constructs_intervals_and_signed_edges() -> None:
    request = _typed_request(
        [
            {
                "observation_id": "observation.m1403.hypoxia",
                "program": GliomaMicroenvironmentProgram.HYPOXIA.value,
                "evidence_state": MechanisticEvidenceState.OBSERVED.value,
                "standardized_effect": 1.2,
                "standard_error": 0.2,
                "quality_weight": 0.9,
                "evidence": [],
            },
            {
                "observation_id": "observation.m1403.myeloid",
                "program": GliomaMicroenvironmentProgram.MYELOID.value,
                "evidence_state": MechanisticEvidenceState.OBSERVED.value,
                "standardized_effect": 0.7,
                "standard_error": 0.3,
                "quality_weight": 0.8,
                "evidence": [],
            },
            {
                "observation_id": "observation.m1403.opc",
                "program": GliomaMicroenvironmentProgram.OPC_LIKE.value,
                "evidence_state": MechanisticEvidenceState.LEFT_CENSORED.value,
                "standardized_effect": -0.4,
                "standard_error": 0.25,
                "quality_weight": 0.7,
                "evidence": [],
            },
        ]
    )
    service = m1403.M1403Service()
    result = service.construct(request)

    assert result.status is MechanisticConstructionStatus.CONSTRUCTED
    assert result.feature_object is not None
    assert len(result.feature_object.features) == (
        _FEATURE_COUNT + len(GliomaMicroenvironmentProgram)
    )
    typed = tuple(
        feature
        for feature in result.feature_object.features
        if feature.value_kind is MechanisticValueKind.INTERVAL
    )
    assert len(typed) == len(GliomaMicroenvironmentProgram)
    assert all(
        feature.lower_bound is not None and feature.upper_bound is not None
        for feature in typed
    )
    assert any(
        relation.kind is MechanisticRelationKind.ACTIVATES
        for relation in result.feature_object.relations
    )
    assert any(
        relation.kind is MechanisticRelationKind.INHIBITS
        for relation in result.feature_object.relations
    )
    assert any("trace_digest=" in diagnostic.message for diagnostic in result.diagnostics)
    assert result.uncertainty.measurement.state.value == "estimated"
    assert result.uncertainty.sampling.probability == _TYPED_BOOTSTRAP_PROBABILITY
    assert any(
        item.code == "typed_glioma_microenvironment_graph" for item in result.limitations
    )
    assert service.verify(result).model_dump(mode="json") == result.model_dump(mode="json")


def test_typed_solver_backtracks_objective_increase(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    request = _typed_request(
        [
            {
                "observation_id": "observation.m1403.backtrack",
                "program": GliomaMicroenvironmentProgram.HYPOXIA.value,
                "evidence_state": MechanisticEvidenceState.OBSERVED.value,
                "standardized_effect": 1.0,
                "standard_error": 0.2,
                "quality_weight": 1.0,
                "evidence": [],
            }
        ],
        bootstrap_replicates=16,
    )
    terms = engine_module._typed_terms(request.typed_observations)
    original = engine_module._typed_objective
    calls = 0

    def objective(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        value = original(*args, **kwargs)
        return value + 100.0 if calls == _FIRST_CANDIDATE_CALL else value

    monkeypatch.setattr(engine_module, "_typed_objective", objective)
    fit = engine_module._fit_typed(terms)
    assert fit.converged
    assert calls > _FIRST_CANDIDATE_CALL
    assert all(
        after <= before + engine_module._OBJECTIVE_TOLERANCE
        for before, after in pairwise(fit.objective_trace)
    )


def test_typed_initialization_keeps_left_censored_limits_feasible() -> None:
    """Mechanistic starts use observed centers and feasible censor bounds."""

    grouped = {
        GliomaMicroenvironmentProgram.HYPOXIA: [
            _TypedTerm(
                observation_id="censored",
                program=GliomaMicroenvironmentProgram.HYPOXIA,
                state=MechanisticEvidenceState.LEFT_CENSORED,
                effect=-0.3,
                standard_error=0.2,
                quality_weight=1.0,
            )
        ],
        GliomaMicroenvironmentProgram.MYELOID: [
            _TypedTerm(
                observation_id="observed",
                program=GliomaMicroenvironmentProgram.MYELOID,
                state=MechanisticEvidenceState.OBSERVED,
                effect=1.2,
                standard_error=0.2,
                quality_weight=1.0,
            ),
            _TypedTerm(
                observation_id="limit",
                program=GliomaMicroenvironmentProgram.MYELOID,
                state=MechanisticEvidenceState.LEFT_CENSORED,
                effect=0.4,
                standard_error=0.2,
                quality_weight=1.0,
            ),
        ],
    }

    values = _initial_typed_values(grouped)
    order = list(GliomaMicroenvironmentProgram)
    left_censor_limit = -0.3
    mixed_censor_limit = 0.4
    assert values[order.index(GliomaMicroenvironmentProgram.HYPOXIA)] == left_censor_limit
    assert values[order.index(GliomaMicroenvironmentProgram.MYELOID)] == mixed_censor_limit


def test_typed_initialization_downweights_failed_replicate() -> None:
    """A single extreme phosphoproteomic replicate cannot seed the graph state."""

    program = GliomaMicroenvironmentProgram.HYPOXIA
    grouped = {
        program: [
            _TypedTerm(
                observation_id="replicate-a",
                program=program,
                state=MechanisticEvidenceState.OBSERVED,
                effect=0.8,
                standard_error=0.1,
                quality_weight=1.0,
            ),
            _TypedTerm(
                observation_id="replicate-b",
                program=program,
                state=MechanisticEvidenceState.OBSERVED,
                effect=0.9,
                standard_error=0.1,
                quality_weight=1.0,
            ),
            _TypedTerm(
                observation_id="failed-batch",
                program=program,
                state=MechanisticEvidenceState.OBSERVED,
                effect=8.0,
                standard_error=0.1,
                quality_weight=1.0,
            ),
        ]
    }

    values = _initial_typed_values(grouped)
    center = values[list(GliomaMicroenvironmentProgram).index(program)]
    low_replicate = 0.8
    arithmetic_mean = (low_replicate + 0.9 + 8.0) / 3.0
    assert low_replicate < center < 1.0
    assert center < arithmetic_mean / 2.0


def test_typed_missing_and_unsupported_evidence_abstain_without_negative_observations() -> None:
    request = _typed_request(
        [
            {
                "observation_id": "observation.m1403.missing",
                "program": GliomaMicroenvironmentProgram.HYPOXIA.value,
                "evidence_state": MechanisticEvidenceState.MISSING.value,
                "quality_weight": 0.0,
                "evidence": [],
            },
            {
                "observation_id": "observation.m1403.unsupported",
                "program": GliomaMicroenvironmentProgram.MYELOID.value,
                "evidence_state": MechanisticEvidenceState.UNSUPPORTED.value,
                "quality_weight": 0.0,
                "evidence": [],
            },
        ]
    )
    result = m1403.M1403Service().construct(request)

    assert result.status is MechanisticConstructionStatus.ABSTAINED
    assert result.feature_object is None
    assert "no supported observations" in " ".join(
        diagnostic.message for diagnostic in result.diagnostics
    )
    assert "negative" not in result.diagnostics[0].message.lower()


def test_typed_missing_values_are_excluded_when_supported_programs_remain() -> None:
    request = _typed_request(
        [
            {
                "observation_id": "observation.m1403.hypoxia",
                "program": GliomaMicroenvironmentProgram.HYPOXIA.value,
                "evidence_state": MechanisticEvidenceState.OBSERVED.value,
                "standardized_effect": 0.8,
                "standard_error": 0.25,
                "quality_weight": 0.9,
                "evidence": [],
            },
            {
                "observation_id": "observation.m1403.missing",
                "program": GliomaMicroenvironmentProgram.ANGIOGENIC.value,
                "evidence_state": MechanisticEvidenceState.MISSING.value,
                "quality_weight": 0.0,
                "evidence": [],
            },
        ]
    )
    result = m1403.M1403Service().construct(request)

    assert result.status is MechanisticConstructionStatus.CONSTRUCTED
    assert result.feature_object is not None
    assert len(result.feature_object.features) == (
        _FEATURE_COUNT + len(GliomaMicroenvironmentProgram)
    )


def test_typed_observation_shape_and_bootstrap_bounds_are_closed() -> None:
    with pytest.raises(ValidationError, match="active typed observation"):
        _typed_request(
            [
                {
                    "observation_id": "observation.m1403.invalid",
                    "program": GliomaMicroenvironmentProgram.HYPOXIA.value,
                    "evidence_state": MechanisticEvidenceState.OBSERVED.value,
                    "standardized_effect": 1.0,
                    "quality_weight": 1.0,
                    "evidence": [],
                }
            ]
        )
    with pytest.raises(ValidationError):
        _typed_request(
            [
                {
                    "observation_id": "observation.m1403.invalid",
                    "program": GliomaMicroenvironmentProgram.HYPOXIA.value,
                    "evidence_state": MechanisticEvidenceState.MISSING.value,
                    "standardized_effect": 1.0,
                    "standard_error": 0.2,
                    "quality_weight": 1.0,
                    "evidence": [],
                }
            ]
        )
    with pytest.raises(ValidationError):
        _typed_request([], bootstrap_replicates=8)
