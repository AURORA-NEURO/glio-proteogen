"""Contract-facing deterministic identity-binding audit for M02-02."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_02 import ResolvedLineageGraph
from glio_proteogen.contracts.m01_02.v1 import ResolutionDecision
from glio_proteogen.contracts.m02_02 import (
    M0202_AUDIT_LIMITATION_CODE,
    M0202_AUTHORITY_LIMITATION_CODE,
    M0202_CONTRACT_VERSION,
    M0202_MODULE_ID,
    BindingAssessment,
    BindingDisposition,
    BindingState,
    FindingCode,
    IdentificationArtifactBinding,
    IdentityBindingEvaluation,
    IdentityBindingFinding,
    ValidateIdentityBindingsRequest,
    canonical_request_digest,
    configuration_digest,
    policy_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)
from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage.kernel import (
    BindingState as KernelBindingState,
)
from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage.kernel import (
    EntityKind as KernelEntityKind,
)
from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage.kernel import (
    FindingCode as KernelFindingCode,
)
from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage.kernel import (
    ResolvedComponentBinding,
    audit_resolved_bindings,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m01_02 import EntityKind

_REQUEST_ADAPTER: Final[TypeAdapter[ValidateIdentityBindingsRequest]] = TypeAdapter(
    ValidateIdentityBindingsRequest
)
_AUTHORIZATION_MESSAGE: Final = (
    "identity binding reconciliation requires accepted upstream controls"
)
_REMEDIATION: Final = {
    FindingCode.SWAP: "review_identity_swap",
    FindingCode.TOKEN_COLLISION: "resolve_token_collision",
    FindingCode.DUPLICATE_CONTENT_ASSIGNMENT: "deduplicate_content_assignment",
    FindingCode.CROSS_PATIENT_LINK: "quarantine_cross_patient_link",
    FindingCode.UNRESOLVED_BINDING: "resolve_identity_binding",
    FindingCode.UNSUPPORTED_BINDING: "supply_supported_identity_binding",
    FindingCode.UPSTREAM_IDENTITY_UNRESOLVED: "resolve_upstream_identity_lineage",
}
_HARD: Final = frozenset(
    {
        FindingCode.SWAP,
        FindingCode.TOKEN_COLLISION,
        FindingCode.DUPLICATE_CONTENT_ASSIGNMENT,
        FindingCode.CROSS_PATIENT_LINK,
    }
)
_LIMITATIONS: Final = (
    Limitation(
        code=M0202_AUDIT_LIMITATION_CODE,
        statement=(
            "This result audits artifact bindings against an immutable upstream identity "
            "resolution; it does not infer, merge, or re-solve identity."
        ),
    ),
    Limitation(
        code=M0202_AUTHORITY_LIMITATION_CODE,
        statement=(
            "Opaque tokens, artifact references, and upstream identity authority are "
            "caller-declared and are not authenticated by M02-02."
        ),
    ),
)


class IdentityBindingAuthorizationError(ValueError):
    """Authorization failed before bindings were parsed, traversed, or hashed."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


@dataclass(frozen=True, slots=True)
class _PreparedBinding:
    source: IdentificationArtifactBinding
    audit_digest: str
    state: BindingState
    entity_kind: EntityKind | None
    entity_component_id: str | None
    upstream_subjects: tuple[str, ...]
    observed_subjects: tuple[str, ...]
    component_claim_mismatch: bool


