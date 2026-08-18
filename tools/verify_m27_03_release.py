"""Standard-library verifier for the machine-readable M27-03 release record."""

# Error messages are intentionally stable for release automation.
# ruff: noqa: TRY003

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

_MODULE = "GLIO-PROTEOGEN-M27-03"
_MIN_TESTS = 21
_MIN_COVERAGE = 95


class ReleaseEvidenceError(ValueError):
    """Raised when machine-readable M27-03 release evidence is inconsistent."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(record: Path, wheel: Path, sdist: Path) -> dict[str, object]:
    evidence = json.loads(record.read_text(encoding="utf-8"))
    if evidence["module"] != _MODULE:
        raise ReleaseEvidenceError("release record has the wrong module")
    if (
        evidence["focused_tests"] < _MIN_TESTS
        or evidence["scoped_coverage"]["percent"] < _MIN_COVERAGE
    ):
        raise ReleaseEvidenceError("release record does not meet local gates")
    if evidence["evaluator"]["passed"] != evidence["evaluator"]["scenario_count"]:
        raise ReleaseEvidenceError("evaluator record is incomplete")
    packages = evidence["packages"]
    for path, expected in ((wheel, packages["wheel"]), (sdist, packages["sdist"])):
        if path.name != expected["filename"]:
            raise ReleaseEvidenceError("package filename does not match release record")
        if path.stat().st_size != expected["bytes"] or _sha256(path) != expected["sha256"]:
            raise ReleaseEvidenceError("package size or SHA256 does not match release record")
    with ZipFile(wheel) as archive:
        if not any(name.endswith(".dist-info/METADATA") for name in archive.namelist()):
            raise ReleaseEvidenceError("wheel has no distribution metadata")
    return {
        "verified": True,
        "module": evidence["module"],
        "wheel": wheel.name,
        "sdist": sdist.name,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=Path, default=Path("evidence/m27_03/release.json"))
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.record, args.wheel, args.sdist), sort_keys=True))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
