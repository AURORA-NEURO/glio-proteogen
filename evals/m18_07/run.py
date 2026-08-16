"""Executable evaluator for M18-07 downstream typed export."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from tests.contract.test_m18_07_deep import _request

from glio_proteogen.contracts.m18_07 import (
    CompatibilityMode,
    ExportBiomarkerPanelDownstreamContractRequest,
    ExportStatus,
)
from glio_proteogen.kernel.models import ConsentState, SupportStatus
from glio_proteogen.modules.c18_spatial_proteomics_projection import (
    m18_07_downstream_typed_export as m1807,
)

ROOT: Final = Path(__file__).resolve().parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m18_07" / "scenarios.json"
MODULE_ID: Final = "GLIO-PROTEOGEN-M18-07"
DOSSIER_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
DOSSIER_SLICE: Final = "6420-6460"
EXPECTED_SCENARIOS: Final = 8
EXPECTED_ADVERSARIAL_CASES: Final = 8


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    dossier_sha256: str
    dossier_slice: str
    scenario_count: int
    adversarial_case_count: int
    adversarial_passed_count: int
    adversarial_coverage_percent: float
    target_percent: int
    checks: tuple[EvalCheck, ...]
    passed: bool


def _documented_request(text: str) -> ExportBiomarkerPanelDownstreamContractRequest:
    request = _request()
    field = request.fields[0].model_copy(update={"documentation": text})
    return request.model_copy(update={"fields": (field,)})


def _support_request(status: SupportStatus) -> ExportBiomarkerPanelDownstreamContractRequest:
    request = _request()
    return request.model_copy(
        update={"support_decision": request.support_decision.model_copy(update={"status": status})}
    )


def _consent_denied_request() -> ExportBiomarkerPanelDownstreamContractRequest:
    request = _request()
    references = request.context.references
    consent = references.consent.model_copy(update={"state": ConsentState.REVOKED})
    return request.model_copy(
        update={
            "context": request.context.model_copy(
                update={"references": references.model_copy(update={"consent": consent})}
            )
        }
    )


def _scenario(name: str) -> ExportBiomarkerPanelDownstreamContractRequest:  # noqa: PLR0911
    if name == "supported_export":
        return _request()
    if name == "prohibited_boundary":
        return _documented_request("KINOPHOS kinase-state output.")
    if name == "unsupported_material":
        return _documented_request("unsupported spatial field requires review")
    if name == "review_support":
        return _support_request(SupportStatus.LIMITED)
    if name == "review_compatibility":
        request = _request()
        config = request.configuration.model_copy(
            update={"compatibility": CompatibilityMode.REVIEW_REQUIRED}
        )
        return request.model_copy(update={"configuration": config})
    if name == "missing_consent":
        return _consent_denied_request()
    if name == "replay":
        return _request()
    if name == "strict_json_boundary":
        return _documented_request("all omics fusion and direct treatment recommendation")
    raise ValueError(f"unknown M18-07 evaluator scenario: {name}")  # noqa: TRY003


def evaluate() -> EvaluationReport:
    metadata = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    names = tuple(metadata["scenario_names"])
    engine = m1807.M1807Engine()
    checks = [
        EvalCheck(
            "corpus.scenario_count",
            len(names) == EXPECTED_SCENARIOS,
            f"observed={len(names)} expected={EXPECTED_SCENARIOS}",
        )
    ]
    results = {}
    denied = False
    for name in names:
        try:
            results[name] = engine.export(_scenario(name))
        except m1807.M1807AuthorizationError:
            denied = name == "missing_consent"
    checks.extend(
        (
            EvalCheck(
                "supported.signed_contract",
                results["supported_export"].status is ExportStatus.EXPORTED
                and results["supported_export"].contract is not None,
                "supported request emits a signed bounded contract",
            ),
            EvalCheck(
                "supported.uncertainty",
                all(
                    getattr(results["supported_export"].uncertainty, dimension).state.value
                    == "estimated"
                    for dimension in (
                        "measurement",
                        "sampling",
                        "parameter",
                        "model_form",
                        "identification",
                        "support",
                        "transport",
                    )
                ),
                "all seven uncertainty dimensions are explicit",
            ),
            EvalCheck(
                "unsupported.abstention",
                results["unsupported_material"].status is ExportStatus.ABSTAINED
                and results["unsupported_material"].contract is None,
                "unsupported material is withheld rather than negated",
            ),
            EvalCheck(
                "review.support",
                results["review_support"].status is ExportStatus.ABSTAINED
                and results["review_support"].human_review_required,
                "limited support requires review",
            ),
            EvalCheck(
                "boundary.prohibited",
                results["prohibited_boundary"].status is ExportStatus.ABSTAINED
                and bool(results["prohibited_boundary"].findings),
                "kinase and prohibited boundaries abstain",
            ),
        )
    )
    replay = results["replay"]
    replay_ok = engine.verify(replay).result_digest == replay.result_digest
    tampered = replay.model_copy(update={"result_digest": "sha256:" + "a" * 64})
    tamper_denied = False
    try:
        engine.verify(tampered)
    except m1807.M1807ReplayError:
        tamper_denied = True
    checks.extend(
        (
            EvalCheck("replay.deterministic", replay_ok, "replay reproduces the exact result"),
            EvalCheck("replay.tamper_denied", tamper_denied, "payload digest rejects tampering"),
        )
    )
    adversarial_passed = sum(
        int(
            results[name].status is ExportStatus.ABSTAINED
            and results[name].contract is None
            and bool(results[name].findings)
        )
        for name in (
            "prohibited_boundary",
            "unsupported_material",
            "review_support",
            "review_compatibility",
            "strict_json_boundary",
        )
    )
    adversarial_passed += int(denied) + int(tamper_denied) + int(replay_ok)
    checks.append(
        EvalCheck(
            "adversarial.coverage",
            adversarial_passed / EXPECTED_ADVERSARIAL_CASES * 100
            >= metadata["coverage_target_percent"],
            f"passed={adversarial_passed}/{EXPECTED_ADVERSARIAL_CASES}; boundaries exercised",
        )
    )
    return EvaluationReport(
        module_id=MODULE_ID,
        dossier_sha256=DOSSIER_SHA256,
        dossier_slice=DOSSIER_SLICE,
        scenario_count=len(names),
        adversarial_case_count=EXPECTED_ADVERSARIAL_CASES,
        adversarial_passed_count=adversarial_passed,
        adversarial_coverage_percent=adversarial_passed / EXPECTED_ADVERSARIAL_CASES * 100,
        target_percent=metadata["coverage_target_percent"],
        checks=tuple(checks),
        passed=all(check.passed for check in checks),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    rendered = json.dumps(asdict(evaluate()), indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if json.loads(rendered)["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
