"""Numeric, ingress-size, and exclusion-firewall regressions for M02-06."""

from __future__ import annotations

from copy import deepcopy
from functools import cache
from typing import TYPE_CHECKING, Any

import pytest
from evals.m02_05.run import build_scenario_request as build_m0205_request
from evals.m02_06.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m02_05 import (
    ArtifactClass,
    IdentificationArtifactDetectionResult,
    signal_summary_digest_from_values,
)
from glio_proteogen.contracts.m02_06 import (
    M0206_MAX_CANONICAL_REQUEST_BYTES,
    M0206_MAX_INVARIANTS,
    M0206_MAX_OBSERVATIONS,
    M0206_MAX_STAGES,
    BiologicalControlInvariant,
    DiagnosticStatus,
    HarmonizationDisposition,
    HarmonizationValueState,
    HarmonizedIdentificationValue,
    HarmonizeIdentificationEvidenceRequest,
    IdentificationAbundanceObservation,
    IdentificationHarmonizationPolicy,
    IdentificationHarmonizationProfile,
    IdentificationHarmonizationResult,
    ShiftState,
    SourceObservationSummary,
    configuration_digest,
    contract_json_schema,
    invariant_digest,
    observation_summary_digest,
    policy_digest,
    profile_digest,
    request_manifest_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, EstimateState, ExecutionContext
from glio_proteogen.modules.c02_identification_qc.m02_05_artifact_detection import (
    detect_identification_artifacts,
)
from glio_proteogen.modules.c02_identification_qc.m02_06_harmonization import (
    harmonize_identification_evidence,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m02_06.schema import ContractName

pytestmark = pytest.mark.contract

_DECLARED_OBSERVATION_LIMIT = 2_048
_DECLARED_INVARIANT_LIMIT = 256
_DECLARED_SERIALIZED_LIMIT = 4_194_304
_DERIVED_DIGEST_SENTINEL = "sha256:" + ("0" * 64)
_FORMER_SENTINEL_TARGET = "m0206.no-eligible-control"
_SCHEMA_NAMES: tuple[ContractName, ...] = (
    "request",
    "output",
    "prerequisites",
    "profile",
    "policy",
    "observation",
    "value",
    "manifest",
)


@cache
def _request(case: str = "conformant_eight_factor") -> HarmonizeIdentificationEvidenceRequest:
    return build_scenario_request(case)


@cache
def _result() -> IdentificationHarmonizationResult:
    return harmonize_identification_evidence(_request())


@cache
def _typed_nonobserved_result() -> IdentificationHarmonizationResult:
    return harmonize_identification_evidence(_request("typed_nonobserved_states"))


def _rebind_full_result_configuration(payload: dict[str, Any]) -> None:
    """Rebind every exposed digest after a coherent embedded configuration mutation."""

    profile = IdentificationHarmonizationProfile.model_validate(payload["profile"])
    policy = IdentificationHarmonizationPolicy.model_validate(payload["policy"])
    controls = tuple(
        BiologicalControlInvariant.model_validate(item) for item in payload["biological_controls"]
    )
    old_configuration_digest = payload["configuration_digest"]
    rebound_profile_digest = profile_digest(profile)
    rebound_policy_digest = policy_digest(policy)
    rebound_configuration_digest = configuration_digest(profile, policy, controls)
    rebound_context_digest = sha256_digest(
        {
            "prior_context_digest": payload["context_digest"],
            "approved_configuration_digest": rebound_configuration_digest,
        }
    )
    payload["profile_digest"] = rebound_profile_digest
    payload["policy_digest"] = rebound_policy_digest
    payload["configuration_digest"] = rebound_configuration_digest
    payload["context_digest"] = rebound_context_digest
    manifest = payload["transformation_manifest"]
    manifest["profile_digest"] = rebound_profile_digest
    manifest["policy_digest"] = rebound_policy_digest
    manifest["configuration_digest"] = rebound_configuration_digest
    for reference in payload["evidence"]:
        if reference["reference"]["digest"] == old_configuration_digest:
            reference["reference"]["digest"] = rebound_configuration_digest
    provenance = payload["provenance"]
    provenance["configuration_digest"] = rebound_configuration_digest
    for decision in provenance["control_decisions"]:
        if decision["role"].value == "approved_configuration":
            decision["evidence_digest"] = rebound_configuration_digest
    rebound_request_digest = request_manifest_digest(
        active_context_digest=rebound_context_digest,
        active_prerequisites_digest=payload["prerequisites_digest"],
        active_profile_digest=rebound_profile_digest,
        active_policy_digest=rebound_policy_digest,
        observation_digests=tuple(item["source_observation_digest"] for item in payload["values"]),
        invariant_digests=tuple(invariant_digest(item) for item in controls),
        supersedes_result_digest=payload["supersedes_result_digest"],
    )
    payload["request_digest"] = rebound_request_digest
    suffix = rebound_request_digest.removeprefix("sha256:")
    payload["harmonization_id"] = f"harmonization.m0206.{suffix}"
    provenance["activity_id"] = f"activity.m0206.{suffix}"
    exact_inputs = {
        rebound_request_digest,
        rebound_context_digest,
        payload["prerequisites_digest"],
        rebound_profile_digest,
        rebound_policy_digest,
        rebound_configuration_digest,
        *(receipt["result_digest"] for receipt in payload["upstream_receipts"]),
        *(decision["evidence_digest"] for decision in provenance["control_decisions"]),
    }
    provenance["input_digests"] = tuple(sorted(exact_inputs))
    payload["result_digest"] = _DERIVED_DIGEST_SENTINEL


def _context_with_configuration(
    base: HarmonizeIdentificationEvidenceRequest,
    *,
    profile: IdentificationHarmonizationProfile,
    biological_controls: tuple[BiologicalControlInvariant, ...],
) -> ExecutionContext:
    references = base.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={
                    "digest": configuration_digest(
                        profile,
                        base.policy,
                        biological_controls,
                    )
                }
            )
        }
    )
    return base.context.model_copy(
        update={"references": references.model_copy(update={"approved_configuration": approved})}
    )


