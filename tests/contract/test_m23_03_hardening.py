"""Deep contract and replay closure for provisional M23-03."""

from __future__ import annotations

from datetime import UTC, datetime
from math import nan
from typing import Any, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m23_03 import (
    M2303_M2302_INPUT_MEDIA_TYPE,
    BaselineKind,
    BaselineRun,
    BenchmarkDossier,
    BenchmarkMetric,
    BenchmarkStatus,
    ComponentAblation,
    ComputeMatchedComparison,
    LockedSplit,
    RunVariantPeptideInternalBenchmarkRequest,
    ValidationStatus,
    canonical_request_digest,
    contract_json_schemas,
    normalized_request,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

_SCHEMA_COUNT = 9


def _artifact(label: str, media_type: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2303.{label}",
        version="0.1.0",
        digest="sha256:" + (label.encode().hex() + "0" * 64)[:64],
        media_type=media_type,
    )


def _evidence(label: str = "evidence") -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="Caller-declared benchmark evidence.",
    )


def _decision(role: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"m2303.{role}.decision",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="0.1.0",
        evidence=_artifact(f"{role}-decision"),
    )


def _context(request_id: str) -> ExecutionContext:
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2303.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2303.identity.decision",
                state=IdentityLineageState.RESOLVED,
                policy_version="0.1.0",
                binding_digest=_artifact("identity-binding").digest,
                evidence=_artifact("identity-evidence"),
            ),
            provenance=_decision("provenance"),
            consent=ConsentReference(
                decision_id="m2303.consent.decision",
                state=ConsentState.GRANTED,
                policy_version="0.1.0",
                evidence=_artifact("consent-evidence"),
            ),
            quality=_decision("quality"),
            support=_decision("support"),
            intended_use=_decision("intended-use"),
        ),
    )


def _metric(metric_id: str, *, candidate: float = 0.6) -> BenchmarkMetric:
    return BenchmarkMetric(
        metric_id=metric_id,
        metric_name=metric_id,
        baseline_value=0.5,
        candidate_value=candidate,
        tolerance=0.2,
        status=ValidationStatus.PASS,
        evidence=(_evidence(metric_id),),
    )


def _baseline(run_id: str, kind: BaselineKind) -> BaselineRun:
    return BaselineRun(
        run_id=run_id,
        kind=kind,
        model_name=f"model-{kind.value}",
        compute_units=10.0,
        metrics=(_metric(f"{run_id}.metric"),),
        evidence=(_evidence(run_id),),
    )


def _dossier() -> BenchmarkDossier:
    simple = _baseline("baseline-simple", BaselineKind.SIMPLE)
    mature = _baseline("baseline-mature", BaselineKind.MATURE)
    return BenchmarkDossier(
        dossier_id="dossier-1",
        version="0.1.0",
        split=LockedSplit(
            split_id="split-1",
            version="0.1.0",
            train_examples=10,
            validation_examples=5,
            test_examples=5,
            random_seed=7,
            evidence=(_evidence("split"),),
        ),
        baselines=(simple, mature),
        ablations=(
            ComponentAblation(
                ablation_id="ablation-1",
                component="variant-prior",
                with_component_score=0.7,
                without_component_score=0.5,
                score_delta=0.2,
                compute_units=10.0,
                status=ValidationStatus.PASS,
                evidence=(_evidence("ablation"),),
            ),
        ),
        comparisons=(
            ComputeMatchedComparison(
                comparison_id="comparison-1",
                reference_run_id=simple.run_id,
                candidate_run_id=mature.run_id,
                reference_compute_units=10.0,
                candidate_compute_units=10.0,
                compute_tolerance=0.0,
                reference_score=0.5,
                candidate_score=0.7,
                status=ValidationStatus.PASS,
                evidence=(_evidence("comparison"),),
            ),
        ),
        metrics=(_metric("dossier-metric"),),
        evidence=(_evidence("dossier"),),
    )


