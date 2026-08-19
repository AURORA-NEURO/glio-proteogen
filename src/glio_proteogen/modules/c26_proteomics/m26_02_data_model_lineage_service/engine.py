"""Pure, deterministic M26-02 lineage graph construction and replay."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import chain
from typing import TYPE_CHECKING, Any, Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_02 import (
    M2602_CONTRACT_VERSION,
    M2602_MODULE_ID,
    M2602_UPSTREAM_MEDIA_TYPE,
    BuildProteinSubtypeLineageRequest,
    LineageFinding,
    LineageFindingCode,
    LineageGraph,
    LineageStatus,
    ProteinSubtypeLineageResult,
    canonical_request_digest,
    graph_payload_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

_REQUEST_ADAPTER: Final[TypeAdapter[BuildProteinSubtypeLineageRequest]] = TypeAdapter(
    BuildProteinSubtypeLineageRequest
)
_RESULT_ADAPTER: Final[TypeAdapter[ProteinSubtypeLineageResult]] = TypeAdapter(
    ProteinSubtypeLineageResult
)
_ZERO_DIGEST: Final[str] = "sha256:" + ("0" * 64)
_AUTHORIZATION_MESSAGE: Final = (
    "lineage construction requires accepted upstream authorization states"
)
_EXPECTED_STATES: Final[dict[ControlRole, str]] = {
    ControlRole.APPROVED_CONFIGURATION: "accepted",
    ControlRole.IDENTITY_LINEAGE: "resolved",
    ControlRole.PROVENANCE: "accepted",
    ControlRole.CONSENT: "granted",
    ControlRole.QUALITY: "accepted",
    ControlRole.SUPPORT: "accepted",
    ControlRole.INTENDED_USE: "accepted",
}
_LIMITATIONS: Final = (
    Limitation(
        code="lineage_traceability_only",
        statement=(
            "This module emits a caller-declared lineage graph and replay bundle; it does not "
            "infer a protein subtype, proteotype, kinase state, or treatment recommendation."
        ),
    ),
    Limitation(
        code="upstream_media_boundary",
        statement=(
            "The M26-01 registry artifact is accepted by declared media type only; issuer "
            "authority and registry semantics are not authenticated here."
        ),
    ),
    Limitation(
        code="research_use_only",
        statement=(
            "The dossier limits this provisional implementation to research and development "
            "until analytical, external, subgroup, transport, human-factors, and prospective "
            "validation are complete."
        ),
    ),
)


class LineageAuthorizationError(ValueError):
    """Raised before governed lineage material is traversed."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class LineageReplayError(ValueError):
    """Raised when canonical result or replay material has been tampered with."""

    def __init__(self) -> None:
        super().__init__("lineage replay verification failed")


class M2602LineageEngine:
    """Build one immutable graph without I/O, persistence, or learned inference."""

    __slots__ = ()

    def build(self, request: BuildProteinSubtypeLineageRequest) -> ProteinSubtypeLineageResult:
        preflight_lineage_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_lineage_authorization(validated)
        request_hash = canonical_request_digest(validated)
        graph, findings = _validated_graph(validated)
        if graph is not None:
            findings.extend(_graph_findings(validated, graph))
        supported = not findings
        status = LineageStatus.BUILT if supported else LineageStatus.ABSTAINED
        support = _support_decision(supported=supported)
        controls = _control_records(validated.context)
        configuration_hash = _configuration_digest(validated)
        evidence = _evidence_index(validated, controls)
        provenance = _provenance(validated, request_hash, configuration_hash, controls)
        candidate: dict[str, Any] = {
            "output_type": "protein_subtype_lineage",
            "result_id": f"result.m2602.{request_hash.removeprefix('sha256:')}",
            "result_version": M2602_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": validated,
            "status": status,
            "lineage_graph": graph if supported else None,
            "reproducibility_bundle": validated.reproducibility_bundle if supported else None,
            "findings": tuple(findings),
            "abstention_reason": None if supported else _abstention_reason(findings),
            "parent_target": "protein subtype",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(supported=supported),
            "provenance": provenance,
            "evidence": evidence,
            "limitations": _LIMITATIONS,
            "human_review_required": True,
        }
        materialized = ProteinSubtypeLineageResult.model_construct(**candidate)
        json_payload = materialized.model_dump(mode="json")
        result_digest = result_payload_digest(json_payload)
        payload = materialized.model_dump(mode="python")
        payload["result_digest"] = result_digest
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def build_lineage_graph(request: object) -> ProteinSubtypeLineageResult:
    """Public stateless entry point for the M26-02 service."""

    preflight_lineage_authorization(request)
    validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
    return M2602LineageEngine().build(validated)


