"""Adversarial safety coverage for M21-02."""

from __future__ import annotations

from typing import Any

import pytest
from evals.m21_02.fixture import build_request, denied_request
from pydantic import ValidationError

from glio_proteogen.contracts.m21_02 import (
    ComplexActivitySyntheticTruthResult,
    GenerateComplexActivitySyntheticTruthRequest,
    GenerationStatus,
)
from glio_proteogen.contracts.m21_02.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.modules.c21_reference_material.m21_02_synthetic_truth_simulation_generator import (  # noqa: E501
    M2102AuthorizationError,
    M2102ReplayError,
    M2102Service,
    preflight_m2102_authorization,
)


def test_request_requires_upstream_artifact_in_source_manifest() -> None:
    request = build_request()
    with pytest.raises(ValidationError, match="include the M21-01 result"):
        GenerateComplexActivitySyntheticTruthRequest.model_validate(
            request.model_copy(update={"source_artifacts": request.source_artifacts[1:]}),
            strict=True,
        )


def test_request_rejects_duplicate_source_artifacts() -> None:
    request = build_request()
    with pytest.raises(ValidationError, match="unique by id"):
        GenerateComplexActivitySyntheticTruthRequest.model_validate(
            request.model_copy(
                update={
                    "source_artifacts": (
                        *request.source_artifacts,
                        request.source_artifacts[0],
                    )
                }
            ),
            strict=True,
        )


def test_preflight_rejects_malformed_hostile_mapping() -> None:
    class ExplodingMapping(dict[str, Any]):
        def get(self, key: str, default: object = None) -> object:
            if key == "context":
                raise RuntimeError
            return super().get(key, default)

    with pytest.raises(M2102AuthorizationError):
        preflight_m2102_authorization(ExplodingMapping())


def test_generated_result_requires_supported_closed_corpus() -> None:
    result = M2102Service().generate(build_request())
    assert result.status is GenerationStatus.GENERATED
    assert result.corpus is not None
    with pytest.raises(ValidationError, match="supported corpus"):
        ComplexActivitySyntheticTruthResult.model_validate(
            result.model_copy(
                update={
                    "corpus": None,
                    "result_digest": sha256_digest("tampered"),
                }
            ),
            strict=True,
        )


def test_abstention_closure_rejects_unsafe_generated_shape() -> None:
    result = M2102Service().generate(build_request())
    with pytest.raises(ValidationError, match="abstained result"):
        ComplexActivitySyntheticTruthResult.model_validate(
            result.model_copy(
                update={"status": GenerationStatus.ABSTAINED, "result_digest": result.result_digest}
            ),
            strict=True,
        )
    with pytest.raises(M2102AuthorizationError):
        M2102Service().generate(denied_request())


def test_replay_rejects_self_rehashed_corpus_mutation() -> None:
    service = M2102Service()
    result = service.generate(build_request())
    assert result.corpus is not None
    mutated_case = result.corpus.cases[0].model_copy(update={"truth_values": ("tampered-value",)})
    mutated_corpus = result.corpus.model_copy(
        update={"cases": (mutated_case, *result.corpus.cases[1:])}
    )
    forged = result.model_copy(update={"corpus": mutated_corpus})
    forged = ComplexActivitySyntheticTruthResult.model_validate_json(
        canonical_json_bytes(
            forged.model_copy(update={"result_digest": result_payload_digest(forged)})
        ),
        strict=True,
    )
    with pytest.raises(M2102ReplayError, match="deterministic replay"):
        service.replay(forged)
