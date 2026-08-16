"""Adversarial closure for M22-04 transport and replay boundaries."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m22_04 import (
    M2204_M2202_INPUT_MEDIA_TYPE,
    EvaluateProteinRnaDiscordanceExternalTransportRequest,
    ProteinRnaDiscordanceExternalTransportResult,
    TransportabilityReport,
    TransportDimension,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import ArtifactReference
from glio_proteogen.modules.c21_reference_material.m22_04_external_transport_evaluator import (
    M2204Engine,
    M2204ReplayError,
)
from tests.runtime.test_m2204_transport import _evaluation, _request


def test_upstream_media_and_source_identity_are_bound() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="M22-02"):
        EvaluateProteinRnaDiscordanceExternalTransportRequest.model_validate(
            request.model_copy(
                update={
                    "upstream_truth": request.upstream_truth.model_copy(
                        update={"media_type": "application/json"}
                    )
                }
            )
        )
    with pytest.raises(ValidationError, match="source artifacts"):
        EvaluateProteinRnaDiscordanceExternalTransportRequest.model_validate(
            request.model_copy(update={"source_artifacts": (request.benchmark_package,)})
        )
    assert request.upstream_truth.media_type == M2204_M2202_INPUT_MEDIA_TYPE


def test_configuration_and_collections_cannot_drop_or_repeat_dimensions() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="all seven"):
        type(request.configuration).model_validate(
            request.configuration.model_copy(
                update={"required_dimensions": (TransportDimension.SITE,)}
            )
        )
    with pytest.raises(ValidationError, match="validation ids"):
        type(request).model_validate(
            request.model_copy(
                update={"validations": (*request.validations, request.validations[0])}
            )
        )
    duplicate = (*request.evaluations, request.evaluations[0])
    with pytest.raises(ValidationError, match="evaluation dimensions"):
        type(request).model_validate(request.model_copy(update={"evaluations": duplicate}))


def test_transport_floor_and_support_closure_are_fail_closed() -> None:
    evaluation = _evaluation(TransportDimension.SITE)
    with pytest.raises(ValidationError, match="supported evaluation"):
        type(evaluation).model_validate(evaluation.model_copy(update={"metric_value": 0.1}))
    result = M2204Engine().evaluate(_request())
    assert result.report is not None
    support = result.report.support_domain
    with pytest.raises(ValidationError, match="disjoint"):
        type(support).model_validate(
            support.model_copy(update={"narrowed_dimensions": (TransportDimension.SITE,)})
        )
    with pytest.raises(ValidationError, match="close every configured"):
        TransportabilityReport.model_validate(
            result.report.model_copy(
                update={
                    "support_domain": support.model_copy(
                        update={"retained_dimensions": support.retained_dimensions[:-1]}
                    )
                }
            )
        )


def test_result_identity_digest_and_report_binding_are_immutable() -> None:
    result = M2204Engine().evaluate(_request())
    adapter = TypeAdapter(ProteinRnaDiscordanceExternalTransportResult)
    for field, value, message in (
        ("request_digest", "sha256:" + "f" * 64, "request digest"),
        ("result_id", "result.forged", "result id"),
        ("result_digest", "sha256:" + "f" * 64, "result digest"),
    ):
        with pytest.raises(ValidationError, match=message):
            adapter.validate_python(result.model_copy(update={field: value}), strict=True)
    assert result.request_digest == canonical_request_digest(result.request)
    assert result.result_digest == result_payload_digest(result)
    assert result.report is not None
    with pytest.raises(ValidationError, match="configuration must equal"):
        adapter.validate_python(
            result.model_copy(
                update={
                    "report": result.report.model_copy(
                        update={
                            "configuration": result.report.configuration.model_copy(
                                update={"version": "2.0.0"}
                            )
                        }
                    )
                }
            ),
            strict=True,
        )


def test_result_evidence_and_finding_ids_cannot_repeat() -> None:
    result = M2204Engine().evaluate(_request())
    adapter = TypeAdapter(ProteinRnaDiscordanceExternalTransportResult)
    with pytest.raises(ValidationError, match="result evidence"):
        adapter.validate_python(
            result.model_copy(update={"evidence": result.evidence * 2}), strict=True
        )
    finding = result.findings[0]
    with pytest.raises(ValidationError, match="finding ids"):
        adapter.validate_python(
            result.model_copy(update={"findings": (finding, finding)}), strict=True
        )


def test_replay_rejects_tampered_payload_and_hostile_input() -> None:
    engine = M2204Engine()
    with pytest.raises(M2204ReplayError):
        engine.replay({})  # type: ignore[arg-type]
    result = engine.evaluate(_request())
    with pytest.raises(M2204ReplayError):
        engine.replay(result.model_copy(update={"evidence": ()}))
    with pytest.raises(M2204ReplayError):
        engine.replay(result.model_copy(update={"result_id": "result.forged"}))
    with pytest.raises(ValueError, match="requires accepted configuration"):
        engine.evaluate({"context": {"references": None}})

    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError

    with pytest.raises(ValueError, match="requires accepted configuration"):
        engine.evaluate(Hostile())


def test_source_artifact_digest_and_media_fields_are_strict() -> None:
    request = _request()
    source = request.source_artifacts[-1]
    forged = ArtifactReference.model_construct(
        artifact_id=source.artifact_id,
        version=source.version,
        digest="not-a-digest",
        media_type=source.media_type,
    )
    with pytest.raises(ValidationError, match="sha256"):
        type(request).model_validate(
            request.model_copy(
                update={"source_artifacts": (*request.source_artifacts[:-1], forged)}
            )
        )
