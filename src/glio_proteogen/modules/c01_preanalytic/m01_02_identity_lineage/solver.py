"""Pure deterministic reconciliation core for M01-02.

Identity is asserted, never guessed.  The solver uses explicit ``same_as`` assertions for
candidate components and treats every biological/evidentiary conflict as a reason to retain
separation and require review.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from glio_proteogen.contracts.m01_02.canonical import (
    canonical_request_digest,
    normalized_request,
    policy_digest,
)
from glio_proteogen.contracts.m01_02.v1 import (
    AssertionDisposition,
    AssertionDispositionState,
    ConcordanceAggregate,
    EntityComposition,
    EntityKind,
    IdentityComponent,
    IdentityControlRole,
    IdentityIssue,
    IdentityIssueAction,
    IdentityIssueSeverity,
    IdentityLineageResolutionDraft,
    LineageOperation,
    LineageOperationKind,
    ResolutionDecision,
    ResolvedIdentityNode,
    ResolvedLineageGraph,
    ResolvedLineageOperation,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, ConsentState, UpstreamDecisionState
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.policy import (
    DEMULTIPLEXABLE_KINDS,
    ENTITY_KINDS,
    MAX_ABSOLUTE_DEPTH,
    POOLABLE_KINDS,
    ordinary_transition_allowed,
)

PAIR_SIZE = 2
MINIMUM_POOL_SIZE = 2
MINIMUM_DEMULTIPLEX_SIZE = 2

if TYPE_CHECKING:
    from glio_proteogen.contracts.m01_02.v1 import (
        ReconcileIdentityLineageRequest,
    )


@dataclass(frozen=True, slots=True, order=True)
class SolverIssue:
    """Internal, privacy-safe issue material awaiting public-contract construction."""

    code: str
    subject: str
    detail: str


@dataclass(frozen=True, slots=True)
class ComponentAnalysis:
    component_id: str
    members: tuple[str, ...]
    kind: str
    subject_anchors: tuple[str, ...]
    composition: str
    quarantined: bool


@dataclass(frozen=True, slots=True, order=True)
class ResolvedOperationAnalysis:
    """Privacy-minimized operation material; channels and authority data never cross output."""

    operation_id: str
    kind: str
    source_entity_ids: tuple[str, ...]
    target_entity_ids: tuple[str, ...]
    mixed_subject: bool


@dataclass(frozen=True, slots=True)
class ConcordanceCounts:
    concordant_observations: int = 0
    discordant_observations: int = 0
    indeterminate_observations: int = 0
    unsupported_observations: int = 0
    missing_observations: int = 0
    excluded_dependent_observations: int = 0
    informative_count: int = 0
    concordant_count: int = 0
    discordant_count: int = 0


@dataclass(frozen=True, slots=True)
class SolverAnalysis:
    components: tuple[ComponentAnalysis, ...]
    lineage_edges: tuple[tuple[str, str, str], ...]
    resolved_operations: tuple[ResolvedOperationAnalysis, ...]
    subject_bindings: tuple[tuple[str, tuple[str, ...]], ...]
    concordance: ConcordanceCounts
    issues: tuple[SolverIssue, ...]


class ReconciliationAuthorizationError(PermissionError):
    """A required upstream control denied direct solver execution."""

    def __init__(self, role: IdentityControlRole) -> None:
        self.role = role
        super().__init__(f"upstream {role.value} decision does not authorize reconciliation")


@dataclass(frozen=True, slots=True)
class _Authorization:
    authority_id: str
    authority_policy_version: str
    active_policy_version: str
    controls_accepted: bool


@dataclass(frozen=True, slots=True)
class _SubjectContext:
    initial_bindings: Mapping[str, frozenset[str]]
    patient_members_by_root: Mapping[str, tuple[str, ...]]


class _DisjointSet:
    """Deterministic union-find; representatives remain strictly internal."""

    def __init__(self, members: Iterable[str]) -> None:
        ordered = sorted(members)
        self._parent = {member: member for member in ordered}
        self._size = dict.fromkeys(ordered, 1)

    def find(self, member: str) -> str:
        root = member
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[member] != member:
            parent = self._parent[member]
            self._parent[member] = root
            member = parent
        return root

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        left_size = self._size[left_root]
        right_size = self._size[right_root]
        if left_size < right_size or (left_size == right_size and right_root < left_root):
            left_root, right_root = right_root, left_root
        self._parent[right_root] = left_root
        self._size[left_root] += self._size[right_root]


def _mapping(value: object) -> Mapping[str, object]:
    if type(value) is dict and all(isinstance(key, str) for key in value):
        return cast("Mapping[str, object]", value)
    if isinstance(value, BaseModel):
        return cast("Mapping[str, object]", value.model_dump(mode="python"))
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return cast("Mapping[str, object]", value)
    raise TypeError


def _sequence(value: object, field: str) -> Sequence[object]:
    if type(value) in {list, tuple}:
        return cast("Sequence[object]", value)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(field)
    return value


def _text(value: object, field: str) -> str:
    if type(value) is str:
        return value
    if isinstance(value, Enum):
        value = value.value
    if not isinstance(value, str):
        raise TypeError(field)
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _text(value, "optional text")


def _bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise TypeError(field)
    return value


def _integer(value: object, field: str) -> int:
    if type(value) is not int:
        raise TypeError(field)
    return value


def _ids(record: Mapping[str, object]) -> tuple[str, ...]:
    raw = record.get("entity_ids")
    if raw is not None:
        return tuple(_text(item, "entity_ids item") for item in _sequence(raw, "entity_ids"))
    left = record.get("left_entity_id")
    right = record.get("right_entity_id")
    if left is not None and right is not None:
        return (_text(left, "left_entity_id"), _text(right, "right_entity_id"))
    entity = record.get("entity_id")
    subject = record.get("subject_entity_id") or record.get("patient_entity_id")
    if entity is not None and subject is not None:
        return (_text(entity, "entity_id"), _text(subject, "subject_entity_id"))
    return ()


def _authority_accepted(
    record: Mapping[str, object],
    authorization: _Authorization,
) -> bool:
    decision = _optional_text(record.get("authority_decision_id"))
    declared_policy = _optional_text(record.get("policy_version"))
    return (
        decision == authorization.authority_id
        and declared_policy == authorization.active_policy_version
        and authorization.authority_policy_version == authorization.active_policy_version
        and authorization.controls_accepted
    )


def _component_digest(
    members: tuple[str, ...],
    policy_identity: str,
) -> str:
    return _component_digest_with_tail(
        members,
        _component_digest_tail(policy_identity),
    )


def _component_digest_tail(policy_identity: str) -> bytes:
    encoded_policy = json.dumps(
        policy_identity,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode()
    return (
        b',"policy_identity":'
        + encoded_policy
        + b',"purpose":"GLIO-PROTEOGEN-M01-02.identity-component.v1"}'
    )


def _component_digest_with_tail(members: tuple[str, ...], tail: bytes) -> str:
    encoded_members = json.dumps(
        members,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode()
    payload = b'{"members":' + encoded_members + tail
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _policy_identity(policy: Mapping[str, object]) -> str:
    policy_id = _text(policy.get("policy_id"), "policy_id")
    version = _text(policy.get("version"), "policy version")
    return f"{policy_id}@{version}"


def _controls_are_accepted(references: Mapping[str, object]) -> bool:
    generic_roles = (
        "approved_configuration",
        "provenance",
        "quality",
        "support",
        "intended_use",
    )
    generic_accepted = all(
        _text(_mapping(references[role]).get("state"), f"{role} state") == "accepted"
        for role in generic_roles
    )
    consent_granted = (
        _text(_mapping(references["consent"]).get("state"), "consent state") == "granted"
    )
    authority_accepted = (
        _text(
            _mapping(references["identity_authority"]).get("state"),
            "identity authority state",
        )
        == "accepted"
    )
    return generic_accepted and consent_granted and authority_accepted


def _require_authorized_request(request: ReconcileIdentityLineageRequest) -> None:
    """Check only control state before analysis, hashing, or private-material access."""

    references = request.context.references
    if references.consent.state is not ConsentState.GRANTED:
        raise ReconciliationAuthorizationError(IdentityControlRole.CONSENT)
    if references.identity_authority.state is not UpstreamDecisionState.ACCEPTED:
        raise ReconciliationAuthorizationError(IdentityControlRole.IDENTITY_AUTHORITY)
    generic = (
        (IdentityControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (IdentityControlRole.PROVENANCE, references.provenance),
        (IdentityControlRole.QUALITY, references.quality),
        (IdentityControlRole.SUPPORT, references.support),
        (IdentityControlRole.INTENDED_USE, references.intended_use),
    )
    for role, reference in generic:
        if reference.state is not UpstreamDecisionState.ACCEPTED:
            raise ReconciliationAuthorizationError(role)


def _token_keys(entity: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    keys: list[tuple[str, str]] = []
    for item in _sequence(entity.get("identity_tokens", ()), "identity_tokens"):
        token = _mapping(item)
        scope = "|".join(
            _text(token.get(field), field)
            for field in (
                "issuer_id",
                "namespace_id",
                "scope_id",
                "key_id",
                "token_version",
                "entity_kind",
            )
        )
        token_digest = _text(token.get("token_digest"), "token_digest")
        keys.append((scope, token_digest))
    return tuple(keys)


def _record_evidence_digests(record: Mapping[str, object]) -> tuple[str, ...]:
    evidence = record.get("evidence", ())
    return tuple(
        sorted(
            {
                _text(_mapping(item).get("digest"), "evidence digest")
                for item in _sequence(evidence, "evidence")
            }
        )
    )


def _analyze_components(  # noqa: C901, PLR0912, PLR0915
    entities: Mapping[str, Mapping[str, object]],
    assertions: Sequence[object],
    authorization: _Authorization,
    policy_identity: str,
    component_cap: int,
) -> tuple[
    _DisjointSet,
    tuple[ComponentAnalysis, ...],
    tuple[SolverIssue, ...],
    Mapping[str, frozenset[str]],
    Mapping[str, tuple[str, ...]],
]:
    dsu = _DisjointSet(entities)
    entity_kinds = {
        entity_id: _text(entity.get("kind"), "entity kind")
        for entity_id, entity in entities.items()
    }
    issues: list[SolverIssue] = []
    different_pairs: list[tuple[str, str, str]] = []
    memberships: list[tuple[str, str, str]] = []

    prepared: list[tuple[str, Mapping[str, object]]] = []
    for item in assertions:
        assertion = _mapping(item)
        assertion_id = _text(assertion.get("assertion_id"), "assertion_id")
        prepared.append((assertion_id, assertion))

    for assertion_id, assertion in sorted(prepared):
        assertion_type = _text(assertion.get("assertion_type"), "assertion_type")
        members = _ids(assertion)
        unknown = sorted({member for member in members if member not in entities})
        if unknown:
            issues.append(SolverIssue("assertion.unknown_entity", assertion_id, ",".join(unknown)))
            continue
        if not _authority_accepted(
            assertion,
            authorization,
        ):
            issues.append(
                SolverIssue(
                    "assertion.unauthorized_or_policy_mismatch",
                    assertion_id,
                    "authority or policy mismatch",
                )
            )
            continue
        if assertion_type == "same_as":
            if len(members) != PAIR_SIZE or members[0] == members[1]:
                issues.append(
                    SolverIssue("same_as.invalid_cardinality", assertion_id, "pair required")
                )
                continue
            dsu.union(*members)
        elif assertion_type == "different_from":
            if len(members) != PAIR_SIZE or members[0] == members[1]:
                issues.append(
                    SolverIssue("different_from.invalid_cardinality", assertion_id, "pair required")
                )
                continue
            different_pairs.append((members[0], members[1], assertion_id))
        elif assertion_type == "subject_membership":
            if len(members) != PAIR_SIZE:
                issues.append(
                    SolverIssue(
                        "subject_membership.invalid_cardinality", assertion_id, "pair required"
                    )
                )
                continue
            memberships.append((members[0], members[1], assertion_id))

    grouped: dict[str, list[str]] = defaultdict(list)
    for entity_id in sorted(entities):
        grouped[dsu.find(entity_id)].append(entity_id)

    poisoned: set[str] = set()
    for root, component_members in grouped.items():
        kinds = {entity_kinds[member] for member in component_members}
        if len(kinds) != 1:
            poisoned.add(root)
            issues.append(
                SolverIssue(
                    "component.cross_kind",
                    min(component_members),
                    ",".join(sorted(kinds)),
                )
            )
        if len(component_members) > component_cap:
            poisoned.add(root)
            issues.append(
                SolverIssue(
                    "component.capacity_exceeded",
                    min(component_members),
                    str(len(component_members)),
                )
            )

    for left, right, assertion_id in different_pairs:
        if dsu.find(left) == dsu.find(right):
            poisoned.add(dsu.find(left))
            issues.append(
                SolverIssue("component.different_from_conflict", assertion_id, "same component")
            )

    patient_members_by_root: dict[str, tuple[str, ...]] = {}
    for root, group_members in grouped.items():
        patient_members = tuple(
            member for member in group_members if entity_kinds[member] == "patient"
        )
        if patient_members:
            patient_members_by_root[root] = patient_members
    anchors_by_root: dict[str, set[str]] = defaultdict(set)
    for entity_id, subject_id, assertion_id in memberships:
        if entity_kinds[subject_id] != "patient":
            poisoned.add(dsu.find(entity_id))
            issues.append(
                SolverIssue("membership.non_patient_anchor", assertion_id, subject_id)
            )
            continue
        anchors_by_root[dsu.find(entity_id)].add(dsu.find(subject_id))
    for entity_id in entities:
        if entity_kinds[entity_id] == "patient":
            anchors_by_root[dsu.find(entity_id)].add(dsu.find(entity_id))
    for root, anchors in anchors_by_root.items():
        if len(anchors) > 1:
            poisoned.add(root)
            issues.append(
                SolverIssue(
                    "component.multiple_subject_anchors",
                    min(grouped[root]),
                    "component has distinct subject components",
                )
            )

    tokens: dict[tuple[str, str], list[str]] = defaultdict(list)
    for entity_id, entity in entities.items():
        entity_kind = entity_kinds[entity_id]
        for token_record in _sequence(entity.get("identity_tokens", ()), "identity_tokens"):
            token = _mapping(token_record)
            if _text(token.get("entity_kind"), "token entity_kind") != entity_kind:
                root = dsu.find(entity_id)
                poisoned.add(root)
                issues.append(
                    SolverIssue(
                        "identity.token_kind_mismatch",
                        entity_id,
                        "token kind differs from entity kind",
                    )
                )
        for token_key in _token_keys(entity):
            tokens[token_key].append(entity_id)
    for entity_ids in tokens.values():
        if len(entity_ids) <= 1:
            continue
        roots = {dsu.find(entity_id) for entity_id in entity_ids}
        if len(roots) == 1:
            continue
        poisoned.update(roots)
        issues.append(
            SolverIssue("identity.token_reuse", min(entity_ids), ",".join(sorted(entity_ids)))
        )

    components: list[ComponentAnalysis] = []
    bindings: dict[str, frozenset[str]] = {}
    component_digest_tail = _component_digest_tail(policy_identity)
    for root, unordered in grouped.items():
        component_tuple = tuple(unordered)
        component_kinds = sorted({entity_kinds[member] for member in component_tuple})
        anchor_roots = anchors_by_root.get(root, set())
        subject_aliases = tuple(
            sorted(
                member
                for anchor_root in anchor_roots
                for member in patient_members_by_root[anchor_root]
            )
        )
        component_id = _component_digest_with_tail(component_tuple, component_digest_tail)
        components.append(
            ComponentAnalysis(
                component_id=component_id,
                members=component_tuple,
                kind=(
                    component_kinds[0]
                    if len(component_kinds) == 1
                    else "conflicted"
                ),
                subject_anchors=subject_aliases,
                composition=(
                    "unknown"
                    if not anchor_roots
                    else "single_subject"
                    if len(anchor_roots) == 1
                    else "multi_subject"
                ),
                quarantined=root in poisoned,
            )
        )
        frozen_anchor_roots = frozenset(anchor_roots)
        for member in component_tuple:
            bindings[member] = frozen_anchor_roots
    return (
        dsu,
        tuple(sorted(components, key=lambda item: item.component_id)),
        tuple(issues),
        bindings,
        patient_members_by_root,
    )


def _channels(operation: Mapping[str, object]) -> tuple[tuple[str, str, str, str], ...]:
    raw = operation.get("channels", ())
    result: list[tuple[str, str, str, str]] = []
    for item in _sequence(raw, "channels"):
        channel = _mapping(item)
        source = _text(channel.get("source_entity_id"), "channel source_entity_id")
        target = _text(channel.get("target_entity_id"), "channel target_entity_id")
        channel_id = _text(channel.get("channel_id"), "channel_id")
        tag_digest = _text(channel.get("tag_digest"), "tag_digest")
        result.append((source, target, channel_id, tag_digest))
    return tuple(result)


def _analyze_lineage(  # noqa: C901, PLR0912, PLR0915
    entities: Mapping[str, Mapping[str, object]],
    operations: Sequence[object],
    authorization: _Authorization,
    policy: Mapping[str, object],
    subject_context: _SubjectContext,
) -> tuple[
    tuple[tuple[str, str, str], ...],
    tuple[ResolvedOperationAnalysis, ...],
    tuple[tuple[str, tuple[str, ...]], ...],
    tuple[SolverIssue, ...],
]:
    allow_pooling = _bool(
        policy.get("allow_mixed_subject_pooling", False), "allow_mixed_subject_pooling"
    )
    require_demultiplex_authority = _bool(
        policy.get("require_demultiplex_authority", True), "require_demultiplex_authority"
    )
    depth_cap = min(
        _integer(policy.get("maximum_depth", MAX_ABSOLUTE_DEPTH), "maximum_depth"),
        MAX_ABSOLUTE_DEPTH,
    )
    issues: list[SolverIssue] = []
    edges: list[tuple[str, str, str]] = []
    resolved_operations: list[ResolvedOperationAnalysis] = []
    valid_pools: dict[str, tuple[tuple[str, ...], tuple[str, ...], bool]] = {}
    demultiplex_operation_by_target: dict[str, str] = {}
    operation_signatures: set[tuple[str, tuple[str, ...], tuple[str, ...]]] = set()
    allowed_operation_kinds = {
        _text(item, "allowed operation kind")
        for item in _sequence(policy.get("allowed_operation_kinds", ()), "allowed_operation_kinds")
    }

    prepared = sorted(
        (
            _text(record.get("operation_id"), "operation_id"),
            record,
        )
        for record in (_mapping(item) for item in operations)
    )
    for operation_id, operation in prepared:
        kind = _text(operation.get("kind"), "operation kind")
        parents = tuple(
            _text(item, "parent id")
            for item in _sequence(operation.get("source_entity_ids", ()), "source_entity_ids")
        )
        children = tuple(
            _text(item, "child id")
            for item in _sequence(operation.get("target_entity_ids", ()), "target_entity_ids")
        )
        unknown = sorted(
            {entity_id for entity_id in (*parents, *children) if entity_id not in entities}
        )
        if unknown:
            issues.append(SolverIssue("lineage.unknown_entity", operation_id, ",".join(unknown)))
            continue
        if len(set(parents)) != len(parents) or len(set(children)) != len(children):
            issues.append(SolverIssue("lineage.duplicate_endpoint", operation_id, "duplicates"))
            continue
        if set(parents) & set(children):
            issues.append(SolverIssue("lineage.self_reference", operation_id, "self reference"))
            continue
        ordinary_cardinality = len(parents) == 1 and len(children) == 1
        if ordinary_cardinality:
            parent_kind = _text(entities[parents[0]].get("kind"), "parent kind")
            child_kind = _text(entities[children[0]].get("kind"), "child kind")
            parent_kinds = {parent_kind}
            child_kinds = {child_kind}
        else:
            parent_kinds = {
                _text(entities[item].get("kind"), "parent kind") for item in parents
            }
            child_kinds = {
                _text(entities[item].get("kind"), "child kind") for item in children
            }
        valid = False
        if not _authority_accepted(
            operation,
            authorization,
        ):
            issues.append(
                SolverIssue(
                    "lineage.unauthorized_or_policy_mismatch",
                    operation_id,
                    "authority or policy mismatch",
                )
            )
            continue
        if kind not in allowed_operation_kinds:
            issues.append(
                SolverIssue(
                    "lineage.operation_disabled", operation_id, "policy disallows operation"
                )
            )
            continue
        signature = (
            (kind, parents, children)
            if ordinary_cardinality
            else (kind, tuple(sorted(parents)), tuple(sorted(children)))
        )
        if signature in operation_signatures:
            issues.append(
                SolverIssue(
                    "lineage.duplicate_operation",
                    operation_id,
                    "logical operation is already declared",
                )
            )
            continue
        operation_signatures.add(signature)
        if kind == "pooled_from":
            valid = (
                len(parents) >= MINIMUM_POOL_SIZE
                and len(children) == 1
                and len(parent_kinds) == 1
                and parent_kinds == child_kinds
                and parent_kinds.issubset(POOLABLE_KINDS)
            )
            if not valid:
                issues.append(SolverIssue("pool.invalid", operation_id, "closed pool policy"))
        elif kind == "demultiplexed_from":
            channels = _channels(operation)
            channel_paths = [f"{source}>{target}" for source, target, _id, _tag in channels]
            channel_ids = [channel_id for _source, _target, channel_id, _tag in channels]
            tag_digests = [tag for _source, _target, _channel_id, tag in channels]
            expected_paths = [f"{parents[0]}>{child}" for child in children] if parents else []
            valid = (
                len(parents) == 1
                and len(children) >= MINIMUM_DEMULTIPLEX_SIZE
                and len(parent_kinds) == 1
                and parent_kinds == child_kinds
                and parent_kinds.issubset(DEMULTIPLEXABLE_KINDS)
                and sorted(channel_paths) == sorted(expected_paths)
                and len(set(channel_ids)) == len(channel_ids)
                and len(set(tag_digests)) == len(tag_digests)
                and (
                    not require_demultiplex_authority
                    or bool(authorization.authority_id)
                )
            )
            if not valid:
                issues.append(
                    SolverIssue(
                        "demultiplex.invalid_or_ambiguous",
                        operation_id,
                        "closed demux policy",
                    )
                )
        elif ordinary_cardinality:
            valid = ordinary_transition_allowed(kind, parent_kind, child_kind)
            if not valid:
                issues.append(
                    SolverIssue("lineage.transition_forbidden", operation_id, "closed transition")
                )
        else:
            issues.append(
                SolverIssue("lineage.cardinality_invalid", operation_id, "ordinary relation is 1:1")
            )
        if valid:
            declared_mixed = _bool(operation.get("mixed_subject", False), "mixed_subject")
            if ordinary_cardinality:
                edges.append((parents[0], children[0], kind))
            else:
                edges.extend((parent, child, kind) for parent in parents for child in children)
            if kind == "pooled_from":
                valid_pools[operation_id] = (parents, children, declared_mixed)
            elif kind == "demultiplexed_from":
                demultiplex_operation_by_target.update(
                    dict.fromkeys(children, operation_id)
                )
            resolved_operations.append(
                ResolvedOperationAnalysis(
                    operation_id=operation_id,
                    kind=kind,
                    source_entity_ids=(parents if ordinary_cardinality else tuple(sorted(parents))),
                    target_entity_ids=(
                        children if ordinary_cardinality else tuple(sorted(children))
                    ),
                    mixed_subject=declared_mixed,
                )
            )

    ordered_edges = tuple(sorted(set(edges)))
    adjacency: dict[str, list[str]] = {entity_id: [] for entity_id in entities}
    indegree = dict.fromkeys(entities, 0)
    for parent, child, _kind in ordered_edges:
        adjacency[parent].append(child)
        indegree[child] += 1
    queue = deque(sorted(entity for entity, degree in indegree.items() if degree == 0))
    depth = dict.fromkeys(entities, 0)
    topological: list[str] = []
    while queue:
        parent = queue.popleft()
        topological.append(parent)
        for child in adjacency[parent]:
            depth[child] = max(depth[child], depth[parent] + 1)
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    cyclic = sorted(entity for entity, degree in indegree.items() if degree > 0)
    if cyclic:
        issues.append(SolverIssue("lineage.cycle", cyclic[0], ",".join(cyclic)))
    over_depth = sorted(entity for entity, value in depth.items() if value > depth_cap)
    if over_depth:
        issues.append(
            SolverIssue("lineage.depth_exceeded", over_depth[0], str(max(depth.values())))
        )

    subjects = {
        entity: set(subject_context.initial_bindings.get(entity, frozenset()))
        for entity in entities
    }
    incoming: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for parent, child, kind in ordered_edges:
        incoming[child].append((parent, kind))
    pools_by_target: dict[
        str,
        list[tuple[str, tuple[str, ...], bool]],
    ] = defaultdict(list)
    for operation_id, (parents, children, declared_mixed) in valid_pools.items():
        for child in children:
            pools_by_target[child].append((operation_id, parents, declared_mixed))
    actual_pool_mixed: dict[str, bool] = {}
    for child in topological:
        for parent, kind in incoming.get(child, ()):
            inherited = subjects[parent]
            existing = subjects[child]
            if kind == "pooled_from":
                # A pool is resolved only after every source binding is considered together.
                # Copying one known source here would turn another source's missing identity
                # into affirmative evidence for the known subject.
                continue
            if kind == "demultiplexed_from" and existing:
                # An authoritative complete channel may preserve a separately asserted target
                # membership.  The tag is never interpreted as a subject identity and the
                # pooled parent's multi-subject set is therefore not copied over it.
                if not existing.issubset(inherited):
                    issues.append(
                        SolverIssue(
                            "demultiplex.cross_patient",
                            child,
                            "target subject is outside the source pool",
                        )
                    )
                continue
            if kind == "demultiplexed_from" and not inherited:
                issues.append(
                    SolverIssue(
                        "demultiplex.target_identity_unresolved",
                        demultiplex_operation_by_target[child],
                        "source identity is unresolved",
                    )
                )
                continue
            if (
                kind not in {"pooled_from", "demultiplexed_from"}
                and existing
                and inherited
                and existing != inherited
            ):
                issues.append(
                    SolverIssue(
                        "lineage.cross_patient",
                        child,
                        ",".join(sorted(existing | inherited)),
                    )
                )
            subjects[child].update(inherited)
        # Kahn readiness means every source of each pool targeting ``child`` has already
        # propagated.  Resolve the hyperedge atomically here so the complete pool identity
        # reaches later ordinary and demultiplex descendants.  A missing source binding
        # contributes nothing: a known sibling must never stand in for an unknown source.
        for operation_id, parents, declared_mixed in pools_by_target.get(child, ()):
            if any(not subjects[parent] for parent in parents):
                issues.append(
                    SolverIssue(
                        "pool.source_identity_unresolved",
                        operation_id,
                        "one or more pool sources have no authoritative subject binding",
                    )
                )
                continue
            source_subjects = {
                subject for parent in parents for subject in subjects[parent]
            }
            actual_mixed = len(source_subjects) > 1
            actual_pool_mixed[operation_id] = actual_mixed
            if declared_mixed != actual_mixed:
                issues.append(
                    SolverIssue(
                        "pool.composition_mismatch",
                        operation_id,
                        "declared mixed-subject state does not match propagated lineage",
                    )
                )
            if actual_mixed and not allow_pooling:
                issues.append(
                    SolverIssue(
                        "pool.mixed_subject_disabled",
                        operation_id,
                        "policy disallows mixed-subject pooling",
                    )
                )
            subjects[child].update(source_subjects)

    if actual_pool_mixed:
        resolved_operations = [
            (
                ResolvedOperationAnalysis(
                    operation_id=operation.operation_id,
                    kind=operation.kind,
                    source_entity_ids=operation.source_entity_ids,
                    target_entity_ids=operation.target_entity_ids,
                    mixed_subject=actual_pool_mixed[operation.operation_id],
                )
                if operation.operation_id in actual_pool_mixed
                else operation
            )
            for operation in resolved_operations
        ]

    for entity_id, entity in entities.items():
        subject_count = len(subjects[entity_id])
        expected_composition = (
            "unknown"
            if subject_count == 0
            else "single_subject"
            if subject_count == 1
            else "multi_subject"
        )
        declared_composition = _text(entity.get("composition"), "entity composition")
        if declared_composition != expected_composition:
            issues.append(
                SolverIssue(
                    "entity.composition_mismatch",
                    entity_id,
                    "declared composition does not match explicit lineage",
                )
            )

    bindings = tuple(
        (
            entity,
            tuple(
                sorted(
                    patient
                    for subject_root in subjects[entity]
                    for patient in subject_context.patient_members_by_root[subject_root]
                )
            ),
        )
        for entity in sorted(subjects)
    )
    return (
        ordered_edges,
        tuple(sorted(resolved_operations)),
        bindings,
        tuple(issues),
    )


def _aggregate_concordance(observations: Sequence[object]) -> ConcordanceCounts:
    unique: dict[tuple[str, ...], tuple[str, int, int, int]] = {}
    for item in observations:
        observation = _mapping(item)
        endpoints = tuple(
            sorted(
                (
                    _text(observation.get("left_entity_id"), "left_entity_id"),
                    _text(observation.get("right_entity_id"), "right_entity_id"),
                )
            )
        )
        key = (
            _text(observation.get("root_observation_id"), "root_observation_id"),
            *_record_evidence_digests(observation),
            *endpoints,
            _text(observation.get("method_id"), "method_id"),
            _text(observation.get("method_version"), "method_version"),
            _text(observation.get("assay_lineage_digest"), "assay_lineage_digest"),
            _text(observation.get("panel_digest"), "panel_digest"),
            _text(observation.get("reference_digest"), "reference_digest"),
            _text(observation.get("target_id"), "target_id"),
            _text(observation.get("evidence_policy_version"), "evidence_policy_version"),
        )
        classification = _text(observation.get("classification"), "classification")
        observation_counts = (
            _integer(observation.get("informative_count"), "informative_count"),
            _integer(observation.get("concordant_count"), "concordant_count"),
            _integer(observation.get("discordant_count"), "discordant_count"),
        )
        previous = unique.get(key)
        if previous is None:
            unique[key] = (classification, *observation_counts)
        elif previous != (classification, *observation_counts):
            unique[key] = ("indeterminate", 0, 0, 0)
    classification_counts: dict[str, int] = defaultdict(int)
    informative = concordant = discordant = 0
    for classification, info, concord, discord in unique.values():
        classification_counts[classification] += 1
        informative += info
        concordant += concord
        discordant += discord
    return ConcordanceCounts(
        concordant_observations=classification_counts["concordant"],
        discordant_observations=classification_counts["discordant"],
        indeterminate_observations=classification_counts["indeterminate"],
        unsupported_observations=classification_counts["unsupported"],
        missing_observations=classification_counts["missing"],
        excluded_dependent_observations=classification_counts["excluded_dependent"],
        informative_count=informative,
        concordant_count=concordant,
        discordant_count=discordant,
    )


def _finalize_components(
    components: tuple[ComponentAnalysis, ...],
    bindings: tuple[tuple[str, tuple[str, ...]], ...],
    patient_members_by_root: Mapping[str, tuple[str, ...]],
    issues: Sequence[SolverIssue],
) -> tuple[ComponentAnalysis, ...]:
    binding_map = dict(bindings)
    patient_root_by_member = {
        patient: root
        for root, patients in patient_members_by_root.items()
        for patient in patients
    }
    issue_subjects = {issue.subject for issue in issues}
    finalized: list[ComponentAnalysis] = []
    for component in components:
        subjects = tuple(
            sorted(
                {
                    subject
                    for member in component.members
                    for subject in binding_map.get(member, ())
                }
            )
        )
        subject_roots = {patient_root_by_member[subject] for subject in subjects}
        finalized.append(
            ComponentAnalysis(
                component_id=component.component_id,
                members=component.members,
                kind=component.kind,
                subject_anchors=subjects,
                composition=(
                    "unknown"
                    if not subject_roots
                    else "single_subject"
                    if len(subject_roots) == 1
                    else "multi_subject"
                ),
                quarantined=component.quarantined
                or not issue_subjects.isdisjoint(component.members),
            )
        )
    return tuple(finalized)


def _analyze(request: ReconcileIdentityLineageRequest) -> SolverAnalysis:
    material = _mapping(request)
    policy = _mapping(material["policy"])
    context = _mapping(material["context"])
    references = _mapping(context["references"])
    authority = _mapping(references["identity_authority"])
    authority_id = _text(authority.get("decision_id"), "identity authority decision_id")
    authority_policy_version = _text(
        authority.get("policy_version"), "identity authority policy_version"
    )
    active_policy_version = _text(policy.get("version"), "policy version")
    authorization = _Authorization(
        authority_id=authority_id,
        authority_policy_version=authority_policy_version,
        active_policy_version=active_policy_version,
        controls_accepted=_controls_are_accepted(references),
    )
    entity_records = [_mapping(item) for item in _sequence(material["entities"], "entities")]
    entities = {
        _text(entity.get("entity_id"), "entity_id"): entity for entity in entity_records
    }
    invalid_kinds = sorted(
        entity_id
        for entity_id, entity in entities.items()
        if _text(entity.get("kind"), "entity kind") not in ENTITY_KINDS
    )
    if invalid_kinds:
        raise ValueError
    component_cap = _integer(policy.get("max_component_size", 256), "max_component_size")
    _dsu, components, component_issues, initial_bindings, patient_members = _analyze_components(
        entities,
        _sequence(material.get("assertions", ()), "assertions"),
        authorization,
        _policy_identity(policy),
        component_cap,
    )
    edges, resolved_operations, bindings, lineage_issues = _analyze_lineage(
        entities,
        _sequence(material.get("lineage_operations", ()), "lineage_operations"),
        authorization,
        policy,
        _SubjectContext(
            initial_bindings=initial_bindings,
            patient_members_by_root=patient_members,
        ),
    )
    concordance = _aggregate_concordance(
        _sequence(material.get("concordance_observations", ()), "concordance_observations")
    )
    issues = list(component_issues + lineage_issues)
    if not authorization.controls_accepted:
        issues.append(
            SolverIssue(
                "control.not_authorized",
                "context",
                "one or more required controls do not authorize reconciliation",
            )
        )
    if authority_policy_version != active_policy_version:
        issues.append(
            SolverIssue(
                "control.policy_mismatch",
                "context",
                "identity authority and active policy versions differ",
            )
        )
    if concordance.discordant_observations:
        issues.append(
            SolverIssue(
                "concordance.counter_evidence",
                "concordance",
                str(concordance.discordant_observations),
            )
        )
    if (
        concordance.indeterminate_observations
        or concordance.unsupported_observations
        or concordance.missing_observations
        or concordance.excluded_dependent_observations
    ):
        issues.append(
            SolverIssue(
                "concordance.indeterminate",
                "concordance",
                "concordance evidence is indeterminate, missing, unsupported, or dependent",
            )
        )
    ordered_issues = tuple(sorted(set(issues)))
    finalized_components = _finalize_components(
        components,
        bindings,
        patient_members,
        ordered_issues,
    )
    return SolverAnalysis(
        components=finalized_components,
        lineage_edges=edges,
        resolved_operations=resolved_operations,
        subject_bindings=bindings,
        concordance=concordance,
        issues=ordered_issues,
    )


def _public_components(
    analysis: SolverAnalysis,
) -> tuple[
    tuple[IdentityComponent, ...],
    dict[str, str],
    dict[str, tuple[str, ...]],
]:
    component_by_member = {
        member: component.component_id
        for component in analysis.components
        for member in component.members
    }
    subject_components_by_member: dict[str, tuple[str, ...]] = {}
    result: list[IdentityComponent] = []
    for component in analysis.components:
        subject_component_ids = tuple(
            sorted({component_by_member[subject] for subject in component.subject_anchors})
        )
        for member in component.members:
            subject_components_by_member[member] = subject_component_ids
        result.append(
            IdentityComponent(
                component_id=component.component_id,
                member_entity_ids=component.members,
                subject_component_ids=subject_component_ids,
                composition=EntityComposition(component.composition),
            )
        )
    return tuple(sorted(result, key=lambda item: item.component_id)), component_by_member, (
        subject_components_by_member
    )


def _public_graph(
    request: ReconcileIdentityLineageRequest,
    analysis: SolverAnalysis,
    component_by_member: Mapping[str, str],
    subject_components_by_member: Mapping[str, tuple[str, ...]],
) -> ResolvedLineageGraph:
    nodes = tuple(
        sorted(
            (
                ResolvedIdentityNode(
                    entity_id=entity.entity_id,
                    kind=EntityKind(entity.kind),
                    component_id=component_by_member[entity.entity_id],
                    subject_component_ids=subject_components_by_member[entity.entity_id],
                )
                for entity in request.entities
            ),
            key=lambda item: item.entity_id,
        )
    )
    operations = tuple(
        ResolvedLineageOperation(
            operation_id=operation.operation_id,
            kind=LineageOperationKind(operation.kind),
            source_entity_ids=operation.source_entity_ids,
            target_entity_ids=operation.target_entity_ids,
            mixed_subject=operation.mixed_subject,
        )
        for operation in analysis.resolved_operations
    )
    return ResolvedLineageGraph(nodes=nodes, operations=operations)


def _issue_action(code: str) -> IdentityIssueAction:
    if code in {"lineage.duplicate_operation", "concordance.indeterminate"}:
        return IdentityIssueAction.HUMAN_REVIEW
    return IdentityIssueAction.QUARANTINE


def _public_issues(  # noqa: C901 - bounded dispatch over causal declaration kinds
    request: ReconcileIdentityLineageRequest,
    analysis: SolverAnalysis,
) -> tuple[IdentityIssue, ...]:
    entity_ids = {entity.entity_id for entity in request.entities}
    operation_ids = {operation.operation_id for operation in request.lineage_operations}
    assertion_ids = {assertion.assertion_id for assertion in request.assertions}
    assertion_by_id = {assertion.assertion_id: assertion for assertion in request.assertions}
    operation_by_id = {
        operation.operation_id: operation for operation in request.lineage_operations
    }
    component_by_member = {
        member: component
        for component in analysis.components
        for member in component.members
    }
    normalized_concordance_material: object = ()
    if any(issue.code.startswith("concordance.") for issue in analysis.issues):
        normalized_concordance_material = normalized_request(request)[
            "concordance_observations"
        ]

    def causal_operation(issue: SolverIssue) -> LineageOperation | None:
        direct = operation_by_id.get(issue.subject)
        if direct is not None:
            return direct
        if issue.code.startswith(("lineage.", "demultiplex.", "pool.")):
            matches = tuple(
                operation
                for operation in request.lineage_operations
                if issue.subject in operation.target_entity_ids
            )
            if len(matches) == 1:
                return matches[0]
        return None

    def causal_material(issue: SolverIssue) -> object:
        if issue.subject in assertion_by_id:
            return assertion_by_id[issue.subject]
        operation = causal_operation(issue)
        if operation is not None:
            return operation
        if issue.code.startswith("concordance."):
            return normalized_concordance_material
        component = component_by_member.get(issue.subject)
        if component is not None:
            return {
                "issue_code": issue.code,
                "component_id": component.component_id,
                "members": component.members,
                "entity_evidence": [
                    artifact
                    for entity in request.entities
                    if entity.entity_id in component.members
                    for artifact in (
                        *entity.evidence,
                        *(token.evidence for token in entity.identity_tokens),
                    )
                ],
            }
        return {"issue_code": issue.code, "subject": issue.subject}

    def causal_evidence(issue: SolverIssue) -> tuple[ArtifactReference, ...]:
        if issue.subject in assertion_by_id:
            return tuple(assertion_by_id[issue.subject].evidence)
        operation = causal_operation(issue)
        if operation is not None:
            return tuple(
                dict.fromkeys(
                    (
                        *operation.evidence,
                        *(
                            artifact
                            for channel in operation.channels
                            for artifact in channel.evidence
                        ),
                    )
                )
            )
        if issue.code.startswith("concordance."):
            return tuple(
                dict.fromkeys(
                    artifact
                    for observation in request.concordance_observations
                    for artifact in observation.evidence
                )
            )
        component = component_by_member.get(issue.subject)
        if component is None:
            return ()
        return tuple(
            dict.fromkeys(
                artifact
                for entity in request.entities
                if entity.entity_id in component.members
                for artifact in (
                    *entity.evidence,
                    *(token.evidence for token in entity.identity_tokens),
                )
            )
        )

    public: list[IdentityIssue] = []
    for issue in analysis.issues:
        action = _issue_action(issue.code)
        evidence = causal_evidence(issue)
        retained_evidence = tuple(sorted(evidence, key=canonical_json_bytes))[:64]
        component_ids = (
            (component_by_member[issue.subject].component_id,)
            if issue.code == "component.cross_kind" and issue.subject in component_by_member
            else ()
        )
        public.append(
            IdentityIssue(
                code=issue.code,
                severity=(
                    IdentityIssueSeverity.CRITICAL
                    if action is IdentityIssueAction.QUARANTINE
                    else IdentityIssueSeverity.WARNING
                ),
                action=action,
                evidence_basis_digest=sha256_digest(causal_material(issue)),
                evidence_reference_count=len(evidence),
                entity_ids=(issue.subject,) if issue.subject in entity_ids else (),
                component_ids=component_ids,
                operation_ids=(issue.subject,) if issue.subject in operation_ids else (),
                assertion_ids=(issue.subject,) if issue.subject in assertion_ids else (),
                message=f"Deterministic reconciliation finding: {issue.code}.",
                evidence=retained_evidence,
            )
        )
    maximum = 1_000
    if len(public) > maximum:
        public = public[: maximum - 1]
        public.append(
            IdentityIssue(
                code="issues.capacity_exceeded",
                severity=IdentityIssueSeverity.CRITICAL,
                action=IdentityIssueAction.QUARANTINE,
                evidence_basis_digest=sha256_digest(
                    {
                        "issue_code": "issues.capacity_exceeded",
                        "complete_issue_count": len(analysis.issues),
                    }
                ),
                evidence_reference_count=0,
                message="Additional deterministic findings exceeded the public issue limit.",
            )
        )
    return tuple(public)


def _assertion_dispositions(
    request: ReconcileIdentityLineageRequest,
    analysis: SolverAnalysis,
) -> tuple[AssertionDisposition, ...]:
    component_by_member = {
        member: component
        for component in analysis.components
        for member in component.members
    }
    issue_by_subject = {issue.subject: issue.code for issue in analysis.issues}
    dispositions: list[AssertionDisposition] = []
    for assertion in sorted(request.assertions, key=lambda item: item.assertion_id):
        material = _mapping(assertion)
        endpoints = _ids(material)
        direct_issue = issue_by_subject.get(assertion.assertion_id)
        component_quarantined = any(
            component_by_member[endpoint].quarantined
            for endpoint in endpoints
            if endpoint in component_by_member
        )
        if direct_issue is not None and (
            direct_issue.startswith("assertion.")
            or direct_issue.endswith("invalid_cardinality")
        ):
            state = AssertionDispositionState.REJECTED
            reason_code = direct_issue
        elif direct_issue is not None or component_quarantined:
            state = AssertionDispositionState.QUARANTINED
            reason_code = direct_issue or "assertion.component_quarantined"
        else:
            state = AssertionDispositionState.ACCEPTED
            reason_code = "assertion.accepted"
        dispositions.append(
            AssertionDisposition(
                assertion_id=assertion.assertion_id,
                state=state,
                reason_code=reason_code,
                evidence=assertion.evidence,
            )
        )
    return tuple(dispositions)


def _public_concordance(counts: ConcordanceCounts) -> ConcordanceAggregate:
    return ConcordanceAggregate(
        concordant=counts.concordant_observations,
        discordant=counts.discordant_observations,
        indeterminate=counts.indeterminate_observations,
        missing=counts.missing_observations,
        unsupported=counts.unsupported_observations,
        excluded_dependent=counts.excluded_dependent_observations,
        informative_loci=counts.informative_count,
        concordant_loci=counts.concordant_count,
        discordant_loci=counts.discordant_count,
    )


def _decision(issues: tuple[IdentityIssue, ...]) -> ResolutionDecision:
    actions = {issue.action for issue in issues}
    if IdentityIssueAction.QUARANTINE in actions:
        return ResolutionDecision.QUARANTINED
    if IdentityIssueAction.REJECT in actions:
        return ResolutionDecision.CONFLICTED
    if IdentityIssueAction.HUMAN_REVIEW in actions:
        return ResolutionDecision.UNRESOLVED
    return ResolutionDecision.RESOLVED


def reconcile_identity_lineage(
    request: ReconcileIdentityLineageRequest,
) -> IdentityLineageResolutionDraft:
    """Reconcile explicit identity and lineage evidence without I/O or inference."""

    _require_authorized_request(request)
    analysis = _analyze(request)
    components, component_by_member, subject_components_by_member = _public_components(
        analysis,
    )
    graph = _public_graph(
        request,
        analysis,
        component_by_member,
        subject_components_by_member,
    )
    issues = _public_issues(request, analysis)
    request_identity = canonical_request_digest(request)
    decision = _decision(issues)
    return IdentityLineageResolutionDraft(
        resolution_id=f"resolution.{request_identity.removeprefix('sha256:')}",
        resolution_version="1.0.0",
        request_digest=request_identity,
        policy_digest=policy_digest(request.policy),
        decision=decision,
        components=components,
        graph=graph,
        assertion_dispositions=_assertion_dispositions(request, analysis),
        concordance=_public_concordance(analysis.concordance),
        issues=issues,
        human_review_required=(
            decision is not ResolutionDecision.RESOLVED
            or any(
                issue.severity is IdentityIssueSeverity.CRITICAL
                for issue in issues
            )
        ),
        resolved_at=request.context.occurred_at,
        supersedes_resolution_digest=request.supersedes_resolution_digest,
    )
