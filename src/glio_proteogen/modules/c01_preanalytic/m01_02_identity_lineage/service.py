"""Fail-closed orchestration for M01-02 identity and lineage reconciliation.

The solver owns pure reconciliation semantics.  This service owns authorization,
idempotent replay, the public evidence/provenance envelope, and ledger commitment.
Submitted identity tokens, demultiplex tags, and entity evidence never enter the
service-owned envelope.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol, Self

from pydantic import AwareDatetime, Field, TypeAdapter, ValidationError, model_validator

from glio_proteogen.contracts.m01_02.canonical import (
    canonical_request_digest,
    evidence_manifest_digest,
    resolution_payload_digest,
)
from glio_proteogen.contracts.m01_02.v1 import (
    M0102_AUTHORITY_LIMITATION_CODE,
    M0102_IDENTITY_LIMITATION_CODE,
    M0102_MAX_ASSERTIONS,
    M0102_MAX_ENTITIES,
    M0102_MAX_ISSUES,
    M0102_MODULE_VERSION,
    AssertionDisposition,
    ConcordanceAggregate,
    IdentityComponent,
    IdentityControlDecisionRecord,
    IdentityControlRole,
    IdentityExecutionContext,
    IdentityIssue,
    IdentityLineageResolution,
    IdentityLineageResolutionDraft,
    IdentityProvenanceRecord,
    ReconcileIdentityLineageRequest,
    ResolutionDecision,
    ResolvedLineageGraph,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ConsentState,
    EstimateState,
    EvidenceReference,
    FrozenModel,
    Identifier,
    Limitation,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    ChainIntegrityError,
    ChainVerification,
    EventRecord,
    EventType,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.solver import (
    reconcile_identity_lineage,
)

if TYPE_CHECKING:
    from types import TracebackType

MODULE_ID: Final = "GLIO-PROTEOGEN-M01-02"
MODULE_VERSION: Final[SemanticVersion] = M0102_MODULE_VERSION
_DERIVED_DIGEST_SENTINEL: Final[Sha256Digest] = "sha256:" + ("0" * 64)
_REQUEST_ADAPTER: Final[TypeAdapter[ReconcileIdentityLineageRequest]] = TypeAdapter(
    ReconcileIdentityLineageRequest
)
_DRAFT_ADAPTER: Final[TypeAdapter[IdentityLineageResolutionDraft]] = TypeAdapter(
    IdentityLineageResolutionDraft
)
_OUTPUT_ADAPTER: Final[TypeAdapter[IdentityLineageResolution]] = TypeAdapter(
    IdentityLineageResolution
)


class ResolutionEventStore(Protocol):
    """Minimal ledger boundary required by the service."""

    def find_replay(
        self,
        *,
        request_id: Identifier,
        request_digest: Sha256Digest,
    ) -> EventRecord | None: ...

    def append_resolution(  # noqa: PLR0913 - exact ledger protocol
        self,
        *,
        request_id: Identifier,
        request_digest: Sha256Digest,
        occurred_at: AwareDatetime,
        core_digest: Sha256Digest,
        resolution_digest: Sha256Digest,
        supersedes_resolution_digest: Sha256Digest | None,
        payload: dict[str, Any],
    ) -> EventRecord: ...

    def get_resolution(self, resolution_digest: Sha256Digest) -> EventRecord: ...

    def verify_event_chain(self) -> ChainVerification: ...

    def close(self) -> None: ...


class IdentityLineageAuthorizationError(RuntimeError):
    """An upstream control does not authorize identity reconciliation."""

    def __init__(self, role: IdentityControlRole) -> None:
        self.role = role
        super().__init__(f"upstream {role.value} decision does not authorize reconciliation")


class InvalidResolutionEventError(ChainIntegrityError):
    """A replayed or newly appended event cannot materialize the public contract."""


class _ResolutionDigestMismatchError(ValueError):
    def __init__(self) -> None:
        super().__init__("resolution event payload digest does not match its content")


class _WrongEventTypeError(InvalidResolutionEventError):
    def __init__(self) -> None:
        super().__init__("identity resolution references the wrong event type")


class _RequestBindingError(InvalidResolutionEventError):
    def __init__(self) -> None:
        super().__init__("identity resolution event does not bind the request")


class _EmbeddedEventDigestError(InvalidResolutionEventError):
    def __init__(self) -> None:
        super().__init__("stored resolution embeds its event digest")


class _InvalidPublicResolutionError(InvalidResolutionEventError):
    def __init__(self) -> None:
        super().__init__("identity resolution event violates the public contract")


class _EventKeyMismatchError(InvalidResolutionEventError):
    def __init__(self) -> None:
        super().__init__("identity resolution event keys contradict its payload")


class _ResolutionEventPayload(FrozenModel):
    """Persisted public envelope, intentionally excluding the chained event digest."""

    output_type: Literal["identity_lineage_resolution"] = "identity_lineage_resolution"
    resolution_id: Identifier
    resolution_version: SemanticVersion
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    core_digest: Sha256Digest
    resolution_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    decision: ResolutionDecision
    components: tuple[IdentityComponent, ...] = Field(
        min_length=1,
        max_length=M0102_MAX_ENTITIES,
    )
    graph: ResolvedLineageGraph
    assertion_dispositions: tuple[AssertionDisposition, ...] = Field(
        default=(),
        max_length=M0102_MAX_ASSERTIONS,
    )
    concordance: ConcordanceAggregate
    issues: tuple[IdentityIssue, ...] = Field(default=(), max_length=M0102_MAX_ISSUES)
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: IdentityProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=7, max_length=7)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    resolved_at: AwareDatetime
    supersedes_resolution_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def resolution_digest_matches_public_payload(self) -> _ResolutionEventPayload:
        expected = resolution_payload_digest(self)
        if self.resolution_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "resolution_digest", expected)
        elif self.resolution_digest != expected:
            raise _ResolutionDigestMismatchError
        return self


_MODULE_LIMITATIONS: Final = (
    Limitation(
        code=M0102_IDENTITY_LIMITATION_CODE,
        statement=(
            "This output reconciles pseudonymous identity and lineage only; it is not a "
            "direct identity, biological interpretation, clinical conclusion, or treatment "
            "recommendation."
        ),
    ),
    Limitation(
        code=M0102_AUTHORITY_LIMITATION_CODE,
        statement=(
            "The seven upstream control references are caller-declared content references; "
            "this offline module does not authenticate their issuers or resolve their content."
        ),
    ),
)


class M0102Service:
    """Authorize, reconcile, envelope, and commit one deterministic request."""

    __slots__ = ("_store",)

    def __init__(self, store: ResolutionEventStore) -> None:
        self._store = store

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the service-owned ledger; repeated calls follow the store contract."""

        self._store.close()

    @staticmethod
    def validate_request(request: object) -> ReconcileIdentityLineageRequest:
        """Revalidate the closed contract and fail before request hashing or execution."""

        _require_authorized_untrusted(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        _require_authorized(validated.context)
        return validated

    def execute(self, request: object) -> IdentityLineageResolution:
        """Execute an authorized request with exact-once deterministic replay."""

        validated = self.validate_request(request)
        request_digest = canonical_request_digest(validated)
        replay = self._store.find_replay(
            request_id=validated.context.request_id,
            request_digest=request_digest,
        )
        if replay is not None:
            return _resolution_from_event(
                replay,
                expected_request_id=validated.context.request_id,
                expected_request_digest=request_digest,
            )

        draft = reconcile_identity_lineage(validated)
        payload = _resolution_payload(draft, validated)
        event = self._store.append_resolution(
            request_id=validated.context.request_id,
            request_digest=request_digest,
            occurred_at=validated.context.occurred_at,
            core_digest=payload.core_digest,
            resolution_digest=payload.resolution_digest,
            supersedes_resolution_digest=payload.supersedes_resolution_digest,
            payload=payload.model_dump(mode="python"),
        )
        return _resolution_from_event(
            event,
            expected_request_id=validated.context.request_id,
            expected_request_digest=request_digest,
        )

    def get_resolution(
        self,
        resolution_digest: Sha256Digest,
    ) -> IdentityLineageResolution:
        """Retrieve and fully revalidate one committed public resolution."""

        event = self._store.get_resolution(resolution_digest)
        return _resolution_from_event(
            event,
            expected_request_id=event.request_id,
            expected_request_digest=event.request_digest,
        )

    def verify_event_chain(self) -> ChainVerification:
        """Delegate exhaustive append-only chain verification to the ledger."""

        return self._store.verify_event_chain()


def preflight_identity_authorization(request: object) -> None:
    """Reject an explicitly denied raw request before relational validation or hashing."""

    _require_authorized_untrusted(request)


def _resolution_payload(
    draft: IdentityLineageResolutionDraft,
    request: ReconcileIdentityLineageRequest,
) -> _ResolutionEventPayload:
    """Build the persistable envelope without inventing a ledger event digest."""

    draft = _DRAFT_ADAPTER.validate_python(draft, strict=True)
    return _ResolutionEventPayload(
        resolution_id=draft.resolution_id,
        resolution_version=draft.resolution_version,
        request_digest=draft.request_digest,
        policy_digest=draft.policy_digest,
        core_digest=draft.core_digest,
        decision=draft.decision,
        components=draft.components,
        graph=draft.graph,
        assertion_dispositions=draft.assertion_dispositions,
        concordance=draft.concordance,
        issues=draft.issues,
        support=_support(draft.decision),
        uncertainty=_uncertainty(),
        provenance=_provenance(draft, request),
        evidence=_control_evidence(request.context),
        limitations=_MODULE_LIMITATIONS,
        human_review_required=draft.human_review_required,
        resolved_at=draft.resolved_at,
        supersedes_resolution_digest=draft.supersedes_resolution_digest,
    )


def _resolution_from_event(
    event: EventRecord,
    *,
    expected_request_id: Identifier,
    expected_request_digest: Sha256Digest,
) -> IdentityLineageResolution:
    if event.event_type is not EventType.RESOLUTION_COMMITTED:
        raise _WrongEventTypeError
    if (
        event.request_id != expected_request_id
        or event.request_digest != expected_request_digest
    ):
        raise _RequestBindingError
    if "event_digest" in event.payload:
        raise _EmbeddedEventDigestError
    candidate = {**event.payload, "event_digest": event.event_digest}
    try:
        resolution = _OUTPUT_ADAPTER.validate_json(
            canonical_json_bytes(candidate),
            strict=True,
        )
    except (TypeError, ValueError, ValidationError) as error:
        raise _InvalidPublicResolutionError from error
    if (
        resolution.core_digest != event.core_digest
        or resolution.resolution_digest != event.resolution_digest
    ):
        raise _EventKeyMismatchError
    return resolution


def _support(decision: ResolutionDecision) -> SupportDecision:
    status, reason_code, rationale = {
        ResolutionDecision.RESOLVED: (
            SupportStatus.LIMITED,
            "identity_lineage_resolved",
            "Explicit authority-bound assertions and valid lineage operations were resolved.",
        ),
        ResolutionDecision.UNRESOLVED: (
            SupportStatus.REVIEW_REQUIRED,
            "identity_lineage_unresolved",
            "At least one ambiguity remains unresolved and must not be treated as negative.",
        ),
        ResolutionDecision.CONFLICTED: (
            SupportStatus.UNSUPPORTED,
            "identity_lineage_conflicted",
            "Contradictory identity or lineage evidence prevents a supported resolution.",
        ),
        ResolutionDecision.QUARANTINED: (
            SupportStatus.REVIEW_REQUIRED,
            "identity_lineage_quarantined",
            "A fail-closed identity or lineage boundary requires quarantine and review.",
        ),
    }[decision]
    return SupportDecision(status=status, reason_code=reason_code, rationale=rationale)


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        measurement=_not_estimable(
            "M01-02 consumes declarations and aggregates but does not estimate measurement error."
        ),
        sampling=_not_estimable(
            "The submitted lineage graph does not identify a calibrated sampling distribution."
        ),
        parameter=_not_estimable(
            "The deterministic reconciliation policy fits no probabilistic parameters."
        ),
        model_form=_not_estimable(
            "No predictive model is used, so model-form uncertainty is not calibrated."
        ),
        identification=_not_estimable(
            "Identity is accepted only from explicit authority decisions; residual ambiguity "
            "is represented as unresolved or quarantined, not a probability."
        ),
        support=_not_estimable(
            "Support is a typed deterministic policy result, not a calibrated confidence."
        ),
        transport=_not_estimable(
            "Transportability outside the bound policy, authority, namespace, and issuer scope "
            "is not estimated."
        ),
        sensitivity_notes=(
            "Concordance aggregates may downgrade or quarantine but never authorize a merge.",
            "Missing or ambiguous evidence is preserved as unknown rather than negative.",
        ),
    )


