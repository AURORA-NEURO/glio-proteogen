"""Runtime, replay and strict-plugin tests for M19-07."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m19_07 import ExportFindingCode, ExportStatus
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_07_downstream_typed_export import (
    M1907AuthorizationError,
    M1907Engine,
    M1907Plugin,
)

from .test_m19_07_deep import _field, _request


def test_engine_exports_and_replays_canonical_result() -> None:
    engine = M1907Engine()
    result = engine.export(_request())
    assert result.status is ExportStatus.EXPORTED
    assert result.contract is not None
    assert result.contract.parent_target == "proteotype"
    assert result.result_id.removeprefix("result.") == result.request_digest.removeprefix(
        "sha256:"
    )
    assert engine.verify(result) == result


def test_engine_abstains_for_unsupported_declared_field() -> None:
    engine = M1907Engine()
    result = engine.export(_request(fields=(_field("unsupported"),)))
    assert result.status is ExportStatus.ABSTAINED
    assert result.contract is None
    assert result.human_review_required
    assert result.support_decision.status.value == "unsupported"
    assert any(item.code is ExportFindingCode.UPSTREAM_UNSUPPORTED for item in result.findings)
    assert engine.verify(result) == result


def test_preflight_fails_closed_for_missing_or_wrong_control() -> None:
    request = _request().model_dump(mode="python")
    context = request["context"]
    references = context["references"]
    references["support"]["state"] = "rejected"
    with pytest.raises(M1907AuthorizationError, match="support"):
        M1907Engine().export(request)


def test_plugin_issues_opaque_token_and_rejects_raw_run() -> None:
    plugin = M1907Plugin()
    request = _request()
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M19-07"
    token = plugin.validate(canonical_json_bytes(request.model_dump(mode="json")))
    result = plugin.run(token)
    assert result.status is ExportStatus.EXPORTED
    model_token = plugin.validate(request)
    assert plugin.run(model_token) == result
    assert plugin.verify(canonical_json_bytes(result.model_dump(mode="json"))) == result
    with pytest.raises(TypeError):
        plugin.run(request)  # type: ignore[arg-type]


def test_verify_rejects_tampered_digest() -> None:
    engine = M1907Engine()
    result = engine.export(_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    with pytest.raises(ValueError, match=r"result (is invalid|digest mismatch)"):
        engine.verify(tampered, replay=False)
