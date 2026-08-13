"""Exact numeric, cardinality, source-closure, and safe-failure boundaries for M03-03."""

from __future__ import annotations

import gzip
import hashlib
from copy import deepcopy
from typing import Any, cast

import pytest
from evals.m03_03.run import Scenario, build_scenario
from pydantic import ValidationError

from glio_proteogen.contracts.m03_01 import ProtocolConformanceDisposition
from glio_proteogen.contracts.m03_02 import (
    ReconciliationDisposition,
    ReconciliationFindingCode,
)
from glio_proteogen.contracts.m03_03 import (
    M0303_MAX_DECODED_BYTES,
    M0303_MAX_LINEAGE_ARTIFACTS,
    M0303_MAX_SOURCE_BYTES,
    M0303_MAX_SOURCES,
    M0303_MAX_TOTAL_DECODED_BYTES,
    M0303_MAX_TOTAL_SOURCE_BYTES,
    ApprovedBuild,
    IngestProteinInferenceRawInputsRequest,
    ProteinInferenceAdmissionDisposition,
    ProteinInferenceBuildBindingReceipt,
    ProteinInferenceBuildState,
    ProteinInferenceDiagnosticCode,
    ProteinInferenceLineageArtifactReceipt,
    ProteinInferenceLineageIngestionReceipt,
    ProteinInferenceProtocolIngestionReceipt,
    ProteinInferenceRawPolicy,
    ProteinInferenceRawRole,
    ProteinInferenceRawSource,
    ValidatedProteinInferenceRawInput,
    configuration_digest,
    diagnostic_for,
    expected_upstream_diagnostics,
    lineage_receipt_digest,
    protocol_receipt_digest,
    source_manifest_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_03_raw_ingestion import (
    ProteinInferenceRawIngestionInputError,
    ProteinInferenceRawIngestionInputErrorCode,
    ingest_protein_inference_raw_inputs,
)

_MAX_SPECTRA_SOURCES = 32
_MAX_APPROVED_BUILDS = 32
_MAX_FINDING_CODES = 16
_MAX_LINEAGE_RECEIPT_ARTIFACTS = 256
_MAX_ADMISSION_EVIDENCE = 271
_MAX_RAW_INPUT_DIAGNOSTICS = 64
_MAX_RECORDS = 10_000_000
_FORGED_DIGEST = "sha256:" + ("f" * 64)


@pytest.fixture(scope="module")
def canonical_scenario() -> Scenario:
    return build_scenario()


def _payload(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", strict_json_loads(canonical_json_bytes(value)))


def _validate_request(payload: dict[str, Any]) -> IngestProteinInferenceRawInputsRequest:
    return IngestProteinInferenceRawInputsRequest.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )


def _resign_protocol_receipt(payload: dict[str, Any]) -> None:
    payload["receipt_digest"] = protocol_receipt_digest(payload)


def _resign_lineage_receipt(payload: dict[str, Any]) -> None:
    payload["receipt_digest"] = lineage_receipt_digest(payload)


def _resign_request(payload: dict[str, Any]) -> None:
    payload["source_manifest_digest"] = source_manifest_digest(
        tuple(
            ProteinInferenceRawSource.model_validate_json(canonical_json_bytes(item), strict=True)
            for item in payload["sources"]
        )
    )


def _refresh_manifest_bundle_and_lineage(
    payload: dict[str, Any],
    payloads: dict[str, bytes],
) -> None:
    sources = cast("list[dict[str, Any]]", payload["sources"])
    payload["source_manifest_digest"] = source_manifest_digest(
        tuple(
            ProteinInferenceRawSource.model_validate_json(canonical_json_bytes(item), strict=True)
            for item in sources
        )
    )
    bundle_source = next(
        item for item in sources if item["role"] == "complex_activity_input_bundle"
    )
    bundle_id = cast("str", bundle_source["source_id"])
    bundle_payload = cast(
        "dict[str, Any]",
        strict_json_loads(payloads[bundle_id]),
    )
    bundle_payload["source_manifest_digest"] = payload["source_manifest_digest"]
    bundle_bytes = canonical_json_bytes(bundle_payload)
    bundle_source["byte_length"] = len(bundle_bytes)
    bundle_source["artifact"]["digest"] = f"sha256:{hashlib.sha256(bundle_bytes).hexdigest()}"
    payloads[bundle_id] = bundle_bytes
    bundle_receipt = next(
        item
        for item in payload["lineage_receipt"]["artifacts"]
        if item["claim_role"] == "complex_activity_input_bundle"
    )
    bundle_receipt["artifact"] = deepcopy(bundle_source["artifact"])
    _resign_lineage_receipt(payload["lineage_receipt"])


@pytest.mark.contract
@pytest.mark.parametrize(
    ("field", "maximum"),
    [
        ("max_sources", M0303_MAX_SOURCES),
        ("max_lineage_artifacts", M0303_MAX_LINEAGE_ARTIFACTS),
        ("max_spectra_sources", _MAX_SPECTRA_SOURCES),
        ("max_source_bytes", M0303_MAX_SOURCE_BYTES),
        ("max_decoded_bytes", M0303_MAX_DECODED_BYTES),
        ("max_total_source_bytes", M0303_MAX_TOTAL_SOURCE_BYTES),
        ("max_total_decoded_bytes", M0303_MAX_TOTAL_DECODED_BYTES),
    ],
)
def test_policy_accepts_each_global_maximum_and_rejects_max_plus_one(
    canonical_scenario: Scenario,
    field: str,
    maximum: int,
) -> None:
    payload = _payload(canonical_scenario.request.policy)
    payload[field] = maximum
    if field == "max_source_bytes":
        payload["max_decoded_bytes"] = max(payload["max_decoded_bytes"], maximum)
        payload["max_total_source_bytes"] = max(payload["max_total_source_bytes"], maximum)
    elif field == "max_decoded_bytes":
        payload["max_total_decoded_bytes"] = max(payload["max_total_decoded_bytes"], maximum)
    assert ProteinInferenceRawPolicy.model_validate_json(canonical_json_bytes(payload), strict=True)
    payload[field] = maximum + 1
    with pytest.raises(ValidationError):
        ProteinInferenceRawPolicy.model_validate_json(canonical_json_bytes(payload), strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    "field",
    [
        "max_sources",
        "max_lineage_artifacts",
        "max_spectra_sources",
        "max_source_bytes",
        "max_decoded_bytes",
        "max_total_source_bytes",
        "max_total_decoded_bytes",
    ],
)
def test_policy_rejects_zero_for_every_positive_capacity(
    canonical_scenario: Scenario,
    field: str,
) -> None:
    payload = _payload(canonical_scenario.request.policy)
    payload[field] = 0
    with pytest.raises(ValidationError):
        ProteinInferenceRawPolicy.model_validate_json(canonical_json_bytes(payload), strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("left", "right", "message"),
    [
        ("max_decoded_bytes", "max_source_bytes", "decoded byte ceiling"),
        ("max_total_source_bytes", "max_source_bytes", "total source ceiling"),
        ("max_total_decoded_bytes", "max_decoded_bytes", "total decoded ceiling"),
    ],
)
def test_policy_byte_hierarchy_is_closed(
    canonical_scenario: Scenario,
    left: str,
    right: str,
    message: str,
) -> None:
    payload = _payload(canonical_scenario.request.policy)
    payload[left] = payload[right] - 1
    with pytest.raises(ValidationError, match=message):
        ProteinInferenceRawPolicy.model_validate_json(canonical_json_bytes(payload), strict=True)


@pytest.mark.contract
@pytest.mark.parametrize("field", ["approved_genome_builds", "approved_transcript_builds"])
def test_approved_build_sets_accept_exact_max_reject_plus_one_and_duplicates(
    canonical_scenario: Scenario,
    field: str,
) -> None:
    payload = _payload(canonical_scenario.request.policy)
    payload[field] = [
        {"build_id": f"build.boundary.{index:02d}", "version": "1.0.0"}
        for index in range(_MAX_APPROVED_BUILDS)
    ]
    assert (
        len(
            ProteinInferenceRawPolicy.model_validate_json(
                canonical_json_bytes(payload), strict=True
            ).model_dump(mode="python")[field]
        )
        == _MAX_APPROVED_BUILDS
    )
    payload[field].append({"build_id": "build.boundary.32", "version": "1.0.0"})
    with pytest.raises(ValidationError, match="at most 32 items"):
        ProteinInferenceRawPolicy.model_validate_json(canonical_json_bytes(payload), strict=True)

    payload = _payload(canonical_scenario.request.policy)
    payload[field].append(deepcopy(payload[field][0]))
    with pytest.raises(ValidationError, match="must be unique"):
        ProteinInferenceRawPolicy.model_validate_json(canonical_json_bytes(payload), strict=True)


@pytest.mark.contract
def test_raw_source_size_accepts_global_maximum_and_rejects_plus_one(
    canonical_scenario: Scenario,
) -> None:
    payload = _payload(canonical_scenario.request.sources[0])
    payload["byte_length"] = M0303_MAX_SOURCE_BYTES
    assert (
        ProteinInferenceRawSource.model_validate_json(
            canonical_json_bytes(payload), strict=True
        ).byte_length
        == M0303_MAX_SOURCE_BYTES
    )
    payload["byte_length"] += 1
    with pytest.raises(ValidationError):
        ProteinInferenceRawSource.model_validate_json(canonical_json_bytes(payload), strict=True)


@pytest.mark.contract
def test_source_role_format_and_build_pairing_are_exact(
    canonical_scenario: Scenario,
) -> None:
    expected_formats = {
        "spectra": "mzML",
        "peptide_evidence": "mzIdentML",
        "protein_group_manifest": "protein_group_json",
        "ambiguity_manifest": "ambiguity_json",
        "complex_activity_input_bundle": "complex_bundle_json",
        "canonical_sequences": "FASTA",
        "decoy_sequences": "FASTA",
        "isoform_sequences": "FASTA",
        "variant_sequences": "FASTA",
        "contaminant_sequences": "FASTA",
        "ptm_vocabulary": "PSI_MOD_OBO",
        "genomic_context": "VCF",
        "transcript_context": "GFF3",
    }
    for declaration in canonical_scenario.request.sources:
        assert declaration.declared_format.value == expected_formats[declaration.role.value]
        payload = _payload(declaration)
        payload["declared_format"] = "VCF" if declaration.declared_format.value != "VCF" else "GFF3"
        with pytest.raises(ValidationError, match="format contradicts"):
            ProteinInferenceRawSource.model_validate_json(
                canonical_json_bytes(payload), strict=True
            )

    payload = _payload(canonical_scenario.request.sources[0])
    payload["expected_build_id"] = "build.unpaired"
    payload["expected_build_version"] = None
    with pytest.raises(ValidationError, match="declared together"):
        ProteinInferenceRawSource.model_validate_json(canonical_json_bytes(payload), strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("role", "message"),
    [
        (ProteinInferenceRawRole.PEPTIDE_EVIDENCE, "exact M03-01 search build"),
        (ProteinInferenceRawRole.PTM_VOCABULARY, "exact M03-01 vocabulary version"),
    ],
)
def test_protocol_governed_sources_require_exact_expected_builds(
    canonical_scenario: Scenario,
    role: ProteinInferenceRawRole,
    message: str,
) -> None:
    payload = _payload(canonical_scenario.request)
    source = next(item for item in payload["sources"] if item["role"] == role.value)
    source["expected_build_version"] = "9.0.0"
    _resign_request(payload)
    with pytest.raises(ValidationError, match=message):
        _validate_request(payload)


@pytest.mark.contract
@pytest.mark.parametrize(
    "role",
    [
        ProteinInferenceRawRole.CANONICAL_SEQUENCES,
        ProteinInferenceRawRole.DECOY_SEQUENCES,
        ProteinInferenceRawRole.ISOFORM_SEQUENCES,
        ProteinInferenceRawRole.VARIANT_SEQUENCES,
        ProteinInferenceRawRole.CONTAMINANT_SEQUENCES,
        ProteinInferenceRawRole.PTM_VOCABULARY,
    ],
)
def test_search_space_and_ptm_artifacts_require_exact_content_references(
    canonical_scenario: Scenario,
    role: ProteinInferenceRawRole,
) -> None:
    payload = _payload(canonical_scenario.request)
    source = next(item for item in payload["sources"] if item["role"] == role.value)
    source["artifact"]["digest"] = _FORGED_DIGEST
    _resign_request(payload)
    with pytest.raises(ValidationError, match="does not match M03-01"):
        _validate_request(payload)


@pytest.mark.contract
@pytest.mark.parametrize("mutation", ["duplicate_source", "missing_claim", "wrong_claim_role"])
def test_request_source_and_lineage_binding_are_bijective(
    canonical_scenario: Scenario,
    mutation: str,
) -> None:
    payload = _payload(canonical_scenario.request)
    sources = cast("list[dict[str, Any]]", payload["sources"])
    if mutation == "duplicate_source":
        sources[1]["source_id"] = sources[0]["source_id"]
    elif mutation == "missing_claim":
        next(item for item in sources if item["bound_claim_id"] is not None)["bound_claim_id"] = (
            None
        )
    else:
        bound = [item for item in sources if item["bound_claim_id"] is not None]
        bound[0]["bound_claim_id"], bound[1]["bound_claim_id"] = (
            bound[1]["bound_claim_id"],
            bound[0]["bound_claim_id"],
        )
    _resign_request(payload)
    with pytest.raises(ValidationError):
        _validate_request(payload)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("role", "message"),
    [
        (ProteinInferenceRawRole.SPECTRA, "spectra source set"),
        (ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST, "lineage artifact"),
        (ProteinInferenceRawRole.AMBIGUITY_MANIFEST, "lineage artifact"),
        (ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE, "lineage artifact"),
        (ProteinInferenceRawRole.CANONICAL_SEQUENCES, "required source roles"),
        (ProteinInferenceRawRole.DECOY_SEQUENCES, "required source roles"),
        (ProteinInferenceRawRole.PTM_VOCABULARY, "required source roles"),
        (ProteinInferenceRawRole.PEPTIDE_EVIDENCE, "lineage artifact"),
    ],
)
def test_each_required_role_is_mandatory(
    canonical_scenario: Scenario,
    role: ProteinInferenceRawRole,
    message: str,
) -> None:
    payload = _payload(canonical_scenario.request)
    payload["sources"] = [item for item in payload["sources"] if item["role"] != role.value]
    _resign_request(payload)
    with pytest.raises(ValidationError, match=message):
        _validate_request(payload)


