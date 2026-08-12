"""Focused locked behavior for the M01-03 raw-ingestion contract."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m01_03 import (
    Compression,
    DetectedRawFormat,
    DiagnosticAction,
    DiagnosticSeverity,
    IngestRawInputsRequest,
    ParseDiagnostic,
    RawFormat,
    RawIngestionPolicy,
    RawIngestionResult,
    RawInputDisposition,
    RawSourceDescriptor,
    ValidatedRawInputDescriptor,
    canonical_request_digest,
    contract_json_schema,
    policy_digest,
    result_payload_digest,
    source_descriptor_digest,
)
from glio_proteogen.contracts.m01_03.schema import (
    CONTRACT_VERSION,
    JSON_SCHEMA_DIALECT,
    SCHEMA_ID_PREFIX,
    ContractName,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

pytestmark = pytest.mark.contract

ROOT = Path(__file__).parents[2]
SNAPSHOT_PATH = ROOT / "tests" / "snapshots" / "m01_03" / "schema_digests.json"
SCHEMA_NAMES: tuple[ContractName, ...] = (
    "request",
    "output",
    "policy",
    "source",
    "raw_input",
    "diagnostic",
)


def _digest(label: str) -> str:
    return sha256_digest({"fixture": label})


def _artifact(label: str, *, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=digest or _digest(label),
        media_type="application/json",
    )


def _policy(
    *,
    allowed_formats: tuple[RawFormat, ...] = tuple(RawFormat),
    allowed_compressions: tuple[Compression, ...] = tuple(Compression),
    max_sources: int = 4,
    max_source_bytes: int = 1_000_000,
) -> RawIngestionPolicy:
    return RawIngestionPolicy(
        policy_id="policy.raw-ingestion",
        version="1.0.0",
        allowed_formats=allowed_formats,
        allowed_compressions=allowed_compressions,
        max_source_bytes=max_source_bytes,
        max_decoded_bytes=2_000_000,
        max_sources=max_sources,
        max_diagnostics_per_source=32,
        require_checksum=True,
    )


def _context(
    policy: RawIngestionPolicy,
    *,
    consent: ConsentState = ConsentState.GRANTED,
    identity: IdentityLineageState = IdentityLineageState.RESOLVED,
    generic: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED,
    configuration_digest: str | None = None,
) -> ExecutionContext:
    def decision(role: str, *, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=generic,
            policy_version="1.0.0",
            evidence=_artifact(role, digest=digest),
        )

    return ExecutionContext(
        request_id="request.raw-ingestion",
        actor_id="actor.test",
        occurred_at=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision(
                "configuration",
                digest=configuration_digest or policy_digest(policy),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity-lineage",
                state=identity,
                policy_version="1.0.0",
                binding_digest=_digest("identity-binding"),
                evidence=_artifact("identity-lineage"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=consent,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _source(label: str = "one", *, size: int = 128) -> RawSourceDescriptor:
    return RawSourceDescriptor(
        source_id=f"source.{label}",
        artifact=_artifact(f"source-{label}"),
        byte_length=size,
        declared_format=RawFormat.MZML,
        declared_version="1.1.0",
        declared_compression=Compression.NONE,
    )


def _request(
    *,
    policy: RawIngestionPolicy | None = None,
    sources: tuple[RawSourceDescriptor, ...] | None = None,
    context: ExecutionContext | None = None,
) -> IngestRawInputsRequest:
    active_policy = policy or _policy()
    return IngestRawInputsRequest(
        context=context or _context(active_policy),
        policy=active_policy,
        sources=sources or (_source(),),
    )


def _diagnostic(
    label: str,
    *,
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR,
    action: DiagnosticAction = DiagnosticAction.QUARANTINE,
) -> ParseDiagnostic:
    return ParseDiagnostic(
        diagnostic_id=f"diagnostic.{label}",
        code=f"parse.{label}",
        severity=severity,
        action=action,
        message=f"Synthetic {label} diagnostic.",
    )


def _raw_input(
    label: str = "one",
    *,
    disposition: RawInputDisposition = RawInputDisposition.ACCEPTED,
    diagnostics: tuple[ParseDiagnostic, ...] = (),
) -> ValidatedRawInputDescriptor:
    accepted = disposition is RawInputDisposition.ACCEPTED
    return ValidatedRawInputDescriptor(
        source_id=f"source.{label}",
        source_digest=_artifact(f"source-{label}").digest,
        source_size_bytes=128,
        decoded_size_bytes=128,
        detected=DetectedRawFormat(
            format=RawFormat.MZML,
            version="1.1.0",
            compression=Compression.NONE,
            media_type="application/mzml+xml",
        ),
        record_count=2 if accepted else 0,
        checksum_verified=True,
        structural_validation_passed=accepted,
        disposition=disposition,
        diagnostics=diagnostics,
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M01-03 performs deterministic structural validation only.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
    )


def _control_records(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    refs = context.references
    return (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=refs.provenance.decision_id,
            state=refs.provenance.state,
            policy_version=refs.provenance.policy_version,
            evidence_digest=refs.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=refs.consent.decision_id,
            state=refs.consent.state,
            policy_version=refs.consent.policy_version,
            evidence_digest=refs.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=refs.quality.decision_id,
            state=refs.quality.state,
            policy_version=refs.quality.policy_version,
            evidence_digest=refs.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=refs.support.decision_id,
            state=refs.support.state,
            policy_version=refs.support.policy_version,
            evidence_digest=refs.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=refs.intended_use.decision_id,
            state=refs.intended_use.state,
            policy_version=refs.intended_use.policy_version,
            evidence_digest=refs.intended_use.evidence.digest,
        ),
    )


def _result(
    raw_inputs: tuple[ValidatedRawInputDescriptor, ...] | None = None,
) -> RawIngestionResult:
    inputs = raw_inputs or (_raw_input(),)
    policy = _policy()
    request = _request(
        policy=policy,
        sources=tuple(_source(item.source_id.removeprefix("source.")) for item in inputs),
    )
    request_hash = canonical_request_digest(request)
    policy_hash = policy_digest(policy)
    completed_at = datetime(2026, 8, 12, 12, 5, tzinfo=UTC)
    disposition = (
        RawInputDisposition.REJECTED
        if any(item.disposition is RawInputDisposition.REJECTED for item in inputs)
        else RawInputDisposition.QUARANTINED
        if any(item.disposition is RawInputDisposition.QUARANTINED for item in inputs)
        else RawInputDisposition.ACCEPTED
    )
    context = request.context
    provenance = ProvenanceRecord(
        activity_id=f"activity.m0103.{request_hash.removeprefix('sha256:')}",
        actor_id=context.actor_id,
        module_id="GLIO-PROTEOGEN-M01-03",
        module_version="1.0.0",
        generated_at=completed_at,
        input_digests=(
            request_hash,
            policy_hash,
            *(item.source_digest for item in inputs),
        ),
        configuration_digest=policy_hash,
        consent_decision_id=context.references.consent.decision_id,
        consent_state=context.references.consent.state,
        consent_policy_version=context.references.consent.policy_version,
        consent_evidence_digest=context.references.consent.evidence.digest,
        control_decisions=_control_records(context),
    )
    evidence_artifacts = (
        context.references.approved_configuration.evidence,
        context.references.identity_lineage.evidence,
        context.references.provenance.evidence,
        context.references.consent.evidence,
        context.references.quality.evidence,
        context.references.support.evidence,
        context.references.intended_use.evidence,
        *(_artifact(f"source-{item.source_id.removeprefix('source.')}") for item in inputs),
    )
    support = {
        RawInputDisposition.ACCEPTED: SupportDecision(
            status=SupportStatus.LIMITED,
            reason_code="raw_input_validated",
            rationale="Raw input passed bounded structural validation.",
        ),
        RawInputDisposition.QUARANTINED: SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="raw_input_quarantined",
            rationale="Raw input requires review.",
        ),
        RawInputDisposition.REJECTED: SupportDecision(
            status=SupportStatus.UNSUPPORTED,
            reason_code="raw_input_rejected",
            rationale="Raw input was rejected.",
        ),
    }[disposition]
    return RawIngestionResult(
        ingestion_id=f"ingestion.m0103.{request_hash.removeprefix('sha256:')}",
        request_digest=request_hash,
        policy_digest=policy_hash,
        disposition=disposition,
        raw_inputs=inputs,
        support=support,
        uncertainty=_uncertainty(),
        provenance=provenance,
        evidence=tuple(
            EvidenceReference(
                reference=artifact,
                role="evidence",
                claim=f"M01-03 input evidence {index}.",
            )
            for index, artifact in enumerate(evidence_artifacts)
        ),
        limitations=(
            Limitation(
                code="raw_ingestion_only",
                statement="This result reports raw-format validation only.",
            ),
            Limitation(
                code="external_controls_unverified",
                statement="External control issuers are not authenticated by M01-03.",
            ),
        ),
        human_review_required=disposition is not RawInputDisposition.ACCEPTED,
        completed_at=completed_at,
    )


def _json_payload(model: BaseModel) -> dict[str, Any]:
    return cast("dict[str, Any]", model.model_dump(mode="json"))


def _validate_json(model: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
    return model.model_validate_json(json.dumps(payload), strict=True)


def test_supported_formats_are_closed_and_versions_are_separate() -> None:
    assert {item.value for item in RawFormat} == {
        "mzML",
        "mzIdentML",
        "mzTab-M",
        "FASTA",
        "VCF",
        "GFF3",
    }
    for raw_format, version in (
        (RawFormat.MZIDENTML, "1.2.0"),
        (RawFormat.MZIDENTML, "1.3.0"),
        (RawFormat.VCF, "4.1"),
        (RawFormat.VCF, "4.5"),
    ):
        assert DetectedRawFormat(
            format=raw_format,
            version=version,
            compression=Compression.NONE,
            media_type="application/octet-stream",
        ).version == version


def test_declared_version_requires_format() -> None:
    payload = _json_payload(_source())
    payload["declared_format"] = None
    with pytest.raises(ValidationError, match="declared version requires"):
        _validate_json(RawSourceDescriptor, payload)


def test_source_descriptor_forbids_coercion_unknown_fields_and_raw_content() -> None:
    payload = _json_payload(_source())
    payload["byte_length"] = "128"
    payload["path"] = "C:/private/patient.raw"
    payload["raw_bytes"] = "secret"
    with pytest.raises(ValidationError):
        _validate_json(RawSourceDescriptor, payload)


@pytest.mark.parametrize("field", ["allowed_formats", "allowed_compressions"])
def test_policy_allowed_values_must_be_unique(field: str) -> None:
    payload = _json_payload(_policy())
    payload[field] = [payload[field][0], payload[field][0]]
    with pytest.raises(ValidationError, match="must be unique"):
        _validate_json(RawIngestionPolicy, payload)


def test_policy_requires_checksum_verification() -> None:
    payload = _json_payload(_policy())
    payload["require_checksum"] = False
    with pytest.raises(ValidationError):
        _validate_json(RawIngestionPolicy, payload)


def test_request_and_policy_digests_ignore_semantically_unordered_collections() -> None:
    first_policy = _policy(
        allowed_formats=(RawFormat.MZML, RawFormat.VCF),
        allowed_compressions=(Compression.NONE, Compression.GZIP),
    )
    second_policy = _policy(
        allowed_formats=tuple(reversed(first_policy.allowed_formats)),
        allowed_compressions=tuple(reversed(first_policy.allowed_compressions)),
    )
    first_sources = (_source("one"), _source("two"))
    second_sources = tuple(reversed(first_sources))
    first = _request(policy=first_policy, sources=first_sources)
    second = _request(policy=second_policy, sources=second_sources)

    assert policy_digest(first_policy) == policy_digest(second_policy)
    assert canonical_request_digest(first) == canonical_request_digest(second)


def test_source_descriptor_digest_binds_declared_metadata() -> None:
    source = _source()
    payload = _json_payload(source)
    payload["declared_version"] = "1.2.0"
    changed = cast("RawSourceDescriptor", _validate_json(RawSourceDescriptor, payload))
    assert source_descriptor_digest(source) != source_descriptor_digest(changed)


@pytest.mark.parametrize(
    ("consent", "identity", "generic", "message"),
    [
        (
            ConsentState.WITHHELD,
            IdentityLineageState.RESOLVED,
            UpstreamDecisionState.ACCEPTED,
            "consent",
        ),
        (
            ConsentState.GRANTED,
            IdentityLineageState.UNRESOLVED,
            UpstreamDecisionState.ACCEPTED,
            "identity lineage",
        ),
        (
            ConsentState.GRANTED,
            IdentityLineageState.RESOLVED,
            UpstreamDecisionState.UNKNOWN,
            "upstream control",
        ),
    ],
)
def test_request_rejects_unauthorized_controls(
    consent: ConsentState,
    identity: IdentityLineageState,
    generic: UpstreamDecisionState,
    message: str,
) -> None:
    policy = _policy()
    with pytest.raises(ValidationError, match=message):
        _request(
            policy=policy,
            context=_context(policy, consent=consent, identity=identity, generic=generic),
        )


def test_request_requires_exact_configuration_policy_binding() -> None:
    policy = _policy()
    with pytest.raises(ValidationError, match="configuration does not bind"):
        _request(
            policy=policy,
            context=_context(policy, configuration_digest=_digest("wrong-policy")),
        )


def test_request_rejects_duplicate_source_ids_and_policy_cap_overflow() -> None:
    duplicate = _source()
    with pytest.raises(ValidationError, match="identifiers must be unique"):
        _request(sources=(duplicate, duplicate))
    policy = _policy(max_sources=1)
    with pytest.raises(ValidationError, match="count exceeds"):
        _request(policy=policy, sources=(_source("one"), _source("two")))


@pytest.mark.parametrize(
    ("policy", "source", "message"),
    [
        (_policy(max_source_bytes=64), _source(size=65), "size exceeds"),
        (_policy(allowed_formats=(RawFormat.VCF,)), _source(), "format is disabled"),
        (_policy(allowed_compressions=(Compression.GZIP,)), _source(), "compression is disabled"),
    ],
)
def test_request_applies_active_policy_to_each_source(
    policy: RawIngestionPolicy,
    source: RawSourceDescriptor,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _request(policy=policy, sources=(source,))


@pytest.mark.parametrize(
    "action",
    [DiagnosticAction.QUARANTINE, DiagnosticAction.REJECT, DiagnosticAction.HUMAN_REVIEW],
)
def test_blocking_diagnostics_require_error_or_critical_severity(
    action: DiagnosticAction,
) -> None:
    with pytest.raises(ValidationError, match="blocking diagnostics"):
        _diagnostic("weak", severity=DiagnosticSeverity.WARNING, action=action)


def test_diagnostic_evidence_must_be_unique() -> None:
    artifact = _artifact("diagnostic")
    with pytest.raises(ValidationError, match="must be unique"):
        ParseDiagnostic(
            diagnostic_id="diagnostic.duplicate",
            code="parse.duplicate",
            severity=DiagnosticSeverity.WARNING,
            action=DiagnosticAction.RECORD,
            message="Duplicate evidence test.",
            evidence=(artifact, artifact),
        )


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("checksum_verified", False),
        ("structural_validation_passed", False),
        ("detected", None),
    ],
)
def test_accepted_input_requires_positive_validation_facts(
    mutation: str,
    value: object,
) -> None:
    payload = _json_payload(_raw_input())
    payload[mutation] = value
    with pytest.raises(ValidationError, match="accepted raw input must pass"):
        _validate_json(ValidatedRawInputDescriptor, payload)


@pytest.mark.parametrize(
    "action",
    [DiagnosticAction.QUARANTINE, DiagnosticAction.REJECT, DiagnosticAction.HUMAN_REVIEW],
)
def test_accepted_input_forbids_every_blocking_action(action: DiagnosticAction) -> None:
    payload = _json_payload(_raw_input())
    payload["diagnostics"] = [
        _json_payload(_diagnostic("blocking", action=action))
    ]
    with pytest.raises(ValidationError, match="accepted raw input must pass"):
        _validate_json(ValidatedRawInputDescriptor, payload)


@pytest.mark.parametrize("action", [DiagnosticAction.QUARANTINE, DiagnosticAction.HUMAN_REVIEW])
def test_quarantined_input_requires_quarantine_or_review(action: DiagnosticAction) -> None:
    assert _raw_input(
        disposition=RawInputDisposition.QUARANTINED,
        diagnostics=(_diagnostic("quarantine", action=action),),
    ).disposition is RawInputDisposition.QUARANTINED

    payload = _json_payload(_raw_input())
    payload.update(
        disposition="quarantined",
        structural_validation_passed=False,
        diagnostics=[
            _json_payload(
                _diagnostic(
                    "record",
                    severity=DiagnosticSeverity.WARNING,
                    action=DiagnosticAction.RECORD,
                )
            )
        ],
    )
    with pytest.raises(ValidationError, match="requires a quarantine or review"):
        _validate_json(ValidatedRawInputDescriptor, payload)


def test_rejection_action_cannot_be_downgraded_and_rejected_requires_it() -> None:
    payload = _json_payload(_raw_input())
    payload.update(
        disposition="quarantined",
        structural_validation_passed=False,
        diagnostics=[
            _json_payload(_diagnostic("quarantine")),
            _json_payload(_diagnostic("reject", action=DiagnosticAction.REJECT)),
        ],
    )
    with pytest.raises(ValidationError, match="requires rejected disposition"):
        _validate_json(ValidatedRawInputDescriptor, payload)

    payload["disposition"] = "rejected"
    payload["diagnostics"] = [_json_payload(_diagnostic("quarantine"))]
    with pytest.raises(ValidationError, match="requires a rejection diagnostic"):
        _validate_json(ValidatedRawInputDescriptor, payload)


def test_diagnostic_identifiers_are_unique_within_one_source() -> None:
    diagnostic = _diagnostic("reject", action=DiagnosticAction.REJECT)
    with pytest.raises(ValidationError, match="identifiers must be unique"):
        _raw_input(
            disposition=RawInputDisposition.REJECTED,
            diagnostics=(diagnostic, diagnostic),
        )


def test_result_digest_is_automatic_and_canonical_over_unordered_evidence() -> None:
    first = _result((_raw_input("one"), _raw_input("two")))
    payload = _json_payload(first)
    payload["result_digest"] = "sha256:" + ("0" * 64)
    for field in ("raw_inputs", "evidence", "limitations"):
        payload[field].reverse()
    payload["provenance"]["input_digests"].reverse()
    payload["provenance"]["control_decisions"].reverse()
    reordered = cast("RawIngestionResult", _validate_json(RawIngestionResult, payload))

    assert first.result_digest == result_payload_digest(first)
    assert reordered.result_digest == first.result_digest


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (("disposition",), "quarantined", "disposition contradicts"),
        (("support", "reason_code"), "raw_input_rejected", "support contradicts"),
        (("human_review_required",), True, "review flag contradicts"),
        (("ingestion_id",), "ingestion.m0103.wrong", "identifier does not bind"),
        (("provenance", "activity_id"), "activity.m0103.wrong", "activity does not bind"),
        (
            ("provenance", "configuration_digest"),
            _digest("wrong-config"),
            "configuration contradicts",
        ),
        (("provenance", "module_id"), "GLIO-PROTEOGEN-M01-04", "wrong module"),
        (("provenance", "generated_at"), "2026-08-12T13:00:00Z", "timestamp contradicts"),
    ],
)
def test_result_envelope_rejects_contradictory_claims(
    path: tuple[str, ...],
    replacement: object,
    message: str,
) -> None:
    payload = _json_payload(_result())
    target: dict[str, Any] = payload
    for part in path[:-1]:
        target = cast("dict[str, Any]", target[part])
    target[path[-1]] = replacement
    payload["result_digest"] = "sha256:" + ("0" * 64)
    with pytest.raises(ValidationError, match=message):
        _validate_json(RawIngestionResult, payload)


def test_result_provenance_must_include_request_policy_and_every_source() -> None:
    payload = _json_payload(_result())
    payload["provenance"]["input_digests"] = [payload["policy_digest"]]
    payload["result_digest"] = "sha256:" + ("0" * 64)
    with pytest.raises(ValidationError, match="input digests are incomplete"):
        _validate_json(RawIngestionResult, payload)


def test_result_digest_detects_semantic_tampering() -> None:
    payload = _json_payload(_result())
    payload["support"]["rationale"] = "Tampered but structurally valid rationale."
    with pytest.raises(ValidationError, match="digest does not match"):
        _validate_json(RawIngestionResult, payload)


def test_result_requires_exact_limitations_unique_evidence_and_sources() -> None:
    payload = _json_payload(_result())
    payload["limitations"][1]["code"] = "raw_ingestion_only"
    payload["result_digest"] = "sha256:" + ("0" * 64)
    with pytest.raises(ValidationError, match="requires both module limitations"):
        _validate_json(RawIngestionResult, payload)

    payload = _json_payload(_result())
    payload["evidence"][1] = deepcopy(payload["evidence"][0])
    payload["result_digest"] = "sha256:" + ("0" * 64)
    with pytest.raises(ValidationError, match="evidence references must be unique"):
        _validate_json(RawIngestionResult, payload)

    payload = _json_payload(_result((_raw_input("one"), _raw_input("two"))))
    payload["raw_inputs"][1]["source_id"] = payload["raw_inputs"][0]["source_id"]
    payload["result_digest"] = "sha256:" + ("0" * 64)
    with pytest.raises(ValidationError, match="unique source identifiers"):
        _validate_json(RawIngestionResult, payload)


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_schema_is_self_identifying_valid_draft_2020_12(name: ContractName) -> None:
    schema = contract_json_schema(name)
    assert schema["$schema"] == JSON_SCHEMA_DIALECT
    assert schema["$id"] == f"{SCHEMA_ID_PREFIX}:{name}"
    Draft202012Validator.check_schema(schema)


def test_schema_declares_strict_runtime_and_relational_keys() -> None:
    request = cast("dict[str, Any]", contract_json_schema("request"))
    output = cast("dict[str, Any]", contract_json_schema("output"))
    assert request["x-glio-validation-profile"] == {
        "id": f"{SCHEMA_ID_PREFIX}:runtime-conformance",
        "strictJson": True,
        "silentCoercion": False,
        "rawContentInOutput": False,
        "authoritativeRuntime": "Pydantic-v2 strict contracts plus the M01-03 parser registry",
        "extensionKeywords": ["x-glio-uniqueBy", "x-glio-relationalInvariants"],
    }
    assert request["properties"]["sources"]["x-glio-uniqueBy"] == "/source_id"
    assert output["properties"]["raw_inputs"]["x-glio-uniqueBy"] == "/source_id"


def test_generated_schemas_accept_valid_public_models() -> None:
    pairs = (("request", _request()), ("output", _result()))
    for name, model in pairs:
        Draft202012Validator(
            contract_json_schema(cast("ContractName", name)),
            format_checker=FormatChecker(),
        ).validate(model.model_dump(mode="json"))


def test_output_schema_exposes_no_raw_or_scientific_claim_fields() -> None:
    schema = contract_json_schema("output")
    property_names: set[str] = set()

    def collect(value: object) -> None:
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict):
                property_names.update(properties)
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    collect(schema)
    assert property_names.isdisjoint(
        {
            "raw_bytes",
            "content",
            "path",
            "file_path",
            "token",
            "patient_id",
            "subject_id",
            "kinase_activity",
            "treatment_recommendation",
            "proteotype",
            "scientific_interpretation",
        }
    )


def test_output_forbids_undeclared_raw_and_scientific_fields() -> None:
    payload = _json_payload(_result())
    payload.update(
        raw_bytes="forbidden",
        path="C:/private/patient.raw",
        kinase_activity=0.9,
        treatment_recommendation="forbidden",
    )
    with pytest.raises(ValidationError):
        _validate_json(RawIngestionResult, payload)


def test_public_schema_snapshots_are_locked() -> None:
    expected = strict_json_loads(SNAPSHOT_PATH.read_bytes())
    actual = {
        "contract_version": CONTRACT_VERSION,
        "dialect": JSON_SCHEMA_DIALECT,
        "schemas": {
            name: {
                "$id": contract_json_schema(name)["$id"],
                "digest": sha256_digest(contract_json_schema(name)),
            }
            for name in SCHEMA_NAMES
        },
    }
    assert actual == expected
