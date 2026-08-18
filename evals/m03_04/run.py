"""Build and execute the locked M03-04 protein-inference quality corpus."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, cast

from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from typer.testing import CliRunner

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m03_02.run import build_scenario_request as build_m0302_request
from evals.m03_03.run import (
    ScenarioOptions as M0303ScenarioOptions,
)
from evals.m03_03.run import (
    build_scenario as build_m0303_scenario,
)
from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m03_03 import (
    IngestProteinInferenceRawInputsRequest,
    ProteinInferenceAdmissionDisposition,
    ProteinInferenceRawRole,
    lineage_ingestion_receipt,
    protocol_ingestion_receipt,
    source_manifest_digest,
)
from glio_proteogen.contracts.m03_03 import (
    configuration_digest as m0303_configuration_digest,
)
from glio_proteogen.contracts.m03_04 import (
    M0304_MAX_CANONICAL_REQUEST_BYTES,
    M0304_MAX_COUNT,
    M0304_MAX_EVIDENCE,
    M0304_MAX_FINDINGS,
    M0304_MAX_LINEAGE_ARTIFACTS,
    M0304_MAX_PROFILES,
    M0304_MAX_SOURCES,
    ComputeProteinInferenceQualityRequest,
    ProteinInferenceAssayQualityProfile,
    ProteinInferenceQualityCounts,
    ProteinInferenceQualityDisposition,
    ProteinInferenceQualityFactLedger,
    ProteinInferenceQualityFactStates,
    ProteinInferenceQualityMetricCode,
    ProteinInferenceQualityMetricDirection,
    ProteinInferenceQualityMetricResult,
    ProteinInferenceQualityMetricStatus,
    ProteinInferenceQualityObservationState,
    ProteinInferenceQualityPolicy,
    ProteinInferenceQualityResult,
    ProteinInferenceQualityThreshold,
    ProteinInferenceRawQualityClaimReceipt,
    ProteinInferenceRawQualityReceipt,
    ProteinInferenceRawQualitySourceReceipt,
    canonical_request_digest,
    claim_binding_digest,
    configuration_digest,
    fact_ledger_digest,
    policy_digest,
    profile_digest,
    raw_quality_receipt,
    raw_quality_receipt_digest,
    result_payload_digest,
    source_binding_digest,
    threshold_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, ExecutionContext
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_02_identity_lineage import (
    reconcile_protein_inference_identity_lineage,
)
from glio_proteogen.modules.c03_protein_inference.m03_03_raw_ingestion import (
    ingest_protein_inference_raw_inputs,
)
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics import (
    M0304Plugin,
    M0304ProteinInferenceQualityEngine,
    M0304Service,
    compute_protein_inference_quality,
    preflight_protein_inference_quality_authorization,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from glio_proteogen.contracts.m03_01 import ProteinInferenceApplicability
    from glio_proteogen.contracts.m03_03 import ProteinInferenceRawAdmissionResult

MODULE_ID = "GLIO-PROTEOGEN-M03-04"
ROOT = Path(__file__).parents[2]
SCENARIO_PATH = ROOT / "tests" / "fixtures" / "m03_04" / "scenarios.json"
_EXPECTED_GROUP_COUNT = 8
_EXPECTED_CASE_COUNT = 57
_HTTP_OK = 200
_SCHEMA_COUNT = 9


class ScenarioGroup(TypedDict):
    group_id: str
    case_ids: list[str]


class Corpus(TypedDict):
    module_id: str
    scenario_groups: list[ScenarioGroup]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


class _MissingLedgerError(ValueError):
    pass


class _ExpectedFailureMissingError(AssertionError):
    pass


class _HostileLedger:
    traversals = 0

    def __getattribute__(self, name: str) -> object:
        if name == "traversals":
            return object.__getattribute__(self, name)
        type(self).traversals += 1
        raise _ExpectedFailureMissingError


@dataclass(frozen=True, slots=True)
class Scenario:
    """One genuine M01-02→M03-03 handoff plus an exact aggregate fact ledger."""

    request: ComputeProteinInferenceQualityRequest
    upstream_result: ProteinInferenceRawAdmissionResult
    source_count: int
    claim_count: int


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m0304.{name}",
        version="1.0.0",
        digest=sha256_digest({"m0304_evidence": name}),
        media_type="application/json",
    )


def _threshold(code: ProteinInferenceQualityMetricCode) -> ProteinInferenceQualityThreshold:
    at_most = code is ProteinInferenceQualityMetricCode.PROTEIN_GROUP_AMBIGUITY_BURDEN
    return ProteinInferenceQualityThreshold(
        metric_code=code,
        direction=(
            ProteinInferenceQualityMetricDirection.AT_MOST
            if at_most
            else ProteinInferenceQualityMetricDirection.AT_LEAST
        ),
        pass_threshold_ppm=200_000 if at_most else 700_000,
        warning_threshold_ppm=300_000 if at_most else 500_000,
        required=True,
        evidence=_artifact(f"threshold.{code.value}"),
    )


def _policy(
    receipt: ProteinInferenceRawQualityReceipt,
    applicability: ProteinInferenceApplicability,
) -> ProteinInferenceQualityPolicy:
    profile = ProteinInferenceAssayQualityProfile(
        profile_id="profile.synthetic.m0304.shotgun-dda",
        version="1.0.0",
        applicability=applicability,
        approved_assay_protocol_versions=(receipt.assay_protocol_version,),
        approved_controlled_vocabulary_versions=(receipt.controlled_vocabulary_version,),
        approved_unit_system_versions=(receipt.unit_system_version,),
        controls_applicable=True,
        thresholds=tuple(_threshold(code) for code in ProteinInferenceQualityMetricCode),
        evidence=_artifact("profile.shotgun-dda"),
    )
    return ProteinInferenceQualityPolicy(
        policy_id="policy.synthetic.m0304",
        version="1.0.0",
        max_sources=M0304_MAX_SOURCES,
        max_lineage_artifacts=M0304_MAX_LINEAGE_ARTIFACTS,
        profiles=(profile,),
        evidence=_artifact("policy"),
        reviewed_by="reviewer.synthetic.clinical-science",
        reviewed_at=datetime(2026, 8, 12, 16, 0, tzinfo=UTC),
    )


def _counts() -> ProteinInferenceQualityCounts:
    return ProteinInferenceQualityCounts(
        eligible_peptide_evidence_count=100,
        unique_assigned_peptide_evidence_count=75,
        shared_group_assigned_peptide_evidence_count=20,
        unassigned_peptide_evidence_count=5,
        total_group_member_assignment_count=100,
        ambiguous_group_member_assignment_count=10,
        eligible_proteoform_claim_count=20,
        discriminating_proteoform_claim_count=15,
        detection_eligible_group_count=20,
        quantifiable_group_count=16,
        left_censored_group_count=4,
        detection_missing_group_count=0,
        competition_eligible_group_count=20,
        competition_closed_group_count=18,
        control_expected_group_count=10,
        control_recovered_group_count=9,
        context_applicable_binding_count=10,
        context_coherent_binding_count=10,
    )


def _states() -> ProteinInferenceQualityFactStates:
    observed = ProteinInferenceQualityObservationState.OBSERVED
    return ProteinInferenceQualityFactStates(
        peptide_assignment=observed,
        ambiguity_burden=observed,
        proteoform_discrimination=observed,
        detection_support=ProteinInferenceQualityObservationState.CENSORED,
        competition_closure=observed,
        control_recovery=observed,
        sample_context_coherence=observed,
    )


def _fact_ledger(
    receipt: ProteinInferenceRawQualityReceipt,
    applicability: ProteinInferenceApplicability,
) -> ProteinInferenceQualityFactLedger:
    states = _states()
    counts = _counts()
    evidence = _artifact("fact-ledger")
    recorded_at = datetime(2026, 8, 12, 17, 0, tzinfo=UTC)
    payload = {
        "ledger_id": "ledger.synthetic.m0304",
        "version": "1.0.0",
        "admission_result_digest": receipt.admission_result_digest,
        "protocol_result_digest": receipt.protocol_result_digest,
        "search_space_digest": receipt.search_space_digest,
        "identity_resolution_digest": receipt.identity_resolution_digest,
        "source_manifest_digest": receipt.source_manifest_digest,
        "applicability": applicability,
        "source_binding_digest": source_binding_digest(receipt.sources),
        "claim_binding_digest": claim_binding_digest(receipt.claims),
        "states": states,
        "counts": counts,
        "evidence": evidence,
        "recorded_at": recorded_at,
    }
    return ProteinInferenceQualityFactLedger(
        ledger_id="ledger.synthetic.m0304",
        version="1.0.0",
        admission_result_digest=receipt.admission_result_digest,
        protocol_result_digest=receipt.protocol_result_digest,
        search_space_digest=receipt.search_space_digest,
        identity_resolution_digest=receipt.identity_resolution_digest,
        source_manifest_digest=receipt.source_manifest_digest,
        applicability=applicability,
        source_binding_digest=source_binding_digest(receipt.sources),
        claim_binding_digest=claim_binding_digest(receipt.claims),
        states=states,
        counts=counts,
        evidence=evidence,
        recorded_at=recorded_at,
        ledger_digest=fact_ledger_digest(payload),
    )


def build_scenario() -> Scenario:
    """Execute the genuine upstream chain and construct one closed M03-04 request."""

    m0303 = build_m0303_scenario()
    admission = ingest_protein_inference_raw_inputs(m0303.request, m0303.sources)
    receipt = raw_quality_receipt(admission)
    applicability = m0303.protocol_result.protocol_schema.applicability
    policy = _policy(receipt, applicability)
    ledger = _fact_ledger(receipt, applicability)
    references = admission.request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    context = ExecutionContext(
        request_id="request.synthetic.m0304",
        actor_id="actor.synthetic.clinical-science",
        occurred_at=datetime(2026, 8, 13, 0, 0, tzinfo=UTC),
        references=references.model_copy(update={"approved_configuration": approved}),
    )
    request = ComputeProteinInferenceQualityRequest(
        context=context,
        raw_quality_receipt=receipt,
        fact_ledger=ledger,
        policy=policy,
    )
    return Scenario(
        request=request,
        upstream_result=admission,
        source_count=len(receipt.sources),
        claim_count=len(receipt.claims),
    )


def build_scenario_request() -> ComputeProteinInferenceQualityRequest:
    """Public evidence helper for runtime, interface, and benchmark parity tests."""

    return build_scenario().request


def _request_with_ledger(
    request: ComputeProteinInferenceQualityRequest,
    *,
    counts: ProteinInferenceQualityCounts | None = None,
    states: ProteinInferenceQualityFactStates | None = None,
    ledger_updates: dict[str, object] | None = None,
) -> ComputeProteinInferenceQualityRequest:
    """Rebuild one digest-closed ledger mutation without touching upstream evidence."""

    ledger = request.fact_ledger
    if ledger is None:
        raise _MissingLedgerError
    payload = ledger.model_dump(mode="python", exclude={"ledger_digest"})
    payload.update(ledger_updates or {})
    if counts is not None:
        payload["counts"] = counts
    if states is not None:
        payload["states"] = states
    mutated = ProteinInferenceQualityFactLedger(
        **payload,
        ledger_digest=fact_ledger_digest(payload),
    )
    return ComputeProteinInferenceQualityRequest(
        **{
            **request.model_dump(mode="python"),
            "fact_ledger": mutated,
        }
    )


def _request_with_policy(
    request: ComputeProteinInferenceQualityRequest,
    policy: ProteinInferenceQualityPolicy,
) -> ComputeProteinInferenceQualityRequest:
    """Rebind the approved configuration when mutating a quality policy."""

    references = request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    context = request.context.model_copy(
        update={"references": references.model_copy(update={"approved_configuration": approved})}
    )
    return ComputeProteinInferenceQualityRequest(
        **{
            **request.model_dump(mode="python"),
            "context": context,
            "policy": policy,
        }
    )


def _request_from_admission(
    template: ComputeProteinInferenceQualityRequest,
    admission: ProteinInferenceRawAdmissionResult,
) -> ComputeProteinInferenceQualityRequest:
    """Project one real non-traversable M03-03 result into a safe M03-04 request."""

    receipt = raw_quality_receipt(admission)
    references = admission.request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(template.policy)}
            )
        }
    )
    context = ExecutionContext(
        request_id=f"request.synthetic.m0304.{admission.disposition.value}",
        actor_id="actor.synthetic.clinical-science",
        occurred_at=template.context.occurred_at,
        references=references.model_copy(update={"approved_configuration": approved}),
    )
    return ComputeProteinInferenceQualityRequest(
        context=context,
        raw_quality_receipt=receipt,
        fact_ledger=None,
        policy=template.policy,
    )


def _m0303_safe_failure_results() -> dict[str, ProteinInferenceRawAdmissionResult]:
    """Execute three genuine M03-03 failure modes without fabricated result envelopes."""

    rejected_scenario = build_m0303_scenario()
    rejected_sources = dict(rejected_scenario.sources)
    rejected_sources["source.spectra.mzml"] += b"tamper"
    rejected = ingest_protein_inference_raw_inputs(
        rejected_scenario.request,
        rejected_sources,
    )

    canonical_vcf = rejected_scenario.sources["source.variants.vcf"]
    foreign_vcf = canonical_vcf.replace(
        b"build.synthetic.reference:1.0.0",
        b"build.synthetic.foreign:2.0.0",
    )
    quarantined_scenario = build_m0303_scenario(
        options=M0303ScenarioOptions(
            raw_overrides={ProteinInferenceRawRole.GENOMIC_CONTEXT: foreign_vcf}
        )
    )
    quarantined = ingest_protein_inference_raw_inputs(
        quarantined_scenario.request,
        quarantined_scenario.sources,
    )

    canonical_mzml = rejected_scenario.sources["source.spectra.mzml"]
    unsupported_mzml = canonical_mzml.replace(b'version="1.1.0"', b'version="9.0.0"')
    abstained_scenario = build_m0303_scenario(
        options=M0303ScenarioOptions(
            raw_overrides={ProteinInferenceRawRole.SPECTRA: unsupported_mzml}
        )
    )
    abstained = ingest_protein_inference_raw_inputs(
        abstained_scenario.request,
        abstained_scenario.sources,
    )
    return {
        "rejected": rejected,
        "quarantined": quarantined,
        "abstained": abstained,
    }


def _m0303_unsupported_shape_result() -> ProteinInferenceRawAdmissionResult:
    """Execute a genuine 256-claim M03-02 result through M03-03 safe admission."""

    lineage = reconcile_protein_inference_identity_lineage(build_m0302_request("maximum"))
    template = build_m0303_scenario().request
    references = lineage.request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": m0303_configuration_digest(template.policy)}
            )
        }
    )
    context = ExecutionContext(
        request_id="request.synthetic.m0303.unsupported-shape",
        actor_id="actor.synthetic.quality",
        occurred_at=datetime(2026, 8, 12, 15, 0, tzinfo=UTC),
        references=references.model_copy(update={"approved_configuration": approved}),
    )
    request = IngestProteinInferenceRawInputsRequest(
        context=context,
        protocol_receipt=protocol_ingestion_receipt(lineage.request.protocol_result),
        lineage_receipt=lineage_ingestion_receipt(lineage),
        policy=template.policy,
        source_manifest_digest=source_manifest_digest(()),
        sources=(),
    )
    return ingest_protein_inference_raw_inputs(request, {})


def _corpus() -> Corpus:
    return cast("Corpus", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _static_checks(corpus: Corpus, scenario: Scenario) -> list[EvalCheck]:
    groups = corpus["scenario_groups"]
    cases = [case_id for group in groups for case_id in group["case_ids"]]
    request = scenario.request
    ledger = request.fact_ledger
    return [
        EvalCheck(
            name="corpus.exact_inventory",
            passed=(
                corpus["module_id"] == MODULE_ID
                and len(groups) == _EXPECTED_GROUP_COUNT
                and len(cases) == len(set(cases)) == _EXPECTED_CASE_COUNT
            ),
            detail=f"groups={len(groups)};cases={len(cases)};unique={len(set(cases))}",
        ),
        EvalCheck(
            name="builder.genuine_chain_and_receipt",
            passed=(
                request.raw_quality_receipt.admission_result_digest
                == scenario.upstream_result.result_digest
                and scenario.source_count == len(request.raw_quality_receipt.sources)
                and scenario.claim_count == len(request.raw_quality_receipt.claims)
            ),
            detail=f"sources={scenario.source_count};claims={scenario.claim_count}",
        ),
        EvalCheck(
            name="builder.fact_ledger_closure",
            passed=(
                ledger is not None
                and ledger.ledger_digest == fact_ledger_digest(ledger)
                and ledger.source_binding_digest
                == source_binding_digest(request.raw_quality_receipt.sources)
                and ledger.claim_binding_digest
                == claim_binding_digest(request.raw_quality_receipt.claims)
            ),
            detail=(ledger.ledger_digest if ledger is not None else "ledger=none"),
        ),
    ]


def _scenario_check(case_id: str, *, passed: bool, detail: str) -> EvalCheck:
    return EvalCheck(name=f"scenario.{case_id}", passed=passed, detail=detail)


def _fails(operation: Callable[[], object]) -> bool:
    try:
        operation()
    except (TypeError, ValueError):
        return True
    return False


def _authorization_fails(candidate: object) -> bool:
    return _fails(lambda: preflight_protein_inference_quality_authorization(candidate))


def _metric_by_code(
    result: ProteinInferenceQualityResult,
) -> dict[ProteinInferenceQualityMetricCode, ProteinInferenceQualityMetricResult]:
    return {item.metric_code: item for item in result.metrics}


def _genuine_and_metric_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    result = compute_protein_inference_quality(request)
    receipt = request.raw_quality_receipt
    ledger = request.fact_ledger
    metrics = _metric_by_code(result)
    expected_ratios = {
        ProteinInferenceQualityMetricCode.ADMITTED_SOURCE_COMPLETENESS: (13, 13),
        ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE: (95, 100),
        ProteinInferenceQualityMetricCode.PROTEIN_GROUP_AMBIGUITY_BURDEN: (10, 100),
        ProteinInferenceQualityMetricCode.PROTEOFORM_DISCRIMINATION_COVERAGE: (15, 20),
        ProteinInferenceQualityMetricCode.PROTEIN_GROUP_DETECTION_SUPPORT: (16, 20),
        ProteinInferenceQualityMetricCode.PROTEIN_GROUP_COMPETITION_CLOSURE: (18, 20),
        ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY: (9, 10),
        ProteinInferenceQualityMetricCode.SAMPLE_CONTEXT_BINDING_COHERENCE: (10, 10),
    }
    case_by_metric = {
        ProteinInferenceQualityMetricCode.ADMITTED_SOURCE_COMPLETENESS: (
            "admitted_source_completeness_uses_exact_integer_ratio"
        ),
        ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE: (
            "peptide_assignment_coverage_uses_exact_integer_ratio"
        ),
        ProteinInferenceQualityMetricCode.PROTEIN_GROUP_AMBIGUITY_BURDEN: (
            "protein_group_ambiguity_burden_uses_exact_integer_ratio"
        ),
        ProteinInferenceQualityMetricCode.PROTEOFORM_DISCRIMINATION_COVERAGE: (
            "proteoform_discrimination_coverage_uses_exact_integer_ratio"
        ),
        ProteinInferenceQualityMetricCode.PROTEIN_GROUP_DETECTION_SUPPORT: (
            "protein_group_detection_support_uses_exact_integer_ratio"
        ),
        ProteinInferenceQualityMetricCode.PROTEIN_GROUP_COMPETITION_CLOSURE: (
            "protein_group_competition_closure_uses_exact_integer_ratio"
        ),
        ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY: (
            "control_group_recovery_uses_exact_integer_ratio"
        ),
        ProteinInferenceQualityMetricCode.SAMPLE_CONTEXT_BINDING_COHERENCE: (
            "sample_context_binding_coherence_uses_exact_integer_ratio"
        ),
    }
    metric_checks = [
        _scenario_check(
            case_by_metric[code],
            passed=(
                metrics[code].numerator == numerator
                and metrics[code].denominator == denominator
                and metrics[code].value_ppm
                == (numerator * 1_000_000 + denominator // 2) // denominator
            ),
            detail=f"ratio={numerator}/{denominator};ppm={metrics[code].value_ppm}",
        )
        for code, (numerator, denominator) in expected_ratios.items()
    ]
    profile = request.policy.profiles[0]
    boundary_thresholds = tuple(
        item.model_copy(
            update=(
                {
                    "pass_threshold_ppm": metrics[item.metric_code].value_ppm,
                    "warning_threshold_ppm": metrics[item.metric_code].value_ppm,
                }
                if metrics[item.metric_code].value_ppm is not None
                else {}
            )
        )
        for item in profile.thresholds
    )
    boundary_profile = profile.model_copy(update={"thresholds": boundary_thresholds})
    boundary_policy = request.policy.model_copy(update={"profiles": (boundary_profile,)})
    boundary_result = compute_protein_inference_quality(
        _request_with_policy(request, boundary_policy)
    )
    return [
        _scenario_check(
            "genuine_public_m0102_m0301_m0302_m0303_handoff",
            passed=(
                scenario.upstream_result.disposition.value == "validated"
                and receipt.admission_result_digest == scenario.upstream_result.result_digest
            ),
            detail=receipt.admission_result_digest,
        ),
        _scenario_check(
            "canonical_raw_quality_receipt_binds_exact_m0303_result",
            passed=(
                receipt.receipt_digest == raw_quality_receipt_digest(receipt)
                and receipt.admission_request_digest == scenario.upstream_result.request_digest
                and receipt.source_manifest_digest
                == scenario.upstream_result.receipt.source_manifest_digest
            ),
            detail=receipt.receipt_digest,
        ),
        _scenario_check(
            "source_and_claim_projections_close_over_complete_upstream_handoff",
            passed=(
                len(receipt.sources) == receipt.source_count == scenario.source_count
                and len(receipt.claims) == receipt.lineage_artifact_count == scenario.claim_count
            ),
            detail=f"sources={len(receipt.sources)};claims={len(receipt.claims)}",
        ),
        _scenario_check(
            "aggregate_fact_ledger_binds_sources_claims_counts_states_and_provenance",
            passed=(
                ledger is not None
                and ledger.source_binding_digest == source_binding_digest(receipt.sources)
                and ledger.claim_binding_digest == claim_binding_digest(receipt.claims)
                and ledger.ledger_digest == fact_ledger_digest(ledger)
            ),
            detail=ledger.ledger_digest if ledger is not None else "ledger=none",
        ),
        _scenario_check(
            "fact_ledger_receipt_and_graph_bindings_are_non_circular",
            passed=(
                ledger is not None
                and ledger.admission_result_digest == receipt.admission_result_digest
                and ledger.source_manifest_digest == receipt.source_manifest_digest
            ),
            detail="receipt digests are ledger inputs; ledger digest is externally carried",
        ),
        _scenario_check(
            "qualified_result_retains_complex_activity_parent_without_inference",
            passed=(
                result.disposition is ProteinInferenceQualityDisposition.QUALIFIED
                and result.parent_target == "complex_activity"
                and not result.emits_complex_activity
                and not result.infers_protein
                and not result.infers_kinase_activity
            ),
            detail=f"disposition={result.disposition.value};parent={result.parent_target}",
        ),
        _scenario_check(
            "canonical_result_emits_exactly_eight_quality_metrics",
            passed=(
                len(result.metrics) == len(ProteinInferenceQualityMetricCode)
                and set(metrics) == set(ProteinInferenceQualityMetricCode)
            ),
            detail=f"metrics={len(result.metrics)};findings={len(result.findings)}",
        ),
        *metric_checks,
        _scenario_check(
            "at_least_at_most_threshold_boundaries_and_first_excess_are_exact",
            passed=(
                boundary_result.disposition is ProteinInferenceQualityDisposition.QUALIFIED
                and all(
                    item.status is ProteinInferenceQualityMetricStatus.PASS
                    for item in boundary_result.metrics
                )
            ),
            detail="each exact threshold equality passes under its declared direction",
        ),
    ]


def _zero_partition_counts(
    counts: ProteinInferenceQualityCounts,
    *,
    partition: str,
) -> ProteinInferenceQualityCounts:
    updates_by_partition: dict[str, dict[str, int]] = {
        "proteoform": {
            "eligible_proteoform_claim_count": 0,
            "discriminating_proteoform_claim_count": 0,
        },
        "control": {
            "control_expected_group_count": 0,
            "control_recovered_group_count": 0,
        },
    }
    return counts.model_copy(update=updates_by_partition[partition])


def _ambiguity_and_missingness_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    canonical = compute_protein_inference_quality(request)
    canonical_metrics = _metric_by_code(canonical)
    ledger = request.fact_ledger
    if ledger is None:
        raise _MissingLedgerError

    missing_states = ledger.states.model_copy(
        update={"proteoform_discrimination": ProteinInferenceQualityObservationState.MISSING}
    )
    missing_request = _request_with_ledger(
        request,
        counts=_zero_partition_counts(ledger.counts, partition="proteoform"),
        states=missing_states,
    )
    missing_result = compute_protein_inference_quality(missing_request)
    missing_metric = _metric_by_code(missing_result)[
        ProteinInferenceQualityMetricCode.PROTEOFORM_DISCRIMINATION_COVERAGE
    ]

    zero_request = _request_with_ledger(
        request,
        counts=_zero_partition_counts(ledger.counts, partition="proteoform"),
    )
    zero_result = compute_protein_inference_quality(zero_request)
    zero_metric = _metric_by_code(zero_result)[
        ProteinInferenceQualityMetricCode.PROTEOFORM_DISCRIMINATION_COVERAGE
    ]

    na_states = ledger.states.model_copy(
        update={"control_recovery": ProteinInferenceQualityObservationState.NOT_APPLICABLE}
    )
    na_request = _request_with_ledger(
        request,
        counts=_zero_partition_counts(ledger.counts, partition="control"),
        states=na_states,
    )
    profile = na_request.policy.profiles[0].model_copy(update={"controls_applicable": False})
    na_request = _request_with_policy(
        na_request,
        na_request.policy.model_copy(update={"profiles": (profile,)}),
    )
    na_result = compute_protein_inference_quality(na_request)
    na_metric = _metric_by_code(na_result)[ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY]
    peptide = canonical_metrics[ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE]
    ambiguity = canonical_metrics[ProteinInferenceQualityMetricCode.PROTEIN_GROUP_AMBIGUITY_BURDEN]
    detection = canonical_metrics[ProteinInferenceQualityMetricCode.PROTEIN_GROUP_DETECTION_SUPPORT]
    expected = ledger.counts
    return [
        _scenario_check(
            "shared_peptide_and_group_ambiguity_are_not_double_counted",
            passed=(
                peptide.numerator
                == expected.unique_assigned_peptide_evidence_count
                + expected.shared_group_assigned_peptide_evidence_count
                and peptide.denominator == expected.eligible_peptide_evidence_count
                and ambiguity.numerator == expected.ambiguous_group_member_assignment_count
                and ambiguity.denominator == expected.total_group_member_assignment_count
            ),
            detail="assignment=75 unique+20 shared/100;ambiguity=10/100",
        ),
        _scenario_check(
            "ambiguity_burden_retains_competing_explanations_without_resolution",
            passed=(
                ambiguity.metric_code
                is ProteinInferenceQualityMetricCode.PROTEIN_GROUP_AMBIGUITY_BURDEN
                and ambiguity.numerator == expected.ambiguous_group_member_assignment_count
                and not canonical.infers_identity
                and not canonical.infers_protein
            ),
            detail="10 ambiguous assignments retained; no identity/protein inference",
        ),
        _scenario_check(
            "detection_censored_observation_is_retained_outside_quantifiable_numerator",
            passed=(
                detection.observation_state is ProteinInferenceQualityObservationState.CENSORED
                and detection.numerator == expected.quantifiable_group_count
                and detection.denominator == expected.detection_eligible_group_count
                and detection.censored_count == expected.left_censored_group_count
            ),
            detail="quantifiable=16;left-censored=4;eligible=20",
        ),
        _scenario_check(
            "missing_proteoform_evidence_is_not_negative_evidence",
            passed=(
                missing_metric.observation_state is ProteinInferenceQualityObservationState.MISSING
                and missing_metric.numerator is None
                and missing_metric.denominator is None
                and missing_metric.value_ppm is None
            ),
            detail=f"state={missing_metric.observation_state.value};value=None",
        ),
        _scenario_check(
            "not_applicable_metric_is_distinct_from_missing_or_unsupported",
            passed=(
                na_metric.observation_state
                is ProteinInferenceQualityObservationState.NOT_APPLICABLE
                and na_metric.status is ProteinInferenceQualityMetricStatus.NOT_APPLICABLE
                and na_result.disposition is ProteinInferenceQualityDisposition.QUALIFIED
            ),
            detail=f"state={na_metric.observation_state.value};status={na_metric.status.value}",
        ),
        _scenario_check(
            "zero_denominator_metric_is_typed_not_evaluable",
            passed=(
                zero_metric.observation_state is ProteinInferenceQualityObservationState.OBSERVED
                and zero_metric.denominator == 0
                and zero_metric.value_ppm is None
                and zero_metric.status is ProteinInferenceQualityMetricStatus.NOT_EVALUABLE
            ),
            detail=f"denominator=0;status={zero_metric.status.value}",
        ),
        _scenario_check(
            "not_evaluable_required_metric_cannot_satisfy_required_threshold",
            passed=(
                zero_metric.required
                and zero_result.disposition is ProteinInferenceQualityDisposition.ABSTAINED
            ),
            detail=f"required=true;disposition={zero_result.disposition.value}",
        ),
    ]


def _profile_and_reference_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    canonical = compute_protein_inference_quality(request)
    receipt = request.raw_quality_receipt
    profile = request.policy.profiles[0]
    ledger = request.fact_ledger
    if ledger is None:
        raise _MissingLedgerError

    unsupported_profile = profile.model_copy(
        update={"approved_assay_protocol_versions": ("9.9.9",)}
    )
    unsupported_request = _request_with_policy(
        request,
        request.policy.model_copy(update={"profiles": (unsupported_profile,)}),
    )
    unsupported_result = compute_protein_inference_quality(unsupported_request)

    duplicate_profile_rejected = False
    second = profile.model_copy(update={"profile_id": "profile.synthetic.m0304.overlap"})
    try:
        ProteinInferenceQualityPolicy(
            **{
                **request.policy.model_dump(mode="python"),
                "profiles": (profile, second),
            }
        )
    except ValueError:
        duplicate_profile_rejected = True

    missing_control_states = ledger.states.model_copy(
        update={"control_recovery": ProteinInferenceQualityObservationState.MISSING}
    )
    missing_control_result = compute_protein_inference_quality(
        _request_with_ledger(
            request,
            counts=_zero_partition_counts(ledger.counts, partition="control"),
            states=missing_control_states,
        )
    )
    missing_control_metric = _metric_by_code(missing_control_result)[
        ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY
    ]

    drift_request = _request_with_ledger(
        request,
        ledger_updates={"search_space_digest": sha256_digest({"drift": "search-space"})},
    )
    drift_result = compute_protein_inference_quality(drift_request)
    exact_builds = {
        (
            source.role.value,
            source.build.declared_build_id,
            source.build.declared_build_version,
        )
        for source in receipt.sources
        if source.build.state.value == "exact"
    }
    expected = ledger.counts
    return [
        _scenario_check(
            "exact_assay_profile_is_selected_by_protocol_cv_and_unit_versions",
            passed=(
                receipt.assay_protocol_version in profile.approved_assay_protocol_versions
                and receipt.controlled_vocabulary_version
                in profile.approved_controlled_vocabulary_versions
                and receipt.unit_system_version in profile.approved_unit_system_versions
                and canonical.receipt.profile_digest is not None
            ),
            detail=f"profile={profile.profile_id}@{profile.version}",
        ),
        _scenario_check(
            "no_matching_assay_profile_abstains_as_unsupported",
            passed=(
                unsupported_result.disposition is ProteinInferenceQualityDisposition.ABSTAINED
                and not unsupported_result.metrics
                and any(
                    finding.code.value == "assay_profile_unsupported"
                    for finding in unsupported_result.findings
                )
            ),
            detail=f"disposition={unsupported_result.disposition.value};metrics=0",
        ),
        _scenario_check(
            "ambiguous_multiple_profile_match_is_rejected_by_policy_validation",
            passed=duplicate_profile_rejected,
            detail="overlapping match domains rejected during policy construction",
        ),
        _scenario_check(
            "control_group_reference_and_expected_counts_close_exactly",
            passed=(
                _metric_by_code(canonical)[
                    ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY
                ].numerator
                == expected.control_recovered_group_count
                and _metric_by_code(canonical)[
                    ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY
                ].denominator
                == expected.control_expected_group_count
            ),
            detail="recovered=9;expected=10",
        ),
        _scenario_check(
            "missing_required_control_group_is_not_evaluable",
            passed=(
                missing_control_metric.status is ProteinInferenceQualityMetricStatus.NOT_EVALUABLE
                and missing_control_result.disposition
                is ProteinInferenceQualityDisposition.ABSTAINED
            ),
            detail=f"status={missing_control_metric.status.value};disposition=abstained",
        ),
        _scenario_check(
            "search_space_protocol_or_reference_drift_is_quarantined",
            passed=(
                drift_result.disposition is ProteinInferenceQualityDisposition.QUARANTINED
                and not drift_result.metrics
                and any(
                    finding.code.value == "fact_ledger_binding_mismatch"
                    for finding in drift_result.findings
                )
            ),
            detail=f"disposition={drift_result.disposition.value};metrics=0",
        ),
        _scenario_check(
            "sample_context_build_cv_and_unit_disagreement_is_retained",
            passed=(
                len(exact_builds) >= len({role for role, _, _ in exact_builds})
                and receipt.controlled_vocabulary_id.startswith("vocabulary.")
                and receipt.unit_system_version in profile.approved_unit_system_versions
                and any(role == "genomic_context" for role, _, _ in exact_builds)
                and any(role == "ptm_vocabulary" for role, _, _ in exact_builds)
            ),
            detail=f"distinct exact build bindings retained={len(exact_builds)}",
        ),
    ]


def _safe_failure_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    safe_admissions = _m0303_safe_failure_results()
    safe_results = {
        name: compute_protein_inference_quality(_request_from_admission(request, admission))
        for name, admission in safe_admissions.items()
    }
    shape_admission = _m0303_unsupported_shape_result()
    shape_result = compute_protein_inference_quality(
        _request_from_admission(request, shape_admission)
    )

    mismatch_result = compute_protein_inference_quality(
        _request_with_ledger(
            request,
            ledger_updates={
                "admission_result_digest": sha256_digest({"stale": "admission-result"})
            },
        )
    )
    canonical = compute_protein_inference_quality(request)
    peptide_code = ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE
    profile = request.policy.profiles[0]
    warning_thresholds = tuple(
        item.model_copy(update={"pass_threshold_ppm": 960_000, "warning_threshold_ppm": 950_000})
        if item.metric_code is peptide_code
        else item
        for item in profile.thresholds
    )
    warning_profile = profile.model_copy(update={"thresholds": warning_thresholds})
    warning_result = compute_protein_inference_quality(
        _request_with_policy(
            request,
            request.policy.model_copy(update={"profiles": (warning_profile,)}),
        )
    )
    warning_metric = _metric_by_code(warning_result)[peptide_code]
    expected_dispositions = {
        "rejected": ProteinInferenceQualityDisposition.REJECTED,
        "quarantined": ProteinInferenceQualityDisposition.QUARANTINED,
        "abstained": ProteinInferenceQualityDisposition.ABSTAINED,
    }
    propagated = {
        name: (
            safe_admissions[name].disposition,
            result.disposition,
            len(result.metrics),
        )
        for name, result in safe_results.items()
    }
    safe_outputs = (*safe_results.values(), shape_result, mismatch_result)
    return [
        _scenario_check(
            "genuine_m0303_rejected_handoff_propagates_without_ledger_traversal",
            passed=(
                safe_admissions["rejected"].disposition
                is ProteinInferenceAdmissionDisposition.REJECTED
                and safe_results["rejected"].disposition
                is ProteinInferenceQualityDisposition.REJECTED
                and safe_results["rejected"].request.fact_ledger is None
                and not safe_results["rejected"].metrics
            ),
            detail="real checksum rejection; fact_ledger=None;metrics=0",
        ),
        _scenario_check(
            "genuine_m0303_quarantined_handoff_propagates_without_ledger_traversal",
            passed=(
                safe_admissions["quarantined"].disposition
                is ProteinInferenceAdmissionDisposition.QUARANTINED
                and safe_results["quarantined"].disposition
                is ProteinInferenceQualityDisposition.QUARANTINED
                and safe_results["quarantined"].request.fact_ledger is None
                and not safe_results["quarantined"].metrics
            ),
            detail="real governed-build disagreement; fact_ledger=None;metrics=0",
        ),
        _scenario_check(
            "genuine_m0303_abstained_handoff_propagates_without_ledger_traversal",
            passed=(
                safe_admissions["abstained"].disposition
                is ProteinInferenceAdmissionDisposition.ABSTAINED
                and safe_results["abstained"].disposition
                is ProteinInferenceQualityDisposition.ABSTAINED
                and safe_results["abstained"].request.fact_ledger is None
                and not safe_results["abstained"].metrics
            ),
            detail="real unsupported mzML profile; fact_ledger=None;metrics=0",
        ),
        _scenario_check(
            "receipt_ledger_binding_mismatch_fails_before_metric_evaluation",
            passed=(
                mismatch_result.disposition is ProteinInferenceQualityDisposition.QUARANTINED
                and not mismatch_result.metrics
                and any(
                    finding.code.value == "fact_ledger_binding_mismatch"
                    for finding in mismatch_result.findings
                )
            ),
            detail="re-digested stale admission binding;metrics=0",
        ),
        _scenario_check(
            "unsupported_lineage_shape_abstains_without_metric_evaluation",
            passed=(
                shape_admission.disposition is ProteinInferenceAdmissionDisposition.ABSTAINED
                and len(shape_admission.request.lineage_receipt.artifacts)
                > M0304_MAX_LINEAGE_ARTIFACTS
                and shape_result.disposition is ProteinInferenceQualityDisposition.ABSTAINED
                and shape_result.request.fact_ledger is None
                and not shape_result.metrics
            ),
            detail=(f"lineage={len(shape_admission.request.lineage_receipt.artifacts)};metrics=0"),
        ),
        _scenario_check(
            "reject_quarantine_abstain_warning_precedence_is_deterministic",
            passed=(
                all(
                    propagated[name][0].value == name
                    and propagated[name][1] is expected
                    and propagated[name][2] == 0
                    for name, expected in expected_dispositions.items()
                )
                and warning_metric.status is ProteinInferenceQualityMetricStatus.WARNING
                and warning_result.disposition is ProteinInferenceQualityDisposition.QUARANTINED
                and canonical.disposition is ProteinInferenceQualityDisposition.QUALIFIED
            ),
            detail="rejected>quarantined>abstained safe gates; required warning quarantines",
        ),
        _scenario_check(
            "safe_failure_emits_no_graph_or_metric_success_claims",
            passed=all(
                not result.metrics
                and not result.emits_complex_activity
                and not result.infers_identity
                and not result.infers_protein
                for result in safe_outputs
            ),
            detail=f"safe_results={len(safe_outputs)};all metrics empty",
        ),
    ]


def _capacity_request(
    request: ComputeProteinInferenceQualityRequest,
) -> ComputeProteinInferenceQualityRequest:
    """Build exact 64-source/48-claim projections with a re-bound aggregate ledger."""

    receipt = request.raw_quality_receipt
    ledger = request.fact_ledger
    if ledger is None:
        raise _MissingLedgerError
    peptide_claim = next(
        item for item in receipt.claims if item.claim_role.value == "peptide_evidence_manifest"
    )
    peptide_source = next(
        item for item in receipt.sources if item.bound_claim_id == peptide_claim.claim_id
    )
    claim_excess = M0304_MAX_LINEAGE_ARTIFACTS - len(receipt.claims)
    extra_claims: list[ProteinInferenceRawQualityClaimReceipt] = []
    extra_bound_sources: list[ProteinInferenceRawQualitySourceReceipt] = []
    for index in range(claim_excess):
        claim_id = f"claim.synthetic.m0304.capacity.{index:03d}"
        extra_claims.append(peptide_claim.model_copy(update={"claim_id": claim_id}))
        extra_bound_sources.append(
            peptide_source.model_copy(
                update={
                    "source_id": f"source.synthetic.m0304.capacity.bound.{index:03d}",
                    "bound_claim_id": claim_id,
                }
            )
        )
    sources = (*receipt.sources, *extra_bound_sources)
    unbound_excess = M0304_MAX_SOURCES - len(sources)
    unbound_template = next(
        item for item in receipt.sources if item.role is ProteinInferenceRawRole.SPECTRA
    )
    extra_unbound_sources = tuple(
        unbound_template.model_copy(
            update={"source_id": f"source.synthetic.m0304.capacity.unbound.{index:03d}"}
        )
        for index in range(unbound_excess)
    )
    sources = (*sources, *extra_unbound_sources)
    claims = (*receipt.claims, *extra_claims)
    receipt_payload = receipt.model_dump(mode="python", exclude={"receipt_digest"})
    receipt_payload.update(
        {
            "source_count": len(sources),
            "lineage_artifact_count": len(claims),
            "sources": sources,
            "claims": claims,
        }
    )
    capacity_receipt = ProteinInferenceRawQualityReceipt(
        **receipt_payload,
        receipt_digest=raw_quality_receipt_digest(receipt_payload),
    )
    ledger_payload = ledger.model_dump(mode="python", exclude={"ledger_digest"})
    ledger_payload.update(
        {
            "source_binding_digest": source_binding_digest(capacity_receipt.sources),
            "claim_binding_digest": claim_binding_digest(capacity_receipt.claims),
        }
    )
    capacity_ledger = ProteinInferenceQualityFactLedger(
        **ledger_payload,
        ledger_digest=fact_ledger_digest(ledger_payload),
    )
    return ComputeProteinInferenceQualityRequest(
        **{
            **request.model_dump(mode="python"),
            "raw_quality_receipt": capacity_receipt,
            "fact_ledger": capacity_ledger,
        }
    )


def build_capacity_scenario_request() -> ComputeProteinInferenceQualityRequest:
    """Build the exact supported 64-source and 48-lineage projection boundary."""

    return _capacity_request(build_scenario().request)


def _strict_capacity_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    plugin = M0304Plugin(M0304Service())
    request_bytes = canonical_json_bytes(request)
    hostile = _HostileLedger()
    denied_roles = (
        "approved_configuration",
        "identity_lineage",
        "provenance",
        "consent",
        "quality",
        "support",
        "intended_use",
    )
    _HostileLedger.traversals = 0
    authorization_denials: list[bool] = []
    for role in denied_roles:
        payload = request.model_dump(mode="python")
        payload["fact_ledger"] = hostile
        references = cast("dict[str, object]", payload["context"])["references"]
        reference_map = cast("dict[str, dict[str, object]]", references)
        reference_map[role]["state"] = "denied"
        authorization_denials.append(_authorization_fails(payload))

    duplicate = b'{"operation":"compute_protein_inference_quality",' + request_bytes[1:]
    duplicate_rejected = _fails(lambda: plugin.validate(duplicate))
    coerced = request.model_dump(mode="json")
    coerced["contract_version"] = 1
    unknown = request.model_dump(mode="json")
    unknown["unexpected"] = True
    nonfinite = request_bytes[:-1] + b',"supersedes_result_digest":NaN}'
    strict_failures = (
        _fails(lambda: plugin.validate(coerced)),
        _fails(lambda: plugin.validate(unknown)),
        _fails(lambda: plugin.validate(nonfinite)),
    )

    capacity_request = _capacity_request(request)
    capacity_result = compute_protein_inference_quality(capacity_request)
    capacity_receipt = capacity_request.raw_quality_receipt
    source_excess = (*capacity_receipt.sources, capacity_receipt.sources[-1])
    source_excess_rejected = _fails(
        lambda: ProteinInferenceRawQualityReceipt(
            **{
                **capacity_receipt.model_dump(mode="python", exclude={"receipt_digest"}),
                "source_count": len(source_excess),
                "sources": source_excess,
                "receipt_digest": raw_quality_receipt_digest(
                    {
                        **capacity_receipt.model_dump(mode="python", exclude={"receipt_digest"}),
                        "source_count": len(source_excess),
                        "sources": source_excess,
                    }
                ),
            }
        )
    )
    claim_excess = (*capacity_receipt.claims, capacity_receipt.claims[-1])
    claim_excess_rejected = _fails(
        lambda: ProteinInferenceRawQualityReceipt(
            **{
                **capacity_receipt.model_dump(mode="python", exclude={"receipt_digest"}),
                "lineage_artifact_count": len(claim_excess),
                "claims": claim_excess,
                "receipt_digest": raw_quality_receipt_digest(
                    {
                        **capacity_receipt.model_dump(mode="python", exclude={"receipt_digest"}),
                        "lineage_artifact_count": len(claim_excess),
                        "claims": claim_excess,
                    }
                ),
            }
        )
    )

    profile = request.policy.profiles[0]
    profiles = tuple(
        profile.model_copy(
            update={
                "profile_id": f"profile.synthetic.m0304.capacity.{index:02d}",
                "approved_assay_protocol_versions": (f"{index + 1}.0.0",),
                "approved_controlled_vocabulary_versions": (f"{index + 1}.0.0",),
                "approved_unit_system_versions": (f"{index + 1}.0.0",),
            }
        )
        for index in range(M0304_MAX_PROFILES)
    )
    maximum_profiles = request.policy.model_copy(update={"profiles": profiles})
    profile_excess_rejected = _fails(
        lambda: ProteinInferenceQualityPolicy(
            **{
                **maximum_profiles.model_dump(mode="python"),
                "profiles": (*profiles, profiles[-1]),
            }
        )
    )
    maximum_counts = ProteinInferenceQualityCounts(
        eligible_peptide_evidence_count=M0304_MAX_COUNT,
        unique_assigned_peptide_evidence_count=M0304_MAX_COUNT,
        shared_group_assigned_peptide_evidence_count=0,
        unassigned_peptide_evidence_count=0,
        total_group_member_assignment_count=M0304_MAX_COUNT,
        ambiguous_group_member_assignment_count=M0304_MAX_COUNT,
        eligible_proteoform_claim_count=M0304_MAX_COUNT,
        discriminating_proteoform_claim_count=M0304_MAX_COUNT,
        detection_eligible_group_count=M0304_MAX_COUNT,
        quantifiable_group_count=M0304_MAX_COUNT,
        left_censored_group_count=0,
        detection_missing_group_count=0,
        competition_eligible_group_count=M0304_MAX_COUNT,
        competition_closed_group_count=M0304_MAX_COUNT,
        control_expected_group_count=M0304_MAX_COUNT,
        control_recovered_group_count=M0304_MAX_COUNT,
        context_applicable_binding_count=M0304_MAX_COUNT,
        context_coherent_binding_count=M0304_MAX_COUNT,
    )
    count_excess_rejected = _fails(
        lambda: ProteinInferenceQualityCounts(
            **{
                **maximum_counts.model_dump(mode="python"),
                "eligible_peptide_evidence_count": M0304_MAX_COUNT + 1,
            }
        )
    )

    padded = request_bytes + b" " * (M0304_MAX_CANONICAL_REQUEST_BYTES - len(request_bytes))
    exact_cap_accepted = plugin.run(plugin.validate(padded))
    first_excess_rejected = _fails(lambda: plugin.validate(padded + b" "))
    schema = ProteinInferenceQualityResult.model_json_schema()
    schema_text = json.dumps(schema, sort_keys=True)
    installed_result_caps = all(
        str(value) in schema_text
        for value in (
            M0304_MAX_FINDINGS,
            M0304_MAX_EVIDENCE,
            len(ProteinInferenceQualityMetricCode),
        )
    )
    return [
        _scenario_check(
            "seven_control_authorization_matrix_precedes_hostile_request_traversal",
            passed=(
                all(authorization_denials)
                and len(authorization_denials) == len(denied_roles)
                and _HostileLedger.traversals == 0
            ),
            detail=f"denials={sum(authorization_denials)}/7;ledger_traversals=0",
        ),
        _scenario_check(
            "duplicate_json_object_key_is_rejected",
            passed=duplicate_rejected,
            detail="strict JSON rejected a duplicate operation key",
        ),
        _scenario_check(
            "scalar_coercion_nonfinite_and_unknown_field_are_rejected",
            passed=all(strict_failures),
            detail=f"rejected={sum(strict_failures)}/3",
        ),
        _scenario_check(
            "exact_installed_source_lineage_metric_finding_evidence_profile_and_count_caps_are_accepted",
            passed=(
                len(capacity_receipt.sources) == M0304_MAX_SOURCES
                and len(capacity_receipt.claims) == M0304_MAX_LINEAGE_ARTIFACTS
                and len(maximum_profiles.profiles) == M0304_MAX_PROFILES
                and maximum_counts.eligible_peptide_evidence_count == M0304_MAX_COUNT
                and len(capacity_result.metrics) == len(ProteinInferenceQualityMetricCode)
                and installed_result_caps
            ),
            detail="sources=64;lineage=48;profiles=16;counts=10000000;metrics=8",
        ),
        _scenario_check(
            "first_excess_source_lineage_metric_finding_evidence_profile_or_count_is_rejected",
            passed=(
                source_excess_rejected
                and claim_excess_rejected
                and profile_excess_rejected
                and count_excess_rejected
            ),
            detail="source,lineage,profile,count first excess rejected; result caps installed",
        ),
        _scenario_check(
            "canonical_request_exact_byte_cap_and_first_excess_are_enforced",
            passed=(
                len(padded) == M0304_MAX_CANONICAL_REQUEST_BYTES
                and exact_cap_accepted == compute_protein_inference_quality(request)
                and first_excess_rejected
            ),
            detail=f"accepted={len(padded)};rejected={len(padded) + 1}",
        ),
        _scenario_check(
            "hostile_fact_ledger_is_not_traversed_before_request_and_authorization_closure",
            passed=(_HostileLedger.traversals == 0 and all(authorization_denials)),
            detail="hostile ledger accessor count remains zero across seven denials",
        ),
    ]


def _semantically_reordered_request(
    request: ComputeProteinInferenceQualityRequest,
) -> ComputeProteinInferenceQualityRequest:
    receipt = request.raw_quality_receipt
    ledger = request.fact_ledger
    if ledger is None:
        raise _MissingLedgerError
    receipt_payload = receipt.model_dump(mode="python", exclude={"receipt_digest"})
    receipt_payload.update(
        {
            "sources": tuple(reversed(receipt.sources)),
            "claims": tuple(reversed(receipt.claims)),
        }
    )
    reordered_receipt = ProteinInferenceRawQualityReceipt(
        **receipt_payload,
        receipt_digest=raw_quality_receipt_digest(receipt_payload),
    )
    ledger_payload = ledger.model_dump(mode="python", exclude={"ledger_digest"})
    ledger_payload.update(
        {
            "source_binding_digest": source_binding_digest(reordered_receipt.sources),
            "claim_binding_digest": claim_binding_digest(reordered_receipt.claims),
        }
    )
    reordered_ledger = ProteinInferenceQualityFactLedger(
        **ledger_payload,
        ledger_digest=fact_ledger_digest(ledger_payload),
    )
    profile = request.policy.profiles[0]
    reordered_profile = profile.model_copy(
        update={"thresholds": tuple(reversed(profile.thresholds))}
    )
    policy = request.policy.model_copy(update={"profiles": (reordered_profile,)})
    rebound = _request_with_policy(request, policy)
    return ComputeProteinInferenceQualityRequest(
        **{
            **rebound.model_dump(mode="python"),
            "raw_quality_receipt": reordered_receipt,
            "fact_ledger": reordered_ledger,
        }
    )


def _result_forgery_rejected(
    result: ProteinInferenceQualityResult,
    mutate: Callable[[dict[str, object]], None],
) -> bool:
    payload = result.model_dump(mode="python")
    mutate(payload)
    payload["result_digest"] = result_payload_digest(payload)
    adapter = TypeAdapter(ProteinInferenceQualityResult)
    return _fails(lambda: adapter.validate_python(payload, strict=True))


def _canonical_privacy_forgery_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    result = compute_protein_inference_quality(request)
    reordered_request = _semantically_reordered_request(request)
    reordered_result = compute_protein_inference_quality(reordered_request)
    service = M0304Service()
    plugin = M0304Plugin(service)
    typed = compute_protein_inference_quality(request)
    dictionary = compute_protein_inference_quality(request.model_dump(mode="python"))
    strict_json = plugin.run(plugin.validate(canonical_json_bytes(request)))

    profile = request.policy.profiles[0]
    ledger = request.fact_ledger
    if ledger is None:
        raise _MissingLedgerError
    stable_digests = (
        canonical_request_digest(request),
        policy_digest(request.policy),
        profile_digest(profile),
        fact_ledger_digest(ledger),
        result.result_digest,
    )
    result_json = canonical_json_bytes(result).decode("utf-8").lower()
    forbidden_keys = {
        "protein_accession",
        "peptide_sequence",
        "proteoform_assignment",
        "protein_abundance",
        "complex_activity_score",
        "treatment_recommendation",
        "clinical_decision",
    }

    def mutate_numerator(payload: dict[str, object]) -> None:
        metrics = cast("list[dict[str, object]]", payload["metrics"])
        metrics[0]["numerator"] = cast("int", metrics[0]["numerator"]) - 1

    def mutate_status(payload: dict[str, object]) -> None:
        metrics = cast("list[dict[str, object]]", payload["metrics"])
        metrics[0]["status"] = ProteinInferenceQualityMetricStatus.FAIL

    def mutate_disposition(payload: dict[str, object]) -> None:
        payload["disposition"] = ProteinInferenceQualityDisposition.REJECTED

    forged_receipt_payload = request.raw_quality_receipt.model_dump(
        mode="python", exclude={"receipt_digest"}
    )
    forged_receipt_payload["search_space_digest"] = sha256_digest(
        {"resigned": "foreign-search-space"}
    )
    forged_receipt = ProteinInferenceRawQualityReceipt(
        **forged_receipt_payload,
        receipt_digest=raw_quality_receipt_digest(forged_receipt_payload),
    )
    forged_request = ComputeProteinInferenceQualityRequest(
        **{
            **request.model_dump(mode="python"),
            "raw_quality_receipt": forged_receipt,
        }
    )
    forged_result = compute_protein_inference_quality(forged_request)
    return [
        _scenario_check(
            "semantic_reordering_preserves_complete_result_equality",
            passed=(
                canonical_request_digest(reordered_request) == canonical_request_digest(request)
                and reordered_result == result
            ),
            detail=f"result_digest={result.result_digest}",
        ),
        _scenario_check(
            "typed_dict_and_strict_json_requests_produce_equal_results",
            passed=(typed == dictionary == strict_json),
            detail="library typed/dict and plugin strict-JSON results are equal",
        ),
        _scenario_check(
            "canonical_request_policy_profile_ledger_and_result_digests_are_stable",
            passed=(
                stable_digests
                == (
                    canonical_request_digest(request),
                    policy_digest(request.policy),
                    profile_digest(profile),
                    fact_ledger_digest(ledger),
                    compute_protein_inference_quality(request).result_digest,
                )
                and all(item.startswith("sha256:") for item in stable_digests)
                and all(threshold_digest(item).startswith("sha256:") for item in profile.thresholds)
            ),
            detail="request,policy,profile,ledger,threshold,result digests repeat exactly",
        ),
        _scenario_check(
            "recursive_privacy_and_ownership_canaries_are_absent",
            passed=(
                not any(f'"{key}"' in result_json for key in forbidden_keys)
                and "mpeptidek" not in result_json
                and not result.emits_complex_activity
                and not result.infers_protein
                and not result.infers_kinase_activity
            ),
            detail="forbidden output keys and raw sequence canary absent recursively",
        ),
        _scenario_check(
            "derived_metric_threshold_and_disposition_forgery_matrix_is_rejected",
            passed=all(
                _result_forgery_rejected(result, mutation)
                for mutation in (mutate_numerator, mutate_status, mutate_disposition)
            ),
            detail="re-digested numerator,status,disposition mutations rejected",
        ),
        _scenario_check(
            "resigned_nested_receipt_without_ledger_rebinding_is_quarantined",
            passed=(
                forged_result.disposition is ProteinInferenceQualityDisposition.QUARANTINED
                and not forged_result.metrics
                and any(
                    finding.code.value == "fact_ledger_binding_mismatch"
                    for finding in forged_result.findings
                )
            ),
            detail="self-content-addressed receipt contradiction quarantined at ledger closure",
        ),
    ]


def _interface_recovery_evidence_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    library = compute_protein_inference_quality(request)
    engine = M0304ProteinInferenceQualityEngine().compute(request)
    service = M0304Service()
    service_result = service.execute(service.validate_request(request))
    plugin = M0304Plugin(service)
    plugin_result = plugin.run(plugin.validate(request))
    request_bytes = canonical_json_bytes(request)

    with tempfile.TemporaryDirectory(prefix="m0304-eval-") as directory:
        root = Path(directory)
        request_path = root / "request.json"
        request_path.write_bytes(request_bytes)
        with TestClient(create_app(root / "interfaces.sqlite3")) as client:
            api_response = client.post(
                "/v1/modules/M03-04/quality",
                content=request_bytes,
                headers={"content-type": "application/json"},
            )
            api_result = ProteinInferenceQualityResult.model_validate_json(
                api_response.content, strict=True
            )
            api_verify_response = client.post(
                "/v1/modules/M03-04/quality/verify",
                content=canonical_json_bytes(library),
                headers={"content-type": "application/json"},
            )
            api_verified = ProteinInferenceQualityResult.model_validate_json(
                api_verify_response.content, strict=True
            )
            api_schemas = {
                name: client.get(f"/v1/contracts/M03-04/{name}/schema")
                for name in (
                    "request",
                    "output",
                    "policy",
                    "profile",
                    "threshold",
                    "raw-quality-receipt",
                    "fact-ledger",
                    "metric",
                    "finding",
                )
            }
        cli_compute = CliRunner().invoke(
            cli_app,
            ["protein-inference-quality", "compute", str(request_path)],
        )
        cli_result = ProteinInferenceQualityResult.model_validate_json(
            cli_compute.stdout,
            strict=True,
        )
        result_path = root / "result.json"
        result_path.write_bytes(canonical_json_bytes(library))
        cli_verify = CliRunner().invoke(
            cli_app,
            ["protein-inference-quality", "verify", str(result_path)],
        )
        cli_verified = ProteinInferenceQualityResult.model_validate_json(
            cli_verify.stdout,
            strict=True,
        )
        cli_schemas = {
            name: CliRunner().invoke(
                cli_app,
                ["protein-inference-quality", "export-schema", name],
            )
            for name in api_schemas
        }

    superseding_request = ComputeProteinInferenceQualityRequest(
        **{
            **request.model_dump(mode="python"),
            "supersedes_result_digest": library.result_digest,
        }
    )
    superseding_result = compute_protein_inference_quality(superseding_request)
    scenario_ids = {
        case_id for group in _corpus()["scenario_groups"] for case_id in group["case_ids"]
    }
    evidence_files = (
        ROOT / "docs" / "modules" / "GLIO-PROTEOGEN-M03-04.md",
        ROOT / "docs" / "modules" / "M03-04.manifest.md",
        ROOT / "docs" / "evidence" / "M03-04.md",
        ROOT / "docs" / "traceability" / "GLIO-PROTEOGEN-M03-04.csv",
        SCENARIO_PATH,
        Path(__file__).with_name("benchmark.py"),
    )
    schema_parity = all(
        response.status_code == _HTTP_OK
        and response.json() == json.loads(cli_schemas[name].stdout)
        and response.json()["$id"]
        == f"urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-04:1.0.0:{name}"
        for name, response in api_schemas.items()
    )
    return [
        _scenario_check(
            "public_library_engine_service_and_plugin_results_match",
            passed=(library == engine == service_result == plugin_result),
            detail="public library, engine, service, and plugin are completely equal",
        ),
        _scenario_check(
            "api_compute_result_matches_public_library_operation",
            passed=(api_response.status_code == _HTTP_OK and api_result == library),
            detail=f"status={api_response.status_code};digest={api_result.result_digest}",
        ),
        _scenario_check(
            "cli_compute_result_matches_public_library_operation",
            passed=(cli_compute.exit_code == 0 and cli_result == library),
            detail=f"exit={cli_compute.exit_code};digest={cli_result.result_digest}",
        ),
        _scenario_check(
            "api_and_cli_replay_verify_the_complete_result",
            passed=(
                api_verify_response.status_code == _HTTP_OK
                and api_verified == library
                and cli_verify.exit_code == 0
                and cli_verified == library
            ),
            detail=(
                f"api_status={api_verify_response.status_code};"
                f"cli_exit={cli_verify.exit_code};digest={library.result_digest}"
            ),
        ),
        _scenario_check(
            "schema_api_and_cli_export_exact_installed_contracts",
            passed=(
                schema_parity
                and len(api_schemas) == _SCHEMA_COUNT
                and all(result.exit_code == 0 for result in cli_schemas.values())
            ),
            detail=f"exact schema pairs={len(api_schemas)};URN prefix exact",
        ),
        _scenario_check(
            "recovery_requires_new_superseding_quality_result",
            passed=(
                superseding_request.supersedes_result_digest == library.result_digest
                and superseding_result.result_digest != library.result_digest
                and library.result_digest in superseding_result.provenance.input_digests
                and library.request.supersedes_result_digest is None
                and library == compute_protein_inference_quality(request)
            ),
            detail=(
                f"prior={library.result_digest};new={superseding_result.result_digest};"
                f"bound={library.result_digest in superseding_result.provenance.input_digests}"
            ),
        ),
        _scenario_check(
            "evidence_artifacts_and_benchmark_time_only_public_m0304_operation",
            passed=(
                all(path.is_file() for path in evidence_files)
                and len(scenario_ids) == _EXPECTED_CASE_COUNT
                and "compute_protein_inference_quality_only"
                in Path(__file__).with_name("benchmark.py").read_text(encoding="utf-8")
            ),
            detail=f"evidence_files={len(evidence_files)};declared_cases={len(scenario_ids)}",
        ),
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    scenario = build_scenario()
    checks = [
        *_static_checks(_corpus(), scenario),
        *_genuine_and_metric_checks(scenario),
        *_ambiguity_and_missingness_checks(scenario),
        *_profile_and_reference_checks(scenario),
        *_safe_failure_checks(scenario),
        *_strict_capacity_checks(scenario),
        *_canonical_privacy_forgery_checks(scenario),
        *_interface_recovery_evidence_checks(scenario),
    ]
    declared = {case_id for group in _corpus()["scenario_groups"] for case_id in group["case_ids"]}
    executed = {
        check.name.removeprefix("scenario.")
        for check in checks
        if check.name.startswith("scenario.")
    }
    missing = sorted(declared - executed)
    extra = sorted(executed - declared)
    checks.append(
        EvalCheck(
            name="corpus.executable_coverage",
            passed=(
                len(declared) == len(executed) == _EXPECTED_CASE_COUNT and not missing and not extra
            ),
            detail=(
                f"declared={len(declared)};executed={len(executed)};missing={missing};extra={extra}"
            ),
        )
    )
    passed = all(check.passed for check in checks)
    rendered = json.dumps(
        {
            "module_id": MODULE_ID,
            "passed": passed,
            "phase": "locked_executable_corpus",
            "declared_case_count": len(declared),
            "executed_case_count": len(executed),
            "missing_case_ids": missing,
            "extra_case_ids": extra,
            "checks": [asdict(check) for check in checks],
        },
        indent=2,
        sort_keys=True,
    )
    if arguments.output is None:
        sys.stdout.write(rendered + "\n")
    else:
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
