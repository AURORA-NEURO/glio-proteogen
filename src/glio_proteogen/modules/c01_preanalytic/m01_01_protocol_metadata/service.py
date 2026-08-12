"""Deterministic orchestration for M01-01.

The service is the only layer that joins pure validation to the append-only ledger.  It
builds complete public envelopes from immutable inputs, uses caller-supplied event time,
and persists metadata findings without persisting submitted metadata values.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, Self

from pydantic import AwareDatetime, Field, TypeAdapter, ValidationError

from glio_proteogen.contracts.m01_01.canonical import (
    canonical_request_digest,
    metadata_document_digest,
    protocol_digest,
)
from glio_proteogen.contracts.m01_01.v1 import (
    M0101_SCOPE_LIMITATION_CODE,
    M0101_UNVERIFIED_CONTROLS_LIMITATION_CODE,
    ConformanceDecision,
    ConformanceIssue,
    ConformanceProfile,
    EvaluateMetadataRequest,
    IssueAction,
    IssueSeverity,
    M0101Output,
    M0101Request,
    MetadataDocument,
    ProtocolLookup,
    ProtocolReference,
    ProtocolSchema,
    ProtocolSchemaReceipt,
    RegisterProtocolRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.event_store import (
    ChainIntegrityError,
    ChainVerification,
    EventRecord,
    EventStoreError,
    EventType,
    IdempotencyConflictError,
    InvalidEventPayloadError,
    M0101EventStore,
    PayloadTooLargeError,
    ProtocolNotFoundError,
    ProtocolVersionConflictError,
    StoredProtocol,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.quality_consensus import (
    ConsensusStatus,
    LoadedQualityConsensus,
    QualityConsensusArtifactError,
    QualityConsensusAssessment,
    assess_quality_consensus,
    is_owned_quality_profile,
    load_packaged_quality_consensus,
    not_applicable_quality_assessment,
    unavailable_quality_assessment,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.validator import (
    ValidationReport,
    validate_metadata,
    validate_protocol_schema,
)

if TYPE_CHECKING:
    from types import TracebackType

MODULE_ID: Final = "GLIO-PROTEOGEN-M01-01"
MODULE_VERSION: Final[SemanticVersion] = "1.0.0"
EVENT_SCHEMA_VERSION: Final[SemanticVersion] = "1.0.0"
RECEIPT_VERSION: Final[SemanticVersion] = "1.0.0"
PROFILE_VERSION: Final[SemanticVersion] = "1.0.0"
_MAX_OUTPUT_LIMITATIONS: Final = 1_000
_MAX_OUTPUT_ISSUES: Final = 256
_REQUEST_ADAPTER: Final[TypeAdapter[RegisterProtocolRequest | EvaluateMetadataRequest]] = (
    TypeAdapter(M0101Request)
)
_REGISTER_ADAPTER: Final[TypeAdapter[RegisterProtocolRequest]] = TypeAdapter(
    RegisterProtocolRequest
)
_EVALUATE_ADAPTER: Final[TypeAdapter[EvaluateMetadataRequest]] = TypeAdapter(
    EvaluateMetadataRequest
)
_LOOKUP_ADAPTER: Final[TypeAdapter[ProtocolLookup]] = TypeAdapter(ProtocolLookup)


# Storage failures are intentionally part of the service error family.  Re-exporting the
# concrete types keeps API and CLI callers on one stable exception surface without wrapping
# away their useful conflict/not-found distinctions.
M0101ServiceError = EventStoreError


class ProtocolSchemaValidationError(EventStoreError):
    """A shape-valid protocol schema failed the module's semantic safety checks."""

    def __init__(self, issues: tuple[ConformanceIssue, ...]) -> None:
        self.issues = issues
        codes = ", ".join(sorted({issue.code for issue in issues}))
        detail = codes or "unspecified semantic failure"
        super().__init__(f"protocol schema failed semantic validation: {detail}")