class M0202IdentityBindingEvaluator:
    """Audit declared bindings without mutating or recomputing upstream identity."""

    __slots__ = ()

    def evaluate(
        self,
        request: ValidateIdentityBindingsRequest,
    ) -> IdentityBindingEvaluation:
        preflight_identity_binding_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        prepared = _prepare(validated)
        findings = _findings(validated, prepared)
        assessments = _assessments(prepared, findings)
        codes = {item.code for item in findings}
        disposition = (
            BindingDisposition.QUARANTINED
            if codes & _HARD
            else BindingDisposition.ABSTAINED
            if codes
            else BindingDisposition.CONFORMANT
        )
        request_hash = canonical_request_digest(validated)
        policy_hash = policy_digest(validated.policy)
        configuration_hash = configuration_digest(validated.policy)
        resolution = validated.identity_resolution
        graph_hash = resolution.graph.graph_digest
        lineage_graph = _canonical_graph(resolution.graph)
        hashes = (
            request_hash,
            policy_hash,
            configuration_hash,
            resolution.resolution_digest,
            graph_hash,
        )
        return IdentityBindingEvaluation(
            evaluation_id=f"evaluation.m0202.{request_hash.removeprefix('sha256:')}",
            request_digest=request_hash,
            policy_digest=policy_hash,
            configuration_digest=configuration_hash,
            upstream_resolution_digest=resolution.resolution_digest,
            upstream_graph_digest=graph_hash,
            upstream_resolution_decision=resolution.decision,
            disposition=disposition,
            bindings=assessments,
            findings=findings,
            lineage_graph=lineage_graph,
            support=_support(disposition),
            uncertainty=_uncertainty(),
            provenance=_provenance(validated, hashes),
            evidence=_evidence(validated),
            limitations=_LIMITATIONS,
            human_review_required=disposition is not BindingDisposition.CONFORMANT,
            completed_at=validated.context.occurred_at,
            supersedes_result_digest=validated.supersedes_result_digest,
        )


def evaluate_identity_bindings(
    request: ValidateIdentityBindingsRequest,
) -> IdentityBindingEvaluation:
    """Evaluate one immutable identity-binding request."""

    return M0202IdentityBindingEvaluator().evaluate(request)


def preflight_identity_binding_authorization(candidate: object) -> None:
    """Reject raw denial before typed validation or access to binding payloads."""

    context = (
        candidate.context
        if isinstance(candidate, ValidateIdentityBindingsRequest)
        else candidate.get("context")
        if isinstance(candidate, Mapping)
        else None
    )
    references = _value(context, "references")
    expected = {
        "approved_configuration": "accepted",
        "provenance": "accepted",
        "consent": "granted",
        "quality": "accepted",
        "support": "accepted",
        "intended_use": "accepted",
    }
    if any(
        _state(_value(_value(references, role), "state")) != state
        for role, state in expected.items()
    ):
        raise IdentityBindingAuthorizationError