@pytest.mark.contract
def test_optional_search_space_sources_have_exact_reference_presence(
    canonical_scenario: Scenario,
) -> None:
    for role in (
        ProteinInferenceRawRole.ISOFORM_SEQUENCES,
        ProteinInferenceRawRole.VARIANT_SEQUENCES,
        ProteinInferenceRawRole.CONTAMINANT_SEQUENCES,
    ):
        payload = _payload(canonical_scenario.request)
        payload["sources"] = [item for item in payload["sources"] if item["role"] != role.value]
        _resign_request(payload)
        with pytest.raises(ValidationError, match="conditional search-space sources"):
            _validate_request(payload)


@pytest.mark.contract
@pytest.mark.parametrize("role", ["genomic_context", "transcript_context"])
def test_context_sources_require_exact_approved_builds(
    canonical_scenario: Scenario,
    role: str,
) -> None:
    payload = _payload(canonical_scenario.request)
    source = next(item for item in payload["sources"] if item["role"] == role)
    source["expected_build_id"] = "build.unreviewed"
    _resign_request(payload)
    with pytest.raises(ValidationError, match="outside the reviewed"):
        _validate_request(payload)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("protocol_result_digest", _FORGED_DIGEST, "receipts do not close"),
        ("identity_subject_digest", _FORGED_DIGEST, "receipts do not close"),
    ],
)
def test_protocol_receipt_must_close_to_lineage(
    canonical_scenario: Scenario,
    field: str,
    replacement: str,
    message: str,
) -> None:
    payload = _payload(canonical_scenario.request)
    payload["protocol_receipt"][field] = replacement
    _resign_protocol_receipt(payload["protocol_receipt"])
    with pytest.raises(ValidationError, match=message):
        _validate_request(payload)


