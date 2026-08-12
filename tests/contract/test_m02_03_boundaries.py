"""Compact relational and maximum-shape boundaries for M02-03."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m01_03 import (
    Compression,
    RawFormat,
    RawIngestionPolicy,
    RawInputDisposition,
    RawSourceDescriptor,
)
from glio_proteogen.contracts.m02_03 import (
    BundleDiagnosticCode,
    IdentificationIngestionPolicy,
    IdentificationRawIngestionResult,
    IdentificationRawSource,
    IngestIdentificationRawInputsRequest,
    RawInputRole,
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
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c02_identification_qc.m02_03_raw_ingestion import (
    evaluate_identification_raw_ingestion,
)

pytestmark = pytest.mark.contract
ZERO = "sha256:" + ("0" * 64)
BAD = "sha256:" + ("f" * 64)
FASTA = b">synthetic\nMPEPTIDE\n"
MAX_SOURCES = 64


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"fixture": label}),
        media_type="application/octet-stream",
    )


def _policy(*, max_sources: int = 64) -> IdentificationIngestionPolicy:
    base = RawIngestionPolicy(
        policy_id="policy.synthetic.m0203.base",
        version="1.0.0",
        allowed_formats=tuple(RawFormat),
        allowed_compressions=tuple(Compression),
        max_source_bytes=1024,
        max_decoded_bytes=2048,
        max_sources=max_sources,
        max_diagnostics_per_source=16,
        require_checksum=True,
    )
    allowed = {
        RawInputRole.SPECTRA: (RawFormat.MZML,),
        RawInputRole.PEPTIDE_IDENTIFICATIONS: (RawFormat.MZIDENTML,),
        RawInputRole.SEQUENCE_DATABASE: (RawFormat.FASTA,),
        RawInputRole.GENOMIC_VARIANTS: (RawFormat.VCF,),
        RawInputRole.TRANSCRIPT_ANNOTATIONS: (RawFormat.GFF3,),
        RawInputRole.PTM_ANNOTATIONS: (RawFormat.MZTAB_M,),
    }
    return IdentificationIngestionPolicy(
        policy_id="policy.synthetic.m0203",
        version="1.0.0",
        base_policy=base,
        role_requirements=tuple(
            RoleFormatRequirement(
                role=role,
                requirement=RoleRequirement.OPTIONAL,
                allowed_formats=allowed[role],
                min_sources=0,
                max_sources=max_sources,
            )
            for role in RawInputRole
        ),
    )


def _context(policy: IdentificationIngestionPolicy) -> ExecutionContext:
    def accepted(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role, digest),
        )

    return ExecutionContext(
        request_id="request.synthetic.m0203",
        actor_id="actor.synthetic.m0203",
        occurred_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted("configuration", configuration_digest(policy)),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"fixture": "identity"}),
                evidence=_artifact("identity"),
            ),
            provenance=accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=accepted("quality"),
            support=accepted("support"),
            intended_use=accepted("intended-use"),
        ),
    )


def _source(
    label: str,
    *,
    role: RawInputRole = RawInputRole.SEQUENCE_DATABASE,
) -> IdentificationRawSource:
    return IdentificationRawSource(
        role=role,
        source=RawSourceDescriptor(
            source_id=f"source.synthetic.{label}",
            artifact=_artifact(label, f"sha256:{hashlib.sha256(FASTA).hexdigest()}"),
            byte_length=len(FASTA),
            declared_format=(RawFormat.FASTA if role is RawInputRole.SEQUENCE_DATABASE else None),
            declared_compression=Compression.NONE,
        ),
    )


def _request() -> tuple[IngestIdentificationRawInputsRequest, dict[str, bytes]]:
    policy = _policy()
    source = _source("one")
    request = IngestIdentificationRawInputsRequest(
        context=_context(policy),
        policy=policy,
        sources=(source,),
    )
    return request, {source.source.source_id: FASTA}


def _result() -> IdentificationRawIngestionResult:
    request, payloads = _request()
    return evaluate_identification_raw_ingestion(request, payloads)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_format", "role formats must be unique"),
        ("required_zero", "required roles must require"),
        ("optional_nonzero", "optional roles must permit zero"),
        ("inverted_range", "minimum cannot exceed"),
    ],
)
def test_role_requirement_is_closed(case: str, message: str) -> None:
    values = _policy().role_requirements[0].model_dump(mode="python")
    if case == "duplicate_format":
        values["allowed_formats"] = (RawFormat.MZML, RawFormat.MZML)
    elif case == "required_zero":
        values["requirement"] = RoleRequirement.REQUIRED
    elif case == "optional_nonzero":
        values["min_sources"] = 1
    else:
        values["min_sources"] = 2
        values["max_sources"] = 1

    with pytest.raises(ValidationError, match=message):
        RoleFormatRequirement.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_role", "unique roles"),
        ("missing_role", "explicitly govern every"),
        ("disabled_format", "enabled by the base"),
        ("role_cap", "maximum exceeds"),
    ],
)
def test_policy_is_closed_over_every_role(case: str, message: str) -> None:
    values = _policy(max_sources=8).model_dump(mode="python")
    if case == "duplicate_role":
        values["role_requirements"] = (
            values["role_requirements"][0],
            *values["role_requirements"][:-1],
        )
    elif case == "missing_role":
        values["role_requirements"] = values["role_requirements"][:-1]
    elif case == "disabled_format":
        values["base_policy"]["allowed_formats"] = (RawFormat.FASTA,)
    else:
        values["role_requirements"][0]["max_sources"] = 9

    with pytest.raises(ValidationError, match=message):
        IdentificationIngestionPolicy.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_source", "identifiers must be unique"),
        ("source_cap", "source count exceeds"),
        ("role_format", "not allowed for the raw-input role"),
        ("configuration", "does not bind"),
        ("consent", "consent does not authorize"),
        ("quality", "generic upstream control"),
    ],
)
def test_request_closes_sources_policy_and_authority(case: str, message: str) -> None:
    request, _ = _request()
    values = request.model_dump(mode="python")
    if case == "duplicate_source":
        values["sources"] = (*values["sources"], deepcopy(values["sources"][0]))
    elif case == "source_cap":
        values["policy"]["base_policy"]["max_sources"] = 1
        for requirement in values["policy"]["role_requirements"]:
            requirement["max_sources"] = 1
        extra = deepcopy(values["sources"][0])
        extra["source"]["source_id"] = "source.synthetic.extra"
        extra["source"]["artifact"]["artifact_id"] = "artifact.synthetic.extra"
        values["sources"] = (*values["sources"], extra)
    elif case == "role_format":
        values["sources"][0]["role"] = RawInputRole.SPECTRA
    elif case == "configuration":
        values["context"]["references"]["approved_configuration"]["evidence"]["digest"] = BAD
    elif case == "consent":
        values["context"]["references"]["consent"]["state"] = ConsentState.WITHHELD
    else:
        values["context"]["references"]["quality"]["state"] = UpstreamDecisionState.REJECTED

    with pytest.raises(ValidationError, match=message):
        IngestIdentificationRawInputsRequest.model_validate(values, strict=True)


def _forged_result(case: str) -> dict[str, Any]:
    values = _result().model_dump(mode="python")
    values["result_digest"] = ZERO
    if case == "duplicate_source":
        values["raw_inputs"] = (*values["raw_inputs"], deepcopy(values["raw_inputs"][0]))
    elif case == "disposition":
        values["disposition"] = RawInputDisposition.QUARANTINED
    elif case == "support":
        values["support"]["status"] = SupportStatus.REVIEW_REQUIRED
    elif case == "ingestion_id":
        values["ingestion_id"] = "ingestion.m0203.wrong"
    elif case == "provenance":
        values["provenance"]["input_digests"] = tuple(
            item
            for item in values["provenance"]["input_digests"]
            if item != values["policy_digest"]
        )
    elif case == "limitation":
        values["limitations"][0]["code"] = "wrong_limitation"
    elif case == "diagnostic_role":
        database = next(
            item
            for item in values["raw_inputs"]
            if item["role"] is RawInputRole.SEQUENCE_DATABASE
        )
        values["bundle_diagnostics"] = (
            {
                "code": BundleDiagnosticCode.ROLE_FORMAT_MISMATCH,
                "role": RawInputRole.SPECTRA,
                "source_ids": (database["raw_input"]["source_id"],),
                "severity": "error",
                "action": "quarantine",
                "message": "Detected content is not allowed for its raw-input role.",
            },
        )
        values["disposition"] = RawInputDisposition.QUARANTINED
        values["support"] = {
            "status": SupportStatus.REVIEW_REQUIRED,
            "reason_code": "identification_raw_inputs_quarantined",
            "rationale": "One or more raw inputs or bundle rules require review.",
        }
        values["human_review_required"] = True
    else:
        values["result_digest"] = BAD
    return values


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_source", "unique source identifiers"),
        ("disposition", "disposition contradicts"),
        ("support", "support contradicts"),
        ("ingestion_id", "identifier does not bind"),
        ("provenance", "provenance inputs are incomplete"),
        ("limitation", "requires both limitation codes"),
        ("diagnostic_role", "source roles contradict"),
        ("digest", "digest does not match"),
    ],
)
def test_result_envelope_rejects_forgery(case: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        IdentificationRawIngestionResult.model_validate(
            _forged_result(case),
            strict=True,
        )


def test_sixty_four_source_role_mismatch_is_representable_and_aggregated() -> None:
    policy = _policy(max_sources=MAX_SOURCES)
    sources = tuple(
        _source(f"max.{index:02d}", role=RawInputRole.PTM_ANNOTATIONS)
        for index in range(MAX_SOURCES)
    )
    request = IngestIdentificationRawInputsRequest(
        context=_context(policy),
        policy=policy,
        sources=tuple(reversed(sources)),
    )
    payloads = {item.source.source_id: FASTA for item in reversed(sources)}

    result = evaluate_identification_raw_ingestion(request, payloads)

    assert result.disposition is RawInputDisposition.QUARANTINED
    assert len(result.raw_inputs) == MAX_SOURCES
    assert len(result.bundle_diagnostics) == 1
    diagnostic = result.bundle_diagnostics[0]
    assert diagnostic.code is BundleDiagnosticCode.ROLE_FORMAT_MISMATCH
    assert diagnostic.role is RawInputRole.PTM_ANNOTATIONS
    assert diagnostic.source_ids == tuple(sorted(diagnostic.source_ids))
    assert len(diagnostic.source_ids) == MAX_SOURCES
    assert IdentificationRawIngestionResult.model_validate(
        result.model_dump(mode="python"),
        strict=True,
    ) == result