def _value(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _canonical_graph(graph: ResolvedLineageGraph) -> ResolvedLineageGraph:
    nodes = tuple(
        sorted(
            (
                node.model_copy(
                    update={
                        "subject_component_ids": tuple(
                            sorted(node.subject_component_ids)
                        )
                    }
                )
                for node in graph.nodes
            ),
            key=canonical_json_bytes,
        )
    )
    operations = tuple(
        sorted(
            (
                operation.model_copy(
                    update={
                        "source_entity_ids": tuple(sorted(operation.source_entity_ids)),
                        "target_entity_ids": tuple(sorted(operation.target_entity_ids)),
                    }
                )
                for operation in graph.operations
            ),
            key=canonical_json_bytes,
        )
    )
    return ResolvedLineageGraph(
        nodes=nodes,
        operations=operations,
        graph_digest=graph.graph_digest,
    )


def _state(value: object) -> object:
    return getattr(value, "value", value)


def _prepare(request: ValidateIdentityBindingsRequest) -> tuple[_PreparedBinding, ...]:
    nodes = {item.entity_id: item for item in request.identity_resolution.graph.nodes}
    graph_components = {
        component
        for node in request.identity_resolution.graph.nodes
        for component in (node.component_id, *node.subject_component_ids)
    }
    allowed_kinds = set(request.policy.allowed_entity_kinds)
    allowed_scopes = set(request.policy.allowed_token_scope_ids)
    prepared: list[_PreparedBinding] = []
    for binding in sorted(request.bindings, key=lambda item: item.binding_id):
        audit_digest = sha256_digest(
            {"binding_id": binding.binding_id, "artifact": binding.artifact.digest}
        )
        node = nodes.get(binding.entity_id) if binding.entity_id is not None else None
        state = binding.state
        if state is BindingState.BOUND and (
            node is None
            or node.kind not in allowed_kinds
            or binding.scoped_token is None
            or binding.scoped_token.scope_id not in allowed_scopes
            or not node.subject_component_ids
            or not set(binding.observed_subject_component_ids).issubset(graph_components)
        ):
            state = BindingState.UNSUPPORTED
        entity_kind: EntityKind | None = None
        entity_component_id: str | None = None
        upstream_subjects: tuple[str, ...] = ()
        observed_subjects: tuple[str, ...] = ()
        component_claim_mismatch = False
        if state is BindingState.BOUND and node is not None:
            entity_kind = node.kind
            entity_component_id = node.component_id
            upstream_subjects = tuple(sorted(node.subject_component_ids))
            observed_subjects = tuple(sorted(binding.observed_subject_component_ids))
            component_claim_mismatch = (
                binding.entity_kind is not node.kind
                or binding.component_id != node.component_id
            )
        prepared.append(
            _PreparedBinding(
                source=binding,
                audit_digest=audit_digest,
                state=state,
                entity_kind=entity_kind,
                entity_component_id=entity_component_id,
                upstream_subjects=upstream_subjects,
                observed_subjects=observed_subjects,
                component_claim_mismatch=component_claim_mismatch,
            )
        )
    return tuple(prepared)


def _findings(
    request: ValidateIdentityBindingsRequest,
    prepared: tuple[_PreparedBinding, ...],
) -> tuple[IdentityBindingFinding, ...]:
    by_digest = {item.audit_digest: item for item in prepared}
    kernel_bindings = tuple(_kernel_binding(item) for item in prepared)
    audit = audit_resolved_bindings(kernel_bindings)
    grouped: dict[tuple[FindingCode, tuple[str, ...]], set[str]] = {}
    for finding in audit.findings:
        code = FindingCode(KernelFindingCode(finding.code).value)
        binding_ids = tuple(
            sorted(by_digest[digest].source.binding_id for digest in finding.binding_digests)
        )
        grouped.setdefault((code, binding_ids), set()).update(finding.component_ids)
    for item in prepared:
        if item.component_claim_mismatch and item.entity_component_id is not None:
            grouped.setdefault((FindingCode.SWAP, (item.source.binding_id,)), set()).add(
                item.entity_component_id
            )
    if request.identity_resolution.decision is not ResolutionDecision.RESOLVED:
        grouped[(FindingCode.UPSTREAM_IDENTITY_UNRESOLVED, ())] = set()
    by_id = {item.source.binding_id: item for item in prepared}
    findings = []
    for (code, binding_ids), components in sorted(
        grouped.items(),
        key=lambda item: canonical_json_bytes(item[0]),
    ):
        findings.append(
            IdentityBindingFinding(
                code=code,
                binding_ids=binding_ids,
                artifact_digests=tuple(
                    sorted(
                        {
                            by_id[binding_id].source.artifact.digest
                            for binding_id in binding_ids
                        }
                    )
                ),
                component_ids=tuple(sorted(components)),
                remediation_code=_REMEDIATION[code],
            )
        )
    return tuple(findings)


def _kernel_binding(item: _PreparedBinding) -> ResolvedComponentBinding:
    source = item.source
    token = source.scoped_token
    return ResolvedComponentBinding(
        binding_digest=item.audit_digest,
        entity_kind=KernelEntityKind(
            item.entity_kind.value if item.entity_kind is not None else source.entity_kind.value
            if source.entity_kind is not None
            else "derived_object"
        ),
        state=KernelBindingState(item.state.value),
        entity_component_id=item.entity_component_id,
        upstream_subject_component_ids=item.upstream_subjects,
        observed_subject_component_ids=item.observed_subjects,
        token_scope_id=token.scope_id if item.state is BindingState.BOUND and token else None,
        scoped_token_digest=(
            token.token_digest if item.state is BindingState.BOUND and token else None
        ),
        content_digest=(source.artifact.digest if item.state is BindingState.BOUND else None),
    )


def _assessments(
    prepared: tuple[_PreparedBinding, ...],
    findings: tuple[IdentityBindingFinding, ...],
) -> tuple[BindingAssessment, ...]:
    codes_by_id: dict[str, set[FindingCode]] = {
        item.source.binding_id: set() for item in prepared
    }
    for finding in findings:
        for binding_id in finding.binding_ids:
            codes_by_id[binding_id].add(finding.code)
    return tuple(
        BindingAssessment(
            binding_id=item.source.binding_id,
            artifact_digest=item.source.artifact.digest,
            state=item.state,
            entity_kind=item.entity_kind,
            entity_component_id=item.entity_component_id,
            upstream_subject_component_ids=item.upstream_subjects,
            observed_subject_component_ids=item.observed_subjects,
            finding_codes=tuple(sorted(codes_by_id[item.source.binding_id], key=str)),
        )
        for item in prepared
    )


def _support(disposition: BindingDisposition) -> SupportDecision:
    if disposition is BindingDisposition.CONFORMANT:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="identity_bindings_conformant",
            rationale="All artifact bindings agree with the supplied upstream resolution.",
        )
    status = (
        "identity_bindings_quarantined"
        if disposition is BindingDisposition.QUARANTINED
        else "identity_bindings_abstained"
    )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code=status,
        rationale="Identity binding evidence is conflicting, unresolved, or unsupported.",
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(rationale: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)

    return UncertaintyProfile(
        measurement=unavailable("The audit receives opaque identity claims, not measurements."),
        sampling=unavailable("Sampling uncertainty remains with the upstream authority."),
        parameter=unavailable("The deterministic audit fits no parameters."),
        model_form=unavailable("No learned identity model is used."),
        identification=unavailable("Identity authority remains external to M02-02."),
        support=unavailable("Support follows closed deterministic findings."),
        transport=unavailable("Cross-system token authority is not assessed."),
    )


