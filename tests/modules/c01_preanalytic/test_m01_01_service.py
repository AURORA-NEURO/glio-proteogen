"""Focused orchestration and plugin evidence for M01-01."""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m01_01.canonical import (
    canonical_request_digest,
    metadata_document_digest,
    protocol_digest,
)
from glio_proteogen.contracts.m01_01.schema import contract_json_schema
from glio_proteogen.contracts.m01_01.v1 import (
    ConformanceDecision,
    ConformanceProfile,
    EvaluateMetadataRequest,
    IssueAction,
    MetadataEntry,
    ProtocolSchemaReceipt,
    RegisterProtocolRequest,
    UnresolvedValue,
)
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlRole,
    IdentityLineageState,
    Limitation,
    SupportStatus,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.plugin import ModulePlugin
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata import (
    service as service_module,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.event_store import (
    ChainIntegrityError,
    EventRecord,
    EventType,
    IdempotencyConflictError,
    M0101EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.plugin import (
    M0101Plugin,
    ValidatedM0101Request,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.service import (
    ConsentAuthorizationError,
    M0101Service,
    ProtocolSchemaValidationError,
    UpstreamControlAuthorizationError,
)
from tests.m01_01_support import FIXTURE_DIRECTORY, load_request

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Literal

_EVIDENCE_COUNT = 7
_UNCERTAINTY_FIELD_COUNT = 8
_REGISTER_AND_EVALUATE_EVENT_COUNT = 2
_DECLARED_LIMITATION_CAP = 998
_OUTPUT_LIMITATION_CAP = 1_000


def _registration_request() -> RegisterProtocolRequest:
    request = load_request("register_minimal.valid.json")
    assert isinstance(request, RegisterProtocolRequest)
    return request


def _evaluation_request(filename: str, receipt: ProtocolSchemaReceipt) -> EvaluateMetadataRequest:
    request = load_request(filename)
    assert isinstance(request, EvaluateMetadataRequest)
    return request.model_copy(update={"protocol": receipt.protocol})


def _service(database: Path) -> M0101Service:
    return M0101Service(M0101EventStore(database))


def _with_context_reference(
    request: RegisterProtocolRequest | EvaluateMetadataRequest,
    role: str,
    reference: object,
) -> RegisterProtocolRequest | EvaluateMetadataRequest:
    references = request.context.references.model_copy(update={role: reference})
    context = request.context.model_copy(update={"references": references})
    return request.model_copy(update={"context": context})


def test_registration_builds_complete_deterministic_envelope(tmp_path: Path) -> None:
    database = tmp_path / "events.sqlite3"
    request = _registration_request()

    with _service(database) as service:
        receipt = service.register(request)
        replay = service.register(request)
        retrieved = service.get_protocol(
            request.protocol_schema.schema_id,
            request.protocol_schema.version,
        )
        chain = service.verify_event_chain()

    assert receipt == replay == retrieved
    assert receipt.receipt_version == "1.0.0"
    assert receipt.protocol.digest == protocol_digest(request.protocol_schema)
    assert receipt.support.status is SupportStatus.LIMITED
    assert receipt.provenance.generated_at == request.context.occurred_at
    assert receipt.provenance.configuration_digest == (
        request.context.references.approved_configuration.evidence.digest
    )
    assert tuple(decision.role for decision in receipt.provenance.control_decisions) == tuple(
        sorted(ControlRole, key=lambda role: role.value)
    )
    assert len(receipt.provenance.control_decisions) == _EVIDENCE_COUNT
    assert len(receipt.evidence) == _EVIDENCE_COUNT
    assert len(receipt.uncertainty.model_fields_set) == _UNCERTAINTY_FIELD_COUNT
    assert {limitation.code for limitation in receipt.limitations} >= {
        "external_controls_unverified",
        "metadata_conformance_only",
        "synthetic_only",
    }
    assert chain.valid is True
    assert chain.event_count == 1


def test_registration_replay_returns_before_rebuilding_the_output_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _registration_request()
    with _service(tmp_path / "registration-replay.sqlite3") as service:
        expected = service.register(request)

        def forbidden_envelope(*_args: object, **_kwargs: object) -> object:
            raise AssertionError

        monkeypatch.setattr(service_module, "_registration_support", forbidden_envelope)
        actual = service.register(request)
        chain = service.verify_event_chain()

    assert actual == expected
    assert chain.valid
    assert chain.event_count == 1


def test_semantically_unsafe_schema_fails_before_event_append(tmp_path: Path) -> None:
    database = tmp_path / "events.sqlite3"
    request = _registration_request()
    unsafe_field = request.protocol_schema.fields[0].model_copy(update={"pattern": "^SYN-.+$"})
    unsafe_schema = request.protocol_schema.model_copy(
        update={"fields": (unsafe_field, *request.protocol_schema.fields[1:])}
    )
    unsafe_request = request.model_copy(update={"protocol_schema": unsafe_schema})

    with _service(database) as service:
        with pytest.raises(ProtocolSchemaValidationError) as caught:
            service.register(unsafe_request)
        chain = service.verify_event_chain()

    assert {issue.code for issue in caught.value.issues} == {"schema.pattern_unsafe"}
    assert chain.valid is True
    assert chain.event_count == 0


def test_revoked_consent_fails_before_request_hash_or_event_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _registration_request()
    revoked = request.context.references.consent.model_copy(
        update={"state": ConsentState.REVOKED}
    )
    denied = _with_context_reference(request, "consent", revoked)
    assert isinstance(denied, RegisterProtocolRequest)
    hash_called = False

    def forbidden_digest(_request: object) -> str:
        nonlocal hash_called
        hash_called = True
        raise AssertionError

    monkeypatch.setattr(service_module, "canonical_request_digest", forbidden_digest)
    with _service(tmp_path / "events.sqlite3") as service:
        with pytest.raises(ConsentAuthorizationError) as caught:
            service.register(denied)
        chain = service.verify_event_chain()

    assert caught.value.state is ConsentState.REVOKED
    assert hash_called is False
    assert chain.valid is True
    assert chain.event_count == 0


@pytest.mark.parametrize(
    ("reference_name", "state", "expected_role"),
    [
        (
            "approved_configuration",
            UpstreamDecisionState.REJECTED,
            ControlRole.APPROVED_CONFIGURATION,
        ),
        ("provenance", UpstreamDecisionState.UNKNOWN, ControlRole.PROVENANCE),
        ("quality", UpstreamDecisionState.REJECTED, ControlRole.QUALITY),
        ("support", UpstreamDecisionState.UNKNOWN, ControlRole.SUPPORT),
        ("intended_use", UpstreamDecisionState.REJECTED, ControlRole.INTENDED_USE),
        (
            "identity_lineage",
            IdentityLineageState.UNRESOLVED,
            ControlRole.IDENTITY_LINEAGE,
        ),
        (
            "identity_lineage",
            IdentityLineageState.CONFLICTED,
            ControlRole.IDENTITY_LINEAGE,
        ),
    ],
)
def test_nonaccepted_control_fails_before_request_hash_or_event_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reference_name: str,
    state: UpstreamDecisionState | IdentityLineageState,
    expected_role: ControlRole,
) -> None:
    request = _registration_request()
    reference = getattr(request.context.references, reference_name)
    denied_reference = reference.model_copy(update={"state": state})
    denied = _with_context_reference(request, reference_name, denied_reference)
    assert isinstance(denied, RegisterProtocolRequest)
    hash_called = False

    def forbidden_digest(_request: object) -> str:
        nonlocal hash_called
        hash_called = True
        raise AssertionError

    monkeypatch.setattr(service_module, "canonical_request_digest", forbidden_digest)
    with _service(tmp_path / "events.sqlite3") as service:
        with pytest.raises(UpstreamControlAuthorizationError) as caught:
            service.register(denied)
        chain = service.verify_event_chain()

    assert caught.value.role is expected_role
    assert hash_called is False
    assert chain.valid is True
    assert chain.event_count == 0


@pytest.mark.parametrize("denial", ["revoked_consent", "rejected_quality"])
def test_evaluation_control_denial_fails_before_hash_without_appending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    denial: str,
) -> None:
    with _service(tmp_path / "events.sqlite3") as service:
        receipt = service.register(_registration_request())
        request = _evaluation_request("evaluate_conformant.valid.json", receipt)
        if denial == "revoked_consent":
            reference = request.context.references.consent.model_copy(
                update={"state": ConsentState.REVOKED}
            )
            denied = _with_context_reference(request, "consent", reference)
            expected_error = ConsentAuthorizationError
        else:
            reference = request.context.references.quality.model_copy(
                update={"state": UpstreamDecisionState.REJECTED}
            )
            denied = _with_context_reference(request, "quality", reference)
            expected_error = UpstreamControlAuthorizationError
        assert isinstance(denied, EvaluateMetadataRequest)
        hash_called = False

        def forbidden_digest(_request: object) -> str:
            nonlocal hash_called
            hash_called = True
            raise AssertionError

        monkeypatch.setattr(service_module, "canonical_request_digest", forbidden_digest)
        with pytest.raises(expected_error):
            service.evaluate(denied)
        chain = service.verify_event_chain()

    assert hash_called is False
    assert chain.valid is True
    assert chain.event_count == 1


def test_request_identifier_collision_is_typed_and_does_not_append(tmp_path: Path) -> None:
    database = tmp_path / "events.sqlite3"
    request = _registration_request()
    changed_schema = request.protocol_schema.model_copy(update={"title": "Changed synthetic title"})
    collision = request.model_copy(update={"protocol_schema": changed_schema})

    with _service(database) as service:
        service.register(request)
        with pytest.raises(IdempotencyConflictError):
            service.register(collision)
        chain = service.verify_event_chain()

    assert canonical_request_digest(request) != canonical_request_digest(collision)
    assert chain.valid is True
    assert chain.event_count == 1


@pytest.mark.parametrize(
    ("filename", "decision", "support", "review_expectation"),
    [
        (
            "evaluate_conformant.valid.json",
            ConformanceDecision.CONFORMANT,
            SupportStatus.LIMITED,
            "not_required",
        ),
        (
            "evaluate_quarantine.valid.json",
            ConformanceDecision.QUARANTINED,
            SupportStatus.REVIEW_REQUIRED,
            "required",
        ),
        (
            "evaluate_reject.valid.json",
            ConformanceDecision.NONCONFORMANT,
            SupportStatus.UNSUPPORTED,
            "required",
        ),
        (
            "evaluate_unresolved.valid.json",
            ConformanceDecision.QUARANTINED,
            SupportStatus.REVIEW_REQUIRED,
            "required",
        ),
    ],
)
def test_evaluation_maps_validation_to_typed_output(
    tmp_path: Path,
    filename: str,
    decision: ConformanceDecision,
    support: SupportStatus,
    review_expectation: Literal["required", "not_required"],
) -> None:
    database = tmp_path / "events.sqlite3"
    with _service(database) as service:
        receipt = service.register(_registration_request())
        request = _evaluation_request(filename, receipt)
        profile = service.evaluate(request)

    assert profile.profile_version == "1.0.0"
    assert profile.protocol == receipt.protocol
    assert profile.document_digest == metadata_document_digest(request.document)
    assert profile.decision is decision
    assert profile.support.status is support
    assert profile.evaluated_at == request.context.occurred_at
    assert profile.provenance.generated_at == request.context.occurred_at
    assert profile.human_review_required is (review_expectation == "required")
    assert len(profile.evidence) == _EVIDENCE_COUNT
    assert len(profile.uncertainty.model_fields_set) == _UNCERTAINTY_FIELD_COUNT


def test_identity_lineage_binding_mismatch_is_critically_quarantined(
    tmp_path: Path,
) -> None:
    mismatched_digest = f"sha256:{'0' * 64}"
    with _service(tmp_path / "events.sqlite3") as service:
        receipt = service.register(_registration_request())
        request = _evaluation_request("evaluate_conformant.valid.json", receipt)
        identity = request.context.references.identity_lineage.model_copy(
            update={"binding_digest": mismatched_digest}
        )
        mismatched = _with_context_reference(request, "identity_lineage", identity)
        assert isinstance(mismatched, EvaluateMetadataRequest)

        profile = service.evaluate(mismatched)
        chain = service.verify_event_chain()

    assert profile.decision is ConformanceDecision.QUARANTINED
    assert profile.support.status is SupportStatus.REVIEW_REQUIRED
    assert profile.human_review_required is True
    assert [
        (issue.code, issue.path, issue.severity.value, issue.action.value)
        for issue in profile.issues
    ] == [
        (
            "identity.lineage_binding_mismatch",
            "/entries",
            "critical",
            "quarantine",
        )
    ]
    identity_record = next(
        decision
        for decision in profile.provenance.control_decisions
        if decision.role is ControlRole.IDENTITY_LINEAGE
    )
    assert identity_record.subject_digest == mismatched_digest
    assert chain.valid is True
    assert chain.event_count == _REGISTER_AND_EVALUATE_EVENT_COUNT


def test_evaluation_replay_is_exact_and_event_omits_raw_metadata(tmp_path: Path) -> None:
    database = tmp_path / "events.sqlite3"
    with _service(database) as service:
        receipt = service.register(_registration_request())
        request = _evaluation_request("evaluate_conformant.valid.json", receipt)
        first = service.evaluate(request)
        replay = service.evaluate(request)
        chain = service.verify_event_chain()

    assert replay == first
    assert chain.valid is True
    assert chain.event_count == _REGISTER_AND_EVALUATE_EVENT_COUNT

    connection = sqlite3.connect(database)
    try:
        payload_text = connection.execute(
            "SELECT payload_json FROM m0101_events WHERE event_type = ?",
            ("metadata_evaluated",),
        ).fetchone()[0]
    finally:
        connection.close()
    payload = json.loads(payload_text)

    assert set(payload) == {
        "decision",
        "document_digest",
        "evaluated_at",
        "event_schema_version",
        "evidence",
        "human_review_required",
        "issues",
        "limitations",
        "output_type",
        "profile_version",
        "protocol",
        "provenance",
        "support",
        "uncertainty",
    }
    assert not {"document", "document_id", "entries", "values"} & set(payload)
    for submitted_value in ("SYN-001", "direct", "12.5", "BATCH-AA"):
        assert submitted_value not in payload_text


def test_unresolved_reason_is_not_returned_or_persisted(tmp_path: Path) -> None:
    database = tmp_path / "events.sqlite3"
    canary = "patient_jane_diagnosis"
    with _service(database) as service:
        receipt = service.register(_registration_request())
        request = _evaluation_request("evaluate_conformant.valid.json", receipt)
        entries = tuple(
            MetadataEntry(
                path=entry.path,
                values=(
                    UnresolvedValue(
                        state="unknown",
                        reason_code=canary,
                        explanation="Submitted detail must not cross the persistence boundary.",
                    ),
                ),
            )
            if entry.path == "/sample/key"
            else entry
            for entry in request.document.entries
        )
        unresolved = request.model_copy(
            update={"document": request.document.model_copy(update={"entries": entries})}
        )

        profile = service.evaluate(unresolved)

    connection = sqlite3.connect(database)
    try:
        payload_text = connection.execute(
            "SELECT payload_json FROM m0101_events WHERE event_type = ?",
            ("metadata_evaluated",),
        ).fetchone()[0]
    finally:
        connection.close()

    assert canary not in profile.model_dump_json()
    assert canary not in payload_text
    assert "value.unresolved_unknown" in {issue.code for issue in profile.issues}


def test_all_seven_control_decisions_persist_and_reconstruct_exactly(
    tmp_path: Path,
) -> None:
    database = tmp_path / "events.sqlite3"
    registration = _registration_request()
    with _service(database) as service:
        receipt = service.register(registration)
        evaluation = _evaluation_request("evaluate_conformant.valid.json", receipt)
        profile = service.evaluate(evaluation)

    with _service(database) as service:
        reconstructed_receipt = service.get_protocol(
            receipt.protocol.schema_id,
            receipt.protocol.version,
        )
        reconstructed_profile = service.evaluate(evaluation)
        chain = service.verify_event_chain()

    assert reconstructed_receipt == receipt
    assert reconstructed_profile == profile
    assert chain.valid is True
    assert chain.event_count == _REGISTER_AND_EVALUATE_EVENT_COUNT

    connection = sqlite3.connect(database)
    try:
        stored_payloads = [
            json.loads(row[0])
            for row in connection.execute(
                "SELECT payload_json FROM m0101_events ORDER BY sequence"
            ).fetchall()
        ]
    finally:
        connection.close()

    for payload, context in (
        (stored_payloads[0], registration.context),
        (stored_payloads[1], evaluation.context),
    ):
        provenance = payload["provenance"]
        decisions = provenance["control_decisions"]
        assert len(decisions) == _EVIDENCE_COUNT
        assert [decision["role"] for decision in decisions] == sorted(
            role.value for role in ControlRole
        )
        assert provenance["actor_id"] == context.actor_id
        assert provenance["consent_decision_id"] == context.references.consent.decision_id
        assert provenance["consent_state"] == ConsentState.GRANTED.value
        assert (
            provenance["consent_policy_version"]
            == context.references.consent.policy_version
        )
        assert (
            provenance["consent_evidence_digest"]
            == context.references.consent.evidence.digest
        )
        identity = next(
            decision
            for decision in decisions
            if decision["role"] == ControlRole.IDENTITY_LINEAGE.value
        )
        assert identity["subject_digest"] == (
            context.references.identity_lineage.binding_digest
        )
        assert all(
            decision["subject_digest"] is None
            for decision in decisions
            if decision["role"] != ControlRole.IDENTITY_LINEAGE.value
        )


def test_conformance_profile_rejects_forged_decision_support_and_review_envelopes(
    tmp_path: Path,
) -> None:
    with _service(tmp_path / "events.sqlite3") as service:
        receipt = service.register(_registration_request())
        profile = service.evaluate(
            _evaluation_request("evaluate_conformant.valid.json", receipt)
        )
    baseline = profile.model_dump(mode="json")
    for mutation, expected in (
        ({"decision": "nonconformant"}, "decision contradicts issue actions"),
        (
            {
                "support": {
                    **baseline["support"],
                    "status": "unsupported",
                    "reason_code": "metadata_nonconformant",
                }
            },
            "support decision contradicts conformance decision",
        ),
        ({"human_review_required": True}, "human-review flag contradicts issues"),
    ):
        forged = {**baseline, **mutation}
        with pytest.raises(ValidationError, match=expected):
            TypeAdapter(ConformanceProfile).validate_json(
                json.dumps(forged),
                strict=True,
            )


@pytest.mark.parametrize(
    ("reference_field", "forged_value"),
    [
        ("schema_id", "protocol.forged"),
        ("version", "1.0.1"),
        ("digest", f"sha256:{'0' * 64}"),
    ],
)
def test_protocol_receipt_rejects_forged_embedded_schema_reference(
    tmp_path: Path,
    reference_field: str,
    forged_value: str,
) -> None:
    with _service(tmp_path / "events.sqlite3") as service:
        receipt = service.register(_registration_request())
    payload = receipt.model_dump(mode="json")
    payload["protocol"][reference_field] = forged_value

    with pytest.raises(ValidationError, match="does not match its embedded schema"):
        TypeAdapter(ProtocolSchemaReceipt).validate_json(json.dumps(payload), strict=True)


def test_public_output_rejects_missing_or_duplicate_control_roles(tmp_path: Path) -> None:
    with _service(tmp_path / "events.sqlite3") as service:
        receipt = service.register(_registration_request())
    baseline = receipt.model_dump(mode="json")
    decisions = baseline["provenance"]["control_decisions"]
    missing = {
        **baseline,
        "provenance": {
            **baseline["provenance"],
            "control_decisions": decisions[:-1],
        },
    }
    duplicate = {
        **baseline,
        "provenance": {
            **baseline["provenance"],
            "control_decisions": [*decisions[:-1], decisions[0]],
        },
    }
    adapter = TypeAdapter(ProtocolSchemaReceipt)

    with pytest.raises(ValidationError, match="at least 7 items"):
        adapter.validate_json(json.dumps(missing), strict=True)
    with pytest.raises(
        ValidationError,
        match="provenance must record every upstream control role exactly once",
    ):
        adapter.validate_json(json.dumps(duplicate), strict=True)


def test_public_outputs_reject_duplicate_or_missing_mandatory_limitations(
    tmp_path: Path,
) -> None:
    with _service(tmp_path / "events.sqlite3") as service:
        receipt = service.register(_registration_request())
        profile = service.evaluate(
            _evaluation_request("evaluate_conformant.valid.json", receipt)
        )

    for output, adapter, contract_name in (
        (receipt, TypeAdapter(ProtocolSchemaReceipt), "protocol-receipt"),
        (profile, TypeAdapter(ConformanceProfile), "conformance-profile"),
    ):
        baseline = output.model_dump(mode="json")
        mandatory = next(
            limitation
            for limitation in baseline["limitations"]
            if limitation["code"] == "metadata_conformance_only"
        )
        duplicate = {
            **baseline,
            "limitations": [*baseline["limitations"], mandatory],
        }
        missing = {
            **baseline,
            "limitations": [
                limitation
                for limitation in baseline["limitations"]
                if limitation["code"] != "external_controls_unverified"
            ],
        }

        with pytest.raises(ValidationError, match="limitation codes must be unique"):
            adapter.validate_json(json.dumps(duplicate), strict=True)
        with pytest.raises(ValidationError, match="missing a mandatory M01-01 limitation"):
            adapter.validate_json(json.dumps(missing), strict=True)

        standard = Draft202012Validator(
            contract_json_schema(contract_name),
            format_checker=FormatChecker(),
        )
        assert not standard.is_valid(duplicate)
        assert not standard.is_valid(missing)


def test_plugin_covers_declared_human_review_decision(tmp_path: Path) -> None:
    registration = _registration_request()
    rule = registration.protocol_schema.compatibility_rules[0].model_copy(
        update={"on_failure": IssueAction.HUMAN_REVIEW}
    )
    schema = registration.protocol_schema.model_copy(update={"compatibility_rules": (rule,)})
    registration = registration.model_copy(update={"protocol_schema": schema})

    with _service(tmp_path / "events.sqlite3") as service:
        receipt = service.register(registration)
        request = _evaluation_request("evaluate_quarantine.valid.json", receipt)
        plugin = M0101Plugin(service)
        profile = plugin.run(plugin.validate(request))

    assert profile.output_type == "conformance_profile"
    assert profile.decision is ConformanceDecision.REVIEW_REQUIRED
    assert profile.support.status is SupportStatus.REVIEW_REQUIRED
    assert profile.human_review_required is True


def _event(event_type: EventType, payload: dict[str, object]) -> EventRecord:
    digest = f"sha256:{'1' * 64}"
    return EventRecord(
        sequence=1,
        event_type=event_type,
        request_id="request.synthetic.integrity",
        request_digest=digest,
        occurred_at="2026-01-01T00:00:00.000000Z",
        previous_digest=digest,
        event_digest=digest,
        payload=payload,
    )


def test_output_reconstruction_rejects_wrong_event_types_and_payloads() -> None:
    registration_event = _event(EventType.PROTOCOL_REGISTERED, {})
    evaluation_event = _event(EventType.METADATA_EVALUATED, {})

    with pytest.raises(ChainIntegrityError, match="wrong event type"):
        service_module._receipt_from_event(evaluation_event)
    with pytest.raises(ChainIntegrityError, match="registration event payload is invalid"):
        service_module._receipt_from_event(registration_event)
    with pytest.raises(ChainIntegrityError, match="wrong event type"):
        service_module._profile_from_event(registration_event)
    with pytest.raises(ChainIntegrityError, match="evaluation event payload is invalid"):
        service_module._profile_from_event(evaluation_event)


def test_receipt_projection_mismatch_is_rejected(tmp_path: Path) -> None:
    store = M0101EventStore(tmp_path / "events.sqlite3")
    service = M0101Service(store)
    try:
        receipt = service.register(_registration_request())
        stored = store.get_protocol(receipt.protocol.schema_id, receipt.protocol.version)
        bad_protocol = receipt.protocol.model_copy(update={"digest": f"sha256:{'2' * 64}"})
        bad_receipt = receipt.model_copy(update={"protocol": bad_protocol})

        with pytest.raises(ChainIntegrityError, match="does not match"):
            service_module._assert_receipt_matches_projection(bad_receipt, stored)
    finally:
        service.close()


def test_module_limitation_never_displaces_declared_limitations_at_output_cap() -> None:
    schema = _registration_request().protocol_schema.model_copy(
        update={
            "limitations": tuple(
                Limitation(code=f"limit{index}", statement=f"Declared limitation {index}.")
                for index in range(_DECLARED_LIMITATION_CAP)
            )
        }
    )

    limitations = service_module._limitations(schema)

    assert len(limitations) == _OUTPUT_LIMITATION_CAP
    limitation_codes = [limitation.code for limitation in limitations]
    assert len(limitation_codes) == len(set(limitation_codes))
    assert set(limitation_codes) == {
        *(f"limit{index}" for index in range(_DECLARED_LIMITATION_CAP)),
        "external_controls_unverified",
        "metadata_conformance_only",
    }


def test_limitation_capacity_defensively_rejects_shape_bypass() -> None:
    schema = _registration_request().protocol_schema.model_copy(
        update={
            "limitations": tuple(
                Limitation(code=f"limit{index}", statement=f"Declared limitation {index}.")
                for index in range(_OUTPUT_LIMITATION_CAP)
            )
        }
    )

    with pytest.raises(
        service_module.EventStoreError,
        match="leave no room for the module safety ceiling",
    ):
        service_module._limitations(schema)


def test_plugin_exposes_closed_validate_then_run_protocol(tmp_path: Path) -> None:
    request_bytes = (FIXTURE_DIRECTORY / "register_minimal.valid.json").read_bytes()

    with _service(tmp_path / "events.sqlite3") as service:
        plugin = M0101Plugin(service)
        validated = plugin.validate(request_bytes)
        output = plugin.run(validated)

    assert isinstance(plugin, ModulePlugin)
    assert isinstance(validated, ValidatedM0101Request)
    assert output.output_type == "protocol_schema"
    descriptor = plugin.descriptor()
    assert descriptor.module_id == "GLIO-PROTEOGEN-M01-01"
    assert descriptor.owner == "Scientific engineering"
    assert descriptor.safety_class == "S2"
    assert descriptor.gate == "G0"
    assert descriptor.prohibited_outputs == (
        "kinase state estimation",
        "generic all-omics fusion",
        "treatment recommendation",
    )


def test_plugin_strict_validation_rejects_unknown_input(tmp_path: Path) -> None:
    request = _registration_request().model_dump(mode="json")
    request["unexpected"] = True

    with _service(tmp_path / "events.sqlite3") as service:
        plugin = M0101Plugin(service)
        with pytest.raises(ValidationError):
            plugin.validate(request)
