"""Focused M02-03 role-aware raw-ingestion behavior."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest

from glio_proteogen.contracts.m01_03 import Compression, RawFormat, RawIngestionPolicy
from glio_proteogen.contracts.m02_03 import (
    BundleDiagnosticCode,
    IdentificationIngestionPolicy,
    IdentificationRawSource,
    IngestIdentificationRawInputsRequest,
    RawInputDisposition,
    RawInputRole,
    RawSourceDescriptor,
    RoleFormatRequirement,
    RoleRequirement,
    configuration_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c02_identification_qc.m02_03_raw_ingestion import (
    IdentificationRawIngestionAuthorizationError,
    IdentificationRawIngestionSubmission,
    M0203IdentificationRawIngestionEngine,
    M0203Plugin,
    M0203Service,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "m01_03"


def _bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _digest(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"fixture": label}),
        media_type="application/octet-stream",
    )


def _policy() -> IdentificationIngestionPolicy:
    base = RawIngestionPolicy(
        policy_id="policy.m0203.bytes",
        version="1.0.0",
        allowed_formats=tuple(RawFormat),
        allowed_compressions=tuple(Compression),
        max_source_bytes=16_384,
        max_decoded_bytes=32_768,
        max_sources=8,
        max_diagnostics_per_source=16,
        require_checksum=True,
    )
    formats = {
        RawInputRole.SPECTRA: (RawFormat.MZML,),
        RawInputRole.PEPTIDE_IDENTIFICATIONS: (RawFormat.MZIDENTML,),
        RawInputRole.SEQUENCE_DATABASE: (RawFormat.FASTA,),
        RawInputRole.GENOMIC_VARIANTS: (RawFormat.VCF,),
        RawInputRole.TRANSCRIPT_ANNOTATIONS: (RawFormat.GFF3,),
        RawInputRole.PTM_ANNOTATIONS: (RawFormat.MZTAB_M,),
    }
    required = {
        RawInputRole.SPECTRA,
        RawInputRole.PEPTIDE_IDENTIFICATIONS,
        RawInputRole.SEQUENCE_DATABASE,
    }
    return IdentificationIngestionPolicy(
        policy_id="policy.m0203.identification-raw",
        version="1.0.0",
        base_policy=base,
        role_requirements=tuple(
            RoleFormatRequirement(
                role=role,
                requirement=(
                    RoleRequirement.REQUIRED if role in required else RoleRequirement.OPTIONAL
                ),
                allowed_formats=formats[role],
                min_sources=1 if role in required else 0,
                max_sources=2,
            )
            for role in RawInputRole
        ),
    )


def _context(
    policy: IdentificationIngestionPolicy,
    *,
    consent: ConsentState = ConsentState.GRANTED,
) -> ExecutionContext:
    def decision(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role, digest),
        )

    return ExecutionContext(
        request_id="request.m0203.synthetic",
        actor_id="actor.test",
        occurred_at=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", configuration_digest(policy)),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"fixture": "identity"}),
                evidence=_artifact("identity"),
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


def _source(
    role: RawInputRole,
    label: str,
    payload: bytes,
    declared_format: RawFormat | None,
    *,
    digest: str | None = None,
) -> IdentificationRawSource:
    return IdentificationRawSource(
        role=role,
        source=RawSourceDescriptor(
            source_id=f"source.{label}",
            artifact=_artifact(label, digest or _digest(payload)),
            byte_length=len(payload),
            declared_format=declared_format,
            declared_compression=Compression.NONE,
        ),
    )


def _request() -> tuple[IngestIdentificationRawInputsRequest, dict[str, bytes]]:
    policy = _policy()
    values = (
        (RawInputRole.SPECTRA, "spectra", _bytes("mzml.valid.mzML"), RawFormat.MZML),
        (
            RawInputRole.PEPTIDE_IDENTIFICATIONS,
            "identifications",
            _bytes("mzidentml.valid.mzid"),
            RawFormat.MZIDENTML,
        ),
        (
            RawInputRole.SEQUENCE_DATABASE,
            "database",
            _bytes("proteins.valid.fasta"),
            RawFormat.FASTA,
        ),
    )
    sources = tuple(_source(*item) for item in values)
    request = IngestIdentificationRawInputsRequest(
        context=_context(policy),
        policy=policy,
        sources=sources,
    )
    payloads = {
        item.source.source_id: payload
        for item, (_, _, payload, _) in zip(sources, values, strict=True)
    }
    return request, payloads


def test_conformant_bundle_is_metadata_only_and_deterministic() -> None:
    request, payloads = _request()
    engine = M0203IdentificationRawIngestionEngine()
    first = engine.evaluate(request, payloads)
    reversed_request = IngestIdentificationRawInputsRequest(
        context=request.context,
        policy=request.policy.model_copy(
            update={"role_requirements": tuple(reversed(request.policy.role_requirements))}
        ),
        sources=tuple(reversed(request.sources)),
    )
    second = engine.evaluate(reversed_request, dict(reversed(tuple(payloads.items()))))

    assert first.disposition is RawInputDisposition.ACCEPTED
    assert second == first
    serialized = first.model_dump_json()
    assert "<mzML" not in serialized
    assert "MPEPTIDE" not in serialized
    assert "synthetic-run-1" not in serialized


def test_binary_streams_match_bytes_and_plugin_snapshots_once() -> None:
    request, payloads = _request()
    expected = M0203IdentificationRawIngestionEngine().evaluate(request, payloads)
    streams = {source_id: BytesIO(payload) for source_id, payload in payloads.items()}
    engine_result = M0203IdentificationRawIngestionEngine().evaluate(request, streams)
    plugin = M0203Plugin(M0203Service())
    token = plugin.validate(
        IdentificationRawIngestionSubmission(
            request,
            {source_id: BytesIO(payload) for source_id, payload in payloads.items()},
        )
    )

    assert engine_result == expected
    assert plugin.run(token) == expected
    assert plugin.run(token) == expected


def test_oversized_binary_stream_is_bounded_and_rejected() -> None:
    request, payloads = _request()
    limit = request.policy.base_policy.max_source_bytes
    payload = b"x" * (limit + 4096)
    spectra = _source(
        RawInputRole.SPECTRA,
        "spectra",
        payload[:limit],
        RawFormat.MZML,
    )
    request = IngestIdentificationRawInputsRequest(
        context=request.context,
        policy=request.policy,
        sources=tuple(
            spectra if item.role is RawInputRole.SPECTRA else item
            for item in request.sources
        ),
    )
    payloads[spectra.source.source_id] = BytesIO(payload)

    result = M0203IdentificationRawIngestionEngine().evaluate(request, payloads)
    raw_input = next(
        item.raw_input for item in result.raw_inputs if item.role is RawInputRole.SPECTRA
    )

    assert result.disposition is RawInputDisposition.REJECTED
    assert raw_input.source_size_bytes == limit + 1
    assert "raw_size_limit_exceeded" in {item.code for item in raw_input.diagnostics}


def test_missing_required_role_quarantines() -> None:
    request, payloads = _request()
    kept = tuple(
        item
        for item in request.sources
        if item.role is not RawInputRole.PEPTIDE_IDENTIFICATIONS
    )
    missing_id = next(
        item.source.source_id
        for item in request.sources
        if item.role is RawInputRole.PEPTIDE_IDENTIFICATIONS
    )
    request = IngestIdentificationRawInputsRequest(
        context=request.context,
        policy=request.policy,
        sources=kept,
    )
    payloads.pop(missing_id)
    result = M0203IdentificationRawIngestionEngine().evaluate(request, payloads)
    assert result.disposition is RawInputDisposition.QUARANTINED
    assert BundleDiagnosticCode.REQUIRED_ROLE_MISSING in {
        item.code for item in result.bundle_diagnostics
    }


def test_detected_role_format_mismatch_quarantines() -> None:
    request, payloads = _request()
    vcf = _bytes("variants.valid.vcf")
    spectra = next(item for item in request.sources if item.role is RawInputRole.SPECTRA)
    replacement = _source(RawInputRole.SPECTRA, "spectra", vcf, None)
    request = IngestIdentificationRawInputsRequest(
        context=request.context,
        policy=request.policy,
        sources=tuple(replacement if item is spectra else item for item in request.sources),
    )
    payloads[replacement.source.source_id] = vcf
    result = M0203IdentificationRawIngestionEngine().evaluate(request, payloads)
    assert result.disposition is RawInputDisposition.QUARANTINED
    assert BundleDiagnosticCode.ROLE_FORMAT_MISMATCH in {
        item.code for item in result.bundle_diagnostics
    }


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("mzml.truncated.invalid.mzML", RawInputDisposition.QUARANTINED),
        ("mzml.valid.mzML", RawInputDisposition.REJECTED),
    ],
)
def test_parser_failures_remain_typed(fixture: str, expected: RawInputDisposition) -> None:
    request, payloads = _request()
    payload = _bytes(fixture)
    wrong_checksum = expected is RawInputDisposition.REJECTED
    source = _source(
        RawInputRole.SPECTRA,
        "spectra",
        payload,
        RawFormat.MZML,
        digest=sha256_digest({"wrong": True}) if wrong_checksum else None,
    )
    request = IngestIdentificationRawInputsRequest(
        context=request.context,
        policy=request.policy,
        sources=tuple(
            source if item.role is RawInputRole.SPECTRA else item
            for item in request.sources
        ),
    )
    payloads[source.source.source_id] = payload
    result = M0203IdentificationRawIngestionEngine().evaluate(request, payloads)
    assert result.disposition is expected


class _UnreadableSources(Mapping[str, bytes]):
    _MESSAGE = "source mapping was traversed"

    def __getitem__(self, key: str) -> bytes:
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        raise AssertionError(self._MESSAGE)

    def __len__(self) -> int:
        raise AssertionError(self._MESSAGE)


def test_denied_consent_precedes_source_traversal() -> None:
    request, _ = _request()
    denied = request.model_dump(mode="python")
    denied["context"]["references"]["consent"]["state"] = "withheld"
    with pytest.raises(IdentificationRawIngestionAuthorizationError):
        M0203IdentificationRawIngestionEngine().evaluate(denied, _UnreadableSources())


def test_plugin_strict_json_validate_and_run() -> None:
    request, payloads = _request()
    plugin = M0203Plugin(M0203Service())
    token = plugin.validate(
        IdentificationRawIngestionSubmission(request.model_dump_json(), payloads)
    )
    assert plugin.run(token).disposition is RawInputDisposition.ACCEPTED
    assert plugin.descriptor().owner == "ML engineering"
