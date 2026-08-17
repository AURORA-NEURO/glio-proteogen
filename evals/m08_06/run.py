"""Executable M08-06 evaluator for uncertainty, safety, and replay claims."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m08_06 import (
    DecomposeTranscriptProteinUncertaintyRequest,
    TranscriptProteinUncertaintyDecompositionResult,
    UncertaintyDecompositionStatus,
    canonical_request_digest,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_06_uncertainty_decomposition import (  # noqa: E501
    M0806AuthorizationError,
    M0806ReplayVerificationError,
    M0806Service,
)

_ROOT = Path(__file__).parents[2]
_SCENARIO = _ROOT / "tests" / "fixtures" / "m08_06" / "scenarios.json"
_REQUEST = TypeAdapter(DecomposeTranscriptProteinUncertaintyRequest)


def load_request() -> DecomposeTranscriptProteinUncertaintyRequest:
    """Load a frozen fixture through the strict JSON contract parser."""

    document = json.loads(_SCENARIO.read_text(encoding="utf-8"))
    return _REQUEST.validate_json(json.dumps(document["request"]), strict=True)


def run_evaluation() -> dict[str, Any]:
    """Run safe-abstention, determinism, tamper, and authorization scenarios."""

    service = M0806Service()
    request = load_request()
    first = service.execute(request)
    second = service.execute(request)
    cases: list[dict[str, Any]] = [
        {
            "id": "safe-abstention-with-explicit-seven-dimension-uncertainty",
            "passed": (
                first.status is UncertaintyDecompositionStatus.ABSTAINED
                and first.decomposition is None
                and first.human_review_required
                and first.sensitivity_envelope.status.value == "abstained"
                and first.uncertainty.transport.state.value == "not_estimable"
            ),
        },
        {
            "id": "deterministic-request-replay",
            "passed": (
                first.model_dump(mode="json") == second.model_dump(mode="json")
                and first.request_digest == canonical_request_digest(request)
            ),
        },
        {"id": "tamper-rejected-by-result-replay", "passed": _tamper_rejected(service, first)},
        {
            "id": "withheld-consent-rejected-before-engine",
            "passed": _consent_rejected(service, request),
        },
        {
            "id": "ownership-claim-ceiling",
            "passed": (
                first.emits_parent is False
                and first.parent_target == "protein_subtype"
                and {limitation.code for limitation in first.limitations}
                == {
                    "uncertainty_decomposition_only",
                    "no_kinase_or_treatment_output",
                    "provisional_abi_pending_owner_confirmation",
                }
            ),
        },
    ]
    return {
        "module_id": "GLIO-PROTEOGEN-M08-06",
        "contract_version": "0.1.0-provisional",
        "authority_sha256": "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181",
        "dossier_lines": "2776-2819",
        "scenario_count": len(cases),
        "passed": all(case["passed"] for case in cases),
        "cases": cases,
        "status": first.status.value,
        "result_digest": first.result_digest,
    }


def _tamper_rejected(
    service: M0806Service,
    result: TranscriptProteinUncertaintyDecompositionResult,
) -> bool:
    tampered = result.model_copy(update={"abstention_reason": "tampered"})
    try:
        service.verify(tampered)
    except M0806ReplayVerificationError:
        return True
    return False


def _consent_rejected(
    service: M0806Service,
    request: DecomposeTranscriptProteinUncertaintyRequest,
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
    except M0806AuthorizationError:
        return True
    return False


def main() -> None:
    sys.stdout.write(json.dumps(run_evaluation(), sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
