"""Tests for the coupled, glioma-specific M06-04 research optimizer."""

from __future__ import annotations

from glio_proteogen.contracts.m06_01 import (
    FormalProteinStateSchema,
    FormalStateFeatureDefinition,
    FormalStateFeatureValue,
    FormalStateFeatureValueKind,
    FormalStateMissingness,
)
from glio_proteogen.contracts.m06_04 import ProbabilisticEstimatorFamily
from glio_proteogen.modules.c06_protein_abundance.m06_04_probabilistic_advanced_estimator import (
    M0604_GLIOMA_PROGRAM_IRLS_OPTIMIZER,
    M0604ProbabilisticEstimatorEngine,
)
from tests.contract.test_m06_04_hardening import _artifact, _configuration, _context

_EXPECTED_ESTIMATE_COUNT = 4
_POSTERIOR_MASS = 0.9


def _schema(feature_ids: tuple[str, ...]) -> FormalProteinStateSchema:
    return FormalProteinStateSchema(
        schema_id="schema.m0604.glioma-program",
        version="1.0.0",
        features=tuple(
            FormalStateFeatureDefinition(
                feature_id=feature_id,
                version="1.0.0",
                value_kind=FormalStateFeatureValueKind.SCALAR,
                unit="normalized-abundance",
                allowed_missingness=(
                    FormalStateMissingness.OBSERVED,
                    FormalStateMissingness.MISSING,
                    FormalStateMissingness.UNSUPPORTED,
                ),
                domain_lower=0.0,
            )
            for feature_id in feature_ids
        ),
    )


def _request(*, missing_mki67: bool = False) -> dict[str, object]:
    feature_ids = ("protein.egfr", "protein.pik3ca", "protein.tp53", "protein.mki67")
    schema = _schema(feature_ids)
    values = tuple(
        FormalStateFeatureValue(
            feature_id=feature_id,
            state=(
                FormalStateMissingness.MISSING
                if missing_mki67 and feature_id == "protein.mki67"
                else FormalStateMissingness.OBSERVED
            ),
            unit="normalized-abundance",
            scalar_value=(None if missing_mki67 and feature_id == "protein.mki67" else value),
        )
        for feature_id, value in zip(feature_ids, (2.4, 2.0, 0.3, 2.2), strict=True)
    )
    return {
        "request_id": "request.m0604.glioma-program",
        "context": _context(),
        "state_schema": schema,
        "feature_values": values,
        "representation_artifact": _artifact("representation", 3),
        "baseline_result_digest": None,
        "configuration": _configuration(
            schema,
            family=ProbabilisticEstimatorFamily.MECHANISM_GUIDED,
            optimizer=M0604_GLIOMA_PROGRAM_IRLS_OPTIMIZER,
        ),
        "source_artifacts": (_artifact("source", 4),),
        "supersedes_result_digest": None,
    }


def test_coupled_glioma_program_fit_is_replayable_and_signed() -> None:
    engine = M0604ProbabilisticEstimatorEngine()
    result = engine.estimate(_request())
    replay = engine.estimate(result.request.model_dump(mode="json"))

    assert result == replay
    assert result.status.value == "estimated"
    assert len(result.estimates) == _EXPECTED_ESTIMATE_COUNT
    assert result.diagnostics[0].diagnostic_id == "diagnostic.m0604.glioma_program"
    assert "signed programs" in result.diagnostics[0].message
    assert all(item.posterior_mass == _POSTERIOR_MASS for item in result.estimates)


def test_coupled_glioma_program_gate_abstains_without_two_programs() -> None:
    request = _request(missing_mki67=True)
    request["feature_values"] = (
        *(
            value
            for value in request["feature_values"]
            if value.feature_id != "protein.mki67"
        ),
        FormalStateFeatureValue(
            feature_id="protein.mki67",
            state=FormalStateMissingness.MISSING,
            unit="normalized-abundance",
        ),
    )
    # Three observed markers are below the support gate even though two
    # programs are represented.
    result = M0604ProbabilisticEstimatorEngine().estimate(request)
    assert result.status.value == "abstained"
    assert "at least four" in (result.abstention_reason or "")
    assert not result.estimates