def _m0205_evidence(target_id: str, signal_id: str) -> ArtifactReference:
    label = f"{target_id}.{signal_id}"
    return ArtifactReference(
        artifact_id=f"artifact.m0206.exclusion.{label}",
        version="1.0.0",
        digest=sha256_digest({"m0206_exclusion_signal": label}),
        media_type="application/json",
    )


@cache
def _genuine_artifact_detection(
    excluded_target_ids: tuple[str, ...],
) -> IdentificationArtifactDetectionResult:
    seed = build_m0205_request("multi_class")
    templates = seed.signals[: len(ArtifactClass)]
    excluded = set(excluded_target_ids)
    targets = tuple(sorted({item.target_id for item in _request().observations}))
    exclusion_signal_ids = {
        "signal.m0205.contamination",
        "signal.m0205.barcode_index",
    }
    signals = tuple(
        template.model_copy(
            update={
                "target_id": target_id,
                "value": (
                    0.95
                    if target_id in excluded and template.signal_id in exclusion_signal_ids
                    else 0.1
                ),
                "evidence": (_m0205_evidence(target_id, template.signal_id),),
            }
        )
        for target_id in targets
        for template in templates
    )
    result = detect_identification_artifacts(seed.model_copy(update={"signals": signals}))
    assert set(result.evaluated_target_ids) == set(targets)
    assert set(result.exclusion_mask.excluded_target_ids) == excluded
    return result


def _request_with_genuine_exclusions(
    excluded_target_ids: tuple[str, ...],
) -> HarmonizeIdentificationEvidenceRequest:
    base = _request()
    prerequisites = base.prerequisites.model_copy(
        update={
            "artifact_detection": _genuine_artifact_detection(tuple(sorted(excluded_target_ids)))
        }
    )
    candidate = base.model_copy(update={"prerequisites": prerequisites})
    return HarmonizeIdentificationEvidenceRequest.model_validate(
        candidate.model_dump(mode="python")
    )


