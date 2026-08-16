"""Executable M07-06 evaluator for safety, replay, and claim ceilings."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from glio_proteogen.contracts.m07_06 import (
    CopyNumberDosageUncertaintyDecompositionResult,
    DecomposeCopyNumberDosageUncertaintyRequest,
    UncertaintyDecompositionStatus,
    canonical_request_digest,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c07_copy_number_dosage.m07_06_uncertainty_decomposition import (
    M0706AuthorizationError,
    M0706ReplayVerificationError,
    M0706Service,
)

_ROOT = Path(__file__).parents[2]
_SCENARIO = _ROOT / "tests" / "fixtures" / "m07_06" / "scenarios.json"
_REQUEST = TypeAdapter(DecomposeCopyNumberDosageUncertaintyRequest)


def load_request() -> DecomposeCopyNumberDosageUncertaintyRequest:
    """Load the frozen fixture through the strict JSON contract parser."""

    document = json.loads(_SCENARIO.read_text(encoding="utf-8"))
    return _REQUEST.validate_json(json.dumps(document["request"]), strict=True)


def run_evaluation() -> dict[str, Any]:
    """Run deterministic positive, negative, and replay scenarios."""

    service = M0706Service()
    request = load_request()
    first = service.execute(request)
    second = service.execute(request)
    cases: list[dict[str, Any]] = []
    cases.append(
        {
            "id": "safe-abstention-with-explicit-seven-dimension-uncertainty",
            "passed": first.status is UncertaintyDecompositionStatus.ABSTAINED
            and first.decomposition is None
            and first.human_review_required
            and first.support_decision.status.value == "review_required",
        }
    )
    cases.append(
        {
            "id": "deterministic-request-replay",
            "passed": first.model_dump(mode="json") == second.model_dump(mode="json")
            and first.request_digest == canonical_request_digest(request),
        }
    )
    cases.append(
        {
            "id": "tamper-rejected-by-result-replay",
            "passed": _tamper_rejected(service, first),
        }
    )
    cases.append(
        {
            "id": "withheld-consent-rejected-before-engine",
            "passed": _consent_rejected(service, request),
        }
    )
    cases.append(
        {
            "id": "ownership-claim-ceiling",
            "passed": first.emits_parent is False
            and first.parent_target == "proteotype"
            and {limitation.code for limitation in first.limitations}
            == {
                "uncertainty_decomposition_only",
                "no_kinase_or_treatment_output",
                "provisional_abi_pending_owner_confirmation",
            },
        }
    )
    return {
        "module_id": "GLIO-PROTEOGEN-M07-06",
        "contract_version": "0.1.0-provisional",
        "scenario_count": len(cases),
        "passed": all(case["passed"] for case in cases),
        "cases": cases,
        "status": first.status.value,
        "result_digest": first.result_digest,
    }


def _tamper_rejected(
    service: M0706Service,
    result: CopyNumberDosageUncertaintyDecompositionResult,
) -> bool:
    tampered = result.model_copy(update={"abstention_reason": "tampered"})
    try:
        service.verify(tampered)
    except M0706ReplayVerificationError:
        return True
    return False


def _consent_rejected(
    service: M0706Service,
    request: DecomposeCopyNumberDosageUncertaintyRequest,
) -> bool:
    refs = request.context.references
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": refs.model_copy(
                        update={
                            "consent": refs.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    try:
        service.execute(denied)
    except M0706AuthorizationError:
        return True
    return False


def main() -> None:
    sys.stdout.write(json.dumps(run_evaluation(), sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
