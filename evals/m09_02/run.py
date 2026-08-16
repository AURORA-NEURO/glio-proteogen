"""Executable M09-02 construction, safe-failure, leakage, and replay matrix."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.modules.c09_complex_activity.test_m09_02_constructor import _request

from glio_proteogen.modules.c09_complex_activity import (
    m09_02_representation_feature_constructor as m0902,
)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    constructed_status: str
    unsupported_status: str
    leakage_failure_status: str
    leakage_check_status: str
    replay_verified: bool
    tamper_rejected: bool
    deterministic: bool
    lineage_complete: bool
    passed: bool


def evaluate() -> EvaluationReport:
    engine = m0902.M0902RepresentationConstructor()
    supported = engine.construct(_request())
    repeat = engine.construct(_request())
    unsupported = engine.construct(_request(marker="unsupported"))
    leakage_request = _request().model_copy(
        update={"policy": _request().policy.model_copy(update={"mask_policy": "leakage_failure"})}
    )
    leakage = engine.construct(leakage_request)
    replay = engine.verify(supported.result, supported.canonical_bytes)
    tampered = engine.verify(supported.result, supported.canonical_bytes + b" ")
    lineage_complete = bool(supported.result.features) and all(
        feature.lineage.leakage_safe and feature.lineage.source_fields
        for feature in supported.result.features
    )
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M09-02",
        contract_version="0.1.0-provisional",
        constructed_status=supported.result.status.value,
        unsupported_status=unsupported.result.status.value,
        leakage_failure_status=leakage.result.status.value,
        leakage_check_status=leakage.result.leakage_checks[0].status.value,
        replay_verified=replay,
        tamper_rejected=not tampered,
        deterministic=supported.canonical_bytes == repeat.canonical_bytes,
        lineage_complete=lineage_complete,
        passed=(
            supported.result.status.value == "constructed"
            and unsupported.result.status.value == "abstained"
            and leakage.result.status.value == "abstained"
            and leakage.result.leakage_checks[0].status.value == "failed"
            and replay
            and not tampered
            and supported.canonical_bytes == repeat.canonical_bytes
            and lineage_complete
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