class ConsentAuthorizationError(EventStoreError):
    """The supplied upstream consent decision does not authorize any processing."""

    def __init__(self, state: ConsentState) -> None:
        self.state = state
        super().__init__("consent decision does not authorize this operation")


class InvalidProtocolLookupError(EventStoreError):
    """A protocol lookup key failed the shared identifier/version contract."""

    def __init__(self) -> None:
        super().__init__("protocol lookup identifier or version is invalid")


class UpstreamControlAuthorizationError(EventStoreError):
    """A typed external control decision does not permit module execution."""

    def __init__(self, role: ControlRole) -> None:
        self.role = role
        super().__init__(f"upstream {role.value} decision does not authorize this operation")


class _RegistrationEventTypeError(ChainIntegrityError):
    def __init__(self) -> None:
        super().__init__("registration receipt references the wrong event type")


class _RegistrationPayloadError(ChainIntegrityError):
    def __init__(self) -> None:
        super().__init__("stored registration event payload is invalid")


class _EvaluationEventTypeError(ChainIntegrityError):
    def __init__(self) -> None:
        super().__init__("conformance profile references the wrong event type")


class _EvaluationPayloadError(ChainIntegrityError):
    def __init__(self) -> None:
        super().__init__("stored evaluation event payload is invalid")


class _ProjectionMismatchError(ChainIntegrityError):
    def __init__(self) -> None:
        super().__init__("registration receipt does not match the protocol projection")


class _LimitationCapacityError(EventStoreError):
    def __init__(self) -> None:
        super().__init__("declared limitations leave no room for the module safety ceiling")


def _verified_injected_consensus(
    candidate: LoadedQualityConsensus,
) -> LoadedQualityConsensus:
    packaged = load_packaged_quality_consensus()
    if candidate != packaged:
        raise QualityConsensusArtifactError
    return packaged


class _RegistrationEventPayload(FrozenModel):
    event_schema_version: Literal["1.0.0"] = "1.0.0"
    output_type: Literal["protocol_schema"] = "protocol_schema"
    receipt_version: SemanticVersion
    protocol: ProtocolReference
    protocol_schema: ProtocolSchema
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=256)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=1_000)


class _EvaluationEventPayload(FrozenModel):
    event_schema_version: Literal["1.0.0"] = "1.0.0"
    output_type: Literal["conformance_profile"] = "conformance_profile"
    profile_version: SemanticVersion
    protocol: ProtocolReference
    document_digest: Sha256Digest
    decision: ConformanceDecision
    support: SupportDecision
    issues: tuple[ConformanceIssue, ...] = Field(max_length=256)
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=256)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=1_000)
    human_review_required: bool
    evaluated_at: AwareDatetime


_MODULE_LIMITATIONS: Final = (
    Limitation(
        code=M0101_SCOPE_LIMITATION_CODE,
        statement=(
            "This output describes protocol and metadata conformance only; it is not a "
            "biological interpretation, clinical conclusion, or treatment recommendation."
        ),
    ),
    Limitation(
        code=M0101_UNVERIFIED_CONTROLS_LIMITATION_CODE,
        statement=(
            "External configuration, identity, provenance, consent, quality, support, and "
            "intended-use artifacts are caller-declared content references; this offline "
            "slice does not authenticate their issuer or resolve their contents."
        ),
    ),
)


