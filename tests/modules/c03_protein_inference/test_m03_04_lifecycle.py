"""Focused M03-04 evidence-graph quality runtime lifecycle tests."""

from __future__ import annotations

from collections.abc import Iterator, Mapping

import pytest
from evals.m03_04.run import build_scenario_request

from glio_proteogen.contracts.m03_01 import ProteinInferenceApplicability
from glio_proteogen.contracts.m03_03 import ProteinInferenceAdmissionDisposition
from glio_proteogen.contracts.m03_04 import (
    M0304_MAX_CANONICAL_RESULT_BYTES,
    M0304_METRIC_COUNT,
    ComputeProteinInferenceQualityRequest,
    ProteinInferenceAssayQualityProfile,
    ProteinInferenceQualityCounts,
    ProteinInferenceQualityDisposition,
    ProteinInferenceQualityFactLedger,
    ProteinInferenceQualityFactStates,
    ProteinInferenceQualityFindingCode,
    ProteinInferenceQualityMetricCode,
    ProteinInferenceQualityMetricResult,
    ProteinInferenceQualityMetricStatus,
    ProteinInferenceQualityObservationState,
    ProteinInferenceQualityPolicy,
    ProteinInferenceQualityResult,
    ProteinInferenceQualityThreshold,
    ProteinInferenceRawQualityReceipt,
    configuration_digest,
    fact_ledger_digest,
    raw_quality_receipt_digest,
    result_payload_digest,
)
from glio_proteogen.contracts.m03_04 import v1 as m0304_contract
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ConsentState,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics import (
    M0304Plugin,
    M0304ProteinInferenceQualityEngine,
    M0304Service,
    ProteinInferenceQualityAuthorizationError,
    ValidatedM0304Request,
    compute_protein_inference_quality,
    preflight_protein_inference_quality_authorization,
)
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics import (
    engine as m0304_engine,
)
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics import (
    service as m0304_service,
)
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics.kernel import (
    compute_quality_metrics,
    matching_quality_profile,
    protein_inference_metric_facts,
    quality_ledger_bindings_close,
)

_EXPECTED_CENSORED_GROUPS = 4
_UNSET = object()


def test_result_ceiling_applies_after_canonicalization_to_every_ingress_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = compute_protein_inference_quality(build_scenario_request())
    result_size = len(canonical_json_bytes(result))
    assert result_size <= M0304_MAX_CANONICAL_RESULT_BYTES
    monkeypatch.setattr(m0304_service, "M0304_MAX_CANONICAL_RESULT_BYTES", result_size - 1)
    service = M0304Service()

    for value in (result, result.model_dump(mode="python")):
        with pytest.raises(ValueError, match="result exceeds its canonical byte limit"):
            service.verify(value)

    monkeypatch.setattr(m0304_contract, "M0304_MAX_CANONICAL_RESULT_BYTES", result_size - 1)
    with pytest.raises(ValueError, match="result exceeds its canonical byte limit"):
        type(result).model_validate_json(canonical_json_bytes(result), strict=True)


def test_canonical_quality_profile_is_exact_private_and_deterministic() -> None:
    request = build_scenario_request()
    first = compute_protein_inference_quality(request)
    second = M0304ProteinInferenceQualityEngine().compute(request)

    assert first == second
    assert first.disposition is ProteinInferenceQualityDisposition.QUALIFIED
    assert len(first.metrics) == M0304_METRIC_COUNT
    assert first.findings == ()
    assert first.support.status is SupportStatus.SUPPORTED
    by_code = {item.metric_code: item for item in first.metrics}
    expected_ppm = {
        ProteinInferenceQualityMetricCode.ADMITTED_SOURCE_COMPLETENESS: 1_000_000,
        ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE: 950_000,
        ProteinInferenceQualityMetricCode.PROTEIN_GROUP_AMBIGUITY_BURDEN: 100_000,
        ProteinInferenceQualityMetricCode.PROTEOFORM_DISCRIMINATION_COVERAGE: 750_000,
        ProteinInferenceQualityMetricCode.PROTEIN_GROUP_DETECTION_SUPPORT: 800_000,
        ProteinInferenceQualityMetricCode.PROTEIN_GROUP_COMPETITION_CLOSURE: 900_000,
        ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY: 900_000,
        ProteinInferenceQualityMetricCode.SAMPLE_CONTEXT_BINDING_COHERENCE: 1_000_000,
    }
    assert {code: item.value_ppm for code, item in by_code.items()} == expected_ppm
    detection = by_code[ProteinInferenceQualityMetricCode.PROTEIN_GROUP_DETECTION_SUPPORT]
    assert detection.observation_state is ProteinInferenceQualityObservationState.CENSORED
    assert detection.censored_count == _EXPECTED_CENSORED_GROUPS
    rendered = first.model_dump_json()
    assert "MPEPTIDEK" not in rendered
    assert "scan=1" not in rendered
    assert "group.synthetic.1" not in rendered
    assert first.emits_complex_activity is False
    assert first.infers_protein is False
    assert first.infers_kinase_activity is False


