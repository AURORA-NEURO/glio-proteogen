from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

import glio_proteogen.research.longitudinal_gbm_reactome_transition.demo as demo_module
import glio_proteogen.research.longitudinal_gbm_reactome_transition.profile as profile_module
import glio_proteogen.research.longitudinal_gbm_reactome_transition.service as service_module
from glio_proteogen.research.longitudinal_gbm_reactome_transition.canonical import (
    profile_payload_digest,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.contracts import (
    LongitudinalGbmReactomeTransitionProfile,
    LongitudinalGbmReactomeTransitionRequest,
    LongitudinalGbmReactomeTransitionResult,
    ReactomeConditionalReplayVerificationRequest,
    UnverifiedLongitudinalGbmReactomeTransitionResult,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.demo import (
    DEMO_ID,
    EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST,
    demo_request_digest,
    synthetic_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.errors import (
    ReactomeConditionalModelIntegrityError,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.fitted_catalog import (
    reactome_conditional_fitted_catalog,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.profile import (
    EXPECTED_NUMPY_VERSION,
    algorithm_profile,
    engine_semantic_digest,
    input_contract_schema_digest,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.service import (
    LongitudinalGbmReactomeTransitionService,
    analyze_longitudinal_gbm_reactome_transition,
    verify_longitudinal_gbm_reactome_transition_replay,
    verify_replay,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
)
from tests.research.test_kncc_reactome_transition_contracts import (
    DIGEST,
    OTHER_DIGEST,
    result,
)


def test_profile_binds_fitted_source_solver_demo_and_modest_evaluation() -> None:
    profile = algorithm_profile()
    fitted = reactome_conditional_fitted_catalog()
    assert profile.profile_digest == profile_payload_digest(profile)
    assert profile.profile_id == fitted.profile_id
    assert profile.model_id == fitted.model_id
    assert profile.numpy_version == EXPECTED_NUMPY_VERSION
    assert profile.demo_id == DEMO_ID
    assert profile.demo_request_digest == demo_request_digest()
    assert profile.demo_semantic_oracle_digest == EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST
    assert profile.digests.engine_semantic_digest == engine_semantic_digest()
    assert profile.digests.input_contract_schema_digest == input_contract_schema_digest()
    assert profile.digests.centering_scaling_digest == fitted.centering_scaling_digest
    assert profile.digests.union_feature_digest == fitted.union_feature_digest
    assert profile.digests.reference_tensor_digest == fitted.reference_tensor_digest
    assert profile.digests.reference_design_digest == fitted.reference_design_digest
    assert profile.digests.global_loading_digest == fitted.global_loading_digest
    assert profile.digests.conditional_loading_digest == fitted.conditional_loading_digest
    assert profile.digests.fold_policy_digest == fitted.fold_policy_digest
    assert profile.digests.evaluation_digest == fitted.evaluation_digest
    assert profile.counts.outer_fold_count == 8
    assert profile.counts.gene_fold_count == 5
    assert profile.constants.solver_max_iterations == 200
    assert profile.constants.solver_tolerance == 1e-9
    assert profile.constants.stable_threshold == 0.25
    assert profile.constants.default_bootstrap_replicates == 64
    assert profile.constants.maximum_bootstrap_replicates == 256
    assert profile.evaluation.patient_count == 104
    assert profile.evaluation.evaluation_count == 520
    assert profile.evaluation.all_primary_solver_fits_converged
    assert profile.evaluation.all_leave_pathway_q05_q95_intervals_cross_zero
    assert profile.evaluation.minimum_outer_loading_cosine == pytest.approx(0.9851914172)
    assert tuple(pathway.panel_index for pathway in profile.pathways) == tuple(range(10))
    assert profile.pathways[2].overlap_confounded


def test_profile_rejects_runtime_and_artifact_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fitted = reactome_conditional_fitted_catalog()
    monkeypatch.setattr(profile_module.np, "__version__", "0.0")
    with pytest.raises(RuntimeError, match="requires NumPy"):
        algorithm_profile()
    monkeypatch.setattr(profile_module.np, "__version__", EXPECTED_NUMPY_VERSION)
    for field, value, message in (
        ("numpy_version", "0.0", "NumPy version"),
        ("profile_id", "wrong-profile", "profile identifier"),
        ("model_id", "wrong-model", "model identifier"),
    ):
        drifted = replace(fitted, **{field: value})
        monkeypatch.setattr(
            profile_module,
            "reactome_conditional_fitted_catalog",
            lambda drifted=drifted: drifted,
        )
        with pytest.raises(RuntimeError, match=message):
            algorithm_profile()


def test_profile_evaluation_parser_rejects_malformed_shapes_and_types() -> None:
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="not an object"):
        profile_module._mapping([], "field")
    with pytest.raises(ReactomeConditionalModelIntegrityError, match="not an array"):
        profile_module._sequence({}, "field")
    with pytest.raises(RuntimeError, match="not an integer"):
        profile_module._integer(1.0, "field")
    with pytest.raises(RuntimeError, match="not numeric"):
        profile_module._number("1", "field")
    assert profile_module._canonical_python_ast(b"x=1\r\n") == (
        profile_module._canonical_python_ast(b"x=1\n")
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "patient_cluster_median_improvement_90_interval",
            (0.1,),
            "two bounds",
        ),
        ("outer_loading_cosine_minima", (0.99,) * 10, "11 entries"),
    ],
)
def test_profile_evaluation_summary_rejects_inventory_drift(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
    message: str,
) -> None:
    fitted = reactome_conditional_fitted_catalog()
    evaluation = dict(fitted.evaluation)
    evaluation[field] = value
    drifted = replace(fitted, evaluation=evaluation)
    monkeypatch.setattr(
        profile_module,
        "reactome_conditional_fitted_catalog",
        lambda: drifted,
    )
    with pytest.raises(RuntimeError, match=message):
        profile_module._evaluation_summary()


def test_profile_contract_rejects_pathway_order_and_digest_forgery() -> None:
    profile = algorithm_profile()
    document = profile.model_dump(mode="python")
    document["pathways"] = tuple(reversed(document["pathways"]))
    with pytest.raises(ValidationError, match="complete fixed pathway order"):
        LongitudinalGbmReactomeTransitionProfile.model_validate(document, strict=True)
    document = profile.model_dump(mode="python")
    document["profile_digest"] = OTHER_DIGEST
    with pytest.raises(ValidationError, match="canonical profile content"):
        LongitudinalGbmReactomeTransitionProfile.model_validate(document, strict=True)


def test_demo_rejects_an_empty_or_oversized_feature_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty_catalog = SimpleNamespace(pathways=(), genes=())
    monkeypatch.setattr(
        demo_module,
        "reactome_transition_source_catalog",
        lambda: empty_catalog,
    )
    with pytest.raises(RuntimeError, match="outside its bound"):
        demo_module._demo_feature_indices()
    assert synthetic_demo_request().request_digest == demo_request_digest()


def _install_engine_stub(
    monkeypatch: pytest.MonkeyPatch,
    expected: LongitudinalGbmReactomeTransitionResult,
) -> list[tuple[LongitudinalGbmReactomeTransitionRequest, CancellationContext | None]]:
    calls: list[
        tuple[LongitudinalGbmReactomeTransitionRequest, CancellationContext | None]
    ] = []

    def infer(
        request: LongitudinalGbmReactomeTransitionRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> LongitudinalGbmReactomeTransitionResult:
        calls.append((request, cancellation))
        return expected

    monkeypatch.setattr(
        service_module,
        "infer_longitudinal_gbm_reactome_transition",
        infer,
    )
    monkeypatch.setattr(
        service_module,
        "algorithm_profile",
        lambda: SimpleNamespace(profile_digest=DIGEST),
    )
    return calls


def test_service_analyze_revalidates_and_delegates_without_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request()
    expected = result(request)
    calls = _install_engine_stub(monkeypatch, expected)
    cancellation = CancellationContext()
    service = LongitudinalGbmReactomeTransitionService()
    assert service.analyze(request, cancellation=cancellation) == expected
    assert analyze_longitudinal_gbm_reactome_transition(request) == expected
    assert calls == [(request, cancellation), (request, None)]

    invalid = request.model_construct(
        **{
            **request.model_dump(mode="python"),
            "bootstrap_replicates": 1,
        }
    )
    with pytest.raises(ValidationError):
        analyze_longitudinal_gbm_reactome_transition(invalid)
    assert len(calls) == 2


def test_service_revalidates_direct_engine_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request()
    valid = result(request)
    forged = LongitudinalGbmReactomeTransitionResult.model_construct(
        **{
            **valid.model_dump(mode="python"),
            "result_digest": OTHER_DIGEST,
        }
    )
    monkeypatch.setattr(
        service_module,
        "infer_longitudinal_gbm_reactome_transition",
        lambda request, *, cancellation=None: forged,
    )
    with pytest.raises(ValidationError, match="canonical result content"):
        analyze_longitudinal_gbm_reactome_transition(request)


def test_service_exact_replay_and_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    request = synthetic_demo_request()
    expected = result(request)
    _install_engine_stub(monkeypatch, expected)
    envelope = ReactomeConditionalReplayVerificationRequest(
        request=request,
        result=expected,
    )
    service = LongitudinalGbmReactomeTransitionService()
    checked = service.verify(envelope)
    assert checked == verify_longitudinal_gbm_reactome_transition_replay(envelope)
    assert checked == verify_replay(envelope)
    assert checked.verified
    assert checked.request_digest_match
    assert checked.profile_digest_match
    assert checked.result_digest_match
    assert checked.transition_topology_match
    assert checked.global_recurrence_semantic_match
    assert checked.pathway_semantic_match
    assert checked.uncertainty_semantic_match
    assert checked.ablation_semantic_match
    assert checked.provenance_match
    assert checked.document_semantic_match
    assert checked.semantic_match
    assert "exactly matches" in checked.message


def _fully_forged_receipt(
    expected: LongitudinalGbmReactomeTransitionResult,
) -> UnverifiedLongitudinalGbmReactomeTransitionResult:
    document: dict[str, Any] = deepcopy(expected.model_dump(mode="python"))
    document["request_digest"] = OTHER_DIGEST
    document["profile_digest"] = OTHER_DIGEST
    document["result_digest"] = OTHER_DIGEST
    document["series_id"] = "forged.series"
    document["provenance"]["request_digest"] = OTHER_DIGEST
    document["provenance"]["profile_digest"] = OTHER_DIGEST
    document["provenance"]["computational_digest"] = OTHER_DIGEST
    transition = document["transitions"][0]
    transition["duration_days"] += 1.0
    transition["global_recurrence"]["shared_active_gene_count"] += 1
    pathway = transition["pathways"][0]
    pathway["discordance"] = 0.2
    pathway["uncertainty"]["variance_closure_residual"] = 0.01
    pathway["ablations"]["global_axis"]["conditional_score_without_component"] = 0.03
    pathway["ablations"]["global_axis"]["score_delta"] = 0.02
    return UnverifiedLongitudinalGbmReactomeTransitionResult.model_validate(
        document,
        strict=True,
    )


def test_service_replay_reports_every_semantic_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request()
    expected = result(request)
    _install_engine_stub(monkeypatch, expected)
    forged = _fully_forged_receipt(expected)
    checked = verify_replay(
        ReactomeConditionalReplayVerificationRequest(request=request, result=forged)
    )
    assert not checked.verified
    assert not checked.request_digest_match
    assert not checked.profile_digest_match
    assert not checked.result_digest_match
    assert not checked.transition_topology_match
    assert not checked.global_recurrence_semantic_match
    assert not checked.pathway_semantic_match
    assert not checked.uncertainty_semantic_match
    assert not checked.ablation_semantic_match
    assert not checked.provenance_match
    assert not checked.document_semantic_match
    assert not checked.semantic_match
    assert "differs" in checked.message


def test_service_honors_cancellation_before_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request()
    expected = result(request)
    calls = _install_engine_stub(monkeypatch, expected)
    cancellation = CancellationContext()
    cancellation.cancel()
    with pytest.raises(InferenceCancelledError):
        analyze_longitudinal_gbm_reactome_transition(
            request,
            cancellation=cancellation,
        )
    assert not calls
