"""Focused lifecycle, replay, and fail-closed checks for M04-02."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import NoReturn

import pytest
from evals.m04_02.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m04_02 import (
    M0402_ARTIFACT_ROLE_COUNT,
    M0402_DERIVATION_COUNT,
    M0402_LIMITATION_COUNT,
    M0402_MAX_APPROVED_METHODS,
    M0402_MAX_ARTIFACT_CLAIMS,
    M0402_MAX_CANONICAL_REQUEST_BYTES,
    M0402_MAX_DERIVATION_SOURCES,
    M0402_MAX_EVIDENCE,
    M0402_MIN_EVIDENCE,
    M0402_PHYSICAL_ENTITY_KIND_COUNT,
    ProteoformIdentityLineageResolution,
    ProteoformLineageDisposition,
    ReconcileProteoformIdentityLineageRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage import (
    M0402Plugin,
    M0402ProteoformIdentityLineageReconciler,
    M0402Service,
    ProteoformIdentityLineageAuthorizationError,
    reconcile_proteoform_identity_lineage,
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


def test_genuine_chain_emits_one_closed_replayable_result() -> None:
    request = build_scenario_request()
    result = reconcile_proteoform_identity_lineage(request)

    assert result.disposition is ProteoformLineageDisposition.RECONCILED
    assert result.result_digest != "sha256:" + ("0" * 64)
    assert len(request.identity_resolution.graph.nodes) == M0402_PHYSICAL_ENTITY_KIND_COUNT
    assert len(result.graph.artifacts) == M0402_ARTIFACT_ROLE_COUNT
    assert len(result.graph.derivations) == M0402_DERIVATION_COUNT
    assert result.findings == ()
    assert len(result.evidence) == M0402_MIN_EVIDENCE
    assert len(result.limitations) == M0402_LIMITATION_COUNT
    assert result.receipt.receipt_digest != "sha256:" + ("0" * 64)
    assert (
        ProteoformIdentityLineageResolution.model_validate_json(
            result.model_dump_json(),
            strict=True,
        )
        == result
    )


def test_library_engine_service_and_plugin_emit_exact_parity() -> None:
    request = build_scenario_request()
    direct = reconcile_proteoform_identity_lineage(request)
    engine = M0402ProteoformIdentityLineageReconciler().reconcile(request)
    service = M0402Service().execute(request)
    plugin = M0402Plugin(M0402Service())
    token = plugin.validate(canonical_json_bytes(request))

    assert direct == engine == service == plugin.run(token)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M04-02"
    assert plugin.descriptor().owner == "Quality engineering"
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
def test_each_denied_control_precedes_all_governed_traversal(
    control: str,
    denied_state: str,
) -> None:
    payload = build_scenario_request().model_dump(mode="python")
    payload["context"]["references"][control]["state"] = denied_state
    traps = tuple(_TraversalTrap() for _ in range(5))
    for field, trap in zip(
        ("identity_resolution", "protocol_result", "policy", "artifact_claims", "derivations"),
        traps,
        strict=True,
    ):
        payload[field] = trap

    with pytest.raises(ProteoformIdentityLineageAuthorizationError):
        reconcile_proteoform_identity_lineage(payload)
    assert all(trap.traversals == 0 for trap in traps)


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

    with pytest.raises(ProteoformIdentityLineageAuthorizationError):
        reconcile_proteoform_identity_lineage(candidate)
    if position != "request":
        assert hostile.touches == 0


def test_dict_subclass_firewall_and_service_materialization() -> None:
    class HostileDict(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise _HostileTraversalError

        def items(self) -> NoReturn:
            raise _HostileTraversalError

        def __iter__(self) -> Iterator[str]:
            raise _HostileTraversalError

    request = build_scenario_request()
    payload = request.model_dump(mode="python")
    payload["policy"] = HostileDict(payload["policy"])
    candidate = HostileDict(payload)

    assert reconcile_proteoform_identity_lineage(candidate) == (
        reconcile_proteoform_identity_lineage(request)
    )
    assert M0402Service.validate_request(candidate) == request

    constructed = ReconcileProteoformIdentityLineageRequest.model_construct(
        **{
            **request.__dict__,
            "policy": HostileDict(request.policy.model_dump(mode="python")),
        }
    )
    assert reconcile_proteoform_identity_lineage(constructed) == (
        reconcile_proteoform_identity_lineage(request)
    )
    assert M0402Service.validate_request(constructed) == request


def test_exception_fails_closed_and_baseexception_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = "glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage.engine"

    def raise_exception(_candidate: object, _field: str) -> NoReturn:
        raise RuntimeError

    monkeypatch.setattr(f"{module}._member", raise_exception)
    with pytest.raises(ProteoformIdentityLineageAuthorizationError):
        reconcile_proteoform_identity_lineage(build_scenario_request())

    def raise_base_exception(_candidate: object, _field: str) -> NoReturn:
        raise _PreflightBaseException

    monkeypatch.setattr(f"{module}._member", raise_base_exception)
    with pytest.raises(_PreflightBaseException):
        reconcile_proteoform_identity_lineage(build_scenario_request())


@pytest.mark.parametrize(
    "case_id",
    [
        "missing_abstains",
        "indeterminate_abstains",
        "unsupported_abstains",
        "redacted_abstains",
    ],
)
def test_nonobserved_evidence_is_typed_abstention(case_id: str) -> None:
    result = reconcile_proteoform_identity_lineage(build_scenario_request(case_id))
    assert result.disposition is ProteoformLineageDisposition.ABSTAINED
    assert result.human_review_required
    assert len(result.graph.artifacts) == M0402_ARTIFACT_ROLE_COUNT
    assert {finding.code.value for finding in result.findings} == {
        "artifact_evidence_not_evaluable"
    }


def test_genuine_unresolved_identity_is_typed_abstention() -> None:
    request = build_scenario_request("valid_unresolved_identity_abstains")
    result = reconcile_proteoform_identity_lineage(request)

    assert request.identity_resolution.decision.value == "unresolved"
    assert result.disposition is ProteoformLineageDisposition.ABSTAINED
    assert {finding.code.value for finding in result.findings} == {"upstream_identity_unresolved"}
    assert result.graph.identity_resolution_digest == request.identity_resolution.resolution_digest


def test_genuine_quarantined_protocol_is_typed_quarantine() -> None:
    request = build_scenario_request("valid_quarantined_m0401_quarantines")
    result = reconcile_proteoform_identity_lineage(request)

    assert request.protocol_result.disposition.value == "quarantined"
    assert result.disposition is ProteoformLineageDisposition.QUARANTINED
    assert result.human_review_required
    assert {finding.code.value for finding in result.findings} == {
        "upstream_protocol_nonconformant"
    }
    assert result.receipt.protocol_result_digest == request.protocol_result.result_digest


@pytest.mark.parametrize(
    ("case_id", "disposition", "codes"),
    [
        (
            "specimen_subject_swap",
            ProteoformLineageDisposition.QUARANTINED,
            {"identity_swap"},
        ),
        (
            "same_binding_scope_collision",
            ProteoformLineageDisposition.QUARANTINED,
            {"binding_scope_collision"},
        ),
        (
            "producer_identity_and_protocol_drift",
            ProteoformLineageDisposition.QUARANTINED,
            {"producer_identity_drift", "producer_protocol_drift"},
        ),
        (
            "physical_cross_patient_link",
            ProteoformLineageDisposition.QUARANTINED,
            {"artifact_lineage_collision", "cross_patient_link", "identity_swap"},
        ),
        (
            "duplicate_content_different_scope_retained",
            ProteoformLineageDisposition.RECONCILED,
            {"duplicate_content_retained"},
        ),
    ],
)
def test_discrepancy_matrix_is_typed_and_nonmutating(
    case_id: str,
    disposition: ProteoformLineageDisposition,
    codes: set[str],
) -> None:
    request = build_scenario_request(case_id)
    result = reconcile_proteoform_identity_lineage(request)

    assert result.disposition is disposition
    assert {finding.code.value for finding in result.findings} == codes
    assert {item.claim_id for item in result.graph.artifacts} == {
        item.claim_id for item in request.artifact_claims
    }
    assert tuple(sorted(item.artifact_digest for item in result.graph.artifacts)) == tuple(
        sorted(item.artifact.digest for item in request.artifact_claims)
    )


def test_semantic_set_reordering_has_full_result_equality() -> None:
    request = build_scenario_request("semantic_reorder_full_result_equality")
    payload = request.model_dump(mode="json")
    payload["policy"]["approved_derivation_methods"].reverse()
    payload["artifact_claims"].reverse()
    payload["derivations"][0]["source_claim_ids"].reverse()
    reordered = ReconcileProteoformIdentityLineageRequest.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )

    assert reconcile_proteoform_identity_lineage(request) == (
        reconcile_proteoform_identity_lineage(reordered)
    )


def test_strict_plugin_json_rejects_duplicate_unknown_coercion_and_oversize() -> None:
    plugin = M0402Plugin(M0402Service())
    request = build_scenario_request()
    rendered = request.model_dump_json()
    duplicate = rendered.replace(
        '"operation":"reconcile_proteoform_identity_lineage"',
        (
            '"operation":"reconcile_proteoform_identity_lineage",'
            '"operation":"reconcile_proteoform_identity_lineage"'
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
        b"{" + (b" " * M0402_MAX_CANONICAL_REQUEST_BYTES) + b"}",
    )
    for candidate in malformed:
        with pytest.raises((ValueError, ValidationError)):
            plugin.validate(candidate)


def test_upstream_and_result_forgery_are_rejected() -> None:
    request_payload = build_scenario_request().model_dump(mode="json")
    request_payload["protocol_result"]["result_digest"] = "sha256:" + ("f" * 64)
    with pytest.raises(ValidationError):
        ReconcileProteoformIdentityLineageRequest.model_validate_json(
            canonical_json_bytes(request_payload),
            strict=True,
        )

    result = reconcile_proteoform_identity_lineage(build_scenario_request())
    result_payload = result.model_dump(mode="json")
    result_payload["receipt"]["graph_digest"] = "sha256:" + ("e" * 64)
    with pytest.raises(ValidationError):
        ProteoformIdentityLineageResolution.model_validate_json(
            canonical_json_bytes(result_payload),
            strict=True,
        )


def test_maximum_policy_shape_and_recursive_authority_ceiling() -> None:
    request = build_scenario_request("maximum_shape_accepted")
    result = reconcile_proteoform_identity_lineage(request)
    assert len(request.policy.approved_derivation_methods) == M0402_MAX_APPROVED_METHODS
    assert len(request.artifact_claims) == M0402_MAX_ARTIFACT_CLAIMS
    assert len(request.derivations[0].source_claim_ids) == M0402_MAX_DERIVATION_SOURCES
    assert len(result.evidence) == M0402_MAX_EVIDENCE
    assert result.disposition is ProteoformLineageDisposition.QUARANTINED
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
        )
    )
    rendered = result.model_dump_json()
    for canary in (
        "patient-raw-001",
        "MPEPTIDEK",
        "P12345",
        "ENSP00000354587",
        "chr7:140453136:A:T",
        "EGFRvIII",
    ):
        assert canary not in rendered


def test_first_claim_above_installed_maximum_is_rejected() -> None:
    request = build_scenario_request("maximum_shape_accepted")
    template = request.artifact_claims[0]
    extra = template.model_copy(
        update={
            "claim_id": "claim." + ("f" * 64),
            "artifact": template.artifact.model_copy(
                update={
                    "artifact_id": "evidence." + ("e" * 64),
                    "digest": "sha256:" + ("d" * 64),
                }
            ),
        }
    )
    oversized = request.model_copy(update={"artifact_claims": (*request.artifact_claims, extra)})

    with pytest.raises(ValidationError):
        ReconcileProteoformIdentityLineageRequest.model_validate(oversized, strict=True)
