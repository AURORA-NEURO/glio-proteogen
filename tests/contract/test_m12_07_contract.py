"""Lightweight contract and schema gates for provisional M12-07."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from glio_proteogen.contracts.m12_07 import (
    M1207_M1206_RESULT_MEDIA_TYPE,
    M1207_OUTPUT_MEDIA_TYPE,
    AdjudicateBiomarkerPanelPlausibilityRequest,
    ControlKind,
    PlausibilityControl,
    UnresolvedConflict,
    contract_json_schemas,
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
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

_SCHEMA_COUNT = 6


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1207": label}),
        media_type="application/json",
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim=f"Evidence claim for {label}.",
    )


def test_m1207_schemas_are_strict_and_explicitly_provisional() -> None:
    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())

    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    metadata = schemas["output"]["x-glio-contract"]
    assert metadata["outputMediaType"] == M1207_OUTPUT_MEDIA_TYPE
    assert metadata["mechanismInputMediaType"] == M1207_M1206_RESULT_MEDIA_TYPE
    assert metadata["parentTarget"] == "biomarker_panel"
    assert metadata["failedControlsBlockRelease"]
    assert metadata["conflictsPreserved"]
    assert metadata["explicitAbstentionRequired"]


def test_m1207_controls_and_conflicts_preserve_release_blocking() -> None:
    evidence = _evidence("control")
    control = PlausibilityControl(
        control_id="control.direction",
        kind=ControlKind.DIRECTION,
        criterion="Observed direction agrees with the locked reference.",
        expected_direction="increasing",
        required_evidence=(evidence,),
    )
    assert control.release_blocking is True

    conflict = UnresolvedConflict(
        conflict_id="conflict.mechanism",
        description="Two mechanisms remain plausible.",
        competing_mechanisms=("mechanism.a", "mechanism.b"),
        evidence=(evidence,),
    )
    assert conflict.release_blocking is True

    with pytest.raises(ValueError, match="at least 2 items"):
        UnresolvedConflict(
            conflict_id="conflict.invalid",
            description="Only one mechanism is not a conflict.",
            competing_mechanisms=("mechanism.only",),
        )


def test_m1207_request_rejects_duplicate_source_artifacts_and_upstream_reuse() -> None:
    evidence = _evidence("source")

    def accepted(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role),
        )

    context = ExecutionContext(
        request_id="request.m1207.contract",
        actor_id="actor.contract",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted("config"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"identity": "bound"}),
                evidence=_artifact("identity"),
            ),
            provenance=accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=accepted("quality"),
            support=accepted("support"),
            intended_use=accepted("intended_use"),
        ),
    )
    control = PlausibilityControl(
        control_id="control.direction",
        kind=ControlKind.DIRECTION,
        criterion="Direction is concordant.",
        required_evidence=(evidence,),
    )
    upstream = _artifact("upstream")
    with pytest.raises(ValueError, match="source artifact ids must be unique"):
        AdjudicateBiomarkerPanelPlausibilityRequest(
            request_id="request.m1207.contract",
            context=context,
            mechanism_inference_result=ArtifactReference(
                artifact_id="artifact.mechanism",
                version="1.0.0",
                digest=sha256_digest({"mechanism": "m1206"}),
                media_type=M1207_M1206_RESULT_MEDIA_TYPE,
            ),
            controls=(control,),
            source_artifacts=(upstream, upstream),
        )
