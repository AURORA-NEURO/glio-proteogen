"""Executable M09-06 support, coverage, abstention, and replay matrix."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.modules.c09_complex_stoichiometry.test_m09_06_uncertainty import _request

from glio_proteogen.contracts.m09_06 import SensitivityEnvelopeStatus
from glio_proteogen.modules.c09_complex_stoichiometry import (
    m09_06_uncertainty_decomposition_engine as m0906_module,
)

M0906Service = m0906_module.M0906Service
M0906UncertaintyDecompositionEngine = m0906_module.M0906UncertaintyDecompositionEngine
_DIMENSION_COUNT = 7


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    supported_status: str
    unsupported_status: str
    uncalibrated_status: str
    seven_dimensions: int
    sensitivity_status: str
    replay_verified: bool
    tamper_rejected: bool
    deterministic: bool
    passed: bool


def evaluate() -> EvaluationReport:
    service = M0906Service()
    supported = service.execute(_request())
    repeat = service.execute(_request())
    unsupported = service.execute(_request(method="unsupported:foundation-model"))
    uncalibrated = service.execute(_request(method="uncalibrated-estimator"))
    replay = M0906UncertaintyDecompositionEngine.verify(
        supported.result,
        supported.canonical_bytes,
    )
    tampered = M0906UncertaintyDecompositionEngine.verify(
        supported.result,
        supported.canonical_bytes + b" ",
    )
    dimensions = (
        len(supported.result.decomposition.components)
        if supported.result.decomposition is not None
        else 0
    )
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M09-06",
        contract_version="0.1.0-provisional",
        supported_status=supported.result.status.value,
        unsupported_status=unsupported.result.status.value,
        uncalibrated_status=uncalibrated.result.status.value,
        seven_dimensions=dimensions,
        sensitivity_status=supported.result.sensitivity_envelope.status.value,
        replay_verified=replay.verified,
        tamper_rejected=not tampered.verified,
        deterministic=supported.canonical_bytes == repeat.canonical_bytes,
        passed=(
            supported.result.status.value == "decomposed"
            and unsupported.result.status.value == "abstained"
            and uncalibrated.result.status.value == "abstained"
            and dimensions == _DIMENSION_COUNT
            and supported.result.sensitivity_envelope.status is SensitivityEnvelopeStatus.EVALUATED
            and replay.verified
            and not tampered.verified
            and supported.canonical_bytes == repeat.canonical_bytes
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