@pytest.mark.contract
def test_protocol_search_space_digest_is_standalone_exact(
    canonical_scenario: Scenario,
) -> None:
    payload = _payload(canonical_scenario.request.protocol_receipt)
    payload["search_space_digest"] = _FORGED_DIGEST
    _resign_protocol_receipt(payload)
    with pytest.raises(ValidationError, match="search-space receipt digest"):
        ProteinInferenceProtocolIngestionReceipt.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


@pytest.mark.contract
def test_lineage_receipt_shape_ids_and_finding_codes_are_standalone_closed(
    canonical_scenario: Scenario,
) -> None:
    payload = _payload(canonical_scenario.request.lineage_receipt)
    payload["artifacts"][1]["claim_id"] = payload["artifacts"][0]["claim_id"]
    _resign_lineage_receipt(payload)
    with pytest.raises(ValidationError, match="unique claim identifiers"):
        ProteinInferenceLineageIngestionReceipt.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    payload = _payload(canonical_scenario.request.lineage_receipt)
    payload["artifacts"][0]["claim_role"] = "protein_group_manifest"
    _resign_lineage_receipt(payload)
    with pytest.raises(ValidationError, match="four-role artifact shape"):
        ProteinInferenceLineageIngestionReceipt.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    artifact = _payload(canonical_scenario.request.lineage_receipt.artifacts[0])
    artifact["finding_codes"] = [item.value for item in ReconciliationFindingCode]
    validated = ProteinInferenceLineageArtifactReceipt.model_validate_json(
        canonical_json_bytes(artifact), strict=True
    )
    assert len(validated.finding_codes) <= _MAX_FINDING_CODES
    artifact["finding_codes"].append(artifact["finding_codes"][0])
    with pytest.raises(ValidationError, match="finding codes must be unique"):
        ProteinInferenceLineageArtifactReceipt.model_validate_json(
            canonical_json_bytes(artifact), strict=True
        )