def preflight_lineage_authorization(candidate: object) -> None:
    """Fail closed on all seven controls before reading graph or evidence payloads."""
    try:
        if isinstance(candidate, BuildProteinSubtypeLineageRequest):
            context: object = candidate.context
        elif isinstance(candidate, Mapping):
            context = candidate.get("context")
        else:
            raise LineageAuthorizationError  # noqa: TRY301
        references = _member(context, "references")
        for role, expected in _EXPECTED_STATES.items():
            value = _member(_member(references, role.value), "state")
            value = getattr(value, "value", value)
            if value != expected:
                raise LineageAuthorizationError  # noqa: TRY301
    except LineageAuthorizationError:
        raise
    except Exception as error:
        raise LineageAuthorizationError from error


def _member(candidate: object, name: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(name)
    return getattr(candidate, name, None)


def verify_lineage_result(result: ProteinSubtypeLineageResult) -> ProteinSubtypeLineageResult:
    """Regenerate and compare the complete deterministic result for replay."""

    validated = _RESULT_ADAPTER.validate_python(result, strict=True)
    expected_request = canonical_request_digest(validated.request)
    if validated.request_digest != expected_request:
        raise LineageReplayError
    if validated.result_digest != result_payload_digest(validated):
        raise LineageReplayError
    if validated.status is LineageStatus.BUILT:
        if validated.lineage_graph is None or validated.reproducibility_bundle is None:
            raise LineageReplayError
        if validated.reproducibility_bundle.graph_digest != validated.lineage_graph.graph_digest:
            raise LineageReplayError
        if graph_payload_digest(validated.lineage_graph) != validated.lineage_graph.graph_digest:
            raise LineageReplayError
    try:
        expected = M2602LineageEngine().build(validated.request)
    except Exception as error:
        raise LineageReplayError from error
    if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
        raise LineageReplayError
    return validated


def _validated_graph(
    request: BuildProteinSubtypeLineageRequest,
) -> tuple[LineageGraph | None, list[LineageFinding]]:
    try:
        graph = LineageGraph(
            graph_id=request.graph_id,
            version=request.graph_version,
            nodes=request.nodes,
            edges=request.edges,
            graph_digest=request.reproducibility_bundle.graph_digest,
            locked=True,
        )
    except ValidationError:
        return None, [_finding("broken_link", "lineage graph links or kinds are not closed")]
    return graph, []


def _graph_findings(
    request: BuildProteinSubtypeLineageRequest,
    graph: LineageGraph,
) -> list[LineageFinding]:
    findings: list[LineageFinding] = []
    expected_graph_digest = graph_payload_digest(graph)
    if expected_graph_digest != graph.graph_digest:
        findings.append(
            _finding("reproducibility_gap", "lineage graph digest does not match content")
        )
    bundle = request.reproducibility_bundle
    if bundle.graph_digest != graph.graph_digest:
        findings.append(_finding("version_mismatch", "replay bundle does not bind graph digest"))
    node_ids = {node.node_id for node in graph.nodes}
    parent_ids = {edge.child_node_id for edge in graph.edges}
    for root in bundle.root_node_ids:
        if root not in node_ids:
            findings.append(_finding("missing_root", "replay bundle references a missing root"))
        elif root in parent_ids:
            findings.append(_finding("broken_link", "replay root has an incoming lineage link"))
    reachable = _reachable_nodes(graph, bundle.root_node_ids, node_ids)
    if reachable != node_ids:
        findings.append(
            _finding(
                "broken_link",
                "lineage graph contains nodes unreachable from replay roots",
            )
        )
    return findings


def _reachable_nodes(
    graph: LineageGraph,
    roots: tuple[str, ...],
    node_ids: set[str],
) -> set[str]:
    children: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for edge in graph.edges:
        children[edge.parent_node_id].add(edge.child_node_id)
    reachable = {root for root in roots if root in node_ids}
    frontier = list(reachable)
    while frontier:
        current = frontier.pop()
        for child in children[current]:
            if child not in reachable:
                reachable.add(child)
                frontier.append(child)
    return reachable


def _finding(code: str, message: str) -> LineageFinding:
    return LineageFinding(
        finding_id=f"finding.m2602.{code}",
        code=LineageFindingCode(code),
        message=message,
    )


def _abstention_reason(findings: Iterable[LineageFinding]) -> str:
    codes = ", ".join(sorted({finding.code.value for finding in findings}))
    return f"Lineage construction abstained because declared lineage controls failed: {codes}."


def _support_decision(*, supported: bool) -> SupportDecision:
    if supported:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="lineage_graph_supported",
            rationale="Every declared node, edge, version, root, and replay binding is closed.",
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="lineage_graph_abstained",
        rationale=(
            "Broken, conflicting, or unreproducible lineage is preserved and requires review."
        ),
    )


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty(*, supported: bool) -> UncertaintyProfile:
    state = (
        "Exact graph checks are deterministic; scientific measurement uncertainty is not "
        "estimated by this service."
        if supported
        else "An abstained graph has no scientifically interpretable estimate."
    )
    return UncertaintyProfile(
        measurement=_not_estimable(state),
        sampling=_not_estimable("No sampling distribution is supplied by the lineage service."),
        parameter=_not_estimable("No fitted parameters are used for lineage construction."),
        model_form=_not_estimable("No learned model is used for lineage construction."),
        identification=_not_estimable("Issuer identity is caller-declared and not authenticated."),
        support=_not_estimable("Support is a deterministic graph-closure decision."),
        transport=_not_estimable("Transport beyond declared artifacts is not estimated."),
        sensitivity_notes=(
            "Missing, unknown, and conflicting lineage never become a negative biological finding.",
            "M26-01 is checked by media type and source inclusion only; its registry semantics "
            "remain upstream.",
        ),
    )


