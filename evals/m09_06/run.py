"""Executable M09-06 support, coverage, abstention, and replay matrix."""

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

from tests.modules.c09_complex_stoichiometry.test_m09_06_uncertainty import (
    _request,
    _typed_request,
)

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
    typed_status: str
    typed_model: str
    typed_interval_components: int
    typed_bottleneck_probability: float | None
    replay_verified: bool
    typed_replay_verified: bool
    tamper_rejected: bool
    deterministic: bool
    passed: bool


def evaluate() -> EvaluationReport:
    service = M0906Service()
    supported = service.execute(_request())
    typed = service.execute(_typed_request())
    repeat = service.execute(_request())
    unsupported = service.execute(_request(method="unsupported:foundation-model"))
    uncalibrated = service.execute(_request(method="uncalibrated-estimator"))
    replay = M0906UncertaintyDecompositionEngine.verify(
        supported.result,
        supported.canonical_bytes,
    )
    typed_replay = M0906UncertaintyDecompositionEngine.verify(
        typed.result,
        typed.canonical_bytes,
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
    typed_decomposition = typed.result.decomposition
    typed_support = (
        next(
            (
                component.estimate.probability
                for component in typed_decomposition.components
                if component.dimension.value == "support"
            ),
            None,
        )
        if typed_decomposition is not None
        else None
    )
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M09-06",
        contract_version="0.1.0-provisional",
        supported_status=supported.result.status.value,
        unsupported_status=unsupported.result.status.value,
        uncalibrated_status=uncalibrated.result.status.value,
        seven_dimensions=dimensions,
        sensitivity_status=supported.result.sensitivity_envelope.status.value,
        typed_status=typed.result.status.value,
        typed_model=(typed_decomposition.method if typed_decomposition is not None else ""),
        typed_interval_components=(
            len(typed_decomposition.components) if typed_decomposition is not None else 0
        ),
        typed_bottleneck_probability=typed_support,
        replay_verified=replay.verified,
        typed_replay_verified=typed_replay.verified,
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
            and typed.result.status.value == "decomposed"
            and typed_decomposition is not None
            and len(typed_decomposition.components) == _DIMENSION_COUNT
            and typed_replay.verified
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
