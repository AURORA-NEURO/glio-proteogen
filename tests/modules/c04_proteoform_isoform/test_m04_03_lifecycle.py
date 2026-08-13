"""Focused lifecycle, firewall, immutable-byte, and replay checks for M04-03."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from hashlib import sha256
from typing import Any, NoReturn, cast

import pytest
from evals.m04_02.run import build_scenario_request as build_m0402_request
from evals.m04_03.run import Scenario, build_scenario
from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m04_02 import (
    ProteoformLineageArtifactRole,
    ProteoformLineageDisposition,
    ReconcileProteoformIdentityLineageRequest,
)
from glio_proteogen.contracts.m04_03 import (
    M0403_LIMITATION_COUNT,
    M0403_MAX_DIAGNOSTICS,
    M0403_MIN_EVIDENCE,
    IngestProteoformRawInputsRequest,
    ProteoformRawDiagnosticCode,
    ProteoformRawInputDisposition,
    ProteoformRawInputRole,
    ProteoformRawInputValidationResult,
    configuration_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c04_proteoform_isoform import m04_03_raw_ingestion
from glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage import (
    reconcile_proteoform_identity_lineage,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_03_raw_ingestion import (
    M0403Plugin,
    M0403ProteoformRawInputIngester,
    M0403Service,
    M0403Submission,
    ProteoformRawInputAuthorizationError,
    ProteoformRawInputError,
    ProteoformRawInputErrorCode,
    ingest_proteoform_raw_inputs,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_03_raw_ingestion import (
    engine as m0403_engine,
)

ROLE_PROJECTION = {
    ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
        ProteoformLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST
    ),
    ProteoformRawInputRole.GENOME: ProteoformLineageArtifactRole.GENOME_MANIFEST,
    ProteoformRawInputRole.TRANSCRIPTOME: (ProteoformLineageArtifactRole.TRANSCRIPTOME_MANIFEST),
    ProteoformRawInputRole.PTM_ANNOTATIONS: (ProteoformLineageArtifactRole.PTM_ANNOTATION_MANIFEST),
}


class _HostileTraversalError(AssertionError):
    """Caller-controlled governed material was touched before authorization."""


class _TraversalTrap(Mapping[str, object]):
    def __init__(self) -> None:
        self.traversals = 0

    def _fail(self) -> NoReturn:
        self.traversals += 1
        raise _HostileTraversalError

    def __getitem__(self, key: str) -> object:
        del key
        self._fail()

    def __iter__(self) -> Iterator[str]:
        self._fail()

    def __len__(self) -> int:  # noqa: PLE0303 - intentional hostile mapping.
        self._fail()


class _HostileDict(dict[object, object]):
    def get(self, key: object, default: object = None) -> object:
        del key, default
        raise _HostileTraversalError

    def items(self) -> NoReturn:
        raise _HostileTraversalError

    def __iter__(self) -> Iterator[object]:
        raise _HostileTraversalError

    def __getitem__(self, key: object) -> object:
        del key
        raise _HostileTraversalError


class _PreflightBaseException(BaseException):
    """Sentinel proving BaseException is never swallowed."""


@pytest.fixture(scope="module")
def scenario() -> Scenario:
    return build_scenario()


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _context_for_lineage(
    request: IngestProteoformRawInputsRequest,
    lineage: Any,
) -> Any:
    refs = request.context.references
    updated = refs.model_copy(
        update={
            "identity_lineage": refs.identity_lineage.model_copy(
                update={"binding_digest": lineage.identity_resolution_digest}
            ),
            "quality": refs.quality.model_copy(
                update={
                    "evidence": refs.quality.evidence.model_copy(
                        update={"digest": lineage.result_digest}
                    )
                }
            ),
            "support": refs.support.model_copy(
                update={
                    "evidence": refs.support.evidence.model_copy(
                        update={"digest": lineage.receipt.receipt_digest}
                    )
                }
            ),
            "intended_use": refs.intended_use.model_copy(
                update={
                    "evidence": refs.intended_use.evidence.model_copy(
                        update={"digest": lineage.receipt.intended_use_evidence_digest}
                    )
                }
            ),
        }
    )
    return request.context.model_copy(update={"references": updated})


def _request_for_lineage(
    scenario: Scenario,
    lineage: Any,
) -> IngestProteoformRawInputsRequest:
    claims = {item.role: item for item in lineage.request.artifact_claims}
    artifacts = tuple(
        item.model_copy(
            update={
                "lineage_claim_id": claims[ROLE_PROJECTION[item.role]].claim_id,
                "manifest_reference": claims[ROLE_PROJECTION[item.role]].artifact,
            }
        )
        for item in scenario.request.artifacts
    )
    context = _context_for_lineage(scenario.request, lineage)
    return IngestProteoformRawInputsRequest(
        request_id=context.request_id,
        context=context,
        lineage_result=lineage,
        policy=scenario.request.policy,
        artifacts=artifacts,
        supersedes_result_digest=None,
    )


def _scenario_with_bytes(
    scenario: Scenario,
    artifacts_by_role: dict[ProteoformRawInputRole, bytes],
) -> Scenario:
    """Rebind genuine M04-02 artifact digests before exercising M04-03 parsing."""

    lineage_request = scenario.request.lineage_result.request
    role_by_upstream = {value: key for key, value in ROLE_PROJECTION.items()}
    claims = tuple(
        claim.model_copy(
            update={
                "artifact": claim.artifact.model_copy(
                    update={
                        "digest": _digest_bytes(artifacts_by_role[role_by_upstream[claim.role]])
                    }
                )
            }
        )
        if claim.role in role_by_upstream
        else claim
        for claim in lineage_request.artifact_claims
    )
    lineage_payload = lineage_request.model_dump(mode="python", exclude_none=False)
    lineage_payload["artifact_claims"] = claims
    rebound_lineage_request = ReconcileProteoformIdentityLineageRequest.model_validate(
        lineage_payload,
        strict=True,
    )
    lineage = reconcile_proteoform_identity_lineage(rebound_lineage_request)
    request = _request_for_lineage(scenario, lineage)
    upstream_claims = {item.role: item for item in lineage.request.artifact_claims}
    artifacts = tuple(
        item.model_copy(
            update={
                "declared_size_bytes": len(artifacts_by_role[item.role]),
                "lineage_claim_id": upstream_claims[ROLE_PROJECTION[item.role]].claim_id,
                "manifest_reference": upstream_claims[ROLE_PROJECTION[item.role]].artifact,
            }
        )
        for item in request.artifacts
    )
    payload = request.model_dump(mode="python", exclude_none=False)
    payload["artifacts"] = artifacts
    return Scenario(
        request=IngestProteoformRawInputsRequest.model_validate(payload, strict=True),
        artifacts_by_role=artifacts_by_role,
    )


def _assert_input_error(
    expected: ProteoformRawInputErrorCode,
    request: object,
    artifacts: object,
) -> None:
    with pytest.raises(ProteoformRawInputError) as captured:
        ingest_proteoform_raw_inputs(request, artifacts)
    assert captured.value.code is expected


def test_genuine_four_role_ingestion_is_closed_and_metadata_only(scenario: Scenario) -> None:
    result = ingest_proteoform_raw_inputs(scenario.request, scenario.artifacts_by_role)

    assert result.disposition is ProteoformRawInputDisposition.VALIDATED
    assert len(result.validated_inputs) == len(ProteoformRawInputRole)
    assert result.diagnostics == ()
    assert len(result.evidence) == M0403_MIN_EVIDENCE
    assert len(result.limitations) == M0403_LIMITATION_COUNT
    assert not result.human_review_required
    assert result.result_digest != "sha256:" + ("0" * 64)
    assert (
        ProteoformRawInputValidationResult.model_validate_json(
            result.model_dump_json(), strict=True
        )
        == result
    )
    rendered = result.model_dump_json()
    assert all(payload.decode() not in rendered for payload in scenario.artifacts_by_role.values())
    assert not any(
        (
            result.emits_protein_rna_discordance,
            result.emits_proteogenomic_state,
            result.emits_proteotype,
            result.emits_protein_level_subtype,
            result.infers_identity,
            result.infers_consent,
            result.infers_protein,
            result.infers_proteoform,
            result.infers_kinase_activity,
            result.performs_cn_to_protein_regression,
            result.performs_all_omics_fusion,
            result.recommends_treatment,
            result.mutates_upstream,
            result.executes_model,
        )
    )


def test_library_engine_service_and_plugin_have_exact_parity(scenario: Scenario) -> None:
    direct = ingest_proteoform_raw_inputs(scenario.request, scenario.artifacts_by_role)
    engine = M0403ProteoformRawInputIngester().ingest(scenario.request, scenario.artifacts_by_role)
    service = M0403Service().execute(scenario.request, scenario.artifacts_by_role)
    plugin = M0403Plugin(M0403Service())
    token = plugin.validate(
        M0403Submission(
            request=canonical_json_bytes(scenario.request),
            artifacts_by_role=scenario.artifacts_by_role,
        )
    )

    assert direct == engine == service == plugin.run(token)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M04-03"
    assert plugin.descriptor().owner == "Clinical science"
    assert (plugin.descriptor().safety_class, plugin.descriptor().gate) == ("S2", "G0")
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(scenario.request)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("control", "denied_state"),
    [
        ("approved_configuration", "rejected"),
        ("identity_lineage", "unresolved"),
        ("provenance", "rejected"),
        ("consent", "withheld"),
        ("quality", "rejected"),
        ("support", "rejected"),
        ("intended_use", "rejected"),
    ],
)
def test_each_denied_control_precedes_request_and_artifact_traversal(
    scenario: Scenario,
    control: str,
    denied_state: str,
) -> None:
    payload = scenario.request.model_dump(mode="python", exclude_none=False)
    cast("dict[str, Any]", payload["context"])["references"][control]["state"] = denied_state
    governed = (_TraversalTrap(), _TraversalTrap(), _TraversalTrap())
    payload["lineage_result"], payload["policy"], payload["artifacts"] = governed
    artifacts = _TraversalTrap()

    with pytest.raises(ProteoformRawInputAuthorizationError):
        ingest_proteoform_raw_inputs(payload, artifacts)
    assert all(item.traversals == 0 for item in (*governed, artifacts))


@pytest.mark.parametrize(
    "candidate",
    [
        _TraversalTrap(),
        {"context": _TraversalTrap()},
        {"context": {"references": _TraversalTrap()}},
    ],
)
def test_arbitrary_mapping_is_denied_without_access(candidate: object) -> None:
    with pytest.raises(ProteoformRawInputAuthorizationError):
        ingest_proteoform_raw_inputs(candidate, _TraversalTrap())


def test_dict_subclass_overrides_are_ignored_at_both_boundaries(scenario: Scenario) -> None:
    payload = scenario.request.model_dump(mode="python", exclude_none=False)
    payload["policy"] = _HostileDict(cast("dict[object, object]", payload["policy"]))
    request = _HostileDict(cast("dict[object, object]", payload))
    artifacts = _HostileDict(cast("dict[object, object]", scenario.artifacts_by_role))

    assert ingest_proteoform_raw_inputs(request, artifacts) == ingest_proteoform_raw_inputs(
        scenario.request, scenario.artifacts_by_role
    )
    assert M0403Service.validate_request(request) == scenario.request


def test_plain_non_dict_artifact_mapping_is_rejected(scenario: Scenario) -> None:
    _assert_input_error(
        ProteoformRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH,
        scenario.request,
        _TraversalTrap(),
    )


def test_strict_plain_materialization_rejects_non_string_keys(scenario: Scenario) -> None:
    payload: dict[object, object] = {
        cast("object", key): cast("object", value)
        for key, value in scenario.request.model_dump(mode="python", exclude_none=False).items()
    }
    payload[1] = "hostile-key"
    with pytest.raises(TypeError, match="exact string keys"):
        M0403Service.validate_request(payload)


def test_exception_fails_closed_but_baseexception_propagates(
    scenario: Scenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_exception(_candidate: object, _field: str) -> NoReturn:
        raise RuntimeError

    monkeypatch.setattr(m0403_engine, "_member", raise_exception)
    with pytest.raises(ProteoformRawInputAuthorizationError):
        ingest_proteoform_raw_inputs(scenario.request, scenario.artifacts_by_role)

    def raise_baseexception(_candidate: object, _field: str) -> NoReturn:
        raise _PreflightBaseException

    monkeypatch.setattr(m0403_engine, "_member", raise_baseexception)
    with pytest.raises(_PreflightBaseException):
        ingest_proteoform_raw_inputs(scenario.request, scenario.artifacts_by_role)


@pytest.mark.parametrize(
    ("case_id", "expected_disposition", "expected_code"),
    [
        (
            "specimen_subject_swap",
            ProteoformLineageDisposition.QUARANTINED,
            ProteoformRawDiagnosticCode.UPSTREAM_LINEAGE_QUARANTINED,
        ),
        (
            "missing_abstains",
            ProteoformLineageDisposition.ABSTAINED,
            ProteoformRawDiagnosticCode.UPSTREAM_LINEAGE_ABSTAINED,
        ),
    ],
)
def test_nonreleasable_upstream_returns_typed_zero_traversal_result(
    scenario: Scenario,
    case_id: str,
    expected_disposition: ProteoformLineageDisposition,
    expected_code: ProteoformRawDiagnosticCode,
) -> None:
    lineage = reconcile_proteoform_identity_lineage(build_m0402_request(case_id))
    assert lineage.disposition is expected_disposition
    request = _request_for_lineage(scenario, lineage)
    artifacts = _TraversalTrap()

    result = ingest_proteoform_raw_inputs(request, artifacts)
    assert artifacts.traversals == 0
    assert result.validated_inputs == ()
    assert tuple(item.code for item in result.diagnostics) == (expected_code,)
    assert result.disposition.value == expected_disposition.value


def test_plugin_safe_failure_token_never_reads_artifact_mapping(scenario: Scenario) -> None:
    lineage = reconcile_proteoform_identity_lineage(build_m0402_request("missing_abstains"))
    request = _request_for_lineage(scenario, lineage)
    artifacts = _TraversalTrap()
    plugin = M0403Plugin(M0403Service())

    token = plugin.validate(M0403Submission(request=request, artifacts_by_role=artifacts))
    result = plugin.run(token)
    assert artifacts.traversals == 0
    assert result.disposition is ProteoformRawInputDisposition.ABSTAINED
    assert result.validated_inputs == ()


@pytest.mark.parametrize("mutation", ["missing", "extra", "string_keys"])
def test_exact_role_mapping_is_enforced(
    scenario: Scenario,
    mutation: str,
) -> None:
    artifacts: dict[object, object] = {
        cast("object", role): cast("object", value)
        for role, value in scenario.artifacts_by_role.items()
    }
    if mutation == "missing":
        artifacts.pop(next(iter(ProteoformRawInputRole)))
    elif mutation == "extra":
        artifacts["extra"] = b"{}"
    else:
        artifacts = {role.value: value for role, value in scenario.artifacts_by_role.items()}
    _assert_input_error(
        ProteoformRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH,
        scenario.request,
        artifacts,
    )


@pytest.mark.parametrize("kind", ["bytearray", "bytes_subclass"])
def test_only_exact_immutable_bytes_are_accepted(scenario: Scenario, kind: str) -> None:
    class BytesSubclass(bytes):
        pass

    artifacts: dict[ProteoformRawInputRole, object] = dict(scenario.artifacts_by_role)
    role = next(iter(ProteoformRawInputRole))
    value = cast("bytes", artifacts[role])
    artifacts[role] = bytearray(value) if kind == "bytearray" else BytesSubclass(value)
    _assert_input_error(
        ProteoformRawInputErrorCode.ARTIFACT_TYPE_INVALID,
        scenario.request,
        artifacts,
    )


def test_declared_size_and_digest_mismatches_are_distinct(scenario: Scenario) -> None:
    first = scenario.request.artifacts[0]
    wrong_size = first.model_copy(update={"declared_size_bytes": first.declared_size_bytes + 1})
    request = scenario.request.model_copy(
        update={"artifacts": (wrong_size, *scenario.request.artifacts[1:])}
    )
    _assert_input_error(
        ProteoformRawInputErrorCode.ARTIFACT_SIZE_MISMATCH,
        request,
        scenario.artifacts_by_role,
    )

    artifacts = dict(scenario.artifacts_by_role)
    artifacts[first.role] += b"x"
    request = scenario.request.model_copy(
        update={
            "artifacts": (
                first.model_copy(update={"declared_size_bytes": len(artifacts[first.role])}),
                *scenario.request.artifacts[1:],
            )
        }
    )
    _assert_input_error(
        ProteoformRawInputErrorCode.ARTIFACT_DIGEST_MISMATCH,
        request,
        artifacts,
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("invalid_json", ProteoformRawInputErrorCode.DOCUMENT_JSON_INVALID),
        ("duplicate_json", ProteoformRawInputErrorCode.DOCUMENT_JSON_INVALID),
        ("noncanonical", ProteoformRawInputErrorCode.DOCUMENT_NOT_CANONICAL),
        ("wrong_type", ProteoformRawInputErrorCode.DOCUMENT_TYPE_MISMATCH),
        ("unknown_field", ProteoformRawInputErrorCode.DOCUMENT_JSON_INVALID),
    ],
)
def test_strict_document_boundary_reports_stable_structural_codes(
    scenario: Scenario,
    mutation: str,
    expected: ProteoformRawInputErrorCode,
) -> None:
    artifacts = dict(scenario.artifacts_by_role)
    role = ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME
    original = artifacts[role]
    payload = cast("dict[str, object]", json.loads(original))
    if mutation == "invalid_json":
        artifacts[role] = b"{"
    elif mutation == "duplicate_json":
        artifacts[role] = original.replace(b"{", b'{"document_type":"duplicate",', 1)
    elif mutation == "noncanonical":
        artifacts[role] = original + b"\n"
    elif mutation == "wrong_type":
        payload["document_type"] = "genome_input"
        artifacts[role] = canonical_json_bytes(payload)
    else:
        payload["unknown_field"] = True
        artifacts[role] = canonical_json_bytes(payload)
    rebound = _scenario_with_bytes(scenario, artifacts)
    _assert_input_error(expected, rebound.request, rebound.artifacts_by_role)


def test_strict_document_materializer_rejects_python_shape_coercions(
    scenario: Scenario,
) -> None:
    role = ProteoformRawInputRole.PTM_ANNOTATIONS
    decoded = cast("dict[str, object]", json.loads(scenario.artifacts_by_role[role]))
    model = type(
        next(
            item.document
            for item in ingest_proteoform_raw_inputs(
                scenario.request, scenario.artifacts_by_role
            ).validated_inputs
            if item.role is role
        )
    )

    missing_default = dict(decoded)
    del missing_default["document_version"]
    assert "document_version" not in m0403_engine._strict_document_python_value(
        model, missing_default
    )

    malformed = []
    wrong_enum = dict(decoded)
    wrong_enum["evidence_state"] = 1
    malformed.append(wrong_enum)
    wrong_collection = dict(decoded)
    wrong_collection["localization_states"] = tuple(
        cast("list[object]", wrong_collection["localization_states"])
    )
    malformed.append(wrong_collection)
    wrong_item = dict(decoded)
    wrong_item["localization_states"] = [1]
    malformed.append(wrong_item)
    for candidate in malformed:
        with pytest.raises(ProteoformRawInputError) as captured:
            m0403_engine._strict_document_python_value(model, candidate)
        assert captured.value.code is ProteoformRawInputErrorCode.DOCUMENT_JSON_INVALID

    class StringTupleModel(BaseModel):
        items: tuple[str, ...]

    assert m0403_engine._strict_document_python_value(StringTupleModel, {"items": ["one"]}) == {
        "items": ("one",)
    }


def test_matching_parser_profile_cap_precedes_hash_and_json(scenario: Scenario) -> None:
    role = ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME
    active_size = len(scenario.artifacts_by_role[role])
    parsers = tuple(
        item.model_copy(update={"max_document_bytes": active_size - 1})
        if item.role is role
        else item
        for item in scenario.request.policy.approved_parsers
    )
    policy = scenario.request.policy.model_copy(update={"approved_parsers": parsers})
    refs = scenario.request.context.references
    approved = refs.approved_configuration.model_copy(
        update={
            "evidence": refs.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    context = scenario.request.context.model_copy(
        update={"references": refs.model_copy(update={"approved_configuration": approved})}
    )
    request = IngestProteoformRawInputsRequest.model_validate(
        scenario.request.model_copy(update={"context": context, "policy": policy}).model_dump(
            mode="python", exclude_none=False
        ),
        strict=True,
    )
    _assert_input_error(
        ProteoformRawInputErrorCode.ARTIFACT_SIZE_MISMATCH,
        request,
        scenario.artifacts_by_role,
    )


def test_maximum_semantic_discrepancy_is_typed_and_diagnostic_capped(
    scenario: Scenario,
) -> None:
    decoded = {
        role: cast("dict[str, Any]", json.loads(payload))
        for role, payload in scenario.artifacts_by_role.items()
    }
    roles = tuple(ProteoformRawInputRole)
    stale_digest = "sha256:" + ("f" * 64)
    for index, role in enumerate(roles):
        document = decoded[role]
        other = decoded[roles[(index + 1) % len(roles)]]
        document["lineage_claim_id"] = other["lineage_claim_id"]
        document["input_id"] = other["input_id"]
        document["content_reference"] = other["content_reference"]
        for field in (
            "identity_resolution_digest",
            "protocol_result_digest",
            "reference_bundle_digest",
            "coordinate_policy_digest",
            "intended_use_evidence_digest",
        ):
            document[field] = stale_digest
        for field in (
            "assay_protocol_version",
            "specimen_processing_version",
            "unit_definition_version",
        ):
            document[field] = "9.9.9"
        document["evidence_state"] = "missing"
        document["completeness_state"] = "incomplete"
        document["assay_support_state"] = "unsupported"
        document["parent_quality_state"] = "rejected"

    decoded[ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME].update(
        applicability="top_down",
        protein_unit="molar_fraction",
        protein_scale="log2",
    )
    genome = decoded[ProteoformRawInputRole.GENOME]
    genome.update(
        genome_convention=(
            "zero_based_half_open"
            if genome["genome_convention"] == "one_based_closed"
            else "one_based_closed"
        ),
        genome_reference_digest=stale_digest,
        coordinate_mapping_version="9.9.9",
    )
    transcriptome = decoded[ProteoformRawInputRole.TRANSCRIPTOME]
    transcriptome.update(
        transcript_unit="normalized_count",
        transcript_scale="log2",
        transcript_convention=(
            "zero_based_half_open"
            if transcriptome["transcript_convention"] == "one_based_closed"
            else "one_based_closed"
        ),
        transcript_annotation_digest=stale_digest,
        transcript_protein_mapping_digest=stale_digest,
    )
    ptm = decoded[ProteoformRawInputRole.PTM_ANNOTATIONS]
    ptm.update(
        modification_vocabulary_id="vocabulary." + ("f" * 64),
        modification_vocabulary_version="9.9.9",
        modification_vocabulary_digest=stale_digest,
        protein_convention=(
            "zero_based_half_open"
            if ptm["protein_convention"] == "one_based_closed"
            else "one_based_closed"
        ),
        coordinate_mapping_version="9.9.9",
    )
    artifacts_by_role = {role: canonical_json_bytes(document) for role, document in decoded.items()}
    rebound = _scenario_with_bytes(scenario, artifacts_by_role)
    request_payload = rebound.request.model_dump(mode="python", exclude_none=False)
    request_payload["artifacts"] = tuple(
        item.model_copy(update={"format_version": "9.9.9"}) for item in rebound.request.artifacts
    )
    request = IngestProteoformRawInputsRequest.model_validate(request_payload, strict=True)

    result = ingest_proteoform_raw_inputs(request, artifacts_by_role)
    diagnostic_keys = tuple((item.code, item.role) for item in result.diagnostics)
    assert result.disposition is ProteoformRawInputDisposition.QUARANTINED
    assert len(result.validated_inputs) == len(ProteoformRawInputRole)
    assert M0403_MIN_EVIDENCE < len(result.diagnostics) <= M0403_MAX_DIAGNOSTICS
    assert len(diagnostic_keys) == len(set(diagnostic_keys))


def test_plugin_snapshots_once_and_seals_private_preparation(scenario: Scenario) -> None:
    supplied = dict(scenario.artifacts_by_role)
    plugin = M0403Plugin(M0403Service())
    token = plugin.validate(M0403Submission(request=scenario.request, artifacts_by_role=supplied))
    expected = ingest_proteoform_raw_inputs(scenario.request, scenario.artifacts_by_role)
    for role in tuple(supplied):
        supplied[role] = b"corrupted after validation"

    assert plugin.run(token) == expected
    assert not hasattr(m04_03_raw_ingestion, "prepare_proteoform_raw_inputs")
    assert not hasattr(M0403Service, "execute_prepared")
    assert not hasattr(M0403ProteoformRawInputIngester, "ingest_prepared")


def test_plugin_requires_submission_and_prepared_capability_is_nominal(scenario: Scenario) -> None:
    plugin = M0403Plugin(M0403Service())
    with pytest.raises(TypeError, match="raw-input submission"):
        plugin.validate(scenario.request)

    class PreparedSubclass(m0403_engine._PreparedProteoformRawInputs):
        pass

    prepared = m0403_engine._PreparedProteoformRawInputs(snapshots=(), documents=())
    with pytest.raises(TypeError, match="prepared input capability"):
        M0403ProteoformRawInputIngester()._ingest_prepared(
            scenario.request,
            PreparedSubclass(prepared.snapshots, prepared.documents),
        )


def test_mapping_order_is_semantic_and_result_replay_rejects_forgery(scenario: Scenario) -> None:
    reversed_mapping = dict(reversed(tuple(scenario.artifacts_by_role.items())))
    result = ingest_proteoform_raw_inputs(scenario.request, scenario.artifacts_by_role)
    assert ingest_proteoform_raw_inputs(scenario.request, reversed_mapping) == result

    payload = result.model_dump(mode="python", exclude_none=False)
    cast("dict[str, object]", payload["support"])["rationale"] = "resigned local forgery"
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError):
        ProteoformRawInputValidationResult.model_validate(payload, strict=True)


def test_plugin_rejects_duplicate_unknown_coercion_and_oversize_request(scenario: Scenario) -> None:
    plugin = M0403Plugin(M0403Service())
    rendered = scenario.request.model_dump_json()
    duplicate = rendered.replace(
        '"operation":"ingest_proteoform_raw_inputs"',
        ('"operation":"ingest_proteoform_raw_inputs","operation":"ingest_proteoform_raw_inputs"'),
        1,
    )
    unknown = scenario.request.model_dump(mode="json", exclude_none=False)
    unknown["unexpected"] = True
    coercion = scenario.request.model_dump(mode="json", exclude_none=False)
    coercion["contract_version"] = 1
    malformed: tuple[object, ...] = (
        duplicate,
        canonical_json_bytes(unknown),
        canonical_json_bytes(coercion),
        b"{" + (b" " * (4 * 1024 * 1024)) + b"}",
    )
    for candidate in malformed:
        with pytest.raises((ValueError, ValidationError)):
            plugin.validate(
                M0403Submission(
                    request=candidate,
                    artifacts_by_role=scenario.artifacts_by_role,
                )
            )
