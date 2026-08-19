"""Frozen deterministic M24-02 evaluator request."""

from __future__ import annotations

from evals.m24_07.fixture import artifact, context
from glio_proteogen.contracts.m24_02 import (
    M2402_M2401_INPUT_MEDIA_TYPE,
    FixtureKind,
    GenerateBiomarkerPanelSyntheticTruthRequest,
    GenerationConfiguration,
)
from glio_proteogen.kernel.models import ArtifactReference


def request() -> GenerateBiomarkerPanelSyntheticTruthRequest:
    return GenerateBiomarkerPanelSyntheticTruthRequest(
        request_id="m2402.eval.request",
        context=context(),
        upstream_result=ArtifactReference(
            artifact_id="m2401.eval.result",
            version="0.1.0-provisional",
            digest="sha256:" + "1" * 64,
            media_type=M2402_M2401_INPUT_MEDIA_TYPE,
        ),
        configuration=GenerationConfiguration(
            configuration_id="m2402.eval.configuration",
            version="1.0.0",
            generator_name="locked-evaluator-generator",
            seed=29,
            requested_fixture_kinds=tuple(FixtureKind),
        ),
        requested_case_count=5,
        source_artifacts=(artifact("2"),),
    )
