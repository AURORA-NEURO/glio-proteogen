"""Focused M03-03 runtime lifecycle, byte-boundary, and capability tests."""

from __future__ import annotations

import gzip
import hashlib
from collections.abc import Iterator, Mapping
from io import BytesIO

import pytest
from evals.m03_03.run import ScenarioOptions, build_scenario

from glio_proteogen.contracts.m03_03 import (
    IngestProteinInferenceRawInputsRequest,
    ProteinInferenceAdmissionDisposition,
    ProteinInferenceCompression,
    ProteinInferenceDiagnosticCode,
    ProteinInferenceRawRole,
    ProteinInferenceRawSource,
    configuration_digest,
    lineage_receipt_digest,
    source_manifest_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ConsentState,
    IdentityLineageState,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c03_protein_inference.m03_03_raw_ingestion import (
    M0303Plugin,
    M0303ProteinInferenceRawIngestionEngine,
    M0303Service,
    ProteinInferenceRawIngestionAuthorizationError,
    ProteinInferenceRawIngestionSubmission,
    ValidatedM0303Request,
    ingest_protein_inference_raw_inputs,
    preflight_protein_inference_raw_ingestion_authorization,
)


def test_canonical_capsule_is_metadata_only_and_deterministic() -> None:
    scenario = build_scenario()
    first = ingest_protein_inference_raw_inputs(scenario.request, scenario.sources)
    second = M0303ProteinInferenceRawIngestionEngine().ingest(
        scenario.request,
        dict(reversed(tuple(scenario.sources.items()))),
    )

    assert first == second
    assert first.disposition is ProteinInferenceAdmissionDisposition.VALIDATED
    assert len(first.raw_inputs) == len(scenario.request.sources)
    assert first.diagnostics == ()
    serialized = first.model_dump_json()
    assert "MPEPTIDEK" not in serialized
    assert "scan=1" not in serialized
    assert "group.synthetic.1" not in serialized
    assert first.receipt.emits_complex_activity is False
    assert first.receipt.infers_protein is False
    assert first.receipt.infers_kinase_activity is False


def test_semantic_request_reordering_preserves_complete_result_equality() -> None:
    scenario = build_scenario()
    request = scenario.request.model_copy(
        update={
            "sources": tuple(reversed(scenario.request.sources)),
            "lineage_receipt": scenario.request.lineage_receipt.model_copy(
                update={"artifacts": tuple(reversed(scenario.request.lineage_receipt.artifacts))}
            ),
        }
    )

    assert ingest_protein_inference_raw_inputs(request, scenario.sources) == (
        ingest_protein_inference_raw_inputs(scenario.request, scenario.sources)
    )


@pytest.mark.parametrize(
    ("role", "state"),
    [
        ("approved_configuration", UpstreamDecisionState.REJECTED),
        ("identity_lineage", IdentityLineageState.CONFLICTED),
        ("provenance", UpstreamDecisionState.REJECTED),
        ("consent", ConsentState.REVOKED),
        ("quality", UpstreamDecisionState.REJECTED),
        ("support", UpstreamDecisionState.REJECTED),
        ("intended_use", UpstreamDecisionState.REJECTED),
    ],
)
def test_all_seven_denials_precede_hostile_source_mapping(role: str, state: object) -> None:
    scenario = build_scenario()
    payload = scenario.request.model_dump(mode="python")
    payload["context"]["references"][role]["state"] = state
    with pytest.raises(ProteinInferenceRawIngestionAuthorizationError):
        ingest_protein_inference_raw_inputs(payload, _UnreadableMapping())


class _ProtectedTraversal(BaseException):
    pass


class _ExceptionBoundary(Mapping[str, object]):
    def __getitem__(self, _key: str) -> object:
        raise RuntimeError

    def __iter__(self) -> Iterator[str]:
        return iter(())

    def __len__(self) -> int:
        return 0


class _BaseExceptionBoundary(_ExceptionBoundary):
    def __getitem__(self, _key: str) -> object:
        raise _ProtectedTraversal


def test_preflight_suppresses_exception_but_never_base_exception() -> None:
    with pytest.raises(ProteinInferenceRawIngestionAuthorizationError):
        preflight_protein_inference_raw_ingestion_authorization(_ExceptionBoundary())
    with pytest.raises(_ProtectedTraversal):
        preflight_protein_inference_raw_ingestion_authorization(_BaseExceptionBoundary())


class _UnreadableMapping(Mapping[str, bytes]):
    _MESSAGE = "source mapping traversed"

    def __getitem__(self, key: str) -> bytes:
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        raise AssertionError(self._MESSAGE)

    def __len__(self) -> int:
        raise AssertionError(self._MESSAGE)


def test_upstream_shape_safe_failure_has_zero_mapping_traversal() -> None:
    scenario = build_scenario()
    policy = scenario.request.policy.model_copy(update={"max_lineage_artifacts": 3})
    approved = scenario.request.context.references.approved_configuration
    references = scenario.request.context.references.model_copy(
        update={
            "approved_configuration": approved.model_copy(
                update={
                    "evidence": approved.evidence.model_copy(
                        update={"digest": configuration_digest(policy)}
                    )
                }
            )
        }
    )
    request = scenario.request.model_copy(
        update={
            "context": scenario.request.context.model_copy(update={"references": references}),
            "policy": policy,
            "sources": (),
            "source_manifest_digest": source_manifest_digest(()),
        }
    )
    result = ingest_protein_inference_raw_inputs(request, _UnreadableMapping())
    assert result.raw_inputs == ()
    assert result.disposition is ProteinInferenceAdmissionDisposition.ABSTAINED
    assert {item.code for item in result.diagnostics} == {
        ProteinInferenceDiagnosticCode.UPSTREAM_SHAPE_UNSUPPORTED
    }


class _ReadOnce(BytesIO):
    def __init__(self, value: bytes) -> None:
        super().__init__(value)
        self.calls = 0

    def read(self, size: int | None = -1) -> bytes:
        self.calls += 1
        return super().read(size)


def test_plugin_snapshots_streams_and_prevents_toctou() -> None:
    scenario = build_scenario()
    streams = {key: _ReadOnce(value) for key, value in scenario.sources.items()}
    plugin = M0303Plugin(M0303Service())
    token = plugin.validate(ProteinInferenceRawIngestionSubmission(scenario.request, streams))
    before = {key: stream.calls for key, stream in streams.items()}
    result = plugin.run(token)

    assert isinstance(token, ValidatedM0303Request)
    assert result.disposition is ProteinInferenceAdmissionDisposition.VALIDATED
    assert {key: stream.calls for key, stream in streams.items()} == before
    assert all(value >= 1 for value in before.values())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(scenario.request)  # type: ignore[arg-type]


def test_typed_dict_and_strict_json_plugin_paths_are_equal() -> None:
    scenario = build_scenario()
    plugin = M0303Plugin(M0303Service())
    typed = plugin.run(
        plugin.validate(ProteinInferenceRawIngestionSubmission(scenario.request, scenario.sources))
    )
    encoded = canonical_json_bytes(scenario.request.model_dump(mode="json"))
    strict = plugin.run(
        plugin.validate(ProteinInferenceRawIngestionSubmission(encoded, scenario.sources))
    )

    assert typed == strict
    assert plugin.descriptor().owner == "Quality engineering"


def test_checksum_failure_is_rejected_and_content_free() -> None:
    scenario = build_scenario()
    source_id = next(
        item.source_id
        for item in scenario.request.sources
        if item.role is ProteinInferenceRawRole.SPECTRA
    )
    sources = {**scenario.sources, source_id: scenario.sources[source_id] + b"x"}
    result = ingest_protein_inference_raw_inputs(scenario.request, sources)

    assert result.disposition is ProteinInferenceAdmissionDisposition.REJECTED
    codes = {item.code for item in result.diagnostics}
    assert ProteinInferenceDiagnosticCode.DECLARED_SIZE_MISMATCH in codes
    assert "<mzML" not in result.model_dump_json()


def test_mzidentml_duplicate_xml_ids_are_quarantined() -> None:
    payload = (
        b'<?xml version="1.0"?>'
        b'<MzIdentML xmlns="http://psidev.info/psi/pi/mzIdentML/1.3" version="1.3.0">'
        b"<DataCollection><Inputs>"
        b'<SearchDatabase id="database-1" databaseName="build.synthetic.targets-decoys-v1" '
        b'version="2026.1.0"/><SpectraData id="spectra-1"/>'
        b'<SpectraData id="spectra-1"/>'
        b"</Inputs><AnalysisData>"
        b'<SpectrumIdentificationList id="list-1"><SpectrumIdentificationResult '
        b'id="result-1" spectraData_ref="spectra-1"/></SpectrumIdentificationList>'
        b"</AnalysisData></DataCollection></MzIdentML>"
    )
    scenario = build_scenario(
        options=ScenarioOptions(raw_overrides={ProteinInferenceRawRole.PEPTIDE_EVIDENCE: payload})
    )

    result = ingest_protein_inference_raw_inputs(scenario.request, scenario.sources)

    assert result.disposition is ProteinInferenceAdmissionDisposition.QUARANTINED
    assert ProteinInferenceDiagnosticCode.MALFORMED_CONTENT in {
        item.code for item in result.diagnostics
    }


def test_mzidentml_dangling_reference_is_quarantined() -> None:
    scenario = build_scenario()
    source_id = next(
        item.source_id
        for item in scenario.request.sources
        if item.role is ProteinInferenceRawRole.PEPTIDE_EVIDENCE
    )
    payload = scenario.sources[source_id].replace(
        b"</Inputs><AnalysisData>",
        b'<PeptideEvidence id="evidence-1" peptide_ref="missing-peptide" '
        b'dBSequence_ref="missing-db"/></Inputs><AnalysisData>',
    )
    scenario = build_scenario(
        options=ScenarioOptions(raw_overrides={ProteinInferenceRawRole.PEPTIDE_EVIDENCE: payload})
    )

    result = ingest_protein_inference_raw_inputs(scenario.request, scenario.sources)

    assert result.disposition is ProteinInferenceAdmissionDisposition.QUARANTINED
    assert ProteinInferenceDiagnosticCode.DANGLING_REFERENCE in {
        item.code for item in result.diagnostics
    }


def test_fasta_duplicate_sequence_identifiers_are_quarantined() -> None:
    payload = b">duplicate first\nMPEPTIDEK\n>duplicate second\nKEDITPEPM\n"
    scenario = build_scenario(
        options=ScenarioOptions(
            raw_overrides={ProteinInferenceRawRole.CANONICAL_SEQUENCES: payload}
        )
    )

    result = ingest_protein_inference_raw_inputs(scenario.request, scenario.sources)

    assert result.disposition is ProteinInferenceAdmissionDisposition.QUARANTINED
    assert ProteinInferenceDiagnosticCode.MALFORMED_CONTENT in {
        item.code for item in result.diagnostics
    }


def test_concatenated_or_trailing_gzip_is_rejected() -> None:
    scenario = build_scenario(gzip_roles=frozenset({ProteinInferenceRawRole.SPECTRA}))
    source = next(
        item for item in scenario.request.sources if item.role is ProteinInferenceRawRole.SPECTRA
    )
    extra = gzip.compress(b"extra", mtime=0)
    raw = scenario.sources[source.source_id] + extra
    declaration = source.model_copy(
        update={
            "artifact": source.artifact.model_copy(
                update={"digest": f"sha256:{hashlib.sha256(raw).hexdigest()}"}
            ),
            "byte_length": len(raw),
        }
    )
    request = _replace_source(scenario.request, source, declaration)
    result = ingest_protein_inference_raw_inputs(
        request,
        {**scenario.sources, source.source_id: raw},
    )

    assert result.disposition is ProteinInferenceAdmissionDisposition.REJECTED
    assert ProteinInferenceDiagnosticCode.INVALID_GZIP in {item.code for item in result.diagnostics}


def test_decoded_limit_failure_carries_exact_cap_sentinel() -> None:
    scenario = build_scenario()
    request = scenario.request
    policy = request.policy.model_copy(update={"max_source_bytes": 600, "max_decoded_bytes": 600})
    approved = request.context.references.approved_configuration
    references = request.context.references.model_copy(
        update={
            "approved_configuration": approved.model_copy(
                update={
                    "evidence": approved.evidence.model_copy(
                        update={"digest": configuration_digest(policy)}
                    )
                }
            )
        }
    )
    raw = gzip.compress(b"x" * 601, mtime=0)
    old = next(
        item
        for item in request.sources
        if item.role is ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE
    )
    artifact = old.artifact.model_copy(
        update={"digest": f"sha256:{hashlib.sha256(raw).hexdigest()}"}
    )
    replacement = old.model_copy(
        update={
            "artifact": artifact,
            "byte_length": len(raw),
            "declared_compression": ProteinInferenceCompression.GZIP,
        }
    )
    sources = tuple(replacement if item is old else item for item in request.sources)
    artifacts = tuple(
        item.model_copy(update={"artifact": artifact})
        if item.claim_id == old.bound_claim_id
        else item
        for item in request.lineage_receipt.artifacts
    )
    lineage = request.lineage_receipt.model_copy(update={"artifacts": artifacts})
    lineage = lineage.model_copy(update={"receipt_digest": lineage_receipt_digest(lineage)})
    bounded = request.model_copy(
        update={
            "context": request.context.model_copy(update={"references": references}),
            "policy": policy,
            "lineage_receipt": lineage,
            "sources": sources,
            "source_manifest_digest": source_manifest_digest(sources),
        }
    )
    result = ingest_protein_inference_raw_inputs(
        bounded,
        {**scenario.sources, old.source_id: raw},
    )
    parsed = next(item for item in result.raw_inputs if item.source_id == old.source_id)

    assert result.disposition is ProteinInferenceAdmissionDisposition.REJECTED
    assert parsed.decoded_size_bytes == policy.max_decoded_bytes + 1
    assert parsed.decoded_digest is None
    assert {item.code for item in parsed.diagnostics} == {
        ProteinInferenceDiagnosticCode.DECODED_SIZE_LIMIT_EXCEEDED
    }


def _replace_source(
    request: IngestProteinInferenceRawInputsRequest,
    old: ProteinInferenceRawSource,
    new: ProteinInferenceRawSource,
) -> IngestProteinInferenceRawInputsRequest:
    sources = tuple(new if item is old else item for item in request.sources)
    return request.model_copy(
        update={
            "sources": sources,
            "source_manifest_digest": source_manifest_digest(sources),
        }
    )
