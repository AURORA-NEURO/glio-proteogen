"""Execute the M09-08 publication, abstention, and replay matrix."""

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

from tests.modules.c09_complex_stoichiometry.test_m09_08_publisher import _request

from glio_proteogen.modules.c09_complex_stoichiometry.m09_08_evidence_explanation_publisher import (
    M0908EvidencePublisher,
)

EXPECTED_SOURCE_COUNT = 5
EXPECTED_ASSUMPTION_COUNT = 1
EXPECTED_COUNTER_EVIDENCE_COUNT = 1


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    supported_status: str
    missing_assumptions_status: str
    missing_counter_evidence_status: str
    incomplete_reconstruction_status: str
    missing_source_status: str
    replay_verified: bool
    tamper_rejected: bool
    deterministic: bool
    bundle_closed: bool
    explanation_closed: bool
    passed: bool


def evaluate() -> EvaluationReport:
    engine = M0908EvidencePublisher()
    supported = engine.publish(_request())
    repeat = engine.publish(_request())
    missing_assumptions = engine.publish(_request(include_assumptions=False))
    missing_counter = engine.publish(_request(include_counter_evidence=False))
    incomplete = engine.publish(_request(include_reconstruction=False))
    missing_source = engine.publish(
        _request().model_copy(update={"source_artifacts": _request().source_artifacts[:-1]})
    )
    replay = engine.verify(supported.result, supported.canonical_bytes)
    tampered = engine.verify(supported.result, supported.canonical_bytes + b" ")
    bundle = supported.result.bundle
    explanation = supported.result.explanation
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M09-08",
        contract_version="0.1.0-provisional",
        supported_status=supported.result.status.value,
        missing_assumptions_status=missing_assumptions.result.status.value,
        missing_counter_evidence_status=missing_counter.result.status.value,
        incomplete_reconstruction_status=incomplete.result.status.value,
        missing_source_status=missing_source.result.status.value,
        replay_verified=replay.verified,
        tamper_rejected=not tampered.verified,
        deterministic=supported.canonical_bytes == repeat.canonical_bytes,
        bundle_closed=(
            bundle is not None
            and bundle.reconstruction_status.value == "complete"
            and len(bundle.sources) == EXPECTED_SOURCE_COUNT
            and len(bundle.assumptions) == EXPECTED_ASSUMPTION_COUNT
            and len(bundle.counter_evidence) == EXPECTED_COUNTER_EVIDENCE_COUNT
        ),
        explanation_closed=(
            explanation is not None and explanation.bundle_id == bundle.bundle_id
            if bundle and explanation
            else False
        ),
        passed=(
            supported.result.status.value == "published"
            and missing_assumptions.result.status.value == "abstained"
            and missing_counter.result.status.value == "abstained"
            and incomplete.result.status.value == "abstained"
            and missing_source.result.status.value == "abstained"
            and replay.verified
            and not tampered.verified
            and supported.canonical_bytes == repeat.canonical_bytes
            and bundle is not None
            and explanation is not None
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
