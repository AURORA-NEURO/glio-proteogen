"""Focused contract/schema smoke for provisional M26-07."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m26_07 import (
    M2607_OUTPUT_MEDIA_TYPE,
    M2607_PROVISIONAL_ABI,
    ChangeClass,
    ChangeImpact,
    ChangePackage,
    ChangeProposal,
    RevalidationRecord,
    RollbackPoint,
    RolloutStage,
    ShadowComparison,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_change_control_gates() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["changeClassificationRequired"]
        and schema["x-glio-contract"]["revalidationRequired"]
        and schema["x-glio-contract"]["championChallengerRequired"]
        and schema["x-glio-contract"]["stagedRolloutRequired"]
        and schema["x-glio-contract"]["testedRollbackRequired"]
        and schema["x-glio-contract"]["criticalRegressionBlocksPromotion"]
        and schema["x-glio-contract"]["quarantineUnresolvedInputs"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "protein subtype"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2607_OUTPUT_MEDIA_TYPE
    assert M2607_PROVISIONAL_ABI is True


def test_regression_and_revalidation_gates_are_explicit() -> None:
    proposal = ChangeProposal(
        proposal_id="proposal-1",
        current_version="1.0.0",
        proposed_version="1.1.0",
        change_class=ChangeClass.MINOR,
        impact=ChangeImpact.MODERATE,
        champion_digest="sha256:" + "a" * 64,
        challenger_digest="sha256:" + "b" * 64,
        rationale="validate a bounded change",
        required_revalidation_ids=("revalidation-1",),
    )
    with pytest.raises(ValidationError, match="exceeds declared tolerance"):
        ShadowComparison(
            comparison_id="comparison-1",
            proposal_id=proposal.proposal_id,
            metric_name="error",
            champion_value=0.1,
            challenger_value=0.3,
            tolerance=0.01,
            no_regression=True,
        )
    rollback = RollbackPoint(
        rollback_id="rollback-1",
        target_version="1.0.0",
        restore_artifact=ArtifactReference(
            artifact_id="restore-1",
            version="1.0.0",
            digest="sha256:" + "c" * 64,
            media_type="application/vnd.glio-proteogen.restore+json",
        ),
        restore_command="restore",
        recovery_objective="recover safely",
        evidence=(
            EvidenceReference(
                reference=ArtifactReference(
                    artifact_id="evidence-1",
                    version="1.0.0",
                    digest="sha256:" + "f" * 64,
                    media_type="application/vnd.glio-proteogen.evidence+json",
                ),
                role="evidence",
                claim="rollback smoke",
            ),
        ),
    )
    revalidation = RevalidationRecord(
        revalidation_id="revalidation-1",
        proposal_id="other-proposal",
        check_name="unit check",
        passed=True,
        report_digest="sha256:" + "d" * 64,
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    comparison = ShadowComparison(
        comparison_id="comparison-2",
        proposal_id=proposal.proposal_id,
        metric_name="error",
        champion_value=0.1,
        challenger_value=0.1,
        tolerance=0.01,
        no_regression=True,
    )
    with pytest.raises(ValidationError, match="different proposal"):
        ChangePackage(
            package_id="package-1",
            version="1.0.0",
            proposal=proposal,
            revalidations=(revalidation,),
            comparisons=(comparison,),
            rollout_stage=RolloutStage.SHADOW,
            rollback_point=rollback,
            package_digest="sha256:" + "e" * 64,
        )
