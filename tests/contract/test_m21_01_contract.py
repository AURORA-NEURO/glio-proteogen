"""Focused and adversarial contract coverage for provisional M21-01."""

import hashlib
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m21_01 import (
    M2101_OUTPUT_MEDIA_TYPE,
    M2101_PROVISIONAL_ABI,
    AdjudicationRecord,
    AdjudicationStatus,
    BenchmarkConfiguration,
    ComplexActivityReferenceTruthResult,
    CurateComplexActivityReferenceTruthRequest,
    CurationStatus,
    EndpointDefinition,
    InclusionDecision,
    ReferenceEntry,
    ReferenceKind,
    ReferenceTruthPackage,
    canonical_request_digest,
    contract_json_schemas,
    package_lock_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c21_reference_material.m21_01_reference_truth_benchmark_curator import (
    M2101AuthorizationError,
    M2101Plugin,
    M2101Service,
    ReferenceTruthSubmission,
    cli_app,
    create_app,
)

_SCHEMA_COUNT = 9
_HTTP_OK = 200
_HTTP_UNPROCESSABLE = 422


def test_provisional_schemas_preserve_reference_truth_boundaries() -> None:
    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["referenceTruthRequired"]
        and schema["x-glio-contract"]["benchmarkPackageRequired"]
        and schema["x-glio-contract"]["controlsRequired"]
        and schema["x-glio-contract"]["adjudicationRequired"]
        and schema["x-glio-contract"]["endpointDefinitionRequired"]
        and schema["x-glio-contract"]["provenanceRequired"]
        and schema["x-glio-contract"]["inclusionAndChallengeSetRequired"]
        and schema["x-glio-contract"]["leakageAuditRequired"]
        and schema["x-glio-contract"]["lockProcedureRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "complex activity"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2101_OUTPUT_MEDIA_TYPE
    assert M2101_PROVISIONAL_ABI is True


def test_endpoint_definition_keeps_parent_and_metric_typed() -> None:
    endpoint = EndpointDefinition(
        endpoint_id="endpoint-1",
        name="Complex activity reference endpoint",
        definition="Reference truth for complex activity.",
        metric="calibration_error",
        acceptance_tolerance="Within preregistered tolerance.",
        evidence=(_evidence(),),
    )
    assert endpoint.target == "complex activity"
    assert endpoint.metric == "calibration_error"
    assert ReferenceKind.CHALLENGE_SET.value == "challenge_set"


def _artifact(name: str, version: str = "0.1.0") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version=version,
        digest="sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        media_type="application/json",
    )


def _evidence(name: str = "artifact-1") -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name),
        role="evidence",
        claim="Caller-declared benchmark evidence.",
    )


def _context(request_id: str = "request-1") -> ExecutionContext:
    artifact = _artifact("context-artifact")
    upstream = UpstreamDecisionReference(
        decision_id="decision-accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )
    identity = IdentityLineageReference(
        decision_id="identity-resolved",
        state=IdentityLineageState.RESOLVED,
        policy_version="1.0.0",
        binding_digest="sha256:" + "b" * 64,
        evidence=artifact,
    )
    consent = ConsentReference(
        decision_id="consent-granted",
        state=ConsentState.GRANTED,
        policy_version="1.0.0",
        evidence=artifact,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="test-actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=upstream,
            identity_lineage=identity,
            provenance=upstream,
            consent=consent,
            quality=upstream,
            support=upstream,
            intended_use=upstream,
        ),
    )


def _entry(identifier: str, kind: ReferenceKind) -> ReferenceEntry:
    return ReferenceEntry(
        reference_id=identifier,
        kind=kind,
        artifact=_artifact(identifier),
        expected_label="known complex activity reference",
        inclusion_reason="registered benchmark material",
        provenance_artifact=_artifact(identifier + "-provenance"),
        challenge_set=kind is ReferenceKind.CHALLENGE_SET,
        uncertainty=UncertaintyProfile(
            **cast(
                "Any",
                {
                    field: UncertaintyEstimate(
                        state=EstimateState.NOT_ESTIMABLE,
                        rationale="caller did not provide a calibrated estimate",
                    )
                    for field in (
                        "measurement",
                        "sampling",
                        "parameter",
                        "model_form",
                        "identification",
                        "support",
                        "transport",
                    )
                },
            )
        ),
        evidence=(_evidence(identifier),),
    )


