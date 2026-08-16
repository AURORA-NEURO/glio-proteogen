"""Focused contract/schema smoke for provisional M14-01."""

import pytest

from glio_proteogen.contracts.m14_01 import (
    M1401_OUTPUT_MEDIA_TYPE,
    M1401_PROVISIONAL_ABI,
    BiologicalHypothesis,
    HypothesisFindingCode,
    HypothesisStatus,
    contract_json_schemas,
)

_SCHEMA_COUNT = 10


def test_provisional_schemas_require_hypothesis_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["competingExplanationsRequired"]
        and schema["x-glio-contract"]["falsificationRulesRequired"]
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["primaryArchitecture"] == "pca_ica_baseline"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1401_OUTPUT_MEDIA_TYPE
    assert M1401_PROVISIONAL_ABI is True


def test_hypothesis_without_competing_explanation_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 1 item"):
        BiologicalHypothesis(
            hypothesis_id="h1",
            version="1.0.0",
            statement="A candidate protein_subtype has a biological mechanism.",
            mechanism_class="protein_subtype",
            target_ids=("protein_subtype",),
            competing_explanations=(),
            falsification_rules=(),
            evidence_tiers=(),
            prohibited_interpretations=("Do not infer treatment response.",),
        )
    assert HypothesisStatus.PROPOSED.value == "proposed"
    assert HypothesisFindingCode.PROVISIONAL_ABI_PENDING_REVIEW.value
