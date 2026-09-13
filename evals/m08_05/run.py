"""Executable hard/soft/support/replay matrix for provisional M08-05."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.modules.c08_transcript_protein_discordance.test_m08_05_integrator import (
    _artifact,
    _request,
)

from glio_proteogen.contracts.m08_05 import (
    M0805_GLIOMA_MODEL_FAMILY,
    ConstraintEvidenceObservation,
    ConstraintObservationState,
    IntegrateTranscriptProteinConstraintsRequest,
)
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_05_mechanism_constraint_integrator import (
    M0805ConstraintIntegrator,
)

_TYPED_MIN_ESTIMATES = 2


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    supported_status: str
    hard_violation_status: str
    soft_conflict_status: str
    unsupported_status: str
    estimate_count: int
    report_count: int
    replay_verified: bool
    tamper_rejected: bool
    deterministic: bool
    typed_status: str
    typed_estimate_count: int
    typed_deterministic: bool
    passed: bool


def _typed_request() -> IntegrateTranscriptProteinConstraintsRequest:
    base = _request("conservation_hold")
    observations = (
        ConstraintEvidenceObservation(feature_id="EGFR", value=1.1, standard_error=0.2),
        ConstraintEvidenceObservation(feature_id="CDK4", value=0.8, standard_error=0.2),
        ConstraintEvidenceObservation(
            feature_id="TP53",
            state=ConstraintObservationState.LEFT_CENSORED,
            standard_error=0.2,
            censoring_limit=0.0,
        ),
    )
    return base.model_copy(
        update={
            "source_artifacts": (_artifact("EGFR"), _artifact("CDK4"), _artifact("TP53")),
            "policy": base.policy.model_copy(
                update={"estimator_family": M0805_GLIOMA_MODEL_FAMILY}
            ),
            "observations": observations,
        }
    )


def evaluate() -> EvaluationReport:
    engine = M0805ConstraintIntegrator()
    supported = engine.integrate(_request("conservation_hold"))
    repeat = engine.integrate(_request("conservation_hold"))
    typed = engine.integrate(_typed_request())
    typed_repeat = engine.integrate(_typed_request())
    hard = engine.integrate(_request("force_violation"))
    soft = engine.integrate(_request("soft force_violation"))
    unsupported = engine.integrate(_request("unsupported ontology"))
    replay = engine.verify(supported.result, supported.canonical_bytes)
    tampered = engine.verify(supported.result, supported.canonical_bytes + b" ")
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M08-05",
        contract_version="0.1.0-provisional",
        supported_status=supported.result.status.value,
        hard_violation_status=hard.result.status.value,
        soft_conflict_status=soft.result.status.value,
        unsupported_status=unsupported.result.status.value,
        estimate_count=len(supported.result.estimates),
        report_count=len(supported.result.satisfaction_report),
        replay_verified=replay.verified,
        tamper_rejected=not tampered.verified,
        deterministic=supported.canonical_bytes == repeat.canonical_bytes,
        typed_status=typed.result.status.value,
        typed_estimate_count=len(typed.result.estimates),
        typed_deterministic=typed.canonical_bytes == typed_repeat.canonical_bytes,
        passed=(
            supported.result.status.value == "estimated"
            and hard.result.status.value == "abstained"
            and soft.result.status.value == "estimated"
            and unsupported.result.status.value == "abstained"
            and bool(supported.result.estimates)
            and bool(supported.result.satisfaction_report)
            and replay.verified
            and not tampered.verified
            and supported.canonical_bytes == repeat.canonical_bytes
            and typed.result.status.value == "estimated"
            and typed.result.typed_model
            and len(typed.result.estimates) >= _TYPED_MIN_ESTIMATES
            and typed.canonical_bytes == typed_repeat.canonical_bytes
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = evaluate()
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.write(rendered + "\n")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["EvaluationReport", "evaluate", "main"]
