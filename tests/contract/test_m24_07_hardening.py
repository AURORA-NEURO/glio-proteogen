"""Adversarial contract closure for the provisional M24-07 ABI."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m24_07 import (
    M2407_M2406_INPUT_MEDIA_TYPE,
    M2407_OUTPUT_MEDIA_TYPE,
    EvaluateBiomarkerPanelHumanFactorsRequest,
    FallbackScenario,
    OperationalConfiguration,
    OperationalDimension,
    OperationalMetric,
    OperationalStatus,
    canonical_request_digest,
    result_identifier,
)
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


def artifact(seed: str = "a") -> ArtifactReference:
    digest_seed = seed[0] if seed and seed[0] in "0123456789abcdef" else "a"
    return ArtifactReference(
        artifact_id=f"m2407.evidence.{seed}",
        version="1.0.0",
        digest="sha256:" + digest_seed * 64,
        media_type="application/vnd.glio-proteogen.evidence+json",
    )


def evidence(seed: str = "a") -> tuple[EvidenceReference, ...]:
    reference = ArtifactReference(
        artifact_id=f"m2407.evidence.{seed}",
        version="1.0.0",
        digest="sha256:" + (seed[0] if seed and seed[0] in "0123456789abcdef" else "a") * 64,
        media_type="application/vnd.glio-proteogen.evidence+json",
    )
    return (EvidenceReference(reference=reference, role="evidence", claim="caller material"),)


def context() -> ExecutionContext:
    def decision(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"m2407.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=artifact(role[0]),
        )

    return ExecutionContext(
        request_id="m2407.context.request",
        actor_id="m2407.actor",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2407.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=artifact("b"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="m2407.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifact("c"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intendeduse"),
        ),
    )


def metric(dimension: OperationalDimension, metric_id: str | None = None) -> OperationalMetric:
    return OperationalMetric(
        metric_id=metric_id or f"m2407.metric.{dimension.value}",
        dimension=dimension,
        metric_name=f"{dimension.value} score",
        observed_value=1.0,
        target_value=1.0,
        tolerance=0.1,
        sample_size=10,
        status=OperationalStatus.PASS,
        evidence=evidence(dimension.value[0]),
    )


def fallback(dimension: OperationalDimension) -> FallbackScenario:
    return FallbackScenario(
        scenario_id=f"m2407.fallback.{dimension.value}",
        dimension=dimension,
        trigger=f"{dimension.value} unavailable",
        fallback_path="review and abstain",
        recovery_seconds=3.0,
        fallback_available=True,
        status=OperationalStatus.PASS,
        evidence=evidence(dimension.value[-1]),
    )


def configuration() -> OperationalConfiguration:
    return OperationalConfiguration(
        configuration_id="m2407.config.locked",
        version="1.0.0",
        required_dimensions=tuple(OperationalDimension),
        evidence=evidence("d"),
    )


def upstream_result() -> ArtifactReference:
    return ArtifactReference(
        artifact_id="m2406.challenge.result",
        version="0.1.0-provisional",
        digest="sha256:" + "e" * 64,
        media_type=M2407_M2406_INPUT_MEDIA_TYPE,
    )


def request() -> dict[str, object]:
    return {
        "operation": "evaluate_biomarker_panel_human_factors_operational",
        "contract_version": "0.1.0-provisional",
        "request_id": "m2407.request.valid",
        "context": context().model_dump(mode="json"),
        "upstream_result": upstream_result().model_dump(mode="json"),
        "metrics": [metric(d).model_dump(mode="json") for d in OperationalDimension],
        "fallbacks": [
            fallback(d).model_dump(mode="json")
            for d in (
                OperationalDimension.DOWNTIME,
                OperationalDimension.RECOVERY,
                OperationalDimension.FALLBACK,
            )
        ],
        "configuration": configuration().model_dump(mode="json"),
        "source_artifacts": [upstream_result().model_dump(mode="json")],
    }


def test_request_fixture_is_canonical_and_result_identity_is_deterministic() -> None:
    typed = EvaluateBiomarkerPanelHumanFactorsRequest.model_validate_json(
        json.dumps(request()), strict=True
    )
    assert canonical_request_digest(typed).startswith("sha256:")
    assert result_identifier(typed).startswith("m2407.result.")
    assert M2407_OUTPUT_MEDIA_TYPE.endswith("+json")


def test_pass_metric_must_satisfy_declared_tolerance() -> None:
    with pytest.raises(ValidationError, match="within its declared tolerance"):
        OperationalMetric.model_validate(
            metric(OperationalDimension.LATENCY).model_dump()
            | {"observed_value": 2.0, "target_value": 1.0, "tolerance": 0.1},
            strict=True,
        )


def test_not_evaluable_metric_requires_zero_sample_size() -> None:
    with pytest.raises(ValidationError, match="not-evaluable metric"):
        OperationalMetric(
            metric_id="m2407.metric.missing",
            dimension=OperationalDimension.LATENCY,
            metric_name="latency",
            observed_value=0.0,
            target_value=1.0,
            tolerance=0.1,
            sample_size=1,
            status=OperationalStatus.NOT_EVALUABLE,
            evidence=evidence("f"),
        )


def test_configuration_requires_exactly_all_dimensions() -> None:
    with pytest.raises(ValidationError, match="all operational dimensions"):
        OperationalConfiguration(
            configuration_id="m2407.config.partial",
            version="1.0.0",
            required_dimensions=(OperationalDimension.LATENCY,) * 7,
            evidence=evidence("g"),
        )


def test_fallback_recovery_is_bounded_and_pass_requires_availability() -> None:
    with pytest.raises(ValidationError, match="unavailable fallback"):
        FallbackScenario.model_validate(
            fallback(OperationalDimension.FALLBACK).model_dump()
            | {"fallback_available": False, "status": OperationalStatus.PASS},
            strict=True,
        )
    with pytest.raises(ValidationError):
        FallbackScenario.model_validate(
            fallback(OperationalDimension.RECOVERY).model_dump() | {"recovery_seconds": 86_401.0},
            strict=True,
        )


def test_hostile_unknown_contract_field_is_rejected() -> None:
    payload = request()
    payload["unknown"] = True
    with pytest.raises(ValidationError):
        EvaluateBiomarkerPanelHumanFactorsRequest.model_validate(payload, strict=True)
