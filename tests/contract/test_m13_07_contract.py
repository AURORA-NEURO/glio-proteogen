"""Lightweight contract and schema gates for provisional M13-07."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m13_07 import (
    M1307_M1306_RESULT_MEDIA_TYPE,
    M1307_OUTPUT_MEDIA_TYPE,
    ControlKind,
    PlausibilityControl,
    UnresolvedConflict,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 6


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1307": label}),
        media_type="application/json",
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim=f"Evidence claim for {label}.",
    )


def test_m1307_schemas_are_strict_and_explicitly_provisional() -> None:
    schemas = contract_json_schemas()

    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    metadata = schemas["output"]["x-glio-contract"]
    assert metadata["outputMediaType"] == M1307_OUTPUT_MEDIA_TYPE
    assert metadata["mechanismInputMediaType"] == M1307_M1306_RESULT_MEDIA_TYPE
    assert metadata["parentTarget"] == "proteotype"
    assert metadata["failedControlsBlockRelease"]
    assert metadata["conflictsPreserved"]
    assert metadata["explicitAbstentionRequired"]


def test_m1307_controls_and_conflicts_preserve_release_blocking() -> None:
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
