"""Static contract-spine checks for M04-06 harmonization."""

from datetime import timedelta
from typing import cast, get_args

import pytest
from evals.m04_05.run import build_scenario_result as build_m0405_result
from evals.m04_06.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m04_06 import (
    M0406_CONTRACT_VERSION,
    M0406_FACTOR_COUNT,
    M0406_GATE,
    M0406_MAX_APPLIED_ADJUSTMENTS,
    M0406_MAX_FINDINGS,
    M0406_MAX_INVARIANT_TARGET_REFS,
    M0406_MAX_LEVEL_SHIFTS,
    M0406_MAX_LEVELS_PER_FACTOR,
    M0406_MAX_OBSERVATIONS,
    M0406_MAX_STAGE_ESTIMATION_ANCHORS,
    M0406_MAX_STAGE_VALIDATION_ANCHORS,
    M0406_MAX_TARGETS,
    M0406_MAX_UPSTREAM_TARGETS,
    M0406_MODULE_ID,
    M0406_OPERATION,
    M0406_OWNER,
    M0406_PARENT,
    M0406_SAFETY_CLASS,
    M0406_UPSTREAM_DETECTOR_COUNT,
    ContractName,
    HarmonizeProteoformAnalysisRequest,
    ProteoformArtifactHarmonizationReceipt,
    ProteoformArtifactTargetReceipt,
    ProteoformArtifactTargetState,
    ProteoformHarmonizationComputationReceipt,
    ProteoformHarmonizationDisposition,
    ProteoformHarmonizationPolicy,
    ProteoformHarmonizationProfile,
    ProteoformHarmonizationResult,
    ProteoformHarmonizedAnalysis,
    ProteoformNormalizationFactor,
    ProteoformSupportInvariantKind,
    ProteoformSupportLedger,
    ProteoformTransformationManifest,
    artifact_harmonization_receipt,
    configuration_digest,
    contract_json_schema,
    matching_harmonization_profile,
    opaque_harmonization_identifier,
    support_ledger_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes

_EXPECTED_FACTOR_COUNT = 8
_EXPECTED_UPSTREAM_DETECTOR_COUNT = 7
_EXPECTED_FINDING_COUNT = 14


@pytest.fixture(scope="module")
def accepted_request() -> HarmonizeProteoformAnalysisRequest:
    return build_scenario_request("accepted")


@pytest.fixture(scope="module")
def abstained_request() -> HarmonizeProteoformAnalysisRequest:
    return build_scenario_request("abstained")


def test_module_identity_and_dossier_constants_are_locked() -> None:
    assert (
        M0406_MODULE_ID,
        M0406_OPERATION,
        M0406_CONTRACT_VERSION,
        M0406_OWNER,
        M0406_SAFETY_CLASS,
        M0406_GATE,
        M0406_PARENT,
    ) == (
        "GLIO-PROTEOGEN-M04-06",
        "harmonize_proteoform_analysis",
        "1.0.0",
        "Scientific engineering",
        "S2",
        "G1",
        "protein_rna_discordance",
    )
    assert M0406_FACTOR_COUNT == len(ProteoformNormalizationFactor) == _EXPECTED_FACTOR_COUNT
    assert M0406_UPSTREAM_DETECTOR_COUNT == _EXPECTED_UPSTREAM_DETECTOR_COUNT
    assert M0406_MAX_FINDINGS == _EXPECTED_FINDING_COUNT


def test_public_schema_inventory_and_ids_are_exact() -> None:
    names = get_args(ContractName)
    assert names == (
        "request",
        "output",
        "policy",
        "profile",
        "stage",
        "artifact-receipt",
        "target-receipt",
        "support-ledger",
        "observation",
        "invariant",
        "analysis",
        "value",
        "transformation-manifest",
        "finding",
    )
    for name in names:
        schema = contract_json_schema(name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == (
            f"urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-06:1.0.0:{name}"
        )
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["strict"] is True


def test_owned_processing_capacity_is_distinct_from_the_upstream_receipt_ceiling() -> None:
    assert (
        M0406_MAX_UPSTREAM_TARGETS,
        M0406_MAX_TARGETS,
        M0406_MAX_OBSERVATIONS,
        M0406_MAX_LEVELS_PER_FACTOR,
        M0406_MAX_LEVEL_SHIFTS,
        M0406_MAX_STAGE_ESTIMATION_ANCHORS,
        M0406_MAX_STAGE_VALIDATION_ANCHORS,
        M0406_MAX_INVARIANT_TARGET_REFS,
        M0406_MAX_APPLIED_ADJUSTMENTS,
    ) == (64, 32, 32, 32, 256, 32, 32, 32, 256)

    receipt_properties = cast(
        "dict[str, dict[str, object]]",
        contract_json_schema("artifact-receipt")["properties"],
    )
    ledger_properties = cast(
        "dict[str, dict[str, object]]",
        contract_json_schema("support-ledger")["properties"],
    )
    policy_properties = cast(
        "dict[str, dict[str, object]]",
        contract_json_schema("policy")["properties"],
    )
    analysis_properties = cast(
        "dict[str, dict[str, object]]",
        contract_json_schema("analysis")["properties"],
    )
    assert receipt_properties["target_count"]["maximum"] == M0406_MAX_UPSTREAM_TARGETS
    assert receipt_properties["targets"]["maxItems"] == M0406_MAX_UPSTREAM_TARGETS
    assert ledger_properties["observations"]["maxItems"] == M0406_MAX_OBSERVATIONS
    assert policy_properties["max_targets"]["maximum"] == M0406_MAX_TARGETS
    assert analysis_properties["target_count"]["maximum"] == M0406_MAX_TARGETS


def test_request_embeds_the_full_upstream_result_and_exact_receipt() -> None:
    fields = HarmonizeProteoformAnalysisRequest.model_fields
    assert tuple(fields) == (
        "operation",
        "contract_version",
        "context",
        "artifact_result",
        "artifact_receipt",
        "support_ledger",
        "policy",
        "supersedes_result_digest",
    )
    receipt_fields = ProteoformArtifactHarmonizationReceipt.model_fields
    for field in (
        "artifact_result_digest",
        "quality_result_digest",
        "quality_receipt_digest",
        "identity_resolution_digest",
        "protocol_result_digest",
        "reference_bundle_digest",
        "coordinate_policy_digest",
        "intended_use_evidence_digest",
        "applicability",
        "assay_protocol_version",
        "specimen_processing_version",
        "controlled_vocabulary_id",
        "controlled_vocabulary_version",
        "unit_system_version",
        "targets",
        "target_binding_digest",
    ):
        assert field in receipt_fields


def test_receipt_replays_genuine_m0405_results_without_inventing_safe_failure_data() -> None:
    cleared = build_m0405_result("canonical_clear")
    cleared_receipt = artifact_harmonization_receipt(cleared)
    assert cleared_receipt.artifact_result_digest == cleared.result_digest
    assert cleared_receipt.quality_result_digest == cleared.request.quality_result.result_digest
    assert cleared_receipt.target_count == 1
    assert len(cleared_receipt.targets[0].posterior_digests) == _EXPECTED_UPSTREAM_DETECTOR_COUNT

    abstained = build_m0405_result("upstream_abstained")
    abstained_receipt = artifact_harmonization_receipt(abstained)
    assert abstained_receipt.artifact_result_digest == abstained.result_digest
    assert abstained_receipt.target_count == 0
    assert abstained_receipt.targets == ()
    assert abstained_receipt.selected_profile_digest is None


def test_target_receipt_closes_all_seven_m0405_posteriors() -> None:
    assert set(ProteoformArtifactTargetReceipt.model_fields) == {
        "target_id",
        "unit_kind",
        "target_state",
        "action",
        "posterior_digests",
        "posterior_binding_digest",
        "contamination_flag_ids",
        "excluded",
    }


def test_owned_identifier_and_media_type_sanitization_are_strict(
    accepted_request: HarmonizeProteoformAnalysisRequest,
) -> None:
    target = accepted_request.artifact_receipt.targets[0]
    target_payload = target.model_dump(mode="python")
    target_payload["target_id"] = "target.not-opaque"
    with pytest.raises(ValidationError, match="content-derived opaque target"):
        type(target).model_validate(target_payload, strict=True)

    policy = accepted_request.policy
    policy_payload = policy.model_dump(mode="python")
    policy_payload["evidence"] = policy.evidence.model_copy(
        update={"media_type": "Application/JSON"}
    )
    with pytest.raises(ValidationError, match="strict lowercase type/subtype syntax"):
        type(policy).model_validate(policy_payload, strict=True)


def test_computation_receipt_projects_downstream_replay_fields() -> None:
    fields = ProteoformHarmonizationComputationReceipt.model_fields
    for field in (
        "artifact_result_digest",
        "artifact_receipt_digest",
        "quality_result_digest",
        "identity_resolution_digest",
        "applicability",
        "assay_protocol_version",
        "specimen_processing_version",
        "controlled_vocabulary_id",
        "controlled_vocabulary_version",
        "unit_system_version",
        "analysis_digest",
        "analysis_platform_level_ids",
        "analysis_target_count",
        "analysis_retain_target_count",
        "analysis_review_target_count",
        "analysis_exclude_target_count",
        "analysis_evaluable_target_count",
    ):
        assert field in fields
    assert set(ProteoformArtifactTargetState) == {
        ProteoformArtifactTargetState.CLEAR,
        ProteoformArtifactTargetState.REVIEW,
        ProteoformArtifactTargetState.INDETERMINATE,
        ProteoformArtifactTargetState.EXCLUDED,
    }


def test_result_emits_only_analysis_and_transformation_manifest() -> None:
    result_fields = ProteoformHarmonizationResult.model_fields
    assert result_fields["analysis"].annotation == ProteoformHarmonizedAnalysis | None
    assert result_fields["transformation_manifest"].annotation == (
        ProteoformTransformationManifest | None
    )
    for field in (
        "emits_protein_rna_discordance",
        "emits_proteogenomic_state",
        "emits_proteotype",
        "emits_protein_level_subtype",
        "infers_identity",
        "infers_consent",
        "infers_protein",
        "infers_proteoform",
        "infers_isoform",
        "localizes_modification",
        "infers_kinase_activity",
        "performs_cn_to_protein_regression",
        "performs_all_omics_fusion",
        "recommends_treatment",
        "mutates_upstream",
        "executes_model",
    ):
        assert result_fields[field].default is False
    assert set(ProteoformHarmonizationDisposition) == {
        ProteoformHarmonizationDisposition.ACCEPTED,
        ProteoformHarmonizationDisposition.QUARANTINED,
        ProteoformHarmonizationDisposition.ABSTAINED,
    }


def test_direction_rank_and_composition_invariants_are_closed() -> None:
    assert set(ProteoformSupportInvariantKind) == {
        ProteoformSupportInvariantKind.SUPPORT_DIRECTION,
        ProteoformSupportInvariantKind.SUPPORT_RANK,
        ProteoformSupportInvariantKind.COMPOSITION_FRACTION,
    }


def _validate_profile(payload: dict[str, object]) -> ProteoformHarmonizationProfile:
    return ProteoformHarmonizationProfile.model_validate(payload, strict=True)


def _validate_policy(payload: dict[str, object]) -> ProteoformHarmonizationPolicy:
    return ProteoformHarmonizationPolicy.model_validate(payload, strict=True)


def _validate_relational_contradiction(
    request: HarmonizeProteoformAnalysisRequest,
    case: str,
) -> object:
    policy = request.policy
    profile = policy.profiles[0]
    stage = profile.stages[0]
    if case == "overlapping_anchors":
        payload = {
            **stage.model_dump(mode="python"),
            "validation_anchor_ids": stage.estimation_anchor_ids,
        }
        return type(stage).model_validate(payload, strict=True)
    if case == "duplicate_version":
        payload = {
            **profile.model_dump(mode="python"),
            "approved_assay_protocol_versions": (
                profile.approved_assay_protocol_versions[0],
                profile.approved_assay_protocol_versions[0],
            ),
        }
    elif case == "duplicate_factor":
        duplicate = profile.stages[-1].model_copy(update={"factor": stage.factor})
        payload = {
            **profile.model_dump(mode="python"),
            "stages": (*profile.stages[:-1], duplicate),
        }
    elif case == "duplicate_ordinal":
        duplicate = profile.stages[-1].model_copy(update={"ordinal": stage.ordinal})
        payload = {
            **profile.model_dump(mode="python"),
            "stages": (*profile.stages[:-1], duplicate),
        }
    elif case == "duplicate_stage_id":
        duplicate = profile.stages[-1].model_copy(update={"stage_id": stage.stage_id})
        payload = {
            **profile.model_dump(mode="python"),
            "stages": (*profile.stages[:-1], duplicate),
        }
    elif case == "duplicate_profile_identity":
        policy_payload = {
            **policy.model_dump(mode="python"),
            "profiles": (profile, profile),
        }
        return _validate_policy(policy_payload)
    else:
        overlapping = profile.model_copy(
            update={
                "profile_id": opaque_harmonization_identifier(
                    "profile", {"coverage": "overlapping-domain"}
                )
            }
        )
        policy_payload = {
            **policy.model_dump(mode="python"),
            "profiles": (profile, overlapping),
        }
        return _validate_policy(policy_payload)
    return _validate_profile(payload)


@pytest.mark.parametrize(
    "case",
    [
        "overlapping_anchors",
        "duplicate_version",
        "duplicate_factor",
        "duplicate_ordinal",
        "duplicate_stage_id",
        "duplicate_profile_identity",
        "overlapping_profile_domain",
    ],
)
def test_profile_and_policy_relational_closure_rejects_each_contradiction(
    accepted_request: HarmonizeProteoformAnalysisRequest,
    case: str,
) -> None:
    with pytest.raises(ValidationError):
        _validate_relational_contradiction(accepted_request, case)


def test_matching_profile_returns_none_for_non_evaluable_upstream_shape() -> None:
    request = build_scenario_request("abstained")
    receipt = request.artifact_receipt.model_copy(update={"applicability": None})
    projected = request.model_copy(update={"artifact_receipt": receipt})
    assert matching_harmonization_profile(projected) is None


def _with_rebound_policy(
    request: HarmonizeProteoformAnalysisRequest,
    policy: ProteoformHarmonizationPolicy,
) -> HarmonizeProteoformAnalysisRequest:
    references = request.context.references
    evidence = references.approved_configuration.evidence.model_copy(
        update={"digest": configuration_digest(policy)}
    )
    approved_configuration = references.approved_configuration.model_copy(
        update={"evidence": evidence}
    )
    rebound_references = references.model_copy(
        update={"approved_configuration": approved_configuration}
    )
    context = request.context.model_copy(update={"references": rebound_references})
    return request.model_copy(update={"context": context, "policy": policy})


def _resign_support_ledger(
    ledger: ProteoformSupportLedger,
    **updates: object,
) -> ProteoformSupportLedger:
    payload = ledger.model_dump(mode="python", exclude={"ledger_digest"})
    payload.update(updates)
    payload["ledger_digest"] = support_ledger_digest(payload)
    return ProteoformSupportLedger.model_validate(payload, strict=True)


def _request_with_relational_contradiction(  # noqa: PLR0911 - explicit closure cases.
    request: HarmonizeProteoformAnalysisRequest,
    abstained: HarmonizeProteoformAnalysisRequest,
    case: str,
) -> HarmonizeProteoformAnalysisRequest:
    ledger = request.support_ledger
    assert ledger is not None
    profile = request.policy.profiles[0]
    stage = profile.stages[0]
    if case == "mismatched_receipt":
        return request.model_copy(update={"artifact_receipt": abstained.artifact_receipt})
    if case == "changed_authority":
        references = request.context.references
        provenance = references.provenance.model_copy(
            update={"decision_id": "decision." + ("d" * 64)}
        )
        changed = references.model_copy(update={"provenance": provenance})
        context = request.context.model_copy(update={"references": changed})
        return request.model_copy(update={"context": context})
    if case == "postdated_context":
        context = request.context.model_copy(
            update={
                "occurred_at": request.artifact_receipt.artifact_completed_at - timedelta(seconds=1)
            }
        )
        return request.model_copy(update={"context": context})
    if case == "configuration_mismatch":
        references = request.context.references
        evidence = references.approved_configuration.evidence.model_copy(
            update={"digest": "sha256:" + ("f" * 64)}
        )
        approved = references.approved_configuration.model_copy(update={"evidence": evidence})
        changed = references.model_copy(update={"approved_configuration": approved})
        context = request.context.model_copy(update={"references": changed})
        return request.model_copy(update={"context": context})
    if case == "missing_ledger":
        return request.model_copy(update={"support_ledger": None})
    if case == "predated_ledger":
        changed_ledger = _resign_support_ledger(
            ledger,
            recorded_at=request.artifact_receipt.artifact_completed_at - timedelta(seconds=1),
        )
        return request.model_copy(update={"support_ledger": changed_ledger})
    if case == "invariant_ceiling":
        extra = ledger.invariants[0].model_copy(
            update={
                "invariant_id": opaque_harmonization_identifier(
                    "invariant", {"coverage": "fourth-invariant"}
                )
            }
        )
        invariants = tuple(sorted((*ledger.invariants, extra), key=canonical_json_bytes))
        changed_ledger = _resign_support_ledger(ledger, invariants=invariants)
        policy = request.policy.model_copy(update={"max_invariants": 3})
        rebound = _with_rebound_policy(request, policy)
        return rebound.model_copy(update={"support_ledger": changed_ledger})
    if case in {"unknown_anchor", "invalid_reference_level"}:
        update = (
            {
                "estimation_anchor_ids": (
                    opaque_harmonization_identifier("anchor", {"coverage": "unknown-anchor"}),
                )
            }
            if case == "unknown_anchor"
            else {
                "reference_level_id": opaque_harmonization_identifier(
                    "level", {"coverage": "unknown-reference-level"}
                )
            }
        )
        changed_stage = stage.model_copy(update=update)
        changed_profile = profile.model_copy(
            update={"stages": (changed_stage, *profile.stages[1:])}
        )
        policy = request.policy.model_copy(update={"profiles": (changed_profile,)})
        return _with_rebound_policy(request, policy)
    conflicting_evidence = request.policy.evidence.model_copy(
        update={
            "artifact_id": profile.evidence.artifact_id,
            "version": profile.evidence.version,
            "digest": "sha256:" + ("e" * 64),
        }
    )
    policy = request.policy.model_copy(update={"evidence": conflicting_evidence})
    return _with_rebound_policy(request, policy)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("mismatched_receipt", "artifact receipt must replay"),
        ("changed_authority", "preserve every M04-05 authority"),
        ("postdated_context", "cannot postdate harmonization"),
        ("configuration_mismatch", "does not bind the harmonization policy"),
        ("missing_ledger", "support-ledger presence contradicts"),
        ("predated_ledger", "support facts must follow"),
        ("invariant_ceiling", "exceeds the reviewed invariant ceiling"),
        ("unknown_anchor", "references an unknown anchor"),
        ("invalid_reference_level", "invalid factor-level domain"),
        ("conflicting_artifact", "cannot bind conflicting content"),
    ],
)
def test_request_relational_closure_rejects_each_contradiction(
    accepted_request: HarmonizeProteoformAnalysisRequest,
    abstained_request: HarmonizeProteoformAnalysisRequest,
    case: str,
    message: str,
) -> None:
    contradictory = _request_with_relational_contradiction(
        accepted_request,
        abstained_request,
        case,
    )
    payload = contradictory.model_dump(mode="python")
    with pytest.raises(ValidationError, match=message):
        HarmonizeProteoformAnalysisRequest.model_validate(payload, strict=True)