class M0101Service:
    """Register immutable schemas and evaluate metadata against exact schema versions."""

    def __init__(
        self,
        store: M0101EventStore,
        quality_consensus: LoadedQualityConsensus | None = None,
    ) -> None:
        self._store = store
        loaded_consensus: LoadedQualityConsensus | None
        if quality_consensus is not None:
            try:
                loaded_consensus = _verified_injected_consensus(quality_consensus)
                self._quality_consensus_available = True
            except QualityConsensusArtifactError:
                loaded_consensus = None
                self._quality_consensus_available = False
        else:
            try:
                loaded_consensus = load_packaged_quality_consensus()
                self._quality_consensus_available = True
            except QualityConsensusArtifactError:
                loaded_consensus = None
                self._quality_consensus_available = False
        self._quality_consensus = loaded_consensus

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
        """Close the service-owned event store; repeated calls are harmless."""

        self._store.close()

    @staticmethod
    def validate_request(
        request: RegisterProtocolRequest | EvaluateMetadataRequest,
    ) -> RegisterProtocolRequest | EvaluateMetadataRequest:
        """Apply fail-closed pre-execution validation without mutating the request."""

        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        _require_granted_consent(validated.context)
        _require_accepted_controls(validated.context)
        if isinstance(validated, RegisterProtocolRequest):
            _require_valid_protocol_schema(validated.protocol_schema)
        return validated

    def execute(
        self,
        request: RegisterProtocolRequest | EvaluateMetadataRequest,
    ) -> M0101Output:
        """Dispatch one already shape-valid request through its closed operation union."""

        validated = self.validate_request(request)
        if isinstance(validated, RegisterProtocolRequest):
            return self.register(validated)
        return self.evaluate(validated)

    def register(self, request: RegisterProtocolRequest) -> ProtocolSchemaReceipt:
        """Validate and atomically register one immutable protocol schema."""

        request = _REGISTER_ADAPTER.validate_python(request, strict=True)
        _require_granted_consent(request.context)
        _require_accepted_controls(request.context)
        _require_valid_protocol_schema(request.protocol_schema)
        request_digest = canonical_request_digest(request)
        replay = self._store.find_replay(
            request_id=request.context.request_id,
            request_digest=request_digest,
            event_type=EventType.PROTOCOL_REGISTERED,
        )
        if replay is not None:
            return _receipt_from_event(replay)

        protocol = ProtocolReference(
            schema_id=request.protocol_schema.schema_id,
            version=request.protocol_schema.version,
            digest=protocol_digest(request.protocol_schema),
        )
        payload = _RegistrationEventPayload(
            receipt_version=RECEIPT_VERSION,
            protocol=protocol,
            protocol_schema=request.protocol_schema,
            support=_registration_support(),
            uncertainty=_registration_uncertainty(),
            provenance=_provenance(
                context=request.context,
                request_digest=request_digest,
                primary_digests=(protocol.digest,),
            ),
            evidence=_evidence(request.context),
            limitations=_limitations(request.protocol_schema),
        )
        event = self._store.register_protocol(
            request_id=request.context.request_id,
            request_digest=request_digest,
            occurred_at=request.context.occurred_at,
            schema=request.protocol_schema,
            payload=payload.model_dump(mode="python"),
        )
        return _receipt_from_event(event)

    def evaluate(self, request: EvaluateMetadataRequest) -> ConformanceProfile:
        """Evaluate a document without mutation or persistence of submitted values."""

        request = _EVALUATE_ADAPTER.validate_python(request, strict=True)
        _require_granted_consent(request.context)
        _require_accepted_controls(request.context)
        request_digest = canonical_request_digest(request)
        replay = self._store.find_replay(
            request_id=request.context.request_id,
            request_digest=request_digest,
            event_type=EventType.METADATA_EVALUATED,
        )
        if replay is not None:
            return _profile_from_event(replay)

        stored = self._store.get_protocol(
            request.protocol.schema_id,
            request.protocol.version,
            expected_digest=request.protocol.digest,
        )
        report = validate_metadata(
            stored.schema,
            request.document,
            consent_state=request.context.references.consent.state,
            expected_identity_binding_digest=(
                request.context.references.identity_lineage.binding_digest
            ),
        )
        quality = self._assess_reference_domain(stored.schema, request.document, report)
        report = _merge_quality_assessment(report, quality)
        document_digest = metadata_document_digest(request.document)
        quality_digests = tuple(
            digest
            for digest in (quality.model_digest, quality.corpus_digest)
            if quality.status is not ConsensusStatus.NOT_APPLICABLE and digest is not None
        )
        payload = _EvaluationEventPayload(
            profile_version=PROFILE_VERSION,
            protocol=stored.reference,
            document_digest=document_digest,
            decision=report.decision,
            support=_evaluation_support(report),
            issues=report.issues,
            uncertainty=_evaluation_uncertainty(report, quality),
            provenance=_provenance(
                context=request.context,
                request_digest=request_digest,
                primary_digests=(
                    stored.reference.digest,
                    document_digest,
                    *quality_digests,
                ),
            ),
            evidence=_evaluation_evidence(request.context, quality),
            limitations=_limitations(stored.schema),
            human_review_required=report.human_review_required,
            evaluated_at=request.context.occurred_at,
        )
        event = self._store.append_evaluation(
            request_id=request.context.request_id,
            request_digest=request_digest,
            occurred_at=request.context.occurred_at,
            protocol=stored.reference,
            payload=payload.model_dump(mode="python"),
        )
        return _profile_from_event(event)

    def _assess_reference_domain(
        self,
        schema: ProtocolSchema,
        document: MetadataDocument,
        report: ValidationReport,
    ) -> QualityConsensusAssessment:
        """Run the guard only after authorization and a conformant deterministic result."""

        if report.decision is not ConformanceDecision.CONFORMANT:
            return not_applicable_quality_assessment()
        loaded = self._quality_consensus
        if not self._quality_consensus_available or loaded is None:
            return (
                unavailable_quality_assessment()
                if is_owned_quality_profile(schema)
                else not_applicable_quality_assessment()
            )
        try:
            return assess_quality_consensus(schema, document, loaded)
        except QualityConsensusArtifactError:
            return unavailable_quality_assessment()

    def get_protocol(self, schema_id: str, version: str) -> ProtocolSchemaReceipt:
        """Return the content and original receipt envelope for one protocol version."""

        try:
            lookup = _LOOKUP_ADAPTER.validate_python(
                {"schema_id": schema_id, "version": version},
                strict=True,
            )
        except ValidationError as error:
            raise InvalidProtocolLookupError from error
        stored = self._store.get_protocol(lookup.schema_id, lookup.version)
        receipt = _receipt_from_event(stored.registration_event)
        _assert_receipt_matches_projection(receipt, stored)
        return receipt

    def verify_event_chain(self) -> ChainVerification:
        """Verify the complete event chain and immutable protocol projection."""

        return self._store.verify_event_chain()


