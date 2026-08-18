"""Adversarial contract closure tests for M19-07 downstream typed export."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m19_07 import (
    CompatibilityMode,
    DownstreamContractObject,
    DownstreamExportConfiguration,
    ExportField,
    ExportFieldType,
    ExportOwnershipBinding,
    ExportProteotypeDownstreamContractRequest,
    ExportStatus,
    ProteotypeDownstreamExportResult,
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
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_07_downstream_typed_export import (
    M1907Engine,
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
            _field("same").model_dump(mode="python") | {"field_name": "field.same"}
        )
    evidence = _evidence("same-evidence")
    with pytest.raises(ValidationError, match="evidence digests"):
        ExportField(**(_field().model_dump(mode="python") | {"evidence": (evidence, evidence)}))


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


def test_request_closure_rejects_duplicate_names_context_and_cross_field_evidence() -> None:
    first = _field("first")
    duplicate_name = _field("second").model_copy(update={"field_name": first.field_name})
    with pytest.raises(ValidationError, match="field names"):
        ExportProteotypeDownstreamContractRequest.model_validate(
            _request(fields=(first, duplicate_name)).model_dump(mode="python")
        )
    mismatched_context = _context().model_copy(update={"request_id": "request.other"})
    with pytest.raises(ValidationError, match="context request id"):
        ExportProteotypeDownstreamContractRequest.model_validate(
            _request().model_dump(mode="python") | {"context": mismatched_context}
        )
    shared_evidence = _evidence("shared-field-evidence")
    first_shared = first.model_copy(update={"evidence": (shared_evidence,)})
    second_shared = _field("second").model_copy(update={"evidence": (shared_evidence,)})
    with pytest.raises(ValidationError, match="field evidence"):
        ExportProteotypeDownstreamContractRequest(
            **(_request().model_dump(mode="python") | {"fields": (first_shared, second_shared)})
        )


def test_nested_signature_ownership_and_contract_closures_reject_reuse() -> None:
    evidence = _evidence("repeated-nested-evidence")
    with pytest.raises(ValidationError, match="ownership evidence"):
        ExportOwnershipBinding(
            owning_module=M1907_MODULE_ID,
            owner="Scientific engineering",
            ownership_statement="M19-07 owns the typed export.",
            evidence=(evidence, evidence),
        )
    digest = sha256_digest("nested-payload")
    with pytest.raises(ValidationError, match="signature evidence"):
        SignedContractEnvelope(
            signer_id="actor.test",
            algorithm="caller-declared-sha256",
            signed_payload_digest=digest,
            signature_digest=sha256_digest("nested-signature"),
            evidence=(evidence, evidence),
        )
    result = M1907Engine().export(_request())
    assert result.contract is not None
    contract = result.contract
    duplicate_id = _field("duplicate-id").model_copy(
        update={"field_id": contract.fields[0].field_id}
    )
    with pytest.raises(ValidationError, match="field ids"):
        DownstreamContractObject.model_validate(
            contract.model_dump(mode="python") | {"fields": (contract.fields[0], duplicate_id)}
        )
    duplicate_name = _field("duplicate-name").model_copy(
        update={"field_name": contract.fields[0].field_name}
    )
    with pytest.raises(ValidationError, match="field names"):
        DownstreamContractObject.model_validate(
            contract.model_dump(mode="python") | {"fields": (contract.fields[0], duplicate_name)}
        )
    with pytest.raises(ValidationError, match="granted consent"):
        DownstreamContractObject.model_validate(
            contract.model_dump(mode="python")
            | {"consent": contract.consent.model_copy(update={"state": ConsentState.WITHHELD})}
        )
    with pytest.raises(ValidationError, match="supported status"):
        DownstreamContractObject.model_validate(
            contract.model_dump(mode="python")
            | {
                "support_decision": contract.support_decision.model_copy(
                    update={"status": SupportStatus.LIMITED}
                )
            }
        )
    with pytest.raises(ValidationError, match="versions"):
        DownstreamContractObject.model_validate(
            contract.model_dump(mode="python")
            | {"configuration": contract.configuration.model_copy(update={"version": "2.0.0"})}
        )
    with pytest.raises(ValidationError, match="ownership binding"):
        DownstreamContractObject.model_validate(
            contract.model_dump(mode="python")
            | {"fields": (contract.fields[0].model_copy(update={"owner": "Other owner"}),)}
        )
    with pytest.raises(ValidationError, match="contract evidence"):
        DownstreamContractObject.model_validate(
            contract.model_dump(mode="python")
            | {"evidence": (contract.evidence[0], contract.evidence[0])}
        )


def test_result_closure_rejects_digest_identity_provenance_findings_and_status_drift() -> None:
    engine = M1907Engine()
    result = engine.export(_request())
    result_data = result.model_dump(mode="python")
    with pytest.raises(ValidationError, match="request digest"):
        ProteotypeDownstreamExportResult.model_validate(
            result_data | {"request_digest": sha256_digest("wrong-request")}
        )
    with pytest.raises(ValidationError, match="identifier"):
        ProteotypeDownstreamExportResult.model_validate(result_data | {"result_id": "result.other"})
    with pytest.raises(ValidationError, match="provenance"):
        ProteotypeDownstreamExportResult.model_validate(
            result_data
            | {
                "provenance": result.provenance.model_copy(
                    update={"module_id": "GLIO-PROTEOGEN-M00-00"}
                )
            }
        )
    finding = result.findings[0]
    with pytest.raises(ValidationError, match="finding ids"):
        ProteotypeDownstreamExportResult.model_validate(
            result_data | {"findings": (finding, finding)}
        )
    with pytest.raises(ValidationError, match="result evidence"):
        ProteotypeDownstreamExportResult.model_validate(
            result_data | {"evidence": (result.evidence[0], result.evidence[0])}
        )
    with pytest.raises(ValidationError, match="exported result"):
        ProteotypeDownstreamExportResult.model_validate(result_data | {"contract": None})
    abstained = engine.export(_request(fields=(_field("unsupported"),)))
    with pytest.raises(ValidationError, match="abstained result"):
        ProteotypeDownstreamExportResult.model_validate(
            abstained.model_dump(mode="python") | {"contract": result.contract}
        )
    with pytest.raises(ValidationError, match="human review"):
        ProteotypeDownstreamExportResult.model_validate(
            abstained.model_dump(mode="python") | {"human_review_required": False}
        )
    assert result.status is ExportStatus.EXPORTED
