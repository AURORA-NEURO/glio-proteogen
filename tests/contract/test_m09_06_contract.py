"""Focused contract/schema smoke for provisional M09-06."""

import pytest

from glio_proteogen.contracts.m09_06 import (
    M0906_MAX_COMPONENTS,
    M0906_NOMINAL_COVERAGE,
    M0906_OUTPUT_MEDIA_TYPE,
    M0906_PROVISIONAL_ABI,
    DecomposeComplexActivityUncertaintyVerification,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyDecompositionReplayReason,
    UncertaintyDimension,
    contract_json_schemas,
)

_SCHEMA_COUNT = 7


def test_provisional_schemas_require_seven_dimensions_and_sensitivity() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["sevenUncertaintyDimensionsRequired"]
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0906_OUTPUT_MEDIA_TYPE
    assert M0906_PROVISIONAL_ABI is True


def test_sensitivity_envelope_enforces_provisional_coverage_gate() -> None:
    envelope = SensitivityEnvelope(
        status=SensitivityEnvelopeStatus.EVALUATED,
        lower_bound=0.86,
        upper_bound=0.94,
        observed_coverage=0.9,
        rationale="Synthetic smoke coverage remains within the provisional gate.",
    )
    assert envelope.nominal_coverage == M0906_NOMINAL_COVERAGE
    assert len(tuple(UncertaintyDimension)) == M0906_MAX_COMPONENTS


def test_sensitivity_non_evaluated_cannot_smuggle_coverage() -> None:
    with pytest.raises(ValueError, match="evaluated sensitivity"):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.EVALUATED,
            rationale="missing bounds",
        )
    with pytest.raises(ValueError, match="non-evaluated"):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.ABSTAINED,
            observed_coverage=0.9,
            rationale="coverage must not be retained after abstention",
        )
    with pytest.raises(ValueError, match="85-95"):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.EVALUATED,
            lower_bound=0.8,
            upper_bound=0.99,
            observed_coverage=0.99,
            rationale="outside the provisional coverage gate",
        )


def test_replay_verification_flags_are_closed() -> None:
    valid = DecomposeComplexActivityUncertaintyVerification(
        content_verified=True,
        deterministic_verified=True,
        verified=True,
        result_digest="sha256:" + ("a" * 64),
        reason=UncertaintyDecompositionReplayReason.VERIFIED,
    )
    assert valid.verified is True
    with pytest.raises(ValueError, match="verified must equal"):
        DecomposeComplexActivityUncertaintyVerification(
            content_verified=True,
            deterministic_verified=False,
            verified=True,
            reason=UncertaintyDecompositionReplayReason.DIGEST_MISMATCH,
        )
