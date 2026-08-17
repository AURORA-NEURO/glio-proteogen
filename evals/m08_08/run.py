"""Executable supported/abstention/replay matrix for provisional M08-08."""

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

from tests.modules.c08_transcript_protein_discordance.test_m08_08_publisher import _request

from glio_proteogen.modules.c08_transcript_protein_discordance.m08_08_evidence_explanation_publisher import (
    M0808EvidenceExplanationPublisher,
)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    published_status: str
    unsupported_status: str
    source_count: int
    explanation_count: int
    counter_evidence_count: int
    reconstruction_count: int
    replay_verified: bool
    tamper_rejected: bool
    deterministic: bool
    passed: bool


def evaluate() -> EvaluationReport:
    engine = M0808EvidenceExplanationPublisher()
    supported = engine.publish(_request("source.1", "source.2"))
    repeat = engine.publish(_request("source.1", "source.2"))
    unsupported = engine.publish(_request("source.unsupported"))
    replay = engine.verify(supported.result, supported.canonical_bytes)
    tampered = engine.verify(supported.result, supported.canonical_bytes + b" ")
    bundle = supported.result.evidence_bundle
    explanation = supported.result.explanation
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M08-08",
        contract_version="0.1.0-provisional",
        published_status=supported.result.status.value,
        unsupported_status=unsupported.result.status.value,
        source_count=len(supported.result.evidence),
        explanation_count=len(explanation.diagnostics) if explanation is not None else 0,
        counter_evidence_count=len(bundle.counter_evidence) if bundle is not None else 0,
        reconstruction_count=len(bundle.reconstruction) if bundle is not None else 0,
        replay_verified=replay.verified,
        tamper_rejected=not tampered.verified,
        deterministic=supported.canonical_bytes == repeat.canonical_bytes,
        passed=(
            supported.result.status.value == "published"
            and unsupported.result.status.value == "abstained"
            and bool(supported.result.evidence)
            and bundle is not None
            and explanation is not None
            and bool(bundle.counter_evidence)
            and bool(bundle.reconstruction)
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
