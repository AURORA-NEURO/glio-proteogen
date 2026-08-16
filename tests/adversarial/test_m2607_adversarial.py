"""Adversarial closure for M26-07 identity, replay, and parser boundaries."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from glio_proteogen.contracts.m26_07 import ControlProteinSubtypeChangeRequest
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c20_biomarker_panel.m26_07_change_control_rollback import (
    M2607ChangeControlService,
    M2607Plugin,
    M2607ReplayError,
    RollbackSubmission,
    ValidatedM2607Request,
    app,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_07_change_control_rollback import (
    plugin as plugin_module,
)
from tests.runtime.test_m2607_runtime import _request

HTTP_UNPROCESSABLE = 422


def test_plugin_rejects_duplicate_json_keys_before_model_validation() -> None:
    plugin = M2607Plugin()

    with pytest.raises(StrictJsonError):
        plugin.validate(RollbackSubmission(b'{"request_id":"a","request_id":"b"}'))


def test_plugin_rejects_malformed_json_without_partial_parse() -> None:
    with pytest.raises((StrictJsonError, ValueError)):
        M2607Plugin().validate(RollbackSubmission(b'{"request_id":'))


def test_forged_validated_request_token_is_rejected() -> None:
    request = _request()
    forged = ValidatedM2607Request(request, object())

    with pytest.raises(TypeError, match="validated request token"):
        M2607Plugin().run(forged)


def test_revalidation_cross_proposal_is_rejected_at_request_boundary() -> None:
    request = _request()
    record = request.revalidations[0].model_copy(update={"proposal_id": "proposal.other"})

    with pytest.raises(ValidationError, match="different proposal"):
        ControlProteinSubtypeChangeRequest.model_validate(
            request.model_dump(mode="python")
            | {"revalidations": (record.model_dump(mode="python"),)}
        )


def test_result_id_tamper_is_rejected_even_when_digest_shape_is_valid() -> None:
    service = M2607ChangeControlService()
    result = service.control(_request())
    tampered = result.model_copy(update={"result_id": "result.m2607.forged"})

    with pytest.raises(M2607ReplayError):
        service.verify(tampered)


def test_request_digest_tamper_is_rejected() -> None:
    service = M2607ChangeControlService()
    result = service.control(_request())
    tampered = result.model_copy(update={"request_digest": "sha256:" + "f" * 64})

    with pytest.raises(M2607ReplayError):
        service.verify(tampered)


def test_api_sanitizes_non_object_and_tampered_replay_errors() -> None:
    service = M2607ChangeControlService()
    result = service.control(_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})

    with TestClient(app) as client:
        non_object = client.post("/v1/modules/M26-07/validate", content=b"[]")
        replay = client.post(
            "/v1/modules/M26-07/verify",
            content=json.dumps({"result": tampered.model_dump(mode="json")}),
        )

    assert non_object.status_code == HTTP_UNPROCESSABLE
    assert replay.status_code == HTTP_UNPROCESSABLE
    assert "Traceback" not in replay.text


def test_plugin_strict_json_decode_is_called_once(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request()
    original = plugin_module.strict_json_loads  # type: ignore[attr-defined]
    calls = 0

    def counting_decode(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(plugin_module, "strict_json_loads", counting_decode)
    M2607Plugin().validate(RollbackSubmission(request.model_dump_json()))

    assert calls == 1