def _request() -> CurateComplexActivityReferenceTruthRequest:
    references = (
        _entry("calibrator-1", ReferenceKind.CALIBRATOR),
        _entry("challenge-1", ReferenceKind.CHALLENGE_SET),
    )
    controls = (
        _entry("positive-control-1", ReferenceKind.POSITIVE_CONTROL),
        _entry("negative-control-1", ReferenceKind.NEGATIVE_CONTROL),
    )
    ids = tuple(item.reference_id for item in (*references, *controls))
    endpoint = EndpointDefinition(
        endpoint_id="endpoint-1",
        name="Complex activity reference endpoint",
        definition="Reference truth for complex activity.",
        metric="calibration_error",
        acceptance_tolerance="Within preregistered tolerance.",
        evidence=(_evidence("endpoint-evidence"),),
    )
    configuration = BenchmarkConfiguration(
        configuration_id="configuration-1",
        version="0.1.0",
    )
    return CurateComplexActivityReferenceTruthRequest(
        request_id="request-1",
        context=_context(),
        endpoint=endpoint,
        references=references,
        controls=controls,
        inclusions=tuple(
            InclusionDecision(
                reference_id=identifier,
                included=True,
                rationale="meets locked benchmark inclusion policy",
                leakage_audit="audited against challenge partition",
                evidence=(_evidence(identifier + "-inclusion"),),
            )
            for identifier in ids
        ),
        adjudications=tuple(
            AdjudicationRecord(
                reference_id=identifier,
                status=AdjudicationStatus.LOCKED,
                reviewer_tokens=("reviewer-a", "reviewer-b"),
                agreement_statement="Independent reviewers agree.",
                evidence=(_evidence(identifier + "-adjudication"),),
            )
            for identifier in ids
        ),
        configuration=configuration,
        source_artifacts=(_artifact("source-1"),),
    )


def _package(request: CurateComplexActivityReferenceTruthRequest) -> ReferenceTruthPackage:
    base = {
        "package_id": "package-1",
        "version": "0.1.0",
        "endpoint": request.endpoint,
        "references": request.references,
        "controls": request.controls,
        "inclusions": request.inclusions,
        "adjudications": request.adjudications,
        "challenge_set_ids": ("challenge-1",),
        "configuration": request.configuration,
        "lock_digest": "sha256:" + "0" * 64,
        "locked": True,
        "evidence": (_evidence("package-evidence"),),
    }
    provisional = ReferenceTruthPackage.model_construct(**cast("Any", base))
    base["lock_digest"] = package_lock_digest(provisional)
    return ReferenceTruthPackage(**cast("Any", base))


