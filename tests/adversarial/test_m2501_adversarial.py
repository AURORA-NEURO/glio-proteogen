"""Adversarial and negative-path closure for M25-01."""

from __future__ import annotations

from typing import Any, cast

import pytest
from evals.m25_01.fixture import build_request, denied_request, pending_request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m25_01 import (
    AdjudicationRecord,
    AdjudicationStatus,
    CurateProteotypeReferenceTruthRequest,
    ProteotypeReferenceTruthResult,
    ReferenceTruthPackage,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c21_reference_material.m25_01_reference_truth_benchmark_curator import (
    M2501Plugin,
    M2501ReplayError,
    M2501Service,
    ReferenceTruthSubmission,
    app,
    create_app,
)

_HTTP_UNPROCESSABLE = 422
_HTTP_NOT_FOUND = 404
_HTTP_OK = 200
_MAX_REQUEST_BYTES = 8 * 1024 * 1024


def test_request_unknown_field_is_rejected() -> None:
    request = build_request().model_dump(mode="python")
    request["unexpected"] = "hostile"

    with pytest.raises(ValidationError):
        CurateProteotypeReferenceTruthRequest.model_validate(request, strict=True)


def test_request_duplicate_source_artifact_ids_are_rejected() -> None:
    request = build_request()
    duplicate = request.model_copy(
        update={"source_artifacts": (request.source_artifacts[0], request.source_artifacts[0])}
    )

    with pytest.raises(ValidationError, match="source artifact"):
        CurateProteotypeReferenceTruthRequest.model_validate(
            duplicate.model_dump(mode="python"), strict=True
        )


def test_request_duplicate_reference_and_control_ids_are_rejected() -> None:
    request = build_request()
    duplicate = request.model_copy(
        update={
            "controls": (
                request.controls[0].model_copy(update={"reference_id": "fixture-calibrator"}),
            )
        }
    )

    with pytest.raises(ValidationError, match="reference and control ids"):
        CurateProteotypeReferenceTruthRequest.model_validate(
            duplicate.model_dump(mode="python"), strict=True
        )


def test_rejected_adjudication_requires_disagreement() -> None:
    request = build_request()
    rejected = request.adjudications[0].model_copy(update={"status": AdjudicationStatus.REJECTED})

    with pytest.raises(ValidationError, match="disagreement"):
        AdjudicationRecord.model_validate(rejected.model_dump(mode="python"), strict=True)


def test_duplicate_reviewer_tokens_are_rejected() -> None:
    adjudication = (
        build_request()
        .adjudications[0]
        .model_copy(update={"reviewer_tokens": ("same-reviewer", "same-reviewer")})
    )

    with pytest.raises(ValidationError, match="reviewer tokens"):
        AdjudicationRecord.model_validate(adjudication.model_dump(mode="python"), strict=True)


def test_inclusion_and_adjudication_sets_must_be_closed() -> None:
    request = build_request()
    incomplete = request.model_copy(update={"inclusions": request.inclusions[:-1]})

    with pytest.raises(ValidationError, match="inclusions"):
        CurateProteotypeReferenceTruthRequest.model_validate(
            incomplete.model_dump(mode="python"), strict=True
        )


def test_adjudication_set_must_be_closed() -> None:
    request = build_request()
    incomplete = request.model_copy(update={"adjudications": request.adjudications[:-1]})

    with pytest.raises(ValidationError, match="adjudications"):
        CurateProteotypeReferenceTruthRequest.model_validate(
            incomplete.model_dump(mode="python"), strict=True
        )


def test_package_challenge_set_must_match_marked_entries() -> None:
    result = M2501Service().execute(build_request())
    assert result.package is not None
    package = result.package.model_copy(update={"challenge_set_ids": ("fixture-calibrator",)})

    with pytest.raises(ValidationError, match="challenge set identifiers"):
        ReferenceTruthPackage.model_validate(package.model_dump(mode="python"), strict=True)


def test_package_unknown_challenge_entry_is_rejected() -> None:
    result = M2501Service().execute(build_request())
    assert result.package is not None
    package = result.package.model_copy(update={"challenge_set_ids": ("unknown-entry",)})

    with pytest.raises(ValidationError, match="known entries"):
        ReferenceTruthPackage.model_validate(package.model_dump(mode="python"), strict=True)


def test_package_duplicate_challenge_ids_are_rejected() -> None:
    result = M2501Service().execute(build_request())
    assert result.package is not None
    package = result.package.model_copy(
        update={"challenge_set_ids": ("fixture-challenge", "fixture-challenge")}
    )

    with pytest.raises(ValidationError, match="unique"):
        ReferenceTruthPackage.model_validate(package.model_dump(mode="python"), strict=True)


def test_package_duplicate_reference_ids_are_rejected() -> None:
    result = M2501Service().execute(build_request())
    assert result.package is not None
    package = result.package.model_copy(
        update={"references": (result.package.references[0], result.package.references[0])}
    )

    with pytest.raises(ValidationError, match="reference and control ids"):
        ReferenceTruthPackage.model_validate(package.model_dump(mode="python"), strict=True)


def test_package_adjudication_closure_is_revalidated() -> None:
    result = M2501Service().execute(build_request())
    assert result.package is not None
    package = result.package.model_copy(update={"adjudications": result.package.adjudications[:-1]})

    with pytest.raises(ValidationError, match="adjudications"):
        ReferenceTruthPackage.model_validate(package.model_dump(mode="python"), strict=True)


def test_package_inclusion_closure_is_revalidated() -> None:
    result = M2501Service().execute(build_request())
    assert result.package is not None
    package = result.package.model_copy(update={"inclusions": result.package.inclusions[:-1]})

    with pytest.raises(ValidationError, match="inclusion decisions"):
        ReferenceTruthPackage.model_validate(package.model_dump(mode="python"), strict=True)


def test_pending_result_never_contains_a_package() -> None:
    result = M2501Service().execute(pending_request())

    assert result.package is None
    assert result.status.value == "abstained"
    assert result.support_decision.status.value == "review_required"


def test_result_digest_tamper_is_rejected() -> None:
    result = M2501Service().execute(build_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + ("f" * 64)})

    with pytest.raises(ValidationError, match="result digest"):
        ProteotypeReferenceTruthResult.model_validate(
            tampered.model_dump(mode="python"), strict=True
        )


