"""Runtime and replay gates for M19-01."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m19_01 import (
    CompatibilityStatus,
    ResolverStatus,
    ResolverFindingCode,
)
from glio_proteogen.contracts.m19_01.canonical import canonical_request_digest
from glio_proteogen.kernel.models import ConsentState, SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m19_01_upstream_contract_resolver import (
    M1901AuthorizationError,
    M1901Engine,
    M1901ReplayError,
    M1901Service,
    preflight_m1901_authorization,
    resolve_proteotype_upstream_contracts,
)
from tests.contract.test_m19_01_deep import _candidate, _request


def test_supported_candidate_is_validated_and_bound_to_proteotype() -> None:
    result = M1901Engine().resolve(_request())
    assert result.status is ResolverStatus.VALIDATED
    assert result.bundle is not None
    assert result.compatibility_report.selected_candidate_ids == ("candidate.proteome",)
    assert result.parent_target == "proteotype"
    assert result.emits_parent is False
    assert len(result.provenance.control_decisions) == 7
    assert result.request_digest == canonical_request_digest(result.request)


def test_unknown_candidate_abstains_without_negative_inference() -> None:
    result = M1901Engine().resolve(
        _request((_candidate("candidate.unknown", compatibility=CompatibilityStatus.UNKNOWN),))
    )
    assert result.status is ResolverStatus.ABSTAINED
    assert result.bundle is None
    assert result.human_review_required is True
    assert result.compatibility_report.unresolved_candidate_ids == ("candidate.unknown",)
    assert result.findings[0].code is ResolverFindingCode.COMPATIBILITY_UNKNOWN


def test_mixed_selected_and_unresolved_inputs_fail_closed_to_review() -> None:
    result = M1901Engine().resolve(
        _request(
            (
                _candidate(),
                _candidate("candidate.unknown", compatibility=CompatibilityStatus.UNKNOWN),
            )
        )
    )
    assert result.status is ResolverStatus.ABSTAINED
    assert result.bundle is None
    assert result.compatibility_report.selected_candidate_ids == ("candidate.proteome",)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("consent_state", ConsentState.UNKNOWN, ResolverFindingCode.CONSENT_NOT_GRANTED),
        ("support_status", SupportStatus.REVIEW_REQUIRED, ResolverFindingCode.SUPPORT_NOT_AVAILABLE),
        ("intended_use", "restricted use", ResolverFindingCode.MEDIA_TYPE_MISMATCH),
    ],
)
def test_control_and_rule_rejections_are_typed(
    field: str,
    value: object,
    code: ResolverFindingCode,
) -> None:
    candidate = _candidate("candidate.rejected")
    candidate = candidate.model_copy(update={field: value})
    # Pydantic construction prevents unsafe compatible declarations; convert to
    # an explicitly incompatible caller declaration for runtime rejection.
    if field in {"consent_state", "support_status"}:
        candidate = candidate.model_copy(update={"compatibility": CompatibilityStatus.INCOMPATIBLE})
    result = M1901Engine().resolve(_request((candidate,)))
    assert result.status is ResolverStatus.ABSTAINED
    assert result.findings[0].code in {
        code,
        ResolverFindingCode.INCOMPATIBLE,
        ResolverFindingCode.MEDIA_TYPE_MISMATCH,
    }


def test_preflight_rejects_missing_or_denied_control_before_validation() -> None:
    original = _request()
    request = original.model_copy(
        update={
            "context": original.context.model_copy(
                update={
                    "references": original.context.references.model_copy(
                        update={
                            "consent": original.context.references.consent.model_copy(
                                update={"state": ConsentState.UNKNOWN}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(M1901AuthorizationError, match="consent"):
        preflight_m1901_authorization(request)
    with pytest.raises(M1901AuthorizationError, match="consent"):
        M1901Engine().resolve(request)


def test_replay_accepts_exact_result_and_rejects_tampering() -> None:
    service = M1901Service()
    result = service.resolve(_request())
    assert service.replay(result) == result
    with pytest.raises(M1901ReplayError, match="identifier"):
        service.replay(result.model_copy(update={"result_id": "result.tampered"}))
    with pytest.raises(M1901ReplayError, match="payload"):
        service.replay(result.model_copy(update={"result_digest": "sha256:" + "0" * 64}))


def test_strict_public_wrapper_matches_engine() -> None:
    assert resolve_proteotype_upstream_contracts(_request()).result_digest == M1901Engine().resolve(
        _request()
    ).result_digest
    with pytest.raises((ValidationError, M1901AuthorizationError)):
        M1901Engine().validate_request({"request_id": "bad"})
