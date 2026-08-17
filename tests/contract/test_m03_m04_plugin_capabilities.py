"""Capability-sealing regression tests for M03-08 and M04-08 release plugins."""

from __future__ import annotations

import pytest
from evals.m03_08.run import build_scenario as build_m0308_scenario
from evals.m04_08.run import _fixture as build_m0408_fixture

from glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging import (
    M0308Plugin,
    M0308Service,
    ProteinInferenceReleaseSubmission,
    ValidatedM0308Request,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging import (
    M0408Plugin,
    M0408Service,
    ProteoformReleaseSubmission,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging.plugin import (
    ValidatedM0408Request,
)


def test_m0308_release_token_is_issued_and_non_forgeable() -> None:
    scenario = build_m0308_scenario()
    plugin = M0308Plugin(M0308Service())
    token = plugin.validate(
        ProteinInferenceReleaseSubmission(
            request=scenario.request,
            artifacts_by_path=scenario.artifacts,
            stage_results_by_module=scenario.stages,
        )
    )
    result = plugin.run(token)
    assert result.result.release_result_id.startswith("result.m0308.")

    forged = ValidatedM0308Request(
        request=token.request,
        artifacts_by_path=token.artifacts_by_path,
        stage_results_by_module=token.stage_results_by_module,
        _seal=object(),
    )
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)

    object.__setattr__(token, "request", token.request.model_copy())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_m0408_release_token_is_issued_and_non_forgeable() -> None:
    fixture = build_m0408_fixture()
    plugin = M0408Plugin(M0408Service())
    token = plugin.validate(
        ProteoformReleaseSubmission(
            request=fixture.request,
            artifacts_by_path=fixture.artifacts,
            stage_results_by_module=fixture.stages,
        )
    )
    result = plugin.run(token)
    assert result.result.release_result_id.startswith("result.m0408.")

    forged = ValidatedM0408Request(
        request=token.request,
        artifacts_by_path=token.artifacts_by_path,
        stage_results_by_module=token.stage_results_by_module,
        _seal=object(),
    )
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)

    object.__setattr__(token, "request", token.request.model_copy())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)