def _control_records(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    references = context.references
    controls = (
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
            state=getattr(reference.state, "value", reference.state),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject_digest,
        )
        for role, reference, subject_digest in controls
    )


def _configuration_digest(request: BuildProteinSubtypeLineageRequest) -> str:
    return sha256_digest(
        {
            "module": M2602_MODULE_ID,
            "contract": M2602_CONTRACT_VERSION,
            "operation": request.operation,
            "upstream_media_type": M2602_UPSTREAM_MEDIA_TYPE,
            "graph_version": request.graph_version,
            "bundle_version": request.reproducibility_bundle.version,
        }
    )


def _provenance(
    request: BuildProteinSubtypeLineageRequest,
    request_hash: str,
    configuration_hash: str,
    controls: tuple[ControlDecisionRecord, ...],
) -> ProvenanceRecord:
    references = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m2602.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M2602_MODULE_ID,
        module_version=M2602_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted(
                {
                    request_hash,
                    *(artifact.digest for artifact in request.source_artifacts),
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


def _evidence_index(
    request: BuildProteinSubtypeLineageRequest,
    controls: tuple[ControlDecisionRecord, ...],
) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    control_artifacts = (
        references.approved_configuration.evidence,
        references.identity_lineage.evidence,
        references.provenance.evidence,
        references.consent.evidence,
        references.quality.evidence,
        references.support.evidence,
        references.intended_use.evidence,
    )
    indexed = tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared control evidence; issuer authority is not authenticated here.",
        )
        for artifact in chain(control_artifacts, request.source_artifacts)
    )
    return _dedupe_evidence(indexed, controls)


def _dedupe_evidence(
    evidence: Iterable[EvidenceReference],
    controls: tuple[ControlDecisionRecord, ...],
) -> tuple[EvidenceReference, ...]:
    del controls  # The argument documents that evidence is tied to seven control records.
    seen: set[bytes] = set()
    result: list[EvidenceReference] = []
    for item in evidence:
        key = canonical_json_bytes(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return tuple(result)


__all__ = [
    "LineageAuthorizationError",
    "LineageReplayError",
    "M2602LineageEngine",
    "build_lineage_graph",
    "preflight_lineage_authorization",
    "verify_lineage_result",
]
