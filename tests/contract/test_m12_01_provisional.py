"""Focused contract/schema smoke for provisional M12-01."""

import pytest

from glio_proteogen.contracts.m12_01 import (
    M1201_OUTPUT_MEDIA_TYPE,
    M1201_PROVISIONAL_ABI,
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
        schema["x-glio-contract"]["primaryArchitecture"] == "bayesian_factor_analysis"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1201_OUTPUT_MEDIA_TYPE
    assert M1201_PROVISIONAL_ABI is True


def test_hypothesis_without_competing_explanation_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 1 item"):
        BiologicalHypothesis(
            hypothesis_id="h1",
            version="1.0.0",
            statement="A candidate biomarker panel has a biological mechanism.",
            mechanism_class="biomarker_panel",
            target_ids=("biomarker-panel",),
            competing_explanations=(),
            falsification_rules=(),
            evidence_tiers=(),
            prohibited_interpretations=("Do not infer treatment response.",),
        )
    assert HypothesisStatus.PROPOSED.value == "proposed"
    assert HypothesisFindingCode.PROVISIONAL_ABI_PENDING_REVIEW.value
