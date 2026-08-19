"""Deep adversarial coverage for M25-02 replay and safety boundaries."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m25_02 import (
    GenerateProteotypeSyntheticTruthRequest,
    GenerationStatus,
    GeneratorFinding,
    GeneratorFindingCode,
    ProteotypeSyntheticTruthResult,
    SyntheticTruthCorpus,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import SupportStatus, UpstreamDecisionState
from glio_proteogen.kernel.strict_json import StrictJsonError, StrictJsonErrorCode
from glio_proteogen.modules.c21_reference_material import (
    m25_02_synthetic_truth_simulation_generator as m2402,
)
from tests.contract.test_m25_02_deep import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = HTTPStatus.OK
_HTTP_UNPROCESSABLE = HTTPStatus.UNPROCESSABLE_ENTITY
_EXPECTED_CASE_COUNT = 2


def test_plugin_rejects_duplicate_keys_before_contract_parse() -> None:
    plugin = m2402.M2502Plugin(m2402.M2502Service())
    duplicate = b'{"request_id":"first","request_id":"second"}'
    with pytest.raises(StrictJsonError) as error:
        plugin.validate(m2402.SyntheticTruthSubmission(duplicate))
    assert error.value.code is StrictJsonErrorCode.DUPLICATE_KEY


def test_plugin_rejects_unwrapped_and_unvalidated_execution() -> None:
    plugin = m2402.M2502Plugin(m2402.M2502Service())
    request = _request()
    with pytest.raises(TypeError, match="synthetic-truth submission"):
        plugin.validate(request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", request))


def test_hostile_mapping_fails_closed_before_material_traversal() -> None:
    class ExplodingMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError("hostile mapping")  # noqa: TRY003

    with pytest.raises(m2402.M2502AuthorizationError):
        m2402.preflight_m2502_authorization(ExplodingMapping())
    with pytest.raises(m2402.M2502AuthorizationError):
        m2402.M2502Service().validate_request(ExplodingMapping())


def test_service_rejects_unknown_fields_and_wrong_upstream_media() -> None:
    request = _request()
    payload = request.model_dump(mode="python")
    payload["unexpected"] = "must be rejected"
    with pytest.raises(ValidationError):
        m2402.M2502Service().validate_request(payload)

    wrong_media = request.model_copy(
        update={
            "upstream_result": request.upstream_result.model_copy(
                update={"media_type": "application/json"}
            )
        }
    )
    with pytest.raises(ValidationError, match="M25-01"):
        m2402.M2502Service().validate_request(wrong_media)


def test_request_closure_rejects_context_and_source_drift() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="context"):
        GenerateProteotypeSyntheticTruthRequest.model_validate(
            request.model_dump(mode="python")
            | {"context": request.context.model_copy(update={"request_id": "other"})},
            strict=True,
        )
    with pytest.raises(ValidationError, match="bind the declared upstream"):
        GenerateProteotypeSyntheticTruthRequest.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (request.source_artifacts[1],)},
            strict=True,
        )


def test_result_replay_rejects_each_digest_identity_tamper() -> None:
    service = m2402.M2502Service()
    result = service.generate(_request())
    assert result.request_digest == canonical_request_digest(result.request)
    assert result.result_id == result_identifier(result.request_digest)
    tampered_values = (
        {"request_digest": "sha256:" + "0" * 64},
        {"result_id": "result.forged"},
        {"result_digest": "sha256:" + "f" * 64},
    )
    for update in tampered_values:
        with pytest.raises(m2402.M2502ReplayError):
            service.verify_replay(result.model_copy(update=update))


def test_result_replay_rejects_request_mutation() -> None:
    service = m2402.M2502Service()
    result = service.generate(_request())
    changed_request = result.request.model_copy(update={"request_id": "changed"})
    with pytest.raises(m2402.M2502ReplayError, match="request digest"):
        service.verify_replay(result.model_copy(update={"request": changed_request}))


def test_result_replay_rejects_recomputed_digest_for_forged_corpus() -> None:
    service = m2402.M2502Service()
    result = service.generate(_request())
    assert result.corpus is not None
    assert result.manifest is not None
    forged_case = result.corpus.cases[0].model_copy(update={"truth_values": ("forged",) * 3})
    forged_cases = (forged_case, *result.corpus.cases[1:])
    forged_manifest = result.manifest.model_copy(
        update={
            "reproducibility_digest": sha256_digest(
                {"cases": forged_cases, "configuration": result.manifest.configuration}
            )
        }
    )
    forged_corpus = result.corpus.model_copy(
        update={"cases": forged_cases, "manifest": forged_manifest}
    )
    payload = result.model_dump(mode="python")
    payload["corpus"] = forged_corpus
    payload["manifest"] = forged_manifest
    provisional = ProteotypeSyntheticTruthResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(provisional)
    forged = ProteotypeSyntheticTruthResult.model_validate(payload, strict=True)
    with pytest.raises(m2402.M2502ReplayError, match="output mismatch"):
        service.verify_replay(forged)


def test_contract_rejects_self_rehashed_stale_reproducibility_digest() -> None:
    result = m2402.M2502Service().generate(_request())
    assert result.corpus is not None
    assert result.manifest is not None
    stale = result.manifest.model_copy(update={"reproducibility_digest": "sha256:" + "f" * 64})

    with pytest.raises(ValidationError, match="reproducibility digest"):
        SyntheticTruthCorpus.model_validate(
            result.corpus.model_copy(update={"manifest": stale}).model_dump(mode="python"),
            strict=True,
        )


def test_contract_rejects_corpus_and_manifest_case_drift() -> None:
    result = m2402.M2502Service().generate(_request())
    assert result.corpus is not None
    assert result.manifest is not None
    corpus = result.corpus
    manifest = result.manifest
    changed_case_ids = ("m2402.case.changed", *manifest.case_ids[1:])
    with pytest.raises(ValidationError, match="manifest must enumerate"):
        SyntheticTruthCorpus.model_validate(
            corpus.model_dump(mode="python")
            | {
                "manifest": manifest.model_copy(update={"case_ids": changed_case_ids}),
            },
            strict=True,
        )
    changed_configuration = manifest.configuration.model_copy(update={"version": "2.0.0"})
    with pytest.raises(ValidationError, match="configuration version"):
        SyntheticTruthCorpus.model_validate(
            corpus.model_dump(mode="python")
            | {
                "manifest": manifest.model_copy(update={"configuration": changed_configuration}),
            },
            strict=True,
        )


def test_contract_rejects_duplicate_corpus_cases_and_forged_result_closure() -> None:
    service = m2402.M2502Service()
    result = service.generate(_request())
    assert result.corpus is not None
    duplicate_cases = (result.corpus.cases[0], result.corpus.cases[0])
    with pytest.raises(ValidationError, match="case ids must be unique"):
        SyntheticTruthCorpus.model_validate(
            result.corpus.model_dump(mode="python") | {"cases": duplicate_cases},
            strict=True,
        )

    invalid_results: tuple[dict[str, object], ...] = (
        {"request_digest": "sha256:" + "0" * 64},
        {"result_id": "result.forged"},
        {
            "provenance": result.provenance.model_copy(
                update={"module_id": "GLIO-PROTEOGEN-M25-03"}
            ),
        },
        {
            "provenance": result.provenance.model_copy(
                update={"input_digests": ("sha256:" + "0" * 64,)}
            )
        },
        {
            "findings": (
                GeneratorFinding(
                    finding_id="m2502.finding",
                    code=GeneratorFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                    message="review",
                ),
            )
            * 2
        },
        {"corpus": None, "manifest": None},
    )
    for update in invalid_results:
        with pytest.raises(ValidationError):
            ProteotypeSyntheticTruthResult.model_validate(
                result.model_dump(mode="python") | update,
                strict=True,
            )

    with pytest.raises(ValidationError, match="abstained result"):
        ProteotypeSyntheticTruthResult.model_validate(
            result.model_dump(mode="python")
            | {
                "status": GenerationStatus.ABSTAINED,
                "abstention_reason": "review required",
            },
            strict=True,
        )
    abstained_payload = result.model_dump(mode="python")
    abstained_payload.update(
        {
            "status": GenerationStatus.ABSTAINED,
            "corpus": None,
            "manifest": None,
            "abstention_reason": "upstream unsupported",
            "support_decision": result.support_decision.model_copy(
                update={"status": SupportStatus.UNSUPPORTED}
            ),
            "findings": (
                GeneratorFinding(
                    finding_id="m2502.abstention",
                    code=GeneratorFindingCode.UPSTREAM_UNSUPPORTED,
                    message="upstream support is unavailable",
                ),
            ),
        }
    )
    provisional = ProteotypeSyntheticTruthResult.model_construct(**abstained_payload)
    abstained_payload["result_digest"] = result_payload_digest(provisional)
    abstained = ProteotypeSyntheticTruthResult.model_validate(abstained_payload, strict=True)
    assert abstained.status is GenerationStatus.ABSTAINED


def test_api_rejects_nonobject_duplicate_and_tampered_verify_payloads() -> None:
    request = _request()
    client = TestClient(m2402.create_app(m2402.M2502Service()))
    non_object = client.post("/v1/modules/M25-02/verify", json=[])
    assert non_object.status_code == _HTTP_UNPROCESSABLE
    generated = client.post(
        "/v1/modules/M25-02/generate",
        content=request.model_dump_json(),
        headers={"content-type": "application/json"},
    )
    assert generated.status_code == _HTTP_OK
    result = generated.json()
    result["result_digest"] = "sha256:" + "f" * 64
    tampered = client.post("/v1/modules/M25-02/verify", json=result)
    assert tampered.status_code == _HTTP_UNPROCESSABLE
    duplicate = client.post(
        "/v1/modules/M25-02/validate",
        content=b'{"request_id":"safe","request_id":"sensitive-second"}',
        headers={"content-type": "application/json"},
    )
    assert duplicate.status_code == _HTTP_UNPROCESSABLE
    assert "sensitive-second" not in duplicate.text


def test_api_denies_failed_support_without_leaking_details() -> None:
    request = _request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = request.context.references.model_copy(update={"support": support})
    denied = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    client = TestClient(m2402.create_app(m2402.M2502Service()))
    response = client.post("/v1/modules/M25-02/generate", json=denied.model_dump(mode="json"))
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in response.text


def test_cli_rejects_bad_input_and_preserves_existing_output(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m2402.cli.app, ["export-schema", "unknown"])
    assert unknown.exit_code != 0
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_text("{not-json", encoding="utf-8")
    assert runner.invoke(m2402.cli.app, ["validate", str(bad_request)]).exit_code != 0
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    output_path = tmp_path / "result.json"
    assert (
        runner.invoke(
            m2402.cli.app, ["generate", str(request_path), "--output", str(output_path)]
        ).exit_code
        == 0
    )
    original = output_path.read_bytes()
    duplicate = runner.invoke(
        m2402.cli.app, ["generate", str(request_path), "--output", str(output_path)]
    )
    assert duplicate.exit_code != 0
    assert output_path.read_bytes() == original


def test_cli_sanitizes_denied_validation_and_generation(tmp_path: Path) -> None:
    request = _request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = request.context.references.model_copy(update={"support": support})
    denied = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    request_path = tmp_path / "denied.json"
    request_path.write_bytes(canonical_json_bytes(denied))
    runner = CliRunner()
    validated = runner.invoke(m2402.cli.app, ["validate", str(request_path)])
    generated = runner.invoke(m2402.cli.app, ["generate", str(request_path)])
    assert validated.exit_code != 0
    assert generated.exit_code != 0
    assert "Traceback" not in generated.output


def test_public_entrypoint_matches_engine_and_json_boundary() -> None:
    request = _request()
    service = m2402.M2502Service()
    direct = m2402.generate_proteotype_synthetic_truth(request)
    via_json = service.generate(json.dumps(request.model_dump(mode="json"), sort_keys=True))
    assert direct.result_digest == via_json.result_digest
    assert service.export_json(direct).startswith("{")
