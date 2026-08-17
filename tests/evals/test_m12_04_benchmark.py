"""Direct-execution regression for the M12-04 benchmark wrapper."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).parents[2]


def test_benchmark_script_is_directly_executable() -> None:
    completed = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(_ROOT / "evals" / "m12_04" / "benchmark.py"),
            "--iterations",
            "1",
        ],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
