"""Focused import/schema/safety smoke for provisional M07-03."""

from typing import Final

import pytest
from evals.m07_03.run import artifact, request
from pydantic import ValidationError

from glio_proteogen.contracts.m07_03 import (
    M0703_OUTPUT_MEDIA_TYPE,
    BaselineEstimate,
    BaselineEstimateKind,
    BaselinePreprocessingPolicy,
    BaselineTuningRecord,
    MatureBaselineConfiguration,
    canonical_result_digest,
    contract_json_schemas,
    verify_result_digest,
)
from glio_proteogen.contracts.m07_03.canonical import normalized_result_payload
from glio_proteogen.kernel.models import EvidenceReference
from glio_proteogen.modules.c07_copy_number_dosage.m07_03_mature_baseline_estimator import (
    M0703AuthorizationError,
    M0703Plugin,
    M0703Service,
    preflight_m0703_authorization,
)

_SCHEMA_COUNT: Final = 7


def test_provisional_schemas_are_strict_and_owner_pending() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0703_OUTPUT_MEDIA_TYPE


def test_plugin_descriptor_and_preflight_fail_closed() -> None:
    descriptor = M0703Plugin(M0703Service()).descriptor()
    assert descriptor.module_id == "GLIO-PROTEOGEN-M07-03"
    assert descriptor.version == "0.1.0-provisional"
    with pytest.raises(M0703AuthorizationError):
        preflight_m0703_authorization({"context": {"references": {}}})


def test_canonical_mapping_and_invalid_digest_inputs_are_explicit() -> None:
    result = M0703Service().execute(request())
    projection = result.model_dump(mode="json")
    assert normalized_result_payload(projection)["status"] == "abstained"
    assert canonical_result_digest(projection) == projection["result_digest"]
    assert verify_result_digest(projection)
    assert not verify_result_digest({"result_digest": "not-a-digest"})
    assert not verify_result_digest(object())
    assert not verify_result_digest({"result_digest": None})


def test_locked_policy_tuning_and_configuration_reject_counter_evidence() -> None:
    candidate = request()
    counter = EvidenceReference(
        reference=artifact("counter", "8"),
        role="counter_evidence",
        claim="conflicting evidence",
    )
    with pytest.raises(ValidationError):
        BaselinePreprocessingPolicy(
            policy_id="policy.invalid",
            version="1.0.0",
            operations=("normalize",),
            evidence=(counter,),
        )
    with pytest.raises(ValidationError):
        BaselineTuningRecord(
            tuning_id="tuning.invalid",
            version="1.0.0",
            method="fit",
            objective="error",
            seed=1,
            evidence=(counter,),
        )
    with pytest.raises(ValidationError):
        MatureBaselineConfiguration.model_validate(
            candidate.configuration.model_dump(mode="python")
            | {"evidence": (counter,)},
            strict=True,
        )
    with pytest.raises(ValidationError):
        MatureBaselineConfiguration.model_validate(
            candidate.configuration.model_dump(mode="python")
            | {
                "reference": artifact("reference", "9"),
                "representation_media_type": "application/vnd.glio-proteogen.m07-02+json",
            },
            strict=True,
        )


def test_baseline_estimate_interval_and_category_shapes_are_valid() -> None:
    interval = BaselineEstimate(
        feature_id="feature.interval",
        kind=BaselineEstimateKind.INTERVAL,
        unit="copies",
        estimate_value=2.0,
        lower_bound=1.0,
        upper_bound=3.0,
    )
    category = BaselineEstimate(
        feature_id="feature.category",
        kind=BaselineEstimateKind.CATEGORICAL,
        unit="class",
        category="diploid",
    )
    assert interval.lower_bound == 1.0
    assert category.category == "diploid"
    with pytest.raises(ValidationError):
        BaselineEstimate(
            feature_id="feature.interval-bad",
            kind=BaselineEstimateKind.INTERVAL,
            unit="copies",
            estimate_value=0.0,
            lower_bound=1.0,
            upper_bound=3.0,
        )
    with pytest.raises(ValidationError):
        BaselineEstimate(
            feature_id="feature.category-bad",
            kind=BaselineEstimateKind.CATEGORICAL,
            unit="class",
            category="diploid",
            estimate_value=2.0,
        )


def test_result_validator_rejects_each_closure_gap() -> None:
    result = M0703Service().execute(request())
    estimate = BaselineEstimate(
        feature_id="feature.one",
        kind=BaselineEstimateKind.SCALAR,
        unit="copies",
        estimate_value=2.0,
    )
    diagnostic = result.diagnostics[0]
    candidates = (
        result.model_copy(update={"request_digest": "sha256:" + "0" * 64}),
        result.model_copy(update={"result_id": "result.invalid"}),
        result.model_copy(update={"evidence": ()}),
        result.model_copy(update={"estimates": (estimate, estimate)}),
        result.model_copy(update={"diagnostics": (diagnostic, diagnostic)}),
        result.model_copy(update={"status": "estimated"}),
        result.model_copy(update={"abstention_reason": None}),
        result.model_copy(
            update={
                "support_decision": result.support_decision.model_copy(
                    update={"status": "supported"}
                )
            }
        ),
        result.model_copy(update={"human_review_required": False}),
        result.model_copy(update={"result_digest": "sha256:" + "0" * 64}),
    )
    for candidate in candidates:
        with pytest.raises(ValidationError):
            type(result).model_validate(candidate, strict=True)