def _control_records(
    context: IdentityExecutionContext,
) -> tuple[IdentityControlDecisionRecord, ...]:
    references = context.references
    generic = (
        (IdentityControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (IdentityControlRole.PROVENANCE, references.provenance),
        (IdentityControlRole.QUALITY, references.quality),
        (IdentityControlRole.SUPPORT, references.support),
        (IdentityControlRole.INTENDED_USE, references.intended_use),
    )
    records = [
        IdentityControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
        )
        for role, reference in generic
    ]
    records.extend(
        (
            IdentityControlDecisionRecord(
                role=IdentityControlRole.IDENTITY_AUTHORITY,
                decision_id=references.identity_authority.decision_id,
                state=references.identity_authority.state.value,
                policy_version=references.identity_authority.policy_version,
                evidence_digest=references.identity_authority.evidence.digest,
            ),
            IdentityControlDecisionRecord(
                role=IdentityControlRole.CONSENT,
                decision_id=references.consent.decision_id,
                state=references.consent.state.value,
                policy_version=references.consent.policy_version,
                evidence_digest=references.consent.evidence.digest,
            ),
        )
    )
    return tuple(sorted(records, key=lambda record: record.role.value))


def _provenance(
    draft: IdentityLineageResolutionDraft,
    request: ReconcileIdentityLineageRequest,
) -> IdentityProvenanceRecord:
    context = request.context
    references = context.references
    controls = _control_records(context)
    manifest_digest = evidence_manifest_digest(request)
    input_digests = tuple(
        dict.fromkeys(
            (
                draft.request_digest,
                draft.policy_digest,
                draft.core_digest,
                draft.graph.graph_digest,
                manifest_digest,
                *(record.evidence_digest for record in controls),
            )
        )
    )
    return IdentityProvenanceRecord(
        activity_id=f"activity.m0102.{draft.request_digest.removeprefix('sha256:')}",
        actor_id=context.actor_id,
        module_version=MODULE_VERSION,
        generated_at=context.occurred_at,
        input_digests=input_digests,
        evidence_manifest_digest=manifest_digest,
        configuration_digest=references.approved_configuration.evidence.digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _control_evidence(
    context: IdentityExecutionContext,
) -> tuple[EvidenceReference, ...]:
    references = context.references
    declared = (
        (
            IdentityControlRole.APPROVED_CONFIGURATION,
            references.approved_configuration.evidence,
        ),
        (IdentityControlRole.IDENTITY_AUTHORITY, references.identity_authority.evidence),
        (IdentityControlRole.PROVENANCE, references.provenance.evidence),
        (IdentityControlRole.CONSENT, references.consent.evidence),
        (IdentityControlRole.QUALITY, references.quality.evidence),
        (IdentityControlRole.SUPPORT, references.support.evidence),
        (IdentityControlRole.INTENDED_USE, references.intended_use.evidence),
    )
    return tuple(
        EvidenceReference(
            reference=reference,
            role="evidence",
            claim=(
                f"Caller-declared {role.value.replace('_', '-')} control reference; "
                "issuer and content are not authenticated by M01-02."
            ),
        )
        for role, reference in declared
    )


def _reference_state(reference: object) -> object:
    if isinstance(reference, Mapping):
        return reference.get("state")
    return getattr(reference, "state", None)


def _references_from_untrusted(request: object) -> object | None:
    if isinstance(request, Mapping):
        context = request.get("context")
    else:
        context = getattr(request, "context", None)
    if isinstance(context, Mapping):
        return context.get("references")
    return getattr(context, "references", None)


def _control_from_untrusted(references: object, role: IdentityControlRole) -> object:
    if isinstance(references, Mapping):
        return references.get(role.value)
    return getattr(references, role.value, None)


def _state_matches(value: object, expected: ConsentState | UpstreamDecisionState) -> bool:
    return value is expected or value == expected.value


def _require_authorized_untrusted(request: object) -> None:
    references = _references_from_untrusted(request)
    if references is None:
        return
    required: tuple[
        tuple[IdentityControlRole, ConsentState | UpstreamDecisionState], ...
    ] = (
        (IdentityControlRole.CONSENT, ConsentState.GRANTED),
        (IdentityControlRole.IDENTITY_AUTHORITY, UpstreamDecisionState.ACCEPTED),
        (IdentityControlRole.APPROVED_CONFIGURATION, UpstreamDecisionState.ACCEPTED),
        (IdentityControlRole.PROVENANCE, UpstreamDecisionState.ACCEPTED),
        (IdentityControlRole.QUALITY, UpstreamDecisionState.ACCEPTED),
        (IdentityControlRole.SUPPORT, UpstreamDecisionState.ACCEPTED),
        (IdentityControlRole.INTENDED_USE, UpstreamDecisionState.ACCEPTED),
    )
    for role, expected in required:
        reference = _control_from_untrusted(references, role)
        state = _reference_state(reference)
        if state is not None and not _state_matches(state, expected):
            raise IdentityLineageAuthorizationError(role)


def _require_authorized(context: IdentityExecutionContext) -> None:
    references = context.references
    if references.consent.state is not ConsentState.GRANTED:
        raise IdentityLineageAuthorizationError(IdentityControlRole.CONSENT)
    if references.identity_authority.state is not UpstreamDecisionState.ACCEPTED:
        raise IdentityLineageAuthorizationError(IdentityControlRole.IDENTITY_AUTHORITY)
    generic = (
        (IdentityControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (IdentityControlRole.PROVENANCE, references.provenance),
        (IdentityControlRole.QUALITY, references.quality),
        (IdentityControlRole.SUPPORT, references.support),
        (IdentityControlRole.INTENDED_USE, references.intended_use),
    )
    for role, reference in generic:
        if reference.state is not UpstreamDecisionState.ACCEPTED:
            raise IdentityLineageAuthorizationError(role)


__all__ = [
    "IdentityLineageAuthorizationError",
    "InvalidResolutionEventError",
    "M0102Service",
    "ResolutionEventStore",
    "preflight_identity_authorization",
]
