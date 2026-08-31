"""Admission and public-boundary M04-07 lifecycle cases."""

from tests.modules.c04_proteoform_isoform.m04_07_lifecycle_cases import (
    test_admission_cache_drops_dead_source_and_warm_concurrency_is_deterministic,
    test_admission_capability_rejects_nested_stale_source_and_validated_state,
    test_admission_capability_rejects_stale_request_and_upstream_mutation,
    test_admission_capability_rejects_wrong_typed_fields_without_equality,
    test_authorized_materialization_rejects_virtual_sequence_without_touching_it,
    test_plugin_json_boundary_strict_decodes_once_without_service_reparse,
    test_plugin_rejects_unvalidated_execution_capability,
    test_plugin_run_uses_private_validated_execution_path,
    test_preflight_rejects_arbitrary_mapping_accessors_without_touching_them,
    test_public_route_reuses_only_one_fully_admitted_exact_request_and_rederives,
    test_semantic_reorder_reconstructs_complete_result_equality,
    test_strict_plugin_json_rejects_unknown_members,
)

__all__ = (
    "test_admission_cache_drops_dead_source_and_warm_concurrency_is_deterministic",
    "test_admission_capability_rejects_nested_stale_source_and_validated_state",
    "test_admission_capability_rejects_stale_request_and_upstream_mutation",
    "test_admission_capability_rejects_wrong_typed_fields_without_equality",
    "test_authorized_materialization_rejects_virtual_sequence_without_touching_it",
    "test_plugin_json_boundary_strict_decodes_once_without_service_reparse",
    "test_plugin_rejects_unvalidated_execution_capability",
    "test_plugin_run_uses_private_validated_execution_path",
    "test_preflight_rejects_arbitrary_mapping_accessors_without_touching_them",
    "test_public_route_reuses_only_one_fully_admitted_exact_request_and_rederives",
    "test_semantic_reorder_reconstructs_complete_result_equality",
    "test_strict_plugin_json_rejects_unknown_members",
)
