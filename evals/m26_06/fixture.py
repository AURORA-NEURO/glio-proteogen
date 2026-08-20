"""Frozen, synthetic M26-06 request fixtures with no protected content."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from glio_proteogen.contracts.m26_06 import (
    ControlStatus,
    EvaluateProteomicsSecurityAccessRequest,
    SecurityControlDeclaration,
    SecurityControlKind,
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

SCENARIO_PATH = Path(__file__).parents[2] / "tests" / "fixtures" / "m26_06" / "scenarios.json"


def artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2606.fixture.{label}",
        version="1.0.0",
        digest="sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest(),
        media_type="application/json",
    )


def _context(request_id: str, consent: ConsentState) -> ExecutionContext:
    def decision(label: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"m2606.fixture.decision.{label}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=artifact(f"control.{label}"),
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="m2606.fixture.actor",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2606.fixture.decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=artifact("identity").digest,
                evidence=artifact("identity.evidence"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="m2606.fixture.decision.consent",
                state=consent,
                policy_version="1.0.0",
                evidence=artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended.use"),
        ),
    )


def request_for(
    scenario_id: str,
    control_mode: str = "passed",
    consent: str = "granted",
) -> EvaluateProteomicsSecurityAccessRequest:
    request_id = f"m2606.fixture.request.{scenario_id}"
    source = artifact(f"source.{scenario_id}")
    evidence = EvidenceReference(
        reference=source,
        role="evidence",
        claim="Synthetic caller-declared security evidence.",
    )
    statuses: dict[SecurityControlKind, ControlStatus] = dict.fromkeys(
        SecurityControlKind, ControlStatus.PASSED
    )
    if control_mode == "least_privilege_failed":
        statuses[SecurityControlKind.LEAST_PRIVILEGE] = ControlStatus.FAILED
    elif control_mode == "threat_detection_failed":
        statuses[SecurityControlKind.THREAT_DETECTION] = ControlStatus.FAILED
    elif control_mode == "encryption_unknown":
        statuses[SecurityControlKind.ENCRYPTION] = ControlStatus.NOT_EVALUABLE
    elif control_mode == "audit_review":
        statuses[SecurityControlKind.AUDIT] = ControlStatus.REVIEW_REQUIRED
    elif control_mode != "passed":
        raise ValueError(f"unknown synthetic control mode: {control_mode}")  # noqa: TRY003
    declarations = tuple(
        SecurityControlDeclaration(
            control=control,
            status=statuses[control],
            rationale=(
                "Synthetic control evidence passed."
                if statuses[control] is ControlStatus.PASSED
                else "Synthetic fixture deliberately leaves this control unresolved."
            ),
            evidence=(evidence,),
        )
        for control in SecurityControlKind
    )
    consent_state = ConsentState.GRANTED if consent == "granted" else ConsentState.REVOKED
    return EvaluateProteomicsSecurityAccessRequest(
        request_id=request_id,
        context=_context(request_id, consent_state),
        upstream_result=ArtifactReference(
            artifact_id="m2605.fixture.result",
            version="0.1.0-provisional",
            digest="sha256:" + "b" * 64,
            media_type="application/vnd.glio-proteogen.m26-05+json",
        ),
        principal="m2606.fixture.principal",
        resource="m2606.fixture.resource",
        action="read",
        policy_version="1.0.0",
        requested_controls=tuple(SecurityControlKind),
        control_declarations=declarations,
        consent_reference=artifact("consent"),
        source_artifacts=(source,),
    )


def load_scenarios() -> list[dict[str, Any]]:
    decoded: object = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    if not isinstance(decoded, list) or not all(isinstance(item, dict) for item in decoded):
        raise ValueError("M26-06 scenario fixture must be a list of objects")  # noqa: TRY003
    return [cast("dict[str, Any]", item) for item in decoded]


__all__ = ["SCENARIO_PATH", "artifact", "load_scenarios", "request_for"]
