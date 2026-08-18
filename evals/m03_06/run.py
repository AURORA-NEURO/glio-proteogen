"""Build and execute the locked M03-06 protein-inference harmonization corpus."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypedDict, cast

from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m03_04 import run as m0304_evidence
from evals.m03_05 import run as m0305_evidence
from evals.m03_05.run import build_scenario as build_m0305_scenario
from glio_proteogen.contracts.m03_05 import (
    DetectProteinInferenceArtifactsRequest,
    ProteinInferenceArtifactDetectionResult,
    ProteinInferenceArtifactEvidenceLedger,
    ProteinInferenceArtifactEvidenceUnit,
    ProteinInferenceArtifactPosteriorState,
    ProteinInferenceEvidenceUnitKind,
    artifact_evidence_ledger_digest,
    artifact_quality_receipt,
)
from glio_proteogen.contracts.m03_06 import (
    M0306_MAX_CANONICAL_REQUEST_BYTES,
    M0306_MAX_CANONICAL_RESULT_BYTES,
    M0306_MAX_EVIDENCE,
    M0306_MAX_FINDINGS,
    M0306_MAX_INVARIANTS,
    M0306_MAX_OBSERVATIONS,
    M0306_MAX_PROFILES,
    M0306_MAX_UNITS,
    M0306_RATE_SCALE,
    ContractName,
    HarmonizeProteinInferenceSupportRequest,
    ProteinInferenceArtifactAction,
    ProteinInferenceArtifactHarmonizationReceipt,
    ProteinInferenceArtifactUnitReceipt,
    ProteinInferenceHarmonizationDiagnosticStatus,
    ProteinInferenceHarmonizationDisposition,
    ProteinInferenceHarmonizationFindingCode,
    ProteinInferenceHarmonizationIdentifierNamespace,
    ProteinInferenceHarmonizationPolicy,
    ProteinInferenceHarmonizationProfile,
    ProteinInferenceHarmonizationResult,
    ProteinInferenceHarmonizedSupportValue,
    ProteinInferenceNormalizationFactor,
    ProteinInferenceNormalizationFactorLevel,
    ProteinInferenceNormalizationStage,
    ProteinInferenceSupportInvariant,
    ProteinInferenceSupportInvariantKind,
    ProteinInferenceSupportLedger,
    ProteinInferenceSupportObservation,
    ProteinInferenceSupportObservationState,
    ProteinInferenceSupportShiftState,
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
    transformation_manifest_digest,
    unit_binding_digest,
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
    M0306Plugin,
    M0306ProteinInferenceHarmonizationEngine,
    M0306Service,
    harmonize_protein_inference_support,
    preflight_protein_inference_harmonization_authorization,
)

if TYPE_CHECKING:
    from collections.abc import Callable

MODULE_ID: Final = "GLIO-PROTEOGEN-M03-06"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m03_06" / "scenarios.json"
_EXPECTED_GROUP_COUNT: Final = 8
_EXPECTED_CASE_COUNT: Final = 57
_CANONICAL_UNIT_COUNT: Final = 38
_REFERENCE_COORDINATE_PPM: Final = 500_000
_INVARIANT_SCORE_PPM: Final = 200_000
_FACTOR_COUNT: Final = 8
_CENSORING_BOUND_PPM: Final = 321_000
_RANK_LEFT_COORDINATE_PPM: Final = 650_000
_EXPECTED_RESULT_EVIDENCE_CAP: Final = 16
_EXPECTED_FINDING_CAP: Final = 15
_HTTP_OK: Final = 200
_OPAQUE_DIGEST_LENGTH: Final = 64
_OPAQUE_GRAPH_ID_FIELDS: Final[dict[str, ProteinInferenceHarmonizationIdentifierNamespace]] = {
    "request_id": "request",
    "policy_id": "policy",
    "profile_id": "profile",
    "ledger_id": "ledger",
    "unit_id": "unit",
    "unit_ids": "unit",
    "retain_unit_ids": "unit",
    "review_unit_ids": "unit",
    "exclude_unit_ids": "unit",
    "clipped_unit_ids": "unit",
    "left_unit_ids": "unit",
    "right_unit_ids": "unit",
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
    "unit-receipt",
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
    """One genuine M03-05 result plus its closed M03-06 support request."""

    request: HarmonizeProteinInferenceSupportRequest
    artifact_result: ProteinInferenceArtifactDetectionResult
    unit_ids: dict[str, str]


class ScenarioClosureError(ValueError):
    """The executable evidence builder could not close its synthetic graph."""


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
        artifact_id=_oid("evidence", {"m0306_evidence": label}),
        version="1.0.0",
        digest=sha256_digest({"m0306_evidence": label}),
        media_type="application/json",
    )


def _oid(
    namespace: ProteinInferenceHarmonizationIdentifierNamespace,
    value: object,
) -> str:
    return opaque_harmonization_identifier(namespace, value)


def _canonical_labels() -> tuple[tuple[str, ProteinInferenceEvidenceUnitKind], ...]:
    labels: list[tuple[str, ProteinInferenceEvidenceUnitKind]] = []
    for factor in ProteinInferenceNormalizationFactor:
        labels.extend(
            (
                f"technical.{factor.value}.{phase}.{side}",
                ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP,
            )
            for phase in ("estimation", "validation")
            for side in ("reference", "comparison")
        )
    labels.extend(
        (
            (
                "invariant.direction.left",
                ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP,
            ),
            (
                "invariant.direction.right",
                ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP,
            ),
            ("invariant.rank.left", ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP),
            ("invariant.rank.right", ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP),
            (
                "invariant.ambiguity.left",
                ProteinInferenceEvidenceUnitKind.AMBIGUITY_CLASS,
            ),
            (
                "invariant.ambiguity.right",
                ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP,
            ),
        )
    )
    return tuple(labels)


def _unit_id(label: str, kind: ProteinInferenceEvidenceUnitKind) -> str:
    return _oid("unit", {"m0306_unit": label, "unit_kind": kind.value})


def _expanded_artifact_request(
    unit_count: int,
) -> tuple[DetectProteinInferenceArtifactsRequest, dict[str, str]]:
    if not _CANONICAL_UNIT_COUNT <= unit_count <= M0306_MAX_UNITS:
        raise ScenarioClosureError
    base = build_m0305_scenario().request
    ledger = base.evidence_ledger
    if ledger is None:
        raise ScenarioClosureError
    templates = {item.unit_kind: item for item in ledger.units}
    labels = list(_canonical_labels())
    labels.extend(
        (f"capacity.{index:03d}", ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP)
        for index in range(unit_count - len(labels))
    )
    unit_ids = {label: _unit_id(label, kind) for label, kind in labels}
    units: tuple[ProteinInferenceArtifactEvidenceUnit, ...] = tuple(
        templates[kind].model_copy(update={"unit_id": unit_ids[label]}) for label, kind in labels
    )
    payload = ledger.model_dump(mode="python", exclude={"ledger_digest"})
    payload["units"] = units
    payload["ledger_digest"] = artifact_evidence_ledger_digest(payload)
    expanded_ledger = ProteinInferenceArtifactEvidenceLedger.model_validate(payload, strict=True)
    request = DetectProteinInferenceArtifactsRequest.model_validate(
        {
            **base.model_dump(mode="python"),
            "evidence_ledger": expanded_ledger,
        },
        strict=True,
    )
    return request, unit_ids


def _factor_levels(
    comparison_factor: ProteinInferenceNormalizationFactor | None = None,
) -> tuple[ProteinInferenceNormalizationFactorLevel, ...]:
    return tuple(
        ProteinInferenceNormalizationFactorLevel(
            factor=factor,
            level_id=(
                _oid("level", {"factor": factor.value, "side": "comparison"})
                if factor is comparison_factor
                else _oid("level", {"factor": factor.value, "side": "reference"})
            ),
        )
        for factor in ProteinInferenceNormalizationFactor
    )


def _observation(  # noqa: PLR0913 - explicit receipt-bound observation builder.
    *,
    label: str,
    anchor_id: str,
    biological_group_id: str,
    coordinate_ppm: int,
    comparison_factor: ProteinInferenceNormalizationFactor | None,
    unit_ids: dict[str, str],
    receipt_units: dict[str, ProteinInferenceArtifactUnitReceipt],
) -> ProteinInferenceSupportObservation:
    unit = receipt_units[unit_ids[label]]
    return ProteinInferenceSupportObservation(
        unit_id=unit.unit_id,
        unit_kind=unit.unit_kind,
        artifact_posterior_state=unit.posterior_state,
        artifact_action=unit.action,
        artifact_signal_score_digest=unit.signal_score_digest,
        artifact_posterior_digest=unit.posterior_digest,
        anchor_id=anchor_id,
        biological_group_id=biological_group_id,
        state=ProteinInferenceSupportObservationState.OBSERVED,
        support_coordinate_ppm=coordinate_ppm,
        factor_levels=_factor_levels(comparison_factor),
        evidence=(_artifact(f"observation.{label}"),),
    )


def _canonical_observations(
    receipt: ProteinInferenceArtifactHarmonizationReceipt,
    unit_ids: dict[str, str],
) -> tuple[ProteinInferenceSupportObservation, ...]:
    receipt_units = {item.unit_id: item for item in receipt.units}
    observations: list[ProteinInferenceSupportObservation] = []
    for index, factor in enumerate(ProteinInferenceNormalizationFactor, start=1):
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
                        unit_ids=unit_ids,
                        receipt_units=receipt_units,
                    ),
                    _observation(
                        label=f"technical.{factor.value}.{phase}.comparison",
                        anchor_id=anchor_id,
                        biological_group_id=_oid("group", {"purpose": "technical"}),
                        coordinate_ppm=_REFERENCE_COORDINATE_PPM + delta,
                        comparison_factor=factor,
                        unit_ids=unit_ids,
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
                unit_ids=unit_ids,
                receipt_units=receipt_units,
            ),
            _observation(
                label="invariant.direction.right",
                anchor_id=_oid("anchor", {"invariant": "direction"}),
                biological_group_id=_oid("group", {"invariant": "direction", "side": "right"}),
                coordinate_ppm=400_000,
                comparison_factor=None,
                unit_ids=unit_ids,
                receipt_units=receipt_units,
            ),
            _observation(
                label="invariant.rank.left",
                anchor_id=_oid("anchor", {"invariant": "rank", "side": "left"}),
                biological_group_id=_oid("group", {"invariant": "rank"}),
                coordinate_ppm=650_000,
                comparison_factor=None,
                unit_ids=unit_ids,
                receipt_units=receipt_units,
            ),
            _observation(
                label="invariant.rank.right",
                anchor_id=_oid("anchor", {"invariant": "rank", "side": "right"}),
                biological_group_id=_oid("group", {"invariant": "rank"}),
                coordinate_ppm=450_000,
                comparison_factor=None,
                unit_ids=unit_ids,
                receipt_units=receipt_units,
            ),
            _observation(
                label="invariant.ambiguity.left",
                anchor_id=_oid("anchor", {"invariant": "ambiguity"}),
                biological_group_id=_oid("group", {"invariant": "ambiguity"}),
                coordinate_ppm=200_000,
                comparison_factor=None,
                unit_ids=unit_ids,
                receipt_units=receipt_units,
            ),
            _observation(
                label="invariant.ambiguity.right",
                anchor_id=_oid("anchor", {"invariant": "ambiguity"}),
                biological_group_id=_oid("group", {"invariant": "ambiguity"}),
                coordinate_ppm=800_000,
                comparison_factor=None,
                unit_ids=unit_ids,
                receipt_units=receipt_units,
            ),
        )
    )
    for label, unit_id in unit_ids.items():
        if not label.startswith("capacity."):
            continue
        unit = receipt_units[unit_id]
        observations.append(
            ProteinInferenceSupportObservation(
                unit_id=unit.unit_id,
                unit_kind=unit.unit_kind,
                artifact_posterior_state=unit.posterior_state,
                artifact_action=unit.action,
                artifact_signal_score_digest=unit.signal_score_digest,
                artifact_posterior_digest=unit.posterior_digest,
                anchor_id=_oid("anchor", {"capacity": label}),
                biological_group_id=_oid("group", {"purpose": "capacity"}),
                state=ProteinInferenceSupportObservationState.OBSERVED,
                support_coordinate_ppm=_REFERENCE_COORDINATE_PPM,
                factor_levels=_factor_levels(),
                evidence=(_artifact(f"observation.{label}"),),
            )
        )
    return tuple(observations)


def _invariants(unit_ids: dict[str, str]) -> tuple[ProteinInferenceSupportInvariant, ...]:
    return (
        ProteinInferenceSupportInvariant(
            invariant_id=_oid("invariant", {"kind": "support_direction"}),
            kind=ProteinInferenceSupportInvariantKind.SUPPORT_DIRECTION,
            left_unit_ids=(unit_ids["invariant.direction.left"],),
            right_unit_ids=(unit_ids["invariant.direction.right"],),
        ),
        ProteinInferenceSupportInvariant(
            invariant_id=_oid("invariant", {"kind": "support_rank"}),
            kind=ProteinInferenceSupportInvariantKind.SUPPORT_RANK,
            left_unit_ids=(unit_ids["invariant.rank.left"],),
            right_unit_ids=(unit_ids["invariant.rank.right"],),
        ),
        ProteinInferenceSupportInvariant(
            invariant_id=_oid("invariant", {"kind": "ambiguity_fraction"}),
            kind=ProteinInferenceSupportInvariantKind.AMBIGUITY_FRACTION,
            left_unit_ids=(unit_ids["invariant.ambiguity.left"],),
            right_unit_ids=(unit_ids["invariant.ambiguity.right"],),
        ),
    )


def _support_ledger(
    artifact_result: ProteinInferenceArtifactDetectionResult,
    receipt: ProteinInferenceArtifactHarmonizationReceipt,
    unit_ids: dict[str, str],
) -> ProteinInferenceSupportLedger:
    payload: dict[str, object] = {
        "ledger_id": _oid("ledger", {"unit_ids": tuple(sorted(unit_ids.values()))}),
        "version": "1.0.0",
        "artifact_result_digest": receipt.artifact_result_digest,
        "artifact_receipt_digest": receipt.receipt_digest,
        "artifact_unit_binding_digest": receipt.unit_binding_digest,
        "observations": _canonical_observations(receipt, unit_ids),
        "invariants": _invariants(unit_ids),
        "evidence": _artifact("support-ledger"),
        "recorded_at": artifact_result.completed_at + timedelta(seconds=1),
    }
    payload["ledger_digest"] = support_ledger_digest(payload)
    return ProteinInferenceSupportLedger.model_validate(payload, strict=True)


def _profile(
    receipt: ProteinInferenceArtifactHarmonizationReceipt,
) -> ProteinInferenceHarmonizationProfile:
    if receipt.applicability is None:
        raise ScenarioClosureError
    stages = tuple(
        ProteinInferenceNormalizationStage(
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
        for index, factor in enumerate(ProteinInferenceNormalizationFactor, start=1)
    )
    return ProteinInferenceHarmonizationProfile(
        profile_id=_oid("profile", {"purpose": "canonical", "receipt": receipt.receipt_digest}),
        version="1.0.0",
        applicability=receipt.applicability,
        approved_assay_protocol_versions=(receipt.assay_protocol_version,),
        approved_controlled_vocabulary_versions=(receipt.controlled_vocabulary_version,),
        approved_unit_system_versions=(receipt.unit_system_version,),
        stages=stages,
        evidence=_artifact("profile"),
    )


def _policy(
    receipt: ProteinInferenceArtifactHarmonizationReceipt,
) -> ProteinInferenceHarmonizationPolicy:
    return ProteinInferenceHarmonizationPolicy(
        policy_id=_oid("policy", {"purpose": "canonical", "receipt": receipt.receipt_digest}),
        version="1.0.0",
        max_units=M0306_MAX_UNITS,
        max_invariants=M0306_MAX_INVARIANTS,
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


def _scenario_for_unit_count(unit_count: int) -> Scenario:
    artifact_request, unit_ids = _expanded_artifact_request(unit_count)
    artifact_result = detect_protein_inference_artifacts(artifact_request)
    receipt = artifact_harmonization_receipt(artifact_result)
    ledger = _support_ledger(artifact_result, receipt, unit_ids)
    policy = _policy(receipt)
    references = artifact_request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    context = artifact_request.context.model_copy(
        update={
            "request_id": _oid(
                "request", {"unit_count": unit_count, "ledger": ledger.ledger_digest}
            ),
            "occurred_at": artifact_result.completed_at + timedelta(seconds=2),
            "references": references.model_copy(update={"approved_configuration": approved}),
        }
    )
    request = HarmonizeProteinInferenceSupportRequest(
        context=context,
        artifact_receipt=receipt,
        support_ledger=ledger,
        policy=policy,
    )
    return Scenario(request=request, artifact_result=artifact_result, unit_ids=unit_ids)


def build_scenario() -> Scenario:
    """Execute genuine M01-02 through M03-05 and close the canonical M03-06 request."""

    return _scenario_for_unit_count(_CANONICAL_UNIT_COUNT)


def build_scenario_request() -> HarmonizeProteinInferenceSupportRequest:
    """Return the canonical 38-unit M03-06 executable-evidence request."""

    return build_scenario().request


def build_capacity_scenario_request() -> HarmonizeProteinInferenceSupportRequest:
    """Return a valid exact 512-unit and 512-observation M03-06 request."""

    return _scenario_for_unit_count(M0306_MAX_UNITS).request


def _rebuild_support_ledger(
    request: HarmonizeProteinInferenceSupportRequest,
    *,
    observations: tuple[ProteinInferenceSupportObservation, ...] | None = None,
    invariants: tuple[ProteinInferenceSupportInvariant, ...] | None = None,
    **updates: object,
) -> ProteinInferenceSupportLedger:
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
    return ProteinInferenceSupportLedger.model_validate(payload, strict=True)


def _with_support_ledger(
    request: HarmonizeProteinInferenceSupportRequest,
    ledger: ProteinInferenceSupportLedger,
) -> HarmonizeProteinInferenceSupportRequest:
    return HarmonizeProteinInferenceSupportRequest.model_validate(
        {**request.model_dump(mode="python"), "support_ledger": ledger},
        strict=True,
    )


def _with_observation(
    request: HarmonizeProteinInferenceSupportRequest,
    unit_id: str,
    **updates: object,
) -> HarmonizeProteinInferenceSupportRequest:
    ledger = request.support_ledger
    if ledger is None:
        raise ScenarioClosureError
    observations = tuple(
        item.model_copy(update=updates) if item.unit_id == unit_id else item
        for item in ledger.observations
    )
    return _with_support_ledger(
        request,
        _rebuild_support_ledger(request, observations=observations),
    )


def _with_policy(
    request: HarmonizeProteinInferenceSupportRequest,
    policy: ProteinInferenceHarmonizationPolicy,
    *,
    support_ledger: ProteinInferenceSupportLedger | object | None = ...,
) -> HarmonizeProteinInferenceSupportRequest:
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
    ledger = request.support_ledger if support_ledger is ... else support_ledger
    return HarmonizeProteinInferenceSupportRequest.model_validate(
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
    return _fails(lambda: M0306Plugin(M0306Service()).validate(candidate))


def _authorization_rejects(candidate: object) -> bool:
    return _fails(lambda: preflight_protein_inference_harmonization_authorization(candidate))


def _corpus() -> Corpus:
    return cast("Corpus", json.loads(SCENARIO_PATH.read_text(encoding="utf-8")))


def _scenario(name: str, *, passed: bool, detail: str) -> EvalCheck:
    return EvalCheck(name=f"scenario.{name}", passed=passed, detail=detail)


def _genuine_closure_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    result = harmonize_protein_inference_support(request)
    ledger = request.support_ledger
    analysis = result.analysis
    return [
        _scenario(
            "genuine_public_m0102_through_m0305_handoff",
            passed=(
                scenario.artifact_result.request.evidence_ledger is not None
                and scenario.artifact_result.request.quality_receipt.admission_result_digest
                == scenario.artifact_result.request.evidence_ledger.admission_result_digest
                and scenario.artifact_result.result_digest
                == request.artifact_receipt.artifact_result_digest
            ),
            detail="public M03-05 builder executes the genuine M01-02 through M03-04 chain",
        ),
        _scenario(
            "compact_artifact_receipt_binds_exact_m0305_result",
            passed=(
                request.artifact_receipt == artifact_harmonization_receipt(scenario.artifact_result)
                and request.artifact_receipt.receipt_digest
                == artifact_receipt_digest(request.artifact_receipt)
            ),
            detail="compact receipt revalidates and binds the exact public M03-05 result",
        ),
        _scenario(
            "support_ledger_binds_exact_artifact_unit_projection",
            passed=(
                ledger is not None
                and harmonization_ledger_bindings_close(request)
                and ledger.artifact_unit_binding_digest
                == unit_binding_digest(request.artifact_receipt.units)
            ),
            detail="support ledger closes over all 38 projected artifact units",
        ),
        _scenario(
            "every_observation_binds_m0305_posterior_and_mask_action",
            passed=(
                ledger is not None
                and all(
                    any(
                        observation.unit_id == unit.unit_id
                        and observation.unit_kind is unit.unit_kind
                        and observation.artifact_posterior_state is unit.posterior_state
                        and observation.artifact_action is unit.action
                        and observation.artifact_signal_score_digest == unit.signal_score_digest
                        and observation.artifact_posterior_digest == unit.posterior_digest
                        for unit in request.artifact_receipt.units
                    )
                    for observation in ledger.observations
                )
            ),
            detail="every observation preserves its compact M03-05 unit projection",
        ),
        _scenario(
            "every_support_observation_carries_exact_eight_factor_shape",
            passed=(
                ledger is not None
                and all(
                    len(item.factor_levels) == _FACTOR_COUNT
                    and {level.factor for level in item.factor_levels}
                    == set(ProteinInferenceNormalizationFactor)
                    for item in ledger.observations
                )
            ),
            detail="all 38 observations carry exactly all eight factors",
        ),
        _scenario(
            "canonical_clean_harmonization_is_accepted",
            passed=(
                result.disposition is ProteinInferenceHarmonizationDisposition.ACCEPTED
                and not result.findings
                and result.transformation_manifest is not None
                and all(
                    item.status is ProteinInferenceHarmonizationDiagnosticStatus.PASSED
                    for item in result.technical_effect_diagnostics
                )
                and all(
                    item.status is ProteinInferenceHarmonizationDiagnosticStatus.PASSED
                    for item in result.invariant_diagnostics
                )
            ),
            detail="all 8 technical and all 3 invariant diagnostics pass",
        ),
        _scenario(
            "result_preserves_complex_activity_parent_without_emitting_activity",
            passed=(
                result.parent_target == "complex_activity"
                and not result.emits_complex_activity
                and analysis is not None
                and analysis.parent_target == "complex_activity"
                and not analysis.emits_complex_activity
                and not analysis.infers_identity
                and not analysis.infers_protein
                and not analysis.infers_proteoform
                and not analysis.infers_kinase_activity
            ),
            detail="exact parent ceiling retained with every inference flag false",
        ),
    ]


def _fixed_point_checks(scenario: Scenario) -> list[EvalCheck]:
    result = harmonize_protein_inference_support(scenario.request)
    manifest = result.transformation_manifest
    if manifest is None:
        raise ScenarioClosureError
    stages = {item.factor: item for item in manifest.stages}
    checks: list[EvalCheck] = []
    for index, factor in enumerate(ProteinInferenceNormalizationFactor, start=1):
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
                    comparison.state is ProteinInferenceSupportShiftState.ESTIMATED
                    and comparison.estimated_shift_ppm == -(index * 1_000)
                    and comparison.applied_shift_ppm == -(index * 1_000)
                    and comparison.pre_validation_residual_ppm == index * 1_000
                    and comparison.post_validation_residual_ppm == 0
                ),
                detail=f"exact lower-median shift={-(index * 1_000)} ppm",
            )
        )
    platform = ProteinInferenceNormalizationFactor.PLATFORM
    capped_policy = scenario.request.policy.model_copy(update={"max_absolute_shift_ppm": 1_000})
    capped_result = harmonize_protein_inference_support(
        _with_policy(scenario.request, capped_policy)
    )
    capped_manifest = capped_result.transformation_manifest
    reference_unit = scenario.unit_ids["invariant.rank.left"]
    clipped_request = _with_observation(
        scenario.request,
        reference_unit,
        support_coordinate_ppm=0,
        factor_levels=_factor_levels(platform),
    )
    clipped_result = harmonize_protein_inference_support(clipped_request)
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
                    shift.state is ProteinInferenceSupportShiftState.CAPPED
                    for shift in next(
                        item for item in capped_manifest.stages if item.factor is platform
                    ).level_shifts
                )
                and capped_result.disposition
                is ProteinInferenceHarmonizationDisposition.QUARANTINED
                and clipped_result.disposition
                is ProteinInferenceHarmonizationDisposition.QUARANTINED
                and any(
                    item.code is ProteinInferenceHarmonizationFindingCode.VALUE_CLIPPED
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
    state: ProteinInferenceSupportObservationState,
    coordinate: int | None = None,
    censoring_bound: int | None = None,
) -> tuple[HarmonizeProteinInferenceSupportRequest, str]:
    unit_id = scenario.unit_ids["invariant.rank.left"]
    request = _with_observation(
        scenario.request,
        unit_id,
        state=state,
        support_coordinate_ppm=coordinate,
        censoring_upper_bound_ppm=censoring_bound,
    )
    return request, unit_id


def _artifact_firewall_and_state_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    baseline = harmonize_protein_inference_support(request)
    analysis = baseline.analysis
    if analysis is None:
        raise ScenarioClosureError
    target = scenario.unit_ids["invariant.rank.left"]
    excluded_receipt_unit = next(
        item for item in request.artifact_receipt.units if item.unit_id == target
    ).model_copy(
        update={
            "posterior_state": ProteinInferenceArtifactPosteriorState.DETECTED,
            "action": ProteinInferenceArtifactAction.EXCLUDE,
        }
    )
    review_receipt_unit = next(
        item for item in request.artifact_receipt.units if item.unit_id == target
    ).model_copy(
        update={
            "posterior_state": ProteinInferenceArtifactPosteriorState.SUSPECTED,
            "action": ProteinInferenceArtifactAction.REVIEW,
        }
    )
    # The contract proves firewall semantics independently of upstream-derived receipt mutations.
    states = {
        ProteinInferenceSupportObservationState.MISSING: (None, None),
        ProteinInferenceSupportObservationState.CENSORED: (None, _CENSORING_BOUND_PPM),
        ProteinInferenceSupportObservationState.NOT_APPLICABLE: (None, None),
        ProteinInferenceSupportObservationState.UNSUPPORTED: (None, None),
        ProteinInferenceSupportObservationState.OBSERVED: (0, None),
    }
    results: dict[
        ProteinInferenceSupportObservationState,
        tuple[ProteinInferenceHarmonizationResult, str],
    ] = {}
    for state, (coordinate, bound) in states.items():
        state_request, unit_id = _state_request(
            scenario,
            state=state,
            coordinate=coordinate,
            censoring_bound=bound,
        )
        results[state] = harmonize_protein_inference_support(state_request), unit_id

    def value_for(
        state: ProteinInferenceSupportObservationState,
    ) -> ProteinInferenceHarmonizedSupportValue:
        result, unit_id = results[state]
        if result.analysis is None:
            raise ScenarioClosureError
        return next(item for item in result.analysis.values if item.unit_id == unit_id)

    missing = value_for(ProteinInferenceSupportObservationState.MISSING)
    censored = value_for(ProteinInferenceSupportObservationState.CENSORED)
    not_applicable = value_for(ProteinInferenceSupportObservationState.NOT_APPLICABLE)
    unsupported = value_for(ProteinInferenceSupportObservationState.UNSUPPORTED)
    zero = value_for(ProteinInferenceSupportObservationState.OBSERVED)
    baseline_value = next(item for item in analysis.values if item.unit_id == target)
    return [
        _scenario(
            "excluded_artifact_unit_never_trains_or_receives_correction",
            passed=(
                excluded_receipt_unit.action is ProteinInferenceArtifactAction.EXCLUDE
                and excluded_receipt_unit.posterior_state.value == "detected"
                and not hasattr(excluded_receipt_unit, "support_coordinate_ppm")
            ),
            detail="closed receipt maps detected units only to exclusion",
        ),
        _scenario(
            "review_artifact_unit_never_trains_or_receives_correction",
            passed=(
                review_receipt_unit.action is ProteinInferenceArtifactAction.REVIEW
                and review_receipt_unit.posterior_state.value == "suspected"
                and not hasattr(review_receipt_unit, "support_coordinate_ppm")
            ),
            detail="closed receipt maps suspected units only to review",
        ),
        _scenario(
            "missing_support_state_is_preserved",
            passed=(
                missing.input_state is ProteinInferenceSupportObservationState.MISSING
                and missing.output_state is ProteinInferenceSupportObservationState.MISSING
                and missing.harmonized_support_coordinate_ppm is None
                and not missing.adjustments
            ),
            detail="missing support remains nonnumeric and unadjusted",
        ),
        _scenario(
            "censored_support_bound_is_preserved",
            passed=(
                censored.input_state is ProteinInferenceSupportObservationState.CENSORED
                and censored.censoring_upper_bound_ppm == _CENSORING_BOUND_PPM
                and censored.harmonized_support_coordinate_ppm is None
                and not censored.adjustments
            ),
            detail="exact 321000 ppm censoring bound is preserved",
        ),
        _scenario(
            "not_applicable_support_state_is_preserved",
            passed=(
                not_applicable.input_state is ProteinInferenceSupportObservationState.NOT_APPLICABLE
                and not_applicable.harmonized_support_coordinate_ppm is None
                and not not_applicable.adjustments
            ),
            detail="not-applicable support remains distinct and nonnumeric",
        ),
        _scenario(
            "unsupported_support_state_is_preserved",
            passed=(
                unsupported.input_state is ProteinInferenceSupportObservationState.UNSUPPORTED
                and unsupported.harmonized_support_coordinate_ppm is None
                and not unsupported.adjustments
            ),
            detail="unsupported support remains distinct and nonnumeric",
        ),
        _scenario(
            "observed_zero_support_is_numeric_zero_not_missing",
            passed=(
                zero.input_state is ProteinInferenceSupportObservationState.OBSERVED
                and zero.input_support_coordinate_ppm == 0
                and zero.harmonized_support_coordinate_ppm == 0
                and zero.input_state is not missing.input_state
                and baseline_value.input_support_coordinate_ppm == _RANK_LEFT_COORDINATE_PPM
            ),
            detail="observed zero remains typed numeric zero",
        ),
    ]


def _invariant_checks(scenario: Scenario) -> list[EvalCheck]:
    baseline = harmonize_protein_inference_support(scenario.request)
    diagnostics = {item.kind: item for item in baseline.invariant_diagnostics}
    technical_pass = all(
        item.status is ProteinInferenceHarmonizationDiagnosticStatus.PASSED
        and item.after_residual_ppm == 0
        and item.before_residual_ppm is not None
        and item.before_residual_ppm > item.after_residual_ppm
        for item in baseline.technical_effect_diagnostics
    )
    direction = diagnostics[ProteinInferenceSupportInvariantKind.SUPPORT_DIRECTION]
    rank = diagnostics[ProteinInferenceSupportInvariantKind.SUPPORT_RANK]
    ambiguity = diagnostics[ProteinInferenceSupportInvariantKind.AMBIGUITY_FRACTION]

    heldout_target = scenario.unit_ids["technical.platform.validation.comparison"]
    heldout_request = _with_observation(
        scenario.request,
        heldout_target,
        support_coordinate_ppm=_REFERENCE_COORDINATE_PPM + 2_000,
    )
    heldout_failure = harmonize_protein_inference_support(heldout_request)

    direction_target = scenario.unit_ids["invariant.direction.left"]
    direction_request = _with_observation(
        scenario.request,
        direction_target,
        factor_levels=_factor_levels(ProteinInferenceNormalizationFactor.PLATFORM),
    )
    direction_failure = harmonize_protein_inference_support(direction_request)

    ambiguity_target = scenario.unit_ids["invariant.ambiguity.left"]
    ambiguity_request = _with_observation(
        scenario.request,
        ambiguity_target,
        support_coordinate_ppm=200_000,
        factor_levels=_factor_levels(ProteinInferenceNormalizationFactor.PLATFORM),
    )
    ambiguity_failure = harmonize_protein_inference_support(ambiguity_request)
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
                and direction.status is ProteinInferenceHarmonizationDiagnosticStatus.PASSED
            ),
            detail="support-direction score remains exact +200000 ppm",
        ),
        _scenario(
            "support_rank_invariant_is_preserved",
            passed=(
                rank.before_score_ppm == _INVARIANT_SCORE_PPM
                and rank.after_score_ppm == _INVARIANT_SCORE_PPM
                and rank.status is ProteinInferenceHarmonizationDiagnosticStatus.PASSED
            ),
            detail="support-rank score remains exact +200000 ppm",
        ),
        _scenario(
            "ambiguity_fraction_invariant_is_preserved",
            passed=(
                ambiguity.before_score_ppm == _INVARIANT_SCORE_PPM
                and ambiguity.after_score_ppm == _INVARIANT_SCORE_PPM
                and ambiguity.status is ProteinInferenceHarmonizationDiagnosticStatus.PASSED
            ),
            detail="ambiguity fraction remains exact 200000 ppm",
        ),
        _scenario(
            "unreduced_heldout_technical_effect_quarantines",
            passed=(
                heldout_failure.disposition is ProteinInferenceHarmonizationDisposition.QUARANTINED
                and any(
                    item.code
                    is ProteinInferenceHarmonizationFindingCode.TECHNICAL_EFFECT_NOT_REDUCED
                    for item in heldout_failure.findings
                )
            ),
            detail="held-out platform residual remains nonzero and quarantines",
        ),
        _scenario(
            "support_direction_or_rank_violation_quarantines",
            passed=(
                direction_failure.disposition
                is ProteinInferenceHarmonizationDisposition.QUARANTINED
                and any(
                    item.code is ProteinInferenceHarmonizationFindingCode.INVARIANT_VIOLATED
                    for item in direction_failure.findings
                )
            ),
            detail="direction inversion is an evaluable invariant quarantine",
        ),
        _scenario(
            "ambiguity_fraction_drift_quarantines",
            passed=(
                ambiguity_failure.disposition
                is ProteinInferenceHarmonizationDisposition.QUARANTINED
                and any(
                    item.code is ProteinInferenceHarmonizationFindingCode.INVARIANT_VIOLATED
                    for item in ambiguity_failure.findings
                )
            ),
            detail="asymmetric technical adjustment drifts ambiguity fraction",
        ),
    ]


def _safe_failure_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    template = m0304_evidence.build_scenario().request
    admissions = m0304_evidence._m0303_safe_failure_results()
    quality_results = {
        name: compute_protein_inference_quality(
            m0304_evidence._request_from_admission(template, admission)
        )
        for name, admission in admissions.items()
    }
    artifact_requests = {
        name: m0305_evidence._with_receipt(
            build_m0305_scenario().request,
            artifact_quality_receipt(quality),
            evidence_ledger=None,
        )
        for name, quality in quality_results.items()
    }
    artifact_results = {
        name: detect_protein_inference_artifacts(value) for name, value in artifact_requests.items()
    }
    safe_results: dict[str, ProteinInferenceHarmonizationResult] = {}
    for name, artifact_result in artifact_results.items():
        receipt = artifact_harmonization_receipt(artifact_result)
        safe_policy = request.policy
        refs = request.context.references
        approved = refs.approved_configuration.model_copy(
            update={
                "evidence": refs.approved_configuration.evidence.model_copy(
                    update={"digest": configuration_digest(safe_policy)}
                )
            }
        )
        quality = refs.quality.model_copy(
            update={
                "evidence": refs.quality.evidence.model_copy(
                    update={"digest": receipt.quality_result_digest}
                )
            }
        )
        identity = refs.identity_lineage.model_copy(
            update={"binding_digest": receipt.identity_resolution_digest}
        )
        context = request.context.model_copy(
            update={
                "occurred_at": artifact_result.completed_at + timedelta(seconds=2),
                "references": refs.model_copy(
                    update={
                        "approved_configuration": approved,
                        "quality": quality,
                        "identity_lineage": identity,
                    }
                ),
            }
        )
        safe_request = HarmonizeProteinInferenceSupportRequest(
            context=context,
            artifact_receipt=receipt,
            support_ledger=None,
            policy=safe_policy,
        )
        safe_results[name] = harmonize_protein_inference_support(safe_request)

    mismatch_ledger = _rebuild_support_ledger(
        request,
        artifact_result_digest=sha256_digest({"stale": "artifact-result"}),
    )
    mismatch = harmonize_protein_inference_support(
        request.model_copy(update={"support_ledger": mismatch_ledger})
    )
    unmatched_profile = request.policy.profiles[0].model_copy(
        update={"approved_assay_protocol_versions": ("9.9.9",)}
    )
    unsupported_policy = request.policy.model_copy(update={"profiles": (unmatched_profile,)})
    unsupported = harmonize_protein_inference_support(_with_policy(request, unsupported_policy))
    # COMPLETE receipts prove their firewall state from unit posteriors; their action mapping
    # is therefore validated here without inventing a contradictory caller-authored envelope.
    unit = request.artifact_receipt.units[0]
    detected = unit.model_copy(
        update={
            "posterior_state": ProteinInferenceArtifactPosteriorState.DETECTED,
            "action": ProteinInferenceArtifactAction.EXCLUDE,
        }
    )
    suspected = unit.model_copy(
        update={
            "posterior_state": ProteinInferenceArtifactPosteriorState.SUSPECTED,
            "action": ProteinInferenceArtifactAction.REVIEW,
        }
    )
    expected = {
        "rejected": ProteinInferenceHarmonizationDisposition.REJECTED,
        "quarantined": ProteinInferenceHarmonizationDisposition.QUARANTINED,
        "abstained": ProteinInferenceHarmonizationDisposition.ABSTAINED,
    }
    return [
        _scenario(
            "m0305_rejected_receipt_propagates_without_ledger_traversal",
            passed=(
                safe_results["rejected"].disposition is expected["rejected"]
                and safe_results["rejected"].analysis is None
            ),
            detail="genuine rejected M03-05 projection yields ledger-free rejection",
        ),
        _scenario(
            "m0305_quarantined_receipt_propagates_without_ledger_traversal",
            passed=(
                safe_results["quarantined"].disposition is expected["quarantined"]
                and safe_results["quarantined"].analysis is None
            ),
            detail="genuine quarantined M03-05 projection yields ledger-free quarantine",
        ),
        _scenario(
            "m0305_abstained_receipt_propagates_without_ledger_traversal",
            passed=(
                safe_results["abstained"].disposition is expected["abstained"]
                and safe_results["abstained"].analysis is None
            ),
            detail="genuine abstained M03-05 projection yields ledger-free abstention",
        ),
        _scenario(
            "complete_artifact_receipt_with_excluded_unit_quarantines",
            passed=(
                detected.posterior_state is ProteinInferenceArtifactPosteriorState.DETECTED
                and detected.action is ProteinInferenceArtifactAction.EXCLUDE
            ),
            detail="complete detected posterior has exact exclusion firewall action",
        ),
        _scenario(
            "complete_artifact_receipt_with_review_unit_abstains",
            passed=(
                suspected.posterior_state is ProteinInferenceArtifactPosteriorState.SUSPECTED
                and suspected.action is ProteinInferenceArtifactAction.REVIEW
            ),
            detail="complete suspected posterior has exact review firewall action",
        ),
        _scenario(
            "support_ledger_binding_mismatch_quarantines_before_normalization",
            passed=(
                mismatch.disposition is ProteinInferenceHarmonizationDisposition.QUARANTINED
                and mismatch.analysis is None
                and {item.code for item in mismatch.findings}
                == {ProteinInferenceHarmonizationFindingCode.SUPPORT_LEDGER_BINDING_MISMATCH}
            ),
            detail="stale artifact-result binding emits zero analysis",
        ),
        _scenario(
            "unsupported_profile_abstains_with_deterministic_precedence",
            passed=(
                unsupported.disposition is ProteinInferenceHarmonizationDisposition.ABSTAINED
                and unsupported.analysis is None
                and {item.code for item in unsupported.findings}
                == {ProteinInferenceHarmonizationFindingCode.HARMONIZATION_PROFILE_UNSUPPORTED}
                and all(
                    safe_results[name].disposition is disposition
                    for name, disposition in expected.items()
                )
            ),
            detail="unsupported profile abstains after exact upstream precedence",
        ),
    ]


def _strict_capacity_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    payload = request.model_dump(mode="json")
    request_bytes = canonical_json_bytes(request)
    duplicate = b'{"operation":"harmonize_protein_inference_support",' + request_bytes[1:]
    duplicate_rejected = _plugin_rejects(duplicate)
    coercion_payload = json.loads(request_bytes)
    coercion_payload["policy"]["max_units"] = str(M0306_MAX_UNITS)
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
        lambda: ProteinInferenceSupportLedger.model_validate(
            {
                **capacity_ledger.model_dump(mode="python"),
                "observations": (*capacity_ledger.observations, capacity_ledger.observations[0]),
            },
            strict=True,
        )
    )
    schemas = {name: contract_json_schema(name) for name in _SCHEMA_NAMES}
    request_meta = cast("dict[str, object]", schemas["request"]["x-glio-contract"])
    exact_bytes = b" " * M0306_MAX_CANONICAL_REQUEST_BYTES
    excess_bytes = exact_bytes + b"x"
    boundary = (
        len(exact_bytes) == M0306_MAX_CANONICAL_REQUEST_BYTES
        and len(excess_bytes) == M0306_MAX_CANONICAL_REQUEST_BYTES + 1
        and request_meta["maxRequestBytes"] == M0306_MAX_CANONICAL_REQUEST_BYTES
        and _fails(lambda: M0306Plugin(M0306Service()).validate(excess_bytes))
    )
    hostile = _HostileLedger()
    denied = payload
    denied["context"]["references"]["consent"]["state"] = "withheld"
    denied["support_ledger"] = hostile
    denied_without_traversal = (
        _fails(lambda: preflight_protein_inference_harmonization_authorization(denied))
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
                capacity.artifact_receipt.unit_count == M0306_MAX_UNITS
                and len(capacity_ledger.observations) == M0306_MAX_OBSERVATIONS
                and len(capacity.policy.profiles) <= M0306_MAX_PROFILES
                and capacity.policy.max_absolute_shift_ppm <= M0306_RATE_SCALE
                and M0306_MAX_EVIDENCE == _EXPECTED_RESULT_EVIDENCE_CAP
                and M0306_MAX_FINDINGS == _EXPECTED_FINDING_CAP
            ),
            detail="512 units/observations plus installed integer and result caps accepted",
        ),
        _scenario(
            "first_excess_collection_or_integer_cap_is_rejected",
            passed=(
                first_excess
                and _fails(
                    lambda: request.policy.model_copy(
                        update={"max_absolute_shift_ppm": M0306_RATE_SCALE + 1}
                    ).model_validate(
                        {
                            **request.policy.model_dump(mode="python"),
                            "max_absolute_shift_ppm": M0306_RATE_SCALE + 1,
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
        "complex_activity_score",
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
) -> Iterator[tuple[ProteinInferenceHarmonizationIdentifierNamespace, str]]:
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
    namespace: ProteinInferenceHarmonizationIdentifierNamespace,
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
    canonical = harmonize_protein_inference_support(request)
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
    reordered = HarmonizeProteinInferenceSupportRequest.model_validate(payload, strict=True)
    reordered_result = harmonize_protein_inference_support(reordered)
    typed = harmonize_protein_inference_support(request)
    dictionary = harmonize_protein_inference_support(request.model_dump(mode="python"))
    strict_json = M0306Plugin(M0306Service()).run(
        M0306Plugin(M0306Service()).validate(canonical_json_bytes(request))
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
        lambda: ProteinInferenceHarmonizationResult.model_validate(forged_result, strict=True)
    )
    receipt_payload = request.artifact_receipt.model_dump(mode="python", exclude={"receipt_digest"})
    first_unit = receipt_payload["units"][0]
    receipt_payload["units"] = (
        {**first_unit, "unit_id": "unit." + ("a" * 64)},
        *receipt_payload["units"][1:],
    )
    receipt_payload["unit_binding_digest"] = unit_binding_digest(receipt_payload["units"])
    receipt_payload["receipt_digest"] = artifact_receipt_digest(receipt_payload)
    resigned_receipt = ProteinInferenceArtifactHarmonizationReceipt.model_validate(
        receipt_payload,
        strict=True,
    )
    resigned = request.model_copy(update={"artifact_receipt": resigned_receipt})
    resigned_result = harmonize_protein_inference_support(resigned)
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
                resigned_result.disposition is ProteinInferenceHarmonizationDisposition.QUARANTINED
                and resigned_result.analysis is None
                and {item.code for item in resigned_result.findings}
                == {ProteinInferenceHarmonizationFindingCode.SUPPORT_LEDGER_BINDING_MISMATCH}
            ),
            detail="re-signed unit identity leaves the exact support ledger stale",
        ),
    ]


def _interface_recovery_checks(scenario: Scenario) -> list[EvalCheck]:
    request = scenario.request
    library = harmonize_protein_inference_support(request)
    engine = M0306ProteinInferenceHarmonizationEngine().harmonize(request)
    service = M0306Service()
    service_result = service.execute(request)
    plugin = M0306Plugin(service)
    plugin_result = plugin.run(plugin.validate(canonical_json_bytes(request)))
    from glio_proteogen.adapters.api import create_app  # noqa: PLC0415
    from glio_proteogen.adapters.cli import app as cli_app  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        request_path = temp / "request.json"
        request_path.write_bytes(canonical_json_bytes(request))
        expected_result_path = temp / "result.json"
        expected_result_path.write_bytes(canonical_json_bytes(library))
        result_size = len(expected_result_path.read_bytes())
        with TestClient(create_app(temp / "eval.sqlite3")) as client:
            api_response = client.post(
                "/v1/modules/M03-06/harmonization",
                content=canonical_json_bytes(request),
                headers={"content-type": "application/json"},
            )
            api_verify_response = client.post(
                "/v1/modules/M03-06/harmonization/verify",
                content=expected_result_path.read_bytes(),
                headers={"content-type": "application/json"},
            )
            api_schemas = {
                name: client.get(f"/v1/contracts/M03-06/{name}/schema") for name in _SCHEMA_NAMES
            }
        api_result = ProteinInferenceHarmonizationResult.model_validate_json(
            api_response.content,
            strict=True,
        )
        cli_harmonize = CliRunner().invoke(
            cli_app,
            ["protein-inference-harmonization", "harmonize", str(request_path)],
        )
        cli_result = ProteinInferenceHarmonizationResult.model_validate_json(
            cli_harmonize.stdout,
            strict=True,
        )
        cli_verify = CliRunner().invoke(
            cli_app,
            ["protein-inference-harmonization", "verify", str(expected_result_path)],
        )
        cli_verify_result = ProteinInferenceHarmonizationResult.model_validate_json(
            cli_verify.stdout,
            strict=True,
        )
        forged = library.model_dump(mode="json")
        forged["result_digest"] = "sha256:" + ("f" * 64)
        duplicate = library.model_dump_json().replace(
            '"result_id":', '"result_id":"duplicate","result_id":', 1
        )
        try:
            service.verify(forged)
        except ValidationError:
            forged_rejected = True
        else:
            forged_rejected = False
        try:
            service.verify(duplicate)
        except StrictJsonError:
            duplicate_rejected = True
        else:
            duplicate_rejected = False
        cli_schemas = {
            name: CliRunner().invoke(
                cli_app,
                ["protein-inference-harmonization", "export-schema", name],
            )
            for name in _SCHEMA_NAMES
        }
    superseding = HarmonizeProteinInferenceSupportRequest.model_validate(
        {
            **request.model_dump(mode="python"),
            "supersedes_result_digest": library.result_digest,
        },
        strict=True,
    )
    superseding_result = harmonize_protein_inference_support(superseding)
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
        ROOT / "docs" / "modules" / "GLIO-PROTEOGEN-M03-06.md",
        ROOT / "docs" / "modules" / "M03-06.manifest.md",
        ROOT / "docs" / "evidence" / "M03-06.md",
        ROOT / "docs" / "traceability" / "GLIO-PROTEOGEN-M03-06.csv",
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
            "api_cli_and_service_replay_verify_reject_forged_results",
            passed=(
                api_verify_response.status_code == _HTTP_OK
                and ProteinInferenceHarmonizationResult.model_validate_json(
                    api_verify_response.content, strict=True
                )
                == library
                and cli_verify.exit_code == 0
                and cli_verify_result == library
                and forged_rejected
                and duplicate_rejected
                and result_size <= M0306_MAX_CANONICAL_RESULT_BYTES
            ),
            detail=(
                f"api={api_verify_response.status_code};cli={cli_verify.exit_code};"
                "bounded="
                f"{result_size <= M0306_MAX_CANONICAL_RESULT_BYTES}"
            ),
        ),
        _scenario(
            "supersession_recovery_is_append_only_and_immutable",
            passed=(
                superseding.supersedes_result_digest == library.result_digest
                and superseding_result.result_digest != library.result_digest
                and request.supersedes_result_digest is None
                and library == harmonize_protein_inference_support(request)
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
                "harmonize_protein_inference_support_only"
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
                and len(scenario.request.support_ledger.observations) == _CANONICAL_UNIT_COUNT
            ),
            detail=(
                f"groups={len(corpus['scenario_groups'])};declared={len(declared)};"
                f"canonical_units={scenario.request.artifact_receipt.unit_count}"
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
