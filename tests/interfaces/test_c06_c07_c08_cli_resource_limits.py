"""Size-boundary regressions for the remaining C06-C08 module CLIs."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from glio_proteogen.adapters.limits import RequestBodyTooLargeError

_CLI_FILES = (
    "modules/c06_protein_abundance/m06_02_representation_feature_constructor/cli.py",
    "modules/c06_protein_abundance/m06_05_mechanism_constraint_integrator/cli.py",
    "modules/c06_protein_abundance/m06_07_calibration_selective_prediction/cli.py",
    "modules/c07_copy_number/m07_01_formal_state_feature_schema/cli.py",
    "modules/c07_copy_number/m07_02_representation_feature_constructor/cli.py",
    "modules/c07_copy_number_dosage/m07_05_mechanism_constraint_integrator/cli.py",
    "modules/c07_copy_number_dosage/m07_06_uncertainty_decomposition/cli.py",
    "modules/c07_copy_number_dosage/m07_07_calibration_selective_prediction/cli.py",
    "modules/c08_transcript_protein_discordance/m08_02_representation_feature_constructor/cli.py",
    "modules/c08_transcript_protein_discordance/m08_05_mechanism_constraint_integrator/cli.py",
    "modules/c08_transcript_protein_discordance/m08_06_uncertainty_decomposition/cli.py",
    "modules/c08_transcript_protein_discordance/m08_07_calibration_selective_prediction/cli.py",
    "modules/c08_transcript_protein_discordance/m08_08_evidence_explanation_publisher/cli.py",
)

_READERS: tuple[tuple[str, str], ...] = (
    (
        "glio_proteogen.modules.c06_protein_abundance.m06_02_representation_feature_constructor.cli",
        "_read",
    ),
    (
        "glio_proteogen.modules.c06_protein_abundance.m06_05_mechanism_constraint_integrator.cli",
        "_read",
    ),
    (
        "glio_proteogen.modules.c06_protein_abundance.m06_07_calibration_selective_prediction.cli",
        "_read",
    ),
    (
        "glio_proteogen.modules.c07_copy_number.m07_01_formal_state_feature_schema.cli",
        "_request_from_file",
    ),
    (
        "glio_proteogen.modules.c07_copy_number.m07_02_representation_feature_constructor.cli",
        "_read",
    ),
    (
        "glio_proteogen.modules.c07_copy_number_dosage.m07_05_mechanism_constraint_integrator.cli",
        "_read",
    ),
    (
        "glio_proteogen.modules.c07_copy_number_dosage.m07_06_uncertainty_decomposition.cli",
        "_read",
    ),
    (
        "glio_proteogen.modules.c07_copy_number_dosage.m07_07_calibration_selective_prediction.cli",
        "_read",
    ),
    (
        "glio_proteogen.modules.c08_transcript_protein_discordance.m08_02_representation_feature_constructor.cli",
        "_read",
    ),
    (
        "glio_proteogen.modules.c08_transcript_protein_discordance.m08_05_mechanism_constraint_integrator.cli",
        "_read",
    ),
    (
        "glio_proteogen.modules.c08_transcript_protein_discordance.m08_06_uncertainty_decomposition.cli",
        "_read",
    ),
    (
        "glio_proteogen.modules.c08_transcript_protein_discordance.m08_07_calibration_selective_prediction.cli",
        "_load",
    ),
    (
        "glio_proteogen.modules.c08_transcript_protein_discordance.m08_08_evidence_explanation_publisher.cli",
        "_read",
    ),
)


def _oversized_json(path: Path, limit: int) -> None:
    with path.open("wb") as stream:
        stream.seek(limit)
        stream.write(b"x")


@pytest.mark.parametrize(("module_name", "reader_name"), _READERS)
def test_c06_c07_c08_reader_rejects_oversized_path(
    tmp_path: Path,
    module_name: str,
    reader_name: str,
) -> None:
    module = importlib.import_module(module_name)
    limit = int(
        next(
            value
            for name, value in vars(module).items()
            if name.endswith("MAX_CANONICAL_REQUEST_BYTES")
        )
    )
    path = tmp_path / "oversized.json"
    _oversized_json(path, limit)
    reader = getattr(module, reader_name)
    with pytest.raises(RequestBodyTooLargeError):
        reader(path)


def test_c06_c07_c08_cli_sources_have_no_unbounded_reads() -> None:
    root = Path(__file__).parents[2] / "src" / "glio_proteogen"
    for relative in _CLI_FILES:
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            assert node.func.attr != "read_bytes", relative
            if node.func.attr == "read":
                assert node.args, relative
