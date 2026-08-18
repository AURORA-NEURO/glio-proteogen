"""Executable evidence and genuine public builders for M04-04 quality computation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, cast
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from typer.testing import CliRunner

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

import glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics.engine as m0404_engine
from evals.m04_03.run import (
    _genuine_scenario as build_m0403_genuine_scenario,
)
from evals.m04_03.run import (
    _with_document_updates as with_m0403_document_updates,
)
from evals.m04_03.run import build_scenario as build_m0403_scenario
from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m04_03 import (
    MassSpectrometryProteomeInputDocument,
    ProteoformRawInputRole,
    ProteoformRawInputValidationResult,
    ValidatedProteoformRawInput,
    validated_input_digest,
)
from glio_proteogen.contracts.m04_03 import (
    result_payload_digest as m0403_result_payload_digest,
)
from glio_proteogen.contracts.m04_04 import (
    M0404_COMPUTED_METRIC_COUNT,
    M0404_LIMITATION_COUNT,
    M0404_MAX_EVIDENCE,
    M0404_MAX_PROFILES,
    M0404_METRIC_COUNT,
    M0404_MIN_EVIDENCE,
    M0404_ROLE_COUNT,
    ComputeProteoformQualityMetricsRequest,
    ProteoformAssayQualityProfile,
    ProteoformQualityDisposition,
    ProteoformQualityFactLedger,
    ProteoformQualityFindingCode,
    ProteoformQualityMetric,
    ProteoformQualityMetricCode,
    ProteoformQualityMetricDirection,
    ProteoformQualityMetricStatus,
    ProteoformQualityObservationState,
    ProteoformQualityPolicy,
    ProteoformQualityResult,
    ProteoformQualityRoleCounts,
    ProteoformQualityRoleFacts,
    ProteoformQualityRoleFactStates,
    ProteoformQualityThreshold,
    configuration_digest,
    contract_json_schemas,
    expected_limitations,
    expected_provenance,
    expected_receipt,
    expected_uncertainty,
    fact_ledger_digest,
    matching_quality_profiles,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c04_proteoform_isoform.m04_03_raw_ingestion import (
    ingest_proteoform_raw_inputs,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics import (
    M0404Plugin,
    M0404Service,
    ProteoformQualityAuthorizationError,
    compute_proteoform_quality_metrics,
    preflight_proteoform_quality_authorization,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M04-04"
SCENARIO_PATH: Final = Path("tests/fixtures/m04_04/scenarios.json")
EXPECTED_CASE_COUNT: Final = 72
EXPECTED_ALLOCATION: Final = (8, 9, 9, 9, 8, 8, 8, 13)
EXPECTED_GROUP_COUNT: Final = len(EXPECTED_ALLOCATION)
EXPECTED_CONTROL_COUNT: Final = 7
EXPECTED_SCHEMA_COUNT: Final = 13
CLI_USAGE_ERROR: Final = 2
HTTP_OK: Final = 200
HTTP_UNPROCESSABLE_CONTENT: Final = 422
ROUNDING_NUMERATOR: Final = 2
ROUNDING_DENOMINATOR: Final = 3
ROUNDING_VALUE_PPM: Final = 666_667
CENSORED_VALUE_PPM: Final = 333_333
DUPLICATE_EVIDENCE_COUNT: Final = 2
_PROFILE_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-04.assay-profile+json"
_POLICY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-04.policy+json"
_LEDGER_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-04.fact-ledger+json"
_FACT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-04.role-fact+json"


@dataclass(frozen=True, slots=True)
class Scenario:
    """One strict metadata-only M04-04 computation request."""

    request: ComputeProteoformQualityMetricsRequest


@dataclass(frozen=True, slots=True)
class EvalCheck:
    """One named executable assertion in the locked corpus."""

    name: str
    passed: bool
    detail: str


class _UnsupportedScenarioError(ValueError):
    pass


class _InvalidFixtureError(RuntimeError):
    pass


def _oid(namespace: str, label: object) -> str:
    digest = sha256_digest({"m0404_fixture": str(label)}).removeprefix("sha256:")
    return f"{namespace}.{digest}"


def _reference(label: str, *, media_type: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_oid("evidence", label),
        version="1.0.0",
        digest=sha256_digest({"m0404_evidence": label}),
        media_type=media_type,
    )


def _thresholds() -> tuple[ProteoformQualityThreshold, ...]:
    return tuple(
        ProteoformQualityThreshold(
            metric_code=code,
            direction=(
                ProteoformQualityMetricDirection.AT_MOST
                if code is ProteoformQualityMetricCode.DETECTION_LIMIT_BURDEN
                else ProteoformQualityMetricDirection.AT_LEAST
            ),
            pass_threshold_ppm=(
                0 if code is ProteoformQualityMetricCode.DETECTION_LIMIT_BURDEN else 666_667
            ),
            warning_threshold_ppm=(
                333_333 if code is ProteoformQualityMetricCode.DETECTION_LIMIT_BURDEN else 500_000
            ),
            required=True,
        )
        for code in ProteoformQualityMetricCode
    )


def _profile_for(
    source: ValidatedProteoformRawInput,
    role: ProteoformRawInputRole,
    *,
    ordinal: int = 0,
) -> ProteoformAssayQualityProfile:
    document = source.document
    canonical = ordinal == 0
    version = "1.0.0" if canonical else f"{ordinal + 1}.0.0"
    approved_version = document.assay_protocol_version if canonical else version
    return ProteoformAssayQualityProfile(
        profile_id=_oid("profile", f"{role.value}-{ordinal}"),
        version=version,
        role=role,
        applicability=(
            cast("MassSpectrometryProteomeInputDocument", document).applicability
            if role is ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME
            else None
        ),
        approved_assay_protocol_versions=(approved_version,),
        approved_specimen_processing_versions=(
            document.specimen_processing_version if canonical else version,
        ),
        approved_unit_definition_versions=(
            document.unit_definition_version if canonical else version,
        ),
        controls_applicable=True,
        thresholds=_thresholds(),
        evidence=_reference(f"profile-{role.value}-{ordinal}", media_type=_PROFILE_MEDIA_TYPE),
    )


def _policy(
    raw_result: ProteoformRawInputValidationResult,
    *,
    profile_count: int,
) -> ProteoformQualityPolicy:
    per_role = profile_count // len(ProteoformRawInputRole)
    profiles = [
        _profile_for(source, source.role, ordinal=ordinal)
        for source in raw_result.validated_inputs
        for ordinal in range(per_role)
    ]
    return ProteoformQualityPolicy(
        policy_id=_oid("policy", f"profiles-{profile_count}"),
        version="1.0.0",
        max_count=9_223_372_036_854_775_807,
        profiles=tuple(profiles),
        evidence=_reference(f"policy-{profile_count}", media_type=_POLICY_MEDIA_TYPE),
        reviewed_by=_oid("reviewer", "canonical"),
        reviewed_at=raw_result.completed_at,
    )


def _counts() -> ProteoformQualityRoleCounts:
    return ProteoformQualityRoleCounts(
        declared_record_count=3,
        parsed_record_count=2,
        valid_record_count=2,
        expected_feature_count=3,
        observed_feature_count=3,
        reference_eligible_count=3,
        reference_mapped_count=3,
        detection_eligible_count=3,
        above_detection_limit_count=3,
        below_detection_limit_count=0,
        control_expected_count=3,
        control_recovered_count=3,
        context_applicable_count=3,
        context_coherent_count=3,
        cross_input_applicable_count=3,
        cross_input_coherent_count=3,
    )


def _states() -> ProteoformQualityRoleFactStates:
    observed = ProteoformQualityObservationState.OBSERVED
    return ProteoformQualityRoleFactStates(
        raw_input_completeness=observed,
        valid_record_coverage=observed,
        assay_feature_coverage=observed,
        reference_mapping_coverage=observed,
        detection_limit_burden=observed,
        control_material_recovery=observed,
        sample_context_binding_coherence=observed,
        cross_input_consistency=observed,
    )


def _fact(source: ValidatedProteoformRawInput) -> ProteoformQualityRoleFacts:
    document = source.document
    role = source.role
    return ProteoformQualityRoleFacts(
        fact_id=_oid("fact", role.value),
        role=role,
        input_id=document.input_id,
        validated_input_digest=validated_input_digest(source),
        document_digest=source.document_digest,
        counts=_counts(),
        states=_states(),
        evidence=_reference(f"fact-{role.value}", media_type=_FACT_MEDIA_TYPE),
    )


def _ledger(raw_result: ProteoformRawInputValidationResult) -> ProteoformQualityFactLedger:
    payload: dict[str, object] = {
        "ledger_id": _oid("ledger", "canonical"),
        "version": "1.0.0",
        "raw_input_result_digest": raw_result.result_digest,
        "raw_input_receipt_digest": raw_result.receipt.receipt_digest,
        "role_facts": tuple(_fact(item) for item in raw_result.validated_inputs),
        "evidence": _reference("ledger", media_type=_LEDGER_MEDIA_TYPE),
        "recorded_at": raw_result.completed_at,
        "ledger_digest": "sha256:" + ("0" * 64),
    }
    payload["ledger_digest"] = fact_ledger_digest(payload)
    return ProteoformQualityFactLedger.model_validate(payload, strict=True)


def _request_from_raw_result(
    raw_result: ProteoformRawInputValidationResult,
    profile_count: int,
) -> ComputeProteoformQualityMetricsRequest:
    """Bind one genuine M04-03 result into the exact M04-04 request graph."""

    policy = (
        _policy(raw_result, profile_count=profile_count)
        if raw_result.validated_inputs
        else _base_request(profile_count).policy
    )
    ledger = _ledger(raw_result) if raw_result.disposition.value == "validated" else None
    base = raw_result.request.context
    references = base.references.model_copy(
        update={
            "approved_configuration": base.references.approved_configuration.model_copy(
                update={
                    "evidence": base.references.approved_configuration.evidence.model_copy(
                        update={"digest": configuration_digest(policy)}
                    )
                }
            ),
            "identity_lineage": base.references.identity_lineage.model_copy(
                update={"binding_digest": raw_result.receipt.identity_resolution_digest}
            ),
            "quality": base.references.quality.model_copy(
                update={
                    "evidence": base.references.quality.evidence.model_copy(
                        update={"digest": raw_result.result_digest}
                    )
                }
            ),
            "support": base.references.support.model_copy(
                update={
                    "evidence": base.references.support.evidence.model_copy(
                        update={"digest": raw_result.receipt.receipt_digest}
                    )
                }
            ),
            "intended_use": base.references.intended_use.model_copy(
                update={
                    "evidence": base.references.intended_use.evidence.model_copy(
                        update={"digest": raw_result.receipt.intended_use_evidence_digest}
                    )
                }
            ),
        }
    )
    context = base.model_copy(
        update={"occurred_at": raw_result.completed_at, "references": references}
    )
    return ComputeProteoformQualityMetricsRequest(
        request_id=context.request_id,
        context=context,
        raw_input_result=raw_result,
        policy=policy,
        fact_ledger=ledger,
        supersedes_result_digest=None,
    )


@lru_cache(maxsize=4)
def _base_request(
    profile_count: int,
    upstream_case_id: str = "canonical_four_role_documents_validated",
) -> ComputeProteoformQualityMetricsRequest:
    m0403 = (
        build_m0403_scenario()
        if upstream_case_id == "canonical_four_role_documents_validated"
        else build_m0403_genuine_scenario(upstream_case_id)
    )
    raw_result = ingest_proteoform_raw_inputs(m0403.request, m0403.artifacts_by_role)
    return _request_from_raw_result(raw_result, profile_count)


def build_scenario_request(
    case_id: str = "canonical_four_role_quality_qualified",
) -> ComputeProteoformQualityMetricsRequest:
    """Build one strict request through genuine public M01-02 to M04-03 operations."""

    upstream_cases = {
        "canonical_four_role_quality_qualified": "canonical_four_role_documents_validated",
        "quarantined_upstream_zero_ledger_traversal": "valid_quarantined_m0401_quarantines",
        "abstained_upstream_zero_ledger_traversal": "valid_unresolved_identity_abstains",
    }
    try:
        upstream_case = upstream_cases[case_id]
    except KeyError as error:
        raise _UnsupportedScenarioError(case_id) from error
    return _base_request(4, upstream_case)


def build_scenario(case_id: str = "canonical_four_role_quality_qualified") -> Scenario:
    return Scenario(request=build_scenario_request(case_id))


def build_maximum_scenario() -> Scenario:
    """Build the exact 32-profile, 256-threshold, 45-evidence metadata ceiling."""

    return Scenario(request=_base_request(M0404_MAX_PROFILES))


def build_representative_quality_fixture() -> Scenario:
    """Return the maximum supported metadata shape used by the representative benchmark."""

    return build_maximum_scenario()


def _corpus() -> dict[str, object]:
    return cast("dict[str, object]", json.loads(SCENARIO_PATH.read_text(encoding="utf-8")))


def _rejects(model: type[BaseModel], payload: object) -> bool:
    try:
        model.model_validate_json(canonical_json_bytes(payload), strict=True)
    except (ValidationError, ValueError):
        return True
    return False


def _request_payload(
    request: ComputeProteoformQualityMetricsRequest,
    *,
    policy: ProteoformQualityPolicy | None = None,
    ledger: ProteoformQualityFactLedger | object | None = ...,
) -> dict[str, object]:
    payload = cast("dict[str, object]", request.model_dump(mode="json"))
    selected_policy = policy or request.policy
    payload["policy"] = selected_policy.model_dump(mode="json")
    if ledger is not ...:
        payload["fact_ledger"] = (
            ledger.model_dump(mode="json")
            if isinstance(ledger, ProteoformQualityFactLedger)
            else ledger
        )
    context = cast("dict[str, object]", payload["context"])
    references = cast("dict[str, object]", context["references"])
    approved = cast("dict[str, object]", references["approved_configuration"])
    evidence = cast("dict[str, object]", approved["evidence"])
    evidence["digest"] = configuration_digest(selected_policy)
    return payload


def _with_policy(
    request: ComputeProteoformQualityMetricsRequest,
    profiles: tuple[ProteoformAssayQualityProfile, ...],
) -> ComputeProteoformQualityMetricsRequest:
    policy = request.policy.model_copy(update={"profiles": profiles})
    return ComputeProteoformQualityMetricsRequest.model_validate_json(
        canonical_json_bytes(_request_payload(request, policy=policy)), strict=True
    )


def _with_fact(
    request: ComputeProteoformQualityMetricsRequest,
    fact: ProteoformQualityRoleFacts,
) -> ComputeProteoformQualityMetricsRequest:
    ledger = request.fact_ledger
    if ledger is None:
        raise _InvalidFixtureError
    facts = tuple(fact if item.role is fact.role else item for item in ledger.role_facts)
    payload = cast("dict[str, object]", ledger.model_dump(mode="json"))
    payload["role_facts"] = tuple(item.model_dump(mode="json") for item in facts)
    payload["recorded_at"] = ledger.recorded_at
    payload["ledger_digest"] = "sha256:" + ("0" * 64)
    payload["ledger_digest"] = fact_ledger_digest(payload)
    resealed = ProteoformQualityFactLedger.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )
    return ComputeProteoformQualityMetricsRequest.model_validate_json(
        canonical_json_bytes(_request_payload(request, ledger=resealed)), strict=True
    )


def _mutated_fact(
    request: ComputeProteoformQualityMetricsRequest,
    *,
    counts: dict[str, int] | None = None,
    states: dict[str, str] | None = None,
    input_id: str | None = None,
) -> ProteoformQualityRoleFacts:
    ledger = request.fact_ledger
    if ledger is None:
        raise _InvalidFixtureError
    source = ledger.role_facts[0]
    payload = cast("dict[str, object]", source.model_dump(mode="json"))
    if counts:
        cast("dict[str, object]", payload["counts"]).update(counts)
    if states:
        cast("dict[str, object]", payload["states"]).update(states)
    if input_id is not None:
        payload["input_id"] = input_id
    return ProteoformQualityRoleFacts.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )


def _with_threshold(
    request: ComputeProteoformQualityMetricsRequest,
    code: ProteoformQualityMetricCode,
    **updates: object,
) -> ComputeProteoformQualityMetricsRequest:
    profile = request.policy.profiles[0]
    thresholds = tuple(
        item.model_copy(update=updates) if item.metric_code is code else item
        for item in profile.thresholds
    )
    replacement = ProteoformAssayQualityProfile.model_validate_json(
        canonical_json_bytes({**profile.model_dump(mode="json"), "thresholds": thresholds}),
        strict=True,
    )
    profiles = tuple(replacement if item is profile else item for item in request.policy.profiles)
    return _with_policy(request, profiles)


def _with_profile_update(
    request: ComputeProteoformQualityMetricsRequest,
    **updates: object,
) -> ComputeProteoformQualityMetricsRequest:
    profile = request.policy.profiles[0]
    payload = {**profile.model_dump(mode="json"), **updates}
    replacement = ProteoformAssayQualityProfile.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )
    return _with_policy(
        request,
        tuple(replacement if item is profile else item for item in request.policy.profiles),
    )


def _metric(
    result: ProteoformQualityResult,
    code: ProteoformQualityMetricCode,
    role: ProteoformRawInputRole | None = None,
) -> ProteoformQualityMetric:
    return next(
        item
        for area in result.assay_quality
        for item in area.metrics
        if item.metric_code is code and (role is None or item.role is role)
    )


def _codes(result: ProteoformQualityResult) -> set[ProteoformQualityFindingCode]:
    return {item.code for item in result.findings}


class _UntouchedMapping(Mapping[str, object]):
    touched = 0

    def __getitem__(self, key: str) -> object:
        type(self).touched += 1
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        type(self).touched += 1
        raise AssertionError

    def __len__(self) -> int:
        type(self).touched += 1
        raise AssertionError


class _ExplodingDict(dict[str, object]):
    def get(self, key: str, _default: object = None) -> object:
        raise RuntimeError(key)


class _FatalDict(dict[str, object]):
    def get(self, key: str, _default: object = None) -> object:
        raise KeyboardInterrupt(key)


def _safe_failure_rejects_without_ledger_access(
    request: ComputeProteoformQualityMetricsRequest,
) -> bool:
    payload = request.model_dump(mode="json")
    _UntouchedMapping.touched = 0
    payload["fact_ledger"] = _UntouchedMapping()
    rejected = False
    try:
        compute_proteoform_quality_metrics(payload)
    except ValueError as error:
        rejected = "prohibits fact-ledger traversal" in str(error)
    return rejected and _UntouchedMapping.touched == 0


def _check(case_id: str, passed: bool, detail: str) -> EvalCheck:  # noqa: FBT001
    return EvalCheck(name=f"scenario.{case_id}", passed=passed, detail=detail)


def _semantic_checks() -> dict[str, EvalCheck]:  # noqa: C901, PLR0912, PLR0915
    request = build_scenario_request()
    result = compute_proteoform_quality_metrics(request)
    raw = request.raw_input_result
    ledger = request.fact_ledger
    if ledger is None:
        raise _InvalidFixtureError
    metrics = tuple(item for area in result.assay_quality for item in area.metrics)
    checks: dict[str, EvalCheck] = {}

    def add(case_id: str, passed: bool, detail: str) -> None:  # noqa: FBT001
        checks[case_id] = _check(case_id, passed, detail)

    # G1: genuine transitive replay and exact deterministic envelope.
    add(
        "canonical_four_role_quality_qualified",
        result.disposition is ProteoformQualityDisposition.QUALIFIED,
        f"disposition={result.disposition.value}",
    )
    add(
        "exact_m0403_full_result_replay",
        result.request.raw_input_result == raw
        and result.receipt.raw_input_result_digest == raw.result_digest
        and result.receipt.raw_input_receipt_digest == raw.receipt.receipt_digest,
        "embedded full M04-03 result and receipt replay",
    )
    add(
        "exact_m0402_transitive_lineage_binding",
        raw.request.lineage_result.result_digest == raw.receipt.lineage_result_digest
        and result.receipt.identity_resolution_digest == raw.receipt.identity_resolution_digest,
        "M04-02 lineage and identity digests close transitively",
    )
    add(
        "exact_m0401_transitive_protocol_binding",
        raw.request.lineage_result.protocol_result_digest == raw.receipt.protocol_result_digest
        and result.receipt.protocol_result_digest == raw.receipt.protocol_result_digest,
        "M04-01 protocol digest closes transitively",
    )
    add(
        "exact_eight_metrics_per_role",
        len(result.assay_quality) == M0404_ROLE_COUNT
        and all(len(item.metrics) == M0404_METRIC_COUNT for item in result.assay_quality)
        and len(metrics) == M0404_COMPUTED_METRIC_COUNT,
        f"areas={len(result.assay_quality)};metrics={len(metrics)}",
    )
    add(
        "deterministic_full_result_equality",
        result == compute_proteoform_quality_metrics(request),
        "two public computations are exactly equal",
    )
    add(
        "compact_receipt_projection_exact",
        result.receipt
        == expected_receipt(request, result.assay_quality, result.findings, result.disposition),
        "receipt exactly projects the embedded full result",
    )
    add(
        "parent_context_preserved_without_emission",
        result.request.context == request.context
        and result.parent_target == "protein_rna_discordance"
        and not result.emits_protein_rna_discordance,
        "parent context retained; parent output not emitted",
    )

    # G2: closed count partitions, integer math, censoring, and ledger binding.
    add(
        "count_partitions_close",
        _counts().valid_record_count
        <= _counts().parsed_record_count
        <= _counts().declared_record_count,
        "canonical count partitions validate",
    )
    completeness = _metric(result, ProteoformQualityMetricCode.RAW_INPUT_COMPLETENESS)
    add(
        "ratio_round_half_up_exact",
        completeness.numerator == ROUNDING_NUMERATOR
        and completeness.denominator == ROUNDING_DENOMINATOR
        and completeness.value_ppm == ROUNDING_VALUE_PPM
        and completeness.status is ProteoformQualityMetricStatus.PASS,
        f"2/3={completeness.value_ppm}ppm;status={completeness.status.value}",
    )
    zero_fact = _mutated_fact(
        request,
        counts={"context_applicable_count": 0, "context_coherent_count": 0},
    )
    zero_result = compute_proteoform_quality_metrics(_with_fact(request, zero_fact))
    zero_metric = _metric(
        zero_result,
        ProteoformQualityMetricCode.SAMPLE_CONTEXT_BINDING_COHERENCE,
        zero_fact.role,
    )
    add(
        "zero_denominator_remains_not_evaluable",
        zero_metric.denominator == 0
        and zero_metric.value_ppm is None
        and zero_metric.status is ProteoformQualityMetricStatus.NOT_EVALUABLE,
        f"value={zero_metric.value_ppm};status={zero_metric.status.value}",
    )
    censored_fact = _mutated_fact(
        request,
        counts={
            "detection_eligible_count": 3,
            "above_detection_limit_count": 2,
            "below_detection_limit_count": 1,
        },
        states={"detection_limit_burden": "censored"},
    )
    censored_result = compute_proteoform_quality_metrics(_with_fact(request, censored_fact))
    censored_metric = _metric(
        censored_result,
        ProteoformQualityMetricCode.DETECTION_LIMIT_BURDEN,
        censored_fact.role,
    )
    add(
        "censored_detection_state_retained",
        censored_metric.observation_state is ProteoformQualityObservationState.CENSORED
        and censored_metric.censored_count == 1
        and censored_metric.value_ppm == CENSORED_VALUE_PPM,
        f"censored={censored_metric.censored_count};value={censored_metric.value_ppm}",
    )
    fact_payload = ledger.role_facts[0].model_dump(mode="json")
    cast("dict[str, object]", fact_payload["states"])["detection_limit_burden"] = "censored"
    add(
        "detection_censoring_shape_rejected",
        _rejects(ProteoformQualityRoleFacts, fact_payload),
        "censored state with zero below-limit count is rejected",
    )
    count_payload = _counts().model_dump(mode="json")
    count_payload["valid_record_count"] = 3
    add(
        "numerator_exceeds_denominator_rejected",
        _rejects(ProteoformQualityRoleCounts, count_payload),
        "invalid numerator partition is rejected",
    )
    ledger_payload = ledger.model_dump(mode="json")
    ledger_payload["ledger_digest"] = "sha256:" + ("f" * 64)
    add(
        "fact_ledger_digest_mismatch_rejected",
        _rejects(ProteoformQualityFactLedger, ledger_payload),
        "stale ledger self-digest is rejected",
    )
    mismatched_fact = _mutated_fact(request, input_id=_oid("input", "wrong-binding"))
    mismatch_result = compute_proteoform_quality_metrics(_with_fact(request, mismatched_fact))
    add(
        "role_fact_binding_mismatch_quarantines",
        mismatch_result.disposition is ProteoformQualityDisposition.QUARANTINED
        and mismatch_result.assay_quality == ()
        and _codes(mismatch_result) == {ProteoformQualityFindingCode.FACT_LEDGER_BINDING_MISMATCH},
        f"disposition={mismatch_result.disposition.value};metrics=0",
    )
    reordered_payload = request.model_dump(mode="json")
    reordered_ledger = cast("dict[str, object]", reordered_payload["fact_ledger"])
    reordered_ledger["role_facts"] = tuple(
        reversed(cast("list[object]", reordered_ledger["role_facts"]))
    )
    reordered = ComputeProteoformQualityMetricsRequest.model_validate_json(
        canonical_json_bytes(reordered_payload), strict=True
    )
    add(
        "semantic_role_order_full_equality",
        compute_proteoform_quality_metrics(reordered) == result,
        "semantic role reordering produces exact full equality",
    )

    # G3: exact, disjoint reviewed profiles and version/unit closure.
    add(
        "exact_profile_per_role_selected",
        len(matching_quality_profiles(request)) == M0404_ROLE_COUNT,
        "exactly one profile selected for every role",
    )
    first_profile = request.policy.profiles[0]
    duplicate_profile = first_profile.model_copy(
        update={"profile_id": _oid("profile", "overlapping-domain")}
    )
    overlap_payload = request.policy.model_dump(mode="json")
    overlap_payload["profiles"] = (*request.policy.profiles, duplicate_profile)
    add(
        "overlapping_profile_domain_rejected",
        _rejects(ProteoformQualityPolicy, overlap_payload),
        "overlapping profile match domains are rejected",
    )
    no_control_fact = _mutated_fact(
        request,
        counts={"control_expected_count": 0, "control_recovered_count": 0},
    )
    missing_profile_result = compute_proteoform_quality_metrics(
        _with_fact(request, no_control_fact)
    )
    add(
        "missing_role_profile_abstains",
        missing_profile_result.disposition is ProteoformQualityDisposition.ABSTAINED
        and _codes(missing_profile_result)
        == {ProteoformQualityFindingCode.ASSAY_PROFILE_UNSUPPORTED},
        f"disposition={missing_profile_result.disposition.value}",
    )
    version_cases = (
        (
            "assay_protocol_version_mismatch_quarantines",
            "approved_assay_protocol_versions",
            ProteoformQualityFindingCode.ASSAY_PROTOCOL_VERSION_MISMATCH,
        ),
        (
            "specimen_processing_version_mismatch_quarantines",
            "approved_specimen_processing_versions",
            ProteoformQualityFindingCode.SPECIMEN_PROCESSING_VERSION_MISMATCH,
        ),
        (
            "unit_definition_version_mismatch_quarantines",
            "approved_unit_definition_versions",
            ProteoformQualityFindingCode.UNIT_DEFINITION_VERSION_MISMATCH,
        ),
    )
    for case_id, field, code in version_cases:
        version_result = compute_proteoform_quality_metrics(
            _with_profile_update(request, **{field: ("9.9.9",)})
        )
        add(
            case_id,
            version_result.disposition is ProteoformQualityDisposition.QUARANTINED
            and code in _codes(version_result),
            f"codes={sorted(item.value for item in _codes(version_result))}",
        )
    applicability_result = compute_proteoform_quality_metrics(
        _with_profile_update(request, applicability="top_down")
    )
    add(
        "proteome_applicability_mismatch_abstains",
        applicability_result.disposition is ProteoformQualityDisposition.ABSTAINED
        and ProteoformQualityFindingCode.ASSAY_PROFILE_UNSUPPORTED in _codes(applicability_result),
        f"disposition={applicability_result.disposition.value}",
    )
    threshold_payload = first_profile.thresholds[0].model_dump(mode="json")
    threshold_payload["direction"] = "at_most"
    add(
        "threshold_direction_contradiction_rejected",
        _rejects(ProteoformQualityThreshold, threshold_payload),
        "metric/direction contradiction is rejected",
    )
    profile_payload = first_profile.model_dump(mode="json")
    profile_payload["thresholds"] = cast("list[object]", profile_payload["thresholds"])[1:]
    add(
        "each_profile_requires_exact_eight_thresholds",
        _rejects(ProteoformAssayQualityProfile, profile_payload),
        "seven-threshold profile is rejected",
    )

    # G4: exact threshold bands, support, and precedence.
    add(
        "all_required_metrics_pass_qualifies",
        result.disposition is ProteoformQualityDisposition.QUALIFIED
        and all(item.status is ProteoformQualityMetricStatus.PASS for item in metrics),
        "all 32 required metrics pass",
    )
    warning_request = _with_threshold(
        request,
        ProteoformQualityMetricCode.RAW_INPUT_COMPLETENESS,
        pass_threshold_ppm=700_000,
        warning_threshold_ppm=600_000,
    )
    warning_result = compute_proteoform_quality_metrics(warning_request)
    add(
        "required_metric_warning_quarantines",
        warning_result.disposition is ProteoformQualityDisposition.QUARANTINED
        and ProteoformQualityFindingCode.REQUIRED_METRIC_WARNING in _codes(warning_result),
        f"disposition={warning_result.disposition.value}",
    )
    failure_request = _with_threshold(
        request,
        ProteoformQualityMetricCode.RAW_INPUT_COMPLETENESS,
        pass_threshold_ppm=800_000,
        warning_threshold_ppm=700_000,
    )
    failure_result = compute_proteoform_quality_metrics(failure_request)
    add(
        "required_metric_failure_quarantines",
        failure_result.disposition is ProteoformQualityDisposition.QUARANTINED
        and ProteoformQualityFindingCode.METRIC_THRESHOLD_FAILED in _codes(failure_result),
        f"disposition={failure_result.disposition.value}",
    )
    optional_warning_result = compute_proteoform_quality_metrics(
        _with_threshold(
            request,
            ProteoformQualityMetricCode.RAW_INPUT_COMPLETENESS,
            pass_threshold_ppm=700_000,
            warning_threshold_ppm=600_000,
            required=False,
        )
    )
    add(
        "optional_metric_warning_limits_support",
        optional_warning_result.disposition is ProteoformQualityDisposition.QUALIFIED
        and optional_warning_result.support.reason_code
        == "proteoform_quality_qualified_with_optional_warning",
        optional_warning_result.support.reason_code,
    )
    optional_failure_result = compute_proteoform_quality_metrics(
        _with_threshold(
            request,
            ProteoformQualityMetricCode.RAW_INPUT_COMPLETENESS,
            pass_threshold_ppm=800_000,
            warning_threshold_ppm=700_000,
            required=False,
        )
    )
    add(
        "optional_metric_failure_quarantines",
        optional_failure_result.disposition is ProteoformQualityDisposition.QUARANTINED
        and ProteoformQualityFindingCode.METRIC_THRESHOLD_FAILED in _codes(optional_failure_result),
        f"disposition={optional_failure_result.disposition.value}",
    )
    state_results: dict[str, ProteoformQualityResult] = {}
    for state in ("missing", "unsupported"):
        state_fact = _mutated_fact(
            request,
            counts={"context_applicable_count": 0, "context_coherent_count": 0},
            states={"sample_context_binding_coherence": state},
        )
        state_results[state] = compute_proteoform_quality_metrics(_with_fact(request, state_fact))
    add(
        "required_metric_missing_abstains",
        state_results["missing"].disposition is ProteoformQualityDisposition.ABSTAINED
        and ProteoformQualityFindingCode.REQUIRED_METRIC_MISSING
        in _codes(state_results["missing"]),
        f"disposition={state_results['missing'].disposition.value}",
    )
    add(
        "required_metric_unsupported_abstains",
        state_results["unsupported"].disposition is ProteoformQualityDisposition.ABSTAINED
        and ProteoformQualityFindingCode.REQUIRED_METRIC_UNSUPPORTED
        in _codes(state_results["unsupported"]),
        f"disposition={state_results['unsupported'].disposition.value}",
    )
    add(
        "required_metric_not_evaluable_abstains",
        zero_result.disposition is ProteoformQualityDisposition.ABSTAINED
        and ProteoformQualityFindingCode.REQUIRED_METRIC_NOT_EVALUABLE in _codes(zero_result),
        f"disposition={zero_result.disposition.value}",
    )
    precedence_fact = _mutated_fact(
        failure_request,
        counts={"context_applicable_count": 0, "context_coherent_count": 0},
        states={"sample_context_binding_coherence": "missing"},
    )
    precedence_result = compute_proteoform_quality_metrics(
        _with_fact(failure_request, precedence_fact)
    )
    add(
        "quarantine_precedes_abstention",
        precedence_result.disposition is ProteoformQualityDisposition.QUARANTINED
        and ProteoformQualityFindingCode.METRIC_THRESHOLD_FAILED in _codes(precedence_result)
        and ProteoformQualityFindingCode.REQUIRED_METRIC_MISSING in _codes(precedence_result),
        f"codes={sorted(item.value for item in _codes(precedence_result))}",
    )

    # G5: strict upstream replay and ledger-free safe failure.
    add(
        "validated_upstream_requires_fact_ledger",
        _rejects(
            ComputeProteoformQualityMetricsRequest,
            _request_payload(request, ledger=None),
        ),
        "validated upstream without ledger is rejected",
    )
    quarantined_request = build_scenario_request("quarantined_upstream_zero_ledger_traversal")
    quarantined = compute_proteoform_quality_metrics(quarantined_request)
    abstained_request = build_scenario_request("abstained_upstream_zero_ledger_traversal")
    abstained = compute_proteoform_quality_metrics(abstained_request)
    add(
        "quarantined_upstream_zero_ledger_traversal",
        quarantined_request.fact_ledger is None
        and quarantined.disposition is ProteoformQualityDisposition.QUARANTINED
        and quarantined.assay_quality == ()
        and _safe_failure_rejects_without_ledger_access(quarantined_request),
        "genuine quarantined M04-03 yields zero metrics and never traverses a supplied ledger",
    )
    add(
        "abstained_upstream_zero_ledger_traversal",
        abstained_request.fact_ledger is None
        and abstained.disposition is ProteoformQualityDisposition.ABSTAINED
        and abstained.assay_quality == ()
        and _safe_failure_rejects_without_ledger_access(abstained_request),
        "genuine abstained M04-03 yields zero metrics and never traverses a supplied ledger",
    )
    stale_bindings = (
        ("stale_identity_binding_rejected", "identity_lineage", "binding_digest"),
        ("stale_quality_result_binding_rejected", "quality", "evidence.digest"),
        ("stale_support_receipt_binding_rejected", "support", "evidence.digest"),
        ("stale_intended_use_binding_rejected", "intended_use", "evidence.digest"),
    )
    for case_id, role, path in stale_bindings:
        stale = request.model_dump(mode="json")
        refs = cast("dict[str, object]", cast("dict[str, object]", stale["context"])["references"])
        control = cast("dict[str, object]", refs[role])
        if path == "binding_digest":
            control[path] = "sha256:" + ("f" * 64)
        else:
            cast("dict[str, object]", control["evidence"])["digest"] = "sha256:" + ("f" * 64)
        add(
            case_id,
            _rejects(ComputeProteoformQualityMetricsRequest, stale),
            "stale context binding is rejected",
        )
    resigned = request.model_dump(mode="json")
    upstream = cast("dict[str, object]", resigned["raw_input_result"])
    upstream["result_id"] = "result.m0403." + ("f" * 64)
    upstream["result_digest"] = m0403_result_payload_digest(upstream)
    add(
        "resigned_m0403_full_result_forgery_rejected",
        _rejects(ComputeProteoformQualityMetricsRequest, resigned),
        "re-signed semantic M04-03 forgery is rejected",
    )

    # G6: evidence retention, privacy, and authority ceiling.
    add(
        "all_input_artifact_references_preserved",
        result.request.raw_input_result.request.artifacts == raw.request.artifacts,
        "all four upstream artifact references are unchanged",
    )
    first_fact, second_fact = ledger.role_facts[:2]
    duplicate_payload = first_fact.model_dump(mode="json")
    cast("dict[str, object]", duplicate_payload["evidence"])["digest"] = second_fact.evidence.digest
    duplicate_fact = ProteoformQualityRoleFacts.model_validate_json(
        canonical_json_bytes(duplicate_payload), strict=True
    )
    duplicate_result = compute_proteoform_quality_metrics(_with_fact(request, duplicate_fact))
    duplicate_digest_count = sum(
        item.reference.digest == second_fact.evidence.digest for item in duplicate_result.evidence
    )
    add(
        "duplicate_content_retained_without_deduplication",
        duplicate_digest_count == DUPLICATE_EVIDENCE_COUNT
        and len(duplicate_result.evidence) == len(result.evidence),
        f"same-content evidence occurrences={duplicate_digest_count}",
    )
    missing_metric = _metric(
        state_results["missing"],
        ProteoformQualityMetricCode.SAMPLE_CONTEXT_BINDING_COHERENCE,
        ledger.role_facts[0].role,
    )
    add(
        "missing_evidence_never_becomes_negative",
        missing_metric.value_ppm is None
        and missing_metric.numerator is None
        and missing_metric.status is ProteoformQualityMetricStatus.NOT_EVALUABLE,
        "missing observation remains nonnumeric and not evaluable",
    )
    add(
        "safe_failure_minimum_12_evidence",
        len(quarantined.evidence) == M0404_MIN_EVIDENCE
        and len(abstained.evidence) == M0404_MIN_EVIDENCE,
        f"quarantined={len(quarantined.evidence)};abstained={len(abstained.evidence)}",
    )
    maximum_request = build_maximum_scenario().request
    maximum = compute_proteoform_quality_metrics(maximum_request)
    maximum_ledger = maximum_request.fact_ledger
    maximum_metric_count = sum(len(item.metrics) for item in maximum.assay_quality)
    maximum_threshold_count = sum(len(item.thresholds) for item in maximum_request.policy.profiles)
    add(
        "maximum_45_evidence",
        maximum.disposition is ProteoformQualityDisposition.QUALIFIED
        and len(maximum_request.policy.profiles) == M0404_MAX_PROFILES
        and maximum_threshold_count == M0404_MAX_PROFILES * M0404_METRIC_COUNT
        and maximum_ledger is not None
        and len(maximum_ledger.role_facts) == M0404_ROLE_COUNT
        and len(maximum.assay_quality) == M0404_ROLE_COUNT
        and maximum_metric_count == M0404_COMPUTED_METRIC_COUNT
        and len(maximum.evidence) == M0404_MAX_EVIDENCE,
        (
            f"disposition={maximum.disposition.value};"
            f"profiles={len(maximum_request.policy.profiles)};"
            f"thresholds={maximum_threshold_count};"
            f"facts={len(maximum_ledger.role_facts) if maximum_ledger is not None else 0};"
            f"assay={len(maximum.assay_quality)};metrics={maximum_metric_count};"
            f"evidence={len(maximum.evidence)}"
        ),
    )
    canary = "CANARY_M0404_EXTERNAL_CONTENT_DO_NOT_REFLECT"
    canary_bytes = canary.encode()
    canary_base = build_m0403_scenario()
    canary_role = ProteoformRawInputRole.GENOME
    canary_artifact = next(
        item for item in canary_base.request.artifacts if item.role is canary_role
    )
    canary_reference = canary_artifact.content_reference.model_copy(
        update={"digest": f"sha256:{hashlib.sha256(canary_bytes).hexdigest()}"}
    )
    canary_scenario = with_m0403_document_updates(
        canary_base,
        {
            canary_role: {
                "declared_record_count": 424_242,
                "content_reference": canary_reference,
            }
        },
        artifact_updates={canary_role: {"content_reference": canary_reference}},
    )
    canary_raw_result = ingest_proteoform_raw_inputs(
        canary_scenario.request,
        canary_scenario.artifacts_by_role,
    )
    canary_result = compute_proteoform_quality_metrics(
        _request_from_raw_result(canary_raw_result, M0404_ROLE_COUNT)
    )
    canary_rendered = canonical_json_bytes(canary_result)
    add(
        "recursive_canary_absent_from_result",
        canary_bytes not in canary_rendered and canary_reference.digest.encode() in canary_rendered,
        "external canary is represented only by its opaque content digest",
    )
    add(
        "exact_three_limitations",
        result.limitations == expected_limitations()
        and len(result.limitations) == M0404_LIMITATION_COUNT,
        f"limitations={len(result.limitations)}",
    )
    authority_fields = (
        "emits_protein_rna_discordance",
        "emits_proteogenomic_state",
        "emits_proteotype",
        "emits_protein_level_subtype",
        "infers_identity",
        "infers_consent",
        "infers_protein",
        "infers_proteoform",
        "infers_isoform",
        "localizes_modification",
        "infers_kinase_activity",
        "performs_cn_to_protein_regression",
        "performs_all_omics_fusion",
        "recommends_treatment",
        "mutates_upstream",
        "executes_model",
    )
    add(
        "all_authority_flags_false",
        all(getattr(result, field) is False for field in authority_fields),
        "all 16 authority flags are false",
    )

    # G7: uncertainty/provenance closure and adversarial result replay.
    uncertainty = result.uncertainty.model_dump(mode="json")
    dimensions = tuple(key for key in uncertainty if key != "sensitivity_notes")
    add(
        "all_seven_uncertainty_dimensions_explicit_not_estimable",
        len(dimensions) == EXPECTED_CONTROL_COUNT
        and all(
            cast("dict[str, object]", uncertainty[key])["state"] == "not_estimable"
            and cast("dict[str, object]", uncertainty[key])["probability"] is None
            for key in dimensions
        ),
        f"dimensions={len(dimensions)}",
    )
    add(
        "sensitivity_notes_exact",
        result.uncertainty == expected_uncertainty(),
        "sensitivity notes and uncertainty profile replay exactly",
    )
    add(
        "provenance_controls_exact_seven",
        len(result.provenance.control_decisions) == EXPECTED_CONTROL_COUNT,
        f"controls={len(result.provenance.control_decisions)}",
    )
    add(
        "provenance_input_digest_set_exact",
        result.provenance == expected_provenance(request, metrics, result.receipt),
        f"digests={len(result.provenance.input_digests)}",
    )
    add(
        "findings_unique_and_canonical",
        len(warning_result.findings) == len(set(warning_result.findings))
        and warning_result.findings
        == tuple(sorted(warning_result.findings, key=canonical_json_bytes)),
        f"findings={len(warning_result.findings)}",
    )
    metric_forgery = result.model_dump(mode="json")
    metric_region = cast("list[object]", metric_forgery["assay_quality"])
    forged_area = cast("dict[str, object]", metric_region[0])
    forged_metric = cast("dict[str, object]", cast("list[object]", forged_area["metrics"])[0])
    forged_metric["value_ppm"] = cast("int", forged_metric["value_ppm"]) + 1
    metric_forgery["result_digest"] = result_payload_digest(metric_forgery)
    add(
        "result_metric_forgery_rejected",
        _rejects(ProteoformQualityResult, metric_forgery),
        "re-signed metric forgery is rejected",
    )
    finding_forgery = warning_result.model_dump(mode="json")
    forged_finding = cast("dict[str, object]", cast("list[object]", finding_forgery["findings"])[0])
    forged_finding["message"] = "forged"
    finding_forgery["result_digest"] = result_payload_digest(finding_forgery)
    add(
        "result_finding_forgery_rejected",
        _rejects(ProteoformQualityResult, finding_forgery),
        "re-signed finding forgery is rejected",
    )
    receipt_forgery = result.model_dump(mode="json")
    cast("dict[str, object]", receipt_forgery["receipt"])["receipt_digest"] = "sha256:" + ("f" * 64)
    receipt_forgery["receipt_digest"] = "sha256:" + ("f" * 64)
    receipt_forgery["result_digest"] = result_payload_digest(receipt_forgery)
    digest_forgery = result.model_dump(mode="json")
    digest_forgery["result_digest"] = "sha256:" + ("f" * 64)
    add(
        "receipt_and_result_digest_forgery_rejected",
        _rejects(ProteoformQualityResult, receipt_forgery)
        and _rejects(ProteoformQualityResult, digest_forgery),
        "receipt and result digest forgeries are both rejected",
    )

    # G8: seven-control ingress, hostile mapping, strict JSON, caps, and interfaces.
    denied_states = {
        "approved_configuration": "rejected",
        "identity_lineage": "unresolved",
        "provenance": "rejected",
        "consent": "denied",
        "quality": "rejected",
        "support": "rejected",
        "intended_use": "rejected",
    }
    denied_case_ids = {
        "approved_configuration": "approved_configuration_denial_zero_traversal",
        "identity_lineage": "identity_denial_zero_traversal",
        "provenance": "provenance_denial_zero_traversal",
        "consent": "consent_denial_zero_traversal",
        "quality": "quality_denial_zero_traversal",
        "support": "support_denial_zero_traversal",
        "intended_use": "intended_use_denial_zero_traversal",
    }
    for role, state in denied_states.items():
        payload = request.model_dump(mode="json")
        refs = cast(
            "dict[str, object]", cast("dict[str, object]", payload["context"])["references"]
        )
        cast("dict[str, object]", refs[role])["state"] = state
        _UntouchedMapping.touched = 0
        payload["fact_ledger"] = _UntouchedMapping()
        denied = False
        try:
            preflight_proteoform_quality_authorization(payload)
        except ProteoformQualityAuthorizationError:
            denied = True
        add(
            denied_case_ids[role],
            denied and _UntouchedMapping.touched == 0,
            f"denied={denied};ledger_touches={_UntouchedMapping.touched}",
        )
    _UntouchedMapping.touched = 0
    arbitrary_denied = False
    try:
        preflight_proteoform_quality_authorization(_UntouchedMapping())
    except ProteoformQualityAuthorizationError:
        arbitrary_denied = True
    add(
        "arbitrary_mapping_rejected_without_access",
        arbitrary_denied and _UntouchedMapping.touched == 0,
        f"denied={arbitrary_denied};touches={_UntouchedMapping.touched}",
    )
    exploding = _ExplodingDict(request.model_dump(mode="json"))
    fatal = _FatalDict(request.model_dump(mode="json"))
    hostile_dict_overrides_bypassed = True
    try:
        preflight_proteoform_quality_authorization(exploding)
        preflight_proteoform_quality_authorization(fatal)
    except BaseException:  # noqa: BLE001 - the case explicitly audits both exception families.
        hostile_dict_overrides_bypassed = False
    exception_failed_closed = False
    with patch.object(m0404_engine, "_member", side_effect=RuntimeError("ordinary-exception")):
        try:
            preflight_proteoform_quality_authorization(request)
        except ProteoformQualityAuthorizationError:
            exception_failed_closed = True
    base_exception_propagated = False
    with patch.object(m0404_engine, "_member", side_effect=KeyboardInterrupt("fatal-exception")):
        try:
            preflight_proteoform_quality_authorization(request)
        except KeyboardInterrupt:
            base_exception_propagated = True
    add(
        "dict_subclass_exception_baseexception_firewall",
        hostile_dict_overrides_bypassed and exception_failed_closed and base_exception_propagated,
        (
            f"dict_overrides_bypassed={hostile_dict_overrides_bypassed};"
            f"exception_failed_closed={exception_failed_closed};"
            f"baseexception_propagated={base_exception_propagated}"
        ),
    )
    duplicate = request.model_dump_json().replace(
        '"operation":"compute_proteoform_quality_metrics"',
        (
            '"operation":"compute_proteoform_quality_metrics",'
            '"operation":"compute_proteoform_quality_metrics"'
        ),
        1,
    )
    duplicate_rejected = False
    try:
        strict_json_loads(duplicate)
    except StrictJsonError:
        duplicate_rejected = True
    unknown = request.model_dump(mode="json")
    unknown["unexpected"] = True
    coercion = request.model_dump(mode="json")
    coercion["contract_version"] = 1
    add(
        "duplicate_json_unknown_field_and_coercion_rejected",
        duplicate_rejected
        and _rejects(ComputeProteoformQualityMetricsRequest, unknown)
        and _rejects(ComputeProteoformQualityMetricsRequest, coercion),
        "duplicate key, unknown field, and coercion are rejected",
    )
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    exact = serialized + (b" " * (4 * 1024 * 1024 - len(serialized)))
    exact_accepted = strict_json_loads(exact, max_bytes=4 * 1024 * 1024) is not None
    excess_rejected = False
    try:
        strict_json_loads(exact + b" ", max_bytes=4 * 1024 * 1024)
    except StrictJsonError:
        excess_rejected = True
    add(
        "request_exact_4mib_and_first_excess",
        exact_accepted and excess_rejected,
        f"exact={len(exact)};excess_rejected={excess_rejected}",
    )
    service = M0404Service()
    plugin = M0404Plugin(service)
    plugin_result = plugin.run(plugin.validate(serialized))
    schema_registry = contract_json_schemas()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        request_path = root / "request.json"
        output_path = root / "result.json"
        duplicate_path = root / "duplicate-request.json"
        duplicate_output_path = root / "duplicate-result.json"
        request_path.write_bytes(serialized)
        duplicate_path.write_text(duplicate, encoding="utf-8")
        cli_parity = CliRunner().invoke(
            cli_app,
            [
                "proteoform-quality",
                "compute",
                str(request_path),
                "--output",
                str(output_path),
            ],
        )
        with TestClient(create_app(root / "api.sqlite3")) as client:
            api_parity = client.post(
                "/v1/modules/M04-04/quality-metric-computation",
                content=serialized,
                headers={"content-type": "application/json"},
            )
            api_rejection = client.post(
                "/v1/modules/M04-04/quality-metric-computation",
                content=duplicate,
                headers={"content-type": "application/json"},
            )
            api_schema_results = tuple(
                (
                    name,
                    client.get(f"/v1/contracts/M04-04/{name}/schema"),
                )
                for name in schema_registry
            )
        cli_schema_results = tuple(
            (
                name,
                CliRunner().invoke(cli_app, ["proteoform-quality", "export-schema", name]),
            )
            for name in schema_registry
        )
        api_result = (
            ProteoformQualityResult.model_validate_json(api_parity.content, strict=True)
            if api_parity.status_code == HTTP_OK
            else None
        )
        cli_result = (
            ProteoformQualityResult.model_validate_json(output_path.read_bytes(), strict=True)
            if cli_parity.exit_code == 0 and output_path.is_file()
            else None
        )
        all_api_schemas_equal = all(
            response.status_code == HTTP_OK and response.json() == schema_registry[name]
            for name, response in api_schema_results
        )
        all_cli_schemas_equal = all(
            invocation.exit_code == 0 and json.loads(invocation.stdout) == schema_registry[name]
            for name, invocation in cli_schema_results
        )
        add(
            "library_service_plugin_api_cli_schema_parity",
            result == service.execute(request) == plugin_result == api_result == cli_result
            and len(contract_json_schemas()) == EXPECTED_SCHEMA_COUNT
            and all_api_schemas_equal
            and all_cli_schemas_equal,
            (
                "library/service/plugin/API/CLI results and all 13 schema surfaces agree;"
                f"api_status={api_parity.status_code};cli_exit={cli_parity.exit_code};"
                f"api_schemas={len(api_schema_results)};cli_schemas={len(cli_schema_results)}"
            ),
        )
        cli_duplicate_refusal = CliRunner().invoke(
            cli_app,
            [
                "proteoform-quality",
                "compute",
                str(duplicate_path),
                "--output",
                str(duplicate_output_path),
            ],
        )
        existing_bytes = output_path.read_bytes() if output_path.is_file() else b""
        cli_refusal = CliRunner().invoke(
            cli_app,
            [
                "proteoform-quality",
                "compute",
                str(request_path),
                "--output",
                str(output_path),
            ],
        )
        symlink_path = root / "symlink-result.json"
        symlink_target = root / "symlink-target.json"
        symlink_supported = True
        symlink_refused = False
        try:
            symlink_path.symlink_to(symlink_target)
        except OSError:
            symlink_supported = False
            symlink_refused = True
        else:
            symlink_cli = CliRunner().invoke(
                cli_app,
                [
                    "proteoform-quality",
                    "compute",
                    str(request_path),
                    "--output",
                    str(symlink_path),
                ],
            )
            symlink_refused = (
                symlink_cli.exit_code == 1
                and symlink_path.is_symlink()
                and not symlink_target.exists()
            )
        interface_closed = (
            cli_refusal.exit_code == 1
            and output_path.read_bytes() == existing_bytes
            and api_rejection.status_code == HTTP_UNPROCESSABLE_CONTENT
            and cli_duplicate_refusal.exit_code == CLI_USAGE_ERROR
            and not duplicate_output_path.exists()
            and symlink_refused
        )
    add(
        "api_cli_strict_json_symlink_and_existing_output_refused",
        interface_closed,
        (
            "API/CLI reject duplicate JSON; CLI preserves an existing output and refuses a "
            f"symlink;symlink_supported={symlink_supported}"
        ),
    )
    return checks


def run_evaluation() -> dict[str, object]:
    """Execute all 72 locked cases through public contracts and runtime surfaces."""

    corpus = _corpus()
    groups = cast("list[dict[str, Any]]", corpus["scenario_groups"])
    declared = [cast("str", case) for group in groups for case in group["case_ids"]]
    evaluated = _semantic_checks()
    checks = [evaluated[item] for item in declared if item in evaluated]
    executed = [item.name.removeprefix("scenario.") for item in checks]
    missing = sorted(set(declared) - set(executed))
    extra = sorted(set(executed) - set(declared))
    duplicated = sorted({item for item in executed if executed.count(item) > 1})
    passed = (
        len(groups) == EXPECTED_GROUP_COUNT
        and tuple(len(cast("list[object]", group["case_ids"])) for group in groups)
        == EXPECTED_ALLOCATION
        and len(declared) == EXPECTED_CASE_COUNT
        and not missing
        and not extra
        and not duplicated
        and all(item.passed for item in checks)
    )
    return {
        "module_id": MODULE_ID,
        "passed": passed,
        "phase": "G1",
        "declared_case_count": len(declared),
        "executed_case_count": len(executed),
        "missing_case_ids": missing,
        "extra_case_ids": extra,
        "duplicated_case_ids": duplicated,
        "checks": [asdict(item) for item in checks],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    report = run_evaluation()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0 if report["passed"] else 1


__all__ = [
    "Scenario",
    "build_maximum_scenario",
    "build_representative_quality_fixture",
    "build_scenario",
    "build_scenario_request",
    "main",
    "run_evaluation",
]


if __name__ == "__main__":
    raise SystemExit(main())
