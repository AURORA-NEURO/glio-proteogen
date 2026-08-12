"""Focused service and plugin boundary tests for M01-02."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest

from glio_proteogen.contracts.m01_02.canonical import policy_digest
from glio_proteogen.contracts.m01_02.v1 import (
    EntityComposition,
    EntityKind,
    IdentityAuthorityReference,
    IdentityControlRole,
    IdentityEntity,
    IdentityExecutionContext,
    IdentityReconciliationReferences,
    IdentityResolutionPolicy,
    LineageOperationKind,
    ReconcileIdentityLineageRequest,
    ScopedIdentityToken,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    Identifier,
    Sha256Digest,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, StrictJsonError
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage import service
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    ChainVerification,
    EventRecord,
    M0102EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.plugin import (
    M0102Plugin,
    ValidatedM0102Request,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import (
    IdentityLineageAuthorizationError,
    M0102Service,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import AwareDatetime

POLICY_VERSION = "1.0.0"
TOKEN_DIGEST = "sha256:" + ("9" * 64)


class _PreauthorizationBoundaryViolatedError(AssertionError):
    def __init__(self) -> None:
        super().__init__("hash, solver, or store ran before authorization")


class _BombStore:
    def find_replay(
        self,
        *,
        request_id: Identifier,
        request_digest: Sha256Digest,
    ) -> EventRecord | None:
        del request_id, request_digest
        raise _PreauthorizationBoundaryViolatedError

    def append_resolution(  # noqa: PLR0913
        self,
        *,
        request_id: Identifier,
        request_digest: Sha256Digest,
        occurred_at: AwareDatetime,
        core_digest: Sha256Digest,
        resolution_digest: Sha256Digest,
        supersedes_resolution_digest: Sha256Digest | None,
        payload: dict[str, Any],
    ) -> EventRecord:
        del (
            request_id,
            request_digest,
            occurred_at,
            core_digest,
            resolution_digest,
            supersedes_resolution_digest,
            payload,
        )
        raise _PreauthorizationBoundaryViolatedError

    def get_resolution(self, resolution_digest: Sha256Digest) -> EventRecord:
        del resolution_digest
        raise _PreauthorizationBoundaryViolatedError

    def verify_event_chain(self) -> ChainVerification:
        raise _PreauthorizationBoundaryViolatedError

    def close(self) -> None:
        raise _PreauthorizationBoundaryViolatedError


def _artifact(name: str, digest: Sha256Digest | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=digest or sha256_digest({"artifact": name}),
        media_type="application/vnd.aurora.synthetic+json",
    )


def _policy() -> IdentityResolutionPolicy:
    return IdentityResolutionPolicy(
        policy_id="identity.policy.service-test",
        version=POLICY_VERSION,
        max_component_size=32,
        maximum_depth=16,
        allow_mixed_subject_pooling=False,
        require_demultiplex_authority=True,
        allowed_operation_kinds=tuple(LineageOperationKind),
    )


def _request() -> ReconcileIdentityLineageRequest:
    policy = _policy()

    def accepted(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version=POLICY_VERSION,
            evidence=_artifact(f"control.{role}"),
        )

    configuration = accepted("approved-configuration").model_copy(
        update={"evidence": _artifact("control.approved-configuration", policy_digest(policy))}
    )
    references = IdentityReconciliationReferences(
        approved_configuration=configuration,
        identity_authority=IdentityAuthorityReference(
            decision_id="authority.service-test",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version=POLICY_VERSION,
            evidence=_artifact("control.identity-authority"),
        ),
        provenance=accepted("provenance"),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState.GRANTED,
            policy_version=POLICY_VERSION,
            evidence=_artifact("control.consent"),
        ),
        quality=accepted("quality"),
        support=accepted("support"),
        intended_use=accepted("intended-use"),
    )
    patient = IdentityEntity(
        entity_id="patient.pseudonym.a",
        kind=EntityKind.PATIENT,
        composition=EntityComposition.SINGLE_SUBJECT,
        identity_tokens=(
            ScopedIdentityToken(
                issuer_id="issuer.service-test",
                namespace_id="namespace.service-test",
                scope_id="scope.service-test",
                key_id="key.service-test",
                token_version="1.0.0",  # noqa: S106 - version, not a credential
                entity_kind=EntityKind.PATIENT,
                token_digest=TOKEN_DIGEST,
                evidence=_artifact("private.token-evidence"),
            ),
        ),
        evidence=(_artifact("private.entity-evidence"),),
    )
    return ReconcileIdentityLineageRequest(
        context=IdentityExecutionContext(
            request_id="request.service-test",
            actor_id="actor.service-test",
            occurred_at=datetime(2026, 8, 11, 19, tzinfo=UTC),
            references=references,
        ),
        policy=policy,
        entities=(patient,),
    )


def _denied(
    request: ReconcileIdentityLineageRequest,
    role: IdentityControlRole,
) -> ReconcileIdentityLineageRequest:
    references = request.context.references
    current = getattr(references, role.value)
    state = (
        ConsentState.WITHHELD
        if role is IdentityControlRole.CONSENT
        else UpstreamDecisionState.REJECTED
    )
    denied_reference = current.model_copy(update={"state": state})
    denied_references = references.model_copy(update={role.value: denied_reference})
    return request.model_copy(
        update={
            "context": request.context.model_copy(
                update={"references": denied_references}
            )
        }
    )


@pytest.mark.parametrize("role", tuple(IdentityControlRole))
def test_every_denied_control_precedes_hash_solver_and_store(
    role: IdentityControlRole,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    denied = _denied(_request(), role)

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise _PreauthorizationBoundaryViolatedError

    monkeypatch.setattr(service, "canonical_request_digest", forbidden)
    monkeypatch.setattr(service, "reconcile_identity_lineage", forbidden)

    with pytest.raises(IdentityLineageAuthorizationError) as raised:
        M0102Service(_BombStore()).execute(denied)

    assert raised.value.role is role


def test_exact_replay_precedes_solver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    database = tmp_path / "identity-events.sqlite3"
    with M0102Service(M0102EventStore(database)) as runtime:
        first = runtime.execute(request)

        def forbidden(_request: object) -> object:
            raise _PreauthorizationBoundaryViolatedError

        monkeypatch.setattr(service, "reconcile_identity_lineage", forbidden)
        replay = runtime.execute(request)

    assert replay == first


def test_envelope_is_control_only_private_and_retrievable(tmp_path: Path) -> None:
    request = _request()
    database = tmp_path / "identity-events.sqlite3"
    with M0102Service(M0102EventStore(database)) as runtime:
        resolution = runtime.execute(request)
        retrieved = runtime.get_resolution(resolution.resolution_digest)
        verification = runtime.verify_event_chain()

    serialized = canonical_json_bytes(resolution.model_dump(mode="python")).decode()
    expected_control_artifacts = {
        reference.evidence.artifact_id
        for reference in (
            request.context.references.approved_configuration,
            request.context.references.identity_authority,
            request.context.references.provenance,
            request.context.references.consent,
            request.context.references.quality,
            request.context.references.support,
            request.context.references.intended_use,
        )
    }
    assert retrieved == resolution
    assert verification.valid
    assert {item.reference.artifact_id for item in resolution.evidence} == (
        expected_control_artifacts
    )
    assert len(resolution.provenance.control_decisions) == len(IdentityControlRole)
    assert all(
        estimate.state.value == "not_estimable"
        for estimate in (
            resolution.uncertainty.measurement,
            resolution.uncertainty.sampling,
            resolution.uncertainty.parameter,
            resolution.uncertainty.model_form,
            resolution.uncertainty.identification,
            resolution.uncertainty.support,
            resolution.uncertainty.transport,
        )
    )
    assert {limitation.code for limitation in resolution.limitations} == {
        "identity_lineage_only",
        "external_identity_authority_unverified",
    }
    assert TOKEN_DIGEST not in serialized
    assert "private.token-evidence" not in serialized
    assert "private.entity-evidence" not in serialized


def test_plugin_strict_json_and_forged_token_revalidation(tmp_path: Path) -> None:
    request = _request()
    with M0102Service(M0102EventStore(tmp_path / "plugin.sqlite3")) as runtime:
        plugin = M0102Plugin(runtime)
        token = plugin.validate(canonical_json_bytes(request.model_dump(mode="json")))
        descriptor = plugin.descriptor()
        assert descriptor.module_id == "GLIO-PROTEOGEN-M01-02"
        assert descriptor.owner == "Computational biology"
        assert descriptor.safety_class == "S2"
        assert descriptor.gate == "G0"
        assert plugin.run(token).request_digest.startswith("sha256:")
        forged = ValidatedM0102Request(
            request=_denied(request, IdentityControlRole.CONSENT)
        )
        with pytest.raises(IdentityLineageAuthorizationError):
            plugin.run(forged)
        with pytest.raises(StrictJsonError):
            plugin.validate(b" " * (MAX_JSON_BYTES + 1))
