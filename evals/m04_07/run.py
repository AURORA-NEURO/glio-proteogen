"""Build and execute the locked M04-07 proteoform support corpus."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, TypedDict, cast

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m04_04.run import build_scenario_request as build_m0404_request
from evals.m04_05 import run as m0405_evidence
from evals.m04_06 import run as m0406_evidence
from evals.m04_06.run import build_scenario_request as build_m0406_request
from glio_proteogen.contracts.m04_01 import ProteoformApplicability
from glio_proteogen.contracts.m04_04 import (
    ProteoformQualityMetricStatus,
)
from glio_proteogen.contracts.m04_06 import (
    HarmonizeProteoformAnalysisRequest,
    ProteoformNormalizationFactor,
    ProteoformNormalizationFactorLevel,
    artifact_harmonization_receipt,
    opaque_harmonization_identifier,
)
from glio_proteogen.contracts.m04_06 import (
    configuration_digest as harmonization_configuration_digest,
)
from glio_proteogen.contracts.m04_07 import (
    M0407_MAX_ANALYSIS_TARGETS,
    ProteoformAbstentionCode,
    ProteoformContextReceipt,
    ProteoformContextRole,
    ProteoformDeclaredSupportFact,
    ProteoformDeclaredSupportState,
    ProteoformDimensionRemediation,
    ProteoformDimensionSupportDecision,
    ProteoformRemediationPath,
    ProteoformSupportDimension,
    ProteoformSupportDisposition,
    ProteoformSupportEnvelope,
    ProteoformSupportPolicy,
    ProteoformSupportPrerequisites,
    ProteoformSupportProfile,
    ProteoformSupportRouteResult,
    RouteProteoformSupportRequest,
    configuration_digest,
    opaque_support_identifier,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, SupportStatus
from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics import (
    compute_proteoform_quality_metrics,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_06_harmonization import (
    harmonize_proteoform_analysis,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router import (
    ProteoformSupportAuthorizationError,
    preflight_proteoform_support_authorization,
    proteoform_support_prerequisites,
    route_proteoform_support,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m04_04 import ProteoformQualityResult
    from glio_proteogen.contracts.m04_05 import ProteoformArtifactDetectionResult
    from glio_proteogen.contracts.m04_06 import ProteoformHarmonizationResult

MODULE_ID: Final = "GLIO-PROTEOGEN-M04-07"
OUTSIDE_COMPLETENESS_THRESHOLD_PPM: Final = 700_000
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m04_07" / "scenarios.json"
_EXPECTED_GROUP_COUNT: Final = 8
_EXPECTED_CASE_COUNT: Final = 19


class ScenarioGroup(TypedDict):
    group_id: str
    case_ids: list[str]


class Corpus(TypedDict):
    module_id: str
    scenario_groups: list[ScenarioGroup]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class Scenario:
    """One genuine M04-04/M04-06 chain and its closed M04-07 request."""

    request: RouteProteoformSupportRequest
    quality_result: ProteoformQualityResult
    harmonization_result: ProteoformHarmonizationResult


class ScenarioClosureError(ValueError):
    """The genuine prerequisite chain could not form the canonical route."""


class _HostileEvidence(Mapping[str, object]):
    def __init__(self) -> None:
        self.traversals = 0

    def __getitem__(self, key: str) -> object:
        self.traversals += 1
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        self.traversals += 1
        raise AssertionError

    def __len__(self) -> int:
        self.traversals += 1
        raise AssertionError


def _oid(namespace: str, value: object) -> str:
    digest = sha256_digest({"namespace": namespace, "value": value}).removeprefix("sha256:")
    return opaque_support_identifier(namespace, f"{namespace}.{digest}")


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_oid("evidence", {"m0407_evidence": label}),
        version="1.0.0",
        digest=sha256_digest({"m0407_evidence": label}),
        media_type="application/json",
    )


def _remediations() -> tuple[ProteoformDimensionRemediation, ...]:
    paths = {
        ProteoformSupportDimension.ASSAY: (ProteoformRemediationPath.CORRECT_SUPPORT_DECLARATION),
        ProteoformSupportDimension.SPECIMEN: (
            ProteoformRemediationPath.CORRECT_SUPPORT_DECLARATION
        ),
        ProteoformSupportDimension.DISEASE_CLASS: (
            ProteoformRemediationPath.CORRECT_SUPPORT_DECLARATION
        ),
        ProteoformSupportDimension.QUALITY: (
            ProteoformRemediationPath.RESOLVE_UPSTREAM_PREREQUISITE
        ),
        ProteoformSupportDimension.COMPLETENESS: (
            ProteoformRemediationPath.SUPPLY_REQUIRED_SUPPORT_EVIDENCE
        ),
        ProteoformSupportDimension.PLATFORM: (
            ProteoformRemediationPath.REQUEST_GOVERNED_SUPPORT_REVIEW
        ),
        ProteoformSupportDimension.REFERENCE: (
            ProteoformRemediationPath.SUPPLY_REQUIRED_SUPPORT_EVIDENCE
        ),
        ProteoformSupportDimension.INTENDED_USE: (
            ProteoformRemediationPath.SELECT_ONE_REVIEWED_JOINT_ENVELOPE
        ),
    }
    return tuple(
        ProteoformDimensionRemediation(
            dimension=dimension,
            outside_reason_code=_oid("reason", {"dimension": dimension.value, "state": "outside"}),
            indeterminate_reason_code=_oid(
                "reason", {"dimension": dimension.value, "state": "indeterminate"}
            ),
            remediation_code=_oid("remediation", {"dimension": dimension.value}),
            remediation_path=paths[dimension],
        )
        for dimension in ProteoformSupportDimension
    )


def _observed_fact(
    dimension: Literal[
        ProteoformSupportDimension.SPECIMEN,
        ProteoformSupportDimension.DISEASE_CLASS,
        ProteoformSupportDimension.REFERENCE,
        ProteoformSupportDimension.INTENDED_USE,
    ],
    namespace: str,
    label: str,
) -> ProteoformDeclaredSupportFact:
    return ProteoformDeclaredSupportFact(
        dimension=dimension,
        state=ProteoformDeclaredSupportState.OBSERVED,
        values=(_oid(namespace, {"canonical_fact": label}),),
        evidence=(_artifact(f"fact-{label}"),),
    )


def build_scenario() -> Scenario:
    """Execute genuine M04-04/M04-06 operations and close one supported route."""

    harmonization_result = harmonize_proteoform_analysis(build_m0406_request())
    quality_result = harmonization_result.request.artifact_result.request.quality_result
    prerequisites = proteoform_support_prerequisites(quality_result, harmonization_result)
    applicability = prerequisites.quality.applicability
    if applicability is None:
        raise ScenarioClosureError
    specimen = _oid("specimen", {"canonical_fact": "specimen"})
    disease = _oid("disease", {"canonical_fact": "disease"})
    reference = _oid("reference", {"canonical_fact": "reference"})
    intended_use = _oid("use", {"canonical_fact": "intended-use"})
    envelope = ProteoformSupportEnvelope(
        envelope_id=_oid("envelope", {"canonical": "supported"}),
        applicabilities=(applicability,),
        approved_assay_protocol_versions=(prerequisites.quality.assay_protocol_version,),
        approved_specimen_processing_versions=(prerequisites.quality.specimen_processing_version,),
        approved_controlled_vocabulary_ids=(prerequisites.quality.controlled_vocabulary_id,),
        approved_controlled_vocabulary_versions=(
            prerequisites.quality.controlled_vocabulary_version,
        ),
        approved_unit_system_versions=(prerequisites.quality.unit_system_version,),
        specimen_terms=(specimen,),
        disease_class_terms=(disease,),
        quality_statuses=tuple({item.status for item in prerequisites.quality.metrics}),
        minimum_completeness_ppm=600_000,
        platform_level_ids=prerequisites.harmonization.analysis_platform_level_ids,
        reference_terms=(reference,),
        intended_use_terms=(intended_use,),
        required_context_roles=tuple(ProteoformContextRole),
        remediations=_remediations(),
    )
    profile = ProteoformSupportProfile(
        profile_id=_oid("profile", {"canonical": "support-profile"}),
        version="1.0.0",
        envelopes=(envelope,),
        evidence=_artifact("profile"),
    )
    policy = ProteoformSupportPolicy(
        policy_id=_oid("policy", {"canonical": "support-policy"}),
        version="1.0.0",
        max_envelopes=1,
        evidence=_artifact("policy"),
        reviewed_by=_oid("reviewer", {"canonical": "scientific-review"}),
        reviewed_at=harmonization_result.completed_at,
    )
    upstream_context = harmonization_result.request.context
    references = upstream_context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(profile, policy)}
            )
        }
    )
    quality = references.quality.model_copy(
        update={
            "evidence": references.quality.evidence.model_copy(
                update={"digest": quality_result.result_digest}
            )
        }
    )
    support = references.support.model_copy(
        update={
            "evidence": references.support.evidence.model_copy(
                update={"digest": harmonization_result.result_digest}
            )
        }
    )
    request_id = _oid(
        "request",
        {
            "quality": quality_result.result_digest,
            "harmonization": harmonization_result.result_digest,
        },
    )
    context = upstream_context.model_copy(
        update={
            "request_id": request_id,
            "occurred_at": harmonization_result.completed_at + timedelta(seconds=2),
            "references": references.model_copy(
                update={
                    "approved_configuration": approved,
                    "quality": quality,
                    "support": support,
                }
            ),
        }
    )
    facts = (
        _observed_fact(ProteoformSupportDimension.SPECIMEN, "specimen", "specimen"),
        _observed_fact(ProteoformSupportDimension.DISEASE_CLASS, "disease", "disease"),
        _observed_fact(ProteoformSupportDimension.REFERENCE, "reference", "reference"),
        _observed_fact(ProteoformSupportDimension.INTENDED_USE, "use", "intended-use"),
    )
    context_receipts = tuple(
        ProteoformContextReceipt(
            role=role,
            state=ProteoformDeclaredSupportState.OBSERVED,
            reference=_artifact(f"context-{role.value}"),
        )
        for role in ProteoformContextRole
    )
    request = RouteProteoformSupportRequest(
        request_id=request_id,
        context=context,
        prerequisites=prerequisites,
        profile=profile,
        policy=policy,
        declared_facts=facts,
        context_receipts=context_receipts,
    )
    return Scenario(
        request=request,
        quality_result=quality_result,
        harmonization_result=harmonization_result,
    )


def build_scenario_request() -> RouteProteoformSupportRequest:
    """Return the canonical executable M04-07 support-route request."""

    return build_scenario().request


def _corpus() -> Corpus:
    return cast("Corpus", json.loads(SCENARIO_PATH.read_text(encoding="utf-8")))


def _scenario(case_id: str, *, passed: bool, detail: str) -> EvalCheck:
    return EvalCheck(name=f"scenario.{case_id}", passed=passed, detail=detail)


def _envelope_with(
    envelope: ProteoformSupportEnvelope, **updates: object
) -> ProteoformSupportEnvelope:
    payload = envelope.model_dump(mode="python")
    payload.update(updates)
    return ProteoformSupportEnvelope.model_validate(payload, strict=True)


def _request_with(  # noqa: PLR0913 - explicit independent scenario mutation surface.
    request: RouteProteoformSupportRequest,
    label: str,
    *,
    prerequisites: ProteoformSupportPrerequisites | None = None,
    envelopes: tuple[ProteoformSupportEnvelope, ...] | None = None,
    facts: tuple[ProteoformDeclaredSupportFact, ...] | None = None,
    contexts: tuple[ProteoformContextReceipt, ...] | None = None,
    max_envelopes: int | None = None,
) -> RouteProteoformSupportRequest:
    chosen_envelopes = envelopes or request.profile.envelopes
    profile = ProteoformSupportProfile.model_validate(
        {
            **request.profile.model_dump(mode="python"),
            "envelopes": chosen_envelopes,
        },
        strict=True,
    )
    policy = ProteoformSupportPolicy.model_validate(
        {
            **request.policy.model_dump(mode="python"),
            "max_envelopes": max_envelopes or request.policy.max_envelopes,
        },
        strict=True,
    )
    references = request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(profile, policy)}
            )
        }
    )
    request_id = _oid("request", {"m0407_case": label})
    chosen_prerequisites = prerequisites or request.prerequisites
    quality_reference = references.quality.model_copy(
        update={
            "evidence": references.quality.evidence.model_copy(
                update={"digest": chosen_prerequisites.quality.result_digest}
            )
        }
    )
    support_reference = references.support.model_copy(
        update={
            "evidence": references.support.evidence.model_copy(
                update={"digest": chosen_prerequisites.harmonization.result_digest}
            )
        }
    )
    identity_reference = references.identity_lineage.model_copy(
        update={"binding_digest": chosen_prerequisites.quality.identity_resolution_digest}
    )
    context = request.context.model_copy(
        update={
            "request_id": request_id,
            "references": references.model_copy(
                update={
                    "approved_configuration": approved,
                    "quality": quality_reference,
                    "support": support_reference,
                    "identity_lineage": identity_reference,
                }
            ),
        }
    )
    return RouteProteoformSupportRequest.model_validate(
        {
            **request.model_dump(mode="python"),
            "request_id": request_id,
            "context": context,
            "prerequisites": chosen_prerequisites,
            "profile": profile,
            "policy": policy,
            "declared_facts": facts or request.declared_facts,
            "context_receipts": contexts or request.context_receipts,
        },
        strict=True,
    )


def _fact_with(
    fact: ProteoformDeclaredSupportFact, **updates: object
) -> ProteoformDeclaredSupportFact:
    payload = fact.model_dump(mode="python")
    payload.update(updates)
    return ProteoformDeclaredSupportFact.model_validate(payload, strict=True)


def _replace_fact(
    request: RouteProteoformSupportRequest,
    dimension: ProteoformSupportDimension,
    replacement: ProteoformDeclaredSupportFact,
) -> tuple[ProteoformDeclaredSupportFact, ...]:
    return tuple(
        replacement if item.dimension is dimension else item for item in request.declared_facts
    )


def _route_dimension(
    result: ProteoformSupportRouteResult,
    dimension: ProteoformSupportDimension,
) -> ProteoformDimensionSupportDecision:
    return next(
        item for item in result.envelope_assessments[0].dimensions if item.dimension is dimension
    ).decision


def _is_science_free_abstention(result: ProteoformSupportRouteResult) -> bool:
    """Enforce the dossier's no-apparently-valid-scientific-result ceiling."""

    authority_flags = (
        result.emits_protein_rna_discordance,
        result.emits_proteogenomic_state,
        result.emits_proteotype,
        result.emits_protein_level_subtype,
        result.infers_identity,
        result.infers_consent,
        result.infers_protein,
        result.infers_proteoform,
        result.infers_isoform,
        result.localizes_modification,
        result.infers_kinase_activity,
        result.performs_cn_to_protein_regression,
        result.performs_all_omics_fusion,
        result.recommends_treatment,
        result.mutates_upstream,
        result.executes_model,
    )
    return (
        result.disposition is ProteoformSupportDisposition.ABSTAINED
        and result.parent_target == "protein_rna_discordance"
        and result.support.status is SupportStatus.UNSUPPORTED
        and result.human_review_required
        and not result.matched_envelope_ids
        and bool(result.abstention_reasons)
        and not any(authority_flags)
    )


