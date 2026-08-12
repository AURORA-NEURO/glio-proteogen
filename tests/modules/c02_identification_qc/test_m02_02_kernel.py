"""Focused qualification for the pure M02-02 binding-audit kernel."""

from __future__ import annotations

import hashlib

import pytest

from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage import (
    AuditDisposition,
    BindingAuditResult,
    BindingState,
    EntityKind,
    FindingCode,
    ResolvedComponentBinding,
    SupportState,
    audit_resolved_bindings,
)

_DISTINCT_BINDING_COUNT = 2
_OTHER_SCOPE = "scope.synthetic.other"


def _digest(label: str) -> str:
    return f"sha256:{hashlib.sha256(label.encode()).hexdigest()}"


def _binding(label: str, **changes: object) -> ResolvedComponentBinding:
    values: dict[str, object] = {
        "binding_digest": _digest(f"binding.{label}"),
        "entity_kind": EntityKind.RUN,
        "state": BindingState.BOUND,
        "entity_component_id": _digest(f"component.{label}"),
        "upstream_subject_component_ids": (_digest(f"patient.{label}"),),
        "observed_subject_component_ids": (_digest(f"patient.{label}"),),
        "token_scope_id": "scope.synthetic.project",
        "scoped_token_digest": _digest(f"token.{label}"),
        "content_digest": _digest(f"content.{label}"),
    }
    values.update(changes)
    return ResolvedComponentBinding(**values)  # type: ignore[arg-type]


def _codes(result: BindingAuditResult) -> tuple[FindingCode, ...]:
    return tuple(item.code for item in result.findings)


def test_canonical_bound_bindings_are_order_independent() -> None:
    bindings = (_binding("a"), _binding("b"))

    result = audit_resolved_bindings(bindings)
    replay = audit_resolved_bindings(tuple(reversed(bindings)))

    assert result == replay
    assert result.disposition is AuditDisposition.CONFORMANT
    assert result.support is SupportState.SUPPORTED
    assert not result.findings


def test_subject_swap_and_cross_patient_link_are_both_preserved() -> None:
    binding = _binding(
        "swap",
        observed_subject_component_ids=(_digest("patient.other"),),
    )

    result = audit_resolved_bindings((binding,))

    assert result.disposition is AuditDisposition.QUARANTINED
    assert set(_codes(result)) == {
        FindingCode.SWAP,
        FindingCode.CROSS_PATIENT_LINK,
    }


def test_token_collision_is_scoped_and_requires_distinct_components() -> None:
    token = _digest("token.shared")
    same_scope = (
        _binding("a", scoped_token_digest=token),
        _binding("b", scoped_token_digest=token),
    )
    different_scope = (
        same_scope[0],
        _binding(
            "b",
            token_scope_id=_OTHER_SCOPE,
            scoped_token_digest=token,
        ),
    )

    assert FindingCode.TOKEN_COLLISION in _codes(audit_resolved_bindings(same_scope))
    assert FindingCode.TOKEN_COLLISION not in _codes(
        audit_resolved_bindings(different_scope)
    )


def test_duplicate_content_assignment_uses_distinct_bindings() -> None:
    content = _digest("content.shared")
    result = audit_resolved_bindings(
        (_binding("a", content_digest=content), _binding("b", content_digest=content))
    )

    assert FindingCode.DUPLICATE_CONTENT_ASSIGNMENT in _codes(result)
    finding = next(
        item
        for item in result.findings
        if item.code is FindingCode.DUPLICATE_CONTENT_ASSIGNMENT
    )
    assert len(finding.binding_digests) == _DISTINCT_BINDING_COUNT


@pytest.mark.parametrize(
    ("state", "code"),
    [
        (BindingState.UNRESOLVED, FindingCode.UNRESOLVED_BINDING),
        (BindingState.UNSUPPORTED, FindingCode.UNSUPPORTED_BINDING),
    ],
)
def test_nonbound_state_abstains_without_becoming_negative(
    state: BindingState,
    code: FindingCode,
) -> None:
    binding = _binding(
        state.value,
        state=state,
        observed_subject_component_ids=(),
        token_scope_id=None,
        scoped_token_digest=None,
        content_digest=None,
    )

    result = audit_resolved_bindings((binding,))

    assert result.disposition is AuditDisposition.ABSTAINED
    assert result.support is SupportState.ABSTAINED
    assert _codes(result) == (code,)


def test_unbound_state_may_retain_upstream_graph_identity_only() -> None:
    binding = _binding(
        "unresolved",
        state=BindingState.UNRESOLVED,
        observed_subject_component_ids=(),
        token_scope_id=None,
        scoped_token_digest=None,
        content_digest=None,
    )

    result = audit_resolved_bindings((binding,))

    assert result.findings[0].component_ids == ()
    assert binding.entity_component_id is not None
    assert binding.upstream_subject_component_ids


def test_unbound_observed_evidence_and_duplicate_binding_reject() -> None:
    invalid = _binding(
        "invalid",
        state=BindingState.UNRESOLVED,
    )
    with pytest.raises(ValueError, match="cannot carry"):
        audit_resolved_bindings((invalid,))
    valid = _binding("valid")
    with pytest.raises(ValueError, match="unique"):
        audit_resolved_bindings((valid, valid))


@pytest.mark.parametrize("scope", ["", " leading", "a" * 129])
def test_token_scope_requires_a_bounded_identifier(scope: str) -> None:
    with pytest.raises(ValueError, match="token scope"):
        audit_resolved_bindings((_binding("scope", token_scope_id=scope),))
