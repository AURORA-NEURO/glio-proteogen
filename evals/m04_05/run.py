"""Genuine builders and locked executable evaluation for M04-05."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

from evals.m04_04.run import build_scenario_request as build_m0404_request
from glio_proteogen.contracts.m04_04 import (
    M0404_CONTRACT_VERSION,
    ProteoformQualityDisposition,
    ProteoformQualityResult,
)
from glio_proteogen.contracts.m04_05 import (
    M0405_CONTRACT_VERSION,
    M0405_FALSE_EXCLUSION_CEILING_PPM,
    M0405_MODULE_ID,
    M0405_OPERATION,
    M0405_SEEDED_SENSITIVITY_FLOOR_PPM,
    DetectProteoformArtifactsRequest,
    ProteoformArtifactDetectionResult,
    ProteoformArtifactDetectorClass,
    ProteoformArtifactEvidenceEvent,
    ProteoformArtifactEvidenceLedger,
    ProteoformArtifactObservationState,
    ProteoformArtifactPolicy,
    ProteoformArtifactProfile,
    ProteoformArtifactThreshold,
    ProteoformEvidenceUnitKind,
    configuration_digest,
    evidence_ledger_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ContextReferences,
    ExecutionContext,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics import (
    compute_proteoform_quality_metrics,
)

SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m04_05" / "scenarios.json"
)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


@dataclass(frozen=True, slots=True)
class Scenario:
    request: DetectProteoformArtifactsRequest


def _oid(namespace: str, label: object) -> str:
    digest = sha256_digest({"m0405_fixture": str(label)}).removeprefix("sha256:")
    return f"{namespace}.{digest}"


def _reference(label: str, *, media_type: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_oid("evidence", label),
        version="1.0.0",
        digest=digest or sha256_digest({"m0405_evidence": label}),
        media_type=media_type,
    )


def _thresholds() -> tuple[ProteoformArtifactThreshold, ...]:
    return tuple(
        ProteoformArtifactThreshold(
            detector_class=detector_class,
            review_threshold_ppm=200_000,
            exclusion_threshold_ppm=500_000,
            required=True,
            evidence=_reference(
                f"threshold-{detector_class.value}",
                media_type="application/vnd.glio-proteogen.m04-05.threshold+json",
            ),
        )
        for detector_class in ProteoformArtifactDetectorClass
    )


def _policy(
    *,
    reviewed_at: datetime,
    supported_version: str = M0404_CONTRACT_VERSION,
) -> ProteoformArtifactPolicy:
    profile = ProteoformArtifactProfile(
        profile_id=_oid("profile", supported_version),
        version="1.0.0",
        approved_quality_contract_versions=(supported_version,),
        thresholds=_thresholds(),
        evidence=_reference(
            f"profile-{supported_version}",
            media_type="application/vnd.glio-proteogen.m04-05.profile+json",
        ),
    )
    return ProteoformArtifactPolicy(
        policy_id=_oid("policy", supported_version),
        version="1.0.0",
        profiles=(profile,),
        quarantine_suspected=True,
        abstain_missing_required=True,
        open_set_abstention=True,
        never_infer_negative_from_missing=True,
        evidence=_reference(
            f"policy-{supported_version}",
            media_type="application/vnd.glio-proteogen.m04-05.policy+json",
        ),
        reviewed_by=_oid("reviewer", "locked-review"),
        reviewed_at=reviewed_at,
    )


def _quality_result(case_id: str) -> ProteoformQualityResult:
    upstream_case = {
        "upstream_quarantined": "quarantined_upstream_zero_ledger_traversal",
        "upstream_abstained": "abstained_upstream_zero_ledger_traversal",
    }.get(case_id, "canonical_four_role_quality_qualified")
    return compute_proteoform_quality_metrics(build_m0404_request(upstream_case))


def _events(case_id: str) -> tuple[ProteoformArtifactEvidenceEvent, ...]:
    target_id = _oid("target", case_id)
    selected = case_id.removeprefix("critical_")
    events: list[ProteoformArtifactEvidenceEvent] = []
    for sequence, detector_class in enumerate(ProteoformArtifactDetectorClass, start=1):
        state = ProteoformArtifactObservationState.OBSERVED
        supporting_count = 0
        evaluated_count = 100
        if case_id.startswith("critical_") and detector_class.value == selected:
            supporting_count = 80
        elif case_id == "suspected_barcode" and (
            detector_class is ProteoformArtifactDetectorClass.BARCODE_INDEX
        ):
            supporting_count = 30
        elif case_id == "missing_mapping" and (
            detector_class is ProteoformArtifactDetectorClass.MAPPING_ERROR
        ):
            state = ProteoformArtifactObservationState.MISSING
            evaluated_count = 0
        elif case_id == "unsupported_context" and (
            detector_class is ProteoformArtifactDetectorClass.CONTEXT_SPECIFIC_FALSE_POSITIVE
        ):
            state = ProteoformArtifactObservationState.UNSUPPORTED
            evaluated_count = 0
        events.append(
            ProteoformArtifactEvidenceEvent(
                event_id=_oid("event", f"{case_id}-{detector_class.value}"),
                sequence=sequence,
                target_id=target_id,
                unit_kind=ProteoformEvidenceUnitKind.PROTEOFORM_CANDIDATE,
                detector_class=detector_class,
                observation_state=state,
                supporting_count=supporting_count,
                evaluated_count=evaluated_count,
                evidence=(
                    _reference(
                        f"event-{case_id}-{detector_class.value}",
                        media_type="application/vnd.glio-proteogen.m04-05.event+json",
                    ),
                ),
            )
        )
    return tuple(events)


def _ledger(
    case_id: str,
    quality_result: ProteoformQualityResult,
) -> ProteoformArtifactEvidenceLedger:
    quality_digest = quality_result.result_digest
    if case_id == "binding_mismatch":
        quality_digest = sha256_digest({"m0405_fixture": "stale-quality-result"})
    quality_completed_at = quality_result.completed_at
    payload: dict[str, object] = {
        "ledger_id": _oid("ledger", case_id),
        "version": "1.0.0",
        "quality_result_digest": quality_digest,
        "events": _events(case_id),
        "recorded_at": quality_completed_at + timedelta(minutes=1),
        "ledger_digest": _ZERO_DIGEST,
        "evidence": _reference(
            f"ledger-{case_id}",
            media_type="application/vnd.glio-proteogen.m04-05.event-ledger+json",
        ),
    }
    assembled = ProteoformArtifactEvidenceLedger.model_construct(**payload)  # type: ignore[arg-type]
    payload["ledger_digest"] = evidence_ledger_digest(assembled)
    return ProteoformArtifactEvidenceLedger.model_validate(payload, strict=True)


def build_scenario_request(case_id: str = "canonical_clear") -> DetectProteoformArtifactsRequest:
    """Build one request over a genuine public M04-04 result."""

    quality_result = _quality_result(case_id)
    supported_version = "2.0.0" if case_id == "unsupported_profile" else M0404_CONTRACT_VERSION
    policy = _policy(
        reviewed_at=quality_result.completed_at,
        supported_version=supported_version,
    )
    upstream_context = quality_result.request.context
    request_id = _oid("request", case_id)
    occurred_at = quality_result.completed_at + timedelta(minutes=2)
    approved = UpstreamDecisionReference(
        decision_id=_oid("decision", f"configuration-{case_id}"),
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_reference(
            f"configuration-{case_id}",
            media_type="application/vnd.glio-proteogen.m04-05.configuration+json",
            digest=configuration_digest(policy),
        ),
    )
    quality = UpstreamDecisionReference(
        decision_id=_oid("decision", f"quality-{case_id}"),
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_reference(
            f"quality-{case_id}",
            media_type="application/vnd.glio-proteogen.m04-04.result+json",
            digest=quality_result.result_digest,
        ),
    )
    refs = upstream_context.references
    context = ExecutionContext(
        request_id=request_id,
        actor_id=upstream_context.actor_id,
        occurred_at=occurred_at,
        references=ContextReferences(
            approved_configuration=approved,
            identity_lineage=refs.identity_lineage,
            provenance=refs.provenance,
            consent=refs.consent,
            quality=quality,
            support=refs.support,
            intended_use=refs.intended_use,
        ),
    )
    traversable = (
        quality_result.disposition is ProteoformQualityDisposition.QUALIFIED
        and supported_version == M0404_CONTRACT_VERSION
    )
    return DetectProteoformArtifactsRequest(
        operation=M0405_OPERATION,
        contract_version=M0405_CONTRACT_VERSION,
        request_id=request_id,
        context=context,
        quality_result=quality_result,
        policy=policy,
        evidence_ledger=_ledger(case_id, quality_result) if traversable else None,
        supersedes_result_digest=None,
    )


def build_scenario_result(
    case_id: str = "canonical_clear",
) -> ProteoformArtifactDetectionResult:
    """Build through the genuine public M04-05 runtime operation."""

    from glio_proteogen.modules.c04_proteoform_isoform.m04_05_artifact_detection import (  # noqa: PLC0415
        detect_proteoform_artifacts,
    )

    return detect_proteoform_artifacts(build_scenario_request(case_id))


def build_representative_artifact_fixture() -> Scenario:
    return Scenario(request=build_scenario_request("critical_contamination"))


def run_evaluation() -> dict[str, object]:
    """Execute the locked finite acceptance panel."""

    case_ids = tuple(json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))["case_ids"])
    checks: list[dict[str, object]] = []
    for case_id in case_ids:
        result = build_scenario_result(case_id)
        checks.append(
            {
                "name": f"scenario.{case_id}",
                "passed": result.result_digest != _ZERO_DIGEST,
            }
        )
    seeded = tuple(
        build_scenario_result(f"critical_{item.value}") for item in ProteoformArtifactDetectorClass
    )
    detected = sum(bool(item.exclusion_mask) for item in seeded)
    sensitivity_ppm = detected * 1_000_000 // len(seeded)
    clear = build_scenario_result("canonical_clear")
    false_exclusion_ppm = 1_000_000 if clear.exclusion_mask else 0
    checks.extend(
        (
            {
                "name": "acceptance.seeded_critical_sensitivity",
                "passed": sensitivity_ppm >= M0405_SEEDED_SENSITIVITY_FLOOR_PPM,
            },
            {
                "name": "acceptance.false_exclusion_ceiling",
                "passed": false_exclusion_ppm <= M0405_FALSE_EXCLUSION_CEILING_PPM,
            },
        )
    )
    passed = all(item["passed"] is True for item in checks)
    return {
        "module_id": M0405_MODULE_ID,
        "operation": M0405_OPERATION,
        "declared_case_count": len(case_ids),
        "executed_case_count": len(case_ids),
        "seeded_sensitivity_ppm": sensitivity_ppm,
        "false_exclusion_ppm": false_exclusion_ppm,
        "checks": checks,
        "passed": passed,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    report = run_evaluation()
    serialized = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(serialized)
    else:
        arguments.output.write_text(serialized, encoding="utf-8", newline="\n")
    return 0 if report["passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "Scenario",
    "build_representative_artifact_fixture",
    "build_scenario_request",
    "build_scenario_result",
    "main",
    "run_evaluation",
]