def _outside_case(
    case_id: str,
    request: RouteProteoformSupportRequest,
    dimension: ProteoformSupportDimension,
) -> EvalCheck:
    result = route_proteoform_support(request)
    codes = {item.code for item in result.abstention_reasons}
    return _scenario(
        case_id,
        passed=(
            _is_science_free_abstention(result)
            and _route_dimension(result, dimension)
            is ProteoformDimensionSupportDecision.OUTSIDE_DOMAIN
            and ProteoformAbstentionCode.DIMENSION_OUTSIDE_DOMAIN in codes
        ),
        detail=(
            f"disposition={result.disposition.value};dimension={dimension.value};"
            f"codes={sorted(item.value for item in codes)}"
        ),
    )


def _outside_dimension_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    envelope = request.profile.envelopes[0]
    assay = _request_with(
        request,
        "outside_assay",
        envelopes=(
            _envelope_with(
                envelope,
                applicabilities=(ProteoformApplicability.BOTTOM_UP_DDA,),
            ),
        ),
    )
    facts = {item.dimension: item for item in request.declared_facts}
    specimen_fact = _fact_with(
        facts[ProteoformSupportDimension.SPECIMEN],
        values=(_oid("specimen", {"outside": "specimen"}),),
    )
    specimen = _request_with(
        request,
        "outside_specimen",
        facts=_replace_fact(request, ProteoformSupportDimension.SPECIMEN, specimen_fact),
    )
    disease_fact = _fact_with(
        facts[ProteoformSupportDimension.DISEASE_CLASS],
        values=(_oid("disease", {"outside": "disease"}),),
    )
    disease = _request_with(
        request,
        "outside_disease_class",
        facts=_replace_fact(request, ProteoformSupportDimension.DISEASE_CLASS, disease_fact),
    )
    quality = _request_with(
        request,
        "outside_quality",
        envelopes=(
            _envelope_with(
                envelope,
                quality_statuses=(ProteoformQualityMetricStatus.WARNING,),
            ),
        ),
    )
    completeness = _request_with(
        request,
        "outside_completeness",
        envelopes=(
            _envelope_with(
                envelope,
                minimum_completeness_ppm=700_000,
            ),
        ),
    )
    platform = _request_with(
        request,
        "outside_platform",
        envelopes=(
            _envelope_with(
                envelope,
                platform_level_ids=(
                    f"level.{sha256_digest({'outside': 'platform'}).removeprefix('sha256:')}",
                ),
            ),
        ),
    )
    reference_fact = _fact_with(
        facts[ProteoformSupportDimension.REFERENCE],
        values=(_oid("reference", {"outside": "reference"}),),
    )
    reference = _request_with(
        request,
        "outside_reference",
        facts=_replace_fact(request, ProteoformSupportDimension.REFERENCE, reference_fact),
    )
    use_fact = _fact_with(
        facts[ProteoformSupportDimension.INTENDED_USE],
        values=(_oid("use", {"outside": "intended-use"}),),
    )
    intended_use = _request_with(
        request,
        "outside_intended_use",
        facts=_replace_fact(request, ProteoformSupportDimension.INTENDED_USE, use_fact),
    )
    return [
        _outside_case("outside_assay", assay, ProteoformSupportDimension.ASSAY),
        _outside_case("outside_specimen", specimen, ProteoformSupportDimension.SPECIMEN),
        _outside_case(
            "outside_disease_class",
            disease,
            ProteoformSupportDimension.DISEASE_CLASS,
        ),
        _outside_case("outside_quality", quality, ProteoformSupportDimension.QUALITY),
        _reachable_completeness_check(
            completeness,
        ),
        _outside_case("outside_platform", platform, ProteoformSupportDimension.PLATFORM),
        _outside_case("outside_reference", reference, ProteoformSupportDimension.REFERENCE),
        _outside_case(
            "outside_intended_use",
            intended_use,
            ProteoformSupportDimension.INTENDED_USE,
        ),
    ]


