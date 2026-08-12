"""API/CLI parity and hostile transport checks for M01-02."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Self

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from typer.testing import CliRunner

from glio_proteogen.adapters import cli as cli_module
from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.adapters.limits import MAX_REQUEST_BYTES
from glio_proteogen.contracts.m01_02 import v1 as m0102_contract
from glio_proteogen.contracts.m01_02.canonical import policy_digest
from glio_proteogen.contracts.m01_02.v1 import (
    EntityComposition,
    EntityKind,
    IdentityAuthorityReference,
    IdentityEntity,
    IdentityExecutionContext,
    IdentityLineageResolution,
    IdentityReconciliationReferences,
    IdentityResolutionPolicy,
    LineageOperation,
    LineageOperationKind,
    ReconcileIdentityLineageRequest,
    SubjectMembershipAssertion,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import MAX_VALIDATION_ERRORS
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.event_store import (
    ChainVerification as M0101ChainVerification,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.service import (
    M0101Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    ChainVerification,
    M0102EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    EventStoreError as M0102EventStoreError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    IdempotencyConflictError as M0102IdempotencyConflictError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    PayloadTooLargeError as M0102PayloadTooLargeError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.plugin import (
    M0102Plugin,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import (
    IdentityLineageAuthorizationError,
    M0102Service,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

SHA_A = "sha256:" + ("a" * 64)
POLICY_VERSION = "1.0.0"
AUTHORITY_ID = "authority.interfaces"
HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_FORBIDDEN = 403
HTTP_PAYLOAD_TOO_LARGE = 413
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_UNPROCESSABLE_CONTENT = 422
CLI_INVALID_INPUT = 2
CONFLICT_DETAIL = "synthetic request conflict"
PAYLOAD_LIMIT_DETAIL = "synthetic persisted payload limit"
PRIVATE_FILESYSTEM_DETAIL = "private filesystem detail"


class _PolicyHashBeforeAuthorizationError(AssertionError):
    pass


def _artifact(name: str, digest: str = SHA_A) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version=POLICY_VERSION,
        digest=digest,
        media_type="application/vnd.aurora.synthetic+json",
    )


def _request() -> ReconcileIdentityLineageRequest:
    policy = IdentityResolutionPolicy(
        policy_id="identity.policy.interfaces",
        version=POLICY_VERSION,
        max_component_size=32,
        maximum_depth=16,
        allow_mixed_subject_pooling=False,
        require_demultiplex_authority=True,
        allowed_operation_kinds=tuple(LineageOperationKind),
    )
    accepted = UpstreamDecisionReference(
        decision_id="control.interfaces",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version=POLICY_VERSION,
        evidence=_artifact("control.interfaces.evidence"),
    )
    context = IdentityExecutionContext(
        request_id="request.interfaces",
        actor_id="actor.interfaces",
        occurred_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
        references=IdentityReconciliationReferences(
            approved_configuration=accepted.model_copy(
                update={"evidence": _artifact("policy.interfaces", policy_digest(policy))}
            ),
            identity_authority=IdentityAuthorityReference(
                decision_id=AUTHORITY_ID,
                state=UpstreamDecisionState.ACCEPTED,
                policy_version=POLICY_VERSION,
                evidence=_artifact("authority.interfaces.evidence"),
            ),
            provenance=accepted.model_copy(update={"decision_id": "provenance.interfaces"}),
            consent=ConsentReference(
                decision_id="consent.interfaces",
                state=ConsentState.GRANTED,
                policy_version=POLICY_VERSION,
                evidence=_artifact("consent.interfaces.evidence"),
            ),
            quality=accepted.model_copy(update={"decision_id": "quality.interfaces"}),
            support=accepted.model_copy(update={"decision_id": "support.interfaces"}),
            intended_use=accepted.model_copy(update={"decision_id": "use.interfaces"}),
        ),
    )
    patient = IdentityEntity(
        entity_id="patient.interfaces",
        kind=EntityKind.PATIENT,
        composition=EntityComposition.SINGLE_SUBJECT,
        evidence=(_artifact("patient.interfaces.evidence"),),
    )
    specimen = IdentityEntity(
        entity_id="specimen.interfaces",
        kind=EntityKind.SPECIMEN,
        composition=EntityComposition.SINGLE_SUBJECT,
        evidence=(_artifact("specimen.interfaces.evidence"),),
    )
    membership = SubjectMembershipAssertion(
        assertion_id="membership.interfaces",
        entity_id=specimen.entity_id,
        subject_entity_id=patient.entity_id,
        authority_decision_id=AUTHORITY_ID,
        policy_version=POLICY_VERSION,
        evidence=(_artifact("membership.interfaces.evidence"),),
    )
    collection = LineageOperation(
        operation_id="collection.interfaces",
        kind=LineageOperationKind.COLLECTED_FROM,
        source_entity_ids=(patient.entity_id,),
        target_entity_ids=(specimen.entity_id,),
        authority_decision_id=AUTHORITY_ID,
        policy_version=POLICY_VERSION,
        evidence=(_artifact("collection.interfaces.evidence"),),
    )
    return ReconcileIdentityLineageRequest(
        context=context,
        policy=policy,
        entities=(patient, specimen),
        assertions=(membership,),
        lineage_operations=(collection,),
    )


def _write_request(path: Path, request: ReconcileIdentityLineageRequest) -> None:
    path.write_bytes(canonical_json_bytes(request))


def test_api_and_cli_reconcile_get_verify_and_schema_are_exact_parity(
    tmp_path: Path,
) -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    api_database = tmp_path / "api.sqlite3"
    cli_database = tmp_path / "cli.sqlite3"
    request_path = tmp_path / "request.json"
    _write_request(request_path, request)

    with TestClient(create_app(api_database)) as client:
        api_reconcile = client.post("/v1/modules/M01-02/reconcile", json=payload)
        assert api_reconcile.status_code == HTTP_OK
        api_resolution = api_reconcile.json()
        api_get = client.get(
            f"/v1/modules/M01-02/resolutions/{api_resolution['resolution_digest']}"
        )
        api_verify = client.get("/v1/modules/M01-02/events/verify")
        api_schema = client.get("/v1/contracts/M01-02/request/schema")

    runner = CliRunner()
    cli_reconcile = runner.invoke(
        cli_app,
        ["identity", "reconcile", str(request_path), "--database", str(cli_database)],
    )
    assert cli_reconcile.exit_code == 0, cli_reconcile.output
    cli_resolution = json.loads(cli_reconcile.output)
    cli_get = runner.invoke(
        cli_app,
        [
            "identity",
            "get",
            cli_resolution["resolution_digest"],
            "--database",
            str(cli_database),
        ],
    )
    cli_verify = runner.invoke(
        cli_app,
        ["identity", "verify-ledger", "--database", str(cli_database)],
    )
    cli_schema = runner.invoke(cli_app, ["identity", "export-schema", "request"])

    assert api_get.status_code == api_verify.status_code == api_schema.status_code == HTTP_OK
    output_adapter = TypeAdapter(IdentityLineageResolution)
    api_output = output_adapter.validate_json(api_reconcile.content, strict=True)
    api_get_output = output_adapter.validate_json(api_get.content, strict=True)
    cli_output = output_adapter.validate_json(cli_reconcile.output, strict=True)
    cli_get_output = output_adapter.validate_json(cli_get.output, strict=True)
    assert api_get_output == api_output == cli_output == cli_get_output
    assert api_verify.json() == json.loads(cli_verify.output)
    assert api_verify.json()["valid"] is True
    assert api_verify.json()["event_count"] == 1
    assert api_schema.json() == json.loads(cli_schema.output)
    assert cli_get.exit_code == cli_verify.exit_code == cli_schema.exit_code == 0


def test_m0102_api_and_cli_reject_duplicate_keys_and_oversized_bodies(
    tmp_path: Path,
) -> None:
    encoded = canonical_json_bytes(_request())
    duplicate = encoded.replace(
        b'"operation":"reconcile"',
        b'"operation":"reconcile","operation":"reconcile"',
        1,
    )
    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_bytes(duplicate)
    oversized_path = tmp_path / "oversized.json"
    oversized_path.write_bytes(b" " * (MAX_REQUEST_BYTES + 1))

    with TestClient(create_app(tmp_path / "api-invalid.sqlite3")) as client:
        duplicate_api = client.post(
            "/v1/modules/M01-02/reconcile",
            content=duplicate,
            headers={"content-type": "application/json"},
        )
        oversized_api = client.post(
            "/v1/modules/M01-02/reconcile",
            content=oversized_path.read_bytes(),
            headers={"content-type": "application/json"},
        )

    runner = CliRunner()
    duplicate_cli = runner.invoke(
        cli_app,
        [
            "identity",
            "reconcile",
            str(duplicate_path),
            "--database",
            str(tmp_path / "duplicate.sqlite3"),
        ],
    )
    oversized_cli = runner.invoke(
        cli_app,
        [
            "identity",
            "reconcile",
            str(oversized_path),
            "--database",
            str(tmp_path / "oversized.sqlite3"),
        ],
    )

    assert duplicate_api.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert "duplicate JSON object key" in json.dumps(duplicate_api.json())
    assert duplicate_cli.exit_code == CLI_INVALID_INPUT
    assert "duplicate JSON object key" in duplicate_cli.output
    assert oversized_api.status_code == HTTP_PAYLOAD_TOO_LARGE
    assert oversized_api.json() == {"detail": "request body exceeds the byte limit"}
    assert oversized_cli.exit_code == CLI_INVALID_INPUT
    assert "request body exceeds the byte limit" in oversized_cli.output


def test_m0102_validation_diagnostics_are_bounded_and_do_not_echo_canaries(
    tmp_path: Path,
) -> None:
    payload = _request().model_dump(mode="json")
    canary_prefix = "private-field-canary-"
    canary_value = "private-value-canary-" + ("Q" * 32)
    for index in range(MAX_VALIDATION_ERRORS + 40):
        payload[f"{canary_prefix}{index:03}"] = canary_value

    with TestClient(create_app(tmp_path / "bounded.sqlite3")) as client:
        response = client.post("/v1/modules/M01-02/reconcile", json=payload)

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    details = response.json()["detail"]
    assert len(details) == MAX_VALIDATION_ERRORS
    assert details[-1]["type"] == "validation_errors_truncated"
    rendered = json.dumps(details)
    assert canary_prefix not in rendered
    assert canary_value not in rendered
    assert "Q" * 8 not in rendered
    assert "input_value" not in rendered


def test_m0102_authorization_denial_is_fail_closed_across_api_and_cli(
    tmp_path: Path,
) -> None:
    request = _request()
    references = request.context.references
    denied_context = request.context.model_copy(
        update={
            "references": references.model_copy(
                update={
                    "consent": references.consent.model_copy(
                        update={"state": ConsentState.REVOKED}
                    )
                }
            )
        }
    )
    denied = request.model_copy(update={"context": denied_context})
    denied_path = tmp_path / "denied.json"
    _write_request(denied_path, denied)
    api_database = tmp_path / "denied-api.sqlite3"
    cli_database = tmp_path / "denied-cli.sqlite3"

    with TestClient(create_app(api_database)) as client:
        api_response = client.post(
            "/v1/modules/M01-02/reconcile",
            json=denied.model_dump(mode="json"),
        )
    cli_response = CliRunner().invoke(
        cli_app,
        ["identity", "reconcile", str(denied_path), "--database", str(cli_database)],
    )

    assert api_response.status_code == HTTP_FORBIDDEN
    assert "does not authorize reconciliation" in api_response.json()["detail"]
    assert cli_response.exit_code == 1
    assert "reconciliation failed:" in cli_response.output
    for database in (api_database, cli_database):
        with M0102EventStore(database) as store:
            assert store.verify_event_chain().event_count == 0


def test_raw_api_cli_and_plugin_authorize_before_policy_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    references = request.context.references
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": references.model_copy(
                        update={
                            "consent": references.consent.model_copy(
                                update={"state": ConsentState.REVOKED}
                            )
                        }
                    )
                }
            )
        }
    )
    encoded = canonical_json_bytes(denied)
    request_path = tmp_path / "denied-prehash.json"
    request_path.write_bytes(encoded)

    def forbidden_policy_hash(_policy: object) -> str:
        raise _PolicyHashBeforeAuthorizationError

    monkeypatch.setattr(m0102_contract, "policy_digest", forbidden_policy_hash)

    with TestClient(create_app(tmp_path / "prehash-api.sqlite3")) as client:
        api_response = client.post(
            "/v1/modules/M01-02/reconcile",
            content=encoded,
            headers={"content-type": "application/json"},
        )
    cli_response = CliRunner().invoke(
        cli_app,
        [
            "identity",
            "reconcile",
            str(request_path),
            "--database",
            str(tmp_path / "prehash-cli.sqlite3"),
        ],
    )
    with (
        M0102Service(M0102EventStore(tmp_path / "prehash-plugin.sqlite3")) as runtime,
        pytest.raises(IdentityLineageAuthorizationError),
    ):
        M0102Plugin(runtime).validate(encoded)

    assert api_response.status_code == HTTP_FORBIDDEN
    assert cli_response.exit_code == 1


def test_m0102_invalid_lookup_is_sanitized_and_readiness_checks_both_ledgers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_lookup = "private-path-canary-" + ("Q" * 32)
    runner = CliRunner()
    cli_lookup = runner.invoke(
        cli_app,
        [
            "identity",
            "get",
            invalid_lookup,
            "--database",
            str(tmp_path / "lookup.sqlite3"),
        ],
    )
    with TestClient(create_app(tmp_path / "lookup-api.sqlite3")) as client:
        api_lookup = client.get(f"/v1/modules/M01-02/resolutions/{invalid_lookup}")

    assert cli_lookup.exit_code == CLI_INVALID_INPUT
    assert cli_lookup.output.strip() == "invalid lookup: resolution digest is invalid"
    assert api_lookup.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert api_lookup.json() == {"detail": "resolution digest is invalid"}
    assert invalid_lookup not in cli_lookup.output
    assert invalid_lookup not in json.dumps(api_lookup.json())

    invalid_chain = ChainVerification(
        valid=False,
        event_count=0,
        head_digest="sha256:" + ("0" * 64),
        reason="synthetic identity chain failure",
    )
    monkeypatch.setattr(M0102Service, "verify_event_chain", lambda _service: invalid_chain)
    with TestClient(create_app(tmp_path / "readiness.sqlite3")) as client:
        readiness = client.get("/readyz")
        module_verification = client.get("/v1/modules/M01-02/events/verify")

    assert readiness.status_code == HTTP_SERVICE_UNAVAILABLE
    assert module_verification.status_code == HTTP_SERVICE_UNAVAILABLE
    assert readiness.json() == module_verification.json() == {
        "detail": "synthetic identity chain failure"
    }


def test_m0102_missing_resolution_and_service_failures_map_consistently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_digest = "sha256:" + ("0" * 64)
    database = tmp_path / "interface-failures.sqlite3"

    with TestClient(create_app(database)) as client:
        missing = client.get(f"/v1/modules/M01-02/resolutions/{missing_digest}")

    missing_cli = CliRunner().invoke(
        cli_app,
        ["identity", "get", missing_digest, "--database", str(database)],
    )
    assert missing.status_code == HTTP_NOT_FOUND
    assert missing_cli.exit_code == 1
    assert "not registered" in missing.json()["detail"]
    assert "lookup failed:" in missing_cli.output

    def conflict(_service: M0102Service, _request: object) -> None:
        raise M0102IdempotencyConflictError(CONFLICT_DETAIL)

    monkeypatch.setattr(M0102Service, "execute", conflict)
    with TestClient(create_app(tmp_path / "conflict.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M01-02/reconcile",
            json=_request().model_dump(mode="json"),
        )
    assert response.status_code == HTTP_CONFLICT
    assert response.json() == {"detail": CONFLICT_DETAIL}

    def oversized(_service: M0102Service, _request: object) -> None:
        raise M0102PayloadTooLargeError(PAYLOAD_LIMIT_DETAIL)

    monkeypatch.setattr(M0102Service, "execute", oversized)
    with TestClient(create_app(tmp_path / "payload.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M01-02/reconcile",
            json=_request().model_dump(mode="json"),
        )
    assert response.status_code == HTTP_PAYLOAD_TOO_LARGE
    assert response.json() == {"detail": PAYLOAD_LIMIT_DETAIL}


def test_m0102_cli_handles_invalid_chain_and_store_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeIdentityService:
        def __init__(self, result: ChainVerification | Exception) -> None:
            self._result = result

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def verify_event_chain(self) -> ChainVerification:
            if isinstance(self._result, Exception):
                raise self._result
            return self._result

    invalid = ChainVerification(
        valid=False,
        event_count=0,
        head_digest="sha256:" + ("0" * 64),
        reason="synthetic invalid chain",
    )
    monkeypatch.setattr(
        cli_module,
        "_identity_service",
        lambda _database: FakeIdentityService(invalid),
    )
    runner = CliRunner()
    invalid_result = runner.invoke(
        cli_app,
        ["identity", "verify-ledger", "--database", str(tmp_path / "invalid.sqlite3")],
    )
    assert invalid_result.exit_code == 1
    assert '"valid":false' in invalid_result.output

    monkeypatch.setattr(
        cli_module,
        "_identity_service",
        lambda _database: FakeIdentityService(M0102EventStoreError("synthetic store failure")),
    )
    failed_result = runner.invoke(
        cli_app,
        ["identity", "verify-ledger", "--database", str(tmp_path / "failed.sqlite3")],
    )
    assert failed_result.exit_code == 1
    assert failed_result.output.strip() == "verification failed: synthetic store failure"


def test_m0102_cli_sanitizes_request_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_path = tmp_path / "request.json"
    _write_request(request_path, _request())

    def unreadable(_path: Path) -> bytes:
        raise OSError(PRIVATE_FILESYSTEM_DETAIL)

    monkeypatch.setattr(cli_module, "read_bounded", unreadable)
    response = CliRunner().invoke(
        cli_app,
        [
            "identity",
            "reconcile",
            str(request_path),
            "--database",
            str(tmp_path / "unreadable.sqlite3"),
        ],
    )

    assert response.exit_code == CLI_INVALID_INPUT
    assert response.output.strip() == "invalid request: unable to read or decode request document"
    assert PRIVATE_FILESYSTEM_DETAIL not in response.output


def test_shared_interfaces_reject_invalid_protocol_lookup_and_failed_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_schema_id = "contains space"
    database = tmp_path / "shared-interface.sqlite3"
    with TestClient(create_app(database)) as client:
        api_lookup = client.get(
            f"/v1/modules/M01-01/protocols/{invalid_schema_id}/1.0.0"
        )
    cli_lookup = CliRunner().invoke(
        cli_app,
        [
            "protocol",
            "get",
            invalid_schema_id,
            "1.0.0",
            "--database",
            str(database),
        ],
    )
    assert api_lookup.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli_lookup.exit_code == CLI_INVALID_INPUT
    assert "invalid lookup:" in cli_lookup.output

    invalid_chain = M0101ChainVerification(
        valid=False,
        event_count=0,
        head_digest="sha256:" + ("0" * 64),
        reason="synthetic protocol chain failure",
    )
    monkeypatch.setattr(M0101Service, "verify_event_chain", lambda _service: invalid_chain)
    with TestClient(create_app(tmp_path / "protocol-readiness.sqlite3")) as client:
        readiness = client.get("/readyz")

    assert readiness.status_code == HTTP_SERVICE_UNAVAILABLE
    assert readiness.json() == {"detail": "synthetic protocol chain failure"}
