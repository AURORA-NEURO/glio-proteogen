"""Build and execute the locked M03-05 artifact-detection corpus."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, cast

from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m03_04 import run as m0304_evidence
from evals.m03_04.run import build_capacity_scenario_request as build_m0304_capacity_request
from evals.m03_04.run import build_scenario as build_m0304_scenario
from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m03_02 import ArtifactClaimRole
from glio_proteogen.contracts.m03_03 import ProteinInferenceRawRole
from glio_proteogen.contracts.m03_04 import (
    ProteinInferenceQualityDisposition,
    ProteinInferenceQualityResult,
)
from glio_proteogen.contracts.m03_05 import (
    M0305_CONTAMINATION_SIGNALS,
    M0305_MAX_APPROVED_VERSIONS,
    M0305_MAX_CANONICAL_REQUEST_BYTES,
    M0305_MAX_CLAIMS,
    M0305_MAX_CONTAMINATION_FLAGS,
    M0305_MAX_COUNT,
    M0305_MAX_EVIDENCE,
    M0305_MAX_PROFILES,
    M0305_MAX_SIGNAL_SCORES,
    M0305_MAX_SOURCES,
    M0305_MAX_UNIT_CLAIM_REFS,
    M0305_MAX_UNIT_SOURCE_REFS,
    M0305_MAX_UNITS,
    M0305_SIGNAL_APPLICABLE_UNIT_KINDS,
    M0305_SIGNAL_COUNT,
    ContractName,
    DetectProteinInferenceArtifactsRequest,
    ProteinInferenceArtifactDetectionResult,
    ProteinInferenceArtifactDisposition,
    ProteinInferenceArtifactEvidenceLedger,
    ProteinInferenceArtifactEvidenceUnit,
    ProteinInferenceArtifactFindingCode,
    ProteinInferenceArtifactFlagState,
    ProteinInferenceArtifactObservationState,
    ProteinInferenceArtifactPolicy,
    ProteinInferenceArtifactPosteriorState,
    ProteinInferenceArtifactProfile,
    ProteinInferenceArtifactQualityReceipt,
    ProteinInferenceArtifactSignal,
    ProteinInferenceArtifactSignalCode,
    ProteinInferenceArtifactSignalScore,
    ProteinInferenceArtifactThreshold,
    ProteinInferenceEvidenceUnitKind,
    artifact_evidence_ledger_digest,
    artifact_ledger_bindings_close,
    artifact_quality_receipt,
    artifact_quality_receipt_digest,
    canonical_request_digest,
    claim_binding_digest,
    configuration_digest,
    contract_json_schema,
    policy_digest,
    profile_digest,
    quality_metric_binding_digest,
    result_payload_digest,
    source_binding_digest,
    threshold_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, SupportStatus
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics import (
    compute_protein_inference_quality,
)
from glio_proteogen.modules.c03_protein_inference.m03_05_artifact_detection import (
    M0305Plugin,
    M0305ProteinInferenceArtifactEngine,
    M0305Service,
    detect_protein_inference_artifacts,
    preflight_protein_inference_artifact_authorization,
)

if TYPE_CHECKING:
    from collections.abc import Callable

MODULE_ID = "GLIO-PROTEOGEN-M03-05"
ROOT = Path(__file__).parents[2]
SCENARIO_PATH = ROOT / "tests" / "fixtures" / "m03_05" / "scenarios.json"
_EXPECTED_GROUP_COUNT = 8
_EXPECTED_CASE_COUNT = 57
_SCHEMA_NAMES = (
    "request",
    "output",
    "policy",
    "profile",
    "threshold",
    "quality-receipt",
    "evidence-ledger",
    "evidence-unit",
    "signal-score",
    "posterior",
    "contamination-flag",
    "exclusion-mask",
    "finding",
)
_HTTP_OK = 200
_ONE_THIRD_SCORE = 333_333
_ONE_THIRD_DENOMINATOR = 3


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
    """One genuine M03-04 result plus a closed six-kind artifact ledger."""

    request: DetectProteinInferenceArtifactsRequest
    quality_result: ProteinInferenceQualityResult


class _HostileLedger(Mapping[str, object]):
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


class _ScenarioClosureError(ValueError):
    """The executable evidence builder could not close its own graph."""


_UNSET = object()
_ANCHOR_ROLES = {
    ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE: (
        ProteinInferenceRawRole.PEPTIDE_EVIDENCE,
        ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST,
    ),
    ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP: (
        ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST,
        ArtifactClaimRole.PROTEIN_GROUP_MANIFEST,
    ),
    ProteinInferenceEvidenceUnitKind.AMBIGUITY_CLASS: (
        ProteinInferenceRawRole.AMBIGUITY_MANIFEST,
        ArtifactClaimRole.AMBIGUITY_MANIFEST,
    ),
    ProteinInferenceEvidenceUnitKind.PROTEOFORM_CLAIM: (
        ProteinInferenceRawRole.AMBIGUITY_MANIFEST,
        ArtifactClaimRole.AMBIGUITY_MANIFEST,
    ),
    ProteinInferenceEvidenceUnitKind.CONTROL_GROUP: (
        ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST,
        ArtifactClaimRole.PROTEIN_GROUP_MANIFEST,
    ),
    ProteinInferenceEvidenceUnitKind.SAMPLE_CONTEXT_BINDING: (
        ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE,
        ArtifactClaimRole.COMPLEX_ACTIVITY_INPUT_BUNDLE,
    ),
}


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m0305.{name}",
        version="1.0.0",
        digest=sha256_digest({"m0305_evidence": name}),
        media_type="application/json",
    )


def _thresholds() -> tuple[ProteinInferenceArtifactThreshold, ...]:
    return tuple(
        ProteinInferenceArtifactThreshold(
            signal_code=code,
            review_threshold_ppm=200_000,
            exclude_threshold_ppm=500_000,
            required=True,
            applicable_unit_kinds=tuple(sorted(M0305_SIGNAL_APPLICABLE_UNIT_KINDS[code])),
            evidence=_artifact(f"threshold.{code.value}"),
        )
        for code in ProteinInferenceArtifactSignalCode
    )


def _signals(kind: ProteinInferenceEvidenceUnitKind) -> tuple[ProteinInferenceArtifactSignal, ...]:
    return tuple(
        ProteinInferenceArtifactSignal(
            signal_code=code,
            observation_state=(
                ProteinInferenceArtifactObservationState.OBSERVED
                if kind in M0305_SIGNAL_APPLICABLE_UNIT_KINDS[code]
                else ProteinInferenceArtifactObservationState.NOT_APPLICABLE
            ),
            supporting_count=0,
            evaluated_count=10 if kind in M0305_SIGNAL_APPLICABLE_UNIT_KINDS[code] else 0,
        )
        for code in ProteinInferenceArtifactSignalCode
    )


def _unit(  # noqa: PLR0913 - explicit receipt-bound evidence-unit builder.
    receipt: ProteinInferenceArtifactQualityReceipt,
    kind: ProteinInferenceEvidenceUnitKind,
    *,
    suffix: str | None = None,
    source_ids: tuple[str, ...] | None = None,
    claim_ids: tuple[str, ...] | None = None,
    signals: tuple[ProteinInferenceArtifactSignal, ...] | None = None,
) -> ProteinInferenceArtifactEvidenceUnit:
    source_role, claim_role = _ANCHOR_ROLES[kind]
    claim = next(item for item in receipt.claims if item.claim_role is claim_role)
    source = next(
        item
        for item in receipt.sources
        if item.role is source_role and item.bound_claim_id == claim.claim_id
    )
    resolved_sources = source_ids or (source.source_id,)
    resolved_claims = claim_ids or (claim.claim_id,)
    identity = suffix or kind.value
    return ProteinInferenceArtifactEvidenceUnit(
        unit_id=(
            "unit."
            + sha256_digest(
                {
                    "m0305_unit": identity,
                    "unit_kind": kind,
                    "source_ids": resolved_sources,
                    "claim_ids": resolved_claims,
                }
            ).removeprefix("sha256:")
        ),
        unit_kind=kind,
        source_ids=resolved_sources,
        claim_ids=resolved_claims,
        signals=signals or _signals(kind),
    )


def _policy(receipt: ProteinInferenceArtifactQualityReceipt) -> ProteinInferenceArtifactPolicy:
    if receipt.applicability is None:
        raise _ScenarioClosureError
    profile = ProteinInferenceArtifactProfile(
        profile_id="profile.synthetic.m0305.canonical",
        version="1.0.0",
        applicability=receipt.applicability,
        approved_assay_protocol_versions=(receipt.assay_protocol_version,),
        approved_controlled_vocabulary_versions=(receipt.controlled_vocabulary_version,),
        approved_unit_system_versions=(receipt.unit_system_version,),
        thresholds=_thresholds(),
        evidence=_artifact("profile.canonical"),
    )
    return ProteinInferenceArtifactPolicy(
        policy_id="policy.synthetic.m0305",
        version="1.0.0",
        max_units=M0305_MAX_UNITS,
        max_sources=M0305_MAX_SOURCES,
        max_claims=M0305_MAX_CLAIMS,
        profiles=(profile,),
        evidence=_artifact("policy"),
        reviewed_by="reviewer.synthetic.m0305",
        reviewed_at=receipt.quality_completed_at,
    )


def _build_ledger(
    receipt: ProteinInferenceArtifactQualityReceipt,
    units: tuple[ProteinInferenceArtifactEvidenceUnit, ...],
) -> ProteinInferenceArtifactEvidenceLedger:
    payload: dict[str, object] = {
        "ledger_id": "ledger.synthetic.m0305",
        "version": "1.0.0",
        "quality_result_digest": receipt.quality_result_digest,
        "admission_result_digest": receipt.admission_result_digest,
        "source_manifest_digest": receipt.source_manifest_digest,
        "source_binding_digest": receipt.source_binding_digest,
        "claim_binding_digest": receipt.claim_binding_digest,
        "quality_metric_binding_digest": receipt.quality_metric_binding_digest,
        "applicability": receipt.applicability,
        "units": units,
        "evidence": _artifact("ledger"),
        "recorded_at": receipt.quality_completed_at + timedelta(seconds=1),
    }
    payload["ledger_digest"] = artifact_evidence_ledger_digest(payload)
    return ProteinInferenceArtifactEvidenceLedger.model_validate(payload, strict=True)


def _request_from_quality_result(
    quality_result: ProteinInferenceQualityResult,
) -> DetectProteinInferenceArtifactsRequest:
    receipt = artifact_quality_receipt(quality_result)
    policy = _policy(receipt)
    units = tuple(_unit(receipt, kind) for kind in ProteinInferenceEvidenceUnitKind)
    ledger = _build_ledger(receipt, units)
    references = quality_result.request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
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
    context = quality_result.request.context.model_copy(
        update={
            "request_id": "request.synthetic.m0305",
            "occurred_at": receipt.quality_completed_at + timedelta(seconds=2),
            "references": references.model_copy(
                update={"approved_configuration": approved, "quality": quality}
            ),
        }
    )
    return DetectProteinInferenceArtifactsRequest(
        context=context,
        quality_receipt=receipt,
        evidence_ledger=ledger,
        policy=policy,
    )


def build_scenario() -> Scenario:
    """Execute genuine M01-02 through M03-04 and close the M03-05 request."""

    quality_result = compute_protein_inference_quality(build_m0304_scenario().request)
    return Scenario(
        request=_request_from_quality_result(quality_result),
        quality_result=quality_result,
    )


def build_scenario_request() -> DetectProteinInferenceArtifactsRequest:
    """Public evidence helper for interface and benchmark parity checks."""

    return build_scenario().request


def _ledger(
    request: DetectProteinInferenceArtifactsRequest,
    *,
    units: tuple[ProteinInferenceArtifactEvidenceUnit, ...] | None = None,
    **updates: object,
) -> ProteinInferenceArtifactEvidenceLedger:
    current = request.evidence_ledger
    if current is None:
        raise _ScenarioClosureError
    payload = current.model_dump(mode="python", exclude={"ledger_digest"})
    if units is not None:
        payload["units"] = units
    payload.update(updates)
    payload["ledger_digest"] = artifact_evidence_ledger_digest(payload)
    return ProteinInferenceArtifactEvidenceLedger.model_validate(payload, strict=True)


def _with_units(
    request: DetectProteinInferenceArtifactsRequest,
    units: tuple[ProteinInferenceArtifactEvidenceUnit, ...],
) -> DetectProteinInferenceArtifactsRequest:
    return request.model_copy(update={"evidence_ledger": _ledger(request, units=units)})


def _with_signal(
    request: DetectProteinInferenceArtifactsRequest,
    code: ProteinInferenceArtifactSignalCode,
    *,
    unit_id: str | None = None,
    **updates: object,
) -> DetectProteinInferenceArtifactsRequest:
    ledger = request.evidence_ledger
    if ledger is None:
        raise _ScenarioClosureError
    target = next(
        unit
        for unit in ledger.units
        if (unit_id is None or unit.unit_id == unit_id)
        and unit.unit_kind in M0305_SIGNAL_APPLICABLE_UNIT_KINDS[code]
    )
    signals = tuple(
        ProteinInferenceArtifactSignal.model_validate(item.model_copy(update=updates), strict=True)
        if item.signal_code is code
        else item
        for item in target.signals
    )
    rebuilt = ProteinInferenceArtifactEvidenceUnit.model_validate(
        target.model_copy(update={"signals": signals}), strict=True
    )
    units = tuple(rebuilt if item.unit_id == target.unit_id else item for item in ledger.units)
    return _with_units(request, units)


request_with_signal = _with_signal


def _with_policy(
    request: DetectProteinInferenceArtifactsRequest,
    policy: ProteinInferenceArtifactPolicy,
    *,
    evidence_ledger: ProteinInferenceArtifactEvidenceLedger | object | None = _UNSET,
) -> DetectProteinInferenceArtifactsRequest:
    references = request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    context = request.context.model_copy(
        update={"references": references.model_copy(update={"approved_configuration": approved})}
    )
    ledger = request.evidence_ledger if evidence_ledger is _UNSET else evidence_ledger
    return DetectProteinInferenceArtifactsRequest.model_validate(
        {
            **request.model_dump(mode="python"),
            "context": context,
            "policy": policy,
            "evidence_ledger": ledger,
        },
        strict=True,
    )


def _with_receipt(
    request: DetectProteinInferenceArtifactsRequest,
    receipt: ProteinInferenceArtifactQualityReceipt,
    *,
    evidence_ledger: ProteinInferenceArtifactEvidenceLedger | None,
) -> DetectProteinInferenceArtifactsRequest:
    references = request.context.references
    identity = references.identity_lineage.model_copy(
        update={
            "binding_digest": receipt.identity_resolution_digest,
        }
    )
    quality = references.quality.model_copy(
        update={
            "evidence": references.quality.evidence.model_copy(
                update={"digest": receipt.quality_result_digest}
            )
        }
    )
    context = request.context.model_copy(
        update={
            "references": references.model_copy(
                update={"identity_lineage": identity, "quality": quality}
            )
        }
    )
    return DetectProteinInferenceArtifactsRequest(
        context=context,
        quality_receipt=receipt,
        evidence_ledger=evidence_ledger,
        policy=request.policy,
    )


def _scenario(case_id: str, *, passed: bool, detail: str) -> EvalCheck:
    return EvalCheck(name=f"scenario.{case_id}", passed=passed, detail=detail)


def _fails(operation: Callable[[], object]) -> bool:
    try:
        operation()
    except (TypeError, ValueError, ValidationError):
        return True
    return False


def _authorization_fails(payload: object) -> bool:
    return _fails(lambda: preflight_protein_inference_artifact_authorization(payload))


def _corpus() -> Corpus:
    return cast("Corpus", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _static_checks(corpus: Corpus, scenario: Scenario) -> list[EvalCheck]:
    groups = corpus["scenario_groups"]
    case_ids = [case_id for group in groups for case_id in group["case_ids"]]
    return [
        EvalCheck(
            name="corpus.exact_inventory",
            passed=(
                corpus["module_id"] == MODULE_ID
                and len(groups) == _EXPECTED_GROUP_COUNT
                and len(case_ids) == len(set(case_ids)) == _EXPECTED_CASE_COUNT
            ),
            detail=f"groups={len(groups)};cases={len(case_ids)};unique={len(set(case_ids))}",
        ),
        EvalCheck(
            name="builder.genuine_m0304_projection",
            passed=(
                scenario.request.quality_receipt.quality_result_digest
                == scenario.quality_result.result_digest
                and scenario.quality_result.disposition
                is ProteinInferenceQualityDisposition.QUALIFIED
            ),
            detail=f"quality={scenario.quality_result.result_digest}",
        ),
    ]


def _genuine_closure_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    receipt = request.quality_receipt
    ledger = request.evidence_ledger
    if ledger is None:
        raise _ScenarioClosureError
    result = detect_protein_inference_artifacts(request)
    source_roles = {item.source_id: item.role for item in receipt.sources}
    claim_roles = {item.claim_id: item.claim_role for item in receipt.claims}
    return [
        _scenario(
            "genuine_public_m0102_through_m0304_handoff",
            passed=(
                scenario.quality_result.request.raw_quality_receipt.admission_result_digest
                == receipt.admission_result_digest
                and receipt.quality_result_digest == scenario.quality_result.result_digest
            ),
            detail="public M03-04 result projected without a handwritten upstream envelope",
        ),
        _scenario(
            "compact_quality_receipt_binds_exact_m0304_result",
            passed=(
                receipt.receipt_digest == artifact_quality_receipt_digest(receipt)
                and receipt.quality_request_digest == scenario.quality_result.request_digest
                and receipt.quality_policy_digest == scenario.quality_result.policy_digest
            ),
            detail=f"receipt={receipt.receipt_digest}",
        ),
        _scenario(
            "artifact_ledger_binds_quality_sources_claims_and_metrics",
            passed=(
                ledger.source_binding_digest == source_binding_digest(receipt.sources)
                and ledger.claim_binding_digest == claim_binding_digest(receipt.claims)
                and ledger.quality_metric_binding_digest
                == quality_metric_binding_digest(receipt.quality_metrics)
                and artifact_ledger_bindings_close(request)
            ),
            detail=f"ledger={ledger.ledger_digest}",
        ),
        _scenario(
            "unit_source_and_claim_roles_close_over_compact_receipt",
            passed=all(
                unit.source_ids
                and unit.claim_ids
                and all(source_id in source_roles for source_id in unit.source_ids)
                and all(claim_id in claim_roles for claim_id in unit.claim_ids)
                for unit in ledger.units
            ),
            detail=f"role-closed units={len(ledger.units)}",
        ),
        _scenario(
            "every_evidence_unit_carries_the_exact_eight_signal_domain",
            passed=all(
                len(unit.signals) == M0305_SIGNAL_COUNT
                and {item.signal_code for item in unit.signals}
                == set(ProteinInferenceArtifactSignalCode)
                for unit in ledger.units
            ),
            detail=f"units={len(ledger.units)};signals={len(result.signal_scores)}",
        ),
        _scenario(
            "canonical_clean_evidence_is_clear_and_retained",
            passed=(
                result.disposition is ProteinInferenceArtifactDisposition.CLEARED
                and len(result.exclusion_mask.retain_unit_ids) == len(ledger.units)
                and not result.exclusion_mask.review_unit_ids
                and not result.exclusion_mask.exclude_unit_ids
            ),
            detail=f"retained={len(result.exclusion_mask.retain_unit_ids)}",
        ),
        _scenario(
            "result_preserves_complex_activity_parent_without_emitting_activity",
            passed=(
                result.parent_target == "complex_activity"
                and not result.emits_complex_activity
                and not result.infers_identity
                and not result.infers_protein
                and not result.infers_kinase_activity
            ),
            detail="parent target retained; all biological ownership flags false",
        ),
    ]


def _score_for(
    result: ProteinInferenceArtifactDetectionResult,
    code: ProteinInferenceArtifactSignalCode,
    unit_id: str,
) -> ProteinInferenceArtifactSignalScore:
    return next(
        item
        for item in result.signal_scores
        if item.signal_code is code and item.unit_id == unit_id
    )


def _signal_scoring_checks(scenario: Scenario) -> list[EvalCheck]:
    checks: list[EvalCheck] = []
    for code in ProteinInferenceArtifactSignalCode:
        mutated = _with_signal(
            scenario.request,
            code,
            supporting_count=1,
            evaluated_count=_ONE_THIRD_DENOMINATOR,
        )
        target = next(
            unit
            for unit in cast(
                "ProteinInferenceArtifactEvidenceLedger", mutated.evidence_ledger
            ).units
            if unit.unit_kind in M0305_SIGNAL_APPLICABLE_UNIT_KINDS[code]
        )
        score = _score_for(detect_protein_inference_artifacts(mutated), code, target.unit_id)
        checks.append(
            _scenario(
                f"{code.value}_uses_exact_integer_evidence_fraction",
                passed=(
                    score.evidence_score_ppm == _ONE_THIRD_SCORE
                    and score.flag_state is ProteinInferenceArtifactFlagState.SUSPECTED
                    and score.supporting_count == 1
                    and score.evaluated_count == _ONE_THIRD_DENOMINATOR
                ),
                detail=f"1/3={score.evidence_score_ppm}ppm;state={score.flag_state.value}",
            )
        )
    code = ProteinInferenceArtifactSignalCode.CONTAMINANT_REFERENCE_SUPPORT
    ledger = cast("ProteinInferenceArtifactEvidenceLedger", scenario.request.evidence_ledger)
    peptide_unit_id = next(
        item.unit_id
        for item in ledger.units
        if item.unit_kind is ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE
    )
    boundaries = (
        (199_999, ProteinInferenceArtifactFlagState.CLEAR),
        (200_000, ProteinInferenceArtifactFlagState.SUSPECTED),
        (499_999, ProteinInferenceArtifactFlagState.SUSPECTED),
        (500_000, ProteinInferenceArtifactFlagState.DETECTED),
        (500_001, ProteinInferenceArtifactFlagState.DETECTED),
    )
    observed: list[ProteinInferenceArtifactFlagState] = []
    for supporting, _ in boundaries:
        mutated = _with_signal(
            scenario.request,
            code,
            unit_id=peptide_unit_id,
            supporting_count=supporting,
            evaluated_count=1_000_000,
        )
        target = next(
            item
            for item in cast(
                "ProteinInferenceArtifactEvidenceLedger", mutated.evidence_ledger
            ).units
            if item.unit_kind is ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE
        )
        observed.append(
            _score_for(detect_protein_inference_artifacts(mutated), code, target.unit_id).flag_state
        )
    checks.append(
        _scenario(
            "review_and_exclusion_threshold_equal_adjacent_and_first_excess_boundaries_are_exact",
            passed=tuple(observed) == tuple(expected for _, expected in boundaries),
            detail="199999 clear;200000 review;499999 review;500000/500001 detected",
        )
    )
    return checks


def _contamination_checks(scenario: Scenario) -> list[EvalCheck]:
    seeded = scenario.request
    for code in ProteinInferenceArtifactSignalCode:
        seeded = _with_signal(seeded, code, supporting_count=5, evaluated_count=10)
    seeded_result = detect_protein_inference_artifacts(seeded)
    clean = detect_protein_inference_artifacts(scenario.request)
    contamination = ProteinInferenceArtifactSignalCode.CONTAMINANT_REFERENCE_SUPPORT
    suspected = detect_protein_inference_artifacts(
        _with_signal(scenario.request, contamination, supporting_count=3)
    )
    detected = detect_protein_inference_artifacts(
        _with_signal(scenario.request, contamination, supporting_count=6)
    )
    noncontamination = detect_protein_inference_artifacts(
        _with_signal(
            scenario.request,
            ProteinInferenceArtifactSignalCode.DECOY_COMPETITION_FAILURE,
            supporting_count=6,
        )
    )
    coexisting = _with_signal(scenario.request, contamination, supporting_count=6)
    coexisting = _with_signal(
        coexisting,
        ProteinInferenceArtifactSignalCode.DECOY_COMPETITION_FAILURE,
        observation_state=ProteinInferenceArtifactObservationState.MISSING,
        supporting_count=0,
        evaluated_count=0,
    )
    coexisting_result = detect_protein_inference_artifacts(coexisting)
    probability_schema = cast(
        "dict[str, object]", contract_json_schema("output")["x-glio-contract"]
    )
    return [
        _scenario(
            "all_eight_seeded_critical_signal_classes_are_detected",
            passed=(
                {
                    item.signal_code
                    for item in seeded_result.signal_scores
                    if item.flag_state is ProteinInferenceArtifactFlagState.DETECTED
                }
                == set(ProteinInferenceArtifactSignalCode)
            ),
            detail="eight seeded signal classes reach the exact exclusion boundary",
        ),
        _scenario(
            "canonical_clean_units_have_zero_false_exclusions",
            passed=not clean.exclusion_mask.exclude_unit_ids,
            detail=f"false exclusions={len(clean.exclusion_mask.exclude_unit_ids)}",
        ),
        _scenario(
            "suspected_contamination_flags_review_without_exclusion",
            passed=(
                bool(suspected.contamination_flags)
                and all(
                    item.state is ProteinInferenceArtifactFlagState.SUSPECTED
                    for item in suspected.contamination_flags
                )
                and bool(suspected.exclusion_mask.review_unit_ids)
                and not suspected.exclusion_mask.exclude_unit_ids
            ),
            detail="300000ppm contamination reviews but does not exclude",
        ),
        _scenario(
            "detected_contamination_flags_and_excludes",
            passed=(
                bool(detected.contamination_flags)
                and all(
                    item.state is ProteinInferenceArtifactFlagState.DETECTED
                    for item in detected.contamination_flags
                )
                and bool(detected.exclusion_mask.exclude_unit_ids)
            ),
            detail="600000ppm contamination flags and excludes",
        ),
        _scenario(
            "noncontamination_artifact_never_emits_contamination_flag",
            passed=not noncontamination.contamination_flags,
            detail="decoy competition detection remains artifact-only",
        ),
        _scenario(
            "detected_artifact_precedes_coexisting_indeterminate_signal",
            passed=(
                any(
                    item.state is ProteinInferenceArtifactPosteriorState.DETECTED
                    for item in coexisting_result.artifact_posteriors
                )
                and bool(coexisting_result.exclusion_mask.exclude_unit_ids)
            ),
            detail="detected posterior precedes coexisting required indeterminate evidence",
        ),
        _scenario(
            "artifact_scores_posteriors_and_flags_are_never_calibrated_probabilities",
            passed=(
                all(
                    not item.score_is_calibrated_probability for item in seeded_result.signal_scores
                )
                and all(
                    not item.score_is_calibrated_probability
                    for item in seeded_result.artifact_posteriors
                )
                and all(
                    not item.score_is_calibrated_probability
                    for item in seeded_result.contamination_flags
                )
                and probability_schema["calibratedProbability"] is False
            ),
            detail="score, posterior, flag, and schema probability claims all false",
        ),
    ]


def _missingness_checks(scenario: Scenario) -> list[EvalCheck]:
    code = ProteinInferenceArtifactSignalCode.DECOY_COMPETITION_FAILURE
    missing = detect_protein_inference_artifacts(
        _with_signal(
            scenario.request,
            code,
            observation_state=ProteinInferenceArtifactObservationState.MISSING,
            supporting_count=0,
            evaluated_count=0,
        )
    )
    unsupported = detect_protein_inference_artifacts(
        _with_signal(
            scenario.request,
            code,
            observation_state=ProteinInferenceArtifactObservationState.UNSUPPORTED,
            supporting_count=0,
            evaluated_count=0,
        )
    )
    zero = detect_protein_inference_artifacts(
        _with_signal(scenario.request, code, supporting_count=0, evaluated_count=0)
    )
    clean = detect_protein_inference_artifacts(scenario.request)
    not_applicable = next(
        item
        for item in clean.signal_scores
        if item.unit_kind is ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE
        and item.signal_code is ProteinInferenceArtifactSignalCode.SAMPLE_CONTEXT_DISCORDANCE
    )
    ledger = scenario.request.evidence_ledger
    if ledger is None:
        raise _ScenarioClosureError
    matrix_exact = all(
        {
            item.signal_code
            for item in unit.signals
            if item.observation_state is not ProteinInferenceArtifactObservationState.NOT_APPLICABLE
        }
        == {
            signal
            for signal in ProteinInferenceArtifactSignalCode
            if unit.unit_kind in M0305_SIGNAL_APPLICABLE_UNIT_KINDS[signal]
        }
        for unit in ledger.units
    )
    profile = scenario.request.policy.profiles[0].model_copy(
        update={"approved_assay_protocol_versions": ("99.0.0",)}
    )
    mismatched_policy = scenario.request.policy.model_copy(update={"profiles": (profile,)})
    profile_mismatch = detect_protein_inference_artifacts(
        _with_policy(scenario.request, mismatched_policy)
    )
    sample = detect_protein_inference_artifacts(
        _with_signal(
            scenario.request,
            ProteinInferenceArtifactSignalCode.SAMPLE_CONTEXT_DISCORDANCE,
            supporting_count=3,
        )
    )
    return [
        _scenario(
            "missing_required_signal_abstains_without_becoming_clear",
            passed=(
                missing.disposition is ProteinInferenceArtifactDisposition.ABSTAINED
                and any(
                    item.flag_state is ProteinInferenceArtifactFlagState.INDETERMINATE
                    and item.observation_state is ProteinInferenceArtifactObservationState.MISSING
                    for item in missing.signal_scores
                )
            ),
            detail="missing required signal stays indeterminate and abstains",
        ),
        _scenario(
            "unsupported_required_signal_abstains_without_becoming_negative",
            passed=(
                unsupported.disposition is ProteinInferenceArtifactDisposition.ABSTAINED
                and any(
                    item.flag_state is ProteinInferenceArtifactFlagState.INDETERMINATE
                    and item.observation_state
                    is ProteinInferenceArtifactObservationState.UNSUPPORTED
                    for item in unsupported.signal_scores
                )
            ),
            detail="unsupported required signal stays indeterminate and abstains",
        ),
        _scenario(
            "zero_denominator_observed_signal_is_indeterminate",
            passed=any(
                item.signal_code is code
                and item.observation_state is ProteinInferenceArtifactObservationState.OBSERVED
                and item.evaluated_count == 0
                and item.evidence_score_ppm is None
                and item.flag_state is ProteinInferenceArtifactFlagState.INDETERMINATE
                for item in zero.signal_scores
            ),
            detail="observed 0/0 has no score and is indeterminate",
        ),
        _scenario(
            "out_of_domain_signal_is_exactly_not_applicable",
            passed=(
                not_applicable.observation_state
                is ProteinInferenceArtifactObservationState.NOT_APPLICABLE
                and not_applicable.flag_state is ProteinInferenceArtifactFlagState.NOT_APPLICABLE
                and not_applicable.supporting_count is None
                and not_applicable.evaluated_count is None
                and not_applicable.evidence_score_ppm is None
            ),
            detail="out-of-domain score is exact N/A with no counts or value",
        ),
        _scenario(
            "all_six_unit_kinds_apply_only_the_locked_signal_matrix",
            passed=(
                matrix_exact
                and {item.unit_kind for item in ledger.units}
                == set(ProteinInferenceEvidenceUnitKind)
            ),
            detail="all six unit kinds match the immutable applicability matrix",
        ),
        _scenario(
            "no_matching_artifact_profile_abstains_before_scoring",
            passed=(
                profile_mismatch.disposition is ProteinInferenceArtifactDisposition.ABSTAINED
                and not profile_mismatch.signal_scores
                and {item.code for item in profile_mismatch.findings}
                == {ProteinInferenceArtifactFindingCode.DETECTOR_PROFILE_UNSUPPORTED}
            ),
            detail="unsupported profile emits no scores and a typed abstention",
        ),
        _scenario(
            "sample_context_discordance_is_retained_without_biological_resolution",
            passed=(
                any(
                    item.signal_code
                    is ProteinInferenceArtifactSignalCode.SAMPLE_CONTEXT_DISCORDANCE
                    and item.flag_state is ProteinInferenceArtifactFlagState.SUSPECTED
                    for item in sample.signal_scores
                )
                and not sample.infers_identity
                and not sample.infers_protein
                and not sample.emits_complex_activity
            ),
            detail="sample-context disagreement is categorical evidence, never biology",
        ),
    ]


def _safe_failure_checks(scenario: Scenario) -> list[EvalCheck]:
    template = build_m0304_scenario().request
    admissions = m0304_evidence._m0303_safe_failure_results()
    quality_results = {
        name: compute_protein_inference_quality(
            m0304_evidence._request_from_admission(template, admission)
        )
        for name, admission in admissions.items()
    }
    requests = {
        name: _with_receipt(
            scenario.request,
            artifact_quality_receipt(result),
            evidence_ledger=None,
        )
        for name, result in quality_results.items()
    }
    results = {
        name: detect_protein_inference_artifacts(request) for name, request in requests.items()
    }

    capacity_quality = compute_protein_inference_quality(build_m0304_capacity_request())
    capacity_request = _request_from_quality_result(capacity_quality)
    shape_policy = capacity_request.policy.model_copy(update={"max_sources": M0305_MAX_SOURCES - 1})
    shape_request = _with_policy(
        capacity_request,
        shape_policy,
        evidence_ledger=None,
    )
    shape_result = detect_protein_inference_artifacts(shape_request)

    mismatch_ledger = _ledger(
        scenario.request,
        source_binding_digest=sha256_digest({"stale": "source-binding"}),
    )
    mismatch_result = detect_protein_inference_artifacts(
        scenario.request.model_copy(update={"evidence_ledger": mismatch_ledger})
    )
    suspected = detect_protein_inference_artifacts(
        _with_signal(
            scenario.request,
            ProteinInferenceArtifactSignalCode.NONUNIQUE_MAPPING,
            supporting_count=3,
        )
    )
    expected = {
        "rejected": ProteinInferenceArtifactDisposition.REJECTED,
        "quarantined": ProteinInferenceArtifactDisposition.QUARANTINED,
        "abstained": ProteinInferenceArtifactDisposition.ABSTAINED,
    }
    safe_outputs = (*results.values(), shape_result, mismatch_result)
    return [
        _scenario(
            "m0304_rejected_receipt_propagates_without_ledger_traversal",
            passed=(
                results["rejected"].disposition is ProteinInferenceArtifactDisposition.REJECTED
                and requests["rejected"].evidence_ledger is None
                and not results["rejected"].signal_scores
            ),
            detail="genuine rejected M03-04 result projects to ledger-free rejection",
        ),
        _scenario(
            "m0304_quarantined_receipt_propagates_without_ledger_traversal",
            passed=(
                results["quarantined"].disposition
                is ProteinInferenceArtifactDisposition.QUARANTINED
                and requests["quarantined"].evidence_ledger is None
                and not results["quarantined"].signal_scores
            ),
            detail="genuine quarantined M03-04 result projects to ledger-free quarantine",
        ),
        _scenario(
            "m0304_abstained_receipt_propagates_without_ledger_traversal",
            passed=(
                results["abstained"].disposition is ProteinInferenceArtifactDisposition.ABSTAINED
                and requests["abstained"].evidence_ledger is None
                and not results["abstained"].signal_scores
            ),
            detail="genuine abstained M03-04 result projects to ledger-free abstention",
        ),
        _scenario(
            "unsupported_compact_quality_shape_abstains_without_scoring",
            passed=(
                capacity_request.quality_receipt.source_count == M0305_MAX_SOURCES
                and shape_result.disposition is ProteinInferenceArtifactDisposition.ABSTAINED
                and not shape_result.signal_scores
                and {item.code for item in shape_result.findings}
                == {ProteinInferenceArtifactFindingCode.UPSTREAM_SHAPE_UNSUPPORTED}
            ),
            detail="64-source receipt exceeds local 63-source policy before scoring",
        ),
        _scenario(
            "receipt_ledger_binding_mismatch_quarantines_before_scoring",
            passed=(
                mismatch_result.disposition is ProteinInferenceArtifactDisposition.QUARANTINED
                and not mismatch_result.signal_scores
                and {item.code for item in mismatch_result.findings}
                == {ProteinInferenceArtifactFindingCode.EVIDENCE_LEDGER_BINDING_MISMATCH}
            ),
            detail="re-signed stale source binding quarantines with zero scores",
        ),
        _scenario(
            "reject_quarantine_abstain_and_clear_precedence_is_deterministic",
            passed=(
                all(
                    results[name].disposition is disposition
                    for name, disposition in expected.items()
                )
                and shape_result.disposition is ProteinInferenceArtifactDisposition.ABSTAINED
                and mismatch_result.disposition is ProteinInferenceArtifactDisposition.QUARANTINED
                and suspected.disposition is ProteinInferenceArtifactDisposition.QUARANTINED
                and detect_protein_inference_artifacts(scenario.request).disposition
                is ProteinInferenceArtifactDisposition.CLEARED
            ),
            detail="upstream gates, safe failures, artifact review, and clear path are exact",
        ),
        _scenario(
            "safe_failure_emits_no_score_posterior_flag_or_successful_mask_claim",
            passed=all(
                not item.signal_scores
                and not item.artifact_posteriors
                and not item.contamination_flags
                and not item.exclusion_mask.retain_unit_ids
                and item.support.status is not SupportStatus.SUPPORTED
                for item in safe_outputs
            ),
            detail=f"safe outputs={len(safe_outputs)};all success collections empty",
        ),
    ]


def build_capacity_scenario_request() -> DetectProteinInferenceArtifactsRequest:
    """Build the exact supported 64-source, 48-claim, and 512-unit boundary."""

    quality_result = compute_protein_inference_quality(build_m0304_capacity_request())
    request = _request_from_quality_result(quality_result)
    signals = tuple(
        ProteinInferenceArtifactSignal(
            signal_code=code,
            observation_state=(
                ProteinInferenceArtifactObservationState.OBSERVED
                if ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE
                in M0305_SIGNAL_APPLICABLE_UNIT_KINDS[code]
                else ProteinInferenceArtifactObservationState.NOT_APPLICABLE
            ),
            supporting_count=(
                5
                if code in M0305_CONTAMINATION_SIGNALS
                and ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE
                in M0305_SIGNAL_APPLICABLE_UNIT_KINDS[code]
                else 0
            ),
            evaluated_count=(
                10
                if ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE
                in M0305_SIGNAL_APPLICABLE_UNIT_KINDS[code]
                else 0
            ),
        )
        for code in ProteinInferenceArtifactSignalCode
    )
    units = tuple(
        _unit(
            request.quality_receipt,
            ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE,
            suffix=f"capacity.{index:03d}",
            signals=signals,
        )
        for index in range(M0305_MAX_UNITS)
    )
    return _with_units(request, units)


def _schema_max_items(name: ContractName, property_name: str) -> int | None:
    schema = contract_json_schema(name)
    properties = cast("dict[str, dict[str, object]]", schema["properties"])
    value = properties[property_name].get("maxItems")
    return value if isinstance(value, int) else None


def _strict_capacity_checks(scenario: Scenario) -> list[EvalCheck]:  # noqa: PLR0915
    plugin = M0305Plugin(M0305Service())
    request_bytes = canonical_json_bytes(scenario.request)
    denied_states = {
        "approved_configuration": "rejected",
        "identity_lineage": "unresolved",
        "provenance": "rejected",
        "consent": "withheld",
        "quality": "rejected",
        "support": "rejected",
        "intended_use": "rejected",
    }
    hostile = _HostileLedger()
    denied: list[bool] = []
    for role, state in denied_states.items():
        payload = scenario.request.model_dump(mode="python")
        payload["evidence_ledger"] = hostile
        context = cast("dict[str, object]", payload["context"])
        references = cast("dict[str, dict[str, object]]", context["references"])
        references[role]["state"] = state
        denied.append(_authorization_fails(payload))

    duplicate = b'{"operation":"detect_protein_inference_artifacts",' + request_bytes[1:]
    coerced = scenario.request.model_dump(mode="json")
    coerced["contract_version"] = 1
    unknown = scenario.request.model_dump(mode="json")
    unknown["unexpected"] = True
    nonfinite = request_bytes[:-1] + b',"supersedes_result_digest":NaN}'
    strict_failures = (
        _fails(lambda: plugin.validate(duplicate)),
        _fails(lambda: plugin.validate(coerced)),
        _fails(lambda: plugin.validate(unknown)),
        _fails(lambda: plugin.validate(nonfinite)),
    )

    capacity_request = build_capacity_scenario_request()
    receipt = capacity_request.quality_receipt
    ledger = cast("ProteinInferenceArtifactEvidenceLedger", capacity_request.evidence_ledger)
    peptide_claims = tuple(
        item for item in receipt.claims if item.claim_role.value == "peptide_evidence_manifest"
    )
    bound_pairs = tuple(
        (source.source_id, source.bound_claim_id)
        for source in receipt.sources
        if source.bound_claim_id in {item.claim_id for item in peptide_claims}
    )
    exact_refs = _unit(
        receipt,
        ProteinInferenceEvidenceUnitKind.PEPTIDE_EVIDENCE,
        suffix="exact-eight-references",
        source_ids=tuple(item[0] for item in bound_pairs[:M0305_MAX_UNIT_SOURCE_REFS]),
        claim_ids=tuple(item[1] for item in bound_pairs[:M0305_MAX_UNIT_CLAIM_REFS]),
        signals=tuple(
            item.model_copy(
                update={"supporting_count": M0305_MAX_COUNT, "evaluated_count": M0305_MAX_COUNT}
            )
            if item.signal_code is ProteinInferenceArtifactSignalCode.BATCH_INCONSISTENCY
            else item
            for item in ledger.units[0].signals
        ),
    )
    refs_request = _with_units(capacity_request, (exact_refs,))
    refs_result = detect_protein_inference_artifacts(refs_request)
    canonical_result = detect_protein_inference_artifacts(scenario.request)

    base_profile = capacity_request.policy.profiles[0]
    versions = tuple(f"{index}.0.0" for index in range(1, M0305_MAX_APPROVED_VERSIONS + 1))
    version_profile = ProteinInferenceArtifactProfile.model_validate(
        base_profile.model_copy(
            update={
                "approved_assay_protocol_versions": versions,
                "approved_controlled_vocabulary_versions": versions,
                "approved_unit_system_versions": versions,
            }
        ),
        strict=True,
    )
    profiles = (
        base_profile,
        *(
            ProteinInferenceArtifactProfile.model_validate(
                base_profile.model_copy(
                    update={
                        "profile_id": f"profile.synthetic.m0305.capacity.{index:02d}",
                        "version": f"{index + 1}.0.0",
                        "approved_assay_protocol_versions": (f"{index + 1}.0.0",),
                        "approved_controlled_vocabulary_versions": (f"{index + 1}.0.0",),
                        "approved_unit_system_versions": (f"{index + 1}.0.0",),
                        "evidence": _artifact(f"profile.capacity.{index:02d}"),
                    }
                ),
                strict=True,
            )
            for index in range(1, M0305_MAX_PROFILES)
        ),
    )
    profile_policy = ProteinInferenceArtifactPolicy.model_validate(
        capacity_request.policy.model_copy(update={"profiles": profiles}), strict=True
    )
    profile_request = _with_policy(capacity_request, profile_policy)

    source_payload = receipt.model_dump(mode="python")
    source_payload["sources"] = (
        *receipt.sources,
        receipt.sources[-1].model_copy(
            update={"source_id": "source." + sha256_digest("excess-source").removeprefix("sha256:")}
        ),
    )
    source_payload["source_count"] = M0305_MAX_SOURCES + 1
    source_excess = _fails(
        lambda: ProteinInferenceArtifactQualityReceipt.model_validate(source_payload, strict=True)
    )
    claim_payload = receipt.model_dump(mode="python")
    claim_payload["claims"] = (
        *receipt.claims,
        receipt.claims[-1].model_copy(
            update={"claim_id": "claim." + sha256_digest("excess-claim").removeprefix("sha256:")}
        ),
    )
    claim_payload["claim_count"] = M0305_MAX_CLAIMS + 1
    claim_excess = _fails(
        lambda: ProteinInferenceArtifactQualityReceipt.model_validate(claim_payload, strict=True)
    )
    unit_payload = ledger.model_dump(mode="python")
    unit_payload["units"] = (
        *ledger.units,
        ledger.units[-1].model_copy(
            update={"unit_id": "unit." + sha256_digest("excess-unit").removeprefix("sha256:")}
        ),
    )
    unit_excess = _fails(
        lambda: ProteinInferenceArtifactEvidenceLedger.model_validate(unit_payload, strict=True)
    )
    ref_excess = _fails(
        lambda: ProteinInferenceArtifactEvidenceUnit.model_validate(
            exact_refs.model_copy(
                update={
                    "source_ids": (
                        *exact_refs.source_ids,
                        "source." + sha256_digest("excess-reference").removeprefix("sha256:"),
                    )
                }
            ),
            strict=True,
        )
    )
    count_excess = _fails(
        lambda: ProteinInferenceArtifactSignal.model_validate(
            ledger.units[0]
            .signals[0]
            .model_copy(
                update={
                    "supporting_count": M0305_MAX_COUNT + 1,
                    "evaluated_count": M0305_MAX_COUNT + 1,
                }
            ),
            strict=True,
        )
    )
    profile_excess = _fails(
        lambda: ProteinInferenceArtifactPolicy.model_validate(
            profile_policy.model_copy(
                update={
                    "profiles": (
                        *profiles,
                        profiles[-1].model_copy(
                            update={
                                "profile_id": "profile.synthetic.m0305.excess",
                                "approved_assay_protocol_versions": ("99.0.0",),
                                "approved_controlled_vocabulary_versions": ("99.0.0",),
                                "approved_unit_system_versions": ("99.0.0",),
                            }
                        ),
                    )
                }
            ),
            strict=True,
        )
    )
    version_excess = _fails(
        lambda: ProteinInferenceArtifactProfile.model_validate(
            version_profile.model_copy(
                update={"approved_assay_protocol_versions": (*versions, "99.0.0")}
            ),
            strict=True,
        )
    )
    result_payload = refs_result.model_dump(mode="python")
    result_payload["signal_scores"] = (
        *(
            refs_result.signal_scores[index % len(refs_result.signal_scores)]
            for index in range(M0305_MAX_SIGNAL_SCORES + 1)
        ),
    )
    score_excess = _fails(
        lambda: ProteinInferenceArtifactDetectionResult.model_validate(result_payload, strict=True)
    )
    result_payload = refs_result.model_dump(mode="python")
    result_payload["contamination_flags"] = (
        *(
            refs_result.contamination_flags[index % len(refs_result.contamination_flags)]
            for index in range(M0305_MAX_CONTAMINATION_FLAGS + 1)
        ),
    )
    flag_excess = _fails(
        lambda: ProteinInferenceArtifactDetectionResult.model_validate(result_payload, strict=True)
    )
    evidence_payload = canonical_result.model_dump(mode="python")
    evidence_payload["evidence"] = tuple(
        canonical_result.evidence[index % len(canonical_result.evidence)]
        for index in range(M0305_MAX_EVIDENCE + 1)
    )
    evidence_excess = _fails(
        lambda: ProteinInferenceArtifactDetectionResult.model_validate(
            evidence_payload, strict=True
        )
    )

    padding = b" " * (M0305_MAX_CANONICAL_REQUEST_BYTES - len(request_bytes))
    exact_bytes = request_bytes + padding
    exact_size_accepted = not _fails(lambda: plugin.validate(exact_bytes))
    first_excess_rejected = _fails(lambda: plugin.validate(exact_bytes + b" "))

    shape_policy = scenario.request.policy.model_copy(update={"max_units": 1})
    shape_request = _with_policy(scenario.request, shape_policy)
    shape_result = detect_protein_inference_artifacts(shape_request)
    return [
        _scenario(
            "seven_control_authorization_matrix_precedes_hostile_ledger_traversal",
            passed=(all(denied) and hostile.traversals == 0),
            detail=f"denials={sum(denied)}/7;hostile traversals={hostile.traversals}",
        ),
        _scenario(
            "duplicate_json_object_key_is_rejected",
            passed=strict_failures[0],
            detail="strict plugin rejects a duplicated top-level operation key",
        ),
        _scenario(
            "scalar_coercion_nonfinite_and_unknown_field_are_rejected",
            passed=all(strict_failures[1:]),
            detail="integer contract version, NaN, and extra field all rejected",
        ),
        _scenario(
            "exact_installed_source_claim_unit_score_flag_profile_evidence_and_count_caps_are_accepted",
            passed=(
                receipt.source_count == M0305_MAX_SOURCES
                and receipt.claim_count == M0305_MAX_CLAIMS
                and len(ledger.units) == M0305_MAX_UNITS
                and M0305_MAX_SIGNAL_SCORES == M0305_MAX_UNITS * M0305_SIGNAL_COUNT
                and M0305_MAX_CONTAMINATION_FLAGS == 3 * M0305_MAX_UNITS
                and len(profile_policy.profiles) == M0305_MAX_PROFILES
                and len(profile_request.policy.profiles) == M0305_MAX_PROFILES
                and len(version_profile.approved_assay_protocol_versions)
                == M0305_MAX_APPROVED_VERSIONS
                and len(canonical_result.evidence) == M0305_MAX_EVIDENCE
                and _schema_max_items("output", "evidence") == M0305_MAX_EVIDENCE
                and _schema_max_items("output", "signal_scores") == M0305_MAX_SIGNAL_SCORES
                and _schema_max_items("output", "contamination_flags")
                == M0305_MAX_CONTAMINATION_FLAGS
                and len(exact_refs.source_ids) == M0305_MAX_UNIT_SOURCE_REFS
                and len(exact_refs.claim_ids) == M0305_MAX_UNIT_CLAIM_REFS
                and any(
                    item.evidence_score_ppm == M0305_MAX_COUNT // 10
                    for item in refs_result.signal_scores
                )
            ),
            detail=(
                f"sources={receipt.source_count};claims={receipt.claim_count};"
                f"units={len(ledger.units)};score cap={M0305_MAX_SIGNAL_SCORES};"
                f"flag cap={M0305_MAX_CONTAMINATION_FLAGS};profiles={len(profile_policy.profiles)};"
                f"reachable evidence={len(canonical_result.evidence)}/cap={M0305_MAX_EVIDENCE}"
            ),
        ),
        _scenario(
            "first_excess_source_claim_unit_score_flag_profile_evidence_or_count_is_rejected",
            passed=all(
                (
                    source_excess,
                    claim_excess,
                    unit_excess,
                    ref_excess,
                    count_excess,
                    profile_excess,
                    version_excess,
                    score_excess,
                    flag_excess,
                    evidence_excess,
                )
            ),
            detail="first excess rejected across ten installed bounded collections/scalars",
        ),
        _scenario(
            "canonical_request_exact_byte_cap_and_first_excess_are_enforced",
            passed=(
                len(exact_bytes) == M0305_MAX_CANONICAL_REQUEST_BYTES
                and exact_size_accepted
                and first_excess_rejected
            ),
            detail=f"accepted={len(exact_bytes)} bytes;rejected={len(exact_bytes) + 1}",
        ),
        _scenario(
            "hostile_artifact_ledger_is_not_traversed_before_authorization_and_shape_closure",
            passed=(
                hostile.traversals == 0
                and shape_request.evidence_ledger is not None
                and shape_result.disposition is ProteinInferenceArtifactDisposition.ABSTAINED
                and not shape_result.signal_scores
            ),
            detail="hostile denial stays zero-traversal; oversized unit shape is not scored",
        ),
    ]


def _result_forgery_rejected(
    result: ProteinInferenceArtifactDetectionResult,
    field: str,
) -> bool:
    payload = result.model_dump(mode="python")
    if field == "score":
        scores = list(payload["signal_scores"])
        scores[0] = {**scores[0], "evidence_score_ppm": 999_999}
        payload["signal_scores"] = scores
    elif field == "posterior":
        posteriors = list(payload["artifact_posteriors"])
        posteriors[0] = {**posteriors[0], "state": "clear"}
        payload["artifact_posteriors"] = posteriors
    elif field == "flag":
        flags = list(payload["contamination_flags"])
        flags[0] = {**flags[0], "state": "suspected"}
        payload["contamination_flags"] = flags
    elif field == "mask":
        mask = payload["exclusion_mask"]
        mask["retain_unit_ids"] = tuple(mask["exclude_unit_ids"])
        mask["exclude_unit_ids"] = ()
    elif field == "finding":
        findings = list(payload["findings"])
        findings[0] = {**findings[0], "message": "forged finding"}
        payload["findings"] = findings
    elif field == "disposition":
        payload["disposition"] = "cleared"
    else:
        raise AssertionError(field)
    payload["result_digest"] = result_payload_digest(payload)
    return _fails(
        lambda: ProteinInferenceArtifactDetectionResult.model_validate(payload, strict=True)
    )


def _recursive_privacy_closed(value: object) -> bool:
    prohibited = {
        "patient_id",
        "raw_identity_token",
        "peptide_sequence",
        "protein_accession",
        "protein_abundance",
        "complex_activity_score",
        "treatment_recommendation",
        "clinical_decision",
    }
    if isinstance(value, dict):
        if prohibited & set(value):
            return False
        if "probability" in value and value["probability"] is not None:
            return False
        return all(_recursive_privacy_closed(item) for item in value.values())
    if isinstance(value, list | tuple):
        return all(_recursive_privacy_closed(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return "mpeptidek" not in lowered and "scan=1" not in lowered
    return True


def _canonical_privacy_forgery_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    canonical = detect_protein_inference_artifacts(request)
    payload = request.model_dump(mode="python")
    receipt = payload["quality_receipt"]
    receipt["sources"] = tuple(reversed(receipt["sources"]))
    receipt["claims"] = tuple(reversed(receipt["claims"]))
    receipt["quality_metrics"] = tuple(reversed(receipt["quality_metrics"]))
    ledger = payload["evidence_ledger"]
    ledger["units"] = tuple(reversed(ledger["units"]))
    for unit in ledger["units"]:
        unit["signals"] = tuple(reversed(unit["signals"]))
    profile = payload["policy"]["profiles"][0]
    profile["thresholds"] = tuple(reversed(profile["thresholds"]))
    reordered = DetectProteinInferenceArtifactsRequest.model_validate(payload, strict=True)
    reordered_result = detect_protein_inference_artifacts(reordered)

    service = M0305Service()
    typed = service.execute(request)
    dictionary = service.execute(request.model_dump(mode="python"))
    plugin = M0305Plugin(service)
    strict_json = plugin.run(plugin.validate(canonical_json_bytes(request)))
    digests = (
        canonical_request_digest(request),
        policy_digest(request.policy),
        configuration_digest(request.policy),
        artifact_quality_receipt_digest(request.quality_receipt),
        artifact_evidence_ledger_digest(
            cast("ProteinInferenceArtifactEvidenceLedger", request.evidence_ledger)
        ),
        profile_digest(request.policy.profiles[0]),
        *(threshold_digest(item) for item in request.policy.profiles[0].thresholds),
        result_payload_digest(canonical),
    )
    repeat_digests = (
        canonical_request_digest(request.model_dump(mode="python")),
        policy_digest(request.policy.model_dump(mode="python")),
        configuration_digest(request.policy.model_dump(mode="python")),
        artifact_quality_receipt_digest(request.quality_receipt.model_dump(mode="python")),
        artifact_evidence_ledger_digest(
            cast("ProteinInferenceArtifactEvidenceLedger", request.evidence_ledger).model_dump(
                mode="python"
            )
        ),
        profile_digest(request.policy.profiles[0].model_dump(mode="python")),
        *(
            threshold_digest(item.model_dump(mode="python"))
            for item in request.policy.profiles[0].thresholds
        ),
        result_payload_digest(canonical.model_dump(mode="python")),
    )

    detected_request = _with_signal(
        request,
        ProteinInferenceArtifactSignalCode.CONTAMINANT_REFERENCE_SUPPORT,
        supporting_count=6,
    )
    detected = detect_protein_inference_artifacts(detected_request)
    forgeries = tuple(
        _result_forgery_rejected(detected, field)
        for field in ("score", "posterior", "flag", "mask", "finding", "disposition")
    )

    receipt_payload = request.quality_receipt.model_dump(mode="python", exclude={"receipt_digest"})
    source = receipt_payload["sources"][0]
    receipt_payload["sources"] = (
        {
            **source,
            "source_id": "source."
            + sha256_digest({"resigned_source": source}).removeprefix("sha256:"),
        },
        *receipt_payload["sources"][1:],
    )
    receipt_payload["source_binding_digest"] = source_binding_digest(receipt_payload["sources"])
    receipt_payload["receipt_digest"] = artifact_quality_receipt_digest(receipt_payload)
    resigned_receipt = ProteinInferenceArtifactQualityReceipt.model_validate(
        receipt_payload, strict=True
    )
    resigned_request = _with_receipt(
        request,
        resigned_receipt,
        evidence_ledger=request.evidence_ledger,
    )
    resigned_result = detect_protein_inference_artifacts(resigned_request)
    return [
        _scenario(
            "semantic_reordering_preserves_complete_result_equality",
            passed=(reordered_result == canonical),
            detail="source, claim, metric, unit, signal, and threshold reorderings normalize",
        ),
        _scenario(
            "typed_dictionary_and_strict_json_requests_produce_equal_results",
            passed=(typed == dictionary == strict_json == canonical),
            detail="typed, mapping, and strict JSON public boundaries are completely equal",
        ),
        _scenario(
            "canonical_request_policy_receipt_ledger_and_result_digests_are_stable",
            passed=(
                digests == repeat_digests and all(item.startswith("sha256:") for item in digests)
            ),
            detail=f"stable digest count={len(digests)}",
        ),
        _scenario(
            "recursive_privacy_ownership_and_probability_canaries_are_absent",
            passed=(
                _recursive_privacy_closed(canonical.model_dump(mode="python"))
                and all(
                    not item.score_is_calibrated_probability for item in canonical.signal_scores
                )
                and all(
                    estimate.probability is None
                    for estimate in (
                        canonical.uncertainty.measurement,
                        canonical.uncertainty.sampling,
                        canonical.uncertainty.parameter,
                        canonical.uncertainty.model_form,
                        canonical.uncertainty.identification,
                        canonical.uncertainty.support,
                        canonical.uncertainty.transport,
                    )
                )
            ),
            detail="recursive owned-biological fields absent; all probability slots null/false",
        ),
        _scenario(
            "derived_score_posterior_flag_mask_finding_and_disposition_forgery_matrix_is_rejected",
            passed=all(forgeries),
            detail=f"re-signed derived-output forgeries rejected={sum(forgeries)}/6",
        ),
        _scenario(
            "resigned_nested_quality_projection_without_ledger_rebinding_is_quarantined",
            passed=(
                resigned_result.disposition is ProteinInferenceArtifactDisposition.QUARANTINED
                and not resigned_result.signal_scores
                and {item.code for item in resigned_result.findings}
                == {ProteinInferenceArtifactFindingCode.EVIDENCE_LEDGER_BINDING_MISMATCH}
            ),
            detail="re-signed projected source rename leaves ledger binding stale",
        ),
    ]


def _interface_recovery_evidence_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    library = detect_protein_inference_artifacts(request)
    engine = M0305ProteinInferenceArtifactEngine().detect(request)
    service = M0305Service()
    service_result = service.execute(request)
    plugin = M0305Plugin(service)
    plugin_result = plugin.run(plugin.validate(canonical_json_bytes(request)))
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        request_path = temp / "request.json"
        result_path = temp / "result.json"
        request_path.write_bytes(canonical_json_bytes(request))
        result_path.write_bytes(canonical_json_bytes(library))
        with TestClient(create_app(temp / "eval.sqlite3")) as client:
            api_response = client.post(
                "/v1/modules/M03-05/artifacts",
                content=canonical_json_bytes(request),
                headers={"content-type": "application/json"},
            )
            api_verify_response = client.post(
                "/v1/modules/M03-05/artifacts/verify",
                content=result_path.read_bytes(),
                headers={"content-type": "application/json"},
            )
            api_schemas = {
                name: client.get(f"/v1/contracts/M03-05/{name}/schema") for name in _SCHEMA_NAMES
            }
        api_result = ProteinInferenceArtifactDetectionResult.model_validate_json(
            api_response.content, strict=True
        )
        cli_detect = CliRunner().invoke(
            cli_app,
            ["protein-inference-artifacts", "detect", str(request_path)],
        )
        cli_result = ProteinInferenceArtifactDetectionResult.model_validate_json(
            cli_detect.stdout, strict=True
        )
        cli_verify = CliRunner().invoke(
            cli_app,
            ["protein-inference-artifacts", "verify", str(result_path)],
        )
        cli_verify_result = ProteinInferenceArtifactDetectionResult.model_validate_json(
            cli_verify.stdout,
            strict=True,
        )
        cli_schemas = {
            name: CliRunner().invoke(
                cli_app,
                ["protein-inference-artifacts", "export-schema", name],
            )
            for name in _SCHEMA_NAMES
        }

    superseding = DetectProteinInferenceArtifactsRequest.model_validate(
        {
            **request.model_dump(mode="python"),
            "supersedes_result_digest": library.result_digest,
        },
        strict=True,
    )
    superseding_result = detect_protein_inference_artifacts(superseding)
    schema_parity = all(
        api_schemas[name].status_code == _HTTP_OK
        and api_schemas[name].json() == json.loads(cli_schemas[name].stdout)
        and api_schemas[name].json()["$id"]
        == f"urn:aurora-neuro:glio-proteogen:{MODULE_ID}:1.0.0:{name}"
        for name in _SCHEMA_NAMES
    )
    declared_ids = {
        case_id for group in _corpus()["scenario_groups"] for case_id in group["case_ids"]
    }
    evidence_files = (
        ROOT / "docs" / "modules" / "GLIO-PROTEOGEN-M03-05.md",
        ROOT / "docs" / "modules" / "M03-05.manifest.md",
        ROOT / "docs" / "evidence" / "M03-05.md",
        ROOT / "docs" / "traceability" / "GLIO-PROTEOGEN-M03-05.csv",
        SCENARIO_PATH,
        Path(__file__).with_name("benchmark.py"),
    )
    return [
        _scenario(
            "public_library_engine_service_and_plugin_results_match",
            passed=(library == engine == service_result == plugin_result),
            detail="public library, engine, service, and plugin are completely equal",
        ),
        _scenario(
            "api_detection_result_matches_public_library_operation",
            passed=(api_response.status_code == _HTTP_OK and api_result == library),
            detail=f"status={api_response.status_code};digest={api_result.result_digest}",
        ),
        _scenario(
            "cli_detection_result_matches_public_library_operation",
            passed=(cli_detect.exit_code == 0 and cli_result == library),
            detail=f"exit={cli_detect.exit_code};digest={cli_result.result_digest}",
        ),
        _scenario(
            "api_and_cli_replay_verification_matches_public_library_result",
            passed=(
                api_verify_response.status_code == _HTTP_OK
                and cli_verify.exit_code == 0
                and ProteinInferenceArtifactDetectionResult.model_validate_json(
                    api_verify_response.content,
                    strict=True,
                )
                == library
                and cli_verify_result == library
                and service.verify(library) == library
            ),
            detail=(
                f"api={api_verify_response.status_code};cli={cli_verify.exit_code};"
                f"digest={library.result_digest}"
            ),
        ),
        _scenario(
            "schema_api_and_cli_export_exact_installed_contracts",
            passed=(
                schema_parity
                and len(api_schemas) == len(_SCHEMA_NAMES)
                and all(result.exit_code == 0 for result in cli_schemas.values())
            ),
            detail=f"exact schema pairs={len(api_schemas)};URN prefix exact",
        ),
        _scenario(
            "recovery_requires_new_superseding_artifact_result",
            passed=(
                superseding.supersedes_result_digest == library.result_digest
                and superseding_result.result_digest != library.result_digest
                and request.supersedes_result_digest is None
                and library == detect_protein_inference_artifacts(request)
            ),
            detail=f"prior={library.result_digest};new={superseding_result.result_digest}",
        ),
        _scenario(
            "evidence_artifacts_and_benchmark_time_only_public_m0305_operation",
            passed=(
                all(path.is_file() for path in evidence_files)
                and len(declared_ids) == _EXPECTED_CASE_COUNT
                and "detect_protein_inference_artifacts_only"
                in Path(__file__).with_name("benchmark.py").read_text(encoding="utf-8")
            ),
            detail=f"evidence_files={len(evidence_files)};declared_cases={len(declared_ids)}",
        ),
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    scenario = build_scenario()
    checks = [
        *_static_checks(_corpus(), scenario),
        *_genuine_closure_checks(scenario),
        *_signal_scoring_checks(scenario),
        *_contamination_checks(scenario),
        *_missingness_checks(scenario),
        *_safe_failure_checks(scenario),
        *_strict_capacity_checks(scenario),
        *_canonical_privacy_forgery_checks(scenario),
        *_interface_recovery_evidence_checks(scenario),
    ]
    declared = {case_id for group in _corpus()["scenario_groups"] for case_id in group["case_ids"]}
    executed = {
        check.name.removeprefix("scenario.")
        for check in checks
        if check.name.startswith("scenario.")
    }
    missing = sorted(declared - executed)
    extra = sorted(executed - declared)
    checks.append(
        EvalCheck(
            name="corpus.executable_coverage",
            passed=(
                len(declared) == len(executed) == _EXPECTED_CASE_COUNT and not missing and not extra
            ),
            detail=(
                f"declared={len(declared)};executed={len(executed)};missing={missing};extra={extra}"
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


if __name__ == "__main__":
    raise SystemExit(main())