def _controls(
    request: ValidateIdentityBindingsRequest,
) -> tuple[ControlDecisionRecord, ...]:
    references = request.context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration, None),
        (
            ControlRole.IDENTITY_LINEAGE,
            references.identity_lineage,
            references.identity_lineage.binding_digest,
        ),
        (ControlRole.PROVENANCE, references.provenance, None),
        (ControlRole.CONSENT, references.consent, None),
        (ControlRole.QUALITY, references.quality, None),
        (ControlRole.SUPPORT, references.support, None),
        (ControlRole.INTENDED_USE, references.intended_use, None),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject,
        )
        for role, reference, subject in values
    )


def _provenance(
    request: ValidateIdentityBindingsRequest,
    hashes: tuple[str, str, str, str, str],
) -> ProvenanceRecord:
    request_hash, policy_hash, configuration_hash, resolution_hash, graph_hash = hashes
    references = request.context.references
    controls = _controls(request)
    return ProvenanceRecord(
        activity_id=f"activity.m0202.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0202_MODULE_ID,
        module_version=M0202_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted(
                {
                    request_hash,
                    policy_hash,
                    configuration_hash,
                    resolution_hash,
                    graph_hash,
                    *(item.evidence_digest for item in controls),
                }
            )
        ),
        configuration_digest=configuration_hash,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _evidence(
    request: ValidateIdentityBindingsRequest,
) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    role_artifacts: tuple[tuple[str, ArtifactReference], ...] = (
        ("approved configuration", references.approved_configuration.evidence),
        ("identity lineage", references.identity_lineage.evidence),
        ("provenance", references.provenance.evidence),
        ("consent", references.consent.evidence),
        ("quality", references.quality.evidence),
        ("support", references.support.evidence),
        ("intended use", references.intended_use.evidence),
        ("binding policy", request.policy.evidence),
    )
    return tuple(
        sorted(
            {
                EvidenceReference(
                    reference=artifact,
                    role="evidence",
                    claim=f"Caller-declared {role} evidence for identity-binding audit.",
                )
                for role, artifact in role_artifacts
            },
            key=canonical_json_bytes,
        )
    )


__all__ = [
    "IdentityBindingAuthorizationError",
    "M0202IdentityBindingEvaluator",
    "evaluate_identity_bindings",
    "preflight_identity_binding_authorization",
]
