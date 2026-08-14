"""Genuine deterministic builders and locked M05-01 conformance evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from glio_proteogen.contracts.m05_01 import (
    M0501_CONTRACT_VERSION,
    M0501_MAX_APPROVED_REFERENCE_BUNDLES,
    M0501_MAX_APPROVED_VERSIONS,
    M0501_MAX_CANONICAL_REQUEST_BYTES,
    M0501_MAX_COMPATIBILITY_RULES,
    M0501_MAX_VOCABULARY_TERMS,
    ApprovedPtmLocalizationReferenceBundle,
    ApprovedPtmLocalizationVocabulary,
    EvaluatePtmLocalizationProtocolRequest,
    PtmLocalizationAssayKind,
    PtmLocalizationAssaySpecimenPolicy,
    PtmLocalizationCompatibilityDimension,
    PtmLocalizationCompatibilityRule,
    PtmLocalizationCompatibilityState,
    PtmLocalizationControlledVocabulary,
    PtmLocalizationIdentityKey,
    PtmLocalizationInputReference,
    PtmLocalizationInputRole,
    PtmLocalizationMetadataFieldName,
    PtmLocalizationMetadataFieldPolicy,
    PtmLocalizationProtocolConformanceDisposition,
    PtmLocalizationProtocolConformanceResult,
    PtmLocalizationProtocolSchema,
    PtmLocalizationQuantity,
    PtmLocalizationReferenceBundle,
    PtmLocalizationReferenceCardinality,
    PtmLocalizationSpecimenKind,
    PtmLocalizationSupportDomain,
    PtmLocalizationUnit,
    PtmLocalizationUnitPolicy,
    PtmLocalizationUnresolvedAction,
    PtmLocalizationUnresolvedRule,
    PtmLocalizationUnresolvedState,
    PtmLocalizationVocabularyMeaning,
    PtmLocalizationVocabularyTerm,
    ReviewedPtmLocalizationConformanceProfile,
    VariantPeptideHandoffRequirements,
    VariantPeptideHandoffRole,
    assay_specimen_policy_digest,
    configuration_digest,
    contract_json_schema,
    contract_json_schemas,
    protocol_digest,
    receipt_digest,
    reference_bundle_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c05_ptm_localization.m05_01_protocol_metadata import (
    M0501Plugin,
    M0501Service,
    PtmLocalizationProtocolAuthorizationError,
    ValidatedM0501Request,
    evaluate_ptm_localization_protocol,
)

_OCCURRED_AT: Final = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
_VERSION: Final = "1.0.0"
_SCHEMA_COUNT: Final = 13
_GROUP_COUNT: Final = 8
_CASES_PER_GROUP: Final = 5
_CASE_COUNT: Final = _GROUP_COUNT * _CASES_PER_GROUP
_FIXTURE_PATH: Final = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "m05_01" / "scenarios.json"
)


class _InvalidFixtureIdentityError(ValueError):
    def __init__(self) -> None:
        super().__init__("M05-01 locked fixture identity is inconsistent")


class _InvalidFixtureShapeError(ValueError):
    def __init__(self) -> None:
        super().__init__("M05-01 fixture requires exactly eight groups of five cases")


class _DuplicateFixtureCaseError(ValueError):
    def __init__(self) -> None:
        super().__init__("M05-01 fixture case identifiers must be unique")


def _hex(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _digest(label: str) -> str:
    return f"sha256:{_hex(label)}"


def _oid(namespace: str, label: str) -> str:
    return f"{namespace}.{_hex(label)}"


def _artifact(label: str, media_type: str) -> ArtifactReference:
    digest = _digest(f"artifact:{label}")
    return ArtifactReference(
        artifact_id=f"evidence.{digest.removeprefix('sha256:')}",
        version=_VERSION,
        digest=digest,
        media_type=media_type,
    )


def _artifact_for_digest(
    digest: str,
    media_type: str,
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"evidence.{digest.removeprefix('sha256:')}",
        version=_VERSION,
        digest=digest,
        media_type=media_type,
    )


def _replace[T](model: T, **updates: object) -> T:
    model_type = type(model)
    payload = model.model_dump(mode="python", exclude_none=False)  # type: ignore[attr-defined]
    payload.update(updates)
    return model_type.model_validate(payload, strict=True)  # type: ignore[attr-defined,no-any-return]


def _reference_bundle() -> PtmLocalizationReferenceBundle:
    return PtmLocalizationReferenceBundle(
        bundle_id=_oid("bundle", "canonical"),
        version=_VERSION,
        cardinality=PtmLocalizationReferenceCardinality(),
        references=tuple(
            PtmLocalizationInputReference(
                role=role,
                reference=_artifact(
                    f"scientific:{role.value}",
                    "application/vnd.glio-proteogen.m05-01.reference+json",
                ),
            )
            for role in PtmLocalizationInputRole
        ),
        manifest_reference=_artifact(
            "scientific:manifest",
            "application/vnd.glio-proteogen.m05-01.reference-manifest+json",
        ),
    )


def _vocabularies(*, maximum: bool) -> tuple[PtmLocalizationControlledVocabulary, ...]:
    count = M0501_MAX_APPROVED_VERSIONS if maximum else 1
    return tuple(
        PtmLocalizationControlledVocabulary(
            vocabulary_id=_oid("vocabulary", f"vocabulary:{index}"),
            version=f"1.0.{index}",
            terms=tuple(
                PtmLocalizationVocabularyTerm(
                    term_id=_oid("term", f"term:{index}:{meaning.value}"),
                    meaning=meaning,
                )
                for meaning in PtmLocalizationVocabularyMeaning
            ),
        )
        for index in range(count)
    )


def _unit_policies() -> tuple[PtmLocalizationUnitPolicy, ...]:
    pairs = (
        (PtmLocalizationQuantity.MASS, PtmLocalizationUnit.DALTON),
        (PtmLocalizationQuantity.MASS_TO_CHARGE, PtmLocalizationUnit.THOMSON),
        (PtmLocalizationQuantity.RETENTION_TIME, PtmLocalizationUnit.MINUTE),
        (PtmLocalizationQuantity.MASS_ERROR, PtmLocalizationUnit.PARTS_PER_MILLION),
        (
            PtmLocalizationQuantity.LOCALIZATION_CONFIDENCE,
            PtmLocalizationUnit.PROBABILITY_PPM,
        ),
        (PtmLocalizationQuantity.CARDINALITY, PtmLocalizationUnit.COUNT),
    )
    return tuple(
        PtmLocalizationUnitPolicy(
            unit_policy_id=_oid("unit", f"unit:{quantity.value}"),
            version=_VERSION,
            quantity=quantity,
            unit=unit,
        )
        for quantity, unit in pairs
    )


def _metadata_fields() -> tuple[PtmLocalizationMetadataFieldPolicy, ...]:
    return tuple(
        PtmLocalizationMetadataFieldPolicy(
            field_policy_id=_oid("field", f"field:{field.value}"),
            field_name=field,
            required=True,
            minimum_cardinality=1,
            maximum_cardinality=1,
        )
        for field in PtmLocalizationMetadataFieldName
    )


_COMPATIBILITY_PAIRS: Final = (
    (
        PtmLocalizationCompatibilityDimension.ASSAY,
        PtmLocalizationCompatibilityDimension.SPECIMEN,
    ),
    (
        PtmLocalizationCompatibilityDimension.ASSAY,
        PtmLocalizationCompatibilityDimension.VOCABULARY,
    ),
    (
        PtmLocalizationCompatibilityDimension.ASSAY,
        PtmLocalizationCompatibilityDimension.UNIT_SYSTEM,
    ),
    (
        PtmLocalizationCompatibilityDimension.UNIT_SYSTEM,
        PtmLocalizationCompatibilityDimension.PARENT_TARGET,
    ),
)


def _compatibility_rules(*, maximum: bool) -> tuple[PtmLocalizationCompatibilityRule, ...]:
    count = M0501_MAX_COMPATIBILITY_RULES if maximum else len(_COMPATIBILITY_PAIRS)
    return tuple(
        PtmLocalizationCompatibilityRule(
            rule_id=_oid("rule", f"rule:{index}"),
            left_dimension=_COMPATIBILITY_PAIRS[index % len(_COMPATIBILITY_PAIRS)][0],
            left_version=f"1.0.{index}",
            right_dimension=_COMPATIBILITY_PAIRS[index % len(_COMPATIBILITY_PAIRS)][1],
            right_version=f"1.0.{index}",
            state=PtmLocalizationCompatibilityState.COMPATIBLE,
        )
        for index in range(count)
    )


def _protocol(*, maximum: bool) -> PtmLocalizationProtocolSchema:
    return PtmLocalizationProtocolSchema(
        schema_id=_oid("schema", "canonical"),
        version=_VERSION,
        unit_system_version=_VERSION,
        required_identity_keys=tuple(PtmLocalizationIdentityKey),
        unresolved_rules=tuple(
            PtmLocalizationUnresolvedRule(
                state=state,
                action={
                    PtmLocalizationUnresolvedState.MISSING: (
                        PtmLocalizationUnresolvedAction.QUARANTINE
                    ),
                    PtmLocalizationUnresolvedState.UNKNOWN: (
                        PtmLocalizationUnresolvedAction.QUARANTINE
                    ),
                    PtmLocalizationUnresolvedState.UNSUPPORTED: (
                        PtmLocalizationUnresolvedAction.ABSTAIN
                    ),
                    PtmLocalizationUnresolvedState.CONFLICTING: (
                        PtmLocalizationUnresolvedAction.QUARANTINE
                    ),
                    PtmLocalizationUnresolvedState.NOT_APPLICABLE: (
                        PtmLocalizationUnresolvedAction.PRESERVE
                    ),
                    PtmLocalizationUnresolvedState.REDACTED: (
                        PtmLocalizationUnresolvedAction.QUARANTINE
                    ),
                    PtmLocalizationUnresolvedState.NOT_DETECTED: (
                        PtmLocalizationUnresolvedAction.PRESERVE
                    ),
                    PtmLocalizationUnresolvedState.BELOW_DETECTION_LIMIT: (
                        PtmLocalizationUnresolvedAction.PRESERVE
                    ),
                    PtmLocalizationUnresolvedState.VARIANT_AMBIGUOUS: (
                        PtmLocalizationUnresolvedAction.QUARANTINE
                    ),
                    PtmLocalizationUnresolvedState.SITE_AMBIGUOUS: (
                        PtmLocalizationUnresolvedAction.QUARANTINE
                    ),
                }[state],
            )
            for state in PtmLocalizationUnresolvedState
        ),
        reference_bundle=_reference_bundle(),
        controlled_vocabularies=_vocabularies(maximum=maximum),
        unit_policies=_unit_policies(),
        metadata_fields=_metadata_fields(),
        compatibility_rules=_compatibility_rules(maximum=maximum),
        assay_specimen_policy=PtmLocalizationAssaySpecimenPolicy(
            policy_id=_oid("policy", "assay-specimen"),
            assay_kind=PtmLocalizationAssayKind.DATA_INDEPENDENT_ACQUISITION,
            specimen_kind=PtmLocalizationSpecimenKind.TISSUE,
            assay_protocol_version=_VERSION,
            specimen_processing_version=_VERSION,
            support_domain=PtmLocalizationSupportDomain.REVIEWED_SUPPORTED,
            evidence=_artifact(
                "policy:assay-specimen",
                "application/vnd.glio-proteogen.m05-01.policy+json",
            ),
        ),
        variant_peptide_handoff=VariantPeptideHandoffRequirements(
            required_receipt_roles=tuple(VariantPeptideHandoffRole),
            evidence=_artifact(
                "policy:variant-peptide-handoff",
                "application/vnd.glio-proteogen.m05-01.policy+json",
            ),
        ),
        evidence=_artifact(
            "policy:protocol",
            "application/vnd.glio-proteogen.m05-01.policy+json",
        ),
    )


def _profile(
    protocol: PtmLocalizationProtocolSchema,
    *,
    maximum: bool,
    approve_protocol_version: bool = True,
) -> ReviewedPtmLocalizationConformanceProfile:
    version_count = M0501_MAX_APPROVED_VERSIONS if maximum else 1
    bundle_count = M0501_MAX_APPROVED_REFERENCE_BUNDLES if maximum else 1
    bundle = protocol.reference_bundle
    approved_bundles = [
        ApprovedPtmLocalizationReferenceBundle(
            bundle_id=bundle.bundle_id,
            version=bundle.version,
            bundle_digest=reference_bundle_digest(bundle),
        )
    ]
    approved_bundles.extend(
        ApprovedPtmLocalizationReferenceBundle(
            bundle_id=_oid("bundle", f"approved:{index}"),
            version=f"1.0.{index}",
            bundle_digest=_digest(f"approved-bundle:{index}"),
        )
        for index in range(1, bundle_count)
    )
    protocol_versions = [f"1.0.{index}" for index in range(version_count)]
    if approve_protocol_version and protocol.version not in protocol_versions:
        protocol_versions[0] = protocol.version
    approved_vocabularies = [
        ApprovedPtmLocalizationVocabulary(
            vocabulary_id=item.vocabulary_id,
            version=item.version,
        )
        for item in protocol.controlled_vocabularies
    ]
    approved_vocabularies.extend(
        ApprovedPtmLocalizationVocabulary(
            vocabulary_id=_oid("vocabulary", f"approved:{index}"),
            version=f"1.0.{index}",
        )
        for index in range(len(approved_vocabularies), version_count)
    )
    assay_policy_hash = assay_specimen_policy_digest(protocol.assay_specimen_policy)
    policy_digests = [assay_policy_hash]
    policy_digests.extend(_digest(f"approved-policy:{index}") for index in range(1, version_count))
    return ReviewedPtmLocalizationConformanceProfile(
        profile_id=_oid("profile", "canonical"),
        version=_VERSION,
        protocol_schema_id=protocol.schema_id,
        protocol_schema_version=protocol.version,
        protocol_schema_digest=protocol_digest(protocol),
        approved_reference_bundles=tuple(approved_bundles),
        approved_protocol_versions=tuple(protocol_versions),
        approved_assay_versions=tuple(f"1.0.{index}" for index in range(version_count)),
        approved_specimen_versions=tuple(f"1.0.{index}" for index in range(version_count)),
        approved_vocabulary_versions=tuple(approved_vocabularies),
        approved_unit_system_versions=tuple(f"1.0.{index}" for index in range(version_count)),
        approved_assay_specimen_policy_digests=tuple(policy_digests),
        evidence=_artifact(
            "profile:canonical",
            "application/vnd.glio-proteogen.m05-01.profile+json",
        ),
        reviewed_by=_oid("reviewer", "quality-engineering"),
        reviewed_at=_OCCURRED_AT,
    )


def _context(
    request_id: str,
    protocol: PtmLocalizationProtocolSchema,
    profile: ReviewedPtmLocalizationConformanceProfile,
) -> ExecutionContext:
    config_hash = configuration_digest(protocol, profile)

    def decision(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=_oid("decision", role),
            state=UpstreamDecisionState.ACCEPTED,
            policy_version=_VERSION,
            evidence=_artifact(
                f"control:{role}",
                "application/vnd.glio-proteogen.control+json",
            ),
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id=_oid("actor", "quality-engineering"),
        occurred_at=_OCCURRED_AT,
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id=_oid("decision", "approved-configuration"),
                state=UpstreamDecisionState.ACCEPTED,
                policy_version=_VERSION,
                evidence=_artifact_for_digest(
                    config_hash,
                    "application/vnd.glio-proteogen.control+json",
                ),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id=_oid("decision", "identity-lineage"),
                state=IdentityLineageState.RESOLVED,
                policy_version=_VERSION,
                binding_digest=_digest("identity-subject"),
                evidence=_artifact(
                    "control:identity-lineage",
                    "application/vnd.glio-proteogen.control+json",
                ),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id=_oid("decision", "consent"),
                state=ConsentState.GRANTED,
                policy_version=_VERSION,
                evidence=_artifact(
                    "control:consent",
                    "application/vnd.glio-proteogen.control+json",
                ),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def build_scenario_request(
    scenario: str = "canonical_conformant",
) -> EvaluatePtmLocalizationProtocolRequest:
    """Build one genuine strict request without handwritten result objects."""

    maximum = scenario == "maximum_profile_shape_conforms"
    protocol = _protocol(maximum=maximum)
    approve_protocol_version = True
    if scenario == "unsupported_ood_abstains":
        protocol = _replace(
            protocol,
            assay_specimen_policy=_replace(
                protocol.assay_specimen_policy,
                support_domain=PtmLocalizationSupportDomain.NOVEL_OOD,
            ),
        )
    elif scenario == "unsupported_version_abstains":
        protocol = _replace(protocol, version="2.0.0")
        approve_protocol_version = False
    elif scenario == "unit_incompatibility_quarantined":
        policies = list(protocol.unit_policies)
        mass_index = next(
            index
            for index, item in enumerate(policies)
            if item.quantity is PtmLocalizationQuantity.MASS
        )
        policies[mass_index] = _replace(policies[mass_index], unit=PtmLocalizationUnit.COUNT)
        protocol = _replace(protocol, unit_policies=tuple(policies))
    elif scenario == "metadata_incomplete_quarantined":
        protocol = _replace(protocol, metadata_fields=protocol.metadata_fields[:-1])
    elif scenario == "compatibility_failure_quarantined":
        compatibility_rules = list(protocol.compatibility_rules)
        compatibility_rules[0] = _replace(
            compatibility_rules[0],
            state=PtmLocalizationCompatibilityState.INCOMPATIBLE,
        )
        protocol = _replace(protocol, compatibility_rules=tuple(compatibility_rules))
    elif scenario == "unresolved_semantics_quarantined":
        unresolved_rules = list(protocol.unresolved_rules)
        missing_index = next(
            index
            for index, item in enumerate(unresolved_rules)
            if item.state is PtmLocalizationUnresolvedState.MISSING
        )
        unresolved_rules[missing_index] = _replace(
            unresolved_rules[missing_index],
            action=PtmLocalizationUnresolvedAction.PRESERVE,
        )
        protocol = _replace(protocol, unresolved_rules=tuple(unresolved_rules))
    elif scenario == "identity_incomplete_quarantined":
        protocol = _replace(
            protocol,
            required_identity_keys=protocol.required_identity_keys[:-1],
        )
    elif scenario not in {
        "canonical_conformant",
        "maximum_profile_shape_conforms",
        "superseding_recovery_conforms",
    }:
        raise KeyError(scenario)
    profile = _profile(
        protocol,
        maximum=maximum,
        approve_protocol_version=approve_protocol_version,
    )
    request_id = _oid("request", f"request:{scenario}")
    return EvaluatePtmLocalizationProtocolRequest(
        request_id=request_id,
        context=_context(request_id, protocol, profile),
        protocol_schema=protocol,
        conformance_profile=profile,
        supersedes_result_digest=(
            _digest("superseded-result") if scenario == "superseding_recovery_conforms" else None
        ),
    )


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    declared_groups: int
    group_case_counts: dict[str, int]
    declared_cases: int
    executed_cases: int
    passed_cases: int
    failed_cases: tuple[str, ...]
    passed: bool


def _request_rejected(payload: object) -> bool:
    try:
        EvaluatePtmLocalizationProtocolRequest.model_validate(payload, strict=True)
    except ValidationError:
        return True
    return False


def _result_rejected(payload: object) -> bool:
    try:
        PtmLocalizationProtocolConformanceResult.model_validate(payload, strict=True)
    except ValidationError:
        return True
    return False


def _authorization_denied(control: str, state: str) -> bool:
    payload = build_scenario_request().model_dump(mode="python")
    payload["context"]["references"][control]["state"] = state
    try:
        evaluate_ptm_localization_protocol(payload)
    except PtmLocalizationProtocolAuthorizationError:
        return True
    return False


def _semantic_reorder_is_equal() -> bool:
    request = build_scenario_request()
    payload = request.model_dump(mode="json")
    for path in (
        ("protocol_schema", "required_identity_keys"),
        ("protocol_schema", "unresolved_rules"),
        ("protocol_schema", "controlled_vocabularies"),
        ("protocol_schema", "unit_policies"),
        ("protocol_schema", "metadata_fields"),
        ("protocol_schema", "compatibility_rules"),
        ("conformance_profile", "approved_protocol_versions"),
    ):
        cursor: object = payload
        for segment in path:
            if not isinstance(cursor, dict):
                return False
            cursor = cursor[segment]
        if not isinstance(cursor, list):
            return False
        cursor.reverse()
    reordered = EvaluatePtmLocalizationProtocolRequest.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )
    return evaluate_ptm_localization_protocol(request) == evaluate_ptm_localization_protocol(
        reordered
    )


def _nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {
            *(str(key) for key in value),
            *(nested for item in value.values() for nested in _nested_keys(item)),
        }
    if isinstance(value, list | tuple):
        return {nested for item in value for nested in _nested_keys(item)}
    return set()


def _case_succeeds(case_id: str) -> bool:  # noqa: C901, PLR0911, PLR0912, PLR0915
    conformant = {
        "canonical_conformant": "canonical_conformant",
        "maximum_profile_shape_conforms": "maximum_profile_shape_conforms",
        "superseding_recovery_conforms": "superseding_recovery_conforms",
    }
    quarantined = {
        "unit_incompatibility_quarantined": "unit_incompatibility_quarantined",
        "metadata_incomplete_quarantined": "metadata_incomplete_quarantined",
        "identity_incomplete_quarantined": "identity_incomplete_quarantined",
        "compatibility_failure_quarantined": "compatibility_failure_quarantined",
        "unresolved_semantics_quarantined": "unresolved_semantics_quarantined",
    }
    abstained = {
        "unsupported_version_abstains": "unsupported_version_abstains",
        "unsupported_ood_abstains": "unsupported_ood_abstains",
    }
    if case_id in conformant:
        result = evaluate_ptm_localization_protocol(build_scenario_request(conformant[case_id]))
        if case_id == "superseding_recovery_conforms":
            return (
                result.disposition is PtmLocalizationProtocolConformanceDisposition.CONFORMANT
                and result.request.supersedes_result_digest in result.provenance.input_digests
            )
        return result.disposition is PtmLocalizationProtocolConformanceDisposition.CONFORMANT
    if case_id in quarantined:
        result = evaluate_ptm_localization_protocol(build_scenario_request(quarantined[case_id]))
        return result.disposition is PtmLocalizationProtocolConformanceDisposition.QUARANTINED
    if case_id in abstained:
        result = evaluate_ptm_localization_protocol(build_scenario_request(abstained[case_id]))
        return (
            result.disposition is PtmLocalizationProtocolConformanceDisposition.ABSTAINED
            and result.support.status.value == "unsupported"
            and {item.state.value for item in result.findings} == {"indeterminate"}
        )
    if case_id == "unknown_field_rejected":
        payload = build_scenario_request().model_dump(mode="python")
        payload["unknown"] = True
        return _request_rejected(payload)
    if case_id == "scalar_coercion_rejected":
        payload = build_scenario_request().model_dump(mode="python")
        payload["contract_version"] = 1
        return _request_rejected(payload)
    if case_id == "duplicate_json_rejected":
        plugin = M0501Plugin(M0501Service())
        serialized = (
            build_scenario_request()
            .model_dump_json()
            .replace(
                '"operation":"evaluate_ptm_localization_protocol"',
                (
                    '"operation":"evaluate_ptm_localization_protocol",'
                    '"operation":"evaluate_ptm_localization_protocol"'
                ),
                1,
            )
        )
        try:
            plugin.validate(serialized)
        except ValueError:
            return True
        return False
    if case_id == "thirteen_schemas_closed":
        return len(contract_json_schemas()) == _SCHEMA_COUNT
    denial = {
        "configuration_denial_zero_traversal": ("approved_configuration", "rejected"),
        "identity_denial_zero_traversal": ("identity_lineage", "unresolved"),
        "consent_denial_zero_traversal": ("consent", "withheld"),
        "quality_denial_zero_traversal": ("quality", "rejected"),
    }
    if case_id in denial:
        return _authorization_denied(*denial[case_id])
    if case_id == "remaining_controls_denied":
        return all(
            _authorization_denied(control, "rejected")
            for control in ("provenance", "support", "intended_use")
        )
    if case_id == "profile_pin_forgery_rejected":
        payload = build_scenario_request().model_dump(mode="python")
        payload["conformance_profile"]["protocol_schema_digest"] = "sha256:" + ("f" * 64)
        return _request_rejected(payload)
    if case_id == "configuration_forgery_rejected":
        payload = build_scenario_request().model_dump(mode="python")
        payload["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
            "sha256:" + ("f" * 64)
        )
        return _request_rejected(payload)
    if case_id == "vocabulary_cap_excess_rejected":
        payload = build_scenario_request().model_dump(mode="python")
        vocabulary = payload["protocol_schema"]["controlled_vocabularies"][0]
        vocabulary["terms"] = tuple(vocabulary["terms"]) + tuple(
            vocabulary["terms"][0] for _ in range(M0501_MAX_VOCABULARY_TERMS)
        )
        return _request_rejected(payload)
    if case_id == "missing_not_detected_below_lod_distinct":
        rules = {
            item.state: item.action
            for item in build_scenario_request().protocol_schema.unresolved_rules
        }
        return (
            rules[PtmLocalizationUnresolvedState.MISSING]
            is PtmLocalizationUnresolvedAction.QUARANTINE
            and rules[PtmLocalizationUnresolvedState.NOT_DETECTED]
            is PtmLocalizationUnresolvedAction.PRESERVE
            and rules[PtmLocalizationUnresolvedState.BELOW_DETECTION_LIMIT]
            is PtmLocalizationUnresolvedAction.PRESERVE
        )
    if case_id == "variant_peptide_parent_context_only":
        result = evaluate_ptm_localization_protocol(build_scenario_request())
        return result.parent_target == "variant_peptide" and not result.emits_variant_peptide
    if case_id == "authority_flags_all_false":
        result = evaluate_ptm_localization_protocol(build_scenario_request())
        return not any(
            (
                result.emits_variant_peptide,
                result.emits_proteogenomic_state,
                result.emits_proteotype,
                result.emits_protein_level_subtype,
                result.localizes_ptm,
                result.infers_kinase_activity,
                result.performs_all_omics_fusion,
                result.recommends_treatment,
                result.mutates_upstream_evidence,
                result.infers_identity_or_consent,
            )
        )
    if case_id == "uncertainty_support_domain_narrowed":
        result = evaluate_ptm_localization_protocol(build_scenario_request())
        estimates = (
            result.uncertainty.measurement,
            result.uncertainty.sampling,
            result.uncertainty.parameter,
            result.uncertainty.model_form,
            result.uncertainty.identification,
            result.uncertainty.support,
            result.uncertainty.transport,
        )
        return all(
            item.state.value == "not_estimable" and item.probability is None for item in estimates
        ) and any("narrowed" in note for note in result.uncertainty.sensitivity_notes)
    if case_id == "deterministic_result_equality":
        request = build_scenario_request()
        return evaluate_ptm_localization_protocol(request) == evaluate_ptm_localization_protocol(
            request
        )
    if case_id == "semantic_reorder_equality":
        return _semantic_reorder_is_equal()
    if case_id in {
        "result_digest_forgery_rejected",
        "finding_forgery_rejected",
        "receipt_forgery_rejected",
    }:
        payload = evaluate_ptm_localization_protocol(build_scenario_request()).model_dump(
            mode="python"
        )
        if case_id == "result_digest_forgery_rejected":
            payload["result_digest"] = "sha256:" + ("f" * 64)
        elif case_id == "finding_forgery_rejected":
            payload["findings"][0]["message"] = "forged"
            payload["result_digest"] = result_payload_digest(payload)
        else:
            payload["receipt"]["sections"][0]["state"] = "fail"
            payload["receipt"]["receipt_digest"] = receipt_digest(payload["receipt"])
            payload["result_digest"] = result_payload_digest(payload)
        return _result_rejected(payload)
    if case_id in {"evidence_alias_mismatch_rejected", "evidence_media_type_rejected"}:
        payload = build_scenario_request().model_dump(mode="python")
        reference = payload["protocol_schema"]["reference_bundle"]["references"][0]["reference"]
        if case_id == "evidence_alias_mismatch_rejected":
            reference["artifact_id"] = "evidence." + ("f" * 64)
        else:
            reference["media_type"] = "application/octet-stream"
        return _request_rejected(payload)
    if case_id == "biological_canary_not_reflected":
        rendered = evaluate_ptm_localization_protocol(build_scenario_request()).model_dump_json()
        return all(
            canary not in rendered
            for canary in ("MPEPTIDEK", "P12345", "EGFRvIII", "patient-raw-001")
        )
    if case_id == "unknown_schema_name_rejected":
        try:
            contract_json_schema("not-a-contract")  # type: ignore[arg-type]
        except KeyError:
            return True
        return False
    if case_id == "raw_payload_fields_absent":
        keys = _nested_keys(
            evaluate_ptm_localization_protocol(build_scenario_request()).model_dump(mode="json")
        )
        return not {"spectrum", "sequence", "abundance", "clinical_decision"}.intersection(keys)
    if case_id == "plugin_public_parity":
        request = build_scenario_request()
        plugin = M0501Plugin(M0501Service())
        return plugin.run(plugin.validate(canonical_json_bytes(request))) == (
            evaluate_ptm_localization_protocol(request)
        )
    if case_id == "copied_token_forgery_rejected":
        plugin = M0501Plugin(M0501Service())
        token = plugin.validate(build_scenario_request())
        forged = ValidatedM0501Request(token.request.model_copy(deep=True), token._seal)
        try:
            plugin.run(forged)
        except TypeError:
            return True
        return False
    if case_id == "strict_json_roundtrip":
        result = evaluate_ptm_localization_protocol(build_scenario_request())
        return (
            PtmLocalizationProtocolConformanceResult.model_validate_json(
                result.model_dump_json(), strict=True
            )
            == result
        )
    if case_id == "maximum_request_within_byte_cap":
        return (
            len(canonical_json_bytes(build_scenario_request("maximum_profile_shape_conforms")))
            <= M0501_MAX_CANONICAL_REQUEST_BYTES
        )
    return False


def _locked_inventory() -> tuple[dict[str, int], tuple[str, ...]]:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    if (
        payload["module_id"] != "GLIO-PROTEOGEN-M05-01"
        or payload["contract_version"] != M0501_CONTRACT_VERSION
    ):
        raise _InvalidFixtureIdentityError
    groups = payload["groups"]
    counts = {name: len(cases) for name, cases in groups.items()}
    cases = tuple(case for group in groups.values() for case in group)
    if (
        len(groups) != _GROUP_COUNT
        or set(counts.values()) != {_CASES_PER_GROUP}
        or len(cases) != _CASE_COUNT
    ):
        raise _InvalidFixtureShapeError
    if len(set(cases)) != len(cases):
        raise _DuplicateFixtureCaseError
    return counts, cases


def run_evaluation() -> EvaluationReport:
    """Execute every declared locked case exactly once."""

    group_counts, cases = _locked_inventory()
    failures = tuple(case for case in cases if not _case_succeeds(case))
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M05-01",
        contract_version=M0501_CONTRACT_VERSION,
        declared_groups=len(group_counts),
        group_case_counts=group_counts,
        declared_cases=len(cases),
        executed_cases=len(cases),
        passed_cases=len(cases) - len(failures),
        failed_cases=failures,
        passed=not failures,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    report = run_evaluation()
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0 if report.passed else 1


__all__ = ["EvaluationReport", "build_scenario_request", "main", "run_evaluation"]


if __name__ == "__main__":
    raise SystemExit(main())
