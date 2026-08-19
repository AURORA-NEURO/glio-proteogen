"""Adversarial strict-parser coverage for M24--M26 result file readers."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType


_CLI_MODULES: tuple[tuple[str, str], ...] = (
    (
        "glio_proteogen.modules.c21_reference_material.m24_07_human_factors_operational_evaluator.cli",
        "M2407CliError",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m25_01_reference_truth_benchmark_curator.cli",
        "M2501CliError",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m25_02_synthetic_truth_simulation_generator.cli",
        "M2502CliError",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m25_03_internal_benchmark_ablation.cli",
        "M2503CliError",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m25_05_subgroup_equity_evaluator.cli",
        "M2505CliError",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m25_07_human_factors_operational_evaluator.cli",
        "M2507CliError",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m25_08_evidence_gate_release_adjudicator.cli",
        "M2508CliError",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m26_03_reproducible_pipeline_orchestrator.cli",
        "M2603CliError",
    ),
)


class _AcceptingAdapter:
    """Make a parser bypass observable if strict JSON validation is removed."""

    def validate_json(self, data: bytes, *, strict: bool) -> bytes:
        del strict
        return data


@pytest.mark.parametrize(("module_name", "error_name"), _CLI_MODULES)
def test_result_reader_rejects_duplicate_keys_before_schema_validation(
    module_name: str,
    error_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Result replay must reject ambiguous JSON before adapter selection."""

    module: ModuleType = importlib.import_module(module_name)
    monkeypatch.setattr(module, "_RESULT_ADAPTER", _AcceptingAdapter())
    path = tmp_path / "result.json"
    path.write_bytes(
        b'{"result_digest":"sha256:' + b"0" * 64 + b'","result_digest":"sha256:' + b"0" * 64 + b'"}'
    )

    with pytest.raises(getattr(module, error_name)):
        module._read_result(path)  # type: ignore[attr-defined]