def test_raw_count_is_not_an_additive_harmonization_unit() -> None:
    payload = _request().observations[0].model_dump(mode="python")
    payload["unit"] = "raw_count"

    with pytest.raises(ValidationError) as caught:
        IdentificationAbundanceObservation.model_validate(payload)

    assert any(error["loc"] == ("unit",) for error in caught.value.errors())


@pytest.mark.parametrize("value", [1e308, -1e308])
def test_extreme_observed_values_fail_in_observation_and_request_validation(
    value: float,
) -> None:
    observation_payload = _request().observations[0].model_dump(mode="python")
    observation_payload["value"] = value
    with pytest.raises(ValidationError, match="supported numeric envelope"):
        IdentificationAbundanceObservation.model_validate(observation_payload)

    request_payload = _request().model_dump(mode="python")
    request_payload["observations"][0]["value"] = value
    with pytest.raises(ValidationError, match="supported numeric envelope"):
        HarmonizeIdentificationEvidenceRequest.model_validate(request_payload)


@pytest.mark.parametrize("limit", [1e308, -1e308])
def test_extreme_censoring_limits_fail_at_every_public_value_boundary(
    limit: float,
) -> None:
    request = _request("typed_nonobserved_states")
    censored_observation = next(
        item for item in request.observations if item.state is HarmonizationValueState.CENSORED
    )
    observation_payload = censored_observation.model_dump(mode="python")
    observation_payload["censoring_limit"] = limit
    with pytest.raises(ValidationError, match="supported numeric envelope"):
        IdentificationAbundanceObservation.model_validate(observation_payload)

    request_payload = request.model_dump(mode="python")
    nested_observation = next(
        item
        for item in request_payload["observations"]
        if item["state"] is HarmonizationValueState.CENSORED
    )
    nested_observation["censoring_limit"] = limit
    with pytest.raises(ValidationError, match="supported numeric envelope"):
        HarmonizeIdentificationEvidenceRequest.model_validate(request_payload)

    result = harmonize_identification_evidence(request)
    censored_value = next(
        item for item in result.values if item.input_state is HarmonizationValueState.CENSORED
    )
    summary_payload = censored_value.source_observation.model_dump(mode="python")
    summary_payload["censoring_limit"] = limit
    with pytest.raises(ValidationError, match="supported numeric envelope"):
        SourceObservationSummary.model_validate(summary_payload)

    value_payload = censored_value.model_dump(mode="python")
    value_payload["source_observation"]["censoring_limit"] = limit
    with pytest.raises(ValidationError, match="supported numeric envelope"):
        HarmonizedIdentificationValue.model_validate(value_payload)


def test_excluded_only_levels_are_absent_from_active_result_semantics() -> None:
    baseline_request = _request("upstream_excluded_target")
    excluded_targets = set(
        baseline_request.prerequisites.artifact_detection.exclusion_mask.excluded_target_ids
    )
    assert excluded_targets

    payload = baseline_request.model_dump(mode="python")
    excluded_only_levels: set[str] = set()
    for observation in payload["observations"]:
        if observation["target_id"] not in excluded_targets:
            continue
        for level in observation["factor_levels"]:
            factor = str(level["factor"])
            level_id = f"level.m0206.{factor}.excluded_only"
            level["level_id"] = level_id
            excluded_only_levels.add(level_id)

    variant_request = HarmonizeIdentificationEvidenceRequest.model_validate(payload)
    baseline = harmonize_identification_evidence(baseline_request)
    variant = harmonize_identification_evidence(variant_request)

    baseline_active_values = tuple(
        item for item in baseline.values if item.sample_id not in excluded_targets
    )
    variant_active_values = tuple(
        item for item in variant.values if item.sample_id not in excluded_targets
    )
    assert variant_active_values == baseline_active_values
    assert variant.transformation_manifest == baseline.transformation_manifest
    assert variant.technical_effect_diagnostics == baseline.technical_effect_diagnostics
    assert variant.biological_invariant_diagnostics == baseline.biological_invariant_diagnostics
    assert variant.disposition is baseline.disposition
    assert variant.support == baseline.support
    assert variant.uncertainty == baseline.uncertainty
    assert variant.human_review_required is baseline.human_review_required

    active_manifest_levels = {
        shift.level_id
        for stage in variant.transformation_manifest.stages
        for shift in stage.level_shifts
    }
    assert excluded_only_levels.isdisjoint(active_manifest_levels)