@pytest.mark.contract
@pytest.mark.parametrize(
    ("disposition", "expected_code", "expected_output"),
    [
        (
            ReconciliationDisposition.QUARANTINED,
            ProteinInferenceDiagnosticCode.UPSTREAM_QUARANTINED,
            ProteinInferenceAdmissionDisposition.QUARANTINED,
        ),
        (
            ReconciliationDisposition.ABSTAINED,
            ProteinInferenceDiagnosticCode.UPSTREAM_ABSTAINED,
            ProteinInferenceAdmissionDisposition.ABSTAINED,
        ),
    ],
)
def test_lineage_safe_failure_requires_empty_sources_and_never_traverses_mapping(
    canonical_scenario: Scenario,
    disposition: ReconciliationDisposition,
    expected_code: ProteinInferenceDiagnosticCode,
    expected_output: ProteinInferenceAdmissionDisposition,
) -> None:
    payload = _payload(canonical_scenario.request)
    payload["lineage_receipt"]["disposition"] = disposition.value
    _resign_lineage_receipt(payload["lineage_receipt"])
    payload["sources"] = []
    _resign_request(payload)
    request = _validate_request(payload)

    class _NoTraversal(dict[str, bytes]):
        def __iter__(self) -> Any:
            raise AssertionError

    result = ingest_protein_inference_raw_inputs(request, _NoTraversal())
    assert result.disposition is expected_output
    assert not result.raw_inputs
    assert tuple(item.code for item in result.diagnostics) == (expected_code,)
    assert result.diagnostics == expected_upstream_diagnostics(request)


