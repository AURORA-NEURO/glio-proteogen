"""Negative-path coverage for the M21-01 safety envelope."""

from __future__ import annotations

from typing import Any, cast

import pytest
from evals.m21_01.fixture import build_request, pending_request
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m21_01 import (
    AdjudicationRecord,
    AdjudicationStatus,
    ComplexActivityReferenceTruthResult,
    CurateComplexActivityReferenceTruthRequest,
    CurationFinding,
    CurationFindingCode,
    ReferenceKind,
    ReferenceTruthPackage,
    package_lock_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c21_reference_material.m21_01_reference_truth_benchmark_curator import (
    M2101AuthorizationError,
    M2101Plugin,
    M2101ReplayError,
    M2101Service,
    ReferenceTruthSubmission,
    ValidatedM2101Request,
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


def test_preflight_rejects_non_mapping_candidate_without_traversal() -> None:
    with pytest.raises(M2101AuthorizationError):
        preflight_m2101_authorization(object())


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


def _package_payload(package: ReferenceTruthPackage, **updates: Any) -> dict[str, Any]:
    payload = package.model_dump(mode="python")
    payload.update(updates)
    return payload


def _relock_package(package: ReferenceTruthPackage) -> ReferenceTruthPackage:
    payload = package.model_dump(mode="python")
    provisional = ReferenceTruthPackage.model_construct(**cast("Any", payload))
    payload["lock_digest"] = package_lock_digest(provisional)
    return ReferenceTruthPackage(**cast("Any", payload))


def test_locked_package_rejects_partition_and_lock_closure_tampering() -> None:
    result = M2101Service().execute(build_request())
    assert result.package is not None
    package = result.package
    cases = (
        (
            "reference and control ids",
            {"references": (package.references[0], package.references[0])},
        ),
        (
            "references may only",
            {
                "references": (
                    package.references[0].model_copy(
                        update={"kind": ReferenceKind.POSITIVE_CONTROL}
                    ),
                    package.references[1],
                )
            },
        ),
        (
            "challenge-set kind",
            {
                "references": (
                    package.references[0],
                    package.references[1].model_copy(update={"challenge_set": False}),
                )
            },
        ),
        (
            "controls must",
            {
                "controls": (
                    package.controls[0].model_copy(update={"kind": ReferenceKind.CALIBRATOR}),
                    package.controls[1],
                )
            },
        ),
        (
            "inclusion decisions",
            {"inclusions": (package.inclusions[0], *package.inclusions)},
        ),
        (
            "adjudications must",
            {"adjudications": (package.adjudications[0], *package.adjudications)},
        ),
        (
            "challenge set ids",
            {"challenge_set_ids": ("fixture-challenge", "fixture-challenge")},
        ),
        (
            "package and locked configuration",
            {"configuration": package.configuration.model_copy(update={"version": "0.2.0"})},
        ),
    )
    for message, updates in cases:
        with pytest.raises(ValidationError, match=message):
            ReferenceTruthPackage(**_package_payload(package, **updates))


def test_locked_package_rejects_included_rejection() -> None:
    result = M2101Service().execute(build_request())
    assert result.package is not None
    package = result.package
    rejected = package.adjudications[0].model_copy(
        update={
            "status": AdjudicationStatus.REJECTED,
            "disagreement_statement": "Fixture reviewers disagree.",
        }
    )
    with pytest.raises(ValidationError, match="rejected adjudications"):
        ReferenceTruthPackage(
            **_package_payload(package, adjudications=(rejected, *package.adjudications[1:]))
        )


def test_result_closure_rejects_package_projection_and_duplicate_findings() -> None:
    service = M2101Service()
    request = build_request()
    result = service.execute(request)
    assert result.package is not None
    package = result.package
    projections = (
        (
            "endpoint",
            _relock_package(
                package.model_copy(
                    update={"endpoint": request.endpoint.model_copy(update={"name": "other"})}
                )
            ),
        ),
        (
            "references",
            _relock_package(
                package.model_copy(
                    update={"references": (package.references[1], package.references[0])}
                )
            ),
        ),
        (
            "controls",
            _relock_package(
                package.model_copy(update={"controls": (package.controls[1], package.controls[0])})
            ),
        ),
        (
            "inclusions",
            _relock_package(
                package.model_copy(update={"inclusions": tuple(reversed(package.inclusions))})
            ),
        ),
        (
            "adjudications",
            _relock_package(
                package.model_copy(update={"adjudications": tuple(reversed(package.adjudications))})
            ),
        ),
        (
            "configuration",
            _relock_package(
                package.model_copy(
                    update={
                        "configuration": package.configuration.model_copy(
                            update={"configuration_id": "other"}
                        )
                    }
                )
            ),
        ),
    )
    for message, bad_package in projections:
        payload = result.model_dump(mode="python")
        payload["package"] = bad_package
        with pytest.raises(ValidationError, match=message):
            ComplexActivityReferenceTruthResult(**cast("Any", payload))
    finding = CurationFinding(
        finding_id="duplicate-finding",
        code=CurationFindingCode.PROVENANCE_MISSING,
        message="fixture finding",
    )
    payload = result.model_dump(mode="python")
    payload["findings"] = (finding, finding)
    with pytest.raises(ValidationError, match="finding ids"):
        ComplexActivityReferenceTruthResult(**cast("Any", payload))


def test_adjudication_rejection_requires_visible_disagreement() -> None:
    request = build_request()
    rejected = request.adjudications[0].model_copy(update={"status": AdjudicationStatus.REJECTED})
    payload = request.model_dump(mode="python")
    payload["adjudications"] = (rejected, *request.adjudications[1:])
    with pytest.raises(ValidationError, match="disagreement statement"):
        _REQUEST_ADAPTER.validate_python(cast("Any", payload), strict=True)


def test_adjudication_reviewer_tokens_and_disagreement_are_closed() -> None:
    request = build_request()
    duplicate = request.adjudications[0].model_copy(
        update={"reviewer_tokens": ("same-reviewer", "same-reviewer")}
    )
    with pytest.raises(ValidationError, match="reviewer tokens"):
        AdjudicationRecord(**cast("Any", duplicate.model_dump(mode="python")))
    non_rejected = request.adjudications[0].model_copy(
        update={"disagreement_statement": "unexpected disagreement"}
    )
    with pytest.raises(ValidationError, match="only rejected"):
        AdjudicationRecord(**cast("Any", non_rejected.model_dump(mode="python")))


def test_request_requires_unique_inclusion_and_adjudication_coverage() -> None:
    request = build_request()
    payload = request.model_dump(mode="python")
    payload["inclusions"] = (request.inclusions[0], *request.inclusions)
    with pytest.raises(ValidationError, match="inclusions"):
        _REQUEST_ADAPTER.validate_python(cast("Any", payload), strict=True)
    payload["inclusions"] = request.inclusions
    payload["adjudications"] = (request.adjudications[0], *request.adjudications)
    with pytest.raises(ValidationError, match="adjudications"):
        _REQUEST_ADAPTER.validate_python(cast("Any", payload), strict=True)


def test_request_rejects_duplicate_reference_and_control_ids() -> None:
    request = build_request()
    payload = request.model_dump(mode="python")
    payload["controls"] = (
        request.controls[0].model_copy(update={"reference_id": request.references[0].reference_id}),
        request.controls[1],
    )
    with pytest.raises(ValidationError, match="reference and control ids"):
        _REQUEST_ADAPTER.validate_python(cast("Any", payload), strict=True)


def test_request_requires_a_challenge_set() -> None:
    request = build_request()
    references = (request.references[0].model_copy(update={"kind": ReferenceKind.CALIBRATOR}),)
    payload = request.model_dump(mode="python")
    payload["references"] = references
    payload["inclusions"] = tuple(request.inclusions[i] for i in (0, 2, 3))
    payload["adjudications"] = tuple(request.adjudications[i] for i in (0, 2, 3))
    with pytest.raises(ValidationError, match="challenge-set"):
        _REQUEST_ADAPTER.validate_python(cast("Any", payload), strict=True)


def test_result_digest_tamper_is_rejected() -> None:
    result = M2101Service().execute(build_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    with pytest.raises(ValidationError, match="result digest"):
        ComplexActivityReferenceTruthResult(**cast("Any", tampered.model_dump(mode="python")))


def test_replay_rejects_self_rehashed_reference_evidence_forgery() -> None:
    result = M2101Service().execute(build_request())
    evidence = result.evidence[0].model_copy(update={"claim": "forged evidence"})
    forged = result.model_copy(update={"evidence": (evidence, *result.evidence[1:])})
    forged = ComplexActivityReferenceTruthResult.model_construct(
        **{**forged.__dict__, "result_digest": result_payload_digest(forged)}
    )

    with pytest.raises(M2101ReplayError):
        M2101Service().verify_replay(forged)


def test_plugin_rejects_unwrapped_request_and_bad_json() -> None:
    plugin = M2101Plugin(M2101Service())
    with pytest.raises(TypeError, match="reference-truth submission"):
        plugin.validate(build_request())
    with pytest.raises((ValueError, TypeError)):
        plugin.validate(ReferenceTruthSubmission(request=b"[]"))


def test_plugin_token_rejects_forged_cross_instance_and_nested_mutation() -> None:
    request = build_request()
    plugin = M2101Plugin(M2101Service())
    other = M2101Plugin(M2101Service())
    token = plugin.validate(ReferenceTruthSubmission(request=request))

    assert plugin.run(token).status.value == "curated"

    forged = ValidatedM2101Request(request=token.request, _seal=token._seal)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request token"):
        other.run(token)

    changed_endpoint = token.request.endpoint.model_copy(update={"name": "forged endpoint"})
    object.__setattr__(token.request, "endpoint", changed_endpoint)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_api_sanitizes_invalid_json_and_unknown_schema() -> None:
    client = TestClient(create_app(M2101Service()))
    invalid = client.post("/v1/modules/M21-01/validate", content=b"[]")
    unknown = client.get("/v1/modules/M21-01/schemas/unknown")
    assert invalid.status_code == _HTTP_UNPROCESSABLE
    assert unknown.status_code == _HTTP_NOT_FOUND
    assert "Traceback" not in invalid.text


def test_api_rejects_non_object_and_unauthorized_requests() -> None:
    client = TestClient(create_app(M2101Service()))
    assert client.post("/v1/modules/M21-01/verify", content=b"[").status_code == _HTTP_UNPROCESSABLE
    assert (
        client.post("/v1/modules/M21-01/verify", content=b"[]").status_code == _HTTP_UNPROCESSABLE
    )
    denied = build_request()
    denied_support = denied.context.references.support.model_copy(update={"state": "rejected"})
    denied_context = denied.context.model_copy(
        update={
            "references": denied.context.references.model_copy(update={"support": denied_support})
        }
    )
    body = denied.model_copy(update={"context": denied_context}).model_dump(mode="json")
    assert client.post("/v1/modules/M21-01/validate", json=body).status_code == _HTTP_UNPROCESSABLE
    assert client.post("/v1/modules/M21-01/curate", json=body).status_code == _HTTP_UNPROCESSABLE


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


def test_cli_sanitizes_bad_schema_request_and_result(tmp_path: Any) -> None:
    runner = CliRunner()
    assert runner.invoke(cli_app, ["export-schema", "unknown"]).exit_code != 0
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["validate", str(bad_request)]).exit_code != 0
    assert runner.invoke(cli_app, ["curate", str(bad_request)]).exit_code != 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["verify", str(bad_result)]).exit_code != 0


def test_cli_stdout_and_unverified_result_paths(tmp_path: Any) -> None:
    runner = CliRunner()
    assert runner.invoke(cli_app, ["export-schema", "request"]).exit_code == 0
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(build_request()))
    result_path = tmp_path / "result.json"
    assert (
        runner.invoke(
            cli_app, ["curate", str(request_path), "--output", str(result_path)]
        ).exit_code
        == 0
    )
    result_path.write_bytes(
        result_path.read_bytes().replace(b"complex_activity_reference_truth", b"tampered_output")
    )
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code != 0
