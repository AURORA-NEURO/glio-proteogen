"""Focused contract/schema smoke for provisional M12-01."""

from typing import cast

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
    metadata = [cast("dict[str, object]", schema["x-glio-contract"]) for schema in schemas.values()]
    assert all(item["provisionalAbi"] for item in metadata)
    assert all(item["pendingOwnerConfirmation"] for item in metadata)
    assert all(
        item["competingExplanationsRequired"] and item["falsificationRulesRequired"]
        for item in metadata
    )
    assert all(item["primaryArchitecture"] == "bayesian_factor_analysis" for item in metadata)
    assert metadata[list(schemas).index("output")]["outputMediaType"] == M1201_OUTPUT_MEDIA_TYPE
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