def test_one_active_level_from_genuine_m0205_exclusions_completes_typed() -> None:
    base = _request()
    single_level_stage = next(
        stage for stage in base.profile.stages if stage.factor.value == "purity"
    )
    excluded_targets = tuple(
        sorted(
            {
                observation.target_id
                for observation in base.observations
                if next(
                    level.level_id
                    for level in observation.factor_levels
                    if level.factor is single_level_stage.factor
                )
                != single_level_stage.reference_level_id
            }
        )
    )
    assert excluded_targets
    request = _request_with_genuine_exclusions(excluded_targets)
    baseline = harmonize_identification_evidence(request)

    variant_payload = request.model_dump(mode="python")
    excluded = set(excluded_targets)
    for observation in variant_payload["observations"]:
        if observation["target_id"] not in excluded:
            continue
        for level in observation["factor_levels"]:
            factor = level["factor"].value
            level["level_id"] = f"level.m0206.{factor}.excluded.{observation['target_id']}"
    variant_request = HarmonizeIdentificationEvidenceRequest.model_validate(variant_payload)
    variant = harmonize_identification_evidence(variant_request)

    for result in (baseline, variant):
        excluded_values = tuple(item for item in result.values if item.sample_id in excluded)
        assert excluded_values
        assert all(
            item.output_state is HarmonizationValueState.EXCLUDED
            and item.harmonized_value is None
            and not item.applied_adjustments
            for item in excluded_values
        )
        single_level_diagnostic = next(
            item
            for item in result.technical_effect_diagnostics
            if item.factor is single_level_stage.factor
        )
        assert single_level_diagnostic.status is DiagnosticStatus.NOT_EVALUABLE
        assert result.disposition is HarmonizationDisposition.ABSTAINED

    baseline_active = tuple(item for item in baseline.values if item.sample_id not in excluded)
    variant_active = tuple(item for item in variant.values if item.sample_id not in excluded)
    assert baseline_active == variant_active
    assert baseline.technical_effect_diagnostics == variant.technical_effect_diagnostics
    assert baseline.biological_invariant_diagnostics == (variant.biological_invariant_diagnostics)
    assert tuple(
        (stage.input_digest, stage.output_digest)
        for stage in baseline.transformation_manifest.stages
    ) == tuple(
        (stage.input_digest, stage.output_digest)
        for stage in variant.transformation_manifest.stages
    )


def test_all_targets_excluded_by_genuine_m0205_result_completes_typed() -> None:
    target_ids = tuple(sorted({item.target_id for item in _request().observations}))
    request = _request_with_genuine_exclusions(target_ids)

    result = harmonize_identification_evidence(request)

    assert len(result.transformation_manifest.stages) == M0206_MAX_STAGES
    assert len(result.values) == len(request.observations)
    assert all(
        item.output_state is HarmonizationValueState.EXCLUDED
        and item.harmonized_value is None
        and item.censoring_limit is None
        and not item.applied_adjustments
        for item in result.values
    )
    assert all(
        not stage.control_target_ids
        and all(shift.state is ShiftState.NOT_EVALUABLE for shift in stage.level_shifts)
        for stage in result.transformation_manifest.stages
    )
    assert all(
        item.status is DiagnosticStatus.NOT_EVALUABLE
        for item in result.technical_effect_diagnostics
    )
    assert all(
        item.status is DiagnosticStatus.NOT_EVALUABLE
        for item in result.biological_invariant_diagnostics
    )
    assert result.disposition is HarmonizationDisposition.ABSTAINED