def _reachable_completeness_check(
    request: RouteProteoformSupportRequest,
) -> EvalCheck:
    result = route_proteoform_support(request)
    assessment = next(
        item
        for item in result.envelope_assessments[0].dimensions
        if item.dimension is ProteoformSupportDimension.COMPLETENESS
    )
    return _scenario(
        "outside_completeness",
        passed=(
            _is_science_free_abstention(result)
            and assessment.decision is ProteoformDimensionSupportDecision.OUTSIDE_DOMAIN
            and assessment.numeric_value_ppm is not None
            and assessment.numeric_value_ppm < OUTSIDE_COMPLETENESS_THRESHOLD_PPM
            and ProteoformAbstentionCode.DIMENSION_OUTSIDE_DOMAIN
            in {item.code for item in result.abstention_reasons}
        ),
        detail=(
            f"conservative_completeness_ppm={assessment.numeric_value_ppm};"
            f"disposition={result.disposition.value}"
        ),
    )


def _missing_unknown_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    fact = next(
        item
        for item in request.declared_facts
        if item.dimension is ProteoformSupportDimension.SPECIMEN
    )
    checks: list[EvalCheck] = []
    for case_id, state in (
        ("missing_declared_fact", ProteoformDeclaredSupportState.MISSING),
        ("unknown_declared_fact", ProteoformDeclaredSupportState.UNKNOWN),
    ):
        replacement = _fact_with(fact, state=state, values=(), evidence=())
        candidate = _request_with(
            request,
            case_id,
            facts=_replace_fact(request, ProteoformSupportDimension.SPECIMEN, replacement),
        )
        result = route_proteoform_support(candidate)
        checks.append(
            _scenario(
                case_id,
                passed=(
                    _is_science_free_abstention(result)
                    and _route_dimension(result, ProteoformSupportDimension.SPECIMEN)
                    is ProteoformDimensionSupportDecision.INDETERMINATE
                    and ProteoformAbstentionCode.DIMENSION_INDETERMINATE
                    in {item.code for item in result.abstention_reasons}
                ),
                detail=f"state={state.value};disposition={result.disposition.value}",
            )
        )
    return checks


