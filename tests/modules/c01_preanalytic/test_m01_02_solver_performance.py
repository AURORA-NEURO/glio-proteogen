"""Focused equivalence and scaling guards for the M01-02 wide-DAG path."""

from __future__ import annotations

import gc
from copy import deepcopy
from statistics import median
from time import process_time
from typing import Any, cast

import pytest

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.solver import (
    _analyze,
    _component_digest,
)

MAX_GRAPH_NODES = 10_000
ORDER_EQUIVALENCE_NODES = 2_048
# This smoke guard also runs under branch coverage on Windows. The dedicated benchmark keeps
# the tighter preregistered performance evidence; this threshold detects gross regressions
# without making the ordinary correctness suite depend on instrumentation overhead.
MAX_MEDIAN_CPU_SECONDS = 1.000
PERFORMANCE_ROUNDS = 3


def _artifact(role: str, digest_character: str) -> dict[str, str]:
    return {
        "artifact_id": f"artifact.synthetic.performance.{role}",
        "version": "1.0.0",
        "digest": f"sha256:{digest_character * 64}",
        "media_type": "application/json",
    }


def _context() -> dict[str, Any]:
    evidence = _artifact("control", "e")
    accepted = {
        "state": "accepted",
        "policy_version": "1.0.0",
        "evidence": evidence,
    }
    return {
        "request_id": "request.synthetic.performance",
        "actor_id": "actor.synthetic.performance",
        "occurred_at": "2026-08-11T00:00:00Z",
        "references": {
            "approved_configuration": {
                **accepted,
                "decision_id": "decision.synthetic.approved-configuration",
            },
            "identity_authority": {
                **accepted,
                "decision_id": "authority.synthetic.v1",
            },
            "provenance": {**accepted, "decision_id": "decision.synthetic.provenance"},
            "consent": {
                **accepted,
                "decision_id": "decision.synthetic.consent",
                "state": "granted",
            },
            "quality": {**accepted, "decision_id": "decision.synthetic.quality"},
            "support": {**accepted, "decision_id": "decision.synthetic.support"},
            "intended_use": {
                **accepted,
                "decision_id": "decision.synthetic.intended-use",
            },
        },
    }


def _wide_dag(node_count: int) -> dict[str, Any]:
    entity_evidence = [_artifact("entity", "a")]
    operation_evidence = [_artifact("operation", "c")]
    return {
        "policy": {
            "policy_id": "policy.synthetic.performance",
            "version": "1.0.0",
            "max_component_size": 256,
            "maximum_depth": 64,
            "allow_mixed_subject_pooling": False,
            "require_demultiplex_authority": True,
            "allowed_operation_kinds": ["computed_from"],
        },
        "context": _context(),
        "entities": [
            {
                "entity_id": f"obj-{index:05d}",
                "kind": "derived_object",
                "composition": "unknown",
                "identity_tokens": [],
                "evidence": entity_evidence,
            }
            for index in range(node_count)
        ],
        "assertions": [],
        "lineage_operations": [
            {
                "operation_id": f"op-{index:05d}",
                "kind": "computed_from",
                "source_entity_ids": ["obj-00000"],
                "target_entity_ids": [f"obj-{index:05d}"],
                "mixed_subject": False,
                "authority_decision_id": "authority.synthetic.v1",
                "policy_version": "1.0.0",
                "evidence": operation_evidence,
            }
            for index in range(1, node_count)
        ],
        "concordance_observations": [],
    }


@pytest.mark.parametrize(
    ("members", "policy_identity"),
    [
        (("a",), "policy.a@1.0.0"),
        (("a", "b", "z-Z:9._"), "policy.long-name@1.2.3-rc.1"),
        (("entity." + ("x" * 100),), "policy.boundary@999.999.999"),
    ],
)
def test_fast_component_digest_is_exactly_canonical(
    members: tuple[str, ...],
    policy_identity: str,
) -> None:
    expected = sha256_digest(
        {
            "members": members,
            "policy_identity": policy_identity,
            "purpose": "GLIO-PROTEOGEN-M01-02.identity-component.v1",
        }
    )

    assert _component_digest(members, policy_identity) == expected


def test_wide_dag_optimization_preserves_order_invariant_analysis() -> None:
    forward = _wide_dag(ORDER_EQUIVALENCE_NODES)
    reverse = deepcopy(forward)
    reverse["entities"].reverse()
    reverse["lineage_operations"].reverse()

    expected = _analyze(cast("Any", forward))
    actual = _analyze(cast("Any", reverse))

    assert actual == expected
    assert len(actual.components) == ORDER_EQUIVALENCE_NODES
    assert len(actual.lineage_edges) == ORDER_EQUIVALENCE_NODES - 1
    assert not actual.issues


@pytest.mark.benchmark
def test_ten_thousand_node_wide_dag_has_isolated_cpu_headroom() -> None:
    request = _wide_dag(MAX_GRAPH_NODES)
    warmup = _analyze(cast("Any", request))
    assert len(warmup.components) == MAX_GRAPH_NODES

    samples: list[float] = []
    for _ in range(PERFORMANCE_ROUNDS):
        gc.collect()
        started = process_time()
        analysis = _analyze(cast("Any", request))
        samples.append(process_time() - started)
        assert len(analysis.lineage_edges) == MAX_GRAPH_NODES - 1
        assert not analysis.issues

    assert median(samples) < MAX_MEDIAN_CPU_SECONDS, samples
