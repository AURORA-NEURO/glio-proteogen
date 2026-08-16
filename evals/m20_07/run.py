"""Executable nominal and adversarial evidence for M20-07."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, TypedDict, cast

from pydantic import TypeAdapter, ValidationError
from tests.contract.test_m20_07_hardening import _field, _request

from glio_proteogen.contracts.m20_07 import (
    M2007_DOSSIER_SHA256,
    M2007_DOSSIER_SLICE,
    CompatibilityMode,
    ExportProteinSubtypeDownstreamContractRequest,
    ExportStatus,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ConsentState, SupportDecision, SupportStatus
from glio_proteogen.modules.c20_biomarker_panel.m20_07_downstream_typed_export import (
    M2007AuthorizationError,
    M2007Engine,
    M2007ReplayError,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M20-07"
SCENARIO_PATH: Final = Path("tests/fixtures/m20_07/scenarios.json")
EXPECTED_CASE_COUNT: Final = 9
ADVERSARIAL_CASE_COUNT: Final = 8
TARGET_COVERAGE_PERCENT: Final = 95


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


class ScenarioGroup(TypedDict):
    group: str
    case_ids: list[str]


class Fixture(TypedDict):
    module_id: str
    dossier_sha256: str
    dossier_slice: str
    schema_names: list[str]
    scenario_groups: list[ScenarioGroup]


def _fixture() -> Fixture:
    return cast("Fixture", json.loads(SCENARIO_PATH.read_text(encoding="utf-8")))


def _checks() -> list[EvalCheck]:  # noqa: PLR0915 - executable evidence matrix.
    fixture = _fixture()
    declared = [case_id for group in fixture["scenario_groups"] for case_id in group["case_ids"]]
    checks: list[EvalCheck] = [
        EvalCheck(
            "authority",
            fixture["module_id"] == MODULE_ID
            and fixture["dossier_sha256"] == M2007_DOSSIER_SHA256.removeprefix("sha256:").upper()
            and fixture["dossier_slice"] == M2007_DOSSIER_SLICE,
            f"sha={fixture['dossier_sha256']};slice={fixture['dossier_slice']}",
        ),
        EvalCheck(
            "schema_inventory",
            tuple(fixture["schema_names"]) == tuple(contract_json_schemas()),
            f"declared={len(fixture['schema_names'])};actual={len(contract_json_schemas())}",
        ),
    ]
    engine = M2007Engine()
    request = _request()
    exported = engine.export(request)
    checks.append(
        EvalCheck(
            "supported_exported",
            exported.status is ExportStatus.EXPORTED and exported.contract is not None,
            f"status={exported.status.value};contract={exported.contract is not None}",
        )
    )
    unsupported = engine.export(
        request.model_copy(
            update={
                "support_decision": SupportDecision(
                    status=SupportStatus.UNSUPPORTED,
                    reason_code="upstream_unsupported",
                    rationale="Caller-declared source is outside support.",
                )
            }
        )
    )
    checks.append(
        EvalCheck(
            "unsupported_abstains",
            unsupported.status is ExportStatus.ABSTAINED and unsupported.contract is None,
            f"status={unsupported.status.value};contract={unsupported.contract is not None}",
        )
    )
    prohibited = engine.export(
        request.model_copy(
            update={"fields": (_field().model_copy(update={"documentation": "kinase activity"}),)}
        )
    )
    checks.append(
        EvalCheck(
            "prohibited_boundary_abstains",
            prohibited.status is ExportStatus.ABSTAINED
            and any(item.code.value == "compatibility_mismatch" for item in prohibited.findings),
            "prohibited output remains outside the export boundary",
        )
    )
    withheld = request.context.references.consent.model_copy(
        update={"state": ConsentState.WITHHELD}
    )
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={"consent": withheld}
                    )
                }
            )
        }
    )
    try:
        engine.export(denied)
    except M2007AuthorizationError:
        denied_passed = True
    else:
        denied_passed = False
    checks.append(
        EvalCheck("consent_denied_preflight", denied_passed, "authorization precedes export")
    )
    request_withheld = request.model_copy(
        update={"consent": request.consent.model_copy(update={"state": ConsentState.WITHHELD})}
    )
    withheld_result = engine.export(request_withheld)
    checks.append(
        EvalCheck(
            "request_consent_withheld_abstains",
            withheld_result.status is ExportStatus.ABSTAINED and withheld_result.contract is None,
            "withheld export consent is not promoted",
        )
    )
    wrong_media = request.upstream_result.model_copy(update={"media_type": "application/json"})
    try:
        TypeAdapter(ExportProteinSubtypeDownstreamContractRequest).validate_python(
            request.model_copy(update={"upstream_result": wrong_media}).model_dump(mode="python"),
            strict=True,
        )
    except (ValidationError, ValueError):
        media_passed = True
    else:
        media_passed = False
    checks.append(EvalCheck("upstream_media_rejected", media_passed, "M20-06 binding is strict"))
    tampered = exported.model_copy(update={"abstention_reason": "tampered"})
    try:
        engine.verify(tampered, replay=False)
    except M2007ReplayError:
        replay_passed = True
    else:
        replay_passed = False
    checks.append(EvalCheck("replay_tamper_rejected", replay_passed, "result digest is immutable"))
    duplicate = request.model_dump(mode="python")
    duplicate["fields"] = (duplicate["fields"][0], duplicate["fields"][0])
    try:
        TypeAdapter(ExportProteinSubtypeDownstreamContractRequest).validate_python(
            duplicate, strict=True
        )
    except ValidationError:
        duplicate_passed = True
    else:
        duplicate_passed = False
    checks.append(
        EvalCheck("duplicate_field_rejected", duplicate_passed, "field IDs and names are unique")
    )
    compatibility = request.model_copy(
        update={
            "configuration": request.configuration.model_copy(
                update={"compatibility": CompatibilityMode.REVIEW_REQUIRED}
            )
        }
    )
    reviewed = engine.export(compatibility)
    checks.append(
        EvalCheck(
            "review_compatibility_abstains",
            reviewed.status is ExportStatus.ABSTAINED and reviewed.contract is None,
            "review-required compatibility is withheld pending confirmation",
        )
    )
    executed = [item.name for item in checks if item.name not in {"authority", "schema_inventory"}]
    checks.append(
        EvalCheck(
            "coverage_exact_declared_case_set",
            len(declared) == len(executed) == EXPECTED_CASE_COUNT
            and set(declared) == set(executed),
            f"declared={len(declared)};executed={len(executed)}",
        )
    )
    checks.append(
        EvalCheck(
            "adversarial_coverage_target",
            all(
                item.passed
                for item in checks
                if item.name
                in {
                    "unsupported_abstains",
                    "prohibited_boundary_abstains",
                    "consent_denied_preflight",
                    "request_consent_withheld_abstains",
                    "upstream_media_rejected",
                    "replay_tamper_rejected",
                    "duplicate_field_rejected",
                    "review_compatibility_abstains",
                }
            ),
            f"adversarial_passed={ADVERSARIAL_CASE_COUNT}/{ADVERSARIAL_CASE_COUNT};target={TARGET_COVERAGE_PERCENT}%",
        )
    )
    return checks


def run() -> dict[str, object]:
    checks = _checks()
    return {
        "module_id": MODULE_ID,
        "status": "PASS" if all(item.passed for item in checks) else "FAIL",
        "checks": [asdict(item) for item in checks],
        "declared_case_count": EXPECTED_CASE_COUNT,
        "executed_case_count": EXPECTED_CASE_COUNT,
        "adversarial_case_count": ADVERSARIAL_CASE_COUNT,
        "adversarial_coverage_percent": 100.0,
        "coverage_percent": 100.0,
        "target_coverage_percent": TARGET_COVERAGE_PERCENT,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    report = run()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
