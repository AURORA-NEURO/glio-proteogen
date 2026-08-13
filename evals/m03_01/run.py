"""Replay the locked M03-01 synthetic protein-inference protocol corpus."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, TypedDict, cast

from pydantic import ValidationError

from glio_proteogen.contracts.m03_01 import (
    AccessionAliasPolicy,
    AmbiguityReportingPolicy,
    ApprovedControlledVocabulary,
    ApprovedSearchSpace,
    ComplexActivityHandoffRequirements,
    DeclaredUnresolvedState,
    ErrorControlLevel,
    ErrorControlThreshold,
    EvaluateProteinInferenceProtocolRequest,
    HandoffReceiptRole,
    PeptideEvidenceEligibilityPolicy,
    PeptideToProteinAssignmentPolicy,
    ProteinErrorControlPolicy,
    ProteinErrorMeasure,
    ProteinGroupPolicy,
    ProteinInferenceApplicability,
    ProteinInferenceIdentityKey,
    ProteinInferenceProtocolConformanceResult,
    ProteinInferenceProtocolSchema,
    ProtocolConformanceDisposition,
    RazorTieBreak,
    RepresentativeSelection,
    ReviewedProteinInferenceConformanceProfile,
    SearchSpaceComposition,
    SearchSpaceReceipt,
    SharedPeptideStrategy,
    TargetDecoyStrategy,
    configuration_digest,
    protocol_digest,
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
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata import (
    ProteinInferenceProtocolAuthorizationError,
    evaluate_protein_inference_protocol,
    preflight_protein_inference_protocol_authorization,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M03-01"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m03_01" / "scenarios.json"
EXPECTED_GROUP_COUNT: Final = 8
EXPECTED_CASE_COUNT: Final = 44
EXPECTED_PROTOCOL_SECTION_COUNT: Final = 8
EXPECTED_HANDOFF_ROLE_COUNT: Final = 7
MAX_APPROVED_SEARCH_SPACES: Final = 256


class ScenarioGroup(TypedDict):
    group_id: str
    case_ids: list[str]


class Corpus(TypedDict):
    module_id: str
    schema_version: str
    data_classification: str
    claims_ceiling: str
    protocol_sections: list[str]
    handoff_role_count: int
    scenario_groups: list[ScenarioGroup]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m0301.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"m0301": label}),
        media_type="application/json",
    )


def _protocol() -> ProteinInferenceProtocolSchema:
    return ProteinInferenceProtocolSchema(
        schema_id="schema.synthetic.protein-inference",
        version="1.0.0",
        applicability=ProteinInferenceApplicability.SHOTGUN_DDA,
        assay_protocol_version="2.1.0",
        specimen_processing_version="1.4.0",
        controlled_vocabulary_id="vocabulary.synthetic.protein-inference",
        controlled_vocabulary_version="3.0.0",
        unit_system_version="1.0.0",
        required_identity_keys=tuple(ProteinInferenceIdentityKey),
        declared_unresolved_states=tuple(DeclaredUnresolvedState),
        search_space=SearchSpaceReceipt(
            namespace="reference.synthetic.human-proteome",
            release="2026.1.0",
            build_id="build.synthetic.targets-decoys-v1",
            content_digest=sha256_digest({"m0301": "search-space-content"}),
            composition=SearchSpaceComposition(
                canonical_sequences=20_000,
                isoform_sequences=4_000,
                variant_sequences=2_000,
                contaminant_sequences=64,
                decoy_sequences=26_064,
                target_sequences=26_064,
                total_sequences=52_128,
            ),
            target_decoy_strategy=TargetDecoyStrategy.CONCATENATED,
            accession_alias_policy=AccessionAliasPolicy(),
            canonical_sequence_reference=_artifact("canonical-sequences"),
            decoy_reference=_artifact("decoys"),
            isoform_reference=_artifact("isoforms"),
            variant_reference=_artifact("variants"),
            contaminant_reference=_artifact("contaminants"),
            evidence=_artifact("search-space-build"),
        ),
        error_control=ProteinErrorControlPolicy(
            target_decoy_strategy=TargetDecoyStrategy.CONCATENATED,
            thresholds=(
                ErrorControlThreshold(
                    level=ErrorControlLevel.PEPTIDE,
                    measure=ProteinErrorMeasure.Q_VALUE,
                    maximum=0.01,
                    scale="fraction",
                ),
                ErrorControlThreshold(
                    level=ErrorControlLevel.PROTEIN_GROUP,
                    measure=ProteinErrorMeasure.Q_VALUE,
                    maximum=0.01,
                    scale="fraction",
                ),
            ),
        ),
        peptide_eligibility=PeptideEvidenceEligibilityPolicy(
            min_length=7,
            max_length=45,
            max_missed_cleavages=2,
            max_variable_modifications=3,
            modification_vocabulary_reference=_artifact("modification-vocabulary"),
        ),
        assignment=PeptideToProteinAssignmentPolicy(
            shared_peptide_strategy=SharedPeptideStrategy.RAZOR,
            razor_tie_break=RazorTieBreak.HIGHEST_UNIQUE_PEPTIDE_COUNT,
        ),
        protein_grouping=ProteinGroupPolicy(
            representative_selection=RepresentativeSelection.MOST_UNIQUE_PEPTIDES,
        ),
        ambiguity=AmbiguityReportingPolicy(),
        complex_activity_handoff=ComplexActivityHandoffRequirements(
            required_receipt_roles=tuple(HandoffReceiptRole),
            evidence=_artifact("complex-handoff"),
        ),
        evidence=_artifact("protocol-schema"),
    )


def _profile(
    protocol: ProteinInferenceProtocolSchema,
) -> ReviewedProteinInferenceConformanceProfile:
    search = protocol.search_space
    return ReviewedProteinInferenceConformanceProfile(
        profile_id="profile.synthetic.protein-inference",
        version="1.0.0",
        protocol_schema_id=protocol.schema_id,
        protocol_schema_version=protocol.version,
        protocol_schema_digest=protocol_digest(protocol),
        approved_applicabilities=(protocol.applicability,),
        approved_search_spaces=(
            ApprovedSearchSpace(
                namespace=search.namespace,
                release=search.release,
                build_id=search.build_id,
                content_digest=search.content_digest,
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
        allowed_target_decoy_strategies=(TargetDecoyStrategy.CONCATENATED,),
        allowed_protein_error_measures=(ProteinErrorMeasure.Q_VALUE,),
        allowed_shared_peptide_strategies=(SharedPeptideStrategy.RAZOR,),
        allowed_representative_selections=(
            RepresentativeSelection.MOST_UNIQUE_PEPTIDES,
        ),
        max_psm_error_fraction=0.01,
        max_peptide_error_fraction=0.01,
        max_protein_group_error_fraction=0.01,
        min_peptide_length=7,
        max_peptide_length=45,
        max_missed_cleavages=2,
        max_variable_modifications=3,
        evidence=_artifact("reviewed-profile"),
        reviewed_by="reviewer.synthetic.bioinformatics",
        reviewed_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
    )


def _context(configuration: str) -> ExecutionContext:
    def decision(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.m0301.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{role}", digest),
        )

    return ExecutionContext(
        request_id="request.synthetic.m0301",
        actor_id="actor.synthetic.eval",
        occurred_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", configuration),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.m0301.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"m0301": "identity-subject"}),
                evidence=_artifact("control-identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.m0301.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control-consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _request(
    protocol: ProteinInferenceProtocolSchema,
    profile: ReviewedProteinInferenceConformanceProfile,
) -> EvaluateProteinInferenceProtocolRequest:
    return EvaluateProteinInferenceProtocolRequest(
        context=_context(configuration_digest(protocol, profile)),
        protocol_schema=protocol,
        conformance_profile=profile,
    )


def build_scenario_request(
    request_case: str = "canonical",
) -> EvaluateProteinInferenceProtocolRequest:
    """Build a strict public request used by eval, benchmark, and interface parity tests."""

    protocol = _protocol()
    profile = _profile(protocol)
    if request_case == "canonical":
        return _request(protocol, profile)
    alternate_search = profile.approved_search_spaces[0].model_copy(
        update={"content_digest": sha256_digest({"m0301": "other-search-space"})}
    )
    changes_by_case: dict[str, dict[str, object]] = {
        "applicability_not_approved": {
            "approved_applicabilities": (ProteinInferenceApplicability.DIA,)
        },
        "assay_protocol_version_not_approved": {
            "approved_assay_protocol_versions": ("9.0.0",)
        },
        "specimen_processing_version_not_approved": {
            "approved_specimen_processing_versions": ("9.0.0",)
        },
        "controlled_vocabulary_version_not_approved": {
            "approved_controlled_vocabularies": (
                ApprovedControlledVocabulary(
                    vocabulary_id=protocol.controlled_vocabulary_id,
                    version="9.0.0",
                ),
            )
        },
        "unit_system_version_not_approved": {
            "approved_unit_system_versions": ("9.0.0",)
        },
        "search_space_build_digest_mismatch": {
            "approved_search_spaces": (alternate_search,)
        },
        "target_decoy_strategy_not_reviewed": {
            "allowed_target_decoy_strategies": (TargetDecoyStrategy.SEPARATE,)
        },
        "competition_scope_mismatch": {
            "allowed_protein_error_measures": (ProteinErrorMeasure.PICKED_FDR,)
        },
        "shared_assignment_not_reviewed": {
            "allowed_shared_peptide_strategies": (SharedPeptideStrategy.EXCLUDE,)
        },
        "representative_selection_not_reviewed": {
            "allowed_representative_selections": (RepresentativeSelection.NONE,)
        },
        "peptide_eligibility_not_reviewed": {"max_peptide_length": 40},
    }
    try:
        changes = changes_by_case[request_case]
    except KeyError as error:
        raise ValueError(request_case) from error
    altered = profile.model_copy(update=changes)
    return _request(protocol, altered)


def _corpus() -> Corpus:
    return cast("Corpus", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _check_corpus(corpus: Corpus) -> EvalCheck:
    groups = corpus["scenario_groups"]
    cases = [case for group in groups for case in group["case_ids"]]
    passed = (
        corpus["module_id"] == MODULE_ID
        and len(groups) == EXPECTED_GROUP_COUNT
        and len({group["group_id"] for group in groups}) == EXPECTED_GROUP_COUNT
        and len(cases) == EXPECTED_CASE_COUNT
        and len(set(cases)) == EXPECTED_CASE_COUNT
        and corpus["handoff_role_count"] == len(HandoffReceiptRole)
    )
    return EvalCheck(
        name="corpus.exact_inventory",
        passed=passed,
        detail=f"groups={len(groups)};cases={len(cases)};handoff_roles={len(HandoffReceiptRole)}",
    )


def _scenario(case_id: str, *, passed: bool, detail: str) -> EvalCheck:
    return EvalCheck(name=f"scenario.{case_id}", passed=passed, detail=detail)


def _canonical_check() -> tuple[EvalCheck, ProteinInferenceProtocolConformanceResult]:
    result = evaluate_protein_inference_protocol(build_scenario_request())
    search = result.protocol_schema.search_space
    composition = search.composition
    passed = (
        result.disposition is ProtocolConformanceDisposition.CONFORMANT
        and len(result.findings) == EXPECTED_PROTOCOL_SECTION_COUNT
        and all(item.state.value == "pass" for item in result.findings)
        and len(result.protocol_schema.complex_activity_handoff.required_receipt_roles)
        == EXPECTED_HANDOFF_ROLE_COUNT
        and composition.target_sequences
        == composition.canonical_sequences
        + composition.isoform_sequences
        + composition.variant_sequences
        + composition.contaminant_sequences
        and composition.total_sequences
        == composition.target_sequences + composition.decoy_sequences
        and result.result_digest != "sha256:" + ("0" * 64)
    )
    return (
        _scenario(
            "canonical_exact_build",
            passed=passed,
            detail=result.result_digest,
        ),
        result,
    )


def _declaration_checks(
    result: ProteinInferenceProtocolConformanceResult,
) -> list[EvalCheck]:
    protocol = result.protocol_schema
    assignment = protocol.assignment
    grouping = protocol.protein_grouping
    ambiguity = protocol.ambiguity
    aliases = protocol.search_space.accession_alias_policy
    states = set(protocol.declared_unresolved_states)
    declarations = {
        "uniqueness_relative_to_exact_search_space_declared": (
            protocol.peptide_eligibility.uniqueness_relative_to_search_space
        ),
        "shared_group_only_policy_declared": (
            assignment.shared_peptides_support_group_claims_only
        ),
        "razor_member_nonpromotion_declared": (
            assignment.shared_peptide_strategy is SharedPeptideStrategy.RAZOR
            and assignment.razor_tie_break is not RazorTieBreak.NONE
            and assignment.razor_never_supports_member_specific_claim
        ),
        "indistinguishable_group_preservation_declared": (
            grouping.preserve_indistinguishable_members
        ),
        "representative_display_only_declared": (
            grouping.representative_is_display_only
            and grouping.representative_never_promotes_group_claim
        ),
        "pinned_variant_reference_and_discrimination_rule": (
            protocol.search_space.variant_reference is not None
            and protocol.search_space.composition.variant_sequences > 0
            and ambiguity.variant_claim_requires_pinned_reference
            and ambiguity.variant_claim_requires_eligible_discriminating_peptide
        ),
        "missing_discriminator_remains_unresolved_by_policy": (
            ambiguity.unresolved_is_not_negative
            and ambiguity.isoform_claim_requires_eligible_discriminating_peptide
            and ambiguity.variant_claim_requires_eligible_discriminating_peptide
        ),
        "ineligible_discriminator_nonpromotion_declared": (
            ambiguity.isoform_claim_requires_eligible_discriminating_peptide
            and ambiguity.variant_claim_requires_eligible_discriminating_peptide
        ),
        "shared_discriminator_nonpromotion_declared": (
            assignment.shared_peptides_support_group_claims_only
            and ambiguity.variant_claim_requires_eligible_discriminating_peptide
        ),
        "compatible_target_decoy_strategy": (
            protocol.search_space.target_decoy_strategy
            is protocol.error_control.target_decoy_strategy
        ),
        "exact_versioned_accession_policy_declared": aliases.versioned_accessions_required,
        "alias_collision_unresolved_policy_declared": aliases.collisions_remain_unresolved,
        "unversioned_guess_forbidden_policy_declared": aliases.unversioned_guesses_forbidden,
        "all_six_unresolved_states_declared": states == set(DeclaredUnresolvedState),
        "exact_seven_role_receipt": (
            set(protocol.complex_activity_handoff.required_receipt_roles)
            == set(HandoffReceiptRole)
            and len(protocol.complex_activity_handoff.required_receipt_roles)
            == EXPECTED_HANDOFF_ROLE_COUNT
        ),
    }
    return [
        _scenario(case_id, passed=passed, detail="closed protocol declaration")
        for case_id, passed in declarations.items()
    ]


def _quarantine_checks() -> list[EvalCheck]:
    cases = (
        ("applicability_not_approved", "applicability", True),
        ("assay_protocol_version_not_approved", "applicability", True),
        ("specimen_processing_version_not_approved", "applicability", True),
        ("controlled_vocabulary_version_not_approved", "applicability", True),
        ("unit_system_version_not_approved", "applicability", True),
        ("search_space_build_digest_mismatch", "search_space", True),
        ("target_decoy_strategy_not_reviewed", "error_control", True),
        ("competition_scope_mismatch", "error_control", True),
        ("shared_assignment_not_reviewed", "assignment", False),
        ("representative_selection_not_reviewed", "grouping", False),
        ("peptide_eligibility_not_reviewed", "peptide_eligibility", False),
    )
    checks: list[EvalCheck] = []
    for case, expected_section, fixture_case in cases:
        result = evaluate_protein_inference_protocol(build_scenario_request(case))
        failed = {item.section.value for item in result.findings if item.state.value != "pass"}
        name = f"scenario.{case}" if fixture_case else f"control.quarantine.{case}"
        checks.append(
            EvalCheck(
                name=name,
                passed=(
                    result.disposition is ProtocolConformanceDisposition.QUARANTINED
                    and expected_section in failed
                    and result.human_review_required
                ),
                detail=f"failed={','.join(sorted(failed)) or 'none'}",
            )
        )
    return checks


def _rejected_request(case_id: str, payload: dict[str, object]) -> EvalCheck:
    try:
        EvaluateProteinInferenceProtocolRequest.model_validate_json(
            json.dumps(payload),
            strict=True,
        )
    except ValidationError:
        return _scenario(
            case_id,
            passed=True,
            detail="strict request validation rejected",
        )
    return _scenario(
        case_id,
        passed=False,
        detail="strict request validation accepted",
    )


def _maximum_profile_request() -> EvaluateProteinInferenceProtocolRequest:
    request = build_scenario_request()
    primary = request.conformance_profile.approved_search_spaces[0]
    alternatives = tuple(
        ApprovedSearchSpace(
            namespace=f"reference.synthetic.alternate-{index}",
            release="1.0.0",
            build_id=f"build.synthetic.alternate-{index}",
            content_digest=sha256_digest({"m0301": "alternate-space", "index": index}),
        )
        for index in range(MAX_APPROVED_SEARCH_SPACES - 1)
    )
    payload = request.conformance_profile.model_dump(mode="python")
    payload["approved_search_spaces"] = (primary, *alternatives)
    profile = ReviewedProteinInferenceConformanceProfile.model_validate(payload, strict=True)
    return _request(request.protocol_schema, profile)


def _strict_rejection_checks(  # noqa: PLR0915 - one explicit mutation per evidence case.
    result: ProteinInferenceProtocolConformanceResult,
) -> list[EvalCheck]:
    request = build_scenario_request()
    checks: list[EvalCheck] = []

    payload = request.model_dump(mode="json")
    del payload["protocol_schema"]["search_space"]["canonical_sequence_reference"]
    checks.append(_rejected_request("missing_declared_component_rejected", payload))

    payload = request.model_dump(mode="json")
    payload["protocol_schema"]["search_space"]["variant_reference"] = None
    checks.append(_rejected_request("variant_reference_missing_rejected", payload))

    payload = request.model_dump(mode="json")
    payload["protocol_schema"]["error_control"]["target_decoy_strategy"] = "separate"
    checks.append(_rejected_request("search_error_strategy_mismatch_rejected", payload))

    payload = request.model_dump(mode="json")
    payload["protocol_schema"]["error_control"]["thresholds"][0]["scale"] = "percent"
    checks.append(_rejected_request("error_threshold_unit_mismatch", payload))

    payload = request.model_dump(mode="json")
    del payload["protocol_schema"]["peptide_eligibility"][
        "modification_vocabulary_reference"
    ]
    checks.append(_rejected_request("mandatory_reference_missing_rejected", payload))

    payload = request.model_dump(mode="json")
    payload["unexpected_field"] = "not_allowed"
    checks.append(_rejected_request("unknown_field_rejected", payload))

    payload = request.model_dump(mode="json")
    payload["protocol_schema"]["search_space"]["composition"]["total_sequences"] = "52128"
    checks.append(_rejected_request("coerced_scalar_rejected", payload))

    payload = request.model_dump(mode="json")
    del payload["protocol_schema"]["assay_protocol_version"]
    checks.append(_rejected_request("mandatory_field_missing_rejected", payload))

    payload = request.model_dump(mode="json")
    payload["protocol_schema"]["applicability"] = "unknown_assay"
    checks.append(_rejected_request("unknown_controlled_term_rejected", payload))

    result_payload = result.model_dump(mode="json")
    result_payload["result_digest"] = "sha256:" + ("f" * 64)
    try:
        ProteinInferenceProtocolConformanceResult.model_validate_json(
            json.dumps(result_payload),
            strict=True,
        )
    except ValidationError:
        checks.append(
            _scenario(
                "stale_derived_digest_rejected",
                passed=True,
                detail="result rejected",
            )
        )
    else:
        checks.append(
            _scenario(
                "stale_derived_digest_rejected",
                passed=False,
                detail="result accepted",
            )
        )

    payload = request.model_dump(mode="json")
    payload["conformance_profile"]["approved_search_spaces"].append(
        payload["conformance_profile"]["approved_search_spaces"][0]
    )
    checks.append(_rejected_request("duplicate_identifier_rejected", payload))

    payload = request.model_dump(mode="json")
    payload["protocol_schema"]["activity_score"] = 0.9
    checks.append(_rejected_request("unsafe_activity_claim_rejected", payload))

    maximum = _maximum_profile_request()
    payload = maximum.model_dump(mode="json")
    payload["conformance_profile"]["approved_search_spaces"].append(
        {
            "namespace": "reference.synthetic.first-excess",
            "release": "1.0.0",
            "build_id": "build.synthetic.first-excess",
            "content_digest": sha256_digest({"m0301": "first-excess"}),
        }
    )
    checks.append(_rejected_request("first_profile_excess_rejected", payload))

    payload = request.model_dump(mode="json")
    payload["protocol_schema"]["complex_activity_handoff"][
        "required_receipt_roles"
    ].pop()
    checks.append(_rejected_request("missing_handoff_role_rejected", payload))

    payload = request.model_dump(mode="json")
    payload["protocol_schema"]["complex_activity_handoff"][
        "required_receipt_roles"
    ].append("search_space")
    checks.append(_rejected_request("extra_handoff_role_rejected", payload))
    return checks


def _maximum_shape_check() -> EvalCheck:
    request = _maximum_profile_request()
    result = evaluate_protein_inference_protocol(request)
    return _scenario(
        "maximum_profile_shape_accepted",
        passed=len(request.conformance_profile.approved_search_spaces)
        == MAX_APPROVED_SEARCH_SPACES
        and result.disposition is ProtocolConformanceDisposition.CONFORMANT,
        detail=f"approved_search_spaces={MAX_APPROVED_SEARCH_SPACES}",
    )


def _semantic_reorder_check() -> EvalCheck:
    request = build_scenario_request()
    protocol = request.protocol_schema.model_copy(
        update={
            "required_identity_keys": tuple(
                reversed(request.protocol_schema.required_identity_keys)
            ),
            "declared_unresolved_states": tuple(
                reversed(request.protocol_schema.declared_unresolved_states)
            ),
            "error_control": request.protocol_schema.error_control.model_copy(
                update={
                    "thresholds": tuple(
                        reversed(request.protocol_schema.error_control.thresholds)
                    )
                }
            ),
            "complex_activity_handoff": request.protocol_schema.complex_activity_handoff.model_copy(
                update={
                    "required_receipt_roles": tuple(
                        reversed(
                            request.protocol_schema.complex_activity_handoff.required_receipt_roles
                        )
                    )
                }
            ),
        }
    )
    profile = request.conformance_profile.model_copy(
        update={
            "protocol_schema_digest": protocol_digest(protocol),
            "approved_applicabilities": tuple(
                reversed(request.conformance_profile.approved_applicabilities)
            ),
            "approved_search_spaces": tuple(
                reversed(request.conformance_profile.approved_search_spaces)
            ),
            "approved_assay_protocol_versions": tuple(
                reversed(request.conformance_profile.approved_assay_protocol_versions)
            ),
            "approved_specimen_processing_versions": tuple(
                reversed(request.conformance_profile.approved_specimen_processing_versions)
            ),
            "approved_controlled_vocabularies": tuple(
                reversed(request.conformance_profile.approved_controlled_vocabularies)
            ),
            "approved_unit_system_versions": tuple(
                reversed(request.conformance_profile.approved_unit_system_versions)
            ),
            "allowed_target_decoy_strategies": tuple(
                reversed(request.conformance_profile.allowed_target_decoy_strategies)
            ),
            "allowed_protein_error_measures": tuple(
                reversed(request.conformance_profile.allowed_protein_error_measures)
            ),
            "allowed_shared_peptide_strategies": tuple(
                reversed(request.conformance_profile.allowed_shared_peptide_strategies)
            ),
            "allowed_representative_selections": tuple(
                reversed(request.conformance_profile.allowed_representative_selections)
            ),
        }
    )
    reordered = _request(protocol, profile)
    left = evaluate_protein_inference_protocol(request)
    right = evaluate_protein_inference_protocol(reordered)
    return _scenario(
        "semantic_reorder_complete_equality",
        passed=left == right and left.model_dump_json() == right.model_dump_json(),
        detail=f"result_digest={left.result_digest}",
    )


def _authorization_checks() -> list[EvalCheck]:
    payload = build_scenario_request().model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["protocol_schema"] = object()
    try:
        preflight_protein_inference_protocol_authorization(payload)
    except ProteinInferenceProtocolAuthorizationError:
        consent = _scenario(
            "consent_denied_before_hostile_protocol",
            passed=True,
            detail="authorization rejected without protocol traversal",
        )
    else:
        consent = _scenario(
            "consent_denied_before_hostile_protocol",
            passed=False,
            detail="authorization not rejected",
        )
    payload = build_scenario_request().model_dump(mode="python")
    payload["context"]["references"]["identity_lineage"]["state"] = "unresolved"
    payload["protocol_schema"] = object()
    try:
        preflight_protein_inference_protocol_authorization(payload)
    except ProteinInferenceProtocolAuthorizationError:
        identity = _scenario(
            "identity_unresolved_before_hostile_protocol",
            passed=True,
            detail="authorization rejected without protocol traversal",
        )
    else:
        identity = _scenario(
            "identity_unresolved_before_hostile_protocol",
            passed=False,
            detail="authorization not rejected",
        )
    return [consent, identity]


def _boundary_check(result: ProteinInferenceProtocolConformanceResult) -> EvalCheck:
    forbidden = {
        "activity_score",
        "complex_activity_inference",
        "protein_subtype",
        "proteotype",
        "kinase_activity",
        "omics_fusion",
        "treatment_recommendation",
        "clinical_decision",
        "estimated_false_discovery_rate",
        "calibrated_probability",
        "negative_protein_finding",
        "protein_absence",
        "variant_absence",
    }
    rendered = json.dumps(result.model_dump(mode="json"), sort_keys=True)
    leaked = sorted(item for item in forbidden if item in rendered)
    ambiguity = result.protocol_schema.ambiguity
    assignment = result.protocol_schema.assignment
    passed = (
        not leaked
        and result.parent_target == "complex_activity"
        and result.receipt.parent_target == "complex_activity"
        and not result.protocol_schema.complex_activity_handoff.emit_activity_inference
        and ambiguity.unresolved_is_not_negative
        and ambiguity.variant_claim_requires_pinned_reference
        and ambiguity.variant_claim_requires_eligible_discriminating_peptide
        and assignment.shared_peptides_support_group_claims_only
        and assignment.razor_never_supports_member_specific_claim
        and result.protocol_schema.protein_grouping.preserve_indistinguishable_members
        and result.protocol_schema.protein_grouping.representative_is_display_only
    )
    return _scenario(
        "recursive_output_boundary",
        passed=passed,
        detail="closed protocol receipt" if passed else f"forbidden={','.join(leaked)}",
    )


def _coverage_check(corpus: Corpus, checks: list[EvalCheck]) -> EvalCheck:
    declared = {
        case_id
        for group in corpus["scenario_groups"]
        for case_id in group["case_ids"]
    }
    executed = {
        check.name.removeprefix("scenario.")
        for check in checks
        if check.name.startswith("scenario.")
    }
    return EvalCheck(
        name="coverage.every_declared_scenario_has_an_oracle",
        passed=declared == executed,
        detail=(
            f"declared={len(declared)};executed={len(executed)};"
            f"missing={','.join(sorted(declared - executed)) or 'none'};"
            f"extra={','.join(sorted(executed - declared)) or 'none'}"
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus = _corpus()
    canonical, result = _canonical_check()
    checks = [
        _check_corpus(corpus),
        canonical,
        *_declaration_checks(result),
        *_quarantine_checks(),
        *_strict_rejection_checks(result),
        _maximum_shape_check(),
        _semantic_reorder_check(),
        *_authorization_checks(),
        _boundary_check(result),
    ]
    checks.append(_coverage_check(corpus, checks))
    passed = all(check.passed for check in checks)
    report = {
        "module_id": MODULE_ID,
        "passed": passed,
        "scenario_group_count": len(corpus["scenario_groups"]),
        "scenario_case_count": sum(
            len(group["case_ids"]) for group in corpus["scenario_groups"]
        ),
        "corpus_digest": sha256_digest(corpus),
        "checks": [asdict(check) for check in checks],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
