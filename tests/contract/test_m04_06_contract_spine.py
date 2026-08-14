"""Static contract-spine checks for M04-06 harmonization."""

from typing import cast, get_args

from evals.m04_05.run import build_scenario_result as build_m0405_result

from glio_proteogen.contracts.m04_06 import (
    M0406_CONTRACT_VERSION,
    M0406_FACTOR_COUNT,
    M0406_GATE,
    M0406_MAX_FINDINGS,
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
    ProteoformHarmonizationResult,
    ProteoformHarmonizedAnalysis,
    ProteoformNormalizationFactor,
    ProteoformSupportInvariantKind,
    ProteoformTransformationManifest,
    artifact_harmonization_receipt,
    contract_json_schema,
)

_EXPECTED_FACTOR_COUNT = 8
_EXPECTED_UPSTREAM_DETECTOR_COUNT = 7
_EXPECTED_FINDING_COUNT = 14


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