def _harmonization_from_artifact_result(
    artifact_result: ProteoformArtifactDetectionResult,
    label: str,
) -> ProteoformHarmonizationResult:
    artifact_receipt = artifact_harmonization_receipt(artifact_result)
    template = build_m0406_request()
    references = artifact_result.request.context.references
    approved_reference = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": harmonization_configuration_digest(template.policy)}
            )
        }
    )
    context = artifact_result.request.context.model_copy(
        update={
            "request_id": opaque_harmonization_identifier("request", {"m0407_case": label}),
            "occurred_at": artifact_result.completed_at + timedelta(seconds=2),
            "references": references.model_copy(
                update={"approved_configuration": approved_reference}
            ),
        }
    )
    return harmonize_proteoform_analysis(
        HarmonizeProteoformAnalysisRequest(
            context=context,
            artifact_result=artifact_result,
            artifact_receipt=artifact_receipt,
            support_ledger=None,
            policy=template.policy,
        )
    )


def _genuine_unreleasable_harmonization() -> ProteoformHarmonizationResult:
    artifact_result = m0405_evidence.build_scenario_result("critical_barcode_index")
    return _harmonization_from_artifact_result(artifact_result, "m0406_unreleasable")


def _unreleasable_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    quality_request = build_m0404_request("abstained_upstream_zero_ledger_traversal")
    unreleasable_quality = compute_proteoform_quality_metrics(quality_request)
    artifact_result = m0405_evidence.build_scenario_result("upstream_abstained")
    unreleasable_harmonization = _harmonization_from_artifact_result(
        artifact_result, "m0404_unreleasable"
    )
    cases = (
        (
            "m0404_unreleasable",
            proteoform_support_prerequisites(
                unreleasable_quality,
                unreleasable_harmonization,
            ),
            ("GLIO-PROTEOGEN-M04-04", "GLIO-PROTEOGEN-M04-06"),
        ),
        (
            "m0406_unreleasable",
            proteoform_support_prerequisites(
                request.prerequisites.quality_result,
                _genuine_unreleasable_harmonization(),
            ),
            ("GLIO-PROTEOGEN-M04-06",),
        ),
    )
    checks: list[EvalCheck] = []
    for case_id, prerequisites, module_ids in cases:
        result = route_proteoform_support(
            _request_with(request, case_id, prerequisites=prerequisites)
        )
        blockers = tuple(
            item.upstream_module_id
            for item in result.abstention_reasons
            if item.code is ProteoformAbstentionCode.PREREQUISITE_UNRELEASABLE
        )
        checks.append(
            _scenario(
                case_id,
                passed=(_is_science_free_abstention(result) and blockers == module_ids),
                detail=f"exact_upstream_blockers={blockers}",
            )
        )
    return checks


