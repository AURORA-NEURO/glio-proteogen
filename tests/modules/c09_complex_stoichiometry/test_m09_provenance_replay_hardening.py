"""Adversarial provenance and uncertainty replay tests for M09-04/07."""

from __future__ import annotations

from glio_proteogen.contracts.m09_01.canonical import result_payload_digest as digest_m0901
from glio_proteogen.contracts.m09_02.canonical import result_payload_digest as digest_m0902
from glio_proteogen.contracts.m09_03.canonical import result_payload_digest as digest_m0903
from glio_proteogen.contracts.m09_04.canonical import result_payload_digest as digest_m0904
from glio_proteogen.contracts.m09_05.canonical import result_payload_digest as digest_m0905
from glio_proteogen.contracts.m09_06.canonical import result_payload_digest as digest_m0906
from glio_proteogen.contracts.m09_07.canonical import result_payload_digest as digest_m0907
from glio_proteogen.contracts.m09_08.canonical import result_payload_digest as digest_m0908
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c09_complex_activity import (
    m09_02_representation_feature_constructor as m0902,
)
from glio_proteogen.modules.c09_complex_activity import (
    m09_03_mature_baseline_estimator as m0903,
)
from glio_proteogen.modules.c09_complex_activity import (
    m09_05_mechanism_constraint_integrator as m0905,
)
from glio_proteogen.modules.c09_complex_stoichiometry import (
    m09_01_formal_state_feature_schema as m0901,
)
from glio_proteogen.modules.c09_complex_stoichiometry import (
    m09_04_probabilistic_estimator as m0904,
)
from glio_proteogen.modules.c09_complex_stoichiometry import (
    m09_06_uncertainty_decomposition_engine as m0906,
)
from glio_proteogen.modules.c09_complex_stoichiometry import (
    m09_07_calibration_selective_prediction as m0907,
)
from glio_proteogen.modules.c09_complex_stoichiometry import (
    m09_08_evidence_explanation_publisher as m0908,
)
from tests.contract.test_m09_07_contract_hardening import _request as request_m0907
from tests.modules.c09_complex_activity.test_m09_02_constructor import _request as request_m0902
from tests.modules.c09_complex_activity.test_m09_03_estimator import _request as request_m0903
from tests.modules.c09_complex_activity.test_m09_05_integrator import _request as request_m0905
from tests.modules.c09_complex_stoichiometry.test_m09_01_formal_state import (
    _request as request_m0901,
)
from tests.modules.c09_complex_stoichiometry.test_m09_04_estimator import _request as request_m0904
from tests.modules.c09_complex_stoichiometry.test_m09_06_uncertainty import (
    _request as request_m0906,
)
from tests.modules.c09_complex_stoichiometry.test_m09_08_publisher import _request as request_m0908
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


def test_m0901_replay_rejects_recomputed_digest_with_forged_provenance() -> None:
    built = m0901.M0901Service().execute(request_m0901())
    forged = built.result.model_copy(
        update={"provenance": built.result.provenance.model_copy(update={"actor_id": "attacker"})}
    )
    forged = forged.model_copy(update={"result_digest": digest_m0901(forged)})

    outcome = m0901.M0901FormalStateEngine.verify(
        forged,
        canonical_json_bytes(forged.model_dump(mode="json")),
    )
    assert outcome.verified is False


def test_m0902_replay_rejects_recomputed_digest_with_forged_provenance() -> None:
    built = m0902.M0902RepresentationConstructor().construct(request_m0902())
    forged = built.result.model_copy(
        update={"provenance": built.result.provenance.model_copy(update={"actor_id": "attacker"})}
    )
    forged = forged.model_copy(update={"result_digest": digest_m0902(forged)})

    assert m0902.M0902RepresentationConstructor().verify(forged) is False


def test_m0903_replay_rejects_recomputed_digest_with_forged_provenance() -> None:
    built = m0903.M0903BaselineEstimator().construct(request_m0903())
    forged = built.result.model_copy(
        update={"provenance": built.result.provenance.model_copy(update={"actor_id": "attacker"})}
    )
    forged = forged.model_copy(update={"result_digest": digest_m0903(forged)})

    assert m0903.M0903BaselineEstimator().verify(forged) is False


def test_m0905_replay_rejects_recomputed_digest_with_forged_provenance() -> None:
    built = m0905.M0905ConstraintIntegrator().integrate(request_m0905("conservation_hold"))
    forged = built.result.model_copy(
        update={"provenance": built.result.provenance.model_copy(update={"actor_id": "attacker"})}
    )
    forged = forged.model_copy(update={"result_digest": digest_m0905(forged)})

    assert m0905.M0905ConstraintIntegrator().verify(forged).verified is False


def test_m0906_replay_rejects_recomputed_digest_with_forged_provenance() -> None:
    built = m0906.M0906Service().execute(request_m0906())
    forged = built.result.model_copy(
        update={"provenance": built.result.provenance.model_copy(update={"actor_id": "attacker"})}
    )
    forged = forged.model_copy(update={"result_digest": digest_m0906(forged)})

    outcome = m0906.M0906UncertaintyDecompositionEngine.verify(
        forged,
        canonical_json_bytes(forged.model_dump(mode="json")),
    )
    assert outcome.verified is False


def test_m0908_replay_rejects_recomputed_digest_with_forged_provenance() -> None:
    built = m0908.M0908EvidencePublisher().publish(request_m0908())
    forged = built.result.model_copy(
        update={"provenance": built.result.provenance.model_copy(update={"actor_id": "attacker"})}
    )
    forged = forged.model_copy(update={"result_digest": digest_m0908(forged)})

    assert m0908.M0908EvidencePublisher().verify(forged).verified is False
