"""Adversarial source-identity closure for provisional M24-04."""

from __future__ import annotations

from typing import Any

import pytest
from evals.m23_04.run import build_scenario_request

from glio_proteogen.contracts.m24_04 import (
    M2404_OPERATION,
    EvaluateBiomarkerPanelExternalTransportRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes


def _request() -> EvaluateBiomarkerPanelExternalTransportRequest:
    data = build_scenario_request().model_dump(mode="json")
    data["operation"] = M2404_OPERATION
    data["configuration"].pop("isoform_aware_quantification_required")
    return EvaluateBiomarkerPanelExternalTransportRequest.model_validate_json(
        canonical_json_bytes(data), strict=True
    )


def _data(request: EvaluateBiomarkerPanelExternalTransportRequest) -> dict[str, Any]:
    return request.model_dump(mode="json")


def test_source_artifacts_must_bind_all_declared_transport_inputs() -> None:
    data = _data(_request())
    data["source_artifacts"] = [
        {**artifact, "artifact_id": "m2404.unrelated-source"}
        for artifact in data["source_artifacts"]
    ]

    with pytest.raises(ValueError, match="source artifacts"):
        EvaluateBiomarkerPanelExternalTransportRequest.model_validate_json(
            canonical_json_bytes(data), strict=True
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_id", "m2404.forged-input"),
        ("version", "9.9.9"),
        ("digest", "sha256:" + ("f" * 64)),
        ("media_type", "application/x-forged-transport-input"),
    ],
)
def test_declared_transport_input_identity_must_match_source_artifact(
    field: str, value: str
) -> None:
    data = _data(_request())
    declared = dict(data["mass_spectrometry_proteome"])
    declared[field] = value
    data["mass_spectrometry_proteome"] = declared

    with pytest.raises(ValueError, match="source artifacts"):
        EvaluateBiomarkerPanelExternalTransportRequest.model_validate_json(
            canonical_json_bytes(data), strict=True
        )
