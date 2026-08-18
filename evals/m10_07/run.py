"""Executable evaluation matrix for provisional M10-07 calibration."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m10_07 import (
    CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
    CalibrationConfiguration,
    CalibrationFindingCode,
    CalibrationMethod,
    CalibrationScope,
    CalibrationStatus,
    expected_evidence,
    provenance_is_bound,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_07_calibration_selective_prediction import (
    M1007Service,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M10-07"
AUTHORITY_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_LINES: Final = (3540, 3583)
MEDIA: Final = "application/vnd.glio-proteogen.fixture+json"
DIGEST: Final = "sha256:" + ("a" * 64)
NOMINAL_COVERAGE: Final = 0.9
UNCERTAINTY_DIMENSION_COUNT: Final = 7


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _artifact(name: str, media_type: str = MEDIA) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"eval.m10-07.{name}",
        version="1.0.0-provisional",
        digest=DIGEST,
        media_type=media_type,
    )


def _upstream(name: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"eval.decision.{name}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"control-{name}"),
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        request_id="eval.context",
        actor_id="eval.actor",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_upstream("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="eval.decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=DIGEST,
                evidence=_artifact("identity"),
            ),
            provenance=_upstream("provenance"),
            consent=ConsentReference(
                decision_id="eval.decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=_upstream("quality"),
            support=_upstream("support"),
            intended_use=_upstream("intended-use"),
        ),
    )


def build_request(
    *, support_threshold: float = 0.0, ood_threshold: float = 1.0, source_media: str = MEDIA
) -> CalibrateProteinRnaDiscordanceSelectivePredictionRequest:
    """Build one deterministic caller-declared request for evaluation and benchmarking."""

    scope = CalibrationScope(
        site="site.alpha", platform="platform.ms", disease_class="glioma", subgroup="adult"
    )
    configuration = CalibrationConfiguration(
        configuration_id="eval.configuration.m10-07",
        version="1.0.0-provisional",
        method=CalibrationMethod.CONFORMAL,
        scopes=(scope,),
        support_threshold=support_threshold,
        ood_threshold=ood_threshold,
        calibration_artifact=_artifact(
            "calibration", "application/vnd.glio-proteogen.calibration+json"
        ),
        benchmark_artifact=_artifact("benchmark", "application/vnd.glio-proteogen.benchmark+json"),
    )
    return CalibrateProteinRnaDiscordanceSelectivePredictionRequest(
        request_id="eval.request.m10-07",
        context=_context(),
        uncertainty_result=_artifact("uncertainty", "application/vnd.glio-proteogen.m10-06+json"),
        configuration=configuration,
        source_artifacts=(_artifact("source", source_media),),
    )


def run_evaluation(
    request: CalibrateProteinRnaDiscordanceSelectivePredictionRequest | None = None,
) -> dict[str, object]:
    """Run supported, threshold, OOD, unsupported, replay, and determinism cases."""

    service = M1007Service()
    base = request or build_request()
    checks: list[EvalCheck] = []

    def add(name: str, *, passed: bool, detail: str) -> None:
        checks.append(EvalCheck(name=name, passed=passed, detail=detail))

    built = service.execute(base)
    repeated = service.execute(base)
    replay = service.verify(built.result, built.canonical_bytes)
    add(
        "supported_calibration",
        passed=built.result.status is CalibrationStatus.CALIBRATED,
        detail=built.result.status.value,
    )
    add(
        "scoped_prediction_set",
        passed=(
            built.result.prediction_set is not None
            and built.result.prediction_set.nominal_coverage == NOMINAL_COVERAGE
        ),
        detail="nominal coverage=0.9",
    )
    add(
        "seven_uncertainty_dimensions",
        passed=len(built.result.uncertainty.model_dump()) >= UNCERTAINTY_DIMENSION_COUNT,
        detail="explicit uncertainty profile",
    )
    add(
        "result_identifier_binding",
        passed=built.result.result_id
        == f"result.{built.result.request_digest.removeprefix('sha256:')}",
        detail=built.result.result_id,
    )
    add(
        "evidence_provenance_binding",
        passed=(
            built.result.evidence == expected_evidence(base)
            and provenance_is_bound(base, built.result.request_digest, built.result.provenance)
        ),
        detail="request sources and seven controls are bound",
    )
    add(
        "support_threshold_abstention",
        passed=service.execute(build_request(support_threshold=1.0)).result.findings
        == (CalibrationFindingCode.SUPPORT_THRESHOLD_NOT_MET,),
        detail="review required",
    )
    add(
        "ood_abstention",
        passed=CalibrationFindingCode.OOD_UNSUPPORTED
        in service.execute(build_request(ood_threshold=0.0)).result.findings,
        detail="unsupported domain",
    )
    add(
        "media_abstention",
        passed=CalibrationFindingCode.OOD_UNSUPPORTED
        in service.execute(
            build_request(source_media="application/unsupported+json")
        ).result.findings,
        detail="unsupported media",
    )
    add("replay_verification", passed=replay.verified, detail=replay.reason)
    add(
        "deterministic_bytes",
        passed=built.canonical_bytes == repeated.canonical_bytes,
        detail=built.result.result_digest,
    )
    return {
        "module_id": MODULE_ID,
        "authority_sha256": AUTHORITY_SHA256,
        "authority_lines": list(AUTHORITY_LINES),
        "provisional_abi": True,
        "passed": all(item.passed for item in checks),
        "checks": [asdict(item) for item in checks],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    rendered = json.dumps(run_evaluation(), indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if json.loads(rendered)["passed"] else 1


__all__ = ["build_request", "main", "run_evaluation"]


if __name__ == "__main__":
    raise SystemExit(main())
