"""Focused and adversarial contract coverage for provisional M21-03."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from glio_proteogen.contracts.m21_03 import (
    M2103_DOSSIER_SHA256,
    M2103_DOSSIER_SLICE,
    M2103_M2102_INPUT_MEDIA_TYPE,
    M2103_OUTPUT_MEDIA_TYPE,
    M2103_PROVISIONAL_ABI,
    BaselineKind,
    BaselineRun,
    BenchmarkDossier,
    BenchmarkMetric,
    BenchmarkStatus,
    ComplexActivityInternalBenchmarkResult,
    ComponentAblation,
    ComputeMatchedComparison,
    LockedSplit,
    RunComplexActivityInternalBenchmarkRequest,
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

_SCHEMA_COUNT = 9


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest="sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        media_type=media_type,
    )


def _evidence(name: str = "evidence-1") -> EvidenceReference:
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


def _metric(metric_id: str = "metric-1") -> BenchmarkMetric:
    return BenchmarkMetric(
        metric_id=metric_id,
        metric_name="balanced_accuracy",
        baseline_value=0.5,
        candidate_value=0.7,
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


def _request() -> RunComplexActivityInternalBenchmarkRequest:
    upstream = _artifact("synthetic-truth", M2103_M2102_INPUT_MEDIA_TYPE)
    return RunComplexActivityInternalBenchmarkRequest(
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


def _dossier(request: RunComplexActivityInternalBenchmarkRequest) -> BenchmarkDossier:
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


def _provenance() -> ProvenanceRecord:
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
        module_id="GLIO-PROTEOGEN-M21-03",
        module_version="0.1.0-provisional",
        generated_at=datetime(2026, 8, 16, tzinfo=UTC),
        input_digests=(sha256_digest("synthetic-truth"),),
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
    request: RunComplexActivityInternalBenchmarkRequest,
) -> ComplexActivityInternalBenchmarkResult:
    support = SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="benchmark_supported",
        rationale="Caller-declared benchmark inputs satisfy the provisional boundary.",
    )
    provisional = ComplexActivityInternalBenchmarkResult.model_construct(
        result_id=result_identifier(request),
        request_digest=canonical_request_digest(request),
        result_digest=sha256_digest("placeholder"),
        request=request,
        status=BenchmarkStatus.COMPLETED,
        dossier=_dossier(request),
        support_decision=support,
        uncertainty=_uncertainty(),
        provenance=_provenance(),
        limitations=(
            Limitation(code="metadata_only", statement="No parent conclusion is emitted."),
        ),
    )
    return ComplexActivityInternalBenchmarkResult.model_validate(
        provisional.model_copy(update={"result_digest": result_payload_digest(provisional)}),
        strict=True,
    )


def test_provisional_schemas_require_locked_benchmark_controls() -> None:
    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["nestedValidationRequired"]
        and schema["x-glio-contract"]["lockedSplitsRequired"]
        and schema["x-glio-contract"]["simpleBaselineRequired"]
        and schema["x-glio-contract"]["matureBaselineRequired"]
        and schema["x-glio-contract"]["componentAblationRequired"]
        and schema["x-glio-contract"]["computeMatchedComparisonRequired"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m21-02+json")
        and schema["x-glio-contract"]["parentTarget"] == "complex activity"
        and schema["x-glio-contract"]["dossierSha256"] == M2103_DOSSIER_SHA256
        and schema["x-glio-contract"]["dossierSlice"] == M2103_DOSSIER_SLICE
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2103_OUTPUT_MEDIA_TYPE
    assert M2103_PROVISIONAL_ABI is True


def test_request_closure_binds_identity_input_and_comparison_ids() -> None:
    request = _request()
    with pytest.raises(ValueError, match="request id"):
        RunComplexActivityInternalBenchmarkRequest.model_validate(
            request.model_copy(update={"context": _context("other-request")}), strict=True
        )
    with pytest.raises(ValueError, match="source artifacts must include"):
        RunComplexActivityInternalBenchmarkRequest.model_validate(
            request.model_copy(update={"source_artifacts": (_artifact("other"),)}), strict=True
        )
    with pytest.raises(ValueError, match="comparison must reference"):
        RunComplexActivityInternalBenchmarkRequest.model_validate(
            request.model_copy(
                update={
                    "comparisons": (
                        _comparison().model_copy(update={"reference_run_id": "unknown-run"}),
                    )
                }
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="simple baseline"):
        RunComplexActivityInternalBenchmarkRequest.model_validate(
            request.model_copy(
                update={"baseline_runs": (_baseline("mature-only", BaselineKind.MATURE),)}
            ),
            strict=True,
        )


def test_nested_dossier_closure_rejects_duplicate_or_unknown_references() -> None:
    request = _request()
    dossier = _dossier(request)
    with pytest.raises(ValueError, match="baseline metric ids"):
        BenchmarkDossier.model_validate(
            dossier.model_copy(
                update={
                    "baselines": (
                        request.baseline_runs[0].model_copy(
                            update={"metrics": (_metric(), _metric())}
                        ),
                        request.baseline_runs[1],
                    )
                }
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="mature baseline"):
        BenchmarkDossier.model_validate(
            dossier.model_copy(
                update={
                    "baselines": (
                        request.baseline_runs[0],
                        request.baseline_runs[0].model_copy(update={"run_id": "simple-2"}),
                    )
                }
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="known baseline"):
        BenchmarkDossier.model_validate(
            dossier.model_copy(
                update={
                    "comparisons": (
                        _comparison().model_copy(update={"candidate_run_id": "unknown-run"}),
                    )
                }
            ),
            strict=True,
        )


def test_component_ablation_and_compute_matching_are_exact() -> None:
    with pytest.raises(ValueError, match="score delta"):
        ComponentAblation.model_validate(
            _ablation().model_copy(update={"score_delta": 0.1}), strict=True
        )
    with pytest.raises(ValueError, match="compute-matched"):
        ComputeMatchedComparison.model_validate(
            _comparison().model_copy(update={"candidate_compute_units": 12.0}), strict=True
        )


def test_result_replay_identity_digest_and_completion_closure() -> None:
    request = _request()
    result = _completed_result(request)
    assert result.result_id == result_identifier(request)
    assert result.result_digest == result_payload_digest(result)
    with pytest.raises(ValueError, match="result id"):
        ComplexActivityInternalBenchmarkResult.model_validate(
            result.model_copy(update={"result_id": "m2103.result.tampered"}), strict=True
        )
    with pytest.raises(ValueError, match="result digest"):
        ComplexActivityInternalBenchmarkResult.model_validate(
            result.model_copy(update={"result_digest": sha256_digest("tampered")}), strict=True
        )
    assert result.dossier is not None
    with pytest.raises(ValueError, match="baseline run ids"):
        ComplexActivityInternalBenchmarkResult.model_validate(
            result.model_copy(
                update={
                    "dossier": result.dossier.model_copy(
                        update={"baselines": (request.baseline_runs[0], request.baseline_runs[0])}
                    )
                }
            ),
            strict=True,
        )


def test_abstention_requires_safe_status_and_no_dossier() -> None:
    request = _request()
    support = SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code="upstream_unsupported",
        rationale="Caller-declared upstream support is unavailable.",
    )
    provisional = ComplexActivityInternalBenchmarkResult.model_construct(
        result_id=result_identifier(request),
        request_digest=canonical_request_digest(request),
        result_digest=sha256_digest("placeholder"),
        request=request,
        status=BenchmarkStatus.ABSTAINED,
        abstention_reason="M21-02 input is unsupported.",
        support_decision=support,
        uncertainty=_uncertainty(),
        provenance=_provenance(),
        limitations=(Limitation(code="unsupported", statement="No benchmark is emitted."),),
    )
    result = ComplexActivityInternalBenchmarkResult.model_validate(
        provisional.model_copy(update={"result_digest": result_payload_digest(provisional)}),
        strict=True,
    )
    assert result.status is BenchmarkStatus.ABSTAINED
    with pytest.raises(ValueError, match="abstained result"):
        ComplexActivityInternalBenchmarkResult.model_validate(
            result.model_copy(update={"dossier": _dossier(request)}), strict=True
        )
