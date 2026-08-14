"""Focused lifecycle, firewall, immutable-byte, and replay checks for M05-03."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator, Mapping, Sequence
from hashlib import sha256
from typing import Any, NoReturn, cast

import pytest
from evals.m05_02.run import build_scenario_request as build_m0502_request
from evals.m05_03.run import Scenario, build_scenario
from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m05_02 import (
    PtmLocalizationLineageArtifactRole,
    PtmLocalizationLineageDisposition,
    ReconcilePtmLocalizationIdentityLineageRequest,
)
from glio_proteogen.contracts.m05_03 import (
    M0503_LIMITATION_COUNT,
    M0503_MAX_DIAGNOSTICS,
    M0503_MIN_EVIDENCE,
    M0503_MIN_RECONCILED_EVIDENCE,
    IngestPtmLocalizationRawInputsRequest,
    PtmLocalizationRawDiagnosticCode,
    PtmLocalizationRawInputDisposition,
    PtmLocalizationRawInputRole,
    PtmLocalizationRawInputValidationResult,
    configuration_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization import m05_03_raw_ingestion
from glio_proteogen.modules.c05_ptm_localization.m05_02_identity_lineage import (
    reconcile_ptm_localization_identity_lineage,
)
from glio_proteogen.modules.c05_ptm_localization.m05_03_raw_ingestion import (
    M0503Plugin,
    M0503PtmLocalizationRawInputIngester,
    M0503Service,
    M0503Submission,
    PtmLocalizationRawInputAuthorizationError,
    PtmLocalizationRawInputError,
    PtmLocalizationRawInputErrorCode,
    ValidatedM0503Request,
    ingest_ptm_localization_raw_inputs,
)
from glio_proteogen.modules.c05_ptm_localization.m05_03_raw_ingestion import (
    engine as m0503_engine,
)

ROLE_PROJECTION = {
    PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
        PtmLocalizationLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST
    ),
    PtmLocalizationRawInputRole.GENOME: PtmLocalizationLineageArtifactRole.GENOME_MANIFEST,
    PtmLocalizationRawInputRole.TRANSCRIPTOME: (
        PtmLocalizationLineageArtifactRole.TRANSCRIPTOME_MANIFEST
    ),
    PtmLocalizationRawInputRole.PTM_ANNOTATIONS: (
        PtmLocalizationLineageArtifactRole.PTM_ANNOTATION_MANIFEST
    ),
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


class _HostileList(list[object]):
    def __init__(self, values: list[object]) -> None:
        super().__init__(values)
        self.traversals = 0

    def _fail(self) -> NoReturn:
        self.traversals += 1
        raise _HostileTraversalError

    def __iter__(self) -> Iterator[object]:
        self._fail()


class _HostileTuple(tuple[object, ...]):
    __slots__ = ()

    traversals = 0

    def __iter__(self) -> Iterator[object]:
        type(self).traversals += 1
        raise _HostileTraversalError


class _VirtualSequence:
    def __init__(self) -> None:
        self.traversals = 0

    def __len__(self) -> int:
        self.traversals += 1
        raise _HostileTraversalError

    def __getitem__(self, key: object) -> object:
        del key
        self.traversals += 1
        raise _HostileTraversalError


Sequence.register(_VirtualSequence)


class _PreflightBaseException(BaseException):
    """Sentinel proving BaseException is never swallowed."""


@pytest.fixture(scope="module")
def scenario() -> Scenario:
    return build_scenario()


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _context_for_lineage(
    request: IngestPtmLocalizationRawInputsRequest,
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
) -> IngestPtmLocalizationRawInputsRequest:
    claims = {item.role: item for item in lineage.request.artifact_claims}
    artifacts = (
        tuple(
            item.model_copy(
                update={
                    "lineage_claim_id": claims[ROLE_PROJECTION[item.role]].claim_id,
                    "manifest_reference": claims[ROLE_PROJECTION[item.role]].artifact,
                }
            )
            for item in scenario.request.artifacts
        )
        if lineage.disposition.value == "reconciled"
        else ()
    )
    context = _context_for_lineage(scenario.request, lineage)
    return IngestPtmLocalizationRawInputsRequest(
        request_id=context.request_id,
        context=context,
        lineage_result=lineage,
        policy=scenario.request.policy,
        artifacts=artifacts,
        supersedes_result_digest=None,
    )


def _scenario_with_bytes(
    scenario: Scenario,
    artifacts_by_role: dict[PtmLocalizationRawInputRole, bytes],
) -> Scenario:
    """Rebind genuine M05-02 artifact digests before exercising M05-03 parsing."""

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
    rebound_lineage_request = ReconcilePtmLocalizationIdentityLineageRequest.model_validate(
        lineage_payload,
        strict=True,
    )
    lineage = reconcile_ptm_localization_identity_lineage(rebound_lineage_request)
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
        request=IngestPtmLocalizationRawInputsRequest.model_validate(payload, strict=True),
        artifacts_by_role=artifacts_by_role,
    )


def _assert_input_error(
    expected: PtmLocalizationRawInputErrorCode,
    request: object,
    artifacts: object,
) -> None:
    with pytest.raises(PtmLocalizationRawInputError) as captured:
        ingest_ptm_localization_raw_inputs(request, artifacts)
    assert captured.value.code is expected


def test_genuine_four_role_ingestion_is_closed_and_metadata_only(scenario: Scenario) -> None:
    result = ingest_ptm_localization_raw_inputs(scenario.request, scenario.artifacts_by_role)

    assert result.disposition is PtmLocalizationRawInputDisposition.VALIDATED
    assert len(result.validated_inputs) == len(PtmLocalizationRawInputRole)
    assert result.diagnostics == ()
    assert len(result.evidence) == M0503_MIN_RECONCILED_EVIDENCE
    assert len(result.limitations) == M0503_LIMITATION_COUNT
    assert not result.human_review_required
    assert result.result_digest != "sha256:" + ("0" * 64)
    assert (
        PtmLocalizationRawInputValidationResult.model_validate_json(
            result.model_dump_json(), strict=True
        )
        == result
    )
    rendered = result.model_dump_json()
    assert all(payload.decode() not in rendered for payload in scenario.artifacts_by_role.values())
    assert not any(
        (
            result.emits_variant_peptide,
            result.emits_proteogenomic_state,
            result.emits_proteotype,
            result.emits_protein_level_subtype,
            result.infers_identity,
            result.infers_consent,
            result.infers_protein,
            result.infers_ptm_localization,
            result.infers_kinase_activity,
            result.performs_cn_to_protein_regression,
            result.performs_all_omics_fusion,
            result.recommends_treatment,
            result.mutates_upstream,
            result.executes_model,
        )
    )


def test_library_engine_service_and_plugin_have_exact_parity(scenario: Scenario) -> None:
    direct = ingest_ptm_localization_raw_inputs(scenario.request, scenario.artifacts_by_role)
    engine = M0503PtmLocalizationRawInputIngester().ingest(
        scenario.request, scenario.artifacts_by_role
    )
    service = M0503Service().execute(scenario.request, scenario.artifacts_by_role)
    plugin = M0503Plugin(M0503Service())
    token = plugin.validate(
        M0503Submission(
            request=canonical_json_bytes(scenario.request),
            artifacts_by_role=scenario.artifacts_by_role,
        )
    )

    assert direct == engine == service == plugin.run(token)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M05-03"
    assert plugin.descriptor().owner == "Data engineering"
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

    with pytest.raises(PtmLocalizationRawInputAuthorizationError):
        ingest_ptm_localization_raw_inputs(payload, artifacts)
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
    with pytest.raises(PtmLocalizationRawInputAuthorizationError):
        ingest_ptm_localization_raw_inputs(candidate, _TraversalTrap())


def test_dict_subclasses_are_rejected_without_invoking_overrides(scenario: Scenario) -> None:
    payload = scenario.request.model_dump(mode="python", exclude_none=False)
    payload["policy"] = _HostileDict(cast("dict[object, object]", payload["policy"]))
    request = _HostileDict(cast("dict[object, object]", payload))
    artifacts = _HostileDict(cast("dict[object, object]", scenario.artifacts_by_role))

    with pytest.raises(PtmLocalizationRawInputAuthorizationError):
        ingest_ptm_localization_raw_inputs(request, artifacts)
    with pytest.raises(TypeError, match="exact string keys"):
        M0503Service.validate_request(payload)
    _assert_input_error(
        PtmLocalizationRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH,
        scenario.request,
        artifacts,
    )


@pytest.mark.parametrize("hostile_kind", ["list", "tuple", "virtual_sequence"])
def test_nested_container_subclasses_reject_with_zero_access(
    scenario: Scenario,
    hostile_kind: str,
) -> None:
    if hostile_kind == "list":
        hostile: object = _HostileList(list(scenario.request.artifacts))
    elif hostile_kind == "tuple":
        _HostileTuple.traversals = 0
        hostile = _HostileTuple(tuple(scenario.request.artifacts))
    else:
        hostile = _VirtualSequence()
    payload = scenario.request.model_dump(mode="python", exclude_none=False)
    payload["artifacts"] = hostile

    with pytest.raises(TypeError, match="exact string keys"):
        M0503Service.validate_request(payload)
    traversals = (
        _HostileTuple.traversals
        if hostile_kind == "tuple"
        else cast("_HostileList | _VirtualSequence", hostile).traversals
    )
    assert traversals == 0


def test_exact_request_storage_rejects_unknown_and_non_string_members(
    scenario: Scenario,
) -> None:
    unknown = scenario.request.model_copy(deep=True)
    unknown_storage = cast(
        "dict[object, object]",
        object.__getattribute__(unknown, "__dict__"),
    )
    dict.__setitem__(unknown_storage, "unknown", "canary")
    with pytest.raises(TypeError, match="exact string keys"):
        M0503Service.validate_request(unknown)

    non_string = scenario.request.model_copy(deep=True)
    non_string_storage = cast(
        "dict[object, object]",
        object.__getattribute__(non_string, "__dict__"),
    )
    dict.__setitem__(non_string_storage, 1, "canary")
    with pytest.raises(PtmLocalizationRawInputAuthorizationError):
        M0503Service.validate_request(non_string)


def test_plain_non_dict_artifact_mapping_is_rejected(scenario: Scenario) -> None:
    _assert_input_error(
        PtmLocalizationRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH,
        scenario.request,
        _TraversalTrap(),
    )


def test_strict_plain_materialization_rejects_non_string_keys(scenario: Scenario) -> None:
    payload: dict[object, object] = {
        cast("object", key): cast("object", value)
        for key, value in scenario.request.model_dump(mode="python", exclude_none=False).items()
    }
    payload[1] = "hostile-key"
    with pytest.raises(PtmLocalizationRawInputAuthorizationError):
        M0503Service.validate_request(payload)


def test_exception_fails_closed_but_baseexception_propagates(
    scenario: Scenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_exception(_candidate: object, _field: str) -> NoReturn:
        raise RuntimeError

    monkeypatch.setattr(m0503_engine, "_member", raise_exception)
    with pytest.raises(PtmLocalizationRawInputAuthorizationError):
        ingest_ptm_localization_raw_inputs(scenario.request, scenario.artifacts_by_role)

    def raise_baseexception(_candidate: object, _field: str) -> NoReturn:
        raise _PreflightBaseException

    monkeypatch.setattr(m0503_engine, "_member", raise_baseexception)
    with pytest.raises(_PreflightBaseException):
        ingest_ptm_localization_raw_inputs(scenario.request, scenario.artifacts_by_role)


@pytest.mark.parametrize(
    ("case_id", "expected_disposition", "expected_code"),
    [
        (
            "upstream_protocol_quarantined",
            PtmLocalizationLineageDisposition.QUARANTINED,
            PtmLocalizationRawDiagnosticCode.UPSTREAM_LINEAGE_QUARANTINED,
        ),
        (
            "upstream_identity_unresolved",
            PtmLocalizationLineageDisposition.ABSTAINED,
            PtmLocalizationRawDiagnosticCode.UPSTREAM_LINEAGE_ABSTAINED,
        ),
    ],
)
def test_nonreleasable_upstream_returns_typed_zero_traversal_result(
    scenario: Scenario,
    case_id: str,
    expected_disposition: PtmLocalizationLineageDisposition,
    expected_code: PtmLocalizationRawDiagnosticCode,
) -> None:
    lineage = reconcile_ptm_localization_identity_lineage(build_m0502_request(case_id))
    assert lineage.disposition is expected_disposition
    request = _request_for_lineage(scenario, lineage)
    artifacts = _TraversalTrap()

    result = ingest_ptm_localization_raw_inputs(request, artifacts)
    assert request.artifacts == ()
    assert artifacts.traversals == 0
    assert result.validated_inputs == ()
    assert len(result.evidence) == M0503_MIN_EVIDENCE
    assert tuple(item.code for item in result.diagnostics) == (expected_code,)
    assert result.disposition.value == expected_disposition.value


def test_plugin_safe_failure_token_never_reads_artifact_mapping(scenario: Scenario) -> None:
    lineage = reconcile_ptm_localization_identity_lineage(
        build_m0502_request("upstream_identity_unresolved")
    )
    request = _request_for_lineage(scenario, lineage)
    artifacts = _TraversalTrap()
    plugin = M0503Plugin(M0503Service())

    token = plugin.validate(M0503Submission(request=request, artifacts_by_role=artifacts))
    result = plugin.run(token)
    assert artifacts.traversals == 0
    assert result.disposition is PtmLocalizationRawInputDisposition.ABSTAINED
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
        artifacts.pop(next(iter(PtmLocalizationRawInputRole)))
    elif mutation == "extra":
        artifacts["extra"] = b"{}"
    else:
        artifacts = {role.value: value for role, value in scenario.artifacts_by_role.items()}
    _assert_input_error(
        PtmLocalizationRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH,
        scenario.request,
        artifacts,
    )


@pytest.mark.parametrize("kind", ["bytearray", "bytes_subclass"])
def test_only_exact_immutable_bytes_are_accepted(scenario: Scenario, kind: str) -> None:
    class BytesSubclass(bytes):
        pass

    artifacts: dict[PtmLocalizationRawInputRole, object] = dict(scenario.artifacts_by_role)
    role = next(iter(PtmLocalizationRawInputRole))
    value = cast("bytes", artifacts[role])
    artifacts[role] = bytearray(value) if kind == "bytearray" else BytesSubclass(value)
    _assert_input_error(
        PtmLocalizationRawInputErrorCode.ARTIFACT_TYPE_INVALID,
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
        PtmLocalizationRawInputErrorCode.ARTIFACT_SIZE_MISMATCH,
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
        PtmLocalizationRawInputErrorCode.ARTIFACT_DIGEST_MISMATCH,
        request,
        artifacts,
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("invalid_json", PtmLocalizationRawInputErrorCode.DOCUMENT_JSON_INVALID),
        ("duplicate_json", PtmLocalizationRawInputErrorCode.DOCUMENT_JSON_INVALID),
        ("noncanonical", PtmLocalizationRawInputErrorCode.DOCUMENT_NOT_CANONICAL),
        ("wrong_type", PtmLocalizationRawInputErrorCode.DOCUMENT_TYPE_MISMATCH),
        ("unknown_field", PtmLocalizationRawInputErrorCode.DOCUMENT_JSON_INVALID),
    ],
)
def test_strict_document_boundary_reports_stable_structural_codes(
    scenario: Scenario,
    mutation: str,
    expected: PtmLocalizationRawInputErrorCode,
) -> None:
    artifacts = dict(scenario.artifacts_by_role)
    role = PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME
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
    role = PtmLocalizationRawInputRole.PTM_ANNOTATIONS
    decoded = cast("dict[str, object]", json.loads(scenario.artifacts_by_role[role]))
    model = type(
        next(
            item.document
            for item in ingest_ptm_localization_raw_inputs(
                scenario.request, scenario.artifacts_by_role
            ).validated_inputs
            if item.role is role
        )
    )

    missing_default = dict(decoded)
    del missing_default["document_version"]
    assert "document_version" not in m0503_engine._strict_document_python_value(
        model, missing_default
    )

    malformed = []
    wrong_enum = dict(decoded)
    wrong_enum["evidence_state"] = 1
    malformed.append(wrong_enum)
    wrong_collection = dict(decoded)
    wrong_collection["vocabularies"] = tuple(cast("list[object]", wrong_collection["vocabularies"]))
    malformed.append(wrong_collection)
    wrong_item = dict(decoded)
    wrong_item["vocabularies"] = [1]
    malformed.append(wrong_item)
    for candidate in malformed:
        with pytest.raises(PtmLocalizationRawInputError) as captured:
            m0503_engine._strict_document_python_value(model, candidate)
        assert captured.value.code is PtmLocalizationRawInputErrorCode.DOCUMENT_JSON_INVALID

    class StringTupleModel(BaseModel):
        items: tuple[str, ...]

    assert m0503_engine._strict_document_python_value(StringTupleModel, {"items": ["one"]}) == {
        "items": ("one",)
    }


def test_matching_parser_profile_cap_precedes_hash_and_json(scenario: Scenario) -> None:
    role = PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME
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
    with pytest.raises(ValidationError, match="matching parser cap"):
        IngestPtmLocalizationRawInputsRequest.model_validate(
            scenario.request.model_copy(update={"context": context, "policy": policy}).model_dump(
                mode="python", exclude_none=False
            ),
            strict=True,
        )


def test_maximum_semantic_discrepancy_is_typed_and_diagnostic_capped(
    scenario: Scenario,
) -> None:
    decoded = {
        role: cast("dict[str, Any]", json.loads(payload))
        for role, payload in scenario.artifacts_by_role.items()
    }
    roles = tuple(PtmLocalizationRawInputRole)
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
            "assay_specimen_policy_digest",
            "intended_use_evidence_digest",
        ):
            document[field] = stale_digest
        for field in (
            "assay_protocol_version",
            "specimen_processing_version",
            "unit_system_version",
            "reference_bundle_version",
        ):
            document[field] = "9.9.9"
        document["evidence_state"] = "missing"
        document["completeness_state"] = "incomplete"
        document["assay_support_state"] = "unsupported"
        document["parent_quality_state"] = "rejected"

    proteome = decoded[PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME]
    proteome.update(
        reference_digest=stale_digest,
        assay_kind="targeted_mass_spectrometry",
        support_domain="novel_ood",
        declared_units=["count"],
    )
    genome = decoded[PtmLocalizationRawInputRole.GENOME]
    genome.update(
        reference_digest=stale_digest,
        reference_build="input." + ("f" * 64),
    )
    transcriptome = decoded[PtmLocalizationRawInputRole.TRANSCRIPTOME]
    transcriptome.update(
        reference_digest=stale_digest,
        annotation_build="input." + ("e" * 64),
    )
    ptm = decoded[PtmLocalizationRawInputRole.PTM_ANNOTATIONS]
    ptm.update(
        reference_digest=stale_digest,
        vocabularies=[
            {
                "vocabulary_id": "vocabulary." + ("f" * 64),
                "version": "9.9.9",
            }
        ],
        vocabularies_digest=stale_digest,
    )
    artifacts_by_role = {role: canonical_json_bytes(document) for role, document in decoded.items()}
    rebound = _scenario_with_bytes(scenario, artifacts_by_role)
    request_payload = rebound.request.model_dump(mode="python", exclude_none=False)
    request_payload["artifacts"] = tuple(
        item.model_copy(update={"format_version": "9.9.9"}) for item in rebound.request.artifacts
    )
    request = IngestPtmLocalizationRawInputsRequest.model_validate(request_payload, strict=True)

    result = ingest_ptm_localization_raw_inputs(request, artifacts_by_role)
    diagnostic_keys = tuple((item.code, item.role) for item in result.diagnostics)
    assert result.disposition is PtmLocalizationRawInputDisposition.QUARANTINED
    assert len(result.validated_inputs) == len(PtmLocalizationRawInputRole)
    assert M0503_MIN_EVIDENCE < len(result.diagnostics) <= M0503_MAX_DIAGNOSTICS
    assert len(diagnostic_keys) == len(set(diagnostic_keys))


def test_plugin_snapshots_once_and_seals_private_preparation(scenario: Scenario) -> None:
    supplied = dict(scenario.artifacts_by_role)
    plugin = M0503Plugin(M0503Service())
    token = plugin.validate(M0503Submission(request=scenario.request, artifacts_by_role=supplied))
    expected = ingest_ptm_localization_raw_inputs(scenario.request, scenario.artifacts_by_role)
    for role in tuple(supplied):
        supplied[role] = b"corrupted after validation"

    assert plugin.run(token) == expected
    assert not hasattr(m05_03_raw_ingestion, "prepare_ptm_localization_raw_inputs")
    assert not hasattr(M0503Service, "execute_prepared")
    assert not hasattr(M0503PtmLocalizationRawInputIngester, "ingest_prepared")


def test_plugin_rejects_copied_forged_and_stale_nested_capabilities(
    scenario: Scenario,
) -> None:
    plugin = M0503Plugin(M0503Service())

    token = plugin.validate(
        M0503Submission(
            request=scenario.request,
            artifacts_by_role=scenario.artifacts_by_role,
        )
    )
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(copy.copy(token))
    forged_request = token.request.model_copy(
        update={"request_id": "request." + ("f" * 64)},
        deep=True,
    )
    forged = ValidatedM0503Request(
        request=forged_request,
        _prepared=token._prepared,
        _seal=token._seal,
    )
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)

    stale_document_token = plugin.validate(
        M0503Submission(
            request=scenario.request,
            artifacts_by_role=scenario.artifacts_by_role,
        )
    )
    stale_document = cast("Any", stale_document_token._prepared.documents[0])
    object.__setattr__(
        stale_document,
        "declared_record_count",
        stale_document.declared_record_count + 1,
    )
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(stale_document_token)

    stale_upstream_token = plugin.validate(
        M0503Submission(
            request=scenario.request,
            artifacts_by_role=scenario.artifacts_by_role,
        )
    )
    lineage = stale_upstream_token.request.lineage_result
    object.__setattr__(
        lineage,
        "support",
        lineage.support.model_copy(update={"rationale": "stale upstream mutation"}),
    )
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(stale_upstream_token)


def test_plugin_requires_submission_and_prepared_capability_is_nominal(scenario: Scenario) -> None:
    plugin = M0503Plugin(M0503Service())
    with pytest.raises(TypeError, match="raw-input submission"):
        plugin.validate(scenario.request)

    class PreparedSubclass(m0503_engine._PreparedPtmLocalizationRawInputs):
        pass

    prepared = m0503_engine._PreparedPtmLocalizationRawInputs(snapshots=(), documents=())
    with pytest.raises(TypeError, match="prepared input capability"):
        M0503PtmLocalizationRawInputIngester()._ingest_prepared(
            scenario.request,
            PreparedSubclass(prepared.snapshots, prepared.documents),
        )


def test_mapping_order_is_semantic_and_result_replay_rejects_forgery(scenario: Scenario) -> None:
    reversed_mapping = dict(reversed(tuple(scenario.artifacts_by_role.items())))
    result = ingest_ptm_localization_raw_inputs(scenario.request, scenario.artifacts_by_role)
    assert ingest_ptm_localization_raw_inputs(scenario.request, reversed_mapping) == result

    payload = result.model_dump(mode="python", exclude_none=False)
    cast("dict[str, object]", payload["support"])["rationale"] = "resigned local forgery"
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError):
        PtmLocalizationRawInputValidationResult.model_validate(payload, strict=True)


def test_plugin_rejects_duplicate_unknown_coercion_and_oversize_request(scenario: Scenario) -> None:
    plugin = M0503Plugin(M0503Service())
    rendered = scenario.request.model_dump_json()
    duplicate = rendered.replace(
        '"operation":"ingest_ptm_localization_raw_inputs"',
        (
            '"operation":"ingest_ptm_localization_raw_inputs","operation":"ingest_ptm_localization_raw_inputs"'
        ),
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
                M0503Submission(
                    request=candidate,
                    artifacts_by_role=scenario.artifacts_by_role,
                )
            )
