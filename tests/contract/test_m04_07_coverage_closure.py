"""Substantive branch-coverage closure for the M04-07 governed boundary."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, cast
from weakref import ref

import pytest
from evals.m04_07.run import Scenario, build_scenario
from pydantic import BaseModel

from glio_proteogen.contracts.m04_04 import (
    ProteoformQualityDisposition,
    ProteoformQualityMetricStatus,
    ProteoformQualityObservationState,
)
from glio_proteogen.contracts.m04_06 import ProteoformHarmonizationDisposition
from glio_proteogen.contracts.m04_07 import (
    M0407_ZERO_DIGEST,
    ProteoformAbstention,
    ProteoformAbstentionCode,
    ProteoformDeclaredSupportState,
    ProteoformEnvelopeSupportDecision,
    ProteoformRemediationPath,
    ProteoformSupportDimension,
    ProteoformSupportRouteResult,
    RouteProteoformSupportRequest,
    configuration_digest,
)
from glio_proteogen.contracts.m04_07 import canonical as support_canonical
from glio_proteogen.contracts.m04_07 import v1 as support_contract
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router import (
    M0407Plugin,
    M0407Service,
    ValidatedM0407Request,
    route_proteoform_support,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router import (
    engine as support_engine,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router import (
    plugin as support_plugin,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class _DictSubclass(dict[str, object]):
    pass


class _InvalidPrerequisiteService(M0407Service):
    @staticmethod
    def validate_request(request: object) -> RouteProteoformSupportRequest:
        if type(request) is not RouteProteoformSupportRequest:
            raise TypeError
        return request.model_copy(update={"prerequisites": object()})


def _call_validator(method: object) -> object:
    return cast("Callable[[], object]", method)()


@pytest.fixture(scope="module")
def scenario() -> Scenario:
    return build_scenario()


@pytest.fixture(scope="module")
def route_result(scenario: Scenario) -> ProteoformSupportRouteResult:
    return route_proteoform_support(scenario.request)


@pytest.fixture(scope="module")
def issued_token(scenario: Scenario) -> ValidatedM0407Request:
    return M0407Plugin(M0407Service()).validate(scenario.request)


def test_canonical_wrappers_and_owned_identifiers_close_public_values(
    scenario: Scenario,
) -> None:
    request = scenario.request
    fact = request.declared_facts[0]
    context_receipt = request.context_receipts[0]
    remediation = request.profile.envelopes[0].remediations[0]

    assert support_canonical.prerequisites_digest(request.prerequisites).startswith("sha256:")
    assert support_canonical.fact_digest(fact).startswith("sha256:")
    assert support_canonical.context_receipt_digest(context_receipt).startswith("sha256:")
    assert support_canonical.normalized_remediation(remediation)["dimension"] == (
        remediation.dimension.value
    )

    with pytest.raises(ValueError, match="opaque specimen"):
        support_contract.opaque_support_identifier("specimen", "specimen.bad")
    invalid_evidence = fact.evidence[0].model_copy(update={"media_type": "Application/JSON"})
    with pytest.raises(ValueError, match="lowercase"):
        support_contract._owned_evidence(invalid_evidence)


def test_quality_metric_state_value_closure(scenario: Scenario) -> None:
    metric = scenario.request.prerequisites.quality.metrics[0]
    with pytest.raises(ValueError, match="requires its integer value"):
        _call_validator(metric.model_copy(update={"value_ppm": None}).value_matches_observation)

    invalid_nonevaluable = metric.model_copy(
        update={
            "observation_state": ProteoformQualityObservationState.NOT_APPLICABLE,
            "status": ProteoformQualityMetricStatus.FAIL,
            "value_ppm": None,
        }
    )
    with pytest.raises(ValueError, match="cannot carry a value"):
        _call_validator(invalid_nonevaluable.value_matches_observation)

    valid_nonevaluable = invalid_nonevaluable.model_copy(
        update={"status": ProteoformQualityMetricStatus.NOT_APPLICABLE}
    )
    assert _call_validator(valid_nonevaluable.value_matches_observation) is valid_nonevaluable


def test_quality_receipt_rejects_each_relational_contradiction(scenario: Scenario) -> None:
    receipt = scenario.request.prerequisites.quality
    metrics = receipt.metrics
    contradictions = (
        (
            receipt.model_copy(update={"metrics": (metrics[0], metrics[0], *metrics[2:])}),
            "metrics must be unique",
        ),
        (
            receipt.model_copy(
                update={
                    "artifact_reference": receipt.artifact_reference.model_copy(
                        update={"version": "9.9.9"}
                    )
                }
            ),
            "artifact does not bind",
        ),
        (receipt.model_copy(update={"applicability": None}), "exact metric domain"),
        (
            receipt.model_copy(update={"disposition": ProteoformQualityDisposition.QUARANTINED}),
            "cannot project quality values",
        ),
        (
            receipt.model_copy(
                update={
                    "disposition": ProteoformQualityDisposition.QUARANTINED,
                    "metrics": (),
                    "applicability": None,
                }
            ),
            "support envelope contradict",
        ),
        (receipt.model_copy(update={"receipt_digest": M0407_ZERO_DIGEST}), "digest does not match"),
    )
    for candidate, message in contradictions:
        with pytest.raises(ValueError, match=message):
            _call_validator(candidate.receipt_shape_is_closed)


def test_harmonization_receipt_rejects_each_relational_contradiction(
    scenario: Scenario,
) -> None:
    receipt = scenario.request.prerequisites.harmonization
    with pytest.raises(ValueError, match="preserve M04-06"):
        type(receipt).platform_ids_are_canonical(("level.bad",))

    levels = receipt.analysis_platform_level_ids
    counts_cleared = {
        "analysis_target_count": None,
        "analysis_retain_target_count": None,
        "analysis_review_target_count": None,
        "analysis_exclude_target_count": None,
        "analysis_evaluable_target_count": None,
        "analysis_platform_level_ids": (),
        "analysis_digest": None,
    }
    retained = receipt.analysis_retain_target_count
    assert retained is not None
    contradictions = (
        (
            receipt.model_copy(
                update={"analysis_platform_level_ids": (levels[0], levels[0], *levels[2:])}
            ),
            "identifiers must be unique",
        ),
        (
            receipt.model_copy(
                update={
                    "artifact_reference": receipt.artifact_reference.model_copy(
                        update={"version": "9.9.9"}
                    )
                }
            ),
            "artifact does not bind",
        ),
        (receipt.model_copy(update={"analysis_digest": None}), "successful projection"),
        (
            receipt.model_copy(update={"analysis_retain_target_count": retained + 1}),
            "closed partition",
        ),
        (receipt.model_copy(update={"human_review_required": True}), "invalid support envelope"),
        (
            receipt.model_copy(
                update={"disposition": ProteoformHarmonizationDisposition.QUARANTINED}
            ),
            "cannot project analysis values",
        ),
        (
            receipt.model_copy(
                update={
                    "disposition": ProteoformHarmonizationDisposition.QUARANTINED,
                    **counts_cleared,
                }
            ),
            "support envelope contradict",
        ),
        (receipt.model_copy(update={"receipt_digest": M0407_ZERO_DIGEST}), "digest does not match"),
    )
    for candidate, message in contradictions:
        with pytest.raises(ValueError, match=message):
            _call_validator(candidate.receipt_shape_is_closed)


def test_fact_and_context_receipt_state_closure(scenario: Scenario) -> None:
    fact = scenario.request.declared_facts[0]
    duplicate_fact = fact.model_copy(update={"values": (fact.values[0], fact.values[0])})
    with pytest.raises(ValueError, match="collections must be unique"):
        _call_validator(duplicate_fact.declaration_is_closed)
    with pytest.raises(ValueError, match="requires values and evidence"):
        _call_validator(fact.model_copy(update={"values": ()}).declaration_is_closed)
    with pytest.raises(ValueError, match="cannot carry values"):
        _call_validator(
            fact.model_copy(
                update={"state": ProteoformDeclaredSupportState.MISSING}
            ).declaration_is_closed
        )

    receipt = scenario.request.context_receipts[0]
    with pytest.raises(ValueError, match="requires evidence"):
        _call_validator(receipt.model_copy(update={"reference": None}).context_shape_is_closed)
    with pytest.raises(ValueError, match="cannot carry evidence"):
        _call_validator(
            receipt.model_copy(
                update={"state": ProteoformDeclaredSupportState.MISSING}
            ).context_shape_is_closed
        )
    valid_missing = receipt.model_copy(
        update={"state": ProteoformDeclaredSupportState.MISSING, "reference": None}
    )
    assert _call_validator(valid_missing.context_shape_is_closed) is valid_missing


def test_envelope_profile_and_assessment_invariants_are_independent(
    scenario: Scenario,
    route_result: ProteoformSupportRouteResult,
) -> None:
    envelope = scenario.request.profile.envelopes[0]
    applicability = envelope.applicabilities[0]
    with pytest.raises(ValueError, match="collections must be unique"):
        type(envelope).semantic_sets_are_canonical((applicability, applicability))
    with pytest.raises(ValueError, match="one remediation per dimension"):
        _call_validator(
            envelope.model_copy(
                update={"remediations": envelope.remediations[:-1]}
            ).envelope_is_relationally_closed
        )
    with pytest.raises(ValueError, match="preserve M04-06"):
        _call_validator(
            envelope.model_copy(
                update={"platform_level_ids": ("level.bad",)}
            ).envelope_is_relationally_closed
        )
    with pytest.raises(ValueError, match="identifiers must be unique"):
        type(scenario.request.profile).envelopes_are_canonical((envelope, envelope))

    envelope_assessment = route_result.envelope_assessments[0]
    specimen = next(
        item
        for item in envelope_assessment.dimensions
        if item.dimension is ProteoformSupportDimension.SPECIMEN
    )
    with pytest.raises(ValueError, match="values must be unique"):
        type(specimen).values_are_canonical((specimen.values[0], specimen.values[0]))
    remediation = next(
        item
        for item in envelope.remediations
        if item.dimension is ProteoformSupportDimension.SPECIMEN
    )
    with pytest.raises(ValueError, match="cannot carry remediation"):
        _call_validator(
            specimen.model_copy(
                update={
                    "reason_code": remediation.outside_reason_code,
                    "remediation_code": remediation.remediation_code,
                    "remediation_path": remediation.remediation_path,
                }
            ).codes_match_decision
        )

    with pytest.raises(ValueError, match="cover all eight dimensions"):
        _call_validator(
            envelope_assessment.model_copy(
                update={"dimensions": envelope_assessment.dimensions[:-1]}
            ).decision_matches_dimensions
        )
    with pytest.raises(ValueError, match="contradicts dimension assessments"):
        _call_validator(
            envelope_assessment.model_copy(
                update={"decision": ProteoformEnvelopeSupportDecision.ELIMINATED}
            ).decision_matches_dimensions
        )


def test_abstention_shapes_and_result_matches_are_closed(
    scenario: Scenario,
    route_result: ProteoformSupportRouteResult,
) -> None:
    envelope = scenario.request.profile.envelopes[0]
    remediation = envelope.remediations[0]
    malformed = (
        ProteoformAbstention.model_construct(
            code=ProteoformAbstentionCode.DIMENSION_OUTSIDE_DOMAIN,
            envelope_id=None,
            dimension=None,
            upstream_module_id=None,
            reason_code=remediation.outside_reason_code,
            remediation_code=remediation.remediation_code,
            remediation_path=ProteoformRemediationPath.REQUEST_GOVERNED_SUPPORT_REVIEW,
        ),
        ProteoformAbstention.model_construct(
            code=ProteoformAbstentionCode.PREREQUISITE_UNRELEASABLE,
            envelope_id=None,
            dimension=None,
            upstream_module_id=None,
            reason_code=remediation.outside_reason_code,
            remediation_code=remediation.remediation_code,
            remediation_path=ProteoformRemediationPath.REQUEST_GOVERNED_SUPPORT_REVIEW,
        ),
        ProteoformAbstention.model_construct(
            code=ProteoformAbstentionCode.JOINT_COMBINATION_OUTSIDE_DOMAIN,
            envelope_id=envelope.envelope_id,
            dimension=None,
            upstream_module_id=None,
            reason_code=remediation.outside_reason_code,
            remediation_code=remediation.remediation_code,
            remediation_path=ProteoformRemediationPath.REQUEST_GOVERNED_SUPPORT_REVIEW,
        ),
    )
    for candidate in malformed:
        with pytest.raises(
            ValueError,
            match=r"dimension abstention|prerequisite abstention|joint-combination abstention",
        ):
            _call_validator(candidate.shape_matches_code)

    envelope_id = route_result.matched_envelope_ids[0]
    with pytest.raises(ValueError, match="must be unique"):
        type(route_result).matches_are_canonical((envelope_id, envelope_id))


def test_route_boundary_rejects_each_control_and_binding_contradiction(
    scenario: Scenario,
) -> None:
    request = scenario.request
    references = request.context.references
    denied_consent = references.consent.model_copy(update={"state": "denied"})
    denied_context = request.context.model_copy(
        update={"references": references.model_copy(update={"consent": denied_consent})}
    )
    bad_approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": M0407_ZERO_DIGEST}
            )
        }
    )
    bad_configuration_context = request.context.model_copy(
        update={
            "references": references.model_copy(update={"approved_configuration": bad_approved})
        }
    )
    bad_quality = references.quality.model_copy(
        update={
            "evidence": references.quality.evidence.model_copy(update={"digest": M0407_ZERO_DIGEST})
        }
    )
    bad_binding_context = request.context.model_copy(
        update={"references": references.model_copy(update={"quality": bad_quality})}
    )
    contradictions = (
        request.model_copy(update={"context": denied_context}),
        request.model_copy(update={"declared_facts": request.declared_facts[:-1]}),
        request.model_copy(update={"context_receipts": request.context_receipts[:-1]}),
        request.model_copy(
            update={
                "profile": request.profile.model_copy(
                    update={"envelopes": (*request.profile.envelopes, *request.profile.envelopes)}
                )
            }
        ),
        request.model_copy(update={"context": bad_configuration_context}),
        request.model_copy(update={"context": bad_binding_context}),
        request.model_copy(
            update={
                "policy": request.policy.model_copy(
                    update={"reviewed_at": request.context.occurred_at + timedelta(seconds=1)}
                )
            }
        ),
    )
    for candidate in contradictions:
        with pytest.raises(ValueError, match=r"not authorized|requires|exceeds|bind|chronology"):
            support_contract._validate_route_boundary(candidate)


def test_evidence_identity_conflict_and_supersession_provenance_are_explicit(
    scenario: Scenario,
) -> None:
    request = scenario.request
    profile_evidence = request.profile.evidence
    conflicting_evidence = request.policy.evidence.model_copy(
        update={
            "artifact_id": profile_evidence.artifact_id,
            "version": profile_evidence.version,
            "digest": M0407_ZERO_DIGEST,
        }
    )
    policy = request.policy.model_copy(update={"evidence": conflicting_evidence})
    references = request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(request.profile, policy)}
            )
        }
    )
    context = request.context.model_copy(
        update={"references": references.model_copy(update={"approved_configuration": approved})}
    )
    conflict = request.model_copy(update={"policy": policy, "context": context})
    with pytest.raises(ValueError, match="conflicting evidence metadata"):
        support_contract.support_route_evidence_index(conflict)

    superseding = request.model_copy(update={"supersedes_result_digest": M0407_ZERO_DIGEST})
    provenance = support_contract.expected_provenance(superseding)
    assert M0407_ZERO_DIGEST in provenance.input_digests


def test_engine_capability_issuance_rejects_nonexact_inputs(scenario: Scenario) -> None:
    request = scenario.request
    with pytest.raises(TypeError, match="invalid M04-07 admitted"):
        support_engine._issue_admission_capability(object(), request)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="invalid M04-07 admitted"):
        support_engine._issue_admission_capability(
            request.model_copy(update={"prerequisites": object()}),
            request.model_copy(),
        )
    with pytest.raises(TypeError, match="invalid M04-07 admitted"):
        support_engine._issue_admission_capability(request, request)


def test_engine_admission_capability_fails_closed_on_stale_upstream_type(
    scenario: Scenario,
) -> None:
    request = scenario.request
    source_prerequisites = request.prerequisites.model_copy()
    source = request.model_copy(update={"prerequisites": source_prerequisites})
    validated = request.model_copy(update={"prerequisites": request.prerequisites.model_copy()})
    capability = support_engine._issue_admission_capability(source, validated)
    original_quality = source_prerequisites.quality_result
    try:
        object.__setattr__(source_prerequisites, "quality_result", object())
        assert not support_engine._admission_capability_is_issued(capability, source)
    finally:
        object.__setattr__(source_prerequisites, "quality_result", original_quality)
        support_engine._ADMISSION_CACHE.pop(id(source), None)
        support_engine._ISSUED_ADMISSION_CAPABILITIES.pop(capability, None)


def test_engine_admission_cache_drops_stale_and_exceptional_entries(
    scenario: Scenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = scenario.request
    source = request.model_copy()
    validated = request.model_copy()
    capability = support_engine._issue_admission_capability(source, validated)
    other = request.model_copy()
    support_engine._ADMISSION_CACHE[id(source)] = (ref(other), capability)
    assert support_engine._admitted_request(source) is None
    support_engine._ISSUED_ADMISSION_CAPABILITIES.pop(capability, None)

    source = request.model_copy()
    validated = request.model_copy()
    capability = support_engine._issue_admission_capability(source, validated)

    def raise_during_check(_capability: object, _source: object) -> bool:
        raise RuntimeError

    monkeypatch.setattr(support_engine, "_admission_capability_is_issued", raise_during_check)
    with pytest.raises(TypeError, match="invalid M04-07 admitted"):
        support_engine._admitted_request(source)
    support_engine._ISSUED_ADMISSION_CAPABILITIES.pop(capability, None)


def test_engine_prepare_defaults_and_plain_value_firewalls(scenario: Scenario) -> None:
    payload = scenario.request.model_dump(mode="python")
    payload.pop("operation")
    prepared, _capability = support_engine._prepare_support_request_candidate(payload)
    assert "operation" not in prepared

    assert support_engine._member(object(), "request_id") is support_engine._MISSING
    with pytest.raises(TypeError, match="exact built-in containers"):
        support_engine._request_member_names(object())
    with pytest.raises(TypeError, match="exact built-in containers"):
        support_engine._request_member_names(cast("dict[str, object]", {object(): None}))
    assert support_engine._state_text(object()) is None
    with pytest.raises(TypeError, match="exact built-in containers"):
        support_engine._plain_value(object(), _depth=support_engine._MAX_PLAIN_DEPTH + 1)
    with pytest.raises(TypeError, match="exact built-in containers"):
        support_engine._plain_value(object(), _budget=[0])

    corrupted_model = scenario.request.model_copy()
    storage = cast("dict[object, object]", object.__getattribute__(corrupted_model, "__dict__"))
    storage[object()] = None
    with pytest.raises(TypeError, match="exact built-in containers"):
        support_engine._plain_value(corrupted_model)
    with pytest.raises(TypeError, match="exact built-in containers"):
        support_engine._plain_value(_DictSubclass())


def test_plugin_token_failures_are_closed_before_execution(
    scenario: Scenario,
    issued_token: ValidatedM0407Request,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert not support_plugin._token_is_issued(object())  # type: ignore[arg-type]

    prerequisites = issued_token.request.prerequisites
    original_quality = prerequisites.quality_result
    try:
        object.__setattr__(prerequisites, "quality_result", object())
        assert not support_plugin._token_is_issued(issued_token)
    finally:
        object.__setattr__(prerequisites, "quality_result", original_quality)

    def fail_snapshot(_request: RouteProteoformSupportRequest) -> bytes:
        raise RuntimeError

    monkeypatch.setattr(support_plugin, "_request_snapshot", fail_snapshot)
    assert not support_plugin._token_is_issued(issued_token)

    invalid_plugin = M0407Plugin(_InvalidPrerequisiteService())
    with pytest.raises(TypeError, match="validated request token"):
        invalid_plugin.validate(scenario.request)


def test_plain_firewall_uses_only_exact_builtin_model_storage(scenario: Scenario) -> None:
    assert isinstance(scenario.request, BaseModel)
    assert type(object.__getattribute__(scenario.request, "__dict__")) is dict
    assert SupportStatus.LIMITED is scenario.request.prerequisites.harmonization.support_status
