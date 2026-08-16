"""Deep hostile-input and boundary tests for M18-07."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import ConsentState, SupportStatus
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c18_spatial_proteomics_projection.m18_07_downstream_typed_export import (  # noqa: E501
    M1807AuthorizationError,
    M1807Engine,
    M1807ExportError,
    M1807Plugin,
    M1807ReplayError,
    M1807Service,
)
from tests.contract.test_m18_07_deep import _artifact, _request


def test_upstream_media_boundary_cannot_be_reinterpreted() -> None:
    request = _request().model_copy(
        update={
            "upstream_result": _artifact("wrong-upstream", media_type="application/json"),
        }
    )
    with pytest.raises(M1807ExportError, match="invalid"):
        M1807Engine().export(request)


def test_source_artifact_binding_is_not_optional() -> None:
    request = _request()
    request = request.model_copy(update={"source_artifacts": (_artifact("source-only"),)})
    with pytest.raises(M1807ExportError, match="invalid"):
        M1807Service().execute(request)


def test_locked_field_version_cannot_drift_from_configuration() -> None:
    request = _request()
    field = request.fields[0].model_copy(update={"field_version": "2.0.0"})
    with pytest.raises(M1807ExportError, match="invalid"):
        M1807Engine().export(request.model_copy(update={"fields": (field,)}))


def test_signature_payload_tampering_is_rejected_by_replay() -> None:
    engine = M1807Engine()
    result = engine.export(_request())
    assert result.contract is not None
    tampered_contract = result.contract.model_copy(
        update={
            "signature": result.contract.signature.model_copy(
                update={"signed_payload_digest": sha256_digest("tampered")}
            )
        }
    )
    with pytest.raises(M1807ReplayError, match=r"invalid|replay"):
        engine.verify(result.model_copy(update={"contract": tampered_contract}))


def test_signature_digest_tampering_is_rejected_by_replay() -> None:
    engine = M1807Engine()
    result = engine.export(_request())
    assert result.contract is not None
    tampered_contract = result.contract.model_copy(
        update={
            "signature": result.contract.signature.model_copy(
                update={"signature_digest": sha256_digest("tampered-signature")}
            )
        }
    )
    with pytest.raises(M1807ReplayError, match=r"invalid|replay"):
        engine.verify(result.model_copy(update={"contract": tampered_contract}))


def test_withheld_consent_is_rejected_before_export_fields_are_read() -> None:
    request = _request()
    references = request.context.references
    withheld = references.consent.model_copy(update={"state": ConsentState.WITHHELD})
    candidate = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={"references": references.model_copy(update={"consent": withheld})}
            )
        }
    )
    with pytest.raises(M1807AuthorizationError, match="consent"):
        M1807Engine().export(candidate)


def test_identity_and_consent_inference_terms_abstain() -> None:
    request = _request()
    field = request.fields[0].model_copy(
        update={
            "field_name": "identity_inference_field",
            "documentation": "Consent inference is prohibited in this export.",
        }
    )
    result = M1807Engine().export(request.model_copy(update={"fields": (field,)}))
    assert result.contract is None
    assert result.status.value == "abstained"


def test_plugin_rejects_duplicate_json_keys_and_forged_token() -> None:
    plugin = M1807Plugin(M1807Service())
    with pytest.raises(StrictJsonError, match="duplicate"):
        plugin.validate('{"context": {}, "context": {}}')
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]


def test_frozen_request_and_contract_objects_cannot_be_mutated() -> None:
    request = _request()
    with pytest.raises(ValidationError):
        request.request_id = "attacker"  # type: ignore[misc]
    result = M1807Engine().export(request)
    assert result.contract is not None
    with pytest.raises(ValidationError):
        result.contract.parent_target = "kinase"  # type: ignore[misc, assignment]


def test_abstained_support_never_becomes_a_negative_export() -> None:
    request = _request().model_copy(
        update={
            "support_decision": _request().support_decision.model_copy(
                update={"status": SupportStatus.UNSUPPORTED}
            )
        }
    )
    result = M1807Engine().export(request)
    assert result.contract is None
    assert result.support_decision.status is SupportStatus.UNSUPPORTED
    assert result.findings
