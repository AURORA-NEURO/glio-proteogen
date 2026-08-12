"""Compact public-contract checks for M02-01 protocol conformance."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import ValidationError

from glio_proteogen.contracts.m02_01 import (
    AllowedTermPair,
    AllowedTermPairRule,
    ConditionalStateRule,
    ConformanceProfile,
    EvaluateConformanceRequest,
    FieldObservation,
    ObservationState,
    ProtocolFieldDefinition,
    ProtocolSchema,
    RuleAction,
    TermInSetRule,
    ValueKind,
    VocabularyDefinition,
    configuration_digest,
    contract_json_schema,
    schema_digest,
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
from glio_proteogen.modules.c02_identification_qc.m02_01_protocol_metadata import (
    evaluate_conformance,
)

pytestmark = pytest.mark.contract


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"m0201": label}),
        media_type="application/json",
    )


def _context(configuration: str) -> ExecutionContext:
    def decision(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role, digest),
        )

    return ExecutionContext(
        request_id="request.synthetic.m0201",
        actor_id="actor.synthetic.contract",
        occurred_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", configuration),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"m0201": "subject"}),
                evidence=_artifact("identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _schema() -> ProtocolSchema:
    vocab = VocabularyDefinition(
        vocabulary_id="vocabulary.assay",
        version="1.0.0",
        terms=("label_free", "tmt"),
        evidence=_artifact("vocabulary"),
    )
    specimen = VocabularyDefinition(
        vocabulary_id="vocabulary.specimen",
        version="1.0.0",
        terms=("fresh_frozen", "ffpe"),
        evidence=_artifact("specimen-vocabulary"),
    )
    fields = (
        ProtocolFieldDefinition(
            field_id="field.assay",
            label="Assay",
            value_kind=ValueKind.TERM,
            required=True,
            min_items=1,
            max_items=1,
            vocabulary_id=vocab.vocabulary_id,
        ),
        ProtocolFieldDefinition(
            field_id="field.specimen",
            label="Specimen",
            value_kind=ValueKind.TERM,
            required=True,
            min_items=1,
            max_items=1,
            vocabulary_id=specimen.vocabulary_id,
        ),
        ProtocolFieldDefinition(
            field_id="field.channel",
            label="Channel",
            value_kind=ValueKind.TEXT,
            required=False,
            min_items=0,
            max_items=1,
            allow_not_applicable=True,
        ),
    )
    return ProtocolSchema(
        schema_id="schema.synthetic.m0201",
        version="1.0.0",
        assay_type="mass_spectrometry",
        specimen_type="glioma_tissue",
        fields=fields,
        vocabularies=(vocab, specimen),
        compatibility_rules=(
            TermInSetRule(
                rule_id="rule.assay",
                field_id="field.assay",
                action=RuleAction.QUARANTINE,
                reason_code="assay_unsupported",
                remediation_code="select_supported_assay",
                allowed_terms=vocab.terms,
            ),
            ConditionalStateRule(
                rule_id="rule.label-free-channel",
                field_id="field.channel",
                action=RuleAction.REVIEW,
                reason_code="channel_state_invalid",
                remediation_code="review_channel_metadata",
                trigger_field_id="field.assay",
                trigger_terms=("label_free",),
                required_state=ObservationState.NOT_APPLICABLE,
            ),
            AllowedTermPairRule(
                rule_id="rule.assay-specimen",
                field_id="field.assay",
                action=RuleAction.QUARANTINE,
                reason_code="combination_unsupported",
                remediation_code="select_supported_combination",
                other_field_id="field.specimen",
                allowed_pairs=(AllowedTermPair(left="label_free", right="fresh_frozen"),),
            ),
        ),
        evidence=_artifact("schema"),
    )


def _request() -> EvaluateConformanceRequest:
    schema = _schema()
    profile = ConformanceProfile(
        profile_id="profile.synthetic.m0201",
        version="1.0.0",
        schema_id=schema.schema_id,
        schema_version=schema.version,
        schema_digest=schema_digest(schema),
        evidence=_artifact("profile"),
    )
    observations = (
        FieldObservation(
            observation_id="observation.assay",
            field_id="field.assay",
            state=ObservationState.OBSERVED,
            values=("label_free",),
            evidence=(_artifact("observation.assay"),),
        ),
        FieldObservation(
            observation_id="observation.specimen",
            field_id="field.specimen",
            state=ObservationState.OBSERVED,
            values=("fresh_frozen",),
            evidence=(_artifact("observation.specimen"),),
        ),
        FieldObservation(
            observation_id="observation.channel",
            field_id="field.channel",
            state=ObservationState.NOT_APPLICABLE,
            evidence=(_artifact("observation.channel"),),
        ),
    )
    return EvaluateConformanceRequest(
        context=_context(configuration_digest(schema, profile)),
        protocol_schema=schema,
        conformance_profile=profile,
        observations=observations,
    )


@pytest.mark.parametrize("name", ["request", "output", "schema", "profile", "observation"])
def test_public_schemas_are_valid_draft_2020_12(name: str) -> None:
    exported = contract_json_schema(name)  # type: ignore[arg-type]

    assert exported["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(exported)


def test_schema_profile_and_request_are_pinned_and_canonical() -> None:
    request = _request()

    assert request.conformance_profile.schema_digest == schema_digest(request.protocol_schema)
    assert request.observations[2].state is ObservationState.NOT_APPLICABLE


def test_nested_set_order_does_not_change_schema_digest() -> None:
    schema = _schema()
    values = schema.model_dump(mode="python")
    for vocabulary in values["vocabularies"]:
        vocabulary["terms"] = tuple(reversed(vocabulary["terms"]))
    for rule in values["compatibility_rules"]:
        for key in ("allowed_terms", "trigger_terms", "allowed_pairs"):
            if key in rule:
                rule[key] = tuple(reversed(rule[key]))
    reordered = ProtocolSchema.model_validate(values, strict=True)

    assert schema_digest(reordered) == schema_digest(schema)


def test_request_rejects_duplicate_field_observations_and_unpinned_profile() -> None:
    request = _request()
    values = request.model_dump(mode="python")
    values["observations"][1]["field_id"] = values["observations"][0]["field_id"]
    with pytest.raises(ValidationError, match="only one observation"):
        EvaluateConformanceRequest.model_validate(values, strict=True)

    values = request.model_dump(mode="python")
    values["conformance_profile"]["schema_digest"] = "sha256:" + ("f" * 64)
    with pytest.raises(ValidationError, match="does not pin"):
        EvaluateConformanceRequest.model_validate(values, strict=True)


def test_rules_reject_unknown_vocabulary_terms() -> None:
    values = _schema().model_dump(mode="python")
    pair = next(
        rule
        for rule in values["compatibility_rules"]
        if rule["kind"] == "allowed_term_pair"
    )
    pair["allowed_pairs"][0]["right"] = "unknown_specimen"

    with pytest.raises(ValidationError, match="belong to their vocabularies"):
        ProtocolSchema.model_validate(values, strict=True)


def test_public_output_rejects_duplicate_evidence() -> None:
    result = evaluate_conformance(_request())
    values = result.model_dump(mode="python")
    values["evidence"] = (*values["evidence"], values["evidence"][0])
    values["evaluation_digest"] = "sha256:" + ("0" * 64)

    with pytest.raises(ValidationError, match="evidence must be unique"):
        type(result).model_validate(values, strict=True)