@pytest.mark.contract
def test_nonconformant_protocol_safe_failure_rejects_nonempty_sources(
    canonical_scenario: Scenario,
) -> None:
    payload = _payload(canonical_scenario.request)
    payload["protocol_receipt"]["disposition"] = ProtocolConformanceDisposition.QUARANTINED.value
    _resign_protocol_receipt(payload["protocol_receipt"])
    with pytest.raises(ValidationError, match="cannot traverse raw sources"):
        _validate_request(payload)


@pytest.mark.contract
def test_nonconformant_protocol_safe_failure_executes_without_source_traversal(
    canonical_scenario: Scenario,
) -> None:
    payload = _payload(canonical_scenario.request)
    payload["protocol_receipt"]["disposition"] = ProtocolConformanceDisposition.QUARANTINED.value
    _resign_protocol_receipt(payload["protocol_receipt"])
    payload["sources"] = []
    _resign_request(payload)
    request = _validate_request(payload)

    class _NoTraversal(dict[str, bytes]):
        def __iter__(self) -> Any:
            raise AssertionError

    result = ingest_protein_inference_raw_inputs(request, _NoTraversal())
    assert result.disposition is ProteinInferenceAdmissionDisposition.QUARANTINED
    assert not result.raw_inputs
    assert tuple(item.code for item in result.diagnostics) == (
        ProteinInferenceDiagnosticCode.UPSTREAM_QUARANTINED,
    )


@pytest.mark.contract
def test_policy_lineage_shape_boundary_abstains_before_source_mapping(
    canonical_scenario: Scenario,
) -> None:
    payload = _payload(canonical_scenario.request)
    payload["policy"]["max_lineage_artifacts"] = len(payload["lineage_receipt"]["artifacts"]) - 1
    payload["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
        configuration_digest(payload["policy"])
    )
    payload["sources"] = []
    _resign_request(payload)
    request = _validate_request(payload)
    result = ingest_protein_inference_raw_inputs(request, {})
    assert result.disposition is ProteinInferenceAdmissionDisposition.ABSTAINED
    assert not result.raw_inputs
    assert tuple(item.code for item in result.diagnostics) == (
        ProteinInferenceDiagnosticCode.UPSTREAM_SHAPE_UNSUPPORTED,
    )


@pytest.mark.contract
def test_maximum_256_artifact_safe_failure_is_total_with_exact_evidence_cap(
    canonical_scenario: Scenario,
) -> None:
    payload = _payload(canonical_scenario.request)
    artifacts = cast("list[dict[str, Any]]", payload["lineage_receipt"]["artifacts"])
    seed = next(item for item in artifacts if item["claim_role"] == "peptide_evidence_manifest")
    for index in range(len(artifacts), _MAX_LINEAGE_RECEIPT_ARTIFACTS):
        artifact = deepcopy(seed)
        artifact["claim_id"] = f"claim.safe-failure.boundary.{index:03d}"
        artifact["artifact"]["artifact_id"] = f"artifact.safe-failure.boundary.{index:03d}"
        artifact["artifact"]["digest"] = sha256_digest({"safe_failure_artifact": index})
        artifact["lineage_path_digest"] = sha256_digest({"safe_failure_lineage": index})
        artifact["finding_codes"] = []
        artifacts.append(artifact)
    _resign_lineage_receipt(payload["lineage_receipt"])
    payload["sources"] = []
    _resign_request(payload)
    request = _validate_request(payload)

    result = ingest_protein_inference_raw_inputs(request, {})
    assert len(request.lineage_receipt.artifacts) == _MAX_LINEAGE_RECEIPT_ARTIFACTS
    assert result.disposition is ProteinInferenceAdmissionDisposition.ABSTAINED
    assert not result.raw_inputs
    assert tuple(item.code for item in result.diagnostics) == (
        ProteinInferenceDiagnosticCode.UPSTREAM_SHAPE_UNSUPPORTED,
    )
    assert len(result.evidence) == _MAX_ADMISSION_EVIDENCE


