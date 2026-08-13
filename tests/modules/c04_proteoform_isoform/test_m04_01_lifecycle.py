"""Focused lifecycle and fail-closed checks for M04-01."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import NoReturn

import pytest
from evals.m04_01.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m04_01 import (
    M0401_EVIDENCE_COUNT,
    M0401_LIMITATION_COUNT,
    M0401_MAX_CANONICAL_REQUEST_BYTES,
    M0401_SECTION_COUNT,
    EvaluateProteoformProtocolRequest,
    ProteoformApplicability,
    ProteoformProtocolConformanceDisposition,
    ProteoformProtocolConformanceResult,
    ProteoformProtocolConformanceStatus,
    configuration_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c04_proteoform_isoform.m04_01_protocol_metadata import (
    M0401Plugin,
    M0401ProteoformProtocolEngine,
    M0401Service,
    ProteoformProtocolAuthorizationError,
    evaluate_proteoform_protocol,
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


class _HostileAccessor:
    def __init__(self) -> None:
        object.__setattr__(self, "touches", 0)

    def __getattribute__(self, field: str) -> object:
        if field == "touches":
            return object.__getattribute__(self, field)
        touches = object.__getattribute__(self, "touches")
        assert isinstance(touches, int)
        object.__setattr__(self, "touches", touches + 1)
        raise _HostileTraversalError


class _PreflightBaseException(BaseException):
    """Sentinel proving BaseException is never swallowed."""


class _BaseExceptionDict(dict[str, object]):
    def get(self, key: str, default: object = None) -> object:
        del key, default
        raise _PreflightBaseException


def test_canonical_request_emits_one_closed_replayable_result() -> None:
    request = build_scenario_request()
    result = evaluate_proteoform_protocol(request)

    assert result.disposition is ProteoformProtocolConformanceDisposition.CONFORMANT
    assert result.status is ProteoformProtocolConformanceStatus.CONFORMANT
    assert result.result_digest != "sha256:" + ("0" * 64)
    assert len(result.findings) == M0401_SECTION_COUNT
    assert len(result.receipt.sections) == M0401_SECTION_COUNT
    assert len(result.evidence) == M0401_EVIDENCE_COUNT
    assert len(result.limitations) == M0401_LIMITATION_COUNT
    assert (
        ProteoformProtocolConformanceResult.model_validate_json(
            result.model_dump_json(),
            strict=True,
        )
        == result
    )


def test_library_engine_service_and_plugin_emit_exact_parity() -> None:
    request = build_scenario_request()
    direct = evaluate_proteoform_protocol(request)
    engine = M0401ProteoformProtocolEngine().evaluate(request)
    service = M0401Service().execute(request)
    plugin = M0401Plugin(M0401Service())
    token = plugin.validate(canonical_json_bytes(request))

    assert direct == engine == service == plugin.run(token)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M04-01"
    assert plugin.descriptor().owner == "ML engineering"
    assert (plugin.descriptor().safety_class, plugin.descriptor().gate) == ("S2", "G0")
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(request)  # type: ignore[arg-type]


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

    with pytest.raises(ProteoformProtocolAuthorizationError):
        evaluate_proteoform_protocol(payload)
    assert protocol.traversals == profile.traversals == 0


@pytest.mark.parametrize("position", ["request", "context", "references", "control"])
def test_arbitrary_mappings_and_accessors_are_denied_without_traversal(position: str) -> None:
    hostile = _HostileAccessor()
    if position == "request":
        candidate: object = _TraversalTrap()
    elif position == "context":
        candidate = {"context": hostile}
    elif position == "references":
        candidate = {"context": {"references": hostile}}
    else:
        candidate = {"context": {"references": {"consent": hostile}}}

    with pytest.raises(ProteoformProtocolAuthorizationError):
        evaluate_proteoform_protocol(candidate)
    if position != "request":
        assert hostile.touches == 0


def test_dict_subclass_uses_builtin_get_without_invoking_override() -> None:
    request = build_scenario_request()

    class HostileDict(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise _HostileTraversalError

    payload = request.model_dump(mode="python")
    payload["protocol_schema"] = HostileDict(payload["protocol_schema"])
    candidate = HostileDict(payload)
    result = evaluate_proteoform_protocol(candidate)
    assert result == evaluate_proteoform_protocol(request)
    assert M0401Service.validate_request(candidate) == request


def test_dict_overrides_are_ignored_but_base_exception_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = build_scenario_request().model_dump(mode="python")
    assert evaluate_proteoform_protocol(_BaseExceptionDict(request)) == (
        evaluate_proteoform_protocol(request)
    )

    def raise_base_exception(_candidate: object) -> None:
        raise _PreflightBaseException

    monkeypatch.setattr(
        "glio_proteogen.modules.c04_proteoform_isoform.m04_01_protocol_metadata.engine."
        "preflight_authorized",
        raise_base_exception,
    )
    with pytest.raises(_PreflightBaseException):
        evaluate_proteoform_protocol(request)


def test_semantic_set_reordering_has_full_result_equality() -> None:
    request = build_scenario_request()
    payload = request.model_dump(mode="json")
    paths = (
        ("protocol_schema", "required_identity_keys"),
        ("protocol_schema", "declared_unresolved_states"),
        ("protocol_schema", "evidence_eligibility", "eligible_evidence_classes"),
        ("protocol_schema", "isoform_discrimination", "accepted_discriminators"),
        ("protocol_schema", "modification_localization", "declared_states"),
        (
            "protocol_schema",
            "discordance_handoff",
            "required_receipt_roles",
        ),
        ("conformance_profile", "approved_evidence_classes"),
        ("conformance_profile", "approved_isoform_discriminators"),
    )
    for path in paths:
        cursor: object = payload
        for segment in path:
            assert isinstance(cursor, dict)
            cursor = cursor[segment]
        assert isinstance(cursor, list)
        cursor.reverse()
    reordered = EvaluateProteoformProtocolRequest.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )

    assert evaluate_proteoform_protocol(request) == evaluate_proteoform_protocol(reordered)


def test_reviewed_domain_mismatch_is_typed_quarantine() -> None:
    request = build_scenario_request()
    profile = request.conformance_profile.model_copy(
        update={"approved_applicabilities": (ProteoformApplicability.TOP_DOWN,)}
    )
    references = request.context.references

    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(request.protocol_schema, profile)}
            )
        }
    )
    context = request.context.model_copy(
        update={"references": references.model_copy(update={"approved_configuration": approved})}
    )
    changed = EvaluateProteoformProtocolRequest.model_validate(
        request.model_copy(update={"context": context, "conformance_profile": profile}).model_dump(
            mode="python"
        ),
        strict=True,
    )

    result = evaluate_proteoform_protocol(changed)
    assert result.disposition is ProteoformProtocolConformanceDisposition.QUARANTINED
    assert result.status is ProteoformProtocolConformanceStatus.NONCONFORMANT
    assert result.human_review_required
    assert {item.reason_code for item in result.findings if item.state.value == "fail"} == {
        "applicability_unapproved"
    }


def test_strict_plugin_json_rejects_duplicate_unknown_coercion_and_oversize() -> None:
    plugin = M0401Plugin(M0401Service())
    payload = build_scenario_request().model_dump_json()
    duplicate = payload.replace(
        '"operation":"evaluate_proteoform_protocol"',
        ('"operation":"evaluate_proteoform_protocol","operation":"evaluate_proteoform_protocol"'),
        1,
    )
    unknown = build_scenario_request().model_dump(mode="json")
    unknown["unexpected"] = True
    coercion = build_scenario_request().model_dump(mode="json")
    coercion["contract_version"] = 1
    malformed: tuple[object, ...] = (
        duplicate,
        canonical_json_bytes(unknown),
        canonical_json_bytes(coercion),
        b"{" + (b" " * M0401_MAX_CANONICAL_REQUEST_BYTES) + b"}",
    )
    for candidate in malformed:
        with pytest.raises((ValueError, ValidationError)):
            plugin.validate(candidate)


def test_result_recursively_preserves_parent_and_authority_ceiling() -> None:
    result = evaluate_proteoform_protocol(build_scenario_request())
    assert result.parent_target == "protein_rna_discordance"
    assert not any(
        (
            result.emits_protein_rna_discordance,
            result.emits_proteogenomic_state,
            result.emits_proteotype,
            result.emits_protein_level_subtype,
            result.infers_proteoform_or_isoform,
            result.localizes_modification,
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
