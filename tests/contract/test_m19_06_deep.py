"""Adversarial claims-ceiling closure for M19-06."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m19_06 import (
    AdjudicateProteotypeQueueRequest,
    ProteotypeAdjudicationResult,
    QueueFindingCode,
    QueueResultStatus,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import EvidenceReference
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_06_reviewer_adjudication import (
    M1906Engine,
)
from tests.contract.test_m19_06_provisional import _artifact, _request

if TYPE_CHECKING:
    from pathlib import Path

_BAD_CLAIM: Final = "kinase activity claim"
_HTTP_OK: Final = 200


def _bad_evidence() -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact("evidence.prohibited"),
            role="evidence",
            claim=_BAD_CLAIM,
        ),
    )


def _request_with_surface(surface: str) -> AdjudicateProteotypeQueueRequest:
    request = _request()
    if surface == "entry.description":
        entry = request.entries[0].model_copy(update={"description": _BAD_CLAIM})
        return request.model_copy(update={"entries": (entry,)})
    if surface == "configuration.evidence":
        configuration = request.configuration.model_copy(update={"evidence": _bad_evidence()})
        return request.model_copy(update={"configuration": configuration})
    if surface == "assignment.reviewer_role":
        assignment = request.assignments[0].model_copy(update={"reviewer_role": _BAD_CLAIM})
        return request.model_copy(update={"assignments": (assignment,)})
    if surface == "assignment.rationale":
        assignment = request.assignments[0].model_copy(update={"rationale": _BAD_CLAIM})
        return request.model_copy(update={"assignments": (assignment,)})
    if surface == "entry.evidence":
        entry = request.entries[0].model_copy(update={"evidence": _bad_evidence()})
        return request.model_copy(update={"entries": (entry,)})
    if surface == "assignment.evidence":
        assignment = request.assignments[0].model_copy(update={"evidence": _bad_evidence()})
        return request.model_copy(update={"assignments": (assignment,)})
    raise AssertionError


@pytest.mark.parametrize(
    "surface",
    [
        "entry.description",
        "configuration.evidence",
        "assignment.reviewer_role",
        "assignment.rationale",
        "entry.evidence",
        "assignment.evidence",
    ],
)
def test_prohibited_caller_claims_abstain_without_record(surface: str) -> None:
    result = M1906Engine().adapt(_request_with_surface(surface))
    assert result.status is QueueResultStatus.ABSTAINED
    assert result.record is None
    assert result.support_decision.status.value == "review_required"
    assert result.abstention_reason == (
        "M19-06 abstained because caller-controlled text exceeds the claims ceiling."
    )
    assert any(
        finding.code is QueueFindingCode.PROHIBITED_CLAIM_BOUNDARY for finding in result.findings
    )


def test_api_cli_parity_preserves_claim_boundary_abstention(tmp_path: Path) -> None:
    request = _request_with_surface("entry.description")
    payload = canonical_json_bytes(request.model_dump(mode="json"))
    request_path = tmp_path / "request.json"
    request_path.write_bytes(payload)

    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M19-06/adjudication",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["m19-06-adjudication", "adjudicate", str(request_path)],
    )

    assert response.status_code == _HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = ProteotypeAdjudicationResult.model_validate_json(response.content, strict=True)
    cli_result = ProteotypeAdjudicationResult.model_validate_json(cli.stdout, strict=True)
    assert api_result == cli_result
    assert api_result.status is QueueResultStatus.ABSTAINED
    assert api_result.record is None


def test_schema_metadata_publishes_claim_ceiling() -> None:
    metadata = cast(
        "dict[str, object]",
        contract_json_schemas()["request"]["x-glio-contract"],
    )
    assert metadata["prohibitedClaimTerms"]
