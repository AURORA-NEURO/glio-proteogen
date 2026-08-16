"""Verify the M06-04 provisional package boundary in source or a wheel."""

# Operator-facing verification errors are intentionally descriptive.
# ruff: noqa: TRY003, TRY004

from __future__ import annotations

import argparse
import importlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Final

MODULE_ID: Final = "GLIO-PROTEOGEN-M06-04"
CONTRACT_VERSION: Final = "0.1.0-provisional"
EXPECTED_SCHEMAS: Final = frozenset(
    {
        "request",
        "output",
        "configuration",
        "prior",
        "constraint",
        "posterior",
        "diagnostic",
    }
)
EXPECTED_MEMBERS: Final = frozenset(
    {
        "glio_proteogen/contracts/m06_04/__init__.py",
        "glio_proteogen/contracts/m06_04/canonical.py",
        "glio_proteogen/contracts/m06_04/schema.py",
        "glio_proteogen/contracts/m06_04/v1.py",
        "glio_proteogen/modules/c06_protein_abundance/m06_04_probabilistic_advanced_estimator/__init__.py",
        "glio_proteogen/modules/c06_protein_abundance/m06_04_probabilistic_advanced_estimator/engine.py",
        "glio_proteogen/modules/c06_protein_abundance/m06_04_probabilistic_advanced_estimator/plugin.py",
        "glio_proteogen/modules/c06_protein_abundance/m06_04_probabilistic_advanced_estimator/service.py",
    }
)


def _verify_import() -> dict[str, object]:
    contracts = importlib.import_module("glio_proteogen.contracts.m06_04")
    schemas = contracts.contract_json_schemas()
    if frozenset(schemas) != EXPECTED_SCHEMAS:
        raise RuntimeError("M06-04 schema registry is not closed")
    for name, schema in schemas.items():
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise RuntimeError(f"M06-04 {name} schema has the wrong dialect")
        metadata = schema.get("x-glio-contract")
        if not isinstance(metadata, dict):
            raise RuntimeError(f"M06-04 {name} schema is missing ABI metadata")
        if metadata.get("moduleId") != MODULE_ID:
            raise RuntimeError(f"M06-04 {name} schema has the wrong module")
        if metadata.get("contractVersion") != CONTRACT_VERSION:
            raise RuntimeError(f"M06-04 {name} schema has the wrong version")
        if metadata.get("provisionalAbi") is not True:
            raise RuntimeError(f"M06-04 {name} schema is not marked provisional")
        if metadata.get("pendingOwnerConfirmation") is not True:
            raise RuntimeError(f"M06-04 {name} schema lacks owner-confirmation marker")
    importlib.import_module(
        "glio_proteogen.modules.c06_protein_abundance.m06_04_probabilistic_advanced_estimator"
    )
    return {"module_id": MODULE_ID, "schema_count": len(schemas), "provisional_abi": True}


def _verify_wheel(path: Path) -> dict[str, object]:
    try:
        with zipfile.ZipFile(path) as archive:
            members = frozenset(archive.namelist())
    except (OSError, zipfile.BadZipFile) as error:
        raise RuntimeError("candidate wheel cannot be read") from error
    missing = sorted(EXPECTED_MEMBERS - members)
    if missing:
        raise RuntimeError(f"candidate wheel omits M06-04 members: {', '.join(missing)}")
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
