"""Runtime and replay gates for M19-01."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m19_01 import (
    CompatibilityStatus,
    ResolverFindingCode,
    ResolverStatus,
)
from glio_proteogen.contracts.m19_01.canonical import canonical_request_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState, SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m19_01_upstream_contract_resolver as m1901,
)
from tests.contract.test_m19_01_deep import _candidate, _request

_CONTROL_COUNT = 7


def test_supported_candidate_is_validated_and_bound_to_proteotype() -> None:
    result = m1901.M1901Engine().resolve(_request())
    assert result.status is ResolverStatus.VALIDATED
    assert result.bundle is not None
    assert result.compatibility_report.selected_candidate_ids == ("candidate.proteome",)
    assert result.parent_target == "proteotype"
    assert result.emits_parent is False
    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert result.request_digest == canonical_request_digest(result.request)


def test_unknown_candidate_abstains_without_negative_inference() -> None:
    result = m1901.M1901Engine().resolve(
        _request((_candidate("candidate.unknown", compatibility=CompatibilityStatus.UNKNOWN),))
    )
    assert result.status is ResolverStatus.ABSTAINED
    assert result.bundle is None
    assert result.human_review_required is True
    assert result.compatibility_report.unresolved_candidate_ids == ("candidate.unknown",)
    assert result.findings[0].code is ResolverFindingCode.COMPATIBILITY_UNKNOWN


def test_mixed_selected_and_unresolved_inputs_fail_closed_to_review() -> None:
    result = m1901.M1901Engine().resolve(
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
        (
            "support_status",
            SupportStatus.REVIEW_REQUIRED,
            ResolverFindingCode.SUPPORT_NOT_AVAILABLE,
        ),
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
    result = m1901.M1901Engine().resolve(_request((candidate,)))
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
    with pytest.raises(m1901.M1901AuthorizationError, match="consent"):
        m1901.preflight_m1901_authorization(request)
    with pytest.raises(m1901.M1901AuthorizationError, match="consent"):
        m1901.M1901Engine().resolve(request)


def test_replay_accepts_exact_result_and_rejects_tampering() -> None:
    service = m1901.M1901Service()
    result = service.resolve(_request())
    assert service.replay(result) == result
    with pytest.raises(m1901.M1901ReplayError, match="identifier"):
        service.replay(result.model_copy(update={"result_id": "result.tampered"}))
    with pytest.raises(m1901.M1901ReplayError, match="payload"):
        service.replay(result.model_copy(update={"result_digest": "sha256:" + "0" * 64}))
    with pytest.raises(m1901.M1901ReplayError, match="request digest"):
        service.replay(result.model_copy(update={"request_digest": "sha256:" + "0" * 64}))


def test_strict_public_wrapper_matches_engine() -> None:
    assert (
        m1901.resolve_proteotype_upstream_contracts(_request()).result_digest
        == m1901.M1901Engine().resolve(_request()).result_digest
    )
    with pytest.raises((ValidationError, m1901.M1901AuthorizationError)):
        m1901.M1901Engine().validate_request({"request_id": "bad"})
    service = m1901.M1901Service()
    assert service.validate_request(_request()) == _request()


def test_plugin_descriptor_and_strict_json_boundary() -> None:
    plugin = m1901.M1901Plugin()
    descriptor = plugin.descriptor
    assert descriptor.module_id == "GLIO-PROTEOGEN-M19-01"
    assert descriptor.parent_target == "proteotype"
    assert descriptor.unsupported_to_negative is False
    request = _request()
    parsed = plugin.validate_json(canonical_json_bytes(request))
    result = plugin.run(parsed)
    assert plugin.replay(result) == result
    with pytest.raises(ValueError, match="valid JSON"):
        plugin.validate_json(b"not-json")
    with pytest.raises(ValueError, match="valid JSON"):
        plugin.validate_json(b'{"a":1,"a":2}')
    with pytest.raises(ValueError, match="size limit"):
        plugin.validate_json(b"{" + b" " * (4 * 1024 * 1024) + b"}")


def test_plugin_capability_rejects_forged_cross_instance_and_nested_mutation() -> None:
    request = _request()
    plugin = m1901.M1901Plugin()
    other = m1901.M1901Plugin()
    token = plugin.validate(request)

    assert plugin.run(token) == plugin.run(request)

    forged = m1901.ValidatedM1901Request(request=token.request, _seal=token._seal)
    with pytest.raises(m1901.M1901TokenError):
        plugin.run(forged)
    with pytest.raises(m1901.M1901TokenError):
        other.run(token)

    changed_candidate = token.request.candidates[0].model_copy(
        update={"compatibility_reason": "forged after validation"}
    )
    object.__setattr__(
        token.request,
        "candidates",
        (changed_candidate, *token.request.candidates[1:]),
    )
    with pytest.raises(m1901.M1901TokenError):
        plugin.run(token)
