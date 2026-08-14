"""Focused lifecycle, replay, and fail-closed checks for M05-01."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import NoReturn

import pytest
from evals.m05_01.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m05_01 import (
    M0501_EVIDENCE_COUNT,
    M0501_LIMITATION_COUNT,
    M0501_MAX_CANONICAL_REQUEST_BYTES,
    M0501_SECTION_COUNT,
    EvaluatePtmLocalizationProtocolRequest,
    PtmLocalizationProtocolConformanceDisposition,
    PtmLocalizationProtocolConformanceResult,
    PtmLocalizationProtocolConformanceStatus,
    configuration_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization.m05_01_protocol_metadata import (
    M0501Plugin,
    M0501PtmLocalizationProtocolEngine,
    M0501Service,
    PtmLocalizationProtocolAuthorizationError,
    ValidatedM0501Request,
    evaluate_ptm_localization_protocol,
)


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


class _PreflightBaseException(BaseException):
    """Sentinel proving BaseException is never swallowed."""


@pytest.mark.contract
def test_canonical_request_emits_one_closed_replayable_result() -> None:
    request = build_scenario_request()
    result = evaluate_ptm_localization_protocol(request)

    assert result.disposition is PtmLocalizationProtocolConformanceDisposition.CONFORMANT
    assert result.status is PtmLocalizationProtocolConformanceStatus.CONFORMANT
    assert result.result_digest != "sha256:" + ("0" * 64)
    assert len(result.findings) == len(result.receipt.sections) == M0501_SECTION_COUNT
    assert len(result.evidence) == M0501_EVIDENCE_COUNT
    assert len(result.limitations) == M0501_LIMITATION_COUNT
    assert (
        PtmLocalizationProtocolConformanceResult.model_validate_json(
            result.model_dump_json(),
            strict=True,
        )
        == result
    )


@pytest.mark.parametrize(
    ("scenario", "status", "disposition"),
    [
        (
            "canonical_conformant",
            PtmLocalizationProtocolConformanceStatus.CONFORMANT,
            PtmLocalizationProtocolConformanceDisposition.CONFORMANT,
        ),
        (
            "maximum_profile_shape_conforms",
            PtmLocalizationProtocolConformanceStatus.CONFORMANT,
            PtmLocalizationProtocolConformanceDisposition.CONFORMANT,
        ),
        (
            "unsupported_ood_abstains",
            PtmLocalizationProtocolConformanceStatus.INDETERMINATE,
            PtmLocalizationProtocolConformanceDisposition.ABSTAINED,
        ),
        (
            "unsupported_version_abstains",
            PtmLocalizationProtocolConformanceStatus.INDETERMINATE,
            PtmLocalizationProtocolConformanceDisposition.ABSTAINED,
        ),
        (
            "unit_incompatibility_quarantined",
            PtmLocalizationProtocolConformanceStatus.NONCONFORMANT,
            PtmLocalizationProtocolConformanceDisposition.QUARANTINED,
        ),
        (
            "metadata_incomplete_quarantined",
            PtmLocalizationProtocolConformanceStatus.NONCONFORMANT,
            PtmLocalizationProtocolConformanceDisposition.QUARANTINED,
        ),
        (
            "compatibility_failure_quarantined",
            PtmLocalizationProtocolConformanceStatus.NONCONFORMANT,
            PtmLocalizationProtocolConformanceDisposition.QUARANTINED,
        ),
        (
            "unresolved_semantics_quarantined",
            PtmLocalizationProtocolConformanceStatus.NONCONFORMANT,
            PtmLocalizationProtocolConformanceDisposition.QUARANTINED,
        ),
        (
            "identity_incomplete_quarantined",
            PtmLocalizationProtocolConformanceStatus.NONCONFORMANT,
            PtmLocalizationProtocolConformanceDisposition.QUARANTINED,
        ),
    ],
)
def test_supported_failure_and_unsupported_abstention_are_distinct(
    scenario: str,
    status: PtmLocalizationProtocolConformanceStatus,
    disposition: PtmLocalizationProtocolConformanceDisposition,
) -> None:
    result = evaluate_ptm_localization_protocol(build_scenario_request(scenario))
    assert (result.status, result.disposition) == (status, disposition)
    assert result.human_review_required is (
        disposition is not PtmLocalizationProtocolConformanceDisposition.CONFORMANT
    )
    if disposition is PtmLocalizationProtocolConformanceDisposition.ABSTAINED:
        assert result.support.status.value == "unsupported"
        assert {finding.state.value for finding in result.findings} == {"indeterminate"}


def test_library_engine_service_and_plugin_emit_exact_parity() -> None:
    request = build_scenario_request()
    direct = evaluate_ptm_localization_protocol(request)
    engine = M0501PtmLocalizationProtocolEngine().evaluate(request)
    service = M0501Service()
    plugin = M0501Plugin(service)
    token = plugin.validate(canonical_json_bytes(request))

    assert direct == engine == service.execute(request) == plugin.run(token)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M05-01"
    assert plugin.descriptor().owner == "Quality engineering"
    assert (plugin.descriptor().safety_class, plugin.descriptor().gate) == ("S2", "G0")
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(request)  # type: ignore[arg-type]


def test_copied_seal_and_copied_request_cannot_forge_plugin_token() -> None:
    plugin = M0501Plugin(M0501Service())
    token = plugin.validate(build_scenario_request())
    copied_request = token.request.model_copy(deep=True)
    forged = ValidatedM0501Request(request=copied_request, _seal=token._seal)

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)


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
def test_each_denied_control_precedes_protocol_and_profile_traversal(
    control: str,
    denied_state: str,
) -> None:
    payload = build_scenario_request().model_dump(mode="python")
    payload["context"]["references"][control]["state"] = denied_state
    protocol = _TraversalTrap()
    profile = _TraversalTrap()
    payload["protocol_schema"] = protocol
    payload["conformance_profile"] = profile

    with pytest.raises(PtmLocalizationProtocolAuthorizationError):
        evaluate_ptm_localization_protocol(payload)
    assert protocol.traversals == profile.traversals == 0


def test_hostile_mapping_is_denied_and_base_exception_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trap = _TraversalTrap()
    with pytest.raises(PtmLocalizationProtocolAuthorizationError):
        evaluate_ptm_localization_protocol(trap)
    assert trap.traversals == 0

    def raise_base_exception(_candidate: object) -> None:
        raise _PreflightBaseException

    monkeypatch.setattr(
        "glio_proteogen.modules.c05_ptm_localization.m05_01_protocol_metadata.engine."
        "preflight_authorized",
        raise_base_exception,
    )
    with pytest.raises(_PreflightBaseException):
        evaluate_ptm_localization_protocol(build_scenario_request())


def test_dict_subclass_overrides_are_not_invoked() -> None:
    class HostileDict(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise _HostileTraversalError

    request = build_scenario_request()
    payload = request.model_dump(mode="python")
    payload["protocol_schema"] = HostileDict(payload["protocol_schema"])
    candidate = HostileDict(payload)
    assert evaluate_ptm_localization_protocol(candidate) == (
        evaluate_ptm_localization_protocol(request)
    )


def test_semantic_reordering_has_full_result_equality() -> None:
    request = build_scenario_request()
    payload = request.model_dump(mode="json")
    for path in (
        ("protocol_schema", "required_identity_keys"),
        ("protocol_schema", "unresolved_rules"),
        ("protocol_schema", "controlled_vocabularies"),
        ("protocol_schema", "unit_policies"),
        ("protocol_schema", "metadata_fields"),
        ("protocol_schema", "compatibility_rules"),
        ("conformance_profile", "approved_protocol_versions"),
    ):
        cursor: object = payload
        for segment in path:
            assert isinstance(cursor, dict)
            cursor = cursor[segment]
        assert isinstance(cursor, list)
        cursor.reverse()
    reordered = EvaluatePtmLocalizationProtocolRequest.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )
    assert evaluate_ptm_localization_protocol(request) == (
        evaluate_ptm_localization_protocol(reordered)
    )


def test_strict_json_rejects_duplicate_unknown_coercion_and_oversize() -> None:
    plugin = M0501Plugin(M0501Service())
    request = build_scenario_request()
    payload = request.model_dump_json()
    duplicate = payload.replace(
        '"operation":"evaluate_ptm_localization_protocol"',
        (
            '"operation":"evaluate_ptm_localization_protocol",'
            '"operation":"evaluate_ptm_localization_protocol"'
        ),
        1,
    )
    unknown = request.model_dump(mode="json")
    unknown["unexpected"] = True
    coercion = request.model_dump(mode="json")
    coercion["contract_version"] = 1
    malformed: tuple[object, ...] = (
        duplicate,
        canonical_json_bytes(unknown),
        canonical_json_bytes(coercion),
        b"{" + (b" " * M0501_MAX_CANONICAL_REQUEST_BYTES) + b"}",
    )
    for candidate in malformed:
        with pytest.raises((ValueError, ValidationError)):
            plugin.validate(candidate)


@pytest.mark.parametrize(
    "field",
    [
        "result_id",
        "request_digest",
        "protocol_digest",
        "profile_digest",
        "configuration_digest",
        "status",
        "disposition",
        "support",
        "uncertainty",
        "provenance",
        "evidence",
        "limitations",
        "completed_at",
    ],
)
def test_resigned_result_derived_region_forgery_is_rejected(field: str) -> None:
    result = evaluate_ptm_localization_protocol(build_scenario_request())
    payload = result.model_dump(mode="python")
    mutations: dict[str, object] = {
        "result_id": "result.m0501." + ("f" * 64),
        "request_digest": "sha256:" + ("f" * 64),
        "protocol_digest": "sha256:" + ("f" * 64),
        "profile_digest": "sha256:" + ("f" * 64),
        "configuration_digest": "sha256:" + ("f" * 64),
        "status": "indeterminate",
        "disposition": "abstained",
        "support": {**payload["support"], "reason_code": "forged"},
        "uncertainty": {
            **payload["uncertainty"],
            "sensitivity_notes": ("forged",),
        },
        "provenance": {
            **payload["provenance"],
            "input_digests": ("sha256:" + ("f" * 64),),
        },
        "evidence": tuple(reversed(payload["evidence"]))[:-1],
        "limitations": tuple(reversed(payload["limitations"]))[:-1],
        "completed_at": "2026-01-15T12:00:01Z",
    }
    payload[field] = mutations[field]
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError):
        PtmLocalizationProtocolConformanceResult.model_validate(payload, strict=True)


def test_stale_configuration_and_evidence_alias_canary_are_rejected() -> None:
    request = build_scenario_request()
    payload = request.model_dump(mode="python")
    payload["context"]["references"]["approved_configuration"]["evidence"]["digest"] = "sha256:" + (
        "f" * 64
    )
    with pytest.raises(ValidationError):
        EvaluatePtmLocalizationProtocolRequest.model_validate(payload, strict=True)

    canary = request.model_dump(mode="python")
    reference = canary["protocol_schema"]["reference_bundle"]["references"][0]["reference"]
    reference["artifact_id"] = "evidence." + ("a" * 64)
    with pytest.raises(ValidationError):
        EvaluatePtmLocalizationProtocolRequest.model_validate(canary, strict=True)


def test_result_preserves_parent_and_exact_authority_ceiling() -> None:
    result = evaluate_ptm_localization_protocol(build_scenario_request())
    assert result.parent_target == "variant_peptide"
    assert not any(
        (
            result.emits_variant_peptide,
            result.emits_proteogenomic_state,
            result.emits_proteotype,
            result.emits_protein_level_subtype,
            result.localizes_ptm,
            result.infers_kinase_activity,
            result.performs_all_omics_fusion,
            result.recommends_treatment,
            result.mutates_upstream_evidence,
            result.infers_identity_or_consent,
        )
    )
    rendered = result.model_dump_json()
    for canary in (
        "MPEPTIDEK",
        "P12345",
        "ENSP00000354587",
        "chr7:140453136:A:T",
        "EGFRvIII",
        "patient-raw-001",
    ):
        assert canary not in rendered


def test_superseding_recovery_is_append_only_and_provenance_bound() -> None:
    request = build_scenario_request("superseding_recovery_conforms")
    result = evaluate_ptm_localization_protocol(request)
    assert request.supersedes_result_digest in result.provenance.input_digests
    assert result.disposition is PtmLocalizationProtocolConformanceDisposition.CONFORMANT
    assert result.configuration_digest == configuration_digest(
        request.protocol_schema, request.conformance_profile
    )