def _provenance() -> ProvenanceRecord:
    artifact_digest = "sha256:" + "c" * 64
    states = {
        ControlRole.APPROVED_CONFIGURATION: "accepted",
        ControlRole.IDENTITY_LINEAGE: "resolved",
        ControlRole.PROVENANCE: "accepted",
        ControlRole.CONSENT: "granted",
        ControlRole.QUALITY: "accepted",
        ControlRole.SUPPORT: "accepted",
        ControlRole.INTENDED_USE: "accepted",
    }
    return ProvenanceRecord(
        activity_id="activity-1",
        actor_id="test-actor",
        module_id="GLIO-PROTEOGEN-M21-01",
        module_version="0.1.0-provisional",
        generated_at=datetime(2026, 8, 16, tzinfo=UTC),
        input_digests=(artifact_digest,),
        configuration_digest=artifact_digest,
        consent_decision_id="consent-granted",
        consent_state=ConsentState.GRANTED,
        consent_policy_version="1.0.0",
        consent_evidence_digest=artifact_digest,
        control_decisions=tuple(
            ControlDecisionRecord(
                role=role,
                decision_id="control-" + role.value,
                state=state,
                policy_version="1.0.0",
                evidence_digest=artifact_digest,
                subject_digest=artifact_digest if role is ControlRole.IDENTITY_LINEAGE else None,
            )
            for role, state in states.items()
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        **cast(
            "Any",
            {
                field: UncertaintyEstimate(
                    state=EstimateState.NOT_ESTIMABLE,
                    rationale="reference truth calibration is not inferred by this module",
                )
                for field in (
                    "measurement",
                    "sampling",
                    "parameter",
                    "model_form",
                    "identification",
                    "support",
                    "transport",
                )
            },
        )
    )


def _result(
    request: CurateComplexActivityReferenceTruthRequest,
) -> ComplexActivityReferenceTruthResult:
    package = _package(request)
    base = {
        "result_id": result_identifier(request),
        "request_digest": canonical_request_digest(request),
        "result_digest": "sha256:" + "0" * 64,
        "request": request,
        "status": CurationStatus.CURATED,
        "package": package,
        "findings": (),
        "abstention_reason": None,
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="supported_locked_reference_truth",
            rationale="all required controls and lock evidence are present",
        ),
        "uncertainty": _uncertainty(),
        "provenance": _provenance(),
        "evidence": (_evidence("result-evidence"),),
        "limitations": (
            Limitation(
                code="caller_declared_reference_truth",
                statement="Issuer authority is not authenticated.",
            ),
        ),
        "human_review_required": True,
    }
    provisional = ComplexActivityReferenceTruthResult.model_construct(**cast("Any", base))
    base["result_digest"] = result_payload_digest(provisional)
    return ComplexActivityReferenceTruthResult(**cast("Any", base))


def test_locked_package_and_result_replay_canonical_digests() -> None:
    request = _request()
    package = _package(request)
    result = _result(request)
    assert package.lock_digest == package_lock_digest(package)
    assert result.request_digest == canonical_request_digest(request)
    assert result.result_digest == result_payload_digest(result)
    assert result.package == package


def test_request_rejects_control_kind_in_reference_partition() -> None:
    request = _request()
    bad = request.references[0].model_copy(update={"kind": ReferenceKind.POSITIVE_CONTROL})
    with pytest.raises(ValueError, match="references may not be control"):
        CurateComplexActivityReferenceTruthRequest(
            **request.model_dump(
                mode="python",
                include={
                    "operation",
                    "contract_version",
                    "request_id",
                    "context",
                    "endpoint",
                    "controls",
                    "inclusions",
                    "adjudications",
                    "configuration",
                    "source_artifacts",
                    "supersedes_result_digest",
                },
                exclude_unset=False,
                exclude_none=False,
                round_trip=True,
            ),
            references=(bad, request.references[1]),
        )


def test_locked_package_rejects_pending_adjudication_and_bad_lock() -> None:
    request = _request()
    pending = request.adjudications[0].model_copy(update={"status": AdjudicationStatus.PENDING})
    package = _package(request)
    pending_package = package.model_copy(
        update={"adjudications": (pending, *package.adjudications[1:])}
    )
    with pytest.raises(ValueError, match="pending"):
        ReferenceTruthPackage(**pending_package.model_dump())
    with pytest.raises(ValueError, match="lock digest"):
        ReferenceTruthPackage(
            **package.model_copy(update={"lock_digest": "sha256:" + "f" * 64}).model_dump()
        )


