"""Stateless M02-03 role-aware orchestration over the shared M01-03 parser."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_03 import RawInputDisposition
from glio_proteogen.contracts.m02_03 import (
    M0203_AUTHORITY_LIMITATION_CODE,
    M0203_CONTRACT_VERSION,
    M0203_INGESTION_LIMITATION_CODE,
    M0203_MODULE_ID,
    BundleDiagnostic,
    BundleDiagnosticCode,
    IdentificationRawIngestionResult,
    IngestIdentificationRawInputsRequest,
    RawInputRole,
    RoleRequirement,
    ValidatedIdentificationRawInput,
    canonical_request_digest,
    configuration_digest,
    policy_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
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
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion import (
    IngestionLimits,
    RawInputSource,
    parse_raw_input,
    reconcile_raw_input_admission,
)

_REQUEST_ADAPTER: Final = TypeAdapter(IngestIdentificationRawInputsRequest)
_BUNDLE_MESSAGES: Final = {
    BundleDiagnosticCode.REQUIRED_ROLE_MISSING: "A required raw-input role is missing.",
    BundleDiagnosticCode.ROLE_CARDINALITY_MISMATCH: (
        "A raw-input role violates its source cardinality."
    ),
    BundleDiagnosticCode.ROLE_FORMAT_MISMATCH: (
        "Detected content is not allowed for its raw-input role."
    ),
}


class IdentificationRawIngestionInputErrorCode(StrEnum):
    SOURCE_SET_MISMATCH = "source_set_mismatch"
    FILENAME_SET_MISMATCH = "filename_set_mismatch"
    SOURCE_TYPE_INVALID = "source_type_invalid"


class IdentificationRawIngestionInputError(ValueError):
    """Stable, privacy-safe byte-boundary input failure."""

    def __init__(self, code: IdentificationRawIngestionInputErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


class IdentificationRawIngestionAuthorizationError(RuntimeError):
    """Raised before typed validation or source traversal when controls deny use."""


class M0203IdentificationRawIngestionEngine:
    """Validate one bounded identification raw-input bundle without retaining bytes."""

    def evaluate(
        self,
        request: object,
        sources: Mapping[str, RawInputSource],
        filenames: Mapping[str, str] | None = None,
    ) -> IdentificationRawIngestionResult:
        preflight_identification_raw_ingestion_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        payloads, safe_filenames = prepare_identification_raw_inputs(
            validated,
            sources,
            filenames,
        )
        limits = IngestionLimits(
            max_source_bytes=validated.policy.base_policy.max_source_bytes,
            max_decoded_bytes=validated.policy.base_policy.max_decoded_bytes,
            max_diagnostics=validated.policy.base_policy.max_diagnostics_per_source,
        )
        parsed: list[ValidatedIdentificationRawInput] = []
        for item in sorted(validated.sources, key=canonical_json_bytes):
            declared = item.source
            descriptor = parse_raw_input(
                payloads[declared.source_id],
                source_id=declared.source_id,
                filename=safe_filenames.get(declared.source_id),
                expected_sha256=declared.artifact.digest,
                limits=limits,
            )
            descriptor = reconcile_raw_input_admission(
                descriptor,
                declared,
                validated.policy.base_policy,
            )
            parsed.append(ValidatedIdentificationRawInput(role=item.role, raw_input=descriptor))
        raw_inputs = tuple(sorted(parsed, key=canonical_json_bytes))
        diagnostics = _bundle_diagnostics(validated, raw_inputs)
        return _result(validated, raw_inputs, diagnostics)


def evaluate_identification_raw_ingestion(
    request: object,
    sources: Mapping[str, RawInputSource],
    filenames: Mapping[str, str] | None = None,
) -> IdentificationRawIngestionResult:
    """Evaluate one identification raw-input request."""

    return M0203IdentificationRawIngestionEngine().evaluate(request, sources, filenames)


def preflight_identification_raw_ingestion_authorization(candidate: object) -> None:
    """Reject denied raw controls before validation or touching source mappings."""

    context = _value(candidate, "context")
    references = _value(context, "references")
    expected = {
        "approved_configuration": "accepted",
        "identity_lineage": "resolved",
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
        raise IdentificationRawIngestionAuthorizationError


def _value(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


def prepare_identification_raw_inputs(
    request: IngestIdentificationRawInputsRequest,
    sources: Mapping[str, RawInputSource],
    filenames: Mapping[str, str] | None,
) -> tuple[dict[str, bytes], dict[str, str]]:
    expected = {item.source.source_id for item in request.sources}
    if not isinstance(sources, Mapping) or set(sources) != expected:
        raise IdentificationRawIngestionInputError(
            IdentificationRawIngestionInputErrorCode.SOURCE_SET_MISMATCH
        )
    if filenames is not None and set(filenames) != expected:
        raise IdentificationRawIngestionInputError(
            IdentificationRawIngestionInputErrorCode.FILENAME_SET_MISMATCH
        )
    payloads: dict[str, bytes] = {}
    limit = request.policy.base_policy.max_source_bytes
    for source_id in sorted(expected):
        payloads[source_id] = _snapshot_source(sources[source_id], limit)
    return payloads, dict(filenames or {})


def _snapshot_source(source: RawInputSource, limit: int) -> bytes:
    """Read one source once, retaining only the parser's bounded prefix."""

    if isinstance(source, bytes | bytearray | memoryview):
        return bytes(source[: limit + 1])
    reader = getattr(source, "read", None)
    if not callable(reader):
        raise IdentificationRawIngestionInputError(
            IdentificationRawIngestionInputErrorCode.SOURCE_TYPE_INVALID
        )
    chunks: list[bytes] = []
    remaining = limit + 1
    while remaining:
        chunk = reader(min(64 * 1024, remaining))
        if not isinstance(chunk, bytes):
            raise IdentificationRawIngestionInputError(
                IdentificationRawIngestionInputErrorCode.SOURCE_TYPE_INVALID
            )
        if not chunk:
            break
        bounded = chunk[:remaining]
        chunks.append(bounded)
        remaining -= len(bounded)
    return b"".join(chunks)


