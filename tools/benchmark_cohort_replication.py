"""Measure the bounded synthetic replication panel, without a GPU or source data."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tracemalloc
from statistics import median
from time import perf_counter

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cohort_replication import (
    ReplicationRequest,
    algorithm_profile,
    analyze_replication,
    synthetic_demo_request,
    verify_replay,
)
from glio_proteogen.research.cohort_replication.contracts import (
    CohortEffect,
    CohortReceipt,
    FeatureRequest,
)


def synthetic_panel(cohorts: int, features: int) -> ReplicationRequest:
    """Declare entirely fictitious aggregate effects for an operational benchmark."""

    receipts = tuple(
        CohortReceipt(
            cohort_id=f"synthetic-{index}",
            label=f"Fictitious benchmark cohort {index}",
            source_sha256=sha256_digest({"fictitious_benchmark_cohort": index}),
            independence_group=f"declared-disjoint-{index}",
            sample_size=100,
        )
        for index in range(cohorts)
    )
    panel = tuple(
        FeatureRequest(
            feature_id=f"feature-{feature_index}",
            label=f"Synthetic feature {feature_index}",
            effects=tuple(
                CohortEffect(
                    cohort_id=cohort.cohort_id,
                    state="observed",
                    estimate=0.1 * ((feature_index + cohort_index) % 9 - 4),
                    standard_error=0.1 + 0.01 * cohort_index,
                )
                for cohort_index, cohort in enumerate(receipts)
            ),
        )
        for feature_index in range(features)
    )
    return ReplicationRequest.model_validate(
        synthetic_demo_request().model_copy(
            update={
                "analysis_id": "synthetic-operational-benchmark",
                "cohorts": receipts,
                "features": panel,
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohorts", type=int, choices=range(2, 17), default=16)
    parser.add_argument("--features", type=int, choices=range(1, 257), default=256)
    parser.add_argument("--repeats", type=int, choices=range(1, 21), default=5)
    args = parser.parse_args()
    request = synthetic_panel(args.cohorts, args.features)
    result = analyze_replication(request)
    timings = []
    for _ in range(args.repeats):
        start = perf_counter()
        result = analyze_replication(request)
        timings.append(1_000 * (perf_counter() - start))
    replay_start = perf_counter()
    verification = verify_replay(request, result)
    replay_ms = 1_000 * (perf_counter() - replay_start)
    tracemalloc.start()
    analyze_replication(request)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    sys.stdout.write(
        json.dumps(
            {
                "benchmark": "cohort-replication-synthetic-operational-v1",
                "synthetic_only": True,
                "python": platform.python_version(),
                "platform": platform.platform(),
                "cohorts": args.cohorts,
                "features": args.features,
                "aggregate_effects": args.cohorts * args.features,
                "warm_analysis_milliseconds": timings,
                "median_warm_analysis_milliseconds": median(timings),
                "single_replay_milliseconds": replay_ms,
                "python_traced_peak_bytes_separate_run": peak,
                "request_bytes": len(canonical_json_bytes(request)),
                "result_bytes": len(canonical_json_bytes(result)),
                "replay_valid": verification.valid,
                "profile_digest": algorithm_profile().profile_digest,
                "limitation": (
                    "Local operational measurements only; "
                    "no biological accuracy or distributed-scale claim."
                ),
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
