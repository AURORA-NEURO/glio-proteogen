"""Adversarial closure and hostile-boundary coverage for M11-08."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m11_08 import (
    AssembleVariantPeptideMechanismDossierRequest,
    MechanismDossierStatus,
    MechanismEvidenceDossier,
    VariantPeptideMechanismDossierResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c11_protein_native_subtype.m11_08_mechanism_evidence_dossier import (
    M1108AuthorizationError,
    M1108MechanismEvidenceDossierPlugin,
    M1108MechanismEvidenceDossierService,
    assemble_mechanism_dossier,
    preflight_m1108_authorization,
    verify_mechanism_dossier_result,
)
from tests.contract.test_m11_08_runtime import request


def _dossier_dict() -> dict[str, Any]:
    result = assemble_mechanism_dossier(request())
    assert result.dossier is not None
    return result.dossier.model_dump(mode="python")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_source", "source ids must be unique"),
        ("duplicate_artifact", "source artifacts must be unique"),
        ("duplicate_assumption", "assumption ids must be unique"),
        ("duplicate_link", "link ids must be unique"),
        ("duplicate_counter", "counter-evidence ids must be unique"),
        ("duplicate_route", "validation route ids must be unique"),
        ("duplicate_step", "reconstruction steps must have unique ordered sequences"),
        ("unknown_counter_link", "counter-evidence references an unknown link"),
        ("unknown_predecessor", "mechanism link references an unknown predecessor"),
        ("wrong_media", "dossier must bind"),
    ],
)
def test_dossier_closure_rejects_adversarial_mutations(mutation: str, message: str) -> None:
    data = _dossier_dict()
    if mutation == "duplicate_source":
        data["sources"][1]["source_id"] = data["sources"][0]["source_id"]
    elif mutation == "duplicate_artifact":
        data["sources"][1]["artifact"]["artifact_id"] = data["sources"][0]["artifact"][
            "artifact_id"
        ]
    elif mutation == "duplicate_assumption":
        data["assumptions"] = (*data["assumptions"], data["assumptions"][0])
    elif mutation == "duplicate_link":
        data["links"] = (*data["links"], data["links"][0])
    elif mutation == "duplicate_counter":
        data["counter_evidence"] = (*data["counter_evidence"], data["counter_evidence"][0])
    elif mutation == "duplicate_route":
        data["validation_routes"] = (*data["validation_routes"], data["validation_routes"][0])
    elif mutation == "duplicate_step":
        data["reconstruction_steps"] = (
            *data["reconstruction_steps"],
            data["reconstruction_steps"][0],
        )
    elif mutation == "unknown_counter_link":
        data["counter_evidence"][0]["challenges_link_ids"] = ("link.unknown",)
    elif mutation == "unknown_predecessor":
        data["links"][1]["predecessor_ids"] = ("link.unknown",)
    else:
        data["upstream_result"]["media_type"] = "application/json"
    with pytest.raises(ValueError, match=message):
        MechanismEvidenceDossier.model_validate(data, strict=True)


@pytest.mark.parametrize(
    "field",
    [
        "upstream_result",
        "source_artifacts",
        "assumptions",
        "links",
        "counter_evidence",
        "validation_routes",
        "reconstruction_steps",
    ],
)
def test_request_contract_rejects_duplicate_or_wrong_bindings(field: str) -> None:
    data = request().model_dump(mode="python")
    if field == "upstream_result":
        data[field]["media_type"] = "application/json"
    elif field == "source_artifacts":
        data[field][1]["source_id"] = data[field][0]["source_id"]
    elif field == "assumptions":
        data[field] = (*data[field], data[field][0])
    elif field == "links":
        data[field][1]["predecessor_ids"] = ("link.unknown",)
    elif field == "counter_evidence":
        data[field][0]["challenges_link_ids"] = ("link.unknown",)
    elif field == "validation_routes":
        data[field] = (*data[field], data[field][0])
    else:
        data[field] = (*data[field], data[field][0])
    with pytest.raises(ValidationError):
        AssembleVariantPeptideMechanismDossierRequest.model_validate(data, strict=True)


@pytest.mark.parametrize(
    "mutation",
    ["artifact", "link", "counter", "route", "step"],
)
def test_request_contract_rejects_duplicate_nested_identifiers(mutation: str) -> None:
    data = request().model_dump(mode="python")
    if mutation == "artifact":
        data["source_artifacts"][1]["artifact"]["artifact_id"] = data["source_artifacts"][0][
            "artifact"
        ]["artifact_id"]
    elif mutation == "link":
        data["links"][1]["link_id"] = data["links"][0]["link_id"]
    elif mutation == "counter":
        data["counter_evidence"][0]["counter_evidence_id"] = "counter.discordance"
        data["counter_evidence"] = (*data["counter_evidence"], data["counter_evidence"][0])
    elif mutation == "route":
        data["validation_routes"] = (*data["validation_routes"], data["validation_routes"][0])
    else:
        data["reconstruction_steps"] = (
            *data["reconstruction_steps"],
            data["reconstruction_steps"][0],
        )
    with pytest.raises(ValidationError):
        AssembleVariantPeptideMechanismDossierRequest.model_validate(data, strict=True)


def test_invalid_inputs_and_hostile_preflight_fail_closed() -> None:
    service = M1108MechanismEvidenceDossierService()
    with pytest.raises(M1108AuthorizationError):
        service.execute(object())
    with pytest.raises(ValueError, match="request does not match"):
        service.validate_request({"context": request().context})

    class Candidate(BaseModel):
        context: object

    with pytest.raises(TypeError):
        service.execute(Candidate(context=request().context))

    class Explosive(BaseModel):
        context: object

        def model_dump(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            raise RuntimeError

    with pytest.raises(M1108AuthorizationError):
        preflight_m1108_authorization(Explosive(context=request().context))


def test_plugin_strict_json_failure_and_replay_invalid_object() -> None:
    plugin = M1108MechanismEvidenceDossierPlugin(M1108MechanismEvidenceDossierService())
    payload = request().model_dump(mode="json")
    payload.pop("request_id")
    with pytest.raises(ValueError, match="request does not match"):
        plugin.validate(json.dumps(payload))
    with pytest.raises(StrictJsonError):
        plugin.validate('{"request_id":"one","request_id":"two"}')
    assert not verify_mechanism_dossier_result(None)
    assert not verify_mechanism_dossier_result({"result_digest": "sha256:" + "a" * 64})


def test_canonical_request_projection_accepts_plain_mapping() -> None:
    typed = request()
    assert canonical_request_digest(typed.model_dump(mode="json")) == canonical_request_digest(
        typed
    )


def test_result_contract_rejects_digest_id_and_nested_tampering() -> None:
    result = assemble_mechanism_dossier(request())
    data = result.model_dump(mode="python")
    data["request_digest"] = "sha256:" + "b" * 64
    with pytest.raises(ValueError, match="request digest"):
        VariantPeptideMechanismDossierResult.model_validate(data, strict=True)

    data = result.model_dump(mode="python")
    data["result_id"] = "result.m1108.tampered"
    with pytest.raises(ValueError, match="result identifier"):
        VariantPeptideMechanismDossierResult.model_validate(data, strict=True)

    data = result.model_dump(mode="python")
    data["dossier"] = None
    with pytest.raises(ValueError, match="ready result"):
        VariantPeptideMechanismDossierResult.model_validate(data, strict=True)

    data = result.model_dump(mode="python")
    data["status"] = MechanismDossierStatus.ABSTAINED
    with pytest.raises(ValueError, match="abstained result"):
        VariantPeptideMechanismDossierResult.model_validate(data, strict=True)

    data = result.model_dump(mode="python")
    data["provenance"]["module_id"] = "GLIO-PROTEOGEN-M11-07"
    with pytest.raises(ValueError, match="provenance must identify"):
        VariantPeptideMechanismDossierResult.model_validate(data, strict=True)

    data = result.model_dump(mode="python")
    data["provenance"]["consent_state"] = ConsentState.WITHHELD
    with pytest.raises(ValueError, match="granted consent"):
        VariantPeptideMechanismDossierResult.model_validate(data, strict=True)

    data = result.model_dump(mode="python")
    data["findings"] = (*data["findings"], data["findings"][0])
    with pytest.raises(ValueError, match="findings must be unique"):
        VariantPeptideMechanismDossierResult.model_validate(data, strict=True)

    data = result.model_dump(mode="python")
    data["result_digest"] = "sha256:" + "c" * 64
    with pytest.raises(ValueError, match="result digest"):
        VariantPeptideMechanismDossierResult.model_validate(data, strict=True)
