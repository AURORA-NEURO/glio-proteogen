"""Evaluator for research-only external evidence aggregation semantics."""

from __future__ import annotations

import json
import sys
from hashlib import sha256

from glio_proteogen.research import (
    ExternalEvidenceObservation,
    aggregate_external_evidence,
    replay_external_evidence,
)


def _observation(
    evidence_id: str,
    source_id: str,
    direction: str = "supports",
    *,
    source_sha256: str | None = None,
) -> ExternalEvidenceObservation:
    return ExternalEvidenceObservation(
        evidence_id=evidence_id,
        claim_id="caller-claim-1",
        source_id=source_id,
        study_id="PDC000204",
        source_kind="pdc_cohort",
        direction=direction,
        source_sha256=source_sha256 or sha256(source_id.encode()).hexdigest(),
        source_size=1024,
        method_id="caller-method-v1",
        cohort_size=12,
        limitation="missing source receipt" if direction == "abstained" else "",
    )


def run_evidence_aggregation_evaluator() -> dict[str, object]:
    """Run locked support, conflict, abstention, and replay scenarios."""

    scenarios = (
        (
            "consistent_support",
            (_observation("e1", "study-a"), _observation("e2", "study-b")),
            "consistent_support",
        ),
        (
            "mixed_direction",
            (_observation("e1", "study-a"), _observation("e2", "study-b", "contradicts")),
            "mixed_direction",
        ),
        (
            "insufficient_independence",
            (_observation("e1", "study-a"), _observation("e2", "study-a")),
            "abstained_insufficient_independence",
        ),
        (
            "duplicate_receipt_aliases",
            (
                _observation("e1", "study-a", source_sha256="a" * 64),
                _observation("e2", "study-b", source_sha256="a" * 64),
                _observation("e3", "study-c", source_sha256="b" * 64),
            ),
            "consistent_support",
        ),
        (
            "source_conflict",
            (
                _observation("e1", "study-a"),
                _observation("e2", "study-a", "contradicts"),
                _observation("e3", "study-b"),
            ),
            "abstained_source_conflict",
        ),
        (
            "observation_abstention",
            (
                _observation("e1", "study-a", "abstained"),
                _observation("e2", "study-b"),
            ),
            "abstained_observation",
        ),
    )
    outcomes: list[dict[str, object]] = []
    for scenario_id, observations, expected_status in scenarios:
        result = aggregate_external_evidence(observations)
        replay = replay_external_evidence(observations, result)
        outcomes.append(
            {
                "scenario_id": scenario_id,
                "status": result.status,
                "expected_status": expected_status,
                "digest_stable": replay.digest == result.digest,
                "passed": result.status == expected_status and replay.digest == result.digest,
            }
        )
    return {
        "evaluator_version": "research-external-evidence-v1",
        "claim_boundary": "caller-declared descriptive evidence only; no numerical fusion",
        "declared": len(outcomes),
        "executed": len(outcomes),
        "outcomes": outcomes,
        "passed": all(bool(item["passed"]) for item in outcomes),
    }


if __name__ == "__main__":
    sys.stdout.write(json.dumps(run_evidence_aggregation_evaluator(), sort_keys=True))