def _request(request_id: str = "request-1") -> RunVariantPeptideInternalBenchmarkRequest:
    upstream = _artifact("m2302-result", M2303_M2302_INPUT_MEDIA_TYPE)
    return RunVariantPeptideInternalBenchmarkRequest(
        request_id=request_id,
        context=_context(request_id),
        upstream_result=upstream,
        split=_dossier().split,
        baseline_runs=_dossier().baselines,
        ablations=_dossier().ablations,
        comparisons=_dossier().comparisons,
        source_artifacts=(upstream,),
    )


def test_schema_metadata_and_replay_identity_are_explicit() -> None:
    schemas = contract_json_schemas()
    typed_schemas = cast("dict[str, dict[str, Any]]", schemas)
    assert len(typed_schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in typed_schemas.values())
    request = _request()
    projected = normalized_request(request)
    assert canonical_request_digest(projected) == canonical_request_digest(request)
    assert result_identifier(projected) == result_identifier(request)
    assert result_payload_digest({"result_id": "result-1", "value": "a"}) != result_payload_digest(
        {"result_id": "result-1", "value": "b"}
    )


def test_metric_numeric_and_status_closures_reject_adversarial_values() -> None:
    with pytest.raises(ValidationError, match=r"finite|finite number|nan"):
        _metric("nan-metric", candidate=nan)
    with pytest.raises(ValidationError, match="passing metric"):
        _metric("bad-pass", candidate=1.0)
    with pytest.raises(ValidationError, match="failing metric"):
        BenchmarkMetric(
            metric_id="bad-fail",
            metric_name="bad-fail",
            baseline_value=0.5,
            candidate_value=0.6,
            tolerance=0.2,
            status=ValidationStatus.FAIL,
            evidence=(_evidence("bad-fail"),),
        )


def test_ablation_and_compute_matching_are_canonical() -> None:
    with pytest.raises(ValidationError, match="score delta"):
        ComponentAblation(
            ablation_id="ablation-bad",
            component="variant-prior",
            with_component_score=0.7,
            without_component_score=0.5,
            score_delta=0.1,
            compute_units=10.0,
            status=ValidationStatus.PASS,
            evidence=(_evidence("ablation-bad"),),
        )
    comparison = _dossier().comparisons[0]
    with pytest.raises(ValidationError, match="compute-matched"):
        comparison.__class__.model_validate(
            comparison.model_dump(mode="python") | {"candidate_compute_units": 11.0},
            strict=True,
        )


def test_dossier_requires_both_baselines_and_declared_comparison_runs() -> None:
    dossier = _dossier()
    with pytest.raises(ValidationError, match="simple and mature"):
        dossier.__class__.model_validate(
            dossier.model_dump(mode="python") | {"baselines": (dossier.baselines[0],)},
            strict=True,
        )
    with pytest.raises(ValidationError, match="declared baseline"):
        dossier.__class__.model_validate(
            dossier.model_dump(mode="python")
            | {
                "comparisons": (
                    dossier.comparisons[0].model_copy(update={"candidate_run_id": "unknown"}),
                )
            },
            strict=True,
        )


def test_request_binds_context_media_and_unique_source_closure() -> None:
    request = _request()
    assert request.context.request_id == request.request_id
    with pytest.raises(ValidationError, match="execution context"):
        request.__class__.model_validate(
            request.model_dump(mode="python") | {"context": _context("different")},
            strict=True,
        )
    with pytest.raises(ValidationError, match="exactly one declared M23-02"):
        request.__class__.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (_artifact("unrelated-source"),)},
            strict=True,
        )
    with pytest.raises(ValidationError, match="M23-02"):
        request.__class__.model_validate(
            request.model_dump(mode="python")
            | {"upstream_result": _artifact("wrong", "application/json")},
            strict=True,
        )


def test_abstention_status_enum_has_no_implicit_negative_state() -> None:
    assert BenchmarkStatus.ABSTAINED.value == "abstained"
    with pytest.raises(AssertionError):
        assert cast("object", BenchmarkStatus.ABSTAINED) is cast(
            "object", BenchmarkStatus.COMPLETED
        )
