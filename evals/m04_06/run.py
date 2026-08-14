"""Build and execute the locked M04-06 proteoform harmonization corpus."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, TypedDict, cast

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from evals.m04_05.run import (
    build_scenario_request as build_m0405_request,
)
from evals.m04_05.run import (
    build_scenario_result as build_m0405_result,
)
from glio_proteogen.contracts.m04_05 import (
    DetectProteoformArtifactsRequest,
    ProteoformArtifactDetectionResult,
    ProteoformArtifactEvidenceEvent,
    ProteoformArtifactEvidenceLedger,
    ProteoformEvidenceUnitKind,
    evidence_ledger_digest,
)
from glio_proteogen.contracts.m04_06 import (
    M0406_MAX_CANONICAL_REQUEST_BYTES,
    M0406_MAX_EVIDENCE,
    M0406_MAX_FINDINGS,
    M0406_MAX_INVARIANTS,
    M0406_MAX_OBSERVATIONS,
    M0406_MAX_PROFILES,
    M0406_MAX_TARGETS,
    M0406_RATE_SCALE,
    M0406_UPSTREAM_DETECTOR_COUNT,
    ContractName,
    HarmonizeProteoformAnalysisRequest,
    ProteoformArtifactAction,
    ProteoformArtifactHarmonizationReceipt,
    ProteoformArtifactTargetReceipt,
    ProteoformArtifactTargetState,
    ProteoformHarmonizationDiagnosticStatus,
    ProteoformHarmonizationDisposition,
    ProteoformHarmonizationFindingCode,
    ProteoformHarmonizationIdentifierNamespace,
    ProteoformHarmonizationPolicy,
    ProteoformHarmonizationProfile,
    ProteoformHarmonizationResult,
    ProteoformHarmonizedSupportValue,
    ProteoformNormalizationFactor,
    ProteoformNormalizationFactorLevel,
    ProteoformNormalizationStage,
    ProteoformSupportInvariant,
    ProteoformSupportInvariantKind,
    ProteoformSupportLedger,
    ProteoformSupportObservation,
    ProteoformSupportObservationState,
    ProteoformSupportShiftState,
    artifact_harmonization_receipt,
    artifact_receipt_digest,
    canonical_request_digest,
    configuration_digest,
    contract_json_schema,
    harmonization_ledger_bindings_close,
    invariant_digest,
    observation_digest,
    opaque_harmonization_identifier,
    policy_digest,
    profile_digest,
    result_payload_digest,
    stage_digest,
    support_ledger_digest,
    target_binding_digest,
    transformation_manifest_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference
from glio_proteogen.modules.c04_proteoform_isoform.m04_05_artifact_detection import (
    detect_proteoform_artifacts,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_06_harmonization import (
    M0406Plugin,
    M0406ProteoformHarmonizationEngine,
    M0406Service,
    harmonize_proteoform_analysis,
    preflight_proteoform_harmonization_authorization,
)

if TYPE_CHECKING:
    from collections.abc import Callable

MODULE_ID: Final = "GLIO-PROTEOGEN-M04-06"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m04_06" / "scenarios.json"
_EXPECTED_GROUP_COUNT: Final = 8
_EXPECTED_CASE_COUNT: Final = 56
_CANONICAL_TARGET_COUNT: Final = 38
_REFERENCE_COORDINATE_PPM: Final = 500_000
_INVARIANT_SCORE_PPM: Final = 200_000
_FACTOR_COUNT: Final = 8
_CENSORING_BOUND_PPM: Final = 321_000
_RANK_LEFT_COORDINATE_PPM: Final = 650_000
_EXPECTED_RESULT_EVIDENCE_CAP: Final = 16
_EXPECTED_FINDING_CAP: Final = 14
_HTTP_OK: Final = 200
_OPAQUE_DIGEST_LENGTH: Final = 64
_OPAQUE_GRAPH_ID_FIELDS: Final[dict[str, ProteoformHarmonizationIdentifierNamespace]] = {
    "request_id": "request",
    "policy_id": "policy",
    "profile_id": "profile",
    "ledger_id": "ledger",
    "target_id": "target",
    "target_ids": "target",
    "retain_target_ids": "target",
    "review_target_ids": "target",
    "exclude_target_ids": "target",
    "clipped_target_ids": "target",
    "left_target_ids": "target",
    "right_target_ids": "target",
    "anchor_id": "anchor",
    "estimation_anchor_ids": "anchor",
    "validation_anchor_ids": "anchor",
    "biological_group_id": "group",
    "level_id": "level",
    "reference_level_id": "level",
    "invariant_id": "invariant",
    "invariant_ids": "invariant",
    "stage_id": "stage",
    "stage_ids": "stage",
    "reviewed_by": "reviewer",
}
_SCHEMA_NAMES: Final[tuple[ContractName, ...]] = (
    "request",
    "output",
    "policy",
    "profile",
    "stage",
    "artifact-receipt",
    "target-receipt",
    "support-ledger",
    "observation",
    "invariant",
    "analysis",
    "value",
    "transformation-manifest",
    "finding",
)


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
    """One genuine M04-05 result plus its closed M04-06 support request."""

    request: HarmonizeProteoformAnalysisRequest
    artifact_result: ProteoformArtifactDetectionResult
    target_ids: dict[str, str]


class ScenarioClosureError(ValueError):
    """The executable evidence builder could not close its synthetic graph."""


type ScenarioCase = Literal["accepted", "quarantined", "abstained"]


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


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_oid("evidence", {"m0406_evidence": label}),
        version="1.0.0",
        digest=sha256_digest({"m0406_evidence": label}),
        media_type="application/json",
    )


def _oid(
    namespace: ProteoformHarmonizationIdentifierNamespace,
    value: object,
) -> str:
    return opaque_harmonization_identifier(namespace, value)


def _canonical_labels() -> tuple[tuple[str, ProteoformEvidenceUnitKind], ...]:
    labels: list[tuple[str, ProteoformEvidenceUnitKind]] = []
    for factor in ProteoformNormalizationFactor:
        labels.extend(
            (
                f"technical.{factor.value}.{phase}.{side}",
                ProteoformEvidenceUnitKind.SPECTRAL_FEATURE,
            )
            for phase in ("estimation", "validation")
            for side in ("reference", "comparison")
        )
    labels.extend(
        (
            (
                "invariant.direction.left",
                ProteoformEvidenceUnitKind.SPECTRAL_FEATURE,
            ),
            (
                "invariant.direction.right",
                ProteoformEvidenceUnitKind.SPECTRAL_FEATURE,
            ),
            ("invariant.rank.left", ProteoformEvidenceUnitKind.SPECTRAL_FEATURE),
            ("invariant.rank.right", ProteoformEvidenceUnitKind.SPECTRAL_FEATURE),
            (
                "invariant.composition.left",
                ProteoformEvidenceUnitKind.PROTEOFORM_CANDIDATE,
            ),
            (
                "invariant.composition.right",
                ProteoformEvidenceUnitKind.SPECTRAL_FEATURE,
            ),
        )
    )
    return tuple(labels)


def _target_id(label: str, kind: ProteoformEvidenceUnitKind) -> str:
    return _oid("target", {"m0406_target": label, "unit_kind": kind.value})


def _upstream_id(namespace: str, value: object) -> str:
    return f"{namespace}.{sha256_digest(value).removeprefix('sha256:')}"


def _expanded_artifact_request(
    target_count: int,
) -> tuple[DetectProteoformArtifactsRequest, dict[str, str]]:
    if not _CANONICAL_TARGET_COUNT <= target_count <= M0406_MAX_TARGETS:
        raise ScenarioClosureError
    base = build_m0405_request("canonical_clear")
    ledger = base.evidence_ledger
    if ledger is None:
        raise ScenarioClosureError
    templates = tuple(sorted(ledger.events, key=lambda item: item.detector_class.value))
    if len(templates) != M0406_UPSTREAM_DETECTOR_COUNT:
        raise ScenarioClosureError
    labels = list(_canonical_labels())
    labels.extend(
        (f"capacity.{index:03d}", ProteoformEvidenceUnitKind.SPECTRAL_FEATURE)
        for index in range(target_count - len(labels))
    )
    target_ids = {label: _target_id(label, kind) for label, kind in labels}
    events: list[ProteoformArtifactEvidenceEvent] = []
    for label, kind in labels:
        target_id = target_ids[label]
        for template in templates:
            events.append(
                ProteoformArtifactEvidenceEvent.model_validate(
                    {
                        **template.model_dump(mode="python"),
                        "event_id": _upstream_id(
                            "event",
                            {
                                "m0406_target": target_id,
                                "detector_class": template.detector_class.value,
                            },
                        ),
                        "sequence": len(events) + 1,
                        "target_id": target_id,
                        "unit_kind": kind,
                    },
                    strict=True,
                )
            )
    payload = ledger.model_dump(mode="python", exclude={"ledger_digest"})
    payload["ledger_id"] = _upstream_id(
        "ledger",
        {"m0406_targets": tuple(sorted(target_ids.values()))},
    )
    payload["events"] = tuple(events)
    payload["ledger_digest"] = evidence_ledger_digest(payload)
    expanded_ledger = ProteoformArtifactEvidenceLedger.model_validate(payload, strict=True)
    request = DetectProteoformArtifactsRequest.model_validate(
        {
            **base.model_dump(mode="python"),
            "evidence_ledger": expanded_ledger,
        },
        strict=True,
    )
    return request, target_ids


def _factor_levels(
    comparison_factor: ProteoformNormalizationFactor | None = None,
) -> tuple[ProteoformNormalizationFactorLevel, ...]:
    return tuple(
        ProteoformNormalizationFactorLevel(
            factor=factor,
            level_id=(
                _oid("level", {"factor": factor.value, "side": "comparison"})
                if factor is comparison_factor
                else _oid("level", {"factor": factor.value, "side": "reference"})
            ),
        )
        for factor in ProteoformNormalizationFactor
    )


def _observation(  # noqa: PLR0913 - explicit receipt-bound observation builder.
    *,
    label: str,
    anchor_id: str,
    biological_group_id: str,
    coordinate_ppm: int,
    comparison_factor: ProteoformNormalizationFactor | None,
    target_ids: dict[str, str],
    receipt_units: dict[str, ProteoformArtifactTargetReceipt],
) -> ProteoformSupportObservation:
    target = receipt_units[target_ids[label]]
    return ProteoformSupportObservation(
        target_id=target.target_id,
        unit_kind=target.unit_kind,
        artifact_target_state=target.target_state,
        artifact_action=target.action,
        artifact_posterior_digests=target.posterior_digests,
        artifact_posterior_binding_digest=target.posterior_binding_digest,
        artifact_contamination_flag_ids=target.contamination_flag_ids,
        artifact_excluded=target.excluded,
        anchor_id=anchor_id,
        biological_group_id=biological_group_id,
        state=ProteoformSupportObservationState.OBSERVED,
        support_coordinate_ppm=coordinate_ppm,
        factor_levels=_factor_levels(comparison_factor),
        evidence=(_artifact(f"observation.{label}"),),
    )


def _canonical_observations(
    receipt: ProteoformArtifactHarmonizationReceipt,
    target_ids: dict[str, str],
) -> tuple[ProteoformSupportObservation, ...]:
    receipt_units = {item.target_id: item for item in receipt.targets}
    observations: list[ProteoformSupportObservation] = []
    for index, factor in enumerate(ProteoformNormalizationFactor, start=1):
        delta = index * 1_000
        for phase in ("estimation", "validation"):
            anchor_id = _oid("anchor", {"purpose": phase, "factor": factor.value})
            observations.extend(
                (
                    _observation(
                        label=f"technical.{factor.value}.{phase}.reference",
                        anchor_id=anchor_id,
                        biological_group_id=_oid("group", {"purpose": "technical"}),
                        coordinate_ppm=_REFERENCE_COORDINATE_PPM,
                        comparison_factor=None,
                        target_ids=target_ids,
                        receipt_units=receipt_units,
                    ),
                    _observation(
                        label=f"technical.{factor.value}.{phase}.comparison",
                        anchor_id=anchor_id,
                        biological_group_id=_oid("group", {"purpose": "technical"}),
                        coordinate_ppm=_REFERENCE_COORDINATE_PPM + delta,
                        comparison_factor=factor,
                        target_ids=target_ids,
                        receipt_units=receipt_units,
                    ),
                )
            )
    observations.extend(
        (
            _observation(
                label="invariant.direction.left",
                anchor_id=_oid("anchor", {"invariant": "direction"}),
                biological_group_id=_oid("group", {"invariant": "direction", "side": "left"}),
                coordinate_ppm=600_000,
                comparison_factor=None,
                target_ids=target_ids,
                receipt_units=receipt_units,
            ),
            _observation(
                label="invariant.direction.right",
                anchor_id=_oid("anchor", {"invariant": "direction"}),
                biological_group_id=_oid("group", {"invariant": "direction", "side": "right"}),
                coordinate_ppm=400_000,
                comparison_factor=None,
                target_ids=target_ids,
                receipt_units=receipt_units,
            ),
            _observation(
                label="invariant.rank.left",
                anchor_id=_oid("anchor", {"invariant": "rank", "side": "left"}),
                biological_group_id=_oid("group", {"invariant": "rank"}),
                coordinate_ppm=650_000,
                comparison_factor=None,
                target_ids=target_ids,
                receipt_units=receipt_units,
            ),
            _observation(
                label="invariant.rank.right",
                anchor_id=_oid("anchor", {"invariant": "rank", "side": "right"}),
                biological_group_id=_oid("group", {"invariant": "rank"}),
                coordinate_ppm=450_000,
                comparison_factor=None,
                target_ids=target_ids,
                receipt_units=receipt_units,
            ),
            _observation(
                label="invariant.composition.left",
                anchor_id=_oid("anchor", {"invariant": "composition"}),
                biological_group_id=_oid("group", {"invariant": "composition"}),
                coordinate_ppm=200_000,
                comparison_factor=None,
                target_ids=target_ids,
                receipt_units=receipt_units,
            ),
            _observation(
                label="invariant.composition.right",
                anchor_id=_oid("anchor", {"invariant": "composition"}),
                biological_group_id=_oid("group", {"invariant": "composition"}),
                coordinate_ppm=800_000,
                comparison_factor=None,
                target_ids=target_ids,
                receipt_units=receipt_units,
            ),
        )
    )
    for label, target_id in target_ids.items():
        if not label.startswith("capacity."):
            continue
        target = receipt_units[target_id]
        observations.append(
            ProteoformSupportObservation(
                target_id=target.target_id,
                unit_kind=target.unit_kind,
                artifact_target_state=target.target_state,
                artifact_action=target.action,
                artifact_posterior_digests=target.posterior_digests,
                artifact_posterior_binding_digest=target.posterior_binding_digest,
                artifact_contamination_flag_ids=target.contamination_flag_ids,
                artifact_excluded=target.excluded,
                anchor_id=_oid("anchor", {"capacity": label}),
                biological_group_id=_oid("group", {"purpose": "capacity"}),
                state=ProteoformSupportObservationState.OBSERVED,
                support_coordinate_ppm=_REFERENCE_COORDINATE_PPM,
                factor_levels=_factor_levels(),
                evidence=(_artifact(f"observation.{label}"),),
            )
        )
    return tuple(observations)


def _invariants(target_ids: dict[str, str]) -> tuple[ProteoformSupportInvariant, ...]:
    return (
        ProteoformSupportInvariant(
            invariant_id=_oid("invariant", {"kind": "support_direction"}),
            kind=ProteoformSupportInvariantKind.SUPPORT_DIRECTION,
            left_target_ids=(target_ids["invariant.direction.left"],),
            right_target_ids=(target_ids["invariant.direction.right"],),
        ),
        ProteoformSupportInvariant(
            invariant_id=_oid("invariant", {"kind": "support_rank"}),
            kind=ProteoformSupportInvariantKind.SUPPORT_RANK,
            left_target_ids=(target_ids["invariant.rank.left"],),
            right_target_ids=(target_ids["invariant.rank.right"],),
        ),
        ProteoformSupportInvariant(
            invariant_id=_oid("invariant", {"kind": "composition_fraction"}),
            kind=ProteoformSupportInvariantKind.COMPOSITION_FRACTION,
            left_target_ids=(target_ids["invariant.composition.left"],),
            right_target_ids=(target_ids["invariant.composition.right"],),
        ),
    )


def _support_ledger(
    artifact_result: ProteoformArtifactDetectionResult,
    receipt: ProteoformArtifactHarmonizationReceipt,
    target_ids: dict[str, str],
) -> ProteoformSupportLedger:
    payload: dict[str, object] = {
        "ledger_id": _oid("ledger", {"target_ids": tuple(sorted(target_ids.values()))}),
        "version": "1.0.0",
        "artifact_result_digest": receipt.artifact_result_digest,
        "artifact_receipt_digest": receipt.receipt_digest,
        "artifact_target_binding_digest": receipt.target_binding_digest,
        "observations": _canonical_observations(receipt, target_ids),
        "invariants": _invariants(target_ids),
        "evidence": _artifact("support-ledger"),
        "recorded_at": artifact_result.completed_at + timedelta(seconds=1),
    }
    payload["ledger_digest"] = support_ledger_digest(payload)
    return ProteoformSupportLedger.model_validate(payload, strict=True)


def _profile(
    receipt: ProteoformArtifactHarmonizationReceipt,
) -> ProteoformHarmonizationProfile:
    if receipt.applicability is None:
        raise ScenarioClosureError
    stages = tuple(
        ProteoformNormalizationStage(
            stage_id=_oid("stage", {"factor": factor.value, "ordinal": index}),
            ordinal=index,
            factor=factor,
            reference_level_id=_oid("level", {"factor": factor.value, "side": "reference"}),
            estimation_anchor_ids=(
                _oid("anchor", {"purpose": "estimation", "factor": factor.value}),
            ),
            validation_anchor_ids=(
                _oid("anchor", {"purpose": "validation", "factor": factor.value}),
            ),
        )
        for index, factor in enumerate(ProteoformNormalizationFactor, start=1)
    )
    return ProteoformHarmonizationProfile(
        profile_id=_oid("profile", {"purpose": "canonical", "receipt": receipt.receipt_digest}),
        version="1.0.0",
        applicability=receipt.applicability,
        approved_assay_protocol_versions=(receipt.assay_protocol_version,),
        approved_specimen_processing_versions=(receipt.specimen_processing_version,),
        approved_controlled_vocabulary_versions=(receipt.controlled_vocabulary_version,),
        approved_unit_system_versions=(receipt.unit_system_version,),
        stages=stages,
        evidence=_artifact("profile"),
    )


def _policy(
    receipt: ProteoformArtifactHarmonizationReceipt,
) -> ProteoformHarmonizationPolicy:
    return ProteoformHarmonizationPolicy(
        policy_id=_oid("policy", {"purpose": "canonical", "receipt": receipt.receipt_digest}),
        version="1.0.0",
        max_targets=M0406_MAX_TARGETS,
        max_invariants=M0406_MAX_INVARIANTS,
        max_absolute_shift_ppm=100_000,
        technical_effect_tolerance_ppm=0,
        biological_invariant_tolerance_ppm=0,
        min_estimation_pairs_per_level=1,
        min_validation_pairs_per_level=1,
        profiles=(_profile(receipt),),
        evidence=_artifact("policy"),
        reviewed_by=_oid(
            "reviewer",
            {"purpose": "canonical_policy_review", "receipt": receipt.receipt_digest},
        ),
        reviewed_at=receipt.artifact_completed_at,
    )


def _scenario_for_target_count(target_count: int) -> Scenario:
    artifact_request, target_ids = _expanded_artifact_request(target_count)
    artifact_result = detect_proteoform_artifacts(artifact_request)
    receipt = artifact_harmonization_receipt(artifact_result)
    ledger = _support_ledger(artifact_result, receipt, target_ids)
    policy = _policy(receipt)
    references = artifact_request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "decision_id": _upstream_id(
                "decision",
                {"m0406_policy": policy.policy_id, "version": policy.version},
            ),
            "evidence": ArtifactReference(
                artifact_id=_oid(
                    "evidence",
                    {"m0406_configuration": policy.policy_id, "version": policy.version},
                ),
                version="1.0.0",
                digest=configuration_digest(policy),
                media_type="application/vnd.glio-proteogen.m04-06.configuration+json",
            ),
        }
    )
    context = artifact_request.context.model_copy(
        update={
            "request_id": _oid(
                "request", {"target_count": target_count, "ledger": ledger.ledger_digest}
            ),
            "occurred_at": artifact_result.completed_at + timedelta(seconds=2),
            "references": references.model_copy(update={"approved_configuration": approved}),
        }
    )
    request = HarmonizeProteoformAnalysisRequest(
        context=context,
        artifact_result=artifact_result,
        artifact_receipt=receipt,
        support_ledger=ledger,
        policy=policy,
    )
    return Scenario(request=request, artifact_result=artifact_result, target_ids=target_ids)


def _request_for_artifact_result(
    artifact_result: ProteoformArtifactDetectionResult,
) -> HarmonizeProteoformAnalysisRequest:
    """Close a ledger-free M04-06 request around one genuine safe-failure result."""

    receipt = artifact_harmonization_receipt(artifact_result)
    policy = _policy(receipt)
    references = artifact_result.request.context.references
    config_digest = configuration_digest(policy)
    approved = references.approved_configuration.model_copy(
        update={
            "decision_id": _upstream_id(
                "decision",
                {
                    "m0406_safe_policy": policy.policy_id,
                    "result": artifact_result.result_digest,
                },
            ),
            "evidence": ArtifactReference(
                artifact_id=_oid(
                    "evidence",
                    {"m0406_safe_configuration": config_digest},
                ),
                version="1.0.0",
                digest=config_digest,
                media_type="application/vnd.glio-proteogen.m04-06.configuration+json",
            ),
        }
    )
    context = artifact_result.request.context.model_copy(
        update={
            "request_id": _oid(
                "request",
                {"m0406_safe_result": artifact_result.result_digest},
            ),
            "occurred_at": max(artifact_result.completed_at, policy.reviewed_at)
            + timedelta(seconds=2),
            "references": references.model_copy(update={"approved_configuration": approved}),
        }
    )
    return HarmonizeProteoformAnalysisRequest(
        context=context,
        artifact_result=artifact_result,
        artifact_receipt=receipt,
        support_ledger=None,
        policy=policy,
    )


def build_scenario() -> Scenario:
    """Execute genuine M04-01 through M04-05 and close the canonical M04-06 request."""

    return _scenario_for_target_count(_CANONICAL_TARGET_COUNT)


def build_scenario_request(
    case_id: ScenarioCase = "accepted",
) -> HarmonizeProteoformAnalysisRequest:
    """Return a genuine accepted, quarantined, or abstained M04-06 request."""

    if case_id == "accepted":
        return build_scenario().request
    upstream_case = {
        "quarantined": "upstream_quarantined",
        "abstained": "upstream_abstained",
    }[case_id]
    return _request_for_artifact_result(build_m0405_result(upstream_case))


def build_scenario_result(
    case_id: ScenarioCase = "accepted",
) -> ProteoformHarmonizationResult:
    """Build one genuine accepted, quarantined, or abstained M04-06 result."""

    return harmonize_proteoform_analysis(build_scenario_request(case_id))


def build_capacity_scenario_request() -> HarmonizeProteoformAnalysisRequest:
    """Return a valid exact 512-target and 512-observation M04-06 request."""

    return _scenario_for_target_count(M0406_MAX_TARGETS).request


def _rebuild_support_ledger(
    request: HarmonizeProteoformAnalysisRequest,
    *,
    observations: tuple[ProteoformSupportObservation, ...] | None = None,
    invariants: tuple[ProteoformSupportInvariant, ...] | None = None,
    **updates: object,
) -> ProteoformSupportLedger:
    ledger = request.support_ledger
    if ledger is None:
        raise ScenarioClosureError
    payload = ledger.model_dump(mode="python", exclude={"ledger_digest"})
    if observations is not None:
        payload["observations"] = observations
    if invariants is not None:
        payload["invariants"] = invariants
    payload.update(updates)
    payload["ledger_digest"] = support_ledger_digest(payload)
    return ProteoformSupportLedger.model_validate(payload, strict=True)


def _with_support_ledger(
    request: HarmonizeProteoformAnalysisRequest,
    ledger: ProteoformSupportLedger,
) -> HarmonizeProteoformAnalysisRequest:
    return HarmonizeProteoformAnalysisRequest.model_validate(
        {**request.model_dump(mode="python"), "support_ledger": ledger},
        strict=True,
    )


def _with_observation(
    request: HarmonizeProteoformAnalysisRequest,
    target_id: str,
    **updates: object,
) -> HarmonizeProteoformAnalysisRequest:
    ledger = request.support_ledger
    if ledger is None:
        raise ScenarioClosureError
    observations = tuple(
        item.model_copy(update=updates) if item.target_id == target_id else item
        for item in ledger.observations
    )
    return _with_support_ledger(
        request,
        _rebuild_support_ledger(request, observations=observations),
    )


def _with_policy(
    request: HarmonizeProteoformAnalysisRequest,
    policy: ProteoformHarmonizationPolicy,
    *,
    support_ledger: ProteoformSupportLedger | object | None = ...,
) -> HarmonizeProteoformAnalysisRequest:
    references = request.context.references
    config_digest = configuration_digest(policy)
    approved = references.approved_configuration.model_copy(
        update={
            "decision_id": _upstream_id(
                "decision",
                {"m0406_policy": policy.policy_id, "configuration": config_digest},
            ),
            "evidence": ArtifactReference(
                artifact_id=_oid(
                    "evidence",
                    {"m0406_configuration": config_digest},
                ),
                version="1.0.0",
                digest=config_digest,
                media_type="application/vnd.glio-proteogen.m04-06.configuration+json",
            ),
        }
    )
    context = request.context.model_copy(
        update={"references": references.model_copy(update={"approved_configuration": approved})}
    )
    ledger = request.support_ledger if support_ledger is ... else support_ledger
    return HarmonizeProteoformAnalysisRequest.model_validate(
        {
            **request.model_dump(mode="python"),
            "context": context,
            "support_ledger": ledger,
            "policy": policy,
        },
        strict=True,
    )


def _fails(operation: Callable[[], object]) -> bool:
    try:
        operation()
    except (TypeError, ValueError):
        return True
    return False


def _plugin_rejects(candidate: object) -> bool:
    return _fails(lambda: M0406Plugin(M0406Service()).validate(candidate))


def _authorization_rejects(candidate: object) -> bool:
    return _fails(lambda: preflight_proteoform_harmonization_authorization(candidate))


def _corpus() -> Corpus:
    return cast("Corpus", json.loads(SCENARIO_PATH.read_text(encoding="utf-8")))


def _scenario(name: str, *, passed: bool, detail: str) -> EvalCheck:
    return EvalCheck(name=f"scenario.{name}", passed=passed, detail=detail)


def _genuine_closure_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    result = harmonize_proteoform_analysis(request)
    ledger = request.support_ledger
    analysis = result.analysis
    return [
        _scenario(
            "genuine_public_m0401_through_m0405_handoff",
            passed=(
                scenario.artifact_result.request.evidence_ledger is not None
                and scenario.artifact_result.request.evidence_ledger.quality_result_digest
                == scenario.artifact_result.request.quality_result.result_digest
                and scenario.artifact_result.receipt.quality_result_digest
                == scenario.artifact_result.request.quality_result.result_digest
                and scenario.artifact_result.result_digest
                == request.artifact_receipt.artifact_result_digest
            ),
            detail="public M04-05 builder executes the genuine M04-01 through M04-04 chain",
        ),
        _scenario(
            "derived_artifact_receipt_binds_exact_m0405_result",
            passed=(
                request.artifact_receipt == artifact_harmonization_receipt(scenario.artifact_result)
                and request.artifact_receipt.receipt_digest
                == artifact_receipt_digest(request.artifact_receipt)
            ),
            detail="derived receipt revalidates and binds the exact public M04-05 result",
        ),
        _scenario(
            "support_ledger_binds_exact_artifact_target_projection",
            passed=(
                ledger is not None
                and harmonization_ledger_bindings_close(request)
                and ledger.artifact_target_binding_digest
                == target_binding_digest(request.artifact_receipt.targets)
            ),
            detail="support ledger closes over all 38 projected artifact targets",
        ),
        _scenario(
            "every_observation_binds_all_seven_m0405_posteriors_and_mask_action",
            passed=(
                ledger is not None
                and all(
                    any(
                        observation.target_id == target.target_id
                        and observation.unit_kind is target.unit_kind
                        and observation.artifact_target_state is target.target_state
                        and observation.artifact_action is target.action
                        and observation.artifact_posterior_digests == target.posterior_digests
                        and observation.artifact_posterior_binding_digest
                        == target.posterior_binding_digest
                        and observation.artifact_contamination_flag_ids
                        == target.contamination_flag_ids
                        and observation.artifact_excluded is target.excluded
                        for target in request.artifact_receipt.targets
                    )
                    for observation in ledger.observations
                )
            ),
            detail="every observation preserves its exact seven-posterior M04-05 projection",
        ),
        _scenario(
            "every_support_observation_carries_exact_eight_factor_shape",
            passed=(
                ledger is not None
                and all(
                    len(item.factor_levels) == _FACTOR_COUNT
                    and {level.factor for level in item.factor_levels}
                    == set(ProteoformNormalizationFactor)
                    for item in ledger.observations
                )
            ),
            detail="all 38 observations carry exactly all eight factors",
        ),
        _scenario(
            "canonical_clean_harmonization_is_accepted",
            passed=(
                result.disposition is ProteoformHarmonizationDisposition.ACCEPTED
                and not result.findings
                and result.transformation_manifest is not None
                and all(
                    item.status is ProteoformHarmonizationDiagnosticStatus.PASSED
                    for item in result.technical_effect_diagnostics
                )
                and all(
                    item.status is ProteoformHarmonizationDiagnosticStatus.PASSED
                    for item in result.invariant_diagnostics
                )
            ),
            detail="all 8 technical and all 3 invariant diagnostics pass",
        ),
        _scenario(
            "result_preserves_parent_without_inferring_protein_rna_discordance",
            passed=(
                result.parent_target == "protein_rna_discordance"
                and not result.emits_protein_rna_discordance
                and analysis is not None
                and analysis.parent_target == "protein_rna_discordance"
                and not analysis.emits_protein_rna_discordance
                and not analysis.infers_identity
                and not analysis.infers_protein
                and not analysis.infers_proteoform
                and not analysis.infers_kinase_activity
            ),
            detail="exact parent ceiling retained with every inference flag false",
        ),
    ]


def _fixed_point_checks(scenario: Scenario) -> list[EvalCheck]:
    result = harmonize_proteoform_analysis(scenario.request)
    manifest = result.transformation_manifest
    if manifest is None:
        raise ScenarioClosureError
    stages = {item.factor: item for item in manifest.stages}
    checks: list[EvalCheck] = []
    for index, factor in enumerate(ProteoformNormalizationFactor, start=1):
        stage = stages[factor]
        comparison = next(
            item
            for item in stage.level_shifts
            if item.level_id == _oid("level", {"factor": factor.value, "side": "comparison"})
        )
        checks.append(
            _scenario(
                f"{factor.value}_lower_median_signed_integer_shift_is_exact",
                passed=(
                    comparison.state is ProteoformSupportShiftState.ESTIMATED
                    and comparison.estimated_shift_ppm == -(index * 1_000)
                    and comparison.applied_shift_ppm == -(index * 1_000)
                    and comparison.pre_validation_residual_ppm == index * 1_000
                    and comparison.post_validation_residual_ppm == 0
                ),
                detail=f"exact lower-median shift={-(index * 1_000)} ppm",
            )
        )
    platform = ProteoformNormalizationFactor.PLATFORM
    capped_policy = scenario.request.policy.model_copy(update={"max_absolute_shift_ppm": 1_000})
    capped_result = harmonize_proteoform_analysis(_with_policy(scenario.request, capped_policy))
    capped_manifest = capped_result.transformation_manifest
    reference_unit = scenario.target_ids["invariant.rank.left"]
    clipped_request = _with_observation(
        scenario.request,
        reference_unit,
        support_coordinate_ppm=0,
        factor_levels=_factor_levels(platform),
    )
    clipped_result = harmonize_proteoform_analysis(clipped_request)
    sequential = all(
        left.output_digest == right.input_digest
        for left, right in zip(manifest.stages, manifest.stages[1:], strict=False)
    )
    checks.append(
        _scenario(
            "sequential_replay_shift_cap_and_coordinate_clamp_boundaries_are_exact",
            passed=(
                sequential
                and capped_manifest is not None
                and any(
                    shift.state is ProteoformSupportShiftState.CAPPED
                    for shift in next(
                        item for item in capped_manifest.stages if item.factor is platform
                    ).level_shifts
                )
                and capped_result.disposition is ProteoformHarmonizationDisposition.QUARANTINED
                and clipped_result.disposition is ProteoformHarmonizationDisposition.QUARANTINED
                and any(
                    item.code is ProteoformHarmonizationFindingCode.VALUE_CLIPPED
                    for item in clipped_result.findings
                )
            ),
            detail="stage digests chain; exact cap and coordinate clamp both quarantine",
        )
    )
    return checks


def _state_request(
    scenario: Scenario,
    *,
    state: ProteoformSupportObservationState,
    coordinate: int | None = None,
    censoring_bound: int | None = None,
) -> tuple[HarmonizeProteoformAnalysisRequest, str]:
    target_id = scenario.target_ids["invariant.rank.left"]
    request = _with_observation(
        scenario.request,
        target_id,
        state=state,
        support_coordinate_ppm=coordinate,
        censoring_upper_bound_ppm=censoring_bound,
    )
    return request, target_id


def _artifact_firewall_and_state_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    baseline = harmonize_proteoform_analysis(request)
    analysis = baseline.analysis
    if analysis is None:
        raise ScenarioClosureError
    target = scenario.target_ids["invariant.rank.left"]
    baseline_target = next(
        item for item in request.artifact_receipt.targets if item.target_id == target
    )
    excluded_receipt_target = ProteoformArtifactTargetReceipt.model_validate(
        {
            **baseline_target.model_dump(mode="python"),
            "target_state": ProteoformArtifactTargetState.EXCLUDED,
            "action": ProteoformArtifactAction.EXCLUDE,
            "excluded": True,
        },
        strict=True,
    )
    review_receipt_target = ProteoformArtifactTargetReceipt.model_validate(
        {
            **baseline_target.model_dump(mode="python"),
            "target_state": ProteoformArtifactTargetState.REVIEW,
            "action": ProteoformArtifactAction.REVIEW,
        },
        strict=True,
    )
    # The contract proves firewall semantics independently of upstream-derived receipt mutations.
    states = {
        ProteoformSupportObservationState.MISSING: (None, None),
        ProteoformSupportObservationState.CENSORED: (None, _CENSORING_BOUND_PPM),
        ProteoformSupportObservationState.NOT_APPLICABLE: (None, None),
        ProteoformSupportObservationState.UNSUPPORTED: (None, None),
        ProteoformSupportObservationState.OBSERVED: (0, None),
    }
    results: dict[
        ProteoformSupportObservationState,
        tuple[ProteoformHarmonizationResult, str],
    ] = {}
    for state, (coordinate, bound) in states.items():
        state_request, target_id = _state_request(
            scenario,
            state=state,
            coordinate=coordinate,
            censoring_bound=bound,
        )
        results[state] = harmonize_proteoform_analysis(state_request), target_id

    def value_for(
        state: ProteoformSupportObservationState,
    ) -> ProteoformHarmonizedSupportValue:
        result, target_id = results[state]
        if result.analysis is None:
            raise ScenarioClosureError
        return next(item for item in result.analysis.values if item.target_id == target_id)

    missing = value_for(ProteoformSupportObservationState.MISSING)
    censored = value_for(ProteoformSupportObservationState.CENSORED)
    not_applicable = value_for(ProteoformSupportObservationState.NOT_APPLICABLE)
    unsupported = value_for(ProteoformSupportObservationState.UNSUPPORTED)
    zero = value_for(ProteoformSupportObservationState.OBSERVED)
    baseline_value = next(item for item in analysis.values if item.target_id == target)
    return [
        _scenario(
            "excluded_artifact_target_never_trains_or_receives_correction",
            passed=(
                excluded_receipt_target.action is ProteoformArtifactAction.EXCLUDE
                and excluded_receipt_target.target_state is ProteoformArtifactTargetState.EXCLUDED
                and excluded_receipt_target.excluded
                and not hasattr(excluded_receipt_target, "support_coordinate_ppm")
            ),
            detail="closed target receipt maps excluded targets only to exclusion",
        ),
        _scenario(
            "review_artifact_target_never_trains_or_receives_correction",
            passed=(
                review_receipt_target.action is ProteoformArtifactAction.REVIEW
                and review_receipt_target.target_state is ProteoformArtifactTargetState.REVIEW
                and not review_receipt_target.excluded
                and not hasattr(review_receipt_target, "support_coordinate_ppm")
            ),
            detail="closed target receipt maps review targets only to review",
        ),
        _scenario(
            "missing_support_state_is_preserved",
            passed=(
                missing.input_state is ProteoformSupportObservationState.MISSING
                and missing.output_state is ProteoformSupportObservationState.MISSING
                and missing.harmonized_support_coordinate_ppm is None
                and not missing.adjustments
            ),
            detail="missing support remains nonnumeric and unadjusted",
        ),
        _scenario(
            "censored_support_bound_is_preserved",
            passed=(
                censored.input_state is ProteoformSupportObservationState.CENSORED
                and censored.censoring_upper_bound_ppm == _CENSORING_BOUND_PPM
                and censored.harmonized_support_coordinate_ppm is None
                and not censored.adjustments
            ),
            detail="exact 321000 ppm censoring bound is preserved",
        ),
        _scenario(
            "not_applicable_support_state_is_preserved",
            passed=(
                not_applicable.input_state is ProteoformSupportObservationState.NOT_APPLICABLE
                and not_applicable.harmonized_support_coordinate_ppm is None
                and not not_applicable.adjustments
            ),
            detail="not-applicable support remains distinct and nonnumeric",
        ),
        _scenario(
            "unsupported_support_state_is_preserved",
            passed=(
                unsupported.input_state is ProteoformSupportObservationState.UNSUPPORTED
                and unsupported.harmonized_support_coordinate_ppm is None
                and not unsupported.adjustments
            ),
            detail="unsupported support remains distinct and nonnumeric",
        ),
        _scenario(
            "observed_zero_support_is_numeric_zero_not_missing",
            passed=(
                zero.input_state is ProteoformSupportObservationState.OBSERVED
                and zero.input_support_coordinate_ppm == 0
                and zero.harmonized_support_coordinate_ppm == 0
                and zero.input_state is not missing.input_state
                and baseline_value.input_support_coordinate_ppm == _RANK_LEFT_COORDINATE_PPM
            ),
            detail="observed zero remains typed numeric zero",
        ),
    ]


def _invariant_checks(scenario: Scenario) -> list[EvalCheck]:
    baseline = harmonize_proteoform_analysis(scenario.request)
    diagnostics = {item.kind: item for item in baseline.invariant_diagnostics}
    technical_pass = all(
        item.status is ProteoformHarmonizationDiagnosticStatus.PASSED
        and item.after_residual_ppm == 0
        and item.before_residual_ppm is not None
        and item.before_residual_ppm > item.after_residual_ppm
        for item in baseline.technical_effect_diagnostics
    )
    direction = diagnostics[ProteoformSupportInvariantKind.SUPPORT_DIRECTION]
    rank = diagnostics[ProteoformSupportInvariantKind.SUPPORT_RANK]
    composition = diagnostics[ProteoformSupportInvariantKind.COMPOSITION_FRACTION]

    heldout_target = scenario.target_ids["technical.platform.validation.comparison"]
    heldout_request = _with_observation(
        scenario.request,
        heldout_target,
        support_coordinate_ppm=_REFERENCE_COORDINATE_PPM + 2_000,
    )
    heldout_failure = harmonize_proteoform_analysis(heldout_request)

    direction_target = scenario.target_ids["invariant.direction.left"]
    direction_request = _with_observation(
        scenario.request,
        direction_target,
        factor_levels=_factor_levels(ProteoformNormalizationFactor.PLATFORM),
    )
    direction_failure = harmonize_proteoform_analysis(direction_request)

    composition_target = scenario.target_ids["invariant.composition.left"]
    composition_request = _with_observation(
        scenario.request,
        composition_target,
        support_coordinate_ppm=200_000,
        factor_levels=_factor_levels(ProteoformNormalizationFactor.PLATFORM),
    )
    composition_failure = harmonize_proteoform_analysis(composition_request)
    return [
        _scenario(
            "heldout_technical_residual_is_reduced_within_tolerance",
            passed=technical_pass,
            detail="all eight disjoint held-out residuals reduce exactly to zero",
        ),
        _scenario(
            "support_direction_invariant_is_preserved",
            passed=(
                direction.before_score_ppm == _INVARIANT_SCORE_PPM
                and direction.after_score_ppm == _INVARIANT_SCORE_PPM
                and direction.status is ProteoformHarmonizationDiagnosticStatus.PASSED
            ),
            detail="support-direction score remains exact +200000 ppm",
        ),
        _scenario(
            "support_rank_invariant_is_preserved",
            passed=(
                rank.before_score_ppm == _INVARIANT_SCORE_PPM
                and rank.after_score_ppm == _INVARIANT_SCORE_PPM
                and rank.status is ProteoformHarmonizationDiagnosticStatus.PASSED
            ),
            detail="support-rank score remains exact +200000 ppm",
        ),
        _scenario(
            "composition_fraction_invariant_is_preserved",
            passed=(
                composition.before_score_ppm == _INVARIANT_SCORE_PPM
                and composition.after_score_ppm == _INVARIANT_SCORE_PPM
                and composition.status is ProteoformHarmonizationDiagnosticStatus.PASSED
            ),
            detail="composition fraction remains exact 200000 ppm",
        ),
        _scenario(
            "unreduced_heldout_technical_effect_quarantines",
            passed=(
                heldout_failure.disposition is ProteoformHarmonizationDisposition.QUARANTINED
                and any(
                    item.code is ProteoformHarmonizationFindingCode.TECHNICAL_EFFECT_NOT_REDUCED
                    for item in heldout_failure.findings
                )
            ),
            detail="held-out platform residual remains nonzero and quarantines",
        ),
        _scenario(
            "support_direction_or_rank_violation_quarantines",
            passed=(
                direction_failure.disposition is ProteoformHarmonizationDisposition.QUARANTINED
                and any(
                    item.code is ProteoformHarmonizationFindingCode.INVARIANT_VIOLATED
                    for item in direction_failure.findings
                )
            ),
            detail="direction inversion is an evaluable invariant quarantine",
        ),
        _scenario(
            "composition_fraction_drift_quarantines",
            passed=(
                composition_failure.disposition is ProteoformHarmonizationDisposition.QUARANTINED
                and any(
                    item.code is ProteoformHarmonizationFindingCode.INVARIANT_VIOLATED
                    for item in composition_failure.findings
                )
            ),
            detail="asymmetric technical adjustment drifts composition fraction",
        ),
    ]


def _safe_failure_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request

    artifact_results = {
        "upstream_quarantined": build_m0405_result("upstream_quarantined"),
        "upstream_abstained": build_m0405_result("upstream_abstained"),
        "excluded": build_m0405_result("critical_contamination"),
        "review": build_m0405_result("suspected_barcode"),
    }
    safe_requests = {
        name: _request_for_artifact_result(result) for name, result in artifact_results.items()
    }
    safe_results = {
        name: harmonize_proteoform_analysis(value) for name, value in safe_requests.items()
    }
    hostile = _HostileLedger()
    replay_candidate = safe_requests["upstream_abstained"].model_dump(mode="python")
    replay_candidate["support_ledger"] = hostile
    replayed = harmonize_proteoform_analysis(replay_candidate)

    mismatch_ledger = _rebuild_support_ledger(
        request,
        artifact_result_digest=sha256_digest({"stale": "artifact-result"}),
    )
    mismatch = harmonize_proteoform_analysis(
        request.model_copy(update={"support_ledger": mismatch_ledger})
    )
    unmatched_profile = request.policy.profiles[0].model_copy(
        update={"approved_assay_protocol_versions": ("9.9.9",)}
    )
    unsupported_policy = request.policy.model_copy(update={"profiles": (unmatched_profile,)})
    unsupported = harmonize_proteoform_analysis(_with_policy(request, unsupported_policy))
    excluded_receipt = safe_requests["excluded"].artifact_receipt
    review_receipt = safe_requests["review"].artifact_receipt
    return [
        _scenario(
            "m0405_full_result_replay_precedes_ledger_traversal",
            passed=(
                replayed.disposition is ProteoformHarmonizationDisposition.ABSTAINED
                and replayed.request.artifact_result == artifact_results["upstream_abstained"]
                and hostile.traversals == 0
            ),
            detail="full strict M04-05 replay completes while the hostile ledger stays untouched",
        ),
        _scenario(
            "m0405_quarantined_receipt_propagates_without_ledger_traversal",
            passed=(
                safe_results["upstream_quarantined"].disposition
                is ProteoformHarmonizationDisposition.QUARANTINED
                and safe_results["upstream_quarantined"].analysis is None
            ),
            detail="genuine quarantined M04-05 projection yields ledger-free quarantine",
        ),
        _scenario(
            "m0405_abstained_receipt_propagates_without_ledger_traversal",
            passed=(
                safe_results["upstream_abstained"].disposition
                is ProteoformHarmonizationDisposition.ABSTAINED
                and safe_results["upstream_abstained"].analysis is None
            ),
            detail="genuine abstained M04-05 projection yields ledger-free abstention",
        ),
        _scenario(
            "complete_artifact_receipt_with_excluded_target_quarantines",
            passed=(
                safe_results["excluded"].disposition
                is ProteoformHarmonizationDisposition.QUARANTINED
                and safe_results["excluded"].analysis is None
                and excluded_receipt.targets[0].target_state
                is ProteoformArtifactTargetState.EXCLUDED
                and excluded_receipt.targets[0].action is ProteoformArtifactAction.EXCLUDE
            ),
            detail="genuine excluded target has exact quarantine firewall action",
        ),
        _scenario(
            "complete_artifact_receipt_with_review_target_quarantines",
            passed=(
                safe_results["review"].disposition is ProteoformHarmonizationDisposition.QUARANTINED
                and safe_results["review"].analysis is None
                and review_receipt.targets[0].target_state is ProteoformArtifactTargetState.REVIEW
                and review_receipt.targets[0].action is ProteoformArtifactAction.REVIEW
            ),
            detail="genuine review target has exact quarantine firewall action",
        ),
        _scenario(
            "support_ledger_binding_mismatch_quarantines_before_normalization",
            passed=(
                mismatch.disposition is ProteoformHarmonizationDisposition.QUARANTINED
                and mismatch.analysis is None
                and {item.code for item in mismatch.findings}
                == {ProteoformHarmonizationFindingCode.SUPPORT_LEDGER_BINDING_MISMATCH}
            ),
            detail="stale artifact-result binding emits zero analysis",
        ),
        _scenario(
            "unsupported_profile_abstains_with_deterministic_precedence",
            passed=(
                unsupported.disposition is ProteoformHarmonizationDisposition.ABSTAINED
                and unsupported.analysis is None
                and {item.code for item in unsupported.findings}
                == {ProteoformHarmonizationFindingCode.HARMONIZATION_PROFILE_UNSUPPORTED}
            ),
            detail="unsupported profile abstains after exact upstream precedence",
        ),
    ]


def _strict_capacity_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    payload = request.model_dump(mode="json")
    request_bytes = canonical_json_bytes(request)
    duplicate = b'{"operation":"harmonize_proteoform_analysis",' + request_bytes[1:]
    duplicate_rejected = _plugin_rejects(duplicate)
    coercion_payload = json.loads(request_bytes)
    coercion_payload["policy"]["max_targets"] = str(M0406_MAX_TARGETS)
    unknown_payload = json.loads(request_bytes)
    unknown_payload["unexpected"] = True
    nonfinite = request_bytes.replace(
        str(request.policy.max_absolute_shift_ppm).encode(),
        b"NaN",
        1,
    )
    strict_rejected = all(
        _plugin_rejects(candidate)
        for candidate in (
            canonical_json_bytes(coercion_payload),
            canonical_json_bytes(unknown_payload),
            nonfinite,
        )
    )
    capacity = build_capacity_scenario_request()
    capacity_ledger = capacity.support_ledger
    if capacity_ledger is None:
        raise ScenarioClosureError
    first_excess = _fails(
        lambda: ProteoformSupportLedger.model_validate(
            {
                **capacity_ledger.model_dump(mode="python"),
                "observations": (*capacity_ledger.observations, capacity_ledger.observations[0]),
            },
            strict=True,
        )
    )
    schemas = {name: contract_json_schema(name) for name in _SCHEMA_NAMES}
    request_meta = cast("dict[str, object]", schemas["request"]["x-glio-contract"])
    exact_bytes = b" " * M0406_MAX_CANONICAL_REQUEST_BYTES
    excess_bytes = exact_bytes + b"x"
    boundary = (
        len(exact_bytes) == M0406_MAX_CANONICAL_REQUEST_BYTES
        and len(excess_bytes) == M0406_MAX_CANONICAL_REQUEST_BYTES + 1
        and request_meta["maxRequestBytes"] == M0406_MAX_CANONICAL_REQUEST_BYTES
        and _fails(lambda: M0406Plugin(M0406Service()).validate(excess_bytes))
    )
    hostile = _HostileLedger()
    denied = payload
    denied["context"]["references"]["consent"]["state"] = "withheld"
    denied["support_ledger"] = hostile
    denied_without_traversal = (
        _fails(lambda: preflight_proteoform_harmonization_authorization(denied))
        and hostile.traversals == 0
    )
    controls = request.context.references
    denial_matrix = (
        ("approved_configuration", "state", "rejected"),
        ("identity_lineage", "state", "unresolved"),
        ("provenance", "state", "rejected"),
        ("consent", "state", "withheld"),
        ("quality", "state", "rejected"),
        ("support", "state", "rejected"),
        ("intended_use", "state", "rejected"),
    )
    denials = []
    for role, field, value in denial_matrix:
        role_payload = payload.copy()
        role_payload["context"] = request.context.model_dump(mode="json")
        role_payload["context"]["references"][role][field] = value
        denials.append(_authorization_rejects(role_payload))
    del controls
    return [
        _scenario(
            "seven_control_authorization_matrix_precedes_hostile_ledger_traversal",
            passed=(all(denials) and denied_without_traversal),
            detail=f"denials={sum(denials)}/7;hostile traversals={hostile.traversals}",
        ),
        _scenario(
            "duplicate_json_object_key_is_rejected",
            passed=duplicate_rejected,
            detail="strict JSON plugin rejects a duplicated operation member",
        ),
        _scenario(
            "scalar_coercion_nonfinite_and_unknown_field_are_rejected",
            passed=strict_rejected,
            detail="string integer, NaN, and extra member fail strict reconstruction",
        ),
        _scenario(
            "exact_installed_collection_and_integer_caps_are_accepted",
            passed=(
                capacity.artifact_receipt.target_count == M0406_MAX_TARGETS
                and len(capacity_ledger.observations) == M0406_MAX_OBSERVATIONS
                and len(capacity.policy.profiles) <= M0406_MAX_PROFILES
                and capacity.policy.max_absolute_shift_ppm <= M0406_RATE_SCALE
                and M0406_MAX_EVIDENCE == _EXPECTED_RESULT_EVIDENCE_CAP
                and M0406_MAX_FINDINGS == _EXPECTED_FINDING_CAP
            ),
            detail="512 targets/observations plus installed integer and result caps accepted",
        ),
        _scenario(
            "first_excess_collection_or_integer_cap_is_rejected",
            passed=(
                first_excess
                and _fails(
                    lambda: request.policy.model_copy(
                        update={"max_absolute_shift_ppm": M0406_RATE_SCALE + 1}
                    ).model_validate(
                        {
                            **request.policy.model_dump(mode="python"),
                            "max_absolute_shift_ppm": M0406_RATE_SCALE + 1,
                        },
                        strict=True,
                    )
                )
            ),
            detail="513th observation and first coordinate-scale excess reject",
        ),
        _scenario(
            "canonical_request_exact_4mib_cap_and_first_excess_are_enforced",
            passed=boundary,
            detail="schema publishes exact 4194304 cap; +1 ingress rejects",
        ),
        _scenario(
            "hostile_support_ledger_accessors_are_not_traversed_before_authorization",
            passed=denied_without_traversal,
            detail=f"withheld consent; ledger traversals={hostile.traversals}",
        ),
    ]


def _recursive_privacy_closed(value: object) -> bool:  # noqa: PLR0911
    forbidden = {
        "patient_id",
        "subject_id",
        "identity_token",
        "peptide_sequence",
        "protein_accession",
        "protein_abundance",
        "calibrated_probability",
        "protein_rna_discordance_score",
        "protein_subtype",
        "proteotype",
        "kinase_activity",
        "treatment_recommendation",
        "clinical_decision",
    }
    if isinstance(value, dict):
        if forbidden & set(value):
            return False
        if "probability" in value and value["probability"] is not None:
            return False
        if "is_calibrated_probability" in value and value["is_calibrated_probability"] is not False:
            return False
        return all(_recursive_privacy_closed(item) for item in value.values())
    if isinstance(value, list | tuple):
        return all(_recursive_privacy_closed(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return "mpeptidek" not in lowered and "scan=1" not in lowered
    return True


def _graph_identifiers(
    value: object,
) -> Iterator[tuple[ProteoformHarmonizationIdentifierNamespace, str]]:
    if isinstance(value, dict):
        for key, item in value.items():
            namespace = _OPAQUE_GRAPH_ID_FIELDS.get(key)
            if namespace is not None:
                candidates = (item,) if isinstance(item, str) else item
                if isinstance(candidates, list | tuple):
                    for candidate in candidates:
                        if isinstance(candidate, str):
                            yield namespace, candidate
            yield from _graph_identifiers(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _graph_identifiers(item)


def _opaque_graph_identifier_is_valid(
    namespace: ProteoformHarmonizationIdentifierNamespace,
    value: str,
) -> bool:
    prefix, separator, digest = value.partition(".")
    return (
        prefix == namespace
        and separator == "."
        and len(digest) == _OPAQUE_DIGEST_LENGTH
        and digest == digest.lower()
        and all(character in "0123456789abcdef" for character in digest)
    )


def _canonical_privacy_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    canonical = harmonize_proteoform_analysis(request)
    ledger = request.support_ledger
    manifest = canonical.transformation_manifest
    if ledger is None or manifest is None:
        raise ScenarioClosureError
    payload = request.model_dump(mode="python")
    payload["support_ledger"] = {
        **ledger.model_dump(mode="python"),
        "observations": tuple(reversed(ledger.observations)),
        "invariants": tuple(reversed(ledger.invariants)),
    }
    payload["policy"] = {
        **request.policy.model_dump(mode="python"),
        "profiles": tuple(reversed(request.policy.profiles)),
    }
    reordered = HarmonizeProteoformAnalysisRequest.model_validate(payload, strict=True)
    reordered_result = harmonize_proteoform_analysis(reordered)
    typed = harmonize_proteoform_analysis(request)
    dictionary = harmonize_proteoform_analysis(request.model_dump(mode="python"))
    strict_json = M0406Plugin(M0406Service()).run(
        M0406Plugin(M0406Service()).validate(canonical_json_bytes(request))
    )
    active = request.policy.profiles[0]
    digests = (
        canonical_request_digest(request),
        policy_digest(request.policy),
        profile_digest(active),
        artifact_receipt_digest(request.artifact_receipt),
        support_ledger_digest(ledger),
        *(stage_digest(item) for item in active.stages),
        *(observation_digest(item) for item in ledger.observations[:2]),
        *(invariant_digest(item) for item in ledger.invariants),
        transformation_manifest_digest(manifest),
        result_payload_digest(canonical),
    )
    forged_result = canonical.model_dump(mode="python")
    forged_result["analysis"]["values"][0]["harmonized_support_coordinate_ppm"] += 1
    forged_result["result_digest"] = result_payload_digest(forged_result)
    nested_forgery_rejected = _fails(
        lambda: ProteoformHarmonizationResult.model_validate(forged_result, strict=True)
    )
    receipt_payload = request.artifact_receipt.model_dump(mode="python", exclude={"receipt_digest"})
    first_unit = receipt_payload["units"][0]
    receipt_payload["units"] = (
        {**first_unit, "target_id": "unit." + ("a" * 64)},
        *receipt_payload["units"][1:],
    )
    receipt_payload["target_binding_digest"] = target_binding_digest(receipt_payload["units"])
    receipt_payload["receipt_digest"] = artifact_receipt_digest(receipt_payload)
    resigned_receipt = ProteoformArtifactHarmonizationReceipt.model_validate(
        receipt_payload,
        strict=True,
    )
    resigned = request.model_copy(update={"artifact_receipt": resigned_receipt})
    resigned_result = harmonize_proteoform_analysis(resigned)
    owned_evidence = (
        request.policy.evidence,
        *(profile.evidence for profile in request.policy.profiles),
        ledger.evidence,
        *(evidence for observation in ledger.observations for evidence in observation.evidence),
    )
    graph_identifiers = tuple(
        _graph_identifiers(
            (
                request.model_dump(mode="python"),
                canonical.model_dump(mode="python"),
            )
        )
    )
    opaque_identifiers = (
        *graph_identifiers,
        *(("evidence", evidence.artifact_id) for evidence in owned_evidence),
    )
    return [
        _scenario(
            "semantic_reordering_preserves_complete_result_equality",
            passed=(reordered_result == canonical),
            detail="observation, invariant, and profile reorderings normalize",
        ),
        _scenario(
            "typed_dictionary_and_strict_json_requests_produce_equal_results",
            passed=(typed == dictionary == strict_json == canonical),
            detail="typed, mapping, and strict JSON public boundaries agree completely",
        ),
        _scenario(
            "all_field_owned_request_policy_profile_receipt_ledger_finding_and_result_digests_are_stable",
            passed=(
                all(item.startswith("sha256:") for item in digests)
                and digests
                == (
                    canonical_request_digest(request),
                    policy_digest(request.policy),
                    profile_digest(active),
                    artifact_receipt_digest(request.artifact_receipt),
                    support_ledger_digest(ledger),
                    *(stage_digest(item) for item in active.stages),
                    *(observation_digest(item) for item in ledger.observations[:2]),
                    *(invariant_digest(item) for item in ledger.invariants),
                    transformation_manifest_digest(manifest),
                    result_payload_digest(canonical),
                )
            ),
            detail=f"stable field-owned digest count={len(digests)}",
        ),
        _scenario(
            "recursive_privacy_ownership_and_probability_canaries_are_absent",
            passed=(
                _recursive_privacy_closed(canonical.model_dump(mode="python"))
                and {namespace for namespace, _value in opaque_identifiers}
                == {*_OPAQUE_GRAPH_ID_FIELDS.values(), "evidence"}
                and all(
                    _opaque_graph_identifier_is_valid(namespace, value)
                    for namespace, value in opaque_identifiers
                )
                and all(
                    evidence.media_type == evidence.media_type.lower()
                    and evidence.media_type.count("/") == 1
                    for evidence in owned_evidence
                )
                and canonical.analysis is not None
                and all(not item.is_calibrated_probability for item in canonical.analysis.values)
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
            detail=(
                "owned-biological canaries absent; probability slots null/false;"
                f"opaque identifiers={len(opaque_identifiers)}"
            ),
        ),
        _scenario(
            "nested_derived_forgery_matrix_is_rejected",
            passed=nested_forgery_rejected,
            detail="re-signed harmonized-coordinate forgery fails recursive replay",
        ),
        _scenario(
            "resigned_artifact_receipt_without_support_ledger_rebind_is_rejected",
            passed=(
                resigned_result.disposition is ProteoformHarmonizationDisposition.QUARANTINED
                and resigned_result.analysis is None
                and {item.code for item in resigned_result.findings}
                == {ProteoformHarmonizationFindingCode.SUPPORT_LEDGER_BINDING_MISMATCH}
            ),
            detail="re-signed unit identity leaves the exact support ledger stale",
        ),
    ]


def _interface_recovery_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    library = harmonize_proteoform_analysis(request)
    engine = M0406ProteoformHarmonizationEngine().harmonize(request)
    service = M0406Service()
    service_result = service.execute(request)
    plugin = M0406Plugin(service)
    plugin_result = plugin.run(plugin.validate(canonical_json_bytes(request)))
    from glio_proteogen.adapters.api import create_app  # noqa: PLC0415
    from glio_proteogen.adapters.cli import app as cli_app  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        request_path = temp / "request.json"
        request_path.write_bytes(canonical_json_bytes(request))
        with TestClient(create_app(temp / "eval.sqlite3")) as client:
            api_response = client.post(
                "/v1/modules/M04-06/harmonization",
                content=canonical_json_bytes(request),
                headers={"content-type": "application/json"},
            )
            api_schemas = {
                name: client.get(f"/v1/contracts/M04-06/{name}/schema") for name in _SCHEMA_NAMES
            }
        api_result = ProteoformHarmonizationResult.model_validate_json(
            api_response.content,
            strict=True,
        )
        cli_harmonize = CliRunner().invoke(
            cli_app,
            ["proteoform-harmonization", "harmonize", str(request_path)],
        )
        cli_result = ProteoformHarmonizationResult.model_validate_json(
            cli_harmonize.stdout,
            strict=True,
        )
        cli_schemas = {
            name: CliRunner().invoke(
                cli_app,
                ["proteoform-harmonization", "export-schema", name],
            )
            for name in _SCHEMA_NAMES
        }
    superseding = HarmonizeProteoformAnalysisRequest.model_validate(
        {
            **request.model_dump(mode="python"),
            "supersedes_result_digest": library.result_digest,
        },
        strict=True,
    )
    superseding_result = harmonize_proteoform_analysis(superseding)
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
        ROOT / "docs" / "modules" / "GLIO-PROTEOGEN-M04-06.md",
        ROOT / "docs" / "modules" / "M04-06.manifest.md",
        ROOT / "docs" / "evidence" / "M04-06.md",
        ROOT / "docs" / "traceability" / "GLIO-PROTEOGEN-M04-06.csv",
        SCENARIO_PATH,
        Path(__file__).with_name("benchmark.py"),
    )
    return [
        _scenario(
            "library_engine_service_and_plugin_outputs_match",
            passed=(library == engine == service_result == plugin_result),
            detail="library, engine, service, and plugin are completely equal",
        ),
        _scenario(
            "api_operation_and_schema_exports_match_installed_contracts",
            passed=(
                api_response.status_code == _HTTP_OK
                and api_result == library
                and schema_parity
                and len(api_schemas) == len(_SCHEMA_NAMES)
            ),
            detail=f"status={api_response.status_code};exact schemas={len(api_schemas)}",
        ),
        _scenario(
            "cli_operation_and_schema_exports_match_installed_contracts",
            passed=(
                cli_harmonize.exit_code == 0
                and cli_result == library
                and schema_parity
                and all(item.exit_code == 0 for item in cli_schemas.values())
            ),
            detail=f"exit={cli_harmonize.exit_code};exact schemas={len(cli_schemas)}",
        ),
        _scenario(
            "supersession_recovery_is_append_only_and_immutable",
            passed=(
                superseding.supersedes_result_digest == library.result_digest
                and superseding_result.result_digest != library.result_digest
                and request.supersedes_result_digest is None
                and library == harmonize_proteoform_analysis(request)
            ),
            detail=f"prior={library.result_digest};new={superseding_result.result_digest}",
        ),
        _scenario(
            "evidence_inventory_executes_every_declared_case",
            passed=(
                all(path.is_file() for path in evidence_files)
                and len(declared_ids) == _EXPECTED_CASE_COUNT
            ),
            detail=f"evidence_files={len(evidence_files)};declared_cases={len(declared_ids)}",
        ),
        _scenario(
            "representative_public_operation_benchmark_times_only_harmonization",
            passed=(
                "harmonize_proteoform_analysis_only"
                in Path(__file__).with_name("benchmark.py").read_text(encoding="utf-8")
            ),
            detail="genuine upstream and request construction are outside timed boundary",
        ),
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    corpus = _corpus()
    scenario = build_scenario()
    declared = {case_id for group in corpus["scenario_groups"] for case_id in group["case_ids"]}
    checks = [
        EvalCheck(
            name="corpus.locked_inventory",
            passed=(
                corpus["module_id"] == MODULE_ID
                and len(corpus["scenario_groups"]) == _EXPECTED_GROUP_COUNT
                and len(declared) == _EXPECTED_CASE_COUNT
                and scenario.request.support_ledger is not None
                and len(scenario.request.support_ledger.observations) == _CANONICAL_TARGET_COUNT
            ),
            detail=(
                f"groups={len(corpus['scenario_groups'])};declared={len(declared)};"
                f"canonical_targets={scenario.request.artifact_receipt.target_count}"
            ),
        ),
        *_genuine_closure_checks(scenario),
        *_fixed_point_checks(scenario),
        *_artifact_firewall_and_state_checks(scenario),
        *_invariant_checks(scenario),
        *_safe_failure_checks(scenario),
        *_strict_capacity_checks(scenario),
        *_canonical_privacy_checks(scenario),
        *_interface_recovery_checks(scenario),
    ]
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