def _genuine_extra_platform_harmonization() -> ProteoformHarmonizationResult:
    scenario = m0406_evidence._scenario_for_target_count(M0407_MAX_ANALYSIS_TARGETS)
    request = scenario.request
    ledger = request.support_ledger
    if ledger is None:
        raise ScenarioClosureError
    stage = next(
        item
        for item in request.policy.profiles[0].stages
        if item.factor is ProteoformNormalizationFactor.PLATFORM
    )
    group_id = next(
        item.biological_group_id
        for item in ledger.observations
        if item.anchor_id == stage.estimation_anchor_ids[0]
    )
    extra_level = opaque_harmonization_identifier("level", {"m0407_case": "platform_extra_member"})
    mutations = (
        (
            "technical.platform.estimation.reference",
            stage.estimation_anchor_ids[0],
            stage.reference_level_id,
            500_000,
        ),
        (
            "technical.platform.estimation.comparison",
            stage.estimation_anchor_ids[0],
            extra_level,
            501_000,
        ),
        (
            "technical.platform.validation.reference",
            stage.validation_anchor_ids[0],
            stage.reference_level_id,
            500_000,
        ),
        (
            "technical.platform.validation.comparison",
            stage.validation_anchor_ids[0],
            extra_level,
            501_000,
        ),
    )
    for label, anchor_id, level_id, coordinate in mutations:
        target_id = scenario.target_ids[label]
        observation = next(item for item in ledger.observations if item.target_id == target_id)
        levels = tuple(
            ProteoformNormalizationFactorLevel(
                factor=item.factor,
                level_id=(
                    level_id
                    if item.factor is ProteoformNormalizationFactor.PLATFORM
                    else item.level_id
                ),
            )
            for item in observation.factor_levels
        )
        request = m0406_evidence._with_observation(
            request,
            target_id,
            anchor_id=anchor_id,
            biological_group_id=group_id,
            support_coordinate_ppm=coordinate,
            factor_levels=levels,
        )
    return harmonize_proteoform_analysis(request)


