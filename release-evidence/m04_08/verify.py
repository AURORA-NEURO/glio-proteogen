"""Verify M04-08 synthetic-only evaluator evidence and dependency safety."""

# This directory is a committed evidence namespace, not an importable package.
# ruff: noqa: INP001

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from glio_proteogen.contracts.m04_08 import v1 as contract_v1

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(__file__).resolve().parent
MODULE_ID = "GLIO-PROTEOGEN-M04-08"
SYNTHETIC_CASE = "scenario.synthetic_m0401_m0407_chain"


def _load(name: str) -> dict[str, Any]:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _dependency_guard() -> bool:
    """Prove an absent M04-07 binding cannot be treated as executable input."""

    binding = contract_v1._M0407_BINDING
    if binding is None:
        return False
    contract_v1._M0407_BINDING = None
    try:
        contract_v1._m0407_binding()
    except contract_v1.M0408DependencyUnavailableError:
        return True
    finally:
        contract_v1._M0407_BINDING = binding
    return False


def verify() -> dict[str, bool]:
    """Return and enforce the M04-08 evidence invariants."""

    evaluation = _load("evaluation.json")
    fixture = json.loads(
        (ROOT / "tests" / "fixtures" / "m04_08" / "scenarios.json").read_text(encoding="utf-8")
    )
    checks = evaluation.get("checks", [])
    names = {item.get("name") for item in checks}
    synthetic_check = next((item for item in checks if item.get("name") == SYNTHETIC_CASE), None)
    dependency = fixture.get("dependency", {})
    result = {
        "module": evaluation.get("module_id") == MODULE_ID,
        "evaluation": evaluation.get("passed") is True
        and all(item.get("passed") is True for item in checks),
        "synthetic_only": evaluation.get("genuine_e2e_executed") is False
        and evaluation.get("synthetic_chain_executed") is True
        and synthetic_check is not None
        and synthetic_check.get("passed") is True
        and "scenario.genuine_m0401_m0407_chain" not in names,
        "fixture_ceiling": dependency.get("module_id") == "GLIO-PROTEOGEN-M04-07"
        and dependency.get("state") == "public_abi_not_frozen"
        and dependency.get("genuine_e2e_allowed") is False
        and dependency.get("synthetic_chain_allowed") is True,
        "dependency_fail_closed": _dependency_guard(),
    }
    if not all(result.values()):
        raise SystemExit(1)
    return result


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))  # noqa: T201
