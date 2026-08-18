"""Replay the locked M04-01 synthetic proteoform protocol corpus."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any, Final, NoReturn, TypedDict, cast

from pydantic import ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m04_01 import (
    M0401_EVIDENCE_COUNT,
    M0401_LIMITATION_COUNT,
    M0401_MAX_APPROVED_REFERENCE_BUNDLES,
    M0401_MAX_APPROVED_VERSIONS,
    M0401_MAX_CANONICAL_PROTEIN_SEQUENCES,
    M0401_MAX_CANONICAL_REQUEST_BYTES,
    M0401_MAX_COORDINATE_PROFILES,
    M0401_MAX_GENE_RECORDS,
    M0401_MAX_ISOFORM_DISCRIMINATORS,
    M0401_MAX_ISOFORM_SEQUENCES,
    M0401_MAX_MODIFICATION_TERMS,
    M0401_MAX_QUANTIFICATION_PAIRS,
    M0401_MAX_TRANSCRIPT_PROTEIN_EDGES,
    M0401_MAX_TRANSCRIPT_RECORDS,
    ApprovedControlledVocabulary,
    ApprovedCoordinateProfile,
    ApprovedProteoformReferenceBundle,
    ApprovedQuantificationPair,
    CoordinateConvention,
    EvaluateProteoformProtocolRequest,
    IsoformDiscriminationPolicy,
    LabileModificationHandling,
    ModificationLocalizationPolicy,
    ModificationLocalizationState,
    ProteinQuantificationUnit,
    ProteinRnaDiscordanceHandoffRequirements,
    ProteinRnaDiscordanceHandoffRole,
    ProteoformApplicability,
    ProteoformCoordinatePolicy,
    ProteoformEvidenceClass,
    ProteoformEvidenceEligibilityPolicy,
    ProteoformIdentityKey,
    ProteoformProtocolConformanceDisposition,
    ProteoformProtocolConformanceResult,
    ProteoformProtocolOpaqueNamespace,
    ProteoformProtocolSchema,
    ProteoformProtocolSection,
    ProteoformQuantificationPolicy,
    ProteoformQuantificationScale,
    ProteoformReferenceBundle,
    ProteoformReferenceCardinality,
    ProteoformUnresolvedState,
    ReviewedProteoformConformanceProfile,
    TranscriptQuantificationUnit,
    configuration_digest,
    protocol_digest,
    receipt_digest,
    reference_bundle_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
from glio_proteogen.modules.c04_proteoform_isoform.m04_01_protocol_metadata import (
    M0401Plugin,
    M0401Service,
    ProteoformProtocolAuthorizationError,
    evaluate_proteoform_protocol,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M04-01"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m04_01" / "scenarios.json"
EXPECTED_GROUP_COUNT: Final = 8
EXPECTED_CASE_COUNT: Final = 46
EXPECTED_UNRESOLVED_STATE_COUNT: Final = 10
EXPECTED_ALLOCATION: Final = (6, 6, 6, 5, 5, 9, 3, 6)
REFERENCE_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-01.reference+json"
POLICY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-01.policy+json"
PROFILE_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-01.profile+json"
MANIFEST_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-01.manifest+json"
CONTROL_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.control+json"
FIXED_TIME: Final = datetime(2026, 8, 13, 12, tzinfo=UTC)
OPAQUE_IDENTIFIER_PATTERN: Final = re.compile(
    r"^(request|actor|decision|schema|profile|bundle|vocabulary|reviewer|evidence)"
    r"\.[0-9a-f]{64}$"
)


class ScenarioGroup(TypedDict):
    group_id: str
    case_ids: list[str]
    expected_case_count: int


class Corpus(TypedDict):
    module_id: str
    schema_version: str
    operation: str
    scenario_groups: list[ScenarioGroup]
    expected_group_count: int
    expected_total_case_count: int
    expected_case_allocation: list[int]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


class _HostileDict(dict[str, object]):
    traversals: int

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.traversals = 0

    def __getitem__(self, key: str) -> object:
        self.traversals += 1
        raise AssertionError(key)

    def get(self, key: str, _default: object = None) -> object:
        self.traversals += 1
        raise AssertionError(key)

    def items(self) -> NoReturn:
        self.traversals += 1
        raise AssertionError

    def __iter__(self) -> NoReturn:
        self.traversals += 1
        raise AssertionError


def _oid(namespace: ProteoformProtocolOpaqueNamespace, label: object) -> str:
    return f"{namespace}.{sha256_digest({'m0401': label}).removeprefix('sha256:')}"


def _artifact(
    label: str,
    *,
    media_type: str,
    digest: str | None = None,
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_oid("evidence", label),
        version="1.0.0",
        digest=digest or sha256_digest({"m0401_evidence": label}),
        media_type=media_type,
    )


def _reference_cardinality(*, maximum: bool) -> ProteoformReferenceCardinality:
    if maximum:
        return ProteoformReferenceCardinality(
            gene_records=M0401_MAX_GENE_RECORDS,
            transcript_records=M0401_MAX_TRANSCRIPT_RECORDS,
            canonical_protein_sequences=M0401_MAX_CANONICAL_PROTEIN_SEQUENCES,
            isoform_sequences=M0401_MAX_ISOFORM_SEQUENCES,
            mapped_transcripts=M0401_MAX_TRANSCRIPT_RECORDS,
            mapped_protein_sequences=(
                M0401_MAX_CANONICAL_PROTEIN_SEQUENCES + M0401_MAX_ISOFORM_SEQUENCES
            ),
            transcript_protein_edges=M0401_MAX_TRANSCRIPT_PROTEIN_EDGES,
            modification_terms=M0401_MAX_MODIFICATION_TERMS,
        )
    return ProteoformReferenceCardinality(
        gene_records=10,
        transcript_records=20,
        canonical_protein_sequences=15,
        isoform_sequences=5,
        mapped_transcripts=15,
        mapped_protein_sequences=10,
        transcript_protein_edges=20,
        modification_terms=100,
    )


def _reference_bundle(*, maximum: bool) -> ProteoformReferenceBundle:
    return ProteoformReferenceBundle(
        bundle_id=_oid("bundle", "canonical"),
        version="1.0.0",
        cardinality=_reference_cardinality(maximum=maximum),
        genome_reference=_artifact("genome", media_type=REFERENCE_MEDIA_TYPE),
        transcript_annotation_reference=_artifact(
            "transcript-annotation", media_type=REFERENCE_MEDIA_TYPE
        ),
        canonical_protein_reference=_artifact("canonical-protein", media_type=REFERENCE_MEDIA_TYPE),
        isoform_reference=_artifact("isoform", media_type=REFERENCE_MEDIA_TYPE),
        transcript_protein_mapping_reference=_artifact(
            "transcript-protein-mapping", media_type=REFERENCE_MEDIA_TYPE
        ),
        modification_vocabulary_reference=_artifact(
            "modification-vocabulary", media_type=REFERENCE_MEDIA_TYPE
        ),
        bundle_manifest_reference=_artifact("bundle-manifest", media_type=MANIFEST_MEDIA_TYPE),
    )


def _protocol(*, maximum: bool = False) -> ProteoformProtocolSchema:
    reference_bundle = _reference_bundle(maximum=maximum)
    return ProteoformProtocolSchema(
        schema_id=_oid("schema", "canonical"),
        version="1.0.0",
        applicability=ProteoformApplicability.BOTTOM_UP_DIA,
        assay_protocol_version="2.1.0",
        specimen_processing_version="1.4.0",
        controlled_vocabulary_id=_oid("vocabulary", "canonical"),
        controlled_vocabulary_version="3.0.0",
        unit_system_version="1.0.0",
        required_identity_keys=tuple(ProteoformIdentityKey),
        declared_unresolved_states=tuple(ProteoformUnresolvedState),
        reference_bundle=reference_bundle,
        coordinate_policy=ProteoformCoordinatePolicy(
            genome_convention=CoordinateConvention.ONE_BASED_CLOSED,
            transcript_convention=CoordinateConvention.ONE_BASED_CLOSED,
            protein_convention=CoordinateConvention.ONE_BASED_CLOSED,
            coordinate_mapping_version="1.0.0",
        ),
        evidence_eligibility=ProteoformEvidenceEligibilityPolicy(
            eligible_evidence_classes=tuple(ProteoformEvidenceClass),
            evidence=_artifact("evidence-eligibility", media_type=POLICY_MEDIA_TYPE),
        ),
        isoform_discrimination=IsoformDiscriminationPolicy(
            accepted_discriminators=tuple(ProteoformEvidenceClass),
            minimum_independent_discriminators=(M0401_MAX_ISOFORM_DISCRIMINATORS if maximum else 2),
            evidence=_artifact("isoform-discrimination", media_type=POLICY_MEDIA_TYPE),
        ),
        modification_localization=ModificationLocalizationPolicy(
            declared_states=tuple(ModificationLocalizationState),
            minimum_localized_probability_ppm=900_000,
            labile_modification_handling=LabileModificationHandling.PRESERVE_SITE_SET,
            evidence=_artifact("modification-localization", media_type=POLICY_MEDIA_TYPE),
        ),
        quantification=ProteoformQuantificationPolicy(
            protein_unit=ProteinQuantificationUnit.NORMALIZED_INTENSITY,
            transcript_unit=TranscriptQuantificationUnit.TPM,
            protein_scale=ProteoformQuantificationScale.LOG2,
            transcript_scale=ProteoformQuantificationScale.LOG2,
            evidence=_artifact("quantification", media_type=POLICY_MEDIA_TYPE),
        ),
        discordance_handoff=ProteinRnaDiscordanceHandoffRequirements(
            required_receipt_roles=tuple(ProteinRnaDiscordanceHandoffRole),
            evidence=_artifact("discordance-handoff", media_type=POLICY_MEDIA_TYPE),
        ),
        evidence=_artifact("protocol", media_type=POLICY_MEDIA_TYPE),
    )


def _versions(canonical: str, count: int) -> tuple[str, ...]:
    return (canonical, *(f"90.0.{index}" for index in range(1, count)))


def _approved_bundles(
    protocol: ProteoformProtocolSchema, *, maximum: bool
) -> tuple[ApprovedProteoformReferenceBundle, ...]:
    bundle = protocol.reference_bundle
    canonical = ApprovedProteoformReferenceBundle(
        bundle_id=bundle.bundle_id,
        version=bundle.version,
        bundle_digest=reference_bundle_digest(bundle),
    )
    if not maximum:
        return (canonical,)
    extras = tuple(
        ApprovedProteoformReferenceBundle(
            bundle_id=_oid("bundle", {"approved": index}),
            version=f"80.0.{index}",
            bundle_digest=sha256_digest({"approved_bundle": index}),
        )
        for index in range(1, M0401_MAX_APPROVED_REFERENCE_BUNDLES)
    )
    return (canonical, *extras)


def _approved_vocabularies(
    protocol: ProteoformProtocolSchema, *, maximum: bool
) -> tuple[ApprovedControlledVocabulary, ...]:
    canonical = ApprovedControlledVocabulary(
        vocabulary_id=protocol.controlled_vocabulary_id,
        version=protocol.controlled_vocabulary_version,
    )
    if not maximum:
        return (canonical,)
    extras = tuple(
        ApprovedControlledVocabulary(
            vocabulary_id=_oid("vocabulary", {"approved": index}),
            version=f"70.0.{index}",
        )
        for index in range(1, M0401_MAX_APPROVED_VERSIONS)
    )
    return (canonical, *extras)


def _approved_coordinates(
    protocol: ProteoformProtocolSchema, *, maximum: bool
) -> tuple[ApprovedCoordinateProfile, ...]:
    canonical = ApprovedCoordinateProfile(
        genome_convention=protocol.coordinate_policy.genome_convention,
        transcript_convention=protocol.coordinate_policy.transcript_convention,
        protein_convention=protocol.coordinate_policy.protein_convention,
        coordinate_mapping_version=protocol.coordinate_policy.coordinate_mapping_version,
    )
    if not maximum:
        return (canonical,)
    extras = tuple(
        ApprovedCoordinateProfile(
            genome_convention=(
                CoordinateConvention.ONE_BASED_CLOSED
                if index % 2 == 0
                else CoordinateConvention.ZERO_BASED_HALF_OPEN
            ),
            transcript_convention=CoordinateConvention.ONE_BASED_CLOSED,
            protein_convention=CoordinateConvention.ONE_BASED_CLOSED,
            coordinate_mapping_version=f"60.0.{index}",
        )
        for index in range(1, M0401_MAX_COORDINATE_PROFILES)
    )
    return (canonical, *extras)


def _quantification_pair(protocol: ProteoformProtocolSchema) -> ApprovedQuantificationPair:
    quantification = protocol.quantification
    return ApprovedQuantificationPair(
        protein_unit=quantification.protein_unit,
        transcript_unit=quantification.transcript_unit,
        protein_scale=quantification.protein_scale,
        transcript_scale=quantification.transcript_scale,
    )


def _approved_quantification_pairs(
    protocol: ProteoformProtocolSchema, *, maximum: bool
) -> tuple[ApprovedQuantificationPair, ...]:
    canonical = _quantification_pair(protocol)
    if not maximum:
        return (canonical,)
    candidates = (
        ApprovedQuantificationPair(
            protein_unit=protein_unit,
            transcript_unit=transcript_unit,
            protein_scale=protein_scale,
            transcript_scale=transcript_scale,
        )
        for protein_unit, transcript_unit, protein_scale, transcript_scale in product(
            ProteinQuantificationUnit,
            TranscriptQuantificationUnit,
            ProteoformQuantificationScale,
            ProteoformQuantificationScale,
        )
    )
    unique = tuple(item for item in candidates if item != canonical)
    return (canonical, *unique[: M0401_MAX_QUANTIFICATION_PAIRS - 1])


def _profile(
    protocol: ProteoformProtocolSchema,
    *,
    maximum: bool = False,
) -> ReviewedProteoformConformanceProfile:
    return ReviewedProteoformConformanceProfile(
        profile_id=_oid("profile", "canonical" if not maximum else "maximum"),
        version="1.0.0",
        protocol_schema_id=protocol.schema_id,
        protocol_schema_version=protocol.version,
        protocol_schema_digest=protocol_digest(protocol),
        approved_applicabilities=(
            tuple(ProteoformApplicability) if maximum else (protocol.applicability,)
        ),
        approved_reference_bundles=_approved_bundles(protocol, maximum=maximum),
        approved_assay_protocol_versions=(
            _versions(protocol.assay_protocol_version, M0401_MAX_APPROVED_VERSIONS)
            if maximum
            else (protocol.assay_protocol_version,)
        ),
        approved_specimen_processing_versions=(
            _versions(protocol.specimen_processing_version, M0401_MAX_APPROVED_VERSIONS)
            if maximum
            else (protocol.specimen_processing_version,)
        ),
        approved_controlled_vocabularies=_approved_vocabularies(protocol, maximum=maximum),
        approved_unit_system_versions=(
            _versions(protocol.unit_system_version, M0401_MAX_APPROVED_VERSIONS)
            if maximum
            else (protocol.unit_system_version,)
        ),
        approved_coordinate_profiles=_approved_coordinates(protocol, maximum=maximum),
        approved_quantification_pairs=_approved_quantification_pairs(protocol, maximum=maximum),
        approved_evidence_classes=tuple(ProteoformEvidenceClass),
        approved_labile_modification_handlings=tuple(LabileModificationHandling),
        approved_isoform_discriminators=tuple(ProteoformEvidenceClass),
        minimum_isoform_discriminators=(M0401_MAX_ISOFORM_DISCRIMINATORS if maximum else 2),
        minimum_localization_probability_ppm=900_000,
        evidence=_artifact(
            "maximum-profile" if maximum else "profile",
            media_type=PROFILE_MEDIA_TYPE,
        ),
        reviewed_by=_oid("reviewer", "synthetic"),
        reviewed_at=FIXED_TIME,
    )


def _context(
    protocol: ProteoformProtocolSchema,
    profile: ReviewedProteoformConformanceProfile,
    *,
    label: str,
    identity_binding_digest: str | None = None,
) -> ExecutionContext:
    def decision(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=_oid("decision", {"request": label, "role": role}),
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(
                f"control-{label}-{role}",
                media_type=CONTROL_MEDIA_TYPE,
                digest=digest,
            ),
        )

    return ExecutionContext(
        request_id=_oid("request", label),
        actor_id=_oid("actor", "eval"),
        occurred_at=FIXED_TIME,
        references=ContextReferences(
            approved_configuration=decision(
                "approved-configuration", configuration_digest(protocol, profile)
            ),
            identity_lineage=IdentityLineageReference(
                decision_id=_oid("decision", {"request": label, "role": "identity-lineage"}),
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=identity_binding_digest
                or sha256_digest({"identity_binding": "synthetic"}),
                evidence=_artifact(
                    f"control-{label}-identity-lineage", media_type=CONTROL_MEDIA_TYPE
                ),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id=_oid("decision", {"request": label, "role": "consent"}),
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact(f"control-{label}-consent", media_type=CONTROL_MEDIA_TYPE),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _request(
    protocol: ProteoformProtocolSchema,
    profile: ReviewedProteoformConformanceProfile,
    *,
    label: str,
    supersedes_result_digest: str | None = None,
    identity_binding_digest: str | None = None,
) -> EvaluateProteoformProtocolRequest:
    return EvaluateProteoformProtocolRequest(
        request_id=_oid("request", label),
        context=_context(
            protocol,
            profile,
            label=label,
            identity_binding_digest=identity_binding_digest,
        ),
        protocol_schema=protocol,
        conformance_profile=profile,
        supersedes_result_digest=supersedes_result_digest,
    )


def build_scenario_request(
    case_id: str = "canonical_reference_bundle_conforms",
) -> EvaluateProteoformProtocolRequest:
    """Build a genuine strict request; the maximum case fills every installed profile cap."""

    maximum = case_id == "maximum_profile_shape_conforms"
    protocol = _protocol(maximum=maximum)
    return _request(protocol, _profile(protocol, maximum=maximum), label=case_id)


def _corpus() -> Corpus:
    return cast("Corpus", json.loads(SCENARIO_PATH.read_text(encoding="utf-8")))


def _scenario(case_id: str, *, passed: bool, detail: str) -> EvalCheck:
    return EvalCheck(name=f"scenario.{case_id}", passed=passed, detail=detail)


def _request_payload(
    request: EvaluateProteoformProtocolRequest,
) -> dict[str, Any]:
    return request.model_dump(mode="python", exclude_none=False)


def _validation_rejected(payload: object) -> bool:
    try:
        EvaluateProteoformProtocolRequest.model_validate(payload, strict=True)
    except (ValidationError, ValueError):
        return True
    return False


def _evaluation_rejected(payload: object) -> bool:
    try:
        evaluate_proteoform_protocol(payload)
    except (ProteoformProtocolAuthorizationError, ValidationError, ValueError):
        return True
    return False


def _protocol_with(
    protocol: ProteoformProtocolSchema,
    **updates: object,
) -> ProteoformProtocolSchema:
    payload = protocol.model_dump(mode="python")
    payload.update(updates)
    return ProteoformProtocolSchema.model_validate(payload, strict=True)


def _profile_with(
    profile: ReviewedProteoformConformanceProfile,
    **updates: object,
) -> ReviewedProteoformConformanceProfile:
    payload = profile.model_dump(mode="python")
    payload.update(updates)
    return ReviewedProteoformConformanceProfile.model_validate(payload, strict=True)


def _quarantines_section(
    result: ProteoformProtocolConformanceResult,
    section: ProteoformProtocolSection,
) -> bool:
    failed = tuple(item for item in result.findings if item.state.value == "fail")
    return (
        result.disposition is ProteoformProtocolConformanceDisposition.QUARANTINED
        and len(failed) == 1
        and failed[0].section is section
    )


def _reordered_request(
    request: EvaluateProteoformProtocolRequest,
) -> EvaluateProteoformProtocolRequest:
    payload = _request_payload(request)
    protocol = cast("dict[str, Any]", payload["protocol_schema"])
    profile = cast("dict[str, Any]", payload["conformance_profile"])
    protocol["required_identity_keys"] = tuple(
        reversed(cast("tuple[object, ...]", protocol["required_identity_keys"]))
    )
    protocol["declared_unresolved_states"] = tuple(
        reversed(cast("tuple[object, ...]", protocol["declared_unresolved_states"]))
    )
    for policy_name, field in (
        ("evidence_eligibility", "eligible_evidence_classes"),
        ("isoform_discrimination", "accepted_discriminators"),
        ("modification_localization", "declared_states"),
        ("discordance_handoff", "required_receipt_roles"),
    ):
        policy = cast("dict[str, Any]", protocol[policy_name])
        policy[field] = tuple(reversed(cast("tuple[object, ...]", policy[field])))
    for field in (
        "approved_applicabilities",
        "approved_reference_bundles",
        "approved_assay_protocol_versions",
        "approved_specimen_processing_versions",
        "approved_controlled_vocabularies",
        "approved_unit_system_versions",
        "approved_coordinate_profiles",
        "approved_quantification_pairs",
        "approved_evidence_classes",
        "approved_labile_modification_handlings",
        "approved_isoform_discriminators",
    ):
        profile[field] = tuple(reversed(cast("tuple[object, ...]", profile[field])))
    return EvaluateProteoformProtocolRequest.model_validate(payload, strict=True)


def _bundle_coordinate_checks() -> list[EvalCheck]:
    request = build_scenario_request()
    result = evaluate_proteoform_protocol(request)
    missing_isoform = _request_payload(request)
    missing_bundle = cast(
        "dict[str, Any]",
        cast("dict[str, Any]", missing_isoform["protocol_schema"])["reference_bundle"],
    )
    missing_bundle.pop("isoform_reference")

    nonclosing = _request_payload(request)
    cardinality = cast(
        "dict[str, Any]",
        cast(
            "dict[str, Any]",
            cast("dict[str, Any]", nonclosing["protocol_schema"])["reference_bundle"],
        )["cardinality"],
    )
    cardinality["transcript_protein_edges"] = 1

    identity_conflict = _request_payload(request)
    conflict_bundle = cast(
        "dict[str, Any]",
        cast("dict[str, Any]", identity_conflict["protocol_schema"])["reference_bundle"],
    )
    conflict_bundle["isoform_reference"] = conflict_bundle["canonical_protein_reference"]

    mismatched_profile = _profile_with(
        request.conformance_profile,
        approved_coordinate_profiles=(
            ApprovedCoordinateProfile(
                genome_convention=CoordinateConvention.ZERO_BASED_HALF_OPEN,
                transcript_convention=CoordinateConvention.ZERO_BASED_HALF_OPEN,
                protein_convention=CoordinateConvention.ZERO_BASED_HALF_OPEN,
                coordinate_mapping_version="99.0.0",
            ),
        ),
    )
    mismatch_result = evaluate_proteoform_protocol(
        _request(
            request.protocol_schema,
            mismatched_profile,
            label="coordinate_profile_mismatch_quarantined",
        )
    )
    reordered = _reordered_request(request)
    reordered_result = evaluate_proteoform_protocol(reordered)
    return [
        _scenario(
            "canonical_reference_bundle_conforms",
            passed=result.disposition is ProteoformProtocolConformanceDisposition.CONFORMANT,
            detail=f"disposition={result.disposition.value}",
        ),
        _scenario(
            "missing_isoform_reference_rejected",
            passed=_validation_rejected(missing_isoform),
            detail="required isoform reference omitted",
        ),
        _scenario(
            "mapping_cardinality_nonclosure_rejected",
            passed=_validation_rejected(nonclosing),
            detail="edge count is below mapped-record closure",
        ),
        _scenario(
            "artifact_identity_conflict_rejected",
            passed=_validation_rejected(identity_conflict),
            detail="two bundle roles share artifact identity and digest",
        ),
        _scenario(
            "coordinate_profile_mismatch_quarantined",
            passed=_quarantines_section(
                mismatch_result, ProteoformProtocolSection.COORDINATE_MAPPING
            ),
            detail=f"disposition={mismatch_result.disposition.value}",
        ),
        _scenario(
            "coordinate_declaration_reorder_invariant",
            passed=reordered == request and reordered_result == result,
            detail=f"complete_result_equality={reordered_result == result}",
        ),
    ]


def _evidence_isoform_checks() -> list[EvalCheck]:
    request = build_scenario_request("bottom_up_unique_evidence_conforms")
    canonical = evaluate_proteoform_protocol(request)
    eligibility = request.protocol_schema.evidence_eligibility
    without_intact_profile = _profile_with(
        request.conformance_profile,
        approved_evidence_classes=tuple(
            item
            for item in ProteoformEvidenceClass
            if item is not ProteoformEvidenceClass.INTACT_PROTEOFORM
        ),
    )
    without_intact = evaluate_proteoform_protocol(
        _request(
            request.protocol_schema,
            without_intact_profile,
            label="top_down_without_intact_proteoform_quarantined",
        )
    )

    splice = _request_payload(request)
    cast(
        "dict[str, Any]",
        cast("dict[str, Any]", splice["protocol_schema"])["evidence_eligibility"],
    )["splice_junction_requires_transcript_support"] = False
    variant = _request_payload(request)
    cast(
        "dict[str, Any]",
        cast("dict[str, Any]", variant["protocol_schema"])["evidence_eligibility"],
    )["sequence_variant_requires_genome_support"] = False
    shared = _request_payload(request)
    cast(
        "dict[str, Any]",
        cast("dict[str, Any]", shared["protocol_schema"])["isoform_discrimination"],
    )["shared_evidence_never_promotes_isoform"] = False

    isoform_payload = request.protocol_schema.isoform_discrimination.model_dump(mode="python")
    isoform_payload["minimum_independent_discriminators"] = 1
    insufficient_protocol = _protocol_with(
        request.protocol_schema,
        isoform_discrimination=IsoformDiscriminationPolicy.model_validate(
            isoform_payload, strict=True
        ),
    )
    insufficient = evaluate_proteoform_protocol(
        _request(
            insufficient_protocol,
            _profile(insufficient_protocol),
            label="insufficient_independent_discriminators_quarantined",
        )
    )
    return [
        _scenario(
            "bottom_up_unique_evidence_conforms",
            passed=(
                canonical.disposition is ProteoformProtocolConformanceDisposition.CONFORMANT
                and eligibility.uniqueness_relative_to_reference_bundle
            ),
            detail=f"disposition={canonical.disposition.value}",
        ),
        _scenario(
            "top_down_without_intact_proteoform_quarantined",
            passed=_quarantines_section(
                without_intact, ProteoformProtocolSection.EVIDENCE_ELIGIBILITY
            ),
            detail=f"disposition={without_intact.disposition.value}",
        ),
        _scenario(
            "splice_junction_without_transcript_support_rejected",
            passed=_validation_rejected(splice),
            detail="required literal transcript support disabled",
        ),
        _scenario(
            "sequence_variant_without_genome_support_rejected",
            passed=_validation_rejected(variant),
            detail="required literal genome support disabled",
        ),
        _scenario(
            "shared_evidence_member_promotion_rejected",
            passed=_validation_rejected(shared),
            detail="shared-evidence non-promotion disabled",
        ),
        _scenario(
            "insufficient_independent_discriminators_quarantined",
            passed=_quarantines_section(
                insufficient, ProteoformProtocolSection.ISOFORM_DISCRIMINATION
            ),
            detail=f"disposition={insufficient.disposition.value}",
        ),
    ]


def _ptm_checks() -> list[EvalCheck]:
    request = build_scenario_request("canonical_localization_policy_conforms")
    canonical = evaluate_proteoform_protocol(request)
    localization_payload = request.protocol_schema.modification_localization.model_dump(
        mode="python"
    )
    localization_payload["minimum_localized_probability_ppm"] = 899_999
    below_protocol = _protocol_with(
        request.protocol_schema,
        modification_localization=ModificationLocalizationPolicy.model_validate(
            localization_payload, strict=True
        ),
    )
    below = evaluate_proteoform_protocol(
        _request(
            below_protocol,
            _profile(below_protocol),
            label="localization_threshold_below_profile_quarantined",
        )
    )
    unlocalized = _request_payload(request)
    cast(
        "dict[str, Any]",
        cast("dict[str, Any]", unlocalized["protocol_schema"])["modification_localization"],
    )["unlocalized_is_not_absent"] = False
    residue = _request_payload(request)
    cast(
        "dict[str, Any]",
        cast("dict[str, Any]", residue["protocol_schema"])["modification_localization"],
    )["residue_reference_validation_required"] = False
    labile_profile = _profile_with(
        request.conformance_profile,
        approved_labile_modification_handlings=tuple(
            item
            for item in LabileModificationHandling
            if item is not LabileModificationHandling.PRESERVE_SITE_SET
        ),
    )
    labile = evaluate_proteoform_protocol(
        _request(
            request.protocol_schema,
            labile_profile,
            label="unapproved_labile_handling_quarantined",
        )
    )
    localization = request.protocol_schema.modification_localization
    return [
        _scenario(
            "canonical_localization_policy_conforms",
            passed=canonical.disposition is ProteoformProtocolConformanceDisposition.CONFORMANT,
            detail=f"disposition={canonical.disposition.value}",
        ),
        _scenario(
            "localization_threshold_below_profile_quarantined",
            passed=_quarantines_section(below, ProteoformProtocolSection.MODIFICATION_LOCALIZATION),
            detail=f"disposition={below.disposition.value}",
        ),
        _scenario(
            "ambiguous_site_set_preserved",
            passed=(
                localization.ambiguous_site_sets_preserved
                and ModificationLocalizationState.AMBIGUOUS_SITE_SET in localization.declared_states
                and canonical.disposition is ProteoformProtocolConformanceDisposition.CONFORMANT
            ),
            detail="ambiguous_site_set retained as an explicit state",
        ),
        _scenario(
            "unlocalized_as_absent_rejected",
            passed=_validation_rejected(unlocalized),
            detail="unlocalized preservation cannot be disabled",
        ),
        _scenario(
            "residue_validation_disabled_rejected",
            passed=_validation_rejected(residue),
            detail="residue validation cannot be disabled",
        ),
        _scenario(
            "unapproved_labile_handling_quarantined",
            passed=_quarantines_section(
                labile, ProteoformProtocolSection.MODIFICATION_LOCALIZATION
            ),
            detail=f"disposition={labile.disposition.value}",
        ),
    ]


def _quantification_handoff_checks() -> list[EvalCheck]:
    request = build_scenario_request("approved_quantification_pair_conforms")
    canonical = evaluate_proteoform_protocol(request)
    unapproved_profile = _profile_with(
        request.conformance_profile,
        approved_quantification_pairs=(
            ApprovedQuantificationPair(
                protein_unit=ProteinQuantificationUnit.MOLAR_FRACTION,
                transcript_unit=TranscriptQuantificationUnit.NORMALIZED_COUNT,
                protein_scale=ProteoformQuantificationScale.LINEAR,
                transcript_scale=ProteoformQuantificationScale.LINEAR,
            ),
        ),
    )
    unapproved = evaluate_proteoform_protocol(
        _request(
            request.protocol_schema,
            unapproved_profile,
            label="unapproved_quantification_pair_quarantined",
        )
    )
    zero = _request_payload(request)
    cast(
        "dict[str, Any]",
        cast("dict[str, Any]", zero["protocol_schema"])["quantification"],
    )["zero_is_observed_value"] = False
    incomplete = _request_payload(request)
    handoff = cast(
        "dict[str, Any]",
        cast("dict[str, Any]", incomplete["protocol_schema"])["discordance_handoff"],
    )
    handoff["required_receipt_roles"] = tuple(
        cast("tuple[object, ...]", handoff["required_receipt_roles"])[1:]
    )
    unsafe = _request_payload(request)
    cast(
        "dict[str, Any]",
        cast("dict[str, Any]", unsafe["protocol_schema"])["discordance_handoff"],
    )["emit_protein_rna_discordance"] = True
    unresolved = set(ProteoformUnresolvedState)
    return [
        _scenario(
            "approved_quantification_pair_conforms",
            passed=canonical.disposition is ProteoformProtocolConformanceDisposition.CONFORMANT,
            detail=f"disposition={canonical.disposition.value}",
        ),
        _scenario(
            "unapproved_quantification_pair_quarantined",
            passed=_quarantines_section(unapproved, ProteoformProtocolSection.QUANTIFICATION),
            detail=f"disposition={unapproved.disposition.value}",
        ),
        _scenario(
            "zero_without_observation_policy_rejected",
            passed=_validation_rejected(zero),
            detail="numeric zero requires an observed-value policy",
        ),
        _scenario(
            "missing_nondetected_below_lod_remain_distinct",
            passed={
                ProteoformUnresolvedState.MISSING,
                ProteoformUnresolvedState.NOT_DETECTED,
                ProteoformUnresolvedState.BELOW_DETECTION_LIMIT,
            }.issubset(unresolved)
            and len(unresolved) == EXPECTED_UNRESOLVED_STATE_COUNT,
            detail="three non-observed states remain distinct in the ten-state vocabulary",
        ),
        _scenario(
            "unsafe_or_incomplete_handoff_rejected",
            passed=_validation_rejected(incomplete) and _validation_rejected(unsafe),
            detail="both missing-role and discordance-emitting handoffs rejected",
        ),
    ]


def _identity_version_checks() -> list[EvalCheck]:
    request = build_scenario_request("exact_identity_and_versions_conform")
    canonical = evaluate_proteoform_protocol(request)
    missing = _request_payload(request)
    protocol = cast("dict[str, Any]", missing["protocol_schema"])
    protocol["required_identity_keys"] = tuple(
        cast("tuple[object, ...]", protocol["required_identity_keys"])[1:]
    )
    assay_profile = _profile_with(
        request.conformance_profile,
        approved_assay_protocol_versions=("99.0.0",),
    )
    assay = evaluate_proteoform_protocol(
        _request(
            request.protocol_schema,
            assay_profile,
            label="assay_version_mismatch_quarantined",
        )
    )
    metadata_profile = _profile_with(
        request.conformance_profile,
        approved_specimen_processing_versions=("99.0.0",),
        approved_controlled_vocabularies=(
            ApprovedControlledVocabulary(
                vocabulary_id=_oid("vocabulary", "outside"), version="99.0.0"
            ),
        ),
        approved_unit_system_versions=("99.0.0",),
    )
    metadata = evaluate_proteoform_protocol(
        _request(
            request.protocol_schema,
            metadata_profile,
            label="specimen_vocabulary_unit_mismatch_quarantined",
        )
    )
    omission = _request_payload(request)
    omission_protocol = cast("dict[str, Any]", omission["protocol_schema"])
    omission_protocol["declared_unresolved_states"] = tuple(
        cast("tuple[object, ...]", omission_protocol["declared_unresolved_states"])[1:]
    )
    conflation = _request_payload(request)
    conflation_protocol = cast("dict[str, Any]", conflation["protocol_schema"])
    states = list(cast("tuple[object, ...]", conflation_protocol["declared_unresolved_states"]))
    states[-1] = states[0]
    conflation_protocol["declared_unresolved_states"] = tuple(states)
    return [
        _scenario(
            "exact_identity_and_versions_conform",
            passed=(
                canonical.disposition is ProteoformProtocolConformanceDisposition.CONFORMANT
                and set(request.protocol_schema.required_identity_keys)
                == set(ProteoformIdentityKey)
            ),
            detail=f"identity_keys={len(request.protocol_schema.required_identity_keys)}",
        ),
        _scenario(
            "missing_identity_key_rejected",
            passed=_validation_rejected(missing),
            detail="one of seven identity keys omitted",
        ),
        _scenario(
            "assay_version_mismatch_quarantined",
            passed=_quarantines_section(assay, ProteoformProtocolSection.METADATA_VERSIONS),
            detail=f"disposition={assay.disposition.value}",
        ),
        _scenario(
            "specimen_vocabulary_unit_mismatch_quarantined",
            passed=_quarantines_section(metadata, ProteoformProtocolSection.METADATA_VERSIONS),
            detail=f"disposition={metadata.disposition.value}",
        ),
        _scenario(
            "unresolved_state_omission_or_conflation_rejected",
            passed=_validation_rejected(omission) and _validation_rejected(conflation),
            detail="both omission and duplicate-state conflation rejected",
        ),
    ]


def _profile_first_excesses_reject(
    profile: ReviewedProteoformConformanceProfile,
) -> tuple[bool, int]:
    base = profile.model_dump(mode="python")
    mutations: list[tuple[str, tuple[object, ...]]] = []
    mutations.append(
        (
            "approved_applicabilities",
            (*tuple(ProteoformApplicability), ProteoformApplicability.BOTTOM_UP_DIA),
        )
    )
    mutations.append(
        (
            "approved_reference_bundles",
            tuple(
                ApprovedProteoformReferenceBundle(
                    bundle_id=_oid("bundle", {"excess": index}),
                    version=f"50.0.{index}",
                    bundle_digest=sha256_digest({"excess_bundle": index}),
                )
                for index in range(M0401_MAX_APPROVED_REFERENCE_BUNDLES + 1)
            ),
        )
    )
    mutations.extend(
        (
            field,
            tuple(f"40.0.{index}" for index in range(M0401_MAX_APPROVED_VERSIONS + 1)),
        )
        for field in (
            "approved_assay_protocol_versions",
            "approved_specimen_processing_versions",
            "approved_unit_system_versions",
        )
    )
    mutations.append(
        (
            "approved_controlled_vocabularies",
            tuple(
                ApprovedControlledVocabulary(
                    vocabulary_id=_oid("vocabulary", {"excess": index}),
                    version=f"30.0.{index}",
                )
                for index in range(M0401_MAX_APPROVED_VERSIONS + 1)
            ),
        )
    )
    mutations.append(
        (
            "approved_coordinate_profiles",
            tuple(
                ApprovedCoordinateProfile(
                    genome_convention=CoordinateConvention.ONE_BASED_CLOSED,
                    transcript_convention=CoordinateConvention.ONE_BASED_CLOSED,
                    protein_convention=CoordinateConvention.ONE_BASED_CLOSED,
                    coordinate_mapping_version=f"20.0.{index}",
                )
                for index in range(M0401_MAX_COORDINATE_PROFILES + 1)
            ),
        )
    )
    quantification_values = tuple(
        ApprovedQuantificationPair(
            protein_unit=protein_unit,
            transcript_unit=transcript_unit,
            protein_scale=protein_scale,
            transcript_scale=transcript_scale,
        )
        for protein_unit, transcript_unit, protein_scale, transcript_scale in product(
            ProteinQuantificationUnit,
            TranscriptQuantificationUnit,
            ProteoformQuantificationScale,
            ProteoformQuantificationScale,
        )
    )
    mutations.append(
        (
            "approved_quantification_pairs",
            quantification_values[: M0401_MAX_QUANTIFICATION_PAIRS + 1],
        )
    )
    mutations.extend(
        (
            (
                "approved_evidence_classes",
                (*tuple(ProteoformEvidenceClass), ProteoformEvidenceClass.INTACT_PROTEOFORM),
            ),
            (
                "approved_labile_modification_handlings",
                (
                    *tuple(LabileModificationHandling),
                    LabileModificationHandling.PRESERVE_SITE_SET,
                ),
            ),
            (
                "approved_isoform_discriminators",
                (*tuple(ProteoformEvidenceClass), ProteoformEvidenceClass.INTACT_PROTEOFORM),
            ),
        )
    )
    rejected = 0
    for field, values in mutations:
        payload = {**base, field: values}
        try:
            ReviewedProteoformConformanceProfile.model_validate(payload, strict=True)
        except (ValidationError, ValueError):
            rejected += 1
    return rejected == len(mutations), len(mutations)


def _strict_caps_checks() -> list[EvalCheck]:
    request = build_scenario_request("semantic_set_reorder_same_digest")
    result = evaluate_proteoform_protocol(request)
    reordered = _reordered_request(request)
    reordered_result = evaluate_proteoform_protocol(reordered)

    unknown = _request_payload(request)
    unknown["unexpected"] = True
    coercion = _request_payload(request)
    coercion["contract_version"] = 1
    duplicate = _request_payload(request)
    duplicate_profile = cast("dict[str, Any]", duplicate["conformance_profile"])
    approved = cast("tuple[object, ...]", duplicate_profile["approved_reference_bundles"])
    duplicate_profile["approved_reference_bundles"] = (*approved, approved[0])
    stale = _request_payload(request)
    cast("dict[str, Any]", stale["conformance_profile"])["protocol_schema_digest"] = sha256_digest(
        "stale-schema-pin"
    )
    split = _request_payload(request)
    split["request_id"] = _oid("request", "split-from-context")

    maximum_request = build_scenario_request("maximum_profile_shape_conforms")
    maximum_result = evaluate_proteoform_protocol(maximum_request)
    maximum_profile = maximum_request.conformance_profile
    first_excesses_reject, excess_count = _profile_first_excesses_reject(maximum_profile)
    oversized = b'{"padding":"' + (b"x" * M0401_MAX_CANONICAL_REQUEST_BYTES) + b'"}'
    oversized_rejected = False
    try:
        M0401Plugin(M0401Service()).validate(oversized)
    except (ValidationError, ValueError):
        oversized_rejected = True
    maximum_shape = (
        len(maximum_profile.approved_applicabilities) == len(ProteoformApplicability)
        and len(maximum_profile.approved_reference_bundles) == M0401_MAX_APPROVED_REFERENCE_BUNDLES
        and len(maximum_profile.approved_assay_protocol_versions) == M0401_MAX_APPROVED_VERSIONS
        and len(maximum_profile.approved_specimen_processing_versions)
        == M0401_MAX_APPROVED_VERSIONS
        and len(maximum_profile.approved_controlled_vocabularies) == M0401_MAX_APPROVED_VERSIONS
        and len(maximum_profile.approved_unit_system_versions) == M0401_MAX_APPROVED_VERSIONS
        and len(maximum_profile.approved_coordinate_profiles) == M0401_MAX_COORDINATE_PROFILES
        and len(maximum_profile.approved_quantification_pairs) == M0401_MAX_QUANTIFICATION_PAIRS
        and maximum_profile.minimum_isoform_discriminators == M0401_MAX_ISOFORM_DISCRIMINATORS
    )
    return [
        _scenario(
            "semantic_set_reorder_same_digest",
            passed=(
                reordered == request
                and reordered_result == result
                and reordered_result.request_digest == result.request_digest
                and reordered_result.result_digest == result.result_digest
            ),
            detail=f"complete_digest_equality={reordered_result == result}",
        ),
        _scenario(
            "unknown_field_rejected",
            passed=_validation_rejected(unknown),
            detail="extra top-level field rejected",
        ),
        _scenario(
            "scalar_coercion_rejected",
            passed=_validation_rejected(coercion),
            detail="integer contract version is not coerced",
        ),
        _scenario(
            "duplicate_reviewed_entry_rejected",
            passed=_validation_rejected(duplicate),
            detail="duplicate reviewed bundle rejected",
        ),
        _scenario(
            "stale_profile_schema_pin_rejected",
            passed=_validation_rejected(stale),
            detail="profile-to-schema digest pin is stale",
        ),
        _scenario(
            "request_context_identifier_split_rejected",
            passed=_validation_rejected(split),
            detail="top-level and context request identifiers differ",
        ),
        _scenario(
            "maximum_profile_shape_conforms",
            passed=(
                maximum_shape
                and maximum_result.disposition
                is ProteoformProtocolConformanceDisposition.CONFORMANT
                and len(maximum_result.evidence) == M0401_EVIDENCE_COUNT
                and len(maximum_result.limitations) == M0401_LIMITATION_COUNT
            ),
            detail=(
                f"bundles={len(maximum_profile.approved_reference_bundles)};"
                f"quantification_pairs={len(maximum_profile.approved_quantification_pairs)}"
            ),
        ),
        _scenario(
            "each_first_excess_collection_cap_rejected",
            passed=first_excesses_reject,
            detail=f"rejected_collection_first_excesses={excess_count}",
        ),
        _scenario(
            "canonical_request_over_4mib_rejected",
            passed=oversized_rejected and len(oversized) > M0401_MAX_CANONICAL_REQUEST_BYTES,
            detail=f"submitted_bytes={len(oversized)}",
        ),
    ]


def _authorization_recovery_checks() -> list[EvalCheck]:
    request = build_scenario_request("each_unauthorized_control_denied_zero_traversal")
    denied_states = {
        "approved_configuration": "rejected",
        "identity_lineage": "unresolved",
        "provenance": "rejected",
        "consent": "withheld",
        "quality": "rejected",
        "support": "rejected",
        "intended_use": "rejected",
    }
    every_denied = True
    total_traversals = 0
    for role, state in denied_states.items():
        payload = request.model_dump(mode="python")
        cast("dict[str, Any]", cast("dict[str, Any]", payload["context"])["references"])[role][
            "state"
        ] = state
        hostile = _HostileDict(cast("dict[str, object]", payload["protocol_schema"]))
        payload["protocol_schema"] = hostile
        try:
            evaluate_proteoform_protocol(payload)
        except ProteoformProtocolAuthorizationError:
            pass
        else:
            every_denied = False
        total_traversals += hostile.traversals

    hostile_payload = request.model_dump(mode="python")
    references = cast(
        "dict[str, Any]", cast("dict[str, Any]", hostile_payload["context"])["references"]
    )
    references["consent"]["state"] = "withheld"
    hostile_protocol = _HostileDict(cast("dict[str, object]", hostile_payload["protocol_schema"]))
    hostile_payload["protocol_schema"] = hostile_protocol
    hostile_candidate = _HostileDict(hostile_payload)
    hostile_denied = False
    try:
        evaluate_proteoform_protocol(hostile_candidate)
    except ProteoformProtocolAuthorizationError:
        hostile_denied = True

    prior_profile = _profile_with(
        request.conformance_profile,
        approved_applicabilities=(ProteoformApplicability.TOP_DOWN,),
    )
    prior_request = _request(
        request.protocol_schema,
        prior_profile,
        label="prior-quarantined-request",
    )
    prior_result = evaluate_proteoform_protocol(prior_request)
    prior_snapshot = prior_result.model_dump_json()
    corrected = _request(
        request.protocol_schema,
        _profile(request.protocol_schema),
        label="corrected_superseding_request_succeeds",
        supersedes_result_digest=prior_result.result_digest,
    )
    corrected_result = evaluate_proteoform_protocol(corrected)
    return [
        _scenario(
            "each_unauthorized_control_denied_zero_traversal",
            passed=every_denied and total_traversals == 0,
            detail=f"denied_controls={len(denied_states)};traversals={total_traversals}",
        ),
        _scenario(
            "hostile_dict_subclass_denied_zero_traversal",
            passed=(
                hostile_denied
                and hostile_candidate.traversals == 0
                and hostile_protocol.traversals == 0
            ),
            detail=(
                f"candidate_traversals={hostile_candidate.traversals};"
                f"protocol_traversals={hostile_protocol.traversals}"
            ),
        ),
        _scenario(
            "corrected_superseding_request_succeeds",
            passed=(
                prior_result.disposition is ProteoformProtocolConformanceDisposition.QUARANTINED
                and corrected_result.disposition
                is ProteoformProtocolConformanceDisposition.CONFORMANT
                and prior_result.result_digest in corrected_result.provenance.input_digests
                and prior_result.model_dump_json() == prior_snapshot
            ),
            detail=(
                f"prior={prior_result.disposition.value};"
                f"corrected={corrected_result.disposition.value}"
            ),
        ),
    ]


def _result_rejected(payload: dict[str, Any]) -> bool:
    try:
        ProteoformProtocolConformanceResult.model_validate(payload, strict=True)
    except (ValidationError, ValueError):
        return True
    return False


def _privacy_ownership_checks() -> list[EvalCheck]:
    request = build_scenario_request("recursive_identifiers_are_opaque")
    result = evaluate_proteoform_protocol(request)
    references = request.context.references
    controls = (
        references.approved_configuration,
        references.identity_lineage,
        references.provenance,
        references.consent,
        references.quality,
        references.support,
        references.intended_use,
    )
    owned_ids = (
        request.request_id,
        request.context.request_id,
        request.context.actor_id,
        request.protocol_schema.schema_id,
        request.protocol_schema.controlled_vocabulary_id,
        request.protocol_schema.reference_bundle.bundle_id,
        request.conformance_profile.profile_id,
        request.conformance_profile.reviewed_by,
        *(item.decision_id for item in controls),
        *(item.reference.artifact_id for item in result.evidence),
    )
    opaque = all(OPAQUE_IDENTIFIER_PATTERN.fullmatch(value) for value in owned_ids)

    media_payload = _request_payload(request)
    cast(
        "dict[str, Any]",
        cast("dict[str, Any]", media_payload["protocol_schema"])["evidence"],
    )["media_type"] = "application/json"
    media_rejected = _validation_rejected(media_payload)

    canaries = (
        "MPEPTIDEK",
        "P12345",
        "ENSP00000354587",
        "chr7:140453136:A:T",
        "EGFRvIII",
        "patient-raw-001",
    )
    rendered = result.model_dump_json()

    stale_result = result.model_dump(mode="python")
    stale_result["result_digest"] = sha256_digest("forged-result")
    finding_forgery = result.model_dump(mode="python")
    cast("list[dict[str, Any]]", finding_forgery["findings"])[0]["reason_code"] = "forged"
    finding_forgery["result_digest"] = result_payload_digest(finding_forgery)

    receipt_forgery = result.model_dump(mode="python")
    receipt = cast("dict[str, Any]", receipt_forgery["receipt"])
    cast("list[dict[str, Any]]", receipt["sections"])[0]["section_digest"] = sha256_digest(
        "forged-section"
    )
    receipt["receipt_digest"] = receipt_digest(receipt)
    receipt_forgery["result_digest"] = result_payload_digest(receipt_forgery)
    evidence_forgery = result.model_dump(mode="python")
    cast("list[dict[str, Any]]", evidence_forgery["evidence"])[0]["claim"] = "forged"
    evidence_forgery["result_digest"] = result_payload_digest(evidence_forgery)
    provenance_forgery = result.model_dump(mode="python")
    cast("dict[str, Any]", provenance_forgery["provenance"])["configuration_digest"] = (
        sha256_digest("forged-provenance")
    )
    provenance_forgery["result_digest"] = result_payload_digest(provenance_forgery)

    flags = (
        result.emits_protein_rna_discordance,
        result.emits_proteogenomic_state,
        result.emits_proteotype,
        result.emits_protein_level_subtype,
        result.infers_proteoform_or_isoform,
        result.localizes_modification,
        result.infers_kinase_activity,
        result.performs_all_omics_fusion,
        result.recommends_treatment,
        result.mutates_upstream_evidence,
        result.infers_identity_or_consent,
    )
    return [
        _scenario(
            "recursive_identifiers_are_opaque",
            passed=opaque,
            detail=f"checked_owned_identifiers={len(owned_ids)}",
        ),
        _scenario(
            "artifact_media_type_allowlist_enforced",
            passed=media_rejected,
            detail="application/json rejected for M04-owned policy evidence",
        ),
        _scenario(
            "biological_canary_never_reflected",
            passed=not any(canary in rendered for canary in canaries),
            detail=f"checked_canaries={len(canaries)}",
        ),
        _scenario(
            "result_digest_or_finding_forgery_rejected",
            passed=_result_rejected(stale_result) and _result_rejected(finding_forgery),
            detail="stale digest and re-signed finding mutation rejected",
        ),
        _scenario(
            "receipt_evidence_or_provenance_forgery_rejected",
            passed=(
                _result_rejected(receipt_forgery)
                and _result_rejected(evidence_forgery)
                and _result_rejected(provenance_forgery)
            ),
            detail="re-signed receipt evidence and provenance mutations rejected",
        ),
        _scenario(
            "parent_and_all_authority_flags_exact",
            passed=result.parent_target == "protein_rna_discordance" and not any(flags),
            detail=f"parent={result.parent_target};false_authority_flags={len(flags)}",
        ),
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    corpus = _corpus()
    declared = {case_id for group in corpus["scenario_groups"] for case_id in group["case_ids"]}
    allocation = tuple(len(group["case_ids"]) for group in corpus["scenario_groups"])
    checks = [
        *_bundle_coordinate_checks(),
        *_evidence_isoform_checks(),
        *_ptm_checks(),
        *_quantification_handoff_checks(),
        *_identity_version_checks(),
        *_strict_caps_checks(),
        *_authorization_recovery_checks(),
        *_privacy_ownership_checks(),
    ]
    executed = {
        check.name.removeprefix("scenario.")
        for check in checks
        if check.name.startswith("scenario.")
    }
    missing = sorted(declared - executed)
    extra = sorted(executed - declared)
    checks.extend(
        (
            EvalCheck(
                name="corpus.locked_inventory",
                passed=(
                    corpus["module_id"] == MODULE_ID
                    and corpus["expected_group_count"] == EXPECTED_GROUP_COUNT
                    and corpus["expected_total_case_count"] == EXPECTED_CASE_COUNT
                    and len(corpus["scenario_groups"]) == EXPECTED_GROUP_COUNT
                    and len(declared) == EXPECTED_CASE_COUNT
                    and allocation == EXPECTED_ALLOCATION
                    and tuple(corpus["expected_case_allocation"]) == EXPECTED_ALLOCATION
                ),
                detail=(
                    f"groups={len(corpus['scenario_groups'])};"
                    f"declared={len(declared)};allocation={allocation}"
                ),
            ),
            EvalCheck(
                name="corpus.executable_coverage",
                passed=(
                    len(declared) == len(executed) == EXPECTED_CASE_COUNT
                    and not missing
                    and not extra
                ),
                detail=(
                    f"declared={len(declared)};executed={len(executed)};"
                    f"missing={missing};extra={extra}"
                ),
            ),
        )
    )
    passed = all(check.passed for check in checks)
    rendered = json.dumps(
        {
            "module_id": MODULE_ID,
            "passed": passed,
            "phase": "locked_executable_corpus",
            "declared_case_count": len(declared),
            "executed_case_count": len(executed),
            "missing_case_ids": missing,
            "extra_case_ids": extra,
            "checks": [asdict(check) for check in checks],
        },
        indent=2,
        sort_keys=True,
    )
    if arguments.output is None:
        sys.stdout.write(rendered + "\n")
    else:
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if passed else 1


__all__ = ["EvalCheck", "build_scenario_request", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
