"""Focused schema and locked-baseline smoke for provisional M10-03."""

from math import inf, nan
from typing import cast

import pytest
from evals.m10_03.run import build_scenario_request
from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m10_03 import (
    M1003_BASELINE_MEDIA_TYPE,
    M1003_OUTPUT_MEDIA_TYPE,
    BaselineConfiguration,
    BaselineDiagnostic,
    BaselineDiagnosticStatus,
    BaselineEstimate,
    BaselineEstimateKind,
    BaselineEstimatorFamily,
    BaselinePreprocessingStep,
    BaselineReplayReason,
    BaselineResultStatus,
    BaselineTuningSpec,
    EstimateProteinRnaDiscordanceBaselineVerification,
    ProteinRnaDiscordanceBaselineResult,
    contract_json_schemas,
    result_payload_digest,
)
from glio_proteogen.kernel.models import ArtifactReference, SupportDecision, SupportStatus

_DIGEST = "sha256:" + ("a" * 64)


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest=_DIGEST,
        media_type="application/json",
    )


def test_schema_inventory_is_strict_and_provisional() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == (
        "request",
        "output",
        "configuration",
        "preprocessing",
        "tuning",
        "estimate",
        "diagnostic",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["lockedPreprocessingRequired"] is True
        assert metadata["lockedTuningRequired"] is True
        assert metadata["uncertaintyRequired"] is True
        assert metadata["diagnosticsRequired"] is True
        assert metadata["unsupportedToNegative"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1003_OUTPUT_MEDIA_TYPE
    assert schemas["request"]["x-glio-contract"]["formalStateInputMediaType"] == (
        M1003_BASELINE_MEDIA_TYPE
    )


def test_locked_preprocessing_tuning_and_diagnostic_smoke() -> None:
    preprocessing = BaselinePreprocessingStep(
        sequence=1,
        operation="robust-scale",
        parameters_digest=_DIGEST,
    )
    tuning = BaselineTuningSpec(
        tuning_id="tuning.m1003.smoke",
        protocol="locked-five-fold",
        objective="mean absolute error",
        folds=5,
        benchmark_artifact=_artifact("artifact.benchmark"),
    )
    diagnostic = BaselineDiagnostic(
        diagnostic_id="diagnostic.m1003.smoke",
        status=BaselineDiagnosticStatus.PASS,
        metric_name="reproduction_error",
        metric_value=0.1,
        message="Published baseline behavior is reproducible in the fixture.",
    )
    assert preprocessing.locked is True
    assert tuning.locked is True
    assert diagnostic.status is BaselineDiagnosticStatus.PASS


def test_baseline_estimate_shapes_are_strict() -> None:
    with pytest.raises(ValueError, match="scalar baseline"):
        BaselineEstimate(
            feature_id="feature.scalar",
            kind=BaselineEstimateKind.SCALAR,
            unit="u",
            support_score=0.9,
        )
    with pytest.raises(ValueError, match="interval baseline"):
        BaselineEstimate(
            feature_id="feature.interval",
            kind=BaselineEstimateKind.INTERVAL,
            unit="u",
            estimate_value=2.0,
            lower_bound=3.0,
            upper_bound=4.0,
            support_score=0.9,
        )
    with pytest.raises(ValueError, match="categorical baseline"):
        BaselineEstimate(
            feature_id="feature.category",
            kind=BaselineEstimateKind.CATEGORICAL,
            unit="u",
            estimate_value=1.0,
            support_score=0.9,
        )


@pytest.mark.parametrize("field", ["estimate_value", "lower_bound", "upper_bound", "support_score"])
def test_baseline_estimate_rejects_non_finite_numbers(field: str) -> None:
    values: dict[str, object] = {
        "feature_id": "feature.finite",
        "kind": BaselineEstimateKind.SCALAR,
        "unit": "u",
        "estimate_value": 0.0,
        "support_score": 0.9,
    }
    values[field] = inf if field != "support_score" else nan
    with pytest.raises(ValueError, match="finite"):
        BaselineEstimate(**values)


def test_diagnostic_rejects_non_finite_metric() -> None:
    with pytest.raises(ValueError, match="finite"):
        BaselineDiagnostic(
            diagnostic_id="diagnostic.nonfinite",
            status=BaselineDiagnosticStatus.PASS,
            metric_name="metric",
            metric_value=nan,
            message="not a valid metric",
        )


def test_configuration_order_and_target_identity_are_closed() -> None:
    with pytest.raises(ValueError, match="ordered sequences"):
        BaselineConfiguration(
            configuration_id="config.bad-order",
            version="1.0.0",
            estimator_family=BaselineEstimatorFamily.ROBUST_LINEAR,
            target_feature_ids=("a",),
            preprocessing=(
                BaselinePreprocessingStep(sequence=2, operation="b", parameters_digest=_DIGEST),
                BaselinePreprocessingStep(sequence=1, operation="a", parameters_digest=_DIGEST),
            ),
            tuning=BaselineTuningSpec(
                tuning_id="tuning.bad-order",
                protocol="p",
                objective="o",
                folds=2,
                benchmark_artifact=_artifact("benchmark"),
            ),
            uncertainty_method="u",
            reference=_artifact("ref"),
        )
    with pytest.raises(ValueError, match="target feature ids"):
        BaselineConfiguration(
            configuration_id="config.bad-targets",
            version="1.0.0",
            estimator_family=BaselineEstimatorFamily.ROBUST_LINEAR,
            target_feature_ids=("a", "a"),
            preprocessing=(
                BaselinePreprocessingStep(sequence=1, operation="a", parameters_digest=_DIGEST),
            ),
            tuning=BaselineTuningSpec(
                tuning_id="tuning.bad-targets",
                protocol="p",
                objective="o",
                folds=2,
                benchmark_artifact=_artifact("benchmark"),
            ),
            uncertainty_method="u",
            reference=_artifact("ref"),
        )


def test_verification_flags_and_request_media_are_closed() -> None:
    with pytest.raises(ValueError, match="verified must equal"):
        EstimateProteinRnaDiscordanceBaselineVerification(
            content_verified=True,
            deterministic_verified=True,
            verified=False,
            reason=BaselineReplayReason.INVALID_RESULT,
        )
    with pytest.raises(ValueError, match="verified results"):
        EstimateProteinRnaDiscordanceBaselineVerification(
            content_verified=True,
            deterministic_verified=True,
            verified=True,
            reason=BaselineReplayReason.VERIFIED,
        )
    verified = EstimateProteinRnaDiscordanceBaselineVerification(
        content_verified=True,
        deterministic_verified=True,
        verified=True,
        result_digest=_DIGEST,
        reason=BaselineReplayReason.VERIFIED,
    )
    assert verified.verified is True


def test_request_and_result_replay_bindings_are_strict() -> None:
    request = build_scenario_request()
    with pytest.raises(ValueError, match="M10-01 result"):
        type(request).model_validate(
            request.model_copy(
                update={
                    "formal_state_result": request.formal_state_result.model_copy(
                        update={"media_type": "application/json"}
                    )
                }
            ),
            strict=True,
        )
    result = __import__(
        "glio_proteogen.modules.c10_pathway_proteotype.m10_03_mature_baseline_estimator",
        fromlist=["estimate_protein_rna_discordance_baseline"],
    ).estimate_protein_rna_discordance_baseline(request)
    with pytest.raises(ValueError, match="request digest"):
        ProteinRnaDiscordanceBaselineResult.model_validate(
            result.model_copy(update={"request_digest": _DIGEST}), strict=True
        )


def test_result_status_and_identity_closures_reject_contradictions() -> None:
    result = __import__(
        "glio_proteogen.modules.c10_pathway_proteotype.m10_03_mature_baseline_estimator",
        fromlist=["estimate_protein_rna_discordance_baseline"],
    ).estimate_protein_rna_discordance_baseline(build_scenario_request())
    for update, message in (
        ({"estimates": ()}, "estimated result"),
        ({"abstention_reason": "unexpected"}, "estimated result"),
        (
            {
                "support_decision": result.support_decision.model_copy(
                    update={"status": SupportStatus.REVIEW_REQUIRED}
                )
            },
            "estimated result",
        ),
        ({"estimates": (result.estimates[0], result.estimates[0])}, "estimate feature ids"),
        ({"diagnostics": (result.diagnostics[0], result.diagnostics[0])}, "diagnostic ids"),
    ):
        with pytest.raises(ValueError, match=message):
            ProteinRnaDiscordanceBaselineResult.model_validate(
                result.model_copy(update=update), strict=True
            )


def test_valid_abstained_result_branch_is_machine_validated() -> None:
    result = __import__(
        "glio_proteogen.modules.c10_pathway_proteotype.m10_03_mature_baseline_estimator",
        fromlist=["estimate_protein_rna_discordance_baseline"],
    ).estimate_protein_rna_discordance_baseline(build_scenario_request())
    abstained_payload = result.model_dump(mode="python")
    abstained_payload.update(
        {
            "status": BaselineResultStatus.ABSTAINED,
            "estimates": (),
            "abstention_reason": "unsupported upstream",
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="UNSUPPORTED",
                rationale="upstream is not evaluable",
            ),
        }
    )
    candidate = ProteinRnaDiscordanceBaselineResult.model_construct(**abstained_payload)
    abstained_payload["result_digest"] = result_payload_digest(candidate)
    checked = ProteinRnaDiscordanceBaselineResult.model_validate(abstained_payload, strict=True)
    assert checked.status is BaselineResultStatus.ABSTAINED