def test_result_identifier_tamper_is_rejected() -> None:
    service = M2501Service()
    result = service.execute(build_request())
    tampered = result.model_copy(update={"result_id": "result-forged"})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})

    with pytest.raises(ValidationError, match="result identifier"):
        ProteotypeReferenceTruthResult.model_validate(
            tampered.model_dump(mode="python"), strict=True
        )


def test_request_digest_tamper_is_rejected() -> None:
    result = M2501Service().execute(build_request())
    tampered = result.model_copy(update={"request_digest": "sha256:" + ("a" * 64)})

    with pytest.raises(ValidationError, match="request digest"):
        ProteotypeReferenceTruthResult.model_validate(
            tampered.model_dump(mode="python"), strict=True
        )


def test_curated_result_requires_package_and_supported_status() -> None:
    result = M2501Service().execute(build_request())
    tampered = result.model_copy(update={"package": None})

    with pytest.raises(ValidationError, match="curated result"):
        ProteotypeReferenceTruthResult.model_validate(
            tampered.model_dump(mode="python"), strict=True
        )


def test_abstained_result_cannot_contain_package() -> None:
    result = M2501Service().execute(pending_request())
    package = M2501Service().execute(build_request()).package
    assert package is not None
    tampered = result.model_copy(update={"package": package})

    with pytest.raises(ValidationError, match="abstained result"):
        ProteotypeReferenceTruthResult.model_validate(
            tampered.model_dump(mode="python"), strict=True
        )


def test_package_lock_tamper_is_rejected() -> None:
    service = M2501Service()
    result = service.execute(build_request())
    assert result.package is not None
    package = result.package.model_copy(update={"lock_digest": "sha256:" + ("f" * 64)})
    tampered = result.model_copy(update={"package": package})

    with pytest.raises(M2501ReplayError):
        service.verify_replay(tampered)


def test_result_identifier_is_derived_from_request_and_status() -> None:
    result = M2501Service().execute(build_request())

    assert result.result_id == result_identifier(result.request, result.status.value)


def test_replay_rejects_self_rehashed_semantic_regions() -> None:
    """A forged payload must fail even when its result digest is recomputed."""

    service = M2501Service()
    result = service.execute(build_request())
    evidence = result.evidence[0].model_copy(update={"claim": "forged evidence"})
    provenance = result.provenance.model_copy(update={"activity_id": "forged.activity"})
    support = result.support_decision.model_copy(update={"rationale": "forged support"})
    mutations: tuple[tuple[str, object], ...] = (
        (
            "limitations",
            (result.limitations[0].model_copy(update={"statement": "forged limitation"}),)
            + result.limitations[1:],
        ),
        ("evidence", (evidence,)),
        ("provenance", provenance),
        ("support_decision", support),
    )

    for field, value in mutations:
        forged = result.model_copy(update={field: value})
        forged = ProteotypeReferenceTruthResult.model_construct(
            **{**forged.__dict__, "result_digest": result_payload_digest(forged)}
        )
        with pytest.raises(M2501ReplayError):
            service.verify_replay(forged)


