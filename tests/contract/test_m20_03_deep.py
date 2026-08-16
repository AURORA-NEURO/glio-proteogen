"""Deep boundary and replay coverage for M20-03."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m20_03 import (
    AggregationConfiguration,
    DisagreementRecord,
    DisagreementStatus,
    FusionFinding,
    FusionFindingCode,
    FusionStatus,
    ReliabilityBand,
    canonical_request_digest,
)
from glio_proteogen.kernel.models import SupportDecision, SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m20_03_fusion_aggregation import (
    M2003Engine,
)
from tests.contract.test_m20_03_adversarial import _artifact, _contribution, _evidence, _request


def test_configuration_flags_are_literal_safety_closures() -> None:
    with pytest.raises(ValidationError):
        AggregationConfiguration(
            configuration_id="configuration.m2003.invalid",
            version="1.0.0",
            method="unsafe",
            reliability_threshold=0.7,
            preserve_disagreement=False,
        )


def test_request_rejects_missing_contribution_artifact() -> None:
    request = _request()
    with pytest.raises(ValueError, match="every contribution artifact"):
        type(request).model_validate(
            request.model_copy(update={"source_artifacts": (request.contributions[0].artifact,)}),
            strict=True,
        )


def test_request_rejects_duplicate_disagreement_ids() -> None:
    disagreement = DisagreementRecord(
        disagreement_id="disagreement.m2003.duplicate",
        source_ids=("source.m2003.proteome", "source.m2003.genome"),
        description="Duplicate disagreement.",
        status=DisagreementStatus.OPEN,
        evidence=(_evidence(_artifact("duplicate-disagreement")),),
    )
    with pytest.raises(ValueError, match="disagreement ids"):
        _request(disagreements=(disagreement, disagreement))


def test_result_rejects_erased_source_contribution() -> None:
    result = M2003Engine().fuse(_request())
    assert result.integrated_evidence is not None
    changed = result.integrated_evidence.model_copy(
        update={"contributions": (result.integrated_evidence.contributions[0],)}
    )
    with pytest.raises(ValueError, match="exact source contributions"):
        type(result).model_validate(
            result.model_copy(update={"integrated_evidence": changed}), strict=True
        )


def test_result_rejects_supported_abstention() -> None:
    result = M2003Engine().fuse(_request())
    with pytest.raises(ValueError, match="abstained result"):
        type(result).model_validate(
            result.model_copy(
                update={
                    "status": FusionStatus.ABSTAINED,
                    "integrated_evidence": None,
                    "abstention_reason": "review",
                    "support_decision": SupportDecision(
                        status=SupportStatus.SUPPORTED,
                        reason_code="invalid",
                        rationale="must fail",
                    ),
                }
            ),
            strict=True,
        )


def test_result_finding_ids_are_unique_and_review_is_closed() -> None:
    result = M2003Engine().fuse(_request())
    finding = FusionFinding(
        finding_id="finding.m2003.duplicate",
        code=FusionFindingCode.INPUT_INCOMPLETE,
        message="duplicate",
    )
    with pytest.raises(ValueError, match="finding ids"):
        type(result).model_validate(
            result.model_copy(update={"findings": (finding, finding)}), strict=True
        )


def test_not_evaluable_source_is_safe_abstention() -> None:
    source = _contribution("not-evaluable", 0.0).model_copy(
        update={"reliability_band": ReliabilityBand.NOT_EVALUABLE}
    )
    result = M2003Engine().fuse(_request(contributions=(source, _contribution("second", 0.7))))
    assert result.status is FusionStatus.ABSTAINED
    assert result.integrated_evidence is None


def test_request_digest_changes_with_configuration() -> None:
    request = _request()
    altered = request.model_copy(
        update={
            "configuration": request.configuration.model_copy(
                update={"method": "different-locked-method"}
            )
        }
    )
    assert canonical_request_digest(request) != canonical_request_digest(altered)
