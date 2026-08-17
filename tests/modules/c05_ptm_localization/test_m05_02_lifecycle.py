"""Lifecycle, firewall, and replay tests for GLIO-PROTEOGEN-M05-02."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, cast

import pytest
from evals.m05_02.benchmark import MEAN_BUDGET_NS, P95_BUDGET_NS, run_benchmark
from evals.m05_02.run import (
    build_scenario_request,
    build_scenario_result,
    run_evaluation,
)
from pydantic import ValidationError

from glio_proteogen.contracts.m05_02 import (
    M0502_MAX_ARTIFACT_CLAIMS,
    M0502_MAX_CANONICAL_REQUEST_BYTES,
    M0502_MAX_DERIVATION_SOURCES,
    M0502_MIN_DERIVATION_SOURCES,
    M0502_PHYSICAL_ENTITY_KIND_COUNT,
    PtmLocalizationIdentityLineageFindingCode,
    PtmLocalizationIdentityLineageResolution,
    PtmLocalizationLineageDisposition,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c05_ptm_localization.m05_02_identity_lineage import (
    M0502Plugin,
    M0502Service,
    PtmLocalizationIdentityLineageAuthorizationError,
    PtmLocalizationIdentityLineageInputError,
    ValidatedM0502Request,
    reconcile_ptm_localization_identity_lineage,
)
from glio_proteogen.modules.c05_ptm_localization.m05_02_identity_lineage import (
    plugin as m0502_plugin,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class _TraversalCanary:
    def __iter__(self) -> object:
        raise AssertionError


_EXPECTED_ARTIFACT_COUNT = 5
_EXPECTED_GROUP_COUNT = 8
_EXPECTED_CASE_COUNT = 70


def test_canonical_result_is_replayable_immutable_and_scope_closed() -> None:
    request = build_scenario_request()
    first = reconcile_ptm_localization_identity_lineage(request)
    second = reconcile_ptm_localization_identity_lineage(request)

    assert first == second
    assert first.disposition is PtmLocalizationLineageDisposition.RECONCILED
    assert len(first.graph.artifacts) == _EXPECTED_ARTIFACT_COUNT
    assert not first.findings
    assert first.request_digest == second.request_digest
    assert first.result_digest == second.result_digest
    assert first.parent_target == "variant_peptide"
    assert not any(
        (
            first.emits_variant_peptide,
            first.emits_proteogenomic_state,
            first.emits_proteotype,
            first.emits_protein_level_subtype,
            first.infers_identity,
            first.infers_consent,
            first.infers_protein,
            first.infers_ptm_localization,
            first.infers_kinase_activity,
            first.performs_cn_to_protein_regression,
            first.performs_all_omics_fusion,
            first.recommends_treatment,
            first.mutates_upstream,
        )
    )
    with pytest.raises(ValidationError):
        first.disposition = PtmLocalizationLineageDisposition.ABSTAINED  # type: ignore[misc]


@pytest.mark.parametrize(
    ("scenario", "disposition", "code"),
    [
        (
            "unsupported_configuration_abstained",
            PtmLocalizationLineageDisposition.ABSTAINED,
            PtmLocalizationIdentityLineageFindingCode.UPSTREAM_CONFIGURATION_UNSUPPORTED,
        ),
        (
            "upstream_protocol_quarantined",
            PtmLocalizationLineageDisposition.QUARANTINED,
            PtmLocalizationIdentityLineageFindingCode.UPSTREAM_PROTOCOL_NONCONFORMANT,
        ),
    ],
)
def test_nontraversable_upstream_emits_typed_empty_safe_failure(
    scenario: str,
    disposition: PtmLocalizationLineageDisposition,
    code: PtmLocalizationIdentityLineageFindingCode,
) -> None:
    result = build_scenario_result(scenario)

    assert result.disposition is disposition
    assert not result.graph.artifacts
    assert not result.graph.derivations
    assert tuple(item.code for item in result.findings) == (code,)
    assert result.human_review_required


def test_unsupported_configuration_does_not_traverse_supplied_claim_region() -> None:
    payload = build_scenario_request("unsupported_configuration_abstained").model_dump(
        mode="python", exclude_none=False
    )
    payload["artifact_claims"] = _TraversalCanary()
    payload["derivations"] = _TraversalCanary()

    result = M0502Service().execute(payload)

    assert result.disposition is PtmLocalizationLineageDisposition.ABSTAINED
    assert not result.request.artifact_claims


def test_authorization_fails_before_hostile_claim_region() -> None:
    payload = build_scenario_request().model_dump(mode="python", exclude_none=False)
    payload["context"]["references"]["consent"]["state"] = "denied"
    payload["artifact_claims"] = _TraversalCanary()

    with pytest.raises(PtmLocalizationIdentityLineageAuthorizationError):
        M0502Service().execute(payload)


def test_supported_request_rejects_non_builtin_claim_region_without_reflection() -> None:
    payload = build_scenario_request().model_dump(mode="python", exclude_none=False)
    payload["artifact_claims"] = _TraversalCanary()

    with pytest.raises(PtmLocalizationIdentityLineageInputError) as captured:
        M0502Service().execute(payload)

    assert "artifact region" not in str(captured.value)


def test_plugin_typed_and_canonical_json_paths_are_byte_semantically_equal() -> None:
    request = build_scenario_request()
    plugin = M0502Plugin(M0502Service())

    typed = plugin.run(plugin.validate(request))
    serialized = plugin.run(plugin.validate(canonical_json_bytes(request)))

    assert canonical_json_bytes(typed) == canonical_json_bytes(serialized)


def test_plugin_json_is_decoded_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    original = cast("Callable[..., object]", m0502_plugin.__dict__["_strict_json_loads"])

    def counted(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(m0502_plugin, "_strict_json_loads", counted)
    M0502Plugin(M0502Service()).validate(canonical_json_bytes(build_scenario_request()))

    assert calls == 1


def test_plugin_rejects_duplicate_unknown_and_coerced_json() -> None:
    plugin = M0502Plugin(M0502Service())
    request = canonical_json_bytes(build_scenario_request())

    duplicate = request.replace(
        b'"operation":"reconcile_ptm_localization_identity_lineage"',
        (
            b'"operation":"reconcile_ptm_localization_identity_lineage",'
            b'"operation":"reconcile_ptm_localization_identity_lineage"'
        ),
        1,
    )
    with pytest.raises(StrictJsonError):
        plugin.validate(duplicate)

    unknown = copy.deepcopy(build_scenario_request().model_dump(mode="json", exclude_none=False))
    unknown["recursive_canary"] = "secret"
    with pytest.raises(PtmLocalizationIdentityLineageInputError):
        plugin.validate(canonical_json_bytes(unknown))

    coerced = copy.deepcopy(build_scenario_request().model_dump(mode="json", exclude_none=False))
    coerced["policy"]["max_artifact_claims"] = "16"
    with pytest.raises(PtmLocalizationIdentityLineageInputError):
        plugin.validate(canonical_json_bytes(coerced))


def test_plugin_rejects_copied_seal_and_mutated_issued_token() -> None:
    plugin = M0502Plugin(M0502Service())
    token = plugin.validate(build_scenario_request())
    forged_request = token.request.model_copy(update={"request_id": f"request.{'f' * 64}"})
    copied = ValidatedM0502Request(request=forged_request, _seal=token._seal)

    with pytest.raises(TypeError):
        plugin.run(copied)

    object.__setattr__(token, "request", forged_request)
    with pytest.raises(TypeError):
        plugin.run(token)


def test_stale_upstream_digest_and_resigned_result_forgery_fail_replay() -> None:
    request_payload = build_scenario_request().model_dump(mode="python", exclude_none=False)
    request_payload["protocol_result"]["status"] = "nonconformant"
    with pytest.raises(PtmLocalizationIdentityLineageInputError):
        M0502Service().execute(request_payload)

    result_payload = build_scenario_result().model_dump(mode="python", exclude_none=False)
    result_payload["disposition"] = PtmLocalizationLineageDisposition.ABSTAINED
    result_payload["result_digest"] = result_payload_digest(result_payload)
    with pytest.raises(ValidationError):
        PtmLocalizationIdentityLineageResolution.model_validate(result_payload, strict=True)


def test_maximum_admitted_shape_is_total_and_within_the_request_cap() -> None:
    request = build_scenario_request("maximum_admitted_shape_quarantined")
    result = reconcile_ptm_localization_identity_lineage(request)

    assert len(request.artifact_claims) == M0502_MAX_ARTIFACT_CLAIMS
    assert len(request.derivations) == 1
    assert len(request.derivations[0].source_claim_ids) == M0502_MAX_DERIVATION_SOURCES
    assert len(result.graph.artifacts) == M0502_MAX_ARTIFACT_CLAIMS
    assert result.disposition is PtmLocalizationLineageDisposition.QUARANTINED
    assert len(canonical_json_bytes(request)) <= M0502_MAX_CANONICAL_REQUEST_BYTES


def test_one_iteration_benchmark_smoke_locks_public_shape_and_budgets() -> None:
    report = run_benchmark(1)

    assert report.physical_entity_kind_count == M0502_PHYSICAL_ENTITY_KIND_COUNT
    assert report.artifact_role_count == report.artifact_claim_count == _EXPECTED_ARTIFACT_COUNT
    assert report.derivation_count == 1
    assert report.derivation_source_count == M0502_MIN_DERIVATION_SOURCES
    assert report.finding_count == 0
    assert report.warmup_count == 1
    assert report.mean_budget_ns == MEAN_BUDGET_NS
    assert report.p95_budget_ns == P95_BUDGET_NS
    assert report.timed_boundary == "reconcile_ptm_localization_identity_lineage_only"


def test_locked_evaluation_executes_all_seventy_unique_cases() -> None:
    report = run_evaluation()

    assert report.passed is True
    assert report.declared_groups == _EXPECTED_GROUP_COUNT
    assert (
        report.declared_cases
        == report.executed_cases
        == report.passed_cases
        == _EXPECTED_CASE_COUNT
    )
    assert report.failed_cases == ()
    assert sum(report.group_case_counts.values()) == _EXPECTED_CASE_COUNT
