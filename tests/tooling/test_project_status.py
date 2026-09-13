"""Tests for reproducible, filesystem-derived project-status evidence."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest
from tools.verify_project_status import (
    PLANNING_CELLS_PER_MODULE,
    PLANNING_MATRIX_TOTAL,
    PLANNING_MODULES,
    PROVISIONAL_SOURCE_IDS,
    ProjectStatusError,
    build_report,
    verify,
)

if TYPE_CHECKING:
    from pathlib import Path

EXPECTED_TEST_FILES_AFTER_ADDITION = 2
EXPECTED_DISCOVERED_BENCHMARKS = 2
EXPECTED_EVIDENCE_FILES = 5
EXPECTED_EVALUATION_ENTRYPOINTS = 2


def test_project_status_reports_discovered_artifact_categories() -> None:
    report = verify()
    inventory = report["inventory"]

    assert report["planning_assumption"] == {
        "modules": PLANNING_MODULES,
        "cells_per_module": PLANNING_CELLS_PER_MODULE,
        "matrix_total": PLANNING_MATRIX_TOTAL,
        "is_completion_claim": False,
    }
    assert set(inventory) == {
        "contracts",
        "engines",
        "adapters",
        "tests",
        "evals",
        "evidence",
    }
    assert inventory["contracts"]["count"] > 0
    assert inventory["engines"]["count"] > 0
    assert inventory["engines"]["services"]["count"] > 0
    assert inventory["engines"]["plugins"]["count"] > 0
    assert inventory["adapters"]["central"]["count"] > 0
    assert inventory["tests"]["count"] > 0
    assert inventory["evals"]["runners"]["count"] > 0
    assert inventory["evals"]["repository_benchmarks"]["count"] > 0
    assert inventory["evidence"]["all"]["count"] > 0
    assert inventory["evidence"]["research_narrative_markdown"]["count"] > 0


def test_project_status_keeps_planning_gaps_explicit() -> None:
    report = build_report()

    assert report["known_provisional_source_ids"] == list(PROVISIONAL_SOURCE_IDS)
    assert report["provisional_contracts_present"] == []


def test_inventory_digest_changes_when_a_discovered_path_changes(tmp_path: Path) -> None:
    _make_minimum_repository(tmp_path)
    before = build_report(tmp_path)

    (tmp_path / "tests" / "contract" / "test_second.py").write_text("", encoding="utf-8")
    after = build_report(tmp_path)

    assert before["inventory_digest"] != after["inventory_digest"]
    assert before["inventory"]["tests"]["count"] == 1
    assert after["inventory"]["tests"]["count"] == EXPECTED_TEST_FILES_AFTER_ADDITION


def test_inventory_digests_bind_paths_and_content_independently(tmp_path: Path) -> None:
    _make_minimum_repository(tmp_path)
    test_file = tmp_path / "tests" / "contract" / "test_example.py"
    report = build_report(tmp_path)
    expected = hashlib.sha256(b"tests/contract/test_example.py").hexdigest()
    content_before = report["inventory"]["tests"]["content_digest"]

    assert report["inventory"]["tests"]["path_digest"] == f"sha256:{expected}"
    test_file.write_text("changed content", encoding="utf-8")
    changed = build_report(tmp_path)["inventory"]["tests"]
    assert changed["path_digest"] == f"sha256:{expected}"
    assert changed["content_digest"] != content_before
    assert changed["bytes"] == len("changed content")
    assert build_report(tmp_path)["inventory_digest"] != report["inventory_digest"]


def test_inventory_discovers_research_engines_benchmarks_and_evidence(tmp_path: Path) -> None:
    _make_minimum_repository(tmp_path)

    inventory = build_report(tmp_path)["inventory"]

    engine_paths = (
        "src/glio_proteogen/modules/c01/m01_01_example/engine.py",
        "src/glio_proteogen/research/proteogenomic_state/engine.py",
    )
    assert inventory["engines"]["count"] == len(engine_paths)
    assert inventory["engines"]["path_digest"] == _paths_digest(*engine_paths)
    assert inventory["evals"]["benchmarks"]["count"] == EXPECTED_DISCOVERED_BENCHMARKS
    assert inventory["evals"]["entrypoints"]["count"] == EXPECTED_EVALUATION_ENTRYPOINTS
    assert inventory["evals"]["alternate_evaluators"]["count"] == 1
    assert inventory["evals"]["repository_benchmarks"]["path_digest"] == _paths_digest(
        "benchmarks/research_proteogenomic_state.py"
    )
    assert inventory["evals"]["repository_benchmarks"]["count"] == 1
    assert inventory["evidence"]["research_narrative_markdown"]["path_digest"] == _paths_digest(
        "docs/research/evidence-conserving-graph-inference.md"
    )
    assert inventory["evidence"]["research_narrative_markdown"]["count"] == 1
    assert inventory["evidence"]["all"]["count"] == EXPECTED_EVIDENCE_FILES


def test_verify_rejects_a_known_provisional_contract_package(tmp_path: Path) -> None:
    _make_minimum_repository(tmp_path)
    (tmp_path / "src" / "glio_proteogen" / "contracts" / "m23_06").mkdir()

    with pytest.raises(ProjectStatusError, match="known provisional contracts"):
        verify(tmp_path)


def _make_minimum_repository(root: Path) -> None:
    paths = (
        "src/glio_proteogen/contracts/m01_01",
        "src/glio_proteogen/modules/c01/m01_01_example",
        "src/glio_proteogen/research/proteogenomic_state",
        "src/glio_proteogen/adapters",
        "tests/contract",
        "evals/m01_01",
        "evals/m01_02",
        "benchmarks",
        "evidence",
        "release-evidence/m01_01",
        "docs/evidence",
        "docs/release-evidence",
        "docs/research",
    )
    for relative in paths:
        (root / relative).mkdir(parents=True, exist_ok=True)
    for relative in (
        "src/glio_proteogen/modules/c01/m01_01_example/engine.py",
        "src/glio_proteogen/research/proteogenomic_state/engine.py",
        "src/glio_proteogen/modules/c01/m01_01_example/service.py",
        "src/glio_proteogen/modules/c01/m01_01_example/plugin.py",
        "src/glio_proteogen/modules/c01/m01_01_example/api.py",
        "src/glio_proteogen/modules/c01/m01_01_example/cli.py",
        "src/glio_proteogen/adapters/api.py",
        "tests/contract/test_example.py",
        "evals/m01_01/run.py",
        "evals/m01_02/evaluator.py",
        "evals/m01_01/benchmark.py",
        "benchmarks/research_proteogenomic_state.py",
        "evidence/m01-01-evaluation.json",
        "release-evidence/m01_01/package.json",
        "docs/evidence/M01-01.md",
        "docs/evidence/M01-01.json",
        "docs/research/evidence-conserving-graph-inference.md",
    ):
        (root / relative).write_text("", encoding="utf-8")


def _paths_digest(*paths: str) -> str:
    payload = "\n".join(sorted(paths)).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