def test_result_id_and_package_equality_bind_replay() -> None:
    request = _request()
    result = _result(request)
    changed_context = request.context.model_copy(update={"request_id": "request-changed"})
    changed = request.model_copy(
        update={"request_id": "request-changed", "context": changed_context}
    )
    with pytest.raises(ValueError, match="result id"):
        ComplexActivityReferenceTruthResult(
            **cast(
                "Any",
                result.model_dump(
                    mode="python",
                    exclude={"result_id"},
                    exclude_none=False,
                    round_trip=True,
                ),
            ),
            result_id="result-tampered",
        )
    with pytest.raises(ValueError, match="request digest"):
        ComplexActivityReferenceTruthResult(
            **cast(
                "Any",
                result.model_dump(
                    mode="python",
                    exclude={"request", "result_id"},
                    exclude_none=False,
                    round_trip=True,
                ),
            ),
            request=changed,
            result_id=result_identifier(changed),
        )


def test_engine_curates_locked_package_and_replays_exactly() -> None:
    request = _request()
    service = M2101Service()
    result = service.execute(request)
    assert result.status is CurationStatus.CURATED
    assert result.package is not None
    assert result.package.lock_digest == package_lock_digest(result.package)
    assert service.verify_replay(result) == result


def test_pending_adjudication_abstains_without_package() -> None:
    request = _request()
    pending = request.adjudications[0].model_copy(update={"status": AdjudicationStatus.PENDING})
    pending_request = request.model_copy(
        update={"adjudications": (pending, *request.adjudications[1:])}
    )
    result = M2101Service().execute(pending_request)
    assert result.status is CurationStatus.ABSTAINED
    assert result.package is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert any(finding.code.value == "adjudication_pending" for finding in result.findings)


def test_denied_upstream_support_fails_closed_before_curation() -> None:
    request = _request()
    denied_support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    denied_references = request.context.references.model_copy(update={"support": denied_support})
    denied_context = request.context.model_copy(update={"references": denied_references})
    denied_request = request.model_copy(update={"context": denied_context})
    with pytest.raises(M2101AuthorizationError):
        M2101Service().execute(denied_request)


def test_plugin_parses_json_once_and_requires_validation_capability() -> None:
    request = _request()
    plugin = M2101Plugin(M2101Service())
    validated = plugin.validate(ReferenceTruthSubmission(request=request.model_dump_json()))
    result = plugin.run(validated)
    assert result.status is CurationStatus.CURATED
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", request))


def test_fastapi_validate_curate_verify_and_sanitized_tamper() -> None:
    request = _request()
    client = TestClient(create_app(M2101Service()))
    request_json = request.model_dump(mode="json")
    schemas = client.get("/v1/modules/M21-01/schemas")
    assert schemas.status_code == _HTTP_OK
    assert set(schemas.json()) == {
        "request",
        "output",
        "reference",
        "endpoint",
        "inclusion",
        "adjudication",
        "configuration",
        "package",
        "finding",
    }
    validated = client.post("/v1/modules/M21-01/validate", json=request_json)
    assert validated.status_code == _HTTP_OK
    curated = client.post("/v1/modules/M21-01/curate", json=request_json)
    assert curated.status_code == _HTTP_OK
    result = curated.json()
    verified = client.post("/v1/modules/M21-01/verify", json={"result": result})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    tampered = {**result, "result_id": "tampered-result"}
    assert (
        client.post("/v1/modules/M21-01/verify", json={"result": tampered}).status_code
        == _HTTP_UNPROCESSABLE
    )


def test_typer_export_validate_and_no_overwrite(tmp_path: Any) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request))
    output_path = tmp_path / "schema.json"
    runner = CliRunner()
    exported = runner.invoke(
        cli_app,
        ["export-schema", "request", "--output", str(output_path)],
    )
    assert exported.exit_code == 0
    assert output_path.exists()
    assert (
        runner.invoke(
            cli_app,
            ["export-schema", "request", "--output", str(output_path)],
        ).exit_code
        != 0
    )
    validated = runner.invoke(cli_app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    result_path = tmp_path / "result.json"
    curated = runner.invoke(
        cli_app,
        ["curate", str(request_path), "--output", str(result_path)],
    )
    assert curated.exit_code == 0
    verified = runner.invoke(cli_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert '"verified": true' in verified.stdout