def test_semantic_reordering_preserves_complete_result_equality() -> None:
    request = build_scenario_request()
    receipt = request.raw_quality_receipt.model_copy(
        update={
            "sources": tuple(reversed(request.raw_quality_receipt.sources)),
            "claims": tuple(reversed(request.raw_quality_receipt.claims)),
        }
    )
    profile = request.policy.profiles[0].model_copy(
        update={"thresholds": tuple(reversed(request.policy.profiles[0].thresholds))}
    )
    policy = request.policy.model_copy(update={"profiles": (profile,)})
    reordered = request.model_copy(update={"raw_quality_receipt": receipt, "policy": policy})

    assert compute_protein_inference_quality(reordered) == (
        compute_protein_inference_quality(request)
    )


def test_superseding_recovery_binds_prior_result_in_provenance() -> None:
    request = build_scenario_request()
    prior = compute_protein_inference_quality(request)
    superseding_request = ComputeProteinInferenceQualityRequest(
        **{
            **request.model_dump(mode="python"),
            "supersedes_result_digest": prior.result_digest,
        }
    )

    recovered = compute_protein_inference_quality(superseding_request)

    assert recovered.request.supersedes_result_digest == prior.result_digest
    assert prior.result_digest in recovered.provenance.input_digests
    forged = recovered.model_dump(mode="python")
    forged["provenance"]["input_digests"] = tuple(
        digest for digest in forged["provenance"]["input_digests"] if digest != prior.result_digest
    )
    forged["result_digest"] = result_payload_digest(forged)
    with pytest.raises(ValueError, match="provenance does not close"):
        ProteinInferenceQualityResult.model_validate(forged, strict=True)


@pytest.mark.parametrize(
    ("coverage", "status", "finding"),
    [
        (
            60,
            ProteinInferenceQualityMetricStatus.WARNING,
            ProteinInferenceQualityFindingCode.REQUIRED_METRIC_WARNING,
        ),
        (
            40,
            ProteinInferenceQualityMetricStatus.FAIL,
            ProteinInferenceQualityFindingCode.METRIC_THRESHOLD_FAILED,
        ),
    ],
)
def test_required_threshold_warning_and_failure_quarantine(
    coverage: int,
    status: ProteinInferenceQualityMetricStatus,
    finding: ProteinInferenceQualityFindingCode,
) -> None:
    request = build_scenario_request()
    counts = _counts(
        request,
        unique_assigned_peptide_evidence_count=coverage,
        shared_group_assigned_peptide_evidence_count=0,
        unassigned_peptide_evidence_count=100 - coverage,
    )
    changed = _with_ledger(request, counts=counts)
    result = compute_protein_inference_quality(changed)
    metric = _metric(result, ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE)

    assert metric.value_ppm == coverage * 10_000
    assert metric.status is status
    assert result.disposition is ProteinInferenceQualityDisposition.QUARANTINED
    assert {item.code for item in result.findings} == {finding}


@pytest.mark.parametrize(
    ("ambiguous", "status"),
    [
        (25, ProteinInferenceQualityMetricStatus.WARNING),
        (40, ProteinInferenceQualityMetricStatus.FAIL),
    ],
)
def test_ambiguity_burden_uses_at_most_warning_and_failure_bands(
    ambiguous: int,
    status: ProteinInferenceQualityMetricStatus,
) -> None:
    request = build_scenario_request()
    counts = _counts(request, ambiguous_group_member_assignment_count=ambiguous)
    result = compute_protein_inference_quality(_with_ledger(request, counts=counts))
    metric = _metric(result, ProteinInferenceQualityMetricCode.PROTEIN_GROUP_AMBIGUITY_BURDEN)

    assert metric.value_ppm == ambiguous * 10_000
    assert metric.status is status
    assert result.disposition is ProteinInferenceQualityDisposition.QUARANTINED


