"""Focused public-contract checks for M01-04 quality computation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from glio_proteogen.contracts.m01_04 import (
    AnalyteLevel,
    AssayProfile,
    AssayType,
    Computation,
    ComputeQualityMetricsRequest,
    MetricCategory,
    MetricDefinition,
    MetricState,
    MetricStatus,
    Observation,
    Provenance,
    QualityComputationPolicy,
    QualityDisposition,
    QualityMetric,
    QualityProfile,
    canonical_request_digest,
    contract_json_schema,
    policy_digest,
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
from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics import (
    compute_quality_profile,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m01_04.schema import ContractName

pytestmark = pytest.mark.contract


def _digest(label: str) -> str:
    return sha256_digest({"m0104": label})


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=digest or _digest(label),
        media_type="application/json",
    )


def _policy() -> QualityComputationPolicy:
    return QualityComputationPolicy(
        policy_id="policy.quality",
        version="1.0.0",
        enabled_categories=tuple(MetricCategory),
    )


def _context(policy: QualityComputationPolicy) -> ExecutionContext:
    def decision(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role, digest),
        )

    return ExecutionContext(
        request_id="request.quality",
        actor_id="actor.test",
        occurred_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", policy_digest(policy)),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity-lineage",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_digest("identity-binding"),
                evidence=_artifact("identity-lineage"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _request() -> ComputeQualityMetricsRequest:
    policy = _policy()
    profile = AssayProfile(
        profile_id="assay.dia.protein",
        version="1.0.0",
        assay_type=AssayType.DIA,
        analyte_level=AnalyteLevel.PROTEIN,
        required_metric_ids=("metric.coverage",),
        evidence=_artifact("assay-profile"),
    )
    definition = MetricDefinition(
        metric_id="metric.coverage",
        version="1.0.0",
        category=MetricCategory.COVERAGE,
        computation=Computation.DIRECT,
        unit="%",
        observation_ids=("observation.coverage",),
        pass_minimum=80.0,
        warning_minimum=60.0,
    )
    observation = Observation(
        observation_id="observation.coverage",
        state=MetricState.OBSERVED,
        value=92.0,
        unit="%",
        evidence=(_artifact("coverage"),),
    )
    return ComputeQualityMetricsRequest(
        context=_context(policy),
        assay_profile=profile,
        policy=policy,
        metric_definitions=(definition,),
        observations=(observation,),
    )


@pytest.mark.parametrize(
    "name",
    [
        "request",
        "output",
        "policy",
        "assay_profile",
        "metric_definition",
        "observation",
        "quality_metric",
    ],
)
def test_public_schema_is_valid_draft_2020_12(name: ContractName) -> None:
    schema = contract_json_schema(name)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].endswith(f":{name}")
    Draft202012Validator.check_schema(schema)


def test_request_digest_ignores_semantically_unordered_input_order() -> None:
    request = _request()
    reversed_policy = request.policy.model_copy(
        update={"enabled_categories": tuple(reversed(request.policy.enabled_categories))}
    )
    reordered = request.model_copy(update={"policy": reversed_policy})

    assert canonical_request_digest(reordered) == canonical_request_digest(request)


def test_missing_observation_never_carries_numeric_zero() -> None:
    with pytest.raises(ValidationError, match="non-observed quality input cannot carry a value"):
        Observation(
            observation_id="observation.missing",
            state=MetricState.MISSING,
            value=0.0,
            evidence=(_artifact("missing"),),
        )


def test_ratio_definition_requires_two_observations() -> None:
    with pytest.raises(ValidationError, match="invalid observation cardinality"):
        MetricDefinition(
            metric_id="metric.ratio",
            version="1.0.0",
            category=MetricCategory.COMPLETENESS,
            computation=Computation.RATIO,
            unit="%",
            observation_ids=("observation.only",),
            pass_minimum=0.9,
        )


def test_request_rejects_unbound_observation_reference() -> None:
    request = _request()
    definition = request.metric_definitions[0].model_copy(
        update={"observation_ids": ("observation.unknown",)}
    )

    with pytest.raises(ValidationError, match="unknown observation"):
        ComputeQualityMetricsRequest(
            context=request.context,
            assay_profile=request.assay_profile,
            policy=request.policy,
            metric_definitions=(definition,),
            observations=request.observations,
        )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda values: values.update(required_metric_ids=("metric.coverage",) * 2),
        lambda values: values.update(
            evidence=(values["evidence"], values["evidence"]),
        ),
    ],
)
def test_assay_profile_collections_are_closed(mutator: object) -> None:
    profile = _request().assay_profile.model_dump(mode="python")
    if callable(mutator):
        mutator(profile)

    with pytest.raises(ValidationError):
        AssayProfile.model_validate(profile, strict=True)


@pytest.mark.parametrize(
    "updates",
    [
        {"observation_ids": ("observation.coverage", "observation.coverage")},
        {"observation_ids": ("one", "two")},
        {"computation": Computation.DETECTION_MARGIN, "reference_value": None},
        {"computation": Computation.RELATIVE_ERROR, "reference_value": 0.0},
        {"computation": Computation.BOOLEAN_MATCH, "reference_value": 1.0},
        {"pass_minimum": None, "pass_maximum": None},
        {"pass_minimum": 2.0, "pass_maximum": 1.0},
        {"pass_minimum": 0.8, "warning_minimum": 0.9},
    ],
)
def test_metric_definition_rejects_incoherent_shapes(
    updates: dict[str, object],
) -> None:
    values = _request().metric_definitions[0].model_dump(mode="python")
    values.update(updates)

    with pytest.raises(ValidationError):
        MetricDefinition.model_validate(values, strict=True)


@pytest.mark.parametrize(
    "updates",
    [
        {"state": MetricState.OBSERVED, "value": None},
        {"state": MetricState.MISSING, "value": 0.0},
        {"state": MetricState.BELOW_DETECTION, "value": None, "detection_limit": None},
        {"state": MetricState.OBSERVED, "value": 1.0, "detection_limit": 0.5},
    ],
)
def test_observation_state_is_explicit(updates: dict[str, object]) -> None:
    values = _request().observations[0].model_dump(mode="python")
    values.update(updates)

    with pytest.raises(ValidationError):
        Observation.model_validate(values, strict=True)


def test_metric_provenance_closes_positional_bindings() -> None:
    result = compute_quality_profile(_request())
    provenance = result.metrics[0].provenance.model_dump(mode="python")

    for observation_ids, observation_digests in (
        (("one", "two"), provenance["observation_digests"]),
        (("one", "one"), provenance["observation_digests"] * 2),
    ):
        with pytest.raises(ValidationError):
            Provenance.model_validate(
                {
                    **provenance,
                    "observation_ids": observation_ids,
                    "observation_digests": observation_digests,
                },
                strict=True,
            )


@pytest.mark.parametrize(
    "updates",
    [
        {"value": None},
        {"status": MetricStatus.NOT_EVALUABLE},
        {"state": MetricState.MISSING, "value": 1.0},
    ],
)
def test_quality_metric_state_cannot_be_forged(updates: dict[str, object]) -> None:
    metric = compute_quality_profile(_request()).metrics[0].model_dump(mode="python")
    metric.update(updates)

    with pytest.raises(ValidationError):
        QualityMetric.model_validate(metric, strict=True)


def test_policy_and_request_identifiers_are_unique() -> None:
    request = _request()
    policy = request.policy.model_dump(mode="python")
    policy["enabled_categories"] = (MetricCategory.COVERAGE, MetricCategory.COVERAGE)
    with pytest.raises(ValidationError):
        QualityComputationPolicy.model_validate(policy, strict=True)

    request_values = request.model_dump(mode="python")
    request_values["metric_definitions"] = request_values["metric_definitions"] * 2
    with pytest.raises(ValidationError):
        ComputeQualityMetricsRequest.model_validate(request_values, strict=True)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quality_profile_id", "quality.m0104.wrong"),
        ("result_digest", _digest("wrong-result")),
        ("disposition", QualityDisposition.QUARANTINED),
    ],
)
def test_quality_profile_rejects_forged_envelope(field: str, value: object) -> None:
    profile = compute_quality_profile(_request()).model_dump(mode="python")
    profile[field] = value

    with pytest.raises(ValidationError):
        QualityProfile.model_validate(profile, strict=True)


@pytest.mark.parametrize("role", ["consent", "identity_lineage", "quality"])
def test_quality_request_requires_authorized_controls(role: str) -> None:
    request = _request()
    references = request.context.references.model_dump(mode="python")
    if role == "consent":
        references[role]["state"] = ConsentState.REVOKED
    elif role == "identity_lineage":
        references[role]["state"] = IdentityLineageState.UNRESOLVED
    else:
        references[role]["state"] = UpstreamDecisionState.REJECTED
    context = request.context.model_dump(mode="python")
    context["references"] = references
    values = request.model_dump(mode="python")
    values["context"] = context

    with pytest.raises(ValidationError):
        ComputeQualityMetricsRequest.model_validate(values, strict=True)