def _require_valid_protocol_schema(schema: ProtocolSchema) -> None:
    report = validate_protocol_schema(schema)
    if report.decision is not ConformanceDecision.CONFORMANT:
        raise ProtocolSchemaValidationError(report.issues)


def _merge_quality_assessment(
    report: ValidationReport,
    assessment: QualityConsensusAssessment,
) -> ValidationReport:
    """Add only a generic abstention issue; reference details remain internal evidence."""

    if assessment.status in {ConsensusStatus.IN_DOMAIN, ConsensusStatus.NOT_APPLICABLE}:
        return report
    messages = {
        ConsensusStatus.OUT_OF_DOMAIN: (
            "Declared metadata is outside the locked synthetic reference-domain envelope."
        ),
        ConsensusStatus.INDETERMINATE: (
            "Reference-domain proximity is indeterminate from the declared metadata."
        ),
        ConsensusStatus.UNAVAILABLE: (
            "Reference-domain proximity evidence is unavailable; quarantine-first fallback applies."
        ),
    }
    issue = ConformanceIssue(
        code=assessment.reason_code,
        path="/entries",
        severity=IssueSeverity.CRITICAL,
        action=IssueAction.QUARANTINE,
        message=messages[assessment.status],
    )
    if len(report.issues) >= _MAX_OUTPUT_ISSUES:
        return report
    issues = tuple(
        sorted(
            (*report.issues, issue),
            key=lambda item: (
                item.code,
                item.path,
                item.severity.value,
                item.action.value,
                item.message,
            ),
        )
    )
    return ValidationReport(
        decision=ConformanceDecision.QUARANTINED,
        issues=issues,
        human_review_required=True,
    )


