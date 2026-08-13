"""Boundary and adversarial tests for M04-01 contracts."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

import pytest
from evals.m04_01.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m04_01 import (
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
    LabileModificationHandling,
    ProteinQuantificationUnit,
    ProteinRnaDiscordanceHandoffRequirements,
    ProteinRnaDiscordanceHandoffRole,
    ProteoformApplicability,
    ProteoformEvidenceClass,
    ProteoformIdentityKey,
    ProteoformProtocolConformanceResult,
    ProteoformProtocolFindingState,
    ProteoformProtocolReceipt,
    ProteoformProtocolSchema,
    ProteoformQuantificationScale,
    ProteoformReferenceBundle,
    ProteoformReferenceCardinality,
    ProteoformUnresolvedState,
    ReviewedProteoformConformanceProfile,
    TranscriptQuantificationUnit,
    canonical_request_digest,
    configuration_digest,
    expected_protocol_findings,
    opaque_proteoform_protocol_identifier,
    preflight_authorized,
    protocol_digest,
    receipt_digest,
    reference_bundle_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from tests.contract.test_m04_01_contract import build_request, build_result

if TYPE_CHECKING:
    from collections.abc import Iterator


def _payload(value: object) -> dict[str, Any]:
    return deepcopy(value.model_dump(mode="json"))  # type: ignore[attr-defined]


def _bound_request(
    protocol: ProteoformProtocolSchema,
    **profile_updates: object,
) -> EvaluateProteoformProtocolRequest:
    base = build_request()
    profile_payload = base.conformance_profile.model_dump(mode="python")
    profile_payload.update(
        {
            "protocol_schema_id": protocol.schema_id,
            "protocol_schema_version": protocol.version,
            "protocol_schema_digest": protocol_digest(protocol),
            **profile_updates,
        }
    )
    profile = ReviewedProteoformConformanceProfile.model_validate(profile_payload, strict=True)
    approved = base.context.references.approved_configuration
    rebound_evidence = approved.evidence.model_copy(
        update={"digest": configuration_digest(protocol, profile)}
    )
    rebound_approved = approved.model_copy(update={"evidence": rebound_evidence})
    references = base.context.references.model_copy(
        update={"approved_configuration": rebound_approved}
    )
    context = base.context.model_copy(update={"references": references})
    return EvaluateProteoformProtocolRequest.model_validate(
        {
            **base.model_dump(mode="python"),
            "context": context,
            "protocol_schema": protocol,
            "conformance_profile": profile,
        },
        strict=True,
    )


@pytest.mark.contract
@pytest.mark.parametrize(
    ("field", "maximum"),
    [
        ("gene_records", M0401_MAX_GENE_RECORDS),
        ("transcript_records", M0401_MAX_TRANSCRIPT_RECORDS),
        ("canonical_protein_sequences", M0401_MAX_CANONICAL_PROTEIN_SEQUENCES),
        ("isoform_sequences", M0401_MAX_ISOFORM_SEQUENCES),
        ("modification_terms", M0401_MAX_MODIFICATION_TERMS),
    ],
)
def test_reference_scalar_caps_reject_first_excess(field: str, maximum: int) -> None:
    base = {
        "gene_records": 1,
        "transcript_records": 1,
        "canonical_protein_sequences": 1,
        "isoform_sequences": 1,
        "mapped_transcripts": 1,
        "mapped_protein_sequences": 1,
        "transcript_protein_edges": 1,
        "modification_terms": 1,
    }
    valid = {**base, field: maximum}
    if field == "gene_records":
        valid["transcript_records"] = maximum
    if field in {"canonical_protein_sequences", "isoform_sequences"}:
        valid["mapped_protein_sequences"] = 1
    ProteoformReferenceCardinality.model_validate(valid, strict=True)
    with pytest.raises(ValidationError):
        ProteoformReferenceCardinality.model_validate({**valid, field: maximum + 1}, strict=True)


@pytest.mark.contract
def test_reference_joint_maximum_is_total_and_first_edge_excess_rejects() -> None:
    maximum = ProteoformReferenceCardinality(
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
    assert maximum.transcript_protein_edges == M0401_MAX_TRANSCRIPT_PROTEIN_EDGES
    payload = maximum.model_dump(mode="python")
    payload["transcript_protein_edges"] = M0401_MAX_TRANSCRIPT_PROTEIN_EDGES + 1
    with pytest.raises(ValidationError):
        ProteoformReferenceCardinality.model_validate(payload, strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"gene_records": 3, "transcript_records": 2}, "gene records"),
        ({"mapped_transcripts": 3, "transcript_records": 2}, "mapped transcripts"),
        (
            {
                "canonical_protein_sequences": 1,
                "isoform_sequences": 1,
                "mapped_protein_sequences": 3,
            },
            "mapped protein",
        ),
        (
            {
                "mapped_transcripts": 2,
                "mapped_protein_sequences": 2,
                "transcript_protein_edges": 1,
            },
            "edges do not close",
        ),
        (
            {
                "mapped_transcripts": 2,
                "mapped_protein_sequences": 2,
                "transcript_protein_edges": 5,
            },
            "edges do not close",
        ),
    ],
)
def test_reference_relational_cardinality_matrix(mutation: dict[str, int], message: str) -> None:
    payload = {
        "gene_records": 1,
        "transcript_records": 2,
        "canonical_protein_sequences": 1,
        "isoform_sequences": 1,
        "mapped_transcripts": 1,
        "mapped_protein_sequences": 1,
        "transcript_protein_edges": 1,
        "modification_terms": 1,
        **mutation,
    }
    with pytest.raises(ValidationError, match=message):
        ProteoformReferenceCardinality.model_validate(payload, strict=True)


@pytest.mark.contract
@pytest.mark.parametrize("field", ["artifact_id", "digest"])
def test_reference_bundle_requires_seven_distinct_artifacts(field: str) -> None:
    payload = _payload(build_request().protocol_schema.reference_bundle)
    source = payload["genome_reference"][field]
    payload["transcript_annotation_reference"][field] = source
    with pytest.raises(ValidationError, match="seven distinct"):
        ProteoformReferenceBundle.model_validate_json(canonical_json_bytes(payload), strict=True)


@pytest.mark.contract
def test_reference_bundle_digest_binds_cardinality_and_every_artifact() -> None:
    bundle = build_request().protocol_schema.reference_bundle
    original = reference_bundle_digest(bundle)
    payload = _payload(bundle)
    payload["cardinality"]["modification_terms"] += 1
    changed = ProteoformReferenceBundle.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )
    assert reference_bundle_digest(changed) != original


@pytest.mark.contract
@pytest.mark.parametrize(
    ("field", "limit"),
    [
        ("approved_reference_bundles", M0401_MAX_APPROVED_REFERENCE_BUNDLES),
        ("approved_assay_protocol_versions", M0401_MAX_APPROVED_VERSIONS),
        ("approved_specimen_processing_versions", M0401_MAX_APPROVED_VERSIONS),
        ("approved_controlled_vocabularies", M0401_MAX_APPROVED_VERSIONS),
        ("approved_unit_system_versions", M0401_MAX_APPROVED_VERSIONS),
        ("approved_coordinate_profiles", M0401_MAX_COORDINATE_PROFILES),
        ("approved_quantification_pairs", M0401_MAX_QUANTIFICATION_PAIRS),
    ],
)
def test_profile_collection_caps_accept_max_and_reject_first_excess(field: str, limit: int) -> None:
    profile = build_request().conformance_profile
    payload = profile.model_dump(mode="python")
    if field == "approved_reference_bundles":
        values: tuple[object, ...] = tuple(
            ApprovedProteoformReferenceBundle(
                bundle_id=f"bundle.{sha256_digest(f'bundle-{index}').removeprefix('sha256:')}",
                version="1.0.0",
                bundle_digest=sha256_digest(f"bundle-digest-{index}"),
            )
            for index in range(limit + 1)
        )
    elif field == "approved_coordinate_profiles":
        values = tuple(
            ApprovedCoordinateProfile(
                genome_convention=(
                    CoordinateConvention.ONE_BASED_CLOSED
                    if index % 2 == 0
                    else CoordinateConvention.ZERO_BASED_HALF_OPEN
                ),
                transcript_convention=CoordinateConvention.ONE_BASED_CLOSED,
                protein_convention=CoordinateConvention.ONE_BASED_CLOSED,
                coordinate_mapping_version=f"1.0.{index}",
            )
            for index in range(limit + 1)
        )
    elif field == "approved_controlled_vocabularies":
        values = tuple(
            ApprovedControlledVocabulary(
                vocabulary_id=(
                    f"vocabulary.{sha256_digest(f'vocabulary-{index}').removeprefix('sha256:')}"
                ),
                version=f"1.0.{index}",
            )
            for index in range(limit + 1)
        )
    elif field == "approved_quantification_pairs":
        combinations = (
            (protein, transcript, protein_scale, transcript_scale)
            for protein in ProteinQuantificationUnit
            for transcript in TranscriptQuantificationUnit
            for protein_scale in ProteoformQuantificationScale
            for transcript_scale in ProteoformQuantificationScale
        )
        values = tuple(
            ApprovedQuantificationPair(
                protein_unit=protein,
                transcript_unit=transcript,
                protein_scale=protein_scale,
                transcript_scale=transcript_scale,
            )
            for protein, transcript, protein_scale, transcript_scale in combinations
        )[: limit + 1]
    else:
        values = tuple(f"1.0.{index}" for index in range(limit + 1))
    payload[field] = values[:limit]
    ReviewedProteoformConformanceProfile.model_validate(payload, strict=True)
    payload[field] = values
    with pytest.raises(ValidationError):
        ReviewedProteoformConformanceProfile.model_validate(payload, strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("field", "values"),
    [
        ("approved_applicabilities", tuple(ProteoformApplicability)),
        ("approved_evidence_classes", tuple(ProteoformEvidenceClass)),
        (
            "approved_labile_modification_handlings",
            tuple(LabileModificationHandling),
        ),
        ("approved_isoform_discriminators", tuple(ProteoformEvidenceClass)),
    ],
)
def test_closed_profile_domain_caps_are_reachable_and_first_excess_rejects(
    field: str,
    values: tuple[object, ...],
) -> None:
    payload = build_request().conformance_profile.model_dump(mode="python")
    payload[field] = values
    ReviewedProteoformConformanceProfile.model_validate(payload, strict=True)
    payload[field] = (*values, values[0])
    with pytest.raises(ValidationError):
        ReviewedProteoformConformanceProfile.model_validate(payload, strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    "field",
    [
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
    ],
)
def test_profile_semantic_collections_reject_duplicates(field: str) -> None:
    payload = build_request().conformance_profile.model_dump(mode="python")
    values = payload[field]
    payload[field] = (*values[:-1], values[0]) if len(values) > 1 else (*values, values[0])
    with pytest.raises(ValidationError, match="unique"):
        ReviewedProteoformConformanceProfile.model_validate(payload, strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("minimum_isoform_discriminators", 0),
        ("minimum_isoform_discriminators", M0401_MAX_ISOFORM_DISCRIMINATORS + 1),
        ("minimum_localization_probability_ppm", -1),
        ("minimum_localization_probability_ppm", 1_000_001),
    ],
)
def test_profile_scalar_bounds_are_exact(field: str, value: int) -> None:
    payload = build_request().conformance_profile.model_dump(mode="python")
    payload[field] = value
    with pytest.raises(ValidationError):
        ReviewedProteoformConformanceProfile.model_validate(payload, strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("mutation", "failed_code"),
    [
        (
            {"approved_applicabilities": (ProteoformApplicability.TOP_DOWN,)},
            "applicability_unapproved",
        ),
        ({"approved_assay_protocol_versions": ("2.0.0",)}, "metadata_versions_unapproved"),
        ({"approved_reference_bundles": ()}, "reference_bundle_unapproved"),
        ({"approved_coordinate_profiles": ()}, "coordinate_mapping_incompatible"),
        (
            {"approved_evidence_classes": (ProteoformEvidenceClass.INTACT_PROTEOFORM,)},
            "evidence_eligibility_unapproved",
        ),
        ({"minimum_isoform_discriminators": 3}, "isoform_discrimination_unapproved"),
        ({"minimum_localization_probability_ppm": 900_000}, "modification_localization_unapproved"),
        ({"approved_quantification_pairs": ()}, "quantification_units_unapproved"),
    ],
)
def test_reviewed_domain_mismatch_maps_to_exact_finding(
    mutation: dict[str, object], failed_code: str
) -> None:
    request = build_request()
    payload = request.conformance_profile.model_dump(mode="python")
    # Empty collections are structurally invalid; use one alternate governed record instead.
    if "approved_reference_bundles" in mutation:
        mutation = {
            "approved_reference_bundles": (
                ApprovedProteoformReferenceBundle(
                    bundle_id=f"bundle.{sha256_digest('alternate').removeprefix('sha256:')}",
                    version="1.0.0",
                    bundle_digest=sha256_digest("alternate-bundle"),
                ),
            )
        }
    if "approved_coordinate_profiles" in mutation:
        mutation = {
            "approved_coordinate_profiles": (
                ApprovedCoordinateProfile(
                    genome_convention=CoordinateConvention.ZERO_BASED_HALF_OPEN,
                    transcript_convention=CoordinateConvention.ZERO_BASED_HALF_OPEN,
                    protein_convention=CoordinateConvention.ZERO_BASED_HALF_OPEN,
                    coordinate_mapping_version="2.0.0",
                ),
            )
        }
    if "approved_quantification_pairs" in mutation:
        mutation = {
            "approved_quantification_pairs": (
                ApprovedQuantificationPair(
                    protein_unit=ProteinQuantificationUnit.MOLAR_FRACTION,
                    transcript_unit=TranscriptQuantificationUnit.NORMALIZED_COUNT,
                    protein_scale=ProteoformQuantificationScale.LINEAR,
                    transcript_scale=ProteoformQuantificationScale.LINEAR,
                ),
            )
        }
    payload.update(mutation)
    profile = ReviewedProteoformConformanceProfile.model_validate(payload, strict=True)
    findings = expected_protocol_findings(request.protocol_schema, profile)
    failed = [item for item in findings if item.state is ProteoformProtocolFindingState.FAIL]
    assert [item.reason_code for item in failed] == [failed_code]


@pytest.mark.contract
@pytest.mark.parametrize(
    ("applicability", "eligible", "expected_reason"),
    [
        (
            ProteoformApplicability.TOP_DOWN,
            (ProteoformEvidenceClass.ISOFORM_UNIQUE_PEPTIDE,),
            "evidence_eligibility_unapproved",
        ),
        (
            ProteoformApplicability.TOP_DOWN,
            (ProteoformEvidenceClass.INTACT_PROTEOFORM,),
            None,
        ),
        (
            ProteoformApplicability.BOTTOM_UP_DIA,
            (ProteoformEvidenceClass.INTACT_PROTEOFORM,),
            "evidence_eligibility_unapproved",
        ),
        (
            ProteoformApplicability.BOTTOM_UP_DIA,
            (ProteoformEvidenceClass.TERMINAL_PEPTIDE,),
            None,
        ),
    ],
)
def test_assay_evidence_compatibility_is_typed_not_structural(
    applicability: ProteoformApplicability,
    eligible: tuple[ProteoformEvidenceClass, ...],
    expected_reason: str | None,
) -> None:
    base = build_request()
    protocol_payload = base.protocol_schema.model_dump(mode="python")
    protocol_payload["applicability"] = applicability
    protocol_payload["evidence_eligibility"]["eligible_evidence_classes"] = eligible
    protocol = ProteoformProtocolSchema.model_validate(protocol_payload, strict=True)
    request = _bound_request(
        protocol,
        approved_applicabilities=(applicability,),
    )
    failed = {
        finding.reason_code
        for finding in expected_protocol_findings(
            request.protocol_schema, request.conformance_profile
        )
        if finding.state is ProteoformProtocolFindingState.FAIL
    }
    assert failed == ({expected_reason} if expected_reason is not None else set())


@pytest.mark.contract
@pytest.mark.parametrize(
    ("profile_field", "equal_value", "adjacent_value", "reason_code"),
    [
        (
            "minimum_isoform_discriminators",
            2,
            3,
            "isoform_discrimination_unapproved",
        ),
        (
            "minimum_localization_probability_ppm",
            800_000,
            800_001,
            "modification_localization_unapproved",
        ),
    ],
)
def test_reviewed_minimum_thresholds_accept_equality_and_reject_adjacent(
    profile_field: str,
    equal_value: int,
    adjacent_value: int,
    reason_code: str,
) -> None:
    protocol = build_request().protocol_schema
    equal_request = _bound_request(protocol, **{profile_field: equal_value})
    assert all(
        item.state is ProteoformProtocolFindingState.PASS
        for item in expected_protocol_findings(
            equal_request.protocol_schema, equal_request.conformance_profile
        )
    )
    failed_request = _bound_request(protocol, **{profile_field: adjacent_value})
    assert {
        item.reason_code
        for item in expected_protocol_findings(
            failed_request.protocol_schema, failed_request.conformance_profile
        )
        if item.state is ProteoformProtocolFindingState.FAIL
    } == {reason_code}


@pytest.mark.contract
def test_singular_labile_handling_is_checked_against_reviewed_allowlist() -> None:
    protocol = build_request().protocol_schema
    conformant = _bound_request(
        protocol,
        approved_labile_modification_handlings=(LabileModificationHandling.PRESERVE_SITE_SET,),
    )
    assert all(
        item.state is ProteoformProtocolFindingState.PASS
        for item in expected_protocol_findings(
            conformant.protocol_schema, conformant.conformance_profile
        )
    )
    quarantined = _bound_request(
        protocol,
        approved_labile_modification_handlings=(LabileModificationHandling.UNSUPPORTED,),
    )
    failed = {
        item.reason_code
        for item in expected_protocol_findings(
            quarantined.protocol_schema, quarantined.conformance_profile
        )
        if item.state is ProteoformProtocolFindingState.FAIL
    }
    assert failed == {"modification_localization_unapproved"}


@pytest.mark.contract
@pytest.mark.parametrize(
    ("control", "state"),
    [
        ("approved_configuration", "rejected"),
        ("identity_lineage", "unresolved"),
        ("provenance", "unknown"),
        ("consent", "withheld"),
        ("quality", "rejected"),
        ("support", "unknown"),
        ("intended_use", "rejected"),
    ],
)
def test_preflight_rejects_every_unauthorized_control(control: str, state: str) -> None:
    payload = build_request().model_dump(mode="json")
    payload["context"]["references"][control]["state"] = state
    with pytest.raises(ValueError, match="accepted upstream controls"):
        preflight_authorized(payload)


class _HostileDict(dict[str, object]):
    traversals = 0

    def get(self, key: str, _default: object = None) -> object:
        self.traversals += 1
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        self.traversals += 1
        raise AssertionError


@pytest.mark.contract
def test_preflight_uses_builtin_dict_access_before_protocol_traversal() -> None:
    payload = build_request().model_dump(mode="json")
    hostile_protocol = _HostileDict(payload["protocol_schema"])
    candidate = _HostileDict(payload)
    candidate["protocol_schema"] = hostile_protocol
    preflight_authorized(candidate)
    assert candidate.traversals == 0
    assert hostile_protocol.traversals == 0


@pytest.mark.contract
def test_request_context_identifier_split_is_rejected() -> None:
    payload = build_request().model_dump(mode="python")
    payload["request_id"] = f"request.{sha256_digest('different-request').removeprefix('sha256:')}"
    with pytest.raises(ValidationError, match="authorized context identifier"):
        EvaluateProteoformProtocolRequest.model_validate(payload, strict=True)


@pytest.mark.contract
@pytest.mark.parametrize(
    "media_type",
    [
        "application/vnd.glio-proteogen.policy+json",
        "application/vnd.glio-proteogen.M04-01.policy+json",
        "application/vnd.glio-proteogen.m04-02.policy+json",
    ],
)
def test_module_owned_evidence_rejects_generic_foreign_and_uppercase_mime(
    media_type: str,
) -> None:
    payload = build_request().protocol_schema.model_dump(mode="python")
    evidence = payload["evidence_eligibility"]["evidence"]
    evidence["media_type"] = media_type
    with pytest.raises(ValidationError, match="lowercase allowlist"):
        ProteoformProtocolSchema.model_validate(payload, strict=True)


@pytest.mark.contract
def test_protocol_evidence_roles_require_distinct_artifacts_and_digests() -> None:
    payload = build_request().protocol_schema.model_dump(mode="python")
    payload["isoform_discrimination"]["evidence"] = deepcopy(
        payload["evidence_eligibility"]["evidence"]
    )
    with pytest.raises(ValidationError, match="distinct content digests"):
        ProteoformProtocolSchema.model_validate(payload, strict=True)


@pytest.mark.contract
def test_opaque_identifier_namespaces_and_lowercase_hex_are_exact() -> None:
    valid = f"schema.{sha256_digest('schema').removeprefix('sha256:')}"
    assert opaque_proteoform_protocol_identifier("schema", valid) == valid
    for invalid in (
        valid.replace("schema.", "profile."),
        valid.upper(),
        "schema.MPEPTIDEK",
    ):
        with pytest.raises(ValueError, match="opaque schema"):
            opaque_proteoform_protocol_identifier("schema", invalid)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("context", "request_id"), "request.MPEPTIDEK"),
        (("context", "actor_id"), "actor.MPEPTIDEK"),
        (
            ("context", "references", "consent", "decision_id"),
            "decision.MPEPTIDEK",
        ),
        (("protocol_schema", "schema_id"), "schema.MPEPTIDEK"),
        (("conformance_profile", "profile_id"), "profile.MPEPTIDEK"),
    ],
)
def test_biological_canaries_are_rejected_in_reflected_identifiers(
    path: tuple[str, ...], replacement: str
) -> None:
    payload = build_request().model_dump(mode="json")
    cursor: dict[str, Any] = payload
    for segment in path[:-1]:
        cursor = cursor[segment]
    cursor[path[-1]] = replacement
    with pytest.raises(ValidationError):
        EvaluateProteoformProtocolRequest.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


@pytest.mark.contract
def test_receipt_rejects_missing_duplicate_or_stale_section_and_digest() -> None:
    receipt = build_result().receipt
    cases = []
    missing = _payload(receipt)
    missing["sections"].pop()
    cases.append(missing)
    duplicate = _payload(receipt)
    duplicate["sections"][-1] = deepcopy(duplicate["sections"][0])
    duplicate["receipt_digest"] = receipt_digest(duplicate)
    cases.append(duplicate)
    stale = _payload(receipt)
    stale["receipt_digest"] = sha256_digest("stale")
    cases.append(stale)
    for payload in cases:
        with pytest.raises(ValidationError):
            ProteoformProtocolReceipt.model_validate_json(
                canonical_json_bytes(payload), strict=True
            )


@pytest.mark.contract
def test_standalone_receipt_rejects_resigned_disposition_section_contradiction() -> None:
    payload = _payload(build_result().receipt)
    payload["disposition"] = "quarantined"
    payload["receipt_digest"] = receipt_digest(payload)
    with pytest.raises(ValidationError, match="disposition contradicts section states"):
        ProteoformProtocolReceipt.model_validate_json(canonical_json_bytes(payload), strict=True)


@pytest.mark.contract
def test_supersession_is_bound_into_request_provenance_and_result() -> None:
    request = build_request()
    supersedes = sha256_digest("prior-result")
    changed = EvaluateProteoformProtocolRequest.model_validate(
        {**request.model_dump(mode="python"), "supersedes_result_digest": supersedes},
        strict=True,
    )
    result = build_result(changed)
    assert canonical_request_digest(changed) != canonical_request_digest(request)
    assert supersedes in result.provenance.input_digests
    forged = result.model_dump(mode="json")
    forged["request"]["supersedes_result_digest"] = sha256_digest("other-prior")
    forged["result_digest"] = result_payload_digest(forged)
    with pytest.raises(ValidationError):
        ProteoformProtocolConformanceResult.model_validate_json(
            canonical_json_bytes(forged), strict=True
        )


@pytest.mark.contract
def test_structural_exact_sets_cannot_be_downgraded_to_findings() -> None:
    request = build_request()
    cases = (
        ("required_identity_keys", tuple(ProteoformIdentityKey)[:-1]),
        ("declared_unresolved_states", tuple(ProteoformUnresolvedState)[:-1]),
    )
    for field, replacement in cases:
        payload = request.protocol_schema.model_dump(mode="python")
        payload[field] = replacement
        with pytest.raises(ValidationError):
            type(request.protocol_schema).model_validate(payload, strict=True)
    handoff = request.protocol_schema.discordance_handoff.model_dump(mode="python")
    handoff["required_receipt_roles"] = tuple(ProteinRnaDiscordanceHandoffRole)[:-1]
    with pytest.raises(ValidationError):
        ProteinRnaDiscordanceHandoffRequirements.model_validate(handoff, strict=True)


@pytest.mark.contract
def test_resigned_result_cannot_expand_any_authority_flag() -> None:
    result = build_result()
    flags = (
        "emits_protein_rna_discordance",
        "emits_proteogenomic_state",
        "emits_proteotype",
        "emits_protein_level_subtype",
        "infers_proteoform_or_isoform",
        "localizes_modification",
        "infers_kinase_activity",
        "performs_all_omics_fusion",
        "recommends_treatment",
        "mutates_upstream_evidence",
        "infers_identity_or_consent",
    )
    for flag in flags:
        payload = result.model_dump(mode="json")
        payload[flag] = True
        payload["result_digest"] = result_payload_digest(payload)
        with pytest.raises(ValidationError):
            ProteoformProtocolConformanceResult.model_validate_json(
                canonical_json_bytes(payload), strict=True
            )


@pytest.mark.contract
def test_public_maximum_profile_shape_executes_exact_result_replay_within_cap() -> None:
    request = build_scenario_request("maximum_profile_shape_conforms")
    assert len(request.conformance_profile.approved_reference_bundles) == (
        M0401_MAX_APPROVED_REFERENCE_BUNDLES
    )
    assert len(request.conformance_profile.approved_quantification_pairs) == (
        M0401_MAX_QUANTIFICATION_PAIRS
    )
    assert len(canonical_json_bytes(request)) <= M0401_MAX_CANONICAL_REQUEST_BYTES
    result = build_result(request)
    assert result.request == request
    assert result.disposition.value == "conformant"
