"""Deterministic, reference-only M27-02 complex-activity lineage resolver."""

from __future__ import annotations

from typing import Final, cast

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m27_02 import (
    M2702_CONTRACT_VERSION,
    M2702_MODULE_ID,
    ComplexActivityLineageResult,
    LineageEdge,
    LineageFinding,
    LineageFindingCode,
    LineageGraph,
    LineageNode,
    LineageNodeKind,
    LineageRelation,
    LineageStatus,
    ReproducibilityBundle,
    ResolveComplexActivityLineageRequest,
    SafeFailureReport,
    canonical_request_digest,
    graph_payload_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ResolveComplexActivityLineageRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityLineageResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_EXPECTED_CONTROLS: Final = {
    "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
    "identity_lineage": IdentityLineageState.RESOLVED.value,
    "provenance": UpstreamDecisionState.ACCEPTED.value,
    "consent": ConsentState.GRANTED.value,
    "quality": UpstreamDecisionState.ACCEPTED.value,
    "support": UpstreamDecisionState.ACCEPTED.value,
    "intended_use": UpstreamDecisionState.ACCEPTED.value,
}
_STATE_ENUMS: Final = (str, UpstreamDecisionState, IdentityLineageState, ConsentState)
_AUTHORIZATION_MESSAGE: Final = "M27-02 lineage resolution requires accepted upstream controls"


class M2702AuthorizationError(ValueError):
    """Raised before any caller-controlled lineage references are traversed."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2702ReplayError(ValueError):
    """A lineage result failed canonical identity or deterministic replay."""


class M2702ValidatedRequestError(TypeError):
    """A private validated-execution seam received a non-exact model."""

    def __init__(self) -> None:
        super().__init__("M27-02 validated execution requires the exact request model")


def preflight_m2702_authorization(candidate: object) -> None:
    """Check all seven caller-declared controls before reading lineage material."""

    authorized = False
    try:
        candidate_mro = type.__getattribute__(type(candidate), "__mro__")
        supported = ResolveComplexActivityLineageRequest in candidate_mro or dict in candidate_mro
        context = _member(candidate, "context") if supported else None
        references = _member(context, "references")
        states = {
            role: _state_text(_member(_member(references, role), "state"))
            for role in _EXPECTED_CONTROLS
        }
        authorized = supported and states == _EXPECTED_CONTROLS
    except Exception:  # noqa: BLE001 - authorization is intentionally fail closed.
        raise M2702AuthorizationError from None
    if not authorized:
        raise M2702AuthorizationError


class M2702LineageResolver:
    """Resolve only explicit artifact references into a sealed lineage graph."""

    __slots__ = ()

    def resolve(self, request: object) -> ComplexActivityLineageResult:
        preflight_m2702_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(_plain_value(request), strict=True)
        return self._resolve_validated(validated)

    def resolve_validated(
        self, request: ResolveComplexActivityLineageRequest
    ) -> ComplexActivityLineageResult:
        """Resolve a request already parsed by an API/CLI/service boundary."""

        return self._resolve_validated(request)

    def _resolve_validated(
        self, canonical: ResolveComplexActivityLineageRequest
    ) -> ComplexActivityLineageResult:
        if type(canonical) is not ResolveComplexActivityLineageRequest:
            raise M2702ValidatedRequestError
        request_hash = canonical_request_digest(canonical)
        graph, findings = _derive_graph(canonical, request_hash)
        evidence = _evidence_for(canonical.source_artifacts)
        provenance = _provenance(canonical, request_hash)
        if graph is None:
            return _build_abstention(canonical, request_hash, findings, evidence, provenance)
        graph_digest = graph_payload_digest(graph)
        bundle = graph.reproducibility_bundle.model_copy(update={"manifest_digest": graph_digest})
        sealed_graph = graph.model_copy(update={"reproducibility_bundle": bundle})
        payload: dict[str, object] = {
            "output_type": "complex_activity_lineage",
            "result_id": f"result.m2702.{request_hash.removeprefix('sha256:')}",
            "result_version": M2702_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": canonical,
            "status": LineageStatus.RESOLVED,
            "lineage_graph": sealed_graph,
            "findings": findings,
            "safe_failure_report": None,
            "abstention_reason": None,
            "parent_target": "complex activity",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="lineage_resolved",
                rationale="All caller-declared lineage references are closed and version-bound.",
            ),
            "uncertainty": _uncertainty(),
            "provenance": provenance,
            "evidence": evidence,
            "limitations": _limitations(),
            "human_review_required": False,
        }
        payload["result_digest"] = result_payload_digest(payload)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def replay(self, result: object) -> ComplexActivityLineageResult:
        """Verify one sealed result and replay its exact request deterministically."""

        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
            if validated.request_digest != canonical_request_digest(validated.request):
                raise M2702ReplayError  # noqa: TRY301
            expected_result_id = (
                f"result.m2702.{validated.request_digest.removeprefix('sha256:')}"
            )
            if validated.result_id != expected_result_id:
                raise M2702ReplayError  # noqa: TRY301
            if validated.result_digest != result_payload_digest(validated):
                raise M2702ReplayError  # noqa: TRY301
            expected = self.resolve_validated(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M2702ReplayError  # noqa: TRY301
        except M2702ReplayError:
            raise
        except Exception as error:
            raise M2702ReplayError from error
        return validated


def resolve_complex_activity_lineage(request: object) -> ComplexActivityLineageResult:
    """Resolve one request through the stateless M27-02 public operation."""

    return M2702LineageResolver().resolve(request)


def _derive_graph(
    request: ResolveComplexActivityLineageRequest,
    request_hash: str,
) -> tuple[LineageGraph | None, tuple[LineageFinding, ...]]:
    """Construct a multi-parent graph or typed findings without guessing."""

    findings: list[LineageFinding] = []
    by_identifier: dict[str, ArtifactReference] = {}
    for artifact in request.source_artifacts:
        if artifact.artifact_id in by_identifier:
            findings.append(
                _finding(
                    0,
                    LineageFindingCode.BROKEN_LINK,
                    "duplicate artifact identifiers make lineage ownership ambiguous",
                    request.source_artifacts,
                )
            )
            break
        by_identifier[artifact.artifact_id] = artifact
    if request.root_object_id in by_identifier:
        findings.append(
            _finding(
                len(findings),
                LineageFindingCode.BROKEN_LINK,
                "root object identifier collides with a source artifact identifier",
                request.source_artifacts,
            )
        )
    if findings:
        return None, tuple(findings)

    source_evidence = _evidence_for(request.source_artifacts)
    root = LineageNode(
        node_id=request.root_object_id,
        kind=LineageNodeKind.TRANSFORMATION,
        name="complex_activity_lineage_root",
        version=M2702_CONTRACT_VERSION,
        digest=request_hash,
        media_type="application/vnd.glio-proteogen.m27-02+json",
        evidence=source_evidence[:1],
    )
    nodes = [root]
    edges: list[LineageEdge] = []
    for index, artifact in enumerate(request.source_artifacts):
        nodes.append(
            LineageNode(
                node_id=artifact.artifact_id,
                kind=LineageNodeKind.SOURCE_DATA,
                name=artifact.artifact_id,
                version=artifact.version,
                digest=artifact.digest,
                media_type=artifact.media_type,
                evidence=(_evidence(artifact, "caller-declared lineage source"),),
            )
        )
        edges.append(
            LineageEdge(
                edge_id=f"edge.m2702.{index}",
                source_node_id=artifact.artifact_id,
                target_node_id=request.root_object_id,
                relation=LineageRelation.DERIVED_FROM,
                producing_version=artifact.version,
                evidence=(_evidence(artifact, "source contributes to lineage root"),),
            )
        )
    versions = tuple(sorted({node.version for node in nodes}))
    bundle = ReproducibilityBundle(
        bundle_id=f"bundle.m2702.{request_hash.removeprefix('sha256:')}",
        version=M2702_CONTRACT_VERSION,
        root_node_id=root.node_id,
        node_ids=tuple(node.node_id for node in nodes),
        edge_ids=tuple(edge.edge_id for edge in edges),
        producing_versions=versions,
        manifest_digest=_ZERO_DIGEST,
        evidence=source_evidence,
    )
    return (
        LineageGraph(
            graph_id=f"graph.m2702.{request_hash.removeprefix('sha256:')}",
            version=M2702_CONTRACT_VERSION,
            nodes=tuple(nodes),
            edges=tuple(edges),
            reproducibility_bundle=bundle,
            evidence=source_evidence,
        ),
        (),
    )


def _build_abstention(
    request: ResolveComplexActivityLineageRequest,
    request_hash: str,
    findings: tuple[LineageFinding, ...],
    evidence: tuple[EvidenceReference, ...],
    provenance: ProvenanceRecord,
) -> ComplexActivityLineageResult:
    report = SafeFailureReport(
        report_id=f"safe-failure.m2702.{request_hash.removeprefix('sha256:')}",
        version=M2702_CONTRACT_VERSION,
        trigger="lineage_integrity_not_closed",
        action="abstain_without_emitting_complex_activity_claims",
        recovery_note="Correct the caller-declared references and submit a new request.",
        evidence=evidence,
    )
    payload: dict[str, object] = {
        "output_type": "complex_activity_lineage",
        "result_id": f"result.m2702.{request_hash.removeprefix('sha256:')}",
        "result_version": M2702_CONTRACT_VERSION,
        "request_digest": request_hash,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": LineageStatus.ABSTAINED,
        "lineage_graph": None,
        "findings": findings,
        "safe_failure_report": report,
        "abstention_reason": "lineage_integrity_not_closed",
        "parent_target": "complex activity",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.UNSUPPORTED,
            reason_code="lineage_not_closed",
            rationale=(
                "The declared lineage cannot be resolved without choosing between "
                "conflicting links."
            ),
        ),
        "uncertainty": _uncertainty(),
        "provenance": provenance,
        "evidence": evidence,
        "limitations": _limitations(),
        "human_review_required": False,
    }
    payload["result_digest"] = result_payload_digest(payload)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


def _finding(
    index: int,
    code: LineageFindingCode,
    message: str,
    artifacts: tuple[ArtifactReference, ...],
) -> LineageFinding:
    return LineageFinding(
        finding_id=f"finding.m2702.{index}",
        code=code,
        message=message,
        evidence=_evidence_for(artifacts),
    )


def _evidence(artifact: ArtifactReference, claim: str) -> EvidenceReference:
    return EvidenceReference(reference=artifact, role="evidence", claim=claim)


def _evidence_for(artifacts: tuple[ArtifactReference, ...]) -> tuple[EvidenceReference, ...]:
    return tuple(_evidence(artifact, "caller-declared lineage evidence") for artifact in artifacts)


def _uncertainty() -> UncertaintyProfile:
    unknown = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M27-02 records lineage and does not estimate biological uncertainty.",
    )
    return UncertaintyProfile(
        measurement=unknown,
        sampling=unknown,
        parameter=unknown,
        model_form=unknown,
        identification=unknown,
        support=unknown,
        transport=unknown,
        sensitivity_notes=("No biological or activity inference is performed.",),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="caller_declared_only",
            statement="Lineage is limited to immutable references supplied by the caller.",
        ),
        Limitation(
            code="no_parent_claim",
            statement=(
                "The module emits no complex-activity, protein, proteoform, isoform, "
                "or glioma claim."
            ),
        ),
    )


def _provenance(
    request: ResolveComplexActivityLineageRequest,
    request_hash: str,
) -> ProvenanceRecord:
    references = request.context.references
    decisions = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=references.approved_configuration.decision_id,
            state=references.approved_configuration.state.value,
            policy_version=references.approved_configuration.policy_version,
            evidence_digest=references.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=references.identity_lineage.decision_id,
            state=references.identity_lineage.state.value,
            policy_version=references.identity_lineage.policy_version,
            evidence_digest=references.identity_lineage.evidence.digest,
            subject_digest=references.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=references.provenance.decision_id,
            state=references.provenance.state.value,
            policy_version=references.provenance.policy_version,
            evidence_digest=references.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=references.consent.decision_id,
            state=references.consent.state.value,
            policy_version=references.consent.policy_version,
            evidence_digest=references.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=references.quality.decision_id,
            state=references.quality.state.value,
            policy_version=references.quality.policy_version,
            evidence_digest=references.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=references.support.decision_id,
            state=references.support.state.value,
            policy_version=references.support.policy_version,
            evidence_digest=references.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=references.intended_use.decision_id,
            state=references.intended_use.state.value,
            policy_version=references.intended_use.policy_version,
            evidence_digest=references.intended_use.evidence.digest,
        ),
    )
    return ProvenanceRecord(
        activity_id=f"activity.m2702.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M2702_MODULE_ID,
        module_version=M2702_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(artifact.digest for artifact in request.source_artifacts),
        configuration_digest=request_hash,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


def _member(candidate: object, field: str) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if dict in candidate_mro:
        return dict.get(cast("dict[object, object]", candidate), field)
    if BaseModel in candidate_mro:
        storage = object.__getattribute__(candidate, "__dict__")
        return dict.get(cast("dict[object, object]", storage), field)
    return None


def _state_text(candidate: object) -> object:
    candidate_type = type(candidate)
    if candidate_type is str:
        return candidate
    if candidate_type in _STATE_ENUMS[1:]:
        value = object.__getattribute__(candidate, "_value_")
        return value if type(value) is str else None
    return None


def _plain_value(candidate: object) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if BaseModel in candidate_mro:
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        return {key: _plain_value(dict.__getitem__(storage, key)) for key in dict.keys(storage)}
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        return {key: _plain_value(dict.__getitem__(mapping, key)) for key in dict.keys(mapping)}
    if list in candidate_mro:
        return [_plain_value(item) for item in cast("list[object]", candidate)]
    if tuple in candidate_mro:
        return tuple(_plain_value(item) for item in cast("tuple[object, ...]", candidate))
    return candidate


__all__ = [
    "M2702AuthorizationError",
    "M2702LineageResolver",
    "M2702ReplayError",
    "preflight_m2702_authorization",
    "resolve_complex_activity_lineage",
]
