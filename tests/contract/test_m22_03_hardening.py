"""Adversarial contract and replay coverage for provisional M22-03."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m22_03 import (
    M2203_DOSSIER_SHA256,
    M2203_DOSSIER_SLICE,
    M2203_M2202_INPUT_MEDIA_TYPE,
    M2203_MODULE_ID,
    BaselineKind,
    BaselineRun,
    BenchmarkDossier,
    BenchmarkMetric,
    BenchmarkStatus,
    ComponentAblation,
    ComputeMatchedComparison,
    LockedSplit,
    ProteinRnaDiscordanceInternalBenchmarkResult,
    RunProteinRnaDiscordanceInternalBenchmarkRequest,
    ValidationStatus,
    canonical_request_digest,
    contract_json_schemas,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest="sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        media_type=media_type,
    )


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name),
        role="evidence",
        claim="Caller-declared benchmark evidence.",
    )


def _context(request_id: str = "request-1") -> ExecutionContext:
    artifact = _artifact("context-artifact")
    accepted = UpstreamDecisionReference(
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
        actor_id="benchmark-actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=identity,
            provenance=accepted,
            consent=consent,
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _metric(metric_id: str = "metric-1", *, candidate: float = 0.7) -> BenchmarkMetric:
    return BenchmarkMetric(
        metric_id=metric_id,
        metric_name="balanced_accuracy",
        baseline_value=0.5,
        candidate_value=candidate,
        tolerance=0.1,
        status=ValidationStatus.PASS,
        evidence=(_evidence(metric_id + "-evidence"),),
    )


def _baseline(run_id: str, kind: BaselineKind) -> BaselineRun:
    return BaselineRun(
        run_id=run_id,
        kind=kind,
        model_name=kind.value + " baseline",
        compute_units=10.0,
        metrics=(_metric(run_id + "-metric"),),
        evidence=(_evidence(run_id + "-evidence"),),
    )


def _split() -> LockedSplit:
    return LockedSplit(
        split_id="split-1",
        version="1.0.0",
        train_examples=10,
        validation_examples=5,
        test_examples=5,
        random_seed=17,
        evidence=(_evidence("split-evidence"),),
    )


def _ablation() -> ComponentAblation:
    return ComponentAblation(
        ablation_id="ablation-1",
        component="pathway_context",
        with_component_score=0.8,
        without_component_score=0.6,
        score_delta=0.2,
        compute_units=10.0,
        status=ValidationStatus.PASS,
        evidence=(_evidence("ablation-evidence"),),
    )


def _comparison() -> ComputeMatchedComparison:
    return ComputeMatchedComparison(
        comparison_id="comparison-1",
        reference_run_id="simple-run",
        candidate_run_id="mature-run",
        reference_compute_units=10.0,
        candidate_compute_units=10.0,
        compute_tolerance=0.0,
        reference_score=0.5,
        candidate_score=0.7,
        status=ValidationStatus.PASS,
        evidence=(_evidence("comparison-evidence"),),
    )


def _request() -> RunProteinRnaDiscordanceInternalBenchmarkRequest:
    upstream = _artifact("synthetic-truth", M2203_M2202_INPUT_MEDIA_TYPE)
    return RunProteinRnaDiscordanceInternalBenchmarkRequest(
        request_id="request-1",
        context=_context(),
        upstream_result=upstream,
        split=_split(),
        baseline_runs=(
            _baseline("simple-run", BaselineKind.SIMPLE),
            _baseline("mature-run", BaselineKind.MATURE),
        ),
        ablations=(_ablation(),),
        comparisons=(_comparison(),),
        source_artifacts=(upstream, _artifact("benchmark-material")),
    )


def _dossier(request: RunProteinRnaDiscordanceInternalBenchmarkRequest) -> BenchmarkDossier:
    return BenchmarkDossier(
        dossier_id="dossier-1",
        version="1.0.0",
        split=request.split,
        baselines=request.baseline_runs,
        ablations=request.ablations,
        comparisons=request.comparisons,
        metrics=(_metric(),),
        evidence=(_evidence("dossier-evidence"),),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="Caller did not provide a calibrated uncertainty estimate.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
    )


def _provenance(request: RunProteinRnaDiscordanceInternalBenchmarkRequest) -> ProvenanceRecord:
    states: dict[ControlRole, str] = {
        ControlRole.APPROVED_CONFIGURATION: UpstreamDecisionState.ACCEPTED.value,
        ControlRole.IDENTITY_LINEAGE: IdentityLineageState.RESOLVED.value,
        ControlRole.PROVENANCE: UpstreamDecisionState.ACCEPTED.value,
        ControlRole.CONSENT: ConsentState.GRANTED.value,
        ControlRole.QUALITY: UpstreamDecisionState.ACCEPTED.value,
        ControlRole.SUPPORT: UpstreamDecisionState.ACCEPTED.value,
        ControlRole.INTENDED_USE: UpstreamDecisionState.ACCEPTED.value,
    }
    return ProvenanceRecord(
        activity_id="benchmark-activity",
        actor_id="benchmark-actor",
        module_id=M2203_MODULE_ID,
        module_version="0.1.0-provisional",
        generated_at=datetime(2026, 8, 16, tzinfo=UTC),
        input_digests=(request.upstream_result.digest,),
        configuration_digest=sha256_digest("benchmark-config"),
        consent_decision_id="consent-granted",
        consent_state=ConsentState.GRANTED,
        consent_policy_version="1.0.0",
        consent_evidence_digest=sha256_digest("context-artifact"),
        control_decisions=tuple(
            ControlDecisionRecord(
                role=role,
                decision_id="decision-" + role.value,
                state=state,
                policy_version="1.0.0",
                evidence_digest=sha256_digest("evidence-" + role.value),
                subject_digest=sha256_digest("subject")
                if role is ControlRole.IDENTITY_LINEAGE
                else None,
            )
            for role, state in states.items()
        ),
    )


def _completed_result(
    request: RunProteinRnaDiscordanceInternalBenchmarkRequest,
) -> ProteinRnaDiscordanceInternalBenchmarkResult:
    result = ProteinRnaDiscordanceInternalBenchmarkResult.model_construct(
        result_id=result_identifier(request),
        request_digest=canonical_request_digest(request),
        result_digest=sha256_digest("placeholder"),
        request=request,
        status=BenchmarkStatus.COMPLETED,
        dossier=_dossier(request),
        support_decision=SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="benchmark_supported",
            rationale="Inputs satisfy the provisional benchmark boundary.",
        ),
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        limitations=(Limitation(code="metadata_only", statement="No parent conclusion."),),
    )
    return ProteinRnaDiscordanceInternalBenchmarkResult.model_validate(
        result.model_copy(update={"result_digest": result_payload_digest(result)}), strict=True
    )


def _request_update(
    request: RunProteinRnaDiscordanceInternalBenchmarkRequest, **updates: object
) -> RunProteinRnaDiscordanceInternalBenchmarkRequest:
    payload = request.model_dump(mode="python")
    payload.update(updates)
    return RunProteinRnaDiscordanceInternalBenchmarkRequest.model_validate(payload, strict=True)


def _result_update(
    result: ProteinRnaDiscordanceInternalBenchmarkResult, **updates: object
) -> ProteinRnaDiscordanceInternalBenchmarkResult:
    payload = result.model_dump(mode="python")
    payload.update(updates)
    return ProteinRnaDiscordanceInternalBenchmarkResult.model_validate(payload, strict=True)


def test_authority_and_schema_metadata_are_explicit() -> None:
    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    assert M2203_DOSSIER_SHA256.startswith("sha256:")
    assert M2203_DOSSIER_SLICE.endswith(":7684-7724")
    assert all(
        schema["x-glio-contract"]["authoritySha256"] == M2203_DOSSIER_SHA256
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["authoritySlice"] == M2203_DOSSIER_SLICE
        for schema in schemas.values()
    )


def test_request_closes_context_media_and_source_artifacts() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="context request id"):
        _request_update(request, context=_context("other-request"))
    with pytest.raises(ValidationError, match="provisional M22-02"):
        _request_update(request, upstream_result=_artifact("wrong", "application/wrong"))
    with pytest.raises(ValidationError, match="include the upstream"):
        _request_update(request, source_artifacts=(_artifact("benchmark-material"),))
    with pytest.raises(ValidationError, match="source artifact ids"):
        _request_update(request, source_artifacts=(request.source_artifacts[0],) * 2)


def test_request_requires_exact_baselines_and_known_comparisons() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="exactly simple and mature"):
        _request_update(
            request,
            baseline_runs=(_baseline("simple-run", BaselineKind.SIMPLE),) * 2,
        )
    bad_comparison = request.comparisons[0].model_copy(update={"reference_run_id": "unknown-run"})
    with pytest.raises(ValidationError, match="known baselines"):
        _request_update(request, comparisons=(bad_comparison,))


def test_dossier_closes_baselines_comparisons_and_metric_ids() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="exactly simple and mature"):
        BenchmarkDossier(
            dossier_id="dossier-1",
            version="1.0.0",
            split=request.split,
            baselines=(
                _baseline("simple-run", BaselineKind.SIMPLE),
                _baseline("simple-run-2", BaselineKind.SIMPLE),
            ),
            ablations=request.ablations,
            comparisons=request.comparisons,
            metrics=(_metric(),),
            evidence=(_evidence("dossier-evidence"),),
        )
    duplicate_metric = _metric("simple-run-metric")
    with pytest.raises(ValidationError, match="benchmark dossier ids"):
        BenchmarkDossier(
            dossier_id="dossier-1",
            version="1.0.0",
            split=request.split,
            baselines=request.baseline_runs,
            ablations=request.ablations,
            comparisons=request.comparisons,
            metrics=(duplicate_metric, duplicate_metric),
            evidence=(_evidence("dossier-evidence"),),
        )


def test_numeric_contracts_reject_non_finite_and_inconsistent_values() -> None:
    with pytest.raises(ValidationError, match="finite"):
        _metric(candidate=math.nan)
    with pytest.raises(ValidationError, match="score delta"):
        ComponentAblation(
            ablation_id="ablation-bad",
            component="pathway_context",
            with_component_score=0.8,
            without_component_score=0.6,
            score_delta=0.3,
            compute_units=10.0,
            status=ValidationStatus.PASS,
            evidence=(_evidence("bad-ablation"),),
        )
    with pytest.raises(ValidationError, match="compute-matched"):
        _request_update(
            _request(),
            comparisons=(_comparison().model_copy(update={"candidate_compute_units": 11.0}),),
        )


def test_result_replay_identity_provenance_and_findings_are_closed() -> None:
    request = _request()
    result = _completed_result(request)
    assert result.result_id == result_identifier(request)
    assert result.request_digest == canonical_request_digest(request)
    assert result.result_digest == result_payload_digest(result)
    with pytest.raises(ValidationError, match="deterministic request identity"):
        _result_update(result, result_id="other-result")
    with pytest.raises(ValidationError, match="provenance module id"):
        _result_update(
            result,
            provenance=_provenance(request).model_copy(
                update={"module_id": "GLIO-PROTEOGEN-M22-01"}
            ),
        )
