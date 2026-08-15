"""Contract and schema invariants for provisional M15-07."""

# ruff: noqa: PLR2004

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m15_07 import (
    M1507_M1506_RESULT_MEDIA_TYPE,
    AdjudicateComplexActivityPlausibilityRequest,
    ComplexActivityPlausibilityAdjudicationResult,
    ControlEvaluation,
    ControlKind,
    ControlOutcome,
    PlausibilityAdjudicationStatus,
    PlausibilityControl,
    PlausibilityGrade,
    contract_json_schemas,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportDecision,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1507": label}),
        media_type=media_type,
    )


def _context(*, accepted: bool = True) -> ExecutionContext:
    decision = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    return ExecutionContext(
        request_id="request.m1507",
        actor_id="actor.test",
        occurred_at=_WHEN,
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="decision.configuration",
                state=decision,
                policy_version="1.0.0",
                evidence=_artifact("configuration"),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=identity,
                policy_version="1.0.0",
                binding_digest=sha256_digest("identity"),
                evidence=_artifact("identity"),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="decision.provenance",
                state=decision,
                policy_version="1.0.0",
                evidence=_artifact("provenance"),
            ),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=consent,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="decision.quality",
                state=decision,
                policy_version="1.0.0",
                evidence=_artifact("quality"),
            ),
            support=UpstreamDecisionReference(
                decision_id="decision.support",
                state=decision,
                policy_version="1.0.0",
                evidence=_artifact("support"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="decision.intended",
                state=decision,
                policy_version="1.0.0",
                evidence=_artifact("intended"),
            ),
        ),
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label), role="evidence", claim=f"Evidence {label}."
    )


def _request(*, accepted: bool = True) -> AdjudicateComplexActivityPlausibilityRequest:
    controls = tuple(
        PlausibilityControl(
            control_id=f"control.{kind.value}",
            kind=kind,
            criterion=f"Criterion for {kind.value}",
            expected_direction="increasing" if kind is ControlKind.DIRECTION else None,
            required_evidence=(_evidence(kind.value),),
        )
        for kind in ControlKind
    )
    return AdjudicateComplexActivityPlausibilityRequest(
        request_id="request.m1507",
        context=_context(accepted=accepted),
        sensitivity_result=_artifact("sensitivity", M1507_M1506_RESULT_MEDIA_TYPE),
        controls=controls,
        source_artifacts=(_artifact("proteome"), _artifact("transcript"), _artifact("ptm")),
    )


def test_schema_metadata_and_control_catalogue_are_locked() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == ("request", "output", "control", "evaluation", "conflict", "finding")
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    metadata = schemas["output"]["x-glio-contract"]
    assert metadata["failedControlsBlockRelease"] is True
    assert metadata["negativeControlRequired"] is True
    assert metadata["conflictsPreserved"] is True


def test_request_binds_sensitivity_and_requires_unique_controls() -> None:
    request = _request()
    assert request.sensitivity_result.media_type == M1507_M1506_RESULT_MEDIA_TYPE
    duplicate = request.controls[0].model_copy(
        update={"control_id": request.controls[1].control_id}
    )
    with pytest.raises(ValidationError, match="control ids must be unique"):
        AdjudicateComplexActivityPlausibilityRequest.model_validate(
            request.model_dump(mode="python")
            | {
                "controls": (
                    request.controls[0],
                    request.controls[1],
                    duplicate,
                    *request.controls[2:],
                )
            }
        )
    with pytest.raises(ValidationError, match="bind the provisional M15-06"):
        AdjudicateComplexActivityPlausibilityRequest.model_validate(
            request.model_dump(mode="python") | {"sensitivity_result": _artifact("wrong")}
        )


def test_uncertainty_and_provenance_expose_required_dimensions() -> None:
    request = _request()
    digest = sha256_digest(request.model_dump(mode="json"))
    profile = expected_uncertainty(supported=True)
    assert profile.measurement.probability == 0.9
    assert profile.transport.state.value == "estimated"
    provenance = expected_provenance(request, digest)
    assert len(provenance.control_decisions) == 7
    assert provenance.input_digests[0] == digest


def test_result_closure_rejects_missing_evaluation_or_invalid_status() -> None:
    request = _request()
    digest = sha256_digest(request.model_dump(mode="json"))
    evaluations = tuple(
        ControlEvaluation(
            control_id=control.control_id,
            outcome=ControlOutcome.PASSED,
            rationale="Control passed.",
            evidence=control.required_evidence,
        )
        for control in request.controls
    )
    payload = {
        "result_id": f"result.{digest.removeprefix('sha256:')}",
        "request_digest": digest,
        "result_digest": sha256_digest("placeholder"),
        "request": request,
        "status": PlausibilityAdjudicationStatus.ADJUDICATED,
        "grade": PlausibilityGrade.HIGH,
        "evaluations": evaluations,
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="supported",
            rationale="All controls passed.",
        ),
        "uncertainty": expected_uncertainty(supported=True),
        "provenance": expected_provenance(request, digest),
        "evidence": (_evidence("sensitivity"),),
        "limitations": ({"code": "provisional", "statement": "Provisional."},),
        "human_review_required": False,
    }
    with pytest.raises(ValidationError, match="result digest"):
        ComplexActivityPlausibilityAdjudicationResult.model_construct(**payload).model_validate(
            payload
        )
    with pytest.raises(ValidationError, match="every control"):
        ComplexActivityPlausibilityAdjudicationResult.model_validate(
            {**payload, "evaluations": evaluations[:-1]}
        )
