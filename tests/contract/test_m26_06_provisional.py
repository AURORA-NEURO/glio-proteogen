"""Focused schema and security-control smoke for provisional M26-06."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from glio_proteogen.contracts.m26_06 import (
    M2606_DOSSIER_SHA256,
    M2606_DOSSIER_SLICE,
    M2606_M2605_INPUT_MEDIA_TYPE,
    M2606_OUTPUT_MEDIA_TYPE,
    M2606_PROVISIONAL_ABI,
    AccessDecisionState,
    ControlStatus,
    EvaluateProteomicsSecurityAccessRequest,
    SecurityAssessmentStatus,
    SecurityControlCheck,
    SecurityControlDeclaration,
    SecurityControlKind,
    SecurityFinding,
    SecurityFindingCode,
    SecurityFindingSeverity,
    SecurityPostureRecord,
    SecurityPostureStatus,
    contract_json_schemas,
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

_SCHEMA_COUNT = 8
_CONTROL_COUNT = 8


def test_provisional_schemas_require_security_and_safe_failure_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "access-decision",
        "audit-event",
        "posture",
        "control",
        "finding",
        "safe-failure",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["leastPrivilegeRequired"] is True
        assert metadata["consentEnforcementRequired"] is True
        assert metadata["deIdentificationRequired"] is True
        assert metadata["auditRequired"] is True
        assert metadata["threatDetectionRequired"] is True
        assert metadata["safeFailureRequired"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "protein subtype"
        assert metadata["upstreamInputMediaType"] == M2606_M2605_INPUT_MEDIA_TYPE
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2606_OUTPUT_MEDIA_TYPE
    assert M2606_PROVISIONAL_ABI is True


def test_security_states_and_all_required_controls_are_explicit() -> None:
    assert len(tuple(SecurityControlKind)) == _CONTROL_COUNT
    assert AccessDecisionState.ABSTAIN_UNSUPPORTED.value == "abstain_unsupported"
    assert SecurityAssessmentStatus.ABSTAINED.value == "abstained"
    assert SecurityPostureStatus.NOT_EVALUABLE.value == "not_evaluable"


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2606.artifact.{label}",
        version="1.0.0",
        digest="sha256:" + (label.encode().hex() * 64)[:64],
        media_type="application/json",
    )


def _context() -> ExecutionContext:
    def decision(label: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"m2606.decision.{label}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control.{label}"),
        )

    return ExecutionContext(
        request_id="m2606.request.contract",
        actor_id="m2606.actor.contract",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2606.decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_artifact("identity").digest,
                evidence=_artifact("identity.evidence"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="m2606.decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended.use"),
        ),
    )


def _request() -> EvaluateProteomicsSecurityAccessRequest:
    source = _artifact("source")
    evidence = EvidenceReference(reference=source, role="evidence", claim="Control evidence.")
    return EvaluateProteomicsSecurityAccessRequest(
        request_id="m2606.request.contract",
        context=_context(),
        upstream_result=ArtifactReference(
            artifact_id="m2605.result",
            version="0.1.0-provisional",
            digest="sha256:" + "a" * 64,
            media_type="application/vnd.glio-proteogen.m26-05+json",
        ),
        principal="principal.reviewer",
        resource="resource.proteome",
        action="read",
        policy_version="1.0.0",
        requested_controls=tuple(SecurityControlKind),
        control_declarations=tuple(
            SecurityControlDeclaration(
                control=control,
                status=ControlStatus.PASSED,
                rationale="Caller supplied control evidence.",
                evidence=(evidence,),
            )
            for control in SecurityControlKind
        ),
        consent_reference=_artifact("consent.reference"),
        source_artifacts=(source,),
    )


def test_authority_and_request_require_exact_control_set() -> None:
    request = _request()
    assert M2606_DOSSIER_SHA256.endswith("da181")
    assert M2606_DOSSIER_SLICE.endswith(":9256-9296")
    with pytest.raises(ValidationError, match="at least 8 items"):
        type(request).model_validate(
            request.model_copy(update={"requested_controls": tuple(SecurityControlKind)[:-1]})
        )


def test_posture_status_cannot_overstate_failed_or_unresolved_controls() -> None:
    evidence = EvidenceReference(
        reference=_artifact("posture"), role="evidence", claim="Control evidence."
    )
    controls = tuple(
        SecurityControlCheck(
            control=control,
            status=ControlStatus.FAILED
            if control is SecurityControlKind.CONSENT
            else ControlStatus.PASSED,
            rationale="Consent evidence is withheld."
            if control is SecurityControlKind.CONSENT
            else "Control passed.",
            evidence=(evidence,),
        )
        for control in SecurityControlKind
    )
    with pytest.raises(ValidationError, match="compliant posture"):
        SecurityPostureRecord(
            posture_id="posture.m2606.invalid",
            version="0.1.0-provisional",
            status=SecurityPostureStatus.COMPLIANT,
            controls=controls,
            evidence=(evidence,),
        )


def test_severe_finding_requires_evidence_and_schema_metadata_is_explicit() -> None:
    with pytest.raises(ValidationError, match="Field required"):
        SecurityFinding(
            finding_id="finding.m2606.unreferenced",
            code=SecurityFindingCode.THREAT_DETECTED,
            severity=SecurityFindingSeverity.CRITICAL,
            message="Threat evidence is missing.",
        )
    metadata = cast("dict[str, Any]", contract_json_schemas()["output"]["x-glio-contract"])
    assert metadata["rawPayload"] is False
    assert metadata["unsupportedToNegative"] is False
