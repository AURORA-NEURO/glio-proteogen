"""Contract, derivation, and replay closure for M04-05 artifact detection."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from typing import Final, cast
from unittest.mock import patch

import pytest
from evals.m04_05.run import build_scenario_request, build_scenario_result
from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m04_05 import (
    M0405_DETECTOR_CLASS_COUNT,
    M0405_EVIDENCE_CLAIM,
    M0405_MAX_EVIDENCE,
    M0405_PARENT,
    M0405_RATE_SCALE,
    DetectProteoformArtifactsRequest,
    ProteoformArtifactDetectionResult,
    ProteoformArtifactDetectorClass,
    ProteoformArtifactDisposition,
    ProteoformArtifactEvidenceLedger,
    ProteoformArtifactEvidenceLedgerBinding,
    ProteoformArtifactFinding,
    ProteoformArtifactFindingAction,
    ProteoformArtifactObservationState,
    ProteoformArtifactPosterior,
    ProteoformArtifactPosteriorState,
    ProteoformContaminationFlag,
    ProteoformEvidenceUnitKind,
    ProteoformExclusionMaskEntry,
    artifact_evidence_index,
    canonical_request_digest,
    configuration_digest,
    contract_json_schemas,
    evidence_ledger_digest,
    expected_detection_bundle,
    expected_result_id,
    matching_artifact_profile,
    normalized_request,
    normalized_result,
    policy_digest,
    receipt_digest,
    result_payload_digest,
)
from glio_proteogen.contracts.m04_05 import v1 as m0405_v1
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ConsentState, UpstreamDecisionState

_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SCHEMA_NAMES: Final = (
    "request",
    "output",
    "policy",
    "threshold",
    "profile",
    "evidence-event",
    "evidence-ledger",
    "evidence-ledger-binding",
    "artifact-posterior",
    "contamination-flag",
    "exclusion-mask-entry",
    "finding",
    "receipt",
)


@pytest.fixture(scope="module")
def canonical_request() -> DetectProteoformArtifactsRequest:
    return build_scenario_request()


@pytest.fixture(scope="module")
def canonical_result() -> ProteoformArtifactDetectionResult:
    return build_scenario_result()


def _reseal_result(
    result: ProteoformArtifactDetectionResult,
    **updates: object,
) -> dict[str, object]:
    payload = result.model_dump(mode="python", exclude_none=False)
    payload.update(updates)
    payload["result_digest"] = _ZERO_DIGEST
    provisional = result.model_copy(update={**updates, "result_digest": _ZERO_DIGEST}, deep=True)
    payload["result_digest"] = result_payload_digest(provisional)
    return payload


def _validate[ModelT: BaseModel](model: ModelT, **updates: object) -> ModelT:
    payload = model.model_dump(mode="python", exclude_none=False)
    payload.update(updates)
    return type(model).model_validate(payload, strict=True)


def _resealed_receipt(
    result: ProteoformArtifactDetectionResult,
    **updates: object,
) -> dict[str, object]:
    payload = result.receipt.model_dump(mode="python", exclude_none=False)
    payload.update(updates)
    payload["receipt_digest"] = _ZERO_DIGEST
    payload["receipt_digest"] = receipt_digest(payload)
    return payload


def _resealed_result_payload(
    result: ProteoformArtifactDetectionResult,
    **updates: object,
) -> dict[str, object]:
    payload = result.model_dump(mode="python", exclude_none=False)
    payload.update(updates)
    payload["result_digest"] = _ZERO_DIGEST
    payload["result_digest"] = result_payload_digest(payload)
    return payload


def test_exact_schema_inventory_and_authority_metadata() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == _SCHEMA_NAMES
    assert all(
        schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        for schema in schemas.values()
    )
    assert all(cast("str", schema["$id"]).endswith(f":{name}") for name, schema in schemas.items())
    metadata = cast("dict[str, object]", schemas["request"]["x-glio-contract"])
    assert metadata["rateScale"] == M0405_RATE_SCALE
    assert metadata["parentTarget"] == M0405_PARENT
    assert metadata["aggregateEvidenceOnly"] is True
    assert metadata["openSetAbstention"] is True
    assert metadata["externalContentTraversal"] is False
    assert metadata["calibratedProbability"] is False
    assert metadata["identityInference"] is False
    assert metadata["kinaseActivityInference"] is False
    assert metadata["allOmicsFusion"] is False
    assert metadata["treatmentRecommendation"] is False


def test_public_bundle_rederives_every_result_region(
    canonical_request: DetectProteoformArtifactsRequest,
    canonical_result: ProteoformArtifactDetectionResult,
) -> None:
    bundle = expected_detection_bundle(canonical_request)
    assert canonical_result.result_id == expected_result_id(canonical_request)
    assert canonical_result.request_digest == canonical_request_digest(canonical_request)
    assert canonical_result.policy_digest == policy_digest(canonical_request.policy)
    assert canonical_result.configuration_digest == configuration_digest(canonical_request.policy)
    assert canonical_result.artifact_posteriors == bundle.artifact_posteriors
    assert canonical_result.contamination_flags == bundle.contamination_flags
    assert canonical_result.exclusion_mask == bundle.exclusion_mask
    assert canonical_result.findings == bundle.findings
    assert canonical_result.disposition is bundle.disposition
    assert canonical_result.receipt == bundle.receipt
    assert canonical_result.support == bundle.support
    assert canonical_result.uncertainty == bundle.uncertainty
    assert canonical_result.provenance == bundle.provenance
    assert canonical_result.evidence == bundle.evidence
    assert canonical_result.limitations == bundle.limitations
    assert canonical_result.human_review_required is bundle.human_review_required
    assert canonical_result.completed_at == canonical_request.context.occurred_at
    assert canonical_result.result_digest == result_payload_digest(canonical_result)


def test_canonical_clear_is_explicit_not_absence_as_negative(
    canonical_result: ProteoformArtifactDetectionResult,
) -> None:
    assert canonical_result.disposition is ProteoformArtifactDisposition.CLEARED
    assert len(canonical_result.artifact_posteriors) == M0405_DETECTOR_CLASS_COUNT
    assert canonical_result.contamination_flags == ()
    assert canonical_result.exclusion_mask == ()
    assert {item.state for item in canonical_result.artifact_posteriors} == {
        ProteoformArtifactPosteriorState.CLEAR
    }
    assert all(
        item.observation_state is ProteoformArtifactObservationState.OBSERVED
        and item.posterior_ppm == 0
        and item.score_is_calibrated_probability is False
        and item.evidence[0].claim == M0405_EVIDENCE_CLAIM
        for item in canonical_result.artifact_posteriors
    )


def test_normalizers_and_strict_json_replay_are_idempotent(
    canonical_request: DetectProteoformArtifactsRequest,
    canonical_result: ProteoformArtifactDetectionResult,
) -> None:
    assert normalized_request(normalized_request(canonical_request)) == normalized_request(
        canonical_request
    )
    assert normalized_result(normalized_result(canonical_result)) == normalized_result(
        canonical_result
    )
    replay = ProteoformArtifactDetectionResult.model_validate_json(
        canonical_json_bytes(normalized_result(canonical_result)), strict=True
    )
    assert replay == canonical_result


def test_event_reordering_is_canonical_and_deterministic(
    canonical_request: DetectProteoformArtifactsRequest,
    canonical_result: ProteoformArtifactDetectionResult,
) -> None:
    ledger = canonical_request.evidence_ledger
    assert type(ledger) is ProteoformArtifactEvidenceLedger
    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    payload["evidence_ledger"]["events"] = tuple(reversed(ledger.events))  # type: ignore[index]
    replay = DetectProteoformArtifactsRequest.model_validate(payload, strict=True)
    assert replay == canonical_request
    assert build_scenario_result() == canonical_result


def test_profile_matches_both_upstream_version_and_configuration() -> None:
    supported = build_scenario_request()
    unsupported_version = build_scenario_request("unsupported_profile")
    unsupported_configuration = build_scenario_request("unsupported_configuration")
    assert matching_artifact_profile(supported) is not None
    assert matching_artifact_profile(unsupported_version) is None
    assert matching_artifact_profile(unsupported_configuration) is None
    result = build_scenario_result("unsupported_configuration")
    assert result.disposition is ProteoformArtifactDisposition.ABSTAINED
    assert result.artifact_posteriors == result.contamination_flags == result.exclusion_mask == ()
    assert result.human_review_required


def test_request_closes_operation_identity_chronology_and_traversal_envelope(
    canonical_request: DetectProteoformArtifactsRequest,
) -> None:
    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    payload["request_id"] = "request." + ("1" * 64)
    with pytest.raises(ValidationError, match="must equal authorized context"):
        DetectProteoformArtifactsRequest.model_validate(payload, strict=True)

    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    payload["operation"] = "infer_proteoform"
    with pytest.raises(ValidationError):
        DetectProteoformArtifactsRequest.model_validate(payload, strict=True)

    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    payload["context"]["occurred_at"] = canonical_request.quality_result.completed_at - timedelta(
        seconds=1
    )  # type: ignore[index]
    with pytest.raises(ValidationError, match="cannot postdate"):
        DetectProteoformArtifactsRequest.model_validate(payload, strict=True)

    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    payload["evidence_ledger"] = None
    with pytest.raises(ValidationError, match="traversal envelope"):
        DetectProteoformArtifactsRequest.model_validate(payload, strict=True)


@pytest.mark.parametrize("region", ["disposition", "review", "support", "completed_at"])
def test_resigned_derived_region_forgery_is_rejected(
    canonical_result: ProteoformArtifactDetectionResult,
    region: str,
) -> None:
    updates: dict[str, object] = {
        "disposition": {"disposition": ProteoformArtifactDisposition.ABSTAINED},
        "review": {"human_review_required": True},
        "support": {
            "support": canonical_result.support.model_copy(
                update={"rationale": "A valid but forged support rationale."}
            )
        },
        "completed_at": {"completed_at": canonical_result.completed_at + timedelta(seconds=1)},
    }[region]
    forged = _reseal_result(canonical_result, **updates)
    with pytest.raises(ValidationError, match=r"deriv|completion"):
        ProteoformArtifactDetectionResult.model_validate(forged, strict=True)


def test_evidence_index_is_exact_and_identity_consistent(
    canonical_request: DetectProteoformArtifactsRequest,
    canonical_result: ProteoformArtifactDetectionResult,
) -> None:
    assert artifact_evidence_index(canonical_request) == canonical_result.evidence
    assert len(canonical_result.evidence) == M0405_MAX_EVIDENCE
    identities: dict[str, tuple[str, str, str]] = {}
    for item in canonical_result.evidence:
        identity = (
            item.reference.version,
            item.reference.digest,
            item.reference.media_type,
        )
        assert identities.setdefault(item.reference.artifact_id, identity) == identity
    assert sha256_digest(normalized_request(canonical_request)) == canonical_request_digest(
        canonical_request
    )


def test_policy_profile_threshold_and_owned_evidence_negative_closure(
    canonical_request: DetectProteoformArtifactsRequest,
) -> None:
    policy = canonical_request.policy
    profile = policy.profiles[0]
    threshold = profile.thresholds[0]

    with pytest.raises(ValidationError, match="review threshold cannot exceed"):
        _validate(
            threshold,
            review_threshold_ppm=threshold.exclusion_threshold_ppm + 1,
        )
    with pytest.raises(ValidationError, match="exact owned media type"):
        _validate(
            threshold,
            evidence=threshold.evidence.model_copy(update={"media_type": "application/json"}),
        )
    with pytest.raises(ValidationError, match="versions must be unique"):
        _validate(
            profile,
            approved_quality_contract_versions=(
                profile.approved_quality_contract_versions[0],
                profile.approved_quality_contract_versions[0],
            ),
        )
    with pytest.raises(ValidationError, match="configuration digests must be unique"):
        _validate(
            profile,
            approved_quality_configuration_digests=(
                profile.approved_quality_configuration_digests[0],
                profile.approved_quality_configuration_digests[0],
            ),
        )
    repeated_class = profile.thresholds[0].model_copy(
        update={"detector_class": profile.thresholds[1].detector_class}
    )
    with pytest.raises(ValidationError, match="every detector class exactly once"):
        _validate(profile, thresholds=(repeated_class, *profile.thresholds[1:]))

    with pytest.raises(ValidationError, match="profile identities must be unique"):
        _validate(policy, profiles=(profile, profile))
    overlapping_profile = profile.model_copy(update={"profile_id": "profile." + ("a" * 64)})
    with pytest.raises(ValidationError, match="domains must be disjoint"):
        _validate(policy, profiles=(profile, overlapping_profile))


def test_event_ledger_binding_and_identity_negative_closure(
    canonical_request: DetectProteoformArtifactsRequest,
) -> None:
    ledger = canonical_request.evidence_ledger
    assert type(ledger) is ProteoformArtifactEvidenceLedger
    event = ledger.events[0]

    with pytest.raises(ValidationError, match="supporting count cannot exceed"):
        _validate(event, supporting_count=event.evaluated_count + 1)
    with pytest.raises(ValidationError, match="only observed events"):
        _validate(event, observation_state=ProteoformArtifactObservationState.MISSING)

    shifted = tuple(
        item.model_copy(update={"sequence": item.sequence + 1}) for item in ledger.events
    )
    with pytest.raises(ValidationError, match="sequence must be contiguous"):
        _validate(ledger, events=shifted)
    duplicate_event = ledger.events[1].model_copy(update={"event_id": ledger.events[0].event_id})
    with pytest.raises(ValidationError, match="event identifiers must be unique"):
        _validate(ledger, events=(ledger.events[0], duplicate_event, *ledger.events[2:]))
    duplicate_pair = ledger.events[1].model_copy(
        update={
            "target_id": ledger.events[0].target_id,
            "detector_class": ledger.events[0].detector_class,
        }
    )
    with pytest.raises(ValidationError, match="event pairs must be unique"):
        _validate(ledger, events=(ledger.events[0], duplicate_pair, *ledger.events[2:]))
    second_target = ledger.events[0].model_copy(update={"target_id": "target." + ("b" * 64)})
    with pytest.raises(ValidationError, match="requires all seven detector classes"):
        _validate(ledger, events=(second_target, *ledger.events[1:]))
    changed_unit = ledger.events[0].model_copy(
        update={"unit_kind": ProteoformEvidenceUnitKind.PEPTIDE_FEATURE}
    )
    with pytest.raises(ValidationError, match="cannot change evidence-unit kind"):
        _validate(ledger, events=(changed_unit, *ledger.events[1:]))

    stale_ledger = build_scenario_request("binding_mismatch").evidence_ledger
    assert type(stale_ledger) is ProteoformArtifactEvidenceLedger
    stale = ProteoformArtifactEvidenceLedgerBinding.model_validate(
        stale_ledger.model_dump(
            mode="python",
            include={
                "ledger_id",
                "version",
                "quality_result_digest",
                "recorded_at",
                "ledger_digest",
                "evidence",
            },
        ),
        strict=True,
    )
    with pytest.raises(ValidationError, match="final caller-declared digest"):
        _validate(stale, ledger_digest=_ZERO_DIGEST)

    conflicting = canonical_request.model_dump(mode="python", exclude_none=False)
    policy_evidence = conflicting["policy"]["evidence"]  # type: ignore[index]
    event_evidence = conflicting["evidence_ledger"]["events"][0]["evidence"][0]  # type: ignore[index]
    event_evidence["artifact_id"] = policy_evidence["artifact_id"]
    event_evidence["version"] = policy_evidence["version"]
    conflicting["evidence_ledger"]["ledger_digest"] = evidence_ledger_digest(  # type: ignore[index]
        conflicting["evidence_ledger"]  # type: ignore[index]
    )
    with pytest.raises(ValidationError, match="conflicting content"):
        DetectProteoformArtifactsRequest.model_validate(conflicting, strict=True)


def test_posterior_flag_mask_and_finding_negative_closure() -> None:
    clear = build_scenario_result()
    posterior = clear.artifact_posteriors[0]
    assert type(posterior) is ProteoformArtifactPosterior

    with pytest.raises(ValidationError, match="requires a score and interval"):
        _validate(posterior, posterior_ppm=None)
    with pytest.raises(ValidationError, match="cannot be indeterminate"):
        _validate(posterior, state=ProteoformArtifactPosteriorState.INDETERMINATE)
    with pytest.raises(ValidationError, match="interval must contain"):
        _validate(posterior, lower_bound_ppm=posterior.posterior_ppm + 1)  # type: ignore[operator]
    missing = next(
        item
        for item in build_scenario_result("missing_mapping").artifact_posteriors
        if item.observation_state is ProteoformArtifactObservationState.MISSING
    )
    with pytest.raises(ValidationError, match="scoreless and indeterminate"):
        _validate(missing, posterior_ppm=0)
    with pytest.raises(ValidationError, match="digest does not bind"):
        _validate(posterior, posterior_digest=sha256_digest("forged-posterior"))

    contaminated = build_scenario_result("critical_contamination")
    flag = contaminated.contamination_flags[0]
    assert type(flag) is ProteoformContaminationFlag
    with pytest.raises(ValidationError, match="only contamination detector classes"):
        _validate(flag, detector_class=ProteoformArtifactDetectorClass.TECHNICAL_ARTIFACT)

    entry = contaminated.exclusion_mask[0]
    assert type(entry) is ProteoformExclusionMaskEntry
    duplicate_digest = entry.triggering_posterior_digests[0]
    with pytest.raises(ValidationError, match="trigger identifiers must be unique"):
        _validate(entry, triggering_posterior_digests=(duplicate_digest, duplicate_digest))

    finding = contaminated.findings[0]
    assert type(finding) is ProteoformArtifactFinding
    assert finding.target_ids
    with pytest.raises(ValidationError, match="finding values must be unique"):
        _validate(finding, target_ids=(finding.target_ids[0], finding.target_ids[0]))
    with pytest.raises(ValidationError, match="identifier does not bind"):
        _validate(finding, finding_id="finding.m0405." + ("f" * 64))
    wrong_action = (
        ProteoformArtifactFindingAction.ABSTAIN
        if finding.action is not ProteoformArtifactFindingAction.ABSTAIN
        else ProteoformArtifactFindingAction.QUARANTINE
    )
    with pytest.raises(ValidationError, match="action contradicts"):
        _validate(finding, action=wrong_action)
    with pytest.raises(ValidationError, match="message contradicts"):
        _validate(finding, message="Valid but forged finding message.")


def test_receipt_collection_shape_and_digest_negative_closure() -> None:
    result = build_scenario_result("critical_contamination")
    receipt = result.receipt

    duplicate_event = receipt.event_digests[0]
    with pytest.raises(ValidationError, match="receipt collections must be unique"):
        _validate(receipt, event_digests=(duplicate_event, duplicate_event))

    mismatched = _resealed_receipt(
        result,
        posterior_digests=receipt.posterior_digests[:-1],
    )
    with pytest.raises(ValidationError, match="every traversed event"):
        type(receipt).model_validate(mismatched, strict=True)

    no_ledger = _resealed_receipt(result, evidence_ledger_digest=None)
    with pytest.raises(ValidationError, match="safe-failure receipt"):
        type(receipt).model_validate(no_ledger, strict=True)

    no_profile = _resealed_receipt(result, selected_profile_digest=None)
    with pytest.raises(ValidationError, match="requires one selected profile"):
        type(receipt).model_validate(no_profile, strict=True)

    with pytest.raises(ValidationError, match="receipt digest does not bind"):
        _validate(receipt, receipt_digest=sha256_digest("forged-receipt"))


@pytest.mark.parametrize(
    "field",
    [
        "request_digest",
        "policy_digest",
        "configuration_digest",
        "receipt_digest",
        "result_digest",
    ],
)
def test_result_envelope_digest_regions_reject_resigned_substitution(
    canonical_result: ProteoformArtifactDetectionResult,
    field: str,
) -> None:
    payload = canonical_result.model_dump(mode="python", exclude_none=False)
    payload[field] = sha256_digest({"forged": field})
    if field != "result_digest":
        payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError, match=r"digest is stale|digest does not bind"):
        ProteoformArtifactDetectionResult.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("quality_result_digest", "does not bind M04-04"),
        ("identity_resolution_digest", "identity-resolution binding"),
    ],
)
def test_result_receipt_authority_bindings_reject_resigned_substitution(
    canonical_result: ProteoformArtifactDetectionResult,
    field: str,
    message: str,
) -> None:
    receipt = _resealed_receipt(
        canonical_result,
        **{field: sha256_digest({"forged": field})},
    )
    payload = _resealed_result_payload(
        canonical_result,
        receipt=receipt,
        receipt_digest=receipt["receipt_digest"],
    )
    with pytest.raises(ValidationError, match=message):
        ProteoformArtifactDetectionResult.model_validate(payload, strict=True)


def test_result_posterior_flag_and_mask_cross_reference_closure() -> None:
    clear = build_scenario_result()
    duplicate_posteriors = (
        clear.artifact_posteriors[0],
        clear.artifact_posteriors[0],
        *clear.artifact_posteriors[1:],
    )
    payload = _resealed_result_payload(clear, artifact_posteriors=duplicate_posteriors)
    with pytest.raises(ValidationError, match="posterior digests must be unique"):
        ProteoformArtifactDetectionResult.model_validate(payload, strict=True)

    receipt = _resealed_receipt(
        clear,
        event_digests=clear.receipt.event_digests[:-1],
        posterior_digests=clear.receipt.posterior_digests[:-1],
    )
    payload = _resealed_result_payload(
        clear,
        receipt=receipt,
        receipt_digest=receipt["receipt_digest"],
    )
    with pytest.raises(ValidationError, match="posterior closure is incomplete"):
        ProteoformArtifactDetectionResult.model_validate(payload, strict=True)

    contaminated = build_scenario_result("critical_contamination")
    payload = _resealed_result_payload(
        contaminated,
        contamination_flags=(
            contaminated.contamination_flags[0],
            contaminated.contamination_flags[0],
        ),
    )
    with pytest.raises(ValidationError, match="flag identifiers must be unique"):
        ProteoformArtifactDetectionResult.model_validate(payload, strict=True)

    payload = _resealed_result_payload(
        contaminated,
        exclusion_mask=(contaminated.exclusion_mask[0], contaminated.exclusion_mask[0]),
    )
    with pytest.raises(ValidationError, match="each target only once"):
        ProteoformArtifactDetectionResult.model_validate(payload, strict=True)

    flags = list(contaminated.model_dump(mode="python")["contamination_flags"])
    flags[0] = deepcopy(flags[0])
    flags[0]["target_id"] = "target." + ("c" * 64)
    payload = _resealed_result_payload(contaminated, contamination_flags=tuple(flags))
    with pytest.raises(ValidationError, match="must bind one emitted posterior"):
        ProteoformArtifactDetectionResult.model_validate(payload, strict=True)

    mask = list(contaminated.model_dump(mode="python")["exclusion_mask"])
    mask[0] = deepcopy(mask[0])
    mask[0]["triggering_posterior_digests"] = (sha256_digest("unknown-posterior"),)
    payload = _resealed_result_payload(contaminated, exclusion_mask=tuple(mask))
    with pytest.raises(ValidationError, match="unknown posterior"):
        ProteoformArtifactDetectionResult.model_validate(payload, strict=True)

    mask = list(contaminated.model_dump(mode="python")["exclusion_mask"])
    mask[0] = deepcopy(mask[0])
    mask[0]["triggering_flag_ids"] = ("flag." + ("d" * 64),)
    payload = _resealed_result_payload(contaminated, exclusion_mask=tuple(mask))
    with pytest.raises(ValidationError, match="unknown contamination flag"):
        ProteoformArtifactDetectionResult.model_validate(payload, strict=True)


def test_result_size_and_generated_identifier_are_replayed_exactly(
    canonical_result: ProteoformArtifactDetectionResult,
) -> None:
    payload = canonical_result.model_dump(mode="python", exclude_none=False)
    with (
        patch.object(m0405_v1, "M0405_MAX_CANONICAL_RESULT_BYTES", 1),
        pytest.raises(ValidationError, match="result exceeds the installed ceiling"),
    ):
        ProteoformArtifactDetectionResult.model_validate(payload, strict=True)

    forged_id = _resealed_result_payload(
        canonical_result,
        result_id="result.m0405." + ("e" * 64),
    )
    with pytest.raises(ValidationError, match="identifier does not bind"):
        ProteoformArtifactDetectionResult.model_validate(forged_id, strict=True)


def test_request_authorization_and_verbatim_authority_closure(
    canonical_request: DetectProteoformArtifactsRequest,
) -> None:
    denied = canonical_request.model_dump(mode="python", exclude_none=False)
    denied["context"]["references"]["support"]["state"] = (  # type: ignore[index]
        UpstreamDecisionState.REJECTED
    )
    with pytest.raises(ValidationError, match="accepted and resolved upstream controls"):
        DetectProteoformArtifactsRequest.model_validate(denied, strict=True)

    withheld = canonical_request.model_dump(mode="python", exclude_none=False)
    withheld["context"]["references"]["consent"]["state"] = ConsentState.WITHHELD  # type: ignore[index]
    with pytest.raises(ValidationError, match="caller-declared granted consent"):
        DetectProteoformArtifactsRequest.model_validate(withheld, strict=True)

    for control, message in (
        ("identity_lineage", "identity-lineage authority"),
        ("consent", "consent authority"),
        ("provenance", "provenance authority"),
        ("support", "support authority"),
        ("intended_use", "intended-use authority"),
    ):
        altered = canonical_request.model_dump(mode="python", exclude_none=False)
        altered["context"]["references"][control]["policy_version"] = "1.0.1"  # type: ignore[index]
        with pytest.raises(ValidationError, match=message):
            DetectProteoformArtifactsRequest.model_validate(altered, strict=True)


def test_request_quality_configuration_chronology_and_byte_ceiling_closure(
    canonical_request: DetectProteoformArtifactsRequest,
) -> None:
    stale_quality = canonical_request.model_dump(mode="python", exclude_none=False)
    stale_quality["context"]["references"]["quality"]["evidence"]["digest"] = (  # type: ignore[index]
        sha256_digest("stale-quality-binding")
    )
    with pytest.raises(ValidationError, match="quality authority evidence"):
        DetectProteoformArtifactsRequest.model_validate(stale_quality, strict=True)

    stale_configuration = canonical_request.model_dump(mode="python", exclude_none=False)
    stale_configuration["context"]["references"]["approved_configuration"]["evidence"][  # type: ignore[index]
        "digest"
    ] = sha256_digest("stale-configuration-binding")
    with pytest.raises(ValidationError, match="approved configuration must bind"):
        DetectProteoformArtifactsRequest.model_validate(stale_configuration, strict=True)

    stale_ledger = canonical_request.model_dump(mode="python", exclude_none=False)
    stale_ledger["evidence_ledger"]["recorded_at"] = (  # type: ignore[index]
        canonical_request.quality_result.completed_at - timedelta(seconds=1)
    )
    stale_ledger["evidence_ledger"]["ledger_digest"] = evidence_ledger_digest(  # type: ignore[index]
        stale_ledger["evidence_ledger"]  # type: ignore[index]
    )
    with pytest.raises(ValidationError, match="events must follow M04-04"):
        DetectProteoformArtifactsRequest.model_validate(stale_ledger, strict=True)

    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    with (
        patch.object(m0405_v1, "M0405_MAX_CANONICAL_REQUEST_BYTES", 1),
        pytest.raises(ValidationError, match="request exceeds the installed ceiling"),
    ):
        DetectProteoformArtifactsRequest.model_validate(payload, strict=True)