@pytest.mark.parametrize(
    ("state", "finding"),
    [
        (
            ProteinInferenceQualityObservationState.MISSING,
            ProteinInferenceQualityFindingCode.REQUIRED_METRIC_MISSING,
        ),
        (
            ProteinInferenceQualityObservationState.OBSERVED,
            ProteinInferenceQualityFindingCode.REQUIRED_METRIC_NOT_EVALUABLE,
        ),
    ],
)
def test_missing_and_observed_zero_denominator_remain_distinct(
    state: ProteinInferenceQualityObservationState,
    finding: ProteinInferenceQualityFindingCode,
) -> None:
    request = build_scenario_request()
    counts = _counts(
        request,
        eligible_peptide_evidence_count=0,
        unique_assigned_peptide_evidence_count=0,
        shared_group_assigned_peptide_evidence_count=0,
        unassigned_peptide_evidence_count=0,
    )
    states = _states(request, peptide_assignment=state)
    result = compute_protein_inference_quality(_with_ledger(request, counts=counts, states=states))
    metric = _metric(result, ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE)

    assert metric.status is ProteinInferenceQualityMetricStatus.NOT_EVALUABLE
    assert metric.value_ppm is None
    if state is ProteinInferenceQualityObservationState.MISSING:
        assert metric.numerator is None
        assert metric.denominator is None
    else:
        assert metric.numerator == metric.denominator == 0
    assert result.disposition is ProteinInferenceQualityDisposition.ABSTAINED
    assert {item.code for item in result.findings} == {finding}


def test_not_applicable_control_is_qualified_only_for_profile_without_controls() -> None:
    request = build_scenario_request()
    counts = _counts(
        request,
        control_expected_group_count=0,
        control_recovered_group_count=0,
    )
    states = _states(
        request,
        control_recovery=ProteinInferenceQualityObservationState.NOT_APPLICABLE,
    )
    changed = _with_ledger(request, counts=counts, states=states)
    changed = _with_policy(changed, controls_applicable=False)
    result = compute_protein_inference_quality(changed)
    metric = _metric(result, ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY)

    assert metric.required is True
    assert metric.status is ProteinInferenceQualityMetricStatus.NOT_APPLICABLE
    assert result.findings == ()
    assert result.disposition is ProteinInferenceQualityDisposition.QUALIFIED


def test_binding_mismatch_and_unsupported_profile_never_compute_metrics() -> None:
    request = build_scenario_request()
    ledger = _ledger(
        request,
        admission_result_digest="sha256:" + ("a" * 64),
    )
    mismatch = _request(request, fact_ledger=ledger)
    mismatch_result = compute_protein_inference_quality(mismatch)

    assert mismatch_result.metrics == ()
    assert mismatch_result.disposition is ProteinInferenceQualityDisposition.QUARANTINED
    assert {item.code for item in mismatch_result.findings} == {
        ProteinInferenceQualityFindingCode.FACT_LEDGER_BINDING_MISMATCH
    }

    unsupported_ledger = _ledger(
        request,
        applicability=ProteinInferenceApplicability.DIA,
    )
    unsupported = _request(request, fact_ledger=unsupported_ledger)
    unsupported_result = compute_protein_inference_quality(unsupported)

    assert unsupported_result.metrics == ()
    assert unsupported_result.disposition is ProteinInferenceQualityDisposition.ABSTAINED
    assert {item.code for item in unsupported_result.findings} == {
        ProteinInferenceQualityFindingCode.ASSAY_PROFILE_UNSUPPORTED
    }


def test_upstream_rejection_and_policy_shape_abstention_are_typed_safe_failures() -> None:
    request = build_scenario_request()
    rejected_receipt = _receipt(
        request,
        upstream_disposition=ProteinInferenceAdmissionDisposition.REJECTED,
        upstream_support_status=SupportStatus.UNSUPPORTED,
        upstream_human_review_required=True,
        sources=(),
        claims=(),
    )
    rejected = _request(request, raw_quality_receipt=rejected_receipt, fact_ledger=None)
    assert matching_quality_profile(rejected) is None
    assert quality_ledger_bindings_close(rejected) is False
    assert protein_inference_metric_facts(rejected) == {}
    with pytest.raises(ValueError, match="fact ledger required"):
        compute_quality_metrics(rejected, rejected.policy.profiles[0])
    rejected_result = compute_protein_inference_quality(rejected)

    assert rejected_result.metrics == ()
    assert rejected_result.disposition is ProteinInferenceQualityDisposition.REJECTED
    assert {item.code for item in rejected_result.findings} == {
        ProteinInferenceQualityFindingCode.UPSTREAM_REJECTED
    }

    shaped = _with_policy(request, max_sources=12, fact_ledger=None)
    shaped_result = compute_protein_inference_quality(shaped)
    assert shaped_result.metrics == ()
    assert shaped_result.disposition is ProteinInferenceQualityDisposition.ABSTAINED
    assert {item.code for item in shaped_result.findings} == {
        ProteinInferenceQualityFindingCode.UPSTREAM_SHAPE_UNSUPPORTED
    }


