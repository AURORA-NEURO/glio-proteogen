"""Negative-path coverage for the M21-01 safety envelope."""

from __future__ import annotations

from typing import Any, cast

import pytest
from evals.m21_01.fixture import build_request, pending_request
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m21_01 import (
    ComplexActivityReferenceTruthResult,
    CurateComplexActivityReferenceTruthRequest,
    ReferenceTruthPackage,
    package_lock_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c21_reference_material.m21_01_reference_truth_benchmark_curator import (
    M2101AuthorizationError,
    M2101Plugin,
    M2101Service,
    ReferenceTruthSubmission,
    cli_app,
    create_app,
    preflight_m2101_authorization,
)

_REQUEST_ADAPTER = TypeAdapter(CurateComplexActivityReferenceTruthRequest)
_HTTP_UNPROCESSABLE = 422
_HTTP_NOT_FOUND = 404


def test_preflight_rejects_malformed_mapping_without_traversal() -> None:
    with pytest.raises(M2101AuthorizationError):
        preflight_m2101_authorization({"context": {"references": {}}})


def test_preflight_rejects_wrong_control_state() -> None:
    request = build_request()
    support = request.context.references.support.model_copy(update={"state": "rejected"})
    references = request.context.references.model_copy(update={"support": support})
    denied = request.context.model_copy(update={"references": references})
    with pytest.raises(M2101AuthorizationError):
        M2101Service().execute(request.model_copy(update={"context": denied}))


def test_request_context_id_mismatch_is_not_accepted() -> None:
    request = build_request()
    context = request.context.model_copy(update={"request_id": "different-request"})
    payload = request.model_dump(mode="python")
    payload["context"] = context
    with pytest.raises(ValidationError, match="context request id"):
        _REQUEST_ADAPTER.validate_python(cast("Any", payload), strict=True)


def test_challenge_kind_and_flag_cannot_diverge() -> None:
    request = build_request()
    reference = request.references[0].model_copy(update={"challenge_set": True})
    payload = request.model_dump(mode="python")
    payload["references"] = (reference, request.references[1])
    with pytest.raises(ValidationError, match="challenge-set kind"):
        _REQUEST_ADAPTER.validate_python(cast("Any", payload), strict=True)


def test_locked_package_rejects_tampered_challenge_ids() -> None:
    result = M2101Service().execute(build_request())
    assert result.package is not None
    tampered = result.package.model_copy(update={"challenge_set_ids": ("unknown",)})
    with pytest.raises(ValidationError, match="challenge set ids"):
        ReferenceTruthPackage(**cast("Any", tampered.model_dump(mode="python")))


def test_locked_package_digest_changes_when_content_changes() -> None:
    result = M2101Service().execute(build_request())
    assert result.package is not None
    changed = result.package.model_copy(update={"package_id": "different-package"})
    assert package_lock_digest(changed) != package_lock_digest(result.package)


def test_result_digest_tamper_is_rejected() -> None:
    result = M2101Service().execute(build_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    with pytest.raises(ValidationError, match="result digest"):
        ComplexActivityReferenceTruthResult(**cast("Any", tampered.model_dump(mode="python")))


def test_plugin_rejects_unwrapped_request_and_bad_json() -> None:
    plugin = M2101Plugin(M2101Service())
    with pytest.raises(TypeError, match="reference-truth submission"):
        plugin.validate(build_request())
    with pytest.raises((ValueError, TypeError)):
        plugin.validate(ReferenceTruthSubmission(request=b"[]"))


def test_api_sanitizes_invalid_json_and_unknown_schema() -> None:
    client = TestClient(create_app(M2101Service()))
    invalid = client.post("/v1/modules/M21-01/validate", content=b"[]")
    unknown = client.get("/v1/modules/M21-01/schemas/unknown")
    assert invalid.status_code == _HTTP_UNPROCESSABLE
    assert unknown.status_code == _HTTP_NOT_FOUND
    assert "Traceback" not in invalid.text


def test_cli_abstention_emits_result_and_nonzero_review_exit(tmp_path: Any) -> None:
    path = tmp_path / "pending.json"
    path.write_bytes(canonical_json_bytes(pending_request()))
    result_path = tmp_path / "pending-result.json"
    completed = CliRunner().invoke(
        cli_app,
        ["curate", str(path), "--output", str(result_path)],
    )
    assert completed.exit_code == 1
    assert result_path.exists()
