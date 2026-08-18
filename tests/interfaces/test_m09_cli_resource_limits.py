"""Resource-admission regressions for the eight M09 Typer CLIs."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from glio_proteogen.modules.c09_complex_activity.m09_02_representation_feature_constructor import (
    cli as m0902,
)
from glio_proteogen.modules.c09_complex_activity.m09_03_mature_baseline_estimator import (
    cli as m0903,
)
from glio_proteogen.modules.c09_complex_activity.m09_05_mechanism_constraint_integrator import (
    cli as m0905,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_01_formal_state_feature_schema import (
    cli as m0901,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_04_probabilistic_estimator import (
    cli as m0904,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_06_uncertainty_decomposition_engine import (  # noqa: E501
    cli as m0906,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_07_calibration_selective_prediction import (  # noqa: E501
    cli as m0907,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_08_evidence_explanation_publisher import (
    cli as m0908,
)

_MAX_JSON_BYTES = 4 * 1024 * 1024
_CLIS: tuple[tuple[Any, str], ...] = (
    (m0901, "m09_01_formal_state_feature_schema/cli.py"),
    (m0902, "m09_02_representation_feature_constructor/cli.py"),
    (m0903, "m09_03_mature_baseline_estimator/cli.py"),
    (m0904, "m09_04_probabilistic_estimator/cli.py"),
    (m0905, "m09_05_mechanism_constraint_integrator/cli.py"),
    (m0906, "m09_06_uncertainty_decomposition_engine/cli.py"),
    (m0907, "m09_07_calibration_selective_prediction/cli.py"),
    (m0908, "m09_08_evidence_explanation_publisher/cli.py"),
)


def test_m09_validate_commands_reject_sparse_oversized_inputs(tmp_path: Path) -> None:
    path = tmp_path / "oversized.json"
    with path.open("wb") as stream:
        stream.seek(_MAX_JSON_BYTES)
        stream.write(b"x")
    for module, _ in _CLIS:
        result = CliRunner().invoke(module.app, ["validate", str(path)])
        assert result.exit_code != 0


def test_m09_cli_sources_have_no_unbounded_path_reads() -> None:
    for module, relative in _CLIS:
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Attribute) and node.attr == "read_bytes" for node in ast.walk(tree)
        ), relative