@pytest.mark.parametrize(
    ("role", "state"),
    [
        ("approved_configuration", UpstreamDecisionState.REJECTED),
        ("identity_lineage", IdentityLineageState.CONFLICTED),
        ("provenance", UpstreamDecisionState.REJECTED),
        ("consent", ConsentState.REVOKED),
        ("quality", UpstreamDecisionState.REJECTED),
        ("support", UpstreamDecisionState.REJECTED),
        ("intended_use", UpstreamDecisionState.REJECTED),
    ],
)
def test_all_seven_control_denials_precede_fact_ledger_validation(
    role: str,
    state: object,
) -> None:
    request = build_scenario_request().model_dump(mode="python")
    request["context"]["references"][role]["state"] = state
    request["fact_ledger"] = _ExplodingLedger()

    with pytest.raises(ProteinInferenceQualityAuthorizationError):
        compute_protein_inference_quality(request)


class _ProtectedTraversal(BaseException):
    pass


class _HostileMapping(Mapping[str, object]):
    def __getitem__(self, _key: str) -> object:
        raise _HostileAccessorError

    def __iter__(self) -> Iterator[str]:
        return iter(())

    def __len__(self) -> int:
        return 0


class _BaseExceptionMapping(_HostileMapping):
    def __getitem__(self, _key: str) -> object:
        raise _ProtectedTraversal


class _HostileAccessorError(OSError):
    def __init__(self) -> None:
        super().__init__("private hostile accessor detail")


class _ExplodingLedger:
    def __getattribute__(self, _name: str) -> object:
        raise _PrematureLedgerTraversalError


class _PrematureLedgerTraversalError(AssertionError):
    def __init__(self) -> None:
        super().__init__("fact ledger traversed before authorization")


def test_preflight_sanitizes_exception_but_never_base_exception() -> None:
    with pytest.raises(ProteinInferenceQualityAuthorizationError) as captured:
        preflight_protein_inference_quality_authorization(_HostileMapping())
    assert "private hostile" not in str(captured.value)
    with pytest.raises(_ProtectedTraversal):
        preflight_protein_inference_quality_authorization(_BaseExceptionMapping())