def test_plugin_rejects_unwrapped_request_and_duplicate_json_keys() -> None:
    plugin = M2501Plugin(M2501Service())
    with pytest.raises(TypeError, match="reference-truth submission"):
        plugin.validate(build_request())
    with pytest.raises((ValueError, TypeError)):
        plugin.validate(ReferenceTruthSubmission(b'{"request_id":1,"request_id":2}'))


def test_plugin_rejects_invalid_execution_token() -> None:
    plugin = M2501Plugin(M2501Service())

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", object()))


def test_plugin_descriptor_is_explicit() -> None:
    descriptor = M2501Plugin(M2501Service()).descriptor()

    assert descriptor.module_id == "GLIO-PROTEOGEN-M25-01"
    assert descriptor.prohibited_outputs


def test_plugin_rejects_oversized_json() -> None:
    plugin = M2501Plugin(M2501Service())
    with pytest.raises((ValueError, TypeError)):
        plugin.validate(ReferenceTruthSubmission(b"{" + (b"x" * _MAX_REQUEST_BYTES) + b"}"))


def test_api_sanitizes_invalid_json_and_unknown_schema() -> None:
    client = TestClient(create_app(M2501Service()))
    invalid = client.post("/v1/modules/M25-01/validate", content=b"[]")
    unknown = client.get("/v1/modules/M25-01/schemas/unknown")

    assert invalid.status_code == _HTTP_UNPROCESSABLE
    assert unknown.status_code == _HTTP_NOT_FOUND
    assert "Traceback" not in invalid.text


def test_api_rejects_non_object_and_unauthorized_requests() -> None:
    client = TestClient(create_app(M2501Service()))
    assert client.post("/v1/modules/M25-01/verify", content=b"[").status_code == _HTTP_UNPROCESSABLE
    assert (
        client.post("/v1/modules/M25-01/verify", content=b"[]").status_code == _HTTP_UNPROCESSABLE
    )
    denied = denied_request().model_dump(mode="json")
    assert (
        client.post("/v1/modules/M25-01/validate", json=denied).status_code == _HTTP_UNPROCESSABLE
    )


def test_api_replay_rejects_invalid_result_object() -> None:
    client = TestClient(create_app(M2501Service()))

    response = client.post(
        "/v1/modules/M25-01/verify",
        json={"result": {"status": "curated"}},
    )

    assert response.status_code == _HTTP_UNPROCESSABLE


def test_hostile_mapping_preflight_fails_closed() -> None:
    class HostileMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError("hostile mapping")  # noqa: TRY003

    client = TestClient(create_app(M2501Service()))
    response = client.post("/v1/modules/M25-01/validate", json=HostileMapping())

    assert response.status_code == _HTTP_UNPROCESSABLE


def test_cli_refuses_overwrite_and_bad_inputs(tmp_path: Any) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(build_request()))
    output = tmp_path / "result.json"
    first = runner.invoke(app, ["curate", str(request_path), "--output", str(output)])
    second = runner.invoke(app, ["curate", str(request_path), "--output", str(output)])

    assert first.exit_code == 0
    assert second.exit_code != 0
    assert runner.invoke(app, ["export-schema", "unknown"]).exit_code != 0
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_bytes(b"[]")
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_bytes(b"[]")
    assert runner.invoke(app, ["validate", str(bad_request)]).exit_code != 0
    assert runner.invoke(app, ["curate", str(bad_request)]).exit_code != 0
    assert runner.invoke(app, ["verify", str(bad_result)]).exit_code != 0


def test_cli_abstention_emits_result_and_nonzero_review_exit(tmp_path: Any) -> None:
    runner = CliRunner()
    path = tmp_path / "pending.json"
    path.write_bytes(canonical_json_bytes(pending_request()))
    result_path = tmp_path / "pending-result.json"

    completed = runner.invoke(app, ["curate", str(path), "--output", str(result_path)])

    assert completed.exit_code == 1
    assert result_path.exists()


def test_api_accepts_result_wrapper_for_replay() -> None:
    client = TestClient(create_app(M2501Service()))
    result = M2501Service().execute(build_request()).model_dump(mode="json")

    response = client.post("/v1/modules/M25-01/verify", json={"result": result})

    assert response.status_code == _HTTP_OK
    assert response.json()["verified"] is True


def test_contract_schema_does_not_authorize_scientific_content() -> None:
    client = TestClient(create_app(M2501Service()))
    schema = client.get("/v1/modules/M25-01/schemas/output").json()
    metadata = cast("dict[str, object]", schema["x-glio-contract"])

    assert metadata["externalContentTraversal"] is False
    assert metadata["unsupportedToNegative"] is False
    assert metadata["kinaseActivity"] is False
    assert metadata["treatmentRecommendation"] is False
