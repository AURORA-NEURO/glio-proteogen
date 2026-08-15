"""Contract, invariant, and exact-replay closure for M05-04."""

# mypy: disable-error-code=operator

from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest
from evals.m05_04.run import build_scenario_request

from glio_proteogen.contracts.m05_03 import PtmLocalizationRawInputRole
from glio_proteogen.contracts.m05_04 import (
    M0504_COMPUTED_METRIC_COUNT,
    M0504_CONTRACT_VERSION,
    M0504_GATE,
    M0504_MAX_APPROVED_VERSIONS,
    M0504_MAX_CANONICAL_REQUEST_BYTES,
    M0504_MAX_EVIDENCE,
    M0504_MAX_PROFILES,
    M0504_METRIC_COUNT,
    M0504_MODULE_ID,
    M0504_OPERATION,
    M0504_OWNER,
    M0504_PARENT,
    M0504_ROLE_COUNT,
    M0504_SAFETY_CLASS,
    ComputePtmLocalizationQualityMetricsRequest,
    PtmLocalizationQualityDisposition,
    PtmLocalizationQualityFindingCode,
    PtmLocalizationQualityMetricCode,
    PtmLocalizationQualityMetricDirection,
    PtmLocalizationQualityMetricStatus,
    PtmLocalizationQualityObservationState,
    PtmLocalizationQualityResult,
    context_digest,
    contract_json_schemas,
    expected_assay_quality,
    expected_disposition,
    expected_provenance,
    expected_quality_findings,
    expected_quality_metrics,
    expected_receipt,
    normalized_result,
    opaque_ptm_localization_quality_identifier,
    receipt_digest,
)
from glio_proteogen.contracts.m05_04 import canonical as m0504_canonical
from glio_proteogen.contracts.m05_04 import v1 as m0504_contract
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import SupportStatus, UpstreamDecisionState
from glio_proteogen.modules.c05_ptm_localization.m05_04_quality_metrics import (
    compute_ptm_localization_quality_metrics,
)


@pytest.fixture(scope="module")
def m0504_request() -> ComputePtmLocalizationQualityMetricsRequest:
    return build_scenario_request()


@pytest.fixture(scope="module")
def result(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
) -> PtmLocalizationQualityResult:
    return compute_ptm_localization_quality_metrics(m0504_request)


def test_frozen_identity_capacity_and_schema_surface() -> None:
    assert (
        M0504_MODULE_ID,
        M0504_OPERATION,
        M0504_CONTRACT_VERSION,
        M0504_PARENT,
        M0504_OWNER,
        M0504_SAFETY_CLASS,
        M0504_GATE,
    ) == (
        "GLIO-PROTEOGEN-M05-04",
        "compute_ptm_localization_quality_metrics",
        "1.0.0",
        "variant_peptide",
        "Platform engineering",
        "S2",
        "G1",
    )
    assert (
        M0504_ROLE_COUNT,
        M0504_METRIC_COUNT,
        M0504_COMPUTED_METRIC_COUNT,
        M0504_MAX_PROFILES,
        M0504_MAX_APPROVED_VERSIONS,
        M0504_MAX_EVIDENCE,
        M0504_MAX_CANONICAL_REQUEST_BYTES,
    ) == (4, 8, 32, 32, 32, 45, 4 * 1024 * 1024)
    schemas = contract_json_schemas()
    assert set(schemas) == {
        "request",
        "output",
        "policy",
        "threshold",
        "assay-profile",
        "fact-counts",
        "fact-states",
        "role-facts",
        "fact-ledger",
        "metric",
        "assay-quality",
        "finding",
        "receipt",
    }
    for name, schema in schemas.items():
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert schema["$id"] == (f"urn:aurora-neuro:glio-proteogen:{M0504_MODULE_ID}:1.0.0:{name}")
        assert metadata["moduleId"] == M0504_MODULE_ID
        assert metadata["parentTarget"] == M0504_PARENT
        assert metadata["externalContentTraversal"] is False


