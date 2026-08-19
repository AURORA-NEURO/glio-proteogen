"""Negative-path coverage for the M20-06 safety envelope."""

from __future__ import annotations

from typing import Any, cast

import pytest
from evals.m20_06.benchmark import main as benchmark_main
from evals.m20_06.benchmark import run_benchmark
from evals.m20_06.run import main as evaluator_main
from evals.m20_06.run import run
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m20_06 import (
    AdjudicateProteinSubtypeQueueRequest,
    QueueEntryState,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c20_biomarker_panel.m20_06_reviewer_discrepancy_adjudication import (
    AdjudicationSubmission,
    M2006AuthorizationError,
    M2006Engine,
    M2006Plugin,
    M2006ReplayError,
    M2006Service,
    cli_app,
    create_app,
    preflight_m2006_authorization,
)
from tests.contract.test_m20_06_adversarial import _entry, _request

_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_preflight_rejects_non_mapping_and_missing_controls() -> None:
    with pytest.raises(M2006AuthorizationError):
        preflight_m2006_authorization(object())
    with pytest.raises(M2006AuthorizationError):
        preflight_m2006_authorization({"context": {"references": {}}})

    class ExplodingContext:
        @property
        def context(self) -> object:
            raise RuntimeError

    with pytest.raises(M2006AuthorizationError):
        preflight_m2006_authorization(ExplodingContext())


def test_request_rejects_wrong_upstream_media_duplicate_ids_and_positions() -> None:
    request = _request()
    payload = request.model_dump(mode="python")
    payload["upstream_result"] = request.upstream_result.model_copy(
        update={"media_type": "application/json"}
    )
    with pytest.raises(ValidationError, match="provisional M20-05"):
        AdjudicateProteinSubtypeQueueRequest(**cast("Any", payload))
    payload = request.model_dump(mode="python")
    payload["entries"] = (request.entries[0], request.entries[0])
    with pytest.raises(ValidationError, match="discrepancy ids"):
        AdjudicateProteinSubtypeQueueRequest(**cast("Any", payload))


def test_service_denies_unsafe_context_and_replay_tampering() -> None:
    service = M2006Service()
    request = _request()
    denied = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": denied})}
    )
    with pytest.raises(M2006AuthorizationError):
        service.adjudicate(request.model_copy(update={"context": context}))
    result = service.adjudicate(request)
    assert result.record is not None
    with pytest.raises(M2006ReplayError, match="payload digest"):
        service.replay(
            result.model_copy(
                update={
                    "record": result.record.model_copy(update={"resolution_summary": "tampered"})
                }
            )
        )


def test_provenance_binds_unlisted_adjudication_evidence_and_replays() -> None:
    request = _request()
    entry = request.entries[0]
    reference = entry.evidence[0].reference.model_copy(
        update={"artifact_id": "unlisted-m2006-entry-evidence", "digest": "sha256:" + "9" * 64}
    )
    changed_entry = entry.model_copy(
        update={"evidence": (entry.evidence[0].model_copy(update={"reference": reference}),)}
    )
    changed = request.model_copy(update={"entries": (changed_entry, *request.entries[1:])})
    result = M2006Service().adjudicate(changed)

    assert reference.digest in result.provenance.input_digests
    assert M2006Service().replay(result) == result


def test_api_sanitizes_non_object_unknown_schema_and_denial() -> None:
    client = TestClient(create_app(M2006Service()))
    assert client.post("/v1/modules/M20-06/verify", content=b"[").status_code == (
        _HTTP_UNPROCESSABLE
    )
    assert client.post("/v1/modules/M20-06/verify", content=b"[]").status_code == (
        _HTTP_UNPROCESSABLE
    )
    assert client.get("/v1/modules/M20-06/schemas/unknown").status_code == _HTTP_NOT_FOUND
    request = _request()
    denied = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    denied_request = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(update={"support": denied})
                }
            )
        }
    )
    response = client.post(
        "/v1/modules/M20-06/validate", json=denied_request.model_dump(mode="json")
    )
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in response.text


def test_cli_sanitizes_bad_inputs_and_refuses_overwrite(tmp_path: Any) -> None:
    runner = CliRunner()
    assert runner.invoke(cli_app, ["export-schema", "unknown"]).exit_code != 0
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["validate", str(bad_request)]).exit_code != 0
    assert runner.invoke(cli_app, ["adjudicate", str(bad_request)]).exit_code != 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["verify", str(bad_result)]).exit_code != 0
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    output_path = tmp_path / "result.json"
    assert (
        runner.invoke(
            cli_app, ["adjudicate", str(request_path), "--output", str(output_path)]
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            cli_app, ["adjudicate", str(request_path), "--output", str(output_path)]
        ).exit_code
        != 0
    )


def test_plugin_rejects_bad_submission_and_json() -> None:
    plugin = M2006Plugin(M2006Service())
    with pytest.raises(TypeError, match="adjudication submission"):
        plugin.validate(_request())
    with pytest.raises((TypeError, ValueError, M2006AuthorizationError)):
        plugin.validate(AdjudicationSubmission(request=b"[]"))


def test_public_wrapper_plugin_and_evaluator_entrypoints(capsys: Any) -> None:
    request = _request()
    result = M2006Engine().adjudicate(request)
    plugin = M2006Plugin(M2006Service())
    assert plugin.replay(result).result_digest == result.result_digest
    report = run()
    assert report["status"] == "PASS"
    assert run_benchmark().passed is True
    benchmark_main([])
    evaluator_main([])
    assert "M20-06" in capsys.readouterr().out


def test_unresolved_and_not_evaluable_entries_never_record() -> None:
    request = _request()
    unresolved = _entry("unresolved", QueueEntryState.IN_REVIEW)
    request = request.model_copy(update={"entries": (request.entries[0], unresolved)})
    # The missing assignment path is intentionally exercised by the engine.
    result = M2006Engine().adjudicate(request)
    assert result.record is None
    assert result.abstention_reason is not None
