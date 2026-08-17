"""Genuine M05-03-backed scenarios for M05-05 artifact detection."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Final

from evals.m05_03.run import canonical_smoke as m0503_canonical_smoke
from glio_proteogen.contracts.m05_05 import (
    DetectPtmLocalizationArtifactsRequest,
    PtmLocalizationArtifactDetectionResult,
    PtmLocalizationArtifactDetectorClass,
    PtmLocalizationArtifactDisposition,
    PtmLocalizationArtifactEvidenceEvent,
    PtmLocalizationArtifactEvidenceLedger,
    PtmLocalizationArtifactEvidenceLedgerBinding,
    PtmLocalizationArtifactObservationState,
    PtmLocalizationArtifactPolicy,
    PtmLocalizationArtifactProfile,
    PtmLocalizationArtifactThreshold,
    PtmLocalizationArtifactUpstreamDisposition,
    PtmLocalizationEvidenceUnitKind,
    configuration_digest,
    evidence_ledger_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, ContextReferences, ExecutionContext
from glio_proteogen.modules.c05_ptm_localization.m05_05_artifact_detection import (
    detect_ptm_localization_artifacts,
)

if TYPE_CHECKING:
    from datetime import datetime

    from glio_proteogen.contracts.m05_03 import PtmLocalizationRawInputValidationResult

_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m05_05" / "scenarios.json"
)
_EVENT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-05.event+json"
_LEDGER_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-05.ledger+json"
_POLICY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-05.policy+json"
_PROFILE_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-05.profile+json"
_THRESHOLD_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-05.threshold+json"


@dataclass(frozen=True, slots=True)
class Scenario:
    case_id: str
    request: DetectPtmLocalizationArtifactsRequest
    expected_disposition: PtmLocalizationArtifactDisposition
    expected_posteriors: int
    expected_flags: int
    expected_exclusions: int


class _UnknownScenarioError(ValueError):
    def __init__(self) -> None:
        super().__init__("unknown M05-05 scenario")


def _digest(label: str) -> str:
    return sha256_digest({"m0505_scenario": label})


def _opaque(namespace: str, label: str) -> str:
    return f"{namespace}.{_digest(f'{namespace}-{label}').removeprefix('sha256:')}"


def _reference(label: str, media_type: str, *, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_opaque("evidence", label),
        version="1.0.0",
        digest=digest or _digest(f"evidence-{label}"),
        media_type=media_type,
    )


@cache
def _raw_result() -> PtmLocalizationRawInputValidationResult:
    """Return one genuine, fully validated M05-03 result for downstream replay."""

    return m0503_canonical_smoke()


def _policy(
    quality_configuration_digest: str,
    reviewed_at: datetime,
) -> PtmLocalizationArtifactPolicy:
    thresholds = tuple(
        PtmLocalizationArtifactThreshold(
            detector_class=detector_class,
            review_threshold_ppm=250_000,
            exclusion_threshold_ppm=750_000,
            required=True,
            evidence=_reference(f"threshold-{detector_class.value}", _THRESHOLD_MEDIA_TYPE),
        )
        for detector_class in PtmLocalizationArtifactDetectorClass
    )
    profile = PtmLocalizationArtifactProfile(
        profile_id=_opaque("profile", "canonical"),
        version="1.0.0",
        approved_quality_contract_versions=("1.0.0",),
        approved_quality_configuration_digests=(quality_configuration_digest,),
        thresholds=thresholds,
        evidence=_reference("profile", _PROFILE_MEDIA_TYPE),
    )
    return PtmLocalizationArtifactPolicy.model_validate(
        {
            "policy_id": _opaque("policy", "canonical"),
            "version": "1.0.0",
            "profiles": (profile,),
            "evidence": _reference("policy", _POLICY_MEDIA_TYPE),
            "reviewed_by": _opaque("reviewer", "canonical"),
            "reviewed_at": reviewed_at,
        },
        strict=True,
    )


def _event_state(
    case_id: str,
    detector_class: PtmLocalizationArtifactDetectorClass,
) -> tuple[PtmLocalizationArtifactObservationState, int, int, bool]:
    if case_id == "missing_required" and (
        detector_class is PtmLocalizationArtifactDetectorClass.TECHNICAL_ARTIFACT
    ):
        return PtmLocalizationArtifactObservationState.MISSING, 0, 0, False
    if case_id == "unsupported_required" and (
        detector_class is PtmLocalizationArtifactDetectorClass.MAPPING_ERROR
    ):
        return PtmLocalizationArtifactObservationState.UNSUPPORTED, 0, 0, False
    if case_id == "seeded_critical" and (
        detector_class is PtmLocalizationArtifactDetectorClass.TECHNICAL_ARTIFACT
    ):
        return PtmLocalizationArtifactObservationState.OBSERVED, 0, 10, True
    if case_id == "contamination_detected" and (
        detector_class is PtmLocalizationArtifactDetectorClass.CONTAMINATION
    ):
        return PtmLocalizationArtifactObservationState.OBSERVED, 9, 10, False
    return PtmLocalizationArtifactObservationState.OBSERVED, 0, 10, False


def _ledger(
    case_id: str,
    *,
    quality_result_digest: str,
    quality_configuration_digest: str,
    quality_receipt_digest: str,
    raw_result: PtmLocalizationRawInputValidationResult,
) -> PtmLocalizationArtifactEvidenceLedger:
    target_id = _opaque("target", case_id)
    events = tuple(
        PtmLocalizationArtifactEvidenceEvent(
            event_id=_opaque("event", f"{case_id}-{detector_class.value}"),
            sequence=index,
            target_id=target_id,
            unit_kind=PtmLocalizationEvidenceUnitKind.VARIANT_PEPTIDE,
            detector_class=detector_class,
            observation_state=state,
            supporting_count=supporting_count,
            evaluated_count=evaluated_count,
            seeded_critical=seeded_critical,
            evidence=(_reference(f"event-{case_id}-{detector_class.value}", _EVENT_MEDIA_TYPE),),
        )
        for index, detector_class in enumerate(PtmLocalizationArtifactDetectorClass, start=1)
        for state, supporting_count, evaluated_count, seeded_critical in (
            _event_state(case_id, detector_class),
        )
    )
    payload: dict[str, object] = {
        "ledger_id": _opaque("ledger", case_id),
        "version": "1.0.0",
        "quality_result_digest": quality_result_digest,
        "quality_contract_version": "1.0.0",
        "quality_configuration_digest": quality_configuration_digest,
        "quality_receipt_digest": quality_receipt_digest,
        "identity_resolution_digest": raw_result.receipt.identity_resolution_digest,
        "raw_input_receipt_digest": raw_result.receipt.receipt_digest,
        "events": events,
        "recorded_at": raw_result.completed_at,
        "ledger_digest": _ZERO_DIGEST,
        "evidence": _reference(f"ledger-{case_id}", _LEDGER_MEDIA_TYPE),
    }
    provisional = PtmLocalizationArtifactEvidenceLedger.model_construct(**payload)  # type: ignore[arg-type]
    payload["ledger_digest"] = evidence_ledger_digest(provisional)
    return PtmLocalizationArtifactEvidenceLedger.model_validate(payload, strict=True)


def _binding(
    ledger: PtmLocalizationArtifactEvidenceLedger,
) -> PtmLocalizationArtifactEvidenceLedgerBinding:
    payload = ledger.model_dump(mode="python", exclude={"events"})
    return PtmLocalizationArtifactEvidenceLedgerBinding.model_validate(payload, strict=True)


def build_scenario(case_id: str = "clear") -> Scenario:
    """Build one strict request whose upstream raw result is genuine M05-03 output."""

    allowed = {
        "clear",
        "seeded_critical",
        "contamination_detected",
        "missing_required",
        "unsupported_required",
        "ledger_binding_only",
        "upstream_quarantined",
        "upstream_abstained",
    }
    if case_id not in allowed:
        raise _UnknownScenarioError
    # The canonical upstream fixture is cached for benchmark determinism, but
    # every downstream scenario owns an isolated tree.  This prevents a
    # hostile replay test from mutating the fixture seen by later scenarios.
    raw_result = _raw_result().model_copy(deep=True)
    quality_result_digest = _digest("quality-result")
    quality_configuration_digest = _digest("quality-configuration")
    quality_receipt_digest = _digest("quality-receipt")
    policy = _policy(quality_configuration_digest, raw_result.completed_at)
    raw_refs = raw_result.request.context.references
    references = ContextReferences(
        approved_configuration=raw_refs.approved_configuration.model_copy(
            update={
                "evidence": raw_refs.approved_configuration.evidence.model_copy(
                    update={"digest": configuration_digest(policy)}
                )
            }
        ),
        identity_lineage=raw_refs.identity_lineage,
        provenance=raw_refs.provenance,
        consent=raw_refs.consent,
        quality=raw_refs.quality.model_copy(
            update={
                "evidence": raw_refs.quality.evidence.model_copy(
                    update={"digest": quality_result_digest}
                )
            }
        ),
        support=raw_refs.support,
        intended_use=raw_refs.intended_use,
    )
    context = ExecutionContext(
        request_id=_opaque("request", case_id),
        actor_id=raw_result.request.context.actor_id,
        occurred_at=raw_result.completed_at,
        references=references,
    )
    upstream = {
        "upstream_quarantined": PtmLocalizationArtifactUpstreamDisposition.QUARANTINED,
        "upstream_abstained": PtmLocalizationArtifactUpstreamDisposition.ABSTAINED,
    }.get(case_id, PtmLocalizationArtifactUpstreamDisposition.QUALIFIED)
    evidence_ledger: (
        PtmLocalizationArtifactEvidenceLedger | PtmLocalizationArtifactEvidenceLedgerBinding | None
    ) = None
    if upstream is PtmLocalizationArtifactUpstreamDisposition.QUALIFIED:
        full_ledger = _ledger(
            case_id,
            quality_result_digest=quality_result_digest,
            quality_configuration_digest=quality_configuration_digest,
            quality_receipt_digest=quality_receipt_digest,
            raw_result=raw_result,
        )
        evidence_ledger = _binding(full_ledger) if case_id == "ledger_binding_only" else full_ledger
    request = DetectPtmLocalizationArtifactsRequest(
        request_id=context.request_id,
        context=context,
        raw_input_result=raw_result,
        quality_result_digest=quality_result_digest,
        quality_contract_version="1.0.0",
        quality_configuration_digest=quality_configuration_digest,
        quality_receipt_digest=quality_receipt_digest,
        identity_resolution_digest=raw_result.receipt.identity_resolution_digest,
        raw_input_receipt_digest=raw_result.receipt.receipt_digest,
        quality_disposition=upstream,
        policy=policy,
        evidence_ledger=evidence_ledger,
    )
    expected = {
        "clear": (PtmLocalizationArtifactDisposition.CLEARED, 7, 0, 0),
        "seeded_critical": (PtmLocalizationArtifactDisposition.QUARANTINED, 7, 0, 1),
        "contamination_detected": (PtmLocalizationArtifactDisposition.QUARANTINED, 7, 1, 1),
        "missing_required": (PtmLocalizationArtifactDisposition.ABSTAINED, 7, 0, 0),
        "unsupported_required": (PtmLocalizationArtifactDisposition.ABSTAINED, 7, 0, 0),
        "ledger_binding_only": (PtmLocalizationArtifactDisposition.QUARANTINED, 0, 0, 0),
        "upstream_quarantined": (PtmLocalizationArtifactDisposition.QUARANTINED, 0, 0, 0),
        "upstream_abstained": (PtmLocalizationArtifactDisposition.ABSTAINED, 0, 0, 0),
    }[case_id]
    return Scenario(case_id, request, expected[0], expected[1], expected[2], expected[3])


def canonical_smoke(case_id: str = "clear") -> PtmLocalizationArtifactDetectionResult:
    """Execute one deterministic genuine-chain scenario."""

    return detect_ptm_localization_artifacts(build_scenario(case_id).request)


def run_evaluation() -> dict[str, object]:
    corpus = json.loads(_SCENARIO_PATH.read_text(encoding="utf-8"))
    checks: list[dict[str, object]] = []
    for item in corpus["cases"]:
        scenario = build_scenario(item["case_id"])
        result = detect_ptm_localization_artifacts(scenario.request)
        passed = (
            result.disposition is scenario.expected_disposition
            and len(result.artifact_posteriors) == scenario.expected_posteriors
            and len(result.contamination_flags) == scenario.expected_flags
            and len(result.exclusion_mask) == scenario.expected_exclusions
        )
        checks.append({"case_id": scenario.case_id, "passed": passed})
    return {
        "module_id": "GLIO-PROTEOGEN-M05-05",
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = run_evaluation()
    print(json.dumps(report, sort_keys=True) if args.json else report)  # noqa: T201
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["Scenario", "build_scenario", "canonical_smoke", "run_evaluation"]
