"""Locked ABI-independent inventory checks for the M04-08 scaffold."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

from glio_proteogen.contracts.m04_08 import (
    M0408_MODULE_ID,
    M0408DependencyUnavailableError,
    ProteoformReleaseArtifact,
    ProteoformReleaseArtifactRole,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import ArtifactReference
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging import (
    build_proteoform_release,
    build_proteoform_release_manifest,
    verify_proteoform_release,
)

SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m04_08" / "scenarios.json"
)
_EXPECTED_CASE_IDS: Final = frozenset(
    {
        "schema_inventory",
        "canonical_digest_helpers",
        "fixed_archive_paths",
        "bounded_archive_shape",
        "external_signature_boundary",
        "reproduction_evidence_inventory",
        "authority_ceiling",
        "parent_context_only",
        "m0407_artifact_binding_fails_closed",
        "runtime_build_fails_closed",
        "runtime_manifest_fails_closed",
        "runtime_verify_fails_closed",
    }
)
_SCHEMA_COUNT: Final = 9


def _digest(label: str) -> str:
    return sha256_digest({"m0408_scaffold": label})


def _m0407_dependency_is_sealed() -> bool:
    reference = ArtifactReference(
        artifact_id=f"unbound.{_digest('m0407').removeprefix('sha256:')}",
        version="1.0.0",
        digest=_digest("m0407-bytes"),
        media_type="application/octet-stream",
    )
    try:
        ProteoformReleaseArtifact(
            path="stages/m04-07-upstream-result.json",
            role=ProteoformReleaseArtifactRole.M04_07_UPSTREAM_RESULT,
            reference=reference,
            declared_size=1,
        )
    except M0408DependencyUnavailableError:
        return True
    return False


def _runtime_dependency_is_sealed() -> tuple[bool, bool, bool]:
    checks: list[bool] = []
    operations = (
        lambda: build_proteoform_release(object(), {}, {}),
        lambda: build_proteoform_release_manifest(object(), {}, {}),
        lambda: verify_proteoform_release(object(), b""),
    )
    for operation in operations:
        try:
            operation()
        except M0408DependencyUnavailableError:
            checks.append(True)
        else:
            checks.append(False)
    return checks[0], checks[1], checks[2]


def evaluate() -> dict[str, object]:
    inventory = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    declared = tuple(item["case_id"] for item in inventory["cases"])
    declared_set = set(declared)
    schemas = contract_json_schemas()
    runtime_checks = _runtime_dependency_is_sealed()
    checks = (
        {"name": "inventory.module", "passed": inventory["module_id"] == M0408_MODULE_ID},
        {"name": "inventory.phase", "passed": inventory["phase"] == "abi_independent_scaffold"},
        {"name": "inventory.case_ids", "passed": declared_set == _EXPECTED_CASE_IDS},
        {"name": "schemas.count", "passed": len(schemas) == _SCHEMA_COUNT},
        {
            "name": "schemas.identities",
            "passed": all(
                isinstance((schema_id := schema.get("$id")), str)
                and schema_id.startswith(
                    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-08:1.0.0:"
                )
                for schema in schemas.values()
            ),
        },
        {"name": "dependency.artifact", "passed": _m0407_dependency_is_sealed()},
        {"name": "dependency.build", "passed": runtime_checks[0]},
        {"name": "dependency.manifest", "passed": runtime_checks[1]},
        {"name": "dependency.verify", "passed": runtime_checks[2]},
        {
            "name": "dependency.e2e_disabled",
            "passed": inventory["dependency"]["genuine_e2e_allowed"] is False,
        },
    )
    passed = all(item["passed"] is True for item in checks)
    return {
        "module_id": M0408_MODULE_ID,
        "phase": "abi_independent_scaffold",
        "passed": passed,
        "declared_case_count": len(declared),
        "executed_scaffold_check_count": len(checks),
        "genuine_e2e_executed": False,
        "missing_case_ids": sorted(_EXPECTED_CASE_IDS - declared_set),
        "extra_case_ids": sorted(declared_set - _EXPECTED_CASE_IDS),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = evaluate()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0 if report["passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
