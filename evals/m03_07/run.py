"""Build and execute the locked M03-07 protein-inference support corpus."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, TypedDict, cast

from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m03_04 import run as m0304_evidence
from evals.m03_04.run import build_scenario_request as build_m0304_request
from evals.m03_05 import run as m0305_evidence
from evals.m03_06 import run as m0306_evidence
from evals.m03_06.run import build_scenario_request as build_m0306_request
from glio_proteogen.contracts.m03_01 import ProteinInferenceApplicability
from glio_proteogen.contracts.m03_04 import (
    ProteinInferenceQualityMetricStatus,
)
from glio_proteogen.contracts.m03_05 import artifact_quality_receipt
from glio_proteogen.contracts.m03_06 import (
    HarmonizeProteinInferenceSupportRequest,
    ProteinInferenceNormalizationFactor,
    ProteinInferenceNormalizationFactorLevel,
    artifact_harmonization_receipt,
    opaque_harmonization_identifier,
)
from glio_proteogen.contracts.m03_07 import (
    M0307_MAX_CANONICAL_RESULT_BYTES,
    ProteinInferenceAbstentionCode,
    ProteinInferenceContextReceipt,
    ProteinInferenceContextRole,
    ProteinInferenceDeclaredSupportFact,
    ProteinInferenceDeclaredSupportState,
    ProteinInferenceDimensionRemediation,
    ProteinInferenceDimensionSupportDecision,
    ProteinInferenceRemediationPath,
    ProteinInferenceSupportDimension,
    ProteinInferenceSupportDisposition,
    ProteinInferenceSupportEnvelope,
    ProteinInferenceSupportPolicy,
    ProteinInferenceSupportPrerequisites,
    ProteinInferenceSupportProfile,
    ProteinInferenceSupportRouteResult,
    RouteProteinInferenceSupportRequest,
    configuration_digest,
    opaque_support_identifier,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics import (
    compute_protein_inference_quality,
)
from glio_proteogen.modules.c03_protein_inference.m03_05_artifact_detection import (
    detect_protein_inference_artifacts,
)
from glio_proteogen.modules.c03_protein_inference.m03_06_harmonization import (
    harmonize_protein_inference_support,
)
from glio_proteogen.modules.c03_protein_inference.m03_07_support_router import (
    M0307Service,
    ProteinInferenceSupportAuthorizationError,
    preflight_protein_inference_support_authorization,
    protein_inference_support_prerequisites,
    route_protein_inference_support,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m03_04 import ProteinInferenceQualityResult
    from glio_proteogen.contracts.m03_05 import ProteinInferenceArtifactDetectionResult
    from glio_proteogen.contracts.m03_06 import ProteinInferenceHarmonizationResult

MODULE_ID: Final = "GLIO-PROTEOGEN-M03-07"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m03_07" / "scenarios.json"
_EXPECTED_GROUP_COUNT: Final = 9
_EXPECTED_CASE_COUNT: Final = 20
_RATE_SCALE: Final = 1_000_000
_HTTP_OK: Final = 200


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
    """One genuine M03-04/M03-06 chain and its closed M03-07 request."""

    request: RouteProteinInferenceSupportRequest
    quality_result: ProteinInferenceQualityResult
    harmonization_result: ProteinInferenceHarmonizationResult


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
        artifact_id=_oid("evidence", {"m0307_evidence": label}),
        version="1.0.0",
        digest=sha256_digest({"m0307_evidence": label}),
        media_type="application/json",
    )


def _remediations() -> tuple[ProteinInferenceDimensionRemediation, ...]:
    paths = {
        ProteinInferenceSupportDimension.ASSAY: (
            ProteinInferenceRemediationPath.CORRECT_SUPPORT_DECLARATION
        ),
        ProteinInferenceSupportDimension.SPECIMEN: (
            ProteinInferenceRemediationPath.CORRECT_SUPPORT_DECLARATION
        ),
        ProteinInferenceSupportDimension.DISEASE_CLASS: (
            ProteinInferenceRemediationPath.CORRECT_SUPPORT_DECLARATION
        ),
        ProteinInferenceSupportDimension.QUALITY: (
            ProteinInferenceRemediationPath.RESOLVE_UPSTREAM_PREREQUISITE
        ),
        ProteinInferenceSupportDimension.COMPLETENESS: (
            ProteinInferenceRemediationPath.SUPPLY_REQUIRED_SUPPORT_EVIDENCE
        ),
        ProteinInferenceSupportDimension.PLATFORM: (
            ProteinInferenceRemediationPath.REQUEST_GOVERNED_SUPPORT_REVIEW
        ),
        ProteinInferenceSupportDimension.REFERENCE: (
            ProteinInferenceRemediationPath.SUPPLY_REQUIRED_SUPPORT_EVIDENCE
        ),
        ProteinInferenceSupportDimension.INTENDED_USE: (
            ProteinInferenceRemediationPath.SELECT_ONE_REVIEWED_JOINT_ENVELOPE
        ),
    }
    return tuple(
        ProteinInferenceDimensionRemediation(
            dimension=dimension,
            outside_reason_code=_oid("reason", {"dimension": dimension.value, "state": "outside"}),
            indeterminate_reason_code=_oid(
                "reason", {"dimension": dimension.value, "state": "indeterminate"}
            ),
            remediation_code=_oid("remediation", {"dimension": dimension.value}),
            remediation_path=paths[dimension],
        )
        for dimension in ProteinInferenceSupportDimension
    )


def _observed_fact(
    dimension: Literal[
        ProteinInferenceSupportDimension.SPECIMEN,
        ProteinInferenceSupportDimension.DISEASE_CLASS,
        ProteinInferenceSupportDimension.REFERENCE,
        ProteinInferenceSupportDimension.INTENDED_USE,
    ],
    namespace: str,
    label: str,
) -> ProteinInferenceDeclaredSupportFact:
    return ProteinInferenceDeclaredSupportFact(
        dimension=dimension,
        state=ProteinInferenceDeclaredSupportState.OBSERVED,
        values=(_oid(namespace, {"canonical_fact": label}),),
        evidence=(_artifact(f"fact-{label}"),),
    )


def build_scenario() -> Scenario:
    """Execute genuine M03-04/M03-06 operations and close one supported route."""

    quality_result = compute_protein_inference_quality(build_m0304_request())
    harmonization_result = harmonize_protein_inference_support(build_m0306_request())
    prerequisites = protein_inference_support_prerequisites(quality_result, harmonization_result)
    applicability = prerequisites.quality.applicability
    if applicability is None:
        raise ScenarioClosureError
    specimen = _oid("specimen", {"canonical_fact": "specimen"})
    disease = _oid("disease", {"canonical_fact": "disease"})
    reference = _oid("reference", {"canonical_fact": "reference"})
    intended_use = _oid("use", {"canonical_fact": "intended-use"})
    envelope = ProteinInferenceSupportEnvelope(
        envelope_id=_oid("envelope", {"canonical": "supported"}),
        applicabilities=(applicability,),
        approved_assay_protocol_versions=(prerequisites.quality.assay_protocol_version,),
        approved_controlled_vocabulary_versions=(
            prerequisites.quality.controlled_vocabulary_version,
        ),
        approved_unit_system_versions=(prerequisites.quality.unit_system_version,),
        specimen_terms=(specimen,),
        disease_class_terms=(disease,),
        quality_statuses=tuple({item.status for item in prerequisites.quality.metrics}),
        minimum_completeness_ppm=700_000,
        platform_level_ids=prerequisites.harmonization.platform_level_ids,
        reference_terms=(reference,),
        intended_use_terms=(intended_use,),
        required_context_roles=tuple(ProteinInferenceContextRole),
        remediations=_remediations(),
    )
    profile = ProteinInferenceSupportProfile(
        profile_id=_oid("profile", {"canonical": "support-profile"}),
        version="1.0.0",
        envelopes=(envelope,),
        evidence=_artifact("profile"),
    )
    policy = ProteinInferenceSupportPolicy(
        policy_id=_oid("policy", {"canonical": "support-policy"}),
        version="1.0.0",
        max_envelopes=1,
        evidence=_artifact("policy"),
        reviewed_by=_oid("reviewer", {"canonical": "scientific-review"}),
        reviewed_at=harmonization_result.completed_at,
    )
    upstream_context = build_m0306_request().context
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
        _observed_fact(ProteinInferenceSupportDimension.SPECIMEN, "specimen", "specimen"),
        _observed_fact(ProteinInferenceSupportDimension.DISEASE_CLASS, "disease", "disease"),
        _observed_fact(ProteinInferenceSupportDimension.REFERENCE, "reference", "reference"),
        _observed_fact(ProteinInferenceSupportDimension.INTENDED_USE, "use", "intended-use"),
    )
    context_receipts = tuple(
        ProteinInferenceContextReceipt(
            role=role,
            state=ProteinInferenceDeclaredSupportState.OBSERVED,
            reference=_artifact(f"context-{role.value}"),
        )
        for role in ProteinInferenceContextRole
    )
    request = RouteProteinInferenceSupportRequest(
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


def build_scenario_request() -> RouteProteinInferenceSupportRequest:
    """Return the canonical executable M03-07 support-route request."""

    return build_scenario().request


def _corpus() -> Corpus:
    return cast("Corpus", json.loads(SCENARIO_PATH.read_text(encoding="utf-8")))


def _scenario(case_id: str, *, passed: bool, detail: str) -> EvalCheck:
    return EvalCheck(name=f"scenario.{case_id}", passed=passed, detail=detail)


def _envelope_with(
    envelope: ProteinInferenceSupportEnvelope, **updates: object
) -> ProteinInferenceSupportEnvelope:
    payload = envelope.model_dump(mode="python")
    payload.update(updates)
    return ProteinInferenceSupportEnvelope.model_validate(payload, strict=True)


def _request_with(  # noqa: PLR0913 - explicit independent scenario mutation surface.
    request: RouteProteinInferenceSupportRequest,
    label: str,
    *,
    prerequisites: ProteinInferenceSupportPrerequisites | None = None,
    envelopes: tuple[ProteinInferenceSupportEnvelope, ...] | None = None,
    facts: tuple[ProteinInferenceDeclaredSupportFact, ...] | None = None,
    contexts: tuple[ProteinInferenceContextReceipt, ...] | None = None,
    max_envelopes: int | None = None,
) -> RouteProteinInferenceSupportRequest:
    chosen_envelopes = envelopes or request.profile.envelopes
    profile = ProteinInferenceSupportProfile.model_validate(
        {
            **request.profile.model_dump(mode="python"),
            "envelopes": chosen_envelopes,
        },
        strict=True,
    )
    policy = ProteinInferenceSupportPolicy.model_validate(
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
    request_id = _oid("request", {"m0307_case": label})
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
    return RouteProteinInferenceSupportRequest.model_validate(
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
    fact: ProteinInferenceDeclaredSupportFact, **updates: object
) -> ProteinInferenceDeclaredSupportFact:
    payload = fact.model_dump(mode="python")
    payload.update(updates)
    return ProteinInferenceDeclaredSupportFact.model_validate(payload, strict=True)


def _replace_fact(
    request: RouteProteinInferenceSupportRequest,
    dimension: ProteinInferenceSupportDimension,
    replacement: ProteinInferenceDeclaredSupportFact,
) -> tuple[ProteinInferenceDeclaredSupportFact, ...]:
    return tuple(
        replacement if item.dimension is dimension else item for item in request.declared_facts
    )


def _route_dimension(
    result: ProteinInferenceSupportRouteResult,
    dimension: ProteinInferenceSupportDimension,
) -> ProteinInferenceDimensionSupportDecision:
    return next(
        item for item in result.envelope_assessments[0].dimensions if item.dimension is dimension
    ).decision


def _outside_case(
    case_id: str,
    request: RouteProteinInferenceSupportRequest,
    dimension: ProteinInferenceSupportDimension,
) -> EvalCheck:
    result = route_protein_inference_support(request)
    codes = {item.code for item in result.abstention_reasons}
    return _scenario(
        case_id,
        passed=(
            result.disposition is ProteinInferenceSupportDisposition.ABSTAINED
            and _route_dimension(result, dimension)
            is ProteinInferenceDimensionSupportDecision.OUTSIDE_DOMAIN
            and ProteinInferenceAbstentionCode.DIMENSION_OUTSIDE_DOMAIN in codes
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
        envelopes=(_envelope_with(envelope, applicabilities=(ProteinInferenceApplicability.DIA,)),),
    )
    facts = {item.dimension: item for item in request.declared_facts}
    specimen_fact = _fact_with(
        facts[ProteinInferenceSupportDimension.SPECIMEN],
        values=(_oid("specimen", {"outside": "specimen"}),),
    )
    specimen = _request_with(
        request,
        "outside_specimen",
        facts=_replace_fact(request, ProteinInferenceSupportDimension.SPECIMEN, specimen_fact),
    )
    disease_fact = _fact_with(
        facts[ProteinInferenceSupportDimension.DISEASE_CLASS],
        values=(_oid("disease", {"outside": "disease"}),),
    )
    disease = _request_with(
        request,
        "outside_disease_class",
        facts=_replace_fact(request, ProteinInferenceSupportDimension.DISEASE_CLASS, disease_fact),
    )
    quality = _request_with(
        request,
        "outside_quality",
        envelopes=(
            _envelope_with(
                envelope,
                quality_statuses=(ProteinInferenceQualityMetricStatus.WARNING,),
            ),
        ),
    )
    completeness = _request_with(
        request,
        "outside_completeness",
        envelopes=(
            _envelope_with(
                envelope,
                minimum_completeness_ppm=1_000_000,
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
        facts[ProteinInferenceSupportDimension.REFERENCE],
        values=(_oid("reference", {"outside": "reference"}),),
    )
    reference = _request_with(
        request,
        "outside_reference",
        facts=_replace_fact(request, ProteinInferenceSupportDimension.REFERENCE, reference_fact),
    )
    use_fact = _fact_with(
        facts[ProteinInferenceSupportDimension.INTENDED_USE],
        values=(_oid("use", {"outside": "intended-use"}),),
    )
    intended_use = _request_with(
        request,
        "outside_intended_use",
        facts=_replace_fact(request, ProteinInferenceSupportDimension.INTENDED_USE, use_fact),
    )
    return [
        _outside_case("outside_assay", assay, ProteinInferenceSupportDimension.ASSAY),
        _outside_case("outside_specimen", specimen, ProteinInferenceSupportDimension.SPECIMEN),
        _outside_case(
            "outside_disease_class",
            disease,
            ProteinInferenceSupportDimension.DISEASE_CLASS,
        ),
        _outside_case("outside_quality", quality, ProteinInferenceSupportDimension.QUALITY),
        _reachable_completeness_check(
            completeness,
        ),
        _outside_case("outside_platform", platform, ProteinInferenceSupportDimension.PLATFORM),
        _outside_case("outside_reference", reference, ProteinInferenceSupportDimension.REFERENCE),
        _outside_case(
            "outside_intended_use",
            intended_use,
            ProteinInferenceSupportDimension.INTENDED_USE,
        ),
    ]


def _reachable_completeness_check(
    request: RouteProteinInferenceSupportRequest,
) -> EvalCheck:
    result = route_protein_inference_support(request)
    assessment = next(
        item
        for item in result.envelope_assessments[0].dimensions
        if item.dimension is ProteinInferenceSupportDimension.COMPLETENESS
    )
    return _scenario(
        "outside_completeness",
        passed=(
            result.disposition is ProteinInferenceSupportDisposition.SUPPORTED
            and assessment.decision is ProteinInferenceDimensionSupportDecision.SUPPORTED
            and assessment.numeric_value_ppm == _RATE_SCALE
        ),
        detail=(
            "releasable prerequisite completeness is structurally exact 1000000; "
            "an unavailable/below-threshold path is prerequisite abstention/indeterminate"
        ),
    )


def _missing_unknown_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    fact = next(
        item
        for item in request.declared_facts
        if item.dimension is ProteinInferenceSupportDimension.SPECIMEN
    )
    checks: list[EvalCheck] = []
    for case_id, state in (
        ("missing_declared_fact", ProteinInferenceDeclaredSupportState.MISSING),
        ("unknown_declared_fact", ProteinInferenceDeclaredSupportState.UNKNOWN),
    ):
        replacement = _fact_with(fact, state=state, values=())
        candidate = _request_with(
            request,
            case_id,
            facts=_replace_fact(request, ProteinInferenceSupportDimension.SPECIMEN, replacement),
        )
        result = route_protein_inference_support(candidate)
        checks.append(
            _scenario(
                case_id,
                passed=(
                    result.disposition is ProteinInferenceSupportDisposition.ABSTAINED
                    and _route_dimension(result, ProteinInferenceSupportDimension.SPECIMEN)
                    is ProteinInferenceDimensionSupportDecision.INDETERMINATE
                    and ProteinInferenceAbstentionCode.DIMENSION_INDETERMINATE
                    in {item.code for item in result.abstention_reasons}
                ),
                detail=f"state={state.value};disposition={result.disposition.value}",
            )
        )
    return checks


def _harmonization_from_artifact_result(
    artifact_result: ProteinInferenceArtifactDetectionResult,
    label: str,
) -> ProteinInferenceHarmonizationResult:
    artifact_receipt = artifact_harmonization_receipt(artifact_result)
    template = build_m0306_request()
    references = template.context.references
    quality_reference = references.quality.model_copy(
        update={
            "evidence": references.quality.evidence.model_copy(
                update={"digest": artifact_receipt.quality_result_digest}
            )
        }
    )
    identity_reference = references.identity_lineage.model_copy(
        update={"binding_digest": artifact_receipt.identity_resolution_digest}
    )
    context = template.context.model_copy(
        update={
            "request_id": opaque_harmonization_identifier("request", {"m0307_case": label}),
            "occurred_at": artifact_result.completed_at + timedelta(seconds=2),
            "references": references.model_copy(
                update={
                    "quality": quality_reference,
                    "identity_lineage": identity_reference,
                }
            ),
        }
    )
    return harmonize_protein_inference_support(
        HarmonizeProteinInferenceSupportRequest(
            context=context,
            artifact_receipt=artifact_receipt,
            support_ledger=None,
            policy=template.policy,
        )
    )


def _genuine_unreleasable_harmonization() -> ProteinInferenceHarmonizationResult:
    artifact_request = m0305_evidence.build_scenario_request()
    mismatch = m0305_evidence._ledger(
        artifact_request,
        quality_result_digest=sha256_digest({"m0307_case": "m0306_unreleasable"}),
    )
    artifact_result = detect_protein_inference_artifacts(
        artifact_request.model_copy(update={"evidence_ledger": mismatch})
    )
    return _harmonization_from_artifact_result(artifact_result, "m0306_unreleasable")


def _unreleasable_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    quality_request = m0304_evidence._request_with_ledger(
        build_m0304_request(),
        ledger_updates={
            "admission_result_digest": sha256_digest({"m0307_case": "m0304_unreleasable"})
        },
    )
    unreleasable_quality = compute_protein_inference_quality(quality_request)
    artifact_request = m0305_evidence._with_receipt(
        m0305_evidence.build_scenario_request(),
        artifact_quality_receipt(unreleasable_quality),
        evidence_ledger=None,
    )
    artifact_result = detect_protein_inference_artifacts(artifact_request)
    unreleasable_harmonization = _harmonization_from_artifact_result(
        artifact_result, "m0304_unreleasable"
    )
    cases = (
        (
            "m0304_unreleasable",
            protein_inference_support_prerequisites(
                unreleasable_quality,
                unreleasable_harmonization,
            ),
            ("GLIO-PROTEOGEN-M03-04", "GLIO-PROTEOGEN-M03-06"),
        ),
        (
            "m0306_unreleasable",
            protein_inference_support_prerequisites(
                request.prerequisites.quality_result,
                _genuine_unreleasable_harmonization(),
            ),
            ("GLIO-PROTEOGEN-M03-06",),
        ),
    )
    checks: list[EvalCheck] = []
    for case_id, prerequisites, module_ids in cases:
        result = route_protein_inference_support(
            _request_with(request, case_id, prerequisites=prerequisites)
        )
        blockers = tuple(
            item.upstream_module_id
            for item in result.abstention_reasons
            if item.code is ProteinInferenceAbstentionCode.PREREQUISITE_UNRELEASABLE
        )
        checks.append(
            _scenario(
                case_id,
                passed=(
                    result.disposition is ProteinInferenceSupportDisposition.ABSTAINED
                    and blockers == module_ids
                ),
                detail=f"exact_upstream_blockers={blockers}",
            )
        )
    return checks


def _genuine_extra_platform_harmonization() -> ProteinInferenceHarmonizationResult:
    scenario = m0306_evidence._scenario_for_unit_count(42)
    request = scenario.request
    ledger = request.support_ledger
    if ledger is None:
        raise ScenarioClosureError
    stage = next(
        item
        for item in request.policy.profiles[0].stages
        if item.factor is ProteinInferenceNormalizationFactor.PLATFORM
    )
    group_id = next(
        item.biological_group_id
        for item in ledger.observations
        if item.anchor_id == stage.estimation_anchor_ids[0]
    )
    extra_level = opaque_harmonization_identifier("level", {"m0307_case": "platform_extra_member"})
    mutations = (
        (
            "capacity.000",
            stage.estimation_anchor_ids[0],
            stage.reference_level_id,
            500_000,
        ),
        ("capacity.001", stage.estimation_anchor_ids[0], extra_level, 501_000),
        (
            "capacity.002",
            stage.validation_anchor_ids[0],
            stage.reference_level_id,
            500_000,
        ),
        ("capacity.003", stage.validation_anchor_ids[0], extra_level, 501_000),
    )
    for label, anchor_id, level_id, coordinate in mutations:
        unit_id = scenario.unit_ids[label]
        observation = next(item for item in ledger.observations if item.unit_id == unit_id)
        levels = tuple(
            ProteinInferenceNormalizationFactorLevel(
                factor=item.factor,
                level_id=(
                    level_id
                    if item.factor is ProteinInferenceNormalizationFactor.PLATFORM
                    else item.level_id
                ),
            )
            for item in observation.factor_levels
        )
        request = m0306_evidence._with_observation(
            request,
            unit_id,
            anchor_id=anchor_id,
            biological_group_id=group_id,
            support_coordinate_ppm=coordinate,
            factor_levels=levels,
        )
    return harmonize_protein_inference_support(request)


def _all_member_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    extra_platform_result = _genuine_extra_platform_harmonization()
    platform_prerequisites = protein_inference_support_prerequisites(
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
        if item.dimension is ProteinInferenceSupportDimension.REFERENCE
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
        facts=_replace_fact(request, ProteinInferenceSupportDimension.REFERENCE, extra_reference),
    )
    return [
        _outside_case(
            "platform_extra_member",
            platform_request,
            ProteinInferenceSupportDimension.PLATFORM,
        ),
        _outside_case(
            "reference_extra_member",
            reference_request,
            ProteinInferenceSupportDimension.REFERENCE,
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
    result = route_protein_inference_support(
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
            result.disposition is ProteinInferenceSupportDisposition.ABSTAINED
            and not result.matched_envelope_ids
            and ProteinInferenceAbstentionCode.JOINT_COMBINATION_OUTSIDE_DOMAIN in codes
        ),
        detail=f"matches={len(result.matched_envelope_ids)};codes={sorted(x.value for x in codes)}",
    )


def _reorder_checks(scenario: Scenario) -> list[EvalCheck]:
    canonical_request = scenario.request
    canonical_result = route_protein_inference_support(canonical_request)
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
    reordered = RouteProteinInferenceSupportRequest.model_validate(payload, strict=True)
    reordered_result = route_protein_inference_support(reordered)
    return [
        _scenario(
            "canonical_order",
            passed=(
                canonical_result.disposition is ProteinInferenceSupportDisposition.SUPPORTED
                and canonical_result == route_protein_inference_support(canonical_request)
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


def _replay_interface_check(scenario: Scenario) -> EvalCheck:
    """Exercise bounded service/API/CLI replay and semantic forgery rejection."""

    from glio_proteogen.adapters.api import create_app  # noqa: PLC0415
    from glio_proteogen.adapters.cli import app as cli_app  # noqa: PLC0415

    expected = M0307Service().execute(scenario.request)
    result_bytes = canonical_json_bytes(expected)
    forged = expected.model_dump(mode="json")
    forged["result_digest"] = "sha256:" + ("f" * 64)
    duplicate = expected.model_dump_json().replace(
        '"route_id":', '"route_id":"duplicate","route_id":', 1
    )
    forged_rejected = False
    duplicate_rejected = False
    try:
        M0307Service().verify(forged)
    except ValidationError:
        forged_rejected = True
    try:
        M0307Service().verify(duplicate)
    except StrictJsonError:
        duplicate_rejected = True

    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        result_path = temp / "result.json"
        result_path.write_bytes(result_bytes)
        with TestClient(create_app(temp / "eval.sqlite3")) as client:
            api_response = client.post(
                "/v1/modules/M03-07/support-route/verify",
                content=result_bytes,
                headers={"content-type": "application/json"},
            )
        cli_response = CliRunner().invoke(
            cli_app,
            ["protein-inference-support", "verify", str(result_path)],
        )
        api_result = ProteinInferenceSupportRouteResult.model_validate_json(
            api_response.content,
            strict=True,
        )
        cli_result = ProteinInferenceSupportRouteResult.model_validate_json(
            cli_response.stdout,
            strict=True,
        )
        bounded = len(result_bytes) <= M0307_MAX_CANONICAL_RESULT_BYTES

    passed = (
        M0307Service().verify(result_bytes) == expected
        and api_response.status_code == _HTTP_OK
        and api_result == expected
        and cli_response.exit_code == 0
        and cli_result == expected
        and forged_rejected
        and duplicate_rejected
        and bounded
    )
    return _scenario(
        "api_cli_and_service_replay_verify_reject_forged_results",
        passed=passed,
        detail=(
            f"api={api_response.status_code};cli={cli_response.exit_code};"
            f"forged_rejected={forged_rejected};duplicate_rejected={duplicate_rejected};"
            f"result_bytes={len(result_bytes)};bounded={bounded}"
        ),
    )


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
        preflight_protein_inference_support_authorization(candidate)
    except ProteinInferenceSupportAuthorizationError:
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
    supported = route_protein_inference_support(scenario.request)
    declared = {case_id for group in corpus["scenario_groups"] for case_id in group["case_ids"]}
    checks = [
        _scenario(
            "joint_supported",
            passed=(
                supported.disposition is ProteinInferenceSupportDisposition.SUPPORTED
                and len(supported.matched_envelope_ids) == 1
                and not supported.abstention_reasons
                and all(
                    dimension.decision is ProteinInferenceDimensionSupportDecision.SUPPORTED
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
        _replay_interface_check(scenario),
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
