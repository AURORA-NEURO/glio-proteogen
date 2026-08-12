"""Focused adversarial evidence for the pure M01-02 reconciliation solver."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m01_02.canonical import policy_digest
from glio_proteogen.contracts.m01_02.v1 import (
    ConcordanceClassification,
    ConcordanceObservation,
    DemultiplexChannel,
    EntityComposition,
    EntityKind,
    IdentityAuthorityReference,
    IdentityControlRole,
    IdentityEntity,
    IdentityExecutionContext,
    IdentityLineageResolutionDraft,
    IdentityReconciliationReferences,
    IdentityResolutionPolicy,
    LineageOperation,
    LineageOperationKind,
    ReconcileIdentityLineageRequest,
    ResolutionDecision,
    SameAsAssertion,
    ScopedIdentityToken,
    SubjectMembershipAssertion,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage import solver
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.solver import (
    ReconciliationAuthorizationError,
    _analyze,
    reconcile_identity_lineage,
)

SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64
SHA_D = "sha256:" + "d" * 64
POLICY_VERSION = "1.0.0"
AUTHORITY_ID = "authority.synthetic"
TWO = 2
INFORMATIVE_LOCI = 8


class _PreauthorizationBoundaryViolatedError(AssertionError):
    def __init__(self) -> None:
        super().__init__("private analysis or canonical hashing ran before authorization")


def _artifact(name: str, digest: str = SHA_A) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=digest,
        media_type="application/vnd.aurora.synthetic+json",
    )


def _policy(*, pooling: bool = True) -> IdentityResolutionPolicy:
    return IdentityResolutionPolicy(
        policy_id="identity.policy.synthetic",
        version=POLICY_VERSION,
        max_component_size=32,
        maximum_depth=16,
        allow_mixed_subject_pooling=pooling,
        require_demultiplex_authority=True,
        allowed_operation_kinds=tuple(LineageOperationKind),
    )


def _context(policy: IdentityResolutionPolicy) -> IdentityExecutionContext:
    accepted = UpstreamDecisionReference(
        decision_id="control.synthetic",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version=POLICY_VERSION,
        evidence=_artifact("control.evidence"),
    )
    configuration = accepted.model_copy(
        update={"evidence": _artifact("policy.evidence", policy_digest(policy))}
    )
    return IdentityExecutionContext(
        request_id="request.synthetic",
        actor_id="actor.synthetic",
        occurred_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
        references=IdentityReconciliationReferences(
            approved_configuration=configuration,
            identity_authority=IdentityAuthorityReference(
                decision_id=AUTHORITY_ID,
                state=UpstreamDecisionState.ACCEPTED,
                policy_version=POLICY_VERSION,
                evidence=_artifact("authority.evidence"),
            ),
            provenance=accepted.model_copy(update={"decision_id": "provenance.synthetic"}),
            consent=ConsentReference(
                decision_id="consent.synthetic",
                state=ConsentState.GRANTED,
                policy_version=POLICY_VERSION,
                evidence=_artifact("consent.evidence"),
            ),
            quality=accepted.model_copy(update={"decision_id": "quality.synthetic"}),
            support=accepted.model_copy(update={"decision_id": "support.synthetic"}),
            intended_use=accepted.model_copy(update={"decision_id": "use.synthetic"}),
        ),
    )


def _entity(
    entity_id: str,
    kind: EntityKind,
    composition: EntityComposition,
    *,
    token_digest: str | None = None,
    scope_id: str = "project.synthetic",
) -> IdentityEntity:
    tokens = (
        (
            ScopedIdentityToken(
                issuer_id="issuer.synthetic",
                namespace_id="namespace.synthetic",
                scope_id=scope_id,
                key_id="key.synthetic",
                token_version="1.0.0",  # noqa: S106 - semantic version, not a credential
                entity_kind=kind,
                token_digest=token_digest,
                evidence=_artifact(f"{entity_id}.token.evidence"),
            ),
        )
        if token_digest is not None
        else ()
    )
    return IdentityEntity(
        entity_id=entity_id,
        kind=kind,
        composition=composition,
        identity_tokens=tokens,
        evidence=(_artifact(f"{entity_id}.evidence"),),
    )


def _membership(assertion_id: str, entity_id: str, patient_id: str) -> SubjectMembershipAssertion:
    return SubjectMembershipAssertion(
        assertion_id=assertion_id,
        entity_id=entity_id,
        subject_entity_id=patient_id,
        authority_decision_id=AUTHORITY_ID,
        policy_version=POLICY_VERSION,
        evidence=(_artifact(f"{assertion_id}.evidence"),),
    )


def _operation(  # noqa: PLR0913
    operation_id: str,
    kind: LineageOperationKind,
    sources: tuple[str, ...],
    targets: tuple[str, ...],
    *,
    mixed: bool = False,
    channels: tuple[DemultiplexChannel, ...] = (),
) -> LineageOperation:
    return LineageOperation(
        operation_id=operation_id,
        kind=kind,
        source_entity_ids=sources,
        target_entity_ids=targets,
        mixed_subject=mixed,
        channels=channels,
        authority_decision_id=AUTHORITY_ID,
        policy_version=POLICY_VERSION,
        evidence=(_artifact(f"{operation_id}.evidence"),),
    )


def _request(
    entities: tuple[IdentityEntity, ...],
    *,
    assertions: tuple[object, ...] = (),
    operations: tuple[LineageOperation, ...] = (),
    observations: tuple[ConcordanceObservation, ...] = (),
    pooling: bool = True,
) -> ReconcileIdentityLineageRequest:
    policy = _policy(pooling=pooling)
    return ReconcileIdentityLineageRequest.model_validate(
        {
            "context": _context(policy),
            "policy": policy,
            "entities": entities,
            "assertions": assertions,
            "lineage_operations": operations,
            "concordance_observations": observations,
        },
        strict=True,
    )


def test_clean_lineage_returns_pure_deterministic_draft() -> None:
    patient = _entity("patient.a", EntityKind.PATIENT, EntityComposition.SINGLE_SUBJECT)
    specimen = _entity("specimen.a", EntityKind.SPECIMEN, EntityComposition.SINGLE_SUBJECT)
    request = _request(
        (patient, specimen),
        assertions=(_membership("membership.a", "specimen.a", "patient.a"),),
        operations=(
            _operation(
                "collection.a",
                LineageOperationKind.COLLECTED_FROM,
                ("patient.a",),
                ("specimen.a",),
            ),
        ),
    )

    draft = reconcile_identity_lineage(request)

    assert isinstance(draft, IdentityLineageResolutionDraft)
    assert draft.decision is ResolutionDecision.RESOLVED
    assert draft.human_review_required is False
    assert draft.core_digest.startswith("sha256:")
    patient_component = next(
        component for component in draft.components if "patient.a" in component.member_entity_ids
    )
    specimen_component = next(
        component for component in draft.components if "specimen.a" in component.member_entity_ids
    )
    assert patient_component.subject_component_ids == (patient_component.component_id,)
    assert specimen_component.subject_component_ids == (patient_component.component_id,)


def test_direct_solver_denial_precedes_analysis_and_canonical_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(
        (_entity("patient.a", EntityKind.PATIENT, EntityComposition.SINGLE_SUBJECT),)
    )
    consent = request.context.references.consent.model_copy(
        update={"state": ConsentState.WITHHELD}
    )
    references = request.context.references.model_copy(update={"consent": consent})
    denied = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise _PreauthorizationBoundaryViolatedError

    monkeypatch.setattr(solver, "_analyze", forbidden)
    monkeypatch.setattr(solver, "canonical_request_digest", forbidden)

    with pytest.raises(ReconciliationAuthorizationError) as raised:
        reconcile_identity_lineage(denied)

    assert raised.value.role is IdentityControlRole.CONSENT


def test_patient_alias_same_as_reduces_to_one_subject_component() -> None:
    patients = (
        _entity("patient.a", EntityKind.PATIENT, EntityComposition.SINGLE_SUBJECT),
        _entity("patient.alias", EntityKind.PATIENT, EntityComposition.SINGLE_SUBJECT),
    )
    same_as = SameAsAssertion(
        assertion_id="same.patient",
        left_entity_id="patient.a",
        right_entity_id="patient.alias",
        authority_decision_id=AUTHORITY_ID,
        policy_version=POLICY_VERSION,
        evidence=(_artifact("same.patient.evidence"),),
    )

    draft = reconcile_identity_lineage(_request(patients, assertions=(same_as,)))

    assert draft.decision is ResolutionDecision.RESOLVED
    assert len(draft.components) == 1
    assert draft.components[0].subject_component_ids == (draft.components[0].component_id,)
    assert draft.components[0].member_entity_ids == ("patient.a", "patient.alias")


def test_repeated_token_is_safe_only_inside_explicit_same_as_component() -> None:
    first = _entity(
        "specimen.a",
        EntityKind.SPECIMEN,
        EntityComposition.UNKNOWN,
        token_digest=SHA_B,
    )
    second = _entity(
        "specimen.b",
        EntityKind.SPECIMEN,
        EntityComposition.UNKNOWN,
        token_digest=SHA_B,
    )
    separate = reconcile_identity_lineage(_request((first, second)))
    same_as = SameAsAssertion(
        assertion_id="same.specimen",
        left_entity_id="specimen.a",
        right_entity_id="specimen.b",
        authority_decision_id=AUTHORITY_ID,
        policy_version=POLICY_VERSION,
        evidence=(_artifact("same.specimen.evidence"),),
    )
    united = reconcile_identity_lineage(_request((first, second), assertions=(same_as,)))

    assert separate.decision is ResolutionDecision.QUARANTINED
    assert "identity.token_reuse" in {issue.code for issue in separate.issues}
    assert united.decision is ResolutionDecision.RESOLVED
    assert len(united.components) == 1


def test_token_digest_in_different_scope_never_implicitly_merges_or_collides() -> None:
    entities = (
        _entity(
            "specimen.a",
            EntityKind.SPECIMEN,
            EntityComposition.UNKNOWN,
            token_digest=SHA_B,
            scope_id="project.a",
        ),
        _entity(
            "specimen.b",
            EntityKind.SPECIMEN,
            EntityComposition.UNKNOWN,
            token_digest=SHA_B,
            scope_id="project.b",
        ),
    )

    draft = reconcile_identity_lineage(_request(entities))

    assert draft.decision is ResolutionDecision.RESOLVED
    assert len(draft.components) == TWO


def test_pool_uses_subjects_inherited_through_ordinary_lineage() -> None:
    entities = (
        _entity("patient.a", EntityKind.PATIENT, EntityComposition.SINGLE_SUBJECT),
        _entity("patient.b", EntityKind.PATIENT, EntityComposition.SINGLE_SUBJECT),
        _entity("specimen.a", EntityKind.SPECIMEN, EntityComposition.SINGLE_SUBJECT),
        _entity("specimen.b", EntityKind.SPECIMEN, EntityComposition.SINGLE_SUBJECT),
        _entity("aliquot.a", EntityKind.ALIQUOT, EntityComposition.SINGLE_SUBJECT),
        _entity("aliquot.b", EntityKind.ALIQUOT, EntityComposition.SINGLE_SUBJECT),
        _entity("aliquot.pool", EntityKind.ALIQUOT, EntityComposition.MULTI_SUBJECT),
    )
    operations = (
        _operation(
            "collect.a", LineageOperationKind.COLLECTED_FROM, ("patient.a",), ("specimen.a",)
        ),
        _operation(
            "collect.b", LineageOperationKind.COLLECTED_FROM, ("patient.b",), ("specimen.b",)
        ),
        _operation(
            "divide.a", LineageOperationKind.SUBDIVIDED_FROM, ("specimen.a",), ("aliquot.a",)
        ),
        _operation(
            "divide.b", LineageOperationKind.SUBDIVIDED_FROM, ("specimen.b",), ("aliquot.b",)
        ),
        _operation(
            "pool.ab",
            LineageOperationKind.POOLED_FROM,
            ("aliquot.a", "aliquot.b"),
            ("aliquot.pool",),
            mixed=True,
        ),
    )

    draft = reconcile_identity_lineage(_request(entities, operations=operations))

    assert draft.decision is ResolutionDecision.RESOLVED
    pool = next(
        component for component in draft.components if "aliquot.pool" in component.member_entity_ids
    )
    assert pool.composition is EntityComposition.MULTI_SUBJECT
    assert len(pool.subject_component_ids) == TWO


def test_pool_identity_propagates_through_multiple_ordinary_descendants() -> None:
    entities = (
        _entity("patient.a", EntityKind.PATIENT, EntityComposition.SINGLE_SUBJECT),
        _entity("patient.b", EntityKind.PATIENT, EntityComposition.SINGLE_SUBJECT),
        _entity("aliquot.a", EntityKind.ALIQUOT, EntityComposition.SINGLE_SUBJECT),
        _entity("aliquot.b", EntityKind.ALIQUOT, EntityComposition.SINGLE_SUBJECT),
        _entity("aliquot.pool", EntityKind.ALIQUOT, EntityComposition.MULTI_SUBJECT),
        _entity("aliquot.child", EntityKind.ALIQUOT, EntityComposition.MULTI_SUBJECT),
        _entity("analyte.child", EntityKind.ANALYTE, EntityComposition.MULTI_SUBJECT),
    )
    assertions = (
        _membership("membership.a", "aliquot.a", "patient.a"),
        _membership("membership.b", "aliquot.b", "patient.b"),
    )
    operations = (
        _operation(
            "z.pool",
            LineageOperationKind.POOLED_FROM,
            ("aliquot.a", "aliquot.b"),
            ("aliquot.pool",),
            mixed=True,
        ),
        _operation(
            "a.subdivide",
            LineageOperationKind.SUBDIVIDED_FROM,
            ("aliquot.pool",),
            ("aliquot.child",),
        ),
        _operation(
            "b.extract",
            LineageOperationKind.EXTRACTED_FROM,
            ("aliquot.child",),
            ("analyte.child",),
        ),
    )
    request = _request(entities, assertions=assertions, operations=operations)

    draft = reconcile_identity_lineage(request)
    bindings = {
        node.entity_id: node.subject_component_ids for node in draft.graph.nodes
    }

    assert draft.decision is ResolutionDecision.RESOLVED
    assert len(bindings["aliquot.pool"]) == TWO
    assert bindings["aliquot.child"] == bindings["aliquot.pool"]
    assert bindings["analyte.child"] == bindings["aliquot.pool"]


def test_pool_identity_reaches_demultiplex_targets_without_inferred_separation() -> None:
    entities = (
        _entity("patient.a", EntityKind.PATIENT, EntityComposition.SINGLE_SUBJECT),
        _entity("patient.b", EntityKind.PATIENT, EntityComposition.SINGLE_SUBJECT),
        _entity("analyte.a", EntityKind.ANALYTE, EntityComposition.SINGLE_SUBJECT),
        _entity("analyte.b", EntityKind.ANALYTE, EntityComposition.SINGLE_SUBJECT),
        _entity("analyte.pool", EntityKind.ANALYTE, EntityComposition.MULTI_SUBJECT),
        _entity("analyte.channel.a", EntityKind.ANALYTE, EntityComposition.MULTI_SUBJECT),
        _entity("analyte.channel.b", EntityKind.ANALYTE, EntityComposition.MULTI_SUBJECT),
    )
    assertions = (
        _membership("membership.a", "analyte.a", "patient.a"),
        _membership("membership.b", "analyte.b", "patient.b"),
    )
    channels = tuple(
        DemultiplexChannel(
            channel_id=f"channel.{suffix}",
            source_entity_id="analyte.pool",
            target_entity_id=f"analyte.channel.{suffix}",
            tag_digest=digest,
            evidence=(_artifact(f"channel.{suffix}.evidence"),),
        )
        for suffix, digest in (("a", SHA_B), ("b", SHA_C))
    )
    operations = (
        _operation(
            "z.pool",
            LineageOperationKind.POOLED_FROM,
            ("analyte.a", "analyte.b"),
            ("analyte.pool",),
            mixed=True,
        ),
        _operation(
            "a.demultiplex",
            LineageOperationKind.DEMULTIPLEXED_FROM,
            ("analyte.pool",),
            ("analyte.channel.a", "analyte.channel.b"),
            channels=channels,
        ),
    )
    request = _request(entities, assertions=assertions, operations=operations)

    draft = reconcile_identity_lineage(request)
    bindings = {
        node.entity_id: node.subject_component_ids for node in draft.graph.nodes
    }

    assert draft.decision is ResolutionDecision.RESOLVED
    assert len(bindings["analyte.pool"]) == TWO
    assert bindings["analyte.channel.a"] == bindings["analyte.pool"]
    assert bindings["analyte.channel.b"] == bindings["analyte.pool"]


def test_pool_hyperedge_propagation_is_order_invariant() -> None:
    entities = (
        _entity("patient.a", EntityKind.PATIENT, EntityComposition.SINGLE_SUBJECT),
        _entity("patient.b", EntityKind.PATIENT, EntityComposition.SINGLE_SUBJECT),
        _entity("aliquot.a", EntityKind.ALIQUOT, EntityComposition.SINGLE_SUBJECT),
        _entity("aliquot.b", EntityKind.ALIQUOT, EntityComposition.SINGLE_SUBJECT),
        _entity("aliquot.pool", EntityKind.ALIQUOT, EntityComposition.MULTI_SUBJECT),
        _entity("aliquot.child", EntityKind.ALIQUOT, EntityComposition.MULTI_SUBJECT),
    )
    assertions = (
        _membership("membership.a", "aliquot.a", "patient.a"),
        _membership("membership.b", "aliquot.b", "patient.b"),
    )
    operations = (
        _operation(
            "pool.ab",
            LineageOperationKind.POOLED_FROM,
            ("aliquot.a", "aliquot.b"),
            ("aliquot.pool",),
            mixed=True,
        ),
        _operation(
            "subdivide.pool",
            LineageOperationKind.SUBDIVIDED_FROM,
            ("aliquot.pool",),
            ("aliquot.child",),
        ),
    )
    forward = _request(entities, assertions=assertions, operations=operations)
    reversed_pool = operations[0].model_copy(
        update={"source_entity_ids": tuple(reversed(operations[0].source_entity_ids))}
    )
    reverse = forward.model_copy(
        update={
            "entities": tuple(reversed(forward.entities)),
            "assertions": tuple(reversed(forward.assertions)),
            "lineage_operations": (
                operations[1],
                reversed_pool,
            ),
        }
    )

    left = reconcile_identity_lineage(forward)
    right = reconcile_identity_lineage(reverse)

    assert left == right
    assert left.core_digest == right.core_digest


def test_pool_with_unknown_source_never_infers_known_subject() -> None:
    entities = (
        _entity("patient.a", EntityKind.PATIENT, EntityComposition.SINGLE_SUBJECT),
        _entity("aliquot.a", EntityKind.ALIQUOT, EntityComposition.SINGLE_SUBJECT),
        _entity("aliquot.unknown", EntityKind.ALIQUOT, EntityComposition.UNKNOWN),
        _entity("aliquot.pool", EntityKind.ALIQUOT, EntityComposition.UNKNOWN),
        _entity("aliquot.descendant", EntityKind.ALIQUOT, EntityComposition.UNKNOWN),
    )
    request = _request(
        entities,
        assertions=(_membership("membership.a", "aliquot.a", "patient.a"),),
        operations=(
            _operation(
                "pool.partial",
                LineageOperationKind.POOLED_FROM,
                ("aliquot.a", "aliquot.unknown"),
                ("aliquot.pool",),
            ),
            _operation(
                "subdivide.partial",
                LineageOperationKind.SUBDIVIDED_FROM,
                ("aliquot.pool",),
                ("aliquot.descendant",),
            ),
        ),
    )

    draft = reconcile_identity_lineage(request)
    pool = next(
        component for component in draft.components if "aliquot.pool" in component.member_entity_ids
    )

    assert draft.decision is ResolutionDecision.QUARANTINED
    assert pool.composition is EntityComposition.UNKNOWN
    assert pool.subject_component_ids == ()
    descendant = next(
        component
        for component in draft.components
        if "aliquot.descendant" in component.member_entity_ids
    )
    assert descendant.composition is EntityComposition.UNKNOWN
    assert descendant.subject_component_ids == ()
    assert "pool.source_identity_unresolved" in {issue.code for issue in draft.issues}


def _observation(  # noqa: PLR0913 - compact typed test-fixture constructor
    observation_id: str,
    classification: ConcordanceClassification,
    *,
    concordant: int,
    discordant: int,
    left: str = "specimen.a",
    right: str = "specimen.b",
    method_id: str = "method.synthetic",
) -> ConcordanceObservation:
    return ConcordanceObservation(
        observation_id=observation_id,
        root_observation_id="root.synthetic",
        left_entity_id=left,
        right_entity_id=right,
        target_id="specimen.a",
        classification=classification,
        informative_count=concordant + discordant,
        concordant_count=concordant,
        discordant_count=discordant,
        method_id=method_id,
        method_version="1.0.0",
        assay_lineage_digest=SHA_C,
        panel_digest=SHA_C,
        reference_digest=SHA_D,
        evidence_policy_version="1.0.0",
        evidence=(_artifact("concordance.evidence", SHA_D),),
    )


def test_related_concordance_is_deduplicated_and_never_merges() -> None:
    entities = (
        _entity("specimen.a", EntityKind.SPECIMEN, EntityComposition.UNKNOWN),
        _entity("specimen.b", EntityKind.SPECIMEN, EntityComposition.UNKNOWN),
    )
    observations = (
        _observation(
            "observation.a", ConcordanceClassification.CONCORDANT, concordant=8, discordant=0
        ),
        _observation(
            "observation.copy", ConcordanceClassification.CONCORDANT, concordant=8, discordant=0
        ),
    )

    draft = reconcile_identity_lineage(_request(entities, observations=observations))

    assert len(draft.components) == TWO
    assert draft.concordance.concordant == 1
    assert draft.concordance.informative_loci == INFORMATIVE_LOCI


def test_evidence_artifact_alias_cannot_inflate_concordance() -> None:
    entities = (
        _entity("specimen.a", EntityKind.SPECIMEN, EntityComposition.UNKNOWN),
        _entity("specimen.b", EntityKind.SPECIMEN, EntityComposition.UNKNOWN),
    )
    first = _observation(
        "observation.a", ConcordanceClassification.CONCORDANT, concordant=8, discordant=0
    )
    alias = first.model_copy(
        update={
            "observation_id": "observation.alias",
            "evidence": (_artifact("concordance.alias", SHA_D),),
        }
    )

    draft = reconcile_identity_lineage(_request(entities, observations=(first, alias)))

    assert draft.concordance.concordant == 1
    assert draft.concordance.informative_loci == INFORMATIVE_LOCI


def test_conflicting_copies_become_indeterminate_without_score_inflation() -> None:
    entities = (
        _entity("specimen.a", EntityKind.SPECIMEN, EntityComposition.UNKNOWN),
        _entity("specimen.b", EntityKind.SPECIMEN, EntityComposition.UNKNOWN),
    )
    observations = (
        _observation(
            "observation.a", ConcordanceClassification.CONCORDANT, concordant=8, discordant=0
        ),
        _observation(
            "observation.copy", ConcordanceClassification.DISCORDANT, concordant=0, discordant=8
        ),
    )

    draft = reconcile_identity_lineage(_request(entities, observations=observations))

    assert draft.decision is ResolutionDecision.UNRESOLVED
    assert draft.concordance.indeterminate == 1
    assert draft.concordance.informative_loci == 0


def test_distinct_endpoint_and_method_observations_never_collapse() -> None:
    entities = (
        _entity("specimen.a", EntityKind.SPECIMEN, EntityComposition.UNKNOWN),
        _entity("specimen.b", EntityKind.SPECIMEN, EntityComposition.UNKNOWN),
        _entity("specimen.c", EntityKind.SPECIMEN, EntityComposition.UNKNOWN),
    )
    observations = (
        _observation(
            "observation.a-b",
            ConcordanceClassification.CONCORDANT,
            concordant=8,
            discordant=0,
            right="specimen.b",
            method_id="method.a",
        ),
        _observation(
            "observation.a-c",
            ConcordanceClassification.DISCORDANT,
            concordant=0,
            discordant=8,
            right="specimen.c",
            method_id="method.b",
        ),
    )

    draft = reconcile_identity_lineage(_request(entities, observations=observations))

    assert draft.concordance.concordant == 1
    assert draft.concordance.discordant == 1
    assert draft.concordance.indeterminate == 0
    assert draft.concordance.informative_loci == INFORMATIVE_LOCI * TWO


def test_concordance_endpoint_orientation_is_semantically_symmetric() -> None:
    entities = (
        _entity("specimen.a", EntityKind.SPECIMEN, EntityComposition.UNKNOWN),
        _entity("specimen.b", EntityKind.SPECIMEN, EntityComposition.UNKNOWN),
    )
    first = _observation(
        "observation.a-b", ConcordanceClassification.CONCORDANT, concordant=8, discordant=0
    )
    reversed_copy = first.model_copy(
        update={
            "observation_id": "observation.b-a",
            "left_entity_id": first.right_entity_id,
            "right_entity_id": first.left_entity_id,
        }
    )

    draft = reconcile_identity_lineage(
        _request(entities, observations=(first, reversed_copy))
    )

    assert draft.concordance.concordant == 1
    assert draft.concordance.informative_loci == INFORMATIVE_LOCI


def test_conflicting_concordance_order_preserves_exact_issue_identity() -> None:
    entities = (
        _entity("specimen.a", EntityKind.SPECIMEN, EntityComposition.UNKNOWN),
        _entity("specimen.b", EntityKind.SPECIMEN, EntityComposition.UNKNOWN),
    )
    observations = (
        _observation(
            "observation.concordant",
            ConcordanceClassification.CONCORDANT,
            concordant=8,
            discordant=0,
        ),
        _observation(
            "observation.discordant",
            ConcordanceClassification.DISCORDANT,
            concordant=0,
            discordant=8,
        ),
    )
    first = _request(entities, observations=observations)
    second = first.model_copy(update={"concordance_observations": tuple(reversed(observations))})

    left = reconcile_identity_lineage(first)
    right = reconcile_identity_lineage(second)

    assert left == right
    assert left.core_digest == right.core_digest
    assert {issue.code for issue in left.issues} == {"concordance.indeterminate"}


def test_logical_duplicate_operation_is_not_replayed_in_graph() -> None:
    entities = (
        _entity("patient.a", EntityKind.PATIENT, EntityComposition.SINGLE_SUBJECT),
        _entity("specimen.a", EntityKind.SPECIMEN, EntityComposition.SINGLE_SUBJECT),
    )
    operations = (
        _operation(
            "collect.a", LineageOperationKind.COLLECTED_FROM, ("patient.a",), ("specimen.a",)
        ),
        _operation(
            "collect.copy", LineageOperationKind.COLLECTED_FROM, ("patient.a",), ("specimen.a",)
        ),
    )

    draft = reconcile_identity_lineage(_request(entities, operations=operations))

    assert draft.decision is ResolutionDecision.UNRESOLVED
    assert len(draft.graph.operations) == 1
    assert "lineage.duplicate_operation" in {issue.code for issue in draft.issues}


def test_order_permutation_preserves_exact_core_identity() -> None:
    entities = (
        _entity("patient.a", EntityKind.PATIENT, EntityComposition.SINGLE_SUBJECT),
        _entity("specimen.a", EntityKind.SPECIMEN, EntityComposition.SINGLE_SUBJECT),
    )
    membership = _membership("membership.a", "specimen.a", "patient.a")
    operation = _operation(
        "collection.a",
        LineageOperationKind.COLLECTED_FROM,
        ("patient.a",),
        ("specimen.a",),
    )
    first = _request(entities, assertions=(membership,), operations=(operation,))
    second = first.model_copy(update={"entities": tuple(reversed(first.entities))})

    left = reconcile_identity_lineage(first)
    right = reconcile_identity_lineage(second)

    assert left == right
    assert left.core_digest == right.core_digest


def test_public_draft_never_contains_token_or_demultiplex_tag_digests() -> None:
    tag_digest = "sha256:" + "1" * 64
    token_digest = "sha256:" + "2" * 64
    entities = (
        _entity(
            "aliquot.pool",
            EntityKind.ALIQUOT,
            EntityComposition.UNKNOWN,
            token_digest=token_digest,
        ),
        _entity("aliquot.a", EntityKind.ALIQUOT, EntityComposition.UNKNOWN),
        _entity("aliquot.b", EntityKind.ALIQUOT, EntityComposition.UNKNOWN),
    )
    channels = tuple(
        DemultiplexChannel(
            channel_id=f"channel.{suffix}",
            source_entity_id="aliquot.pool",
            target_entity_id=f"aliquot.{suffix}",
            tag_digest=tag,
            evidence=(_artifact(f"channel.{suffix}.evidence"),),
        )
        for suffix, tag in (("a", tag_digest), ("b", SHA_B))
    )
    operation = _operation(
        "demux.ab",
        LineageOperationKind.DEMULTIPLEXED_FROM,
        ("aliquot.pool",),
        ("aliquot.a", "aliquot.b"),
        channels=channels,
    )

    encoded = reconcile_identity_lineage(
        _request(entities, operations=(operation,))
    ).model_dump_json()

    assert token_digest not in encoded
    assert tag_digest not in encoded
    assert "identity_tokens" not in encoded
    assert "channels" not in encoded


def test_invalid_authority_policy_is_detected_before_any_union() -> None:
    entities = (
        _entity("specimen.a", EntityKind.SPECIMEN, EntityComposition.UNKNOWN),
        _entity("specimen.b", EntityKind.SPECIMEN, EntityComposition.UNKNOWN),
    )
    same_as = SameAsAssertion(
        assertion_id="same.specimen",
        left_entity_id="specimen.a",
        right_entity_id="specimen.b",
        authority_decision_id=AUTHORITY_ID,
        policy_version=POLICY_VERSION,
        evidence=(_artifact("same.specimen.evidence"),),
    )
    request = _request(entities, assertions=(same_as,))
    invalid_authority = request.context.references.identity_authority.model_copy(
        update={"policy_version": "2.0.0"}
    )
    invalid_references = request.context.references.model_copy(
        update={"identity_authority": invalid_authority}
    )
    invalid = request.model_copy(
        update={"context": request.context.model_copy(update={"references": invalid_references})}
    )

    analysis = _analyze(invalid)

    assert len(analysis.components) == TWO
    assert "assertion.unauthorized_or_policy_mismatch" in {issue.code for issue in analysis.issues}
