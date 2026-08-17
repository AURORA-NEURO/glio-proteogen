"""Replay the locked M02-07 synthetic joint support-envelope corpus."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m02_04.run import build_scenario_request as build_m0204_request
from evals.m02_06.run import build_scenario_request as build_m0206_request
from glio_proteogen.contracts.m02_04 import IdentificationMetricStatus
from glio_proteogen.contracts.m02_06 import HarmonizeIdentificationEvidenceRequest
from glio_proteogen.contracts.m02_07 import (
    DeclaredSupportFact,
    DeclaredSupportState,
    DimensionSupportDecision,
    EnvelopeSupportDecision,
    IdentificationAbstentionCode,
    IdentificationContextReceipt,
    IdentificationContextRole,
    IdentificationDimensionRemediation,
    IdentificationSupportDimension,
    IdentificationSupportEnvelope,
    IdentificationSupportPolicy,
    IdentificationSupportPrerequisites,
    IdentificationSupportProfile,
    RouteIdentificationSupportRequest,
    configuration_digest,
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
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics import (
    compute_identification_quality,
)
from glio_proteogen.modules.c02_identification_qc.m02_06_harmonization import (
    harmonize_identification_evidence,
)
from glio_proteogen.modules.c02_identification_qc.m02_07_support_router import (
    IdentificationSupportAuthorizationError,
    build_identification_support_prerequisites,
    route_identification_support,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M02-07"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m02_07" / "scenarios.json"
SUPPORTED_SPECIMEN: Final = "specimen.ffpe"
SUPPORTED_DISEASE: Final = "disease.glioma"
SUPPORTED_REFERENCES: Final = ("reference.ensembl.2026", "reference.uniprot.2026")
SUPPORTED_INTENDED_USE: Final = "use.research.proteomics"
EXPECTED_GROUP_IDS: Final = (
    "exact_joint_envelope_supported",
    "each_dimension_outside_envelope",
    "missing_and_unknown_evidence",
    "unreleasable_prerequisite_receipts",
    "all_members_platform_reference",
    "cross_envelope_combination_rejected",
    "semantic_reorder_full_equality",
    "denied_consent_hostile_preflight",
)
EXPECTED_CASE_COUNT: Final = 19


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


class _UnreadableSupportEvidence:
    """Hostile object proving denied authorization precedes scientific traversal."""

    _MESSAGE = "support evidence was traversed before authorization"

    def __iter__(self) -> Iterator[object]:
        raise AssertionError(self._MESSAGE)

    def __len__(self) -> int:
        raise AssertionError(self._MESSAGE)


class _InvalidCorpusError(TypeError):
    pass


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m0207.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"m0207": label}),
        media_type="application/json",
    )


@lru_cache(maxsize=16)
def _genuine_prerequisites(
    m0204_mutation: str = "none",
    m0206_mutation: str = "conformant_eight_factor",
) -> IdentificationSupportPrerequisites:
    """Execute one lineage-coherent M02-04 -> M02-06 chain and reduce it publicly."""

    harmonization_request = build_m0206_request(m0206_mutation)
    quality_request = build_m0204_request(m0204_mutation)
    identity_digest = harmonization_request.prerequisites.identity.result_digest
    identity = quality_request.context.references.identity_lineage.model_copy(
        update={"binding_digest": identity_digest}
    )
    quality_references = quality_request.context.references.model_copy(
        update={"identity_lineage": identity}
    )
    quality_request = quality_request.model_copy(
        update={
            "context": quality_request.context.model_copy(
                update={"references": quality_references}
            )
        }
    )
    quality_result = compute_identification_quality(quality_request)
    harmonization_prerequisites = harmonization_request.prerequisites.model_copy(
        update={"quality": quality_result}
    )
    harmonization_request = HarmonizeIdentificationEvidenceRequest.model_validate(
        harmonization_request.model_copy(
            update={"prerequisites": harmonization_prerequisites}
        ).model_dump(mode="python")
    )
    harmonization_result = harmonize_identification_evidence(harmonization_request)
    return build_identification_support_prerequisites(
        quality_request.assay_profile,
        quality_result,
        harmonization_result,
    )


def _remediations() -> tuple[IdentificationDimensionRemediation, ...]:
    return tuple(
        IdentificationDimensionRemediation(
            dimension=dimension,
            outside_reason_code=f"outside.{dimension.value}",
            indeterminate_reason_code=f"indeterminate.{dimension.value}",
            remediation_code=f"remediate.{dimension.value}",
        )
        for dimension in IdentificationSupportDimension
    )


def _envelope(
    prerequisites: IdentificationSupportPrerequisites,
    *,
    envelope_id: str = "envelope.m0207.joint-supported",
) -> IdentificationSupportEnvelope:
    return IdentificationSupportEnvelope(
        envelope_id=envelope_id,
        assay_types=(prerequisites.assay_profile.assay_type.value,),
        specimen_terms=(SUPPORTED_SPECIMEN,),
        disease_class_terms=(SUPPORTED_DISEASE,),
        quality_statuses=(IdentificationMetricStatus.PASS,),
        minimum_completeness=0.90,
        platform_ids=prerequisites.harmonization.platform_ids,
        reference_ids=SUPPORTED_REFERENCES,
        intended_use_terms=(SUPPORTED_INTENDED_USE,),
        required_context_roles=tuple(IdentificationContextRole),
        remediations=_remediations(),
    )


def _profile(
    prerequisites: IdentificationSupportPrerequisites,
) -> IdentificationSupportProfile:
    return IdentificationSupportProfile(
        profile_id="profile.synthetic.m0207.joint-support",
        version="1.0.0",
        envelopes=(_envelope(prerequisites),),
        evidence=_artifact("profile"),
    )


def _policy() -> IdentificationSupportPolicy:
    return IdentificationSupportPolicy(
        policy_id="policy.synthetic.m0207.joint-support",
        version="1.0.0",
        evidence=_artifact("policy"),
    )


def _facts() -> tuple[DeclaredSupportFact, ...]:
    values = {
        IdentificationSupportDimension.SPECIMEN: (SUPPORTED_SPECIMEN,),
        IdentificationSupportDimension.DISEASE_CLASS: (SUPPORTED_DISEASE,),
        IdentificationSupportDimension.REFERENCE: SUPPORTED_REFERENCES,
        IdentificationSupportDimension.INTENDED_USE: (SUPPORTED_INTENDED_USE,),
    }
    return tuple(
        DeclaredSupportFact(
            dimension=dimension,
            state=DeclaredSupportState.OBSERVED,
            values=members,
            evidence=(_artifact(f"fact.{dimension.value}"),),
        )
        for dimension, members in values.items()
    )


def _context_receipts() -> tuple[IdentificationContextReceipt, ...]:
    return tuple(
        IdentificationContextReceipt(
            role=role,
            state=DeclaredSupportState.OBSERVED,
            reference=_artifact(f"context.{role.value}"),
        )
        for role in IdentificationContextRole
    )


def _context(configuration: str, identity_digest: str) -> ExecutionContext:
    def accepted(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.m0207.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control.{role}", digest),
        )

    return ExecutionContext(
        request_id="request.synthetic.m0207.joint-support",
        actor_id="actor.synthetic.eval",
        occurred_at=datetime(2026, 8, 12, 23, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted("configuration", configuration),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.m0207.identity-lineage",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=identity_digest,
                evidence=_artifact("control.identity-lineage"),
            ),
            provenance=accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.m0207.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control.consent"),
            ),
            quality=accepted("quality"),
            support=accepted("support"),
            intended_use=accepted("intended-use"),
        ),
    )


def _base_request(
    prerequisites: IdentificationSupportPrerequisites | None = None,
) -> RouteIdentificationSupportRequest:
    active_prerequisites = prerequisites or _genuine_prerequisites()
    profile = _profile(active_prerequisites)
    policy = _policy()
    return RouteIdentificationSupportRequest(
        context=_context(
            configuration_digest(profile, policy),
            active_prerequisites.quality.identity_subject_digest,
        ),
        prerequisites=active_prerequisites,
        profile=profile,
        policy=policy,
        declared_facts=_facts(),
        context_receipts=_context_receipts(),
    )


def build_scenario_request(
    request_case: str = "joint_supported",
    *,
    outside_dimension: IdentificationSupportDimension | None = None,
) -> RouteIdentificationSupportRequest:
    """Build one strict deterministic M02-07 request from genuine upstream executions."""

    if request_case in {"joint_supported", "consent_denied_hostile_evidence"}:
        return _base_request()
    if request_case == "outside_dimension_matrix" and outside_dimension is not None:
        return _outside_dimension_request(outside_dimension)
    builders: dict[str, Callable[[], RouteIdentificationSupportRequest]] = {
        "missing_evidence": lambda: _fact_state_request(
            IdentificationSupportDimension.SPECIMEN,
            DeclaredSupportState.MISSING,
        ),
        "unknown_evidence": lambda: _fact_state_request(
            IdentificationSupportDimension.REFERENCE,
            DeclaredSupportState.UNKNOWN,
        ),
        "m0204_unreleasable": lambda: _base_request(
            _genuine_prerequisites("low_identification_coverage")
        ),
        "m0206_unreleasable": lambda: _base_request(
            _genuine_prerequisites("none", "insufficient_controls")
        ),
        "platform_all_members": lambda: _outside_dimension_request(
            IdentificationSupportDimension.PLATFORM
        ),
        "reference_all_members": _all_member_reference_request,
        "cross_envelope_composite": _cross_envelope_request,
        "semantic_reorder_pair": lambda: _reordered_request(_base_request()),
    }
    try:
        builder = builders[request_case]
    except KeyError as error:
        raise ValueError(request_case) from error
    return builder()


def _replace_fact(
    request: RouteIdentificationSupportRequest,
    replacement: DeclaredSupportFact,
) -> RouteIdentificationSupportRequest:
    facts = tuple(
        replacement if item.dimension is replacement.dimension else item
        for item in request.declared_facts
    )
    return RouteIdentificationSupportRequest.model_validate(
        request.model_copy(update={"declared_facts": facts}).model_dump(mode="python")
    )


def _fact_state_request(
    dimension: IdentificationSupportDimension,
    state: DeclaredSupportState,
) -> RouteIdentificationSupportRequest:
    request = _base_request()
    original = next(item for item in request.declared_facts if item.dimension is dimension)
    return _replace_fact(request, original.model_copy(update={"state": state, "values": ()}))


def _outside_dimension_request(
    dimension: IdentificationSupportDimension,
) -> RouteIdentificationSupportRequest:
    request = _base_request()
    envelope = request.profile.envelopes[0]
    if dimension is IdentificationSupportDimension.ASSAY:
        envelope = envelope.model_copy(update={"assay_types": ("assay.dda",)})
    elif dimension in {
        IdentificationSupportDimension.SPECIMEN,
        IdentificationSupportDimension.DISEASE_CLASS,
    }:
        return _outside_declared_fact(request, dimension)
    elif dimension is IdentificationSupportDimension.QUALITY:
        envelope = envelope.model_copy(
            update={"quality_statuses": (IdentificationMetricStatus.WARNING,)}
        )
    elif dimension is IdentificationSupportDimension.COMPLETENESS:
        envelope = envelope.model_copy(update={"minimum_completeness": 0.99})
    elif dimension is IdentificationSupportDimension.PLATFORM:
        envelope = envelope.model_copy(update={"platform_ids": envelope.platform_ids[:1]})
    elif dimension in {
        IdentificationSupportDimension.REFERENCE,
        IdentificationSupportDimension.INTENDED_USE,
    }:
        return _outside_declared_fact(request, dimension)
    return _with_envelopes(request, (envelope,))


def _outside_declared_fact(
    request: RouteIdentificationSupportRequest,
    dimension: IdentificationSupportDimension,
) -> RouteIdentificationSupportRequest:
    original = next(item for item in request.declared_facts if item.dimension is dimension)
    replacement = original.model_copy(update={"values": (f"outside.{dimension.value}",)})
    return _replace_fact(request, replacement)


def _all_member_reference_request() -> RouteIdentificationSupportRequest:
    request = _base_request()
    original = next(
        item
        for item in request.declared_facts
        if item.dimension is IdentificationSupportDimension.REFERENCE
    )
    replacement = original.model_copy(
        update={"values": (*original.values, "reference.outside")}
    )
    return _replace_fact(request, replacement)


def _with_envelopes(
    request: RouteIdentificationSupportRequest,
    envelopes: tuple[IdentificationSupportEnvelope, ...],
) -> RouteIdentificationSupportRequest:
    profile = request.profile.model_copy(update={"envelopes": envelopes})
    configuration = configuration_digest(profile, request.policy)
    references = request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration}
            )
        }
    )
    context = request.context.model_copy(
        update={
            "references": references.model_copy(
                update={"approved_configuration": approved}
            )
        }
    )
    return RouteIdentificationSupportRequest.model_validate(
        request.model_copy(
            update={"context": context, "profile": profile}
        ).model_dump(mode="python")
    )


def _cross_envelope_request() -> RouteIdentificationSupportRequest:
    request = _base_request()
    base = request.profile.envelopes[0]
    first = base.model_copy(
        update={
            "envelope_id": "envelope.m0207.cross-a",
            "disease_class_terms": ("disease.other",),
        }
    )
    second = base.model_copy(
        update={
            "envelope_id": "envelope.m0207.cross-b",
            "specimen_terms": ("specimen.other",),
        }
    )
    return _with_envelopes(request, (first, second))


def _reordered_request(
    request: RouteIdentificationSupportRequest,
) -> RouteIdentificationSupportRequest:
    profile = request.profile.model_copy(
        update={
            "envelopes": tuple(
                envelope.model_copy(
                    update={
                        "assay_types": tuple(reversed(envelope.assay_types)),
                        "specimen_terms": tuple(reversed(envelope.specimen_terms)),
                        "disease_class_terms": tuple(
                            reversed(envelope.disease_class_terms)
                        ),
                        "quality_statuses": tuple(reversed(envelope.quality_statuses)),
                        "platform_ids": tuple(reversed(envelope.platform_ids)),
                        "reference_ids": tuple(reversed(envelope.reference_ids)),
                        "intended_use_terms": tuple(
                            reversed(envelope.intended_use_terms)
                        ),
                        "required_context_roles": tuple(
                            reversed(envelope.required_context_roles)
                        ),
                        "remediations": tuple(reversed(envelope.remediations)),
                    }
                )
                for envelope in reversed(request.profile.envelopes)
            )
        }
    )
    facts = tuple(
        item.model_copy(
            update={
                "values": tuple(reversed(item.values)),
                "evidence": tuple(reversed(item.evidence)),
            }
        )
        for item in reversed(request.declared_facts)
    )
    reordered = request.model_copy(
        update={
            "profile": profile,
            "declared_facts": facts,
            "context_receipts": tuple(reversed(request.context_receipts)),
        }
    )
    return RouteIdentificationSupportRequest.model_validate(
        reordered.model_dump(mode="python")
    )


def build_representative_request(
    *,
    envelope_count: int = 64,
) -> RouteIdentificationSupportRequest:
    """Build the maximum-envelope supported request used by the public benchmark."""

    request = _base_request()
    template = request.profile.envelopes[0]
    envelopes = tuple(
        template.model_copy(update={"envelope_id": f"envelope.m0207.capacity.{index:02d}"})
        for index in range(envelope_count)
    )
    return _with_envelopes(request, envelopes)


def _canonical_request_size(request: RouteIdentificationSupportRequest) -> int:
    return len(canonical_json_bytes(request))


def _load_corpus() -> dict[str, Any]:
    value = strict_json_loads(SCENARIO_PATH.read_bytes())
    if not isinstance(value, dict):
        raise _InvalidCorpusError
    return value


def _corpus_check(corpus: dict[str, Any]) -> EvalCheck:
    groups = corpus.get("scenario_groups")
    dimensions = corpus.get("dimensions")
    if not isinstance(groups, list) or not isinstance(dimensions, list):
        return EvalCheck(
            name="corpus.locked_joint_routing_plan",
            passed=False,
            detail="invalid corpus shape",
        )
    group_ids = tuple(
        item.get("group_id") for item in groups if isinstance(item, dict)
    )
    case_count = sum(
        item.get("case_count", 0)
        for item in groups
        if isinstance(item, dict) and isinstance(item.get("case_count"), int)
    )
    passed = (
        corpus.get("module_id") == MODULE_ID
        and corpus.get("schema_version") == "1.0.0"
        and corpus.get("data_classification") == "synthetic_nonclinical"
        and corpus.get("claims_ceiling")
        == "deterministic_joint_envelope_routing_not_support_domain_validation"
        and group_ids == EXPECTED_GROUP_IDS
        and case_count == EXPECTED_CASE_COUNT
        and dimensions == [item.value for item in IdentificationSupportDimension]
    )
    return EvalCheck(
        "corpus.locked_joint_routing_plan",
        passed,
        f"groups={len(group_ids)};cases={case_count};dimensions={len(dimensions)}",
    )


def _exact_joint_check() -> tuple[EvalCheck, dict[str, Any]]:
    result = route_identification_support(build_scenario_request())
    confirmed = tuple(
        item
        for item in result.envelope_assessments
        if item.decision is EnvelopeSupportDecision.CONFIRMED
    )
    passed = (
        result.disposition.value == "supported"
        and result.matched_envelope_ids == ("envelope.m0207.joint-supported",)
        and not result.abstention_reasons
        and len(confirmed) == 1
        and all(
            item.decision is DimensionSupportDecision.SUPPORTED
            for item in confirmed[0].dimensions
        )
    )
    return (
        EvalCheck(
            "scenario.exact_joint_envelope_supported",
            passed,
            f"disposition={result.disposition.value};matches={len(result.matched_envelope_ids)}",
        ),
        result.model_dump(mode="json"),
    )


def _outside_dimension_check() -> tuple[EvalCheck, list[dict[str, Any]]]:
    results = []
    observed: list[str] = []
    exact = True
    for dimension in IdentificationSupportDimension:
        result = route_identification_support(
            build_scenario_request(
                "outside_dimension_matrix",
                outside_dimension=dimension,
            )
        )
        blocking = {
            item.dimension
            for item in result.abstention_reasons
            if item.code is IdentificationAbstentionCode.DIMENSION_OUTSIDE_DOMAIN
        }
        exact = exact and result.disposition.value == "abstained" and blocking == {dimension}
        observed.extend(item.value for item in blocking if item is not None)
        results.append(result.model_dump(mode="json"))
    passed = exact and sorted(observed) == sorted(
        item.value for item in IdentificationSupportDimension
    )
    return (
        EvalCheck(
            "scenario.each_dimension_outside_envelope",
            passed,
            f"isolated={','.join(observed)}",
        ),
        results,
    )


def _typed_nonobserved_check() -> tuple[EvalCheck, list[dict[str, Any]]]:
    missing = route_identification_support(build_scenario_request("missing_evidence"))
    unknown = route_identification_support(build_scenario_request("unknown_evidence"))
    missing_fact = next(
        item
        for item in missing.declared_facts
        if item.dimension is IdentificationSupportDimension.SPECIMEN
    )
    unknown_fact = next(
        item
        for item in unknown.declared_facts
        if item.dimension is IdentificationSupportDimension.REFERENCE
    )
    passed = (
        missing.disposition.value == "abstained"
        and unknown.disposition.value == "abstained"
        and missing_fact.state is DeclaredSupportState.MISSING
        and unknown_fact.state is DeclaredSupportState.UNKNOWN
        and any(
            item.code is IdentificationAbstentionCode.DIMENSION_INDETERMINATE
            and item.dimension is IdentificationSupportDimension.SPECIMEN
            for item in missing.abstention_reasons
        )
        and any(
            item.code is IdentificationAbstentionCode.DIMENSION_INDETERMINATE
            and item.dimension is IdentificationSupportDimension.REFERENCE
            for item in unknown.abstention_reasons
        )
    )
    return (
        EvalCheck(
            "scenario.missing_and_unknown_evidence",
            passed,
            f"states={missing_fact.state.value},{unknown_fact.state.value}",
        ),
        [missing.model_dump(mode="json"), unknown.model_dump(mode="json")],
    )


def _receipt_check() -> tuple[EvalCheck, list[dict[str, Any]]]:
    quality = route_identification_support(build_scenario_request("m0204_unreleasable"))
    harmonization = route_identification_support(
        build_scenario_request("m0206_unreleasable")
    )
    quality_modules = {
        item.upstream_module_id
        for item in quality.abstention_reasons
        if item.code is IdentificationAbstentionCode.PREREQUISITE_UNRELEASABLE
    }
    harmonization_modules = {
        item.upstream_module_id
        for item in harmonization.abstention_reasons
        if item.code is IdentificationAbstentionCode.PREREQUISITE_UNRELEASABLE
    }
    passed = (
        quality.disposition.value == "abstained"
        and harmonization.disposition.value == "abstained"
        and "GLIO-PROTEOGEN-M02-04" in quality_modules
        and harmonization_modules == {"GLIO-PROTEOGEN-M02-06"}
        and quality.prerequisites.quality.result_digest
        == quality.prerequisites.harmonization.m0204_result_digest
        and harmonization.prerequisites.quality.result_digest
        == harmonization.prerequisites.harmonization.m0204_result_digest
    )
    return (
        EvalCheck(
            "scenario.unreleasable_prerequisite_receipts",
            passed,
            f"quality={sorted(item for item in quality_modules if item)};"
            f"harmonization={sorted(item for item in harmonization_modules if item)}",
        ),
        [quality.model_dump(mode="json"), harmonization.model_dump(mode="json")],
    )


def _all_members_check() -> tuple[EvalCheck, list[dict[str, Any]]]:
    platform = route_identification_support(build_scenario_request("platform_all_members"))
    reference = route_identification_support(build_scenario_request("reference_all_members"))
    platform_members = platform.prerequisites.harmonization.platform_ids
    reference_fact = next(
        item
        for item in reference.declared_facts
        if item.dimension is IdentificationSupportDimension.REFERENCE
    )
    passed = (
        len(platform_members) > 1
        and len(reference_fact.values) > 1
        and platform.disposition.value == "abstained"
        and reference.disposition.value == "abstained"
        and any(
            item.dimension is IdentificationSupportDimension.PLATFORM
            for item in platform.abstention_reasons
        )
        and any(
            item.dimension is IdentificationSupportDimension.REFERENCE
            for item in reference.abstention_reasons
        )
    )
    return (
        EvalCheck(
            "scenario.all_members_platform_reference",
            passed,
            f"platform_members={len(platform_members)};reference_members={len(reference_fact.values)}",
        ),
        [platform.model_dump(mode="json"), reference.model_dump(mode="json")],
    )


def _cross_envelope_check() -> tuple[EvalCheck, dict[str, Any]]:
    result = route_identification_support(
        build_scenario_request("cross_envelope_composite")
    )
    passed = (
        result.disposition.value == "abstained"
        and not result.matched_envelope_ids
        and all(
            any(
                next(
                    item
                    for item in assessment.dimensions
                    if item.dimension is dimension
                ).decision
                is DimensionSupportDecision.SUPPORTED
                for assessment in result.envelope_assessments
            )
            for dimension in IdentificationSupportDimension
        )
        and any(
            item.code is IdentificationAbstentionCode.JOINT_COMBINATION_OUTSIDE_DOMAIN
            for item in result.abstention_reasons
        )
    )
    return (
        EvalCheck(
            "scenario.cross_envelope_combination_rejected",
            passed,
            f"envelopes={len(result.envelope_assessments)};matches={len(result.matched_envelope_ids)}",
        ),
        result.model_dump(mode="json"),
    )


def _semantic_equality_check() -> tuple[EvalCheck, list[dict[str, Any]]]:
    first = route_identification_support(build_scenario_request())
    reordered = route_identification_support(
        build_scenario_request("semantic_reorder_pair")
    )
    passed = first == reordered and first.model_dump_json() == reordered.model_dump_json()
    return (
        EvalCheck(
            "scenario.semantic_reorder_full_equality",
            passed,
            f"digest_equal={first.result_digest == reordered.result_digest}",
        ),
        [first.model_dump(mode="json"), reordered.model_dump(mode="json")],
    )


def _authorization_check() -> EvalCheck:
    payload = build_scenario_request().model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["declared_facts"] = _UnreadableSupportEvidence()
    try:
        route_identification_support(payload)
    except IdentificationSupportAuthorizationError as error:
        return EvalCheck(
            "scenario.denied_consent_hostile_preflight",
            "support evidence" not in str(error).casefold(),
            "authorization rejected before support-evidence traversal",
        )
    except AssertionError as error:
        return EvalCheck(
            name="scenario.denied_consent_hostile_preflight",
            passed=False,
            detail=str(error),
        )
    return EvalCheck(
        name="scenario.denied_consent_hostile_preflight",
        passed=False,
        detail="denied request was accepted",
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _all_keys(item)}
    if isinstance(value, list | tuple):
        return {key for item in value for key in _all_keys(item)}
    return set()


def _boundary_check(results: list[dict[str, Any]]) -> EvalCheck:
    forbidden = {
        "harmonized_value",
        "transformation_manifest",
        "raw_payload",
        "raw_spectra",
        "peptide_rows",
        "protein_subtype_inference",
        "kinase_activity",
        "treatment_recommendation",
        "clinical_recommendation",
        "upstream_mutations",
    }
    leaked = sorted(_all_keys(results) & forbidden)
    rendered = canonical_json_bytes(results).decode("utf-8")
    leaked_values = [
        value
        for value in ("MPEPTIDE", "SYNTHETIC_PATIENT", "synthetic-spectrum")
        if value in rendered
    ]
    return EvalCheck(
        "boundary.closed_identification_support_output",
        not leaked and not leaked_values,
        (
            "compact receipts and support-owned routing only"
            if not leaked and not leaked_values
            else f"keys={leaked};values={leaked_values}"
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus = _load_corpus()
    checks = [_corpus_check(corpus)]
    results: list[dict[str, Any]] = []

    exact_check, exact_result = _exact_joint_check()
    checks.append(exact_check)
    results.append(exact_result)
    for runner in (
        _outside_dimension_check,
        _typed_nonobserved_check,
        _receipt_check,
        _all_members_check,
    ):
        check, group_results = runner()
        checks.append(check)
        results.extend(group_results)
    cross_check, cross_result = _cross_envelope_check()
    checks.append(cross_check)
    results.append(cross_result)
    equality_check, equality_results = _semantic_equality_check()
    checks.append(equality_check)
    results.extend(equality_results)
    checks.append(_authorization_check())
    checks.append(_boundary_check(results))

    passed = all(item.passed for item in checks)
    report = {
        "module_id": MODULE_ID,
        "passed": passed,
        "scenario_group_count": len(EXPECTED_GROUP_IDS),
        "scenario_case_count": EXPECTED_CASE_COUNT,
        "corpus_digest": sha256_digest(corpus),
        "checks": [asdict(item) for item in checks],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
