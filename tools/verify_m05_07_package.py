"""Verify the M05-07 package boundary in source or an installed environment."""

# Verification failures deliberately carry an operator-facing detail.
# ruff: noqa: TRY003, TRY004

from __future__ import annotations

import argparse
import importlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Final

MODULE_ID: Final = "GLIO-PROTEOGEN-M05-07"
EXPECTED_VERSION: Final = "0.1.0-provisional"
EXPECTED_SCHEMAS: Final = frozenset(
    {"request", "output", "policy", "prerequisites", "fact", "receipt"}
)
EXPECTED_MEMBERS: Final = frozenset(
    {
        "glio_proteogen/contracts/m05_07/__init__.py",
        "glio_proteogen/contracts/m05_07/canonical.py",
        "glio_proteogen/contracts/m05_07/schema.py",
        "glio_proteogen/contracts/m05_07/v1.py",
    }
)


def _verify_import() -> dict[str, object]:
    contracts = importlib.import_module("glio_proteogen.contracts.m05_07")
    schemas = contracts.contract_json_schemas()
    if frozenset(schemas) != EXPECTED_SCHEMAS:
        raise RuntimeError("M05-07 schema registry is not closed")
    for name, schema in schemas.items():
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise RuntimeError(f"M05-07 {name} schema has the wrong dialect")
        metadata = schema.get("x-glio-contract")
        if not isinstance(metadata, dict):
            raise RuntimeError(f"M05-07 {name} schema is missing ABI metadata")
        if metadata.get("moduleId") != MODULE_ID:
            raise RuntimeError(f"M05-07 {name} schema has the wrong module")
        if metadata.get("contractVersion") != EXPECTED_VERSION:
            raise RuntimeError(f"M05-07 {name} schema has the wrong version")
        if metadata.get("provisionalAbi") is not True:
            raise RuntimeError(f"M05-07 {name} schema is not marked provisional")
        if metadata.get("pendingOwnerConfirmation") is not True:
            raise RuntimeError(f"M05-07 {name} schema lacks owner-confirmation marker")
    importlib.import_module(
        "glio_proteogen.modules.c05_ptm_localization.m05_07_unsupported_abstention_router"
    )
    return {"schema_count": len(schemas), "module_id": MODULE_ID, "provisional_abi": True}


def _verify_wheel(path: Path) -> dict[str, object]:
    try:
        with zipfile.ZipFile(path) as archive:
            members = frozenset(archive.namelist())
    except (OSError, zipfile.BadZipFile) as error:
        raise RuntimeError("candidate wheel cannot be read") from error
    missing = sorted(EXPECTED_MEMBERS - members)
    if missing:
        raise RuntimeError(f"candidate wheel omits M05-07 members: {', '.join(missing)}")
    return {"wheel": str(path), "required_members": len(EXPECTED_MEMBERS)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path)
    args = parser.parse_args()
    report: dict[str, object] = {"passed": True, "import": _verify_import()}
    if args.wheel is not None:
        report["wheel"] = _verify_wheel(args.wheel)
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