def test_declared_observation_cap_rejects_2049_items_and_is_in_schema() -> None:
    assert M0206_MAX_OBSERVATIONS == _DECLARED_OBSERVATION_LIMIT
    schema = contract_json_schema("request")
    properties = schema["properties"]
    definitions = schema["$defs"]
    assert isinstance(properties, dict)
    assert isinstance(definitions, dict)
    assert properties["observations"]["maxItems"] == M0206_MAX_OBSERVATIONS
    policy_schema = definitions["IdentificationHarmonizationPolicy"]
    assert policy_schema["properties"]["max_observations"]["maximum"] == (M0206_MAX_OBSERVATIONS)

    base = _request()
    template = base.observations[0]
    additional_count = (M0206_MAX_OBSERVATIONS + 1) - len(base.observations)
    observations = base.observations + tuple(
        template.model_copy(update={"feature_id": f"feature.limit.{index:04d}"})
        for index in range(additional_count)
    )
    payload = base.model_dump(mode="python")
    payload["observations"] = observations

    with pytest.raises(ValidationError) as caught:
        HarmonizeIdentificationEvidenceRequest.model_validate(payload)

    assert any(
        error["loc"] == ("observations",) and error["type"] == "too_long"
        for error in caught.value.errors()
    )


def test_oversized_canonical_request_is_rejected_and_limit_is_advertised() -> None:
    assert M0206_MAX_CANONICAL_REQUEST_BYTES == _DECLARED_SERIALIZED_LIMIT
    request_metadata = contract_json_schema("request")["x-glio-contract"]
    assert isinstance(request_metadata, dict)
    assert request_metadata["maxRequestBytes"] == M0206_MAX_CANONICAL_REQUEST_BYTES
    for name in _SCHEMA_NAMES:
        if name == "request":
            continue
        metadata = contract_json_schema(name)["x-glio-contract"]
        assert isinstance(metadata, dict)
        assert "maxRequestBytes" not in metadata

    media_type = "application/x.m0206." + ("x" * (512 - len("application/x.m0206.")))
    evidence = tuple(
        ArtifactReference(
            artifact_id=f"artifact.m0206.oversize.{index:02d}",
            version="1.0.0",
            digest=f"sha256:{index:064x}",
            media_type=media_type,
        )
        for index in range(64)
    )
    base = _request()
    observations = tuple(
        item.model_copy(update={"evidence": evidence}) for item in base.observations
    )
    oversized = base.model_copy(update={"observations": observations})
    assert len(canonical_json_bytes(oversized)) > M0206_MAX_CANONICAL_REQUEST_BYTES

    with pytest.raises(ValidationError, match="canonical request exceeds"):
        HarmonizeIdentificationEvidenceRequest.model_validate(oversized.model_dump(mode="python"))


@cache
def _exact_capacity_request() -> HarmonizeIdentificationEvidenceRequest:
    base = _request()
    controls = tuple(
        base.biological_controls[index % len(base.biological_controls)].model_copy(
            update={"invariant_id": f"invariant.m0206.capacity.{index:03d}"}
        )
        for index in range(M0206_MAX_INVARIANTS)
    )
    template = base.observations[0]
    observations = base.observations + tuple(
        template.model_copy(update={"feature_id": f"feature.capacity.{index:04d}"})
        for index in range(M0206_MAX_OBSERVATIONS - len(base.observations))
    )
    context = _context_with_configuration(
        base,
        profile=base.profile,
        biological_controls=controls,
    )
    candidate = base.model_copy(
        update={
            "context": context,
            "observations": observations,
            "biological_controls": controls,
        }
    )
    return HarmonizeIdentificationEvidenceRequest.model_validate(
        candidate.model_dump(mode="python")
    )


def test_exact_declared_maximum_executes_all_stages_and_invariants() -> None:
    assert M0206_MAX_OBSERVATIONS == _DECLARED_OBSERVATION_LIMIT
    assert M0206_MAX_INVARIANTS == _DECLARED_INVARIANT_LIMIT
    request = _exact_capacity_request()
    assert len(request.observations) == M0206_MAX_OBSERVATIONS
    assert len(request.biological_controls) == M0206_MAX_INVARIANTS
    assert len(canonical_json_bytes(request)) <= M0206_MAX_CANONICAL_REQUEST_BYTES

    result = harmonize_identification_evidence(request)

    assert len(result.values) == M0206_MAX_OBSERVATIONS
    assert len(result.transformation_manifest.stages) == M0206_MAX_STAGES
    assert len(result.technical_effect_diagnostics) == M0206_MAX_STAGES
    assert len(result.biological_invariant_diagnostics) == M0206_MAX_INVARIANTS
    assert all(
        diagnostic.status is DiagnosticStatus.PASSED
        for diagnostic in result.technical_effect_diagnostics
    )
    assert all(
        diagnostic.status is DiagnosticStatus.PASSED
        for diagnostic in result.biological_invariant_diagnostics
    )
    assert result.disposition is HarmonizationDisposition.ACCEPTED