@pytest.mark.contract
@pytest.mark.parametrize(
    ("state", "declared", "expected", "accepted"),
    [
        ("exact", ("build.a", "1.0.0"), ("build.a", "1.0.0"), True),
        ("exact", ("build.a", "1.0.0"), ("build.b", "1.0.0"), False),
        ("mismatched", ("build.a", "1.0.0"), ("build.b", "1.0.0"), True),
        ("mismatched", ("build.a", "1.0.0"), ("build.a", "1.0.0"), False),
        ("missing", (None, None), ("build.a", "1.0.0"), True),
        ("unsupported", (None, None), ("build.a", "1.0.0"), True),
        ("not_applicable", (None, None), (None, None), True),
        ("not_applicable", ("build.a", "1.0.0"), (None, None), False),
    ],
)
def test_standalone_build_receipt_state_matrix(
    state: str,
    declared: tuple[str | None, str | None],
    expected: tuple[str | None, str | None],
    accepted: bool,  # noqa: FBT001 - explicit parameterized state matrix.
) -> None:
    payload = {
        "state": state,
        "declared_build_id": declared[0],
        "declared_build_version": declared[1],
        "expected_build_id": expected[0],
        "expected_build_version": expected[1],
    }
    if accepted:
        assert (
            ProteinInferenceBuildBindingReceipt.model_validate_json(
                canonical_json_bytes(payload), strict=True
            ).state.value
            == state
        )
    else:
        with pytest.raises(ValidationError):
            ProteinInferenceBuildBindingReceipt.model_validate_json(
                canonical_json_bytes(payload), strict=True
            )


@pytest.mark.contract
def test_raw_input_standalone_numeric_maxima_and_plus_one() -> None:
    build = ProteinInferenceBuildBindingReceipt(state=ProteinInferenceBuildState.NOT_APPLICABLE)
    base: dict[str, Any] = {
        "source_id": "source.boundary",
        "role": "spectra",
        "source_digest": sha256_digest({"source": "boundary"}),
        "source_size_bytes": M0303_MAX_SOURCE_BYTES + 1,
        "decoded_digest": sha256_digest({"decoded": "boundary"}),
        "decoded_size_bytes": M0303_MAX_DECODED_BYTES + 1,
        "detected_format": "mzML",
        "detected_version": "1.0.0",
        "compression": "none",
        "record_count": _MAX_RECORDS,
        "reference_count": _MAX_RECORDS,
        "build": build.model_dump(mode="json"),
        "diagnostics": [],
    }
    assert ValidatedProteinInferenceRawInput.model_validate_json(
        canonical_json_bytes(base), strict=True
    )
    for field in ("source_size_bytes", "decoded_size_bytes", "record_count", "reference_count"):
        payload = deepcopy(base)
        payload[field] += 1
        with pytest.raises(ValidationError):
            ValidatedProteinInferenceRawInput.model_validate_json(
                canonical_json_bytes(payload), strict=True
            )


@pytest.mark.contract
def test_raw_input_diagnostic_cardinality_accepts_max_and_rejects_plus_one() -> None:
    source_id = "source.boundary"
    diagnostics = [
        diagnostic_for(
            ProteinInferenceDiagnosticCode.CROSS_SOURCE_DISAGREEMENT,
            (source_id, f"source.boundary.peer.{index:02d}"),
        )
        for index in range(_MAX_RAW_INPUT_DIAGNOSTICS)
    ]
    payload: dict[str, Any] = {
        "source_id": source_id,
        "role": "spectra",
        "source_digest": sha256_digest({"source": "boundary"}),
        "source_size_bytes": 1,
        "decoded_digest": sha256_digest({"decoded": "boundary"}),
        "decoded_size_bytes": 1,
        "detected_format": "mzML",
        "detected_version": "1.0.0",
        "compression": "none",
        "record_count": 1,
        "reference_count": 0,
        "build": {"state": "not_applicable"},
        "diagnostics": diagnostics,
    }
    assert (
        len(
            ValidatedProteinInferenceRawInput.model_validate_json(
                canonical_json_bytes(payload), strict=True
            ).diagnostics
        )
        == _MAX_RAW_INPUT_DIAGNOSTICS
    )
    payload["diagnostics"].append(
        diagnostic_for(
            ProteinInferenceDiagnosticCode.CROSS_SOURCE_DISAGREEMENT,
            (source_id, "source.boundary.peer.64"),
        )
    )
    with pytest.raises(ValidationError, match="at most 64 items"):
        ValidatedProteinInferenceRawInput.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


@pytest.mark.contract
def test_gzip_decoded_limit_is_inclusive_and_limit_plus_one_rejects(
    canonical_scenario: Scenario,
) -> None:
    prefix = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<mzML xmlns="http://psi.hupo.org/ms/mzml" version="1.1.0">'
        b'<run id="run-boundary"><spectrumList count="0"></spectrumList>'
        b'<chromatogramList count="0"></chromatogramList></run>'
    )
    suffix = b"</mzML>"
    for delta, expected in (
        (0, ProteinInferenceAdmissionDisposition.VALIDATED),
        (1, ProteinInferenceAdmissionDisposition.REJECTED),
    ):
        payload = _payload(canonical_scenario.request)
        payloads = dict(canonical_scenario.sources)
        source = next(item for item in payload["sources"] if item["role"] == "spectra")
        decoded_length = payload["policy"]["max_decoded_bytes"] + delta
        decoded = prefix + (b" " * (decoded_length - len(prefix) - len(suffix))) + suffix
        transported = gzip.compress(decoded, compresslevel=9, mtime=0)
        source["byte_length"] = len(transported)
        source["declared_compression"] = "gzip"
        source["artifact"]["digest"] = f"sha256:{hashlib.sha256(transported).hexdigest()}"
        payloads[source["source_id"]] = transported
        _refresh_manifest_bundle_and_lineage(payload, payloads)
        request = _validate_request(payload)
        result = ingest_protein_inference_raw_inputs(request, payloads)
        assert result.disposition is expected
        parsed = next(item for item in result.raw_inputs if item.source_id == source["source_id"])
        if delta == 0:
            assert parsed.decoded_size_bytes == decoded_length
        else:
            assert ProteinInferenceDiagnosticCode.DECODED_SIZE_LIMIT_EXCEEDED in {
                item.code for item in result.diagnostics
            }