def _require_granted_consent(context: ExecutionContext) -> None:
    state = context.references.consent.state
    if state is not ConsentState.GRANTED:
        raise ConsentAuthorizationError(state)


def _require_accepted_controls(context: ExecutionContext) -> None:
    references = context.references
    decisions = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration.state),
        (ControlRole.PROVENANCE, references.provenance.state),
        (ControlRole.QUALITY, references.quality.state),
        (ControlRole.SUPPORT, references.support.state),
        (ControlRole.INTENDED_USE, references.intended_use.state),
    )
    for role, state in decisions:
        if state is not UpstreamDecisionState.ACCEPTED:
            raise UpstreamControlAuthorizationError(role)
    if references.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise UpstreamControlAuthorizationError(ControlRole.IDENTITY_LINEAGE)


def _registration_support() -> SupportDecision:
    return SupportDecision(
        status=SupportStatus.LIMITED,
        reason_code="protocol_schema_structurally_valid",
        rationale=(
            "The protocol schema passed M01-01 structural and semantic checks, but the "
            "caller-declared external control references were not authenticated."
        ),
    )


def _evaluation_support(report: ValidationReport) -> SupportDecision:
    if report.decision is ConformanceDecision.CONFORMANT:
        return SupportDecision(
            status=SupportStatus.LIMITED,
            reason_code="metadata_structurally_conformant",
            rationale=(
                "The document conforms structurally within the registered M01-01 protocol, "
                "but external control references were not authenticated."
            ),
        )
    if report.decision is ConformanceDecision.NONCONFORMANT:
        return SupportDecision(
            status=SupportStatus.UNSUPPORTED,
            reason_code="metadata_nonconformant",
            rationale="One or more protocol requirements are not satisfied.",
        )
    if report.decision is ConformanceDecision.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="metadata_quarantined",
            rationale="The document must remain quarantined pending explicit review.",
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="metadata_review_required",
        rationale="The declared compatibility policy requires human review.",
    )


def _registration_uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        measurement=_not_applicable(
            "Schema registration does not measure a specimen or biological quantity."
        ),
        sampling=_not_applicable("Schema registration does not perform specimen sampling."),
        parameter=_not_applicable("Schema registration fits no statistical parameters."),
        model_form=_not_applicable("Schema registration uses no predictive model."),
        identification=_not_estimable(
            "Identity lineage is caller-declared, is not authenticated here, and is never inferred."
        ),
        support=_not_estimable(
            "Registration support is a deterministic rules result, not a probability estimate."
        ),
        transport=_not_estimable(
            "Transportability beyond the declared schema versions is not estimated."
        ),
        sensitivity_notes=(
            "A successful receipt establishes schema conformance only, not downstream validity.",
        ),
    )


def _evaluation_uncertainty(
    report: ValidationReport,
    quality: QualityConsensusAssessment,
) -> UncertaintyProfile:
    issue_note = (
        "No conformance issues were emitted."
        if not report.issues
        else f"The deterministic evaluator emitted {len(report.issues)} typed issue(s)."
    )
    quality_note = (
        "The frozen synthetic reference-domain guard was not applicable to this protocol."
        if quality.status is ConsensusStatus.NOT_APPLICABLE
        else (
            "The frozen synthetic reference-domain guard is deterministic and uncalibrated; "
            "its proximity and agreement aggregates are not probabilities or biological quality."
        )
    )
    model_form = (
        _not_applicable("No reference-domain guard applies to this protocol schema.")
        if quality.status is ConsensusStatus.NOT_APPLICABLE
        else _not_estimable(
            "Reference-domain model-form uncertainty is not calibrated from the synthetic corpus."
        )
    )
    return UncertaintyProfile(
        measurement=_not_estimable(
            "M01-01 validates measurement metadata but does not estimate measurement error."
        ),
        sampling=_not_estimable(
            "Sampling uncertainty cannot be estimated from the metadata declaration alone."
        ),
        parameter=_not_applicable("The conformance algorithm fits no statistical parameters."),
        model_form=model_form,
        identification=_not_estimable(
            "Identity lineage is caller-declared, is not authenticated here, and is never inferred."
        ),
        support=_not_estimable(
            "Support is a deterministic policy decision, not a calibrated probability."
        ),
        transport=_not_estimable(
            "Transportability beyond the registered assay and specimen versions is not estimated."
        ),
        sensitivity_notes=(issue_note, quality_note),
    )