def _bundle_diagnostics(
    request: IngestIdentificationRawInputsRequest,
    raw_inputs: tuple[ValidatedIdentificationRawInput, ...],
) -> tuple[BundleDiagnostic, ...]:
    source_ids_by_role: dict[RawInputRole, list[str]] = {role: [] for role in RawInputRole}
    for item in request.sources:
        source_ids_by_role[item.role].append(item.source.source_id)
    requirements = {item.role: item for item in request.policy.role_requirements}
    diagnostics: list[BundleDiagnostic] = []
    for role in RawInputRole:
        requirement = requirements[role]
        source_ids = tuple(sorted(source_ids_by_role[role]))
        count = len(source_ids)
        if requirement.requirement is RoleRequirement.REQUIRED and count == 0:
            diagnostics.append(_bundle_diagnostic(BundleDiagnosticCode.REQUIRED_ROLE_MISSING, role))
        elif not requirement.min_sources <= count <= requirement.max_sources:
            diagnostics.append(
                _bundle_diagnostic(
                    BundleDiagnosticCode.ROLE_CARDINALITY_MISMATCH,
                    role,
                    source_ids,
                )
            )
    mismatched_by_role: dict[RawInputRole, list[str]] = {
        role: [] for role in RawInputRole
    }
    for parsed_item in raw_inputs:
        detected = parsed_item.raw_input.detected
        if (
            detected is not None
            and detected.format not in requirements[parsed_item.role].allowed_formats
        ):
            mismatched_by_role[parsed_item.role].append(
                parsed_item.raw_input.source_id
            )
    diagnostics.extend(
        _bundle_diagnostic(
            BundleDiagnosticCode.ROLE_FORMAT_MISMATCH,
            role,
            tuple(sorted(source_ids)),
        )
        for role, source_ids in mismatched_by_role.items()
        if source_ids
    )
    return tuple(sorted(diagnostics, key=canonical_json_bytes))


def _bundle_diagnostic(
    code: BundleDiagnosticCode,
    role: RawInputRole,
    source_ids: tuple[str, ...] = (),
) -> BundleDiagnostic:
    return BundleDiagnostic(
        code=code,
        role=role,
        source_ids=source_ids,
        message=_BUNDLE_MESSAGES[code],
    )


def _result(
    request: IngestIdentificationRawInputsRequest,
    raw_inputs: tuple[ValidatedIdentificationRawInput, ...],
    diagnostics: tuple[BundleDiagnostic, ...],
) -> IdentificationRawIngestionResult:
    request_hash = canonical_request_digest(request)
    policy_hash = policy_digest(request.policy)
    configuration_hash = configuration_digest(request.policy)
    disposition = _disposition(raw_inputs, diagnostics)
    return IdentificationRawIngestionResult(
        ingestion_id=f"ingestion.m0203.{request_hash.removeprefix('sha256:')}",
        request_digest=request_hash,
        policy_digest=policy_hash,
        configuration_digest=configuration_hash,
        disposition=disposition,
        raw_inputs=raw_inputs,
        bundle_diagnostics=diagnostics,
        support=_support(disposition),
        uncertainty=_uncertainty(),
        provenance=_provenance(
            request,
            request_hash,
            policy_hash,
            configuration_hash,
            raw_inputs,
        ),
        evidence=_evidence(request),
        limitations=(
            Limitation(
                code=M0203_INGESTION_LIMITATION_CODE,
                statement="This result validates raw-input transport, structure, and role only.",
            ),
            Limitation(
                code=M0203_AUTHORITY_LIMITATION_CODE,
                statement="External control issuers and source content are not authenticated here.",
            ),
        ),
        human_review_required=disposition is not RawInputDisposition.ACCEPTED,
        completed_at=request.context.occurred_at,
        supersedes_result_digest=request.supersedes_result_digest,
    )


