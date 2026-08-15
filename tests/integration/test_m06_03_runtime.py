"""Runtime, replay, and sealing checks for provisional M06-03."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

import pytest
from evals.m06_03.run import build_scenario

from glio_proteogen.contracts.m06_03 import BaselineResultStatus
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator import (
    M0603MatureBaselineEngine,
    M0603Plugin,
    M0603Service,
    estimate_protein_abundance_baseline,
)
from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator.engine import (
    PtmBaselineAuthorizationError,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m06_03 import EstimateProteinAbundanceBaselineRequest

pytestmark = pytest.mark.integration


def _request(case_id: str = "clear") -> EstimateProteinAbundanceBaselineRequest:
    return build_scenario(case_id).request


def test_clear_request_emits_scalar_interval_and_categorical_estimates() -> None:
    result = estimate_protein_abundance_baseline(_request())

    assert result.status is BaselineResultStatus.ESTIMATED
    assert tuple(item.kind.value for item in result.estimates) == (
        "scalar",
        "interval",
        "categorical",
    )
    assert result.abstention_reason is None
    assert result.emits_parent is False


def test_missing_formal_state_abstains_without_partial_estimates() -> None:
    result = M0603MatureBaselineEngine().estimate(_request("missing"))

    assert result.status is BaselineResultStatus.ABSTAINED
    assert result.estimates == ()
    assert result.abstention_reason == "formal-state feature is missing or unsupported"


def test_upstream_non_valid_result_abstains_before_kernel() -> None:
    result = M0603MatureBaselineEngine().estimate(_request("upstream-abstained"))

    assert result.status is BaselineResultStatus.ABSTAINED
    assert result.estimates == ()
    assert result.diagnostics[0].status.value == "not_evaluable"


def test_service_and_engine_are_exactly_equal() -> None:
    request = _request()
    assert M0603Service()._execute_validated(request) == M0603MatureBaselineEngine().estimate(
        request
    )


def test_plugin_typed_and_canonical_json_validation_are_equal() -> None:
    request = _request()
    plugin = M0603Plugin(M0603Service())
    payload = canonical_json_bytes(request.model_dump(mode="json"))

    typed_result = plugin.run(plugin.validate(request))
    json_result = plugin.run(plugin.validate(payload))

    assert typed_result == json_result
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M06-03"


def test_plugin_rejects_forged_execution_token() -> None:
    plugin = M0603Plugin(M0603Service())
    token = plugin.validate(_request())

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]

    assert plugin.run(token).status is BaselineResultStatus.ESTIMATED


def test_plugin_rejects_mutated_token_request() -> None:
    plugin = M0603Plugin(M0603Service())
    token = plugin.validate(_request())
    object.__setattr__(token, "request", _request("missing"))

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_stale_upstream_digest_is_rejected() -> None:
    request = _request()
    stale_upstream = request.formal_state_result.model_copy(
        update={"request_digest": "sha256:" + "0" * 64}
    )
    stale_request = request.model_copy(update={"formal_state_result": stale_upstream})

    with pytest.raises(ValueError, match="stale"):
        M0603MatureBaselineEngine().estimate_validated(stale_request)


def test_schema_replay_mismatch_is_rejected() -> None:
    request = _request()
    altered_schema = request.state_schema.model_copy(update={"schema_id": "schema.other"})

    with pytest.raises(ValueError, match="schema replay"):
        M0603MatureBaselineEngine().estimate_validated(
            request.model_copy(update={"state_schema": altered_schema})
        )


@pytest.mark.parametrize(
    "role",
    [
        "approved_configuration",
        "identity_lineage",
        "provenance",
        "consent",
        "quality",
        "support",
        "intended_use",
    ],
)
def test_each_control_denies_before_execution(role: str) -> None:
    request = _request()
    denied_context = copy.deepcopy(request.context)
    state = "unresolved" if role == "identity_lineage" else "rejected"
    if role == "consent":
        state = "denied"
    object.__setattr__(getattr(denied_context.references, role), "state", state)
    denied_request = request.model_copy(update={"context": denied_context})

    with pytest.raises(PtmBaselineAuthorizationError):
        M0603Service().validate_request(denied_request)