@pytest.mark.contract
def test_stale_protocol_json_is_a_typed_quarantine_not_a_result_validation_crash(
    canonical_scenario: Scenario,
) -> None:
    payload = _payload(canonical_scenario.request)
    payloads = dict(canonical_scenario.sources)
    sources = cast("list[dict[str, Any]]", payload["sources"])
    artifacts = cast("list[dict[str, Any]]", payload["lineage_receipt"]["artifacts"])

    group = next(item for item in sources if item["role"] == "protein_group_manifest")
    group_id = cast("str", group["source_id"])
    group_document = cast("dict[str, Any]", strict_json_loads(payloads[group_id]))
    group_document["protocol_result_digest"] = _FORGED_DIGEST
    group_bytes = canonical_json_bytes(group_document)
    group["byte_length"] = len(group_bytes)
    group["artifact"]["digest"] = f"sha256:{hashlib.sha256(group_bytes).hexdigest()}"
    payloads[group_id] = group_bytes
    group_receipt = next(item for item in artifacts if item["claim_id"] == group["bound_claim_id"])
    group_receipt["artifact"] = deepcopy(group["artifact"])

    ambiguity = next(item for item in sources if item["role"] == "ambiguity_manifest")
    ambiguity_id = cast("str", ambiguity["source_id"])
    ambiguity_document = cast("dict[str, Any]", strict_json_loads(payloads[ambiguity_id]))
    ambiguity_document["group_claim_digest"] = group["artifact"]["digest"]
    ambiguity_bytes = canonical_json_bytes(ambiguity_document)
    ambiguity["byte_length"] = len(ambiguity_bytes)
    ambiguity["artifact"]["digest"] = f"sha256:{hashlib.sha256(ambiguity_bytes).hexdigest()}"
    payloads[ambiguity_id] = ambiguity_bytes
    ambiguity_receipt = next(
        item for item in artifacts if item["claim_id"] == ambiguity["bound_claim_id"]
    )
    ambiguity_receipt["artifact"] = deepcopy(ambiguity["artifact"])

    bundle = next(item for item in sources if item["role"] == "complex_activity_input_bundle")
    bundle_id = cast("str", bundle["source_id"])
    bundle_document = cast("dict[str, Any]", strict_json_loads(payloads[bundle_id]))
    bundle_document["protein_group_digest"] = group["artifact"]["digest"]
    bundle_document["ambiguity_digest"] = ambiguity["artifact"]["digest"]
    payloads[bundle_id] = canonical_json_bytes(bundle_document)
    _refresh_manifest_bundle_and_lineage(payload, payloads)

    request = _validate_request(payload)
    result = ingest_protein_inference_raw_inputs(request, payloads)
    assert result.disposition is ProteinInferenceAdmissionDisposition.QUARANTINED
    assert ProteinInferenceDiagnosticCode.DANGLING_REFERENCE in {
        item.code for item in result.diagnostics
    }
    parsed_group = next(item for item in result.raw_inputs if item.source_id == group_id)
    assert parsed_group.detected_format is None


@pytest.mark.contract
def test_runtime_raw_source_cap_plus_one_is_a_typed_rejected_result(
    canonical_scenario: Scenario,
) -> None:
    source = canonical_scenario.request.sources[0]
    payloads = dict(canonical_scenario.sources)
    payloads[source.source_id] = b"x" * (canonical_scenario.request.policy.max_source_bytes + 1)
    result = ingest_protein_inference_raw_inputs(canonical_scenario.request, payloads)
    assert result.disposition is ProteinInferenceAdmissionDisposition.REJECTED
    assert ProteinInferenceDiagnosticCode.RAW_SIZE_LIMIT_EXCEEDED in {
        item.code for item in result.diagnostics
    }