def test_authorized_dict_subclass_replays_without_accessor_dispatch() -> None:
    request = build_scenario_request()

    class HostileDict(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise AssertionError

        def __iter__(self) -> Iterator[str]:
            raise AssertionError

        def __getitem__(self, key: str) -> object:
            raise AssertionError(key)

    candidate = HostileDict(request.model_dump(mode="python"))
    assert compute_protein_inference_quality(candidate) == compute_protein_inference_quality(
        request
    )


def test_direct_python_quality_ingress_bounds_nested_and_sequence_graphs() -> None:
    payload = build_scenario_request().model_dump(mode="python")
    nested: object = "leaf"
    for _ in range(m0304_engine._MAX_PLAIN_DEPTH + 1):
        nested = {"nested": nested}
    payload["unexpected"] = nested

    with pytest.raises(TypeError, match="bounded built-in containers"):
        M0304Service.validate_request(payload)
    with pytest.raises(TypeError, match="bounded built-in containers"):
        compute_protein_inference_quality(payload)

    class HostileList(list[object]):
        def __iter__(self) -> Iterator[object]:
            raise AssertionError

        def __getitem__(self, key: int) -> object:  # type: ignore[override]
            raise AssertionError(key)

    oversized = build_scenario_request().model_dump(mode="python")
    oversized["unexpected"] = HostileList([None] * (m0304_engine._MAX_PLAIN_SEQUENCE_ITEMS + 1))
    with pytest.raises(TypeError, match="bounded built-in containers"):
        M0304Service.validate_request(oversized)


def test_quality_result_replay_bounds_caller_owned_graph() -> None:
    result = compute_protein_inference_quality(build_scenario_request())
    payload = result.model_dump(mode="python")
    nested: object = "leaf"
    for _ in range(m0304_engine._MAX_PLAIN_DEPTH + 1):
        nested = {"nested": nested}
    payload["unexpected"] = nested

    with pytest.raises(TypeError, match="bounded built-in containers"):
        M0304Service().verify(payload)


def test_plugin_typed_and_strict_json_paths_match_and_reject_forged_capability() -> None:
    request = build_scenario_request()
    plugin = M0304Plugin(M0304Service())
    typed_token = plugin.validate(request)
    json_token = plugin.validate(canonical_json_bytes(request.model_dump(mode="json")))

    assert isinstance(typed_token, ValidatedM0304Request)
    assert plugin.run(typed_token) == plugin.run(json_token)
    assert plugin.descriptor().owner == "Clinical science"
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(request)  # type: ignore[arg-type]


def _metric(
    result: ProteinInferenceQualityResult,
    code: ProteinInferenceQualityMetricCode,
) -> ProteinInferenceQualityMetricResult:
    return next(item for item in result.metrics if item.metric_code is code)


def _counts(
    request: ComputeProteinInferenceQualityRequest,
    **updates: int,
) -> ProteinInferenceQualityCounts:
    assert request.fact_ledger is not None
    payload = request.fact_ledger.counts.model_dump(mode="python")
    payload.update(updates)
    return ProteinInferenceQualityCounts.model_validate(payload, strict=True)


def _states(
    request: ComputeProteinInferenceQualityRequest,
    **updates: ProteinInferenceQualityObservationState,
) -> ProteinInferenceQualityFactStates:
    assert request.fact_ledger is not None
    payload = request.fact_ledger.states.model_dump(mode="python")
    payload.update(updates)
    return ProteinInferenceQualityFactStates.model_validate(payload, strict=True)


def _ledger(
    request: ComputeProteinInferenceQualityRequest,
    **updates: object,
) -> ProteinInferenceQualityFactLedger:
    assert request.fact_ledger is not None
    payload = request.fact_ledger.model_dump(mode="python")
    payload.update(updates)
    payload["ledger_digest"] = fact_ledger_digest(payload)
    return ProteinInferenceQualityFactLedger.model_validate(payload, strict=True)


def _with_ledger(
    request: ComputeProteinInferenceQualityRequest,
    *,
    counts: ProteinInferenceQualityCounts | None = None,
    states: ProteinInferenceQualityFactStates | None = None,
) -> ComputeProteinInferenceQualityRequest:
    updates = {key: value for key, value in {"counts": counts, "states": states}.items() if value}
    return _request(request, fact_ledger=_ledger(request, **updates))


def _receipt(
    request: ComputeProteinInferenceQualityRequest,
    **updates: object,
) -> ProteinInferenceRawQualityReceipt:
    payload = request.raw_quality_receipt.model_dump(mode="python")
    payload.update(updates)
    payload["receipt_digest"] = raw_quality_receipt_digest(payload)
    return ProteinInferenceRawQualityReceipt.model_validate(payload, strict=True)


def _with_policy(
    request: ComputeProteinInferenceQualityRequest,
    *,
    controls_applicable: bool | None = None,
    max_sources: int | None = None,
    fact_ledger: ProteinInferenceQualityFactLedger | object | None = _UNSET,
) -> ComputeProteinInferenceQualityRequest:
    original_profile = request.policy.profiles[0]
    profile_payload = original_profile.model_dump(mode="python")
    if controls_applicable is not None:
        profile_payload["controls_applicable"] = controls_applicable
    profile_payload["thresholds"] = tuple(
        ProteinInferenceQualityThreshold.model_validate(item, strict=True)
        for item in profile_payload["thresholds"]
    )
    profile = ProteinInferenceAssayQualityProfile.model_validate(profile_payload, strict=True)
    policy_payload = request.policy.model_dump(mode="python")
    policy_payload["profiles"] = (profile,)
    if max_sources is not None:
        policy_payload["max_sources"] = max_sources
    policy = ProteinInferenceQualityPolicy.model_validate(policy_payload, strict=True)
    approved = request.context.references.approved_configuration
    references = request.context.references.model_copy(
        update={
            "approved_configuration": approved.model_copy(
                update={
                    "evidence": approved.evidence.model_copy(
                        update={"digest": configuration_digest(policy)}
                    )
                }
            )
        }
    )
    context = request.context.model_copy(update={"references": references})
    selected_ledger = request.fact_ledger if fact_ledger is _UNSET else fact_ledger
    return _request(
        request,
        context=context,
        policy=policy,
        fact_ledger=selected_ledger,
    )


def _request(
    request: ComputeProteinInferenceQualityRequest,
    **updates: object,
) -> ComputeProteinInferenceQualityRequest:
    payload = request.model_dump(mode="python")
    payload.update(updates)
    return ComputeProteinInferenceQualityRequest.model_validate(payload, strict=True)
