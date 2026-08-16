"""Adversarial boundary coverage for M03-05 artifact evidence masks."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Never, cast

import pytest
from evals.m03_05.run import (
    build_capacity_scenario_request,
    build_scenario_request,
    request_with_signal,
)
from pydantic import ValidationError

from glio_proteogen.contracts.m03_03 import ProteinInferenceRawRole
from glio_proteogen.contracts.m03_04 import (
    ProteinInferenceQualityDisposition,
    ProteinInferenceQualityMetricDirection,
    ProteinInferenceQualityMetricStatus,
    ProteinInferenceQualityObservationState,
)
from glio_proteogen.contracts.m03_05 import (
    M0305_GATE,
    M0305_MAX_APPROVED_VERSIONS,
    M0305_MAX_CANONICAL_REQUEST_BYTES,
    M0305_MAX_CANONICAL_RESULT_BYTES,
    M0305_MAX_CLAIMS,
    M0305_MAX_CONTAMINATION_FLAGS,
    M0305_MAX_COUNT,
    M0305_MAX_EVIDENCE,
    M0305_MAX_FINDINGS,
    M0305_MAX_PROFILES,
    M0305_MAX_SIGNAL_SCORES,
    M0305_MAX_SOURCES,
    M0305_MAX_UNIT_CLAIM_REFS,
    M0305_MAX_UNIT_SOURCE_REFS,
    M0305_MAX_UNITS,
    M0305_OPERATION,
    M0305_OWNER,
    M0305_PARENT,
    M0305_RATE_SCALE,
    M0305_SAFETY_CLASS,
    M0305_SCORE_LIMITATION_CODE,
    M0305_SIGNAL_APPLICABLE_UNIT_KINDS,
    M0305_SIGNAL_COUNT,
    DetectProteinInferenceArtifactsRequest,
    ProteinInferenceArtifactDetectionResult,
    ProteinInferenceArtifactDisposition,
    ProteinInferenceArtifactEvidenceLedger,
    ProteinInferenceArtifactEvidenceUnit,
    ProteinInferenceArtifactFindingCode,
    ProteinInferenceArtifactFlagState,
    ProteinInferenceArtifactObservationState,
    ProteinInferenceArtifactPolicy,
    ProteinInferenceArtifactProfile,
    ProteinInferenceArtifactQualityMetricReceipt,
    ProteinInferenceArtifactQualityReceipt,
    ProteinInferenceArtifactSignal,
    ProteinInferenceArtifactSignalCode,
    ProteinInferenceEvidenceUnitKind,
    artifact_evidence_ledger_digest,
    artifact_quality_receipt_digest,
    canonical_request_digest,
    claim_binding_digest,
    configuration_digest,
    contract_json_schema,
    expected_signal_scores,
    finding_for,
    normalized_request,
    normalized_result,
    quality_metric_binding_digest,
    result_payload_digest,
    source_binding_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_05_artifact_detection import (
    M0305Plugin,
    M0305Service,
    ProteinInferenceArtifactAuthorizationError,
    detect_protein_inference_artifacts,
)

_ZERO_DIGEST = "sha256:" + ("0" * 64)
_ONE_THIRD_PPM = 333_333
_EXPECTED_SIGNAL_COUNT = 8
_EXPECTED_UNIT_KIND_COUNT = 6
_EXPECTED_EVIDENCE_CAP = 18
_SCHEMA_NAMES = (
    "request",
    "output",
    "policy",
    "profile",
    "threshold",
    "quality-receipt",
    "evidence-ledger",
    "evidence-unit",
    "signal-score",
    "posterior",
    "contamination-flag",
    "exclusion-mask",
    "finding",
)


@pytest.fixture(scope="module")
def canonical_request() -> DetectProteinInferenceArtifactsRequest:
    return build_scenario_request()


@pytest.fixture(scope="module")
def canonical_result(
    canonical_request: DetectProteinInferenceArtifactsRequest,
) -> ProteinInferenceArtifactDetectionResult:
    return detect_protein_inference_artifacts(canonical_request)


@pytest.fixture(scope="module")
def capacity_request() -> DetectProteinInferenceArtifactsRequest:
    return build_capacity_scenario_request()


@pytest.fixture(scope="module")
def capacity_result(
    capacity_request: DetectProteinInferenceArtifactsRequest,
) -> ProteinInferenceArtifactDetectionResult:
    return detect_protein_inference_artifacts(capacity_request)


def _payload(value: object) -> dict[str, Any]:
    return cast(
        "dict[str, Any]",
        strict_json_loads(
            canonical_json_bytes(value), max_bytes=M0305_MAX_CANONICAL_RESULT_BYTES
        ),
    )


def _opaque_id(prefix: str, label: str) -> str:
    return f"{prefix}.{sha256_digest(label).removeprefix('sha256:')}"


def _resigned_receipt(payload: dict[str, Any]) -> ProteinInferenceArtifactQualityReceipt:
    payload["source_binding_digest"] = source_binding_digest(payload["sources"])
    payload["claim_binding_digest"] = claim_binding_digest(payload["claims"])
    payload["quality_metric_binding_digest"] = quality_metric_binding_digest(
        payload["quality_metrics"]
    )
    payload["receipt_digest"] = artifact_quality_receipt_digest(payload)
    return ProteinInferenceArtifactQualityReceipt.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )


def _resigned_ledger(
    request: DetectProteinInferenceArtifactsRequest,
    *,
    units: tuple[ProteinInferenceArtifactEvidenceUnit, ...] | None = None,
    **updates: object,
) -> ProteinInferenceArtifactEvidenceLedger:
    ledger = request.evidence_ledger
    assert ledger is not None
    payload = _payload(ledger)
    if units is not None:
        payload["units"] = units
    payload.update(updates)
    payload["ledger_digest"] = artifact_evidence_ledger_digest(payload)
    return ProteinInferenceArtifactEvidenceLedger.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )


def _request_with_policy(
    request: DetectProteinInferenceArtifactsRequest,
    policy: ProteinInferenceArtifactPolicy,
    *,
    evidence_ledger: ProteinInferenceArtifactEvidenceLedger | None,
) -> DetectProteinInferenceArtifactsRequest:
    refs = request.context.references
    approved = refs.approved_configuration.model_copy(
        update={
            "evidence": refs.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    context = request.context.model_copy(
        update={"references": refs.model_copy(update={"approved_configuration": approved})}
    )
    return DetectProteinInferenceArtifactsRequest.model_validate(
        request.model_copy(
            update={"context": context, "policy": policy, "evidence_ledger": evidence_ledger}
        ),
        strict=True,
    )


def _request_with_receipt(
    request: DetectProteinInferenceArtifactsRequest,
    receipt: ProteinInferenceArtifactQualityReceipt,
    *,
    evidence_ledger: ProteinInferenceArtifactEvidenceLedger | None,
) -> DetectProteinInferenceArtifactsRequest:
    refs = request.context.references
    quality = refs.quality.model_copy(
        update={
            "evidence": refs.quality.evidence.model_copy(
                update={"digest": receipt.quality_result_digest}
            )
        }
    )
    identity = refs.identity_lineage.model_copy(
        update={"binding_digest": receipt.identity_resolution_digest}
    )
    context = request.context.model_copy(
        update={
            "references": refs.model_copy(update={"quality": quality, "identity_lineage": identity})
        }
    )
    return DetectProteinInferenceArtifactsRequest.model_validate(
        request.model_copy(
            update={
                "context": context,
                "quality_receipt": receipt,
                "evidence_ledger": evidence_ledger,
            }
        ),
        strict=True,
    )


def _with_threshold_required(
    request: DetectProteinInferenceArtifactsRequest,
    code: ProteinInferenceArtifactSignalCode,
    *,
    required: bool,
) -> DetectProteinInferenceArtifactsRequest:
    profile = request.policy.profiles[0]
    thresholds = tuple(
        item.model_copy(update={"required": required}) if item.signal_code is code else item
        for item in profile.thresholds
    )
    rebuilt = ProteinInferenceArtifactProfile.model_validate(
        profile.model_copy(update={"thresholds": thresholds}), strict=True
    )
    policy = ProteinInferenceArtifactPolicy.model_validate(
        request.policy.model_copy(update={"profiles": (rebuilt,)}), strict=True
    )
    return _request_with_policy(request, policy, evidence_ledger=request.evidence_ledger)


def _schema_property(name: str, field: str) -> dict[str, Any]:
    schema = contract_json_schema(cast("Any", name))
    return cast("dict[str, Any]", cast("dict[str, Any]", schema["properties"])[field])


def _safe_receipt(
    request: DetectProteinInferenceArtifactsRequest,
    disposition: ProteinInferenceQualityDisposition,
) -> ProteinInferenceArtifactQualityReceipt:
    payload = _payload(request.quality_receipt)
    support = {
        ProteinInferenceQualityDisposition.REJECTED: SupportStatus.UNSUPPORTED,
        ProteinInferenceQualityDisposition.QUARANTINED: SupportStatus.REVIEW_REQUIRED,
        ProteinInferenceQualityDisposition.ABSTAINED: SupportStatus.UNSUPPORTED,
    }[disposition]
    payload.update(
        {
            "quality_disposition": disposition,
            "quality_support_status": support,
            "quality_human_review_required": True,
            "sources": (),
            "claims": (),
            "quality_metrics": (),
        }
    )
    return _resigned_receipt(payload)


def test_locked_abi_schema_inventory_and_caps_are_exact() -> None:
    assert M0305_OPERATION == "detect_protein_inference_artifacts"
    assert (M0305_OWNER, M0305_SAFETY_CLASS, M0305_GATE, M0305_PARENT) == (
        "Data engineering",
        "S2",
        "G1",
        "complex_activity",
    )
    assert tuple(item.value for item in ProteinInferenceArtifactSignalCode) == (
        "contaminant_reference_support",
        "decoy_competition_failure",
        "low_complexity_evidence",
        "nonunique_mapping",
        "batch_inconsistency",
        "barcode_index_collision",
        "technical_carryover",
        "sample_context_discordance",
    )
    assert len(ProteinInferenceArtifactSignalCode) == M0305_SIGNAL_COUNT == (
        _EXPECTED_SIGNAL_COUNT
    )
    assert len(ProteinInferenceEvidenceUnitKind) == _EXPECTED_UNIT_KIND_COUNT
    for name in _SCHEMA_NAMES:
        schema = contract_json_schema(cast("Any", name))
        metadata = cast("dict[str, Any]", schema["x-glio-contract"])
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False
        assert metadata == {
            "moduleId": "GLIO-PROTEOGEN-M03-05",
            "contractVersion": "1.0.0",
            "strict": True,
            "rawPayloadInSchema": False,
            "reparsesRawPayload": False,
            "identityInference": False,
            "proteinInference": False,
            "proteoformInference": False,
            "isoformInference": False,
            "gliomaSpecificBiologyInference": False,
            "complexActivityInference": False,
            "kinaseActivityInference": False,
            "calibratedProbability": False,
            **({"maxRequestBytes": M0305_MAX_CANONICAL_REQUEST_BYTES} if name == "request" else {}),
            **({"maxResultBytes": M0305_MAX_CANONICAL_RESULT_BYTES} if name == "output" else {}),
        }
    assert _schema_property("quality-receipt", "sources")["maxItems"] == M0305_MAX_SOURCES
    assert _schema_property("quality-receipt", "claims")["maxItems"] == M0305_MAX_CLAIMS
    assert _schema_property("quality-receipt", "quality_metrics")["maxItems"] == (
        M0305_SIGNAL_COUNT
    )
    assert _schema_property("evidence-ledger", "units")["maxItems"] == M0305_MAX_UNITS
    assert _schema_property("evidence-unit", "source_ids")["maxItems"] == (
        M0305_MAX_UNIT_SOURCE_REFS
    )
    assert _schema_property("evidence-unit", "claim_ids")["maxItems"] == (
        M0305_MAX_UNIT_CLAIM_REFS
    )
    assert _schema_property("evidence-unit", "signals")["maxItems"] == M0305_SIGNAL_COUNT
    assert _schema_property("policy", "profiles")["maxItems"] == M0305_MAX_PROFILES
    assert _schema_property("profile", "approved_assay_protocol_versions")["maxItems"] == (
        M0305_MAX_APPROVED_VERSIONS
    )
    assert _schema_property("output", "signal_scores")["maxItems"] == M0305_MAX_SIGNAL_SCORES
    assert _schema_property("output", "contamination_flags")["maxItems"] == (
        M0305_MAX_CONTAMINATION_FLAGS
    )
    assert _schema_property("output", "findings")["maxItems"] == M0305_MAX_FINDINGS
    assert _schema_property("output", "evidence")["maxItems"] == M0305_MAX_EVIDENCE == (
        _EXPECTED_EVIDENCE_CAP
    )


@pytest.mark.parametrize("code", list(ProteinInferenceArtifactSignalCode))
def test_all_eight_signal_scores_are_integer_fractions_not_probabilities(
    canonical_request: DetectProteinInferenceArtifactsRequest,
    code: ProteinInferenceArtifactSignalCode,
) -> None:
    ledger = canonical_request.evidence_ledger
    assert ledger is not None
    unit = next(
        item
        for item in ledger.units
        if item.unit_kind in M0305_SIGNAL_APPLICABLE_UNIT_KINDS[code]
    )
    request = request_with_signal(
        canonical_request,
        code,
        unit_id=unit.unit_id,
        supporting_count=1,
        evaluated_count=3,
    )
    score = next(
        item
        for item in expected_signal_scores(request)
        if item.unit_id == unit.unit_id and item.signal_code is code
    )
    assert score.evidence_score_ppm == _ONE_THIRD_PPM
    assert score.flag_state is ProteinInferenceArtifactFlagState.SUSPECTED
    assert score.score_is_calibrated_probability is False


@pytest.mark.parametrize(
    ("supporting", "expected"),
    [
        (199_999, ProteinInferenceArtifactFlagState.CLEAR),
        (200_000, ProteinInferenceArtifactFlagState.SUSPECTED),
        (499_999, ProteinInferenceArtifactFlagState.SUSPECTED),
        (500_000, ProteinInferenceArtifactFlagState.DETECTED),
        (500_001, ProteinInferenceArtifactFlagState.DETECTED),
    ],
)
def test_thresholds_use_exact_cross_products_not_rounded_ppm(
    canonical_request: DetectProteinInferenceArtifactsRequest,
    supporting: int,
    expected: ProteinInferenceArtifactFlagState,
) -> None:
    code = ProteinInferenceArtifactSignalCode.CONTAMINANT_REFERENCE_SUPPORT
    request = request_with_signal(
        canonical_request,
        code,
        supporting_count=supporting,
        evaluated_count=M0305_RATE_SCALE,
    )
    score = next(
        item
        for item in expected_signal_scores(request)
        if item.signal_code is code and item.supporting_count == supporting
    )
    assert score.flag_state is expected


def test_zero_denominator_and_optional_missing_are_typed_not_negative(
    canonical_request: DetectProteinInferenceArtifactsRequest,
) -> None:
    code = ProteinInferenceArtifactSignalCode.TECHNICAL_CARRYOVER
    zero = detect_protein_inference_artifacts(
        request_with_signal(
            canonical_request,
            code,
            supporting_count=0,
            evaluated_count=0,
        )
    )
    zero_score = next(
        item
        for item in zero.signal_scores
        if item.signal_code is code
        and item.observation_state is ProteinInferenceArtifactObservationState.OBSERVED
        and item.evaluated_count == 0
    )
    assert zero_score.flag_state is ProteinInferenceArtifactFlagState.INDETERMINATE
    assert zero_score.evidence_score_ppm is None
    assert zero.disposition is ProteinInferenceArtifactDisposition.ABSTAINED
    assert ProteinInferenceArtifactFindingCode.SIGNAL_NOT_EVALUABLE in {
        item.code for item in zero.findings
    }

    optional = _with_threshold_required(canonical_request, code, required=False)
    optional = request_with_signal(
        optional,
        code,
        observation_state=ProteinInferenceArtifactObservationState.MISSING,
        supporting_count=0,
        evaluated_count=0,
    )
    result = detect_protein_inference_artifacts(optional)
    assert result.disposition is ProteinInferenceArtifactDisposition.ABSTAINED
    assert result.support.status is SupportStatus.UNSUPPORTED
    assert result.human_review_required is True
    assert result.exclusion_mask.review_unit_ids
    assert ProteinInferenceArtifactFindingCode.SIGNAL_NOT_EVALUABLE in {
        item.code for item in result.findings
    }


def test_retain_review_exclude_mask_and_disagreement_findings_close_together(
    canonical_request: DetectProteinInferenceArtifactsRequest,
) -> None:
    code = ProteinInferenceArtifactSignalCode.BATCH_INCONSISTENCY
    ledger = canonical_request.evidence_ledger
    assert ledger is not None
    peptide = next(
        item
        for item in ledger.units
        if item.unit_kind is ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE
    )
    group = next(
        item
        for item in ledger.units
        if item.unit_kind is ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP
    )
    ambiguity = next(
        item
        for item in ledger.units
        if item.unit_kind is ProteinInferenceEvidenceUnitKind.AMBIGUITY_CLASS
    )
    request = request_with_signal(
        canonical_request,
        code,
        unit_id=peptide.unit_id,
        supporting_count=6,
        evaluated_count=10,
    )
    request = request_with_signal(
        request,
        code,
        unit_id=group.unit_id,
        supporting_count=3,
        evaluated_count=10,
    )
    request = request_with_signal(
        request,
        code,
        unit_id=ambiguity.unit_id,
        observation_state=ProteinInferenceArtifactObservationState.MISSING,
        supporting_count=0,
        evaluated_count=0,
    )
    result = detect_protein_inference_artifacts(request)
    assert peptide.unit_id in result.exclusion_mask.exclude_unit_ids
    assert {group.unit_id, ambiguity.unit_id} <= set(result.exclusion_mask.review_unit_ids)
    assert set(result.exclusion_mask.retain_unit_ids) == {
        item.unit_id for item in ledger.units
    } - {peptide.unit_id, group.unit_id, ambiguity.unit_id}
    assert result.disposition is ProteinInferenceArtifactDisposition.QUARANTINED
    assert {
        ProteinInferenceArtifactFindingCode.ARTIFACT_DETECTED,
        ProteinInferenceArtifactFindingCode.REQUIRED_SIGNAL_MISSING,
    } <= {item.code for item in result.findings}


def test_same_signal_preserves_every_indeterminate_category_with_detection(
    canonical_request: DetectProteinInferenceArtifactsRequest,
) -> None:
    code = ProteinInferenceArtifactSignalCode.BATCH_INCONSISTENCY
    ledger = canonical_request.evidence_ledger
    assert ledger is not None
    units = ledger.units
    request = request_with_signal(
        canonical_request,
        code,
        unit_id=units[0].unit_id,
        supporting_count=6,
        evaluated_count=10,
    )
    for unit, state in zip(
        units[1:4],
        (
            ProteinInferenceArtifactObservationState.MISSING,
            ProteinInferenceArtifactObservationState.UNSUPPORTED,
            ProteinInferenceArtifactObservationState.OBSERVED,
        ),
        strict=True,
    ):
        request = request_with_signal(
            request,
            code,
            unit_id=unit.unit_id,
            observation_state=state,
            supporting_count=0,
            evaluated_count=0,
        )
    result = detect_protein_inference_artifacts(request)
    assert {
        ProteinInferenceArtifactFindingCode.ARTIFACT_DETECTED,
        ProteinInferenceArtifactFindingCode.REQUIRED_SIGNAL_MISSING,
        ProteinInferenceArtifactFindingCode.REQUIRED_SIGNAL_UNSUPPORTED,
        ProteinInferenceArtifactFindingCode.SIGNAL_NOT_EVALUABLE,
    } <= {item.code for item in result.findings}


@pytest.mark.parametrize(
    "mutation",
    [
        "delete_required_source",
        "delete_required_claim_and_anchor",
        "wrong_format",
        "wrong_artifact_digest",
    ],
)
def test_resigned_compact_graph_laundering_is_rejected(
    canonical_request: DetectProteinInferenceArtifactsRequest,
    mutation: str,
) -> None:
    receipt = canonical_request.quality_receipt
    payload = _payload(receipt)
    if mutation == "delete_required_source":
        payload["sources"] = [
            item
            for item in payload["sources"]
            if item["role"] != ProteinInferenceRawRole.CANONICAL_SEQUENCES.value
        ]
        payload["source_count"] -= 1
    elif mutation == "delete_required_claim_and_anchor":
        claim_id = next(
            item["claim_id"]
            for item in payload["claims"]
            if item["claim_role"] == "complex_activity_input_bundle"
        )
        payload["claims"] = [item for item in payload["claims"] if item["claim_id"] != claim_id]
        payload["sources"] = [
            item for item in payload["sources"] if item["bound_claim_id"] != claim_id
        ]
        payload["claim_count"] -= 1
        payload["source_count"] -= 1
    elif mutation == "wrong_format":
        payload["sources"][0]["detected_format"] = "fasta"
    else:
        payload["sources"][0]["artifact_digest"] = _ZERO_DIGEST
    with pytest.raises(ValidationError):
        _resigned_receipt(payload)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("status", "status contradicts"),
        ("ratio", "counts contradict"),
        ("missing_counts", "cannot carry a ratio"),
        ("direction", "direction contradicts"),
        ("censored", "censored state"),
    ],
)
def test_compact_quality_metric_rejects_reauthored_semantics(
    canonical_request: DetectProteinInferenceArtifactsRequest,
    mutation: str,
    message: str,
) -> None:
    payload = _payload(canonical_request.quality_receipt.quality_metrics[0])
    if mutation == "status":
        payload["status"] = ProteinInferenceQualityMetricStatus.FAIL.value
    elif mutation == "ratio":
        payload.update({"numerator": 2, "denominator": 1, "value_ppm": M0305_RATE_SCALE})
    elif mutation == "missing_counts":
        payload["observation_state"] = ProteinInferenceQualityObservationState.MISSING.value
    elif mutation == "direction":
        payload["direction"] = (
            ProteinInferenceQualityMetricDirection.AT_MOST.value
            if payload["direction"] == ProteinInferenceQualityMetricDirection.AT_LEAST.value
            else ProteinInferenceQualityMetricDirection.AT_LEAST.value
        )
    else:
        payload["observation_state"] = ProteinInferenceQualityObservationState.CENSORED.value
        payload["censored_count"] = 0
    with pytest.raises(ValidationError, match=message):
        ProteinInferenceArtifactQualityMetricReceipt.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


def test_qualified_receipt_rejects_self_consistent_required_failure(
    canonical_request: DetectProteinInferenceArtifactsRequest,
) -> None:
    payload = _payload(canonical_request.quality_receipt)
    metric = next(
        item
        for item in payload["quality_metrics"]
        if item["direction"] == ProteinInferenceQualityMetricDirection.AT_LEAST.value
        and item["observation_state"] == ProteinInferenceQualityObservationState.OBSERVED.value
    )
    metric.update(
        {
            "numerator": 0,
            "denominator": 1,
            "value_ppm": 0,
            "status": ProteinInferenceQualityMetricStatus.FAIL.value,
            "censored_count": 0,
        }
    )
    with pytest.raises(ValidationError, match="qualified quality receipt contradicts"):
        _resigned_receipt(payload)


def test_semantic_reorder_materializes_one_exact_request_and_result(
    canonical_request: DetectProteinInferenceArtifactsRequest,
) -> None:
    request = request_with_signal(
        canonical_request,
        ProteinInferenceArtifactSignalCode.CONTAMINANT_REFERENCE_SUPPORT,
        supporting_count=3,
    )
    request = request_with_signal(
        request,
        ProteinInferenceArtifactSignalCode.DECOY_COMPETITION_FAILURE,
        supporting_count=3,
    )
    canonical = detect_protein_inference_artifacts(request)
    payload = _payload(canonical)
    embedded = payload["request"]
    embedded["quality_receipt"]["sources"].reverse()
    embedded["quality_receipt"]["claims"].reverse()
    embedded["quality_receipt"]["quality_metrics"].reverse()
    embedded["policy"]["profiles"].reverse()
    embedded["policy"]["profiles"][0]["thresholds"].reverse()
    embedded["evidence_ledger"]["units"].reverse()
    for unit in embedded["evidence_ledger"]["units"]:
        unit["source_ids"].reverse()
        unit["claim_ids"].reverse()
        unit["signals"].reverse()
    for field in (
        "signal_scores",
        "artifact_posteriors",
        "contamination_flags",
        "findings",
        "evidence",
        "limitations",
    ):
        payload[field].reverse()
    for posterior in payload["artifact_posteriors"]:
        posterior["contributing_signal_codes"].reverse()
    for finding in payload["findings"]:
        finding["signal_codes"].reverse()
        finding["unit_ids"].reverse()
    for field in ("retain_unit_ids", "review_unit_ids", "exclude_unit_ids"):
        payload["exclusion_mask"][field].reverse()
    payload["provenance"]["input_digests"].reverse()
    payload["provenance"]["control_decisions"].reverse()
    payload["uncertainty"]["sensitivity_notes"].reverse()
    payload["result_digest"] = result_payload_digest(payload)

    reconstructed = ProteinInferenceArtifactDetectionResult.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )
    assert normalized_result(payload) == normalized_result(canonical)
    assert reconstructed == canonical
    assert reconstructed.request == canonical.request
    assert reconstructed.result_digest == canonical.result_digest


def _mutate_result(payload: dict[str, Any], mutation: str) -> None:  # noqa: C901, PLR0912
    if mutation == "result_id":
        payload["result_id"] = "result.m0305.forged"
    elif mutation == "score":
        payload["signal_scores"][0]["evidence_score_ppm"] = 1
    elif mutation == "posterior":
        state = payload["artifact_posteriors"][0]["state"]
        payload["artifact_posteriors"][0]["state"] = (
            "detected" if state == "clear" else "clear"
        )
    elif mutation == "flag":
        payload["contamination_flags"] = payload["contamination_flags"][1:]
    elif mutation == "mask":
        unit_id = payload["exclusion_mask"]["review_unit_ids"].pop()
        payload["exclusion_mask"]["retain_unit_ids"].append(unit_id)
    elif mutation == "finding_remove":
        payload["findings"] = payload["findings"][1:]
    elif mutation == "finding_add":
        payload["findings"].append(
            _payload(finding_for(ProteinInferenceArtifactFindingCode.UPSTREAM_ABSTAINED))
        )
    elif mutation == "support":
        payload["support"]["reason_code"] = "forged"
    elif mutation == "provenance":
        payload["provenance"]["actor_id"] = "actor.forged"
    elif mutation == "evidence":
        payload["evidence"] = payload["evidence"][1:]
    elif mutation == "limitation":
        payload["limitations"][0]["statement"] = "forged limitation"
    elif mutation == "review":
        payload["human_review_required"] = False
    else:
        payload["receipt"]["supersedes_result_digest"] = _ZERO_DIGEST


@pytest.mark.parametrize(
    "mutation",
    [
        "result_id",
        "score",
        "posterior",
        "flag",
        "mask",
        "finding_remove",
        "finding_add",
        "support",
        "provenance",
        "evidence",
        "limitation",
        "review",
        "supersedes",
    ],
)
def test_resigned_result_forgery_matrix_is_rejected(
    canonical_request: DetectProteinInferenceArtifactsRequest,
    mutation: str,
) -> None:
    request = request_with_signal(
        canonical_request,
        ProteinInferenceArtifactSignalCode.CONTAMINANT_REFERENCE_SUPPORT,
        supporting_count=3,
    )
    result = detect_protein_inference_artifacts(request)
    payload = _payload(result)
    _mutate_result(payload, mutation)
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError):
        ProteinInferenceArtifactDetectionResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


@pytest.mark.parametrize(
    ("upstream", "expected", "finding"),
    [
        (
            ProteinInferenceQualityDisposition.REJECTED,
            ProteinInferenceArtifactDisposition.REJECTED,
            ProteinInferenceArtifactFindingCode.UPSTREAM_REJECTED,
        ),
        (
            ProteinInferenceQualityDisposition.QUARANTINED,
            ProteinInferenceArtifactDisposition.QUARANTINED,
            ProteinInferenceArtifactFindingCode.UPSTREAM_QUARANTINED,
        ),
        (
            ProteinInferenceQualityDisposition.ABSTAINED,
            ProteinInferenceArtifactDisposition.ABSTAINED,
            ProteinInferenceArtifactFindingCode.UPSTREAM_ABSTAINED,
        ),
    ],
)
def test_upstream_failure_precedence_is_typed_and_never_traverses_success_graph(
    canonical_request: DetectProteinInferenceArtifactsRequest,
    upstream: ProteinInferenceQualityDisposition,
    expected: ProteinInferenceArtifactDisposition,
    finding: ProteinInferenceArtifactFindingCode,
) -> None:
    receipt = _safe_receipt(canonical_request, upstream)
    request = _request_with_receipt(canonical_request, receipt, evidence_ledger=None)
    result = detect_protein_inference_artifacts(request)
    assert result.disposition is expected
    assert {item.code for item in result.findings} == {finding}
    assert result.signal_scores == ()
    assert result.artifact_posteriors == ()
    assert result.contamination_flags == ()
    assert result.exclusion_mask.retain_unit_ids == ()
    assert result.support.status is not SupportStatus.SUPPORTED
    assert result.human_review_required is True


def test_upstream_limited_review_is_preserved_and_supersession_is_explicit(
    canonical_request: DetectProteinInferenceArtifactsRequest,
) -> None:
    payload = _payload(canonical_request.quality_receipt)
    metric = next(
        item
        for item in payload["quality_metrics"]
        if item["direction"] == ProteinInferenceQualityMetricDirection.AT_LEAST.value
        and item["observation_state"] == ProteinInferenceQualityObservationState.OBSERVED.value
    )
    metric.update(
        {
            "required": False,
            "numerator": metric["warning_threshold_ppm"],
            "denominator": M0305_RATE_SCALE,
            "value_ppm": metric["warning_threshold_ppm"],
            "status": ProteinInferenceQualityMetricStatus.WARNING.value,
            "censored_count": 0,
        }
    )
    payload.update(
        {
            "quality_support_status": SupportStatus.LIMITED.value,
            "quality_human_review_required": True,
        }
    )
    limited_receipt = _resigned_receipt(payload)
    limited_ledger = _resigned_ledger(
        canonical_request,
        quality_metric_binding_digest=limited_receipt.quality_metric_binding_digest,
    )
    limited_request = _request_with_receipt(
        canonical_request,
        limited_receipt,
        evidence_ledger=limited_ledger,
    )
    limited = detect_protein_inference_artifacts(limited_request)
    assert limited.disposition is ProteinInferenceArtifactDisposition.QUARANTINED
    assert limited.support.status is SupportStatus.REVIEW_REQUIRED
    assert limited.human_review_required is True
    assert {item.code for item in limited.findings} == {
        ProteinInferenceArtifactFindingCode.UPSTREAM_REVIEW_REQUIRED
    }

    supersedes = "sha256:" + ("f" * 64)
    recovery = DetectProteinInferenceArtifactsRequest.model_validate(
        canonical_request.model_copy(update={"supersedes_result_digest": supersedes}), strict=True
    )
    recovered = detect_protein_inference_artifacts(recovery)
    assert recovered.receipt.supersedes_result_digest == supersedes
    assert supersedes in recovered.provenance.input_digests
    assert recovered.request_digest == canonical_request_digest(recovery)
    assert recovered.request_digest != canonical_request_digest(canonical_request)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("header", ProteinInferenceArtifactFindingCode.EVIDENCE_LEDGER_BINDING_MISMATCH),
        ("unit", ProteinInferenceArtifactFindingCode.EVIDENCE_UNIT_BINDING_CONFLICT),
        ("profile", ProteinInferenceArtifactFindingCode.DETECTOR_PROFILE_UNSUPPORTED),
    ],
)
def test_binding_and_profile_failures_are_distinct_before_scoring(
    canonical_request: DetectProteinInferenceArtifactsRequest,
    mutation: str,
    expected: ProteinInferenceArtifactFindingCode,
) -> None:
    request = canonical_request
    if mutation == "header":
        ledger = _resigned_ledger(request, source_binding_digest=_ZERO_DIGEST)
        request = request.model_copy(update={"evidence_ledger": ledger})
    elif mutation == "unit":
        current_ledger = request.evidence_ledger
        assert current_ledger is not None
        peptide = next(
            item
            for item in current_ledger.units
            if item.unit_kind is ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE
        )
        incompatible = next(
            item
            for item in request.quality_receipt.sources
            if item.role is ProteinInferenceRawRole.AMBIGUITY_MANIFEST
        )
        unit = ProteinInferenceArtifactEvidenceUnit.model_validate(
            peptide.model_copy(update={"source_ids": (incompatible.source_id,)}), strict=True
        )
        units = tuple(
            unit if item.unit_id == peptide.unit_id else item for item in current_ledger.units
        )
        request = request.model_copy(
            update={"evidence_ledger": _resigned_ledger(request, units=units)}
        )
    else:
        profile = request.policy.profiles[0]
        profile = ProteinInferenceArtifactProfile.model_validate(
            profile.model_copy(update={"approved_assay_protocol_versions": ("99.0.0",)}),
            strict=True,
        )
        policy = ProteinInferenceArtifactPolicy.model_validate(
            request.policy.model_copy(update={"profiles": (profile,)}), strict=True
        )
        request = _request_with_policy(request, policy, evidence_ledger=request.evidence_ledger)
    result = detect_protein_inference_artifacts(request)
    assert result.signal_scores == ()
    assert {item.code for item in result.findings} == {expected}
    assert result.disposition is (
        ProteinInferenceArtifactDisposition.ABSTAINED
        if mutation == "profile"
        else ProteinInferenceArtifactDisposition.QUARANTINED
    )


class _HostileLedger(dict[str, object]):
    def __init__(self) -> None:
        super().__init__()
        self.traversals = 0

    def get(self, key: str, default: object = None) -> object:
        self.traversals += 1
        raise AssertionError((key, default))

    def items(self) -> Never:
        self.traversals += 1
        raise AssertionError("items")

    def __iter__(self) -> Never:
        self.traversals += 1
        raise AssertionError("iteration")


@pytest.mark.parametrize(
    ("role", "state"),
    [
        ("approved_configuration", "rejected"),
        ("identity_lineage", "unresolved"),
        ("provenance", "rejected"),
        ("consent", "withheld"),
        ("quality", "rejected"),
        ("support", "rejected"),
        ("intended_use", "rejected"),
    ],
)
def test_each_denied_control_precedes_hostile_ledger_access(
    canonical_request: DetectProteinInferenceArtifactsRequest,
    role: str,
    state: str,
) -> None:
    payload = canonical_request.model_dump(mode="python")
    hostile = _HostileLedger()
    payload["evidence_ledger"] = hostile
    references = cast("dict[str, dict[str, Any]]", payload["context"]["references"])
    references[role]["state"] = state
    with pytest.raises(ProteinInferenceArtifactAuthorizationError):
        detect_protein_inference_artifacts(payload)
    assert hostile.traversals == 0


def test_authorized_policy_shape_failure_discards_hostile_ledger_without_access(
    canonical_request: DetectProteinInferenceArtifactsRequest,
) -> None:
    policy = ProteinInferenceArtifactPolicy.model_validate(
        canonical_request.policy.model_copy(
            update={"max_sources": canonical_request.quality_receipt.source_count - 1}
        ),
        strict=True,
    )
    refs = canonical_request.context.references
    approved = refs.approved_configuration.model_copy(
        update={
            "evidence": refs.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    context = canonical_request.context.model_copy(
        update={"references": refs.model_copy(update={"approved_configuration": approved})}
    )
    payload = canonical_request.model_dump(mode="python")
    payload.update({"context": context, "policy": policy})
    hostile = _HostileLedger()
    payload["evidence_ledger"] = hostile

    result = detect_protein_inference_artifacts(payload)
    assert hostile.traversals == 0
    assert result.disposition is ProteinInferenceArtifactDisposition.ABSTAINED
    assert {item.code for item in result.findings} == {
        ProteinInferenceArtifactFindingCode.UPSTREAM_SHAPE_UNSUPPORTED
    }
    assert result.signal_scores == ()
    assert result.artifact_posteriors == ()
    assert result.contamination_flags == ()
    assert result.exclusion_mask.retain_unit_ids == ()
    assert result.support.status is SupportStatus.UNSUPPORTED
    assert result.human_review_required is True


def test_identifier_privacy_rejects_payload_like_peptide_canary(
    canonical_request: DetectProteinInferenceArtifactsRequest,
) -> None:
    ledger = canonical_request.evidence_ledger
    assert ledger is not None
    with pytest.raises(ValidationError, match="opaque"):
        ProteinInferenceArtifactEvidenceUnit.model_validate(
            ledger.units[0].model_copy(update={"unit_id": "unit.mpeptidek"}), strict=True
        )


def test_output_is_metadata_only_and_probability_limitation_is_explicit(
    canonical_result: ProteinInferenceArtifactDetectionResult,
) -> None:
    rendered = canonical_result.model_dump_json()
    assert "MPEPTIDEK" not in rendered
    assert "scan=1" not in rendered
    assert all(not item.score_is_calibrated_probability for item in canonical_result.signal_scores)
    assert all(
        not item.score_is_calibrated_probability for item in canonical_result.artifact_posteriors
    )
    assert {item.code for item in canonical_result.limitations} >= {
        M0305_SCORE_LIMITATION_CODE
    }
    assert canonical_result.parent_target == "complex_activity"
    assert canonical_result.emits_complex_activity is False
    assert canonical_result.infers_identity is False
    assert canonical_result.infers_protein is False
    assert canonical_result.infers_kinase_activity is False


def test_exact_capacity_executes_totally_and_all_first_excesses_reject(
    capacity_request: DetectProteinInferenceArtifactsRequest,
    capacity_result: ProteinInferenceArtifactDetectionResult,
) -> None:
    receipt = capacity_request.quality_receipt
    ledger = capacity_request.evidence_ledger
    assert ledger is not None
    assert (receipt.source_count, receipt.claim_count, len(ledger.units)) == (
        M0305_MAX_SOURCES,
        M0305_MAX_CLAIMS,
        M0305_MAX_UNITS,
    )
    assert len(capacity_result.signal_scores) == M0305_MAX_SIGNAL_SCORES
    assert len(capacity_result.artifact_posteriors) == M0305_MAX_UNITS
    assert len(capacity_result.contamination_flags) == M0305_MAX_CONTAMINATION_FLAGS
    assert len(capacity_result.evidence) == M0305_MAX_EVIDENCE
    assert len(canonical_json_bytes(capacity_request)) <= M0305_MAX_CANONICAL_REQUEST_BYTES
    assert len(canonical_json_bytes(capacity_result)) <= M0305_MAX_CANONICAL_RESULT_BYTES

    source_payload = _payload(receipt)
    source_payload["sources"].append(deepcopy(source_payload["sources"][-1]))
    source_payload["sources"][-1]["source_id"] = _opaque_id("source", "excess")
    source_payload["source_count"] = M0305_MAX_SOURCES + 1
    with pytest.raises(ValidationError):
        _resigned_receipt(source_payload)

    claim_payload = _payload(receipt)
    claim_payload["claims"].append(deepcopy(claim_payload["claims"][-1]))
    claim_payload["claims"][-1]["claim_id"] = _opaque_id("claim", "excess")
    claim_payload["claim_count"] = M0305_MAX_CLAIMS + 1
    with pytest.raises(ValidationError):
        _resigned_receipt(claim_payload)

    unit = ledger.units[-1].model_copy(update={"unit_id": _opaque_id("unit", "excess")})
    ledger_payload = _payload(ledger)
    ledger_payload["units"].append(_payload(unit))
    ledger_payload["ledger_digest"] = artifact_evidence_ledger_digest(ledger_payload)
    with pytest.raises(ValidationError):
        ProteinInferenceArtifactEvidenceLedger.model_validate_json(
            canonical_json_bytes(ledger_payload), strict=True
        )

    result_payload = _payload(capacity_result)
    result_payload["evidence"].append(deepcopy(result_payload["evidence"][-1]))
    result_payload["result_digest"] = result_payload_digest(result_payload)
    with pytest.raises(ValidationError):
        ProteinInferenceArtifactDetectionResult.model_validate_json(
            canonical_json_bytes(result_payload), strict=True
        )


def test_profile_version_reference_and_count_caps_accept_exact_and_reject_first_excess(
    capacity_request: DetectProteinInferenceArtifactsRequest,
) -> None:
    profile = capacity_request.policy.profiles[0]
    versions = tuple(f"{index}.0.0" for index in range(1, M0305_MAX_APPROVED_VERSIONS + 1))
    max_profile = ProteinInferenceArtifactProfile.model_validate(
        profile.model_copy(
            update={
                "approved_assay_protocol_versions": versions,
                "approved_controlled_vocabulary_versions": versions,
                "approved_unit_system_versions": versions,
            }
        ),
        strict=True,
    )
    assert len(max_profile.approved_assay_protocol_versions) == M0305_MAX_APPROVED_VERSIONS
    with pytest.raises(ValidationError):
        ProteinInferenceArtifactProfile.model_validate(
            max_profile.model_copy(
                update={"approved_assay_protocol_versions": (*versions, "99.0.0")}
            ),
            strict=True,
        )

    profiles = (
        profile,
        *(
            ProteinInferenceArtifactProfile.model_validate(
                profile.model_copy(
                    update={
                        "profile_id": f"profile.synthetic.m0305.boundary.{index:02d}",
                        "version": f"{index + 1}.0.0",
                        "approved_assay_protocol_versions": (f"{index + 1}.0.0",),
                        "approved_controlled_vocabulary_versions": (f"{index + 1}.0.0",),
                        "approved_unit_system_versions": (f"{index + 1}.0.0",),
                    }
                ),
                strict=True,
            )
            for index in range(1, M0305_MAX_PROFILES)
        ),
    )
    policy = ProteinInferenceArtifactPolicy.model_validate(
        capacity_request.policy.model_copy(update={"profiles": profiles}), strict=True
    )
    assert len(policy.profiles) == M0305_MAX_PROFILES
    with pytest.raises(ValidationError):
        ProteinInferenceArtifactPolicy.model_validate(
            policy.model_copy(
                update={
                    "profiles": (
                        *profiles,
                        profiles[-1].model_copy(
                            update={
                                "profile_id": "profile.synthetic.m0305.excess",
                                "approved_assay_protocol_versions": ("99.0.0",),
                                "approved_controlled_vocabulary_versions": ("99.0.0",),
                                "approved_unit_system_versions": ("99.0.0",),
                            }
                        ),
                    )
                }
            ),
            strict=True,
        )

    peptide_claims = {
        item.claim_id
        for item in capacity_request.quality_receipt.claims
        if item.claim_role.value == "peptide_evidence_manifest"
    }
    pairs = tuple(
        (item.source_id, item.bound_claim_id)
        for item in capacity_request.quality_receipt.sources
        if item.bound_claim_id in peptide_claims
    )
    base_unit = cast(
        "ProteinInferenceArtifactEvidenceLedger", capacity_request.evidence_ledger
    ).units[0]
    exact_refs = ProteinInferenceArtifactEvidenceUnit.model_validate(
        base_unit.model_copy(
            update={
                "unit_id": _opaque_id("unit", "exactrefs"),
                "source_ids": tuple(item[0] for item in pairs[:M0305_MAX_UNIT_SOURCE_REFS]),
                "claim_ids": tuple(item[1] for item in pairs[:M0305_MAX_UNIT_CLAIM_REFS]),
            }
        ),
        strict=True,
    )
    assert len(exact_refs.source_ids) == M0305_MAX_UNIT_SOURCE_REFS
    assert len(exact_refs.claim_ids) == M0305_MAX_UNIT_CLAIM_REFS
    with pytest.raises(ValidationError):
        ProteinInferenceArtifactEvidenceUnit.model_validate(
            exact_refs.model_copy(
                update={"source_ids": (*exact_refs.source_ids, _opaque_id("source", "excess"))}
            ),
            strict=True,
        )
    signal = next(
        item
        for item in base_unit.signals
        if item.observation_state is ProteinInferenceArtifactObservationState.OBSERVED
    )
    assert ProteinInferenceArtifactSignal.model_validate(
        signal.model_copy(
            update={"supporting_count": M0305_MAX_COUNT, "evaluated_count": M0305_MAX_COUNT}
        ),
        strict=True,
    )
    with pytest.raises(ValidationError):
        ProteinInferenceArtifactSignal.model_validate(
            signal.model_copy(
                update={
                    "supporting_count": M0305_MAX_COUNT + 1,
                    "evaluated_count": M0305_MAX_COUNT + 1,
                }
            ),
            strict=True,
        )


def test_plugin_accepts_exact_byte_ceiling_and_rejects_cap_plus_one(
    canonical_request: DetectProteinInferenceArtifactsRequest,
) -> None:
    plugin = M0305Plugin(M0305Service())
    request_bytes = canonical_json_bytes(canonical_request)
    exact = request_bytes + b" " * (M0305_MAX_CANONICAL_REQUEST_BYTES - len(request_bytes))
    token = plugin.validate(exact)
    assert token.request == canonical_request
    with pytest.raises(ValueError, match=r"maximum|exceeds|bytes"):
        plugin.validate(exact + b" ")


def test_normalized_request_typed_dict_parity_and_strict_unknown_rejection(
    canonical_request: DetectProteinInferenceArtifactsRequest,
) -> None:
    payload = _payload(canonical_request)
    assert normalized_request(canonical_request) == normalized_request(payload)
    assert canonical_request_digest(canonical_request) == canonical_request_digest(payload)
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        DetectProteinInferenceArtifactsRequest.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )
