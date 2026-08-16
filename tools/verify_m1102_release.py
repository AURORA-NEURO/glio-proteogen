"""Verify M11-02 evaluator, benchmark, and package evidence manifests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_EXPECTED_ARGC = 2


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"evidence must be an object: {path.name}")  # noqa: TRY003
    return value


def verify(root: Path) -> None:
    expected = ("evaluation.json", "benchmark.json", "package.json")
    documents = {name: _load(root / name) for name in expected}
    for name, document in documents.items():
        if document.get("module_id") != "GLIO-PROTEOGEN-M11-02":
            raise ValueError(f"{name} has the wrong module id")  # noqa: TRY003
        if document.get("contract_version") != "0.1.0-provisional":
            raise ValueError(f"{name} has the wrong contract version")  # noqa: TRY003
    if documents["evaluation.json"].get("passed") is not True:
        raise ValueError("evaluator evidence is not green")  # noqa: TRY003
    if documents["benchmark.json"].get("passed") is not True:
        raise ValueError("benchmark evidence is not green")  # noqa: TRY003
    for artifact in ("wheel", "sdist"):
        item = documents["package.json"].get(artifact)
        if not isinstance(item, dict) or not item.get("filename") or not item.get("sha256"):
            raise ValueError(f"package evidence is incomplete for {artifact}")  # noqa: TRY003


if __name__ == "__main__":
    if len(sys.argv) != _EXPECTED_ARGC:
        raise SystemExit("usage: verify_m1102_release.py RELEASE_EVIDENCE_DIR")  # noqa: TRY003
    verify(Path(sys.argv[1]))
    sys.stdout.write("M11-02 release evidence verified\n")
