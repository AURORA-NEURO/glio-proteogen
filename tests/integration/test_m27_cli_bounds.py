"""Resource-bound parity for the M27 Typer file interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from glio_proteogen.contracts.m27_03 import (
    M2703_MAX_CANONICAL_REQUEST_BYTES,
    M2703_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m27_05 import (
    M2705_MAX_CANONICAL_REQUEST_BYTES,
    M2705_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m27_06 import (
    M2706_MAX_CANONICAL_REQUEST_BYTES,
    M2706_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m27_07 import (
    M2707_MAX_CANONICAL_REQUEST_BYTES,
    M2707_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m27_08 import (
    M2708_MAX_CANONICAL_REQUEST_BYTES,
    M2708_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.modules.c27_complex_activity.m27_03_reproducible_pipeline_orchestrator import (
    cli as m2703_cli,
)
from glio_proteogen.modules.c27_complex_activity.m27_05_observability_telemetry import (
    cli as m2705_cli,
)
from glio_proteogen.modules.c27_complex_activity.m27_06_security_access import (
    cli as m2706_cli,
)
from glio_proteogen.modules.c27_complex_activity.m27_07_change_control import (
    cli as m2707_cli,
)
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement import cli as m2708_cli

if TYPE_CHECKING:
    from pathlib import Path

    from typer import Typer


@dataclass(frozen=True)
class _CliCase:
    app: Typer
    request_command: str
    result_command: str
    request_limit: int
    result_limit: int


_CASES = (
    _CliCase(
        m2703_cli.app,
        "validate",
        "verify",
        M2703_MAX_CANONICAL_REQUEST_BYTES,
        M2703_MAX_CANONICAL_RESULT_BYTES,
    ),
    _CliCase(
        m2705_cli.app,
        "validate",
        "verify",
        M2705_MAX_CANONICAL_REQUEST_BYTES,
        M2705_MAX_CANONICAL_RESULT_BYTES,
    ),
    _CliCase(
        m2706_cli.app,
        "validate",
        "verify",
        M2706_MAX_CANONICAL_REQUEST_BYTES,
        M2706_MAX_CANONICAL_RESULT_BYTES,
    ),
    _CliCase(
        m2707_cli.cli,
        "validate",
        "verify",
        M2707_MAX_CANONICAL_REQUEST_BYTES,
        M2707_MAX_CANONICAL_RESULT_BYTES,
    ),
    _CliCase(
        m2708_cli.cli,
        "validate",
        "verify",
        M2708_MAX_CANONICAL_REQUEST_BYTES,
        M2708_MAX_CANONICAL_RESULT_BYTES,
    ),
)


def _sparse_file(path: Path, size: int) -> None:
    with path.open("wb") as stream:
        stream.truncate(size)


@pytest.mark.parametrize("case", _CASES)
def test_request_cli_rejects_oversized_file_before_json_parsing(
    case: _CliCase, tmp_path: Path
) -> None:
    request = tmp_path / "oversized-request.json"
    _sparse_file(request, case.request_limit + 1)
    invocation = CliRunner().invoke(case.app, [case.request_command, str(request)])
    assert invocation.exit_code != 0
    assert "Traceback" not in invocation.output
    assert "RequestBodyTooLargeError" not in invocation.output


@pytest.mark.parametrize("case", _CASES)
def test_result_cli_rejects_oversized_file_before_json_parsing(
    case: _CliCase, tmp_path: Path
) -> None:
    result = tmp_path / "oversized-result.json"
    _sparse_file(result, case.result_limit + 1)
    invocation = CliRunner().invoke(case.app, [case.result_command, str(result)])
    assert invocation.exit_code != 0
    assert "Traceback" not in invocation.output
    assert "RequestBodyTooLargeError" not in invocation.output
