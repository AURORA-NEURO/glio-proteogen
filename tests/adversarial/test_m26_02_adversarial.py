"""Adversarial closure for mappings, boundaries, abstention, and replay."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m26_02 import (
    M2602_MAX_CANONICAL_REQUEST_BYTES,
    M2602_MAX_CANONICAL_RESULT_BYTES,
    BuildProteinSubtypeLineageRequest,
    LineageEdge,
    LineageRelation,
)
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service import (
    LineageAuthorizationError,
    M2602LineagePlugin,
    M2602LineageService,
)
from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service import (
    cli as cli_module,
)
from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service.cli import app
from tests.runtime.test_m26_02_runtime import _artifact, _request

_ABSTENTION_EXIT_CODE = 3


def test_contract_forbids_unknown_fields_and_mutation() -> None:
    payload = _request().model_dump(mode="python")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        BuildProteinSubtypeLineageRequest.model_validate(payload, strict=True)
    with pytest.raises(ValidationError):
        _request().context.actor_id = "attacker"  # type: ignore[misc]


def test_wrong_upstream_media_is_not_silently_reinterpreted() -> None:
    candidate = _request().model_copy(
        update={"upstream_registry_artifact": _artifact("m2601", "application/octet-stream")}
    )
    with pytest.raises(ValidationError, match="M26-01 media type"):
        M2602LineageService().execute(candidate)


def test_missing_upstream_source_is_not_accepted() -> None:
    upstream = _request().upstream_registry_artifact
    candidate = _request().model_copy(update={"source_artifacts": (_artifact("different-source"),)})
    assert upstream not in candidate.source_artifacts
    with pytest.raises(ValidationError, match="included in source artifacts"):
        M2602LineageService().execute(candidate)


def test_duplicate_edge_and_unknown_edge_are_rejected() -> None:
    request = _request()
    duplicate = request.model_copy(update={"edges": (*request.edges, request.edges[0])})
    with pytest.raises(ValidationError, match="edge ids must be unique"):
        M2602LineageService().execute(duplicate)
    unknown = request.model_copy(
        update={
            "edges": (
                *request.edges[:-1],
                LineageEdge(
                    edge_id="edge-unknown",
                    parent_node_id="node-6",
                    child_node_id="missing-node",
                    relation=LineageRelation.DERIVED_FROM,
                ),
            )
        }
    )
    with pytest.raises(ValidationError, match="unknown node"):
        M2602LineageService().execute(unknown)


def test_duplicate_node_ids_are_rejected_before_engine() -> None:
    request = _request()
    candidate = request.model_copy(update={"nodes": (*request.nodes, request.nodes[0])})
    with pytest.raises(ValidationError, match="node ids must be unique"):
        M2602LineageService().execute(candidate)


def test_plugin_rejects_duplicate_keys_and_unvalidated_tokens() -> None:
    plugin = M2602LineagePlugin(M2602LineageService())
    with pytest.raises(StrictJsonError, match="duplicate"):
        plugin.validate('{"context": {}, "context": {}}')
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M26-02"
    with pytest.raises(LineageAuthorizationError):
        plugin.validate(object())


def test_replay_rejects_graph_tampering() -> None:
    service = M2602LineageService()
    result = service.execute(_request())
    assert result.lineage_graph is not None
    tampered_graph = result.lineage_graph.model_copy(update={"graph_digest": "sha256:" + "e" * 64})
    tampered = result.model_copy(update={"lineage_graph": tampered_graph})
    with pytest.raises(ValidationError):
        service.verify(tampered)


def test_abstention_never_writes_cli_output(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(_request(graph_digest="sha256:" + "f" * 64).model_dump(mode="json")),
        encoding="utf-8",
    )
    output_path = tmp_path / "abstained.json"
    result = CliRunner().invoke(
        app,
        ["construct", str(request_path), "--output", str(output_path)],
    )
    assert result.exit_code == _ABSTENTION_EXIT_CODE
    assert not output_path.exists()


@pytest.mark.parametrize(
    ("helper", "limit"),
    [
        (cli_module._validated_request, M2602_MAX_CANONICAL_REQUEST_BYTES),
        (cli_module._validated_result, M2602_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_cli_rejects_oversized_json_before_reading(
    tmp_path: Path,
    helper: Callable[[Path], object],
    limit: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b"{" + b" " * limit + b"}")
    read_called = False

    def fail_if_read(_path: Path) -> bytes:
        nonlocal read_called
        read_called = True
        raise AssertionError(  # noqa: TRY003
            "oversized CLI input must be rejected before read_bytes"
        )

    monkeypatch.setattr(Path, "read_bytes", fail_if_read)
    with pytest.raises(ValueError, match="bounded JSON byte limit"):
        helper(path)
    assert not read_called