def _disposition(
    raw_inputs: tuple[ValidatedIdentificationRawInput, ...],
    diagnostics: tuple[BundleDiagnostic, ...],
) -> RawInputDisposition:
    states = {item.raw_input.disposition for item in raw_inputs}
    if RawInputDisposition.REJECTED in states:
        return RawInputDisposition.REJECTED
    if diagnostics or RawInputDisposition.QUARANTINED in states:
        return RawInputDisposition.QUARANTINED
    return RawInputDisposition.ACCEPTED


def _support(disposition: RawInputDisposition) -> SupportDecision:
    values = {
        RawInputDisposition.ACCEPTED: (
            SupportStatus.LIMITED,
            "identification_raw_inputs_validated",
            "Raw inputs passed the declared transport, structure, and role policy.",
        ),
        RawInputDisposition.QUARANTINED: (
            SupportStatus.REVIEW_REQUIRED,
            "identification_raw_inputs_quarantined",
            "One or more raw inputs or bundle rules require review.",
        ),
        RawInputDisposition.REJECTED: (
            SupportStatus.UNSUPPORTED,
            "identification_raw_inputs_rejected",
            "One or more raw inputs failed a hard transport boundary.",
        ),
    }[disposition]
    return SupportDecision(status=values[0], reason_code=values[1], rationale=values[2])


def _uncertainty() -> UncertaintyProfile:
    def unavailable(rationale: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)

    return UncertaintyProfile(
        measurement=unavailable("Raw ingestion does not estimate measurement uncertainty."),
        sampling=unavailable("Raw ingestion does not estimate sampling uncertainty."),
        parameter=unavailable("The deterministic parser fits no parameters."),
        model_form=unavailable("No learned model is used."),
        identification=unavailable("Identification correctness is outside this parser."),
        support=unavailable("Support follows deterministic admission rules."),
        transport=unavailable("External source authority is not assessed."),
    )


def _controls(
    request: IngestIdentificationRawInputsRequest,
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
    request: IngestIdentificationRawInputsRequest,
    request_hash: str,
    policy_hash: str,
    configuration_hash: str,
    raw_inputs: tuple[ValidatedIdentificationRawInput, ...],
) -> ProvenanceRecord:
    references = request.context.references
    controls = _controls(request)
    return ProvenanceRecord(
        activity_id=f"activity.m0203.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0203_MODULE_ID,
        module_version=M0203_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted(
                {
                    request_hash,
                    policy_hash,
                    configuration_hash,
                    *(item.raw_input.source_digest for item in raw_inputs),
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
    request: IngestIdentificationRawInputsRequest,
) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    controls: tuple[tuple[ControlRole, ArtifactReference], ...] = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration.evidence),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage.evidence),
        (ControlRole.PROVENANCE, references.provenance.evidence),
        (ControlRole.CONSENT, references.consent.evidence),
        (ControlRole.QUALITY, references.quality.evidence),
        (ControlRole.SUPPORT, references.support.evidence),
        (ControlRole.INTENDED_USE, references.intended_use.evidence),
    )
    result = [
        EvidenceReference(
            reference=reference,
            role="evidence",
            claim=f"Caller-declared {role.value} control reference; issuer is not authenticated.",
        )
        for role, reference in controls
    ]
    result.extend(
        EvidenceReference(
            reference=item.source.artifact,
            role="evidence",
            claim=f"Caller-declared source reference for {item.source.source_id}.",
        )
        for item in sorted(request.sources, key=canonical_json_bytes)
    )
    return tuple(sorted(result, key=canonical_json_bytes))


__all__ = [
    "IdentificationRawIngestionAuthorizationError",
    "IdentificationRawIngestionInputError",
    "IdentificationRawIngestionInputErrorCode",
    "M0203IdentificationRawIngestionEngine",
    "evaluate_identification_raw_ingestion",
    "preflight_identification_raw_ingestion_authorization",
    "prepare_identification_raw_inputs",
]
