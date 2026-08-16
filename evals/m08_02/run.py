"""Executable M08-02 representation-construction scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.modules.c08_transcript_protein_discordance.test_m08_02_representation import _request

from glio_proteogen.modules.c08_transcript_protein_discordance import (
    m08_02_representation_feature_constructor as m0802,
)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    constructed_status: str
    leakage_abstained_status: str
    duplicate_source_abstained_status: str
    feature_count: int
    lineage_complete: bool
    leakage_checks_complete: bool
    replay_verified: bool
    deterministic: bool
    passed: bool


def evaluate() -> EvaluationReport:
    engine = m0802.M0802RepresentationEngine()
    request = _request()
    first = engine.construct(request)
    second = engine.construct(request)
    leakage = engine.construct(_request(field="outcome_label"))
    duplicate_request = request.model_copy(
        update={"source_artifacts": (request.source_artifacts[0],) * 2}
    )
    duplicate = engine.construct(duplicate_request)
    replay = engine.verify(first.result, first.canonical_bytes)
    expected_ids = {item.feature_id for item in request.feature_specs}
    lineage_complete = all(
        feature.lineage.feature_id == feature.feature_id
        and feature.lineage.leakage_safe
        and bool(feature.lineage.source_fields)
        and all(item.leakage_safe for item in feature.lineage.transformations)
        for feature in first.result.features
    )
    leakage_checks_complete = {item.check_id for item in first.result.leakage_checks} == {
        f"leakage.{feature_id}" for feature_id in expected_ids
    }
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M08-02",
        contract_version="0.1.0-provisional",
        constructed_status=first.result.status.value,
        leakage_abstained_status=leakage.result.status.value,
        duplicate_source_abstained_status=duplicate.result.status.value,
        feature_count=len(first.result.features),
        lineage_complete=lineage_complete,
        leakage_checks_complete=leakage_checks_complete,
        replay_verified=replay.verified,
        deterministic=first.canonical_bytes == second.canonical_bytes,
        passed=(
            first.result.status.value == "constructed"
            and leakage.result.status.value == "abstained"
            and duplicate.result.status.value == "abstained"
            and lineage_complete
            and leakage_checks_complete
            and replay.verified
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
