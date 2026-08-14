"""Contract, derivation, and replay closure for M04-05 artifact detection."""

from __future__ import annotations

from datetime import timedelta
from typing import Final, cast

import pytest
from evals.m04_05.run import build_scenario_request, build_scenario_result
from pydantic import ValidationError

from glio_proteogen.contracts.m04_05 import (
    M0405_DETECTOR_CLASS_COUNT,
    M0405_EVIDENCE_CLAIM,
    M0405_MAX_EVIDENCE,
    M0405_PARENT,
    M0405_RATE_SCALE,
    DetectProteoformArtifactsRequest,
    ProteoformArtifactDetectionResult,
    ProteoformArtifactDisposition,
    ProteoformArtifactEvidenceLedger,
    ProteoformArtifactObservationState,
    ProteoformArtifactPosteriorState,
    artifact_evidence_index,
    canonical_request_digest,
    configuration_digest,
    contract_json_schemas,
    expected_detection_bundle,
    expected_result_id,
    matching_artifact_profile,
    normalized_request,
    normalized_result,
    policy_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

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