def _not_applicable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_APPLICABLE, rationale=rationale)


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _evidence(context: ExecutionContext) -> tuple[EvidenceReference, ...]:
    references = context.references
    declared: tuple[tuple[ArtifactReference, str], ...] = (
        (
            references.approved_configuration.evidence,
            "Caller-declared approved-configuration reference; issuer not authenticated here.",
        ),
        (references.identity_lineage.evidence, "Caller-declared identity-lineage reference."),
        (references.provenance.evidence, "Caller-declared upstream-provenance reference."),
        (references.consent.evidence, "Caller-declared consent-decision evidence reference."),
        (references.quality.evidence, "Caller-declared upstream-quality reference."),
        (references.support.evidence, "Caller-declared upstream-support reference."),
        (
            references.intended_use.evidence,
            "Caller-declared intended-use evidence reference.",
        ),
    )
    return tuple(
        EvidenceReference(reference=reference, role="evidence", claim=claim)
        for reference, claim in declared
    )


def _evaluation_evidence(
    context: ExecutionContext,
    quality: QualityConsensusAssessment,
) -> tuple[EvidenceReference, ...]:
    declared = _evidence(context)
    if (
        quality.status is ConsensusStatus.NOT_APPLICABLE
        or quality.model_id is None
        or quality.model_version is None
        or quality.model_digest is None
        or quality.corpus_id is None
        or quality.corpus_version is None
        or quality.corpus_digest is None
    ):
        return declared
    model = EvidenceReference(
        reference=ArtifactReference(
            artifact_id=quality.model_id,
            version=quality.model_version,
            digest=quality.model_digest,
            media_type="application/vnd.glio-proteogen.quality-model+json",
        ),
        role="evidence",
        claim="Frozen synthetic reference-domain guard used for abstention only.",
    )
    corpus = EvidenceReference(
        reference=ArtifactReference(
            artifact_id=quality.corpus_id,
            version=quality.corpus_version,
            digest=quality.corpus_digest,
            media_type="application/vnd.glio-proteogen.quality-reference-corpus+json",
        ),
        role="evidence",
        claim="Synthetic non-clinical reference features used for proximity support.",
    )
    return (*declared, model, corpus)


def _limitations(schema: ProtocolSchema) -> tuple[Limitation, ...]:
    declared = {limitation.code: limitation for limitation in schema.limitations}
    ordered_declared = tuple(declared[code] for code in sorted(declared))
    additions = tuple(
        limitation for limitation in _MODULE_LIMITATIONS if limitation.code not in declared
    )
    combined = (*ordered_declared, *additions)
    if len(combined) > _MAX_OUTPUT_LIMITATIONS:
        raise _LimitationCapacityError
    return combined