def _artifact_detection_with_public_collision_target(
    source: IdentificationArtifactDetectionResult,
) -> IdentificationArtifactDetectionResult:
    payload = source.model_dump(mode="python")
    source_target = "sample.000"
    cloned_flags: list[dict[str, Any]] = []
    for source_flag in payload["flags"]:
        if source_flag["target_id"] != source_target:
            continue
        flag = deepcopy(source_flag)
        flag["target_id"] = _FORMER_SENTINEL_TARGET
        for trace in flag["evaluations"]:
            trace["target_id"] = _FORMER_SENTINEL_TARGET
            trace["signal_digest"] = signal_summary_digest_from_values(
                (
                    _FORMER_SENTINEL_TARGET,
                    trace["signal_id"],
                    str(trace["signal_state"]),
                    trace["signal_value"],
                    trace["signal_unit"],
                ),
                trace["evidence_digests"],
            )
        flag["provenance"]["signal_digests"] = tuple(
            sorted(
                trace["signal_digest"]
                for trace in flag["evaluations"]
                if trace["signal_digest"] is not None
            )
        )
        cloned_flags.append(flag)
    assert cloned_flags
    payload["evaluated_target_ids"] = (
        *payload["evaluated_target_ids"],
        _FORMER_SENTINEL_TARGET,
    )
    payload["flags"] = (*payload["flags"], *cloned_flags)
    payload["result_digest"] = _DERIVED_DIGEST_SENTINEL
    return IdentificationArtifactDetectionResult.model_validate(payload)


def test_former_internal_sentinel_is_a_safe_public_target_with_no_controls() -> None:
    base = _request("upstream_excluded_target")
    excluded_target = base.prerequisites.artifact_detection.exclusion_mask.excluded_target_ids[0]
    artifact_detection = _artifact_detection_with_public_collision_target(
        base.prerequisites.artifact_detection
    )
    prerequisites = base.prerequisites.model_copy(update={"artifact_detection": artifact_detection})
    observations = tuple(
        item.model_copy(update={"target_id": _FORMER_SENTINEL_TARGET})
        if item.target_id == "sample.000"
        else item
        for item in base.observations
    )
    profile = base.profile.model_copy(
        update={
            "stages": tuple(
                stage.model_copy(update={"control_target_ids": (excluded_target,)})
                for stage in base.profile.stages
            )
        }
    )
    context = _context_with_configuration(
        base,
        profile=profile,
        biological_controls=base.biological_controls,
    )
    candidate = base.model_copy(
        update={
            "context": context,
            "prerequisites": prerequisites,
            "profile": profile,
            "observations": observations,
        }
    )
    request = HarmonizeIdentificationEvidenceRequest.model_validate(
        candidate.model_dump(mode="python")
    )

    result = harmonize_identification_evidence(request)

    collision_values = tuple(
        item for item in result.values if item.sample_id == _FORMER_SENTINEL_TARGET
    )
    assert collision_values
    assert all(item.harmonized_value == item.input_value for item in collision_values)
    assert all(not item.applied_adjustments for item in collision_values)
    assert all(not stage.control_target_ids for stage in result.transformation_manifest.stages)
    assert all(
        shift.state is ShiftState.NOT_EVALUABLE
        for stage in result.transformation_manifest.stages
        for shift in stage.level_shifts
    )
    assert all(
        diagnostic.status is DiagnosticStatus.NOT_EVALUABLE
        for diagnostic in result.technical_effect_diagnostics
    )
    assert result.disposition is HarmonizationDisposition.ABSTAINED


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("limitation_statement", "requires both fixed limitations"),
        ("support_rationale", "support contradicts disposition"),
        ("evidence_role", "evidence claims exceed"),
        ("evidence_claim", "evidence claims exceed"),
        ("calibrated_uncertainty", "uncertainty must remain deterministic"),
    ],
)
def test_output_envelope_is_fixed_independently_of_result_digest(
    mutation: str,
    message: str,
) -> None:
    payload = deepcopy(_result().model_dump(mode="python"))
    payload["result_digest"] = _DERIVED_DIGEST_SENTINEL
    if mutation == "limitation_statement":
        payload["limitations"][0]["statement"] = "Broader interpretation is permitted."
    elif mutation == "support_rationale":
        payload["support"]["rationale"] = "Support is fully calibrated."
    elif mutation == "evidence_role":
        payload["evidence"][0]["role"] = "counter_evidence"
    elif mutation == "evidence_claim":
        payload["evidence"][0]["claim"] = "This evidence proves biological interpretation."
    else:
        payload["uncertainty"]["measurement"] = {
            "state": EstimateState.ESTIMATED,
            "probability": 0.99,
            "rationale": "Calibrated by this deterministic transformation.",
        }

    with pytest.raises(ValidationError, match=message):
        IdentificationHarmonizationResult.model_validate(payload)


