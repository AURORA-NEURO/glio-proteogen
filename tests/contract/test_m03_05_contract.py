"""Relational contract hardening for M03-05 artifact detection."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m03_04 import ProteinInferenceQualityDisposition
from glio_proteogen.contracts.m03_05 import (
    DetectProteinInferenceArtifactsRequest,
    ProteinInferenceArtifactDetectionResult,
    ProteinInferenceArtifactEvidenceLedger,
    ProteinInferenceArtifactEvidenceUnit,
    ProteinInferenceArtifactFinding,
    ProteinInferenceArtifactObservationState,
    ProteinInferenceArtifactPolicy,
    ProteinInferenceArtifactPosterior,
    ProteinInferenceArtifactProfile,
    ProteinInferenceArtifactQualityReceipt,
    ProteinInferenceArtifactSignal,
    ProteinInferenceArtifactSignalCode,
    ProteinInferenceArtifactSignalScore,
    ProteinInferenceArtifactThreshold,
    ProteinInferenceContaminationFlag,
    ProteinInferenceEvidenceExclusionMask,
    artifact_evidence_ledger_digest,
    artifact_quality_receipt_digest,
    configuration_digest,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c03_protein_inference.m03_05_artifact_detection import (
    detect_protein_inference_artifacts,
)
from tests.modules.c03_protein_inference.test_m03_05_lifecycle import (
    build_m0305_request,
    request_with_signal,
)

_ZERO_DIGEST = "sha256:" + ("0" * 64)


def _payload(value: object) -> dict[str, Any]:
    return value.model_dump(mode="python")  # type: ignore[attr-defined,no-any-return]


def test_threshold_profile_and_policy_semantics_are_closed() -> None:
    request = build_m0305_request()
    threshold = request.policy.profiles[0].thresholds[0]
    payload = _payload(threshold)
    payload["review_threshold_ppm"] = 900_000
    with pytest.raises(ValidationError, match="cannot exceed"):
        ProteinInferenceArtifactThreshold.model_validate(payload, strict=True)

    payload = _payload(threshold)
    payload["applicable_unit_kinds"] = (
        threshold.applicable_unit_kinds[0],
        threshold.applicable_unit_kinds[0],
    )
    with pytest.raises(ValidationError, match="must be unique"):
        ProteinInferenceArtifactThreshold.model_validate(payload, strict=True)

    payload = _payload(threshold)
    payload["applicable_unit_kinds"] = threshold.applicable_unit_kinds[:-1]
    with pytest.raises(ValidationError, match="locked signal domain"):
        ProteinInferenceArtifactThreshold.model_validate(payload, strict=True)

    profile = request.policy.profiles[0]
    profile_payload = _payload(profile)
    profile_payload["approved_assay_protocol_versions"] = (
        profile.approved_assay_protocol_versions[0],
        profile.approved_assay_protocol_versions[0],
    )
    with pytest.raises(ValidationError, match="versions must be unique"):
        ProteinInferenceArtifactProfile.model_validate(profile_payload, strict=True)

    profile_payload = _payload(profile)
    profile_payload["thresholds"] = (profile.thresholds[0],) * 8
    with pytest.raises(ValidationError, match="each of eight signals"):
        ProteinInferenceArtifactProfile.model_validate(profile_payload, strict=True)

    with pytest.raises(ValidationError, match="identities must be unique"):
        ProteinInferenceArtifactPolicy.model_validate(
            request.policy.model_copy(update={"profiles": (profile, profile)}),
            strict=True,
        )
    overlapping = profile.model_copy(update={"profile_id": "profile.m0305.overlap"})
    with pytest.raises(ValidationError, match="pairwise disjoint"):
        ProteinInferenceArtifactPolicy.model_validate(
            request.policy.model_copy(update={"profiles": (profile, overlapping)}),
            strict=True,
        )


def test_compact_quality_receipt_rejects_projection_and_envelope_contradictions() -> None:
    receipt = build_m0305_request().quality_receipt
    payload = _payload(receipt)
    payload["sources"] = (receipt.sources[0], receipt.sources[0], *receipt.sources[2:])
    payload["receipt_digest"] = artifact_quality_receipt_digest(payload)
    with pytest.raises(ValidationError, match="projections must be unique"):
        ProteinInferenceArtifactQualityReceipt.model_validate(payload, strict=True)

    payload = _payload(receipt)
    payload["quality_metrics"] = ()
    payload["receipt_digest"] = artifact_quality_receipt_digest(payload)
    with pytest.raises(ValidationError, match="exact compact graph"):
        ProteinInferenceArtifactQualityReceipt.model_validate(payload, strict=True)

    payload = _payload(receipt)
    payload.update(
        quality_disposition=ProteinInferenceQualityDisposition.ABSTAINED,
        quality_support_status=SupportStatus.UNSUPPORTED,
        quality_human_review_required=True,
    )
    payload["receipt_digest"] = artifact_quality_receipt_digest(payload)
    with pytest.raises(ValidationError, match="cannot expose graph"):
        ProteinInferenceArtifactQualityReceipt.model_validate(payload, strict=True)

    payload = _payload(receipt)
    payload["quality_support_status"] = SupportStatus.UNSUPPORTED
    payload["receipt_digest"] = artifact_quality_receipt_digest(payload)
    with pytest.raises(ValidationError, match="support status contradict"):
        ProteinInferenceArtifactQualityReceipt.model_validate(payload, strict=True)

    payload = _payload(receipt)
    payload["quality_human_review_required"] = True
    payload["receipt_digest"] = artifact_quality_receipt_digest(payload)
    with pytest.raises(ValidationError, match="review requirement contradict"):
        ProteinInferenceArtifactQualityReceipt.model_validate(payload, strict=True)

    with pytest.raises(ValidationError, match="digest closure failed"):
        ProteinInferenceArtifactQualityReceipt.model_validate(
            receipt.model_copy(update={"receipt_digest": _ZERO_DIGEST}),
            strict=True,
        )


def test_signal_unit_and_ledger_structural_invariants_are_closed() -> None:
    request = build_m0305_request()
    ledger = request.evidence_ledger
    assert ledger is not None
    unit = ledger.units[0]
    signal = next(
        item
        for item in unit.signals
        if item.signal_code is ProteinInferenceArtifactSignalCode.CONTAMINANT_REFERENCE_SUPPORT
    )
    with pytest.raises(ValidationError, match="cannot exceed"):
        ProteinInferenceArtifactSignal.model_validate(
            signal.model_copy(update={"supporting_count": 11}),
            strict=True,
        )
    with pytest.raises(ValidationError, match="zero counts"):
        ProteinInferenceArtifactSignal.model_validate(
            signal.model_copy(
                update={"observation_state": ProteinInferenceArtifactObservationState.MISSING}
            ),
            strict=True,
        )
    with pytest.raises(ValidationError, match="bindings must be unique"):
        ProteinInferenceArtifactEvidenceUnit.model_validate(
            unit.model_copy(update={"source_ids": unit.source_ids * 2}),
            strict=True,
        )
    with pytest.raises(ValidationError, match="all eight exact signals"):
        ProteinInferenceArtifactEvidenceUnit.model_validate(
            unit.model_copy(update={"signals": (unit.signals[0],) * 8}),
            strict=True,
        )
    with pytest.raises(ValidationError, match="cannot be marked not applicable"):
        ProteinInferenceArtifactEvidenceUnit.model_validate(
            unit.model_copy(
                update={
                    "signals": tuple(
                        item.model_copy(
                            update={
                                "observation_state": (
                                    ProteinInferenceArtifactObservationState.NOT_APPLICABLE
                                ),
                                "supporting_count": 0,
                                "evaluated_count": 0,
                            }
                        )
                        if item is signal
                        else item
                        for item in unit.signals
                    )
                }
            ),
            strict=True,
        )
    duplicate_payload = _payload(ledger)
    duplicate_payload["units"] = (unit, unit)
    duplicate_payload["ledger_digest"] = artifact_evidence_ledger_digest(duplicate_payload)
    with pytest.raises(ValidationError, match="identifiers must be unique"):
        ProteinInferenceArtifactEvidenceLedger.model_validate(
            duplicate_payload,
            strict=True,
        )
    with pytest.raises(ValidationError, match="digest does not match"):
        ProteinInferenceArtifactEvidenceLedger.model_validate(
            ledger.model_copy(update={"ledger_digest": _ZERO_DIGEST}),
            strict=True,
        )


def test_request_temporal_control_and_presence_relations_are_closed() -> None:
    request = build_m0305_request()
    refs = request.context.references
    bad_quality = refs.quality.model_copy(
        update={"evidence": refs.quality.evidence.model_copy(update={"digest": _ZERO_DIGEST})}
    )
    with pytest.raises(ValidationError, match="quality control"):
        DetectProteinInferenceArtifactsRequest.model_validate(
            request.model_copy(
                update={
                    "context": request.context.model_copy(
                        update={"references": refs.model_copy(update={"quality": bad_quality})}
                    )
                }
            ),
            strict=True,
        )
    with pytest.raises(ValidationError, match="approved configuration"):
        DetectProteinInferenceArtifactsRequest.model_validate(
            request.model_copy(
                update={
                    "policy": request.policy.model_copy(
                        update={"max_units": request.policy.max_units - 1}
                    )
                }
            ),
            strict=True,
        )
    policy = request.policy.model_copy(update={"max_sources": 12})
    approved = refs.approved_configuration.model_copy(
        update={
            "evidence": refs.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    with pytest.raises(ValidationError, match="ledger presence"):
        DetectProteinInferenceArtifactsRequest.model_validate(
            request.model_copy(
                update={
                    "policy": policy,
                    "context": request.context.model_copy(
                        update={
                            "references": refs.model_copy(
                                update={"approved_configuration": approved}
                            )
                        }
                    ),
                }
            ),
            strict=True,
        )
    ledger = request.evidence_ledger
    assert ledger is not None
    late_payload = _payload(ledger)
    late_payload["recorded_at"] = request.context.occurred_at + timedelta(seconds=1)
    late_payload["ledger_digest"] = artifact_evidence_ledger_digest(late_payload)
    late = ProteinInferenceArtifactEvidenceLedger.model_validate(late_payload, strict=True)
    with pytest.raises(ValidationError, match="precede detection"):
        DetectProteinInferenceArtifactsRequest.model_validate(
            request.model_copy(update={"evidence_ledger": late}),
            strict=True,
        )


def test_score_posterior_flag_mask_and_finding_shapes_are_closed() -> None:
    result = detect_protein_inference_artifacts(build_m0305_request())
    score = result.signal_scores[0]
    invalid_scores = (
        score.model_copy(update={"supporting_count": None}),
        score.model_copy(update={"supporting_count": 11}),
        score.model_copy(update={"evidence_score_ppm": 1}),
        score.model_copy(
            update={"observation_state": ProteinInferenceArtifactObservationState.MISSING}
        ),
    )
    for invalid in invalid_scores:
        with pytest.raises(ValidationError):
            ProteinInferenceArtifactSignalScore.model_validate(invalid, strict=True)

    posterior = result.artifact_posteriors[0]
    code = posterior.contributing_signal_codes[0]
    with pytest.raises(ValidationError, match="must be unique"):
        ProteinInferenceArtifactPosterior.model_validate(
            posterior.model_copy(update={"contributing_signal_codes": (code, code)}),
            strict=True,
        )

    suspected = detect_protein_inference_artifacts(
        request_with_signal(
            build_m0305_request(),
            ProteinInferenceArtifactSignalCode.CONTAMINANT_REFERENCE_SUPPORT,
            supporting_count=3,
        )
    )
    flag = suspected.contamination_flags[0]
    with pytest.raises(ValidationError, match="locked contamination signal"):
        ProteinInferenceContaminationFlag.model_validate(
            flag.model_copy(
                update={"signal_code": ProteinInferenceArtifactSignalCode.LOW_COMPLEXITY_EVIDENCE}
            ),
            strict=True,
        )
    with pytest.raises(ValidationError, match="unique unit identifiers"):
        ProteinInferenceEvidenceExclusionMask(
            retain_unit_ids=("unit.a", "unit.a"),
        )
    with pytest.raises(ValidationError, match="must be disjoint"):
        ProteinInferenceEvidenceExclusionMask(
            retain_unit_ids=("unit.a",),
            review_unit_ids=("unit.a",),
        )
    finding = suspected.findings[0]
    with pytest.raises(ValidationError, match="references must be unique"):
        ProteinInferenceArtifactFinding.model_validate(
            finding.model_copy(update={"unit_ids": finding.unit_ids * 2}),
            strict=True,
        )
    with pytest.raises(ValidationError, match="closed vocabulary"):
        ProteinInferenceArtifactFinding.model_validate(
            finding.model_copy(update={"message": "forged finding"}),
            strict=True,
        )


def test_result_relational_replay_rejects_every_material_tamper() -> None:
    result = detect_protein_inference_artifacts(build_m0305_request())
    mutations: tuple[tuple[dict[str, object], str], ...] = (
        ({"signal_scores": ()}, "signal scores"),
        ({"artifact_posteriors": ()}, "posteriors"),
        (
            {"exclusion_mask": ProteinInferenceEvidenceExclusionMask()},
            "exclusion mask",
        ),
        ({"request_digest": _ZERO_DIGEST}, "output envelope"),
        ({"completed_at": result.completed_at + timedelta(seconds=1)}, "completion time"),
        (
            {"support": result.support.model_copy(update={"status": SupportStatus.LIMITED})},
            "support is not deterministic",
        ),
        ({"evidence": result.evidence[1:]}, "evidence index"),
        (
            {
                "limitations": (
                    result.limitations[0],
                    result.limitations[0],
                    result.limitations[0],
                )
            },
            "limitations do not close",
        ),
        ({"human_review_required": True}, "human-review"),
        ({"result_digest": _ZERO_DIGEST}, "result digest"),
    )
    for update, message in mutations:
        with pytest.raises(ValidationError, match=message):
            ProteinInferenceArtifactDetectionResult.model_validate(
                result.model_copy(update=update),
                strict=True,
            )

    suspected = detect_protein_inference_artifacts(
        request_with_signal(
            build_m0305_request(),
            ProteinInferenceArtifactSignalCode.CONTAMINANT_REFERENCE_SUPPORT,
            supporting_count=3,
        )
    )
    for field, message in (
        ("contamination_flags", "contamination flags"),
        ("findings", "findings"),
    ):
        update: dict[str, object] = {field: ()}
        with pytest.raises(ValidationError, match=message):
            ProteinInferenceArtifactDetectionResult.model_validate(
                suspected.model_copy(update=update),
                strict=True,
            )
