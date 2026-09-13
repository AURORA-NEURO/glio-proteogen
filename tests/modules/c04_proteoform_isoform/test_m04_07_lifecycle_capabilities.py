"""Capability and materialization M04-07 lifecycle cases."""

from tests.modules.c04_proteoform_isoform.m04_07_lifecycle_cases import (
    test_admission_capability_binds_exact_prerequisite_identity_before_access,
    test_authorized_materialization_rejects_arbitrary_sequence_without_touching_it,
    test_each_control_independently_denies_before_route,
    test_genuine_receipt_builders_reconstruct_exact_compact_chain,
    test_internal_prerequisite_capability_requires_issuance_and_preserves_identity,
    test_owned_result_derives_once_then_validates_the_sealed_full_bundle,
    test_plugin_capability_binds_equal_upstream_object_identity,
    test_plugin_capability_binds_exact_prerequisite_identity_before_access,
    test_plugin_capability_is_issued_identity_not_a_constructible_dataclass,
    test_plugin_capability_rejects_stale_digest_upstream_object_mutation,
    test_plugin_capability_rejects_wrong_typed_request_without_equality,
    test_preflight_rejects_non_exact_string_keys_without_equality_or_upstream_traversal,
)

__all__ = (
    "test_admission_capability_binds_exact_prerequisite_identity_before_access",
    "test_authorized_materialization_rejects_arbitrary_sequence_without_touching_it",
    "test_each_control_independently_denies_before_route",
    "test_genuine_receipt_builders_reconstruct_exact_compact_chain",
    "test_internal_prerequisite_capability_requires_issuance_and_preserves_identity",
    "test_owned_result_derives_once_then_validates_the_sealed_full_bundle",
    "test_plugin_capability_binds_equal_upstream_object_identity",
    "test_plugin_capability_binds_exact_prerequisite_identity_before_access",
    "test_plugin_capability_is_issued_identity_not_a_constructible_dataclass",
    "test_plugin_capability_rejects_stale_digest_upstream_object_mutation",
    "test_plugin_capability_rejects_wrong_typed_request_without_equality",
    "test_preflight_rejects_non_exact_string_keys_without_equality_or_upstream_traversal",
)
