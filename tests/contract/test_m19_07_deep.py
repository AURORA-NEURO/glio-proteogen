"""Adversarial contract closure tests for M19-07 downstream typed export."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m19_07 import (
    CompatibilityMode,
    DownstreamExportConfiguration,
    ExportField,
    ExportFieldType,
    ExportOwnershipBinding,
    ExportProteotypeDownstreamContractRequest,
    SignedContractEnvelope,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.contracts.m19_07.v1 import M1907_M1906_INPUT_MEDIA_TYPE, M1907_MODULE_ID
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportDecision,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _artifact(label: str, *, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1907": label}),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="M19-07 downstream typed export evidence",
    )


def _context() -> ExecutionContext:
    accepted = UpstreamDecisionState.ACCEPTED
    return ExecutionContext(
        request_id="request.m1907",
        actor_id="actor.test",
        occurred_at=_WHEN,
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="decision.configuration",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("configuration"),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("identity"),
                evidence=_artifact("identity"),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="decision.provenance",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("provenance"),
            ),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="decision.quality",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("quality"),
            ),
            support=UpstreamDecisionReference(
                decision_id="decision.support",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("support"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="decision.intended",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("intended"),
            ),
        ),
    )


def _field(label: str = "proteotype") -> ExportField:
    return ExportField(
        field_id=f"field.{label}",
        field_name=f"proteotype_{label}",
        value_type=ExportFieldType.REFERENCE,
        field_version="1.0.0",
        owner="Scientific engineering",
        documentation="Documented proteotype field for downstream export.",
        value_digest=sha256_digest({"field": label}),
        evidence=(_evidence(f"field.{label}"),),
    )


def _config() -> DownstreamExportConfiguration:
    return DownstreamExportConfiguration(
        configuration_id="configuration.m1907",
        version="1.0.0",
        compatibility=CompatibilityMode.VERSIONED,
        evidence=(_evidence("configuration.m1907"),),
    )


def _request(
    *,
    fields: tuple[ExportField, ...] | None = None,
    consent: ConsentReference | None = None,
    source_artifacts: tuple[ArtifactReference, ...] | None = None,
) -> ExportProteotypeDownstreamContractRequest:
    context = _context()
    return ExportProteotypeDownstreamContractRequest(
        request_id="request.m1907",
        context=context,
        upstream_result=_artifact("upstream", media_type=M1907_M1906_INPUT_MEDIA_TYPE),
        fields=fields or (_field(),),
        consent=consent or context.references.consent,
        support_decision=SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="supported.m1907",
            rationale="Caller-declared support is within the documented export envelope.",
        ),
        configuration=_config(),
        source_artifacts=source_artifacts or (_artifact("source"),),
    )


def test_request_binds_input_controls_and_unique_evidence() -> None:
    request = _request()
    assert request.upstream_result.media_type == M1907_M1906_INPUT_MEDIA_TYPE
    assert request.consent == request.context.references.consent
    with pytest.raises(ValidationError, match="field ids"):
        _request(fields=(_field(), _field()))
    source = _artifact("source")
    with pytest.raises(ValidationError, match="source artifact digests"):
        _request(source_artifacts=(source, source))


def test_request_rejects_wrong_upstream_and_context_consent() -> None:
    with pytest.raises(ValidationError, match="M19-06"):
        ExportProteotypeDownstreamContractRequest.model_validate(
            _request().model_dump(mode="python")
            | {"upstream_result": _artifact("wrong", media_type="application/json")}
        )
    other = ConsentReference(
        decision_id="decision.other",
        state=ConsentState.GRANTED,
        policy_version="1.0.0",
        evidence=_artifact("other-consent"),
    )
    with pytest.raises(ValidationError, match="context consent"):
        _request(consent=other)


def test_field_identity_and_evidence_are_closed() -> None:
    with pytest.raises(ValidationError, match="distinct"):
        _field("same").model_validate(
            _field("same").model_dump(mode="python")
            | {"field_name": "field.same"}
        )
    evidence = _evidence("same-evidence")
    with pytest.raises(ValidationError, match="evidence digests"):
        ExportField(
            **(_field().model_dump(mode="python") | {"evidence": (evidence, evidence)})
        )


def test_ownership_and_signature_closures_are_explicit() -> None:
    with pytest.raises(ValidationError, match="M19-07"):
        ExportOwnershipBinding(
            owning_module="GLIO-PROTEOGEN-M00-00",
            owner="Scientific engineering",
            ownership_statement="Wrong module ownership.",
            parent_target="proteotype",
            evidence=(_evidence("ownership"),),
        )
    digest = sha256_digest("payload")
    with pytest.raises(ValidationError, match="distinct"):
        SignedContractEnvelope(
            signer_id="actor.test",
            algorithm="caller-declared-sha256",
            signed_payload_digest=digest,
            signature_digest=digest,
            evidence=(_evidence("signature"),),
        )


def test_configuration_evidence_cannot_be_empty_or_repeated() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        DownstreamExportConfiguration(
            configuration_id="configuration.empty",
            version="1.0.0",
            compatibility=CompatibilityMode.STRICT,
            evidence=(),
        )
    evidence = _evidence("configuration.repeat")
    with pytest.raises(ValidationError, match="evidence digests"):
        DownstreamExportConfiguration(
            configuration_id="configuration.repeat",
            version="1.0.0",
            compatibility=CompatibilityMode.STRICT,
            evidence=(evidence, evidence),
        )


def test_canonical_request_and_result_mapping_are_stable() -> None:
    request = _request()
    assert canonical_request_digest(request.model_dump(mode="json")) == canonical_request_digest(
        request
    )
    assert result_payload_digest({"result_digest": "sha256:" + "a" * 64}).startswith("sha256:")
    assert M1907_MODULE_ID == "GLIO-PROTEOGEN-M19-07"
