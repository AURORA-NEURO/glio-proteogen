"""Emit hashed wheel and sdist records for the M19-07 release bundle."""

# ruff: noqa: TRY003

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from zipfile import ZipFile

MODULE_ID = "GLIO-PROTEOGEN-M19-07"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {
        "filename": path.name,
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }
    if path.suffix == ".whl":
        with ZipFile(path) as archive:
            record["member_count"] = len(
                [entry for entry in archive.infolist() if not entry.is_dir()]
            )
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--isolated-import", action="store_true")
    arguments = parser.parse_args()
    wheels = sorted(arguments.dist.glob("*.whl"))
    sdists = sorted(arguments.dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise RuntimeError("expected exactly one wheel and one sdist")
    document = {
        "module_id": MODULE_ID,
        "wheel": _record(wheels[0]),
        "sdist": _record(sdists[0]),
        "isolated_import": arguments.isolated_import,
    }
    arguments.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
