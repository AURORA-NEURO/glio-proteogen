"""Black-box authority checks for every mounted research replay endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest
from fastapi.testclient import TestClient

from glio_proteogen.adapters.api import create_app

if TYPE_CHECKING:
    from collections.abc import Iterator

_HTTP_OK: Final = 200
_FORGED_PROFILE_DIGEST: Final = "sha256:" + "e" * 64
_RESEARCH_PREFIXES: Final = (
    "/v1/research/proteogenomic-state",
    "/v1/research/gbm-proteomic-axes",
    "/v1/research/neftel-protein-programs",
    "/v1/research/gbm-master-kinases",
    "/v1/research/gbm-functional-proteotype",
    "/v1/research/gbm-rna-purity",
    "/v1/research/longitudinal-gbm",
    "/v1/research/longitudinal-gbm-phospho",
    "/v1/research/longitudinal-gbm-kinase-transition",
    "/v1/research/longitudinal-gbm-reactome-transition",
    "/v1/research/longitudinal-gbm-complex-transition",
    "/v2/research/modules/m11/protein-native-subtype",
    "/v2/research/modules/m14/microenvironment-protein-programs",
)


@pytest.fixture(scope="module")
def mounted_client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    database_path = tmp_path_factory.mktemp("research-verify-authority") / "events.sqlite3"
    with TestClient(create_app(database_path)) as client:
        yield client


@pytest.mark.parametrize("prefix", _RESEARCH_PREFIXES, ids=lambda value: value.rsplit("/", 1)[-1])
def test_forged_replay_cannot_control_authoritative_profile_header(
    mounted_client: TestClient,
    prefix: str,
) -> None:
    profile = mounted_client.get(f"{prefix}/profile")
    demo = mounted_client.get(f"{prefix}/demo")
    assert profile.status_code == _HTTP_OK
    assert demo.status_code == _HTTP_OK

    authoritative_digest = profile.headers["x-glio-profile-digest"]
    request = demo.json()
    analysis = mounted_client.post(f"{prefix}/analyze", json=request)
    assert analysis.status_code == _HTTP_OK

    forged_result = analysis.json()
    forged_result["profile_digest"] = _FORGED_PROFILE_DIGEST
    provenance = forged_result.get("provenance")
    if isinstance(provenance, dict) and "profile_digest" in provenance:
        provenance["profile_digest"] = _FORGED_PROFILE_DIGEST
    verification = mounted_client.post(
        f"{prefix}/verify",
        json={"request": request, "result": forged_result},
    )

    assert verification.status_code == _HTTP_OK
    assert verification.json()["verified"] is False
    assert verification.json()["profile_digest_match"] is False
    assert verification.headers["x-glio-profile-digest"] == authoritative_digest
    assert verification.headers["x-glio-profile-digest"] != _FORGED_PROFILE_DIGEST