@pytest.mark.parametrize("mutation", ["extra", "duplicate"])
def test_provenance_requires_the_exact_unique_input_digest_set(mutation: str) -> None:
    payload = deepcopy(_result().model_dump(mode="python"))
    payload["result_digest"] = _DERIVED_DIGEST_SENTINEL
    input_digests = payload["provenance"]["input_digests"]
    injected = "sha256:" + ("f" * 64) if mutation == "extra" else input_digests[0]
    payload["provenance"]["input_digests"] = (*input_digests, injected)

    with pytest.raises(ValidationError, match="exact unique input digest set"):
        IdentificationHarmonizationResult.model_validate(payload)


@pytest.mark.parametrize(
    ("capacity_field", "decrement_from"),
    [
        ("max_observations", "values"),
        ("max_invariants", "biological_controls"),
    ],
)
def test_full_result_reenforces_coherently_rebound_policy_capacity(
    capacity_field: str,
    decrement_from: str,
) -> None:
    payload = deepcopy(_result().model_dump(mode="python"))
    payload["policy"][capacity_field] = len(payload[decrement_from]) - 1
    _rebind_full_result_configuration(payload)

    with pytest.raises(
        ValidationError,
        match="result exceeds its embedded policy capacity",
    ):
        IdentificationHarmonizationResult.model_validate(payload)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("unknown_control_target", "profile references an unknown control target"),
        ("unknown_control_feature", "profile references an unknown control feature"),
        ("unknown_invariant_feature", "biological control references an unknown source member"),
        ("unknown_invariant_group", "biological control references an unknown source member"),
    ],
)
def test_coherently_rebound_full_result_rejects_unknown_configuration_members(
    mutation: str,
    message: str,
) -> None:
    payload = deepcopy(_result().model_dump(mode="python"))
    if mutation == "unknown_control_target":
        payload["profile"]["stages"][0]["control_target_ids"] = (
            *payload["profile"]["stages"][0]["control_target_ids"],
            "target.m0206.unknown",
        )
        payload["transformation_manifest"]["stages"][0]["control_target_ids"] = (
            *payload["transformation_manifest"]["stages"][0]["control_target_ids"],
            "target.m0206.unknown",
        )
    elif mutation == "unknown_control_feature":
        payload["profile"]["stages"][0]["control_feature_ids"] = (
            *payload["profile"]["stages"][0]["control_feature_ids"],
            "feature.m0206.unknown",
        )
        payload["transformation_manifest"]["stages"][0]["control_feature_ids"] = (
            *payload["transformation_manifest"]["stages"][0]["control_feature_ids"],
            "feature.m0206.unknown",
        )
    elif mutation == "unknown_invariant_feature":
        payload["biological_controls"][0]["feature_ids"] = ("feature.m0206.unknown",)
    else:
        payload["biological_controls"][0]["biological_group_ids"] = (
            "group.m0206.unknown",
            payload["biological_controls"][0]["biological_group_ids"][1],
        )
    _rebind_full_result_configuration(payload)

    with pytest.raises(ValidationError, match=message):
        IdentificationHarmonizationResult.model_validate(payload)


