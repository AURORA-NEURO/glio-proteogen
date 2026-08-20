from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from glio_proteogen.research.public_proteomics import (
    PDCClientConfig,
    PDCError,
    PDCMetadataClient,
    canonical_json_bytes,
    sha256_digest,
)

_ROOT = Path(__file__).parents[2]
_FIXTURE = _ROOT / "research" / "fixtures" / "pdc" / "pdc000204.metadata.json"
_MANIFEST = _ROOT / "research" / "fixtures" / "pdc" / "pdc000204.manifest.json"
_TEST_TIMEOUT = 2.0
_TEST_RESPONSE_CAP = 4096
_EXPECTED_CASES = 111

if TYPE_CHECKING:
    from collections.abc import Callable


def _transport(
    payload: bytes, response: bytes, status: int = 200, content_type: str = "application/json"
) -> Callable[[str, bytes, float, str, int], tuple[int, bytes, str]]:
    def call(
        url: str, body: bytes, timeout: float, user_agent: str, max_bytes: int
    ) -> tuple[int, bytes, str]:
        assert url == "https://pdc.cancer.gov/graphql"
        assert timeout == _TEST_TIMEOUT
        assert user_agent.startswith("test/")
        assert max_bytes == _TEST_RESPONSE_CAP
        assert json.loads(body) == json.loads(payload)
        return status, response, content_type

    return call


def test_fetches_fixture_with_typed_metadata_and_hashes() -> None:
    response = _FIXTURE.read_bytes()
    query = PDCMetadataClient.build_query("PDC000204")
    payload = canonical_json_bytes({"query": query})
    client = PDCMetadataClient(
        PDCClientConfig(
            timeout_seconds=_TEST_TIMEOUT,
            max_response_bytes=_TEST_RESPONSE_CAP,
            user_agent="test/research",
        ),
        _transport(payload, response),
    )
    snapshot = client.fetch("PDC000204", retrieved_at="2026-08-17T00:00:00Z")
    assert snapshot.metadata.study_name == "CPTAC GBM Discovery Study - Proteome"
    assert snapshot.metadata.cases_count == _EXPECTED_CASES
    assert snapshot.response_sha256 == sha256_digest(response)
    assert snapshot.query_sha256 == sha256_digest(query)
    assert snapshot.source_reference.sha256 == snapshot.response_sha256


def test_captured_manifest_binds_fixture_and_query() -> None:
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    canonical_fixture = canonical_json_bytes(fixture)
    query = PDCMetadataClient.build_query("PDC000204")
    assert manifest["fixture_file_bytes"] == _FIXTURE.stat().st_size
    assert manifest["fixture_canonical_json_sha256"] == sha256_digest(canonical_fixture)
    assert manifest["query_sha256"] == sha256_digest(query)


@pytest.mark.parametrize("study_id", ["PDC00020", "PDC000204x", "TCGA000204"])
def test_rejects_unbounded_or_non_pdc_study_ids(study_id: str) -> None:
    with pytest.raises(PDCError, match="study id"):
        PDCMetadataClient.build_query(study_id)


def test_rejects_graphql_errors_and_non_json() -> None:
    payload = canonical_json_bytes({"query": PDCMetadataClient.build_query("PDC000204")})
    client = PDCMetadataClient(
        PDCClientConfig(
            timeout_seconds=_TEST_TIMEOUT,
            max_response_bytes=_TEST_RESPONSE_CAP,
            user_agent="test/research",
        ),
        _transport(payload, b'{"errors":[{"message":"denied"}]}'),
    )
    with pytest.raises(PDCError, match="GraphQL"):
        client.fetch("PDC000204", retrieved_at="2026-08-17T00:00:00Z")
    non_json = PDCMetadataClient(
        PDCClientConfig(
            timeout_seconds=_TEST_TIMEOUT,
            max_response_bytes=_TEST_RESPONSE_CAP,
            user_agent="test/research",
        ),
        _transport(payload, b"{}", content_type="text/plain"),
    )
    with pytest.raises(PDCError, match="JSON"):
        non_json.fetch("PDC000204", retrieved_at="2026-08-17T00:00:00Z")


def test_config_restricts_endpoint_and_response_bound() -> None:
    with pytest.raises(PDCError, match="allow-listed"):
        PDCClientConfig(endpoint="http://example.invalid/graphql")
    with pytest.raises(PDCError, match="allow-listed"):
        PDCClientConfig(endpoint="https://user:p@pdc.cancer.gov/graphql")
    with pytest.raises(PDCError, match="allow-listed"):
        PDCClientConfig(endpoint="https://pdc.cancer.gov/graphql?access_token=secret")
    with pytest.raises(PDCError, match="allow-listed"):
        PDCClientConfig(endpoint="https://pdc.cancer.gov:444/graphql")
    with pytest.raises(PDCError, match="response cap"):
        PDCClientConfig(max_response_bytes=5 * 1024 * 1024)
    with pytest.raises(PDCError, match="timeout"):
        PDCClientConfig(timeout_seconds=True)  # type: ignore[arg-type]
    with pytest.raises(PDCError, match="response cap"):
        PDCClientConfig(max_response_bytes=True)  # type: ignore[arg-type]


def test_snapshot_rejects_untrusted_metadata_endpoint() -> None:
    response = _FIXTURE.read_bytes()
    query = PDCMetadataClient.build_query("PDC000204")
    payload = canonical_json_bytes({"query": query})
    snapshot = PDCMetadataClient(
        PDCClientConfig(
            timeout_seconds=_TEST_TIMEOUT,
            max_response_bytes=_TEST_RESPONSE_CAP,
            user_agent="test/research",
        ),
        _transport(payload, response),
    ).fetch("PDC000204", retrieved_at="2026-08-17T00:00:00Z")
    with pytest.raises(PDCError, match="allow-listed"):
        replace(snapshot, endpoint="https://evil.example/graphql")
