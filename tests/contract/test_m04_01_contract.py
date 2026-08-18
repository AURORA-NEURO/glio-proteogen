"""Contract tests for M04-01 proteoform protocol metadata."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import ValidationError

from glio_proteogen.contracts.m04_01 import (
    M0401_EVIDENCE_COUNT,
    M0401_HANDOFF_ROLE_COUNT,
    M0401_IDENTITY_KEY_COUNT,
    M0401_LIMITATION_COUNT,
    M0401_MAX_CANONICAL_REQUEST_BYTES,
    M0401_SECTION_COUNT,
    M0401_UNRESOLVED_STATE_COUNT,
    ApprovedControlledVocabulary,
    ApprovedCoordinateProfile,
    ApprovedProteoformReferenceBundle,
    ApprovedQuantificationPair,
    ContractName,
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
    ProteoformProtocolConformanceStatus,
    ProteoformProtocolFindingState,
    ProteoformProtocolSchema,
    ProteoformQuantificationPolicy,
    ProteoformQuantificationScale,
    ProteoformReferenceBundle,
    ProteoformReferenceCardinality,
    ProteoformUnresolvedState,
    ReviewedProteoformConformanceProfile,
    TranscriptQuantificationUnit,
    canonical_request_digest,
    configuration_digest,
    contract_json_schema,
    contract_json_schemas,
    expected_limitations,
    expected_protocol_findings,
    expected_protocol_receipt,
    expected_provenance,
    expected_support,
    expected_uncertainty,
    profile_digest,
    protocol_digest,
    protocol_evidence_index,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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

_SCHEMAS: tuple[ContractName, ...] = (
    "request",
    "output",
    "protocol",
    "profile",
    "reference-bundle",
    "reference-cardinality",
    "coordinate-policy",
    "evidence-eligibility-policy",
    "isoform-discrimination-policy",
    "modification-localization-policy",
    "quantification-policy",
    "discordance-handoff",
    "receipt",
)
_NOW = datetime(2026, 8, 13, 12, tzinfo=UTC)


def _hex(label: str) -> str:
    return sha256_digest(label).removeprefix("sha256:")


def _id(namespace: str, label: str) -> str:
    return f"{namespace}.{_hex(label)}"


def _artifact(label: str, media_type: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_id("evidence", label),
        version="1.0.0",
        digest=sha256_digest({"label": label}),
        media_type=media_type,
    )


def _protocol() -> ProteoformProtocolSchema:
    reference_media = "application/vnd.glio-proteogen.m04-01.reference+json"
    bundle = ProteoformReferenceBundle(
        bundle_id=_id("bundle", "canonical"),
        version="1.0.0",
        cardinality=ProteoformReferenceCardinality(
            gene_records=100,
            transcript_records=200,
            canonical_protein_sequences=100,
            isoform_sequences=100,
            mapped_transcripts=180,
            mapped_protein_sequences=180,
            transcript_protein_edges=200,
            modification_terms=50,
        ),
        genome_reference=_artifact("genome", reference_media),
        transcript_annotation_reference=_artifact("transcripts", reference_media),
        canonical_protein_reference=_artifact("canonical-proteins", reference_media),
        isoform_reference=_artifact("isoforms", reference_media),
        transcript_protein_mapping_reference=_artifact("mapping", reference_media),
        modification_vocabulary_reference=_artifact("modifications", reference_media),
        bundle_manifest_reference=_artifact(
            "bundle-manifest",
            "application/vnd.glio-proteogen.m04-01.manifest+json",
        ),
    )
    policy_media = "application/vnd.glio-proteogen.m04-01.policy+json"
    return ProteoformProtocolSchema(
        schema_id=_id("schema", "canonical"),
        version="1.0.0",
        applicability=ProteoformApplicability.BOTTOM_UP_DIA,
        assay_protocol_version="1.0.0",
        specimen_processing_version="1.0.0",
        controlled_vocabulary_id=_id("vocabulary", "canonical"),
        controlled_vocabulary_version="1.0.0",
        unit_system_version="1.0.0",
        required_identity_keys=tuple(ProteoformIdentityKey),
        declared_unresolved_states=tuple(ProteoformUnresolvedState),
        reference_bundle=bundle,
        coordinate_policy=ProteoformCoordinatePolicy(
            genome_convention=CoordinateConvention.ONE_BASED_CLOSED,
            transcript_convention=CoordinateConvention.ONE_BASED_CLOSED,
            protein_convention=CoordinateConvention.ONE_BASED_CLOSED,
            coordinate_mapping_version="1.0.0",
        ),
        evidence_eligibility=ProteoformEvidenceEligibilityPolicy(
            eligible_evidence_classes=tuple(ProteoformEvidenceClass),
            evidence=_artifact("eligibility", policy_media),
        ),
        isoform_discrimination=IsoformDiscriminationPolicy(
            accepted_discriminators=tuple(ProteoformEvidenceClass),
            minimum_independent_discriminators=2,
            evidence=_artifact("discrimination", policy_media),
        ),
        modification_localization=ModificationLocalizationPolicy(
            declared_states=tuple(ModificationLocalizationState),
            minimum_localized_probability_ppm=800_000,
            labile_modification_handling=LabileModificationHandling.PRESERVE_SITE_SET,
            evidence=_artifact("localization", policy_media),
        ),
        quantification=ProteoformQuantificationPolicy(
            protein_unit=ProteinQuantificationUnit.NORMALIZED_INTENSITY,
            transcript_unit=TranscriptQuantificationUnit.TPM,
            protein_scale=ProteoformQuantificationScale.LOG2,
            transcript_scale=ProteoformQuantificationScale.LOG2,
            evidence=_artifact("quantification", policy_media),
        ),
        discordance_handoff=ProteinRnaDiscordanceHandoffRequirements(
            required_receipt_roles=tuple(ProteinRnaDiscordanceHandoffRole),
            evidence=_artifact("handoff", policy_media),
        ),
        evidence=_artifact("protocol", policy_media),
    )


def _profile(protocol: ProteoformProtocolSchema) -> ReviewedProteoformConformanceProfile:
    return ReviewedProteoformConformanceProfile(
        profile_id=_id("profile", "canonical"),
        version="1.0.0",
        protocol_schema_id=protocol.schema_id,
        protocol_schema_version=protocol.version,
        protocol_schema_digest=protocol_digest(protocol),
        approved_applicabilities=(protocol.applicability,),
        approved_reference_bundles=(
            ApprovedProteoformReferenceBundle(
                bundle_id=protocol.reference_bundle.bundle_id,
                version=protocol.reference_bundle.version,
                bundle_digest=sha256_digest(protocol.reference_bundle.model_dump(mode="python")),
            ),
        ),
        approved_assay_protocol_versions=(protocol.assay_protocol_version,),
        approved_specimen_processing_versions=(protocol.specimen_processing_version,),
        approved_controlled_vocabularies=(
            ApprovedControlledVocabulary(
                vocabulary_id=protocol.controlled_vocabulary_id,
                version=protocol.controlled_vocabulary_version,
            ),
        ),
        approved_unit_system_versions=(protocol.unit_system_version,),
        approved_coordinate_profiles=(
            ApprovedCoordinateProfile(
                genome_convention=protocol.coordinate_policy.genome_convention,
                transcript_convention=protocol.coordinate_policy.transcript_convention,
                protein_convention=protocol.coordinate_policy.protein_convention,
                coordinate_mapping_version=(protocol.coordinate_policy.coordinate_mapping_version),
            ),
        ),
        approved_quantification_pairs=(
            ApprovedQuantificationPair(
                protein_unit=protocol.quantification.protein_unit,
                transcript_unit=protocol.quantification.transcript_unit,
                protein_scale=protocol.quantification.protein_scale,
                transcript_scale=protocol.quantification.transcript_scale,
            ),
        ),
        approved_evidence_classes=tuple(ProteoformEvidenceClass),
        approved_labile_modification_handlings=tuple(LabileModificationHandling),
        approved_isoform_discriminators=tuple(ProteoformEvidenceClass),
        minimum_isoform_discriminators=2,
        minimum_localization_probability_ppm=750_000,
        evidence=_artifact("profile", "application/vnd.glio-proteogen.m04-01.profile+json"),
        reviewed_by=_id("reviewer", "canonical"),
        reviewed_at=_NOW,
    )


def _context(configuration_hash: str) -> ExecutionContext:
    control_media = "application/vnd.glio-proteogen.control+json"

    def upstream(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        evidence = _artifact(role, control_media)
        if digest is not None:
            evidence = evidence.model_copy(update={"digest": digest})
        return UpstreamDecisionReference(
            decision_id=_id("decision", role),
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=evidence,
        )

    return ExecutionContext(
        request_id=_id("request", "canonical"),
        actor_id=_id("actor", "canonical"),
        occurred_at=_NOW,
        references=ContextReferences(
            approved_configuration=upstream("configuration", configuration_hash),
            identity_lineage=IdentityLineageReference(
                decision_id=_id("decision", "identity"),
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("identity-binding"),
                evidence=_artifact("identity", control_media),
            ),
            provenance=upstream("provenance"),
            consent=ConsentReference(
                decision_id=_id("decision", "consent"),
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent", control_media),
            ),
            quality=upstream("quality"),
            support=upstream("support"),
            intended_use=upstream("intended-use"),
        ),
    )


def build_request() -> EvaluateProteoformProtocolRequest:
    protocol = _protocol()
    profile = _profile(protocol)
    return EvaluateProteoformProtocolRequest(
        request_id=_id("request", "canonical"),
        context=_context(configuration_digest(protocol, profile)),
        protocol_schema=protocol,
        conformance_profile=profile,
    )


def build_result(
    request: EvaluateProteoformProtocolRequest | None = None,
) -> ProteoformProtocolConformanceResult:
    active = request if request is not None else build_request()
    findings = expected_protocol_findings(active.protocol_schema, active.conformance_profile)
    receipt = expected_protocol_receipt(active)
    failed = any(item.state is ProteoformProtocolFindingState.FAIL for item in findings)
    disposition = (
        ProteoformProtocolConformanceDisposition.QUARANTINED
        if failed
        else ProteoformProtocolConformanceDisposition.CONFORMANT
    )
    request_hash = canonical_request_digest(active)
    payload: dict[str, Any] = {
        "result_id": f"result.m0401.{request_hash.removeprefix('sha256:')}",
        "request_digest": request_hash,
        "protocol_digest": protocol_digest(active.protocol_schema),
        "profile_digest": profile_digest(active.conformance_profile),
        "configuration_digest": configuration_digest(
            active.protocol_schema, active.conformance_profile
        ),
        "result_digest": "sha256:" + ("1" * 64),
        "request": active,
        "receipt": receipt,
        "findings": findings,
        "status": (
            ProteoformProtocolConformanceStatus.NONCONFORMANT
            if failed
            else ProteoformProtocolConformanceStatus.CONFORMANT
        ),
        "disposition": disposition,
        "infers_protein": False,
        "infers_proteoform": False,
        "infers_isoform": False,
        "infers_glioma_specific_biology": False,
        "support": expected_support(disposition),
        "uncertainty": expected_uncertainty(),
        "provenance": expected_provenance(active, receipt),
        "evidence": protocol_evidence_index(active),
        "limitations": expected_limitations(),
        "human_review_required": failed,
        "completed_at": active.context.occurred_at,
    }
    payload["result_digest"] = result_payload_digest(payload)
    return ProteoformProtocolConformanceResult.model_validate(payload, strict=True)


@pytest.mark.contract
def test_public_schema_surface_is_exact_strict_and_authority_bounded() -> None:
    assert tuple(contract_json_schemas()) == _SCHEMAS
    for name in _SCHEMAS:
        schema = contract_json_schema(name)
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == (
            f"urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-01:1.0.0:{name}"
        )
        assert schema["additionalProperties"] is False
        metadata = cast("dict[str, Any]", schema["x-glio-contract"])
        assert metadata["strict"] is True
        assert metadata["signalValues"] is False
        assert metadata["scientificInference"] is False
        assert metadata["parentTarget"] == "protein_rna_discordance"
        if name == "request":
            assert metadata["maxRequestBytes"] == M0401_MAX_CANONICAL_REQUEST_BYTES
        for definition in cast("dict[str, dict[str, Any]]", schema.get("$defs", {})).values():
            if definition.get("type") == "object":
                assert definition["additionalProperties"] is False


@pytest.mark.contract
def test_exact_enumeration_cardinalities_and_evidence_envelope() -> None:
    request = build_request()
    result = build_result(request)
    assert len(ProteoformIdentityKey) == M0401_IDENTITY_KEY_COUNT
    assert len(ProteoformUnresolvedState) == M0401_UNRESOLVED_STATE_COUNT
    assert len(ProteinRnaDiscordanceHandoffRole) == M0401_HANDOFF_ROLE_COUNT
    assert len(result.findings) == M0401_SECTION_COUNT
    assert len(result.receipt.sections) == M0401_SECTION_COUNT
    assert len(result.evidence) == M0401_EVIDENCE_COUNT
    assert len(result.limitations) == M0401_LIMITATION_COUNT


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("unexpected",), True),
        (("protocol_schema", "unexpected"), True),
        (("protocol_schema", "reference_bundle", "unexpected"), True),
        (("conformance_profile", "unexpected"), True),
    ],
)
def test_unknown_fields_are_rejected_at_major_boundaries(
    path: tuple[str, ...], value: object
) -> None:
    payload = build_request().model_dump(mode="json")
    cursor: dict[str, Any] = payload
    for segment in path[:-1]:
        cursor = cursor[segment]
    cursor[path[-1]] = value
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvaluateProteoformProtocolRequest.model_validate(payload, strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("protocol_schema", "reference_bundle", "cardinality", "gene_records"), "100"),
        (("protocol_schema", "modification_localization", "higher_is_more_localized"), 1),
        (("conformance_profile", "minimum_isoform_discriminators"), 2.0),
    ],
)
def test_python_validation_does_not_coerce_scalars(path: tuple[str, ...], value: object) -> None:
    payload = build_request().model_dump(mode="python")
    cursor: dict[str, Any] = payload
    for segment in path[:-1]:
        cursor = cursor[segment]
    cursor[path[-1]] = value
    with pytest.raises(ValidationError):
        EvaluateProteoformProtocolRequest.model_validate(payload, strict=True)


@pytest.mark.contract
def test_request_semantic_reordering_materializes_full_equality() -> None:
    request = build_request()
    payload = request.model_dump(mode="json")
    paths = (
        ("protocol_schema", "required_identity_keys"),
        ("protocol_schema", "declared_unresolved_states"),
        ("protocol_schema", "evidence_eligibility", "eligible_evidence_classes"),
        ("protocol_schema", "isoform_discrimination", "accepted_discriminators"),
        ("protocol_schema", "modification_localization", "declared_states"),
        ("protocol_schema", "discordance_handoff", "required_receipt_roles"),
        ("conformance_profile", "approved_evidence_classes"),
        ("conformance_profile", "approved_labile_modification_handlings"),
        ("conformance_profile", "approved_isoform_discriminators"),
    )
    for path in paths:
        cursor: Any = payload
        for segment in path:
            cursor = cursor[segment]
        cursor.reverse()
    rebuilt = EvaluateProteoformProtocolRequest.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )
    assert rebuilt == request
    assert canonical_request_digest(rebuilt) == canonical_request_digest(request)


@pytest.mark.contract
def test_result_semantic_reordering_materializes_full_equality() -> None:
    result = build_result()
    payload = result.model_dump(mode="json")
    for path in (
        ("findings",),
        ("receipt", "sections"),
        ("evidence",),
        ("limitations",),
        ("provenance", "input_digests"),
        ("provenance", "control_decisions"),
        ("uncertainty", "sensitivity_notes"),
    ):
        cursor: Any = payload
        for segment in path:
            cursor = cursor[segment]
        cursor.reverse()
    rebuilt = ProteoformProtocolConformanceResult.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )
    assert rebuilt == result
    assert rebuilt.result_digest == result.result_digest


@pytest.mark.contract
@pytest.mark.parametrize(
    "path",
    [
        ("request_digest",),
        ("protocol_digest",),
        ("profile_digest",),
        ("configuration_digest",),
        ("receipt", "reference_bundle_digest"),
        ("receipt", "sections", 0, "section_digest"),
        ("findings", 0, "reason_code"),
        ("support", "reason_code"),
        ("provenance", "configuration_digest"),
        ("evidence", 0, "claim"),
        ("limitations", 0, "statement"),
    ],
)
def test_resigned_result_forgery_matrix_is_rejected(path: tuple[str | int, ...]) -> None:
    payload = build_result().model_dump(mode="json")
    cursor: Any = payload
    for segment in path[:-1]:
        cursor = cursor[segment]
    leaf = path[-1]
    cursor[leaf] = (
        sha256_digest("forged")
        if isinstance(cursor[leaf], str) and cursor[leaf].startswith("sha256:")
        else "forged"
    )
    if path[0] == "receipt":
        payload["receipt"]["receipt_digest"] = sha256_digest(
            {**payload["receipt"], "receipt_digest": "sha256:" + ("0" * 64)}
        )
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError):
        ProteoformProtocolConformanceResult.model_validate(payload, strict=True)


@pytest.mark.contract
def test_result_digest_missing_zero_and_stale_are_rejected() -> None:
    result = build_result()
    missing = result.model_dump(mode="json")
    missing.pop("result_digest")
    zero = result.model_dump(mode="json")
    zero["result_digest"] = "sha256:" + ("0" * 64)
    stale = result.model_dump(mode="json")
    stale["result_digest"] = sha256_digest("stale")
    for payload in (missing, zero, stale):
        with pytest.raises(ValidationError):
            ProteoformProtocolConformanceResult.model_validate(payload, strict=True)


@pytest.mark.contract
def test_all_pass_and_one_fail_envelopes_are_deterministic() -> None:
    conformant = build_result()
    assert conformant.status is ProteoformProtocolConformanceStatus.CONFORMANT
    assert conformant.disposition is ProteoformProtocolConformanceDisposition.CONFORMANT
    assert conformant.human_review_required is False
    payload = build_request().model_dump(mode="python")
    payload["conformance_profile"] = deepcopy(payload["conformance_profile"])
    payload["conformance_profile"]["approved_applicabilities"] = (ProteoformApplicability.TOP_DOWN,)
    changed_profile = ReviewedProteoformConformanceProfile.model_validate(
        payload["conformance_profile"], strict=True
    )
    changed_protocol = cast("ProteoformProtocolSchema", payload["protocol_schema"])
    payload["context"] = _context(configuration_digest(changed_protocol, changed_profile))
    request = EvaluateProteoformProtocolRequest.model_validate(payload, strict=True)
    quarantined = build_result(request)
    assert quarantined.status is ProteoformProtocolConformanceStatus.NONCONFORMANT
    assert quarantined.disposition is ProteoformProtocolConformanceDisposition.QUARANTINED
    assert quarantined.human_review_required is True
    assert {item.reason_code for item in quarantined.findings if item.state.value == "fail"} == {
        "applicability_unapproved"
    }
