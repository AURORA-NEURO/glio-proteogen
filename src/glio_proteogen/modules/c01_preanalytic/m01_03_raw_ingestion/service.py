"""Stateless orchestration for bounded M01-03 raw-input admission.

The parser owns byte decoding and structural checks.  This service owns authorization, exact
batch closure, declaration/policy reconciliation, and the public metadata-only envelope.  Raw
source bytes are held only by the caller and local execution variables; they are never stored on
the service or copied into diagnostics, provenance, evidence, or results.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import BinaryIO, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_03 import (
    DiagnosticAction,
    DiagnosticSeverity,
    IngestRawInputsRequest,
    ParseDiagnostic,
    RawIngestionResult,
    RawInputDisposition,
    RawSourceDescriptor,
    ValidatedRawInputDescriptor,
    canonical_request_digest,
    policy_digest,
)
from glio_proteogen.contracts.m01_03.v1 import (
    M0103_AUTHORITY_LIMITATION_CODE,
    M0103_CONTRACT_VERSION,
    M0103_MODULE_ID,
    M0103_RAW_LIMITATION_CODE,
)
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion.parser import (
    DEFAULT_REGISTRY,
    IngestionLimits,
    ParserRegistry,
    parse_raw_input,
)

type RawInputSource = bytes | bytearray | memoryview | BinaryIO

_REQUEST_ADAPTER: Final[TypeAdapter[IngestRawInputsRequest]] = TypeAdapter(
    IngestRawInputsRequest
)
_RAW_INPUT_ADAPTER: Final[TypeAdapter[ValidatedRawInputDescriptor]] = TypeAdapter(
    ValidatedRawInputDescriptor
)
_MAX_FILENAME_BYTES: Final = 1024

_MODULE_LIMITATIONS: Final = (
    Limitation(
        code=M0103_RAW_LIMITATION_CODE,
        statement=(
            "This result reports bounded raw-format admission only; it does not interpret "
            "measurements, molecular state, clinical meaning, or treatment options."
        ),
    ),
    Limitation(
        code=M0103_AUTHORITY_LIMITATION_CODE,
        statement=(
            "Upstream controls and source artifacts are caller-declared content references; "
            "M01-03 does not authenticate their issuers or independently resolve their content."
        ),
    ),
)

_DIAGNOSTIC_MESSAGES: Final = {
    "detected_format_disabled": "The detected content format is disabled by the active policy.",
    "detected_compression_disabled": (
        "The detected compression is disabled by the active policy."
    ),
    "declared_size_mismatch": "The supplied byte length disagrees with its declaration.",
    "declared_format_mismatch": "The detected content format disagrees with its declaration.",
    "declared_version_mismatch": "The detected format version disagrees with its declaration.",
    "declared_compression_mismatch": (
        "The detected compression disagrees with its declaration."
    ),
}


class RawIngestionInputErrorCode(StrEnum):
    """Stable reasons a batch cannot safely reach the byte parser."""

    SOURCE_SET_MISMATCH = "source_set_mismatch"
    FILENAME_SET_MISMATCH = "filename_set_mismatch"
    INVALID_SOURCE = "invalid_source"
    INVALID_FILENAME = "invalid_filename"
    TOTAL_INPUT_LIMIT_EXCEEDED = "total_input_limit_exceeded"


_INPUT_ERROR_MESSAGES: Final = {
    RawIngestionInputErrorCode.SOURCE_SET_MISMATCH: (
        "supplied raw sources must exactly match the request"
    ),
    RawIngestionInputErrorCode.FILENAME_SET_MISMATCH: (
        "filename hints may reference only requested sources"
    ),
    RawIngestionInputErrorCode.INVALID_SOURCE: "each raw source must be bytes or a binary stream",
    RawIngestionInputErrorCode.INVALID_FILENAME: "filename hints must be bounded strings",
    RawIngestionInputErrorCode.TOTAL_INPUT_LIMIT_EXCEEDED: (
        "known raw input bytes exceed the batch policy limit"
    ),
}


class RawIngestionInputError(ValueError):
    """Sanitized batch-boundary failure that never echoes identifiers or raw values."""

    def __init__(self, code: RawIngestionInputErrorCode) -> None:
        self.code = code
        super().__init__(_INPUT_ERROR_MESSAGES[code])


class RawIngestionAuthorizationError(RuntimeError):
    """An explicit upstream decision does not authorize reading raw inputs."""

    def __init__(self, role: ControlRole) -> None:
        self.role = role
        super().__init__(f"upstream {role.value} decision does not authorize raw ingestion")


class M0103Service:
    """Authorize and execute one deterministic in-memory raw-ingestion batch."""

    __slots__ = ("_registry",)

    def __init__(self, registry: ParserRegistry = DEFAULT_REGISTRY) -> None:
        self._registry = registry

    @staticmethod
    def validate_request(request: object) -> IngestRawInputsRequest:
        """Revalidate the closed request before hashing or touching a source object."""

        _require_authorized_untrusted(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        _require_authorized(validated.context)
        return validated

    def execute(
        self,
        request: object,
        sources: Mapping[str, RawInputSource],
        filenames: Mapping[str, str] | None = None,
    ) -> RawIngestionResult:
        """Parse an exact authorized batch and return a metadata-only result."""

        validated = self.validate_request(request)
        source_batch, filename_batch = _prepare_inputs(validated, sources, filenames)
        limits = IngestionLimits(
            max_source_bytes=validated.policy.max_source_bytes,
            max_decoded_bytes=validated.policy.max_decoded_bytes,
            max_diagnostics=validated.policy.max_diagnostics_per_source,
        )
        descriptors = tuple(
            self._parse_source(
                source,
                source_batch[source.source_id],
                filename_batch.get(source.source_id),
                limits,
                validated,
            )
            for source in sorted(validated.sources, key=lambda item: item.source_id)
        )
        return _result(validated, descriptors)

    def _parse_source(
        self,
        source: RawSourceDescriptor,
        raw: RawInputSource,
        filename: str | None,
        limits: IngestionLimits,
        request: IngestRawInputsRequest,
    ) -> ValidatedRawInputDescriptor:
        parser_source: bytes | BinaryIO = (
            bytes(raw) if isinstance(raw, bytearray | memoryview) else raw
        )
        parsed = parse_raw_input(
            parser_source,
            source_id=source.source_id,
            filename=filename,
            expected_sha256=source.artifact.digest,
            limits=limits,
            registry=self._registry,
        )
        return _reconcile_admission(parsed, source, request)


def preflight_raw_ingestion_authorization(request: object) -> None:
    """Reject an explicit denial before relational validation, hashing, or byte access."""

    _require_authorized_untrusted(request)


def _prepare_inputs(
    request: IngestRawInputsRequest,
    sources: Mapping[str, RawInputSource],
    filenames: Mapping[str, str] | None,
) -> tuple[Mapping[str, RawInputSource], Mapping[str, str]]:
    """Snapshot batch membership without reading binary stream content."""

    expected = {source.source_id for source in request.sources}
    if not isinstance(sources, Mapping) or set(sources) != expected:
        raise RawIngestionInputError(RawIngestionInputErrorCode.SOURCE_SET_MISMATCH)

    source_snapshot: dict[str, RawInputSource] = {}
    known_bytes = 0
    for source_id in sorted(expected):
        snapshot, byte_count = _snapshot_source(sources[source_id])
        source_snapshot[source_id] = snapshot
        known_bytes += byte_count

    total_limit = request.policy.max_source_bytes * len(request.sources)
    if known_bytes > total_limit:
        raise RawIngestionInputError(
            RawIngestionInputErrorCode.TOTAL_INPUT_LIMIT_EXCEEDED
        )

    hints = {} if filenames is None else filenames
    if not isinstance(hints, Mapping) or not set(hints).issubset(expected):
        raise RawIngestionInputError(RawIngestionInputErrorCode.FILENAME_SET_MISMATCH)
    filename_snapshot = {
        source_id: _validated_filename(filename) for source_id, filename in hints.items()
    }

    return MappingProxyType(source_snapshot), MappingProxyType(filename_snapshot)


def _snapshot_source(source: RawInputSource) -> tuple[RawInputSource, int]:
    if isinstance(source, bytes):
        return source, len(source)
    if isinstance(source, bytearray | memoryview):
        immutable = bytes(source)
        return immutable, len(immutable)
    if callable(getattr(source, "read", None)):
        return source, 0
    raise RawIngestionInputError(RawIngestionInputErrorCode.INVALID_SOURCE)


def _validated_filename(filename: object) -> str:
    if not isinstance(filename, str) or not filename:
        raise RawIngestionInputError(RawIngestionInputErrorCode.INVALID_FILENAME)
    try:
        filename_size = len(filename.encode("utf-8"))
    except UnicodeEncodeError:
        raise RawIngestionInputError(RawIngestionInputErrorCode.INVALID_FILENAME) from None
    if filename_size > _MAX_FILENAME_BYTES:
        raise RawIngestionInputError(RawIngestionInputErrorCode.INVALID_FILENAME)
    return filename


def _reconcile_admission(
    parsed: ValidatedRawInputDescriptor,
    declared: RawSourceDescriptor,
    request: IngestRawInputsRequest,
) -> ValidatedRawInputDescriptor:
    admission = _admission_diagnostics(parsed, declared, request)
    if not admission:
        return parsed

    # `structural_validation_passed` is the v1 admission flag: a structurally parseable file is
    # still not admitted when its declaration or active policy contradicts detected content.
    if parsed.disposition is RawInputDisposition.ACCEPTED:
        diagnostics = (*admission, *parsed.diagnostics)
        disposition = RawInputDisposition.QUARANTINED
    else:
        diagnostics = (*parsed.diagnostics, *admission)
        disposition = parsed.disposition
    diagnostics = diagnostics[: request.policy.max_diagnostics_per_source]
    return _RAW_INPUT_ADAPTER.validate_python(
        {
            **parsed.model_dump(mode="python"),
            "structural_validation_passed": False,
            "disposition": disposition,
            "diagnostics": diagnostics,
        },
        strict=True,
    )


def _admission_diagnostics(
    parsed: ValidatedRawInputDescriptor,
    declared: RawSourceDescriptor,
    request: IngestRawInputsRequest,
) -> tuple[ParseDiagnostic, ...]:
    codes: list[str] = []
    detected = parsed.detected
    if detected is not None:
        if detected.format not in request.policy.allowed_formats:
            codes.append("detected_format_disabled")
        if detected.compression not in request.policy.allowed_compressions:
            codes.append("detected_compression_disabled")
    if parsed.source_size_bytes != declared.byte_length:
        codes.append("declared_size_mismatch")
    if detected is not None:
        if declared.declared_format is not None and detected.format is not declared.declared_format:
            codes.append("declared_format_mismatch")
        if declared.declared_version is not None and detected.version != declared.declared_version:
            codes.append("declared_version_mismatch")
        if (
            declared.declared_compression is not None
            and detected.compression is not declared.declared_compression
        ):
            codes.append("declared_compression_mismatch")
    return tuple(
        _admission_diagnostic(declared, code, ordinal=index)
        for index, code in enumerate(codes, start=1)
    )


def _admission_diagnostic(
    source: RawSourceDescriptor,
    code: str,
    *,
    ordinal: int,
) -> ParseDiagnostic:
    digest = hashlib.sha256(f"{source.source_id}|{code}|{ordinal}".encode()).hexdigest()[:24]
    return ParseDiagnostic(
        diagnostic_id=f"diagnostic.m0103.{digest}",
        code=code,
        severity=DiagnosticSeverity.ERROR,
        action=DiagnosticAction.QUARANTINE,
        message=_DIAGNOSTIC_MESSAGES[code],
        evidence=(source.artifact,),
    )


def _result(
    request: IngestRawInputsRequest,
    descriptors: tuple[ValidatedRawInputDescriptor, ...],
) -> RawIngestionResult:
    request_hash = canonical_request_digest(request)
    policy_hash = policy_digest(request.policy)
    disposition = _batch_disposition(descriptors)
    return RawIngestionResult(
        ingestion_id=f"ingestion.m0103.{request_hash.removeprefix('sha256:')}",
        request_digest=request_hash,
        policy_digest=policy_hash,
        disposition=disposition,
        raw_inputs=descriptors,
        support=_support(disposition),
        uncertainty=_uncertainty(),
        provenance=_provenance(request, descriptors, request_hash, policy_hash),
        evidence=_evidence(request),
        limitations=_MODULE_LIMITATIONS,
        human_review_required=disposition is not RawInputDisposition.ACCEPTED,
        completed_at=request.context.occurred_at,
        supersedes_result_digest=request.supersedes_result_digest,
    )


def _batch_disposition(
    descriptors: tuple[ValidatedRawInputDescriptor, ...],
) -> RawInputDisposition:
    dispositions = {descriptor.disposition for descriptor in descriptors}
    if RawInputDisposition.REJECTED in dispositions:
        return RawInputDisposition.REJECTED
    if RawInputDisposition.QUARANTINED in dispositions:
        return RawInputDisposition.QUARANTINED
    return RawInputDisposition.ACCEPTED


def _support(disposition: RawInputDisposition) -> SupportDecision:
    status, code, rationale = {
        RawInputDisposition.ACCEPTED: (
            SupportStatus.LIMITED,
            "raw_input_validated",
            "Every supplied source passed bounded checksum, structure, and admission checks.",
        ),
        RawInputDisposition.QUARANTINED: (
            SupportStatus.REVIEW_REQUIRED,
            "raw_input_quarantined",
            "At least one source failed admission and requires review; absence is not inferred.",
        ),
        RawInputDisposition.REJECTED: (
            SupportStatus.UNSUPPORTED,
            "raw_input_rejected",
            "At least one source violated an integrity or resource boundary and was rejected.",
        ),
    }[disposition]
    return SupportDecision(status=status, reason_code=code, rationale=rationale)


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        measurement=_not_estimable(
            "Raw-format admission does not estimate scientific measurement error."
        ),
        sampling=_not_estimable(
            "Submitted files do not define a calibrated sampling distribution."
        ),
        parameter=_not_estimable(
            "The deterministic parser fits no probabilistic parameters."
        ),
        model_form=_not_estimable(
            "No predictive model is used during structural raw-input admission."
        ),
        identification=_not_estimable(
            "Content identity is checksum-bound; residual attribution uncertainty is not scored."
        ),
        support=_not_estimable(
            "Support is a typed deterministic admission state, not a confidence probability."
        ),
        transport=_not_estimable(
            "Use outside the declared formats, policy, and upstream controls is not estimated."
        ),
        sensitivity_notes=(
            "Missing, malformed, or contradictory input is quarantined or rejected, "
            "never negative.",
            "Filename extensions are advisory; content and declared policy govern admission.",
        ),
    )


def _control_records(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    references = context.references
    records = (
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
    return tuple(sorted(records, key=lambda item: item.role.value))


def _provenance(
    request: IngestRawInputsRequest,
    descriptors: tuple[ValidatedRawInputDescriptor, ...],
    request_hash: str,
    policy_hash: str,
) -> ProvenanceRecord:
    references = request.context.references
    controls = _control_records(request.context)
    input_digests = tuple(
        dict.fromkeys(
            (
                request_hash,
                policy_hash,
                *(descriptor.source_digest for descriptor in descriptors),
                *(record.evidence_digest for record in controls),
                *(source.artifact.digest for source in request.sources),
            )
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.m0103.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0103_MODULE_ID,
        module_version=M0103_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=policy_hash,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _evidence(request: IngestRawInputsRequest) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration.evidence),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage.evidence),
        (ControlRole.PROVENANCE, references.provenance.evidence),
        (ControlRole.CONSENT, references.consent.evidence),
        (ControlRole.QUALITY, references.quality.evidence),
        (ControlRole.SUPPORT, references.support.evidence),
        (ControlRole.INTENDED_USE, references.intended_use.evidence),
    )
    control_evidence = tuple(
        EvidenceReference(
            reference=reference,
            role="evidence",
            claim=(
                f"Caller-declared {role.value.replace('_', '-')} control reference; issuer and "
                "content are not authenticated by M01-03."
            ),
        )
        for role, reference in controls
    )
    source_evidence = tuple(
        EvidenceReference(
            reference=source.artifact,
            role="evidence",
            claim=(
                f"Caller-declared source reference for {source.source_id}; the expected digest "
                "is compared with supplied bytes without retaining them."
            ),
        )
        for source in sorted(request.sources, key=lambda item: item.source_id)
    )
    return (*control_evidence, *source_evidence)


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


def _control_from_untrusted(references: object, role: ControlRole) -> object:
    if isinstance(references, Mapping):
        return references.get(role.value)
    return getattr(references, role.value, None)


def _state_matches(
    value: object,
    expected: ConsentState | IdentityLineageState | UpstreamDecisionState,
) -> bool:
    return value is expected or value == expected.value


def _require_authorized_untrusted(request: object) -> None:
    references = _references_from_untrusted(request)
    if references is None:
        return
    required: tuple[
        tuple[ControlRole, ConsentState | IdentityLineageState | UpstreamDecisionState], ...
    ] = (
        (ControlRole.CONSENT, ConsentState.GRANTED),
        (ControlRole.IDENTITY_LINEAGE, IdentityLineageState.RESOLVED),
        (ControlRole.APPROVED_CONFIGURATION, UpstreamDecisionState.ACCEPTED),
        (ControlRole.PROVENANCE, UpstreamDecisionState.ACCEPTED),
        (ControlRole.QUALITY, UpstreamDecisionState.ACCEPTED),
        (ControlRole.SUPPORT, UpstreamDecisionState.ACCEPTED),
        (ControlRole.INTENDED_USE, UpstreamDecisionState.ACCEPTED),
    )
    for role, expected in required:
        reference = _control_from_untrusted(references, role)
        state = _reference_state(reference)
        if state is not None and not _state_matches(state, expected):
            raise RawIngestionAuthorizationError(role)


def _require_authorized(context: ExecutionContext) -> None:
    references = context.references
    if references.consent.state is not ConsentState.GRANTED:
        raise RawIngestionAuthorizationError(ControlRole.CONSENT)
    if references.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise RawIngestionAuthorizationError(ControlRole.IDENTITY_LINEAGE)
    generic = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    for role, reference in generic:
        if reference.state is not UpstreamDecisionState.ACCEPTED:
            raise RawIngestionAuthorizationError(role)


__all__ = [
    "M0103Service",
    "RawIngestionAuthorizationError",
    "RawIngestionInputError",
    "RawIngestionInputErrorCode",
    "RawInputSource",
    "preflight_raw_ingestion_authorization",
]
