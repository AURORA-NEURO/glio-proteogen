"""Focused contract/schema smoke for provisional M13-04."""

import pytest

from glio_proteogen.contracts.m13_04 import (
    M1304_OUTPUT_MEDIA_TYPE,
    M1304_PROVISIONAL_ABI,
    MechanismEstimate,
    MechanismEstimateKind,
    MechanismFindingCode,
    contract_json_schemas,
)

_SCHEMA_COUNT = 5


def test_provisional_schemas_require_counter_evidence_and_abstention() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["counterEvidenceRequired"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["primaryArchitecture"] == "isoform_aware_quantification"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1304_OUTPUT_MEDIA_TYPE
    assert M1304_PROVISIONAL_ABI is True


def test_posterior_requires_ordered_bounds_and_counter_evidence() -> None:
    with pytest.raises(ValueError, match="at least 1 item"):
        MechanismEstimate(
            estimate_id="estimate-1",
            mechanism_id="mechanism-1",
            label="Candidate mechanism",
            kind=MechanismEstimateKind.POSTERIOR,
            posterior_probability=0.7,
            lower_bound=0.8,
            upper_bound=0.9,
            assumptions=("Assay identity is resolved.",),
            alternatives=("Alternative mechanism remains possible.",),
            counter_evidence=(),
        )
    assert MechanismFindingCode.PROVISIONAL_ABI_PENDING_REVIEW.value
