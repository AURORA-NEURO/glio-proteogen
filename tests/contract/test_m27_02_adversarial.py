"""Adversarial request, plugin, and replay boundaries for M27-02."""

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m27_02 import (
    ComplexActivityLineageResult,
    ResolveComplexActivityLineageRequest,
    result_payload_digest,
)
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c27_complex_activity.m27_02_lineage_service import (
    M2702LineageResolver,
    M2702Plugin,
    M2702Service,
)
from tests.runtime.test_m27_02_lineage import _request


def test_request_rejects_non_m2701_upstream_media_type() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="M27-01 search result"):
        ResolveComplexActivityLineageRequest.model_validate(
            request.model_copy(
                update={
                    "upstream_result": request.upstream_result.model_copy(
                        update={"media_type": "application/json"}
                    )
                }
            ),
            strict=True,
        )


def test_plugin_rejects_duplicate_json_keys_before_validation() -> None:
    plugin = M2702Plugin(M2702Service())
    with pytest.raises(StrictJsonError):
        plugin.validate(b'{"request_id":"one","request_id":"two"}')


def test_resigned_graph_manifest_tamper_is_rejected() -> None:
    result = M2702LineageResolver().resolve(_request())
    assert result.lineage_graph is not None
    tampered_graph = result.lineage_graph.model_copy(
        update={
            "reproducibility_bundle": result.lineage_graph.reproducibility_bundle.model_copy(
                update={"manifest_digest": "sha256:" + "f" * 64}
            )
        }
    )
    payload = result.model_dump(mode="python")
    payload["lineage_graph"] = tampered_graph
    payload["result_digest"] = result_payload_digest(payload)

    with pytest.raises(ValidationError, match="does not bind graph content"):
        ComplexActivityLineageResult.model_validate(payload, strict=True)
