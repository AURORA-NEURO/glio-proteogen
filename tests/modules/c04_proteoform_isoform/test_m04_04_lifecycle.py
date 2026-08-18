"""Focused M04-04 runtime lifecycle, firewall, fixed-point, and replay tests."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, NoReturn, cast

import pytest
from evals.m04_02.run import build_scenario_request as build_m0402_request
from evals.m04_03.run import build_scenario as build_m0403_scenario
from evals.m04_04.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m04_02 import ProteoformLineageArtifactRole
from glio_proteogen.contracts.m04_03 import (
    IngestProteoformRawInputsRequest,
    ProteoformRawInputDisposition,
    ProteoformRawInputRole,
)
from glio_proteogen.contracts.m04_03 import (
    result_payload_digest as m0403_result_payload_digest,
)
from glio_proteogen.contracts.m04_04 import (
    M0404_COMPUTED_METRIC_COUNT,
    M0404_LIMITATION_COUNT,
    M0404_MAX_CANONICAL_REQUEST_BYTES,
    M0404_ROLE_COUNT,
    ComputeProteoformQualityMetricsRequest,
    ProteoformQualityDisposition,
    ProteoformQualityFactLedger,
    ProteoformQualityFindingCode,
    ProteoformQualityMetricCode,
    ProteoformQualityMetricStatus,
    ProteoformQualityObservationState,
    ProteoformQualityResult,
    ProteoformQualityRoleCounts,
    ProteoformQualityRoleFactStates,
    configuration_digest,
    fact_ledger_digest,
    result_payload_digest,
)
from glio_proteogen.contracts.m04_04.v1 import (
    _issue_raw_input_replay_capability,
    _validate_request_with_raw_capability,
    _validate_result_with_capability,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage import (
    reconcile_proteoform_identity_lineage,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_03_raw_ingestion import (
    ingest_proteoform_raw_inputs,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics import (
    M0404Plugin,
    M0404ProteoformQualityEngine,
    M0404Service,
    ProteoformQualityAuthorizationError,
    ValidatedM0404Request,
    compute_proteoform_quality_metrics,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics import (
    engine as m0404_engine,
)

_ROLE_PROJECTION = {
    ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
        ProteoformLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST
    ),
    ProteoformRawInputRole.GENOME: ProteoformLineageArtifactRole.GENOME_MANIFEST,
    ProteoformRawInputRole.TRANSCRIPTOME: ProteoformLineageArtifactRole.TRANSCRIPTOME_MANIFEST,
    ProteoformRawInputRole.PTM_ANNOTATIONS: (ProteoformLineageArtifactRole.PTM_ANNOTATION_MANIFEST),
}
_WARNING_PPM = 500_000


class _HostileTraversalError(AssertionError):
    """Governed material was touched before authorization or safe-failure classification."""


class _TraversalTrap(Mapping[str, object]):
    def __init__(self) -> None:
        self.traversals = 0

    def _fail(self) -> NoReturn:
        self.traversals += 1
        raise _HostileTraversalError

    def __getitem__(self, key: str) -> object:
        del key
        self._fail()

    def __iter__(self) -> Iterator[str]:
        self._fail()

    def __len__(self) -> int:  # noqa: PLE0303 - intentional hostile mapping.
        self._fail()


class _HostileDict(dict[object, object]):
    def get(self, key: object, default: object = None) -> object:
        del key, default
        raise _HostileTraversalError

    def __getitem__(self, key: object) -> object:
        del key
        raise _HostileTraversalError

    def __iter__(self) -> Iterator[object]:
        raise _HostileTraversalError

    def items(self) -> NoReturn:
        raise _HostileTraversalError


class _HostileList(list[object]):
    def __iter__(self) -> Iterator[object]:
        raise _HostileTraversalError


class _HostileTuple(tuple[object, ...]):
    __slots__ = ()

    def __iter__(self) -> Iterator[object]:
        raise _PreflightBaseException


class _PreflightBaseException(BaseException):
    """Sentinel proving BaseException is never swallowed."""


class _PrivateCallerError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("private caller detail")


@pytest.fixture(scope="module")
def canonical_request() -> ComputeProteoformQualityMetricsRequest:
    return build_scenario_request()


def _metric(
    result: ProteoformQualityResult,
    role: ProteoformRawInputRole,
    code: ProteoformQualityMetricCode,
) -> Any:
    assay = next(item for item in result.assay_quality if item.role is role)
    return next(item for item in assay.metrics if item.metric_code is code)


def _with_role_fact(
    request: ComputeProteoformQualityMetricsRequest,
    role: ProteoformRawInputRole,
    *,
    counts: ProteoformQualityRoleCounts | None = None,
    states: ProteoformQualityRoleFactStates | None = None,
) -> ComputeProteoformQualityMetricsRequest:
    ledger = request.fact_ledger
    assert ledger is not None
    facts = tuple(
        fact.model_copy(
            update={
                **({"counts": counts} if fact.role is role and counts is not None else {}),
                **({"states": states} if fact.role is role and states is not None else {}),
            }
        )
        for fact in ledger.role_facts
    )
    payload = ledger.model_dump(mode="python", exclude_none=False)
    payload["role_facts"] = facts
    payload["ledger_digest"] = "sha256:" + ("0" * 64)
    payload["ledger_digest"] = fact_ledger_digest(payload)
    rebound = ProteoformQualityFactLedger.model_validate(payload, strict=True)
    return request.model_copy(update={"fact_ledger": rebound})


def _counts(
    request: ComputeProteoformQualityMetricsRequest,
    role: ProteoformRawInputRole,
    **updates: int,
) -> ProteoformQualityRoleCounts:
    assert request.fact_ledger is not None
    fact = next(item for item in request.fact_ledger.role_facts if item.role is role)
    payload = fact.counts.model_dump(mode="python")
    payload.update(updates)
    return ProteoformQualityRoleCounts.model_validate(payload, strict=True)


def _states(
    request: ComputeProteoformQualityMetricsRequest,
    role: ProteoformRawInputRole,
    **updates: ProteoformQualityObservationState,
) -> ProteoformQualityRoleFactStates:
    assert request.fact_ledger is not None
    fact = next(item for item in request.fact_ledger.role_facts if item.role is role)
    payload = fact.states.model_dump(mode="python")
    payload.update(updates)
    return ProteoformQualityRoleFactStates.model_validate(payload, strict=True)


def _raw_request_for_lineage(case_id: str) -> IngestProteoformRawInputsRequest:
    scenario = build_m0403_scenario()
    lineage = reconcile_proteoform_identity_lineage(build_m0402_request(case_id))
    claims = {item.role: item for item in lineage.request.artifact_claims}
    artifacts = tuple(
        item.model_copy(
            update={
                "lineage_claim_id": claims[_ROLE_PROJECTION[item.role]].claim_id,
                "manifest_reference": claims[_ROLE_PROJECTION[item.role]].artifact,
            }
        )
        for item in scenario.request.artifacts
    )
    refs = scenario.request.context.references
    references = refs.model_copy(
        update={
            "identity_lineage": refs.identity_lineage.model_copy(
                update={"binding_digest": lineage.identity_resolution_digest}
            ),
            "quality": refs.quality.model_copy(
                update={
                    "evidence": refs.quality.evidence.model_copy(
                        update={"digest": lineage.result_digest}
                    )
                }
            ),
            "support": refs.support.model_copy(
                update={
                    "evidence": refs.support.evidence.model_copy(
                        update={"digest": lineage.receipt.receipt_digest}
                    )
                }
            ),
            "intended_use": refs.intended_use.model_copy(
                update={
                    "evidence": refs.intended_use.evidence.model_copy(
                        update={"digest": lineage.receipt.intended_use_evidence_digest}
                    )
                }
            ),
        }
    )
    context = scenario.request.context.model_copy(update={"references": references})
    return IngestProteoformRawInputsRequest(
        request_id=context.request_id,
        context=context,
        lineage_result=lineage,
        policy=scenario.request.policy,
        artifacts=artifacts,
        supersedes_result_digest=None,
    )


def _safe_quality_request(
    canonical: ComputeProteoformQualityMetricsRequest,
    case_id: str,
) -> ComputeProteoformQualityMetricsRequest:
    raw_result = ingest_proteoform_raw_inputs(_raw_request_for_lineage(case_id), _TraversalTrap())
    refs = canonical.context.references
    references = refs.model_copy(
        update={
            "identity_lineage": refs.identity_lineage.model_copy(
                update={"binding_digest": raw_result.receipt.identity_resolution_digest}
            ),
            "quality": refs.quality.model_copy(
                update={
                    "evidence": refs.quality.evidence.model_copy(
                        update={"digest": raw_result.result_digest}
                    )
                }
            ),
            "support": refs.support.model_copy(
                update={
                    "evidence": refs.support.evidence.model_copy(
                        update={"digest": raw_result.receipt.receipt_digest}
                    )
                }
            ),
            "intended_use": refs.intended_use.model_copy(
                update={
                    "evidence": refs.intended_use.evidence.model_copy(
                        update={"digest": raw_result.receipt.intended_use_evidence_digest}
                    )
                }
            ),
            "approved_configuration": refs.approved_configuration.model_copy(
                update={
                    "evidence": refs.approved_configuration.evidence.model_copy(
                        update={"digest": configuration_digest(canonical.policy)}
                    )
                }
            ),
        }
    )
    context = canonical.context.model_copy(update={"references": references})
    return ComputeProteoformQualityMetricsRequest(
        request_id=context.request_id,
        context=context,
        raw_input_result=raw_result,
        policy=canonical.policy,
        fact_ledger=None,
        supersedes_result_digest=None,
    )


def test_canonical_quality_result_is_deterministic_closed_and_metadata_only(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    first = compute_proteoform_quality_metrics(canonical_request)
    second = M0404ProteoformQualityEngine().compute(canonical_request)

    assert first == second
    assert first.disposition is ProteoformQualityDisposition.QUALIFIED
    assert len(first.assay_quality) == M0404_ROLE_COUNT
    assert sum(len(item.metrics) for item in first.assay_quality) == M0404_COMPUTED_METRIC_COUNT
    assert first.findings == ()
    assert first.support.status is SupportStatus.SUPPORTED
    assert len(first.limitations) == M0404_LIMITATION_COUNT
    assert not first.human_review_required
    assert not any(
        (
            first.emits_protein_rna_discordance,
            first.emits_proteogenomic_state,
            first.emits_proteotype,
            first.emits_protein_level_subtype,
            first.infers_identity,
            first.infers_consent,
            first.infers_protein,
            first.infers_proteoform,
            first.infers_isoform,
            first.localizes_modification,
            first.infers_kinase_activity,
            first.performs_cn_to_protein_regression,
            first.performs_all_omics_fusion,
            first.recommends_treatment,
            first.mutates_upstream,
            first.executes_model,
        )
    )
    assert (
        ProteoformQualityResult.model_validate_json(first.model_dump_json(), strict=True) == first
    )


def test_library_engine_service_and_plugin_have_exact_parity(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    expected = compute_proteoform_quality_metrics(canonical_request)
    service = M0404Service()
    plugin = M0404Plugin(service)
    token = plugin.validate(canonical_json_bytes(canonical_request.model_dump(mode="json")))

    assert expected == service.execute(canonical_request) == plugin.run(token)
    assert isinstance(token, ValidatedM0404Request)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M04-04"
    assert plugin.descriptor().owner == "Data engineering"
    assert (plugin.descriptor().safety_class, plugin.descriptor().gate) == ("S2", "G1")
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(canonical_request)  # type: ignore[arg-type]


def test_typed_plugin_validation_uses_the_strict_service_boundary(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    plugin = M0404Plugin(M0404Service())
    token = plugin.validate(canonical_request)

    assert token.request == canonical_request
    assert plugin.run(token) == compute_proteoform_quality_metrics(canonical_request)


@pytest.mark.parametrize(
    ("control", "denied_state"),
    [
        ("approved_configuration", "rejected"),
        ("identity_lineage", "unresolved"),
        ("provenance", "rejected"),
        ("consent", "withheld"),
        ("quality", "rejected"),
        ("support", "rejected"),
        ("intended_use", "rejected"),
    ],
)
def test_each_denied_control_precedes_upstream_policy_and_ledger_traversal(
    canonical_request: ComputeProteoformQualityMetricsRequest,
    control: str,
    denied_state: str,
) -> None:
    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    cast("dict[str, Any]", payload["context"])["references"][control]["state"] = denied_state
    governed = (_TraversalTrap(), _TraversalTrap(), _TraversalTrap())
    payload["raw_input_result"], payload["policy"], payload["fact_ledger"] = governed

    with pytest.raises(ProteoformQualityAuthorizationError):
        compute_proteoform_quality_metrics(payload)
    assert all(item.traversals == 0 for item in governed)


@pytest.mark.parametrize(
    "candidate",
    [
        _TraversalTrap(),
        {"context": _TraversalTrap()},
        {"context": {"references": _TraversalTrap()}},
    ],
)
def test_arbitrary_mapping_is_denied_without_access(candidate: object) -> None:
    with pytest.raises(ProteoformQualityAuthorizationError):
        compute_proteoform_quality_metrics(candidate)
    if isinstance(candidate, _TraversalTrap):
        assert candidate.traversals == 0


def test_dict_subclass_overrides_are_ignored(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    hostile = _HostileDict(cast("dict[object, object]", payload))
    assert compute_proteoform_quality_metrics(hostile) == compute_proteoform_quality_metrics(
        canonical_request
    )


def test_nested_raw_builtin_subclass_overrides_are_ignored(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    raw = cast("dict[str, object]", payload["raw_input_result"])
    raw["request"] = _HostileDict(cast("dict[object, object]", raw["request"]))
    raw["validated_inputs"] = _HostileTuple(cast("tuple[object, ...]", raw["validated_inputs"]))
    raw["evidence"] = _HostileList(cast("tuple[object, ...]", raw["evidence"]))
    payload["raw_input_result"] = _HostileDict(cast("dict[object, object]", raw))

    assert compute_proteoform_quality_metrics(payload) == compute_proteoform_quality_metrics(
        canonical_request
    )


def test_nested_raw_nonstring_keys_and_arbitrary_mappings_fail_without_access(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    raw = cast("dict[str, object]", payload["raw_input_result"])
    raw_request = cast("dict[object, object]", raw["request"])
    raw_request[1] = "private nested value"
    ledger = _TraversalTrap()
    payload["fact_ledger"] = ledger
    with pytest.raises(TypeError, match="exact string keys") as captured:
        compute_proteoform_quality_metrics(payload)
    assert "private nested value" not in str(captured.value)
    assert ledger.traversals == 0

    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    raw = cast("dict[str, object]", payload["raw_input_result"])
    trap = _TraversalTrap()
    raw["request"] = trap
    with pytest.raises(TypeError, match="exact string keys"):
        compute_proteoform_quality_metrics(payload)
    assert trap.traversals == 0


@pytest.mark.parametrize("mutation", ["empty", "missing_request"])
def test_malformed_raw_objects_validate_before_normalization(
    canonical_request: ComputeProteoformQualityMetricsRequest,
    mutation: str,
) -> None:
    payload = canonical_request.model_dump(mode="json", exclude_none=False)
    if mutation == "empty":
        payload["raw_input_result"] = {}
    else:
        raw = cast("dict[str, object]", payload["raw_input_result"])
        del raw["request"]
    payload["fact_ledger"] = {"role_facts": "ledger-field-canary"}
    serialized = canonical_json_bytes(payload)

    with pytest.raises(ValidationError) as captured:
        m0404_engine._validate_json_request(payload, serialized)

    detail = str(captured.value)
    assert "KeyError" not in detail
    assert "ledger-field-canary" not in detail


def test_recursive_materialization_rejects_nonstring_keys_in_dicts_and_models(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    materialized = m0404_engine._plain_value([canonical_request.context, ("sentinel",)])
    assert isinstance(materialized, list)
    assert isinstance(materialized[0], dict)
    assert materialized[1] == ("sentinel",)

    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    cast("dict[object, object]", payload)[1] = "forged"
    with pytest.raises(TypeError, match="exact string keys"):
        compute_proteoform_quality_metrics(payload)

    forged_context = canonical_request.context.model_copy(deep=True)
    storage = cast(
        "dict[object, object]",
        object.__getattribute__(forged_context, "__dict__"),
    )
    storage[1] = "forged"
    with pytest.raises(TypeError, match="exact string keys"):
        m0404_engine._plain_value(forged_context)


def test_plain_materialization_bounds_hostile_depth_and_container_size(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    raw = cast("dict[str, object]", payload["raw_input_result"])
    nested: object = "leaf"
    for _ in range(70):
        nested = {"nested": nested}
    raw["request"] = nested
    with pytest.raises(TypeError, match="exact string keys"):
        compute_proteoform_quality_metrics(payload)

    with pytest.raises(TypeError, match="exact string keys"):
        m0404_engine._plain_value({str(index): index for index in range(513)})
    with pytest.raises(TypeError, match="exact string keys"):
        m0404_engine._plain_value(["item"] * 250_001)


def test_preflight_sanitizes_exception_but_propagates_baseexception(
    canonical_request: ComputeProteoformQualityMetricsRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_exception(_candidate: object, _field: str) -> NoReturn:
        raise _PrivateCallerError

    monkeypatch.setattr(m0404_engine, "_member", raise_exception)
    with pytest.raises(ProteoformQualityAuthorizationError) as captured:
        compute_proteoform_quality_metrics(canonical_request)
    assert "private caller" not in str(captured.value)

    def raise_baseexception(_candidate: object, _field: str) -> NoReturn:
        raise _PreflightBaseException

    monkeypatch.setattr(m0404_engine, "_member", raise_baseexception)
    with pytest.raises(_PreflightBaseException):
        compute_proteoform_quality_metrics(canonical_request)


@pytest.mark.parametrize(
    ("case_id", "upstream_disposition", "result_disposition", "finding"),
    [
        (
            "specimen_subject_swap",
            ProteoformRawInputDisposition.QUARANTINED,
            ProteoformQualityDisposition.QUARANTINED,
            ProteoformQualityFindingCode.UPSTREAM_RAW_INPUTS_QUARANTINED,
        ),
        (
            "missing_abstains",
            ProteoformRawInputDisposition.ABSTAINED,
            ProteoformQualityDisposition.ABSTAINED,
            ProteoformQualityFindingCode.UPSTREAM_RAW_INPUTS_ABSTAINED,
        ),
    ],
)
def test_genuine_nonvalidated_upstream_is_typed_and_never_traverses_a_ledger(
    canonical_request: ComputeProteoformQualityMetricsRequest,
    case_id: str,
    upstream_disposition: ProteoformRawInputDisposition,
    result_disposition: ProteoformQualityDisposition,
    finding: ProteoformQualityFindingCode,
) -> None:
    request = _safe_quality_request(canonical_request, case_id)
    assert request.raw_input_result.disposition is upstream_disposition
    result = compute_proteoform_quality_metrics(request)
    assert result.assay_quality == ()
    assert result.disposition is result_disposition
    assert tuple(item.code for item in result.findings) == (finding,)

    payload = request.model_dump(mode="python", exclude_none=False)
    trap = _TraversalTrap()
    payload["fact_ledger"] = trap
    with pytest.raises(ValueError, match="prohibits fact-ledger traversal"):
        compute_proteoform_quality_metrics(payload)
    assert trap.traversals == 0


def test_semantic_ledger_binding_mismatch_has_zero_partial_metrics(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    assert canonical_request.fact_ledger is not None
    payload = canonical_request.fact_ledger.model_dump(mode="python", exclude_none=False)
    payload["raw_input_result_digest"] = "sha256:" + ("f" * 64)
    payload["ledger_digest"] = "sha256:" + ("0" * 64)
    payload["ledger_digest"] = fact_ledger_digest(payload)
    ledger = ProteoformQualityFactLedger.model_validate(payload, strict=True)
    request = canonical_request.model_copy(update={"fact_ledger": ledger})

    result = compute_proteoform_quality_metrics(request)
    assert result.assay_quality == ()
    assert tuple(item.code for item in result.findings) == (
        ProteoformQualityFindingCode.FACT_LEDGER_BINDING_MISMATCH,
    )
    assert result.disposition is ProteoformQualityDisposition.QUARANTINED


def test_forged_validated_upstream_is_rejected_before_ledger_traversal(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    raw = cast("dict[str, object]", payload["raw_input_result"])
    raw["result_digest"] = "sha256:" + ("f" * 64)
    ledger = _TraversalTrap()
    payload["fact_ledger"] = ledger

    with pytest.raises(ValidationError):
        compute_proteoform_quality_metrics(payload)
    assert ledger.traversals == 0


def test_sealed_capabilities_are_nominal_and_candidate_bound(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    raw_capability = _issue_raw_input_replay_capability(canonical_request)
    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    raw = cast("dict[str, object]", payload["raw_input_result"])
    raw["result_digest"] = "sha256:" + ("f" * 64)
    with pytest.raises(TypeError, match="mismatched"):
        _validate_request_with_raw_capability(payload, raw_capability)

    request_capability = m0404_engine._validated_request_capability(canonical_request)
    result = compute_proteoform_quality_metrics(canonical_request)
    forged_request = request_capability.request.model_copy(
        update={"supersedes_result_digest": "sha256:" + ("f" * 64)}
    )
    forged_result = result.model_copy(update={"request": forged_request})
    with pytest.raises(ValidationError):
        _validate_result_with_capability(forged_result, request_capability)


def test_round_half_up_precedes_threshold_classification(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    role = ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME
    result = compute_proteoform_quality_metrics(canonical_request)
    metric = _metric(result, role, ProteoformQualityMetricCode.RAW_INPUT_COMPLETENESS)
    assert (metric.numerator, metric.denominator, metric.value_ppm) == (2, 3, 666_667)
    assert metric.status is ProteoformQualityMetricStatus.PASS


def test_zero_denominator_remains_not_evaluable_and_abstains(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    role = ProteoformRawInputRole.GENOME
    counts = _counts(
        canonical_request,
        role,
        cross_input_applicable_count=0,
        cross_input_coherent_count=0,
    )
    request = _with_role_fact(canonical_request, role, counts=counts)
    result = compute_proteoform_quality_metrics(request)
    metric = _metric(result, role, ProteoformQualityMetricCode.CROSS_INPUT_CONSISTENCY)

    assert (metric.numerator, metric.denominator, metric.value_ppm) == (0, 0, None)
    assert metric.status is ProteoformQualityMetricStatus.NOT_EVALUABLE
    assert result.disposition is ProteoformQualityDisposition.ABSTAINED
    assert ProteoformQualityFindingCode.REQUIRED_METRIC_NOT_EVALUABLE in {
        item.code for item in result.findings
    }


def test_censored_detection_retains_ratio_and_positive_censored_count(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    role = ProteoformRawInputRole.TRANSCRIPTOME
    counts = _counts(
        canonical_request,
        role,
        detection_eligible_count=3,
        above_detection_limit_count=2,
        below_detection_limit_count=1,
    )
    states = _states(
        canonical_request,
        role,
        detection_limit_burden=ProteoformQualityObservationState.CENSORED,
    )
    request = _with_role_fact(canonical_request, role, counts=counts, states=states)
    result = compute_proteoform_quality_metrics(request)
    metric = _metric(result, role, ProteoformQualityMetricCode.DETECTION_LIMIT_BURDEN)

    assert metric.observation_state is ProteoformQualityObservationState.CENSORED
    assert (metric.numerator, metric.denominator, metric.value_ppm) == (1, 3, 333_333)
    assert metric.censored_count == 1
    assert metric.status is ProteoformQualityMetricStatus.WARNING
    assert result.disposition is ProteoformQualityDisposition.QUARANTINED


def test_required_warning_quarantines_without_dropping_role_metrics(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    role = ProteoformRawInputRole.PTM_ANNOTATIONS
    counts = _counts(
        canonical_request,
        role,
        declared_record_count=4,
        parsed_record_count=2,
        valid_record_count=2,
    )
    request = _with_role_fact(canonical_request, role, counts=counts)
    result = compute_proteoform_quality_metrics(request)
    metric = _metric(result, role, ProteoformQualityMetricCode.RAW_INPUT_COMPLETENESS)

    assert metric.value_ppm == _WARNING_PPM
    assert metric.status is ProteoformQualityMetricStatus.WARNING
    assert result.disposition is ProteoformQualityDisposition.QUARANTINED
    assert sum(len(item.metrics) for item in result.assay_quality) == M0404_COMPUTED_METRIC_COUNT


def test_full_upstream_and_final_result_replay_reject_resigned_forgery(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    request_payload = canonical_request.model_dump(mode="python", exclude_none=False)
    raw = cast("dict[str, Any]", request_payload["raw_input_result"])
    cast("dict[str, object]", raw["support"])["rationale"] = "resigned upstream forgery"
    raw["result_digest"] = m0403_result_payload_digest(raw)
    with pytest.raises(ValidationError):
        compute_proteoform_quality_metrics(request_payload)

    result = compute_proteoform_quality_metrics(canonical_request)
    result_payload = result.model_dump(mode="python", exclude_none=False)
    cast("dict[str, object]", result_payload["support"])["rationale"] = "resigned result forgery"
    result_payload["result_digest"] = result_payload_digest(result_payload)
    with pytest.raises(ValidationError):
        ProteoformQualityResult.model_validate(result_payload, strict=True)


def test_plugin_rejects_duplicate_unknown_coercion_and_request_cap(
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    plugin = M0404Plugin(M0404Service())
    rendered = canonical_json_bytes(canonical_request.model_dump(mode="json"))
    duplicate = rendered.replace(
        b'"operation":"compute_proteoform_quality_metrics"',
        (
            b'"operation":"compute_proteoform_quality_metrics",'
            b'"operation":"compute_proteoform_quality_metrics"'
        ),
        1,
    )
    unknown = canonical_request.model_dump(mode="json", exclude_none=False)
    unknown["unexpected"] = True
    coercion = canonical_request.model_dump(mode="json", exclude_none=False)
    coercion["contract_version"] = 1
    for malformed in (duplicate, canonical_json_bytes(unknown), canonical_json_bytes(coercion)):
        with pytest.raises((ValueError, ValidationError)):
            plugin.validate(malformed)

    exact = rendered + (b" " * (M0404_MAX_CANONICAL_REQUEST_BYTES - len(rendered)))
    assert plugin.validate(exact).request == canonical_request
    with pytest.raises(ValueError, match="exceeds the byte limit"):
        plugin.validate(exact + b" ")