def _all_member_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    extra_platform_result = _genuine_extra_platform_harmonization()
    platform_prerequisites = proteoform_support_prerequisites(
        request.prerequisites.quality_result,
        extra_platform_result,
    )
    platform_request = _request_with(
        request,
        "platform_extra_member",
        prerequisites=platform_prerequisites,
    )
    reference_fact = next(
        item
        for item in request.declared_facts
        if item.dimension is ProteoformSupportDimension.REFERENCE
    )
    extra_reference = _fact_with(
        reference_fact,
        values=(
            *reference_fact.values,
            _oid("reference", {"extra": "reference"}),
        ),
    )
    reference_request = _request_with(
        request,
        "reference_extra_member",
        facts=_replace_fact(request, ProteoformSupportDimension.REFERENCE, extra_reference),
    )
    return [
        _outside_case(
            "platform_extra_member",
            platform_request,
            ProteoformSupportDimension.PLATFORM,
        ),
        _outside_case(
            "reference_extra_member",
            reference_request,
            ProteoformSupportDimension.REFERENCE,
        ),
    ]


def _cross_envelope_check(scenario: Scenario) -> EvalCheck:
    request = scenario.request
    canonical = request.profile.envelopes[0]
    first = _envelope_with(
        canonical,
        envelope_id=_oid("envelope", {"cross": "specimen"}),
        specimen_terms=(_oid("specimen", {"outside": "cross"}),),
    )
    second = _envelope_with(
        canonical,
        envelope_id=_oid("envelope", {"cross": "disease"}),
        disease_class_terms=(_oid("disease", {"outside": "cross"}),),
    )
    result = route_proteoform_support(
        _request_with(
            request,
            "cross_envelope_composite",
            envelopes=(first, second),
            max_envelopes=2,
        )
    )
    codes = {item.code for item in result.abstention_reasons}
    return _scenario(
        "cross_envelope_composite",
        passed=(
            _is_science_free_abstention(result)
            and ProteoformAbstentionCode.JOINT_COMBINATION_OUTSIDE_DOMAIN in codes
        ),
        detail=f"matches={len(result.matched_envelope_ids)};codes={sorted(x.value for x in codes)}",
    )