def test_canonical_helpers_reject_nonstring_keys_and_preserve_result_digest(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
    result: PtmLocalizationQualityResult,
) -> None:
    with pytest.raises(TypeError, match="exact strings"):
        m0504_canonical._python({1: "not-a-string-key"})
    assert context_digest(m0504_request) == context_digest(m0504_request.context)
    normalized = normalized_result(result)
    assert normalized["result_digest"] == result.result_digest
    assert canonical_json_bytes(normalized) == canonical_json_bytes(normalized_result(normalized))


def test_opaque_namespaces_and_owned_evidence_are_exact(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
) -> None:
    with pytest.raises(ValueError, match="exact opaque"):
        opaque_ptm_localization_quality_identifier("actor", m0504_request.request_id)
    profile = m0504_request.policy.profiles[0]
    with pytest.raises(ValueError, match="media type"):
        m0504_contract._owned_artifact(
            profile.evidence.model_copy(update={"media_type": "application/json"}),
            "application/vnd.glio-proteogen.m05-04.assay-profile+json",
        )
    conflict = profile.evidence.model_copy(update={"digest": sha256_digest("conflict")})
    with pytest.raises(ValueError, match="conflicting content"):
        m0504_contract._require_consistent_evidence_identities((profile.evidence, conflict))


def test_threshold_profile_and_policy_invariant_rejections(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
) -> None:
    profiles = m0504_request.policy.profiles
    profile = profiles[0]
    at_least = next(
        item
        for item in profile.thresholds
        if item.direction is PtmLocalizationQualityMetricDirection.AT_LEAST
    )
    at_most = next(
        item
        for item in profile.thresholds
        if item.direction is PtmLocalizationQualityMetricDirection.AT_MOST
    )
    with pytest.raises(ValueError, match="warning threshold cannot exceed"):
        at_least.model_copy(
            update={"warning_threshold_ppm": at_least.pass_threshold_ppm + 1}
        ).thresholds_are_directionally_closed()
    with pytest.raises(ValueError, match="warning threshold cannot be below"):
        at_most.model_copy(
            update={"warning_threshold_ppm": at_most.pass_threshold_ppm - 1}
        ).thresholds_are_directionally_closed()
    with pytest.raises(ValueError, match="unique"):
        profile.approved_versions_are_canonical(("1.0.0", "1.0.0"))

    proteome = next(item for item in profiles if item.assay_kind is not None)
    nonproteome = next(item for item in profiles if item.assay_kind is None)
    with pytest.raises(ValueError, match="required only"):
        proteome.model_copy(update={"assay_kind": None}).profile_is_closed()
    with pytest.raises(ValueError, match="cannot declare"):
        nonproteome.model_copy(
            update={
                "assay_kind": proteome.assay_kind,
            }
        ).profile_is_closed()
    with pytest.raises(ValueError, match="cannot approve"):
        proteome.model_copy(update={"support_domain": "review_required"}).profile_is_closed()
    with pytest.raises(ValueError, match="every metric exactly once"):
        profile.model_copy(
            update={"thresholds": (*profile.thresholds[:-1], profile.thresholds[0])}
        ).profile_is_closed()

    with pytest.raises(ValueError, match="identities must be unique"):
        m0504_request.policy.model_copy(
            update={"profiles": (*profiles[:-1], profiles[0])}
        ).profiles_are_total_and_disjoint()
    replacement = next(item for item in profiles if item.role is not nonproteome.role)
    with pytest.raises(ValueError, match="cover all four roles"):
        m0504_request.policy.model_copy(
            update={
                "profiles": tuple(
                    item.model_copy(update={"role": replacement.role})
                    if item is nonproteome
                    else item
                    for item in profiles
                )
            }
        ).profiles_are_total_and_disjoint()


