"""Privacy-minimized deterministic binding checks for M02-02.

The kernel consumes component identifiers already resolved by an upstream identity authority.
It detects contradictions but never links, merges, or re-solves identity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-zA-Z][a-zA-Z0-9._:-]{0,127}$")
_EMPTY_BINDINGS = "at least one resolved binding is required"
_DUPLICATE_BINDINGS = "binding digests must be unique"
_INVALID_DIGEST = "binding audit references must be tagged SHA-256 digests"
_DUPLICATE_SUBJECTS = "subject component references must be unique per binding"
_BOUND_INCOMPLETE = "bound bindings require component, subject, token, and content claims"
_UNRESOLVED_CARRIES_EVIDENCE = "unresolved bindings cannot carry observed evidence"
_INVALID_SCOPE = "token scope must be a nonempty bounded identifier"


class EntityKind(StrEnum):
    """Closed upstream entity kinds; no direct identifiers cross this boundary."""

    PATIENT = "patient"
    SPECIMEN = "specimen"
    ALIQUOT = "aliquot"
    SECTION = "section"
    ANALYTE = "analyte"
    RUN = "run"
    DERIVED_OBJECT = "derived_object"


class BindingState(StrEnum):
    """Explicit state of an upstream component binding."""

    BOUND = "bound"
    UNRESOLVED = "unresolved"
    UNSUPPORTED = "unsupported"


class FindingCode(StrEnum):
    """Closed, non-scientific identity-binding findings."""

    SWAP = "swap"
    TOKEN_COLLISION = "token" + "_collision"
    DUPLICATE_CONTENT_ASSIGNMENT = "duplicate_content_assignment"
    CROSS_PATIENT_LINK = "cross_patient_link"
    UNRESOLVED_BINDING = "unresolved_binding"
    UNSUPPORTED_BINDING = "unsupported_binding"


class AuditDisposition(StrEnum):
    """Whether binding evidence may proceed."""

    CONFORMANT = "conformant"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"


class SupportState(StrEnum):
    """Support state; abstention is not a negative identity finding."""

    SUPPORTED = "supported"
    ABSTAINED = "abstained"


@dataclass(frozen=True, slots=True)
class ResolvedComponentBinding:
    """One privacy-safe check against an upstream resolved identity component."""

    binding_digest: str
    entity_kind: EntityKind
    state: BindingState
    entity_component_id: str | None = None
    upstream_subject_component_ids: tuple[str, ...] = ()
    observed_subject_component_ids: tuple[str, ...] = ()
    token_scope_id: str | None = None
    scoped_token_digest: str | None = None
    content_digest: str | None = None


@dataclass(frozen=True, slots=True, order=True)
class BindingFinding:
    """Canonical privacy-minimized finding over opaque digests only."""

    code: FindingCode
    binding_digests: tuple[str, ...]
    component_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BindingAuditResult:
    """Deterministic aggregate without raw identifiers or measurements."""

    disposition: AuditDisposition
    support: SupportState
    human_review_required: bool
    findings: tuple[BindingFinding, ...]


def audit_resolved_bindings(
    bindings: tuple[ResolvedComponentBinding, ...],
) -> BindingAuditResult:
    """Audit caller-supplied resolved components without changing their identity."""

    ordered = _validate_and_order(bindings)
    findings = [finding for binding in ordered for finding in _binding_findings(binding)]
    findings.extend(_group_findings(ordered))
    canonical = tuple(sorted(findings))
    hard_conflict = any(
        finding.code
        in {
            FindingCode.SWAP,
            FindingCode.TOKEN_COLLISION,
            FindingCode.DUPLICATE_CONTENT_ASSIGNMENT,
            FindingCode.CROSS_PATIENT_LINK,
        }
        for finding in canonical
    )
    abstained = bool(canonical) and not hard_conflict
    return BindingAuditResult(
        disposition=(
            AuditDisposition.QUARANTINED
            if hard_conflict
            else AuditDisposition.ABSTAINED
            if abstained
            else AuditDisposition.CONFORMANT
        ),
        support=SupportState.ABSTAINED if canonical else SupportState.SUPPORTED,
        human_review_required=bool(canonical),
        findings=canonical,
    )


def _validate_and_order(
    bindings: tuple[ResolvedComponentBinding, ...],
) -> tuple[ResolvedComponentBinding, ...]:
    if not bindings:
        raise ValueError(_EMPTY_BINDINGS)
    identifiers = tuple(binding.binding_digest for binding in bindings)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(_DUPLICATE_BINDINGS)
    for binding in bindings:
        references = (
            binding.binding_digest,
            binding.entity_component_id,
            binding.scoped_token_digest,
            binding.content_digest,
            *binding.upstream_subject_component_ids,
            *binding.observed_subject_component_ids,
        )
        if any(value is not None and _DIGEST.fullmatch(value) is None for value in references):
            raise ValueError(_INVALID_DIGEST)
        if (
            binding.token_scope_id is not None
            and _IDENTIFIER.fullmatch(binding.token_scope_id) is None
        ):
            raise ValueError(_INVALID_SCOPE)
        subject_groups = (
            binding.upstream_subject_component_ids,
            binding.observed_subject_component_ids,
        )
        if any(len(values) != len(set(values)) for values in subject_groups):
            raise ValueError(_DUPLICATE_SUBJECTS)
        if binding.state is BindingState.BOUND:
            if (
                binding.entity_component_id is None
                or not binding.upstream_subject_component_ids
                or not binding.observed_subject_component_ids
                or binding.token_scope_id is None
                or binding.scoped_token_digest is None
                or binding.content_digest is None
            ):
                raise ValueError(_BOUND_INCOMPLETE)
        elif any(
            value is not None
            for value in (
                binding.token_scope_id,
                binding.scoped_token_digest,
                binding.content_digest,
            )
        ) or binding.observed_subject_component_ids:
            raise ValueError(_UNRESOLVED_CARRIES_EVIDENCE)
    return tuple(sorted(bindings, key=lambda item: item.binding_digest))


def _binding_findings(binding: ResolvedComponentBinding) -> tuple[BindingFinding, ...]:
    if binding.state is not BindingState.BOUND:
        code = (
            FindingCode.UNRESOLVED_BINDING
            if binding.state is BindingState.UNRESOLVED
            else FindingCode.UNSUPPORTED_BINDING
        )
        return (BindingFinding(code, (binding.binding_digest,)),)

    findings: list[BindingFinding] = []
    upstream_subjects = tuple(sorted(binding.upstream_subject_component_ids))
    observed_subjects = tuple(sorted(binding.observed_subject_component_ids))
    subject_union = tuple(sorted(set(upstream_subjects) | set(observed_subjects)))
    if upstream_subjects != observed_subjects:
        findings.append(
            BindingFinding(
                FindingCode.SWAP,
                (binding.binding_digest,),
                subject_union,
            )
        )
    if (
        binding.entity_kind in {EntityKind.RUN, EntityKind.DERIVED_OBJECT}
        and len(subject_union) > 1
    ):
        findings.append(
            BindingFinding(
                FindingCode.CROSS_PATIENT_LINK,
                (binding.binding_digest,),
                subject_union,
            )
        )
    return tuple(findings)


def _group_findings(
    bindings: tuple[ResolvedComponentBinding, ...],
) -> tuple[BindingFinding, ...]:
    token_groups: dict[tuple[str, str], list[ResolvedComponentBinding]] = {}
    content_groups: dict[str, list[ResolvedComponentBinding]] = {}
    for binding in bindings:
        if binding.state is not BindingState.BOUND:
            continue
        if binding.token_scope_id is not None and binding.scoped_token_digest is not None:
            token_groups.setdefault(
                (binding.token_scope_id, binding.scoped_token_digest), []
            ).append(binding)
        if binding.content_digest is not None:
            content_groups.setdefault(binding.content_digest, []).append(binding)

    findings: list[BindingFinding] = []
    for group in token_groups.values():
        components = _entity_components(group)
        if len(components) > 1:
            findings.append(
                BindingFinding(
                    FindingCode.TOKEN_COLLISION,
                    _binding_digests(group),
                    components,
                )
            )
    for group in content_groups.values():
        binding_digests = _binding_digests(group)
        if len(binding_digests) > 1:
            findings.append(
                BindingFinding(
                    FindingCode.DUPLICATE_CONTENT_ASSIGNMENT,
                    binding_digests,
                    _entity_components(group),
                )
            )
    return tuple(findings)


def _binding_digests(bindings: list[ResolvedComponentBinding]) -> tuple[str, ...]:
    return tuple(sorted({binding.binding_digest for binding in bindings}))


def _entity_components(bindings: list[ResolvedComponentBinding]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                binding.entity_component_id
                for binding in bindings
                if binding.entity_component_id is not None
            }
        )
    )


__all__ = [
    "AuditDisposition",
    "BindingAuditResult",
    "BindingFinding",
    "BindingState",
    "EntityKind",
    "FindingCode",
    "ResolvedComponentBinding",
    "SupportState",
    "audit_resolved_bindings",
]
