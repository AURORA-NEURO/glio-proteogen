"""Execution and sealed-result M04-07 lifecycle cases."""

from tests.modules.c04_proteoform_isoform.m04_07_lifecycle_cases import (
    test_admission_capability_and_equal_request_copies_cannot_reuse_identity,
    test_admission_capability_rejects_mutated_cached_request,
    test_authorized_materialization_rejects_list_and_tuple_subclasses_untouched,
    test_cached_admission_still_preflights_all_controls,
    test_engine_service_and_plugin_replay_one_joint_envelope,
    test_internal_prerequisite_capability_fields_and_snapshot_fail_without_callbacks,
    test_outside_and_missing_declarations_remain_distinct_abstentions,
    test_owned_result_capability_fields_snapshots_and_bundle_fail_without_callbacks,
    test_owned_result_capability_rejects_mutated_cached_bundle,
    test_plugin_typed_mapping_reordered_and_json_validation_are_exact_parity,
    test_preflight_caps_mapping_before_any_governed_upstream_traversal,
    test_receipt_builders_reject_malformed_and_cross_chain_results,
    test_seven_control_denial_precedes_hostile_prerequisite_traversal,
)

__all__ = (
    "test_admission_capability_and_equal_request_copies_cannot_reuse_identity",
    "test_admission_capability_rejects_mutated_cached_request",
    "test_authorized_materialization_rejects_list_and_tuple_subclasses_untouched",
    "test_cached_admission_still_preflights_all_controls",
    "test_engine_service_and_plugin_replay_one_joint_envelope",
    "test_internal_prerequisite_capability_fields_and_snapshot_fail_without_callbacks",
    "test_outside_and_missing_declarations_remain_distinct_abstentions",
    "test_owned_result_capability_fields_snapshots_and_bundle_fail_without_callbacks",
    "test_owned_result_capability_rejects_mutated_cached_bundle",
    "test_plugin_typed_mapping_reordered_and_json_validation_are_exact_parity",
    "test_preflight_caps_mapping_before_any_governed_upstream_traversal",
    "test_receipt_builders_reject_malformed_and_cross_chain_results",
    "test_seven_control_denial_precedes_hostile_prerequisite_traversal",
)
