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
