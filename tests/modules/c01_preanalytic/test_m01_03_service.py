"""Focused service and agent-plugin behavior for M01-03."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

import pytest

from glio_proteogen.contracts.m01_03 import (
    Compression,
    IngestRawInputsRequest,
    RawFormat,
    RawIngestionPolicy,
    RawInputDisposition,
    RawSourceDescriptor,
    policy_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EstimateState,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion import (
    M0103Plugin,
    M0103Service,
    RawIngestionAuthorizationError,
    RawIngestionInputError,
    RawIngestionInputErrorCode,
    RawIngestionSubmission,
    RawInputSource,
    ValidatedM0103Request,
)

FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "m01_03"
_FASTA_RECORDS: Final = 2


def _fixture(name: str) -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def _digest(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"fixture": label}),
        media_type="application/octet-stream",
    )


def _policy(
    *,
    allowed_formats: tuple[RawFormat, ...] = tuple(RawFormat),
    max_source_bytes: int = 4096,
) -> RawIngestionPolicy:
    return RawIngestionPolicy(
        policy_id="policy.raw-ingestion",
        version="1.0.0",
        allowed_formats=allowed_formats,
        allowed_compressions=tuple(Compression),
        max_source_bytes=max_source_bytes,
        max_decoded_bytes=8192,
        max_sources=4,
        max_diagnostics_per_source=16,
        require_checksum=True,
    )


def _context(
    policy: RawIngestionPolicy,
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
        request_id="request.raw-ingestion",
        actor_id="actor.test",
        occurred_at=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", policy_digest(policy)),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity-lineage",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"fixture": "identity-binding"}),
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


def _source(  # noqa: PLR0913 - fixture builder mirrors the source declaration.
    label: str,
    payload: bytes,
    *,
    raw_format: RawFormat | None = RawFormat.FASTA,
    version: str | None = None,
    compression: Compression | None = Compression.NONE,
    byte_length: int | None = None,
) -> RawSourceDescriptor:
    return RawSourceDescriptor(
        source_id=f"source.{label}",
        artifact=_artifact(f"source-{label}", _digest(payload)),
        byte_length=len(payload) if byte_length is None else byte_length,
        declared_format=raw_format,
        declared_version=version,
        declared_compression=compression,
    )


def _request(
    source: RawSourceDescriptor,
    *,
    policy: RawIngestionPolicy | None = None,
) -> IngestRawInputsRequest:
    active_policy = policy or _policy()
    return IngestRawInputsRequest(
        context=_context(active_policy),
        policy=active_policy,
        sources=(source,),
    )


def test_service_emits_deterministic_metadata_only_envelope() -> None:
    private_marker = "PRIVATESEQUENCEMARKER"
    payload = f">synthetic\nACGT{private_marker}\n".encode()
    request = _request(_source("fasta", payload))
    service = M0103Service()

    first = service.execute(request, {"source.fasta": payload}, {"source.fasta": "input.fa"})
    second = service.execute(request, {"source.fasta": payload}, {"source.fasta": "input.fa"})

    assert second == first
    assert first.disposition is RawInputDisposition.ACCEPTED
    assert first.completed_at == request.context.occurred_at
    assert first.raw_inputs[0].record_count == 1
    assert all(
        estimate.state is EstimateState.NOT_ESTIMABLE
        for estimate in (
            first.uncertainty.measurement,
            first.uncertainty.sampling,
            first.uncertainty.parameter,
            first.uncertainty.model_form,
            first.uncertainty.identification,
            first.uncertainty.support,
            first.uncertainty.transport,
        )
    )
    serialized = first.model_dump_json()
    assert private_marker not in serialized
    assert private_marker not in serialized


class _UnreadableStream:
    def read(self, _size: int = -1) -> bytes:
        raise AssertionError


def test_explicit_denial_fails_before_source_access() -> None:
    payload = _fixture("proteins.valid.fasta")
    request = _request(_source("denied", payload))
    denied = request.model_dump(mode="python")
    denied["context"]["references"]["consent"]["state"] = "revoked"

    with pytest.raises(RawIngestionAuthorizationError) as caught:
        M0103Service().execute(
            denied,
            {"source.denied": cast("RawInputSource", _UnreadableStream())},
        )

    assert caught.value.role.value == "consent"


@pytest.mark.parametrize(
    "sources",
    [
        {},
        {
            "source.fasta": _fixture("proteins.valid.fasta"),
            "source.extra": b"synthetic",
        },
    ],
)
def test_source_set_must_exactly_match_request(sources: dict[str, bytes]) -> None:
    payload = _fixture("proteins.valid.fasta")
    request = _request(_source("fasta", payload))

    with pytest.raises(RawIngestionInputError) as caught:
        M0103Service().execute(request, sources)

    assert caught.value.code is RawIngestionInputErrorCode.SOURCE_SET_MISMATCH


def test_declaration_mismatch_quarantines_with_safe_fixed_diagnostic() -> None:
    payload = _fixture("proteins.valid.fasta")
    source = _source(
        "declared-vcf",
        payload,
        raw_format=RawFormat.VCF,
        version="4.5",
        byte_length=len(payload) - 1,
    )
    result = M0103Service().execute(
        _request(source),
        {source.source_id: payload},
        {source.source_id: "private-name.vcf"},
    )

    descriptor = result.raw_inputs[0]
    assert descriptor.disposition is RawInputDisposition.QUARANTINED
    assert descriptor.detected is not None
    assert descriptor.detected.format is RawFormat.FASTA
    assert descriptor.record_count == _FASTA_RECORDS
    assert descriptor.structural_validation_passed is False
    assert {diagnostic.code for diagnostic in descriptor.diagnostics} >= {
        "declared_size_mismatch",
        "declared_format_mismatch",
        "declared_version_mismatch",
    }
    assert "private-name" not in result.model_dump_json()


def test_detected_format_disabled_by_policy_is_quarantined() -> None:
    payload = _fixture("proteins.valid.fasta")
    policy = _policy(allowed_formats=(RawFormat.VCF,))
    source = _source("policy", payload, raw_format=None, compression=None)
    result = M0103Service().execute(
        _request(source, policy=policy),
        {source.source_id: payload},
    )

    descriptor = result.raw_inputs[0]
    assert descriptor.disposition is RawInputDisposition.QUARANTINED
    assert descriptor.diagnostics[0].code == "detected_format_disabled"
    assert result.human_review_required is True


def test_integrity_failure_rejects_the_batch() -> None:
    payload = _fixture("proteins.valid.fasta")
    source = _source("checksum", payload).model_copy(
        update={"artifact": _artifact("wrong-source", "sha256:" + ("0" * 64))}
    )
    request = _request(source)

    result = M0103Service().execute(request, {source.source_id: payload})

    assert result.disposition is RawInputDisposition.REJECTED
    assert result.raw_inputs[0].diagnostics[0].code == "checksum_mismatch"
    assert result.support.reason_code == "raw_input_rejected"


def test_known_total_bytes_are_bounded_before_parsing() -> None:
    payload = _fixture("proteins.valid.fasta")
    policy = _policy(max_source_bytes=len(payload))
    source = _source("total", payload)
    request = _request(source, policy=policy)

    with pytest.raises(RawIngestionInputError) as caught:
        M0103Service().execute(request, {source.source_id: payload + b"X"})

    assert caught.value.code is RawIngestionInputErrorCode.TOTAL_INPUT_LIMIT_EXCEEDED


def test_plugin_accepts_strict_json_and_revalidates_execution() -> None:
    payload = _fixture("proteins.valid.fasta")
    source = _source("plugin", payload)
    request = _request(source)
    plugin = M0103Plugin(M0103Service())

    token = plugin.validate(
        RawIngestionSubmission(
            request=request.model_dump_json(),
            sources={source.source_id: bytearray(payload)},
            filenames={source.source_id: "input.fasta"},
        )
    )
    result = plugin.run(token)

    assert isinstance(token, ValidatedM0103Request)
    assert result.disposition is RawInputDisposition.ACCEPTED
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M01-03"

    denied_consent = request.context.references.consent.model_copy(
        update={"state": ConsentState.REVOKED}
    )
    denied_references = request.context.references.model_copy(
        update={"consent": denied_consent}
    )
    denied_context = request.context.model_copy(update={"references": denied_references})
    forged_request = request.model_copy(update={"context": denied_context})
    forged = ValidatedM0103Request(
        request=forged_request,
        sources=token.sources,
        filenames=token.filenames,
    )
    with pytest.raises(RawIngestionAuthorizationError):
        plugin.run(forged)


def test_plugin_rejects_forged_token_type_and_unknown_filename_key() -> None:
    payload = _fixture("proteins.valid.fasta")
    source = _source("plugin-errors", payload)
    request = _request(source)
    plugin = M0103Plugin(M0103Service())

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("ValidatedM0103Request", object()))
    with pytest.raises(RawIngestionInputError) as caught:
        plugin.validate(
            RawIngestionSubmission(
                request=request,
                sources={source.source_id: payload},
                filenames={"source.unknown": "unknown.fasta"},
            )
        )

    assert caught.value.code is RawIngestionInputErrorCode.FILENAME_SET_MISMATCH