def _control_decisions(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    references = context.references
    generic = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    records = [
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=decision.state.value,
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
        )
        for role, decision in generic
    ]
    records.extend(
        (
            ControlDecisionRecord(
                role=ControlRole.IDENTITY_LINEAGE,
                decision_id=references.identity_lineage.decision_id,
                state=references.identity_lineage.state.value,
                policy_version=references.identity_lineage.policy_version,
                evidence_digest=references.identity_lineage.evidence.digest,
                subject_digest=references.identity_lineage.binding_digest,
            ),
            ControlDecisionRecord(
                role=ControlRole.CONSENT,
                decision_id=references.consent.decision_id,
                state=references.consent.state.value,
                policy_version=references.consent.policy_version,
                evidence_digest=references.consent.evidence.digest,
            ),
        )
    )
    return tuple(sorted(records, key=lambda record: record.role.value))


def _provenance(
    *,
    context: ExecutionContext,
    request_digest: Sha256Digest,
    primary_digests: tuple[Sha256Digest, ...],
) -> ProvenanceRecord:
    references = context.references
    ordered = (
        request_digest,
        *primary_digests,
        references.identity_lineage.evidence.digest,
        references.provenance.evidence.digest,
        references.consent.evidence.digest,
        references.quality.evidence.digest,
        references.support.evidence.digest,
        references.intended_use.evidence.digest,
    )
    input_digests = tuple(dict.fromkeys(ordered))
    return ProvenanceRecord(
        activity_id=f"activity.m0101.{request_digest.removeprefix('sha256:')}",
        actor_id=context.actor_id,
        module_id=MODULE_ID,
        module_version=MODULE_VERSION,
        generated_at=context.occurred_at,
        input_digests=input_digests,
        configuration_digest=references.approved_configuration.evidence.digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=_control_decisions(context),
    )


def _receipt_from_event(event: EventRecord) -> ProtocolSchemaReceipt:
    if event.event_type is not EventType.PROTOCOL_REGISTERED:
        raise _RegistrationEventTypeError
    try:
        payload = _RegistrationEventPayload.model_validate_json(
            canonical_json_bytes(event.payload),
            strict=True,
        )
    except (TypeError, ValueError, ValidationError) as error:
        raise _RegistrationPayloadError from error
    return ProtocolSchemaReceipt(
        receipt_version=payload.receipt_version,
        protocol=payload.protocol,
        protocol_schema=payload.protocol_schema,
        event_digest=event.event_digest,
        support=payload.support,
        uncertainty=payload.uncertainty,
        provenance=payload.provenance,
        evidence=payload.evidence,
        limitations=payload.limitations,
    )


def _profile_from_event(event: EventRecord) -> ConformanceProfile:
    if event.event_type is not EventType.METADATA_EVALUATED:
        raise _EvaluationEventTypeError
    try:
        payload = _EvaluationEventPayload.model_validate_json(
            canonical_json_bytes(event.payload),
            strict=True,
        )
    except (TypeError, ValueError, ValidationError) as error:
        raise _EvaluationPayloadError from error
    return ConformanceProfile(
        profile_version=payload.profile_version,
        protocol=payload.protocol,
        document_digest=payload.document_digest,
        decision=payload.decision,
        support=payload.support,
        issues=payload.issues,
        uncertainty=payload.uncertainty,
        provenance=payload.provenance,
        evidence=payload.evidence,
        limitations=payload.limitations,
        human_review_required=payload.human_review_required,
        event_digest=event.event_digest,
        evaluated_at=payload.evaluated_at,
    )


def _assert_receipt_matches_projection(
    receipt: ProtocolSchemaReceipt,
    stored: StoredProtocol,
) -> None:
    if receipt.protocol != stored.reference or receipt.protocol_schema != stored.schema:
        raise _ProjectionMismatchError


__all__ = [
    "ChainIntegrityError",
    "ConsentAuthorizationError",
    "IdempotencyConflictError",
    "InvalidEventPayloadError",
    "InvalidProtocolLookupError",
    "M0101Service",
    "M0101ServiceError",
    "PayloadTooLargeError",
    "ProtocolNotFoundError",
    "ProtocolSchemaValidationError",
    "ProtocolVersionConflictError",
    "UpstreamControlAuthorizationError",
]