def test_fact_and_ledger_invariant_rejections(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
) -> None:
    ledger = m0504_request.fact_ledger
    assert ledger is not None
    fact = ledger.role_facts[0]
    with pytest.raises(ValueError, match="exactly partition"):
        fact.counts.model_copy(
            update={"detection_eligible_count": fact.counts.detection_eligible_count + 1}
        ).count_partitions_close()
    with pytest.raises(ValueError, match="only detection-limit"):
        fact.model_copy(
            update={
                "states": fact.states.model_copy(
                    update={
                        "raw_input_completeness": PtmLocalizationQualityObservationState.CENSORED
                    }
                )
            }
        ).fact_shape_is_closed()
    with pytest.raises(ValueError, match="zero count partitions"):
        fact.model_copy(
            update={"states": fact.states.model_copy(update={"raw_input_completeness": "missing"})}
        ).fact_shape_is_closed()
    with pytest.raises(ValueError, match="every role exactly once"):
        ledger.model_copy(
            update={"role_facts": (*ledger.role_facts[:-1], ledger.role_facts[0])}
        ).ledger_is_closed()
    with pytest.raises(ValueError, match="must be final"):
        ledger.model_copy(update={"ledger_digest": "sha256:" + "0" * 64}).ledger_is_closed()


def test_request_chronology_authority_and_capacity_rejections(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = m0504_request.context
    ledger = m0504_request.fact_ledger
    assert ledger is not None
    other_request_id = f"request.{sha256_digest('other-request').removeprefix('sha256:')}"
    with pytest.raises(ValueError, match="must equal"):
        m0504_request.model_copy(update={"request_id": other_request_id}).request_is_closed()

    quarantined = build_scenario_request("quarantined_upstream_zero_ledger_traversal")
    with pytest.raises(ValueError, match="prohibits fact-ledger"):
        quarantined.model_copy(update={"fact_ledger": ledger}).request_is_closed()
    with pytest.raises(ValueError, match="policy cannot postdate"):
        m0504_request.model_copy(
            update={
                "policy": m0504_request.policy.model_copy(
                    update={"reviewed_at": context.occurred_at + timedelta(seconds=1)}
                )
            }
        ).request_is_closed()
    with pytest.raises(ValueError, match="result cannot postdate"):
        m0504_request.model_copy(
            update={
                "raw_input_result": m0504_request.raw_input_result.model_copy(
                    update={"completed_at": context.occurred_at + timedelta(seconds=1)}
                )
            }
        ).request_is_closed()
    with pytest.raises(ValueError, match="ledger chronology"):
        m0504_request.model_copy(
            update={
                "fact_ledger": ledger.model_copy(
                    update={"recorded_at": context.occurred_at + timedelta(seconds=1)}
                )
            }
        ).request_is_closed()
    with pytest.raises(ValueError, match="reviewed policy maximum"):
        m0504_request.model_copy(
            update={"policy": m0504_request.policy.model_copy(update={"max_count": 1})}
        ).request_is_closed()
    denied_refs = context.references.model_copy(
        update={
            "support": context.references.support.model_copy(
                update={"state": UpstreamDecisionState.REJECTED}
            )
        }
    )
    with pytest.raises(ValueError, match="not authorized"):
        m0504_request.model_copy(
            update={"context": context.model_copy(update={"references": denied_refs})}
        ).request_is_closed()
    stale_refs = context.references.model_copy(
        update={
            "quality": context.references.quality.model_copy(
                update={
                    "evidence": context.references.quality.evidence.model_copy(
                        update={"digest": sha256_digest("stale")}
                    )
                }
            )
        }
    )
    with pytest.raises(ValueError, match="does not bind"):
        m0504_request.model_copy(
            update={"context": context.model_copy(update={"references": stale_refs})}
        ).request_is_closed()
    monkeypatch.setattr(m0504_contract, "M0504_MAX_CANONICAL_REQUEST_BYTES", 1)
    with pytest.raises(ValueError, match="exceeds the 4 MiB"):
        m0504_request.request_is_closed()


def test_metric_finding_assay_and_receipt_invariant_rejections(
    result: PtmLocalizationQualityResult,
) -> None:
    assay = result.assay_quality[0]
    observed = next(
        item
        for item in assay.metrics
        if item.observation_state is PtmLocalizationQualityObservationState.OBSERVED
        and item.denominator
    )
    detection = next(
        item
        for item in assay.metrics
        if item.metric_code is PtmLocalizationQualityMetricCode.DETECTION_LIMIT_BURDEN
    )
    with pytest.raises(ValueError, match="cannot carry a ratio"):
        observed.model_copy(
            update={"observation_state": PtmLocalizationQualityObservationState.MISSING}
        ).value_shape_is_closed()
    with pytest.raises(ValueError, match="require numerator"):
        observed.model_copy(update={"numerator": None}).value_shape_is_closed()
    with pytest.raises(ValueError, match="cannot exceed"):
        observed.model_copy(
            update={"numerator": cast("int", observed.denominator) + 1}
        ).value_shape_is_closed()
    with pytest.raises(ValueError, match="zero-denominator"):
        observed.model_copy(
            update={
                "numerator": 0,
                "denominator": 0,
                "value_ppm": 0,
                "status": PtmLocalizationQualityMetricStatus.PASS,
            }
        ).value_shape_is_closed()
    with pytest.raises(ValueError, match="round-half-up"):
        observed.model_copy(update={"value_ppm": 1}).value_shape_is_closed()
    with pytest.raises(ValueError, match="positive censored"):
        detection.model_copy(
            update={
                "observation_state": PtmLocalizationQualityObservationState.CENSORED,
                "censored_count": 0,
            }
        ).value_shape_is_closed()
    with pytest.raises(ValueError, match="only detection burden"):
        observed.model_copy(
            update={
                "observation_state": PtmLocalizationQualityObservationState.CENSORED,
                "censored_count": observed.numerator,
            }
        ).value_shape_is_closed()

    finding = m0504_contract.finding_for(
        PtmLocalizationQualityFindingCode.REQUIRED_METRIC_MISSING,
        roles=(assay.role,),
    )
    with pytest.raises(ValueError, match="references must be unique"):
        finding.model_copy(update={"roles": (assay.role, assay.role)}).finding_is_closed()
    with pytest.raises(ValueError, match="all eight exact metrics"):
        assay.model_copy(
            update={"metrics": (*assay.metrics[:-1], assay.metrics[0])}
        ).assay_quality_is_closed()
    other_role = next(role for role in PtmLocalizationRawInputRole if role is not assay.role)
    with pytest.raises(ValueError, match="retain one exact role"):
        assay.model_copy(
            update={
                "metrics": (
                    assay.metrics[0].model_copy(update={"role": other_role}),
                    *assay.metrics[1:],
                )
            }
        ).assay_quality_is_closed()
    with pytest.raises(ValueError, match="disposition contradicts"):
        assay.model_copy(
            update={"disposition": PtmLocalizationQualityDisposition.ABSTAINED}
        ).assay_quality_is_closed()

    receipt = result.receipt
    with pytest.raises(ValueError, match="collections must be unique"):
        receipt.receipt_collections_are_canonical(
            (receipt.selected_profile_digests[0], receipt.selected_profile_digests[0])
        )
    with pytest.raises(ValueError, match="zero or four"):
        receipt.model_copy(
            update={"selected_profile_digests": receipt.selected_profile_digests[:1]}
        ).receipt_is_closed()
    with pytest.raises(ValueError, match="equal lengths"):
        receipt.model_copy(update={"assay_quality_digests": ()}).receipt_is_closed()
    forged_receipt = receipt.model_copy(
        update={"disposition": PtmLocalizationQualityDisposition.ABSTAINED}
    )
    forged_receipt = forged_receipt.model_copy(
        update={"receipt_digest": receipt_digest(forged_receipt)}
    )
    with pytest.raises(ValueError, match="disposition contradicts"):
        forged_receipt.receipt_is_closed()


def test_public_projection_helpers_reject_forged_overrides(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
    result: PtmLocalizationQualityResult,
) -> None:
    profiles = tuple(m0504_request.policy.profiles[:1])
    metrics = tuple(result.assay_quality[0].metrics[:1])
    findings = tuple(result.findings)
    forged_findings = (
        m0504_contract.finding_for(PtmLocalizationQualityFindingCode.REQUIRED_METRIC_MISSING),
    )
    with pytest.raises(ValueError, match="profiles"):
        expected_quality_metrics(m0504_request, profiles)
    with pytest.raises(ValueError, match="metrics"):
        expected_quality_findings(m0504_request, metrics)
    with pytest.raises(ValueError, match="metrics"):
        expected_disposition(m0504_request, metrics, findings)
    with pytest.raises(ValueError, match="findings"):
        expected_disposition(m0504_request, (), forged_findings)
    with pytest.raises(ValueError, match="metrics"):
        expected_assay_quality(m0504_request, metrics, findings)
    with pytest.raises(ValueError, match="findings"):
        expected_assay_quality(
            m0504_request,
            tuple(item for assay in result.assay_quality for item in assay.metrics),
            forged_findings,
        )
    with pytest.raises(ValueError, match="assay quality"):
        expected_receipt(m0504_request, result.assay_quality[:1], findings, result.disposition)
    with pytest.raises(ValueError, match="findings"):
        expected_receipt(m0504_request, result.assay_quality, forged_findings, result.disposition)
    with pytest.raises(ValueError, match="disposition"):
        expected_receipt(
            m0504_request,
            result.assay_quality,
            findings,
            PtmLocalizationQualityDisposition.ABSTAINED,
        )
    with pytest.raises(ValueError, match="metrics"):
        expected_provenance(m0504_request, metrics, result.receipt)
    with pytest.raises(ValueError, match="receipt"):
        expected_provenance(
            m0504_request,
            (),
            result.receipt.model_copy(update={"raw_input_result_digest": sha256_digest("stale")}),
        )


def test_result_replay_rejects_every_independent_derived_region(
    result: PtmLocalizationQualityResult,
) -> None:
    stale = sha256_digest("m0504-stale-derived-region")
    variants: tuple[PtmLocalizationQualityResult, ...] = (
        result.model_copy(update={"result_id": "result.m0504." + "0" * 64}),
        result.model_copy(update={"completed_at": result.completed_at + timedelta(seconds=1)}),
        result.model_copy(
            update={
                "support": result.support.model_copy(update={"status": SupportStatus.UNSUPPORTED})
            }
        ),
        result.model_copy(
            update={
                "uncertainty": result.uncertainty.model_copy(
                    update={"sensitivity_notes": ("forged",)}
                )
            }
        ),
        result.model_copy(
            update={"provenance": result.provenance.model_copy(update={"input_digests": (stale,)})}
        ),
        result.model_copy(update={"evidence": result.evidence[:-1]}),
        result.model_copy(update={"limitations": result.limitations[:-1]}),
        result.model_copy(update={"human_review_required": not result.human_review_required}),
    )
    messages = (
        "envelope",
        "completion time",
        "support",
        "uncertainty",
        "provenance",
        "evidence index",
        "limitations",
        "review flag",
    )
    for variant, message in zip(variants, messages, strict=True):
        with pytest.raises(ValueError, match=message):
            m0504_contract._validate_result_replay(variant)


def test_supersession_is_retained_in_provenance(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
) -> None:
    superseded = sha256_digest("superseded-m0504-result")
    result = compute_ptm_localization_quality_metrics(
        m0504_request.model_copy(update={"supersedes_result_digest": superseded})
    )
    assert superseded in result.provenance.input_digests


def test_evidence_shape_guard_is_explicit(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(m0504_contract, "M0504_MIN_EVIDENCE", M0504_MAX_EVIDENCE + 1)
    with pytest.raises(ValueError, match="evidence index exceeds"):
        m0504_contract.quality_evidence_index(m0504_request)


def test_nonmodel_normalization_is_identity() -> None:
    marker = object()
    assert m0504_contract._normalized_model(marker) is marker