def _reorder_checks(scenario: Scenario) -> list[EvalCheck]:
    canonical_request = scenario.request
    canonical_result = route_proteoform_support(canonical_request)
    payload = canonical_request.model_dump(mode="python")
    profile = cast("dict[str, Any]", payload["profile"])
    envelopes = cast("list[dict[str, Any]]", profile["envelopes"])
    for envelope in envelopes:
        for field in (
            "platform_level_ids",
            "required_context_roles",
            "remediations",
        ):
            envelope[field] = tuple(reversed(cast("tuple[object, ...]", envelope[field])))
    payload["declared_facts"] = tuple(
        reversed(cast("tuple[object, ...]", payload["declared_facts"]))
    )
    payload["context_receipts"] = tuple(
        reversed(cast("tuple[object, ...]", payload["context_receipts"]))
    )
    reordered = RouteProteoformSupportRequest.model_validate(payload, strict=True)
    reordered_result = route_proteoform_support(reordered)
    return [
        _scenario(
            "canonical_order",
            passed=(
                canonical_result.disposition is ProteoformSupportDisposition.SUPPORTED
                and canonical_result == route_proteoform_support(canonical_request)
            ),
            detail=f"result_digest={canonical_result.result_digest}",
        ),
        _scenario(
            "semantic_reorder",
            passed=(
                reordered == canonical_request
                and canonical_json_bytes(reordered) == canonical_json_bytes(canonical_request)
                and reordered_result == canonical_result
            ),
            detail=f"complete_result_equality={reordered_result == canonical_result}",
        ),
    ]


