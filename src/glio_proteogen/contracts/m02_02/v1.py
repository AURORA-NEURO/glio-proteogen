"""Strict public contracts for M02-02 identity-binding reconciliation."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, model_validator

from glio_proteogen.contracts.m01_02 import (
    EntityKind,
    IdentityLineageResolution,
    ResolvedLineageGraph,
)
from glio_proteogen.contracts.m01_02.v1 import ResolutionDecision
from glio_proteogen.contracts.m02_02.canonical import (
    configuration_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlRole,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    Limitation,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0202_MODULE_ID: Final = "GLIO-PROTEOGEN-M02-02"
M0202_CONTRACT_VERSION: Final = "1.0.0"
M0202_MAX_BINDINGS: Final = 10_000
# Exact maximum over 10,000 bindings: two local findings per binding,
# up to 5,000 token groups, 5,000 content groups, and one upstream finding.
M0202_MAX_FINDINGS: Final = 30_001
M0202_MAX_EVIDENCE_PER_BINDING: Final = 64
M0202_AUDIT_LIMITATION_CODE: Final = "identity_binding_audit_only"
M0202_AUTHORITY_LIMITATION_CODE: Final = "external_identity_authority_unverified"
_DERIVED_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)


class BindingState(StrEnum):
    BOUND = "bound"
    UNRESOLVED = "unresolved"
    UNSUPPORTED = "unsupported"


class FindingCode(StrEnum):
    SWAP = "swap"
    TOKEN_COLLISION = "token_collision"  # noqa: S105 - scientific finding, not a credential.
    DUPLICATE_CONTENT_ASSIGNMENT = "duplicate_content_assignment"
    CROSS_PATIENT_LINK = "cross_patient_link"
    UNRESOLVED_BINDING = "unresolved_binding"
    UNSUPPORTED_BINDING = "unsupported_binding"
    UPSTREAM_IDENTITY_UNRESOLVED = "upstream_identity_unresolved"


class BindingDisposition(StrEnum):
    CONFORMANT = "conformant"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"


_HARD_FINDINGS: Final = frozenset(
    {
        FindingCode.SWAP,
        FindingCode.TOKEN_COLLISION,
        FindingCode.DUPLICATE_CONTENT_ASSIGNMENT,
        FindingCode.CROSS_PATIENT_LINK,
    }
)
_REMEDIATION_BY_CODE: Final = {
    FindingCode.SWAP: "review_identity_swap",
    FindingCode.TOKEN_COLLISION: "resolve_token_collision",
    FindingCode.DUPLICATE_CONTENT_ASSIGNMENT: "deduplicate_content_assignment",
    FindingCode.CROSS_PATIENT_LINK: "quarantine_cross_patient_link",
    FindingCode.UNRESOLVED_BINDING: "resolve_identity_binding",
    FindingCode.UNSUPPORTED_BINDING: "supply_supported_identity_binding",
    FindingCode.UPSTREAM_IDENTITY_UNRESOLVED: "resolve_upstream_identity_lineage",
}


def _identity_state_for_decision(decision: ResolutionDecision) -> str:
    if decision is ResolutionDecision.RESOLVED:
        return "resolved"
    if decision is ResolutionDecision.UNRESOLVED:
        return "unresolved"
    return "conflicted"


class ScopedBindingToken(FrozenModel):
    """Externally issued opaque token; the module never receives a raw identifier."""

    scope_id: Identifier
    token_digest: Sha256Digest


class IdentificationArtifactBinding(FrozenModel):
    binding_id: Identifier
    artifact: ArtifactReference
    state: BindingState
    entity_id: Identifier | None = None
    entity_kind: EntityKind | None = None
    component_id: Sha256Digest | None = None
    observed_subject_component_ids: tuple[Sha256Digest, ...] = Field(
        default=(),
        max_length=256,
    )
    scoped_token: ScopedBindingToken | None = None
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0202_MAX_EVIDENCE_PER_BINDING,
    )

    @model_validator(mode="after")
    def state_and_claims_are_closed(self) -> IdentificationArtifactBinding:
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("binding evidence references must be unique")
        if len(self.observed_subject_component_ids) != len(
            set(self.observed_subject_component_ids)
        ):
            raise ValueError("observed subject component identifiers must be unique")
        identity_claims = (self.entity_id, self.entity_kind, self.component_id)
        if any(value is not None for value in identity_claims) and not all(
            value is not None for value in identity_claims
        ):
            raise ValueError("binding identity claims must be supplied together")
        if self.state is BindingState.BOUND:
            if (
                not all(value is not None for value in identity_claims)
                or not self.observed_subject_component_ids
                or self.scoped_token is None
            ):
                raise ValueError(
                    "bound bindings require identity, observed subjects, and a scoped token"
                )
        elif self.observed_subject_component_ids or self.scoped_token is not None:
            raise ValueError(
                "unresolved or unsupported bindings cannot carry observed identity evidence"
            )
        return self


class IdentityBindingPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    max_bindings: int = Field(default=M0202_MAX_BINDINGS, gt=0, le=M0202_MAX_BINDINGS)
    allowed_entity_kinds: tuple[EntityKind, ...] = Field(min_length=1, max_length=7)
    allowed_token_scope_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=256)
    evidence: ArtifactReference

    @model_validator(mode="after")
    def allowed_sets_are_unique(self) -> IdentityBindingPolicy:
        if len(self.allowed_entity_kinds) != len(set(self.allowed_entity_kinds)):
            raise ValueError("allowed entity kinds must be unique")
        if len(self.allowed_token_scope_ids) != len(set(self.allowed_token_scope_ids)):
            raise ValueError("allowed token scopes must be unique")
        return self


class ValidateIdentityBindingsRequest(FrozenModel):
    operation: Literal["validate_identity_bindings"] = "validate_identity_bindings"
    contract_version: Literal["1.0.0"] = M0202_CONTRACT_VERSION
    context: ExecutionContext
    identity_resolution: IdentityLineageResolution
    policy: IdentityBindingPolicy
    bindings: tuple[IdentificationArtifactBinding, ...] = Field(
        min_length=1,
        max_length=M0202_MAX_BINDINGS,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_and_bound(self) -> ValidateIdentityBindingsRequest:
        _require_authorized_context(self.context)
        if len(self.bindings) > self.policy.max_bindings:
            raise ValueError("binding count exceeds the active policy")
        identifiers = tuple(item.binding_id for item in self.bindings)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("binding identifiers must be unique")
        identity_reference = self.context.references.identity_lineage
        if identity_reference.binding_digest != self.identity_resolution.resolution_digest:
            raise ValueError("identity control does not bind the supplied resolution")
        expected_identity_state = _identity_state_for_decision(
            self.identity_resolution.decision
        )
        if identity_reference.state.value != expected_identity_state:
            raise ValueError(
                "identity control state contradicts the supplied resolution decision"
            )
        expected_configuration = configuration_digest(self.policy)
        if (
            self.context.references.approved_configuration.evidence.digest
            != expected_configuration
        ):
            raise ValueError("approved configuration does not bind the active policy")
        return self


class BindingAssessment(FrozenModel):
    binding_id: Identifier
    artifact_digest: Sha256Digest
    state: BindingState
    entity_kind: EntityKind | None = None
    entity_component_id: Sha256Digest | None = None
    upstream_subject_component_ids: tuple[Sha256Digest, ...] = Field(
        default=(),
        max_length=256,
    )
    observed_subject_component_ids: tuple[Sha256Digest, ...] = Field(
        default=(),
        max_length=256,
    )
    finding_codes: tuple[FindingCode, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def assessment_is_closed(self) -> BindingAssessment:
        for values in (
            self.upstream_subject_component_ids,
            self.observed_subject_component_ids,
            self.finding_codes,
        ):
            if len(values) != len(set(values)):
                raise ValueError("binding assessment values must be unique")
        if self.state is BindingState.BOUND and (
            self.entity_kind is None
            or self.entity_component_id is None
            or not self.upstream_subject_component_ids
            or not self.observed_subject_component_ids
        ):
            raise ValueError("bound assessments require resolved identity components")
        if self.state is not BindingState.BOUND and self.observed_subject_component_ids:
            raise ValueError("non-bound assessments cannot claim observed subjects")
        return self


class IdentityBindingFinding(FrozenModel):
    code: FindingCode
    binding_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0202_MAX_BINDINGS)
    artifact_digests: tuple[Sha256Digest, ...] = Field(
        default=(),
        max_length=M0202_MAX_BINDINGS,
    )
    component_ids: tuple[Sha256Digest, ...] = Field(
        default=(),
        max_length=M0202_MAX_BINDINGS,
    )
    remediation_code: Identifier

    @model_validator(mode="after")
    def references_and_remediation_are_closed(self) -> IdentityBindingFinding:
        for values in (self.binding_ids, self.artifact_digests, self.component_ids):
            if len(values) != len(set(values)):
                raise ValueError("identity binding finding references must be unique")
        if self.code is FindingCode.UPSTREAM_IDENTITY_UNRESOLVED:
            if self.binding_ids or self.artifact_digests:
                raise ValueError("upstream findings cannot claim binding evidence")
        elif not self.binding_ids or not self.artifact_digests:
            raise ValueError("binding findings require binding and artifact references")
        if self.remediation_code != _REMEDIATION_BY_CODE[self.code]:
            raise ValueError("finding remediation does not match its code")
        return self


class IdentityBindingEvaluation(FrozenModel):
    output_type: Literal["identity_binding_evaluation"] = "identity_binding_evaluation"
    evaluation_id: Identifier
    result_version: Literal["1.0.0"] = M0202_CONTRACT_VERSION
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    upstream_resolution_digest: Sha256Digest
    upstream_graph_digest: Sha256Digest
    upstream_resolution_decision: ResolutionDecision
    result_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    disposition: BindingDisposition
    bindings: tuple[BindingAssessment, ...] = Field(
        min_length=1,
        max_length=M0202_MAX_BINDINGS,
    )
    findings: tuple[IdentityBindingFinding, ...] = Field(
        default=(),
        max_length=M0202_MAX_FINDINGS,
    )
    lineage_graph: ResolvedLineageGraph
    parent_target: Literal["protein_subtype"] = "protein_subtype"
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=7, max_length=512)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def result_is_relationally_closed(  # noqa: PLR0912, PLR0915 - one output closure.
        self,
    ) -> IdentityBindingEvaluation:
        binding_ids = tuple(item.binding_id for item in self.bindings)
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("binding assessment identifiers must be unique")
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("identity binding evidence references must be unique")
        known_bindings = set(binding_ids)
        known_artifacts = {item.artifact_digest for item in self.bindings}
        binding_by_id = {item.binding_id: item for item in self.bindings}
        codes_by_binding: dict[Identifier, set[FindingCode]] = {
            binding_id: set() for binding_id in binding_ids
        }
        graph_components = {node.component_id for node in self.lineage_graph.nodes}
        graph_components.update(
            component_id
            for node in self.lineage_graph.nodes
            for component_id in node.subject_component_ids
        )
        kinds_by_component: dict[Sha256Digest, set[EntityKind]] = {}
        subjects_by_component: dict[Sha256Digest, tuple[Sha256Digest, ...]] = {}
        for node in self.lineage_graph.nodes:
            kinds_by_component.setdefault(node.component_id, set()).add(node.kind)
            prior_subjects = subjects_by_component.setdefault(
                node.component_id,
                node.subject_component_ids,
            )
            if prior_subjects != node.subject_component_ids:
                raise ValueError("identity component has inconsistent subject bindings")
        for binding in self.bindings:
            referenced_components = set(binding.upstream_subject_component_ids)
            referenced_components.update(binding.observed_subject_component_ids)
            if binding.entity_component_id is not None:
                referenced_components.add(binding.entity_component_id)
            if not referenced_components.issubset(graph_components):
                raise ValueError("binding assessment references an unknown identity component")
            if binding.state is BindingState.BOUND:
                component_id = binding.entity_component_id
                if (
                    component_id is None
                    or binding.entity_kind not in kinds_by_component.get(component_id, set())
                    or binding.upstream_subject_component_ids
                    != subjects_by_component.get(component_id)
                ):
                    raise ValueError(
                        "bound assessment contradicts its upstream identity component"
                    )
        if len(self.findings) != len(set(self.findings)):
            raise ValueError("identity binding findings must be unique")
        for finding in self.findings:
            if not set(finding.binding_ids).issubset(known_bindings):
                raise ValueError("finding references an unknown binding")
            for binding_id in finding.binding_ids:
                codes_by_binding[binding_id].add(finding.code)
            if not set(finding.artifact_digests).issubset(known_artifacts):
                raise ValueError("finding references an unknown artifact digest")
            if not set(finding.component_ids).issubset(graph_components):
                raise ValueError("finding references an unknown identity component")
            if finding.code is not FindingCode.UPSTREAM_IDENTITY_UNRESOLVED:
                referenced_bindings = tuple(
                    binding_by_id[binding_id] for binding_id in finding.binding_ids
                )
                if set(finding.artifact_digests) != {
                    binding.artifact_digest for binding in referenced_bindings
                }:
                    raise ValueError("finding artifacts do not match its bindings")
                binding_components = {
                    component_id
                    for binding in referenced_bindings
                    for component_id in (
                        binding.entity_component_id,
                        *binding.upstream_subject_component_ids,
                        *binding.observed_subject_component_ids,
                    )
                    if component_id is not None
                }
                if not set(finding.component_ids).issubset(binding_components):
                    raise ValueError("finding components do not match its bindings")
        for binding in self.bindings:
            expected_codes = codes_by_binding[binding.binding_id]
            if set(binding.finding_codes) != expected_codes:
                raise ValueError("binding finding codes do not match aggregate findings")
            state_code = {
                BindingState.BOUND: None,
                BindingState.UNRESOLVED: FindingCode.UNRESOLVED_BINDING,
                BindingState.UNSUPPORTED: FindingCode.UNSUPPORTED_BINDING,
            }[binding.state]
            soft_codes = {
                FindingCode.UNRESOLVED_BINDING,
                FindingCode.UNSUPPORTED_BINDING,
            }
            if state_code is None:
                if expected_codes & soft_codes:
                    raise ValueError("bound assessment cannot carry a non-bound finding")
                if (
                    binding.observed_subject_component_ids
                    != binding.upstream_subject_component_ids
                    and FindingCode.SWAP not in expected_codes
                ):
                    raise ValueError("subject mismatch requires a swap finding")
                subject_union = set(binding.upstream_subject_component_ids) | set(
                    binding.observed_subject_component_ids
                )
                if (
                    binding.entity_kind in {EntityKind.RUN, EntityKind.DERIVED_OBJECT}
                    and len(subject_union) > 1
                    and FindingCode.CROSS_PATIENT_LINK not in expected_codes
                ):
                    raise ValueError("multi-subject run requires a cross-patient finding")
            elif state_code not in expected_codes or expected_codes & (soft_codes - {state_code}):
                raise ValueError("non-bound assessment finding contradicts its state")
        codes = {item.code for item in self.findings}
        expected_disposition = (
            BindingDisposition.QUARANTINED
            if codes & _HARD_FINDINGS
            else BindingDisposition.ABSTAINED
            if codes
            else BindingDisposition.CONFORMANT
        )
        if self.disposition is not expected_disposition:
            raise ValueError("identity binding disposition contradicts its findings")
        upstream_code = FindingCode.UPSTREAM_IDENTITY_UNRESOLVED
        upstream_resolved = self.upstream_resolution_decision is ResolutionDecision.RESOLVED
        if (upstream_code in codes) == upstream_resolved:
            raise ValueError("upstream resolution finding contradicts its decision")
        if self.disposition is BindingDisposition.CONFORMANT and not upstream_resolved:
            raise ValueError("conformant bindings require resolved upstream identity")
        expected_support = {
            BindingDisposition.CONFORMANT: (
                SupportStatus.SUPPORTED,
                "identity_bindings_conformant",
                False,
            ),
            BindingDisposition.QUARANTINED: (
                SupportStatus.REVIEW_REQUIRED,
                "identity_bindings_quarantined",
                True,
            ),
            BindingDisposition.ABSTAINED: (
                SupportStatus.REVIEW_REQUIRED,
                "identity_bindings_abstained",
                True,
            ),
        }[self.disposition]
        if (
            self.support.status,
            self.support.reason_code,
            self.human_review_required,
        ) != expected_support:
            raise ValueError("identity binding support contradicts its disposition")
        if self.lineage_graph.graph_digest != self.upstream_graph_digest:
            raise ValueError("output lineage graph does not bind its upstream digest")
        _validate_result_provenance(self)
        if {item.code for item in self.limitations} != {
            M0202_AUDIT_LIMITATION_CODE,
            M0202_AUTHORITY_LIMITATION_CODE,
        }:
            raise ValueError("identity binding output requires both limitation codes")
        expected_digest = result_payload_digest(self)
        if self.result_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "result_digest", expected_digest)
        elif self.result_digest != expected_digest:
            raise ValueError("identity binding result digest does not match its content")
        return self


def _require_authorized_context(context: ExecutionContext) -> None:
    references = context.references
    if references.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize identity binding reconciliation")
    generic = (
        references.approved_configuration,
        references.provenance,
        references.quality,
        references.support,
        references.intended_use,
    )
    if any(reference.state is not UpstreamDecisionState.ACCEPTED for reference in generic):
        raise ValueError("every generic upstream control must accept binding reconciliation")


def _validate_result_provenance(result: IdentityBindingEvaluation) -> None:
    suffix = result.request_digest.removeprefix("sha256:")
    provenance = result.provenance
    required_digests = {
        result.request_digest,
        result.policy_digest,
        result.configuration_digest,
        result.upstream_resolution_digest,
        result.upstream_graph_digest,
        *(item.evidence_digest for item in provenance.control_decisions),
    }
    if (
        result.evaluation_id != f"evaluation.m0202.{suffix}"
        or provenance.activity_id != f"activity.m0202.{suffix}"
        or provenance.module_id != M0202_MODULE_ID
        or provenance.module_version != result.result_version
        or provenance.generated_at != result.completed_at
        or provenance.configuration_digest != result.configuration_digest
        or not required_digests.issubset(provenance.input_digests)
    ):
        raise ValueError("identity binding provenance envelope is inconsistent")
    controls_by_role = {item.role: item for item in provenance.control_decisions}
    states_by_role = {role: item.state for role, item in controls_by_role.items()}
    expected_states = {
        ControlRole.APPROVED_CONFIGURATION: "accepted",
        ControlRole.IDENTITY_LINEAGE: _identity_state_for_decision(
            result.upstream_resolution_decision
        ),
        ControlRole.PROVENANCE: "accepted",
        ControlRole.CONSENT: "granted",
        ControlRole.QUALITY: "accepted",
        ControlRole.SUPPORT: "accepted",
        ControlRole.INTENDED_USE: "accepted",
    }
    if (
        provenance.consent_state is not ConsentState.GRANTED
        or states_by_role != expected_states
    ):
        raise ValueError("identity binding provenance control states are inconsistent")
    configuration_control = controls_by_role[ControlRole.APPROVED_CONFIGURATION]
    identity_control = controls_by_role[ControlRole.IDENTITY_LINEAGE]
    consent_control = controls_by_role[ControlRole.CONSENT]
    if configuration_control.evidence_digest != result.configuration_digest:
        raise ValueError("approved configuration evidence does not bind the result")
    if identity_control.subject_digest != result.upstream_resolution_digest:
        raise ValueError("identity control does not bind the upstream resolution")
    if (
        provenance.consent_decision_id,
        provenance.consent_state.value,
        provenance.consent_policy_version,
        provenance.consent_evidence_digest,
    ) != (
        consent_control.decision_id,
        consent_control.state,
        consent_control.policy_version,
        consent_control.evidence_digest,
    ):
        raise ValueError("consent provenance contradicts its control record")
    evidence_digests = {item.reference.digest for item in result.evidence}
    if not {
        item.evidence_digest for item in provenance.control_decisions
    }.issubset(evidence_digests):
        raise ValueError("result evidence does not cover every upstream control")


__all__ = [
    "M0202_AUDIT_LIMITATION_CODE",
    "M0202_AUTHORITY_LIMITATION_CODE",
    "M0202_CONTRACT_VERSION",
    "M0202_MAX_BINDINGS",
    "M0202_MAX_EVIDENCE_PER_BINDING",
    "M0202_MAX_FINDINGS",
    "M0202_MODULE_ID",
    "BindingAssessment",
    "BindingDisposition",
    "BindingState",
    "FindingCode",
    "IdentificationArtifactBinding",
    "IdentityBindingEvaluation",
    "IdentityBindingFinding",
    "IdentityBindingPolicy",
    "ScopedBindingToken",
    "ValidateIdentityBindingsRequest",
]
