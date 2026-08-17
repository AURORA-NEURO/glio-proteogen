"""Executable M06-02 evaluation scenarios."""

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

from tests.contract.test_m06_02_contract import _request
from tests.modules.c06_protein_abundance.test_m06_02_representation_constructor import (
    _with_feature_state,
)

from glio_proteogen.contracts.m06_02 import (
    RepresentationConstructorStatus,
    RepresentationObservationState,
)
from glio_proteogen.modules.c06_protein_abundance.m06_02_representation_feature_constructor import (
    M0602RepresentationEngine,
)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    constructed_status: str
    abstained_status: str
    replay_verified: bool
    explicit_mask: bool
    deterministic: bool
    passed: bool


def evaluate() -> EvaluationReport:
    engine = M0602RepresentationEngine()
    first = engine.construct(_request())
    second = engine.construct(_request())
    replay = engine.verify(first.result, first.canonical_bytes)
    abstained = engine.construct(
        _with_feature_state(RepresentationObservationState.UNSUPPORTED)
    )
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M06-02",
        contract_version="0.1.0-provisional",
        constructed_status=first.result.status.value,
        abstained_status=abstained.result.status.value,
        replay_verified=replay.verified,
        explicit_mask=bool(abstained.result.masks),
        deterministic=first.canonical_bytes == second.canonical_bytes,
        passed=(
            first.result.status is RepresentationConstructorStatus.CONSTRUCTED
            and abstained.result.status is RepresentationConstructorStatus.ABSTAINED
            and replay.verified
            and bool(abstained.result.masks)
            and first.canonical_bytes == second.canonical_bytes
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
