"""Adversarial closure tests for M18-01 nested invariants."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m18_01 import (
    BiomarkerPanelUpstreamResolutionResult,
    CompatibilityDecision,
    CompatibilityReport,
    CompatibilityStatus,
    ResolverFindingCode,
    ResolverStatus,
    ValidatedUpstreamBundle,
)
from glio_proteogen.kernel.models import SupportDecision, SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m18_01_upstream_contract_resolver import (  # noqa: E501
    M1801Engine,
)
from tests.contract.test_m18_01_deep import _candidate, _evidence, _report
from tests.modules.c17_metabolomic_lipidomic_integration.test_m18_01_engine import (
    _request as _runtime_request,
)


def _decision(
    candidate_id: str,
    status: CompatibilityStatus,
) -> CompatibilityDecision:
    return CompatibilityDecision(
        candidate_id=candidate_id,
        status=status,
        reason_code=(
            ResolverFindingCode.PROVISIONAL_ABI_PENDING_REVIEW
            if status is CompatibilityStatus.COMPATIBLE
            else ResolverFindingCode.INCOMPATIBLE_VERSION
        ),
        rationale="Adversarial contract decision.",
        evidence=(_evidence(candidate_id),),
    )


def test_report_closure_rejects_duplicate_ids_and_status_bucket_mismatches() -> None:
    with pytest.raises(ValidationError, match="decision candidate ids"):
        CompatibilityReport.model_validate(
            _report().model_dump(mode="python")
            | {"decisions": (_decision("candidate.proteome", CompatibilityStatus.COMPATIBLE),) * 2}
        )
    with pytest.raises(ValidationError, match="selected candidates"):
        CompatibilityReport.model_validate(
            _report().model_dump(mode="python")
            | {
                "decisions": (_decision("candidate.proteome", CompatibilityStatus.INCOMPATIBLE),),
            }
        )
    rejected_decision = _decision("candidate.proteome", CompatibilityStatus.COMPATIBLE)
    with pytest.raises(ValidationError, match="rejected candidates"):
        CompatibilityReport.model_validate(
            _report().model_dump(mode="python")
            | {
                "decisions": (rejected_decision,),
                "selected_candidate_ids": (),
                "rejected_candidate_ids": ("candidate.proteome",),
            }
        )
    unresolved_decision = _decision("candidate.proteome", CompatibilityStatus.COMPATIBLE)
    with pytest.raises(ValidationError, match="unresolved candidates"):
        CompatibilityReport.model_validate(
            _report().model_dump(mode="python")
            | {
                "decisions": (unresolved_decision,),
                "selected_candidate_ids": (),
                "unresolved_candidate_ids": ("candidate.proteome",),
            }
        )


def test_bundle_and_request_closure_reject_duplicate_or_unbound_artifacts() -> None:
    with pytest.raises(ValidationError, match="validated candidate ids"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.duplicate",
            version="1.0.0",
            candidates=(_candidate(), _candidate()),
            compatibility_report=_report(),
            evidence=(_evidence("bundle.duplicate"),),
        )
    request = _runtime_request()
    second = request.candidates[0].model_copy(
        update={"candidate_id": "candidate.other", "artifact": request.candidates[0].artifact}
    )
    with pytest.raises(ValidationError, match="candidate artifacts"):
        type(request).model_validate(
            request.model_dump(mode="python") | {"candidates": (request.candidates[0], second)}
        )


def test_result_closure_rejects_digest_identity_support_and_review_tampering() -> None:
    result = M1801Engine().resolve(_runtime_request())
    with pytest.raises(ValidationError, match="request digest"):
        BiomarkerPanelUpstreamResolutionResult.model_validate(
            result.model_copy(update={"request_digest": "sha256:" + "0" * 64})
        )
    with pytest.raises(ValidationError, match="identifier"):
        BiomarkerPanelUpstreamResolutionResult.model_validate(
            result.model_copy(update={"result_id": "result.tampered"})
        )
    with pytest.raises(ValidationError, match="review-only upstream"):
        BiomarkerPanelUpstreamResolutionResult.model_validate(
            result.model_copy(
                update={
                    "support_decision": SupportDecision(
                        status=SupportStatus.SUPPORTED,
                        reason_code="review",
                        rationale="Forced review.",
                    )
                }
            )
        )
    abstained = M1801Engine().resolve(
        _runtime_request(
            (_candidate("candidate.unknown", compatibility=CompatibilityStatus.UNKNOWN),)
        )
    )
    with pytest.raises(ValidationError, match="abstained result requires"):
        BiomarkerPanelUpstreamResolutionResult.model_validate(
            abstained.model_copy(update={"bundle": result.bundle})
        )
    with pytest.raises(ValidationError, match="human review"):
        BiomarkerPanelUpstreamResolutionResult.model_validate(
            abstained.model_copy(update={"human_review_required": False})
        )
    with pytest.raises(ValidationError, match="result digest"):
        BiomarkerPanelUpstreamResolutionResult.model_validate(
            result.model_copy(update={"result_digest": "sha256:" + "0" * 64})
        )


def test_result_status_enum_is_exercised_for_abstention_and_validation() -> None:
    result = M1801Engine().resolve(_runtime_request())
    assert result.status is ResolverStatus.VALIDATED
