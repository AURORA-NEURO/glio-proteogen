"""End-to-end registration and evaluation of the packaged M01-01 domain profile."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib.resources import files
from typing import TYPE_CHECKING, cast

import pytest
from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_01.canonical import (
    identity_binding_digest,
    metadata_document_digest,
)
from glio_proteogen.contracts.m01_01.v1 import (
    ConformanceDecision,
    EvaluateMetadataRequest,
    MetadataDocument,
    ObservedValue,
    ProtocolSchema,
    ProtocolSchemaReceipt,
    RegisterProtocolRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EstimateState,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import JsonValue, strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata import (
    service as service_module,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.event_store import (
    M0101EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.quality_consensus import (
    LoadedQualityConsensus,
    QualityConsensusArtifactError,
    load_packaged_quality_consensus,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.service import (
    InvalidProtocolLookupError,
    M0101Service,
)
from tests.m01_01_support import load_request

if TYPE_CHECKING:
    from pathlib import Path

_PROFILE_PACKAGE = "glio_proteogen.profiles.m01_01.v1"
_EXPECTED_EVENT_COUNT = 2
_MODEL_DIGEST = "sha256:c0d8b536f2d162a41fb7ff6d3de9941f7debad31aa15bc39444a993e16ab869b"
_CORPUS_DIGEST = "sha256:9ae807d745cbda935222758a2ce29d0d6855cd6452dd16adf9c694fed6145940"
_DIGESTS = {
    "configuration": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "identity": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "provenance": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "consent": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "quality": "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    "support": "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
    "intended_use": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
}


def _profile_case() -> tuple[ProtocolSchema, MetadataDocument]:
    profile = files(_PROFILE_PACKAGE)
    schema = TypeAdapter(ProtocolSchema).validate_json(
        profile.joinpath("protocol-schema.json").read_bytes()
    )
    corpus = cast(
        "dict[str, JsonValue]",
        strict_json_loads(profile.joinpath("conformance-corpus.json").read_bytes()),
    )
    document = TypeAdapter(MetadataDocument).validate_json(
        canonical_json_bytes(corpus["base_document"])
    )
    return schema, document


def _artifact(role: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"{role}.synthetic.evidence",
        version="1.0.0",
        digest=_DIGESTS[role],
        media_type="application/json",
    )


def _accepted_control(role: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"{role}.synthetic.decision",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(role),
    )


def _context(
    request_id: str,
    occurred_at: datetime,
    binding_digest: str,
) -> ExecutionContext:
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor.synthetic.domain_profile",
        occurred_at=occurred_at,
        references=ContextReferences(
            approved_configuration=_accepted_control("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="identity.synthetic.decision",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=binding_digest,
                evidence=_artifact("identity"),
            ),
            provenance=_accepted_control("provenance"),
            consent=ConsentReference(
                decision_id="consent.synthetic.decision",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=_accepted_control("quality"),
            support=_accepted_control("support"),
            intended_use=_accepted_control("intended_use"),
        ),
    )


def _replace_observed(
    document: MetadataDocument,
    path: str,
    value: str | float,
) -> MetadataDocument:
    entries = []
    for entry in document.entries:
        if entry.path != path:
            entries.append(entry)
            continue
        current = entry.values[0]
        assert isinstance(current, ObservedValue)
        entries.append(
            entry.model_copy(
                update={"values": (ObservedValue(value=value, unit=current.unit),)}
            )
        )
    return document.model_copy(update={"entries": tuple(entries)})


def _evaluation_request(
    schema: ProtocolSchema,
    document: MetadataDocument,
    receipt: ProtocolSchemaReceipt,
    occurred_at: datetime,
    *,
    request_id: str = "request.synthetic.domain_profile.evaluate",
) -> EvaluateMetadataRequest:
    return EvaluateMetadataRequest(
        context=_context(
            request_id,
            occurred_at,
            identity_binding_digest(schema, document),
        ),
        protocol=receipt.protocol,
        document=document,
    )


def _all_mapping_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(
            *(_all_mapping_keys(item) for item in value.values()),
        )
    if isinstance(value, (list, tuple)):
        return set().union(*(_all_mapping_keys(item) for item in value))
    return set()


@pytest.mark.integration
def test_packaged_domain_profile_registers_and_evaluates_end_to_end(tmp_path: Path) -> None:
    schema, document = _profile_case()
    binding_digest = identity_binding_digest(schema, document)
    registered_at = datetime(2026, 1, 1, tzinfo=UTC)
    registration = RegisterProtocolRequest(
        context=_context(
            "request.synthetic.domain_profile.register",
            registered_at,
            binding_digest,
        ),
        protocol_schema=schema,
    )
    service = M0101Service(M0101EventStore(tmp_path / "domain-profile.sqlite3"))
    try:
        receipt = service.register(registration)
        evaluation = _evaluation_request(
            schema,
            document,
            receipt,
            registered_at + timedelta(seconds=1),
        )

        profile = service.evaluate(evaluation)
        verification = service.verify_event_chain()
    finally:
        service.close()

    assert receipt.protocol.schema_id == "glio_preanalytic_proteomics"
    assert profile.decision is ConformanceDecision.CONFORMANT
    assert profile.issues == ()
    assert profile.document_digest == metadata_document_digest(document)
    assert not profile.human_review_required
    assert profile.uncertainty.model_form.state is EstimateState.NOT_ESTIMABLE
    evidence = {item.reference.artifact_id: item.reference for item in profile.evidence}
    assert evidence["glio_preanalytic_quality_consensus"].digest == _MODEL_DIGEST
    assert evidence["glio_preanalytic_quality_reference"].digest == _CORPUS_DIGEST
    assert evidence["glio_preanalytic_quality_consensus"].media_type == (
        "application/vnd.glio-proteogen.quality-model+json"
    )
    assert evidence["glio_preanalytic_quality_reference"].media_type == (
        "application/vnd.glio-proteogen.quality-reference-corpus+json"
    )
    assert {_MODEL_DIGEST, _CORPUS_DIGEST}.issubset(profile.provenance.input_digests)
    public_keys = _all_mapping_keys(profile.model_dump(mode="json"))
    assert "consensus" not in public_keys
    assert "mean_distance" not in public_keys
    assert "evaluated_views" not in public_keys
    assert "cluster_id" not in public_keys
    assert "features" not in public_keys
    assert verification.valid
    assert verification.event_count == _EXPECTED_EVENT_COUNT


@pytest.mark.integration
def test_reference_domain_outlier_only_quarantines_and_emits_generic_evidence(
    tmp_path: Path,
) -> None:
    schema, base_document = _profile_case()
    document = _replace_observed(
        base_document,
        "/specimen/warm_ischemia_time",
        1440.0,
    )
    occurred_at = datetime(2026, 1, 2, tzinfo=UTC)
    service = M0101Service(M0101EventStore(tmp_path / "domain-outlier.sqlite3"))
    try:
        receipt = service.register(
            RegisterProtocolRequest(
                context=_context(
                    "request.synthetic.domain_profile.outlier.register",
                    occurred_at,
                    identity_binding_digest(schema, document),
                ),
                protocol_schema=schema,
            )
        )
        profile = service.evaluate(
            _evaluation_request(
                schema,
                document,
                receipt,
                occurred_at + timedelta(seconds=1),
                request_id="request.synthetic.domain_profile.outlier.evaluate",
            )
        )
    finally:
        service.close()

    assert profile.decision is ConformanceDecision.QUARANTINED
    assert profile.human_review_required
    assert [issue.code for issue in profile.issues] == ["quality.novel_or_ood"]
    issue = profile.issues[0]
    assert issue.path == "/entries"
    assert issue.evidence == ()
    rendered = profile.model_dump_json()
    assert "1440" not in rendered
    for internal in ("frozen_dda", "frozen_dia", "ffpe_dda", "ffpe_dia"):
        assert internal not in rendered


@pytest.mark.integration
def test_owned_profile_artifact_failure_quarantines_without_fabricated_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema, document = _profile_case()
    occurred_at = datetime(2026, 1, 3, tzinfo=UTC)

    def fail_loader() -> None:
        raise QualityConsensusArtifactError

    monkeypatch.setattr(service_module, "load_packaged_quality_consensus", fail_loader)
    service = M0101Service(M0101EventStore(tmp_path / "consensus-unavailable.sqlite3"))
    try:
        receipt = service.register(
            RegisterProtocolRequest(
                context=_context(
                    "request.synthetic.domain_profile.unavailable.register",
                    occurred_at,
                    identity_binding_digest(schema, document),
                ),
                protocol_schema=schema,
            )
        )
        profile = service.evaluate(
            _evaluation_request(
                schema,
                document,
                receipt,
                occurred_at + timedelta(seconds=1),
                request_id="request.synthetic.domain_profile.unavailable.evaluate",
            )
        )
    finally:
        service.close()

    assert profile.decision is ConformanceDecision.QUARANTINED
    assert [issue.code for issue in profile.issues] == ["quality.consensus_unavailable"]
    artifact_ids = {item.reference.artifact_id for item in profile.evidence}
    assert "glio_preanalytic_quality_consensus" not in artifact_ids
    assert "glio_preanalytic_quality_reference" not in artifact_ids
    assert _MODEL_DIGEST not in profile.provenance.input_digests
    assert _CORPUS_DIGEST not in profile.provenance.input_digests


@pytest.mark.integration
def test_unrelated_protocol_is_not_quarantined_when_owned_assets_are_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registration = load_request("register_minimal.valid.json")
    evaluation = load_request("evaluate_conformant.valid.json")
    assert isinstance(registration, RegisterProtocolRequest)
    assert isinstance(evaluation, EvaluateMetadataRequest)

    def fail_loader() -> None:
        raise QualityConsensusArtifactError

    monkeypatch.setattr(service_module, "load_packaged_quality_consensus", fail_loader)
    service = M0101Service(M0101EventStore(tmp_path / "unrelated-unavailable.sqlite3"))
    try:
        service.register(registration)
        profile = service.evaluate(evaluation)
    finally:
        service.close()

    assert profile.decision is ConformanceDecision.CONFORMANT
    assert profile.issues == ()
    assert profile.uncertainty.model_form.state is EstimateState.NOT_APPLICABLE


@pytest.mark.integration
def test_exact_replay_does_not_reassess_or_refetch_reference_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema, document = _profile_case()
    occurred_at = datetime(2026, 1, 4, tzinfo=UTC)
    database = tmp_path / "domain-replay.sqlite3"
    service = M0101Service(M0101EventStore(database))
    receipt = service.register(
        RegisterProtocolRequest(
            context=_context(
                "request.synthetic.domain_profile.replay.register",
                occurred_at,
                identity_binding_digest(schema, document),
            ),
            protocol_schema=schema,
        )
    )
    evaluation = _evaluation_request(
        schema,
        document,
        receipt,
        occurred_at + timedelta(seconds=1),
        request_id="request.synthetic.domain_profile.replay.evaluate",
    )
    original_assess = service_module.assess_quality_consensus
    calls = 0

    def counted_assess(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return original_assess(*args, **kwargs)

    monkeypatch.setattr(service_module, "assess_quality_consensus", counted_assess)
    try:
        first = service.evaluate(evaluation)
        replay = service.evaluate(evaluation)
        verification = service.verify_event_chain()
    finally:
        service.close()

    reopened_service = M0101Service(M0101EventStore(database))
    try:
        recovered = reopened_service.evaluate(evaluation)
        recovered_verification = reopened_service.verify_event_chain()
    finally:
        reopened_service.close()

    assert replay == first
    assert recovered == first
    assert calls == 1
    assert verification.event_count == _EXPECTED_EVENT_COUNT
    assert recovered_verification.valid
    assert recovered_verification.event_count == _EXPECTED_EVENT_COUNT
    assert {_MODEL_DIGEST, _CORPUS_DIGEST}.issubset(recovered.provenance.input_digests)


@pytest.mark.integration
def test_nonconformant_metadata_skips_reference_domain_assessment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema, document = _profile_case()
    identity_path = next(field.path for field in schema.fields if field.identity_key)
    invalid_document = document.model_copy(
        update={
            "entries": tuple(entry for entry in document.entries if entry.path != identity_path)
        }
    )
    occurred_at = datetime(2026, 1, 5, tzinfo=UTC)
    service = M0101Service(M0101EventStore(tmp_path / "domain-invalid.sqlite3"))
    receipt = service.register(
        RegisterProtocolRequest(
            context=_context(
                "request.synthetic.domain_profile.invalid.register",
                occurred_at,
                identity_binding_digest(schema, invalid_document),
            ),
            protocol_schema=schema,
        )
    )

    def unexpected_assessment(*_args: object, **_kwargs: object) -> object:
        raise AssertionError

    monkeypatch.setattr(service_module, "assess_quality_consensus", unexpected_assessment)
    try:
        profile = service.evaluate(
            _evaluation_request(
                schema,
                invalid_document,
                receipt,
                occurred_at + timedelta(seconds=1),
                request_id="request.synthetic.domain_profile.invalid.evaluate",
            )
        )
    finally:
        service.close()

    assert profile.decision is not ConformanceDecision.CONFORMANT
    assert all(not issue.code.startswith("quality.") for issue in profile.issues)


@pytest.mark.integration
def test_consensus_dependency_injection_accepts_only_the_exact_packaged_bundle(
    tmp_path: Path,
) -> None:
    loaded = load_packaged_quality_consensus()
    forged = LoadedQualityConsensus(
        model=loaded.model,
        corpus=loaded.corpus,
        model_digest=f"sha256:{'0' * 64}",
        corpus_digest=loaded.corpus_digest,
    )
    accepted = M0101Service(
        M0101EventStore(tmp_path / "accepted-consensus.sqlite3"),
        quality_consensus=loaded,
    )
    rejected = M0101Service(
        M0101EventStore(tmp_path / "rejected-consensus.sqlite3"),
        quality_consensus=forged,
    )
    try:
        assert accepted._quality_consensus_available is True
        assert rejected._quality_consensus_available is False
    finally:
        accepted.close()
        rejected.close()


@pytest.mark.integration
def test_runtime_consensus_artifact_error_uses_quarantine_first_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema, document = _profile_case()
    occurred_at = datetime(2026, 1, 6, tzinfo=UTC)
    service = M0101Service(M0101EventStore(tmp_path / "runtime-consensus-error.sqlite3"))
    receipt = service.register(
        RegisterProtocolRequest(
            context=_context(
                "request.synthetic.domain_profile.runtime_error.register",
                occurred_at,
                identity_binding_digest(schema, document),
            ),
            protocol_schema=schema,
        )
    )

    def fail_assessment(*_args: object, **_kwargs: object) -> object:
        raise QualityConsensusArtifactError

    monkeypatch.setattr(service_module, "assess_quality_consensus", fail_assessment)
    try:
        profile = service.evaluate(
            _evaluation_request(
                schema,
                document,
                receipt,
                occurred_at + timedelta(seconds=1),
                request_id="request.synthetic.domain_profile.runtime_error.evaluate",
            )
        )
    finally:
        service.close()

    assert profile.decision is ConformanceDecision.QUARANTINED
    assert [issue.code for issue in profile.issues] == ["quality.consensus_unavailable"]


@pytest.mark.integration
def test_invalid_protocol_lookup_is_rejected_before_store_access(tmp_path: Path) -> None:
    service = M0101Service(M0101EventStore(tmp_path / "invalid-lookup.sqlite3"))
    try:
        with pytest.raises(InvalidProtocolLookupError):
            service.get_protocol("contains whitespace", "not-a-version")
    finally:
        service.close()
