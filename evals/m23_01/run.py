"""Deterministic M23-01 evaluator over a frozen curation matrix."""

# ruff: noqa: C901, FBT003, PLR0911, T201

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

if __package__ in (None, ""):  # pragma: no cover - direct script invocation.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.contract.test_m23_01_deep import _request

from glio_proteogen.contracts.m23_01 import (
    M2301_DOSSIER_SHA256,
    M2301_DOSSIER_SLICE,
    AdjudicationStatus,
    CurateVariantPeptideReferenceTruthRequest,
    ReferenceKind,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c21_reference_material.m23_01_reference_truth_benchmark_curator import (
    M2301AuthorizationError,
    M2301Plugin,
    M2301Service,
    ReferenceTruthSubmission,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M23-01"
SCENARIO_PATH: Final = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "m23_01" / "scenarios.json"
)
EXPECTED_CASE_IDS: Final = (
    "pass_locked",
    "pending_adjudication_abstention",
    "rejected_included_abstention",
    "missing_challenge_set_abstention",
    "authorization_gate",
    "source_binding_boundary",
    "replay_tamper_determinism",
    "plugin_parse_once",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _fixture_digest() -> str:
    return "sha256:" + hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()


def _run_case(case_id: str) -> EvalCheck:
    request = _request()
    service = M2301Service()
    if case_id == "pass_locked":
        result = service.execute(request)
        return EvalCheck(
            case_id, result.status.value == "curated" and result.package is not None, "curated"
        )
    if case_id == "pending_adjudication_abstention":
        pending = request.adjudications[0].model_copy(update={"status": AdjudicationStatus.PENDING})
        result = service.execute(
            request.model_copy(update={"adjudications": (pending, *request.adjudications[1:])})
        )
        return EvalCheck(
            case_id,
            result.package is None
            and result.support_decision.status is SupportStatus.REVIEW_REQUIRED,
            "abstained",
        )
    if case_id == "rejected_included_abstention":
        rejected = request.adjudications[0].model_copy(
            update={
                "status": AdjudicationStatus.REJECTED,
                "disagreement_statement": "Reviewers disagree.",
            }
        )
        result = service.execute(
            request.model_copy(update={"adjudications": (rejected, *request.adjudications[1:])})
        )
        return EvalCheck(
            case_id, result.package is None and result.status.value == "abstained", "abstained"
        )
    if case_id == "missing_challenge_set_abstention":
        references = (
            request.references[0],
            request.references[1].model_copy(
                update={"kind": ReferenceKind.CALIBRATOR, "challenge_set": False}
            ),
        )
        result = service.execute(request.model_copy(update={"references": references}))
        return EvalCheck(
            case_id,
            result.package is None and result.status.value == "abstained",
            "challenge set withheld",
        )
    if case_id == "authorization_gate":
        denied_context = request.context.model_copy(
            update={
                "references": request.context.references.model_copy(
                    update={
                        "consent": request.context.references.consent.model_copy(
                            update={"state": "withheld"}
                        )
                    }
                )
            }
        )
        try:
            service.execute(request.model_copy(update={"context": denied_context}))
        except M2301AuthorizationError:
            return EvalCheck(case_id, True, "denied controls rejected")
        return EvalCheck(case_id, False, "authorization unexpectedly passed")
    if case_id == "source_binding_boundary":
        source = request.source_artifacts[0].model_copy(update={"digest": "sha256:" + "f" * 64})
        try:
            CurateVariantPeptideReferenceTruthRequest.model_validate(
                request.model_copy(
                    update={"source_artifacts": (source, *request.source_artifacts[1:])}
                ).model_dump(mode="python")
            )
        except ValidationError:
            return EvalCheck(case_id, True, "source substitution rejected")
        return EvalCheck(case_id, False, "source substitution accepted")
    if case_id == "replay_tamper_determinism":
        first = service.execute(request)
        second = service.execute(request)
        tampered = first.model_copy(update={"result_id": "tampered-result"})
        try:
            service.verify_replay(tampered)
        except ValueError:
            return EvalCheck(case_id, first == second, first.result_digest)
        return EvalCheck(case_id, False, "tamper unexpectedly replayed")
    if case_id == "plugin_parse_once":
        plugin = M2301Plugin(service)
        token = plugin.validate(ReferenceTruthSubmission(request.model_dump_json().encode()))
        result = plugin.run(token)
        return EvalCheck(
            case_id, result.result_id.startswith("curation.m2301."), "plugin token accepted"
        )
    return EvalCheck(case_id, False, "unknown scenario")


def run_evaluation() -> dict[str, object]:
    scenarios = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in scenarios["cases"])
    checks = tuple(_run_case(case_id) for case_id in case_ids)
    return {
        "module_id": MODULE_ID,
        "dossier_sha256": M2301_DOSSIER_SHA256,
        "dossier_slice": M2301_DOSSIER_SLICE,
        "fixture": str(SCENARIO_PATH),
        "fixture_digest": _fixture_digest(),
        "case_ids": list(case_ids),
        "declared_cases": len(EXPECTED_CASE_IDS),
        "executed_cases": len(checks),
        "passed_cases": sum(check.passed for check in checks),
        "total_cases": len(checks),
        "checks": [
            {"name": check.name, "passed": check.passed, "detail": check.detail} for check in checks
        ],
        "passed": case_ids == EXPECTED_CASE_IDS and all(check.passed for check in checks),
    }


if __name__ == "__main__":
    print(json.dumps(run_evaluation(), sort_keys=True))
