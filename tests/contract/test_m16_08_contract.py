"""Lightweight contract and schema gates for provisional M16-08."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m16_08 import (
    M1608_OUTPUT_MEDIA_TYPE,
    DriftAssessment,
    HealthSignal,
    HealthSignalKind,
    HealthSignalStatus,
    RollbackPlan,
    TranslationHealthReport,
    TranslationMonitoringConfiguration,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import ArtifactReference

_SCHEMA_COUNT = 8


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1608": label}),
        media_type="application/json",
    )


def test_m1608_schemas_are_strict_and_explicitly_provisional() -> None:
    schemas = contract_json_schemas()

    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["pendingOwnerConfirmation"]
        for schema in schemas.values()
    )
    metadata = schemas["output"]["x-glio-contract"]
    assert metadata["outputMediaType"] == M1608_OUTPUT_MEDIA_TYPE
    assert metadata["parentTarget"] == "protein_rna_discordance"
    assert metadata["supportDriftRequired"]
    assert metadata["suspensionAndRollbackExplicit"]
    assert metadata["rollbackRecoveryRequired"]
    assert metadata["explicitAbstentionRequired"]


def test_m1608_health_report_closes_signal_assessment_and_rollback_references() -> None:
    signal = HealthSignal(
        signal_id="signal.support",
        kind=HealthSignalKind.SUPPORT_DRIFT,
        metric="supported-use proportion",
        observed_value=0.72,
        lower_bound=0.8,
        upper_bound=1.0,
        status=HealthSignalStatus.DRIFTING,
        source_artifacts=(_artifact("support"),),
    )
    assessment = DriftAssessment(
        assessment_id="assessment.support",
        signal_ids=(signal.signal_id,),
        summary="Support drift exceeds the declared envelope.",
        status=HealthSignalStatus.DRIFTING,
        critical=True,
    )
    report = TranslationHealthReport(
        report_id="report.translation",
        version="1.0.0",
        signals=(signal,),
        assessments=(assessment,),
        rollback_plan=RollbackPlan(
            plan_id="rollback.translation",
            trigger_conditions=("Critical support drift persists.",),
            target_version="1.0.0",
            action="Suspend release and restore the last approved version.",
            recovery_steps=("Verify fixtures and obtain reviewer sign-off.",),
        ),
        configuration=TranslationMonitoringConfiguration(
            configuration_id="config.translation",
            version="1.0.0",
            reference_artifact=_artifact("reference"),
            monitoring_window="rolling 30 days",
            critical_threshold="support proportion below 0.80",
        ),
    )
    assert report.assessments[0].signal_ids == ("signal.support",)

    with pytest.raises(ValueError, match="unknown signal"):
        TranslationHealthReport(
            report_id="report.invalid",
            version="1.0.0",
            signals=(signal,),
            assessments=(
                assessment.model_copy(update={"signal_ids": ("signal.missing",)}),
            ),
            rollback_plan=report.rollback_plan,
            configuration=report.configuration,
        )

    with pytest.raises(ValueError, match="bounds must be ordered"):
        HealthSignal(
            signal_id="signal.invalid",
            kind=HealthSignalKind.DISCREPANCY,
            metric="discrepancy count",
            observed_value=2.0,
            lower_bound=3.0,
            upper_bound=1.0,
            status=HealthSignalStatus.DRIFTING,
            source_artifacts=(_artifact("invalid"),),
        )
