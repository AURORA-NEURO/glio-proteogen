"""Tests for strict, dependency-free workflow validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.validate_workflows import WorkflowValidationError, validate_workflow


def test_repository_workflow_has_unique_mapping_keys() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    workflow = repository_root / ".github" / "workflows" / "ci.yml"

    validate_workflow(workflow)
    release_workflow = repository_root / ".github" / "workflows" / "release-evidence.yml"
    validate_workflow(release_workflow)
    workflow_text = workflow.read_text(encoding="utf-8")
    release_text = release_workflow.read_text(encoding="utf-8")
    assert "push:\n    branches:\n      - main" in workflow_text
    assert "YAML.parse_file(path)" in workflow_text
    assert "python tools/validate_workflows.py" in workflow_text
    for text in (workflow_text, release_text):
        assert "tools/verify_module_validation.py" in text
        assert "--run-evaluators" in text
        assert "--run-benchmarks" in text
        assert "--shard-index" in text
        assert "--shard-count 8" in text
        assert "--evaluator-timeout-seconds 300" in text
        assert "--benchmark-timeout-seconds 300" in text
    assert "--junit-xml module-tests.junit.xml" in workflow_text
    assert "--coverage-report coverage.xml" in workflow_text
    assert "git ls-files tests | grep -E" in workflow_text
    assert "rg --files" not in workflow_text
    assert "tests/research/test_m15_longitudinal_recurrence_facade.py" in workflow_text
    assert "tests/integration/test_m15_longitudinal_recurrence_facade.py" in workflow_text
    assert "tests/research/test_m09_complex_transition_facade.py" in workflow_text
    assert "tests/integration/test_m09_complex_transition_facade.py" in workflow_text
    test_and_eval = workflow_text.split("  test-and-eval:\n", maxsplit=1)[1].split(
        "\n  evaluator-receipts:", maxsplit=1
    )[0]
    assert "\n    timeout-minutes: 240\n" in test_and_eval
    assert "uv run pytest tests --junitxml=module-tests.junit.xml" in test_and_eval
    assert "tools/verify_module_validation.py" in test_and_eval
    assert "name: module-test-coverage-validation" in test_and_eval
    assert "-m evals." not in test_and_eval
    assert "emit_research_pipeline_evidence.py" not in test_and_eval
    evaluator_receipts = workflow_text.split("  evaluator-receipts:\n", maxsplit=1)[1].split(
        "\n  microbenchmarks:", maxsplit=1
    )[0]
    assert "\n    timeout-minutes: 60\n" in evaluator_receipts
    assert "\n    needs:" not in evaluator_receipts
    assert "uv sync --locked --all-groups" in evaluator_receipts
    assert "uv build" not in evaluator_receipts
    assert "-m evals.m01_01.run" in evaluator_receipts
    assert "-m evals.m05_08.run" in evaluator_receipts
    assert "emit_research_pipeline_evidence.py" in evaluator_receipts
    assert "microbenchmarks:\n    runs-on: ubuntu-latest\n    timeout-minutes: 30" in workflow_text
    assert "--junit-xml evidence/tests.junit.xml" in release_text
    assert "--coverage-report evidence/coverage.xml" in release_text


def test_duplicate_step_input_is_rejected(tmp_path: Path) -> None:
    workflow = tmp_path / "duplicate.yml"
    workflow.write_text(
        """name: duplicate
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/upload-artifact@digest
        with:
          name: first
          path: first.json
          name: second
""",
        encoding="utf-8",
    )

    with pytest.raises(WorkflowValidationError, match="duplicate mapping key 'name'"):
        validate_workflow(workflow)


def test_shell_block_contents_are_not_parsed_as_yaml(tmp_path: Path) -> None:
    workflow = tmp_path / "block.yml"
    workflow.write_text(
        """name: block
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: |
          first=value
          echo "name: path: $first"
""",
        encoding="utf-8",
    )

    validate_workflow(workflow)


def test_required_top_level_keys_are_enforced(tmp_path: Path) -> None:
    workflow = tmp_path / "missing.yml"
    workflow.write_text("name: incomplete\non: push\n", encoding="utf-8")

    with pytest.raises(WorkflowValidationError, match="missing top-level keys: jobs"):
        validate_workflow(workflow)
