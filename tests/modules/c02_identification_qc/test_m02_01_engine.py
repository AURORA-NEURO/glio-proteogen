"""Representative public engine and lifecycle qualification for M02-01."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from evals.m02_01.run import build_scenario_request, conditional_requests

from glio_proteogen.contracts.m02_01 import (
    ConformanceDisposition,
    ConformanceProfile,
    ConformanceStatus,
    EvaluateConformanceRequest,
    FieldObservation,
    ObservationState,
    ProtocolFieldDefinition,
    ValueKind,
    canonical_request_digest,
    configuration_digest,
    schema_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import ArtifactReference
from glio_proteogen.modules.c02_identification_qc.m02_01_protocol_metadata import (
    ConformanceAuthorizationError,
    M0201Plugin,
    M0201Service,
    ValidatedM0201Request,
    evaluate_conformance,
    preflight_conformance_authorization,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


@pytest.mark.parametrize(
    ("case", "status"),
    [
        ("canonical", ConformanceStatus.CONFORMANT),
        ("missing_mandatory", ConformanceStatus.INDETERMINATE),
        ("unsupported_term", ConformanceStatus.NONCONFORMANT),
        ("incompatible_unit", ConformanceStatus.NONCONFORMANT),
        ("over_cardinality", ConformanceStatus.NONCONFORMANT),
        ("unresolved_mandatory", ConformanceStatus.INDETERMINATE),
    ],
)
def test_public_engine_routes_locked_scenarios(
    case: str,
    status: ConformanceStatus,
) -> None:
    result = evaluate_conformance(build_scenario_request(case))

    assert result.status is status
    assert result.disposition is (
        ConformanceDisposition.CONFORMANT
        if status is ConformanceStatus.CONFORMANT
        else ConformanceDisposition.QUARANTINED
    )


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        (ObservationState.MISSING, "mandatory_value_missing"),
        (ObservationState.UNKNOWN, "mandatory_value_unknown"),
        (ObservationState.CONFLICTING, "mandatory_value_conflicting"),
    ],
)
def test_unresolved_states_remain_distinct(
    state: ObservationState,
    reason: str,
) -> None:
    request = build_scenario_request("canonical")
    original = next(
        item for item in request.observations if item.field_id == "instrument_model"
    )
    values: tuple[str, ...] = (
        ("instrument.a", "instrument.b")
        if state is ObservationState.CONFLICTING
        else ()
    )
    replacement = original.model_copy(update={"state": state, "values": values})
    observations = tuple(
        replacement if item.field_id == "instrument_model" else item
        for item in request.observations
    )

    result = evaluate_conformance(request.model_copy(update={"observations": observations}))
    field_findings = {
        item.reason_code
        for item in result.field_evaluations
        if item.state.value != "pass"
    }
    rule_findings = {
        item.reason_code
        for item in result.rule_evaluations
        if item.state.value != "pass"
    }
    findings = field_findings | rule_findings

    assert findings == {reason}
    assert "mandatory_field_missing" not in findings


def test_conditional_state_rule_changes_only_supported_context() -> None:
    label_free, isobaric = conditional_requests()

    assert evaluate_conformance(label_free).status is ConformanceStatus.CONFORMANT
    result = evaluate_conformance(isobaric)
    assert result.status is ConformanceStatus.NONCONFORMANT
    assert "not_applicable_disallowed" in {
        item.reason_code for item in result.rule_evaluations
    }


def test_declared_vocabulary_is_enforced_without_a_redundant_rule() -> None:
    request = build_scenario_request("canonical")
    observation = next(
        item for item in request.observations if item.field_id == "label_reagent"
    ).model_copy(
        update={"state": ObservationState.OBSERVED, "values": ("unknown_reagent",)}
    )
    observations = tuple(
        observation if item.field_id == "label_reagent" else item
        for item in request.observations
    )
    request = request.model_copy(update={"observations": observations})

    result = evaluate_conformance(request)

    evaluation = next(
        item for item in result.field_evaluations if item.field_id == "label_reagent"
    )
    assert evaluation.reason_code == "controlled_term_unsupported"
    assert result.disposition is ConformanceDisposition.QUARANTINED


def test_observation_evidence_order_replays_to_identical_result() -> None:
    request = build_scenario_request("canonical")
    observation = request.observations[0]
    extra = observation.evidence[0].model_copy(
        update={
            "artifact_id": "artifact.synthetic.observation.extra",
            "digest": sha256_digest({"m0201": "observation-extra"}),
        }
    )
    forward = observation.model_copy(
        update={"evidence": (*observation.evidence, extra)}
    )
    reverse = observation.model_copy(
        update={"evidence": tuple(reversed(forward.evidence))}
    )

    def replace(item: FieldObservation) -> EvaluateConformanceRequest:
        observations = (item, *request.observations[1:])
        return request.model_copy(update={"observations": observations})

    forward_request = replace(forward)
    reverse_request = replace(reverse)

    assert canonical_request_digest(forward_request) == canonical_request_digest(
        reverse_request
    )
    assert evaluate_conformance(forward_request) == evaluate_conformance(reverse_request)


def test_maximum_observation_evidence_is_compacted_in_output() -> None:
    base = build_scenario_request("canonical")
    added_fields = tuple(
        ProtocolFieldDefinition(
            field_id=f"supplemental_field_{index}",
            label=f"Supplemental field {index}",
            value_kind=ValueKind.TEXT,
            required=True,
            min_items=1,
            max_items=1,
        )
        for index in range(65)
    )
    schema = base.protocol_schema.model_copy(
        update={"fields": (*base.protocol_schema.fields, *added_fields)}
    )
    profile = ConformanceProfile(
        **{
            **base.conformance_profile.model_dump(mode="python"),
            "schema_digest": schema_digest(schema),
            "max_observations": 128,
        }
    )
    configuration = configuration_digest(schema, profile)
    approved = base.context.references.approved_configuration
    approved = approved.model_copy(
        update={
            "evidence": approved.evidence.model_copy(
                update={"digest": configuration}
            )
        }
    )
    references = base.context.references.model_copy(
        update={"approved_configuration": approved}
    )
    context = base.context.model_copy(update={"references": references})

    def evidence(field_index: int) -> tuple[ArtifactReference, ...]:
        return tuple(
            ArtifactReference(
                artifact_id=f"artifact.supplemental.{field_index}.{item_index}",
                version="1.0.0",
                digest=sha256_digest(
                    {"field": field_index, "evidence": item_index}
                ),
                media_type="application/json",
            )
            for item_index in range(64)
        )

    added_observations = tuple(
        FieldObservation(
            observation_id=f"observation.supplemental.{index}",
            field_id=field.field_id,
            state=ObservationState.OBSERVED,
            values=(f"value-{index}",),
            evidence=evidence(index),
        )
        for index, field in enumerate(added_fields)
    )
    request = EvaluateConformanceRequest(
        context=context,
        protocol_schema=schema,
        conformance_profile=profile,
        observations=(*base.observations, *added_observations),
    )

    result = evaluate_conformance(request)

    assert result.disposition is ConformanceDisposition.CONFORMANT
    references = request.context.references
    expected_evidence = {
        references.approved_configuration.evidence,
        references.identity_lineage.evidence,
        references.provenance.evidence,
        references.consent.evidence,
        references.quality.evidence,
        references.support.evidence,
        references.intended_use.evidence,
        request.protocol_schema.evidence,
        request.conformance_profile.evidence,
        *(item.evidence for item in request.protocol_schema.vocabularies),
        *(item.evidence for item in request.protocol_schema.units),
    }
    assert {item.reference for item in result.evidence} == expected_evidence
    assert request.observations[-1].evidence[0].digest not in {
        item.reference.digest for item in result.evidence
    }
    assert canonical_request_digest(request) in result.provenance.input_digests


def test_service_and_raw_json_plugin_replay_identically() -> None:
    request = build_scenario_request("canonical")
    service = M0201Service()
    plugin = M0201Plugin(service)

    expected = service.execute(request)
    token = plugin.validate(request.model_dump_json())

    assert plugin.run(token) == expected
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M02-01"
    with pytest.raises(TypeError):
        plugin.run(cast("ValidatedM0201Request", object()))


def test_authorization_rejects_before_observation_traversal() -> None:
    payload = build_scenario_request("canonical").model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["observations"] = cast("Mapping[str, object]", object())

    with pytest.raises(ConformanceAuthorizationError):
        preflight_conformance_authorization(payload)
