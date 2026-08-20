"""Deep M23-01 adversarial boundary and replay coverage."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m23_01 import (
    AdjudicationStatus,
    BenchmarkConfiguration,
    CurateVariantPeptideReferenceTruthRequest,
    ReferenceEntry,
    ReferenceKind,
    ReferenceTruthPackage,
    VariantPeptideReferenceTruthResult,
    canonical_request_digest,
    package_payload_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import SupportDecision, SupportStatus
from glio_proteogen.kernel.strict_json import StrictJsonError, StrictJsonErrorCode
from glio_proteogen.modules.c21_reference_material.m23_01_reference_truth_benchmark_curator import (
    M2301AuthorizationError,
    M2301Plugin,
    M2301ReplayError,
    M2301Service,
    ReferenceTruthSubmission,
    api,
    cli,
    curate_variant_peptide_reference_truth,
)
from tests.contract.test_m23_01_deep import _request

_HTTP_UNPROCESSABLE = 422
_HTTP_OK = 200


def test_plugin_rejects_duplicate_keys_and_unvalidated_tokens() -> None:
    plugin = M2301Plugin(M2301Service())
    with pytest.raises(StrictJsonError) as error:
        plugin.validate(ReferenceTruthSubmission(b'{"request_id":"a","request_id":"b"}'))
    assert error.value.code is StrictJsonErrorCode.DUPLICATE_KEY
    with pytest.raises(TypeError, match="submission"):
        plugin.validate(_request())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_replay_rejects_self_rehashed_reference_evidence_forgery() -> None:
    result = M2301Service().execute(_request())
    evidence = result.evidence[0].model_copy(update={"claim": "forged evidence"})
    forged = result.model_copy(update={"evidence": (evidence, *result.evidence[1:])})
    forged = VariantPeptideReferenceTruthResult.model_construct(
        **{**forged.__dict__, "result_digest": result_payload_digest(forged)}
    )

    with pytest.raises(M2301ReplayError):
        M2301Service().verify_replay(forged)


def test_provenance_binds_the_complete_canonical_request_identity() -> None:
    request = _request()
    result = M2301Service().execute(request)

    assert result.request_digest in result.provenance.input_digests

    changed = request.model_copy(
        update={
            "inclusions": (
                request.inclusions[0].model_copy(update={"rationale": "different policy"}),
                *request.inclusions[1:],
            )
        }
    )
    changed_result = M2301Service().execute(changed)
    assert changed_result.request_digest != result.request_digest
    assert changed_result.provenance.input_digests[0] == changed_result.request_digest


def test_contract_rejects_partition_kind_and_duplicate_source_ids() -> None:
    request = _request()
    invalid_reference = request.references[0].model_copy(
        update={"kind": ReferenceKind.POSITIVE_CONTROL}
    )
    with pytest.raises(ValidationError, match="control kind"):
        CurateVariantPeptideReferenceTruthRequest.model_validate(
            request.model_copy(
                update={"references": (invalid_reference, request.references[1])}
            ).model_dump(mode="python")
        )
    duplicate_sources = (request.source_artifacts[0], *request.source_artifacts)
    with pytest.raises(ValidationError, match="unique artifact"):
        CurateVariantPeptideReferenceTruthRequest.model_validate(
            request.model_copy(update={"source_artifacts": duplicate_sources}).model_dump(
                mode="python"
            )
        )


def test_api_rejects_auth_failure_and_non_object_json() -> None:
    request = _request()
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "consent": request.context.references.consent.model_copy(
                        update={"state": "revoked"}
                    )
                }
            )
        }
    )
    denied = request.model_copy(update={"context": denied_context})
    client = TestClient(api.create_app())
    response = client.post(
        "/v1/modules/M23-01/curate",
        content=denied.model_dump_json(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == _HTTP_UNPROCESSABLE
    non_object = client.post("/v1/modules/M23-01/verify", content=b"[]")
    assert non_object.status_code == _HTTP_UNPROCESSABLE


def test_cli_sanitizes_invalid_input_and_refuses_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    result = runner.invoke(cli.app, ["validate", str(invalid)])
    assert result.exit_code != 0
    unknown = runner.invoke(cli.app, ["export-schema", "unknown"])
    assert unknown.exit_code != 0
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "schema.json"
    request_path.write_bytes(_request().model_dump_json().encode())
    first = runner.invoke(cli.app, ["export-schema", "request", "--output", str(output_path)])
    assert first.exit_code == 0
    second = runner.invoke(cli.app, ["export-schema", "request", "--output", str(output_path)])
    assert second.exit_code != 0


def test_result_abstention_keeps_findings_and_never_emits_package() -> None:
    request = _request()
    pending = request.adjudications[0].model_copy(update={"status": AdjudicationStatus.PENDING})
    result = M2301Service().execute(
        request.model_copy(update={"adjudications": (pending, *request.adjudications[1:])})
    )
    assert result.package is None
    assert result.findings
    assert result.abstention_reason is not None
    assert result.emits_parent is False


def test_service_rejects_hostile_mapping_without_traversal() -> None:
    with pytest.raises(M2301AuthorizationError, match="requires accepted"):
        M2301Service().validate_request({"context": {"references": {}}})


def test_contract_rejects_challenge_adjudication_and_request_closure_gaps() -> None:
    request = _request()
    invalid_challenge_data = request.references[1].model_dump(mode="python")
    invalid_challenge_data["challenge_set"] = False
    invalid_challenge = ReferenceEntry.model_construct(**invalid_challenge_data)
    with pytest.raises(ValidationError, match="challenge-set kind"):
        ReferenceEntry.model_validate(invalid_challenge.model_dump(mode="python"))
    duplicate_reviewer = request.adjudications[0].model_copy(
        update={"reviewer_tokens": ("reviewer-a", "reviewer-a")}
    )
    with pytest.raises(ValidationError, match="reviewer tokens"):
        type(request.adjudications[0]).model_validate(duplicate_reviewer.model_dump(mode="python"))
    rejected_without_statement = request.adjudications[0].model_copy(
        update={"status": AdjudicationStatus.REJECTED, "disagreement_statement": None}
    )
    with pytest.raises(ValidationError, match="disagreement statement"):
        type(request.adjudications[0]).model_validate(
            rejected_without_statement.model_dump(mode="python")
        )
    with pytest.raises(ValidationError, match="inclusions"):
        CurateVariantPeptideReferenceTruthRequest.model_validate(
            request.model_copy(
                update={"inclusions": (request.inclusions[0], *request.inclusions[2:])}
            ).model_dump(mode="python")
        )
    with pytest.raises(ValidationError, match="adjudications"):
        CurateVariantPeptideReferenceTruthRequest.model_validate(
            request.model_copy(
                update={"adjudications": (request.adjudications[0], *request.adjudications[2:])}
            ).model_dump(mode="python")
        )


def test_package_and_result_closure_errors_are_explicit() -> None:
    request = _request()
    result = M2301Service().execute(request)
    assert result.package is not None
    package = result.package
    with pytest.raises(ValidationError, match="known entries"):
        ReferenceTruthPackage.model_validate(
            package.model_copy(update={"challenge_set_ids": ("unknown",)}).model_dump()
        )
    with pytest.raises(ValidationError, match="match flagged"):
        ReferenceTruthPackage.model_validate(
            package.model_copy(update={"challenge_set_ids": ("calibrator-1",)}).model_dump()
        )
    with pytest.raises(ValidationError, match="request digest"):
        VariantPeptideReferenceTruthResult.model_validate(
            result.model_copy(update={"request_digest": "sha256:" + "f" * 64}).model_dump()
        )
    with pytest.raises(ValidationError, match="supported truth package"):
        VariantPeptideReferenceTruthResult.model_validate(
            result.model_copy(update={"package": None}).model_dump()
        )
    pending = request.adjudications[0].model_copy(update={"status": AdjudicationStatus.PENDING})
    abstained = M2301Service().execute(
        request.model_copy(update={"adjudications": (pending, *request.adjudications[1:])})
    )
    with pytest.raises(ValidationError, match="safe status"):
        VariantPeptideReferenceTruthResult.model_validate(
            abstained.model_copy(
                update={
                    "support_decision": SupportDecision(
                        status=SupportStatus.SUPPORTED,
                        reason_code="incorrect",
                        rationale="invalid support status for abstention",
                    )
                }
            ).model_dump()
        )


def test_canonical_mapping_and_public_entry_point_are_exercised() -> None:
    assert canonical_request_digest({"request": "mapping"}).startswith("sha256:")
    result = curate_variant_peptide_reference_truth(_request())
    assert result.result_id.startswith("curation.m2301.")


def test_contract_closure_rejects_all_partition_and_lock_substitutions() -> None:
    request = _request()
    package = M2301Service().execute(request).package
    assert package is not None

    duplicate_reference = package.references[0].model_copy(
        update={"reference_id": package.references[1].reference_id}
    )
    with pytest.raises(ValidationError, match="reference and control ids"):
        ReferenceTruthPackage.model_validate(
            package.model_copy(
                update={"references": (duplicate_reference, package.references[1])}
            ).model_dump()
        )
    configuration_data = package.configuration.model_dump(mode="python")
    configuration_data["parent_target"] = "wrong parent"
    invalid_configuration = BenchmarkConfiguration.model_construct(**configuration_data)
    invalid_package = package.model_copy(update={"configuration": invalid_configuration})
    with pytest.raises(ValueError, match="parent_target"):
        ReferenceTruthPackage.model_validate(invalid_package.model_dump(mode="python"))
    invalid_inclusions = package.model_copy(update={"inclusions": package.inclusions[:-1]})
    with pytest.raises(ValueError, match="inclusion decisions"):
        ReferenceTruthPackage.model_validate(invalid_inclusions.model_dump(mode="python"))
    invalid_adjudications = package.model_copy(update={"adjudications": package.adjudications[:-1]})
    with pytest.raises(ValueError, match="adjudications must cover"):
        ReferenceTruthPackage.model_validate(invalid_adjudications.model_dump(mode="python"))


def test_request_closure_rejects_duplicate_ids_and_partition_substitutions() -> None:
    request = _request()
    duplicate = request.references[0].model_copy(
        update={"reference_id": request.references[1].reference_id}
    )
    with pytest.raises(ValidationError, match="request reference and control ids"):
        CurateVariantPeptideReferenceTruthRequest.model_validate(
            request.model_copy(
                update={"references": (duplicate, request.references[1])}
            ).model_dump()
        )
    invalid_control = request.controls[0].model_copy(update={"kind": ReferenceKind.CALIBRATOR})
    with pytest.raises(ValidationError, match="reference kind"):
        CurateVariantPeptideReferenceTruthRequest.model_validate(
            request.model_copy(
                update={"controls": (invalid_control, *request.controls[1:])}
            ).model_dump()
        )
    with pytest.raises(ValidationError, match="challenge-set"):
        CurateVariantPeptideReferenceTruthRequest.model_validate(
            request.model_copy(
                update={
                    "references": (
                        request.references[0],
                        request.references[1].model_copy(update={"challenge_set": False}),
                    )
                }
            ).model_dump()
        )


def test_result_curated_package_must_bind_exact_request() -> None:
    request = _request()
    result = M2301Service().execute(request)
    assert result.package is not None
    altered_base = result.package.model_copy(
        update={"endpoint": request.endpoint.model_copy(update={"name": "different"})}
    )
    altered_data = altered_base.model_dump(mode="python")
    altered_data["lock_digest"] = package_payload_digest(
        ReferenceTruthPackage.model_construct(**altered_data)
    )
    altered = ReferenceTruthPackage.model_validate(altered_data)
    with pytest.raises(ValidationError, match="exact request declarations"):
        VariantPeptideReferenceTruthResult.model_validate(
            result.model_copy(update={"package": altered}).model_dump()
        )


def test_api_parse_validate_and_known_schema_error_paths() -> None:
    client = TestClient(api.create_app())
    assert client.get("/v1/modules/M23-01/schemas/request").status_code == _HTTP_OK
    invalid = client.post("/v1/modules/M23-01/validate", content=b"not-json")
    assert invalid.status_code == _HTTP_UNPROCESSABLE
    invalid_curate = client.post("/v1/modules/M23-01/curate", content=b"not-json")
    assert invalid_curate.status_code == _HTTP_UNPROCESSABLE
    request = _request()
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "consent": request.context.references.consent.model_copy(
                        update={"state": "revoked"}
                    )
                }
            )
        }
    )
    denied = client.post(
        "/v1/modules/M23-01/validate",
        content=request.model_copy(update={"context": denied_context}).model_dump_json(),
    )
    assert denied.status_code == _HTTP_UNPROCESSABLE


def test_cli_invalid_result_denied_request_abstention_and_replay_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    invalid_result = tmp_path / "invalid-result.json"
    invalid_result.write_text("not-json", encoding="utf-8")
    assert runner.invoke(cli.app, ["verify", str(invalid_result)]).exit_code != 0

    request = _request()
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "consent": request.context.references.consent.model_copy(
                        update={"state": "revoked"}
                    )
                }
            )
        }
    )
    denied_path = tmp_path / "denied.json"
    denied_path.write_bytes(
        request.model_copy(update={"context": denied_context}).model_dump_json().encode()
    )
    assert runner.invoke(cli.app, ["validate", str(denied_path)]).exit_code != 0
    assert runner.invoke(cli.app, ["curate", str(denied_path)]).exit_code != 0

    request_path = tmp_path / "request.json"
    request_path.write_bytes(request.model_dump_json().encode())
    emitted = runner.invoke(cli.app, ["curate", str(request_path)])
    assert emitted.exit_code == 0

    pending = request.adjudications[0].model_copy(update={"status": AdjudicationStatus.PENDING})
    pending_path = tmp_path / "pending.json"
    pending_path.write_bytes(
        request.model_copy(update={"adjudications": (pending, *request.adjudications[1:])})
        .model_dump_json()
        .encode()
    )
    abstained = runner.invoke(cli.app, ["curate", str(pending_path)])
    assert abstained.exit_code == 1

    result_path = tmp_path / "result.json"
    runner.invoke(cli.app, ["curate", str(request_path), "--output", str(result_path)])

    class ReplayMismatch:
        def verify_replay(self, value: VariantPeptideReferenceTruthResult) -> Any:
            return value.model_copy(update={"result_digest": "sha256:" + "f" * 64})

    monkeypatch.setattr(cli, "_SERVICE", ReplayMismatch())
    assert runner.invoke(cli.app, ["verify", str(result_path)]).exit_code == 1


def test_plugin_typed_request_and_hostile_authorization_mapping() -> None:
    plugin = M2301Plugin(M2301Service())
    token = plugin.validate(ReferenceTruthSubmission(request=_request()))
    assert token.request.request_id == "request-1"

    class HostileMapping(dict[str, Any]):
        def get(self, key: str, _default: Any = None) -> Any:
            raise RuntimeError(key)

    with pytest.raises(M2301AuthorizationError):
        M2301Service().validate_request({"context": {"references": HostileMapping()}})