def test_all_excluded_output_still_requires_source_declared_reference_level() -> None:
    target_ids = tuple(sorted({item.target_id for item in _request().observations}))
    result = harmonize_identification_evidence(_request_with_genuine_exclusions(target_ids))
    assert all(item.output_state is HarmonizationValueState.EXCLUDED for item in result.values)
    payload = deepcopy(result.model_dump(mode="python"))
    profile_stage = payload["profile"]["stages"][0]
    manifest_stage = payload["transformation_manifest"]["stages"][0]
    forged_reference = "level.m0206.platform.never-declared"
    declared_source_levels = {
        level["level_id"]
        for item in payload["values"]
        for level in item["source_observation"]["factor_levels"]
        if level["factor"] is profile_stage["factor"]
    }
    assert forged_reference not in declared_source_levels
    profile_stage["reference_level_id"] = forged_reference
    manifest_stage["reference_level_id"] = forged_reference
    manifest_stage["level_shifts"] = (
        *manifest_stage["level_shifts"],
        {
            "level_id": forged_reference,
            "state": ShiftState.NOT_EVALUABLE,
            "estimated_shift": None,
            "applied_shift": None,
            "unit": result.values[0].unit,
            "control_count": 0,
        },
    )
    _rebind_full_result_configuration(payload)

    with pytest.raises(
        ValidationError,
        match="stage requires a source-declared reference and comparison level",
    ):
        IdentificationHarmonizationResult.model_validate(payload)


def test_output_rejects_coherently_rebound_nonobserved_factor_inconsistency() -> None:
    result = _typed_nonobserved_result()
    payload = deepcopy(result.model_dump(mode="python"))
    mutated = next(
        item
        for item in payload["values"]
        if item["input_state"] is not HarmonizationValueState.OBSERVED
        and sum(other["sample_id"] == item["sample_id"] for other in payload["values"]) > 1
    )
    source = mutated["source_observation"]
    source["factor_levels"][0]["level_id"] = "level.m0206.rebound.nonobserved"
    mutated["source_observation_digest"] = observation_summary_digest(
        target_id=source["target_id"],
        feature_id=source["feature_id"],
        biological_group_id=source["biological_group_id"],
        state=source["state"].value,
        value=source["value"],
        censoring_limit=source["censoring_limit"],
        unit=source["unit"],
        factor_levels=tuple(
            (level["factor"].value, level["level_id"]) for level in source["factor_levels"]
        ),
        evidence_digests=source["evidence_digests"],
    )
    rebound_request_digest = request_manifest_digest(
        active_context_digest=payload["context_digest"],
        active_prerequisites_digest=payload["prerequisites_digest"],
        active_profile_digest=payload["profile_digest"],
        active_policy_digest=payload["policy_digest"],
        observation_digests=tuple(item["source_observation_digest"] for item in payload["values"]),
        invariant_digests=tuple(invariant_digest(item) for item in result.biological_controls),
        supersedes_result_digest=payload["supersedes_result_digest"],
    )
    payload["request_digest"] = rebound_request_digest
    suffix = rebound_request_digest.removeprefix("sha256:")
    payload["harmonization_id"] = f"harmonization.m0206.{suffix}"
    payload["provenance"]["activity_id"] = f"activity.m0206.{suffix}"
    exact_inputs = {
        rebound_request_digest,
        payload["context_digest"],
        payload["prerequisites_digest"],
        payload["profile_digest"],
        payload["policy_digest"],
        payload["configuration_digest"],
        *(receipt["result_digest"] for receipt in payload["upstream_receipts"]),
        *(decision["evidence_digest"] for decision in payload["provenance"]["control_decisions"]),
    }
    payload["provenance"]["input_digests"] = tuple(sorted(exact_inputs))
    payload["result_digest"] = _DERIVED_DIGEST_SENTINEL

    with pytest.raises(
        ValidationError,
        match="source factor levels must be consistent within each target",
    ):
        IdentificationHarmonizationResult.model_validate(payload)