def _hostile_preflight_check(scenario: Scenario) -> EvalCheck:
    hostile = _HostileEvidence()
    references = scenario.request.context.references.model_dump(mode="python")
    consent = cast("dict[str, object]", references["consent"])
    consent["state"] = "denied"
    candidate = {
        "context": {"references": references},
        "prerequisites": hostile,
        "declared_facts": hostile,
        "context_receipts": hostile,
    }
    rejected = False
    try:
        preflight_proteoform_support_authorization(candidate)
    except ProteoformSupportAuthorizationError:
        rejected = True
    return _scenario(
        "consent_denied_hostile_evidence",
        passed=rejected and hostile.traversals == 0,
        detail=f"rejected={rejected};governed_traversals={hostile.traversals}",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    corpus = _corpus()
    scenario = build_scenario()
    supported = route_proteoform_support(scenario.request)
    declared = {case_id for group in corpus["scenario_groups"] for case_id in group["case_ids"]}
    checks = [
        _scenario(
            "joint_supported",
            passed=(
                supported.disposition is ProteoformSupportDisposition.SUPPORTED
                and len(supported.matched_envelope_ids) == 1
                and not supported.abstention_reasons
                and all(
                    dimension.decision is ProteoformDimensionSupportDecision.SUPPORTED
                    for dimension in supported.envelope_assessments[0].dimensions
                )
            ),
            detail=(
                f"disposition={supported.disposition.value};"
                f"matches={len(supported.matched_envelope_ids)}"
            ),
        ),
        *_outside_dimension_checks(scenario),
        *_missing_unknown_checks(scenario),
        *_unreleasable_checks(scenario),
        *_all_member_checks(scenario),
        _cross_envelope_check(scenario),
        *_reorder_checks(scenario),
        _hostile_preflight_check(scenario),
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
                    and len(corpus["scenario_groups"]) == _EXPECTED_GROUP_COUNT
                    and len(declared) == _EXPECTED_CASE_COUNT
                ),
                detail=(f"groups={len(corpus['scenario_groups'])};declared={len(declared)}"),
            ),
            EvalCheck(
                name="corpus.executable_coverage",
                passed=(
                    len(declared) == len(executed) == _EXPECTED_CASE_COUNT
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


__all__ = [
    "EvalCheck",
    "Scenario",
    "ScenarioClosureError",
    "build_scenario",
    "build_scenario_request",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
