"""Genuine M05-05-backed scenarios for provisional M05-06 harmonization."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from functools import cache
from typing import Final

from evals.m05_05.run import canonical_smoke as m0505_canonical_smoke
from glio_proteogen.contracts.m05_05 import (
    M0505_CONTRACT_VERSION,
    PtmLocalizationArtifactDetectionResult,
    PtmLocalizationArtifactDisposition,
    PtmLocalizationEvidenceUnitKind,
)
from glio_proteogen.contracts.m05_06 import (
    M0506_CONTRACT_VERSION,
    HarmonizePtmLocalizationAnalysisRequest,
    PtmLocalizationArtifactHarmonizationReceipt,
    PtmLocalizationArtifactTargetReceipt,
    PtmLocalizationHarmonizationDisposition,
    PtmLocalizationHarmonizationPolicy,
    PtmLocalizationHarmonizationProfile,
    PtmLocalizationHarmonizationResult,
    PtmLocalizationNormalizationFactor,
    PtmLocalizationNormalizationFactorLevel,
    PtmLocalizationNormalizationStage,
    PtmLocalizationSupportInvariant,
    PtmLocalizationSupportInvariantKind,
    PtmLocalizationSupportLedger,
    PtmLocalizationSupportObservation,
    PtmLocalizationSupportObservationState,
    configuration_digest,
    support_ledger_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import ArtifactReference
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization import (
    artifact_harmonization_receipt,
    harmonize_ptm_localization_analysis,
)

_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-06.evidence+json"
_FACTOR_LEVELS: Final = {
    factor: f"level.{sha256_digest({'factor': factor.value}).removeprefix('sha256:')}"
    for factor in PtmLocalizationNormalizationFactor
}


@dataclass(frozen=True, slots=True)
class Scenario:
    case_id: str
    request: HarmonizePtmLocalizationAnalysisRequest
    expected_disposition: PtmLocalizationHarmonizationDisposition


class _UnknownScenarioError(ValueError):
    def __init__(self) -> None:
        super().__init__("unknown M05-06 scenario")


def _opaque(namespace: str, label: object) -> str:
    return f"{namespace}.{sha256_digest({'m0506': label}).removeprefix('sha256:')}"


def _reference(label: object, *, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_opaque("evidence", label),
        version=M0506_CONTRACT_VERSION,
        digest=digest or sha256_digest({"evidence": label}),
        media_type=_MEDIA_TYPE,
    )


def _policy() -> PtmLocalizationHarmonizationPolicy:
    stages = tuple(
        PtmLocalizationNormalizationStage(
            stage_id=_opaque("stage", factor.value),
            ordinal=index,
            factor=factor,
            reference_level_id=_FACTOR_LEVELS[factor],
        )
        for index, factor in enumerate(PtmLocalizationNormalizationFactor, start=1)
    )
    profile = PtmLocalizationHarmonizationProfile(
        profile_id=_opaque("profile", "canonical"),
        version=M0506_CONTRACT_VERSION,
        approved_artifact_contract_versions=(M0505_CONTRACT_VERSION,),
        stages=stages,
        evidence=_reference("profile"),
    )
    return PtmLocalizationHarmonizationPolicy(
        policy_id=_opaque("policy", "canonical"),
        version=M0506_CONTRACT_VERSION,
        max_targets=64,
        max_observations=64,
        max_absolute_shift_ppm=100_000,
        technical_effect_tolerance_ppm=10_000,
        profiles=(profile,),
        evidence=_reference("policy"),
    )


def _ledger(receipt: PtmLocalizationArtifactHarmonizationReceipt) -> PtmLocalizationSupportLedger:
    target: PtmLocalizationArtifactTargetReceipt = receipt.targets[0]
    levels = tuple(
        PtmLocalizationNormalizationFactorLevel(
            factor=factor,
            level_id=_FACTOR_LEVELS[factor],
        )
        for factor in PtmLocalizationNormalizationFactor
    )
    observation = PtmLocalizationSupportObservation(
        target_id=target.target_id,
        unit_kind=PtmLocalizationEvidenceUnitKind.VARIANT_PEPTIDE,
        artifact_target_state=target.target_state,
        artifact_action=target.action,
        posterior_digests=target.posterior_digests,
        posterior_binding_digest=target.posterior_binding_digest,
        state=PtmLocalizationSupportObservationState.OBSERVED,
        support_coordinate_ppm=500_000,
        factor_levels=levels,
        evidence=(_reference("observation"),),
        artifact_excluded=target.excluded,
    )
    invariant = PtmLocalizationSupportInvariant(
        invariant_id=_opaque("invariant", "support-direction"),
        kind=PtmLocalizationSupportInvariantKind.SUPPORT_DIRECTION,
        target_ids=(target.target_id,),
        evidence=(_reference("invariant"),),
    )
    payload: dict[str, object] = {
        "ledger_id": _opaque("ledger", "canonical"),
        "version": M0506_CONTRACT_VERSION,
        "artifact_result_digest": receipt.artifact_result_digest,
        "observations": (observation,),
        "invariants": (invariant,),
        "evidence": _reference("ledger"),
        "ledger_digest": _ZERO_DIGEST,
    }
    constructed = PtmLocalizationSupportLedger.model_construct(**payload)  # type: ignore[arg-type]
    payload["ledger_digest"] = support_ledger_digest(constructed)
    return PtmLocalizationSupportLedger.model_validate(payload, strict=True)


@cache
def build_scenario(case_id: str = "clear") -> Scenario:
    """Build one strict M05-06 request with complete upstream replay."""

    result_case = {
        "clear": "clear",
        "quarantined": "seeded_critical",
        "abstained": "missing_required",
    }.get(case_id)
    if result_case is None:
        raise _UnknownScenarioError
    upstream: PtmLocalizationArtifactDetectionResult = m0505_canonical_smoke(result_case)
    policy = _policy()
    upstream_refs = upstream.request.context.references
    context = upstream.request.context.model_copy(
        update={
            "references": upstream_refs.model_copy(
                update={
                    "approved_configuration": upstream_refs.approved_configuration.model_copy(
                        update={
                            "evidence": upstream_refs.approved_configuration.evidence.model_copy(
                                update={"digest": configuration_digest(policy)}
                            )
                        }
                    )
                }
            )
        }
    )
    receipt = artifact_harmonization_receipt(upstream)
    ledger = (
        _ledger(receipt)
        if upstream.disposition is PtmLocalizationArtifactDisposition.CLEARED
        else None
    )
    request = HarmonizePtmLocalizationAnalysisRequest(
        context=context,
        artifact_result=upstream,
        artifact_receipt=receipt,
        support_ledger=ledger,
        policy=policy,
    )
    expected = {
        "clear": PtmLocalizationHarmonizationDisposition.ACCEPTED,
        "quarantined": PtmLocalizationHarmonizationDisposition.QUARANTINED,
        "abstained": PtmLocalizationHarmonizationDisposition.ABSTAINED,
    }[case_id]
    return Scenario(case_id, request, expected)


def canonical_smoke(case_id: str = "clear") -> PtmLocalizationHarmonizationResult:
    """Execute one deterministic scenario through the public engine."""

    return harmonize_ptm_localization_analysis(build_scenario(case_id).request)


def run_evaluation() -> dict[str, object]:
    checks = []
    for case_id in ("clear", "quarantined", "abstained"):
        scenario = build_scenario(case_id)
        result = harmonize_ptm_localization_analysis(scenario.request)
        checks.append(
            {
                "case_id": case_id,
                "passed": result.disposition is scenario.expected_disposition,
            }
        )
    return {
        "module_id": "GLIO-PROTEOGEN-M05-06",
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run_evaluation()
    print(json.dumps(report, sort_keys=True) if args.json else report)  # noqa: T201
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["Scenario", "build_scenario", "canonical_smoke", "run_evaluation"]