@pytest.mark.contract
def test_runtime_total_source_cap_plus_one_is_a_typed_boundary_error(
    canonical_scenario: Scenario,
) -> None:
    payload = _payload(canonical_scenario.request)
    payload["policy"]["max_total_source_bytes"] = payload["policy"]["max_source_bytes"]
    payload["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
        configuration_digest(payload["policy"])
    )
    request = _validate_request(payload)
    source = request.sources[0]
    payloads = dict(canonical_scenario.sources)
    payloads[source.source_id] = b"x" * (request.policy.max_source_bytes + 1)
    with pytest.raises(ProteinInferenceRawIngestionInputError) as caught:
        ingest_protein_inference_raw_inputs(request, payloads)
    assert caught.value.code is (
        ProteinInferenceRawIngestionInputErrorCode.TOTAL_SOURCE_LIMIT_EXCEEDED
    )


@pytest.mark.contract
def test_compact_request_executes_at_exact_64_source_and_32_spectra_maxima(
    canonical_scenario: Scenario,
) -> None:
    payload = _payload(canonical_scenario.request)
    payloads = dict(canonical_scenario.sources)
    sources = cast("list[dict[str, Any]]", payload["sources"])
    artifacts = cast("list[dict[str, Any]]", payload["lineage_receipt"]["artifacts"])
    spectra_seed = next(item for item in sources if item["role"] == "spectra")
    peptide_seed = next(item for item in sources if item["role"] == "peptide_evidence")
    peptide_artifact_seed = next(
        item for item in artifacts if item["claim_role"] == "peptide_evidence_manifest"
    )

    for index in range(1, _MAX_SPECTRA_SOURCES):
        source = deepcopy(spectra_seed)
        source_id = f"source.spectra.boundary.{index:02d}"
        source["source_id"] = source_id
        source["artifact"]["artifact_id"] = f"artifact.spectra.boundary.{index:02d}"
        sources.append(source)
        payloads[source_id] = canonical_scenario.sources[spectra_seed["source_id"]]

    for index in range(20):
        source = deepcopy(peptide_seed)
        source_id = f"source.peptide.boundary.{index:02d}"
        claim_id = f"claim.peptide.boundary.{index:02d}"
        source["source_id"] = source_id
        source["bound_claim_id"] = claim_id
        source["artifact"]["artifact_id"] = f"artifact.peptide.boundary.{index:02d}"
        sources.append(source)
        payloads[source_id] = canonical_scenario.sources[peptide_seed["source_id"]]

        artifact = deepcopy(peptide_artifact_seed)
        artifact["claim_id"] = claim_id
        artifact["artifact"] = deepcopy(source["artifact"])
        artifact["lineage_path_digest"] = sha256_digest({"lineage": index})
        artifact["finding_codes"] = []
        artifacts.append(artifact)

    assert len(sources) == M0303_MAX_SOURCES
    assert sum(item["role"] == "spectra" for item in sources) == _MAX_SPECTRA_SOURCES
    _refresh_manifest_bundle_and_lineage(payload, payloads)

    request = _validate_request(payload)
    result = ingest_protein_inference_raw_inputs(request, payloads)
    assert result.disposition is ProteinInferenceAdmissionDisposition.VALIDATED
    assert len(result.raw_inputs) == M0303_MAX_SOURCES
    assert sum(item.role is ProteinInferenceRawRole.SPECTRA for item in result.raw_inputs) == (
        _MAX_SPECTRA_SOURCES
    )


@pytest.mark.contract
def test_standalone_lineage_receipt_cap_rejects_max_plus_one(
    canonical_scenario: Scenario,
) -> None:
    payload = _payload(canonical_scenario.request.lineage_receipt)
    seed = deepcopy(payload["artifacts"][0])
    artifacts = []
    for index in range(_MAX_LINEAGE_RECEIPT_ARTIFACTS + 1):
        item = deepcopy(seed)
        item["claim_id"] = f"claim.boundary.{index:03d}"
        item["artifact"]["artifact_id"] = f"artifact.boundary.{index:03d}"
        item["artifact"]["digest"] = sha256_digest({"artifact": index})
        artifacts.append(item)
    payload["artifacts"] = artifacts
    _resign_lineage_receipt(payload)
    with pytest.raises(ValidationError, match="at most 256 items"):
        ProteinInferenceLineageIngestionReceipt.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


@pytest.mark.contract
def test_configuration_digest_changes_for_every_policy_semantic_change(
    canonical_scenario: Scenario,
) -> None:
    policy = canonical_scenario.request.policy
    original = configuration_digest(policy)
    changed = policy.model_copy(update={"reviewed_by": "reviewer.boundary.changed"})
    assert configuration_digest(changed) != original
    reordered = policy.model_copy(
        update={
            "approved_genome_builds": tuple(reversed(policy.approved_genome_builds)),
            "approved_transcript_builds": tuple(reversed(policy.approved_transcript_builds)),
        }
    )
    assert configuration_digest(reordered) == original


@pytest.mark.contract
def test_approved_build_model_is_strict_and_closed() -> None:
    assert ApprovedBuild.model_validate_json(
        b'{"build_id":"build.boundary","version":"1.0.0"}', strict=True
    )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ApprovedBuild.model_validate_json(
            b'{"build_id":"build.boundary","version":"1.0.0","extra":true}',
            strict=True,
        )
