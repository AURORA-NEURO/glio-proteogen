"""Adversarial provenance and uncertainty replay tests for M09-04/07."""

from __future__ import annotations

from glio_proteogen.contracts.m09_04.canonical import result_payload_digest as digest_m0904
from glio_proteogen.contracts.m09_07.canonical import result_payload_digest as digest_m0907
from glio_proteogen.modules.c09_complex_stoichiometry import (
    m09_04_probabilistic_estimator as m0904,
)
from glio_proteogen.modules.c09_complex_stoichiometry import (
    m09_07_calibration_selective_prediction as m0907,
)
from tests.contract.test_m09_07_contract_hardening import _request as request_m0907
from tests.modules.c09_complex_stoichiometry.test_m09_04_estimator import _request as request_m0904
from tests.modules.test_m09_07_runtime import _candidate


def test_m0904_replay_rejects_recomputed_digest_with_forged_provenance() -> None:
    built = m0904.M0904ProbabilisticEstimator().build(request_m0904("stable_support"))
    forged = built.result.model_copy(
        update={"provenance": built.result.provenance.model_copy(update={"actor_id": "attacker"})}
    )
    forged = forged.model_copy(update={"result_digest": digest_m0904(forged)})

    assert not m0904.M0904ProbabilisticEstimator().verify(forged).verified


def test_m0907_replay_rejects_recomputed_digest_with_forged_provenance() -> None:
    request = request_m0907().model_copy(update={"candidate": _candidate()})
    result = m0907.M0907Service().execute(request)
    forged = result.model_copy(
        update={"provenance": result.provenance.model_copy(update={"actor_id": "attacker"})}
    )
    forged = forged.model_copy(update={"result_digest": digest_m0907(forged)})

    assert m0907.M0907Service.verify(forged) is False


def test_m0907_replay_rejects_recomputed_digest_with_forged_uncertainty() -> None:
    request = request_m0907().model_copy(update={"candidate": _candidate()})
    result = m0907.M0907Service().execute(request)
    forged = result.model_copy(
        update={"uncertainty": result.uncertainty.model_copy(update={"sensitivity_notes": ()})}
    )
    forged = forged.model_copy(update={"result_digest": digest_m0907(forged)})

    assert m0907.M0907Service.verify(forged) is False
