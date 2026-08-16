"""Deep adversarial closure tests for provisional M22-02."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m22_02 import (
    M2202_MODULE_ID,
    GenerationStatus,
    ProteinRnaDiscordanceSyntheticTruthResult,
    SyntheticTruthCorpus,
    contract_json_schemas,
)
from glio_proteogen.modules.c21_reference_material.m22_02_synthetic_truth_simulation_generator import (  # noqa: E501
    M2202Service,
)
from tests.contract.test_m22_02_hardening import _request


def test_result_identity_and_provenance_tamper_are_rejected() -> None:
    result = M2202Service().generate(_request())
    payload = result.model_dump(mode="python")
    payload["result_id"] = "m2202.result.tampered"
    with pytest.raises(ValidationError, match="deterministically bound"):
        ProteinRnaDiscordanceSyntheticTruthResult(**payload)

    payload = result.model_dump(mode="python")
    payload["provenance"]["module_id"] = "GLIO-PROTEOGEN-M22-01"
    with pytest.raises(ValidationError, match="provenance module id"):
        ProteinRnaDiscordanceSyntheticTruthResult(**payload)


def test_result_request_and_digest_tamper_are_rejected() -> None:
    result = M2202Service().generate(_request())
    payload = result.model_dump(mode="python")
    payload["request_digest"] = "sha256:" + "a" * 64
    with pytest.raises(ValidationError, match="request digest"):
        ProteinRnaDiscordanceSyntheticTruthResult(**payload)

    payload = result.model_dump(mode="python")
    payload["result_digest"] = "sha256:" + "f" * 64
    with pytest.raises(ValidationError, match="result digest"):
        ProteinRnaDiscordanceSyntheticTruthResult(**payload)


def test_schema_exposes_all_prohibited_boundaries() -> None:
    metadata = contract_json_schemas()["output"]["x-glio-contract"]
    assert metadata["moduleId"] == M2202_MODULE_ID
    assert metadata["kinaseActivity"] is False
    assert metadata["allOmicsFusion"] is False
    assert metadata["treatmentRecommendation"] is False
    assert metadata["identityInference"] is False
    assert metadata["consentInference"] is False
    assert metadata["upstreamMutation"] is False
    assert metadata["unsupportedToNegative"] is False


def test_corpus_manifest_and_source_closures_are_fail_closed() -> None:
    result = M2202Service().generate(_request())
    corpus = result.corpus
    assert corpus is not None

    payload = corpus.model_dump(mode="python")
    payload["cases"] = (payload["cases"][0], payload["cases"][0])
    with pytest.raises(ValidationError, match="corpus case ids"):
        SyntheticTruthCorpus(**payload)

    payload = corpus.model_dump(mode="python")
    payload["manifest"]["case_ids"] = ("m2202.unknown",)
    with pytest.raises(ValidationError, match="manifest must enumerate"):
        SyntheticTruthCorpus(**payload)

    payload = corpus.model_dump(mode="python")
    payload["manifest"]["version"] = "2.0.0"
    with pytest.raises(ValidationError, match="manifest version"):
        SyntheticTruthCorpus(**payload)

    payload = corpus.model_dump(mode="python")
    payload["source_artifacts"] = (payload["source_artifacts"][0],) * 2
    with pytest.raises(ValidationError, match="source artifacts"):
        SyntheticTruthCorpus(**payload)


def test_result_support_manifest_configuration_and_provenance_closures() -> None:
    result = M2202Service().generate(_request())

    payload = result.model_dump(mode="python")
    payload["provenance"]["input_digests"] = ("sha256:" + "c" * 64,)
    with pytest.raises(ValidationError, match="upstream result digest"):
        ProteinRnaDiscordanceSyntheticTruthResult(**payload)

    payload = result.model_dump(mode="python")
    payload["corpus"] = None
    with pytest.raises(ValidationError, match="generated result requires"):
        ProteinRnaDiscordanceSyntheticTruthResult(**payload)

    payload = result.model_dump(mode="python")
    payload["manifest"]["manifest_id"] = "m2202.other.manifest"
    with pytest.raises(ValidationError, match="result manifest"):
        ProteinRnaDiscordanceSyntheticTruthResult(**payload)

    payload = result.model_dump(mode="python")
    payload["manifest"]["configuration"]["seed"] = 99
    payload["corpus"]["manifest"]["configuration"]["seed"] = 99
    with pytest.raises(ValidationError, match="result configuration"):
        ProteinRnaDiscordanceSyntheticTruthResult(**payload)


def test_abstained_result_cannot_retain_generated_material() -> None:
    result = M2202Service().generate(_request())
    payload = result.model_dump(mode="python")
    payload["status"] = GenerationStatus.ABSTAINED
    payload["abstention_reason"] = "caller support is insufficient"
    with pytest.raises(ValidationError, match="abstained result requires"):
        ProteinRnaDiscordanceSyntheticTruthResult(**payload)
